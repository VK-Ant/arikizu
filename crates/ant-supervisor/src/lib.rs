//! Worker lifecycle supervisor.
//!
//! Spawns Python workers as child processes, routes capability calls to
//! them over Unix sockets, restarts them on failure.

pub mod events;
pub mod pipeline;
pub mod policy;

pub use events::{Event, EventBus};
pub use pipeline::{run_pipeline, validate_pipeline, PipelineRun, RunStatus, StageResult};
pub use policy::{Enforcement, Policy, load_policies};

use ant_common::{ArikizuError, Result, WorkerState};
use ant_ipc::{bind_supervisor, read_frame, write_frame, Frame};
use dashmap::DashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, oneshot, Mutex};
use tokio::time::{timeout, Duration};
use uuid::Uuid;

/// Per-worker configuration.
#[derive(Debug, Clone)]
pub struct WorkerConfig {
    pub name: String,
    pub python_path: PathBuf,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub env: Vec<(String, String)>,
    pub max_memory_mb: Option<u64>,
}

impl WorkerConfig {
    /// Build a WorkerConfig from the ant-common WorkerSpec in arikizu.yaml.
    /// Empty `spec.args` defaults to `["-m", <module>]`.
    pub fn from_spec(spec: &ant_common::WorkerSpec) -> Self {
        let args = if spec.args.is_empty() {
            vec!["-m".into(), spec.module.clone()]
        } else {
            spec.args.clone()
        };
        Self {
            name: spec.name.clone(),
            python_path: PathBuf::from(&spec.python),
            args,
            cwd: spec.cwd.as_ref().map(PathBuf::from),
            env: spec.env.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
            max_memory_mb: spec.max_memory_mb,
        }
    }
}

/// A handle to a spawned worker.
pub struct WorkerHandle {
    pub name: String,
    pub state: Arc<Mutex<WorkerState>>,
    pub pending_calls: Arc<DashMap<Uuid, oneshot::Sender<Result<serde_json::Value>>>>,
    sender: mpsc::UnboundedSender<Frame>,
}

impl WorkerHandle {
    /// Invoke a capability on this worker and await the result.
    pub async fn call(&self, capability: &str, payload: serde_json::Value, timeout_ms: u64) -> Result<serde_json::Value> {
        let id = Uuid::new_v4();
        let (tx, rx) = oneshot::channel();
        self.pending_calls.insert(id, tx);

        let frame = Frame::Call {
            id,
            capability: capability.into(),
            payload,
        };
        self.sender.send(frame).map_err(|e| ArikizuError::Ipc(e.to_string()))?;

        match timeout(Duration::from_millis(timeout_ms), rx).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => Err(ArikizuError::Ipc("response channel closed".into())),
            Err(_) => {
                self.pending_calls.remove(&id);
                Err(ArikizuError::Timeout { timeout_ms })
            }
        }
    }

    pub async fn current_state(&self) -> WorkerState {
        *self.state.lock().await
    }
}

/// The supervisor owns and arbitrates all workers.
pub struct Supervisor {
    socket_dir: PathBuf,
    workers: DashMap<String, Arc<WorkerHandle>>,
    children: Mutex<Vec<Child>>,
    pub bus: EventBus,
    pub started_at: std::time::Instant,
}

impl Supervisor {
    pub fn new(socket_dir: PathBuf) -> Result<Self> {
        std::fs::create_dir_all(&socket_dir)?;
        Ok(Self {
            socket_dir,
            workers: DashMap::new(),
            children: Mutex::new(Vec::new()),
            bus: EventBus::new(1024),
            started_at: std::time::Instant::now(),
        })
    }

    /// Uptime in seconds since this supervisor was constructed.
    pub fn uptime_s(&self) -> u64 {
        self.started_at.elapsed().as_secs()
    }

    /// Spawn a worker as a child process and start the IPC loop.
    pub async fn spawn_worker(&self, config: WorkerConfig) -> Result<Arc<WorkerHandle>> {
        let socket_path = self.socket_dir.join(format!("{}.sock", config.name));
        let listener = bind_supervisor(&socket_path).await?;

        // Spawn the Python child
        let mut cmd = Command::new(&config.python_path);
        cmd.args(&config.args);
        cmd.env("ARIKIZU_SOCKET", &socket_path);
        if let Some(cwd) = &config.cwd {
            cmd.current_dir(cwd);
        }
        for (k, v) in &config.env {
            cmd.env(k, v);
        }

        let child = cmd.spawn().map_err(ArikizuError::Io)?;
        self.children.lock().await.push(child);
        tracing::info!(worker = %config.name, socket = %socket_path.display(), "worker spawned");

        // Accept the worker's connection. 60s window covers first-run uv/pip
        // dep downloads; a healthy worker connects back in under a second.
        let stream = match timeout(Duration::from_secs(60), listener.accept()).await {
            Ok(Ok((stream, _))) => stream,
            Ok(Err(e)) => return Err(ArikizuError::Io(e)),
            Err(_) => return Err(ArikizuError::Timeout { timeout_ms: 60_000 }),
        };

        // Create channels for sending frames to the worker
        let (tx, mut rx) = mpsc::unbounded_channel::<Frame>();
        let pending_calls: Arc<DashMap<Uuid, oneshot::Sender<Result<serde_json::Value>>>> =
            Arc::new(DashMap::new());

        let state = Arc::new(Mutex::new(WorkerState::Initializing));
        let handle = Arc::new(WorkerHandle {
            name: config.name.clone(),
            state: Arc::clone(&state),
            pending_calls: Arc::clone(&pending_calls),
            sender: tx,
        });

        // Split the stream for concurrent read/write
        let (mut reader, mut writer) = stream.into_split();

        // Spawn writer task
        tokio::spawn(async move {
            while let Some(frame) = rx.recv().await {
                if let Err(e) = write_frame(&mut writer, &frame).await {
                    tracing::error!(error = %e, "writer error");
                    break;
                }
            }
        });

        // Spawn reader task
        let name = config.name.clone();
        let state_r = Arc::clone(&state);
        let pending_r = Arc::clone(&pending_calls);
        let bus_r = self.bus.clone();
        tokio::spawn(async move {
            loop {
                match read_frame(&mut reader).await {
                    Ok(Frame::Hello { worker, version, capabilities }) => {
                        tracing::info!(worker = %worker, version, cap_count = capabilities.len(), "worker hello");
                        *state_r.lock().await = WorkerState::Ready;
                        bus_r.publish(Event::new(
                            "worker.ready",
                            &worker,
                            serde_json::json!({"version": version, "capabilities": capabilities}),
                        ));
                    }
                    Ok(Frame::Reply { id, result }) => {
                        if let Some((_, sender)) = pending_r.remove(&id) {
                            let _ = sender.send(Ok(result));
                        }
                    }
                    Ok(Frame::Error { id, error }) => {
                        if let Some((_, sender)) = pending_r.remove(&id) {
                            let _ = sender.send(Err(ArikizuError::Other(error)));
                        }
                    }
                    Ok(Frame::Heartbeat { memory_rss_mb, queue_depth, in_flight, resident_models }) => {
                        bus_r.publish(Event::new(
                            "worker.heartbeat",
                            &name,
                            serde_json::json!({
                                "memory_rss_mb": memory_rss_mb,
                                "queue_depth": queue_depth,
                                "in_flight": in_flight,
                                "resident_models": resident_models,
                            }),
                        ));
                    }
                    Ok(Frame::Event { subject, payload }) => {
                        tracing::debug!(subject = %subject, "worker event");
                        bus_r.publish(Event::new(subject, &name, payload));
                    }
                    Ok(_) => {}
                    Err(e) => {
                        tracing::error!(worker = %name, error = %e, "reader error, worker likely dead");
                        *state_r.lock().await = WorkerState::Unhealthy;
                        bus_r.publish(Event::new(
                            "worker.died",
                            &name,
                            serde_json::json!({"error": e.to_string()}),
                        ));
                        break;
                    }
                }
            }
        });

        self.workers.insert(config.name.clone(), Arc::clone(&handle));
        Ok(handle)
    }

    pub fn worker(&self, name: &str) -> Option<Arc<WorkerHandle>> {
        self.workers.get(name).map(|e| Arc::clone(e.value()))
    }

    pub fn worker_names(&self) -> Vec<String> {
        self.workers.iter().map(|e| e.key().clone()).collect()
    }

    /// Shutdown: drain workers, terminate children.
    pub async fn shutdown(&self) -> Result<()> {
        for entry in self.workers.iter() {
            *entry.value().state.lock().await = WorkerState::Draining;
        }
        tokio::time::sleep(Duration::from_secs(2)).await;

        let mut children = self.children.lock().await;
        for mut child in children.drain(..) {
            let _ = child.kill().await;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    #[tokio::test]
    async fn supervisor_creates_socket_dir() {
        let tmp = env::temp_dir().join(format!("arikizu-test-{}", Uuid::new_v4()));
        let supervisor = Supervisor::new(tmp.clone()).unwrap();
        assert!(tmp.exists());
        // Workers map should start empty
        assert_eq!(supervisor.worker_names().len(), 0);
        std::fs::remove_dir_all(&tmp).ok();
    }
}

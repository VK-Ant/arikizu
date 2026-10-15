//! The `arikizu` binary. Entry point for the whole runtime.

use ant_common::{ArikizuConfig, WorkerSpec};
use ant_devices::DeviceInventory;
use ant_feedback::{AuditLog, FeedbackManager};
use ant_http::AppState;
use ant_router::CapabilityRegistry;
use ant_supervisor::{Supervisor, WorkerConfig};
use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use std::collections::HashSet;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

#[derive(Parser)]
#[command(name = "arikizu", version, about = "Edge-first, offline-first, responsible-AI runtime")]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Path to arikizu.yaml
    #[arg(long, global = true, default_value = "arikizu.yaml")]
    config: PathBuf,

    /// Path to capabilities.toml
    #[arg(long, global = true, default_value = "capabilities.toml")]
    capabilities: PathBuf,

    /// Directory for Unix sockets
    #[arg(long, global = true, default_value = "/tmp/arikizu")]
    socket_dir: PathBuf,
}

#[derive(Subcommand)]
enum Commands {
    /// Scaffold a new pipeline project
    Init {
        /// Project name
        name: String,
    },

    /// Start the runtime foreground
    Run {
        /// Override HTTP bind address (otherwise taken from arikizu.yaml)
        #[arg(long)]
        bind: Option<String>,

        /// Start as service (no stdin/stdout prompts)
        #[arg(long)]
        service: bool,

        /// Skip spawning workers (HTTP-only mode, useful for dev)
        #[arg(long)]
        no_workers: bool,
    },

    /// Show runtime health status
    Status {
        /// Output as JSON
        #[arg(long)]
        json: bool,

        /// Dev mode (do not require running runtime)
        #[arg(long)]
        dev: bool,
    },

    /// Call a capability
    Call {
        /// Capability name, e.g. vision.detect
        capability: String,

        /// JSON payload
        #[arg(default_value = "{}")]
        payload: String,
    },

    /// List installed workers and capabilities
    List,

    /// Pull a worker and its models
    Pull {
        /// Worker name
        worker: String,
    },

    /// Submit human feedback
    #[command(subcommand)]
    Feedback(FeedbackCmd),

    /// Validate configuration
    Validate {
        #[arg(default_value = "arikizu.yaml")]
        config: PathBuf,
    },

    /// Run a pipeline synchronously by name
    RunPipeline {
        /// Pipeline name (as declared in arikizu.yaml `name:`)
        name: String,
    },

    /// Stop the runtime
    Stop,
}

#[derive(Subcommand)]
enum FeedbackCmd {
    /// Rate a response (good/bad)
    Rate {
        query_id: uuid::Uuid,
        /// good or bad
        label: String,
        #[arg(long)]
        note: Option<String>,
    },

    /// List pending approvals
    Pending,

    /// Approve a pending action
    Approve {
        action_id: uuid::Uuid,
        #[arg(long, default_value = "cli")]
        approver: String,
    },

    /// Reject a pending action
    Reject {
        action_id: uuid::Uuid,
        #[arg(long)]
        reason: String,
        #[arg(long, default_value = "cli")]
        approver: String,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let cli = Cli::parse();

    // Split off `command` so the rest of `cli` (config paths, socket_dir) can
    // still be borrowed when a subcommand needs it.
    let Cli { command, config, capabilities, socket_dir } = cli;
    let cli_rest = Cli {
        command: Commands::Stop, // placeholder; cmd_* don't look at command
        config,
        capabilities,
        socket_dir,
    };

    match command {
        Commands::Init { name } => cmd_init(&name),
        Commands::Run { bind, service, no_workers } => cmd_run(&cli_rest, bind.as_deref(), service, no_workers).await,
        Commands::Status { json, dev } => cmd_status(json, dev).await,
        Commands::Call { capability, payload } => cmd_call(&cli_rest, &capability, &payload).await,
        Commands::List => cmd_list(&cli_rest),
        Commands::Pull { worker } => cmd_pull(&worker),
        Commands::Feedback(sub) => cmd_feedback(sub).await,
        Commands::Validate { config } => cmd_validate(&config),
        Commands::RunPipeline { name } => cmd_run_pipeline(&cli_rest, &name).await,
        Commands::Stop => cmd_stop().await,
    }
}

fn cmd_init(name: &str) -> Result<()> {
    let dir = PathBuf::from(name);
    std::fs::create_dir_all(&dir).context("creating project dir")?;

    let yaml = format!(
        r#"name: {name}

devices: {{}}

pipeline: []

workers: []

reasoning:
  provider: ollama
  model: qwen2.5:3b-instruct-q4_K_M

feedback:
  review_queue:
    retain_hours: 72
    max_pending: 500
  approvers:
    - operator

runtime:
  offline: true
  http_api: 127.0.0.1:7000
  socket_dir: /tmp/arikizu
"#
    );
    std::fs::write(dir.join("arikizu.yaml"), yaml)?;
    std::fs::write(
        dir.join("capabilities.toml"),
        "# capabilities.toml — define routed capabilities here.\n",
    )?;
    std::fs::create_dir_all(dir.join("policies"))?;
    std::fs::create_dir_all(dir.join("models"))?;
    std::fs::create_dir_all(dir.join("golden"))?;

    println!("Initialized project `{name}`.");
    println!("Next: cd {name} && arikizu run");
    Ok(())
}

async fn cmd_run(cli: &Cli, bind_override: Option<&str>, _service: bool, no_workers: bool) -> Result<()> {
    tracing::info!("Arikizu starting");

    // Load config (fallback to defaults if arikizu.yaml does not exist yet).
    let config = if cli.config.exists() {
        ArikizuConfig::load(&cli.config).context("loading arikizu.yaml")?
    } else {
        tracing::warn!("arikizu.yaml not found at {:?}; using defaults", cli.config);
        ArikizuConfig {
            name: "default".into(),
            devices: Default::default(),
            pipeline: vec![],
            workers: vec![],
            reasoning: None,
            feedback: None,
            policies: vec![],
            runtime: Default::default(),
        }
    };

    tracing::info!(name = %config.name, "loaded pipeline config");

    // Capability registry.
    let registry = if cli.capabilities.exists() {
        Arc::new(CapabilityRegistry::load(&cli.capabilities)?)
    } else {
        tracing::warn!("capabilities.toml not found; starting with empty registry");
        Arc::new(CapabilityRegistry::load_from_str("")?)
    };
    tracing::info!(count = registry.len(), "capability registry loaded");

    // Policies.
    let policies_dir = PathBuf::from("./policies");
    let policies = ant_supervisor::load_policies(&policies_dir)?;
    tracing::info!(count = policies.len(), "policies loaded");

    // Audit log.
    let audit = Arc::new(
        AuditLog::open(&config.runtime.db_path)
            .with_context(|| format!("opening audit db at {}", config.runtime.db_path))?,
    );
    audit.append("runtime.started", None, Some(&config.name), &serde_json::json!({}))?;

    // Supervisor.
    let socket_dir = PathBuf::from(&config.runtime.socket_dir);
    let supervisor = Arc::new(Supervisor::new(socket_dir)?);

    // Feedback Manager.
    let feedback = Arc::new(FeedbackManager::new().with_audit(Arc::clone(&audit)));

    // Spawn workers if any are declared and --no-workers was not passed.
    if !no_workers {
        let specs = inferred_workers(&config, &registry);
        for spec in specs {
            match supervisor
                .spawn_worker(WorkerConfig::from_spec(&spec))
                .await
            {
                Ok(_) => tracing::info!(worker = %spec.name, "worker spawned"),
                Err(e) => tracing::error!(worker = %spec.name, error = %e, "worker failed to spawn"),
            }
        }
    }

    let state = AppState {
        supervisor: Arc::clone(&supervisor),
        registry: Arc::clone(&registry),
        feedback: Arc::clone(&feedback),
        audit: Arc::clone(&audit),
        config: Arc::new(config.clone()),
    };

    let bind = bind_override.unwrap_or(&config.runtime.http_api);
    let addr: SocketAddr = bind.parse().context("parsing bind address")?;
    tracing::info!(%addr, "starting HTTP server");

    tokio::select! {
        res = ant_http::serve(addr, state) => {
            if let Err(e) = res {
                tracing::error!(error = %e, "HTTP server error");
            }
        }
        _ = tokio::signal::ctrl_c() => {
            tracing::info!("received Ctrl+C, shutting down");
            supervisor.shutdown().await?;
            audit.append("runtime.stopped", None, None, &serde_json::json!({}))?;
        }
    }

    Ok(())
}

/// Choose which workers to spawn:
///   - if `workers:` is declared in arikizu.yaml, use that
///   - otherwise infer from capabilities.toml (one spec per distinct `worker` field)
fn inferred_workers(config: &ArikizuConfig, registry: &CapabilityRegistry) -> Vec<WorkerSpec> {
    if !config.workers.is_empty() {
        return config.workers.clone();
    }
    let mut seen: HashSet<String> = HashSet::new();
    let mut specs = Vec::new();
    for cap in registry.capabilities.values() {
        if seen.insert(cap.worker.clone()) {
            let module = format!("{}_worker", cap.worker);
            specs.push(WorkerSpec {
                name: cap.worker.clone(),
                module: module.clone(),
                python: "uv".to_string(),
                args: vec![
                    "run".into(),
                    "--package".into(),
                    format!("{}-worker", cap.worker),
                    "python".into(),
                    "-m".into(),
                    module,
                ],
                env: Default::default(),
                cwd: Some("./workers".into()),
                max_memory_mb: None,
            });
        }
    }
    specs
}

async fn cmd_status(json: bool, dev: bool) -> Result<()> {
    if dev {
        let inv = DeviceInventory::detect()?;
        if json {
            println!("{}", serde_json::to_string_pretty(&inv)?);
        } else {
            println!("Arikizu v{}", env!("CARGO_PKG_VERSION"));
            println!("Platform: {}", inv.platform);
            println!("Jetson: {}", inv.is_jetson);
            println!("CPUs: {} cores", inv.cpus.first().map(|c| c.cores).unwrap_or(0));
            println!("GPUs: {}", inv.gpus.len());
            println!("Memory: {} MB", inv.total_memory_mb);
        }
        return Ok(());
    }

    let url = "http://127.0.0.1:7000/api/v1/status";
    match reqwest::get(url).await {
        Ok(resp) => {
            let body = resp.text().await.unwrap_or_default();
            if json {
                println!("{body}");
            } else {
                println!("Runtime: {body}");
            }
            Ok(())
        }
        Err(e) => {
            eprintln!("Could not reach runtime: {e}");
            eprintln!("Is `arikizu run` running? Try `arikizu status --dev` for offline info.");
            std::process::exit(1);
        }
    }
}

async fn cmd_call(_cli: &Cli, capability: &str, payload: &str) -> Result<()> {
    let payload_val: serde_json::Value =
        serde_json::from_str(payload).context("payload is not valid JSON")?;

    let (domain, op) = capability
        .split_once('.')
        .with_context(|| format!("capability must be <domain>.<op>, got `{capability}`"))?;

    let url = format!("http://127.0.0.1:7000/api/v1/call/{domain}/{op}");
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "payload": payload_val }))
        .send()
        .await
        .context("calling runtime")?;

    let status = resp.status();
    let body = resp.text().await.unwrap_or_default();
    if status.is_success() {
        println!("{body}");
    } else {
        eprintln!("HTTP {status}: {body}");
        std::process::exit(1);
    }
    Ok(())
}

fn cmd_list(cli: &Cli) -> Result<()> {
    if !cli.capabilities.exists() {
        println!("No capabilities.toml found at {:?}", cli.capabilities);
        return Ok(());
    }
    let registry = CapabilityRegistry::load(&cli.capabilities)?;
    println!("Registered capabilities ({}):", registry.len());
    let mut names: Vec<&str> = registry.names().collect();
    names.sort();
    for name in names {
        if let Ok(spec) = registry.get(name) {
            println!("  {:30} {:10} {}ms", name, spec.worker, spec.timeout_ms);
        }
    }
    Ok(())
}

fn cmd_pull(worker: &str) -> Result<()> {
    println!("pull {worker}");
    println!("Not yet implemented. See Weekend 15 in docs/PLAN.md.");
    Ok(())
}

async fn cmd_feedback(sub: FeedbackCmd) -> Result<()> {
    let base = "http://127.0.0.1:7000/api/v1/feedback";
    let client = reqwest::Client::new();
    match sub {
        FeedbackCmd::Rate { query_id, label, note } => {
            let r = client
                .post(format!("{base}/rate"))
                .json(&serde_json::json!({ "query_id": query_id, "label": label, "note": note }))
                .send()
                .await?;
            println!("rate: {}", r.status());
        }
        FeedbackCmd::Pending => {
            let r = client.get(format!("{base}/pending")).send().await?;
            println!("{}", r.text().await.unwrap_or_default());
        }
        FeedbackCmd::Approve { action_id, approver } => {
            let r = client
                .post(format!("{base}/approve"))
                .json(&serde_json::json!({ "action_id": action_id, "approver": approver }))
                .send()
                .await?;
            println!("approve: {}", r.status());
        }
        FeedbackCmd::Reject { action_id, reason, approver } => {
            let r = client
                .post(format!("{base}/reject"))
                .json(&serde_json::json!({ "action_id": action_id, "approver": approver, "reason": reason }))
                .send()
                .await?;
            println!("reject: {}", r.status());
        }
    }
    Ok(())
}

fn cmd_validate(config: &PathBuf) -> Result<()> {
    let content = std::fs::read_to_string(config).context("reading config")?;
    let _parsed: ArikizuConfig = serde_yaml::from_str(&content).context("parsing arikizu.yaml")?;
    println!("Config at {config:?} is valid.");
    Ok(())
}

async fn cmd_run_pipeline(_cli: &Cli, name: &str) -> Result<()> {
    let url = format!("http://127.0.0.1:7000/api/v1/pipeline/run");
    let client = reqwest::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "name": name }))
        .send()
        .await?;
    println!("{}", resp.text().await.unwrap_or_default());
    Ok(())
}

async fn cmd_stop() -> Result<()> {
    let url = "http://127.0.0.1:7000/api/v1/stop";
    match reqwest::Client::new().post(url).send().await {
        Ok(r) => println!("stop: {}", r.status()),
        Err(e) => eprintln!("could not reach runtime: {e}"),
    }
    Ok(())
}

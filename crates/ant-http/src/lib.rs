//! Local HTTP server for Dashboard and REST API.
//!
//! Serves the embedded SvelteKit static files at `/` and the REST
//! API under `/api/v1/`. Binds to 127.0.0.1:7000 by default.

use ant_common::{ArikizuConfig, Result};
use ant_devices::DeviceInventory;
use ant_feedback::{AuditLog, FeedbackManager};
use ant_router::CapabilityRegistry;
use ant_supervisor::{run_pipeline, Supervisor};
use axum::{
    extract::{ws::{Message, WebSocket, WebSocketUpgrade}, Path as AxumPath, Query, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::path::Path;
use std::sync::Arc;
use tower_http::services::ServeDir;
use uuid::Uuid;

#[derive(Clone)]
pub struct AppState {
    pub supervisor: Arc<Supervisor>,
    pub registry: Arc<CapabilityRegistry>,
    pub feedback: Arc<FeedbackManager>,
    pub audit: Arc<AuditLog>,
    pub config: Arc<ArikizuConfig>,
}

pub fn build_router(state: AppState) -> Router {
    let mut router = Router::new()
        .route("/api/v1/status", get(get_status))
        .route("/api/v1/devices", get(get_devices))
        .route("/api/v1/capabilities", get(list_capabilities))
        .route("/api/v1/workers", get(list_workers))
        .route("/api/v1/call/:domain/:op", post(call_capability))
        .route("/api/v1/feedback/rate", post(feedback_rate))
        .route("/api/v1/feedback/correct", post(feedback_correct))
        .route("/api/v1/feedback/approve", post(feedback_approve))
        .route("/api/v1/feedback/reject", post(feedback_reject))
        .route("/api/v1/feedback/annotate", post(feedback_annotate))
        .route("/api/v1/feedback/pending", get(feedback_pending))
        .route("/api/v1/pipeline/config", get(get_pipeline_config))
        .route("/api/v1/pipeline/run", post(run_pipeline_route))
        .route("/api/v1/audit", get(get_audit))
        .route("/api/v1/events", get(ws_events))
        .route("/api/v1/runtime", get(get_runtime))
        .route("/api/v1/stop", post(stop_runtime))
        .route("/health", get(health));

    // Serve the zero-dep demo sandbox at /demo when demo/web exists.
    // ant-http's cwd is wherever `arikizu run` was launched; the repo root
    // is the normal case, where demo/web/index.html lives.
    if Path::new("demo/web/index.html").exists() {
        router = router.nest_service("/demo", ServeDir::new("demo/web"));
        tracing::info!("serving demo sandbox at /demo");
    }

    // Serve the operator dashboard at / when ui/static exists.
    // This is the polished home page the user lands on; the dev sandbox
    // stays at /demo for raw capability testing.
    if Path::new("ui/static/index.html").exists() {
        router = router.fallback_service(ServeDir::new("ui/static"));
        tracing::info!("serving operator dashboard at /");
    }

    router.with_state(state)
}

pub async fn serve(addr: SocketAddr, state: AppState) -> Result<()> {
    let router = build_router(state);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!(?addr, "HTTP server listening");
    axum::serve(listener, router)
        .await
        .map_err(|e| ant_common::ArikizuError::Other(e.to_string()))?;
    Ok(())
}

// -------- Status --------

#[derive(Serialize)]
struct DeviceSummary {
    platform: String,
    is_jetson: bool,
    cpus: usize,
    gpus: usize,
}

#[derive(Serialize)]
struct WorkerSummary {
    name: String,
    state: String,
    capabilities: Vec<String>,
}

#[derive(Serialize)]
struct StatusResponse {
    runtime: String,
    version: String,
    uptime_s: u64,
    pipeline: String,
    workers: Vec<WorkerSummary>,
    device: DeviceSummary,
    capability_count: usize,
    audit_rows: i64,
    pending_approvals: usize,
}

async fn get_status(State(state): State<AppState>) -> impl IntoResponse {
    let inv = DeviceInventory::detect().unwrap_or_else(|_| DeviceInventory {
        platform: "unknown".into(),
        is_jetson: false,
        cpus: vec![],
        gpus: vec![],
        total_memory_mb: 0,
    });

    let mut workers = Vec::new();
    for name in state.supervisor.worker_names() {
        if let Some(h) = state.supervisor.worker(&name) {
            let state_s = format!("{:?}", h.current_state().await);
            let caps: Vec<String> = state
                .registry
                .by_worker(&name)
                .map(|(k, _)| k.clone())
                .collect();
            workers.push(WorkerSummary {
                name: name.clone(),
                state: state_s,
                capabilities: caps,
            });
        }
    }

    Json(StatusResponse {
        runtime: "arikizu".into(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        uptime_s: state.supervisor.uptime_s(),
        pipeline: state.config.name.clone(),
        workers,
        device: DeviceSummary {
            platform: inv.platform,
            is_jetson: inv.is_jetson,
            cpus: inv.cpus.first().map(|c| c.cores as usize).unwrap_or(0),
            gpus: inv.gpus.len(),
        },
        capability_count: state.registry.len(),
        audit_rows: state.audit.count().unwrap_or(0),
        pending_approvals: state.feedback.pending_approvals().len(),
    })
}

async fn get_devices() -> impl IntoResponse {
    match DeviceInventory::detect() {
        Ok(inv) => Json(inv).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn list_capabilities(State(state): State<AppState>) -> impl IntoResponse {
    let mut caps: Vec<serde_json::Value> = Vec::new();
    for name in state.registry.names() {
        if let Ok(spec) = state.registry.get(name) {
            caps.push(serde_json::json!({
                "name": name,
                "worker": spec.worker,
                "timeout_ms": spec.timeout_ms,
                "priority": spec.priority,
            }));
        }
    }
    Json(caps).into_response()
}

async fn list_workers(State(state): State<AppState>) -> impl IntoResponse {
    let mut out = Vec::new();
    for name in state.supervisor.worker_names() {
        if let Some(h) = state.supervisor.worker(&name) {
            out.push(serde_json::json!({
                "name": name,
                "state": format!("{:?}", h.current_state().await),
                "capabilities": state.registry.by_worker(&name).map(|(k, _)| k.clone()).collect::<Vec<_>>(),
            }));
        }
    }
    Json(out).into_response()
}

// -------- Call --------

#[derive(Deserialize)]
struct CallBody {
    #[serde(default)]
    payload: serde_json::Value,
}

async fn call_capability(
    State(state): State<AppState>,
    AxumPath((domain, op)): AxumPath<(String, String)>,
    Json(body): Json<CallBody>,
) -> impl IntoResponse {
    let full_name = format!("{domain}.{op}");

    let spec = match state.registry.get(&full_name) {
        Ok(s) => s,
        Err(e) => return (StatusCode::NOT_FOUND, e.to_string()).into_response(),
    };

    let worker = match state.supervisor.worker(&spec.worker) {
        Some(w) => w,
        None => return (StatusCode::SERVICE_UNAVAILABLE, format!("worker `{}` not running", spec.worker)).into_response(),
    };

    match worker.call(&full_name, body.payload.clone(), spec.timeout_ms).await {
        Ok(result) => {
            // Write a trimmed row to the audit log so views like
            // vision_search can query past calls. The full payload is
            // skipped (base64 webcam frames would blow up the DB); only
            // the result summary and small payload keys land here.
            let payload_summary = match &body.payload {
                serde_json::Value::Object(m) => {
                    let mut out = serde_json::Map::new();
                    for (k, v) in m.iter() {
                        if k == "image_base64" || k == "pcm" || k == "file_text" {
                            out.insert(k.clone(), serde_json::json!(format!("<{} bytes>", match v {
                                serde_json::Value::String(s) => s.len(),
                                serde_json::Value::Array(a) => a.len(),
                                _ => 0,
                            })));
                        } else {
                            out.insert(k.clone(), v.clone());
                        }
                    }
                    serde_json::Value::Object(out)
                }
                _ => body.payload.clone(),
            };
            let row = serde_json::json!({
                "capability": full_name,
                "payload": payload_summary,
                "result": result,
            });
            let _ = state.audit.append(&full_name, None, None, &row);
            Json(result).into_response()
        }
        Err(e) => {
            let _ = state.audit.append(
                &format!("{full_name}.error"),
                None, None,
                &serde_json::json!({"error": e.to_string()}),
            );
            (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response()
        }
    }
}

// -------- Feedback --------

#[derive(Deserialize)]
struct RateBody {
    query_id: Uuid,
    label: String,
    note: Option<String>,
}

async fn feedback_rate(
    State(state): State<AppState>,
    Json(body): Json<RateBody>,
) -> impl IntoResponse {
    let label = match body.label.as_str() {
        "good" => ant_common::FeedbackLabel::Good,
        "bad" => ant_common::FeedbackLabel::Bad,
        _ => ant_common::FeedbackLabel::Neutral,
    };
    match state.feedback.rate(body.query_id, label, body.note).await {
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

#[derive(Deserialize)]
struct CorrectBody {
    result_id: Uuid,
    corrections: serde_json::Value,
}

async fn feedback_correct(
    State(state): State<AppState>,
    Json(body): Json<CorrectBody>,
) -> impl IntoResponse {
    match state.feedback.correct(body.result_id, body.corrections).await {
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

#[derive(Deserialize)]
struct ApproveBody {
    action_id: Uuid,
    approver: String,
    note: Option<String>,
}

async fn feedback_approve(
    State(state): State<AppState>,
    Json(body): Json<ApproveBody>,
) -> impl IntoResponse {
    match state.feedback.approve(body.action_id, body.approver, body.note).await {
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::NOT_FOUND, e.to_string()).into_response(),
    }
}

#[derive(Deserialize)]
struct RejectBody {
    action_id: Uuid,
    approver: String,
    reason: String,
}

async fn feedback_reject(
    State(state): State<AppState>,
    Json(body): Json<RejectBody>,
) -> impl IntoResponse {
    match state.feedback.reject(body.action_id, body.approver, body.reason).await {
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::NOT_FOUND, e.to_string()).into_response(),
    }
}

#[derive(Deserialize)]
struct AnnotateBody {
    query_id: Uuid,
    ground_truth: serde_json::Value,
    #[serde(default)]
    labels: Vec<String>,
}

async fn feedback_annotate(
    State(state): State<AppState>,
    Json(body): Json<AnnotateBody>,
) -> impl IntoResponse {
    match state
        .feedback
        .annotate(body.query_id, body.ground_truth, body.labels)
        .await
    {
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn feedback_pending(State(state): State<AppState>) -> impl IntoResponse {
    Json(state.feedback.pending_approvals()).into_response()
}

// -------- Pipeline --------

async fn get_pipeline_config(State(state): State<AppState>) -> impl IntoResponse {
    Json(&*state.config).into_response()
}

#[derive(Deserialize, Default)]
struct RunPipelineBody {
    #[allow(dead_code)]
    #[serde(default)]
    name: Option<String>,
}

async fn run_pipeline_route(
    State(state): State<AppState>,
    body: Option<Json<RunPipelineBody>>,
) -> impl IntoResponse {
    let _body = body.map(|b| b.0).unwrap_or_default();
    let config = &state.config;
    if config.pipeline.is_empty() {
        return (StatusCode::BAD_REQUEST, "no pipeline configured").into_response();
    }
    match run_pipeline(
        &config.name,
        &config.pipeline,
        Arc::clone(&state.supervisor),
        Arc::clone(&state.feedback),
        state.supervisor.bus.clone(),
        &state.registry,
    )
    .await
    {
        Ok(run) => Json(run).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

// -------- Audit --------

#[derive(Deserialize)]
struct AuditQuery {
    #[serde(default = "default_limit")]
    limit: usize,
    #[serde(default)]
    kind: Option<String>,
}

fn default_limit() -> usize {
    100
}

async fn get_audit(
    State(state): State<AppState>,
    Query(q): Query<AuditQuery>,
) -> impl IntoResponse {
    let rows = if let Some(kind) = q.kind {
        state.audit.by_kind_prefix(&kind, q.limit)
    } else {
        state.audit.tail(q.limit)
    };
    match rows {
        Ok(r) => Json(r).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

// -------- Events (WebSocket) --------

async fn ws_events(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_event_socket(socket, state))
}

async fn handle_event_socket(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    let mut rx = state.supervisor.bus.subscribe();

    let forward = async {
        while let Ok(event) = rx.recv().await {
            let text = match serde_json::to_string(&event) {
                Ok(s) => s,
                Err(_) => continue,
            };
            if sender.send(Message::Text(text)).await.is_err() {
                break;
            }
        }
    };

    let drain = async {
        while let Some(msg) = receiver.next().await {
            match msg {
                Ok(Message::Close(_)) => break,
                Ok(_) => {}
                Err(_) => break,
            }
        }
    };

    tokio::select! {
        _ = forward => {},
        _ = drain => {},
    }
}

// -------- Runtime info (aggregated across workers) --------

/// Collects what each worker reports about its runtime: which backends are
/// available, which was picked, what models are on disk. Workers that
/// expose a `.backends` capability contribute their row.
async fn get_runtime(State(state): State<AppState>) -> impl IntoResponse {
    let mut per_worker = serde_json::Map::new();

    for name in state.supervisor.worker_names() {
        let cap = format!("{name}.backends");
        if state.registry.get(&cap).is_err() {
            continue;
        }
        let worker = match state.supervisor.worker(&name) {
            Some(w) => w,
            None => continue,
        };
        match worker.call(&cap, serde_json::json!({}), 5_000).await {
            Ok(v) => {
                per_worker.insert(name.clone(), v);
            }
            Err(e) => {
                per_worker.insert(name.clone(), serde_json::json!({"error": e.to_string()}));
            }
        }
    }

    Json(serde_json::json!({
        "device": DeviceInventory::detect().ok().map(|d| serde_json::json!({
            "platform": d.platform,
            "is_jetson": d.is_jetson,
            "cpus": d.cpus.first().map(|c| c.cores).unwrap_or(0),
            "gpus": d.gpus.len(),
            "total_memory_mb": d.total_memory_mb,
        })),
        "workers": per_worker,
    }))
}

// -------- Stop --------

async fn stop_runtime(State(state): State<AppState>) -> impl IntoResponse {
    tracing::info!("stop requested over HTTP");
    let _ = state.audit.append("runtime.stop_requested", None, None, &serde_json::json!({}));
    // Trigger graceful shutdown in another task; let this response return first.
    let supervisor = Arc::clone(&state.supervisor);
    tokio::spawn(async move {
        let _ = supervisor.shutdown().await;
        std::process::exit(0);
    });
    StatusCode::NO_CONTENT
}

async fn health() -> impl IntoResponse {
    (StatusCode::OK, "ok").into_response()
}

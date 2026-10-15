//! Pipeline executor.
//!
//! Walks the stages in `arikizu.yaml`, invokes each capability, and
//! honors `on_approve` gates by registering a pending action with the
//! Feedback Manager and awaiting its decision before continuing.

use ant_common::{ApprovalDecision, ArikizuError, Result, Severity, StageConfig};
use ant_feedback::{FeedbackManager, PendingAction};
use chrono::{Duration as ChronoDuration, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::time::Duration;
use uuid::Uuid;

use crate::events::{Event, EventBus};
use crate::Supervisor;

/// Record of one pipeline run.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineRun {
    pub run_id: Uuid,
    pub pipeline: String,
    pub stage_results: Vec<StageResult>,
    pub status: RunStatus,
    pub started_at: chrono::DateTime<chrono::Utc>,
    pub finished_at: Option<chrono::DateTime<chrono::Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RunStatus {
    Running,
    Succeeded,
    Rejected,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageResult {
    pub stage: String,
    pub capability: String,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
    pub approval: Option<ApprovalDecision>,
}

/// Run a pipeline synchronously. Returns when every stage has completed
/// or one failed/was rejected.
pub async fn run_pipeline(
    pipeline_name: &str,
    stages: &[StageConfig],
    supervisor: Arc<Supervisor>,
    feedback: Arc<FeedbackManager>,
    bus: EventBus,
    registry: &ant_router::CapabilityRegistry,
) -> Result<PipelineRun> {
    let run_id = Uuid::new_v4();
    let mut run = PipelineRun {
        run_id,
        pipeline: pipeline_name.to_string(),
        stage_results: Vec::new(),
        status: RunStatus::Running,
        started_at: Utc::now(),
        finished_at: None,
    };

    bus.publish(Event::new(
        "pipeline.started",
        pipeline_name,
        serde_json::json!({ "run_id": run_id }),
    ));

    let mut carried: serde_json::Value = serde_json::json!({});

    for stage in stages {
        tracing::info!(pipeline = %pipeline_name, stage = %stage.name, cap = %stage.capability, "running stage");

        // Approval gate: register and await decision.
        if stage.capability == "feedback.approve" {
            let action = PendingAction {
                action_id: Uuid::new_v4(),
                pipeline: pipeline_name.to_string(),
                stage: stage.name.clone(),
                triggered_at: Utc::now(),
                expires_at: Utc::now() + ChronoDuration::minutes(60),
                severity: Severity::Warn,
                approver_role: stage.approver_role.clone().unwrap_or_else(|| "operator".into()),
                proposed_action: carried.clone(),
                evidence: vec![],
            };
            let action_id = action.action_id;
            let rx = feedback.register_pending(action).await;

            bus.publish(Event::new(
                "pipeline.waiting_approval",
                pipeline_name,
                serde_json::json!({ "run_id": run_id, "action_id": action_id, "stage": stage.name }),
            ));

            match tokio::time::timeout(Duration::from_secs(3600), rx).await {
                Ok(Ok(decision)) => {
                    run.stage_results.push(StageResult {
                        stage: stage.name.clone(),
                        capability: stage.capability.clone(),
                        result: None,
                        error: None,
                        approval: Some(decision.clone()),
                    });
                    match decision {
                        ApprovalDecision::Approved { .. } => continue,
                        ApprovalDecision::Rejected { .. } | ApprovalDecision::Expired => {
                            run.status = RunStatus::Rejected;
                            break;
                        }
                    }
                }
                Ok(Err(_)) => {
                    run.status = RunStatus::Failed;
                    break;
                }
                Err(_) => {
                    run.status = RunStatus::Failed;
                    break;
                }
            }
        }

        // Normal capability call.
        let spec = match registry.get(&stage.capability) {
            Ok(s) => s,
            Err(e) => {
                run.stage_results.push(StageResult {
                    stage: stage.name.clone(),
                    capability: stage.capability.clone(),
                    result: None,
                    error: Some(e.to_string()),
                    approval: None,
                });
                run.status = RunStatus::Failed;
                break;
            }
        };

        let worker = match supervisor.worker(&spec.worker) {
            Some(w) => w,
            None => {
                run.stage_results.push(StageResult {
                    stage: stage.name.clone(),
                    capability: stage.capability.clone(),
                    result: None,
                    error: Some(format!("worker `{}` not running", spec.worker)),
                    approval: None,
                });
                run.status = RunStatus::Failed;
                break;
            }
        };

        // Merge stage inputs with the carried payload.
        let payload = merge_json(&carried, &stage.inputs);
        let timeout_ms = stage.timeout_ms.unwrap_or(spec.timeout_ms);

        match worker.call(&stage.capability, payload, timeout_ms).await {
            Ok(result) => {
                carried = result.clone();
                run.stage_results.push(StageResult {
                    stage: stage.name.clone(),
                    capability: stage.capability.clone(),
                    result: Some(result),
                    error: None,
                    approval: None,
                });
                bus.publish(Event::new(
                    "pipeline.stage_ok",
                    pipeline_name,
                    serde_json::json!({ "run_id": run_id, "stage": stage.name }),
                ));
            }
            Err(e) => {
                run.stage_results.push(StageResult {
                    stage: stage.name.clone(),
                    capability: stage.capability.clone(),
                    result: None,
                    error: Some(e.to_string()),
                    approval: None,
                });
                run.status = RunStatus::Failed;
                bus.publish(Event::new(
                    "pipeline.stage_failed",
                    pipeline_name,
                    serde_json::json!({ "run_id": run_id, "stage": stage.name, "error": e.to_string() }),
                ));
                break;
            }
        }
    }

    run.finished_at = Some(Utc::now());
    if matches!(run.status, RunStatus::Running) {
        run.status = RunStatus::Succeeded;
    }

    bus.publish(Event::new(
        "pipeline.finished",
        pipeline_name,
        serde_json::to_value(&run).unwrap_or_default(),
    ));

    Ok(run)
}

/// Shallow merge two JSON objects; `overlay` wins on conflicting keys.
/// If either is not an object, `overlay` wins outright.
fn merge_json(base: &serde_json::Value, overlay: &serde_json::Value) -> serde_json::Value {
    match (base, overlay) {
        (serde_json::Value::Object(a), serde_json::Value::Object(b)) => {
            let mut out = a.clone();
            for (k, v) in b {
                out.insert(k.clone(), v.clone());
            }
            serde_json::Value::Object(out)
        }
        (_, overlay) => overlay.clone(),
    }
}

/// Verify that every capability named in `stages` exists in the registry
/// and that its worker is listed in `known_workers`. Returns the first error.
pub fn validate_pipeline(
    stages: &[StageConfig],
    registry: &ant_router::CapabilityRegistry,
    known_workers: &[String],
) -> Result<()> {
    for stage in stages {
        if stage.capability == "feedback.approve" {
            continue;
        }
        let spec = registry.get(&stage.capability)?;
        if !known_workers.iter().any(|w| w == &spec.worker) {
            return Err(ArikizuError::InvalidInput(format!(
                "stage `{}` uses capability `{}` on worker `{}` which is not in the workers list",
                stage.name, stage.capability, spec.worker
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merge_adds_overlay_keys() {
        let a = serde_json::json!({"a": 1, "b": 2});
        let b = serde_json::json!({"b": 3, "c": 4});
        let merged = merge_json(&a, &b);
        assert_eq!(merged["a"], 1);
        assert_eq!(merged["b"], 3);
        assert_eq!(merged["c"], 4);
    }

    #[test]
    fn validate_rejects_missing_capability() {
        let registry = ant_router::CapabilityRegistry::load_from_str("").unwrap();
        let stages = vec![StageConfig {
            name: "s1".into(),
            capability: "no.such".into(),
            inputs: serde_json::json!({}),
            on_approve: None,
            on_reject: None,
            timeout_ms: None,
            approver_role: None,
        }];
        assert!(validate_pipeline(&stages, &registry, &[]).is_err());
    }
}

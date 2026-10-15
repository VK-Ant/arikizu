//! Feedback Manager — the responsible-AI pillar.
//!
//! Routes human feedback to the right subsystem:
//! - feedback.rate → RL reward in adaptive-intelligence
//! - feedback.correct → extraction template update
//! - feedback.approve / feedback.reject → release pipeline approval gate
//! - feedback.annotate → append to golden evaluation set

pub mod audit;
pub use audit::{AuditLog, AuditRow};

use ant_common::{ApprovalDecision, ArikizuError, FeedbackLabel, Result, Severity};
use chrono::{DateTime, Utc};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::oneshot;
use uuid::Uuid;

/// A pending action awaiting human approval.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingAction {
    pub action_id: Uuid,
    pub pipeline: String,
    pub stage: String,
    pub triggered_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub severity: Severity,
    pub approver_role: String,
    pub proposed_action: serde_json::Value,
    pub evidence: Vec<serde_json::Value>,
}

/// A feedback event for the audit log.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedbackEvent {
    pub kind: FeedbackKind,
    pub timestamp: DateTime<Utc>,
    pub actor: Option<String>,
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeedbackKind {
    Rate,
    Correct,
    Approve,
    Reject,
    Annotate,
}

/// Routes feedback to the right subsystem.
pub struct FeedbackManager {
    pending: DashMap<Uuid, (PendingAction, oneshot::Sender<ApprovalDecision>)>,
    history: Arc<DashMap<Uuid, Vec<FeedbackEvent>>>,
    audit: Option<Arc<AuditLog>>,
}

impl FeedbackManager {
    pub fn new() -> Self {
        Self {
            pending: DashMap::new(),
            history: Arc::new(DashMap::new()),
            audit: None,
        }
    }

    /// Attach a durable audit log. Every subsequent event appends a row.
    pub fn with_audit(mut self, audit: Arc<AuditLog>) -> Self {
        self.audit = Some(audit);
        self
    }

    fn record(&self, kind: &str, actor: Option<&str>, subject: Option<&str>, payload: &serde_json::Value) {
        if let Some(a) = &self.audit {
            if let Err(e) = a.append(kind, actor, subject, payload) {
                tracing::warn!(error = %e, "audit append failed");
            }
        }
    }

    /// Rate an AI response (thumbs up/down).
    /// Routes to orchestration worker for RL reward.
    pub async fn rate(
        &self,
        query_id: Uuid,
        label: FeedbackLabel,
        note: Option<String>,
    ) -> Result<()> {
        let event = FeedbackEvent {
            kind: FeedbackKind::Rate,
            timestamp: Utc::now(),
            actor: None,
            payload: serde_json::json!({ "query_id": query_id, "label": label, "note": note }),
        };
        self.history.entry(query_id).or_default().push(event.clone());
        self.record("feedback.rate", None, Some(&query_id.to_string()), &event.payload);
        tracing::info!(?query_id, ?label, "feedback.rate");
        Ok(())
    }

    /// Correct an extracted result.
    pub async fn correct(
        &self,
        result_id: Uuid,
        corrections: serde_json::Value,
    ) -> Result<()> {
        let event = FeedbackEvent {
            kind: FeedbackKind::Correct,
            timestamp: Utc::now(),
            actor: None,
            payload: serde_json::json!({ "result_id": result_id, "corrections": corrections }),
        };
        self.history.entry(result_id).or_default().push(event.clone());
        self.record("feedback.correct", None, Some(&result_id.to_string()), &event.payload);
        tracing::info!(?result_id, "feedback.correct");
        Ok(())
    }

    /// Register a pending action and return a receiver for the decision.
    pub async fn register_pending(
        &self,
        action: PendingAction,
    ) -> oneshot::Receiver<ApprovalDecision> {
        let (tx, rx) = oneshot::channel();
        let id = action.action_id;
        self.pending.insert(id, (action, tx));
        tracing::info!(?id, "pending approval registered");
        rx
    }

    /// Approve a pending action, releasing its gate.
    pub async fn approve(
        &self,
        action_id: Uuid,
        approver: String,
        note: Option<String>,
    ) -> Result<()> {
        let (_, (_, tx)) = self
            .pending
            .remove(&action_id)
            .ok_or(ArikizuError::ApprovalActionNotFound(action_id))?;
        let decision = ApprovalDecision::Approved {
            by: approver.clone(),
            note,
        };
        tx.send(decision.clone())
            .map_err(|_| ArikizuError::Ipc("approval receiver dropped".into()))?;

        let event = FeedbackEvent {
            kind: FeedbackKind::Approve,
            timestamp: Utc::now(),
            actor: Some(approver.clone()),
            payload: serde_json::to_value(&decision)
                .map_err(|e| ArikizuError::Serialization(e.to_string()))?,
        };
        self.history.entry(action_id).or_default().push(event.clone());
        self.record("feedback.approve", Some(&approver), Some(&action_id.to_string()), &event.payload);
        tracing::info!(?action_id, %approver, "feedback.approve");
        Ok(())
    }

    /// Reject a pending action.
    pub async fn reject(
        &self,
        action_id: Uuid,
        approver: String,
        reason: String,
    ) -> Result<()> {
        let (_, (_, tx)) = self
            .pending
            .remove(&action_id)
            .ok_or(ArikizuError::ApprovalActionNotFound(action_id))?;
        let decision = ApprovalDecision::Rejected {
            by: approver.clone(),
            reason: reason.clone(),
        };
        tx.send(decision.clone())
            .map_err(|_| ArikizuError::Ipc("approval receiver dropped".into()))?;

        let event = FeedbackEvent {
            kind: FeedbackKind::Reject,
            timestamp: Utc::now(),
            actor: Some(approver.clone()),
            payload: serde_json::to_value(&decision)
                .map_err(|e| ArikizuError::Serialization(e.to_string()))?,
        };
        self.history.entry(action_id).or_default().push(event.clone());
        self.record("feedback.reject", Some(&approver), Some(&action_id.to_string()), &event.payload);
        tracing::info!(?action_id, %approver, %reason, "feedback.reject");
        Ok(())
    }

    /// Add an annotation to the golden set.
    pub async fn annotate(
        &self,
        query_id: Uuid,
        ground_truth: serde_json::Value,
        labels: Vec<String>,
    ) -> Result<()> {
        let event = FeedbackEvent {
            kind: FeedbackKind::Annotate,
            timestamp: Utc::now(),
            actor: None,
            payload: serde_json::json!({
                "query_id": query_id,
                "ground_truth": ground_truth,
                "labels": labels
            }),
        };
        self.history.entry(query_id).or_default().push(event.clone());
        self.record("feedback.annotate", None, Some(&query_id.to_string()), &event.payload);
        tracing::info!(?query_id, "feedback.annotate");
        Ok(())
    }

    /// List all pending approvals.
    pub fn pending_approvals(&self) -> Vec<PendingAction> {
        self.pending.iter().map(|e| e.value().0.clone()).collect()
    }

    /// Get feedback history for an id.
    pub fn history(&self, id: &Uuid) -> Vec<FeedbackEvent> {
        self.history.get(id).map(|v| v.value().clone()).unwrap_or_default()
    }
}

impl Default for FeedbackManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    #[tokio::test]
    async fn rate_records_event_in_history() {
        let mgr = FeedbackManager::new();
        let qid = Uuid::new_v4();
        mgr.rate(qid, FeedbackLabel::Good, Some("looks good".into())).await.unwrap();
        let hist = mgr.history(&qid);
        assert_eq!(hist.len(), 1);
    }

    #[tokio::test]
    async fn approve_releases_pending() {
        let mgr = FeedbackManager::new();
        let action = PendingAction {
            action_id: Uuid::new_v4(),
            pipeline: "test".into(),
            stage: "stage1".into(),
            triggered_at: Utc::now(),
            expires_at: Utc::now() + Duration::seconds(60),
            severity: Severity::Warn,
            approver_role: "test_role".into(),
            proposed_action: serde_json::json!({}),
            evidence: vec![],
        };
        let aid = action.action_id;
        let rx = mgr.register_pending(action).await;

        mgr.approve(aid, "operator@test".into(), Some("ok".into())).await.unwrap();
        let decision = rx.await.unwrap();
        assert!(matches!(decision, ApprovalDecision::Approved { .. }));
    }

    #[tokio::test]
    async fn approve_unknown_action_errors() {
        let mgr = FeedbackManager::new();
        let result = mgr.approve(Uuid::new_v4(), "op".into(), None).await;
        assert!(matches!(result, Err(ArikizuError::ApprovalActionNotFound(_))));
    }

    #[tokio::test]
    async fn reject_releases_with_rejection() {
        let mgr = FeedbackManager::new();
        let action = PendingAction {
            action_id: Uuid::new_v4(),
            pipeline: "test".into(),
            stage: "stage1".into(),
            triggered_at: Utc::now(),
            expires_at: Utc::now() + Duration::seconds(60),
            severity: Severity::Critical,
            approver_role: "test_role".into(),
            proposed_action: serde_json::json!({"action": "alert"}),
            evidence: vec![],
        };
        let aid = action.action_id;
        let rx = mgr.register_pending(action).await;

        mgr.reject(aid, "operator@test".into(), "false positive".into()).await.unwrap();
        let decision = rx.await.unwrap();
        match decision {
            ApprovalDecision::Rejected { reason, .. } => assert_eq!(reason, "false positive"),
            _ => panic!("expected rejected"),
        }
    }
}

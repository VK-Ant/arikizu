//! Shared types used across every Arikizu crate.
//!
//! Keep this crate dependency-light. Only standard serde and error types.

pub mod config;

pub use config::{
    ArikizuConfig, DeviceConfig, FeedbackConfig, GoldenSetConfig, ReasoningConfig,
    ReviewQueueConfig, RuntimeConfig, StageConfig, TelemetryConfig, WorkerSpec,
};

use serde::{Deserialize, Serialize};
use std::fmt;
use thiserror::Error;
use uuid::Uuid;

/// A fully-qualified capability name like "vision.detect".
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CapabilityName(pub String);

impl CapabilityName {
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }

    pub fn domain(&self) -> Option<&str> {
        self.0.split('.').next()
    }

    pub fn operation(&self) -> Option<&str> {
        self.0.split_once('.').map(|(_, op)| op)
    }
}

impl fmt::Display for CapabilityName {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Severity level, matches syslog + an extra for events we think are critical.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Trace,
    Debug,
    Info,
    Warn,
    Error,
    Critical,
}

/// Worker lifecycle state.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkerState {
    Created,
    Initializing,
    Ready,
    Serving,
    Draining,
    Stopped,
    Unhealthy,
    Degraded,
}

/// Human feedback label.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FeedbackLabel {
    Good,
    Bad,
    Neutral,
}

/// Approval decision kinds.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ApprovalDecision {
    Approved { by: String, note: Option<String> },
    Rejected { by: String, reason: String },
    Expired,
}

/// Common error type returned across the system.
#[derive(Debug, Error)]
pub enum ArikizuError {
    #[error("capability `{0}` not found")]
    CapabilityNotFound(CapabilityName),

    #[error("worker `{0}` is not healthy")]
    WorkerUnhealthy(String),

    #[error("capability call timed out after {timeout_ms}ms")]
    Timeout { timeout_ms: u64 },

    #[error("policy denied the action: {reason}")]
    PolicyDenied { reason: String },

    #[error("invalid input: {0}")]
    InvalidInput(String),

    #[error("model `{name}` failed integrity check (expected {expected}, got {actual})")]
    ModelIntegrityFailure {
        name: String,
        expected: String,
        actual: String,
    },

    #[error("IPC error: {0}")]
    Ipc(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("serialization error: {0}")]
    Serialization(String),

    #[error("approval action `{0}` not found")]
    ApprovalActionNotFound(Uuid),

    #[error("{0}")]
    Other(String),
}

pub type Result<T> = std::result::Result<T, ArikizuError>;

/// Timestamp with both monotonic (for ordering) and wall-clock (for display).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Timestamp {
    pub monotonic_ns: u64,
    pub wall: Option<chrono::DateTime<chrono::Utc>>,
}

impl Timestamp {
    pub fn now() -> Self {
        Self {
            monotonic_ns: std::time::Instant::now().elapsed().as_nanos() as u64,
            wall: Some(chrono::Utc::now()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capability_name_splits_domain_and_operation() {
        let name = CapabilityName::new("vision.detect");
        assert_eq!(name.domain(), Some("vision"));
        assert_eq!(name.operation(), Some("detect"));
    }

    #[test]
    fn capability_name_handles_no_dot() {
        let name = CapabilityName::new("standalone");
        assert_eq!(name.domain(), Some("standalone"));
        assert_eq!(name.operation(), None);
    }

    #[test]
    fn severity_round_trips_json() {
        let s = Severity::Critical;
        let json = serde_json::to_string(&s).unwrap();
        assert_eq!(json, "\"critical\"");
        let back: Severity = serde_json::from_str(&json).unwrap();
        assert_eq!(back, s);
    }
}

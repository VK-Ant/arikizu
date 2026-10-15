//! `arikizu.yaml` loader.
//!
//! Serde types that mirror the reference pipeline config. Opinionated
//! defaults: everything optional has a sensible fallback, the only
//! required field is `name`.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

use crate::{ArikizuError, Result};

/// Top-level pipeline config, parsed from `arikizu.yaml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArikizuConfig {
    pub name: String,

    #[serde(default)]
    pub devices: HashMap<String, DeviceConfig>,

    #[serde(default)]
    pub pipeline: Vec<StageConfig>,

    #[serde(default)]
    pub workers: Vec<WorkerSpec>,

    #[serde(default)]
    pub reasoning: Option<ReasoningConfig>,

    #[serde(default)]
    pub feedback: Option<FeedbackConfig>,

    #[serde(default)]
    pub policies: Vec<String>,

    #[serde(default)]
    pub runtime: RuntimeConfig,
}

impl ArikizuConfig {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())?;
        serde_yaml::from_str(&content)
            .map_err(|e| ArikizuError::Serialization(format!("arikizu.yaml: {e}")))
    }

    pub fn load_from_str(s: &str) -> Result<Self> {
        serde_yaml::from_str(s)
            .map_err(|e| ArikizuError::Serialization(format!("yaml parse: {e}")))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum DeviceConfig {
    Rtsp { url: String, fps: Option<u32> },
    Alsa { device: String, sample_rate: Option<u32> },
    File { path: String },
    Http { url: String, poll_ms: Option<u64> },
    Mqtt { broker: String, topic: String },
}

/// One pipeline stage. `on_approve` turns it into an approval gate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageConfig {
    pub name: String,
    pub capability: String,

    #[serde(default)]
    pub inputs: serde_json::Value,

    #[serde(default)]
    pub on_approve: Option<String>,

    #[serde(default)]
    pub on_reject: Option<String>,

    #[serde(default)]
    pub timeout_ms: Option<u64>,

    /// Approver role allowed to release this stage, if it is a gate.
    #[serde(default)]
    pub approver_role: Option<String>,
}

/// Workers to spawn at startup. If omitted, the supervisor spawns every
/// worker that appears as `worker = "..."` in capabilities.toml.
///
/// `python` is the executable to run (python3, uv, etc). `args` is the
/// command line passed to it; empty args defaults to `["-m", module]`.
/// For uv workspace layouts, use:
///
///     python: uv
///     args: [run, --package, test-worker, python, -m, test_worker]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerSpec {
    pub name: String,
    pub module: String,
    #[serde(default = "default_python")]
    pub python: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: HashMap<String, String>,
    #[serde(default)]
    pub cwd: Option<String>,
    #[serde(default)]
    pub max_memory_mb: Option<u64>,
}

fn default_python() -> String {
    "python3".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReasoningConfig {
    #[serde(default = "default_provider")]
    pub provider: String,
    pub model: String,
    #[serde(default = "default_ollama_endpoint")]
    pub endpoint: String,
}

fn default_provider() -> String {
    "ollama".to_string()
}

fn default_ollama_endpoint() -> String {
    "http://127.0.0.1:11434".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedbackConfig {
    #[serde(default)]
    pub review_queue: ReviewQueueConfig,
    #[serde(default)]
    pub approvers: Vec<String>,
    #[serde(default = "default_rate_scale")]
    pub rate_scale: String,
    #[serde(default)]
    pub golden_set: Option<GoldenSetConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReviewQueueConfig {
    #[serde(default = "default_retain_hours")]
    pub retain_hours: u32,
    #[serde(default = "default_max_pending")]
    pub max_pending: u32,
}

impl Default for ReviewQueueConfig {
    fn default() -> Self {
        Self {
            retain_hours: default_retain_hours(),
            max_pending: default_max_pending(),
        }
    }
}

fn default_retain_hours() -> u32 {
    72
}
fn default_max_pending() -> u32 {
    500
}
fn default_rate_scale() -> String {
    "binary".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoldenSetConfig {
    pub dir: String,
    #[serde(default = "default_sample_rate")]
    pub auto_sample_rate: f32,
}

fn default_sample_rate() -> f32 {
    0.02
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeConfig {
    #[serde(default = "default_offline")]
    pub offline: bool,
    #[serde(default = "default_http_api")]
    pub http_api: String,
    #[serde(default = "default_socket_dir")]
    pub socket_dir: String,
    #[serde(default = "default_log_level")]
    pub log_level: String,
    #[serde(default)]
    pub telemetry: Option<TelemetryConfig>,
    #[serde(default = "default_db_path")]
    pub db_path: String,
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            offline: default_offline(),
            http_api: default_http_api(),
            socket_dir: default_socket_dir(),
            log_level: default_log_level(),
            telemetry: None,
            db_path: default_db_path(),
        }
    }
}

fn default_offline() -> bool {
    true
}
fn default_http_api() -> String {
    "127.0.0.1:7000".into()
}
fn default_socket_dir() -> String {
    "/tmp/arikizu".into()
}
fn default_log_level() -> String {
    "info".into()
}
fn default_db_path() -> String {
    "./arikizu.db".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryConfig {
    #[serde(default = "default_local_only")]
    pub local_only: bool,
    #[serde(default = "default_retain_days")]
    pub retain_days: u32,
}

fn default_local_only() -> bool {
    true
}
fn default_retain_days() -> u32 {
    30
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn minimal_config_parses() {
        let yaml = "name: my-pipeline";
        let config = ArikizuConfig::load_from_str(yaml).unwrap();
        assert_eq!(config.name, "my-pipeline");
        assert!(config.runtime.offline);
        assert_eq!(config.runtime.http_api, "127.0.0.1:7000");
    }

    #[test]
    fn full_config_parses() {
        let yaml = r#"
name: factory-qa
devices:
  cam_a:
    type: rtsp
    url: rtsp://192.168.1.10/stream1
    fps: 5
pipeline:
  - name: detect
    capability: vision.detect
    inputs:
      image_source: cam_a
  - name: approve
    capability: feedback.approve
    on_approve: notify
reasoning:
  provider: ollama
  model: qwen2.5:3b-instruct-q4_K_M
feedback:
  review_queue:
    retain_hours: 48
    max_pending: 200
  approvers:
    - shift_lead
runtime:
  offline: true
  http_api: 127.0.0.1:7000
"#;
        let config = ArikizuConfig::load_from_str(yaml).unwrap();
        assert_eq!(config.pipeline.len(), 2);
        assert_eq!(config.pipeline[1].on_approve.as_deref(), Some("notify"));
        assert_eq!(config.reasoning.as_ref().unwrap().model, "qwen2.5:3b-instruct-q4_K_M");
        assert_eq!(config.feedback.as_ref().unwrap().review_queue.retain_hours, 48);
    }

    #[test]
    fn missing_name_fails() {
        let yaml = "devices: {}";
        assert!(ArikizuConfig::load_from_str(yaml).is_err());
    }
}

//! Policy enforcement.
//!
//! Policies are small YAML files under `policies/` naming which hosts and
//! which capabilities are allowed. Enforcement is advisory at the
//! supervisor level: a worker that violates `allow_hosts` is logged and,
//! under `block` enforcement, denied at the capability call. True network
//! isolation happens via namespace isolation (Weekend 13+).

use serde::{Deserialize, Serialize};
use std::path::Path;

use ant_common::{ArikizuError, Result};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    pub name: String,
    #[serde(default = "default_version")]
    pub version: u32,
    #[serde(default)]
    pub allow_hosts: Vec<String>,
    #[serde(default)]
    pub allow_capabilities: Vec<String>,
    #[serde(default = "default_log")]
    pub log: LogConfig,
    #[serde(default = "default_enforcement")]
    pub enforcement: Enforcement,
}

fn default_version() -> u32 {
    1
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogConfig {
    #[serde(default = "default_log_level")]
    pub level: String,
    #[serde(default)]
    pub include_payload: bool,
    #[serde(default = "default_sink")]
    pub sink: String,
}

fn default_log_level() -> String {
    "warn".into()
}
fn default_sink() -> String {
    "audit".into()
}

fn default_log() -> LogConfig {
    LogConfig {
        level: default_log_level(),
        include_payload: false,
        sink: default_sink(),
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Enforcement {
    Block,
    Warn,
    Off,
}

fn default_enforcement() -> Enforcement {
    Enforcement::Block
}

impl Policy {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let content = std::fs::read_to_string(path.as_ref())?;
        serde_yaml::from_str(&content)
            .map_err(|e| ArikizuError::Serialization(format!("policy yaml: {e}")))
    }

    /// Return Ok if the capability is permitted, Err(PolicyDenied) otherwise.
    /// Honors `enforcement` level: Off always allows, Warn allows with a log,
    /// Block denies.
    pub fn check_capability(&self, capability: &str) -> Result<()> {
        if self.enforcement == Enforcement::Off {
            return Ok(());
        }
        if self.allow_capabilities.is_empty() || self.allow_capabilities.iter().any(|c| c == capability) {
            return Ok(());
        }
        match self.enforcement {
            Enforcement::Block => Err(ArikizuError::PolicyDenied {
                reason: format!("capability `{capability}` not in policy `{}`", self.name),
            }),
            Enforcement::Warn => {
                tracing::warn!(policy = %self.name, capability, "capability not allowed by policy (warn only)");
                Ok(())
            }
            Enforcement::Off => Ok(()),
        }
    }

    /// Return Ok if the host is on the allow list; Block denies, Warn logs.
    pub fn check_host(&self, host: &str) -> Result<()> {
        if self.enforcement == Enforcement::Off {
            return Ok(());
        }
        if self.allow_hosts.iter().any(|h| h == host) {
            return Ok(());
        }
        match self.enforcement {
            Enforcement::Block => Err(ArikizuError::PolicyDenied {
                reason: format!("host `{host}` not in policy `{}`", self.name),
            }),
            Enforcement::Warn => {
                tracing::warn!(policy = %self.name, host, "host not allowed by policy (warn only)");
                Ok(())
            }
            Enforcement::Off => Ok(()),
        }
    }
}

/// Load every policy file in a directory. Returns an empty list if the dir
/// does not exist.
pub fn load_policies(dir: impl AsRef<Path>) -> Result<Vec<Policy>> {
    let dir = dir.as_ref();
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut policies = Vec::new();
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().is_some_and(|e| e == "yaml" || e == "yml") {
            policies.push(Policy::load(&path)?);
        }
    }
    Ok(policies)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_reference_policy() {
        let yaml = r#"
name: no-outbound
allow_hosts:
  - 127.0.0.1:11434
allow_capabilities:
  - reasoning.summarize
log:
  level: warn
  include_payload: false
  sink: audit
enforcement: block
"#;
        let policy: Policy = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(policy.name, "no-outbound");
        assert_eq!(policy.enforcement, Enforcement::Block);
    }

    #[test]
    fn allow_list_permits_match() {
        let policy = Policy {
            name: "p".into(),
            version: 1,
            allow_hosts: vec!["127.0.0.1:11434".into()],
            allow_capabilities: vec!["reasoning.summarize".into()],
            log: default_log(),
            enforcement: Enforcement::Block,
        };
        assert!(policy.check_capability("reasoning.summarize").is_ok());
        assert!(policy.check_host("127.0.0.1:11434").is_ok());
    }

    #[test]
    fn allow_list_blocks_miss() {
        let policy = Policy {
            name: "p".into(),
            version: 1,
            allow_hosts: vec![],
            allow_capabilities: vec!["reasoning.summarize".into()],
            log: default_log(),
            enforcement: Enforcement::Block,
        };
        assert!(policy.check_capability("vision.detect").is_err());
    }

    #[test]
    fn empty_capability_list_allows_everything() {
        let policy = Policy {
            name: "p".into(),
            version: 1,
            allow_hosts: vec![],
            allow_capabilities: vec![],
            log: default_log(),
            enforcement: Enforcement::Block,
        };
        assert!(policy.check_capability("anything.goes").is_ok());
    }

    #[test]
    fn warn_level_lets_everything_through() {
        let policy = Policy {
            name: "p".into(),
            version: 1,
            allow_hosts: vec![],
            allow_capabilities: vec!["reasoning.summarize".into()],
            log: default_log(),
            enforcement: Enforcement::Warn,
        };
        assert!(policy.check_capability("vision.detect").is_ok());
    }
}

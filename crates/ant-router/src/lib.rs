//! Capability registry and routing.
//!
//! Loads `capabilities.toml` and maps the capability name (e.g. "vision.detect")
//! to its spec. The TOML section name is a slug (`[vision_detect]`); the real
//! capability name lives in the `name = "..."` field of that section, which
//! becomes the key in the in-memory registry.

use ant_common::{ArikizuError, CapabilityName, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

/// One capability's declaration in `capabilities.toml`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilitySpec {
    /// Dotted name, e.g. "vision.detect". Required.
    pub name: String,
    pub worker: String,
    #[serde(default)]
    pub input: HashMap<String, String>,
    #[serde(default)]
    pub output: String,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
    #[serde(default)]
    pub emits_events: Vec<String>,
    #[serde(default)]
    pub requires_authentication: bool,
    #[serde(default)]
    pub priority: i32,
}

fn default_timeout() -> u64 {
    5000
}

/// Capability registry loaded from TOML.
pub struct CapabilityRegistry {
    /// Keyed by dotted capability name (`spec.name`), not by TOML section slug.
    pub capabilities: HashMap<String, CapabilitySpec>,
}

impl CapabilityRegistry {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        // Primary file.
        let path_ref = path.as_ref();
        let content = std::fs::read_to_string(path_ref)?;
        let mut registry = Self::load_from_str(&content)?;

        // Plug-in files: capabilities.d/*.toml next to the primary file.
        // Each file is parsed as a map of capability blocks and merged into
        // the registry. Duplicate capability names are rejected to make
        // the override surface explicit.
        if let Some(parent) = path_ref.parent() {
            let plugin_dir = parent.join("capabilities.d");
            if plugin_dir.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&plugin_dir) {
                    let mut paths: Vec<_> = entries
                        .flatten()
                        .filter_map(|e| {
                            let p = e.path();
                            let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
                            let is_toml = p.extension().and_then(|s| s.to_str()) == Some("toml");
                            let skipped = name.starts_with('.')
                                || name.starts_with('_')
                                || name.ends_with(".example");
                            if is_toml && !skipped {
                                Some(p)
                            } else {
                                None
                            }
                        })
                        .collect();
                    paths.sort();
                    for p in paths {
                        let extra = std::fs::read_to_string(&p)?;
                        let extra_registry = Self::load_from_str(&extra)?;
                        for (name, spec) in extra_registry.capabilities {
                            if registry.capabilities.contains_key(&name) {
                                return Err(ArikizuError::Serialization(format!(
                                    "capabilities.d/{}: duplicate capability name `{}`",
                                    p.file_name().and_then(|s| s.to_str()).unwrap_or("?"),
                                    name,
                                )));
                            }
                            registry.capabilities.insert(name, spec);
                        }
                        tracing::info!(
                            file = ?p.file_name().and_then(|s| s.to_str()).unwrap_or("?"),
                            total = registry.capabilities.len(),
                            "merged plug-in capabilities"
                        );
                    }
                }
            }
        }
        Ok(registry)
    }

    pub fn load_from_str(s: &str) -> Result<Self> {
        // The TOML's section slugs ([vision_detect]) are not the lookup key.
        // Parse into a map first, then rebuild keyed by `spec.name`.
        let by_slug: HashMap<String, CapabilitySpec> = toml::from_str(s)
            .map_err(|e| ArikizuError::Serialization(format!("capabilities.toml: {e}")))?;

        let mut by_name = HashMap::with_capacity(by_slug.len());
        for (slug, spec) in by_slug {
            if spec.name.is_empty() {
                return Err(ArikizuError::Serialization(format!(
                    "capability `[{slug}]` is missing the `name` field"
                )));
            }
            if let Some(prev) = by_name.insert(spec.name.clone(), spec) {
                return Err(ArikizuError::Serialization(format!(
                    "duplicate capability name `{}`",
                    prev.name
                )));
            }
        }

        tracing::info!(count = by_name.len(), "loaded capability registry");
        Ok(Self { capabilities: by_name })
    }

    pub fn get(&self, name: &str) -> Result<&CapabilitySpec> {
        self.capabilities
            .get(name)
            .ok_or_else(|| ArikizuError::CapabilityNotFound(CapabilityName::new(name)))
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.capabilities.keys().map(|s| s.as_str())
    }

    pub fn by_worker<'a>(&'a self, worker: &'a str) -> impl Iterator<Item = (&'a String, &'a CapabilitySpec)> + 'a {
        self.capabilities.iter().filter(move |(_, s)| s.worker == worker)
    }

    pub fn len(&self) -> usize {
        self.capabilities.len()
    }

    pub fn is_empty(&self) -> bool {
        self.capabilities.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_loads_from_toml() {
        let s = r#"
            [test_echo]
            name = "test.echo"
            worker = "test"
            output = "string"
            timeout_ms = 1000

            [vision_detect]
            name = "vision.detect"
            worker = "vision"
            output = "list"
            timeout_ms = 2000
            emits_events = ["vision.detected"]
        "#;

        let registry = CapabilityRegistry::load_from_str(s).unwrap();
        assert_eq!(registry.len(), 2);

        let echo = registry.get("test.echo").unwrap();
        assert_eq!(echo.worker, "test");
        assert_eq!(echo.timeout_ms, 1000);

        let detect = registry.get("vision.detect").unwrap();
        assert_eq!(detect.worker, "vision");
        assert_eq!(detect.emits_events, vec!["vision.detected".to_string()]);
    }

    #[test]
    fn missing_capability_returns_not_found() {
        let registry = CapabilityRegistry::load_from_str("").unwrap();
        let result = registry.get("nonexistent.op");
        assert!(matches!(result, Err(ArikizuError::CapabilityNotFound(_))));
    }

    #[test]
    fn by_worker_filters_correctly() {
        let s = r#"
            [vision_detect]
            name = "vision.detect"
            worker = "vision"
            output = "list"

            [vision_search]
            name = "vision.search"
            worker = "vision"
            output = "list"

            [audio_transcribe]
            name = "audio.transcribe"
            worker = "audio"
            output = "string"
        "#;
        let registry = CapabilityRegistry::load_from_str(s).unwrap();
        let vision_caps: Vec<_> = registry.by_worker("vision").collect();
        assert_eq!(vision_caps.len(), 2);
    }

    #[test]
    fn default_timeout_when_omitted() {
        let s = r#"
            [test_op]
            name = "test.op"
            worker = "test"
            output = "string"
        "#;
        let registry = CapabilityRegistry::load_from_str(s).unwrap();
        let cap = registry.get("test.op").unwrap();
        assert_eq!(cap.timeout_ms, 5000);
    }

    #[test]
    fn duplicate_name_rejected() {
        let s = r#"
            [a_op]
            name = "foo.bar"
            worker = "a"

            [b_op]
            name = "foo.bar"
            worker = "b"
        "#;
        let result = CapabilityRegistry::load_from_str(s);
        assert!(result.is_err());
    }

    #[test]
    fn missing_name_field_rejected() {
        let s = r#"
            [slug_only]
            worker = "x"
        "#;
        // This may be a parse-level rejection (serde) OR a semantic one (empty name).
        let result = CapabilityRegistry::load_from_str(s);
        assert!(result.is_err());
    }

    #[test]
    fn plugin_directory_merges_capabilities() {
        // Write a main capabilities.toml and a capabilities.d/ with two
        // user files; confirm all three capabilities are loaded.
        let tmp = std::env::temp_dir().join(format!("ant_router_test_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        std::fs::create_dir_all(tmp.join("capabilities.d")).unwrap();

        let main_toml = r#"
            [test_echo]
            name = "test.echo"
            worker = "test"
            output = "string"
        "#;
        std::fs::write(tmp.join("capabilities.toml"), main_toml).unwrap();

        std::fs::write(
            tmp.join("capabilities.d").join("math.toml"),
            r#"
            [my_add]
            name = "my.add"
            worker = "custom"
            output = "object"
            "#,
        ).unwrap();

        std::fs::write(
            tmp.join("capabilities.d").join("hello.toml"),
            r#"
            [hello_greet]
            name = "hello.greet"
            worker = "custom"
            output = "object"
            "#,
        ).unwrap();

        // Files starting with _ or . should be skipped.
        std::fs::write(
            tmp.join("capabilities.d").join("_draft.toml"),
            r#"
            [draft_cap]
            name = "draft.one"
            worker = "custom"
            output = "object"
            "#,
        ).unwrap();

        let registry = CapabilityRegistry::load(tmp.join("capabilities.toml")).unwrap();
        assert!(registry.get("test.echo").is_ok(), "primary file should load");
        assert!(registry.get("my.add").is_ok(), "math.toml should merge");
        assert!(registry.get("hello.greet").is_ok(), "hello.toml should merge");
        assert!(registry.get("draft.one").is_err(), "_draft.toml should be skipped");

        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn plugin_directory_rejects_duplicate_name() {
        let tmp = std::env::temp_dir().join(format!("ant_router_test_dup_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        std::fs::create_dir_all(tmp.join("capabilities.d")).unwrap();

        std::fs::write(
            tmp.join("capabilities.toml"),
            r#"[test_echo]
name = "test.echo"
worker = "test"
output = "string"
"#,
        ).unwrap();

        std::fs::write(
            tmp.join("capabilities.d").join("dup.toml"),
            r#"[test_echo_dup]
name = "test.echo"
worker = "custom"
output = "object"
"#,
        ).unwrap();

        let result = CapabilityRegistry::load(tmp.join("capabilities.toml"));
        assert!(result.is_err(), "collision with primary should be rejected");

        let _ = std::fs::remove_dir_all(&tmp);
    }
}

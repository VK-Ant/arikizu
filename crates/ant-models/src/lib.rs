//! Model manifest and integrity verification.
//!
//! Content-addressed storage: models stored under `models/blobs/sha256:...`
//! with symlinks under `models/names/<worker>/<model_name>`.

use ant_common::{ArikizuError, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Backend {
    TensorRt,
    OnnxGpu,
    CudaPytorch,
    OpenVino,
    OnnxCpu,
    PytorchCpu,
    LlamaCpp,
}

/// A single model's manifest entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelManifest {
    pub name: String,
    pub sha256: String,
    pub backend: Backend,
    pub quantization: Option<String>,
    pub device_signature: Option<String>,
    pub file_path: PathBuf,
    pub size_bytes: u64,
}

/// The on-disk manifest for all models.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ModelLock {
    pub models: HashMap<String, ModelManifest>,
}

impl ModelLock {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let content = std::fs::read_to_string(path)?;
        toml::from_str(&content).map_err(|e| ArikizuError::Serialization(e.to_string()))
    }

    pub fn save(&self, path: impl AsRef<Path>) -> Result<()> {
        let content = toml::to_string_pretty(self)
            .map_err(|e| ArikizuError::Serialization(e.to_string()))?;
        std::fs::write(path, content)?;
        Ok(())
    }

    pub fn get(&self, name: &str) -> Option<&ModelManifest> {
        self.models.get(name)
    }
}

/// Compute SHA-256 of a file.
pub fn sha256_of(path: impl AsRef<Path>) -> Result<String> {
    let mut file = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// Verify a model against its manifest hash.
pub fn verify(manifest: &ModelManifest, root: &Path) -> Result<()> {
    let full_path = root.join(&manifest.file_path);
    let actual = sha256_of(&full_path)?;
    if actual != manifest.sha256 {
        return Err(ArikizuError::ModelIntegrityFailure {
            name: manifest.name.clone(),
            expected: manifest.sha256.clone(),
            actual,
        });
    }
    Ok(())
}

/// Backend selection priority. First one for which the predicate is true wins.
pub fn select_backend(available: &[Backend], preferred: &[Backend]) -> Option<Backend> {
    for backend in preferred {
        if available.contains(backend) {
            return Some(*backend);
        }
    }
    None
}

/// Default backend priority order.
pub fn default_priority() -> Vec<Backend> {
    vec![
        Backend::TensorRt,
        Backend::OnnxGpu,
        Backend::CudaPytorch,
        Backend::OpenVino,
        Backend::OnnxCpu,
        Backend::PytorchCpu,
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn sha256_of_known_file() {
        let tmp = std::env::temp_dir().join("arikizu_sha_test");
        let mut f = std::fs::File::create(&tmp).unwrap();
        f.write_all(b"hello world").unwrap();
        drop(f);
        let hash = sha256_of(&tmp).unwrap();
        assert_eq!(hash, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
        std::fs::remove_file(&tmp).ok();
    }

    #[test]
    fn backend_priority_picks_first_available() {
        let available = vec![Backend::OnnxCpu, Backend::PytorchCpu];
        let preferred = default_priority();
        let selected = select_backend(&available, &preferred);
        assert_eq!(selected, Some(Backend::OnnxCpu));
    }

    #[test]
    fn backend_priority_returns_none_when_nothing_matches() {
        let available: Vec<Backend> = vec![];
        let preferred = default_priority();
        let selected = select_backend(&available, &preferred);
        assert_eq!(selected, None);
    }

    #[test]
    fn model_lock_round_trips_toml() {
        let mut lock = ModelLock::default();
        lock.models.insert(
            "sightrag/yolov8n".to_string(),
            ModelManifest {
                name: "sightrag/yolov8n".to_string(),
                sha256: "abc123".to_string(),
                backend: Backend::TensorRt,
                quantization: Some("fp16".to_string()),
                device_signature: Some("jetson-orin-nano-r36.3".to_string()),
                file_path: PathBuf::from("blobs/sha256:abc123"),
                size_bytes: 1_000_000,
            },
        );

        let tmp = std::env::temp_dir().join("arikizu_lock_test.toml");
        lock.save(&tmp).unwrap();
        let loaded = ModelLock::load(&tmp).unwrap();
        assert_eq!(loaded.models.len(), 1);
        assert!(loaded.get("sightrag/yolov8n").is_some());
        std::fs::remove_file(&tmp).ok();
    }
}

//! Device discovery and inventory.
//!
//! Enumerates CPUs, GPUs, cameras, microphones, sensors.
//! Platform-conditional implementations.

use ant_common::Result;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CpuInfo {
    pub cores: u32,
    pub vendor: String,
    pub model: String,
    pub simd: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GpuInfo {
    pub vendor: GpuVendor,
    pub model: String,
    pub memory_mb: u64,
    pub cuda_capability: Option<(u8, u8)>,
    pub driver_version: Option<String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GpuVendor {
    Nvidia,
    Amd,
    Intel,
    Apple,
    Qualcomm,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInventory {
    pub cpus: Vec<CpuInfo>,
    pub gpus: Vec<GpuInfo>,
    pub total_memory_mb: u64,
    pub platform: String,
    pub is_jetson: bool,
}

impl DeviceInventory {
    pub fn detect() -> Result<Self> {
        let cpus = detect_cpus();
        let gpus = detect_gpus();
        let total_memory_mb = detect_total_memory_mb();
        let platform = detect_platform();
        let is_jetson = is_jetson_platform();

        Ok(Self {
            cpus,
            gpus,
            total_memory_mb,
            platform,
            is_jetson,
        })
    }
}

fn detect_cpus() -> Vec<CpuInfo> {
    let cores = std::thread::available_parallelism()
        .map(|n| n.get() as u32)
        .unwrap_or(1);

    vec![CpuInfo {
        cores,
        vendor: std::env::consts::ARCH.to_string(),
        model: "unknown".to_string(),
        simd: detect_simd(),
    }]
}

fn detect_simd() -> Vec<String> {
    let mut simd = Vec::new();
    #[cfg(target_arch = "x86_64")]
    {
        if is_x86_feature_detected!("avx2") {
            simd.push("avx2".to_string());
        }
        if is_x86_feature_detected!("avx512f") {
            simd.push("avx512f".to_string());
        }
    }
    #[cfg(target_arch = "aarch64")]
    {
        simd.push("neon".to_string());
    }
    simd
}

#[cfg(target_os = "linux")]
fn detect_gpus() -> Vec<GpuInfo> {
    // Simplified: parse /proc/driver/nvidia or run nvidia-smi
    // Real implementation would use nvml-rs or similar
    Vec::new()
}

#[cfg(not(target_os = "linux"))]
fn detect_gpus() -> Vec<GpuInfo> {
    Vec::new()
}

fn detect_total_memory_mb() -> u64 {
    #[cfg(target_os = "linux")]
    {
        if let Ok(info) = std::fs::read_to_string("/proc/meminfo") {
            for line in info.lines() {
                if line.starts_with("MemTotal:") {
                    if let Some(kb) = line.split_whitespace().nth(1).and_then(|v| v.parse::<u64>().ok()) {
                        return kb / 1024;
                    }
                }
            }
        }
    }
    0
}

fn detect_platform() -> String {
    format!("{} {}", std::env::consts::OS, std::env::consts::ARCH)
}

fn is_jetson_platform() -> bool {
    #[cfg(target_os = "linux")]
    {
        std::path::Path::new("/etc/nv_tegra_release").exists()
            || std::fs::read_to_string("/proc/device-tree/model")
                .map(|s| s.to_lowercase().contains("jetson"))
                .unwrap_or(false)
    }
    #[cfg(not(target_os = "linux"))]
    {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inventory_can_be_detected() {
        let inv = DeviceInventory::detect().unwrap();
        assert!(!inv.cpus.is_empty());
        assert!(inv.cpus[0].cores >= 1);
        assert!(!inv.platform.is_empty());
    }
}

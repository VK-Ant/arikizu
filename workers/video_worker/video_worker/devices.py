"""Device profile detection and model-fit suggestions.

Reads the running machine's CPU, RAM, platform and (where accessible) GPU,
then recommends which model variants will actually work. The UI calls this
on page load so the user sees "Jetson Orin Nano detected, Qwen2.5-VL 3B
Q4 recommended" instead of discovering model-too-large errors at runtime.

The classifications are deliberately conservative. "Will not work" means we
have strong signal it will OOM or take minutes per frame, not that it's
theoretically impossible.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DeviceProfile:
    """What we detected about this machine."""
    platform: str                 # "linux", "darwin", "windows"
    arch: str                     # "x86_64", "aarch64", "arm64"
    device_class: str             # "pi4", "pi5", "jetson_nano", "jetson_orin_nano", "mac_apple_silicon", "linux_x86", "windows_wsl", "unknown"
    cpu_count: int
    ram_gb: float                 # total installed RAM, GB
    gpu_vendor: str               # "nvidia", "apple", "amd", "none"
    gpu_name: str                 # e.g. "Orin", "M2", or ""
    gpu_vram_gb: float            # 0 if not applicable


@dataclass
class ModelFit:
    """Whether a model fits this device, and the expected per-frame cost."""
    model_key: str
    fits: bool                    # true == recommended for this device
    recommended: bool             # true == primary pick for this device class
    expected_ms_per_frame: int    # realistic ms per frame on this hardware
    expected_fps: float
    reason: str                   # short one-liner explaining the verdict
    delegate: str                 # "cpu-xnnpack", "gpu", "cuda", "coreml"


def _read_meminfo_gb() -> float:
    """Linux /proc/meminfo total memory, in GB."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except Exception:
        pass
    return 0.0


def _read_cpuinfo_model() -> str:
    """First 'Model' or 'model name' line from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith(("model name", "model\t", "model :")):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def _detect_nvidia_gpu() -> tuple[str, float]:
    """Returns (gpu_name, vram_gb). Uses nvidia-smi if available."""
    if not shutil.which("nvidia-smi"):
        return "", 0.0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            first = out.stdout.strip().splitlines()[0]
            name, mem_mb = (p.strip() for p in first.split(",", 1))
            return name, round(int(mem_mb) / 1024, 1)
    except Exception:
        pass
    return "", 0.0


def _detect_device_class(plat: str, arch: str, cpu_model: str, ram_gb: float,
                         gpu_vendor: str, gpu_name: str) -> str:
    """Fuzzy classification based on hints. Order matters: specific checks first."""
    cpu_low = cpu_model.lower()
    gpu_low = gpu_name.lower()
    # Jetson first (ARM + NVIDIA GPU is a dead giveaway)
    if arch in ("aarch64", "arm64") and gpu_vendor == "nvidia":
        if "orin" in gpu_low:
            return "jetson_orin_nano" if ram_gb <= 10 else "jetson_orin"
        if "xavier" in gpu_low:
            return "jetson_xavier"
        return "jetson_nano"
    # Raspberry Pi
    if "raspberry pi" in cpu_low or "bcm" in cpu_low:
        if "pi 5" in cpu_low or "bcm2712" in cpu_low:
            return "pi5"
        return "pi4"
    if arch in ("aarch64", "arm64") and ram_gb <= 8 and gpu_vendor == "none":
        return "pi4"  # generic ARM edge SBC, treat like Pi 4
    # Apple Silicon
    if plat == "darwin" and arch in ("arm64", "aarch64"):
        return "mac_apple_silicon"
    # WSL
    if plat == "linux" and os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop"):
        return "windows_wsl"
    # Generic Linux desktop or server
    if plat == "linux" and arch == "x86_64":
        return "linux_x86"
    if plat == "windows":
        return "windows_wsl"  # treat native windows like wsl for our purposes
    return "unknown"


def detect() -> DeviceProfile:
    """Detect the current machine. Safe to call at import time."""
    plat = platform.system().lower()
    arch = platform.machine().lower()
    cpu_count = os.cpu_count() or 1
    ram_gb = _read_meminfo_gb()
    if ram_gb == 0.0:
        # Darwin / Windows fallback: psutil would be the right answer, but
        # we avoid the dep. Approximate from env or just return 8 GB.
        ram_gb = 8.0
    cpu_model = _read_cpuinfo_model()
    gpu_name, gpu_vram = _detect_nvidia_gpu()
    gpu_vendor = "nvidia" if gpu_name else ("apple" if plat == "darwin" else "none")
    device_class = _detect_device_class(plat, arch, cpu_model, ram_gb, gpu_vendor, gpu_name)
    return DeviceProfile(
        platform=plat, arch=arch, device_class=device_class,
        cpu_count=cpu_count, ram_gb=ram_gb,
        gpu_vendor=gpu_vendor, gpu_name=gpu_name, gpu_vram_gb=gpu_vram,
    )


# ---------------------------------------------------------------------------
# Model-fit table.
#
# This is the "which model works on which device" story. Each row answers:
# does this model fit, what's the realistic FPS, which delegate to use, and
# in one sentence why. Keep this table honest: an over-optimistic row shows
# up later as a bad user experience.
# ---------------------------------------------------------------------------

# Rows: (model_key, pi4, pi5, jetson_nano, jetson_orin_nano, mac_apple_silicon, linux_x86, windows_wsl)
# Values: (fits, recommended, ms_per_frame, delegate, reason)
_FIT_TABLE: dict[str, dict[str, tuple[bool, bool, int, str, str]]] = {
    # MediaPipe object detector
    "efficientdet_lite0": {
        "pi4":               (True, True, 220, "cpu-xnnpack", "Pi 4 CPU with XNNPACK; around 4-5 FPS"),
        "pi5":               (True, True, 110, "cpu-xnnpack", "Pi 5 CPU with XNNPACK; around 9 FPS"),
        "jetson_nano":       (True, False, 90, "cpu-xnnpack", "Jetson Nano CPU; GPU delegate often unstable"),
        "jetson_orin_nano":  (True, True, 70,  "cpu-xnnpack", "Orin Nano CPU; set MP_DELEGATE=gpu for 2-3x speedup"),
        "mac_apple_silicon": (True, True, 25,  "cpu-xnnpack", "Apple Silicon CPU is already fast"),
        "linux_x86":         (True, True, 50,  "cpu-xnnpack", "Modern x86 CPU"),
        "windows_wsl":       (True, True, 60,  "cpu-xnnpack", "WSL2 CPU"),
    },
    "efficientdet_lite2": {
        "pi4":               (False, False, 500, "cpu-xnnpack", "too slow on Pi 4; use lite0"),
        "pi5":               (True, False, 240, "cpu-xnnpack", "Pi 5 CPU"),
        "jetson_nano":       (True, False, 200, "cpu-xnnpack", "Jetson Nano CPU"),
        "jetson_orin_nano":  (True, True, 140, "cpu-xnnpack", "Orin Nano, better accuracy than lite0"),
        "mac_apple_silicon": (True, True, 50,  "cpu-xnnpack", "Apple Silicon CPU"),
        "linux_x86":         (True, True, 100, "cpu-xnnpack", "Modern x86 CPU"),
        "windows_wsl":       (True, False, 120, "cpu-xnnpack", "WSL2 CPU"),
    },
    "pose_landmarker_lite": {
        "pi4":               (True, True, 180, "cpu-xnnpack", "Pi 4 CPU; around 5 FPS"),
        "pi5":               (True, True, 90,  "cpu-xnnpack", "Pi 5 CPU"),
        "jetson_nano":       (True, True, 75,  "cpu-xnnpack", "Jetson Nano CPU"),
        "jetson_orin_nano":  (True, True, 55,  "cpu-xnnpack", "Orin Nano CPU"),
        "mac_apple_silicon": (True, True, 20,  "cpu-xnnpack", "Apple Silicon CPU"),
        "linux_x86":         (True, True, 40,  "cpu-xnnpack", "x86 CPU"),
        "windows_wsl":       (True, True, 50,  "cpu-xnnpack", "WSL2 CPU"),
    },
    "pose_landmarker_full": {
        "pi4":               (False, False, 600, "cpu-xnnpack", "too slow on Pi 4; use lite"),
        "pi5":               (True, False, 280, "cpu-xnnpack", "Pi 5 CPU"),
        "jetson_nano":       (True, False, 220, "cpu-xnnpack", "Jetson Nano CPU"),
        "jetson_orin_nano":  (True, True, 160, "cpu-xnnpack", "Orin Nano CPU, better accuracy"),
        "mac_apple_silicon": (True, True, 60,  "cpu-xnnpack", "Apple Silicon CPU"),
        "linux_x86":         (True, True, 120, "cpu-xnnpack", "x86 CPU"),
        "windows_wsl":       (True, False, 150, "cpu-xnnpack", "WSL2 CPU"),
    },
    "segformer_b0_int8": {
        "pi4":               (True, True, 500, "cpu", "scene parse every 3 s only, not per frame"),
        "pi5":               (True, True, 240, "cpu", "every 2 s"),
        "jetson_nano":       (True, True, 180, "cpu", "every 2 s"),
        "jetson_orin_nano":  (True, True, 55,  "cuda", "with CUDA EP; CPU is 180 ms"),
        "mac_apple_silicon": (True, True, 60,  "coreml", "with CoreML EP; CPU is 120 ms"),
        "linux_x86":         (True, True, 110, "cpu", "x86 CPU"),
        "windows_wsl":       (True, True, 140, "cpu", "WSL2 CPU"),
    },
    # Qwen2.5-VL 3B Q4_K_M: the VLM for open-vocabulary action search.
    # This is where device class really matters.
    "qwen2_5_vl_3b_q4": {
        "pi4":               (False, False, 20000, "cpu", "~2.7 GB RAM for weights alone; Pi 4 4 GB cannot fit it"),
        "pi5":               (False, False, 15000, "cpu", "Pi 5 8 GB fits weights but ~15 s per frame; not practical"),
        "jetson_nano":       (False, False, 10000, "cpu", "4 GB RAM is tight; use smaller MiniCPM-V 2.6 or disable VLM"),
        "jetson_orin_nano":  (True, True, 1800, "cuda", "with CUDA; CPU-only is 6 s"),
        "mac_apple_silicon": (True, True, 900, "coreml", "with CoreML; practical for live demo at 1 FPS per VLM call"),
        "linux_x86":         (True, True, 2500, "cpu", "x86 CPU; CUDA EP if NVIDIA GPU present (~400 ms)"),
        "windows_wsl":       (True, False, 3500, "cpu", "WSL2 CPU; works but prefer native Linux"),
    },
}


# Default perception pick per device class. The UI shows this as the one-click
# "recommended for your device" preset.
_DEFAULT_PRESET: dict[str, dict[str, str]] = {
    "pi4": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "none",
        "note": "Rule-based action recognition only. VLM too slow on 4 GB ARM.",
    },
    "pi5": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "none",
        "note": "Rule-based action recognition. VLM technically fits but too slow for live use.",
    },
    "jetson_nano": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "none",
        "note": "Rule-based action recognition. Original Jetson Nano is memory-tight.",
    },
    "jetson_orin_nano": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "qwen2_5_vl_3b_q4",
        "note": "Full stack with VLM via CUDA. Set MP_DELEGATE=gpu for best FPS.",
    },
    "mac_apple_silicon": {
        "detector": "efficientdet_lite2", "pose": "pose_landmarker_full",
        "scene": "segformer_b0_int8", "vlm": "qwen2_5_vl_3b_q4",
        "note": "Full stack. CoreML EP for SegFormer and VLM when available.",
    },
    "linux_x86": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "qwen2_5_vl_3b_q4",
        "note": "Full stack. CUDA EP if NVIDIA GPU detected.",
    },
    "windows_wsl": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "qwen2_5_vl_3b_q4",
        "note": "Full stack. VLM works but prefer native Linux for CUDA.",
    },
    "unknown": {
        "detector": "efficientdet_lite0", "pose": "pose_landmarker_lite",
        "scene": "segformer_b0_int8", "vlm": "none",
        "note": "Could not detect device class; using safe defaults.",
    },
}


def fits_for(model_key: str, device_class: str) -> ModelFit:
    """Lookup fit for a (model, device) pair. Falls back to 'unknown' row."""
    row = _FIT_TABLE.get(model_key, {}).get(device_class)
    if row is None:
        # Unknown model or unknown device: assume CPU, generic, mark not-recommended
        return ModelFit(
            model_key=model_key, fits=True, recommended=False,
            expected_ms_per_frame=500, expected_fps=2.0,
            reason="no fit data for this (model, device) pair",
            delegate="cpu",
        )
    fits, recommended, ms, delegate, reason = row
    fps = round(1000.0 / ms, 1) if ms > 0 else 0.0
    return ModelFit(
        model_key=model_key, fits=fits, recommended=recommended,
        expected_ms_per_frame=ms, expected_fps=fps,
        reason=reason, delegate=delegate,
    )


def preset_for(device_class: str) -> dict[str, str]:
    """Recommended model preset for a device class. UI calls this on load."""
    return dict(_DEFAULT_PRESET.get(device_class, _DEFAULT_PRESET["unknown"]))


def all_fits(device_class: str) -> list[dict[str, Any]]:
    """Full compatibility table for the current device. Useful for the UI
    'all models' view where the user can see every option with its FPS."""
    out = []
    for model_key in _FIT_TABLE:
        f = fits_for(model_key, device_class)
        out.append(asdict(f))
    return out


def report() -> dict[str, Any]:
    """One call that returns device profile + recommended preset + full fit table.
    This is what the UI polls on page load.
    """
    profile = detect()
    preset = preset_for(profile.device_class)
    return {
        "device": asdict(profile),
        "preset": preset,
        "fits": all_fits(profile.device_class),
    }

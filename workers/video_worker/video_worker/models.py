"""Video worker model registry: paths, downloads, device-aware selection.

Models are downloaded on first use into the Arikizu project's models/
directory (resolved via the same project-root walk the vision and audio
workers use). The device profile picks which models to prefetch at startup
so a Pi 4 doesn't try to download a 2 GB VLM it will never use.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Project root walk (identical to vision_worker / audio_worker pattern)
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from CWD until a project marker is found. The Rust supervisor
    spawns workers from workers/, so './models' must resolve to the project
    root, not the worker's package dir."""
    p = Path.cwd().resolve()
    for parent in [p] + list(p.parents):
        if (parent / "arikizu.yaml.example").exists() or \
           (parent / "capabilities.toml").exists() or \
           (parent / "Cargo.toml").exists():
            return parent
    return p


def _resolve_models_dir(env_value: str) -> Path:
    if os.path.isabs(env_value):
        return Path(env_value)
    root = _find_project_root()
    candidate = root / env_value
    if candidate.exists():
        return candidate
    return Path(env_value).resolve()


MODELS_DIR = _resolve_models_dir(os.environ.get("ARIKIZU_MODELS_DIR", "./models"))


# ---------------------------------------------------------------------------
# Registry: one row per downloadable model file.
#
# Each row has:
#   file:     filename on disk (relative to MODELS_DIR)
#   url:      canonical download URL
#   mb:       approximate size in MB
#   backend:  "mediapipe-litert" | "onnx" | "llama-cpp-mmproj"
#   license:  SPDX short name
#   purpose:  one-line human description
# ---------------------------------------------------------------------------

MEDIAPIPE_BASE = "https://storage.googleapis.com/mediapipe-models"
HF_BASE = "https://huggingface.co"

REGISTRY: dict[str, dict[str, Any]] = {
    # Object detection (COCO 80 classes)
    "efficientdet_lite0": {
        "file": "efficientdet_lite0.tflite",
        "url": f"{MEDIAPIPE_BASE}/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite",
        "mb": 4.5, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Object detector, fast (COCO 80 classes)",
    },
    "efficientdet_lite2": {
        "file": "efficientdet_lite2.tflite",
        "url": f"{MEDIAPIPE_BASE}/object_detector/efficientdet_lite2/float16/1/efficientdet_lite2.tflite",
        "mb": 7.5, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Object detector, more accurate",
    },
    # Pose
    "pose_landmarker_lite": {
        "file": "pose_landmarker_lite.task",
        "url": f"{MEDIAPIPE_BASE}/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "mb": 5.8, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Pose landmarks lite (33 points + person mask)",
    },
    "pose_landmarker_full": {
        "file": "pose_landmarker_full.task",
        "url": f"{MEDIAPIPE_BASE}/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
        "mb": 9.4, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Pose landmarks full (more accurate)",
    },
    # Segmentation
    "selfie_segmenter": {
        "file": "selfie_segmenter.tflite",
        "url": f"{MEDIAPIPE_BASE}/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
        "mb": 0.5, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Person segmentation (fast)",
    },
    # Face detection (for privacy blur)
    "blaze_face": {
        "file": "blaze_face_short_range.tflite",
        "url": f"{MEDIAPIPE_BASE}/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        "mb": 0.2, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Face detector for privacy blur",
    },
    # Click-to-segment
    "magic_touch": {
        "file": "magic_touch.tflite",
        "url": f"{MEDIAPIPE_BASE}/interactive_segmenter/magic_touch/float32/1/magic_touch.tflite",
        "mb": 6.0, "backend": "mediapipe-litert", "license": "Apache-2.0",
        "purpose": "Interactive segmentation: click a point, get its outline",
    },
    # Scene parsing (quantized)
    "segformer_b0_int8": {
        "file": "segformer_b0_ade20k_512_int8.onnx",
        "url": f"{HF_BASE}/Xenova/segformer-b0-finetuned-ade-512-512/resolve/main/onnx/model_quantized.onnx",
        "mb": 4.4, "backend": "onnx", "license": "NVIDIA SegFormer license",
        "purpose": "Scene parser int8 (ADE20K 150 classes: wall, floor, person, etc.)",
    },
    "segformer_b0_f16": {
        "file": "segformer_b0_ade20k_512.onnx",
        "url": f"{HF_BASE}/Xenova/segformer-b0-finetuned-ade-512-512/resolve/main/onnx/model.onnx",
        "mb": 15.3, "backend": "onnx", "license": "NVIDIA SegFormer license",
        "purpose": "Scene parser f16 (more accurate, larger)",
    },
    # VLM (multimodal action search)
    "qwen2_5_vl_3b_q4": {
        "file": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
        "url": f"{HF_BASE}/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
        "mb": 2060, "backend": "llama-cpp", "license": "Apache-2.0",
        "purpose": "Qwen2.5-VL 3B Q4 for text and reference-image action search",
    },
    "qwen2_5_vl_3b_mmproj": {
        "file": "Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf",
        "url": f"{HF_BASE}/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf",
        "mb": 700, "backend": "llama-cpp-mmproj", "license": "Apache-2.0",
        "purpose": "Qwen2.5-VL vision projection (required alongside the GGUF)",
    },
}


def path_for(key: str) -> Path:
    return MODELS_DIR / REGISTRY[key]["file"]


def is_present(key: str) -> bool:
    p = path_for(key)
    return p.exists() and p.stat().st_size > 50_000


def ensure(key: str) -> Path:
    """Return the local path, downloading on first use. Raises RuntimeError with
    manual-fix instructions if the download fails."""
    if key not in REGISTRY:
        raise KeyError(f"unknown model key: {key!r}")
    spec = REGISTRY[key]
    dest = path_for(key)
    if is_present(key):
        return dest
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError(
            f"httpx required for model download; install with: pip install httpx. "
            f"Or download manually from {spec['url']} and save as {dest}"
        ) from e
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[video_worker.models] downloading {spec['file']} (~{spec['mb']} MB)...", flush=True)
    try:
        with tempfile.NamedTemporaryFile(dir=MODELS_DIR, suffix=".part", delete=False) as tmp:
            part = Path(tmp.name)
            with httpx.stream("GET", spec["url"], timeout=120, follow_redirects=True) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 16):
                    tmp.write(chunk)
        if part.stat().st_size < 50_000:
            raise RuntimeError("downloaded file is too small to be a model")
        part.replace(dest)
    except Exception as exc:
        try:
            part.unlink(missing_ok=True)   # noqa: F821 (part defined inside try)
        except Exception:
            pass
        raise RuntimeError(
            f"Could not download {spec['file']}: {exc}. "
            f"Download it manually from {spec['url']} and save it as {dest}"
        ) from exc
    print(f"[video_worker.models] ok: {dest}", flush=True)
    return dest


def status() -> dict[str, Any]:
    """Which models exist on disk right now."""
    rows = {}
    for key, spec in REGISTRY.items():
        p = path_for(key)
        rows[key] = {
            "file": spec["file"],
            "present": is_present(key),
            "size_mb": round(p.stat().st_size / (1024 * 1024), 1) if p.exists() else 0,
            "backend": spec["backend"],
            "purpose": spec["purpose"],
        }
    return {"dir": str(MODELS_DIR), "models": rows}


def prefetch_for_device(device_class: str) -> list[str]:
    """Which model keys the current device actually benefits from downloading."""
    from .devices import preset_for
    preset = preset_for(device_class)
    keys = [preset["detector"], preset["pose"], preset["scene"],
            "blaze_face", "magic_touch", "selfie_segmenter"]
    if preset["vlm"] != "none":
        keys += [preset["vlm"], "qwen2_5_vl_3b_mmproj"]
    # Dedupe, preserve order
    seen = set()
    out = []
    for k in keys:
        if k not in seen and k in REGISTRY:
            seen.add(k)
            out.append(k)
    return out


if __name__ == "__main__":
    # python -m video_worker.models  -> prefetch everything for current device
    from .devices import detect
    profile = detect()
    print(f"device: {profile.device_class} ({profile.arch}, {profile.ram_gb} GB RAM)")
    print(f"models dir: {MODELS_DIR}")
    print()
    for key in prefetch_for_device(profile.device_class):
        try:
            path = ensure(key)
            print(f"  OK  {key}: {path}")
        except RuntimeError as exc:
            print(f"  FAIL {key}: {exc}")

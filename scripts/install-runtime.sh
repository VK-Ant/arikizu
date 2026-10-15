#!/usr/bin/env bash
# Detect what accelerators are on this device and pip-install the matching
# model runtime(s). Runs on first boot of the Pi image; also safe to run
# by hand on a laptop or Jetson.
#
# Idempotent: re-running just verifies the install.
#
# What this does:
#   NVIDIA GPU present              -> onnxruntime-gpu (CUDA EP)
#   Jetson (JetPack 6)              -> onnxruntime-gpu from Jetson AI Lab index
#   Hailo-8 (Pi 5 AI HAT+)          -> hailo-all via apt + hailo-platform pip
#   Apple Silicon                   -> onnxruntime + coremltools
#   Intel CPU                       -> openvino + onnxruntime
#   Plain ARM Pi (no accelerator)   -> onnxruntime (CPU only)
#   Other / fallback                -> onnxruntime (CPU only)
#
# Prints a one-line summary at the end.

set -eu

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; RESET=$'\033[0m'

PY="${PYTHON:-python3}"
UV_PATH="$(command -v uv || true)"

if ! "$PY" --version >/dev/null 2>&1; then
    echo "${RED}no python3 on PATH${RESET}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Detect
# ---------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
IS_JETSON=0
IS_HAILO=0
HAS_NVIDIA=0
IS_APPLE=0
IS_INTEL_CPU=0

if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    IS_APPLE=1
fi

if [ "$OS" = "Linux" ]; then
    if [ -f /etc/nv_tegra_release ] || grep -qi jetson /proc/device-tree/model 2>/dev/null; then
        IS_JETSON=1
    fi
    if ls /dev/hailo* >/dev/null 2>&1 || grep -q hailo /proc/modules 2>/dev/null; then
        IS_HAILO=1
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        HAS_NVIDIA=1
    fi
    if grep -qi "GenuineIntel" /proc/cpuinfo 2>/dev/null; then
        IS_INTEL_CPU=1
    fi
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
echo "${GREY}OS=$OS arch=$ARCH  jetson=$IS_JETSON hailo=$IS_HAILO nvidia=$HAS_NVIDIA apple=$IS_APPLE intel=$IS_INTEL_CPU${RESET}"

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
# Which pip to use. Prefer uv if it's available (faster, builds nothing).
if [ -n "$UV_PATH" ]; then
    pip_install() { uv pip install --python "$PY" "$@" || "$PY" -m pip install --break-system-packages --user "$@" 2>/dev/null || "$PY" -m pip install --user "$@"; }
else
    pip_install() { "$PY" -m pip install --break-system-packages --user "$@" 2>/dev/null || "$PY" -m pip install --user "$@"; }
fi

INSTALLED=()

if [ "$IS_JETSON" = "1" ]; then
    echo "${GREEN}Jetson detected; installing onnxruntime-gpu from Jetson AI Lab index${RESET}"
    pip_install --index-url https://pypi.jetson-ai-lab.dev/jp6/cu126 onnxruntime-gpu || \
      pip_install onnxruntime
    INSTALLED+=("onnxruntime-gpu (Jetson)")
elif [ "$HAS_NVIDIA" = "1" ]; then
    echo "${GREEN}NVIDIA GPU detected; installing onnxruntime-gpu${RESET}"
    pip_install onnxruntime-gpu
    INSTALLED+=("onnxruntime-gpu")
else
    echo "${GREY}no NVIDIA / Jetson; installing onnxruntime CPU${RESET}"
    pip_install onnxruntime
    INSTALLED+=("onnxruntime (CPU)")
fi

if [ "$IS_HAILO" = "1" ]; then
    echo "${GREEN}Hailo-8 detected; installing hailo-platform${RESET}"
    pip_install hailo-platform || echo "${YELLOW}hailo-platform install failed; apt install hailo-all first${RESET}"
    INSTALLED+=("hailo-platform")
fi

if [ "$IS_APPLE" = "1" ]; then
    echo "${GREEN}Apple Silicon detected; installing coremltools${RESET}"
    pip_install coremltools
    INSTALLED+=("coremltools")
fi

if [ "$OS" = "Linux" ] && [ "$IS_INTEL_CPU" = "1" ] && [ "$HAS_NVIDIA" = "0" ] && [ "$IS_JETSON" = "0" ]; then
    echo "${GREEN}Intel CPU on Linux; also installing openvino${RESET}"
    pip_install openvino || echo "${YELLOW}openvino install failed; continuing${RESET}"
    INSTALLED+=("openvino")
fi

# Always add tflite-runtime as a cheap option; it's small.
if ! "$PY" -c "import tflite_runtime" 2>/dev/null && ! "$PY" -c "import tensorflow" 2>/dev/null; then
    pip_install tflite-runtime 2>/dev/null && INSTALLED+=("tflite-runtime") || true
fi

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
echo
echo "${GREY}verifying what Python can import...${RESET}"
"$PY" <<'PYEOF'
import importlib
checks = [
    ("onnxruntime", "ONNX Runtime"),
    ("tflite_runtime.interpreter", "TFLite"),
    ("openvino", "OpenVINO"),
    ("coremltools", "CoreML"),
    ("torch", "PyTorch"),
    ("hailo_platform", "Hailo"),
]
for mod, label in checks:
    try:
        importlib.import_module(mod)
        print(f"  OK   {label}")
    except ImportError:
        print(f"  --   {label}")

try:
    import onnxruntime as ort
    print(f"  ONNX providers: {ort.get_available_providers()}")
except ImportError:
    pass
PYEOF

echo
if [ ${#INSTALLED[@]} -gt 0 ]; then
    echo "${GREEN}installed:${RESET} ${INSTALLED[*]}"
else
    echo "${YELLOW}nothing installed; environment may already be set up${RESET}"
fi
echo "see docs/MODEL_OPTIMIZATION.md for how to add other runtimes."

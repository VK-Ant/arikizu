#!/usr/bin/env bash
# Download default models for Arikizu workers, tiered by device capability.
#
# Tiers (see docs/MODEL_CATALOG.md):
#   minimum   ~8 MB     any Pi, including Pi Zero 2W
#   standard  ~215 MB   Pi 4 (4 GB) and up
#   full      ~2 GB     Pi 5 (8 GB), Jetson, bigger
#
# Idempotent: files already present with the right sha are kept.
#
# Usage:
#   scripts/download-default-models.sh                     # minimum
#   scripts/download-default-models.sh --tier standard
#   scripts/download-default-models.sh --tier full
#   scripts/download-default-models.sh --models-dir /var/lib/arikizu/models

set -eu

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
TIER="minimum"

while [ $# -gt 0 ]; do
    case "$1" in
        --models-dir) MODELS_DIR="$2"; shift 2 ;;
        --tier)       TIER="$2"; shift 2 ;;
        --with)       # kept for back-compat; whisper is in standard tier now
                      [ "$2" = "whisper" ] && TIER="standard"; shift 2 ;;
        -h|--help)
            sed -n '2,/^set -eu/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

case "$TIER" in
    minimum|standard|full) ;;
    *) echo "unknown tier: $TIER (expected: minimum|standard|full)" >&2; exit 2 ;;
esac

mkdir -p "$MODELS_DIR"

GREEN=$'\033[32m'; GREY=$'\033[90m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

fetch() {
    local url="$1" out="$2" expected="${3:-}"
    local dest="$MODELS_DIR/$out"
    if [ -f "$dest" ]; then
        if [ -n "$expected" ]; then
            actual="$(sha256 "$dest")"
            if [ "$actual" = "$expected" ]; then
                echo "${GREEN}  OK  ${RESET}${out} (${GREY}already present, sha verified${RESET})"
                return 0
            fi
            echo "${YELLOW}  --  ${RESET}${out} present but sha differs; refetching"
            rm -f "$dest"
        else
            echo "${GREEN}  OK  ${RESET}${out} (${GREY}already present, no sha pinned${RESET})"
            return 0
        fi
    fi
    echo "${GREY}  ..  fetching ${out}${RESET}"
    curl -fL --retry 3 --retry-delay 2 -o "$dest" "$url" 2>/dev/null || {
        echo "${YELLOW}  !!  failed to fetch ${url}${RESET}"
        rm -f "$dest"
        return 1
    }
    if [ -n "$expected" ]; then
        actual="$(sha256 "$dest")"
        if [ "$actual" != "$expected" ]; then
            echo "${YELLOW}  !!  sha mismatch for ${out} (expected ${expected} got ${actual})${RESET}"
            rm -f "$dest"
            return 1
        fi
    fi
    size=$(du -h "$dest" | awk '{print $1}')
    echo "${GREEN}  OK  ${RESET}${out} (${size})"
}

write_manifest() {
    local file="$1" desc="$2" backend="$3" license="$4"
    local full="$MODELS_DIR/$file"
    [ -f "$full" ] || return
    local sha size
    sha="$(sha256 "$full")"
    size="$(stat -c%s "$full" 2>/dev/null || stat -f%z "$full")"
    cat > "$full.json" <<JEOF
{
  "name": "${file%.*}",
  "sha256": "$sha",
  "size_bytes": $size,
  "backend": "$backend",
  "description": "$desc"
}
JEOF
}

# ---------------------------------------------------------------------------
# tier: minimum
# ---------------------------------------------------------------------------
echo "${GREEN}tier: ${TIER}${RESET}  →  ${MODELS_DIR}"
echo

echo "vision:"
fetch \
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.onnx" \
    "yolov8n.onnx" \
    "" && \
    write_manifest "yolov8n.onnx" "YOLOv8-nano object detection (COCO 80 classes)" "onnx" "AGPL-3.0"

echo
echo "audio:"
fetch \
    "https://github.com/snakers4/silero-vad/raw/v5.1/src/silero_vad/data/silero_vad.onnx" \
    "silero_vad.onnx" \
    "" && \
    write_manifest "silero_vad.onnx" "Silero voice activity detection" "onnx" "MIT"

# Tiny sklearn baselines for timeseries + memory, generated locally if python+sklearn present.
echo
echo "timeseries / memory (sklearn joblib baselines):"
if command -v python3 >/dev/null 2>&1 && python3 -c "import sklearn" 2>/dev/null; then
    python3 - <<PYEOF
import joblib, numpy as np, os
from sklearn.ensemble import IsolationForest
d = os.environ.get("ARIKIZU_MODELS_DIR", "$MODELS_DIR")
# Isolation Forest baseline (fit on a sine wave).
rng = np.random.default_rng(0)
sig = np.sin(np.linspace(0, 10*np.pi, 1000)).reshape(-1, 1) + rng.normal(0, 0.05, (1000, 1))
m = IsolationForest(contamination=0.01, random_state=0).fit(sig)
joblib.dump(m, f"{d}/anomaly_iforest.joblib")
print(f"  OK  anomaly_iforest.joblib")
# Reward bandit baseline (trivial 3-arm Thompson sampler state).
bandit = {"arms": 3, "alpha": [1.0, 1.0, 1.0], "beta": [1.0, 1.0, 1.0]}
joblib.dump(bandit, f"{d}/reward_bandit.joblib")
print(f"  OK  reward_bandit.joblib")
PYEOF
else
    echo "${YELLOW}  --  python3 + sklearn not available; skipping joblib baselines${RESET}"
    echo "       install with: pip install scikit-learn joblib"
fi

# ---------------------------------------------------------------------------
# tier: standard
# ---------------------------------------------------------------------------
if [ "$TIER" = "standard" ] || [ "$TIER" = "full" ]; then
    echo
    echo "audio (standard):"
    fetch \
        "https://huggingface.co/openai/whisper-tiny.en/resolve/main/onnx/encoder_model.onnx" \
        "whisper-tiny.en-encoder.onnx" \
        "" && \
        write_manifest "whisper-tiny.en-encoder.onnx" "Whisper tiny.en encoder" "onnx" "MIT"

    echo
    echo "embeddings (shared by docs, memory, eval):"
    fetch \
        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx" \
        "all-MiniLM-L6-v2.onnx" \
        "" && \
        write_manifest "all-MiniLM-L6-v2.onnx" "Sentence embedding (MiniLM-L6)" "onnx" "Apache-2.0"
    fetch \
        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json" \
        "all-MiniLM-L6-v2.tokenizer.json" \
        "" || true

    echo
    echo "vision (standard):"
    fetch \
        "https://huggingface.co/ChaoningZhang/MobileSAM/resolve/main/mobile_sam.onnx" \
        "mobile_sam.onnx" \
        "" && \
        write_manifest "mobile_sam.onnx" "MobileSAM lightweight segmentation" "onnx" "Apache-2.0"

    echo
    echo "reasoning (small local LLM, ~400 MB):"
    fetch \
        "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf" \
        "qwen2.5-0.5b-instruct-q4_k_m.gguf" \
        "" && \
        write_manifest "qwen2.5-0.5b-instruct-q4_k_m.gguf" "Small instruct LLM (Q4 quantized)" "llama-cpp" "Apache-2.0"
fi

# ---------------------------------------------------------------------------
# tier: full
# ---------------------------------------------------------------------------
if [ "$TIER" = "full" ]; then
    echo
    echo "docs (full tier; ~600 MB):"
    fetch \
        "https://huggingface.co/microsoft/table-transformer-detection/resolve/main/onnx/model.onnx" \
        "table-transformer.onnx" \
        "" && \
        write_manifest "table-transformer.onnx" "Table detection in documents" "onnx" "MIT"
    # LayoutLM is big; comment out to keep the default from being 500MB+
    # fetch \
    #     "https://huggingface.co/microsoft/layoutlmv3-base/resolve/main/onnx/model.onnx" \
    #     "layoutlmv3-base.onnx" \
    #     "" && \
    #     write_manifest "layoutlmv3-base.onnx" "LayoutLMv3 base" "onnx" "CC-BY-NC-SA"

    echo
    echo "vision (full tier):"
    fetch \
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.onnx" \
        "yolov8s.onnx" \
        "" && \
        write_manifest "yolov8s.onnx" "YOLOv8-small (COCO)" "onnx" "AGPL-3.0"

    echo
    echo "audio (full tier):"
    fetch \
        "https://huggingface.co/openai/whisper-small.en/resolve/main/onnx/encoder_model.onnx" \
        "whisper-small.en-encoder.onnx" \
        "" && \
        write_manifest "whisper-small.en-encoder.onnx" "Whisper small.en encoder" "onnx" "MIT"
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
echo
echo "models dir: $MODELS_DIR"
total=$(du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}')
echo "total size: ${total:-unknown}"
echo
echo "Files:"
ls -lh "$MODELS_DIR" | awk 'NR>1 {printf "  %-45s %8s\n", $NF, $5}'
echo
echo "Env vars to point workers at these:"
echo "  export ARIKIZU_MODELS_DIR=$MODELS_DIR"
echo "  export ARIKIZU_VISION_MODEL=$MODELS_DIR/yolov8n.onnx"
if [ "$TIER" != "minimum" ]; then
    echo "  export ARIKIZU_EMBEDDER_MODEL=$MODELS_DIR/all-MiniLM-L6-v2.onnx"
fi
echo
echo "see docs/MODEL_CATALOG.md for the full list per worker and upgrade paths."

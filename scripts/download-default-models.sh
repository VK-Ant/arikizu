#!/usr/bin/env bash
# Download default model assets for Arikizu workers.
#
# Tiers:
#   minimum  lightweight vision + voice-activity models
#   standard minimum + embeddings + small local LLM + complete Whisper tiny.en assets
#   full     standard + larger vision/document models
#
# Downloads are atomic, existing files are reused, and optional SHA-256 values
# are verified when supplied. See docs/MODEL_CATALOG.md for runtime requirements.
#
# Usage:
#   scripts/download-default-models.sh
#   scripts/download-default-models.sh --tier standard
#   scripts/download-default-models.sh --tier full
#   scripts/download-default-models.sh --models-dir /var/lib/arikizu/models

set -Eeuo pipefail

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
TIER="minimum"

usage() {
    sed -n '2,/^set -Eeuo pipefail/p' "$0" | sed 's/^# \{0,1\}//'
}
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while (($#)); do
    case "$1" in
        --models-dir)
            (($# >= 2)) || fail "--models-dir requires a path"
            MODELS_DIR="$2"; shift 2 ;;
        --tier)
            (($# >= 2)) || fail "--tier requires minimum, standard, or full"
            TIER="$2"; shift 2 ;;
        --with)
            (($# >= 2)) || fail "--with requires a value"
            # Backwards compatibility with the old CLI.
            case "$2" in
                whisper) TIER=standard ;;
                *) fail "unsupported --with value: $2 (supported: whisper)" ;;
            esac
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
done

case "$TIER" in minimum|standard|full) ;; *) fail "unknown tier: $TIER (expected: minimum|standard|full)" ;; esac
command -v curl >/dev/null 2>&1 || fail "curl is required"
if command -v sha256sum >/dev/null 2>&1; then
    sha256() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
    sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
else
    fail "sha256sum or shasum is required"
fi

mkdir -p "$MODELS_DIR" || fail "cannot create models directory: $MODELS_DIR"
# Resolve relative paths once so the Python baseline generation uses the same path.
case "$MODELS_DIR" in /*) ;; *) MODELS_DIR="$PWD/$MODELS_DIR" ;; esac

GREEN=$'\033[32m'; GREY=$'\033[90m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

fetch() {
    local url="$1" out="$2" expected="${3:-}"
    local dest="$MODELS_DIR/$out" tmp actual

    if [[ -f "$dest" ]]; then
        if [[ -n "$expected" ]]; then
            actual="$(sha256 "$dest")"
            if [[ "$actual" == "$expected" ]]; then
                printf '%s  OK  %s%s (already present; SHA-256 verified)\n' "$GREEN" "$out" "$RESET"
                return 0
            fi
            printf '%s  --  %s present but checksum differs; downloading again%s\n' "$YELLOW" "$out" "$RESET"
        else
            # Without a pinned checksum, retain a non-empty existing file. We cannot
            # claim cryptographic verification for it.
            if [[ -s "$dest" ]]; then
                printf '%s  OK  %s%s (already present; checksum not pinned)\n' "$GREEN" "$out" "$RESET"
                return 0
            fi
        fi
    fi

    tmp="$(mktemp "$MODELS_DIR/.${out}.part.XXXXXX")" || fail "cannot create temporary file in $MODELS_DIR"
    printf '%s  ..  fetching %s%s\n' "$GREY" "$out" "$RESET"
    if ! curl --fail --location --silent --show-error --retry 3 --retry-delay 2 \
        --connect-timeout 20 --output "$tmp" "$url"; then
        printf '%s  !!  failed to fetch %s%s\n' "$YELLOW" "$url" "$RESET" >&2
        rm -f "$tmp"
        return 1
    fi
    if [[ ! -s "$tmp" ]]; then
        printf '%s  !!  downloaded file is empty: %s%s\n' "$YELLOW" "$out" "$RESET" >&2
        rm -f "$tmp"
        return 1
    fi
    if [[ -n "$expected" ]]; then
        actual="$(sha256 "$tmp")"
        if [[ "$actual" != "$expected" ]]; then
            printf '%s  !!  SHA-256 mismatch for %s (expected %s, got %s)%s\n' "$YELLOW" "$out" "$expected" "$actual" "$RESET" >&2
            rm -f "$tmp"
            return 1
        fi
    fi
    mv -f "$tmp" "$dest"
    printf '%s  OK  %s%s (%s)\n' "$GREEN" "$out" "$RESET" "$(du -h "$dest" | awk '{print $1}')"
}

write_manifest() {
    local file="$1" desc="$2" backend="$3" license="$4"
    local full="$MODELS_DIR/$file" sha size
    [[ -f "$full" ]] || return 0
    sha="$(sha256 "$full")"
    size="$(wc -c < "$full" | tr -d '[:space:]')"
    # Values used here are static strings in this script; keep JSON fields explicit.
    cat > "$full.json" <<JEOF
{
  "name": "${file%.*}",
  "file": "$file",
  "sha256": "$sha",
  "size_bytes": $size,
  "backend": "$backend",
  "license": "$license",
  "description": "$desc"
}
JEOF
}

fetch_manifest() {
    local url="$1" file="$2" desc="$3" backend="$4" license="$5" expected="${6:-}"
    fetch "$url" "$file" "$expected" || return 1
    write_manifest "$file" "$desc" "$backend" "$license"
}

printf '%stier: %s%s  →  %s\n\n' "$GREEN" "$TIER" "$RESET" "$MODELS_DIR"

# ---------------------------------------------------------------------------
# Minimum tier: lightweight models only. No LLM is downloaded in this tier.
# ---------------------------------------------------------------------------
echo 'vision:'
if ! fetch_manifest \
    'https://huggingface.co/Xenova/yolov8n/resolve/main/onnx/model.onnx' \
    'yolov8n.onnx' 'Compact object detector (ONNX, 80 classes)' 'onnx' 'AGPL-3.0'; then
    echo '  Primary Hugging Face URL failed; trying the Ultralytics release mirror.' >&2
    fetch_manifest \
        'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.onnx' \
        'yolov8n.onnx' 'Compact object detector (ONNX, 80 classes)' 'onnx' 'AGPL-3.0' || fail 'could not download yolov8n.onnx'
fi

echo
echo 'audio:'
fetch_manifest \
    'https://huggingface.co/onnx-community/silero-vad/resolve/main/onnx/model.onnx' \
    'silero_vad.onnx' 'Silero voice activity detection' 'onnx' 'MIT' || {
        # Preserve the previously used upstream URL as a fallback.
        fetch_manifest \
            'https://github.com/snakers4/silero-vad/raw/v5.1/src/silero_vad/data/silero_vad.onnx' \
            'silero_vad.onnx' 'Silero voice activity detection' 'onnx' 'MIT' || fail 'could not download silero_vad.onnx'
    }

# Generate optional local baselines only when the dependencies are available.
echo
echo 'timeseries / memory (optional sklearn baselines):'
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sklearn, joblib, numpy' >/dev/null 2>&1; then
    ARIKIZU_MODELS_DIR="$MODELS_DIR" python3 - <<'PYEOF'
import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

root = os.environ["ARIKIZU_MODELS_DIR"]
os.makedirs(root, exist_ok=True)

anomaly_path = os.path.join(root, "anomaly_iforest.joblib")
if not os.path.exists(anomaly_path):
    rng = np.random.default_rng(0)
    signal = np.sin(np.linspace(0, 10 * np.pi, 1000)).reshape(-1, 1)
    signal += rng.normal(0, 0.05, (1000, 1))
    model = IsolationForest(contamination=0.01, random_state=0).fit(signal)
    joblib.dump(model, anomaly_path)
print("  OK  anomaly_iforest.joblib")

bandit_path = os.path.join(root, "reward_bandit.joblib")
if not os.path.exists(bandit_path):
    bandit = {"arms": 3, "alpha": [1.0, 1.0, 1.0], "beta": [1.0, 1.0, 1.0]}
    joblib.dump(bandit, bandit_path)
print("  OK  reward_bandit.joblib")
PYEOF
else
    printf '%s  --  python3 + numpy + scikit-learn + joblib not available; skipping baselines%s\n' "$YELLOW" "$RESET"
    echo '       install with: python3 -m pip install numpy scikit-learn joblib'
fi

# ---------------------------------------------------------------------------
# Standard tier: embeddings, local LLM, and complete Whisper tiny.en assets.
# ---------------------------------------------------------------------------
if [[ "$TIER" == standard || "$TIER" == full ]]; then
    echo
echo 'embeddings:'
    fetch_manifest \
        'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx' \
        'all-MiniLM-L6-v2.onnx' 'Sentence embedding model (MiniLM-L6-v2)' 'onnx' 'Apache-2.0' || fail 'could not download embedding model'
    fetch_manifest \
        'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json' \
        'all-MiniLM-L6-v2.tokenizer.json' 'Tokenizer for MiniLM-L6-v2' 'tokenizer' 'Apache-2.0' || fail 'could not download embedding tokenizer'

    echo
echo 'reasoning (small instruct LLM):'
    fetch_manifest \
        'https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/main/smollm2-360m-instruct-q4_k_m.gguf' \
        'smollm2-360m-instruct-q4_k_m.gguf' 'Small instruct LLM (Q4_K_M)' 'llama-cpp' 'Apache-2.0' || fail 'could not download SmolLM2 GGUF; verify the repository filename'

    echo
echo 'audio (Whisper tiny.en; encoder + decoder + tokenizer/config assets):'
    WHISPER_BASE='https://huggingface.co/onnx-community/whisper-tiny.en-ONNX/resolve/main'
    fetch_manifest "$WHISPER_BASE/onnx/encoder_model.onnx" 'whisper-tiny.en-encoder.onnx' 'Whisper tiny.en encoder' 'onnx' 'MIT' || fail 'could not download Whisper encoder'
    fetch_manifest "$WHISPER_BASE/onnx/decoder_model_merged_quantized.onnx" 'whisper-tiny.en-decoder-merged-quantized.onnx' 'Whisper tiny.en merged quantized decoder' 'onnx' 'MIT' || fail 'could not download Whisper decoder'
    for asset in config.json generation_config.json preprocessor_config.json tokenizer.json tokenizer_config.json vocab.json merges.txt special_tokens_map.json added_tokens.json; do
        fetch "$WHISPER_BASE/$asset" "whisper-tiny.en-$asset" '' || fail "could not download Whisper asset: $asset"
    done
    for asset in config.json generation_config.json preprocessor_config.json tokenizer.json tokenizer_config.json vocab.json merges.txt special_tokens_map.json added_tokens.json; do
        write_manifest "whisper-tiny.en-$asset" "Whisper tiny.en $asset" 'huggingface-transformers' 'MIT'
    done
fi

# ---------------------------------------------------------------------------
# Full tier: larger vision model and document table detection.
# ---------------------------------------------------------------------------
if [[ "$TIER" == full ]]; then
    echo
echo 'documents:'
    fetch_manifest \
        'https://huggingface.co/microsoft/table-transformer-detection/resolve/main/onnx/model.onnx' \
        'table-transformer.onnx' 'Table detection in documents' 'onnx' 'MIT' || fail 'could not download table-transformer.onnx'

    echo
echo 'vision:'
    fetch_manifest \
        'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.onnx' \
        'yolov8s.onnx' 'YOLOv8-small object detector (COCO)' 'onnx' 'AGPL-3.0' || fail 'could not download yolov8s.onnx'
fi

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
echo
echo "models dir: $MODELS_DIR"
printf 'total size: %s\n' "$(du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}')"
echo
echo 'Files:'
find "$MODELS_DIR" -maxdepth 1 -type f ! -name '*.part.*' -printf '%f\t%s bytes\n' 2>/dev/null | sort | while IFS=$'\t' read -r name size; do
    printf '  %-52s %12s\n' "$name" "$size"
done

echo
echo 'Environment variable:'
echo "  export ARIKIZU_MODELS_DIR='$MODELS_DIR'"
echo "  export ARIKIZU_VISION_MODEL='$MODELS_DIR/yolov8n.onnx'"
if [[ "$TIER" != minimum ]]; then
    echo "  export ARIKIZU_EMBEDDER_MODEL='$MODELS_DIR/all-MiniLM-L6-v2.onnx'"
    echo "  export ARIKIZU_LLM_MODEL='$MODELS_DIR/smollm2-360m-instruct-q4_k_m.gguf'"
fi
echo
echo 'Note: downloaded assets are not automatically guaranteed to match every worker runtime. Check docs/MODEL_CATALOG.md for each worker’s expected format and preprocessing.'

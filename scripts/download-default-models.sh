#!/usr/bin/env bash
# Download default models for Arikizu workers, tiered by device capability.
#
# Tiers:
#   minimum  - compact vision/VAD models and a small LLM
#   standard - minimum + embeddings, Whisper tiny encoder, and Qwen 0.5B
#   full     - standard + table detection, YOLOv8s, and Whisper small encoder
#
# Usage:
#   scripts/download-default-models.sh
#   scripts/download-default-models.sh --tier standard
#   scripts/download-default-models.sh --tier full
#   scripts/download-default-models.sh --models-dir /var/lib/arikizu/models

set -Eeuo pipefail

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
TIER="minimum"
FORCE=0

usage() {
    sed -n '2,/^set -Eeuo pipefail/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'
    cat <<'USAGE'
Options:
  --models-dir DIR  Directory for downloaded model files
  --tier TIER       minimum, standard, or full
  --with whisper    Backward-compatible alias for --tier standard
  -h, --help        Show this help
USAGE
}

while (($#)); do
    case "$1" in
        --models-dir)
            (($# >= 2)) || { echo "error: --models-dir requires a value" >&2; exit 2; }
            MODELS_DIR="$2"; shift 2 ;;
        --tier)
            (($# >= 2)) || { echo "error: --tier requires a value" >&2; exit 2; }
            TIER="$2"; shift 2 ;;
        --with)
            (($# >= 2)) || { echo "error: --with requires a value" >&2; exit 2; }
            [[ "$2" == "whisper" ]] || { echo "error: unsupported --with value: $2" >&2; exit 2; }
            TIER="standard"; shift 2 ;;
        -f|--force)
            FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$TIER" in minimum|standard|full) ;; *) echo "error: unknown tier '$TIER' (expected minimum, standard, or full)" >&2; exit 2 ;; esac

command -v curl >/dev/null 2>&1 || { echo "error: curl is required" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
    sha256_file() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
    sha256_file() { shasum -a 256 "$1" | awk '{print $1}'; }
else
    echo "error: sha256sum or shasum is required" >&2; exit 1
fi

mkdir -p "$MODELS_DIR"
# Normalize the directory to an absolute path so Python and manifests agree.
MODELS_DIR="$(cd "$MODELS_DIR" && pwd)"
export ARIKIZU_MODELS_DIR="$MODELS_DIR"

GREEN=$'\033[32m'; GREY=$'\033[90m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
FAILURES=0

fetch() {
    local url="$1" out="$2" expected_sha="${3:-}" dest="$MODELS_DIR/$2" tmp actual
    if [[ -f "$dest" ]]; then
        if (( FORCE )); then
            printf '%s  !!  %s%s --force set; will replace once download succeeds\n' "$YELLOW" "$out" "$RESET"
            # Do NOT rm the old file here. A failed download would leave
            # the user with nothing. The rename at the end is atomic.
        elif [[ -n "$expected_sha" ]]; then
            actual="$(sha256_file "$dest")"
            if [[ "$actual" == "$expected_sha" ]]; then
                printf '%s  OK  %s%s (already present; SHA-256 verified)\n' "$GREEN" "$out" "$RESET"
                return 0
            fi
            printf '%s  !!  %s%s checksum differs; downloading again\n' "$YELLOW" "$out" "$RESET"
        else
            printf '%s  --  %s%s already exists (checksum not pinned; keeping file; use --force to refresh)\n' "$YELLOW" "$out" "$RESET"
            return 0
        fi
    fi

    tmp="$dest.part.$$"
    rm -f "$tmp"
    printf '%s  ..  downloading %s%s\n' "$GREY" "$out" "$RESET"
    if ! curl --fail --location --show-error --retry 3 --retry-delay 2 --connect-timeout 20 \
        --output "$tmp" "$url"; then
        printf '%s  !!  download failed: %s%s\n' "$RED" "$url" "$RESET" >&2
        rm -f "$tmp"
        return 1
    fi
    if [[ ! -s "$tmp" ]]; then
        printf '%s  !!  downloaded file is empty: %s%s\n' "$RED" "$out" "$RESET" >&2
        rm -f "$tmp"
        return 1
    fi
    if [[ -n "$expected_sha" ]]; then
        actual="$(sha256_file "$tmp")"
        if [[ "$actual" != "$expected_sha" ]]; then
            printf '%s  !!  SHA-256 mismatch for %s (expected %s, got %s)%s\n' "$RED" "$out" "$expected_sha" "$actual" "$RESET" >&2
            rm -f "$tmp"
            return 1
        fi
    fi
    mv -f "$tmp" "$dest"
    if command -v du >/dev/null 2>&1; then
        printf '%s  OK  %s%s (%s)\n' "$GREEN" "$out" "$RESET" "$(du -h "$dest" | awk '{print $1}')"
    else
        printf '%s  OK  %s%s\n' "$GREEN" "$out" "$RESET"
    fi
}

write_manifest() {
    local file="$1" desc="$2" backend="$3" license="$4"
    local full="$MODELS_DIR/$file" sha size tmp
    [[ -f "$full" ]] || return 0
    sha="$(sha256_file "$full")"
    if stat -c%s "$full" >/dev/null 2>&1; then size="$(stat -c%s "$full")"; else size="$(stat -f%z "$full")"; fi
    tmp="$full.json.tmp.$$"
    # Escape strings as JSON safely using Python when available; metadata values here are static.
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$file" "$sha" "$size" "$backend" "$desc" "$license" > "$tmp" <<'PY'
import json, sys
name, sha, size, backend, description, license_name = sys.argv[1:]
print(json.dumps({"name": name, "sha256": sha, "size_bytes": int(size), "backend": backend, "description": description, "license": license_name}, indent=2))
PY
    else
        printf '{\n  "name": "%s",\n  "sha256": "%s",\n  "size_bytes": %s,\n  "backend": "%s",\n  "description": "%s",\n  "license": "%s"\n}\n' "${file%.*}" "$sha" "$size" "$backend" "$desc" "$license" > "$tmp"
    fi
    mv -f "$tmp" "$full.json"
}

fetch_and_manifest() {
    local url="$1" file="$2" desc="$3" backend="$4" license="$5" sha="${6:-}"
    if fetch "$url" "$file" "$sha"; then
        write_manifest "$file" "$desc" "$backend" "$license"
        return 0
    else
        printf '%s  !!  skipping manifest for %s because download failed%s\n' "$YELLOW" "$file" "$RESET" >&2
        FAILURES=$((FAILURES + 1))
        return 1
    fi
}

# Try several mirrors in order; stop on the first success. On any
# success, the FAILURES counter is reverted since the asset is on disk.
# Call shape:
#   try_mirrors FILE DESC BACKEND LICENSE URL1 [URL2 URL3 ...]
try_mirrors() {
    local file="$1" desc="$2" backend="$3" license="$4"
    shift 4
    local url
    for url in "$@"; do
        if fetch_and_manifest "$url" "$file" "$desc" "$backend" "$license"; then
            return 0
        fi
        printf '  --  trying next mirror...\n'
    done
    return 1
}

printf '%stier: %s%s  ->  %s\n' "$GREEN" "$TIER" "$RESET" "$MODELS_DIR"
printf '%s(yolov8n.onnx and silero_vad.onnx ship pre-installed; this script is mostly for refreshing or adding the LLM GGUF)%s\n\n' "$GREY" "$RESET"

printf 'vision:\n'
# Try several mirrors in order. The HF repos sometimes return 401 for
# missing files or move paths, so a single URL is fragile.
VISION_URLS=(
    'https://huggingface.co/ragavsachdeva/yolov8n-onnx/resolve/main/yolov8n.onnx'
    'https://huggingface.co/pbcquoc/yolov8n/resolve/main/yolov8n.onnx'
    'https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx'
)
VISION_OK=0
for url in "${VISION_URLS[@]}"; do
    if fetch_and_manifest "$url" 'yolov8n.onnx' \
            'Compact YOLOv8n object detector (ONNX)' 'onnx' 'AGPL-3.0'; then
        VISION_OK=1
        break
    fi
    printf '  !!  mirror failed; trying next...\n' >&2
done
if (( VISION_OK == 0 )); then
    printf '%s  !!  all vision mirrors failed. Fallback: generate from PyTorch:\n' "$YELLOW"
    printf '      python3 -m pip install ultralytics\n'
    printf '      python3 scripts/export_yolo_onnx.py %s%s\n' "$MODELS_DIR" "$RESET"
    FAILURES=$((FAILURES + 1))
fi

printf '\naudio (voice activity detection):\n'
fetch_and_manifest \
    'https://github.com/snakers4/silero-vad/raw/v5.1/src/silero_vad/data/silero_vad.onnx' \
    'silero_vad.onnx' 'Silero voice activity detection' 'onnx' 'MIT'

printf '\nreasoning (small instruct LLM):\n'
# SmolLM2-360M (~230 MB) is the smallest usable chat model and fits
# Pi 4 comfortably. It is enough for canned Q&A but is NOT recommended
# for agent chat with tool calling (use Qwen2.5-1.5B-Instruct for that;
# downloaded by scripts/download-reasoning-llm.sh).
fetch_and_manifest \
    'https://huggingface.co/unsloth/SmolLM2-360M-Instruct-GGUF/resolve/main/SmolLM2-360M-Instruct-Q4_K_M.gguf' \
    'smollm2-360m-instruct-q4_k_m.gguf' 'SmolLM2 360M instruct model, Q4_K_M' 'llama-cpp' 'Apache-2.0'

printf '\ntimeseries / memory (optional local sklearn baselines):\n'
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sklearn, joblib, numpy' >/dev/null 2>&1; then
    if ! python3 - <<'PY'
import joblib, numpy as np, os
from sklearn.ensemble import IsolationForest
out = os.environ['ARIKIZU_MODELS_DIR']
rng = np.random.default_rng(0)
signal = np.sin(np.linspace(0, 10*np.pi, 1000)).reshape(-1, 1) + rng.normal(0, 0.05, (1000, 1))
model = IsolationForest(contamination=0.01, random_state=0).fit(signal)
joblib.dump(model, os.path.join(out, 'anomaly_iforest.joblib'))
joblib.dump({'arms': 3, 'alpha': [1.0, 1.0, 1.0], 'beta': [1.0, 1.0, 1.0]}, os.path.join(out, 'reward_bandit.joblib'))
print('  OK  anomaly_iforest.joblib')
print('  OK  reward_bandit.joblib')
PY
    then
        printf '%s  !!  failed to generate sklearn baselines%s\n' "$YELLOW" "$RESET" >&2
        FAILURES=$((FAILURES + 1))
    fi
else
    printf '%s  --  Python dependencies unavailable; skipping optional joblib baselines%s\n' "$YELLOW" "$RESET"
    printf '      Install with: python3 -m pip install numpy scikit-learn joblib\n'
fi

if [[ "$TIER" == standard || "$TIER" == full ]]; then
    printf '\naudio (standard):\n'
    fetch_and_manifest \
        'https://huggingface.co/onnx-community/whisper-tiny.en-ONNX/resolve/main/onnx/encoder_model.onnx' \
        'whisper-tiny.en-encoder.onnx' 'Whisper tiny.en encoder component (not a complete ASR model by itself)' 'onnx' 'MIT'

    printf '\nembeddings:\n'
    fetch_and_manifest \
        'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx' \
        'all-MiniLM-L6-v2.onnx' 'MiniLM-L6-v2 sentence embedding model' 'onnx' 'Apache-2.0'
    fetch_and_manifest \
        'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json' \
        'all-MiniLM-L6-v2.tokenizer.json' 'MiniLM-L6-v2 tokenizer' 'tokenizer' 'Apache-2.0'

    printf '\nreasoning (larger instruct LLM):\n'
    fetch_and_manifest \
        'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf' \
        'qwen2.5-0.5b-instruct-q4_k_m.gguf' 'Qwen2.5 0.5B instruct model, Q4_K_M' 'llama-cpp' 'Apache-2.0'
fi

if [[ "$TIER" == full ]]; then
    printf '\ndocument table detection (full):\n'
    fetch_and_manifest \
        'https://huggingface.co/microsoft/table-transformer-detection/resolve/main/onnx/model.onnx' \
        'table-transformer.onnx' 'Table Transformer detection model' 'onnx' 'MIT'

    printf '\nvision (full):\n'
    fetch_and_manifest \
        'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.onnx' \
        'yolov8s.onnx' 'YOLOv8s object detector (ONNX)' 'onnx' 'AGPL-3.0'

    printf '\naudio (full):\n'
    fetch_and_manifest \
        'https://huggingface.co/onnx-community/whisper-small.en-ONNX/resolve/main/onnx/encoder_model.onnx' \
        'whisper-small.en-encoder.onnx' 'Whisper small.en encoder component (not a complete ASR model by itself)' 'onnx' 'MIT'
fi

printf '\nmodels dir: %s\n' "$MODELS_DIR"
if command -v du >/dev/null 2>&1; then printf 'total size: %s\n' "$(du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}')"; fi
printf '\nFiles:\n'
find "$MODELS_DIR" -maxdepth 1 -type f ! -name '*.tmp.*' -printf '  %f\t%k KB\n' 2>/dev/null | sort || ls -lh "$MODELS_DIR"
printf '\nEnvironment:\n'
printf '  export ARIKIZU_MODELS_DIR=%q\n' "$MODELS_DIR"
printf '  export ARIKIZU_VISION_MODEL=%q\n' "$MODELS_DIR/yolov8n.onnx"
printf '  export ARIKIZU_REASONING_GGUF=%q\n' "$MODELS_DIR/smollm2-360m-instruct-q4_k_m.gguf"
if [[ "$TIER" != minimum ]]; then printf '  export ARIKIZU_EMBEDDER_MODEL=%q\n' "$MODELS_DIR/all-MiniLM-L6-v2.onnx"; fi
printf '\nFor arikizu.yaml, these go under each worker'"'"'s env: block.\n'
printf 'After editing arikizu.yaml, restart with: pkill -f "arikizu run"; make run\n'
printf '\nSee docs/MODEL_CATALOG.md for worker requirements and upgrade paths.\n'
if ((FAILURES > 0)); then
    printf '%sCompleted with %d download/generation failure(s). Review messages above.%s\n' "$YELLOW" "$FAILURES" "$RESET" >&2
    exit 1
fi

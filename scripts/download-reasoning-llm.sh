#!/usr/bin/env bash
# Download a properly-sized text LLM for agent chat with tool calling.
#
# SmolLM2-360M (what scripts/download-default-models.sh fetches) is too
# small to follow a system prompt reliably or emit structured tool-call
# blocks. For Agent Studio to work well, you want at least 1.5B
# parameters.
#
# Default: Qwen2.5-1.5B-Instruct Q4_K_M (~1.0 GB on disk, ~2 GB RAM in
# use). Edge-friendly: runs on Pi 5, Jetson Orin Nano, Mac, any x86 CPU.
#
# Options:
#   --size 0.5b | 1.5b | 3b | 7b     pick a model size (default 1.5b)
#   --models-dir DIR                 override $ARIKIZU_MODELS_DIR
set -Eeuo pipefail

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
SIZE="1.5b"

while (($#)); do
    case "$1" in
        --size) SIZE="$2"; shift 2 ;;
        --models-dir) MODELS_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^set -Eeuo/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$MODELS_DIR"
MODELS_DIR="$(cd "$MODELS_DIR" && pwd)"
GREEN=$'\033[32m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; RESET=$'\033[0m'

declare -A URLS=(
    [0.5b]="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    [1.5b]="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    [3b]="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
    [7b]="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
)

declare -A SIZES=(
    [0.5b]="~400 MB" [1.5b]="~1.0 GB" [3b]="~2.0 GB" [7b]="~4.4 GB"
)

if [[ -z "${URLS[$SIZE]:-}" ]]; then
    echo "unknown size: $SIZE (use 0.5b, 1.5b, 3b, or 7b)" >&2
    exit 2
fi

URL="${URLS[$SIZE]}"
FILE="qwen2.5-${SIZE}-instruct-q4_k_m.gguf"
DEST="$MODELS_DIR/$FILE"

if [[ -f "$DEST" && -s "$DEST" ]]; then
    printf '%s  --  %s already present%s\n' "$YELLOW" "$FILE" "$RESET"
    exit 0
fi

printf '%s  ..  downloading %s (%s)...%s\n' "$GREY" "$FILE" "${SIZES[$SIZE]}" "$RESET"
TMP="$DEST.part"
if curl --fail --location --show-error --retry 3 --retry-delay 2 \
        --connect-timeout 20 --output "$TMP" "$URL"; then
    mv -f "$TMP" "$DEST"
    size="$(du -h "$DEST" | awk '{print $1}')"
    printf '%s  OK  %s (%s)%s\n\n' "$GREEN" "$FILE" "$size" "$RESET"
    printf 'The reasoning worker will auto-detect and use this model on next restart.\n'
    printf 'Restart Arikizu: pkill -f arikizu && make run\n'
else
    rm -f "$TMP"
    printf '%s  !!  download failed%s\n' "$YELLOW" "$RESET" >&2
    exit 1
fi

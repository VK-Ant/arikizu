#!/usr/bin/env bash
# Download a properly-sized text LLM for agent chat with tool calling.
#
# SmolLM2-360M (what scripts/download-default-models.sh fetches) is too
# small to follow a system prompt reliably or emit structured tool-call
# blocks. For Agent Studio to work well, you want at least 1.5B
# parameters.
#
# Default: Qwen2.5-1.5B-Instruct Q4_K_M (~0.9 GB on disk, ~2 GB RAM in
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

# Primary mirrors: bartowski's quantizations are the most reliable and
# well-maintained community source. Qwen's own GGUFs are the fallback.
declare -A PRIMARY_URLS=(
    [0.5b]="https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
    [1.5b]="https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
    [3b]="https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
    [7b]="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
)
declare -A FALLBACK_URLS=(
    [0.5b]="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    [1.5b]="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    [3b]="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
    [7b]="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
)
declare -A SIZES=(
    [0.5b]="~400 MB" [1.5b]="~0.9 GB" [3b]="~2.0 GB" [7b]="~4.4 GB"
)

if [[ -z "${PRIMARY_URLS[$SIZE]:-}" ]]; then
    echo "unknown size: $SIZE (use 0.5b, 1.5b, 3b, or 7b)" >&2
    exit 2
fi

# Normalize output filename to lowercase so reasoning_worker's
# alphabetical sort picks the biggest.
FILE="qwen2.5-${SIZE}-instruct-q4_k_m.gguf"
DEST="$MODELS_DIR/$FILE"

if [[ -f "$DEST" && -s "$DEST" ]]; then
    SIZE_ON_DISK="$(du -h "$DEST" | awk '{print $1}')"
    printf '%s  --  %s already present (%s)%s\n' "$YELLOW" "$FILE" "$SIZE_ON_DISK" "$RESET"
    exit 0
fi

try_download() {
    local url="$1" label="$2"
    local tmp="$DEST.part"
    printf '%s  ..  trying %s mirror (%s)...%s\n' "$GREY" "$label" "${SIZES[$SIZE]}" "$RESET"
    rm -f "$tmp"
    if curl --fail --location --show-error --retry 3 --retry-delay 2 \
            --connect-timeout 20 --output "$tmp" "$url"; then
        if [[ -s "$tmp" ]] && [[ "$(stat -c%s "$tmp" 2>/dev/null || stat -f%z "$tmp")" -gt 100000000 ]]; then
            mv -f "$tmp" "$DEST"
            return 0
        else
            printf '%s  !!  file too small, likely an error page; retrying next mirror%s\n' "$YELLOW" "$RESET" >&2
            rm -f "$tmp"
            return 1
        fi
    fi
    rm -f "$tmp"
    return 1
}

if try_download "${PRIMARY_URLS[$SIZE]}" "bartowski"; then
    :
elif try_download "${FALLBACK_URLS[$SIZE]}" "Qwen official"; then
    :
else
    printf '%s  !!  all mirrors failed. Manual download:%s\n' "$YELLOW" "$RESET" >&2
    printf '    1. Open: %s\n' "${PRIMARY_URLS[$SIZE]}" >&2
    printf '    2. Click "download" on that file.\n' >&2
    printf '    3. Save to: %s\n' "$DEST" >&2
    exit 1
fi

size_on_disk="$(du -h "$DEST" | awk '{print $1}')"
printf '\n%s  OK  %s (%s)%s\n' "$GREEN" "$FILE" "$size_on_disk" "$RESET"
printf '\nReasoning worker will auto-detect this on next restart.\n'
printf 'Restart: pkill -9 -f arikizu && make run\n'

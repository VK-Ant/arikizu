#!/usr/bin/env bash
# Download every model file Arikizu needs, in one go.
#
# Runs in this order so later steps can fail without hiding earlier
# successes:
#   1. Default stack: YOLOv8 (vision) + Silero VAD (audio) + SmolLM2 (reasoning fallback)
#   2. Video Studio: MediaPipe tflite + SegFormer int8
#   3. Reasoning LLM: Qwen2.5-1.5B-Instruct (replaces SmolLM2 as the agent brain)
#   4. VLM (optional): Qwen2.5-VL-3B for open-vocabulary action search
#
# Options:
#   --with-vlm          include the ~2.7 GB VLM download (step 4)
#   --llm-size SIZE     reasoning LLM size: 0.5b | 1.5b | 3b | 7b (default 1.5b)
#   --skip-defaults     skip step 1 (if YOLO + VAD + SmolLM2 already present)
#   --skip-video        skip step 2
#   --skip-llm          skip step 3
#   --models-dir DIR    override $ARIKIZU_MODELS_DIR
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$(dirname "$HERE")"   # cd to project root

WITH_VLM=0
LLM_SIZE="1.5b"
SKIP_DEFAULTS=0
SKIP_VIDEO=0
SKIP_LLM=0
MODELS_DIR_ARG=""

while (($#)); do
    case "$1" in
        --with-vlm) WITH_VLM=1; shift ;;
        --llm-size) LLM_SIZE="$2"; shift 2 ;;
        --skip-defaults) SKIP_DEFAULTS=1; shift ;;
        --skip-video) SKIP_VIDEO=1; shift ;;
        --skip-llm) SKIP_LLM=1; shift ;;
        --models-dir) MODELS_DIR_ARG="--models-dir $2"; shift 2 ;;
        -h|--help) sed -n '2,/^set -Eeuo/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; GREY=$'\033[90m'; RESET=$'\033[0m'
FAILED_STEPS=()

step() {
    local n="$1" title="$2"
    printf '\n%s=== step %s: %s ===%s\n' "$BOLD" "$n" "$title" "$RESET"
}

run_or_record() {
    local label="$1"; shift
    if "$@"; then
        printf '%s  OK  %s%s\n' "$GREEN" "$label" "$RESET"
    else
        printf '%s  !!  %s failed%s\n' "$RED" "$label" "$RESET"
        FAILED_STEPS+=("$label")
    fi
}

if (( SKIP_DEFAULTS == 0 )); then
    step 1 "default stack (YOLO + Silero VAD + SmolLM2)"
    run_or_record "default models" bash scripts/download-default-models.sh $MODELS_DIR_ARG
else
    printf '%sskipping step 1 (--skip-defaults)%s\n' "$GREY" "$RESET"
fi

if (( SKIP_VIDEO == 0 )); then
    step 2 "Video Studio perception stack (MediaPipe + SegFormer, ~22 MB)"
    if (( WITH_VLM == 1 )); then
        run_or_record "video models + VLM" bash scripts/download-video-models.sh --with-vlm $MODELS_DIR_ARG
    else
        run_or_record "video models (perception only)" bash scripts/download-video-models.sh $MODELS_DIR_ARG
    fi
else
    printf '%sskipping step 2 (--skip-video)%s\n' "$GREY" "$RESET"
fi

if (( SKIP_LLM == 0 )); then
    step 3 "reasoning LLM (Qwen2.5-${LLM_SIZE}-Instruct, replaces SmolLM2 for agents)"
    run_or_record "qwen2.5-${LLM_SIZE}" bash scripts/download-reasoning-llm.sh --size "$LLM_SIZE" $MODELS_DIR_ARG
else
    printf '%sskipping step 3 (--skip-llm)%s\n' "$GREY" "$RESET"
fi

# Summary
printf '\n%s=== summary ===%s\n' "$BOLD" "$RESET"
MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
MODELS_DIR="$(cd "$MODELS_DIR" 2>/dev/null && pwd || echo "$MODELS_DIR")"
printf 'models directory: %s\n' "$MODELS_DIR"
printf 'total on disk:    '
du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}'
printf '\n'

if ((${#FAILED_STEPS[@]} == 0)); then
    printf '%sall downloads succeeded.%s\n' "$GREEN" "$RESET"
    printf '\nNext: pkill -9 -f arikizu && make run\n'
    printf 'Verify: curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/selftest \\\n'
    printf '          -H "content-type: application/json" -d "{\\"payload\\":{}}" | python3 -m json.tool\n'
    exit 0
else
    printf '%s%d step(s) failed:%s\n' "$YELLOW" "${#FAILED_STEPS[@]}" "$RESET"
    for s in "${FAILED_STEPS[@]}"; do
        printf '  - %s\n' "$s"
    done
    printf '\nRetry just the failed step by running its script directly.\n'
    exit 1
fi

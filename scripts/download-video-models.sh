#!/usr/bin/env bash
# Download video-worker models (MediaPipe LiteRT + SegFormer ONNX + optional VLM).
# Device-aware: skips large VLM files on Pi 4 by default.
#
# Usage:
#   scripts/download-video-models.sh              # perception + scene (no VLM)
#   scripts/download-video-models.sh --with-vlm   # also fetch Qwen2.5-VL 3B
#   scripts/download-video-models.sh --vlm-only   # only VLM files
set -Eeuo pipefail

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"
WITH_VLM=0
VLM_ONLY=0

while (($#)); do
    case "$1" in
        --with-vlm) WITH_VLM=1; shift ;;
        --vlm-only) VLM_ONLY=1; WITH_VLM=1; shift ;;
        --models-dir) MODELS_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^set -Eeuo pipefail/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$MODELS_DIR"
MODELS_DIR="$(cd "$MODELS_DIR" && pwd)"
GREEN=$'\033[32m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; RESET=$'\033[0m'
FAILURES=0

fetch() {
    local url="$1" out="$2" dest="$MODELS_DIR/$2"
    if [[ -f "$dest" && -s "$dest" ]]; then
        printf '%s  --  %s already present%s\n' "$YELLOW" "$out" "$RESET"
        return 0
    fi
    printf '%s  ..  downloading %s%s\n' "$GREY" "$out" "$RESET"
    local tmp="$dest.part"
    if curl --fail --location --show-error --retry 3 --retry-delay 2 \
            --connect-timeout 20 --output "$tmp" "$url"; then
        mv -f "$tmp" "$dest"
        local size="$(du -h "$dest" | awk '{print $1}')"
        printf '%s  OK  %s (%s)%s\n' "$GREEN" "$out" "$size" "$RESET"
    else
        rm -f "$tmp"
        FAILURES=$((FAILURES + 1))
        printf '%s  !!  %s FAILED%s\n' "$YELLOW" "$out" "$RESET" >&2
        return 1
    fi
}

MP_BASE="https://storage.googleapis.com/mediapipe-models"

if (( VLM_ONLY == 0 )); then
    printf 'perception (MediaPipe LiteRT):\n'
    fetch "$MP_BASE/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite" \
          "efficientdet_lite0.tflite" || true
    fetch "$MP_BASE/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task" \
          "pose_landmarker_lite.task" || true
    fetch "$MP_BASE/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite" \
          "blaze_face_short_range.tflite" || true
    fetch "$MP_BASE/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite" \
          "selfie_segmenter.tflite" || true
    fetch "$MP_BASE/interactive_segmenter/magic_touch/float32/1/magic_touch.tflite" \
          "magic_touch.tflite" || true

    printf '\nscene parsing (SegFormer int8):\n'
    fetch "https://huggingface.co/Xenova/segformer-b0-finetuned-ade-512-512/resolve/main/onnx/model_quantized.onnx" \
          "segformer_b0_ade20k_512_int8.onnx" || true
fi

if (( WITH_VLM == 1 )); then
    printf '\nmultimodal VLM (Qwen2.5-VL 3B Q4_K_M, ~2 GB + mmproj ~700 MB):\n'
    fetch "https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
          "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" || true
    fetch "https://huggingface.co/bartowski/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf" \
          "Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf" || true
fi

printf '\nmodels dir: %s\n' "$MODELS_DIR"
printf 'total size: '
du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}'
if (( FAILURES > 0 )); then
    printf '%s%d download(s) failed. Review messages above.%s\n' "$YELLOW" "$FAILURES" "$RESET" >&2
    exit 1
fi

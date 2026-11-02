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
    printf '\nmultimodal VLM (OPTIONAL, for reference-image action search):\n'
    # Save the FAILURES counter: VLM mirror retries use fetch() which
    # increments it, but those are not real failures (the next mirror
    # may succeed). We restore the counter after the VLM block.
    FAILURES_BEFORE_VLM=$FAILURES
    VLM_OK=0

    # Lightweight VLM-only fetch (does NOT touch FAILURES counter).
    try_vlm_pair() {
        local model_url="$1" model_file="$2" mmproj_url="$3" mmproj_file="$4" label="$5"
        printf '  .. trying %s mirror...\n' "$label"
        local m="$MODELS_DIR/$model_file" p="$MODELS_DIR/$mmproj_file"
        if curl --fail --location --silent --show-error --retry 2 --connect-timeout 15 \
                --output "$m.part" "$model_url" 2>/dev/null \
           && curl --fail --location --silent --show-error --retry 2 --connect-timeout 15 \
                --output "$p.part" "$mmproj_url" 2>/dev/null; then
            mv -f "$m.part" "$m"
            mv -f "$p.part" "$p"
            printf '%s  OK  VLM pair downloaded from %s%s\n' "$GREEN" "$label" "$RESET"
            VLM_OK=1
            return 0
        fi
        rm -f "$m.part" "$p.part" 2>/dev/null || true
        printf '%s  --  %s mirror failed, trying next%s\n' "$YELLOW" "$label" "$RESET" >&2
        return 1
    }

    # Mirror 1: second-state (prolific GGUF publisher)
    try_vlm_pair \
      "https://huggingface.co/second-state/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
      "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
      "https://huggingface.co/second-state/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-vision-encoder.gguf" \
      "Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf" \
      "second-state" || true

    # Mirror 2: ggml-org official VLM collection
    if (( VLM_OK == 0 )); then
        try_vlm_pair \
          "https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
          "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
          "https://huggingface.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf" \
          "Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf" \
          "ggml-org" || true
    fi

    # Mirror 3: lmstudio-community (sometimes mirrors Qwen VL)
    if (( VLM_OK == 0 )); then
        try_vlm_pair \
          "https://huggingface.co/lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
          "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf" \
          "https://huggingface.co/lmstudio-community/Qwen2.5-VL-3B-Instruct-GGUF/resolve/main/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf" \
          "Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf" \
          "lmstudio-community" || true
    fi

    # Restore FAILURES counter (VLM is optional, retry failures are not real failures).
    FAILURES=$FAILURES_BEFORE_VLM

    if (( VLM_OK == 0 )); then
        printf '\n%s  !!  All VLM mirrors failed (common when a repo is gated or renamed).%s\n' "$YELLOW" "$RESET" >&2
        printf '%s      This is OPTIONAL. Everything else still works:%s\n' "$YELLOW" "$RESET"
        printf '      - Vision detection: YES\n'
        printf '      - Pose + 12 rule-based actions: YES\n'
        printf '      - Scene parsing: YES\n'
        printf '      - Agent Studio chat: YES\n'
        printf '      - Multimodal action search by TEXT prompt: YES (via local reasoning worker)\n'
        printf '      - Multimodal action search by REFERENCE IMAGE: NO (needs VLM)\n\n'
        printf '      To get the VLM manually:\n'
        printf '        1. Open a browser to huggingface.co and search "Qwen2.5-VL-3B-Instruct GGUF"\n'
        printf '        2. Download a Q4_K_M .gguf file AND its vision mmproj .gguf file\n'
        printf '        3. Place both in %s/\n' "$MODELS_DIR"
        printf '        4. Rename them to:\n'
        printf '           - Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf\n'
        printf '           - Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf\n'
        printf '        5. Restart Arikizu.\n'
        # Return 0 on purpose: the VLM is optional, do not fail the whole install.
    fi
fi

printf '\nmodels dir: %s\n' "$MODELS_DIR"
printf 'total size: '
du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}'
if (( FAILURES > 0 )); then
    printf '%s%d download(s) failed. Review messages above.%s\n' "$YELLOW" "$FAILURES" "$RESET" >&2
    exit 1
fi

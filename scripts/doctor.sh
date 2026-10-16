#!/usr/bin/env bash
# Doctor: one-shot diagnostic. Tells you exactly which model / dep is missing.
#
# Usage:
#   scripts/doctor.sh
#   scripts/doctor.sh --models-dir /var/lib/arikizu/models
#
# Exit code is the number of failures, so CI can use it.

set -u

MODELS_DIR="${ARIKIZU_MODELS_DIR:-./models}"

while (($#)); do
    case "$1" in
        --models-dir) MODELS_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^set -u/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'; exit 0 ;;
        *) echo "unknown arg: $1"; exit 2 ;;
    esac
done

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
FAIL=0
PASS_COUNT=0

ok()   { printf '  %sPASS%s  %s\n'   "$GREEN"  "$RESET" "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '  %sFAIL%s  %s\n'   "$RED"    "$RESET" "$1"; printf '        %s%s%s\n' "$GREY" "$2" "$RESET"; FAIL=$((FAIL+1)); }
warn() { printf '  %sWARN%s  %s\n'   "$YELLOW" "$RESET" "$1"; printf '        %s%s%s\n' "$GREY" "$2" "$RESET"; }

printf '%sArikizu doctor%s\n' "$BOLD" "$RESET"
printf '%smodels dir:%s %s\n\n' "$GREY" "$RESET" "$MODELS_DIR"

printf '%ssystem tools%s\n' "$BOLD" "$RESET"
for bin in python3 curl; do
    if command -v "$bin" >/dev/null 2>&1; then
        ok "$bin: $(command -v "$bin")"
    else
        fail "$bin missing" "install $bin"
    fi
done

# Python version (<3.14 for llama-cpp-python wheels)
if command -v python3 >/dev/null 2>&1; then
    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
    if [[ "$PY_MAJOR" == "3" && "$PY_MINOR" -ge 11 && "$PY_MINOR" -le 13 ]]; then
        ok "python version: $PY_VER (supported)"
    elif [[ "$PY_MAJOR" == "3" && "$PY_MINOR" -eq 14 ]]; then
        warn "python version: $PY_VER" "llama-cpp-python has no 3.14 wheels; pin to 3.12 or 3.13"
    else
        fail "python version: $PY_VER" "need 3.11, 3.12, or 3.13"
    fi
fi

printf '\n%spython packages%s\n' "$BOLD" "$RESET"
PY_CHECK() {
    local pkg="$1" import_name="${2:-$1}" needed_for="$3"
    if python3 -c "import $import_name" 2>/dev/null; then
        local ver
        ver="$(python3 -c "import $import_name as m; print(getattr(m, '__version__', '?'))" 2>/dev/null)"
        ok "$pkg ($ver) - $needed_for"
    else
        fail "$pkg missing" "$needed_for ; install:  python3 -m pip install $pkg"
    fi
}
if command -v python3 >/dev/null 2>&1; then
    PY_CHECK "onnxruntime"       "onnxruntime"       "vision + VAD inference"
    PY_CHECK "numpy"             "numpy"             "arrays for inference"
    PY_CHECK "pillow"            "PIL"               "image decode"
    PY_CHECK "llama-cpp-python"  "llama_cpp"         "local LLM (reasoning)"
    PY_CHECK "msgpack"           "msgpack"           "worker IPC"
fi

printf '\n%smodels%s  %s(%s)%s\n' "$BOLD" "$RESET" "$GREY" "$MODELS_DIR" "$RESET"
check_model() {
    local file="$1" min_mb="$2" purpose="$3" fix="$4"
    local full="$MODELS_DIR/$file"
    if [[ ! -f "$full" ]]; then
        fail "$file missing" "$purpose ; fix: $fix"
        return
    fi
    local size_bytes
    if stat -c%s "$full" >/dev/null 2>&1; then size_bytes="$(stat -c%s "$full")";
    else size_bytes="$(stat -f%z "$full")"; fi
    local size_mb=$((size_bytes / 1024 / 1024))
    if (( size_mb < min_mb )); then
        fail "$file truncated (${size_mb}MB, need >=${min_mb}MB)" "download aborted ; fix: $fix"
    else
        ok "$file (${size_mb}MB) - $purpose"
    fi
}

check_model "yolov8n.onnx"                       10 "vision detect/segment"   "scripts/download-default-models.sh    OR    pip install ultralytics && python3 scripts/export_yolo_onnx.py"
check_model "silero_vad.onnx"                     1 "audio voice detection"   "scripts/download-default-models.sh"
check_model "smollm2-360m-instruct-q4_k_m.gguf" 200 "reasoning (local LLM)"   "scripts/download-default-models.sh"

printf '\n%sbuild artifact%s\n' "$BOLD" "$RESET"
if [[ -x target/release/arikizu ]]; then
    ok "target/release/arikizu present"
elif [[ -x target/debug/arikizu ]]; then
    warn "only debug build present" "run: make build  (release is 10x faster)"
else
    fail "arikizu binary missing" "run: make build"
fi

printf '\n%ssupervisor http%s\n' "$BOLD" "$RESET"
# Default port; override via ARIKIZU_HTTP_PORT
PORT="${ARIKIZU_HTTP_PORT:-8787}"
if command -v curl >/dev/null 2>&1; then
    STATUS_JSON="$(curl -sS --connect-timeout 2 "http://127.0.0.1:${PORT}/api/v1/status" 2>&1)"
    if echo "$STATUS_JSON" | grep -q '"runtime"'; then
        workers="$(echo "$STATUS_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("workers",[])))' 2>/dev/null || echo "?")"
        ok "supervisor live on :$PORT ($workers worker(s) running)"
    else
        warn "supervisor not reachable on :$PORT" "start with: make run"
    fi
fi

printf '\n'
if (( FAIL == 0 )); then
    printf '%s%d checks passed, 0 failed%s\n' "$GREEN" "$PASS_COUNT" "$RESET"
    printf '%sYou should see live detections on the vision demo and KW hits on the audio demo.%s\n' "$GREY" "$RESET"
else
    printf '%s%d checks passed, %d failed%s\n' "$YELLOW" "$PASS_COUNT" "$FAIL" "$RESET"
    printf '%sFix the FAIL rows above. Most common fix:%s  scripts/download-default-models.sh\n' "$GREY" "$RESET"
fi

exit "$FAIL"

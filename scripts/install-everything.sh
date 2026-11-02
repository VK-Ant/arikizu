#!/usr/bin/env bash
# One-shot install: system libs + Python deps + models.
#
# Run this ONCE after unzipping Arikizu. It handles the three things that
# break for people on fresh WSL / Ubuntu:
#
#   1. System libraries MediaPipe needs (libgl1 and friends)
#   2. Python workspace deps (uv sync with MediaPipe required)
#   3. All model files (default + video + reasoning LLM)
#
# Each step is independent. If one fails, the others still run, and the
# summary at the end tells you what to retry.
#
# Options:
#   --no-sudo        skip step 1 (if you already installed libgl1 etc)
#   --no-models      skip step 3 (if models already downloaded)
#   --with-vlm       include the ~2.7 GB VLM in step 3
#   --llm-size SIZE  reasoning LLM size (default 1.5b)
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"

NO_SUDO=0
NO_MODELS=0
WITH_VLM=0
LLM_SIZE="1.5b"

while (($#)); do
    case "$1" in
        --no-sudo) NO_SUDO=1; shift ;;
        --no-models) NO_MODELS=1; shift ;;
        --with-vlm) WITH_VLM=1; shift ;;
        --llm-size) LLM_SIZE="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^set -Eeuo/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; GREY=$'\033[90m'; RESET=$'\033[0m'
FAILED=()

# Fail fast with a clear message if uv is missing. Without uv, nothing works.
if ! command -v uv >/dev/null 2>&1; then
    printf '%serror: uv is not installed.%s\n' "$RED" "$RESET" >&2
    printf 'Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
    printf 'Then re-run this script.\n' >&2
    exit 1
fi

# Flag Python 3.14 ambient as a known issue BEFORE sync, so users understand
# why we pin 3.12 in step 2. (uv's own managed Python is unaffected either way.)
AMBIENT_PY="$(python3 --version 2>/dev/null | awk '{print $2}' || echo 'none')"
if [[ "$AMBIENT_PY" == 3.14* ]] || [[ "$AMBIENT_PY" == 3.13* ]]; then
    printf '%snote: ambient Python is %s. MediaPipe has no wheels for 3.13 or 3.14.%s\n' \
        "$YELLOW" "$AMBIENT_PY" "$RESET"
    printf '%s      Step 2 will install uv-managed Python 3.12 and pin the workspace to it. No system changes.%s\n' \
        "$YELLOW" "$RESET"
    echo
fi

step() { printf '\n%s=== %s ===%s\n' "$BOLD" "$1" "$RESET"; }
ok()   { printf '%s  OK  %s%s\n' "$GREEN" "$1" "$RESET"; }
fail() { printf '%s  !!  %s%s\n' "$RED" "$1" "$RESET"; FAILED+=("$2"); }
note() { printf '%s      %s%s\n' "$GREY" "$1" "$RESET"; }

# ---------------------------------------------------------------------
# Step 1: system libs
# ---------------------------------------------------------------------
if (( NO_SUDO == 0 )); then
    step "step 1: system libraries (libgl1 et al.)"
    if bash scripts/install-video-system-deps.sh; then
        ok "system libs installed"
    else
        fail "system libs install failed" "scripts/install-video-system-deps.sh"
    fi
else
    note "skipping system libs (--no-sudo)"
fi

# ---------------------------------------------------------------------
# Step 2: Python workspace sync (installs MediaPipe automatically now
# that it is a required dep of video-worker)
# ---------------------------------------------------------------------
step "step 2: Python workers (uv sync)"
if ! command -v uv >/dev/null 2>&1; then
    fail "uv not installed" "install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
else
    pushd workers >/dev/null

    # CRITICAL: pin Python 3.12. MediaPipe has no Python 3.14 wheels, so a
    # fresh Ubuntu 25.10 / WSL that defaults to 3.14 will fail uv sync with
    # "no compatible version". uv manages its own Pythons, so install 3.12
    # on first use and pin this workspace to it. Idempotent on re-runs.
    if [[ ! -f .python-version ]] || [[ "$(cat .python-version 2>/dev/null)" != "3.12" ]]; then
        printf '  pinning workspace to Python 3.12 (MediaPipe does not yet have 3.14 wheels)...\n'
        uv python install 3.12 2>&1 | sed 's/^/    /'
        uv python pin 3.12 2>&1 | sed 's/^/    /'
        # Wipe the venv so uv rebuilds it with 3.12
        rm -rf .venv
    fi

    if uv sync; then
        ok "uv sync completed (Python $(uv run --package video-worker python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")' 2>/dev/null))"
        # Verify MediaPipe actually imports.
        if uv run --package video-worker python3 -c "import mediapipe; print('mediapipe', mediapipe.__version__)" 2>&1; then
            ok "MediaPipe import verified"
        else
            fail "MediaPipe installed but import crashes" \
                 "likely a system-lib issue. Rerun step 1 or install libgl1 manually."
        fi
    else
        fail "uv sync failed" "see error above; usually a Python version mismatch (video-worker needs 3.11 or 3.12)"
    fi
    popd >/dev/null
fi

# ---------------------------------------------------------------------
# Step 3: models
# ---------------------------------------------------------------------
if (( NO_MODELS == 0 )); then
    step "step 3: download models"
    DOWNLOAD_FLAGS=("--llm-size" "$LLM_SIZE")
    if (( WITH_VLM == 1 )); then DOWNLOAD_FLAGS+=("--with-vlm"); fi
    if bash scripts/download-all.sh "${DOWNLOAD_FLAGS[@]}"; then
        ok "all model downloads succeeded"
    else
        fail "some model downloads failed" "scripts/download-all.sh (see above)"
    fi
else
    note "skipping models (--no-models)"
fi

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
printf '\n%s=== summary ===%s\n' "$BOLD" "$RESET"
if ((${#FAILED[@]} == 0)); then
    printf '%sinstall completed cleanly.%s\n\n' "$GREEN" "$RESET"
    printf 'Next:\n'
    printf '  1. make build          # if not already built\n'
    printf '  2. pkill -9 -f arikizu && make run\n'
    printf '  3. Open http://127.0.0.1:7000/demo/\n'
    printf '  4. Verify:\n'
    printf '       curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/selftest \\\n'
    printf '         -H "content-type: application/json" -d "{\\"payload\\":{}}" | python3 -m json.tool\n'
    printf '     Every stage should show "ok": true.\n'
    exit 0
else
    printf '%s%d step(s) need attention:%s\n' "$YELLOW" "${#FAILED[@]}" "$RESET"
    for f in "${FAILED[@]}"; do
        printf '  - %s\n' "$f"
    done
    exit 1
fi

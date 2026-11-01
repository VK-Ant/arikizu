#!/usr/bin/env bash
# Install the system libraries MediaPipe + OpenCV need on Ubuntu / Debian / WSL.
#
# Fresh Ubuntu images (WSL, Pi, cloud VMs) don't have libgl1 and friends,
# so `import mediapipe` succeeds in isolation but perception init crashes
# with "libGL.so.1: cannot open shared object file" the moment it tries to
# process a frame.
#
# Usage:
#   sudo scripts/install-video-system-deps.sh
#   (or just: scripts/install-video-system-deps.sh  and it will sudo for you)
set -Eeuo pipefail

PACKAGES=(
    libgl1               # OpenGL runtime (MediaPipe inference)
    libglib2.0-0         # GLib runtime
    libsm6               # X session management (OpenCV)
    libxext6             # X extensions (OpenCV)
    libxrender1          # X rendering (OpenCV)
)

GREEN=$'\033[32m'; YELLOW=$'\033[33m'; GREY=$'\033[90m'; RESET=$'\033[0m'

# Detect package manager
if command -v apt-get >/dev/null 2>&1; then
    PM="apt"
elif command -v dnf >/dev/null 2>&1; then
    PM="dnf"
elif command -v pacman >/dev/null 2>&1; then
    PM="pacman"
else
    printf '%serror: no supported package manager found (need apt, dnf, or pacman)%s\n' \
        "$YELLOW" "$RESET" >&2
    printf 'Install these manually: %s\n' "${PACKAGES[*]}" >&2
    exit 1
fi

SUDO=""
if [[ "$EUID" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        printf '%serror: not root and sudo not available. Re-run as root.%s\n' \
            "$YELLOW" "$RESET" >&2
        exit 1
    fi
fi

printf '%sInstalling MediaPipe system dependencies via %s...%s\n' "$GREEN" "$PM" "$RESET"

case "$PM" in
    apt)
        $SUDO apt-get update
        $SUDO apt-get install -y "${PACKAGES[@]}"
        ;;
    dnf)
        $SUDO dnf install -y mesa-libGL glib2 libSM libXext libXrender
        ;;
    pacman)
        $SUDO pacman -S --noconfirm mesa glib2 libsm libxext libxrender
        ;;
esac

printf '\n%sdone.%s\n' "$GREEN" "$RESET"
printf '\nNow restart Arikizu to pick up the new libs:\n'
printf '  pkill -9 -f arikizu && make run\n'
printf '\nVerify with:\n'
printf '  curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/selftest \\\n'
printf '    -H "content-type: application/json" -d "{\\"payload\\":{}}" | python3 -m json.tool\n'
printf '\nEvery stage should now show "ok": true.\n'

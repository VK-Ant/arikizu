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

# Everything MediaPipe + OpenCV + ONNX + llama-cpp might need, installed
# upfront so you don't play whack-a-mole with libGL / libGLES / libEGL /
# libSM / libXrender errors one by one.
PACKAGES=(
    # OpenGL + GLES + EGL (MediaPipe tasks need all three on fresh WSL)
    libgl1
    libgles2
    libegl1
    libglvnd0

    # X11 subsystem (OpenCV requires these even in headless mode)
    libglib2.0-0
    libsm6
    libxext6
    libxrender1
    libxcb1
    libxkbcommon0

    # Parallelism + math (ONNX runtime, numpy, llama-cpp)
    libgomp1

    # Audio IO (PortAudio for the audio_worker; even without it the audio
    # file demos still work, so this one is nice-to-have not critical)
    libportaudio2

    # Video decoding (opencv-python-headless needs ffmpeg libs at runtime
    # for anything other than the simplest MP4s)
    ffmpeg
    libavcodec-extra
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
        # Install in one call. If apt refuses a package name (e.g.
        # libavcodec-extra isn't available on some minimal images), fall
        # back to installing them one at a time so the rest still land.
        if ! $SUDO apt-get install -y "${PACKAGES[@]}"; then
            printf '%sone-shot install failed; retrying each package individually%s\n' "$YELLOW" "$RESET"
            for p in "${PACKAGES[@]}"; do
                $SUDO apt-get install -y "$p" 2>/dev/null || \
                    printf '%s  skipped %s (not available on this distro)%s\n' "$YELLOW" "$p" "$RESET"
            done
        fi
        ;;
    dnf)
        $SUDO dnf install -y mesa-libGL mesa-libGLES mesa-libEGL \
            glib2 libSM libXext libXrender libxcb libxkbcommon \
            libgomp portaudio ffmpeg
        ;;
    pacman)
        $SUDO pacman -S --noconfirm --needed mesa glib2 libsm libxext \
            libxrender libxcb libxkbcommon portaudio ffmpeg
        ;;
esac

printf '\n%sdone.%s\n' "$GREEN" "$RESET"
printf '\nNow restart Arikizu to pick up the new libs:\n'
printf '  pkill -9 -f arikizu && make run\n'
printf '\nVerify with:\n'
printf '  curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/selftest \\\n'
printf '    -H "content-type: application/json" -d "{\\"payload\\":{}}" | python3 -m json.tool\n'
printf '\nEvery stage should now show "ok": true.\n'

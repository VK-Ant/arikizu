#!/usr/bin/env bash
# Build a flashable Arikizu Pi image using pi-gen.
#
# Prereqs on an Ubuntu/Debian x86_64 build host:
#   - docker (pi-gen runs its chroot steps in a docker container)
#   - the aarch64 binary built via scripts/build-aarch64.sh
#   - the worker wheels built via (planned) scripts/build-wheels.sh
#
# Outputs: dist/arikizu-pi-<version>.img.xz

set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:-$(git describe --tags --always --dirty 2>/dev/null || echo dev)}"
PI_GEN_DIR="${PI_GEN_DIR:-$HOME/.cache/arikizu/pi-gen}"
STAGE_SRC="packaging/pi-gen/stage-arikizu"
FILES="$STAGE_SRC/00-arikizu/files"

# ---- 1. Ensure pi-gen is cloned --------------------------------------------
if [ ! -d "$PI_GEN_DIR" ]; then
    echo "Cloning pi-gen into $PI_GEN_DIR..."
    git clone --depth 1 https://github.com/RPi-Distro/pi-gen "$PI_GEN_DIR"
fi

# ---- 2. Drop pre-built artifacts into the stage ----------------------------
if [ ! -f "target/aarch64-unknown-linux-gnu/release/arikizu" ]; then
    echo "aarch64 binary missing. Run scripts/build-aarch64.sh first."
    exit 1
fi
cp target/aarch64-unknown-linux-gnu/release/arikizu "$FILES/arikizu"

mkdir -p "$FILES/wheels"
if ls dist/wheels/*.whl >/dev/null 2>&1; then
    cp dist/wheels/*.whl "$FILES/wheels/"
else
    echo "WARNING: no wheels in dist/wheels; the image's first boot will fail to install workers offline."
fi

cp arikizu.yaml.example      "$FILES/arikizu.yaml.default"
cp capabilities.toml         "$FILES/capabilities.toml.default"
cp policies/no-outbound.yaml "$FILES/no-outbound.yaml"
cp packaging/systemd/arikizu.service "$FILES/arikizu.service"

# ---- 3. Copy the stage into pi-gen -----------------------------------------
rm -rf "$PI_GEN_DIR/stage-arikizu"
cp -r  "$STAGE_SRC" "$PI_GEN_DIR/stage-arikizu"

# ---- 4. pi-gen config ------------------------------------------------------
cat > "$PI_GEN_DIR/config" <<EOF
IMG_NAME=arikizu-pi-$VERSION
RELEASE=bookworm
TARGET_HOSTNAME=arikizu
DISABLE_FIRST_BOOT_USER_RENAME=1
STAGE_LIST="stage0 stage1 stage2 stage-arikizu"
LOCALE_DEFAULT=en_IN.UTF-8
TIMEZONE_DEFAULT=Asia/Kolkata
EOF

# ---- 5. Build --------------------------------------------------------------
pushd "$PI_GEN_DIR" >/dev/null
sudo CLEAN=1 ./build-docker.sh
popd >/dev/null

# ---- 6. Collect the output -------------------------------------------------
mkdir -p dist
IMG=$(ls "$PI_GEN_DIR/deploy/"*arikizu-pi-"$VERSION"*.zip 2>/dev/null | head -1)
if [ -z "$IMG" ]; then
    echo "pi-gen finished but no image found in $PI_GEN_DIR/deploy/"
    exit 1
fi
cp "$IMG" "dist/$(basename "$IMG")"
echo "Image: dist/$(basename "$IMG")"
echo "Flash with: sudo rpi-imager --cli dist/$(basename "$IMG") /dev/sdX"

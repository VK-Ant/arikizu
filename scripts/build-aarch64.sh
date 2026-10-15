#!/usr/bin/env bash
# Cross-compile arikizu for aarch64-unknown-linux-gnu.
# Produces target/aarch64-unknown-linux-gnu/release/arikizu — the binary
# that pi-gen and the .deb packaging consume.
#
# Prereqs on an Ubuntu/Debian x86_64 build host:
#   sudo apt install -y gcc-aarch64-linux-gnu
#   rustup target add aarch64-unknown-linux-gnu

set -euo pipefail
cd "$(dirname "$0")/.."

TARGET=aarch64-unknown-linux-gnu
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc
export CC_aarch64_unknown_linux_gnu=aarch64-linux-gnu-gcc
export CXX_aarch64_unknown_linux_gnu=aarch64-linux-gnu-g++

if ! rustup target list --installed | grep -q "$TARGET"; then
    echo "Adding $TARGET to rustup..."
    rustup target add "$TARGET"
fi

if ! command -v aarch64-linux-gnu-gcc >/dev/null; then
    echo "Missing aarch64-linux-gnu-gcc. Install with:"
    echo "    sudo apt install -y gcc-aarch64-linux-gnu"
    exit 1
fi

echo "Cross-compiling arikizu for $TARGET..."
cargo build --release --locked --target "$TARGET" --bin arikizu

OUT="target/$TARGET/release/arikizu"
if [ ! -f "$OUT" ]; then
    echo "Build succeeded but $OUT is missing"
    exit 1
fi

file "$OUT"
echo
echo "Binary: $OUT"
echo "Size:   $(du -h "$OUT" | awk '{print $1}')"
echo
echo "Next steps:"
echo "  packaging/pi-gen stage expects it at pi-gen/stage-arikizu/00-arikizu/files/arikizu"
echo "  packaging/debian expects it at packaging/debian/arikizu/usr/bin/arikizu"

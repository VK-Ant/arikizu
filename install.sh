#!/usr/bin/env sh
# Arikizu Tier 1 installer. Pulls the pre-built binary for this host.
#
# This is the DEVELOPER install. It does not install workers, does not create
# a service, and does not touch systemd. For a server/daemon install use the
# .deb package; for an OS install flash the .img.xz. See docs/DISTRIBUTION.md.
#
# Usage:
#   curl -fsSL https://arikizu.sh/install.sh | sh
#   curl -fsSL https://arikizu.sh/install.sh | sh -s -- --version v0.1.0
#
# Env:
#   ARIKIZU_HOME       install root (default: $HOME/.arikizu)
#   ARIKIZU_VERSION    override version (default: latest)
#   ARIKIZU_REPO       release source (default: VK-Ant/arikizu)
#
# Nothing in this script compiles anything. If you need to build from source,
# that is a developer flow — clone the repo and run `make build` instead.

set -eu

ARIKIZU_HOME="${ARIKIZU_HOME:-$HOME/.arikizu}"
ARIKIZU_REPO="${ARIKIZU_REPO:-VK-Ant/arikizu}"
VERSION="${ARIKIZU_VERSION:-latest}"

while [ $# -gt 0 ]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --home)    ARIKIZU_HOME="$2"; shift 2 ;;
        -h|--help)
            cat <<EOF
Arikizu Tier 1 (developer binary) installer.

Options:
  --version <tag>    install a specific release (default: latest)
  --home <path>      install into this directory (default: $HOME/.arikizu)
  -h, --help         this message

For a Raspberry Pi server install (Tier 2):
    see https://apt.arikizu.sh  (planned, Weekend 15)

For an "OS" install on a dedicated device (Tier 3):
    flash arikizu-pi-<version>.img.xz with Raspberry Pi Imager
    see docs/DISTRIBUTION.md
EOF
            exit 0
            ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux)  os_tag=linux ;;
    Darwin) os_tag=macos ;;
    *) echo "unsupported OS: $OS. Use the .img.xz for Raspberry Pi install." >&2; exit 1 ;;
esac

case "$ARCH" in
    x86_64|amd64)  arch_tag=x86_64 ;;
    aarch64|arm64) arch_tag=aarch64 ;;
    *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

target="${arch_tag}-${os_tag}"
echo "detected host: ${target}"

# On a Pi running Raspberry Pi OS, suggest the right path.
if [ "$OS" = "Linux" ] && [ -f /proc/device-tree/model ]; then
    if grep -qi raspberry /proc/device-tree/model 2>/dev/null; then
        echo
        echo "NOTE: You're on a Raspberry Pi. This Tier 1 installer puts arikizu in"
        echo "      ~/.arikizu/bin/, with no service and no workers installed. On a"
        echo "      Pi you probably want the .deb (Tier 2) or the flashable image"
        echo "      (Tier 3) instead. See docs/DISTRIBUTION.md."
        echo
    fi
fi

if [ "$VERSION" = "latest" ]; then
    VERSION="$(
        curl -fsSL "https://api.github.com/repos/${ARIKIZU_REPO}/releases/latest" \
          | grep -o '"tag_name": *"[^"]*"' | head -n1 \
          | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/'
    )"
    [ -z "$VERSION" ] && { echo "could not resolve latest version" >&2; exit 1; }
fi
echo "version: ${VERSION}"

asset="arikizu-${VERSION}-${target}.tar.gz"
url="https://github.com/${ARIKIZU_REPO}/releases/download/${VERSION}/${asset}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "downloading ${url}"
curl -fsSL "$url" -o "$tmpdir/$asset"

checksums_url="https://github.com/${ARIKIZU_REPO}/releases/download/${VERSION}/SHA256SUMS"
if curl -fsSL "$checksums_url" -o "$tmpdir/SHA256SUMS" 2>/dev/null; then
    cd "$tmpdir"
    expected="$(grep "$asset" SHA256SUMS | awk '{print $1}')"
    actual="$(sha256sum "$asset" | awk '{print $1}')"
    [ "$expected" = "$actual" ] || { echo "checksum mismatch for $asset" >&2; exit 1; }
    echo "checksum verified"
    cd - >/dev/null
else
    echo "warning: no SHA256SUMS published; skipping checksum verification"
fi

mkdir -p "$ARIKIZU_HOME/bin"
tar -xzf "$tmpdir/$asset" -C "$tmpdir"
install -m 0755 "$tmpdir/arikizu" "$ARIKIZU_HOME/bin/arikizu"

echo
echo "Installed arikizu ${VERSION} to ${ARIKIZU_HOME}/bin/arikizu"
echo

if ! echo ":$PATH:" | grep -q ":$ARIKIZU_HOME/bin:"; then
cat <<EOF
Add Arikizu to your PATH:

  export PATH="$ARIKIZU_HOME/bin:\$PATH"

Append the line to your shell rc file to make it permanent.

Then:  arikizu init my-project
EOF
fi

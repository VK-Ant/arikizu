#!/usr/bin/env bash
# Launch the Arikizu dev container with cwd mounted and target/ cache preserved.
#
# Usage:
#   scripts/docker-dev.sh                 # drop into a shell
#   scripts/docker-dev.sh make build      # run a single command
#   scripts/docker-dev.sh make run        # the HTTP server; dashboard at http://localhost:7000
#
# Why --net=host:  so the HTTP server inside the container is reachable from
#                  your host browser without port mapping.
# Why /tmp mount:  so the Unix sockets under /tmp/arikizu work.

set -eu
cd "$(dirname "$0")/.."

IMAGE="${ARIKIZU_DEV_IMAGE:-arikizu-dev}"

# Build only when the image is missing (fast on reruns).
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building $IMAGE..."
    docker build -f Dockerfile.dev -t "$IMAGE" .
fi

# Preserve the Rust target/ cache in a named volume so rebuilds are fast.
mkdir -p .cache
docker run --rm -it \
    --net=host \
    -v "$(pwd)":/work \
    -v arikizu-target:/work/target \
    -v arikizu-uv-cache:/root/.cache/uv \
    -w /work \
    "$IMAGE" \
    "$@"

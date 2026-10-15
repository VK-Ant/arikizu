#!/usr/bin/env bash
# One-shot bootstrap for a fresh clone of Arikizu.
#
#   git clone https://github.com/VK-Ant/arikizu
#   cd arikizu
#   scripts/bootstrap.sh
#
# After this exits 0, `make build && make run` works.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Arikizu bootstrap ==="
echo

# 1. Verify prerequisites.
scripts/check_prereqs.sh

# 2. Fetch Rust crates (no compile yet; faster to see failures separately).
echo
echo "=== fetching Rust crates ==="
cargo fetch

# 3. Sync Python workspace.
echo
echo "=== syncing Python workspace ==="
cd workers
uv sync
cd ..

# 4. Install UI deps.
echo
echo "=== installing UI deps ==="
cd ui
if [ -f pnpm-lock.yaml ]; then
  pnpm install --frozen-lockfile
else
  pnpm install
fi
cd ..

# 5. Build once to prime the target/ directory.
echo
echo "=== building (debug) ==="
cargo build --workspace

# 6. Smoke test.
echo
echo "=== smoke test ==="
./target/debug/arikizu --version || true
./target/debug/arikizu status --dev

echo
echo "=== bootstrap complete ==="
echo
echo "Next:"
echo "  make run           # start the runtime"
echo "  make test          # run every test tier"
echo "  make ui-dev        # SvelteKit dashboard with HMR"

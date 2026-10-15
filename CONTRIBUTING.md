# Contributing to Arikizu

Arikizu is a solo hobby project at v0.1. Contributions outside the owner are
not accepted yet; this file sets expectations for the owner's own work.

## Workflow

1. One branch per weekend. Name: `weekend-NN-short-topic`.
2. Each weekend ends with a tagged commit, `v0.0.NN` for N=1..19, `v0.1.0` for
   the final weekend.
3. `make lint && make test` must pass before every commit on `main`.
4. Commits are present-tense imperative:
   ```
   add device inventory

   detect Jetson via /etc/nv_tegra_release; detect NVIDIA GPUs via nvidia-smi;
   fall back to zero on parse failures.
   ```
5. Co-author attribution lives in the commit trailer.

## Style

- Rust: `cargo fmt`, `cargo clippy -- -D warnings`. No `unwrap()` outside tests.
- Python: ruff format and check. Type hints on every public function.
- Markdown: no trailing whitespace, lines may run long.

## What goes where

| Change kind                 | Target                   |
| --------------------------- | ------------------------ |
| New capability              | `capabilities.toml`      |
| New worker                  | `workers/<name>_worker/` |
| New HTTP route              | `crates/ant-http/`       |
| New CLI subcommand          | `crates/ant-cli/`        |
| Feedback or approval change | `crates/ant-feedback/`   |
| UI change                   | `ui/src/`                |
| Protocol change             | `crates/ant-ipc/`        |

A protocol change bumps `PROTOCOL_VERSION` in both `ant-ipc` and
`arikizu-worker-sdk`; old workers refuse the Hello and the supervisor logs it.

## Test gates

A commit is not finished until:

- `cargo fmt --all -- --check` passes
- `cargo clippy --workspace --all-targets -- -D warnings` passes
- `cargo test --workspace` passes
- `uv run pytest` passes under `workers/`
- `pnpm run check` passes under `ui/` (if the UI changed)

CI runs all of the above on push and pull request.

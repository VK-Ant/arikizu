# Module index

Where things live in the repo.

## Rust crates (`crates/`)

| Crate | Role | README |
| ---------------- | -------------------------------------------------------------- | -------------------------------------- |
| `ant-common` | Shared types + `arikizu.yaml` loader | [crates/ant-common/README.md](../crates/ant-common/README.md) |
| `ant-ipc` | Length-prefixed MessagePack over Unix sockets | [crates/ant-ipc/README.md](../crates/ant-ipc/README.md) |
| `ant-router` | Capability registry (loads `capabilities.toml`) | [crates/ant-router/README.md](../crates/ant-router/README.md) |
| `ant-supervisor` | Worker lifecycle, event bus, pipeline executor, policy | [crates/ant-supervisor/README.md](../crates/ant-supervisor/README.md) |
| `ant-models` | Model manifests, SHA-256 verify, backend selection | [crates/ant-models/README.md](../crates/ant-models/README.md) |
| `ant-devices` | CPU, GPU, memory, Jetson detection | [crates/ant-devices/README.md](../crates/ant-devices/README.md) |
| `ant-feedback` | Rate/correct/approve/reject/annotate + SQLite audit log | [crates/ant-feedback/README.md](../crates/ant-feedback/README.md) |
| `ant-http` | axum REST + WebSocket surface | [crates/ant-http/README.md](../crates/ant-http/README.md) |
| `ant-cli` | The `arikizu` binary (clap subcommands) | [crates/ant-cli/README.md](../crates/ant-cli/README.md) |

## Python workers (`workers/`)

| Worker | Capabilities | Backing library | README |
| ------------------------ | ------------------------------------------------- | ------------------------- | ----------------------------------------------- |
| `arikizu-worker-sdk` | shared IPC shim + backend module | n/a | [workers/arikizu-worker-sdk/README.md](../workers/arikizu-worker-sdk/README.md) |
| `test_worker` | `test.*` | n/a | [workers/test_worker/README.md](../workers/test_worker/README.md) |
| `vision_worker` | `vision.*` | SightRAG | [workers/vision_worker/README.md](../workers/vision_worker/README.md) |
| `audio_worker` | `audio.*` | Sonarwise | [workers/audio_worker/README.md](../workers/audio_worker/README.md) |
| `docs_worker` | `docs.*` | DocQWise | [workers/docs_worker/README.md](../workers/docs_worker/README.md) |
| `reasoning_worker` | `reasoning.*` | a local LLM runtime/OpenAI-compatible | [workers/reasoning_worker/README.md](../workers/reasoning_worker/README.md) |
| `timeseries_worker` | `timeseries.*` | WavqWise (classical ML libraries) | [workers/timeseries_worker/README.md](../workers/timeseries_worker/README.md) |
| `memory_worker` | `memory.*` | adaptive-intelligence | [workers/memory_worker/README.md](../workers/memory_worker/README.md) |
| `guard_worker` | `guard.*` | AntGuard | [workers/guard_worker/README.md](../workers/guard_worker/README.md) |
| `eval_worker` | `eval.*` | LLMEvalKit | [workers/eval_worker/README.md](../workers/eval_worker/README.md) |

## Repo-level files

| Path | Role |
| ---------------------------------- | ------------------------------------------------------------ |
| `README.md` | Pitch, install, verify, docs index |
| `QUICKSTART.md` | Install and run (Pi-first) |
| `CONTRIBUTING.md` | Branch, commit, PR convention |
| `SECURITY.md` | Threat model, dependency validation, reporting |
| `Cargo.toml` | Rust workspace manifest |
| `Makefile` | Top-level dev commands |
| `Dockerfile.dev` | Mac/Windows cross-OS dev container |
| `arikizu.yaml.example` | Reference pipeline config |
| `capabilities.toml` | Capability registry |
| `install.sh` | Tier 1 developer binary installer |
| `rust-toolchain.toml` | Pins Rust toolchain |

## docs/

| File | Role |
| --------------------------- | -------------------------------------------------------- |
| `WHY_OS.md` | The "is this really an OS?" argument |
| `HOW_IT_RUNS.md` | Stack diagram + boot sequence (on top of Raspberry Pi OS)|
| `DISTRIBUTION.md` | Three install tiers (dev binary, deb, flashable image) |
| `MODELS.md` | LLM strategy, runtime optimization, catalog, defaults |
| `MODULES.md` | This file |
| `SPEC.md` | Non-fit list, qualification checklist, verticals |
| `PI_VISION_TUTORIAL.md` | 1-hour hands-on project |
| `assets/hero.png` | README hero image |

## Config and automation

| Path | Role |
| --------------------------------------------------- | ---------------------------------------------------- |
| `policies/no-outbound.yaml` | Reference security policy |
| `packaging/systemd/arikizu.service` | systemd unit (Tier 2 + Tier 3) |
| `packaging/debian/` | `.deb` build (Tier 2) |
| `packaging/pi-gen/stage-arikizu/` | pi-gen stage for flashable image (Tier 3) |
| `scripts/check_prereqs.sh` | Verify toolchains before build |
| `scripts/bootstrap.sh` | First-run build + sync |
| `scripts/install-runtime.sh` | Detect GPU/accelerator, install matching runtime |
| `scripts/download-default-models.sh` | Fetch default models by tier |
| `scripts/docker-dev.sh` | Launch Mac/Windows dev container |
| `scripts/build-aarch64.sh` | Cross-compile Rust binary |
| `scripts/build-pi-image.sh` | Drive pi-gen; produces `.img.xz` |
| `.github/dependabot.yml` | Weekly dependency bumps |
| `.github/workflows/build.yml` | Rust + Python + integration + UI matrix |
| `.github/workflows/security.yml` | cargo-audit + pip-audit + CodeQL + gitleaks |
| `.github/workflows/release.yml` | Four-target binary release on tags |
| `.github/workflows/image.yml` | Pi flashable image on tags |
| `.github/CODEOWNERS` | Review requirements |
| `.github/ISSUE_TEMPLATE/` | Bug + feature templates |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR checklist |

## UI (`ui/`)

SvelteKit static site, served by `ant-http` at `/`. Routes:

- `/`: overview
- `/pipelines`: the arikizu.yaml with a Run button
- `/review`: pending approvals
- `/models`: runtime + model swap
- `/audit`: SQLite audit log tail
- `/events`: live WebSocket tail
- `/demo`: zero-dep sandbox for every capability

## Demos (`demo/`)

- `demo/README.md`: index
- `demo/smoke_test.py`: PASS/WAIT/FAIL for every capability
- `demo/perception/*.py`: per-worker demos
- `demo/pipelines/*.py`: full pipeline demos
- `demo/raspberrypi/`: camera + mic end-to-end tests on the Pi
- `demo/web/index.html`: zero-dep web sandbox served at `/demo`

# ant-common

Core types and the `arikizu.yaml` loader. Every other crate depends on this one, so it is kept dependency-light: serde, chrono, uuid, thiserror, tracing.

## What it exports

| Item               | Role                                                             |
| ------------------ | ---------------------------------------------------------------- |
| `CapabilityName`   | Fully qualified name like `vision.detect`; splits domain and op  |
| `Severity`         | Trace..Critical, serializes lowercase                             |
| `WorkerState`      | Created, Initializing, Ready, Serving, Draining, Stopped, ...   |
| `FeedbackLabel`    | Good, Bad, Neutral                                               |
| `ApprovalDecision` | Approved { by, note }, Rejected { by, reason }, Expired         |
| `ArikizuError`     | Workspace-wide error enum                                        |
| `Result<T>`        | `std::result::Result<T, ArikizuError>`                           |
| `Timestamp`        | Monotonic + wall-clock pair                                      |
| `config::*`        | `ArikizuConfig`, `WorkerSpec`, `StageConfig`, device types       |

## How it works

The config module is the YAML schema in Rust. Every `arikizu.yaml` passes through `ArikizuConfig::load(path)` and either produces a validated struct or an `ArikizuError::Serialization`. Defaults are chosen so a minimal file (`name: foo`) is enough to boot.

```rust
use ant_common::ArikizuConfig;
let cfg = ArikizuConfig::load("arikizu.yaml")?;
println!("pipeline name: {}", cfg.name);
println!("workers: {}", cfg.workers.len());
```

## Adding a new field

1. Add it to the right struct with `#[serde(default)]` or a `default_*` function so existing YAMLs keep parsing.
2. Add a test in `src/config.rs` showing it parses both when present and absent.
3. Update `arikizu.yaml.example` to document the field.

## Tests

```
cargo test -p ant-common
```

Covers: capability name splitting, severity JSON round-trip, YAML parse for minimal and full configs, missing-required-field rejection.

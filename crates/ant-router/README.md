# ant-router

Capability registry. Loads `capabilities.toml`, maps capability names (`vision.detect`) to workers, and reports the per-call timeout and priority used by the HTTP surface and the pipeline executor.

## Capability spec

Each `[name]` block in `capabilities.toml` becomes a `CapabilitySpec`:

```toml
[vision_detect]
name          = "vision.detect"
worker        = "vision"
input         = { image_path = "string" }
output        = "object"
timeout_ms    = 30000
emits_events  = ["vision.detected"]
priority      = 0
```

Fields:

| Field          | Default    | Meaning                                      |
| -------------- | ---------- | -------------------------------------------- |
| `worker`       | required   | which worker handles the call                |
| `input`        | `{}`       | advisory schema (shape only, no validation)   |
| `output`       | `""`       | advisory output shape                         |
| `timeout_ms`   | `5000`     | per-call deadline                             |
| `emits_events` | `[]`       | subjects this capability may publish          |
| `priority`     | `0`        | router preference under load                  |

## API

```rust
use ant_router::CapabilityRegistry;

let registry = CapabilityRegistry::load("capabilities.toml")?;
let spec = registry.get("vision.detect")?;
assert_eq!(spec.worker, "vision");

for (name, spec) in registry.by_worker("vision") {
    println!("{name} -> {}", spec.worker);
}
```

## How it is used

- `ant-http` serves the registry at `/api/v1/capabilities`
- `ant-cli list` prints every registered capability
- The pipeline executor looks up the worker for each stage
- The HTTP `call` route reads `timeout_ms` and the worker name from here

## Tests

```
cargo test -p ant-router
```

Covers: TOML parse, missing-capability error, filter by worker, default timeout.

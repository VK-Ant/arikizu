# ant-supervisor

The runtime's single owner of all worker processes, the event bus, policy enforcement, and the pipeline executor.

## What it contains

| Module       | Responsibility                                                            |
| ------------ | ------------------------------------------------------------------------- |
| root         | `Supervisor`, `WorkerConfig`, `WorkerHandle` — spawn and talk to workers  |
| `events`     | `EventBus` (tokio broadcast) — republishes worker events, pipeline events |
| `pipeline`   | `run_pipeline()` — walks stages, honors `feedback.approve` gates          |
| `policy`     | `Policy`, `load_policies()` — parses `policies/*.yaml` and checks hosts/caps |

## Supervisor lifecycle

1. `Supervisor::new(socket_dir)` creates the socket directory and the event bus.
2. For each worker in `arikizu.yaml` (or inferred from `capabilities.toml`):
   - Bind a Unix socket at `<socket_dir>/<worker>.sock`
   - Spawn the Python child with `ARIKIZU_SOCKET` set to that path
   - Accept the worker's connection (10s timeout)
   - Spawn a reader task (dispatches `Reply`/`Error`/`Heartbeat`/`Event`)
   - Spawn a writer task (sends `Call` frames from an mpsc channel)
3. `supervisor.worker("vision")?.call(...)` sends a Call and awaits the Reply.
4. `supervisor.shutdown()` drains, waits 2s, then kills each child.

## Making a capability call

```rust
let worker = supervisor.worker("vision").expect("worker running");
let result = worker.call(
    "vision.detect",
    serde_json::json!({ "image_path": "/tmp/x.jpg" }),
    30_000, // timeout_ms
).await?;
```

A call that times out is removed from `pending_calls`; the worker may still deliver a late reply, which is dropped.

## Event bus

`supervisor.bus` is a `tokio::sync::broadcast` with 1024-slot capacity. Any clone of the Supervisor's bus is a producer; any `.subscribe()` call returns a Receiver. Slow subscribers see `RecvError::Lagged(n)`; the HTTP WebSocket handler drops lagged events and keeps going.

Three ways events reach the bus:

- Workers publish via `Frame::Event { subject, payload }`; the reader task republishes with `source = <worker name>`
- The pipeline executor publishes `pipeline.started`, `pipeline.stage_ok`, `pipeline.stage_failed`, `pipeline.finished`, `pipeline.waiting_approval`
- The supervisor itself publishes `worker.ready`, `worker.heartbeat`, `worker.died`

## Policies

`load_policies("./policies")` reads every `*.yaml` under that directory into `Vec<Policy>`. Each policy has:

```yaml
name: no-outbound
allow_hosts: [127.0.0.1:11434]
allow_capabilities: [reasoning.summarize]
enforcement: block   # block | warn | off
```

`policy.check_capability(name)` and `policy.check_host(host)` return `Err(ArikizuError::PolicyDenied)` on a miss when enforcement is `block`, or log and allow on `warn`.

## Pipeline executor

```rust
let run = run_pipeline(
    &config.name,
    &config.pipeline,
    Arc::clone(&supervisor),
    Arc::clone(&feedback),
    supervisor.bus.clone(),
    &registry,
).await?;
```

Each stage either calls a capability (merging the carried JSON with the stage's `inputs`) or, if `capability == "feedback.approve"`, registers a `PendingAction` and awaits the human's decision (up to 60 min). Any failure or rejection terminates the run; status is `Succeeded`, `Rejected`, or `Failed`.

## Tests

```
cargo test -p ant-supervisor                                # unit
cargo test -p ant-supervisor --test integration -- --test-threads=1   # live worker (requires uv)
```

# ant-cli

The `arikizu` binary. Thin clap-based CLI; most commands drive the HTTP API of a running `arikizu run`, except `init`, `validate`, and `status --dev` which work offline.

## Subcommands

| Command                                | What it does                                                  |
| -------------------------------------- | ------------------------------------------------------------- |
| `arikizu init <name>`                  | Scaffold a new project with `arikizu.yaml`, `capabilities.toml` |
| `arikizu run [--bind] [--no-workers]` | Load YAML, spawn workers, serve HTTP, trap Ctrl+C             |
| `arikizu status [--dev] [--json]`     | Hit `/api/v1/status`, or dump device inventory in dev mode   |
| `arikizu call <cap> '<json>'`         | POST `/api/v1/call/<domain>/<op>` with the given payload      |
| `arikizu list`                         | Print every capability in `capabilities.toml`                 |
| `arikizu pull <worker>`                | Model pull (Weekend 15)                                       |
| `arikizu feedback rate <id> <label>`  | POST `/api/v1/feedback/rate`                                  |
| `arikizu feedback pending`             | GET `/api/v1/feedback/pending`                                |
| `arikizu feedback approve <id>`        | POST `/api/v1/feedback/approve`                               |
| `arikizu feedback reject <id> --reason`| POST `/api/v1/feedback/reject`                                |
| `arikizu validate [config]`            | Parse YAML, print "valid" or the error                        |
| `arikizu run-pipeline <name>`         | POST `/api/v1/pipeline/run`                                   |
| `arikizu stop`                          | POST `/api/v1/stop`                                           |

## `arikizu run` sequence

1. Load `arikizu.yaml` (or build defaults if missing).
2. Load `capabilities.toml`.
3. Load every `policies/*.yaml`.
4. Open the SQLite audit log at `runtime.db_path`.
5. Append a `runtime.started` row.
6. Create the Supervisor and FeedbackManager (wired to the audit log).
7. For each worker in the YAML (or inferred from the capability registry), call `supervisor.spawn_worker(WorkerConfig::from_spec(&spec))`.
8. Build the `AppState` and start the axum server.
9. `tokio::select!` on the HTTP server future vs. Ctrl+C.
10. On Ctrl+C: drain workers, append `runtime.stopped`, exit.

## uv convention

Default worker invocation when `workers:` is not declared in `arikizu.yaml`:

```
uv run --package <worker-name>-worker python -m <worker-name>_worker
```

Override by declaring an explicit `workers:` block with `python` and `args`.

## Environment variables

| Variable             | Effect                                                        |
| -------------------- | ------------------------------------------------------------- |
| `RUST_LOG`           | tracing filter (default `info`; try `debug,ant_supervisor=trace`) |
| `ARIKIZU_SOCKET`     | Set by the supervisor on each worker child; do not set yourself |
| `ARIKIZU_OLLAMA_ENDPOINT` | Reasoning worker's HTTP endpoint (default `http://127.0.0.1:11434`) |
| `ARIKIZU_REASONING_MODEL` | Reasoning worker's model (default `qwen2.5:3b-instruct-q4_K_M`) |
| `ARIKIZU_GOLDEN_DIR` | Eval worker's golden-set root (default `./golden`)             |

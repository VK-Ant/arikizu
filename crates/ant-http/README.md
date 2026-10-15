# ant-http

Local axum server. Serves the REST API under `/api/v1/` and the SvelteKit dashboard at `/` (embedded as a static site at build time in Weekend 8).

Default bind: `127.0.0.1:7000` (configurable via `runtime.http_api` in `arikizu.yaml` or `arikizu run --bind`).

## Routes

| Method | Path                                 | Purpose                                       |
| ------ | ------------------------------------ | --------------------------------------------- |
| GET    | `/health`                            | 200 "ok"                                       |
| GET    | `/api/v1/status`                     | Runtime, workers, device, counts               |
| GET    | `/api/v1/devices`                    | Full device inventory                          |
| GET    | `/api/v1/capabilities`               | Registered capabilities + their workers        |
| GET    | `/api/v1/workers`                    | Per-worker state and capabilities              |
| POST   | `/api/v1/call/:domain/:op`           | Invoke a capability with `{ payload: ... }`    |
| POST   | `/api/v1/feedback/rate`              | `{ query_id, label, note? }`                   |
| POST   | `/api/v1/feedback/correct`           | `{ result_id, corrections }`                   |
| POST   | `/api/v1/feedback/approve`           | `{ action_id, approver, note? }`               |
| POST   | `/api/v1/feedback/reject`            | `{ action_id, approver, reason }`              |
| POST   | `/api/v1/feedback/annotate`          | `{ query_id, ground_truth, labels? }`          |
| GET    | `/api/v1/feedback/pending`           | List pending actions                           |
| GET    | `/api/v1/pipeline/config`            | Parsed `arikizu.yaml`                          |
| POST   | `/api/v1/pipeline/run`               | Run the configured pipeline synchronously      |
| GET    | `/api/v1/audit?limit=N&kind=X`       | Tail or filter audit rows                      |
| GET    | `/api/v1/events`                     | WebSocket; one JSON event per message           |
| POST   | `/api/v1/stop`                       | Drain and exit                                 |

## AppState

```rust
pub struct AppState {
    pub supervisor: Arc<Supervisor>,
    pub registry: Arc<CapabilityRegistry>,
    pub feedback: Arc<FeedbackManager>,
    pub audit: Arc<AuditLog>,
    pub config: Arc<ArikizuConfig>,
}
```

Each handler takes `State<AppState>` and dispatches to the right subsystem.

## Example calls

```
# Health
curl http://127.0.0.1:7000/health

# Status (JSON)
curl http://127.0.0.1:7000/api/v1/status

# Call a capability
curl -X POST http://127.0.0.1:7000/api/v1/call/test/echo \
     -H 'content-type: application/json' \
     -d '{"payload":{"message":"hi"}}'

# Audit tail (last 50 pipeline rows)
curl 'http://127.0.0.1:7000/api/v1/audit?limit=50&kind=pipeline.'

# Approve a pending action
curl -X POST http://127.0.0.1:7000/api/v1/feedback/approve \
     -H 'content-type: application/json' \
     -d '{"action_id":"...","approver":"operator"}'

# Live event stream (websocat)
websocat ws://127.0.0.1:7000/api/v1/events
```

## WebSocket events

Each message is a JSON `Event`:

```json
{
  "subject": "pipeline.stage_ok",
  "timestamp": "2026-10-12T12:34:56.123Z",
  "source": "factory-floor-qa",
  "payload": { "run_id": "...", "stage": "detect_defects" }
}
```

Slow subscribers that fall behind by >1024 messages are dropped and reconnect; the dashboard code handles that in `src/lib/api.ts`.

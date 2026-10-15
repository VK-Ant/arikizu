# ant-feedback

The responsible-AI pillar. Routes human feedback to the right subsystem and writes every event to a SQLite audit log.

## Four touchpoints

| Touchpoint          | What it means                                   | Where it ends up                  |
| ------------------- | ----------------------------------------------- | --------------------------------- |
| `feedback.rate`     | Thumbs-up/down on a result                      | Reward for adaptive-intelligence  |
| `feedback.correct`  | Operator fixed the extraction                   | Template update + golden candidate |
| `feedback.approve` / `reject` | Release gate for a pipeline stage      | PendingAction + run resumes/stops  |
| `feedback.annotate` | Operator labeled a result as ground truth       | Append to golden set              |

Every touchpoint also appends an immutable row to the audit log.

## API

```rust
let audit = Arc::new(AuditLog::open("./arikizu.db")?);
let feedback = Arc::new(
    FeedbackManager::new().with_audit(Arc::clone(&audit))
);

feedback.rate(query_id, FeedbackLabel::Good, Some("looks right".into())).await?;
feedback.approve(action_id, "shift_lead".into(), None).await?;
```

### Approval gates

The pipeline executor calls `register_pending(action)` which inserts a `PendingAction` and returns a `oneshot::Receiver<ApprovalDecision>`. When a human posts `/api/v1/feedback/approve` or `/reject`, the manager fulfills the oneshot and the pipeline resumes or stops.

## Audit log

SQLite file at `runtime.db_path` (default `./arikizu.db`). Schema:

```sql
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,         -- ISO 8601 UTC
    kind TEXT NOT NULL,       -- feedback.rate, pipeline.started, policy.denied, ...
    actor TEXT,               -- user or worker name
    subject TEXT,             -- optional id this row concerns
    payload TEXT NOT NULL     -- JSON blob
);
CREATE INDEX idx_audit_ts ON audit(ts);
CREATE INDEX idx_audit_kind ON audit(kind);
```

Writes:

```rust
audit.append("feedback.rate", Some("vk"), Some(&query_id.to_string()), &payload)?;
```

Reads:

```rust
audit.tail(100)?;                                 // newest first
audit.by_kind_prefix("feedback.", 100)?;          // all feedback rows
audit.count()?;                                   // total rows
```

The log is append-only; there is no `UPDATE` or `DELETE` path. The Trust zone depends on that.

## Tests

```
cargo test -p ant-feedback
```

Covers: rate records event in history, approve/reject release the pending oneshot, approve on unknown id returns `ApprovalActionNotFound`, audit round-trip (append + tail + kind prefix).

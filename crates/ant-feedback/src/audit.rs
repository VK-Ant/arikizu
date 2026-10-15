//! SQLite-backed append-only audit log.
//!
//! Every feedback event, pipeline run, and policy denial lands here as a
//! row with timestamp, kind, actor, and JSON payload. Rows are never
//! updated or deleted; the Trust zone depends on that.
//!
//! Schema:
//!   CREATE TABLE audit (
//!     id INTEGER PRIMARY KEY AUTOINCREMENT,
//!     ts  TEXT NOT NULL,           -- ISO 8601
//!     kind TEXT NOT NULL,          -- feedback.rate, pipeline.started, policy.denied, ...
//!     actor TEXT,                  -- user or worker name
//!     subject TEXT,                -- optional id this row concerns
//!     payload TEXT NOT NULL        -- JSON blob
//!   );
//!   CREATE INDEX idx_audit_ts ON audit(ts);
//!   CREATE INDEX idx_audit_kind ON audit(kind);

use ant_common::{ArikizuError, Result};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditRow {
    pub id: i64,
    pub ts: DateTime<Utc>,
    pub kind: String,
    pub actor: Option<String>,
    pub subject: Option<String>,
    pub payload: serde_json::Value,
}

pub struct AuditLog {
    conn: Mutex<Connection>,
}

impl AuditLog {
    /// Open or create a SQLite file at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let conn = Connection::open(path.as_ref())
            .map_err(|e| ArikizuError::Other(format!("open audit db: {e}")))?;
        Self::init_schema(&conn)?;
        Ok(Self { conn: Mutex::new(conn) })
    }

    /// In-memory variant for tests.
    pub fn open_in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()
            .map_err(|e| ArikizuError::Other(format!("open audit db in-memory: {e}")))?;
        Self::init_schema(&conn)?;
        Ok(Self { conn: Mutex::new(conn) })
    }

    fn init_schema(conn: &Connection) -> Result<()> {
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                actor TEXT,
                subject TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
            CREATE INDEX IF NOT EXISTS idx_audit_kind ON audit(kind);
            ",
        )
        .map_err(|e| ArikizuError::Other(format!("init audit schema: {e}")))?;
        Ok(())
    }

    /// Append one row. Returns the new row id.
    pub fn append(
        &self,
        kind: &str,
        actor: Option<&str>,
        subject: Option<&str>,
        payload: &serde_json::Value,
    ) -> Result<i64> {
        let conn = self.conn.lock().unwrap();
        let ts = Utc::now().to_rfc3339();
        let payload_s = serde_json::to_string(payload)
            .map_err(|e| ArikizuError::Serialization(e.to_string()))?;
        conn.execute(
            "INSERT INTO audit (ts, kind, actor, subject, payload) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![ts, kind, actor, subject, payload_s],
        )
        .map_err(|e| ArikizuError::Other(format!("append audit row: {e}")))?;
        Ok(conn.last_insert_rowid())
    }

    /// Tail the last N rows, newest first.
    pub fn tail(&self, limit: usize) -> Result<Vec<AuditRow>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn
            .prepare("SELECT id, ts, kind, actor, subject, payload FROM audit ORDER BY id DESC LIMIT ?1")
            .map_err(|e| ArikizuError::Other(e.to_string()))?;
        let rows = stmt
            .query_map(params![limit as i64], row_from_sql)
            .map_err(|e| ArikizuError::Other(e.to_string()))?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r.map_err(|e| ArikizuError::Other(e.to_string()))?);
        }
        Ok(out)
    }

    /// All rows whose `kind` matches a prefix, newest first.
    pub fn by_kind_prefix(&self, prefix: &str, limit: usize) -> Result<Vec<AuditRow>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn
            .prepare(
                "SELECT id, ts, kind, actor, subject, payload \
                 FROM audit WHERE kind LIKE ?1 ORDER BY id DESC LIMIT ?2",
            )
            .map_err(|e| ArikizuError::Other(e.to_string()))?;
        let pattern = format!("{prefix}%");
        let rows = stmt
            .query_map(params![pattern, limit as i64], row_from_sql)
            .map_err(|e| ArikizuError::Other(e.to_string()))?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r.map_err(|e| ArikizuError::Other(e.to_string()))?);
        }
        Ok(out)
    }

    /// Row count.
    pub fn count(&self) -> Result<i64> {
        let conn = self.conn.lock().unwrap();
        let n: i64 = conn
            .query_row("SELECT COUNT(*) FROM audit", [], |r| r.get(0))
            .map_err(|e| ArikizuError::Other(e.to_string()))?;
        Ok(n)
    }
}

fn row_from_sql(r: &rusqlite::Row) -> rusqlite::Result<AuditRow> {
    let id: i64 = r.get(0)?;
    let ts_s: String = r.get(1)?;
    let kind: String = r.get(2)?;
    let actor: Option<String> = r.get(3)?;
    let subject: Option<String> = r.get(4)?;
    let payload_s: String = r.get(5)?;
    let ts = DateTime::parse_from_rfc3339(&ts_s)
        .map(|dt| dt.with_timezone(&Utc))
        .unwrap_or_else(|_| Utc::now());
    let payload: serde_json::Value =
        serde_json::from_str(&payload_s).unwrap_or(serde_json::Value::Null);
    Ok(AuditRow {
        id,
        ts,
        kind,
        actor,
        subject,
        payload,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn append_and_tail_round_trip() {
        let log = AuditLog::open_in_memory().unwrap();
        log.append(
            "feedback.rate",
            Some("vk"),
            Some("query-123"),
            &serde_json::json!({"label": "good"}),
        )
        .unwrap();
        log.append("pipeline.started", None, Some("run-1"), &serde_json::json!({}))
            .unwrap();
        let rows = log.tail(10).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].kind, "pipeline.started");
        assert_eq!(rows[1].kind, "feedback.rate");
        assert_eq!(log.count().unwrap(), 2);
    }

    #[test]
    fn by_kind_prefix_filters() {
        let log = AuditLog::open_in_memory().unwrap();
        log.append("feedback.rate", None, None, &serde_json::json!({})).unwrap();
        log.append("feedback.approve", None, None, &serde_json::json!({})).unwrap();
        log.append("pipeline.started", None, None, &serde_json::json!({})).unwrap();
        let feedback_rows = log.by_kind_prefix("feedback.", 10).unwrap();
        assert_eq!(feedback_rows.len(), 2);
    }
}

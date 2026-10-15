//! IPC between the Rust supervisor and Python workers.
//!
//! Protocol: length-prefixed MessagePack frames over a Unix domain socket.
//! Large tensors travel via shared memory handles; this module handles only
//! the control plane.

use ant_common::ArikizuError;
use serde::{Deserialize, Serialize};
use std::path::Path;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use uuid::Uuid;

/// Protocol version. Bump on incompatible wire changes.
pub const PROTOCOL_VERSION: u16 = 1;

/// A single framed message exchanged over the socket.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Frame {
    /// Worker → runtime on startup.
    Hello {
        worker: String,
        version: u16,
        capabilities: Vec<String>,
    },

    /// Runtime → worker to invoke a capability.
    Call {
        id: Uuid,
        capability: String,
        payload: serde_json::Value,
    },

    /// Worker → runtime with the result.
    Reply {
        id: Uuid,
        result: serde_json::Value,
    },

    /// Worker → runtime with an error.
    Error {
        id: Uuid,
        error: String,
    },

    /// Either direction, 1 Hz health signal.
    Heartbeat {
        memory_rss_mb: u64,
        queue_depth: u32,
        in_flight: u32,
        resident_models: Vec<String>,
    },

    /// Worker → runtime to publish an event.
    Event {
        subject: String,
        payload: serde_json::Value,
    },
}

/// Write a Frame to the socket with length prefix.
pub async fn write_frame<W>(w: &mut W, frame: &Frame) -> Result<(), ArikizuError>
where
    W: AsyncWriteExt + Unpin,
{
    let bytes = rmp_serde::to_vec_named(frame)
        .map_err(|e| ArikizuError::Serialization(e.to_string()))?;
    let len = bytes.len() as u32;
    w.write_u32(len).await.map_err(ArikizuError::Io)?;
    w.write_all(&bytes).await.map_err(ArikizuError::Io)?;
    w.flush().await.map_err(ArikizuError::Io)?;
    Ok(())
}

/// Read a Frame from the socket.
pub async fn read_frame<R>(r: &mut R) -> Result<Frame, ArikizuError>
where
    R: AsyncReadExt + Unpin,
{
    let len = r.read_u32().await.map_err(ArikizuError::Io)? as usize;
    if len > 100 * 1024 * 1024 {
        return Err(ArikizuError::Ipc(format!("frame too large: {len}")));
    }
    let mut buf = vec![0u8; len];
    r.read_exact(&mut buf).await.map_err(ArikizuError::Io)?;
    rmp_serde::from_slice(&buf).map_err(|e| ArikizuError::Serialization(e.to_string()))
}

/// Bind a Unix listener for the supervisor side.
pub async fn bind_supervisor(socket_path: &Path) -> Result<UnixListener, ArikizuError> {
    if socket_path.exists() {
        std::fs::remove_file(socket_path).ok();
    }
    let listener = UnixListener::bind(socket_path).map_err(ArikizuError::Io)?;
    tracing::info!(socket = %socket_path.display(), "supervisor listening");
    Ok(listener)
}

/// Connect to the supervisor from a worker.
pub async fn connect_to_supervisor(socket_path: &Path) -> Result<UnixStream, ArikizuError> {
    UnixStream::connect(socket_path).await.map_err(ArikizuError::Io)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::duplex;

    #[tokio::test]
    async fn frame_round_trip_hello() {
        let (mut a, mut b) = duplex(1024);
        let sent = Frame::Hello {
            worker: "test".into(),
            version: PROTOCOL_VERSION,
            capabilities: vec!["test.echo".into()],
        };
        write_frame(&mut a, &sent).await.unwrap();
        let received = read_frame(&mut b).await.unwrap();
        match received {
            Frame::Hello { worker, version, capabilities } => {
                assert_eq!(worker, "test");
                assert_eq!(version, PROTOCOL_VERSION);
                assert_eq!(capabilities, vec!["test.echo"]);
            }
            _ => panic!("wrong frame kind"),
        }
    }

    #[tokio::test]
    async fn frame_round_trip_call_and_reply() {
        let (mut a, mut b) = duplex(1024);
        let id = Uuid::new_v4();
        let call = Frame::Call {
            id,
            capability: "test.echo".into(),
            payload: serde_json::json!({"message": "hello"}),
        };
        write_frame(&mut a, &call).await.unwrap();
        let received = read_frame(&mut b).await.unwrap();
        match received {
            Frame::Call { id: rid, capability, payload } => {
                assert_eq!(rid, id);
                assert_eq!(capability, "test.echo");
                assert_eq!(payload["message"], "hello");
            }
            _ => panic!("wrong frame kind"),
        }
    }

    #[tokio::test]
    async fn oversized_frame_rejected() {
        let (mut a, mut b) = duplex(16);
        // Write a bogus 500MB length
        a.write_u32(500 * 1024 * 1024).await.unwrap();
        let result = read_frame(&mut b).await;
        assert!(matches!(result, Err(ArikizuError::Ipc(_))));
    }
}

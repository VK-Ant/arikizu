//! Local event bus.
//!
//! Workers emit events via Frame::Event; the supervisor republishes them
//! to any subscriber (HTTP WebSocket, audit log, pipeline executor).
//!
//! Backing store is `tokio::sync::broadcast`. Slow subscribers drop old
//! messages; subscribe before you miss anything you care about.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::broadcast;

/// An event circulating on the local bus.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub subject: String,
    pub timestamp: DateTime<Utc>,
    pub source: String,
    pub payload: serde_json::Value,
}

impl Event {
    pub fn new(subject: impl Into<String>, source: impl Into<String>, payload: serde_json::Value) -> Self {
        Self {
            subject: subject.into(),
            timestamp: Utc::now(),
            source: source.into(),
            payload,
        }
    }
}

/// Fan-out bus. Clone it freely; it is cheap and all clones share one channel.
#[derive(Clone)]
pub struct EventBus {
    inner: Arc<broadcast::Sender<Event>>,
}

impl EventBus {
    pub fn new(capacity: usize) -> Self {
        let (tx, _) = broadcast::channel(capacity);
        Self { inner: Arc::new(tx) }
    }

    /// Publish an event; a dropped subscriber does not fail the publish.
    pub fn publish(&self, event: Event) {
        let _ = self.inner.send(event);
    }

    /// Subscribe. A slow subscriber will see `RecvError::Lagged(n)` when it
    /// falls behind by more than `capacity` events; handle it by resyncing
    /// from the audit log.
    pub fn subscribe(&self) -> broadcast::Receiver<Event> {
        self.inner.subscribe()
    }

    pub fn subscriber_count(&self) -> usize {
        self.inner.receiver_count()
    }
}

impl Default for EventBus {
    fn default() -> Self {
        Self::new(1024)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[tokio::test]
    async fn publish_and_receive_one_event() {
        let bus = EventBus::new(16);
        let mut rx = bus.subscribe();
        bus.publish(Event::new("test.ping", "unit-test", json!({"n": 1})));
        let event = rx.recv().await.unwrap();
        assert_eq!(event.subject, "test.ping");
        assert_eq!(event.source, "unit-test");
    }

    #[tokio::test]
    async fn fanout_delivers_to_all_subscribers() {
        let bus = EventBus::new(16);
        let mut a = bus.subscribe();
        let mut b = bus.subscribe();
        bus.publish(Event::new("x", "src", json!({})));
        assert!(a.recv().await.is_ok());
        assert!(b.recv().await.is_ok());
    }

    #[tokio::test]
    async fn no_subscribers_is_not_an_error() {
        let bus = EventBus::new(16);
        bus.publish(Event::new("x", "src", json!({})));
    }
}

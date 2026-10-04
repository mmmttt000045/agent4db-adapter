//! Optional request-local timing. Nested spans describe latency; SQL counters charge work only to its executor.

use crate::db::MeterSnap;
use parking_lot::Mutex;
use serde::Serialize;
use std::collections::BTreeMap;
use std::future::Future;
use std::sync::Arc;
use std::time::Instant;

tokio::task_local! {
    static CURRENT: Arc<Ledger>;
}

struct Ledger {
    start: Instant,
    profile: Mutex<Profile>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Span {
    pub kind: String,
    pub start_ms: f64,
    pub end_ms: f64,
}

#[derive(Debug, Default, Serialize)]
pub struct Usage {
    pub replies: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub discarded_tokens: u64,
    pub served_models: BTreeMap<String, u64>,
}

#[derive(Debug, Default, Serialize)]
pub struct Profile {
    pub wall_ms: f64,
    pub db: MeterSnap,
    pub llm: Usage,
    pub spans: Vec<Span>,
}

/// Dropping a span also records failed operations and cancelled futures.
pub struct Timer {
    ledger: Option<Arc<Ledger>>,
    kind: String,
    start_ms: f64,
}

impl Timer {
    pub fn start(kind: &str) -> Timer {
        let ledger = CURRENT.try_with(Arc::clone).ok();
        let start_ms = ledger.as_ref().map_or(0.0, |l| l.start.elapsed().as_secs_f64() * 1000.0);
        Timer { ledger, kind: kind.into(), start_ms }
    }

    pub fn cancel(&mut self) {
        self.ledger = None;
    }
}

impl Drop for Timer {
    fn drop(&mut self) {
        if let Some(l) = &self.ledger {
            l.profile.lock().spans.push(Span {
                kind: self.kind.clone(),
                start_ms: self.start_ms,
                end_ms: l.start.elapsed().as_secs_f64() * 1000.0,
            });
        }
    }
}

pub async fn measure<T>(kind: &str, future: impl Future<Output = T>) -> T {
    if CURRENT.try_with(|_| ()).is_err() {
        return future.await;
    }
    let _timer = Timer::start(kind);
    future.await
}

pub async fn capture<T>(future: impl Future<Output = T>) -> (T, Profile) {
    let ledger = Arc::new(Ledger { start: Instant::now(), profile: Mutex::new(Profile::default()) });
    let result = CURRENT.scope(ledger.clone(), future).await;
    let mut profile = std::mem::take(&mut *ledger.profile.lock());
    profile.wall_ms = ledger.start.elapsed().as_secs_f64() * 1000.0;
    (result, profile)
}

pub fn query(kind: &str, micros: u64) {
    let _ = CURRENT.try_with(|l| {
        let mut p = l.profile.lock();
        let ms = micros as f64 / 1000.0;
        p.db.queries += 1;
        p.db.db_ms += ms;
        let entry = p.db.by_kind.entry(kind.into()).or_default();
        entry.0 += 1;
        entry.1 += ms;
    });
}

pub fn reply(input: u64, output: u64, discarded: u64, model: Option<&str>) {
    let _ = CURRENT.try_with(|l| {
        let mut p = l.profile.lock();
        p.llm.replies += 1;
        p.llm.input_tokens += input;
        p.llm.output_tokens += output;
        p.llm.discarded_tokens += discarded;
        if let Some(model) = model {
            *p.llm.served_models.entry(model.into()).or_default() += 1;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flight::Flight;

    #[tokio::test]
    async fn merged_requests_charge_sql_only_to_executor() {
        let flight = Flight::<u32>::default();
        let work = || async {
            query("metric", 1000);
            tokio::task::yield_now().await;
            Ok(42)
        };
        let (a, b) = tokio::join!(capture(flight.run(true, "key", work)), capture(flight.run(true, "key", work)));
        assert_eq!(a.0.unwrap(), (42, false));
        assert_eq!(b.0.unwrap(), (42, true));
        assert_eq!(a.1.db.queries, 1);
        assert_eq!(b.1.db.queries, 0);
        assert!(b.1.spans.iter().any(|s| s.kind == "shared_wait"));
        assert!(!a.1.spans.iter().any(|s| s.kind == "shared_wait"));
    }

    #[tokio::test]
    async fn failure_keeps_elapsed_time_and_completed_usage() {
        let (result, profile) = capture(measure("llm", async {
            reply(10, 3, 0, Some("test"));
            query("exec", 2000);
            Err::<(), _>("failure")
        }))
        .await;
        assert!(result.is_err());
        assert_eq!(profile.llm.input_tokens, 10);
        assert_eq!(profile.db.db_ms, 2.0);
        assert!(profile.spans[0].end_ms <= profile.wall_ms);
    }
}

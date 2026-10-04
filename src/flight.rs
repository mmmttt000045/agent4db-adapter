//! 在途合并（single-flight）：同一时刻相同的探查 / 检查只打一次数据库，结果分发给所有等待者。

use anyhow::{anyhow, Result};
use parking_lot::Mutex;
use std::collections::HashMap;
use std::future::Future;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::OnceCell;

type Cell<T> = Arc<OnceCell<Result<T, String>>>;

pub struct Flight<T: Clone> {
    map: Mutex<HashMap<String, Cell<T>>>,
    pub merged: AtomicU64,
}

impl<T: Clone> Default for Flight<T> {
    fn default() -> Self {
        Flight { map: Mutex::new(HashMap::new()), merged: AtomicU64::new(0) }
    }
}

impl<T: Clone> Flight<T> {
    /// 返回 (结果, 是否搭了别人的车)。
    pub async fn run<F, Fut>(&self, enabled: bool, key: &str, f: F) -> Result<(T, bool)>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<T>>,
    {
        if !enabled {
            return f().await.map(|v| (v, false));
        }
        let cell = {
            let mut m = self.map.lock();
            m.entry(key.to_string()).or_insert_with(|| Arc::new(OnceCell::new())).clone()
        };
        let ran = AtomicBool::new(false);
        let ran_ref = &ran;
        let mut wait = crate::timing::Timer::start("shared_wait");
        let res = cell
            .get_or_init(move || async move {
                ran_ref.store(true, Ordering::Relaxed);
                f().await.map_err(|e| format!("{e:#}"))
            })
            .await
            .clone();
        if ran.load(Ordering::Relaxed) {
            wait.cancel();
            let mut m = self.map.lock();
            if m.get(key).is_some_and(|c| Arc::ptr_eq(c, &cell)) {
                m.remove(key);
            }
        } else {
            self.merged.fetch_add(1, Ordering::Relaxed);
        }
        res.map(|v| (v, !ran.load(Ordering::Relaxed))).map_err(|e| anyhow!(e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn concurrent_calls_share_work_but_later_calls_retry() {
        let flight = Flight::<u32>::default();
        let calls = AtomicU64::new(0);
        let work = || async {
            calls.fetch_add(1, Ordering::Relaxed);
            tokio::task::yield_now().await;
            Ok(42)
        };
        let (a, b) = tokio::join!(flight.run(true, "key", work), flight.run(true, "key", work));
        assert_eq!(a.unwrap(), (42, false));
        assert_eq!(b.unwrap(), (42, true));
        assert_eq!(calls.load(Ordering::Relaxed), 1);
        assert_eq!(flight.run(true, "key", work).await.unwrap(), (42, false));
        assert_eq!(calls.load(Ordering::Relaxed), 2);
    }

    #[tokio::test]
    async fn errors_do_not_poison_later_calls() {
        let flight = Flight::<u32>::default();
        assert!(flight.run(true, "key", || async { anyhow::bail!("failed") }).await.is_err());
        assert_eq!(flight.run(true, "key", || async { Ok(7) }).await.unwrap(), (7, false));
    }

    #[tokio::test]
    async fn disabled_calls_do_not_merge() {
        let flight = Flight::<u32>::default();
        let (a, b) = tokio::join!(flight.run(false, "key", || async { Ok(1) }), flight.run(false, "key", || async { Ok(2) }));
        assert_eq!(a.unwrap(), (1, false));
        assert_eq!(b.unwrap(), (2, false));
    }
}

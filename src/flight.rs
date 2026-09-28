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
        let res = cell
            .get_or_init(move || async move {
                ran_ref.store(true, Ordering::Relaxed);
                f().await.map_err(|e| format!("{e:#}"))
            })
            .await
            .clone();
        if ran.load(Ordering::Relaxed) {
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

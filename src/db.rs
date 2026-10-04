//! 数据库访问：连接池 + 计量（每条 SQL 记入所属类别，便于比较“数据库替谁买单”）。

use anyhow::{anyhow, Context, Result};
use deadpool_postgres::{Manager, ManagerConfig, Pool, RecyclingMethod};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;
use tokio_postgres::{NoTls, SimpleQueryMessage};

/// SQL 的用途类别。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize)]
pub enum QKind {
    /// 读系统目录、版本指纹
    Meta = 0,
    /// 表探查（行数、空值、样例）
    Probe = 1,
    /// 关联验证检查
    Check = 2,
    /// 复用前的语义守卫
    Guard = 3,
    /// 粒度修复（找区分列）
    Repair = 4,
    /// 执行 Agent 的查询
    Exec = 5,
    /// 指标经验的晋升门槛、守护与回归
    Metric = 6,
}

pub const QKINDS: [QKind; 7] = [QKind::Meta, QKind::Probe, QKind::Check, QKind::Guard, QKind::Repair, QKind::Exec, QKind::Metric];

impl QKind {
    pub fn name(self) -> &'static str {
        match self {
            QKind::Meta => "meta",
            QKind::Probe => "probe",
            QKind::Check => "check",
            QKind::Guard => "guard",
            QKind::Repair => "repair",
            QKind::Exec => "exec",
            QKind::Metric => "metric",
        }
    }
}

#[derive(Default)]
pub struct Meter {
    counts: [AtomicU64; 7],
    micros: [AtomicU64; 7],
}

#[derive(Clone, Debug, Serialize, Default)]
pub struct MeterSnap {
    pub queries: u64,
    pub db_ms: f64,
    /// 类别 -> (条数, 毫秒)
    pub by_kind: BTreeMap<String, (u64, f64)>,
}

/// 两次快照之间的增量（b − a）。
pub fn diff(a: &MeterSnap, b: &MeterSnap) -> MeterSnap {
    let mut d = MeterSnap { queries: b.queries - a.queries, db_ms: b.db_ms - a.db_ms, by_kind: BTreeMap::new() };
    for (k, (n, ms)) in &b.by_kind {
        let (n0, ms0) = a.by_kind.get(k).copied().unwrap_or((0, 0.0));
        d.by_kind.insert(k.clone(), (n - n0, ms - ms0));
    }
    d
}

impl Meter {
    fn record(&self, k: QKind, us: u64) {
        self.counts[k as usize].fetch_add(1, Ordering::Relaxed);
        self.micros[k as usize].fetch_add(us, Ordering::Relaxed);
        crate::timing::query(k.name(), us);
    }

    pub fn snap(&self) -> MeterSnap {
        let mut s = MeterSnap::default();
        for k in QKINDS {
            let n = self.counts[k as usize].load(Ordering::Relaxed);
            let ms = self.micros[k as usize].load(Ordering::Relaxed) as f64 / 1000.0;
            s.queries += n;
            s.db_ms += ms;
            s.by_kind.insert(k.name().to_string(), (n, ms));
        }
        s
    }
}

/// 结果集：全部按文本取回（simple query 协议），够原型用。
#[derive(Clone, Debug, Default)]
pub struct Rows {
    pub cols: Vec<String>,
    pub rows: Vec<Vec<Option<String>>>,
}

impl Rows {
    pub fn cell(&self, r: usize, c: usize) -> Option<&str> {
        self.rows.get(r)?.get(c)?.as_deref()
    }
    pub fn i64(&self, r: usize, c: usize) -> Option<i64> {
        self.cell(r, c)?.parse().ok()
    }
    pub fn f64(&self, r: usize, c: usize) -> Option<f64> {
        self.cell(r, c)?.parse().ok()
    }
    pub fn to_json(&self, max_rows: usize) -> Value {
        let rows: Vec<Value> = self
            .rows
            .iter()
            .take(max_rows)
            .map(|r| Value::Array(r.iter().map(|v| v.clone().map(Value::String).unwrap_or(Value::Null)).collect()))
            .collect();
        json!({
            "columns": self.cols,
            "rows": rows,
            "row_count": self.rows.len(),
            "truncated": self.rows.len() > max_rows,
        })
    }
}

pub struct Db {
    pool: Pool,
    pub meter: Meter,
}

impl Db {
    /// `read_only`：Agent 用的连接池一律只读，ETL / 初始化用单独的可写池。单条 SQL 超时 300 秒。
    pub fn connect(url: &str, size: usize, read_only: bool) -> Result<Self> {
        Self::connect_timeout(url, size, read_only, 300)
    }

    pub fn connect_timeout(url: &str, size: usize, read_only: bool, timeout_secs: u64) -> Result<Self> {
        anyhow::ensure!(size > 0, "连接池大小必须大于 0");
        let mut pg: tokio_postgres::Config = url.parse().context("数据库连接串格式错误")?;
        let mut opts = format!("-c statement_timeout={}", timeout_secs * 1000);
        if read_only {
            opts.push_str(" -c default_transaction_read_only=on");
        }
        pg.options(&opts);
        let mgr = Manager::from_config(pg, NoTls, ManagerConfig { recycling_method: RecyclingMethod::Fast });
        let pool = Pool::builder(mgr).max_size(size).build()?;
        Ok(Db { pool, meter: Meter::default() })
    }

    pub async fn query(&self, kind: QKind, sql: &str) -> Result<Rows> {
        let client = crate::timing::measure("pool_wait", self.pool.get()).await.context("获取数据库连接失败")?;
        timed_query(&client, &self.meter, kind, sql).await
    }

    /// 开启一个可重复读、只读的事务：之后经 `Snapshot::query` 的查询都看到同一个快照（取自事务里的第一条查询）。
    pub async fn snapshot(&self) -> Result<Snapshot<'_>> {
        let client = crate::timing::measure("pool_wait", self.pool.get()).await.context("获取数据库连接失败")?;
        client
            .simple_query("begin isolation level repeatable read read only")
            .await
            .map_err(|e| anyhow!("开启快照事务失败：{}", db_err(&e)))?;
        Ok(Snapshot { client: Some(client), meter: &self.meter })
    }

    /// 执行写入语句（初始化与 ETL 用），返回最后一条命令影响的行数。
    pub async fn execute(&self, sql: &str) -> Result<u64> {
        let client = self.pool.get().await.context("获取数据库连接失败")?;
        let t = Instant::now();
        let res = client.simple_query(sql).await;
        self.meter.record(QKind::Meta, t.elapsed().as_micros() as u64);
        let msgs = res.map_err(|e| anyhow!("SQL 执行失败：{}", db_err(&e)))?;
        Ok(msgs.iter().filter_map(|m| if let SimpleQueryMessage::CommandComplete(n) = m { Some(*n) } else { None }).last().unwrap_or(0))
    }
}

async fn timed_query(client: &tokio_postgres::Client, meter: &Meter, kind: QKind, sql: &str) -> Result<Rows> {
    let t = Instant::now();
    let _span = crate::timing::Timer::start(&format!("db:{}", kind.name()));
    let res = client.simple_query(sql).await;
    meter.record(kind, t.elapsed().as_micros() as u64);
    let msgs = res.map_err(|e| anyhow!("SQL 执行失败：{}", db_err(&e)))?;
    let mut out = Rows::default();
    for m in msgs {
        if let SimpleQueryMessage::RowDescription(ref cols) = m {
            out.cols = cols.iter().map(|c| c.name().to_string()).collect();
        }
        if let SimpleQueryMessage::Row(r) = m {
            if out.cols.is_empty() {
                out.cols = r.columns().iter().map(|c| c.name().to_string()).collect();
            }
            out.rows.push((0..r.len()).map(|i| r.get(i).map(|s| s.to_string())).collect());
        }
    }
    Ok(out)
}

/// 一个可重复读、只读事务。`commit` 后连接回到连接池；未提交就被丢弃时连接直接关闭（不回池），事务随之回滚，
/// 半开的事务不会被后来的请求拿到。
pub struct Snapshot<'a> {
    client: Option<deadpool_postgres::Object>,
    meter: &'a Meter,
}

impl Snapshot<'_> {
    pub async fn query(&self, kind: QKind, sql: &str) -> Result<Rows> {
        let client = self.client.as_ref().ok_or_else(|| anyhow!("快照事务已结束"))?;
        timed_query(client, self.meter, kind, sql).await
    }

    pub async fn commit(mut self) -> Result<()> {
        let client = self.client.take().ok_or_else(|| anyhow!("快照事务已结束"))?;
        client.simple_query("commit").await.map_err(|e| anyhow!("提交快照事务失败：{}", db_err(&e)))?;
        Ok(())
    }
}

impl Drop for Snapshot<'_> {
    fn drop(&mut self) {
        if let Some(client) = self.client.take() {
            drop(deadpool_postgres::Object::take(client));
        }
    }
}

fn db_err(e: &tokio_postgres::Error) -> String {
    match e.as_db_error() {
        Some(d) => format!("{} {}", d.code().code(), d.message()),
        None => e.to_string(),
    }
}

/// SQL 字符串字面量转义。
pub fn lit(s: &str) -> String {
    format!("'{}'", s.replace('\'', "''"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn result_serialization_preserves_nulls_and_truncation() {
        let rows = Rows { cols: vec!["amount".into()], rows: vec![vec![Some("12.50".into())], vec![None]] };
        assert_eq!(rows.to_json(1), json!({"columns": ["amount"], "rows": [["12.50"]], "row_count": 2, "truncated": true}));
        assert_eq!(rows.to_json(2)["rows"][1][0], Value::Null);
        assert!(Db::connect("postgres://localhost/test", 0, true).is_err());
    }
}

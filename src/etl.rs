//! 数据准备与“ETL 改版”模拟（对应 PPT 第 4、8 页）。
//!
//! v1（基线）：store_returns 每条退货一行，sr_status 列恒为“完成”。
//! v2（改版）：自 2001-10-01 起的退货改为“一行一次状态变更”——额外写入一行“申请”，金额相同。
//! 表名、列名都不变，旧 SQL 照常执行，只是 SUM(退货金额) 会重复计算。

use crate::catalog;
use crate::db::{Db, QKind};
use anyhow::Result;
use std::time::Duration;

pub const CHANGE_DATE: &str = "2001-10-01";

async fn exec(db: &Db, sql: &str) -> Result<()> {
    db.query(QKind::Meta, sql).await?;
    Ok(())
}

/// 幂等：建批次日志表、加状态列（v1 全为“完成”）。
pub async fn setup(db: &Db) -> Result<()> {
    exec(db, "create table if not exists etl_batch_log (table_name text, batch_id int, note text, applied_at timestamptz default now())")
        .await?;
    exec(db, "alter table store_returns add column if not exists sr_status varchar(8) not null default '完成'").await?;
    exec(db, "comment on column store_returns.sr_status is '退货状态：申请 / 完成'").await?;
    let n = db.query(QKind::Meta, "select count(*) from etl_batch_log").await?.i64(0, 0).unwrap_or(0);
    if n == 0 {
        exec(db, "insert into etl_batch_log values ('store_returns', 1, '初始装载', now())").await?;
    }
    exec(db, "analyze store_returns").await?;
    Ok(())
}

async fn next_batch(db: &Db) -> Result<i64> {
    Ok(db
        .query(QKind::Meta, "select coalesce(max(batch_id), 0) + 1 from etl_batch_log where table_name = 'store_returns'")
        .await?
        .i64(0, 0)
        .unwrap_or(1))
}

pub async fn is_v2(db: &Db) -> Result<bool> {
    Ok(db.query(QKind::Meta, "select exists (select 1 from store_returns where sr_status = '申请')").await?.cell(0, 0) == Some("t"))
}

/// 应用改版：为变更日之后的退货补写“申请”行。
pub async fn apply_v2(db: &Db) -> Result<i64> {
    if is_v2(db).await? {
        return Ok(0);
    }
    let cols = db
        .query(
            QKind::Meta,
            "select string_agg(column_name, ', ' order by ordinal_position) from information_schema.columns \
             where table_name = 'store_returns' and column_name <> 'sr_status'",
        )
        .await?;
    let cols = cols.cell(0, 0).unwrap_or_default().to_string();
    let sel: Vec<String> = cols.split(", ").map(|c| format!("r.{c}")).collect();
    let b = next_batch(db).await?;
    let before = catalog::versions(db).await?.get("store_returns").map(|v| v.dml).unwrap_or(0);
    exec(
        db,
        &format!(
            "insert into store_returns ({cols}, sr_status) select {}, '申请' from store_returns r \
             join date_dim d on r.sr_returned_date_sk = d.d_date_sk where d.d_date >= date '{CHANGE_DATE}' and r.sr_status = '完成'; select pg_stat_force_next_flush()",
            sel.join(", ")
        ),
    )
    .await?;
    exec(db, &format!("insert into etl_batch_log values ('store_returns', {b}, '退货改为状态流水（申请/完成各一行）', now())")).await?;
    exec(db, "analyze store_returns").await?;
    wait_stats(db, before).await?;
    let n = db.query(QKind::Meta, "select count(*) from store_returns where sr_status = '申请'").await?.i64(0, 0).unwrap_or(0);
    Ok(n)
}

/// 回到 v1（删除“申请”行），也记一个新批次。
pub async fn reset(db: &Db) -> Result<()> {
    if !is_v2(db).await? {
        return Ok(());
    }
    let b = next_batch(db).await?;
    let before = catalog::versions(db).await?.get("store_returns").map(|v| v.dml).unwrap_or(0);
    exec(db, "delete from store_returns where sr_status = '申请'; select pg_stat_force_next_flush()").await?;
    exec(db, &format!("insert into etl_batch_log values ('store_returns', {b}, '回滚到每条退货一行', now())")).await?;
    exec(db, "vacuum analyze store_returns").await?;
    wait_stats(db, before).await?;
    Ok(())
}

async fn wait_stats(db: &Db, before: i64) -> Result<()> {
    wait_table_stats(db, "store_returns", before).await
}

/// 等 pg_stat 的 DML 计数刷新（PG 统计是异步上报的），避免实验里同一次变更被“感知”两次。
pub(crate) async fn wait_table_stats(db: &Db, table: &str, before: i64) -> Result<()> {
    for _ in 0..40 {
        let now = catalog::versions(db).await?.get(table).map(|v| v.dml).unwrap_or(0);
        if now != before {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
    Ok(())
}

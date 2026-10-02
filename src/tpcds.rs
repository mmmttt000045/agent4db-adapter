//! TPC-DS 上的数据变化（配对回放的第二个负载）：与 `scenario::Change` 同一套分类、同一批名字，施加在 dsdgen 生成的
//! 真实 TPC-DS 表上（`tools/tpcds-load.sh` 装入的模板库）。表结构、列数与日期键都按 TPC-DS 的真实定义：
//! 写入一律按 information_schema 取全部列，日期条件经 date_dim 换算，不依赖合成数据的日期编号。
//! 每种变化仍分 `apply_truth`（改变业务事实）与 `apply_hidden`（只改变表示）两步，评测在两步之间计算标准答案。

use crate::catalog;
use crate::db::{Db, QKind};
use crate::etl;
use crate::metricbench::log_batch;
use crate::scenario;
use anyhow::{ensure, Result};
use serde::Serialize;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Change {
    Append,
    Backfill,
    Correct,
    AddColumn,
    Status,
    Revision,
    Duplicate,
    DimHistory,
    LateKey,
    Unit,
    Mirror,
}

/// 补录批次的小票号偏移（TPC-DS SF1 的小票号在 24 万以内）。
const OFFSET: i64 = 1_000_000_000;
const DUP_FROM: &str = "2002-06-01";
const DUP_TO: &str = "2002-09-30";
const UNIT_FROM: &str = "2002-07-01";

impl Change {
    pub fn parse(s: &str) -> Result<Change> {
        Ok(match scenario::Change::parse(s)? {
            scenario::Change::Append => Change::Append,
            scenario::Change::Backfill => Change::Backfill,
            scenario::Change::Correct => Change::Correct,
            scenario::Change::AddColumn => Change::AddColumn,
            scenario::Change::Status => Change::Status,
            scenario::Change::Revision => Change::Revision,
            scenario::Change::Duplicate => Change::Duplicate,
            scenario::Change::DimHistory => Change::DimHistory,
            scenario::Change::LateKey => Change::LateKey,
            scenario::Change::Unit => Change::Unit,
            scenario::Change::Mirror => Change::Mirror,
        })
    }

    /// 合成数据上的同名变化：名字、分类、涉及的表与说明都沿用它。
    pub fn syn(self) -> scenario::Change {
        match self {
            Change::Append => scenario::Change::Append,
            Change::Backfill => scenario::Change::Backfill,
            Change::Correct => scenario::Change::Correct,
            Change::AddColumn => scenario::Change::AddColumn,
            Change::Status => scenario::Change::Status,
            Change::Revision => scenario::Change::Revision,
            Change::Duplicate => scenario::Change::Duplicate,
            Change::DimHistory => scenario::Change::DimHistory,
            Change::LateKey => scenario::Change::LateKey,
            Change::Unit => scenario::Change::Unit,
            Change::Mirror => scenario::Change::Mirror,
        }
    }

    pub async fn apply_truth(self, db: &Db) -> Result<i64> {
        match self {
            Change::Append | Change::LateKey => {
                if has_growth(db).await? {
                    return Ok(0);
                }
                let c = cols(db, "store_sales", &[]).await?;
                let sel: Vec<String> = c
                    .iter()
                    .map(|x| if x == "ss_ticket_number" { format!("s.ss_ticket_number + {OFFSET}") } else { format!("s.{x}") })
                    .collect();
                write(
                    db,
                    "store_sales",
                    "补录 2002-09 门店销售",
                    &format!(
                        "insert into store_sales ({}) select {} from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk \
                         where d.d_year = 2002 and d.d_moy = 9",
                        c.join(", "),
                        sel.join(", ")
                    ),
                )
                .await
            }
            Change::Backfill => {
                db.query(
                    QKind::Meta,
                    "insert into aux.backfill_keys select ss_item_sk, ss_ticket_number from store_sales s \
                     where ss_sold_date_sk is not null and (ss_item_sk + ss_ticket_number) % 50 = 2 and ss_ticket_number % 2 = 0 \
                       and not exists (select 1 from store_returns r where r.sr_item_sk = s.ss_item_sk and r.sr_ticket_number = s.ss_ticket_number)",
                )
                .await?;
                write(
                    db,
                    "store_returns",
                    "补录漏记的历史退货",
                    "insert into store_returns (sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_customer_sk, sr_store_sk, \
                        sr_return_quantity, sr_return_amt, sr_return_tax, sr_return_amt_inc_tax, sr_fee, sr_net_loss) \
                     select least((select max(d_date_sk) from date_dim), ss_sold_date_sk + 1 + ss_ticket_number % 30), ss_item_sk, \
                            ss_ticket_number, ss_customer_sk, ss_store_sk, ss_quantity, a, round(a * 0.08, 2), round(a * 1.08, 2), f, \
                            round(a * 0.5 + f, 2) \
                     from store_sales s join aux.backfill_keys k on k.item = s.ss_item_sk and k.ticket = s.ss_ticket_number \
                     cross join lateral (select round(coalesce(ss_net_paid, 0) * (0.3 + (ss_ticket_number % 7) * 0.1), 2) as a, \
                                                (2 + ss_ticket_number % 5)::numeric(12,2) as f) x",
                )
                .await
            }
            Change::Correct => {
                write(
                    db,
                    "store_sales",
                    "更正 2002 年部分销售金额",
                    &format!(
                        "update store_sales set ss_net_paid = ss_net_paid - 1, ss_net_paid_inc_tax = ss_net_paid_inc_tax - 1.08, \
                         ss_net_profit = ss_net_profit - 1 where ss_ticket_number % 10 = 3 and ss_sold_date_sk >= {}",
                        sk("2002-01-01")
                    ),
                )
                .await
            }
            Change::Revision => {
                let c = cols(db, "store_sales", &["ss_is_current"]).await?;
                let n = write(
                    db,
                    "store_sales",
                    "更正改为追加新版本：保留旧版本行",
                    &format!(
                        "insert into store_sales ({0}, ss_is_current) select {0}, 0 from store_sales \
                         where ss_ticket_number % 10 = 7 and ss_sold_date_sk >= {1} and ss_is_current = 1",
                        c.join(", "),
                        sk("2001-01-01")
                    ),
                )
                .await?;
                write(
                    db,
                    "store_sales",
                    "更正改为追加新版本：当前行改为更正后金额",
                    &format!(
                        "update store_sales set ss_net_paid = round(ss_net_paid * 0.9, 2), \
                         ss_net_paid_inc_tax = round(ss_net_paid_inc_tax * 0.9, 2), \
                         ss_net_profit = ss_net_profit - ss_net_paid + round(ss_net_paid * 0.9, 2) \
                         where ss_ticket_number % 10 = 7 and ss_sold_date_sk >= {} and ss_is_current = 1",
                        sk("2001-01-01")
                    ),
                )
                .await?;
                Ok(n)
            }
            Change::Mirror => {
                write(
                    db,
                    "store_returns",
                    "更正 2002 年部分退货金额",
                    &format!("update store_returns set sr_return_amt = sr_return_amt - 1 where {}", mirror_fixed()),
                )
                .await
            }
            Change::AddColumn | Change::Status | Change::Duplicate | Change::DimHistory | Change::Unit => Ok(0),
        }
    }

    pub async fn apply_hidden(self, db: &Db) -> Result<i64> {
        match self {
            Change::AddColumn => {
                db.query(
                    QKind::Meta,
                    "alter table store_returns add column sr_reason_note varchar(20); \
                     comment on column store_returns.sr_reason_note is '退货原因备注（新接入，暂未填写）'",
                )
                .await?;
                Ok(0)
            }
            Change::Status => etl::apply_v2(db).await,
            Change::Duplicate => {
                write(
                    db,
                    "store_sales",
                    "2002-06 至 2002-09 批次重跑",
                    &format!(
                        "insert into store_sales select s.* from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk \
                         where d.d_date between date '{DUP_FROM}' and date '{DUP_TO}'"
                    ),
                )
                .await
            }
            Change::DimHistory => {
                let c = cols(db, "item", &["i_is_current"]).await?;
                let sel: Vec<String> = c
                    .iter()
                    .map(|x| {
                        if x == "i_category" {
                            "case when i_category = 'Books' then 'Music' else 'Books' end".to_string()
                        } else {
                            x.clone()
                        }
                    })
                    .collect();
                write(
                    db,
                    "item",
                    "商品维表改为保留历史版本",
                    &format!(
                        "insert into item ({}, i_is_current) select {}, 'N' from item where i_item_sk % 3 = 0 and i_is_current = 'Y'",
                        c.join(", "),
                        sel.join(", ")
                    ),
                )
                .await
            }
            Change::LateKey => {
                write(
                    db,
                    "store_sales",
                    "补录批次改用 yyyymmdd 日期键",
                    &format!(
                        "update store_sales s set ss_sold_date_sk = to_char(d.d_date, 'YYYYMMDD')::int from date_dim d \
                         where s.ss_sold_date_sk = d.d_date_sk and s.ss_ticket_number > {OFFSET}"
                    ),
                )
                .await
            }
            Change::Unit => {
                let sets: Vec<String> = money_cols(db).await?.iter().map(|c| format!("{c} = {c} * 100")).collect();
                write(
                    db,
                    "store_sales",
                    "金额改以分记录",
                    &format!(
                        "update store_sales s set {} from date_dim d where s.ss_sold_date_sk = d.d_date_sk and d.d_date >= date '{UNIT_FROM}'",
                        sets.join(", ")
                    ),
                )
                .await
            }
            Change::Mirror => {
                db.query(
                    QKind::Meta,
                    "alter table store_returns add column sr_source varchar(10) not null default 'primary'; \
                     comment on column store_returns.sr_source is '来源系统标识'",
                )
                .await?;
                let c = cols(db, "store_returns", &["sr_source"]).await?;
                let sel: Vec<String> = c
                    .iter()
                    .map(|x| {
                        if x == "sr_return_amt" {
                            format!("sr_return_amt + case when {} then 1 else 0 end", mirror_fixed())
                        } else {
                            x.clone()
                        }
                    })
                    .collect();
                write(
                    db,
                    "store_returns",
                    "写入退货备份副本",
                    &format!(
                        "insert into store_returns ({}, sr_source) select {}, 'backup' from store_returns where sr_source = 'primary'",
                        c.join(", "),
                        sel.join(", ")
                    ),
                )
                .await
            }
            Change::Append | Change::Backfill | Change::Correct | Change::Revision => Ok(0),
        }
    }

    pub async fn reset(self, db: &Db) -> Result<()> {
        match self {
            Change::Append | Change::LateKey => {
                if has_growth(db).await? {
                    write(db, "store_sales", "撤回补录", &format!("delete from store_sales where ss_ticket_number > {OFFSET}")).await?;
                    db.query(QKind::Meta, "vacuum analyze store_sales").await?;
                }
            }
            Change::Backfill => {
                write(
                    db,
                    "store_returns",
                    "撤回补录的退货",
                    "delete from store_returns r using aux.backfill_keys k where r.sr_item_sk = k.item and r.sr_ticket_number = k.ticket",
                )
                .await?;
                db.query(QKind::Meta, "truncate aux.backfill_keys").await?;
            }
            Change::Correct => {
                write(
                    db,
                    "store_sales",
                    "撤回金额更正",
                    &format!(
                        "update store_sales set ss_net_paid = ss_net_paid + 1, ss_net_paid_inc_tax = ss_net_paid_inc_tax + 1.08, \
                         ss_net_profit = ss_net_profit + 1 where ss_ticket_number % 10 = 3 and ss_sold_date_sk >= {}",
                        sk("2002-01-01")
                    ),
                )
                .await?;
            }
            Change::AddColumn => {
                db.query(QKind::Meta, "alter table store_returns drop column if exists sr_reason_note").await?;
            }
            Change::Status => etl::reset(db).await?,
            Change::Revision => {
                write(
                    db,
                    "store_sales",
                    "撤回版本化更正：恢复原金额",
                    "update store_sales c set ss_net_paid = o.ss_net_paid, ss_net_paid_inc_tax = o.ss_net_paid_inc_tax, \
                     ss_net_profit = o.ss_net_profit from store_sales o \
                     where o.ss_is_current = 0 and c.ss_is_current = 1 \
                       and c.ss_ticket_number = o.ss_ticket_number and c.ss_item_sk = o.ss_item_sk",
                )
                .await?;
                write(db, "store_sales", "撤回版本化更正：删除旧版本行", "delete from store_sales where ss_is_current = 0").await?;
            }
            Change::Duplicate => {
                write(
                    db,
                    "store_sales",
                    "撤回重复装载",
                    "delete from store_sales a using store_sales b \
                     where a.ss_ticket_number = b.ss_ticket_number and a.ss_item_sk = b.ss_item_sk and a.ctid > b.ctid",
                )
                .await?;
            }
            Change::DimHistory => {
                write(db, "item", "撤回商品历史版本", "delete from item where i_is_current = 'N'").await?;
            }
            Change::Mirror => {
                write(db, "store_returns", "删除退货备份副本", "delete from store_returns where sr_source = 'backup'").await?;
                db.query(QKind::Meta, "alter table store_returns drop column if exists sr_source").await?;
                write(
                    db,
                    "store_returns",
                    "撤回退货金额更正",
                    &format!("update store_returns set sr_return_amt = sr_return_amt + 1 where {}", mirror_fixed()),
                )
                .await?;
            }
            Change::Unit => {
                let sets: Vec<String> = money_cols(db).await?.iter().map(|c| format!("{c} = {c} / 100")).collect();
                write(
                    db,
                    "store_sales",
                    "撤回金额单位变化",
                    &format!(
                        "update store_sales s set {} from date_dim d where s.ss_sold_date_sk = d.d_date_sk and d.d_date >= date '{UNIT_FROM}'",
                        sets.join(", ")
                    ),
                )
                .await?;
            }
        }
        Ok(())
    }
}

/// 日期在 date_dim 中的键（子查询，嵌进 SQL）。
fn sk(date: &str) -> String {
    format!("(select d_date_sk from date_dim where d_date = date '{date}')")
}

/// 备份副本场景中被更正的退货（2002 年起、小票号尾数为 3）。
fn mirror_fixed() -> String {
    format!("sr_ticket_number % 10 = 3 and sr_returned_date_sk >= {}", sk("2002-01-01"))
}

async fn has_growth(db: &Db) -> Result<bool> {
    Ok(db.query(QKind::Meta, &format!("select exists (select 1 from store_sales where ss_ticket_number > {OFFSET})")).await?.cell(0, 0)
        == Some("t"))
}

/// 表的全部列（按定义顺序），可排除若干列。
async fn cols(db: &Db, table: &str, exclude: &[&str]) -> Result<Vec<String>> {
    let r = db
        .query(
            QKind::Meta,
            &format!(
                "select column_name from information_schema.columns where table_schema = 'public' and table_name = '{table}' \
                 order by ordinal_position"
            ),
        )
        .await?;
    Ok((0..r.rows.len())
        .filter_map(|i| r.cell(i, 0).map(str::to_string))
        .filter(|c| !exclude.contains(&c.as_str()))
        .collect())
}

/// 门店销售的全部金额列（numeric）。
async fn money_cols(db: &Db) -> Result<Vec<String>> {
    let r = db
        .query(
            QKind::Meta,
            "select column_name from information_schema.columns where table_schema = 'public' and table_name = 'store_sales' \
             and data_type = 'numeric' order by ordinal_position",
        )
        .await?;
    Ok((0..r.rows.len()).filter_map(|i| r.cell(i, 0).map(str::to_string)).collect())
}

/// 执行一条写入，记批次，刷新统计信息并等待 DML 计数上报。返回影响行数。
async fn write(db: &Db, table: &str, note: &str, sql: &str) -> Result<i64> {
    let before = catalog::versions(db).await?.get(table).map(|v| v.dml).unwrap_or(0);
    let n = db.execute(sql).await?;
    db.query(QKind::Meta, "select pg_stat_force_next_flush()").await?;
    log_batch(db, table, note).await?;
    db.query(QKind::Meta, &format!("analyze {table}")).await?;
    if n > 0 {
        etl::wait_table_stats(db, table, before).await?;
    }
    Ok(n as i64)
}

/// 模板库复制出来之后的准备：与合成数据相同的状态列、当前版本标志与批次日志（`etl::setup`、`scenario::setup` 的 SQL
/// 与表结构无关），外加回滚用的辅助表（放在 public 之外，中间层的目录与修复搜索只看 public）。幂等。
pub async fn setup(db: &Db) -> Result<()> {
    let pk = db
        .query(
            QKind::Meta,
            "select count(*) from pg_constraint where contype = 'p' and conrelid in \
             ('store_sales'::regclass, 'store_returns'::regclass, 'catalog_sales'::regclass)",
        )
        .await?
        .i64(0, 0)
        .unwrap_or(0);
    ensure!(pk == 0, "TPC-DS 事实表仍有主键，请用 tools/tpcds-load.sh 装载模板库");
    etl::setup(db).await?;
    scenario::setup(db).await?;
    db.query(QKind::Meta, "create schema if not exists aux; create table if not exists aux.backfill_keys (item int, ticket int)")
        .await?;
    Ok(())
}

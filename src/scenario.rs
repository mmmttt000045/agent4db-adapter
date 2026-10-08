//! 数据变化场景：按有效性条件分类，每个场景都从 v1 独立施加、结束后回滚到 v1，并逐表核对内容与 v1 一致。
//!
//! 施加分两步：`apply_truth` 改变业务事实（标准答案随之变化），`apply_hidden` 只改变数据的表示方式（业务事实不变）。
//! 评测在两步之间计算标准答案，因此重复装载、单位变化等场景的标准答案仍是真实业务值。

use crate::catalog;
use crate::db::{Db, QKind};
use crate::etl;
use crate::metricbench::{apply_growth, log_batch, reset_growth, GROWTH_OFFSET};
use anyhow::{bail, ensure, Result};
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Change {
    /// 正常：补录 2002-09 门店销售（新小票号）
    Append,
    /// 正常：补录漏记的历史退货（新的小票与商品键）
    Backfill,
    /// 正常：原地更正 2002 年部分销售的金额
    Correct,
    /// 正常：门店退货表新增一个无关列
    AddColumn,
    /// 粒度：2001-10 起退货改为状态流水，每笔多一行“申请”（v2）
    Status,
    /// 粒度：2001 年起部分销售被更正，旧版本保留为非当前行
    Revision,
    /// 粒度：2002 年 6–9 月的销售批次被重复装载
    Duplicate,
    /// 连接放大：商品维表改为保留历史版本，部分商品多一条旧版本行（同一商品键多行）
    DimHistory,
    /// 覆盖：补录的 2002-09 销售使用 yyyymmdd 日期键，关联不上日期维度
    LateKey,
    /// 未建模：2002-07 起门店销售金额改以“分”记录
    Unit,
    /// 粒度（语义歧义，受限修复的反例）：退货表写入整份备份副本（来源列取 backup），2002 年被更正的退货在副本里仍是旧金额。
    /// 取 primary 或 backup 都能恢复唯一性且不丢键，只有业务语义能区分；不在 ALL 中，需显式指定
    Mirror,
    /// 优化前提：日期维度重装载，2002-02 的日期换成新的代理键（接在最大键之后），三张事实表的日期键同步改指向新键。
    /// 所有日期键仍存在、关联仍唯一、完整性不变，只有日期键按月连续不再成立；不在 ALL 中，需显式指定
    Rekey,
}

pub const ALL: [Change; 10] = [
    Change::Append,
    Change::Backfill,
    Change::Correct,
    Change::AddColumn,
    Change::Status,
    Change::Revision,
    Change::Duplicate,
    Change::DimHistory,
    Change::LateKey,
    Change::Unit,
];

pub const NAMES: [&str; 10] = ["append", "backfill", "correct", "addcol", "status", "revision", "dupload", "dimhist", "latekey", "unit"];

/// fixture 的日期键按日编号（2000-01-01 为 1）：367 为 2001-01-01，732 为 2002-01-01。
const DUP_FROM: &str = "2002-06-01";
const DUP_TO: &str = "2002-09-30";
const UNIT_FROM: &str = "2002-07-01";

/// 日期键重编号：被换键的月份与新键相对原键的偏移（fixture 的日期键不超过 1096）。
const REKEY_MONTH: &str = "d_year = 2002 and d_moy = 2";
const REKEY_SHIFT: i64 = 10_000;

/// 备份副本场景中被更正的退货（2002 年起、小票号尾数为 3）。
const MIRROR_FIXED: &str = "sr_ticket_number % 10 = 3 and sr_returned_date_sk >= 732";

const RETURNS_COLS: &str = "sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, sr_return_tax, \
                            sr_fee, sr_net_loss, sr_status";

const SALES_COLS: &str = "ss_sold_date_sk, ss_item_sk, ss_ticket_number, ss_quantity, ss_sales_price, ss_ext_sales_price, \
                          ss_ext_discount_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit";

impl Change {
    pub fn parse(s: &str) -> Result<Change> {
        if s == "mirror" {
            return Ok(Change::Mirror);
        }
        if s == "rekey" {
            return Ok(Change::Rekey);
        }
        match NAMES.iter().position(|n| *n == s) {
            Some(i) => Ok(ALL[i]),
            None => bail!("未知场景：{s}（可选 {}）", NAMES.join(" / ")),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Change::Mirror => "mirror",
            Change::Rekey => "rekey",
            _ => NAMES[ALL.iter().position(|c| *c == self).unwrap_or(0)],
        }
    }

    /// 报告中的中文名称
    pub fn label(self) -> &'static str {
        match self {
            Change::Append => "正常追加",
            Change::Backfill => "迟到回填",
            Change::Correct => "原地更正",
            Change::AddColumn => "新增无关列",
            Change::Status => "状态流水（v2）",
            Change::Revision => "版本化更正",
            Change::Duplicate => "重复装载",
            Change::DimHistory => "维表拉链",
            Change::LateKey => "日期键格式变化",
            Change::Unit => "金额单位变化",
            Change::Mirror => "备份副本",
            Change::Rekey => "日期键重编号",
        }
    }

    /// 触及的有效性条件：正常（条件应继续成立）/ 粒度 / 连接放大 / 覆盖 / 未建模（守卫不覆盖，作为漏检边界）
    pub fn class(self) -> &'static str {
        match self {
            Change::Append | Change::Backfill | Change::Correct | Change::AddColumn => "正常",
            Change::Status | Change::Revision | Change::Duplicate | Change::Mirror => "粒度",
            Change::DimHistory => "连接放大",
            Change::LateKey => "覆盖",
            Change::Unit => "未建模",
            Change::Rekey => "优化前提",
        }
    }

    pub fn describe(self) -> &'static str {
        match self {
            Change::Append => "复制 2002-09 门店销售行并换新小票号；结构、粒度与关联约束不变",
            Change::Backfill => "为 (商品+小票) % 5 = 2 且小票号为偶数的销售补写退货；新键，每笔退货仍一行",
            Change::Correct => "2002 年小票号尾数为 3 的销售净支付额减 1（含税额与利润同步）；原地 UPDATE",
            Change::AddColumn => "store_returns 新增列 sr_reason（全空）；不改数据",
            Change::Status => "etl::apply_v2：2001-10-01 起的门店退货增加“申请”行，金额相同",
            Change::Revision => "2001 年起小票号尾数为 7 的销售：旧金额保留为 ss_is_current = 0 的行，当前行金额改为九折",
            Change::Duplicate => "2002-06-01 至 2002-09-30 的门店销售整批再装载一次（完全相同的行）",
            Change::DimHistory => "商品键能被 3 整除的商品增加一条旧版本行（i_is_current = 'N'，类别为旧类别）",
            Change::LateKey => "先按“正常追加”补录 2002-09 销售，再把这批行的日期键改为 yyyymmdd",
            Change::Unit => "2002-07-01 起门店销售的价格与金额列乘以 100",
            Change::Mirror => {
                "2002 年小票号尾数为 3 的退货金额更正减 1；另写入整份退货备份副本（sr_source = 'backup'），被更正的行在副本里仍是旧金额"
            }
            Change::Rekey => {
                "日期维度重装载：2002-02 的日期键加 10000（接在最大键之后），门店销售、门店退货与目录销售的日期键同步改指向新键"
            }
        }
    }

    /// 被写入的表；评测只重问读这些表的指标
    pub fn tables(self) -> &'static [&'static str] {
        match self {
            Change::Backfill | Change::AddColumn | Change::Status | Change::Mirror => &["store_returns"],
            Change::DimHistory => &["item"],
            Change::Rekey => &["date_dim", "store_sales", "store_returns", "catalog_sales"],
            _ => &["store_sales"],
        }
    }

    /// 改变业务事实的部分。返回写入行数。
    pub async fn apply_truth(self, db: &Db) -> Result<i64> {
        match self {
            Change::Append | Change::LateKey => apply_growth(db).await,
            Change::Backfill => {
                write(
                    db,
                    "store_returns",
                    "补录漏记的历史退货",
                    "insert into store_returns (sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, \
                     sr_return_tax, sr_fee, sr_net_loss) \
                     select least(1096, ss_sold_date_sk + 1 + ss_ticket_number % 30), ss_item_sk, ss_ticket_number, ss_quantity, a, \
                            round(a * 0.08, 2), f, round(a * 0.5 + f, 2) \
                     from store_sales cross join lateral (select round(ss_net_paid * (0.3 + (ss_ticket_number % 7) * 0.1), 2) as a, \
                                                                 (2 + ss_ticket_number % 5)::numeric(12,2) as f) x \
                     where ss_sold_date_sk is not null and (ss_item_sk + ss_ticket_number) % 5 = 2 and ss_ticket_number % 2 = 0",
                )
                .await
            }
            Change::Correct => {
                write(
                    db,
                    "store_sales",
                    "更正 2002 年部分销售金额",
                    "update store_sales set ss_net_paid = ss_net_paid - 1, ss_net_paid_inc_tax = ss_net_paid_inc_tax - 1.08, \
                     ss_net_profit = ss_net_profit - 1 where ss_ticket_number % 10 = 3 and ss_sold_date_sk >= 732",
                )
                .await
            }
            Change::Revision => {
                let n = write(
                    db,
                    "store_sales",
                    "更正改为追加新版本：保留旧版本行",
                    &format!(
                        "insert into store_sales ({SALES_COLS}, ss_is_current) select {SALES_COLS}, 0 from store_sales \
                         where ss_ticket_number % 10 = 7 and ss_sold_date_sk >= 367 and ss_is_current = 1"
                    ),
                )
                .await?;
                write(
                    db,
                    "store_sales",
                    "更正改为追加新版本：当前行改为更正后金额",
                    "update store_sales set ss_net_paid = round(ss_net_paid * 0.9, 2), \
                     ss_net_paid_inc_tax = round(ss_net_paid_inc_tax * 0.9, 2), \
                     ss_net_profit = ss_net_profit - ss_net_paid + round(ss_net_paid * 0.9, 2) \
                     where ss_ticket_number % 10 = 7 and ss_sold_date_sk >= 367 and ss_is_current = 1",
                )
                .await?;
                Ok(n)
            }
            Change::Mirror => {
                write(
                    db,
                    "store_returns",
                    "更正 2002 年部分退货金额",
                    "update store_returns set sr_return_amt = sr_return_amt - 1 \
                     where sr_ticket_number % 10 = 3 and sr_returned_date_sk >= 732",
                )
                .await
            }
            Change::AddColumn | Change::Status | Change::Duplicate | Change::DimHistory | Change::Unit | Change::Rekey => Ok(0),
        }
    }

    /// 只改变数据表示、不改变业务事实的部分。返回写入行数。
    pub async fn apply_hidden(self, db: &Db) -> Result<i64> {
        match self {
            Change::AddColumn => {
                db.query(
                    QKind::Meta,
                    "alter table store_returns add column sr_reason varchar(20); \
                     comment on column store_returns.sr_reason is '退货原因（新接入，暂未填写）'",
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
                write(
                    db,
                    "item",
                    "商品维表改为保留历史版本",
                    "insert into item (i_item_sk, i_category, i_current_price, i_is_current) \
                     select i_item_sk, (array['家居','服装','电子','食品','运动'])[1 + (i_item_sk + 1) % 5], i_current_price, 'N' \
                     from item where i_item_sk % 3 = 0 and i_is_current = 'Y'",
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
                         where s.ss_sold_date_sk = d.d_date_sk and s.ss_ticket_number > {GROWTH_OFFSET}"
                    ),
                )
                .await
            }
            Change::Unit => {
                write(
                    db,
                    "store_sales",
                    "金额改以分记录",
                    &format!(
                        "update store_sales s set ss_sales_price = ss_sales_price * 100, ss_ext_sales_price = ss_ext_sales_price * 100, \
                         ss_ext_discount_amt = ss_ext_discount_amt * 100, ss_net_paid = ss_net_paid * 100, \
                         ss_net_paid_inc_tax = ss_net_paid_inc_tax * 100, ss_net_profit = ss_net_profit * 100 \
                         from date_dim d where s.ss_sold_date_sk = d.d_date_sk and d.d_date >= date '{UNIT_FROM}'"
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
                write(
                    db,
                    "store_returns",
                    "写入退货备份副本",
                    &format!(
                        "insert into store_returns ({RETURNS_COLS}, sr_source) \
                         select sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, \
                                sr_return_amt + case when {MIRROR_FIXED} then 1 else 0 end, \
                                sr_return_tax, sr_fee, sr_net_loss, sr_status, 'backup' from store_returns where sr_source = 'primary'"
                    ),
                )
                .await
            }
            Change::Rekey => {
                // 先改事实表（按维度上的旧键），再改维度表；业务事实不变
                let mut n = 0;
                for (t, col) in
                    [("store_sales", "ss_sold_date_sk"), ("store_returns", "sr_returned_date_sk"), ("catalog_sales", "cs_sold_date_sk")]
                {
                    n += write(
                        db,
                        t,
                        "日期维度重装载：事实表改指向新日期键",
                        &format!(
                            "update {t} set {col} = {col} + {REKEY_SHIFT} \
                             where {col} in (select d_date_sk from date_dim where {REKEY_MONTH})"
                        ),
                    )
                    .await?;
                }
                n += write(
                    db,
                    "date_dim",
                    "日期维度重装载：换成新的代理键",
                    &format!("update date_dim set d_date_sk = d_date_sk + {REKEY_SHIFT} where {REKEY_MONTH}"),
                )
                .await?;
                Ok(n)
            }
            Change::Append | Change::Backfill | Change::Correct | Change::Revision => Ok(0),
        }
    }

    /// 回到 v1。
    pub async fn reset(self, db: &Db) -> Result<()> {
        match self {
            Change::Append | Change::LateKey => reset_growth(db).await,
            Change::Backfill => {
                write(db, "store_returns", "撤回补录的退货", "delete from store_returns where (sr_item_sk + sr_ticket_number) % 5 = 2")
                    .await?;
                Ok(())
            }
            Change::Correct => {
                write(
                    db,
                    "store_sales",
                    "撤回金额更正",
                    "update store_sales set ss_net_paid = ss_net_paid + 1, ss_net_paid_inc_tax = ss_net_paid_inc_tax + 1.08, \
                     ss_net_profit = ss_net_profit + 1 where ss_ticket_number % 10 = 3 and ss_sold_date_sk >= 732",
                )
                .await?;
                Ok(())
            }
            Change::AddColumn => {
                db.query(QKind::Meta, "alter table store_returns drop column if exists sr_reason").await?;
                Ok(())
            }
            Change::Status => etl::reset(db).await,
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
                Ok(())
            }
            Change::Duplicate => {
                // 重复行与原行完全相同，按物理位置保留一份
                write(
                    db,
                    "store_sales",
                    "撤回重复装载",
                    "delete from store_sales a using store_sales b \
                     where a.ss_ticket_number = b.ss_ticket_number and a.ss_item_sk = b.ss_item_sk and a.ctid > b.ctid",
                )
                .await?;
                Ok(())
            }
            Change::DimHistory => {
                write(db, "item", "撤回商品历史版本", "delete from item where i_is_current = 'N'").await?;
                Ok(())
            }
            Change::Mirror => {
                write(db, "store_returns", "删除退货备份副本", "delete from store_returns where sr_source = 'backup'").await?;
                db.query(QKind::Meta, "alter table store_returns drop column if exists sr_source").await?;
                write(
                    db,
                    "store_returns",
                    "撤回退货金额更正",
                    &format!("update store_returns set sr_return_amt = sr_return_amt + 1 where {MIRROR_FIXED}"),
                )
                .await?;
                Ok(())
            }
            Change::Rekey => {
                write(
                    db,
                    "date_dim",
                    "撤回日期维度重装载",
                    &format!("update date_dim set d_date_sk = d_date_sk - {REKEY_SHIFT} where d_date_sk > {REKEY_SHIFT}"),
                )
                .await?;
                for (t, col) in
                    [("store_sales", "ss_sold_date_sk"), ("store_returns", "sr_returned_date_sk"), ("catalog_sales", "cs_sold_date_sk")]
                {
                    write(
                        db,
                        t,
                        "撤回日期维度重装载",
                        &format!(
                            "update {t} set {col} = {col} - {REKEY_SHIFT} where {col} between {REKEY_SHIFT} + 1 and 2 * {REKEY_SHIFT}"
                        ),
                    )
                    .await?;
                }
                Ok(())
            }
            Change::Unit => {
                write(
                    db,
                    "store_sales",
                    "撤回金额单位变化",
                    &format!(
                        "update store_sales s set ss_sales_price = ss_sales_price / 100, ss_ext_sales_price = ss_ext_sales_price / 100, \
                         ss_ext_discount_amt = ss_ext_discount_amt / 100, ss_net_paid = ss_net_paid / 100, \
                         ss_net_paid_inc_tax = ss_net_paid_inc_tax / 100, ss_net_profit = ss_net_profit / 100 \
                         from date_dim d where s.ss_sold_date_sk = d.d_date_sk and d.d_date >= date '{UNIT_FROM}'"
                    ),
                )
                .await?;
                Ok(())
            }
        }
    }
}

/// 执行一条写入，记批次，刷新统计信息并等待 DML 计数上报（避免同一次变化被感知两次）。返回影响行数。
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

/// 场景需要 v1 里就存在的列（值恒定）：销售与商品的当前版本标志（商品主键改为商品键 + 标志）。
/// 在学习之前执行，Agent 在 v1 就能看到这些列。幂等。
pub async fn setup(db: &Db) -> Result<()> {
    db.query(
        QKind::Meta,
        "alter table store_sales add column if not exists ss_is_current smallint not null default 1; \
         comment on column store_sales.ss_is_current is '是否当前版本（1 = 当前版本）'; \
         alter table item add column if not exists i_is_current char(1) not null default 'Y'; \
         comment on column item.i_is_current is '是否当前版本（Y = 当前版本）'; \
         alter table item drop constraint if exists item_pkey; \
         alter table item add primary key (i_item_sk, i_is_current); \
         analyze store_sales; analyze item",
    )
    .await?;
    Ok(())
}

pub const TABLES: [&str; 5] = ["store_sales", "store_returns", "catalog_sales", "date_dim", "item"];

/// 逐表内容指纹：行数、按行文本哈希之和（与行序无关）、列清单。回滚后必须与 v1 相同。
pub async fn fingerprint(db: &Db) -> Result<BTreeMap<String, String>> {
    let versions = catalog::versions(db).await?;
    let mut out = BTreeMap::new();
    for t in TABLES {
        let r = db.query(QKind::Meta, &format!("select count(*), coalesce(sum(hashtext(x::text)::bigint), 0) from {t} x")).await?;
        let cols = versions.get(t).map(|v| v.schema.clone()).unwrap_or_default();
        out.insert(t.to_string(), format!("{}|{}|{cols}", r.cell(0, 0).unwrap_or("?"), r.cell(0, 1).unwrap_or("?")));
    }
    Ok(out)
}

/// 核对当前内容与 `v1` 相同；不同则报出差异的表。
pub async fn ensure_v1(db: &Db, v1: &BTreeMap<String, String>, after: &str) -> Result<()> {
    let now = fingerprint(db).await?;
    let diff: Vec<&String> = v1.keys().filter(|t| now.get(*t) != v1.get(*t)).collect();
    ensure!(diff.is_empty(), "{after} 后数据未回到 v1：{diff:?}");
    Ok(())
}

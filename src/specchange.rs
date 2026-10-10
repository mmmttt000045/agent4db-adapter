//! 由模式描述驱动的数据变化（配对回放 `--spec`）：与 `scenario::Change` 同一套分类、同一批名字，施加在任意模式上。
//! 模式描述（exp/2026-10-11-generality/schemas/*.json）只给出事实表的粒度、日期列、可偏移的键与金额列，维表的键与
//! 描述属性，日历（日期维度或日期列），以及每种变化作用的表；写入的 SQL 全部由这些字段生成，不含某个模式特有的列名。
//! 每种变化仍分 `apply_truth`（改变业务事实）与 `apply_hidden`（只改变表示）两步，评测在两步之间计算标准答案。
//!
//! 变化需要的区分列由 `setup` 在初始快照里加好（取值恒为当前、完成），与 TPC-DS 上 `etl::setup`、`scenario::setup`
//! 的做法相同：状态流水的目标表加 row_status，更正保留旧行的目标表加 is_current，拉链维表加 is_current 并把主键改为
//! (键, is_current)；备份副本的来源列 source_system 在变化中才加。

use crate::db::{Db, QKind};
use crate::knowledge::Metric;
use crate::scenario::Change;
use crate::tpcds::{cols, write};
use anyhow::{anyhow, bail, ensure, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Calendar {
    /// 事实表上的 DATE / TIMESTAMP 列直接决定期间
    Column,
    /// 日期维度：事实表的日期键关联维度键
    Dim { table: String, key: String, date_col: String, year_col: String, month_col: String },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Years {
    pub learn: i32,
    pub holdout: i32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FactSpec {
    pub table: String,
    pub grain: Vec<String>,
    /// 日期列（日期列日历）或日期键列（日期维度日历）
    pub date: String,
    /// 可偏移出新业务事件的整数键列
    pub new_key: String,
    /// 金额列（numeric）
    pub money: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DimSpec {
    pub table: String,
    pub key: Vec<String>,
    pub attr: String,
    #[serde(default)]
    pub refs: Vec<(String, String)>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Spec {
    pub name: String,
    pub label: String,
    pub template_db: String,
    pub calendar: Calendar,
    pub years: Years,
    pub facts: Vec<FactSpec>,
    pub dims: Vec<DimSpec>,
    /// 变化名 → 作用的表
    pub changes: BTreeMap<String, String>,
}

/// 读入模式描述后的运行状态：各事实表初始快照里的最大新键（追加的事件键都大于它，回滚按它删除）。
pub struct Gen {
    pub spec: Spec,
    max_key: BTreeMap<String, i64>,
}

const STATUS_COL: &str = "row_status";
const CURRENT_COL: &str = "is_current";
const SOURCE_COL: &str = "source_system";
const NOTE_COL: &str = "note_text";

impl Spec {
    pub fn load(path: &str) -> Result<Spec> {
        let s: Spec = serde_json::from_str(&std::fs::read_to_string(path).with_context(|| format!("读取模式描述 {path}"))?)
            .with_context(|| format!("解析模式描述 {path}"))?;
        for (ch, t) in &s.changes {
            Change::parse(ch)?;
            ensure!(s.fact(t).is_some() || s.dim(t).is_some(), "变化 {ch} 的目标表 {t} 不在模式描述中");
        }
        if let Some(t) = s.changes.get("dimhist") {
            ensure!(s.dim(t).is_some(), "维表拉链的目标 {t} 必须是维表");
        }
        Ok(s)
    }

    pub fn fact(&self, t: &str) -> Option<&FactSpec> {
        self.facts.iter().find(|f| f.table == t)
    }

    pub fn dim(&self, t: &str) -> Option<&DimSpec> {
        self.dims.iter().find(|d| d.table == t)
    }

    /// 回滚核对的表：事实表、维表与日期维度。
    pub fn tables(&self) -> Vec<String> {
        let mut t: BTreeSet<String> = self.facts.iter().map(|f| f.table.clone()).collect();
        t.extend(self.dims.iter().map(|d| d.table.clone()));
        if let Calendar::Dim { table, .. } = &self.calendar {
            t.insert(table.clone());
        }
        t.into_iter().collect()
    }

    /// 变化作用的表（决定哪些定义要重答）。
    pub fn change_tables(&self, ch: Change) -> Vec<String> {
        self.changes.get(ch.name()).cloned().into_iter().collect()
    }

    /// 标准答案的区分列过滤：业务方知道的“当前、完成”口径，在初始快照上不起作用（与 TPC-DS 库的 `judge_metric` 相同）。
    pub fn judge_filters(&self) -> Vec<(String, String)> {
        let mut out = vec![];
        if let Some(t) = self.changes.get("status") {
            out.push((t.clone(), format!("{t}.{STATUS_COL} = 'done'")));
        }
        if let Some(t) = self.changes.get("revision") {
            out.push((t.clone(), format!("{t}.{CURRENT_COL} = 1")));
        }
        if let Some(t) = self.changes.get("dimhist") {
            out.push((t.clone(), format!("{t}.{CURRENT_COL} = 'Y'")));
        }
        out
    }

    pub fn judge_metric(&self, m: &Metric) -> Metric {
        let mut j = m.clone();
        let tables = m.tables();
        for (t, f) in self.judge_filters() {
            if tables.contains(&t) {
                let v = j.filters.entry(t).or_default();
                *v = if v.is_empty() { f } else { format!("({v}) and {f}") };
            }
        }
        j
    }

    /// dbt 式表级测试（配对回放的对照）：每张事实表的粒度唯一、每张维表的键唯一与非空、事实表到维表与日期维度的
    /// 参照完整性，全部由模式描述推出，与 TPC-DS 上手写的 `TABLE_TESTS` 同类。返回 (表, 测试名, SQL)。
    pub fn table_tests(&self) -> Vec<(String, String, String)> {
        let mut out = vec![];
        for f in &self.facts {
            let g = f.grain.join(", ");
            out.push((
                f.table.clone(),
                format!("unique({g})"),
                format!("select 1 from {} group by {g} having count(*) > 1 limit 1", f.table),
            ));
            if let Calendar::Column = &self.calendar {
                out.push((
                    f.table.clone(),
                    format!("not_null({})", f.date),
                    format!("select 1 from {} where {} is null limit 1", f.table, f.date),
                ));
            }
            if let Calendar::Dim { table, key, .. } = &self.calendar {
                out.push((
                    f.table.clone(),
                    format!("relationships({} -> {table}.{key})", f.date),
                    format!(
                        "select 1 from {t} s where s.{c} is not null and not exists (select 1 from {table} d where d.{key} = s.{c}) limit 1",
                        t = f.table,
                        c = f.date
                    ),
                ));
            }
        }
        for d in &self.dims {
            let k = d.key.join(", ");
            out.push((
                d.table.clone(),
                format!("unique({k})"),
                format!("select 1 from {} group by {k} having count(*) > 1 limit 1", d.table),
            ));
            out.push((
                d.table.clone(),
                format!("not_null({k})"),
                format!(
                    "select 1 from {} where {} limit 1",
                    d.table,
                    d.key.iter().map(|c| format!("{c} is null")).collect::<Vec<_>>().join(" or ")
                ),
            ));
            for (fact, col) in &d.refs {
                out.push((
                    fact.clone(),
                    format!("relationships({col} -> {}.{})", d.table, d.key[0]),
                    format!(
                        "select 1 from {fact} s where s.{col} is not null and not exists (select 1 from {t} d where d.{k} = s.{col}) limit 1",
                        t = d.table,
                        k = d.key[0]
                    ),
                ));
            }
        }
        if let Calendar::Dim { table, key, .. } = &self.calendar {
            out.push((
                table.clone(),
                format!("unique({key})"),
                format!("select 1 from {table} group by {key} having count(*) > 1 limit 1"),
            ));
        }
        out
    }

    /// 报告里的变化说明（作用的表与写入方式）。
    pub fn describe(&self, ch: Change) -> String {
        let t = self.changes.get(ch.name()).map(String::as_str).unwrap_or("?");
        let y = self.years.holdout;
        match ch {
            Change::Append => format!("{t}：复制 {y}-09 的行并偏移新键"),
            Change::Backfill => format!("{t}：补写 {}-06 的迟到事实（新键）", self.years.learn),
            Change::Correct => format!("{t}：{y} 年起部分行的金额原地减 1"),
            Change::AddColumn => format!("{t}：新增空列 {NOTE_COL}"),
            Change::Status => format!("{t}：{}-10 起每行追加一行 {STATUS_COL} = 'requested'，金额相同", y - 1),
            Change::Revision => format!("{t}：{} 年起部分行更正为 0.9 倍，旧行保留为 {CURRENT_COL} = 0", self.years.learn),
            Change::Duplicate => format!("{t}：{y}-06 至 {y}-09 的行整批重复装载"),
            Change::DimHistory => format!("{t}：三分之一的键追加 {CURRENT_COL} = 'N' 的旧版本行，描述属性不同"),
            Change::LateKey => format!("{t}：追加 {y}-09 的行，其日期键换用另一种格式（日期列日历：日期为空）"),
            Change::Unit => format!("{t}：{y}-07 起金额乘以 100"),
            Change::Mirror => format!("{t}：部分行金额更正后，追加一整份保留旧金额的备份副本（{SOURCE_COL} 标记）"),
            Change::Rekey => "不支持".into(),
        }
    }
}

fn day(y: i32, m: u32) -> String {
    format!("{y:04}-{m:02}-01")
}

impl Gen {
    /// 模板库复制出来之后的准备（幂等）：批次日志、区分列、拉链维表的主键、迟到键目标的日期列允许为空；记下各事实表的最大新键。
    pub async fn setup(db: &Db, spec: Spec) -> Result<Gen> {
        db.query(
            QKind::Meta,
            "create table if not exists etl_batch_log (table_name text, batch_id int, note text, applied_at timestamptz default now())",
        )
        .await?;
        if let Some(t) = spec.changes.get("status") {
            db.query(
                QKind::Meta,
                &format!(
                    "alter table {t} add column if not exists {STATUS_COL} varchar(12) not null default 'done'; \
                     comment on column {t}.{STATUS_COL} is '行状态：requested / done'"
                ),
            )
            .await?;
        }
        if let Some(t) = spec.changes.get("revision") {
            db.query(
                QKind::Meta,
                &format!(
                    "alter table {t} add column if not exists {CURRENT_COL} smallint not null default 1; \
                     comment on column {t}.{CURRENT_COL} is '是否当前版本（1 = 当前版本）'"
                ),
            )
            .await?;
        }
        if let Some(t) = spec.changes.get("dimhist") {
            let d = spec.dim(t).ok_or_else(|| anyhow!("维表 {t} 不在模式描述中"))?;
            db.query(
                QKind::Meta,
                &format!(
                    "alter table {t} add column if not exists {CURRENT_COL} char(1) not null default 'Y'; \
                     comment on column {t}.{CURRENT_COL} is '是否当前版本（Y = 当前版本）'"
                ),
            )
            .await?;
            let pk = db
                .query(QKind::Meta, &format!("select conname from pg_constraint where contype = 'p' and conrelid = '{t}'::regclass"))
                .await?;
            if let Some(name) = pk.cell(0, 0) {
                db.query(QKind::Meta, &format!("alter table {t} drop constraint {name}")).await?;
            }
            db.query(QKind::Meta, &format!("alter table {t} add primary key ({}, {CURRENT_COL})", d.key.join(", "))).await?;
        }
        if let (Some(t), Calendar::Column) = (spec.changes.get("latekey"), &spec.calendar) {
            let f = spec.fact(t).ok_or_else(|| anyhow!("迟到键的目标 {t} 必须是事实表"))?;
            db.query(QKind::Meta, &format!("alter table {t} alter column {} drop not null", f.date)).await?;
        }
        let mut max_key = BTreeMap::new();
        for f in &spec.facts {
            let n = db.query(QKind::Meta, &format!("select coalesce(max({}), 0)::bigint from {}", f.new_key, f.table)).await?;
            max_key.insert(f.table.clone(), n.i64(0, 0).unwrap_or(0));
        }
        for t in spec.tables() {
            db.query(QKind::Meta, &format!("analyze {t}")).await?;
        }
        Ok(Gen { spec, max_key })
    }

    fn target(&self, ch: Change) -> Result<&str> {
        self.spec.changes.get(ch.name()).map(String::as_str).ok_or_else(|| anyhow!("模式描述没有给出变化 {} 的目标表", ch.name()))
    }

    fn fact(&self, ch: Change) -> Result<&FactSpec> {
        let t = self.target(ch)?;
        self.spec.fact(t).ok_or_else(|| anyhow!("变化 {} 的目标 {t} 不是事实表", ch.name()))
    }

    /// 事实行的业务日期落在 [from, to) 内。
    fn dated(&self, f: &FactSpec, from: &str, to: &str) -> String {
        match &self.spec.calendar {
            Calendar::Column => format!("{c} >= date '{from}' and {c} < date '{to}'", c = f.date),
            Calendar::Dim { table, key, date_col, .. } => {
                format!("{} in (select {key} from {table} where {date_col} >= date '{from}' and {date_col} < date '{to}')", f.date)
            }
        }
    }

    fn since(&self, f: &FactSpec, from: &str) -> String {
        self.dated(f, from, "9999-01-01")
    }

    /// 被更正的行：新键尾数为 `digit`、业务日期不早于 `from`。
    fn subset(&self, f: &FactSpec, digit: i64, from: &str) -> String {
        format!("{} % 10 = {digit} and {}", f.new_key, self.since(f, from))
    }

    fn db_probe(&self, f: &FactSpec, max: i64) -> String {
        format!("select 1 from {} where {} > {max} limit 1", f.table, f.new_key)
    }

    /// 复制一个月的行并把新键偏移到初始最大键之上（新的业务事件）。
    async fn copy_month(&self, db: &Db, f: &FactSpec, y: i32, m: u32, note: &str) -> Result<i64> {
        if db.query(QKind::Meta, &self.db_probe(f, self.max_key[&f.table])).await?.cell(0, 0).is_some() {
            return Ok(0);
        }
        let c = cols(db, &f.table, &[]).await?;
        let off = self.max_key[&f.table] + 1;
        let sel: Vec<String> = c.iter().map(|x| if *x == f.new_key { format!("{x} + {off}") } else { x.clone() }).collect();
        let (y2, m2) = if m == 12 { (y + 1, 1) } else { (y, m + 1) };
        write(
            db,
            &f.table,
            note,
            &format!(
                "insert into {t} ({}) select {} from {t} where {}",
                c.join(", "),
                sel.join(", "),
                self.dated(f, &day(y, m), &day(y2, m2)),
                t = f.table
            ),
        )
        .await
    }

    async fn drop_growth(&self, db: &Db, f: &FactSpec) -> Result<()> {
        if db.query(QKind::Meta, &self.db_probe(f, self.max_key[&f.table])).await?.cell(0, 0).is_some() {
            write(db, &f.table, "撤回补录", &format!("delete from {} where {} > {}", f.table, f.new_key, self.max_key[&f.table])).await?;
            db.query(QKind::Meta, &format!("vacuum analyze {}", f.table)).await?;
        }
        Ok(())
    }

    fn money_set(f: &FactSpec, expr: &dyn Fn(&str) -> String) -> String {
        f.money.iter().map(|c| format!("{c} = {}", expr(c))).collect::<Vec<_>>().join(", ")
    }

    pub async fn apply_truth(&self, db: &Db, ch: Change) -> Result<i64> {
        let y = self.spec.years.holdout;
        match ch {
            Change::Append | Change::LateKey => {
                let f = self.fact(ch)?;
                self.copy_month(db, f, y, 9, &format!("补录 {y}-09 的事实")).await
            }
            Change::Backfill => {
                let f = self.fact(ch)?;
                self.copy_month(db, f, self.spec.years.learn, 6, "补写迟到的历史事实").await
            }
            Change::Correct => {
                let f = self.fact(ch)?;
                let set = Self::money_set(f, &|c| format!("{c} - 1"));
                write(db, &f.table, "原地更正部分金额", &format!("update {} set {set} where {}", f.table, self.subset(f, 3, &day(y, 1))))
                    .await
            }
            Change::Revision => {
                let f = self.fact(ch)?;
                let c = cols(db, &f.table, &[CURRENT_COL]).await?;
                let sub = self.subset(f, 7, &day(self.spec.years.learn, 1));
                let n = write(
                    db,
                    &f.table,
                    "更正改为追加新版本：保留旧版本行",
                    &format!(
                        "insert into {t} ({0}, {CURRENT_COL}) select {0}, 0 from {t} where {sub} and {CURRENT_COL} = 1",
                        c.join(", "),
                        t = f.table
                    ),
                )
                .await?;
                let set = Self::money_set(f, &|c| format!("round({c} * 0.9, 2)"));
                write(
                    db,
                    &f.table,
                    "更正改为追加新版本：当前行改为更正后金额",
                    &format!("update {} set {set} where {sub} and {CURRENT_COL} = 1", f.table),
                )
                .await?;
                Ok(n)
            }
            Change::Mirror => {
                let f = self.fact(ch)?;
                let set = Self::money_set(f, &|c| format!("{c} - 1"));
                write(db, &f.table, "更正部分金额", &format!("update {} set {set} where {}", f.table, self.subset(f, 3, &day(y, 1)))).await
            }
            Change::AddColumn | Change::Status | Change::Duplicate | Change::DimHistory | Change::Unit => Ok(0),
            Change::Rekey => bail!("模式描述驱动的变化不含日期键重编号"),
        }
    }

    pub async fn apply_hidden(&self, db: &Db, ch: Change) -> Result<i64> {
        let y = self.spec.years.holdout;
        match ch {
            Change::AddColumn => {
                let t = self.target(ch)?;
                db.query(
                    QKind::Meta,
                    &format!(
                        "alter table {t} add column {NOTE_COL} varchar(20); comment on column {t}.{NOTE_COL} is '备注（新接入，暂未填写）'"
                    ),
                )
                .await?;
                Ok(0)
            }
            Change::Status => {
                let f = self.fact(ch)?;
                let c = cols(db, &f.table, &[STATUS_COL]).await?;
                write(
                    db,
                    &f.table,
                    "改为状态流水（requested / done 各一行）",
                    &format!(
                        "insert into {t} ({0}, {STATUS_COL}) select {0}, 'requested' from {t} where {1} and {STATUS_COL} = 'done'",
                        c.join(", "),
                        self.since(f, &day(y - 1, 10)),
                        t = f.table
                    ),
                )
                .await
            }
            Change::Duplicate => {
                let f = self.fact(ch)?;
                write(
                    db,
                    &f.table,
                    &format!("{y}-06 至 {y}-09 批次重跑"),
                    &format!("insert into {t} select * from {t} where {}", self.dated(f, &day(y, 6), &day(y, 10)), t = f.table),
                )
                .await
            }
            Change::DimHistory => {
                let t = self.target(ch)?;
                let d = self.spec.dim(t).ok_or_else(|| anyhow!("{t} 不是维表"))?;
                let c = cols(db, t, &[CURRENT_COL]).await?;
                // 旧版本行的描述属性取另一个取值（最小值与最大值互换，其余改为最小值），与 TPC-DS 上 Books ↔ Music 的互换同类
                let a = &d.attr;
                let sel: Vec<String> = c
                    .iter()
                    .map(|x| {
                        if x == a {
                            format!("case when {a} = (select min({a}) from {t}) then (select max({a}) from {t}) else (select min({a}) from {t}) end")
                        } else {
                            x.clone()
                        }
                    })
                    .collect();
                write(
                    db,
                    t,
                    "维表改为保留历史版本",
                    &format!(
                        "insert into {t} ({}, {CURRENT_COL}) select {}, 'N' from {t} where {} % 3 = 0 and {CURRENT_COL} = 'Y'",
                        c.join(", "),
                        sel.join(", "),
                        d.key[0]
                    ),
                )
                .await
            }
            Change::LateKey => {
                let f = self.fact(ch)?;
                let max = self.max_key[&f.table];
                match &self.spec.calendar {
                    Calendar::Column => {
                        write(
                            db,
                            &f.table,
                            "补录批次的日期未能解析，写为空",
                            &format!("update {} set {} = null where {} > {max}", f.table, f.date, f.new_key),
                        )
                        .await
                    }
                    Calendar::Dim { table, key, date_col, .. } => {
                        // 换用另一种日期键格式：维度键是 yyyymmdd 时改用自 1970-01-01 起的天数，否则改用 yyyymmdd
                        let smart = db
                            .query(QKind::Meta, &format!("select bool_and({key} between 19000101 and 21001231) from {table}"))
                            .await?
                            .cell(0, 0)
                            == Some("t");
                        let other = if smart {
                            format!("(d.{date_col} - date '1970-01-01')")
                        } else {
                            format!("to_char(d.{date_col}, 'YYYYMMDD')::int")
                        };
                        write(
                            db,
                            &f.table,
                            "补录批次改用另一种日期键格式",
                            &format!(
                                "update {t} s set {c} = {other} from {table} d where s.{c} = d.{key} and s.{k} > {max}",
                                t = f.table,
                                c = f.date,
                                k = f.new_key
                            ),
                        )
                        .await
                    }
                }
            }
            Change::Unit => {
                let f = self.fact(ch)?;
                let set = Self::money_set(f, &|c| format!("{c} * 100"));
                write(db, &f.table, "金额改以分记录", &format!("update {} set {set} where {}", f.table, self.since(f, &day(y, 7)))).await
            }
            Change::Mirror => {
                let f = self.fact(ch)?;
                db.query(
                    QKind::Meta,
                    &format!(
                        "alter table {t} add column {SOURCE_COL} varchar(10) not null default 'primary'; \
                         comment on column {t}.{SOURCE_COL} is '来源系统标识'",
                        t = f.table
                    ),
                )
                .await?;
                let c = cols(db, &f.table, &[SOURCE_COL]).await?;
                let fixed = self.subset(f, 3, &day(y, 1));
                let sel: Vec<String> = c
                    .iter()
                    .map(|x| if f.money.contains(x) { format!("{x} + case when {fixed} then 1 else 0 end") } else { x.clone() })
                    .collect();
                write(
                    db,
                    &f.table,
                    "写入备份副本",
                    &format!(
                        "insert into {t} ({}, {SOURCE_COL}) select {}, 'backup' from {t} where {SOURCE_COL} = 'primary'",
                        c.join(", "),
                        sel.join(", "),
                        t = f.table
                    ),
                )
                .await
            }
            Change::Append | Change::Backfill | Change::Correct | Change::Revision => Ok(0),
            Change::Rekey => bail!("模式描述驱动的变化不含日期键重编号"),
        }
    }

    pub async fn reset(&self, db: &Db, ch: Change) -> Result<()> {
        let y = self.spec.years.holdout;
        match ch {
            Change::Append | Change::LateKey | Change::Backfill => {
                let f = self.fact(ch)?;
                self.drop_growth(db, f).await?;
            }
            Change::Correct => {
                let f = self.fact(ch)?;
                let set = Self::money_set(f, &|c| format!("{c} + 1"));
                write(db, &f.table, "撤回金额更正", &format!("update {} set {set} where {}", f.table, self.subset(f, 3, &day(y, 1))))
                    .await?;
            }
            Change::AddColumn => {
                let t = self.target(ch)?;
                db.query(QKind::Meta, &format!("alter table {t} drop column if exists {NOTE_COL}")).await?;
            }
            Change::Status => {
                let f = self.fact(ch)?;
                write(db, &f.table, "撤回状态流水", &format!("delete from {} where {STATUS_COL} = 'requested'", f.table)).await?;
                db.query(QKind::Meta, &format!("vacuum analyze {}", f.table)).await?;
            }
            Change::Revision => {
                let f = self.fact(ch)?;
                let set: Vec<String> = f.money.iter().map(|c| format!("{c} = o.{c}")).collect();
                let same: Vec<String> = f.grain.iter().map(|g| format!("c.{g} = o.{g}")).collect();
                write(
                    db,
                    &f.table,
                    "撤回版本化更正：恢复原金额",
                    &format!(
                        "update {t} c set {} from {t} o where o.{CURRENT_COL} = 0 and c.{CURRENT_COL} = 1 and {}",
                        set.join(", "),
                        same.join(" and "),
                        t = f.table
                    ),
                )
                .await?;
                write(db, &f.table, "撤回版本化更正：删除旧版本行", &format!("delete from {} where {CURRENT_COL} = 0", f.table)).await?;
                db.query(QKind::Meta, &format!("vacuum analyze {}", f.table)).await?;
            }
            Change::Duplicate => {
                let f = self.fact(ch)?;
                let same: Vec<String> = f.grain.iter().map(|g| format!("a.{g} = b.{g}")).collect();
                write(
                    db,
                    &f.table,
                    "撤回重复装载",
                    &format!("delete from {t} a using {t} b where {} and a.ctid > b.ctid", same.join(" and "), t = f.table),
                )
                .await?;
                db.query(QKind::Meta, &format!("vacuum analyze {}", f.table)).await?;
            }
            Change::DimHistory => {
                let t = self.target(ch)?;
                write(db, t, "撤回维表历史版本", &format!("delete from {t} where {CURRENT_COL} = 'N'")).await?;
            }
            Change::Unit => {
                let f = self.fact(ch)?;
                let set = Self::money_set(f, &|c| format!("{c} / 100"));
                write(db, &f.table, "撤回金额单位变化", &format!("update {} set {set} where {}", f.table, self.since(f, &day(y, 7))))
                    .await?;
            }
            Change::Mirror => {
                let f = self.fact(ch)?;
                write(db, &f.table, "删除备份副本", &format!("delete from {} where {SOURCE_COL} = 'backup'", f.table)).await?;
                db.query(QKind::Meta, &format!("alter table {} drop column if exists {SOURCE_COL}", f.table)).await?;
                let set = Self::money_set(f, &|c| format!("{c} + 1"));
                write(db, &f.table, "撤回金额更正", &format!("update {} set {set} where {}", f.table, self.subset(f, 3, &day(y, 1))))
                    .await?;
                db.query(QKind::Meta, &format!("vacuum analyze {}", f.table)).await?;
            }
            Change::Rekey => bail!("模式描述驱动的变化不含日期键重编号"),
        }
        Ok(())
    }

    /// 逐表内容指纹（与 `scenario::fingerprint` 相同的做法）：行数、按行文本哈希之和、列清单。回滚后必须与初始快照相同。
    pub async fn fingerprint(&self, db: &Db) -> Result<BTreeMap<String, String>> {
        let versions = crate::catalog::versions(db).await?;
        let mut out = BTreeMap::new();
        for t in self.spec.tables() {
            let r = db.query(QKind::Meta, &format!("select count(*), coalesce(sum(hashtext(x::text)::bigint), 0) from {t} x")).await?;
            let cols = versions.get(&t).map(|v| v.schema.clone()).unwrap_or_default();
            out.insert(t.clone(), format!("{}|{}|{cols}", r.cell(0, 0).unwrap_or("?"), r.cell(0, 1).unwrap_or("?")));
        }
        Ok(out)
    }

    pub async fn ensure_same(&self, db: &Db, v1: &BTreeMap<String, String>, after: &str) -> Result<()> {
        let now = self.fingerprint(db).await?;
        let diff: Vec<&String> = v1.keys().filter(|t| now.get(*t) != v1.get(*t)).collect();
        ensure!(diff.is_empty(), "{after} 后数据未回到初始快照：{diff:?}");
        Ok(())
    }

    pub fn report(&self) -> Value {
        json!({"spec": self.spec, "max_key": self.max_key})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn judge_filters_and_table_tests_follow_the_spec() {
        let s = Spec::load("exp/2026-10-11-generality/schemas/tpch.json").unwrap();
        let lib: Value = serde_json::from_str(&std::fs::read_to_string("exp/2026-10-11-generality/libs/tpch.json").unwrap()).unwrap();
        let joins_orders = lib["metric_report"]["entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| serde_json::from_value::<Metric>(e["metric"].clone()).unwrap())
            .find(|m| m.fact == "lineitem" && m.joins.iter().any(|j| j.right == "orders"))
            .expect("至少一个 lineitem 定义关联 orders");
        let j = s.judge_metric(&joins_orders);
        // 状态流水在 orders、更正保留旧行在 lineitem：两张表的区分列过滤都用表名限定
        assert!(j.filters["orders"].ends_with("orders.row_status = 'done'"), "{:?}", j.filters);
        assert!(j.filters["lineitem"].ends_with("lineitem.is_current = 1"), "{:?}", j.filters);
        assert!(!j.filters.contains_key("part") || joins_orders.tables().contains(&"part".to_string()));
        let tests = s.table_tests();
        assert!(tests.iter().any(|(t, n, _)| t == "lineitem" && n == "not_null(l_shipdate)"), "日期列日历要有非空测试");
        assert!(tests.iter().any(|(t, n, _)| t == "lineitem" && n == "relationships(l_partkey -> part.p_partkey)"));
        let ds = Spec::load("exp/2026-10-11-generality/schemas/tpcds.json").unwrap();
        assert!(ds.table_tests().iter().any(|(_, n, _)| n == "relationships(ss_sold_date_sk -> date_dim.d_date_sk)"));
        assert_eq!(ds.change_tables(Change::DimHistory), vec!["item".to_string()]);
    }
}

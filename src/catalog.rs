//! 系统目录：表、列、注释、统计信息，以及每张表的“版本指纹”（变更感知的依据）。

use crate::db::{Db, QKind};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};

/// 不对 Agent 暴露的内部表。
pub const INTERNAL_TABLES: &[&str] = &["etl_batch_log", "mavra_versions"];

/// 事务性表版本：语句级触发器在写入事务里把表的版本号加一，随写入一起提交，因此任一快照里读到的版本
/// 与该快照看到的数据一致（pg_stat 的 DML 计数不随事务提交、且异步上报，做不到这一点）。幂等。
pub async fn install_tx_versions(db: &Db, tables: &[&str]) -> Result<()> {
    let mut sql = String::from(
        "create table if not exists mavra_versions (table_name text primary key, v bigint not null default 0); \
         create or replace function mavra_bump() returns trigger language plpgsql as $$ \
         begin \
           insert into mavra_versions as m values (tg_table_name, 1) \
             on conflict (table_name) do update set v = m.v + 1; \
           return null; \
         end $$; ",
    );
    for t in tables {
        sql.push_str(&format!(
            "insert into mavra_versions values ('{t}', 0) on conflict do nothing; \
             drop trigger if exists mavra_bump on {t}; \
             create trigger mavra_bump after insert or update or delete or truncate on {t} \
               for each statement execute function mavra_bump(); "
        ));
    }
    db.query(QKind::Meta, &sql).await?;
    Ok(())
}

/// 当前快照里各表的事务性版本（`install_tx_versions` 之后）。
pub fn tx_versions(rows: &crate::db::Rows) -> HashMap<String, i64> {
    (0..rows.rows.len()).filter_map(|i| Some((rows.cell(i, 0)?.to_string(), rows.i64(i, 1)?))).collect()
}

#[derive(Clone, Debug, Serialize)]
pub struct Column {
    pub name: String,
    pub dtype: String,
    pub comment: Option<String>,
    /// pg_stats.n_distinct：>0 为绝对值，<0 为占行数的比例
    pub n_distinct: Option<f64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Table {
    pub name: String,
    pub comment: Option<String>,
    pub rows_est: f64,
    pub cols: Vec<Column>,
}

impl Table {
    pub fn col(&self, c: &str) -> Option<&Column> {
        self.cols.iter().find(|x| x.name == c)
    }
    /// 估计的不同值个数（绝对值）。
    pub fn distinct_est(&self, c: &str) -> f64 {
        match self.col(c).and_then(|x| x.n_distinct) {
            Some(d) if d < 0.0 => -d * self.rows_est,
            Some(d) => d,
            None => 0.0,
        }
    }
}

pub struct Catalog {
    pub tables: BTreeMap<String, Table>,
    col_table: HashMap<String, String>,
}

/// 表版本 = 结构指纹 + DML 计数 + ETL 批次号。任何一项变化都视为“依赖已变”。
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct TableVersion {
    pub schema: String,
    pub dml: i64,
    pub batch: i64,
    /// 列清单 `列:类型,…`（结构指纹的原文），用于只比较口径引用的列；不写入报告与 find_metric 返回
    #[serde(default, skip_serializing)]
    pub cols: String,
}

impl TableVersion {
    /// 某列的 `列:类型`；列不存在时为 None。
    pub fn col_sig(&self, col: &str) -> Option<&str> {
        self.cols.split(',').find(|x| x.split_once(':').is_some_and(|(n, _)| n == col))
    }
}

impl Catalog {
    /// 工具输入只能引用目录中实际存在的列，不能作为 SQL 片段直接拼接。
    pub fn validate_join(&self, left: &str, right: &str, on: &crate::checks::On) -> Result<()> {
        anyhow::ensure!(left != right, "暂不支持自关联");
        anyhow::ensure!(!on.is_empty(), "关联列 on 不能为空");
        let a = self.table(left).ok_or_else(|| anyhow::anyhow!("表不存在：{left}"))?;
        let b = self.table(right).ok_or_else(|| anyhow::anyhow!("表不存在：{right}"))?;
        let mut seen = std::collections::BTreeSet::new();
        for (l, r) in on {
            anyhow::ensure!(a.col(l).is_some(), "列不存在：{left}.{l}");
            anyhow::ensure!(b.col(r).is_some(), "列不存在：{right}.{r}");
            anyhow::ensure!(seen.insert((l, r)), "关联列重复：{l} = {r}");
        }
        Ok(())
    }

    pub async fn load(db: &Db) -> Result<Catalog> {
        let cols = db
            .query(
                QKind::Meta,
                "select c.relname, a.attname, format_type(a.atttypid, a.atttypmod), \
                        col_description(c.oid, a.attnum), obj_description(c.oid, 'pg_class'), c.reltuples \
                 from pg_class c join pg_namespace n on n.oid = c.relnamespace \
                 join pg_attribute a on a.attrelid = c.oid \
                 where n.nspname = 'public' and c.relkind = 'r' and a.attnum > 0 and not a.attisdropped \
                 order by c.relname, a.attnum",
            )
            .await?;
        let stats = db.query(QKind::Meta, "select tablename, attname, n_distinct from pg_stats where schemaname = 'public'").await?;
        let mut nd: HashMap<(String, String), f64> = HashMap::new();
        for i in 0..stats.rows.len() {
            if let (Some(t), Some(c), Some(v)) = (stats.cell(i, 0), stats.cell(i, 1), stats.f64(i, 2)) {
                nd.insert((t.to_string(), c.to_string()), v);
            }
        }
        let mut tables: BTreeMap<String, Table> = BTreeMap::new();
        let mut col_table = HashMap::new();
        for i in 0..cols.rows.len() {
            let t = cols.cell(i, 0).unwrap_or_default().to_string();
            if INTERNAL_TABLES.contains(&t.as_str()) {
                continue;
            }
            let c = cols.cell(i, 1).unwrap_or_default().to_string();
            let entry = tables.entry(t.clone()).or_insert_with(|| Table {
                name: t.clone(),
                comment: cols.cell(i, 4).map(str::to_string),
                rows_est: cols.f64(i, 5).unwrap_or(0.0).max(0.0),
                cols: vec![],
            });
            entry.cols.push(Column {
                name: c.clone(),
                dtype: cols.cell(i, 2).unwrap_or_default().to_string(),
                comment: cols.cell(i, 3).map(str::to_string),
                n_distinct: nd.get(&(t.clone(), c.clone())).copied(),
            });
            col_table.insert(c, t);
        }
        Ok(Catalog { tables, col_table })
    }

    pub fn table(&self, t: &str) -> Option<&Table> {
        self.tables.get(t)
    }

    /// TPC-DS 的列名全局唯一（带表前缀），所以可以由列名反查表。
    pub fn table_of(&self, col: &str) -> Option<&str> {
        self.col_table.get(col).map(String::as_str)
    }

    #[cfg(test)]
    pub fn from_tables(tables: Vec<Table>) -> Catalog {
        let col_table = tables.iter().flat_map(|t| t.cols.iter().map(|c| (c.name.clone(), t.name.clone()))).collect();
        Catalog { tables: tables.into_iter().map(|t| (t.name.clone(), t)).collect(), col_table }
    }

    pub fn rows(&self, t: &str) -> f64 {
        self.table(t).map(|x| x.rows_est).unwrap_or(0.0)
    }

    /// 两表之间“名字对得上”的候选关联列：去掉表前缀后相同，或一方是另一方的后缀
    /// （如 ss_sold_date_sk ↔ d_date_sk）。返回 (a 的列, b 的列, 是否完全同名)。
    pub fn match_pairs(&self, a: &str, b: &str) -> Vec<(String, String, bool)> {
        let (Some(ta), Some(tb)) = (self.table(a), self.table(b)) else { return vec![] };
        let mut out = vec![];
        for ca in ta.cols.iter().filter(|c| id_like(&c.name)) {
            for cb in tb.cols.iter().filter(|c| id_like(&c.name)) {
                let (sa, sb) = (strip_prefix(&ca.name), strip_prefix(&cb.name));
                let exact = sa == sb;
                if exact || sa.ends_with(&format!("_{sb}")) || sb.ends_with(&format!("_{sa}")) {
                    out.push((ca.name.clone(), cb.name.clone(), exact));
                }
            }
        }
        out
    }
}

fn id_like(c: &str) -> bool {
    c.ends_with("_sk") || c.ends_with("_number") || c.ends_with("_id")
}

fn strip_prefix(c: &str) -> &str {
    c.split_once('_').map(|(_, r)| r).unwrap_or(c)
}

/// 一次查询取回所有表的版本指纹。
pub async fn versions(db: &Db) -> Result<HashMap<String, TableVersion>> {
    let rows = db
        .query(
            QKind::Meta,
            "select c.relname, \
                    coalesce(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0), \
                    coalesce((select max(b.batch_id) from etl_batch_log b where b.table_name = c.relname), 0), \
                    md5(x.cols), x.cols \
             from pg_class c join pg_namespace n on n.oid = c.relnamespace \
             left join pg_stat_user_tables s on s.relid = c.oid \
             cross join lateral (select coalesce(string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod), ',' order by a.attnum), '') as cols \
                                 from pg_attribute a where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped) x \
             where n.nspname = 'public' and c.relkind = 'r'",
        )
        .await?;
    let mut out = HashMap::new();
    for i in 0..rows.rows.len() {
        let t = rows.cell(i, 0).unwrap_or_default().to_string();
        out.insert(
            t,
            TableVersion {
                dml: rows.i64(i, 1).unwrap_or(0),
                batch: rows.i64(i, 2).unwrap_or(0),
                schema: rows.cell(i, 3).unwrap_or_default().to_string(),
                cols: rows.cell(i, 4).unwrap_or_default().to_string(),
            },
        );
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn join_input_must_reference_real_columns() {
        let tables = ["left", "right"]
            .into_iter()
            .map(|name| {
                (
                    name.into(),
                    Table {
                        name: name.into(),
                        comment: None,
                        rows_est: 1.0,
                        cols: vec![Column { name: "id".into(), dtype: "integer".into(), comment: None, n_distinct: None }],
                    },
                )
            })
            .collect();
        let cat = Catalog { tables, col_table: HashMap::new() };
        let valid = vec![("id".into(), "id".into())];
        assert!(cat.validate_join("left", "right", &valid).is_ok());
        assert!(cat.validate_join("left", "right", &vec![]).is_err());
        assert!(cat.validate_join("left", "left", &valid).is_err());
        assert!(cat.validate_join("left", "missing", &valid).is_err());
        assert!(cat.validate_join("left", "right", &vec![valid[0].clone(), valid[0].clone()]).is_err());
        for name in ["missing", "id); select 1; --"] {
            assert!(cat.validate_join("left", "right", &vec![(name.into(), "id".into())]).is_err());
        }
    }
}

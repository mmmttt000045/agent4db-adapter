//! 从 SQL 文本里抽取用到的表和等值关联谓词。
//! 第一版不做完整解析：依赖 TPC-DS 列名全局唯一（带表前缀），`列 = 列` 且两列属于不同表即视为关联。

use crate::catalog::Catalog;
use crate::checks::On;
use regex::Regex;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

fn eq_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)\b(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)\s*=\s*(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)\b").unwrap()
    })
}

fn word_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)\b[a-z_][a-z0-9_]*\b").unwrap())
}

/// 去掉注释与字符串字面量，避免误匹配。
pub fn strip(sql: &str) -> String {
    let no_comments: String = sql.lines().map(|l| l.split("--").next().unwrap_or("")).collect::<Vec<_>>().join("\n");
    let re = Regex::new(r"'(?:[^']|'')*'").unwrap();
    re.replace_all(&no_comments, "''").to_lowercase()
}

pub fn tables(sql: &str, cat: &Catalog) -> BTreeSet<String> {
    let s = strip(sql);
    word_re().find_iter(&s).map(|m| m.as_str().to_string()).filter(|w| cat.table(w).is_some()).collect()
}

/// 一次关联：left.col = right.col（可多列）。
#[derive(Clone, Debug)]
pub struct JoinUse {
    pub left: String,
    pub right: String,
    pub on: On,
}

/// 按表对分组的关联。同一表对内若某列重复出现（如 date_dim 被两次以不同列关联），拆成多个关联。
pub fn joins(sql: &str, cat: &Catalog) -> Vec<JoinUse> {
    let s = strip(sql);
    let mut groups: BTreeMap<(String, String), Vec<(String, String)>> = BTreeMap::new();
    for cap in eq_re().captures_iter(&s) {
        let (a, b) = (cap[1].to_string(), cap[2].to_string());
        let (Some(ta), Some(tb)) = (cat.table_of(&a), cat.table_of(&b)) else { continue };
        if ta == tb {
            continue;
        }
        let (k, pair) = if ta < tb { ((ta.to_string(), tb.to_string()), (a, b)) } else { ((tb.to_string(), ta.to_string()), (b, a)) };
        let v = groups.entry(k).or_default();
        if !v.contains(&pair) {
            v.push(pair);
        }
    }
    let mut out = vec![];
    for ((t1, t2), preds) in groups {
        let mut seen_l = BTreeSet::new();
        let mut seen_r = BTreeSet::new();
        let repeated = preds.iter().any(|(l, r)| !seen_l.insert(l.clone()) || !seen_r.insert(r.clone()));
        if repeated {
            for p in preds {
                out.push(JoinUse { left: t1.clone(), right: t2.clone(), on: vec![p] });
            }
        } else {
            out.push(JoinUse { left: t1, right: t2, on: preds });
        }
    }
    out
}

/// 保守的结果缓存键：只去掉首尾空白，保留字面量、标识符和注释的原文。
/// 不压缩内部空白，也不转小写，否则不同的查询可能错误共享结果。
pub fn normalize(sql: &str) -> String {
    sql.trim().to_string()
}

/// 过滤条件是否出现在 SQL 中（忽略空白、大小写与表别名）。
pub fn contains_filter(sql: &str, filter: &str) -> bool {
    let squash = |x: &str| -> String {
        let re = Regex::new(r"(?i)\b[a-z_][a-z0-9_]*\.").unwrap();
        re.replace_all(&x.to_lowercase(), "").chars().filter(|c| !c.is_whitespace()).collect()
    };
    squash(sql).contains(&squash(filter))
}

#[cfg(test)]
mod tests {
    use super::normalize;

    #[test]
    fn cache_keys_preserve_sql_semantics() {
        for (a, b) in [
            ("select 'ABC'", "select 'abc'"),
            ("select 'a  b'", "select 'a b'"),
            ("select 1 as \"Name\"", "select 1 as \"name\""),
            ("select $$ABC$$", "select $$abc$$"),
            ("select 1 -- comment\n + 2", "select 1 -- comment + 2"),
        ] {
            assert_ne!(normalize(a), normalize(b));
        }
        assert_eq!(normalize("  select 1\n"), normalize("select 1"));
    }
}

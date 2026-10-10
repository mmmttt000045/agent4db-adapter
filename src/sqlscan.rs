//! 从 SQL 文本里抽取用到的表和等值关联谓词。
//! 不做完整解析：`列 = 列` 且两列属于不同表即视为关联。列所属的表先按限定前缀（表名或 FROM / JOIN 中的别名）确定，
//! 没有前缀时按列名反查（只在列名唯一时成立，如 TPC-DS 带表前缀的列名）。

use crate::catalog::Catalog;
use crate::checks::On;
use regex::Regex;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

fn eq_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)\b(?:([a-z_][a-z0-9_]*)\.)?([a-z_][a-z0-9_]*)\s*=\s*(?:([a-z_][a-z0-9_]*)\.)?([a-z_][a-z0-9_]*)\b").unwrap()
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

/// 表达式中的标识符（小写，已去掉注释与字符串字面量）。
pub fn words(expr: &str) -> Vec<String> {
    word_re().find_iter(&strip(expr)).map(|m| m.as_str().to_string()).collect()
}

/// 一次关联：left.col = right.col（可多列）。
#[derive(Clone, Debug)]
pub struct JoinUse {
    pub left: String,
    pub right: String,
    pub on: On,
}

/// 按表对分组的关联。同一表对内若某列重复出现（如 date_dim 被两次以不同列关联），拆成多个关联。
/// FROM / JOIN 中的表别名（别名 → 表名），表名本身也映射到自己。
fn aliases(s: &str, cat: &Catalog) -> BTreeMap<String, String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"(?i)\b(?:from|join)\s+([a-z_][a-z0-9_]*)(?:\s+(?:as\s+)?([a-z_][a-z0-9_]*))?").unwrap());
    const NOT_ALIAS: &[&str] = &[
        "where", "on", "join", "left", "right", "inner", "outer", "full", "cross", "group", "order", "limit", "using", "natural", "union",
    ];
    let mut out = BTreeMap::new();
    for c in re.captures_iter(s) {
        let t = c[1].to_string();
        if cat.table(&t).is_none() {
            continue;
        }
        if let Some(a) = c.get(2).map(|m| m.as_str().to_string()).filter(|a| !NOT_ALIAS.contains(&a.as_str())) {
            out.insert(a, t.clone());
        }
        out.insert(t.clone(), t);
    }
    out
}

/// 列所属的表：前缀是表名或别名时按它确定，否则（无前缀，或前缀是子查询、CTE 的名字）按唯一的列名反查。
fn owner<'a>(prefix: Option<&str>, col: &str, alias: &'a BTreeMap<String, String>, cat: &'a Catalog) -> Option<&'a str> {
    match prefix.and_then(|p| alias.get(p)) {
        Some(t) => cat.owners(col).iter().any(|o| o == t).then_some(t.as_str()),
        None => cat.table_of(col),
    }
}

pub fn joins(sql: &str, cat: &Catalog) -> Vec<JoinUse> {
    let s = strip(sql);
    let alias = aliases(&s, cat);
    let mut groups: BTreeMap<(String, String), Vec<(String, String)>> = BTreeMap::new();
    for cap in eq_re().captures_iter(&s) {
        let (a, b) = (cap[2].to_string(), cap[4].to_string());
        let ta = owner(cap.get(1).map(|m| m.as_str()), &a, &alias, cat);
        let tb = owner(cap.get(3).map(|m| m.as_str()), &b, &alias, cat);
        let (Some(ta), Some(tb)) = (ta, tb) else { continue };
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

/// 保守的表达式身份：忽略未引用标识符大小写及 token 间空白，保留字符串与引用标识符原文。
/// 遇到转义字符串、美元引用或注释时退回精确文本，宁可少复用也不合并不同值。
pub fn expression_key(expr: &str) -> String {
    if expr.contains(['$', '\\']) || expr.contains("--") || expr.contains("/*") {
        return format!("raw:{}", expr.trim());
    }
    static TOKENS: OnceLock<Regex> = OnceLock::new();
    let tokens = TOKENS.get_or_init(|| {
        Regex::new(
            r#"'(?:[^']|'')*'|"(?:[^"]|"")*"|[a-zA-Z_][a-zA-Z_0-9]*|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[~!@#%^&|+*/<>=:\-]+|[^\s]"#,
        )
        .unwrap()
    });
    let mut key: Vec<String> = vec![];
    for m in tokens.find_iter(expr) {
        let t = m.as_str();
        let operator = t.chars().all(|c| "~!@#%^&|+*/<>=:-".contains(c));
        if (operator && !["=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", "%", "^", "||", "::"].contains(&t))
            || t == "'"
            || t == "\""
            || (t.starts_with('\'') && key.last().is_some_and(|s| ["e", "b", "x", "u", "n"].contains(&s.as_str())))
        {
            return format!("raw:{}", expr.trim());
        }
        key.push(if t.starts_with(['\'', '"']) { t.to_string() } else { t.to_ascii_lowercase() });
    }
    format!("tokens:{}", key.join(" "))
}

/// 过滤条件是否出现在 SQL 中（忽略空白、大小写与表别名）。
pub fn contains_filter(sql: &str, filter: &str) -> bool {
    let squash = |x: &str| -> String {
        let re = Regex::new(r"(?i)\b[a-z_][a-z0-9_]*\.").unwrap();
        re.replace_all(&x.to_lowercase(), "").chars().filter(|c| !c.is_whitespace()).collect()
    };
    squash(sql).contains(&squash(filter))
}

/// 逐键查看的查询不会跨同键的多行汇总：没有聚合，或只有一层 SELECT 且 GROUP BY 含全部键列
/// （例如查看状态流水里哪些键有重复行）。嵌套查询一律不算，避免“内层按键求和、外层再求和”。
pub fn per_key(sql: &str, key: &[String]) -> bool {
    let s = strip(sql);
    let agg = Regex::new(r"\b(sum|count|avg|min|max|string_agg|array_agg|bool_and|bool_or)\s*\(").unwrap();
    let group = Regex::new(r"\bgroup\s+by\b").unwrap();
    if !agg.is_match(&s) && !group.is_match(&s) {
        return true;
    }
    if Regex::new(r"\bselect\b").unwrap().find_iter(&s).count() != 1 {
        return false;
    }
    let Some(m) = group.find(&s) else { return false };
    let rest = &s[m.end()..];
    let end = Regex::new(r"\b(having|order\s+by|limit|offset|window)\b").unwrap().find(rest).map_or(rest.len(), |x| x.start());
    let cols = words(&rest[..end]);
    !key.is_empty() && key.iter().all(|k| cols.contains(&k.to_lowercase()))
}

#[cfg(test)]
mod tests {
    use super::{expression_key, normalize, per_key};

    #[test]
    fn expression_identity_preserves_literal_values_and_token_boundaries() {
        assert_eq!(expression_key("S = '完成'"), expression_key("s='完成'"));
        assert_ne!(expression_key("s='ABC'"), expression_key("s='abc'"));
        assert_ne!(expression_key("s='A B'"), expression_key("s='AB'"));
        assert_ne!(expression_key("s='A.B'"), expression_key("s='B'"));
        assert_ne!(expression_key("s='O''Neil'"), expression_key("s='O''neil'"));
        assert_ne!(expression_key("\"S\"=1"), expression_key("\"s\"=1"));
        assert_ne!(expression_key("a b"), expression_key("ab"));
        assert_ne!(expression_key("x>=1"), expression_key("x > = 1"));
        assert_ne!(expression_key("a +- b"), expression_key("a + - b"));
        assert_ne!(expression_key("x=B'0'"), expression_key("x=b '0'"));
        assert_ne!(expression_key("x=E'\\\\ABC'"), expression_key("x=E'\\\\abc'"));
        assert_ne!(expression_key("x=$tag$ABC$tag$"), expression_key("x=$tag$abc$tag$"));
    }

    #[test]
    fn per_key_queries_do_not_sum_across_duplicates() {
        let key = vec!["sr_ticket_number".to_string(), "sr_item_sk".to_string()];
        let dup = "SELECT sr_ticket_number, sr_item_sk, count(*), count(DISTINCT sr_status) FROM store_returns \
                   GROUP BY sr_ticket_number, sr.sr_item_sk HAVING count(*) > 1 ORDER BY 3 DESC LIMIT 10";
        assert!(per_key(dup, &key));
        assert!(per_key("select * from store_returns limit 5", &key));
        assert!(!per_key("select sum(sr_return_amt) from store_returns", &key));
        assert!(!per_key("select sr_ticket_number, sum(sr_return_amt) from store_returns group by sr_ticket_number", &key));
        assert!(!per_key(
            "select sum(a) from (select sr_ticket_number, sr_item_sk, sum(sr_return_amt) a from store_returns \
             group by sr_ticket_number, sr_item_sk) x",
            &key
        ));
    }

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

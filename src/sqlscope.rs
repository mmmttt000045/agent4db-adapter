//! Query-local cardinality evidence. Never promotes a filtered proof to a base-table fact.
//! Unsupported scopes retain the original conservative admission decision.

use crate::catalog::Catalog;
use crate::sqlscan::JoinUse;
use sqlparser::ast::{
    BinaryOperator, Expr, Ident, JoinConstraint, JoinOperator, Query, Select, SelectItem, SetExpr, Statement, TableFactor, Visit, Visitor,
};
use sqlparser::dialect::PostgreSqlDialect;
use sqlparser::parser::Parser;
use std::collections::{BTreeMap, BTreeSet};
use std::ops::ControlFlow;

#[derive(Clone, Debug, PartialEq, Eq)]
struct Origin {
    table: String,
    column: String,
}

type Columns = BTreeMap<String, Option<Origin>>;

#[derive(Clone, Debug)]
struct Relation {
    factor: String,
    columns: Columns,
}

type Bindings = BTreeMap<String, Relation>;
type Ctes = BTreeMap<String, Columns>;

struct Traversal {
    semi: bool,
    depth: usize,
}

type JoinGroup = (String, String, String, String, bool);
type JoinColumns = (String, String, String, String);

#[derive(Debug)]
struct Claim {
    left: String,
    right: String,
    on: Vec<(String, String)>,
    probes: Vec<String>,
}

#[derive(Default, Debug)]
pub struct Analysis {
    complete: bool,
    claims: Vec<Claim>,
}

fn ident(s: &str) -> String {
    format!("\"{}\"", s.replace('"', "\"\""))
}
fn binding(id: &Ident) -> String {
    if id.quote_style.is_some() {
        id.value.clone()
    } else {
        id.value.to_ascii_lowercase()
    }
}

fn col(expr: &Expr, local: &Bindings, outer: &Bindings) -> Option<(String, String, Origin, bool)> {
    let expr = match expr {
        Expr::Nested(e) => e.as_ref(),
        e => e,
    };
    match expr {
        Expr::CompoundIdentifier(ids) if ids.len() == 2 => {
            let (alias, c) = (binding(&ids[0]), binding(&ids[1]));
            let (rel, outside) = local.get(&alias).map(|r| (r, false)).or_else(|| outer.get(&alias).map(|r| (r, true)))?;
            Some((alias, c.clone(), rel.columns.get(&c)?.clone()?, outside))
        }
        Expr::Identifier(id) => {
            let name = binding(id);
            for (bindings, outside) in [(local, false), (outer, true)] {
                let found: Vec<_> = bindings
                    .iter()
                    .filter_map(|(a, r)| r.columns.get(&name).and_then(Clone::clone).map(|o| (a.clone(), name.clone(), o, outside)))
                    .collect();
                if found.len() == 1 {
                    return found.into_iter().next();
                }
                if found.len() > 1 {
                    return None;
                }
            }
            None
        }
        _ => None,
    }
}

fn conjuncts(expr: &Expr) -> Vec<&Expr> {
    match expr {
        Expr::Nested(e) => conjuncts(e),
        Expr::BinaryOp { left, op: BinaryOperator::And, right } => {
            let mut out = conjuncts(left);
            out.extend(conjuncts(right));
            out
        }
        e => vec![e],
    }
}

struct References<'a> {
    local: &'a Bindings,
    outer: &'a Bindings,
    aliases: BTreeSet<String>,
    unknown: bool,
}
impl Visitor for References<'_> {
    type Break = ();
    fn pre_visit_query(&mut self, _: &Query) -> ControlFlow<()> {
        self.unknown = true;
        ControlFlow::Continue(())
    }
    fn pre_visit_expr(&mut self, expr: &Expr) -> ControlFlow<()> {
        if matches!(expr, Expr::Identifier(_) | Expr::CompoundIdentifier(_)) {
            match col(expr, self.local, self.outer) {
                Some((a, _, _, false)) => {
                    self.aliases.insert(a);
                }
                _ => self.unknown = true,
            }
        }
        ControlFlow::Continue(())
    }
}

#[derive(Default)]
struct Subqueries {
    depth: usize,
    roots: Vec<(Query, bool)>,
}
impl Visitor for Subqueries {
    type Break = ();
    fn pre_visit_query(&mut self, _: &Query) -> ControlFlow<()> {
        self.depth += 1;
        ControlFlow::Continue(())
    }
    fn post_visit_query(&mut self, _: &Query) -> ControlFlow<()> {
        self.depth -= 1;
        ControlFlow::Continue(())
    }
    fn pre_visit_expr(&mut self, expr: &Expr) -> ControlFlow<()> {
        if self.depth == 0 {
            match expr {
                Expr::Exists { subquery, .. } => self.roots.push((subquery.as_ref().clone(), true)),
                // Scalar subqueries have at most one output value per outer row
                // (PostgreSQL errors otherwise); IN is a membership predicate.
                Expr::Subquery(q) | Expr::InSubquery { subquery: q, .. } => self.roots.push((q.as_ref().clone(), true)),
                _ => (),
            }
        }
        ControlFlow::Continue(())
    }
}

impl Analysis {
    pub fn new(sql: &str, cat: &Catalog) -> Self {
        let mut out = Self { complete: true, claims: vec![] };
        match Parser::parse_sql(&PostgreSqlDialect {}, sql) {
            Ok(statements) if statements.len() == 1 => match &statements[0] {
                Statement::Query(q) => {
                    out.query(q, cat, &Ctes::new(), &[], &Bindings::new(), Traversal { semi: false, depth: 0 });
                }
                _ => out.complete = false,
            },
            _ => out.complete = false,
        }
        out
    }

    /// Every occurrence of the base-table/key pair must have query-local evidence.
    /// Empty probe sets mean a correlated EXISTS, which cannot multiply its outer rows.
    pub fn probes_for(&self, join: &JoinUse) -> Option<Vec<String>> {
        if !self.complete {
            return None;
        }
        let wanted: BTreeSet<_> = join.on.iter().cloned().collect();
        let matched: Vec<_> = self
            .claims
            .iter()
            .filter(|c| {
                if c.left == join.left && c.right == join.right {
                    c.on.iter().cloned().collect::<BTreeSet<_>>() == wanted
                } else if c.left == join.right && c.right == join.left {
                    c.on.iter().map(|(a, b)| (b.clone(), a.clone())).collect::<BTreeSet<_>>() == wanted
                } else {
                    false
                }
            })
            .collect();
        if matched.is_empty() {
            return None;
        }
        let mut probes = vec![];
        for claim in matched {
            if claim.probes.iter().any(String::is_empty) {
                return None;
            }
            probes.extend(claim.probes.clone());
        }
        // Legacy extraction does not model self joins. A local exemption must
        // not overlook multiplication introduced by another alias of that table.
        for claim in self.claims.iter().filter(|c| c.left == c.right) {
            if claim.probes.iter().any(String::is_empty) {
                return None;
            }
            probes.extend(claim.probes.clone());
        }
        probes.sort();
        probes.dedup();
        Some(probes)
    }

    fn query(&mut self, q: &Query, cat: &Catalog, inherited: &Ctes, prefix: &[String], outer: &Bindings, traversal: Traversal) -> Columns {
        let Traversal { semi, depth } = traversal;
        if depth > 16 {
            self.complete = false;
            return Columns::new();
        }
        let mut ctes = inherited.clone();
        let mut withs = prefix.to_vec();
        if let Some(with) = &q.with {
            if with.recursive {
                self.complete = false;
                return Columns::new();
            }
            for cte in &with.cte_tables {
                // Shadowing and positional column aliases require another binding layer.
                if ctes.contains_key(&binding(&cte.alias.name)) || !cte.alias.columns.is_empty() {
                    self.complete = false;
                    return Columns::new();
                }
                let columns = self.query(&cte.query, cat, &ctes, &withs, outer, Traversal { semi: false, depth: depth + 1 });
                ctes.insert(binding(&cte.alias.name), columns);
                withs.push(cte.to_string());
            }
        }
        match q.body.as_ref() {
            SetExpr::Select(select) => self.select(select, cat, &ctes, &withs, outer, Traversal { semi, depth }),
            SetExpr::Query(inner) => self.query(inner, cat, &ctes, &withs, outer, Traversal { semi, depth: depth + 1 }),
            _ => {
                self.complete = false;
                Columns::new()
            }
        }
    }

    fn relation(
        &mut self,
        factor: &TableFactor,
        cat: &Catalog,
        ctes: &Ctes,
        prefix: &[String],
        outer: &Bindings,
        depth: usize,
    ) -> Option<(String, Relation)> {
        match factor {
            TableFactor::Table { name, alias, args, .. } if args.is_none() => {
                let table = binding(name.0.last()?);
                if name.0.len() > 1 && binding(&name.0[name.0.len() - 2]) != "public" {
                    self.complete = false;
                    return None;
                }
                let columns = if let Some(c) = ctes.get(&table) {
                    c.clone()
                } else if let Some(t) = cat.table(&table) {
                    t.cols.iter().map(|c| (c.name.clone(), Some(Origin { table: table.clone(), column: c.name.clone() }))).collect()
                } else {
                    self.complete = false;
                    return None;
                };
                if alias.as_ref().is_some_and(|a| !a.columns.is_empty()) {
                    self.complete = false;
                    return None;
                }
                let alias_name = alias.as_ref().map_or(table, |a| binding(&a.name));
                Some((alias_name, Relation { factor: factor.to_string(), columns }))
            }
            TableFactor::Derived { lateral: false, subquery, alias: Some(alias) } if alias.columns.is_empty() => {
                let columns = self.query(subquery, cat, ctes, prefix, outer, Traversal { semi: false, depth: depth + 1 });
                Some((binding(&alias.name), Relation { factor: factor.to_string(), columns }))
            }
            _ => {
                self.complete = false;
                None
            }
        }
    }

    fn select(
        &mut self,
        select: &Select,
        cat: &Catalog,
        ctes: &Ctes,
        prefix: &[String],
        outer: &Bindings,
        traversal: Traversal,
    ) -> Columns {
        let Traversal { semi, depth } = traversal;
        let mut local = Bindings::new();
        let mut conditions = vec![];
        let mut on_filters = vec![];
        for from in &select.from {
            if let Some((a, r)) = self.relation(&from.relation, cat, ctes, prefix, outer, depth) {
                if local.insert(a, r).is_some() {
                    self.complete = false;
                }
            }
            for join in &from.joins {
                let mut right_alias = None;
                if let Some((a, r)) = self.relation(&join.relation, cat, ctes, prefix, outer, depth) {
                    right_alias = Some(a.clone());
                    if local.insert(a, r).is_some() {
                        self.complete = false;
                    }
                }
                match &join.join_operator {
                    JoinOperator::Inner(JoinConstraint::On(e)) => {
                        conditions.push(e);
                        on_filters.push((e, local.keys().cloned().collect::<BTreeSet<_>>()));
                    }
                    JoinOperator::LeftOuter(JoinConstraint::On(e)) => {
                        conditions.push(e);
                        // ON filters constrain only the non-preserved input.
                        on_filters.push((e, right_alias.into_iter().collect::<BTreeSet<_>>()));
                    }
                    JoinOperator::RightOuter(JoinConstraint::On(e)) | JoinOperator::FullOuter(JoinConstraint::On(e)) => conditions.push(e),
                    JoinOperator::CrossJoin => (),
                    _ => self.complete = false,
                }
            }
        }
        if let Some(where_) = &select.selection {
            conditions.push(where_);
        }
        let mut filters: BTreeMap<String, Vec<String>> = BTreeMap::new();
        let mut filter_sources = on_filters;
        if let Some(where_) = &select.selection {
            filter_sources.push((where_, local.keys().cloned().collect()));
        }
        for (condition, allowed) in filter_sources {
            for e in conjuncts(condition) {
                let mut refs = References { local: &local, outer, aliases: BTreeSet::new(), unknown: false };
                let _ = e.visit(&mut refs);
                if !refs.unknown && refs.aliases.len() == 1 {
                    let alias = refs.aliases.into_iter().next().unwrap();
                    if allowed.contains(&alias) {
                        filters.entry(alias).or_default().push(e.to_string());
                    }
                }
            }
        }
        let mut groups: BTreeMap<JoinGroup, Vec<JoinColumns>> = BTreeMap::new();
        for condition in &conditions {
            for e in conjuncts(condition) {
                match e {
                    Expr::BinaryOp { left, op: BinaryOperator::Eq, right } => match (col(left, &local, outer), col(right, &local, outer)) {
                        (Some((a, ac, ao, ax)), Some((b, bc, bo, bx))) if a != b => {
                            let semijoin = semi && ax != bx;
                            groups.entry((a, b, ao.table, bo.table, semijoin)).or_default().push((ac, bc, ao.column, bo.column));
                        }
                        (Some(_), Some(_)) => (),
                        _ if matches!(left.as_ref(), Expr::Identifier(_) | Expr::CompoundIdentifier(_))
                            && matches!(right.as_ref(), Expr::Identifier(_) | Expr::CompoundIdentifier(_)) =>
                        {
                            self.complete = false
                        }
                        _ => (),
                    },
                    // Do not combine disjunctive joins into a false composite key.
                    Expr::BinaryOp { op: BinaryOperator::Or, .. } => self.complete = false,
                    _ => (),
                }
            }
        }
        for ((a, b, left, right, is_semi), pairs) in groups {
            let probes = if is_semi {
                vec![]
            } else {
                [&a, &b]
                    .into_iter()
                    .enumerate()
                    .map(|(side, alias)| {
                        let Some(relation) = local.get(alias) else { return String::new() };
                        let cols: Vec<String> = pairs.iter().map(|p| if side == 0 { p.0.clone() } else { p.1.clone() }).collect();
                        uniqueness_query(prefix, alias, relation, &cols, filters.get(alias).map(Vec::as_slice).unwrap_or_default())
                    })
                    .collect()
            };
            self.claims.push(Claim { left, right, on: pairs.iter().map(|p| (p.2.clone(), p.3.clone())).collect(), probes });
        }
        let mut inherited_outer = outer.clone();
        inherited_outer.extend(local.clone());
        for e in conditions
            .into_iter()
            .chain(select.projection.iter().filter_map(|p| match p {
                SelectItem::UnnamedExpr(e) | SelectItem::ExprWithAlias { expr: e, .. } => Some(e),
                _ => None,
            }))
            .chain(select.having.iter())
        {
            let mut nested = Subqueries::default();
            let _ = e.visit(&mut nested);
            for (query, exists) in nested.roots {
                self.query(&query, cat, ctes, prefix, &inherited_outer, Traversal { semi: exists, depth: depth + 1 });
            }
        }
        let mut columns = Columns::new();
        for item in &select.projection {
            match item {
                SelectItem::UnnamedExpr(e) => {
                    if let Some((_, c, o, _)) = col(e, &local, outer) {
                        insert_column(&mut columns, c, Some(o));
                    }
                }
                SelectItem::ExprWithAlias { expr, alias } => {
                    insert_column(&mut columns, binding(alias), col(expr, &local, outer).map(|x| x.2))
                }
                SelectItem::Wildcard(_) => {
                    for r in local.values() {
                        for (c, o) in &r.columns {
                            insert_column(&mut columns, c.clone(), o.clone());
                        }
                    }
                }
                SelectItem::QualifiedWildcard(name, _) => {
                    if let Some(r) = name.0.last().and_then(|id| local.get(&binding(id))) {
                        for (c, o) in &r.columns {
                            insert_column(&mut columns, c.clone(), o.clone());
                        }
                    } else {
                        self.complete = false;
                    }
                }
            }
        }
        columns
    }
}

fn insert_column(columns: &mut Columns, name: String, origin: Option<Origin>) {
    columns.entry(name).and_modify(|value| *value = None).or_insert(origin);
}

fn uniqueness_query(prefix: &[String], alias: &str, relation: &Relation, cols: &[String], filters: &[String]) -> String {
    let with = if prefix.is_empty() { String::new() } else { format!("WITH {} ", prefix.join(", ")) };
    let projection: Vec<_> = cols.iter().enumerate().map(|(i, c)| format!("{}.{} AS __mavra_k{i}", ident(alias), ident(c))).collect();
    let keys: Vec<_> = (0..cols.len()).map(|i| format!("__mavra_k{i}")).collect();
    let not_null: Vec<_> = keys.iter().map(|k| format!("{k} IS NOT NULL")).collect();
    let filter = if filters.is_empty() {
        String::new()
    } else {
        format!(" WHERE {}", filters.iter().map(|f| format!("({f})")).collect::<Vec<_>>().join(" AND "))
    };
    let key = if keys.len() == 1 { keys[0].clone() } else { format!("({})", keys.join(", ")) };
    format!(
        "{with}SELECT count(*)::bigint, count(DISTINCT {key})::bigint FROM (SELECT {} FROM {}{filter}) AS __mavra_scope WHERE {}",
        projection.join(", "),
        relation.factor,
        not_null.join(" AND ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalog::{Column, Table};
    fn catalog() -> Catalog {
        Catalog::from_tables(
            [("sales", vec!["ticket", "paid"]), ("returns", vec!["rticket", "amount", "source"])]
                .into_iter()
                .map(|(name, cols)| Table {
                    name: name.into(),
                    comment: None,
                    rows_est: 10.,
                    cols: cols
                        .into_iter()
                        .map(|name| Column { name: name.into(), dtype: "integer".into(), comment: None, n_distinct: None })
                        .collect(),
                })
                .collect(),
        )
    }
    fn probes(sql: &str) -> Option<Vec<String>> {
        Analysis::new(sql, &catalog()).probes_for(&JoinUse {
            left: "sales".into(),
            right: "returns".into(),
            on: vec![("ticket".into(), "rticket".into())],
        })
    }
    #[test]
    fn scoped_proofs_keep_filters_and_preaggregation() {
        let p=probes("WITH r AS (SELECT rticket, sum(amount) amount FROM returns WHERE source='primary' GROUP BY rticket) SELECT sum(r.amount) FROM sales s LEFT JOIN r ON s.ticket=r.rticket").unwrap();
        assert_eq!(p.len(), 2);
        assert!(p.iter().all(|s| s.contains("GROUP BY rticket")));
        let p = probes("SELECT sum(r.amount) FROM sales s JOIN returns r ON s.ticket=r.rticket WHERE r.source='primary'").unwrap();
        assert!(p.iter().any(|s| s.contains("r.source = 'primary'")));
        let unfiltered = probes("SELECT sum(r.amount) FROM sales s JOIN returns r ON s.ticket=r.rticket").unwrap();
        assert!(unfiltered.iter().all(|s| !s.contains("primary")));
    }
    #[test]
    fn exists_is_not_a_multiplying_join_and_or_is_not_a_proof() {
        assert_eq!(
            probes("SELECT sum(s.paid) FROM sales s WHERE EXISTS (SELECT 1 FROM returns r WHERE r.rticket=s.ticket)").unwrap().len(),
            0
        );
        assert!(probes("SELECT * FROM sales s JOIN returns r ON s.ticket=r.rticket OR r.amount=s.paid").is_none());
        assert!(probes("SELECT * FROM sales s JOIN returns r ON s.ticket=r.rticket WHERE r.source='primary' OR true").is_none());
    }
    #[test]
    fn on_filters_only_restrict_the_non_preserved_input() {
        let p = probes("SELECT * FROM sales s LEFT JOIN returns r ON s.ticket=r.rticket AND r.source='primary' AND s.paid>10").unwrap();
        assert!(p.iter().any(|s| s.contains("r.source = 'primary'")));
        assert!(p.iter().all(|s| !s.contains("s.paid > 10")));
        assert!(probes("SELECT * FROM SALES AS S LEFT JOIN RETURNS AS R ON s.TICKET=r.RTICKET AND R.SOURCE='primary'").is_some());
    }
    #[test]
    fn self_joins_and_scalar_correlations_keep_all_local_evidence() {
        let p=probes("WITH p AS (SELECT * FROM returns WHERE source='primary'), b AS (SELECT * FROM returns WHERE source='backup') SELECT p.amount, (SELECT s.paid FROM sales s WHERE s.ticket=p.rticket LIMIT 1) FROM p JOIN b ON p.rticket=b.rticket").unwrap();
        assert!(p.iter().any(|s| s.contains("\"p\".\"rticket\"")));
        assert!(p.iter().any(|s| s.contains("\"b\".\"rticket\"")));
    }
}

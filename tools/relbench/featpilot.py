#!/usr/bin/env python3
"""FeatPilot (Liang et al., "FeatPilot: Automatic Feature Augmentation on Tabular Data", ICDE 2025) as a baseline on the
RelBench retraining timeline of exp/2026-10-20-relbench. No LLM. Every choice and change is listed in
exp/2026-10-20-relbench/reproduction-notes.md, section FeatPilot.

Per task and cutoff, from scratch (nothing is kept across tasks or cutoffs):
  base table = the seed table with the entity-table reference columns (Run.reference_sql, the entity row bounded by
  seed_time);
  join graph = RelBench's primary and foreign keys, both directions (child -> parent m:1, parent -> child 1:m);
  breadth-first search over join paths from the entity table (Algorithm 2): each hop joins one more table, no table
  twice; every table on a path that has a time column contributes only rows with time <= the seed's seed_time;
  a path reaching fewer than T_IQ of the training seeds is pruned with all its extensions (Pruning Principle 1);
  the columns of the table a path reaches are its candidate features (paths with a 1:m join: count of rows, mean/min/max
  of numeric and time columns, mean of booleans, count per value of categorical columns, mean text length; m:1 paths:
  the value, one indicator per categorical value, the text length); the entity's own categorical and text columns,
  which the reference leaves out, are candidates of the empty path;
  integration quality IQ = share of training seeds with a non-null feature value (Definition 8);
  feature importance FI = the utility the feature adds on the rows it augments (Definition 7 with Lemma 3), measured
  with the fixed LightGBM: the base table augmented with all candidates of one path is fitted on the seeds of 80% of
  the entities of the 50k training sample; FI(f) = the holdout utility (seeds of the other 20%, rows where f is not
  null) minus the utility with f's values permuted among those rows (permutation importance, as AutoGluon's
  feature_importance); FI <= 0 is pruned and a min-heap keeps the H pairs with the largest FI x IQ (Pruning
  Principle 2); only the H paths of a hop with the highest IQ are extended (the released code's beam);
  exploitation: up to B features chosen greedily by FI x IQ with FeatPilot's weight decay on similar features.
The chosen features and the reference columns form one feature SQL, scored once with Run.evaluate (validation and
test) and audited with Run.audit. Validation seeds are used only for the reported validation score.

Run on noctis (repo root):
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy PYTHONPATH=.pydeps-relbench \
  HF_HUB_OFFLINE=1 python3 tools/relbench/featpilot.py --data results/relbench-data/rel-stack \
      --prep results/relbench-data/rel-stack-prep --template relbench_stack_t1 --out results/relbench-pilot3/featpilot-rel-stack-r1
"""
import argparse
import collections
import concurrent.futures as cf
import heapq
import json
import os
import random
import re
import signal
import sys
import threading
import time
import traceback

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

# ───────────────────────── settings (reproduction notes) ─────────────────────────

T_IQ = 0.1  # IQ threshold of Pruning Principle 1 (the paper gives no value)
HEAP = 30  # heap size H: larger than the budget and a multiple of it (paper: "we set H to a multiple of B")
BUDGET = 10  # feature budget B: the paper's largest (1, 5, 10)
CAT_MAX_DISTINCT = 50  # text or integer columns with at most this many distinct values are categorical
ONEHOT_TOP = 10  # one-hot over the most common values of a categorical column
HOLDOUT = 0.2  # share of the training sample's entities held out for FI
SPLIT_SEED = 42
SIM_EPS = 0.5  # weight decay: chosen features at least this similar (|Spearman|) count as neighbours
MIN_TRAIN, MIN_HOLDOUT = 200, 50  # fewer augmented rows than this: FI not measurable (treated as no gain)
NUM_SHUFFLES = 3  # permutations per candidate for its FI
PATH_TIMEOUT_S = 300  # statement timeout of one path's candidate query on the training sample
# estimated seconds of the final SQL on the larger of the validation and test seed tables (the path query's time on the
# training sample, measured with SQL_WORKERS queries side by side, scaled by the seed count; 4x the real time in the test)
FINAL_COST_S = 400
SQL_WORKERS = 4  # path queries of one hop run side by side
NUMERIC = ("double precision", "real", "numeric")
INTEGER = ("bigint", "integer", "smallint")
TEXT = ("text", "character varying", "character")
ARM = "featpilot"


def lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def q(name):
    return '"' + name + '"'


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


class Graph:
    """Tables, keys, time columns and the kind of every column, from the manifest and the database's statistics."""

    def __init__(self, manifest, cols, stats):
        self.t = {}
        for name, spec in manifest["tables"].items():
            self.t[name.lower()] = {"pk": spec["pkey"].lower(), "tc": (spec.get("time_col") or "").lower() or None,
                                    "fk": {c.lower(): p.lower() for c, p in (spec.get("fkeys") or {}).items()}}
        st = {(r.tablename, r.attname): r for r in stats.itertuples()}
        self.cols = {n: [] for n in self.t}
        for r in cols.itertuples():
            if r.table_name not in self.t:
                continue
            k = self.kind(r.table_name, r.column_name, r.data_type, st.get((r.table_name, r.column_name)))
            if k:
                self.cols[r.table_name].append((r.column_name,) + k)

    def kind(self, table, col, dtype, s):
        spec = self.t[table]
        if col == spec["pk"] or col in spec["fk"]:
            return None
        if col == spec["tc"]:
            return ("time", None)
        if dtype == "boolean":
            return ("bool", None)
        if dtype.startswith("timestamp") or dtype == "date":
            return None  # only the declared time column is known to be dated at or before its row
        if s is None:
            return None  # no statistics: the column holds only nulls
        nd = s.n_distinct if s.n_distinct > 0 else -s.n_distinct * max(s.reltuples, 0)
        if dtype in INTEGER or dtype in TEXT:
            if 0 < nd <= CAT_MAX_DISTINCT and s.mcv:
                return ("cat", list(s.mcv)[:ONEHOT_TOP])
            if col.endswith("id"):
                return None  # identifiers that are not declared keys (e.g. accountid, revisionguid)
            return ("num", None) if dtype in INTEGER else ("text", None)
        if dtype in NUMERIC:
            return ("num", None)
        return None

    def neighbors(self, table):
        """Join steps from a table: (kind, from_table, from_col, to_table, to_col), joined as to.to_col = from.from_col."""
        out = [("m1", table, fk, parent, self.t[parent]["pk"]) for fk, parent in self.t[table]["fk"].items()]
        for child, spec in self.t.items():
            for fk, parent in spec["fk"].items():
                if parent == table:
                    out.append(("1m", table, self.t[table]["pk"], child, fk))
        return out

    def eccentricity(self, start):
        dist, frontier = {start: 0}, [start]
        while frontier:
            nxt = []
            for a in frontier:
                for st in self.neighbors(a):
                    if st[3] not in dist:
                        dist[st[3]] = dist[a] + 1
                        nxt.append(st[3])
            frontier = nxt
        return max(dist.values()), dist


def path_label(entity, steps):
    s = entity
    for kind, ft, fc, tt, tc in steps:
        s += f" -{fc}->{tt}" if kind == "m1" else f" -{tt}.{tc}->{tt}"
    return s


class Session:
    """FeatPilot for one task at one cutoff."""

    def __init__(self, run, c, t, k, seeds, graph):
        self.r, self.c, self.t, self.k, self.seeds, self.g = run, c, t, k, seeds, graph
        e = run.tasks[t]
        self.e = e
        self.ec, self.yc = e["entity_col"].lower(), e["target_col"].lower()
        self.et = e["entity_table"].lower()
        self.epk = graph.t[self.et]["pk"]
        self.tn = H.tname(t)
        self.task_type = e["task_type"]
        self.metric, self.higher = H.metric_of(self.task_type)
        self.tools, self.lock = [], threading.Lock()
        tr = seeds["train_sample"]
        self.keys = tr[[self.ec, "seed_time"]].copy()
        self.y = tr[self.yc].to_numpy()
        # holdout = the seeds of a random 20% of the entities: the released code splits the base table by its id column
        # (Dataset_splitter.new_map_split); a seed table repeats an entity at several seed times, and a random split of
        # seeds would credit features that identify the entity
        ents = np.sort(tr[self.ec].unique())
        perm = np.random.RandomState(SPLIT_SEED).permutation(len(ents))
        held = set(ents[perm[:int(round(HOLDOUT * len(ents)))]].tolist())
        self.ho = tr[self.ec].isin(held).to_numpy()
        self.tr = ~self.ho
        self.fi_trainings, self.fi_train_seconds = 0, 0.0
        self.paths = []  # dicts: steps, label, hop, lookup, iq, seconds, candidates, ...
        self.cands = {}  # name -> candidate
        self.vals = {}  # name -> values on the training sample (candidates kept in the heap)

    # ───────── SQL ─────────
    def sql(self, purpose, query, timeout_s=PATH_TIMEOUT_S):
        t0 = time.time()
        entry = {"name": "featpilot_sql", "category": "probe", "purpose": purpose}
        try:
            df, secs = H.read_sql(self.r.url, query, timeout_s=timeout_s)
            entry.update(seconds=secs, rows=len(df), error=False)
            return df, secs
        except Exception as err:
            entry.update(seconds=time.time() - t0, error=True, message=str(err).strip()[:300])
            raise
        finally:
            with self.lock:
                entry["i"] = len(self.tools)
                self.tools.append(entry)

    def body(self, steps, S, exprs, lookup, with_n):
        """The LATERAL subquery of one path for the seed alias S: every table with a time column bounded by S.seed_time."""
        g = self.g
        froms, wheres = [], []

        def bound(alias, table):
            tc = g.t[table]["tc"]
            if tc:
                wheres.append(f"{alias}.{q(tc)} <= {S}.seed_time")

        if not steps:
            froms.append(f"{q(self.et)} t0")
            wheres.append(f"t0.{q(self.epk)} = {S}.{q(self.ec)}")
            bound("t0", self.et)
        else:
            kind, ft, fc, tt, tc = steps[0]
            if kind == "1m":  # the child's key column equals the seed's entity key
                froms.append(f"{q(tt)} t1")
                wheres.append(f"t1.{q(tc)} = {S}.{q(self.ec)}")
            else:
                froms.append(f"{q(self.et)} t0")
                wheres.append(f"t0.{q(self.epk)} = {S}.{q(self.ec)}")
                bound("t0", self.et)
                froms.append(f"JOIN {q(tt)} t1 ON t1.{q(tc)} = t0.{q(fc)}")
            bound("t1", tt)
            for i, (kind, ft, fc, tt, tc) in enumerate(steps[1:], start=2):
                froms.append(f"JOIN {q(tt)} t{i} ON t{i}.{q(tc)} = t{i - 1}.{q(fc)}")
                bound(f"t{i}", tt)
        last = f"t{len(steps)}"
        sel = [f"{x.replace('§T§', last).replace('§S§', S)} AS {q(n)}" for n, x in exprs]
        if with_n:
            sel.insert(0, "1::double precision AS n" if lookup else "count(*)::double precision AS n")
        return f"SELECT {', '.join(sel)} FROM {' '.join(froms)} WHERE {' AND '.join(wheres)}" + (" LIMIT 1" if lookup else "")

    def candidates(self, table, lookup, hop0):
        """(agg, column, value, SQL expression) of the columns of the table a path reaches."""
        out = [] if lookup else [("count", None, None, "count(*)::double precision")]
        for col, kind, vals in self.g.cols[table]:
            if hop0 and kind not in ("cat", "text"):
                continue  # the reference already holds the entity's numeric, boolean and time columns
            c = f"§T§.{q(col)}"
            if kind == "num":
                if lookup:
                    out.append(("value", col, None, f"{c}::double precision"))
                else:
                    out += [(a, col, None, f"{a}({c}::double precision)::double precision") for a in ("avg", "min", "max")]
            elif kind == "time":
                d = f"(extract(epoch from (§S§.seed_time - {c})) / 86400.0)"
                if lookup:
                    out.append(("days", col, None, f"{d}::double precision"))
                else:
                    out += [(f"{a}_days", col, None, f"{a}{d}::double precision") for a in ("avg", "min", "max")]
            elif kind == "bool":
                out.append(("value", col, None, f"{c}::int::double precision") if lookup else
                           ("avg", col, None, f"avg({c}::int)::double precision"))
            elif kind == "cat":
                for v in vals:
                    cond = f"{c} = {lit(v)}"
                    out.append(("is", col, v, f"(CASE WHEN {cond} THEN 1.0 ELSE 0.0 END)") if lookup else
                               ("count", col, v, f"(count(*) FILTER (WHERE {cond}))::double precision"))
            elif kind == "text":
                out.append(("len", col, None, f"octet_length({c})::double precision") if lookup else
                           ("avg_len", col, None, f"avg(octet_length({c}))::double precision"))
        return out

    def base_sql(self):
        """The reference columns (Run.reference_sql) with the entity row bounded by seed_time, as every table on a path:
        the reference joins the entity row unbounded, and a seed whose entity row is dated after its seed_time then reads
        data after seed_time (the audit flagged accountid and days_since_creationdate on user-engagement)."""
        ref = self.r.reference_sql(self.t)
        tc = self.g.t[self.et]["tc"]
        tail = f"LEFT JOIN {self.et} e ON e.{self.epk} = s.{self.ec}"
        if not ref.endswith(tail):
            raise RuntimeError(f"unexpected reference SQL: {ref[-200:]}")
        return ref + (f" AND e.{tc} <= s.seed_time" if tc else "")

    # ───────── feature importance ─────────
    def us(self, y, p):
        s = H.score(self.task_type, y, p)
        return s if self.higher else -s

    def fit(self, x, y):
        """The study's fixed LightGBM (harness.train_predict's model), kept for repeated predictions."""
        import lightgbm as lgb

        if self.task_type == "binary_classification":
            m = lgb.LGBMClassifier(objective="binary", **H.LGB_PARAMS)
        else:
            m = lgb.LGBMRegressor(objective="l1", **H.LGB_PARAMS)
        m.fit(x, y)
        return m

    def predict(self, m, x):
        return m.predict_proba(x)[:, 1] if self.task_type == "binary_classification" else m.predict(x)

    def path_fi(self, names, vals):
        """FI of each candidate of one path: the base table augmented with all the path's candidates is fitted on the
        training entities; FI(f) = utility on the held-out rows that f augments minus the utility with f's values
        permuted among those rows (mean of NUM_SHUFFLES permutations)."""
        t0 = time.time()
        x = self.xb.copy()
        col = {}
        for j, n in enumerate(names):
            col[n] = f"fp_{j}"
            x[col[n]] = vals[n]
        m = self.fit(x.loc[self.tr], self.y[self.tr])
        self.fi_trainings += 1
        out = {}
        for j, n in enumerate(names):
            nn = ~np.isnan(vals[n])
            rows = self.ho & nn
            yh = self.y[rows]
            if (self.tr & nn).sum() < MIN_TRAIN or rows.sum() < MIN_HOLDOUT or (
                    self.task_type == "binary_classification" and len(np.unique(yh)) < 2):
                out[n] = None  # too few augmented rows to measure
                continue
            xh = x.loc[rows]
            s0 = self.us(yh, self.predict(m, xh))
            rng = np.random.RandomState(SPLIT_SEED + j)
            drops = []
            for _ in range(NUM_SHUFFLES):
                xp = xh.copy()
                xp[col[n]] = rng.permutation(xp[col[n]].to_numpy())
                drops.append(s0 - self.us(yh, self.predict(m, xp)))
            out[n] = float(np.mean(drops))
        self.fi_train_seconds += time.time() - t0
        return out

    # ───────── search ─────────
    def add_path(self, steps, hop):
        last = self.et if not steps else steps[-1][3]
        lookup = all(s[0] == "m1" for s in steps)
        pi = len(self.paths)
        tail = "_".join(slug(s[3]) for s in steps) or "self"
        cands = []
        for agg, col, val, expr in self.candidates(last, lookup, hop0=not steps):
            name = f"f{len(self.cands)}_{tail}_{agg}" + (f"_{slug(col)}" if col else "")
            if val is not None:
                name += f"_{slug(val)[:12]}"
            name = name[:63]
            self.cands[name] = {"name": name, "path": pi, "agg": agg, "col": col, "value": val, "expr": expr}
            cands.append(name)
        self.paths.append({"steps": steps, "label": path_label(self.et, steps), "hop": hop, "lookup": lookup,
                           "table": last, "candidates": cands})
        return pi

    def run_path(self, pi):
        """Candidate values of one path on the training sample; returns (values by name, path coverage)."""
        p = self.paths[pi]
        exprs = [(f"c{j}", self.cands[n]["expr"]) for j, n in enumerate(p["candidates"])]
        body = self.body(p["steps"], "s", exprs, p["lookup"], with_n=True)
        query = (f"SELECT s.{q(self.ec)}, s.seed_time, g.* FROM task.{self.tn}_train_sample s "
                 f"LEFT JOIN LATERAL ({body}) g ON true")
        df, secs = self.sql(f"path {p['label']}", query)
        df = df.rename(columns={df.columns[0]: self.ec})
        df["seed_time"] = pd.to_datetime(df["seed_time"])
        m = self.keys.merge(df, on=[self.ec, "seed_time"], how="left")
        if len(m) != len(self.keys):
            raise RuntimeError(f"path {p['label']}: {len(m)} rows for {len(self.keys)} seeds")
        n = pd.to_numeric(m["n"], errors="coerce").to_numpy(dtype=float)
        vals = {name: pd.to_numeric(m[f"c{j}"], errors="coerce").to_numpy(dtype=float) for j, name in enumerate(p["candidates"])}
        return vals, float(np.mean(np.nan_to_num(n) > 0)), secs

    def search(self):
        g, c = self.g, self.c
        ecc, dist = g.eccentricity(self.et)
        self.kmax = ecc if c.hops == "auto" else int(c.hops)
        self.hop_dist = dist
        ref = self.base_sql()
        t0 = time.time()
        self.xb, s = H.features(self.r.url, ref, f"task.{self.tn}_train_sample", self.seeds["train_sample"], self.ec)
        self.tools.append({"i": len(self.tools), "name": "featpilot_sql", "category": "probe", "purpose": "reference columns",
                           "seconds": s, "rows": len(self.xb), "error": False})
        self.xb = self.xb.reset_index(drop=True)
        p, _, _ = H.train_predict(self.task_type, self.xb.loc[self.tr], self.y[self.tr], self.xb.loc[self.ho])
        self.base_holdout = H.score(self.task_type, self.y[self.ho], p)
        heap, seq = [], 0  # (score, seq, name): min-heap of the H best (feature, path) pairs
        self.hops = []
        frontier = [()]
        for hop in range(0, self.kmax + 1):
            th = time.time()
            if hop == 0:
                todo = [self.add_path((), 0)]
            else:
                todo = []
                for steps in frontier:
                    last = self.et if not steps else steps[-1][3]
                    seen = {self.et} | {x[3] for x in steps}
                    for st in g.neighbors(last):
                        if st[3] in seen:
                            continue  # Algorithm 2: no cyclic joins
                        todo.append(self.add_path(steps + (st,), hop))
            if not todo:
                break
            results = {}
            with cf.ThreadPoolExecutor(min(SQL_WORKERS, len(todo))) as ex:
                futs = {ex.submit(self.run_path, pi): pi for pi in todo}
                for f in cf.as_completed(futs):
                    pi = futs[f]
                    try:
                        results[pi] = f.result()
                    except Exception as err:  # noqa: BLE001 - a path that fails or times out is pruned
                        self.paths[pi]["error"] = str(err).strip()[:300]
            sql_s = time.time() - th
            nxt, measured, inserted = [], 0, 0
            tf = time.time()
            for pi in todo:
                p = self.paths[pi]
                if pi not in results:
                    p["pruned"] = "error"
                    continue
                vals, iq_path, secs = results[pi]
                p.update(iq=iq_path, seconds=secs)
                if hop > 0 and iq_path < T_IQ:
                    p["pruned"] = "iq"  # Pruning Principle 1: the path and every extension of it
                    continue
                if hop > 0:
                    nxt.append((iq_path, pi))
                elig = []
                for name in p["candidates"]:
                    cand = self.cands[name]
                    cand["iq"] = float(np.mean(~np.isnan(vals[name])))
                    if cand["iq"] < T_IQ:
                        cand["pruned"] = "iq"
                    else:
                        elig.append(name)
                fis = self.path_fi(elig, vals) if elig else {}
                for name in elig:
                    v = vals[name]
                    cand = self.cands[name]
                    fi = fis[name]
                    measured += 1
                    cand["fi"] = fi
                    if fi is None or fi <= 0:
                        cand["pruned"] = "fi"  # Pruning Principle 2: no gain even with IQ = 1
                        continue
                    sc = fi * cand["iq"]
                    cand["score"] = sc
                    if len(heap) < HEAP:
                        heapq.heappush(heap, (sc, seq, name))
                        self.vals[name] = v
                        inserted += 1
                    elif sc > heap[0][0]:
                        _, _, out = heapq.heapreplace(heap, (sc, seq, name))
                        self.vals.pop(out, None)
                        self.cands[out]["pruned"] = "heap"
                        self.vals[name] = v
                        inserted += 1
                    else:
                        cand["pruned"] = "heap"
                    seq += 1
            # the released code extends only the K paths of this hop with the highest IQ (K = the heap size)
            nxt = sorted(nxt, key=lambda x: -x[0])
            for _, pi in nxt[HEAP:]:
                self.paths[pi]["pruned"] = "beam"
            nxt = [self.paths[pi]["steps"] for _, pi in nxt[:HEAP]]
            self.hops.append({"hop": hop, "paths": len(todo), "kept_paths": len(nxt) if hop else 1,
                              "pruned_iq": sum(1 for pi in todo if self.paths[pi].get("pruned") == "iq"),
                              "errors": sum(1 for pi in todo if self.paths[pi].get("pruned") == "error"),
                              "candidates": sum(len(self.paths[pi]["candidates"]) for pi in todo), "measured": measured,
                              "inserted": inserted, "sql_seconds": round(sql_s, 1), "fi_seconds": round(time.time() - tf, 1)})
            H.log(f"{self.t} k{self.k} hop {hop}: {self.hops[-1]}")
            frontier = nxt if hop > 0 else [()]
            if hop > 0 and not frontier:
                break
        self.heap = sorted(heap, reverse=True)
        chosen = self.exploit([n for _, _, n in self.heap])
        self.search_seconds = time.time() - t0
        return chosen

    def exploit(self, pool):
        """Greedy choice of up to B features by FI x IQ, with FeatPilot's weight decay on similar chosen features."""
        self.final_cost_estimate, self.cost_skipped = 0.0, []
        if not pool:
            self.decay = []
            return []
        vals = pd.DataFrame({n: self.vals[n] for n in pool})
        sim = vals.corr(method="spearman", min_periods=30).abs().fillna(0.0)
        scale = max(len(self.seeds["val"]), len(self.seeds["test"])) / len(self.seeds["train_sample"])
        chosen, paths_in, cost, self.decay, self.cost_skipped = [], set(), 0.0, [], []
        pool = list(pool)
        while len(chosen) < BUDGET and pool:
            best, best_sc, best_fi = None, 0.0, None
            for n in pool:
                cand = self.cands[n]
                nb = [sim.at[n, x] for x in chosen if sim.at[n, x] >= SIM_EPS]
                fi = cand["fi"] * (float(np.mean([1 - s for s in nb])) if nb else 1.0)
                sc = fi * cand["iq"]
                if best is None or sc > best_sc:
                    best, best_sc, best_fi = n, sc, fi
            if best is None or best_sc <= 0:
                break
            pool.remove(best)
            pi = self.cands[best]["path"]
            extra = 0.0 if pi in paths_in else (self.paths[pi].get("seconds") or 0.0) * scale
            if cost + extra > FINAL_COST_S:
                self.cands[best]["pruned"] = "cost"  # the final SQL would not run within the statement limit
                self.cost_skipped.append(best)
                continue
            cost += extra
            paths_in.add(pi)
            chosen.append(best)
            self.decay.append({"name": best, "fi": self.cands[best]["fi"], "fi_decayed": best_fi, "score": best_sc})
        self.final_cost_estimate = cost
        return chosen

    def final_sql(self, chosen):
        ref = self.base_sql()
        if not chosen:
            return ref
        groups = collections.OrderedDict()
        for n in chosen:
            groups.setdefault(self.cands[n]["path"], []).append(n)
        sel, joins = ["r.*"], []
        for j, (pi, names) in enumerate(groups.items(), start=1):
            p = self.paths[pi]
            body = self.body(p["steps"], "r", [(n, self.cands[n]["expr"]) for n in names], p["lookup"], with_n=False)
            joins.append(f"LEFT JOIN LATERAL ({body}) g{j} ON true")
            sel += [f"g{j}.{q(n)}" for n in names]
        return f"SELECT {', '.join(sel)} FROM ({ref}) r {' '.join(joins)}"


def session(run, c, graph_fn, t, k, seeds):
    e = run.tasks[t]
    metric, higher = H.metric_of(e["task_type"])
    rec = {"arm": ARM, "run": c.run, "task": t, "k": k, "agent": f"{H.tname(t)}-agent", "session": f"{ARM}-r{c.run}-{H.tname(t)}-k{k}",
           "metric": metric, "higher_is_better": higher, "target": None,
           "target_detail": {"val": None, "why": "FeatPilot keeps no goal"}, "goal_reached": None, "llm": [], "tools": [],
           "validations": [], "stop": ARM, "error": None, "learning": None}
    t_start = time.time()
    s = None
    try:
        graph, gtools = graph_fn()  # FeatPilot profiles the database afresh for every task and cutoff
        s = Session(run, c, t, k, seeds, graph)
        s.tools.extend(gtools)
        chosen = s.search()
        sql = s.final_sql(chosen)
        rec["agent_seconds"] = time.time() - t_start
        ev, dropped = None, []
        for attempt in range(4):
            try:
                ev = run.evaluate(t, k, sql, seeds)
                break
            except Exception as err:  # noqa: BLE001 - e.g. a statement timeout on the larger seed tables
                if not chosen or attempt == 3:
                    raise
                # drop the chosen path with the largest cost and score again (recorded)
                worst = max({s.cands[n]["path"] for n in chosen}, key=lambda pi: s.paths[pi].get("seconds") or 0)
                dropped.append({"path": s.paths[worst]["label"], "error": str(err)[:300]})
                chosen = [n for n in chosen if s.cands[n]["path"] != worst]
                sql = s.final_sql(chosen)
        rec["eval"] = ev
        ta = time.time()
        audit = run.audit(t, k, sql, seeds)
        rec["audit_seconds"] = time.time() - ta
        rec["audit"] = audit
        val_entry = {"tool_i": len(s.tools), "val": ev["val"], "improved": True, "sql_seconds": ev["sql_seconds"],
                     "train_seconds": ev["train_seconds"], "audit_seconds": rec["audit_seconds"], "leak": audit.get("result") == "leak",
                     "leaking_columns": audit.get("columns_differing"), "n_features": ev["n_features"], "sql": sql}
        rec["validations"].append(val_entry)
        s.tools.append({"i": len(s.tools), "name": "validate_features", "category": "validate", "purpose": "final feature SQL (Run.evaluate)",
                        "seconds": ev["sql_seconds"] + ev["train_seconds"], "sql_seconds": ev["sql_seconds"],
                        "train_seconds": ev["train_seconds"], "error": False})
        rec["final_sql"] = sql
        rec["final_source"] = ARM
        rec["best_val"] = ev["val"]
        rec["featpilot"] = {
            "hops_max": s.kmax, "table_hops": s.hop_dist, "base_holdout_score": s.base_holdout,
            "search_seconds": s.search_seconds, "fi_trainings": s.fi_trainings, "fi_train_seconds": s.fi_train_seconds,
            "hops": s.hops, "final_cost_estimate_s": s.final_cost_estimate, "evaluate_fallbacks": dropped,
            "paths": [{k2: p.get(k2) for k2 in ("label", "hop", "lookup", "iq", "seconds", "pruned", "error")} | {"candidates": len(p["candidates"])}
                      for p in s.paths],
            "heap": [{"name": n, "path": s.paths[s.cands[n]["path"]]["label"], "agg": s.cands[n]["agg"], "col": s.cands[n]["col"],
                      "value": s.cands[n]["value"], "fi": s.cands[n]["fi"], "iq": s.cands[n]["iq"], "score": sc} for sc, _, n in s.heap],
            "selected": s.decay, "chosen": chosen, "cost_skipped": s.cost_skipped,
        }
    except Exception as err:  # noqa: BLE001 - the session is saved with its error; the run goes on and is not "finished"
        rec["error"] = f"{type(err).__name__}: {str(err)[:1000]}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["stop"] = "error"
        rec.setdefault("agent_seconds", time.time() - t_start)
        H.log(f"{t} k{k}: ERROR {rec['error']}")
    tools = s.tools if s else []
    for i, x in enumerate(tools):
        x["i"] = i
    rec["tools"] = tools
    rec.setdefault("audit_seconds", 0.0)
    rec.setdefault("final_sql", None)
    rec.setdefault("final_source", None)
    rec.setdefault("best_val", None)
    rec.setdefault("eval", None)
    rec.setdefault("audit", None)
    by = {cat: sum(1 for x in tools if x.get("category") == cat) for cat in ("schema", "probe", "validate", "memory", "submit")}
    rec["totals"] = {
        "llm_calls": 0, "planner_llm_calls": 0, "tool_calls": len(tools), "tool_calls_by_category": by,
        "input_tokens": 0, "output_tokens": 0, "llm_seconds": 0, "llm_retry_seconds": 0,
        "tool_seconds": sum(x.get("seconds", 0) for x in tools),
        "validation_sql_seconds": sum(v.get("sql_seconds", 0) for v in rec["validations"]),
        "validation_train_seconds": sum(v.get("train_seconds", 0) for v in rec["validations"]),
        "tokens": 0, "learn_tokens": 0, "learn_seconds": 0, "tokens_with_learning": 0,
    }
    with open(os.path.join(c.out, "sessions", f"{H.tname(t)}-k{k}.json"), "w") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1, default=str)
    ev = rec.get("eval") or {}
    H.log(f"{t} k{k}: featpilot tools={rec['totals']['tool_calls']} t={rec['agent_seconds']:.0f}s val={rec['best_val']} "
          f"test={ev.get('test')} audit={(rec.get('audit') or {}).get('result')} features={len((rec.get('featpilot') or {}).get('chosen') or [])}")
    return rec


def main():
    global HEAP, BUDGET, T_IQ
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--prep", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--cutoffs", nargs="*")
    ap.add_argument("--hops", default="auto", help="largest number of joins on a path; auto = the entity table's eccentricity "
                    "in the join graph (every table of the database is a candidate table)")
    ap.add_argument("--beam", type=int, default=HEAP, help="heap size H (larger than the budget)")
    ap.add_argument("--budget", type=int, default=BUDGET, help="feature budget B")
    ap.add_argument("--tiq", type=float, default=T_IQ, help="IQ threshold T_IQ")
    ap.add_argument("--resume", action="store_true", help="keep finished sessions (no error, audit clean) found in --out")
    ap.add_argument("--keep-db", action="store_true")
    c = ap.parse_args()
    HEAP, BUDGET, T_IQ = c.beam, c.budget, c.tiq
    if HEAP <= BUDGET:
        ap.error("FeatPilot's heap is larger than the feature budget")
    os.makedirs(os.path.join(c.out, "sessions"), exist_ok=True)

    def stop(signum, frame):  # a stopped run still drops its database (finally below)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    a = argparse.Namespace(arm="none", run=c.run, data=c.data, prep=c.prep, template=c.template, out=c.out, tasks=c.tasks,
                           cutoffs=c.cutoffs, targets_from=None, reasoning_effort=None, eval_now=True, llm="deepseek")
    r = H.Run(a)  # its Llm is constructed but never called
    r.db_name = f"relbench_{ARM}_r{c.run}_{os.getpid()}"
    r.url = f"{H.base_url(r.url_admin)}/{r.db_name}"
    settings = {"T_IQ": T_IQ, "H": HEAP, "B": BUDGET, "hops": c.hops, "CAT_MAX_DISTINCT": CAT_MAX_DISTINCT, "ONEHOT_TOP": ONEHOT_TOP,
                "HOLDOUT": HOLDOUT, "SPLIT_SEED": SPLIT_SEED, "SIM_EPS": SIM_EPS, "MIN_TRAIN": MIN_TRAIN, "MIN_HOLDOUT": MIN_HOLDOUT,
                "NUM_SHUFFLES": NUM_SHUFFLES, "FI": "permutation importance per path model", "PATH_TIMEOUT_S": PATH_TIMEOUT_S, "FINAL_COST_S": FINAL_COST_S, "SQL_WORKERS": SQL_WORKERS,
                "SAMPLE_SIZE": H.SAMPLE_SIZE, "LGB_PARAMS": H.LGB_PARAMS, "llm": None}
    summary = {"arm": ARM, "run": c.run, "db": r.db_name, "template": c.template, "settings": settings, "cutoffs": []}
    done = set()
    if c.resume:
        for f in os.listdir(os.path.join(c.out, "sessions")):
            try:
                x = json.load(open(os.path.join(c.out, "sessions", f)))
            except (OSError, ValueError):
                continue
            if not x.get("error") and (x.get("eval") or {}).get("test") is not None and (x.get("audit") or {}).get("result") == "clean":
                done.add((x["task"], x["k"]))
    H.log(f"run {ARM} r{c.run}: database {r.db_name} from {c.template}; {len(done)} sessions kept")
    with open(os.path.join(c.out, "featpilot.pid"), "w") as f:
        f.write(str(os.getpid()))
    errors = 0
    H.create_run_db(r.url_admin, c.template, r.db_name)

    def graph_fn():
        tools = []
        out = []
        for purpose, query in (("columns", "SELECT table_name, column_name, data_type FROM information_schema.columns "
                                           "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"),
                               ("statistics", "SELECT s.tablename, s.attname, s.n_distinct, s.most_common_vals::text::text[] AS mcv, "
                                              "c.reltuples FROM pg_stats s JOIN pg_namespace n ON n.nspname = s.schemaname "
                                              "JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = s.tablename "
                                              "WHERE s.schemaname = 'public'")):
            df, secs = H.read_sql(r.url, query)
            tools.append({"i": len(tools), "name": "featpilot_sql", "category": "probe", "purpose": purpose, "seconds": secs,
                          "rows": len(df), "error": False})
            out.append(df)
        return Graph(r.manifest, out[0], out[1]), tools

    try:
        ks = range(1, r.timeline["K"] + 1) if not c.cutoffs else [int(x) for x in c.cutoffs]
        prev = None
        for k in ks:
            cut = next(iter(r.tasks.values()))["cutoffs"][k - 1]
            rec = {"k": k, "test_timestamp": cut["test_timestamp"]}
            if prev is not None:
                rec["append"] = r.append(pd.Timestamp(prev), pd.Timestamp(cut["test_timestamp"]))
                H.log(f"k{k}: appended {rec['append']['rows']}")
            elif k > 1:
                first = next(iter(r.tasks.values()))["cutoffs"][0]["test_timestamp"]
                rec["append"] = r.append(pd.Timestamp(first), pd.Timestamp(cut["test_timestamp"]))
            prev = cut["test_timestamp"]
            order = list(r.tasks)
            random.Random(c.run * 1000 + k).shuffle(order)  # the harness's arrival order of run 1
            rec["order"] = order
            if all((t, k) in done for t in order):
                old = {}
                try:
                    old = {x["k"]: x for x in json.load(open(os.path.join(c.out, "run.json"))).get("cutoffs", [])}
                except (OSError, ValueError):
                    pass
                if k in old and old[k].get("reference"):
                    rec["reference"] = old[k]["reference"]
                    summary["cutoffs"].append(rec)
                    H.log(f"k{k}: every session kept")
                    continue
            seeds = r.seed_tables(k)
            rec["reference"] = {}
            for t in r.tasks:
                try:
                    rec["reference"][t] = r.evaluate(t, k, r.reference_sql(t), seeds[t])
                except Exception as err:  # noqa: BLE001
                    rec["reference"][t] = {"error": str(err)[:300]}
            H.log(f"k{k}: reference {json.dumps({t: (v.get('val'), v.get('test')) for t, v in rec['reference'].items()})}")
            for t in order:
                if (t, k) in done:
                    continue
                out = session(r, c, graph_fn, t, k, seeds[t])
                errors += bool(out.get("error"))
            summary["cutoffs"].append(rec)
            with open(os.path.join(c.out, "run.json"), "w") as f:
                json.dump(summary, f, indent=1, default=str)
        if errors:
            summary["error"] = f"{errors} sessions failed; rerun with --resume"
        else:
            summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except BaseException:
        traceback.print_exc()
        summary["error"] = traceback.format_exc()[-2000:]
        raise
    finally:
        with open(os.path.join(c.out, "run.json"), "w") as f:
            json.dump(summary, f, indent=1, default=str)
        if not c.keep_db:
            H.drop_db(r.url_admin, r.db_name)
        H.log("run done")


if __name__ == "__main__":
    main()

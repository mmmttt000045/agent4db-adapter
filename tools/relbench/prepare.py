#!/usr/bin/env python3
"""Prepare a RelBench dataset for the retraining-timeline study (exp/2026-10-20-relbench/README.md).

Cutoff k = 1..K: val_k = val_timestamp - (K-k)*delta and test_k = test_timestamp - (K-k)*delta, where delta is the
task window. The train/val/test label tables come from RelBench's own Task._get_table with these timestamps (labels
from the task's SQL, dangling entities filtered against the database up to test_k), so k = K is the official split;
the script checks that the k = K tables equal the hosted official parquet files row by row and stops otherwise.

Outputs under --out:
  tasks/<task>/k<k>/{train,val,test}.parquet   labels for every cutoff (test labels never enter the database)
  timeline.json                                cutoffs, row counts, check results
and, with --pg, a PostgreSQL database holding every row with time <= test_1 (RelBench's Database.upto: rows whose
time column is null are dropped, as pandas' query drops NaT). Identifiers are lower-cased because PostgreSQL folds
unquoted names. Primary keys come from the manifest; foreign keys and time columns are recorded as column comments.

Run on noctis:  PYTHONPATH=.pydeps-relbench python3 tools/relbench/prepare.py --data results/relbench-data/rel-stack \
    --out results/relbench-data/rel-stack-prep --cutoffs 5 --pg "$AGENTDB_URL" --dbname relbench_stack_t1
"""
import argparse
import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Shifted:
    """The dataset with val/test timestamps moved back; everything else delegates to the real dataset."""

    def __init__(self, ds, val, test):
        self._ds, self.val_timestamp, self.test_timestamp = ds, val, test

    def __getattr__(self, name):
        return getattr(self._ds, name)


def cutoffs(ds, delta, k_total):
    return [(k, ds.val_timestamp - (k_total - k) * delta, ds.test_timestamp - (k_total - k) * delta) for k in range(1, k_total + 1)]


def same_rows(a, b, cols):
    a = a[cols].sort_values(cols[:2]).reset_index(drop=True)
    b = b[cols].sort_values(cols[:2]).reset_index(drop=True)
    if len(a) != len(b):
        return False, f"rows {len(a)} vs {len(b)}"
    for c in cols:
        x, y = a[c], b[c]
        if pd.api.types.is_float_dtype(x) or pd.api.types.is_float_dtype(y):
            ok = np.allclose(x.astype(float), y.astype(float), equal_nan=True)
        else:
            ok = (x.astype(str).values == y.astype(str).values).all()
        if not ok:
            return False, f"column {c} differs"
    return True, f"{len(a)} rows equal"


PG_TYPES = [
    (pd.api.types.is_bool_dtype, "boolean"),
    (pd.api.types.is_integer_dtype, "bigint"),
    (pd.api.types.is_float_dtype, "double precision"),
    (pd.api.types.is_datetime64_any_dtype, "timestamp"),
]


def pg_type(s):
    for test, t in PG_TYPES:
        if test(s.dtype):
            return t
    return "text"


def copy_frame(cur, table, df):
    """COPY a frame in CSV chunks; NUL bytes are not allowed in PostgreSQL text and are removed."""
    cols = ", ".join(c.lower() for c in df.columns)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
        for start in range(0, len(df), 200_000):
            part = df.iloc[start:start + 200_000].copy()
            for c in part.columns:
                if part[c].dtype == object:
                    part[c] = part[c].map(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)
                elif pd.api.types.is_integer_dtype(part[c].dtype) and str(part[c].dtype)[0] == "I":
                    part[c] = part[c].astype(object)
            buf = io.StringIO()
            part.to_csv(buf, index=False, header=False, na_rep="\\N", date_format="%Y-%m-%d %H:%M:%S.%f")
            cp.write(buf.getvalue())


def build_pg(url, dbname, ds, db, upto):
    import psycopg

    base = url.rsplit("/", 1)[0]
    with psycopg.connect(f"{base}/postgres", autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
        con.execute(f"CREATE DATABASE {dbname}")
    counts = {}
    with psycopg.connect(f"{base}/{dbname}", autocommit=True) as con:
        cur = con.cursor()
        for name, spec in ds.manifest.tables.items():
            t = db.table_dict[name]
            df = t.df
            dropped_null = 0
            if spec.time_col:
                keep = df[spec.time_col] <= upto
                dropped_null = int(df[spec.time_col].isna().sum())
                df = df[keep]
            tname = name.lower()
            cols = [f"{c.lower()} {pg_type(df[c])}" for c in df.columns]
            cur.execute(f"CREATE TABLE {tname} ({', '.join(cols)})")
            copy_frame(cur, tname, df)
            if spec.pkey:
                cur.execute(f"ALTER TABLE {tname} ADD PRIMARY KEY ({spec.pkey.lower()})")
            for fk, ref in dict(spec.fkeys).items():
                ref_pk = ds.manifest.tables[ref].pkey
                cur.execute(f"COMMENT ON COLUMN {tname}.{fk.lower()} IS 'foreign key to {ref.lower()}.{ref_pk.lower()}'")
            if spec.time_col:
                cur.execute(f"COMMENT ON COLUMN {tname}.{spec.time_col.lower()} IS 'time column of the row'")
            cur.execute(f"ANALYZE {tname}")
            counts[tname] = {"rows": len(df), "total_rows": len(t.df), "null_time_dropped": dropped_null}
            log(f"  {tname}: {len(df)} of {len(t.df)} rows (null time {dropped_null})")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="local RelBench dataset directory (manifest.yaml, db/, tasks/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cutoffs", type=int, required=True)
    ap.add_argument("--tasks", nargs="*", help="default: every entity classification/regression task in the folder")
    ap.add_argument("--pg", help="PostgreSQL URL (any database on the server); builds --dbname when given")
    ap.add_argument("--dbname")
    a = ap.parse_args()

    from relbench.load import load_dataset

    ds = load_dataset(a.data)
    names = a.tasks or ds.get_task_names()
    tasks = {}
    for n in names:
        t = ds.load_task(n)
        if t.task_type.value in ("binary_classification", "regression"):
            tasks[n] = t
    log(f"{a.data}: tasks {list(tasks)}")
    full = ds.get_db(upto_test_timestamp=False)
    timeline = {"dataset": a.data, "val_timestamp": str(ds.val_timestamp), "test_timestamp": str(ds.test_timestamp),
                "K": a.cutoffs, "tasks": {}, "db": {"min_timestamp": str(full.min_timestamp), "max_timestamp": str(full.max_timestamp)}}
    for n, t in tasks.items():
        if t.remove_columns:
            sys.exit(f"{n} hides columns {t.remove_columns}; the shared database would need per-task views")
        cols = [t.entity_col, t.time_col, t.target_col]
        entry = {"entity_table": t.entity_table, "entity_col": t.entity_col, "time_col": t.time_col, "target_col": t.target_col,
                 "task_type": t.task_type.value, "timedelta": str(t.timedelta), "cutoffs": []}
        real = t.dataset
        for k, val, test in cutoffs(ds, t.timedelta, a.cutoffs):
            t.dataset = Shifted(real, val, test)
            out = os.path.join(a.out, "tasks", n, f"k{k}")
            os.makedirs(out, exist_ok=True)
            rec = {"k": k, "val_timestamp": str(val), "test_timestamp": str(test)}
            for split in ("train", "val", "test"):
                df = t._get_table(split, db=full).df
                df.to_parquet(os.path.join(out, f"{split}.parquet"), index=False)
                rec[split] = {"rows": len(df), "seed_times": int(df[t.time_col].nunique()),
                              "first": str(df[t.time_col].min()), "last": str(df[t.time_col].max())}
                if k == a.cutoffs:
                    official = pd.read_parquet(os.path.join(a.data, "tasks", n, f"{split}.parquet"))
                    ok, why = same_rows(df, official, [c for c in cols if c in official.columns])
                    rec[split]["official"] = why
                    if not ok:
                        sys.exit(f"{n} k={k} {split} differs from the official table: {why}")
            t.dataset = real
            entry["cutoffs"].append(rec)
            log(f"{n} k{k}: test {test.date()} train {rec['train']['rows']} val {rec['val']['rows']} test {rec['test']['rows']}"
                + (f" | official: {rec['train'].get('official')}, {rec['val'].get('official')}, {rec['test'].get('official')}" if k == a.cutoffs else ""))
        timeline["tasks"][n] = entry
    tests = {e["cutoffs"][0]["test_timestamp"] for e in timeline["tasks"].values()}
    if len(tests) != 1:
        sys.exit(f"tasks disagree on the first cutoff: {tests}")
    if a.pg:
        first = pd.Timestamp(tests.pop())
        log(f"building {a.dbname} with rows up to {first}")
        timeline["pg"] = {"dbname": a.dbname, "upto": str(first), "tables": build_pg(a.pg, a.dbname, ds, full, first)}
    with open(os.path.join(a.out, "timeline.json"), "w") as f:
        json.dump(timeline, f, indent=1)
    log("done")


if __name__ == "__main__":
    main()

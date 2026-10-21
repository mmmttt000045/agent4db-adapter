#!/usr/bin/env python3
"""Agent sessions on the RelBench retraining timeline (exp/2026-10-20-relbench/README.md).

One run = one method on one database: a fresh copy of the template database built by prepare.py, one agent per task,
one session per (task, cutoff). Before cutoff k > 1 the rows with time in (test_{k-1}, test_k] are appended. Every
session gets the same tools: the middle layer's list_tables / describe_table / join_path / check_join / run_sql over
HTTP (`agentdb-mid serve --mode <m> --no-etl`), plus validate_features and submit implemented here with a fixed
LightGBM. The framework enforces the stopping rule; test labels never enter the database or the agent's context.

Run on noctis (repo root), without the dead local proxy:
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy PYTHONPATH=.pydeps-relbench \
  python3 tools/relbench/harness.py --arm none --run 1 --data results/relbench-data/rel-stack \
      --prep results/relbench-data/rel-stack-prep --template relbench_stack_t1 --out results/relbench-pilot/none-r1
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback

import numpy as np
import pandas as pd
import psycopg
import requests

# ACE's official prompts and playbook helpers (Apache-2.0), see third_party/ace/README.md
ACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "third_party", "ace")
sys.path.insert(0, ACE_DIR)
import curator_prompts as ace_curator  # noqa: E402
import playbook_utils as ace_pb  # noqa: E402
import reflector_prompts as ace_reflector  # noqa: E402

sys.path.pop(0)
# ACE._initialize_empty_playbook (ace/ace.py)
ACE_EMPTY_PLAYBOOK = """## STRATEGIES & INSIGHTS

## FORMULAS & CALCULATIONS

## CODE SNIPPETS & TEMPLATES

## COMMON MISTAKES TO AVOID

## PROBLEM-SOLVING HEURISTICS

## CONTEXT CLUES & INDICATORS

## OTHERS"""
ACE_TOKEN_BUDGET = 80_000  # the official Curator prompt's default token_budget

# ───────────────────────── fixed settings (README §1.2) ─────────────────────────

MAX_LLM_CALLS = 40
MAX_VALIDATIONS = 8
PATIENCE = 2
SAMPLE_SIZE = 50_000          # RelBench's lightgbm_entity.py default
SAMPLE_SEED = 42
MAX_FEATURES = 100
TOOL_OUTPUT_CHARS = 20_000
FEATURE_SQL_TIMEOUT_S = 600
AUDIT_SEEDS = 2000  # seeds for the reproduction check of MAVRA's learning
AUDIT_LEAK_SEEDS = 5000  # seeds of the leak audit (latest training seed time); 500 in the pilot missed leaks
IDLE_RECONNECT_S = 30  # a new connection to the gateway after this long without a request
POST_GOAL_LLM_CALLS = 5  # after the goal: one more validation within this many model calls (README §1.2, rule B)
LGB_PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=20, colsample_bytree=0.8,
                  subsample=0.8, subsample_freq=1, random_state=42, deterministic=True, force_row_wise=True,
                  n_jobs=8, verbose=-1)
ARMS = {
    "none": {"middle_mode": "middle-alone", "parallel_ok": True},
    # README §1.6: feature definitions shared by all agents; sessions of one cutoff run one after another
    "mavra": {"middle_mode": "relbench-mavra", "parallel_ok": False, "feature_memory": True, "extractor": True},
    # ACE (ICLR 2026) as published: one playbook per agent, online, no ground-truth labels (README §1.3)
    "ace": {"middle_mode": "middle-alone", "parallel_ok": True, "ace": True},
    # G-Memory (NeurIPS 2025) as published: one store shared by all agents, tasks one at a time (README §1.3)
    "gmemory": {"middle_mode": "middle-alone", "parallel_ok": False, "gmemory": True},
    # AgentSM (preprint) as described: read-only memory of this database built offline (tools/relbench/agentsm.py build)
    "agentsm": {"middle_mode": "middle-alone", "parallel_ok": True, "agentsm": True},
}
GMEMORY_REPO = "results/ext/GMemory"
GMEMORY_PYTHON = "results/ext/venv-gmem/bin/python"
GMEMORY_OBS_CHARS = 2000
FEATURE_TOOLS = ("find_features", "compose_features", "find_program")

LOCK = threading.Lock()


def log(msg):
    with LOCK:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env(path=".env"):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("DEEPSEEK_", "RIVER_", "AGENTDB_"))})
    return env


# ───────────────────────── LLM (OpenAI-compatible; same request shape as src/llm.rs) ─────────────────────────

# provider name -> (.env prefix, default base URL), as OPENAI_PROFILES in src/llm.rs; since 10-21 every run uses DeepSeek's own API
PROVIDERS = {"deepseek": ("DEEPSEEK", "https://api.deepseek.com"), "river": ("RIVER", "https://api.river.ai/v1")}

class Llm:
    def __init__(self, env, provider="deepseek"):
        prefix, base = PROVIDERS[provider]
        self.provider, self.prefix = provider, prefix
        self.base = env.get(f"{prefix}_BASE_URL", base).rstrip("/")
        self.key = env[f"{prefix}_API_KEY"]
        self.model = env[f"{prefix}_MODEL"]
        self.effort = env.get(f"{prefix}_REASONING_EFFORT")
        self.thinking = env.get(f"{prefix}_THINKING")
        self.require = env.get(f"{prefix}_REQUIRE_MODEL")
        # DeepSeek's thinking mode wants reasoning_content passed back within a tool-calling loop (as src/llm.rs does)
        self.keep_reasoning = "api.deepseek.com" in self.base
        self.local = threading.local()

    def history(self, m):
        """The assistant message as it goes back into the conversation."""
        keep = ("role", "content", "tool_calls", "reasoning_content") if self.keep_reasoning else ("role", "content", "tool_calls")
        return {k: v for k, v in m.items() if k in keep and v is not None} | {"role": "assistant"}

    @property
    def http(self):
        # a kept-alive connection idle for minutes (sessions run one after another, with learning and goals in between)
        # can be dropped on the way without notice; the next request then waits for the full timeout (pilot: 5 times 300 s)
        if not hasattr(self.local, "s") or time.time() - self.local.used > IDLE_RECONNECT_S:
            if hasattr(self.local, "s"):
                self.local.s.close()
            self.local.s = requests.Session()
            self.local.s.trust_env = False
        self.local.used = time.time()
        return self.local.s

    def _post(self, body):
        """One reply; also the number of failed attempts and the seconds they took (gateway stalls, reported apart)."""
        failures = limited = 0
        lost = 0.0
        while True:
            t0 = time.time()
            try:
                r = self.http.post(f"{self.base}/chat/completions", json=body, timeout=300,
                                   headers={"Authorization": f"Bearer {self.key}"})
            except requests.RequestException as e:
                failures += 1
                if failures > 3:
                    raise RuntimeError(f"request failed: {e}")
                time.sleep(2 ** failures)
                lost += time.time() - t0
                continue
            if r.status_code == 200:
                try:
                    return r.json(), failures + limited, lost
                except ValueError:
                    failures += 1
                    if failures > 3:
                        raise RuntimeError(f"non-JSON 200: {r.text[:300]}")
                    time.sleep(2 ** failures)
                    lost += time.time() - t0
                    continue
            if r.status_code == 429:
                limited += 1
                if limited > 8:
                    raise RuntimeError(f"HTTP 429 after 8 retries: {r.text[:300]}")
                time.sleep(min(120, int(r.headers.get("retry-after", 5 * 2 ** (limited - 1)))) + random.random() * 2)
                lost += time.time() - t0
                continue
            if r.status_code >= 500:
                failures += 1
                if failures > 3:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(2 ** failures)
                lost += time.time() - t0
                continue
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")

    def chat(self, messages, tools=None, temperature=None):
        body = {"model": self.model, "messages": messages}
        if self.effort:
            body["reasoning_effort"] = self.effort
        if self.thinking:
            body["thinking"] = {"type": self.thinking}
        if tools:
            body["tools"] = tools
        if temperature is not None:
            body["temperature"] = temperature
        discarded, wasted, retries, lost = 0, 0, 0, 0.0
        t0 = time.time()
        for _ in range(15):
            t1 = time.time()
            v, n, secs = self._post(body)
            retries, lost = retries + n, lost + secs
            if self.require and v.get("model") != self.require:
                discarded += 1
                wasted += (v.get("usage") or {}).get("total_tokens", 0)
                lost += time.time() - t1 - secs
                continue
            u = v.get("usage") or {}
            msg = v["choices"][0]["message"]
            return {
                "message": msg,
                "finish_reason": v["choices"][0].get("finish_reason"),
                "model": v.get("model"),
                "input_tokens": u.get("prompt_tokens", 0),
                "output_tokens": u.get("completion_tokens", 0),
                "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "seconds": time.time() - t0,
                "discarded": discarded,
                "discarded_tokens": wasted,
                # failed attempts and replies from another model: time the gateway lost, included in "seconds"
                "retries": retries,
                "retry_seconds": lost,
            }
        raise RuntimeError(f"no reply from {self.require} in 15 rounds ({discarded} discarded)")


# ───────────────────────── middle layer ─────────────────────────

class GMemoryService:
    """tools/relbench/gmemory_service.py in G-Memory's own Python 3.12 environment, one JSON line per request."""

    def __init__(self, env, out, llm):
        self.err = open(os.path.join(out, "gmemory.log"), "w")
        # its own environment: no proxies, and none of the harness's packages (PYTHONPATH)
        e = {k: v for k, v in os.environ.items() if "proxy" not in k.lower() and k != "PYTHONPATH"}
        e.update(OPENAI_API_BASE=llm.base, OPENAI_API_KEY=llm.key,
                 HF_ENDPOINT="https://hf-mirror.com", TOKENIZERS_PARALLELISM="false")
        here = os.path.dirname(os.path.abspath(__file__))
        self.proc = subprocess.Popen([GMEMORY_PYTHON, os.path.join(here, "gmemory_service.py"), "--repo", GMEMORY_REPO,
                                      "--working-dir", os.path.join(out, "gmemory"), "--model", llm.model],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, env=e, text=True, bufsize=1)
        first = json.loads(self.proc.stdout.readline() or "{}")
        if not first.get("ready"):
            raise RuntimeError("G-Memory service did not start; see gmemory.log")

    def send(self, req):
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("G-Memory service exited; see gmemory.log")
        return json.loads(line)

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class Middle:
    def __init__(self, url, mode, out, port, extractor=None, effort=None, prefix=None):
        self.base = f"http://127.0.0.1:{port}"
        self.log = open(os.path.join(out, "middle.log"), "w")
        env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        if effort and prefix:
            env[f"{prefix}_REASONING_EFFORT"] = effort  # the extractor uses the agents' setting
        self.proc = subprocess.Popen(
            ["./target/release/agentdb-mid", "--db", url, "--pool", "8", "--out", os.path.join(out, "middle"),
             "serve", "--addr", f"127.0.0.1:{port}", "--mode", mode, "--no-etl", *(["--extractor", extractor] if extractor else [])],
            stdout=self.log, stderr=subprocess.STDOUT, env=env)
        self.local = threading.local()
        for _ in range(120):
            try:
                if self.http.get(f"{self.base}/v1/tools", timeout=5).ok:
                    return
            except requests.RequestException:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError(f"middle layer exited ({self.proc.returncode}); see middle.log")
            time.sleep(1)
        raise RuntimeError("middle layer did not start")

    @property
    def http(self):
        if not hasattr(self.local, "s"):
            self.local.s = requests.Session()
            self.local.s.trust_env = False
        return self.local.s

    def call(self, name, agent, session, task, args):
        r = self.http.post(f"{self.base}/v1/tools/{name}", json={"agent": agent, "session": session, "task": task, "args": args},
                           timeout=FEATURE_SQL_TIMEOUT_S)
        return r.json()

    def post(self, path, body, timeout=1800):
        return self.http.post(f"{self.base}{path}", json=body, timeout=timeout).json()

    def get(self, path):
        return self.http.get(f"{self.base}{path}", timeout=120).json()

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ───────────────────────── database helpers ─────────────────────────

def base_url(url):
    return url.rsplit("/", 1)[0]


def create_run_db(url, template, name):
    with psycopg.connect(f"{base_url(url)}/postgres", autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        con.execute(f"CREATE DATABASE {name} TEMPLATE {template}")


def drop_db(url, name):
    with psycopg.connect(f"{base_url(url)}/postgres", autocommit=True) as con:
        con.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def copy_rows(con, table, df):
    import io

    cols = ", ".join(c.lower() for c in df.columns)
    with con.cursor() as cur, cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
        for start in range(0, len(df), 200_000):
            part = df.iloc[start:start + 200_000].copy()
            for c in part.columns:
                if part[c].dtype == object:
                    part[c] = part[c].map(lambda v: v.replace("\x00", "") if isinstance(v, str) else v)
            buf = io.StringIO()
            part.to_csv(buf, index=False, header=False, na_rep="\\N", date_format="%Y-%m-%d %H:%M:%S.%f")
            cp.write(buf.getvalue())


def read_sql(url, sql, timeout_s=FEATURE_SQL_TIMEOUT_S, search_path=None):
    t0 = time.time()
    with psycopg.connect(url, autocommit=False) as con:
        with con.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL lc_messages = 'C'")
            cur.execute(f"SET LOCAL statement_timeout = {timeout_s * 1000}")
            if search_path:
                cur.execute(f"SET LOCAL search_path = {search_path}")
            cur.execute(sql)
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
        con.rollback()
    return pd.DataFrame(rows, columns=cols), time.time() - t0


# ───────────────────────── tasks and learner ─────────────────────────

def tname(task):
    return task.replace("-", "_")


def metric_of(task_type):
    return ("roc_auc", True) if task_type == "binary_classification" else ("mae", False)


def score(task_type, y, p):
    from sklearn.metrics import mean_absolute_error, roc_auc_score

    return float(roc_auc_score(y, p)) if task_type == "binary_classification" else float(mean_absolute_error(y, p))


def train_predict(task_type, xtr, ytr, xev):
    import lightgbm as lgb

    t0 = time.time()
    if task_type == "binary_classification":
        m = lgb.LGBMClassifier(objective="binary", **LGB_PARAMS)
        m.fit(xtr, ytr)
        p = m.predict_proba(xev)[:, 1]
    else:
        m = lgb.LGBMRegressor(objective="l1", **LGB_PARAMS)
        m.fit(xtr, ytr)
        p = m.predict(xev)
    imp = sorted(zip(xtr.columns, m.booster_.feature_importance("gain")), key=lambda x: -x[1])
    return p, [(c, round(float(g), 1)) for c, g in imp], time.time() - t0


class FeatureError(Exception):
    pass


def features(url, sql, seeds_table, seeds, ec, search_path=None):
    """Run feature SQL against one seed table and check the contract; returns (aligned features, seconds)."""
    if "{seeds}" not in sql:
        raise FeatureError("the SQL must use {seeds} as the seed table")
    q = sql.strip().rstrip(";").replace("{seeds}", seeds_table)
    # one row per seed is the contract: more rows are an error, so the database stops after len(seeds) + 1 rows
    q = f"SELECT * FROM ({q}) AS feature_rows LIMIT {len(seeds) + 1}"
    try:
        df, secs = read_sql(url, q, search_path=search_path)
    except psycopg.Error as e:
        raise FeatureError(f"SQL error: {str(e).strip()[:1500]}")
    if len(df) > len(seeds):
        raise FeatureError(f"more than {len(seeds)} rows for {len(seeds)} seeds; return one row per seed (check joins that multiply rows)")
    if df.shape[1] < 3:
        raise FeatureError("need the entity key, seed_time and at least one feature column")
    if df.shape[1] - 2 > MAX_FEATURES:
        raise FeatureError(f"{df.shape[1] - 2} feature columns; at most {MAX_FEATURES}")
    df = df.rename(columns={df.columns[0]: ec, df.columns[1]: "seed_time"})
    if df.duplicated([ec, "seed_time"]).any():
        raise FeatureError(f"{int(df.duplicated([ec, 'seed_time']).sum())} duplicate (key, seed_time) rows; return one row per seed")
    df["seed_time"] = pd.to_datetime(df["seed_time"])
    merged = seeds[[ec, "seed_time"]].merge(df, on=[ec, "seed_time"], how="left", indicator=True)
    missing = int((merged["_merge"] == "left_only").sum())
    if missing or len(df) != len(seeds):
        raise FeatureError(f"returned {len(df)} rows for {len(seeds)} seeds ({missing} seeds missing); return one row per seed")
    x = merged.drop(columns=[ec, "seed_time", "_merge"])
    if x.columns.duplicated().any():
        raise FeatureError(f"duplicate feature column names: {sorted(set(x.columns[x.columns.duplicated()]))[:10]}")
    bad = []
    for c in x.columns:
        if not pd.api.types.is_numeric_dtype(x[c]):
            conv = pd.to_numeric(x[c], errors="coerce")
            if conv.isna().sum() > x[c].isna().sum():
                bad.append(c)
            else:
                x[c] = conv
    if bad:
        raise FeatureError(f"non-numeric feature columns: {bad[:10]}; encode them as numbers in SQL")
    try:
        return x.astype(float), secs
    except (TypeError, ValueError) as err:
        raise FeatureError(f"feature columns are not numeric: {str(err)[:200]}")


# ───────────────────────── one run ─────────────────────────

class Run:
    def __init__(self, a):
        self.a = a
        self.env = load_env()
        self.url_admin = self.env["AGENTDB_URL"]
        self.timeline = json.load(open(os.path.join(a.prep, "timeline.json")))
        self.tasks = {t: e for t, e in self.timeline["tasks"].items() if not a.tasks or t in a.tasks}
        self.manifest = __import__("yaml").safe_load(open(os.path.join(a.data, "manifest.yaml")))
        self.task_desc = {t: __import__("yaml").safe_load(open(os.path.join(a.data, "tasks", t, "manifest.yaml"))) for t in self.tasks}
        self.db_name = f"relbench_{a.arm.replace('-', '_')}_r{a.run}_{os.getpid()}"
        self.url = f"{base_url(self.url_admin)}/{self.db_name}"
        self.llm = Llm(self.env, a.llm)
        self.llm.effort = a.reasoning_effort
        self.arm = ARMS[a.arm]
        self.refs = {}
        # retraining goal (README §1.2, 10-21): the previous cutoff's model, refit on this cutoff's data.
        # task -> (cutoff, final feature SQL whose audit was clean) of this run's latest session
        self.prev_sql = {}
        self.targets = {}
        if a.targets_from:
            first = min(int(x) for x in a.cutoffs) if a.cutoffs else 1
            for f in glob.glob(os.path.join(a.targets_from, "sessions", "*.json")):
                if f.endswith(".partial.json"):
                    continue
                r0 = json.load(open(f))
                if r0["k"] == first - 1 and r0.get("final_sql") and (r0.get("audit") or {}).get("result") == "clean":
                    self.prev_sql[r0["task"]] = (r0["k"], r0["final_sql"])
        self.playbooks = {}  # ACE: agent -> playbook text
        self.ace_steps = {}
        self.gmem = None
        self.asm = None
        os.makedirs(os.path.join(a.out, "sessions"), exist_ok=True)

    # data changes and seed tables
    def table(self, name, rows=None):
        """One database table from the dataset files; with `rows`, only rows whose time column is in (rows[0], rows[1]]."""
        import pyarrow.parquet as pq

        path = os.path.join(self.a.data, "db", f"{name}.parquet")
        tc = self.manifest["tables"][name].get("time_col")
        if rows is None or not tc:
            return pd.read_parquet(path)
        lo, hi = rows
        return pq.read_table(path, filters=[(tc, ">", lo), (tc, "<=", hi)]).to_pandas()

    def append(self, prev, cur):
        t0, n = time.time(), {}
        with psycopg.connect(self.url, autocommit=False) as con:
            for name, spec in self.manifest["tables"].items():
                tc = spec.get("time_col")
                if not tc:
                    continue
                part = self.table(name, (prev, cur))
                if len(part):
                    copy_rows(con, name.lower(), part)
                    # one ETL batch per appended table, as metric-bench logs its data changes
                    con.execute("INSERT INTO etl_batch_log (table_name, batch_id, note) SELECT %s, coalesce(max(batch_id), 0) + 1, %s "
                                "FROM etl_batch_log WHERE table_name = %s", (name.lower(), f"append ({prev}, {cur}]", name.lower()))
                n[name.lower()] = len(part)
            con.commit()
        with psycopg.connect(self.url, autocommit=True) as con:
            for name in self.manifest["tables"]:
                con.execute(f"ANALYZE {name.lower()}")
        return {"rows": n, "seconds": time.time() - t0}

    def seed_tables(self, k):
        """Create schema task with <t>_train / _train_sample / _val (labelled) and _test (unlabelled) for cutoff k."""
        seeds = {}
        with psycopg.connect(self.url, autocommit=True) as con:
            con.execute("DROP SCHEMA IF EXISTS task CASCADE")
            con.execute("CREATE SCHEMA task")
            for t, e in self.tasks.items():
                ec, tc, yc = e["entity_col"].lower(), e["time_col"], e["target_col"].lower()
                d = os.path.join(self.a.prep, "tasks", t, f"k{k}")
                s = {}
                for split in ("train", "val", "test"):
                    df = pd.read_parquet(os.path.join(d, f"{split}.parquet"))
                    df.columns = [c.lower() for c in df.columns]
                    df = df.rename(columns={tc.lower(): "seed_time"})
                    df["seed_time"] = pd.to_datetime(df["seed_time"])
                    s[split] = df
                rng = np.random.RandomState(SAMPLE_SEED)
                tr = s["train"]
                s["train_sample"] = tr.iloc[rng.permutation(len(tr))[:SAMPLE_SIZE]].reset_index(drop=True) if len(tr) > SAMPLE_SIZE else tr
                for split, cols in (("train", [ec, "seed_time", yc]), ("train_sample", [ec, "seed_time", yc]),
                                    ("val", [ec, "seed_time", yc]), ("test", [ec, "seed_time"])):
                    df = s[split][cols]
                    types = {ec: "bigint" if pd.api.types.is_integer_dtype(df[ec]) else "text", "seed_time": "timestamp",
                             yc: "double precision"}
                    con.execute(f"CREATE TABLE task.{tname(t)}_{split} ({', '.join(f'{c} {types[c]}' for c in cols)})")
                    copy_rows(con, f"task.{tname(t)}_{split}", df)
                    con.execute(f"ANALYZE task.{tname(t)}_{split}")
                seeds[t] = s
        return seeds

    def reference_sql(self, t):
        """Entity-table columns only (the input of RelBench's LightGBM baseline): numeric columns and days since each time column."""
        e = self.tasks[t]
        et = e["entity_table"]
        spec = self.manifest["tables"][et]
        pk = spec["pkey"].lower()
        df = self.table(et)
        fk = {c.lower() for c in (spec.get("fkeys") or {})}
        cols = []
        for c in df.columns:
            lc = c.lower()
            if lc == pk or lc in fk:
                continue
            if pd.api.types.is_bool_dtype(df[c]) or pd.api.types.is_numeric_dtype(df[c]):
                cols.append(f"e.{lc}::double precision AS {lc}")
            elif pd.api.types.is_datetime64_any_dtype(df[c]):
                cols.append(f"extract(epoch from (s.seed_time - e.{lc})) / 86400.0 AS days_since_{lc}")
        if not cols:
            cols = ["0.0 AS constant"]
        ec = e["entity_col"].lower()
        return f"SELECT s.{ec}, s.seed_time, {', '.join(cols)} FROM {{seeds}} s LEFT JOIN {et.lower()} e ON e.{pk} = s.{ec}"

    def evaluate(self, t, k, sql, seeds, search_path=None):
        """Validation and test scores of a feature SQL (train on the 50k sample)."""
        e = self.tasks[t]
        ec, yc = e["entity_col"].lower(), e["target_col"].lower()
        test_labels = pd.read_parquet(os.path.join(self.a.prep, "tasks", t, f"k{k}", "test.parquet"))
        test_labels.columns = [c.lower() for c in test_labels.columns]
        test_labels = test_labels.rename(columns={e["time_col"].lower(): "seed_time"})
        test_labels["seed_time"] = pd.to_datetime(test_labels["seed_time"])
        xtr, s1 = features(self.url, sql, f"task.{tname(t)}_train_sample", seeds["train_sample"], ec, search_path=search_path)
        xva, s2 = features(self.url, sql, f"task.{tname(t)}_val", seeds["val"], ec, search_path=search_path)
        xte, s3 = features(self.url, sql, f"task.{tname(t)}_test", seeds["test"], ec, search_path=search_path)
        ytest = seeds["test"][[ec, "seed_time"]].merge(test_labels[[ec, "seed_time", yc]], on=[ec, "seed_time"], how="left")[yc]
        pv, _, _ = train_predict(e["task_type"], xtr, seeds["train_sample"][yc], xva)
        pt, _, tt = train_predict(e["task_type"], xtr, seeds["train_sample"][yc], xte)
        return {"val": score(e["task_type"], seeds["val"][yc], pv), "test": score(e["task_type"], ytest, pt),
                "sql_seconds": s1 + s2 + s3, "train_seconds": tt, "n_features": xtr.shape[1]}

    def audit(self, t, k, sql, seeds):
        """Leakage audit: recompute features for the latest training seeds on views that hide rows after that seed time."""
        e = self.tasks[t]
        ec = e["entity_col"].lower()
        tr = seeds["train_sample"]
        tstar = tr["seed_time"].max()
        sub = tr[tr["seed_time"] == tstar].sort_values(ec).head(AUDIT_LEAK_SEEDS).reset_index(drop=True)
        schema = f"audit_{tname(t)}_k{k}"
        # tables named as public.x read the audit views too
        hidden_sql = re.sub(r"\bpublic\s*\.", f"{schema}.", sql, flags=re.I)
        with psycopg.connect(self.url, autocommit=True) as con:
            con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            con.execute(f"CREATE SCHEMA {schema}")
            for name, spec in self.manifest["tables"].items():
                tc = spec.get("time_col")
                cond = f" WHERE {tc.lower()} <= '{tstar}'" if tc else ""
                con.execute(f"CREATE VIEW {schema}.{name.lower()} AS SELECT * FROM public.{name.lower()}{cond}")
            con.execute(f"CREATE TABLE {schema}.seeds AS SELECT * FROM task.{tname(t)}_train_sample WHERE false")
            copy_rows(con, f"{schema}.seeds", sub[[c for c in sub.columns]])
            con.execute(f"ANALYZE {schema}.seeds")
        try:
            normal, _ = features(self.url, sql, f"{schema}.seeds", sub, ec)
            hidden, _ = features(self.url, hidden_sql, f"{schema}.seeds", sub, ec, search_path=f"{schema}, public")
        except FeatureError as err:
            return {"result": "error", "why": str(err)[:300]}
        finally:
            with psycopg.connect(self.url, autocommit=True) as con:
                con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        a, b = normal.to_numpy(), hidden.to_numpy()
        diff = ~np.isclose(a, b, rtol=1e-6, atol=1e-9, equal_nan=True)
        cols = [c for c, d in zip(normal.columns, diff.any(axis=0)) if d]
        return {"result": "leak" if diff.any() else "clean", "seed_time": str(tstar), "seeds": len(sub),
                "cells_differing": int(diff.sum()), "columns_differing": cols[:20]}

    # ───────── one session ─────────
    def system_prompt(self, t, k, seeds):
        e, d = self.tasks[t], self.task_desc[t]
        cut = e["cutoffs"][k - 1]
        metric, higher = metric_of(e["task_type"])
        ec = e["entity_col"].lower()
        spec = self.manifest["tables"][e["entity_table"]]
        n_times = seeds["train"]["seed_time"].nunique()
        return f"""You are a data scientist agent working on a PostgreSQL database: {self.manifest.get('description', '')}
Your job is to engineer features with SQL for one prediction task. A fixed LightGBM model is trained on your features; you cannot change the model.

Task: {d['description']}
Entity: {e['entity_table'].lower()}.{spec['pkey'].lower()} (column `{ec}` in the seed tables). Target: `{e['target_col'].lower()}` ({e['task_type'].replace('_', ' ')}); metric: {metric}, {'higher' if higher else 'lower'} is better.
Each seed row ({ec}, seed_time) asks for a prediction made at seed_time; the target describes the {e['timedelta']} after seed_time.
Seed tables: task.{tname(t)}_train (labelled training seeds, {len(seeds['train'])} rows over {n_times} seed times), task.{tname(t)}_val (labelled validation seeds at {cut['val_timestamp'][:10]}), task.{tname(t)}_test (unlabelled seeds at {cut['test_timestamp'][:10]}). The other tables are in schema public and hold data up to {cut['test_timestamp'][:10]}.

Feature SQL contract: one SELECT statement that uses {{seeds}} as the seed table (columns {ec}, seed_time) and returns exactly one row per seed row, with {ec} and seed_time as the first two columns followed by numeric feature columns (at most {MAX_FEATURES}). A feature may only use rows whose time is at or before the seed row's seed_time; using later rows is leakage and makes the features invalid.

Tools: list_tables, describe_table, join_path, check_join and run_sql explore the database; the first four cover the tables in schema public, and the seed tables are read with run_sql (read-only, at most 50 rows returned). validate_features(sql) computes your features on a {SAMPLE_SIZE}-row training sample and on the validation seeds, trains the model and returns the validation {metric}. submit(sql) ends the session with your final features.
Budget: at most {MAX_VALIDATIONS} validations and {MAX_LLM_CALLS} model calls; the session also ends after {PATIENCE} validations in a row without improvement. If you do not submit, your best validated features are used.""" + (
            f"\n\nRetraining goal: this task's model from the previous cutoff ({e['cutoffs'][k - 2]['test_timestamp'][:10]}), refit on this cutoff's data, "
            f"reaches validation {metric} {self.target(t, k):.5f}. Once your features reach that score you may make one more attempt to improve them: "
            f"one more validation within the next {POST_GOAL_LLM_CALLS} model calls, after which the session ends with your best validated features." if self.target(t, k) is not None else "") + (f"""

Shared memory: agents on this database publish verified feature definitions and feature programs. Start with find_program (this task's verified program from an earlier cutoff: its complete feature SQL when it still runs, and a feature SQL of its definitions) and find_features (definitions for the entity table, with a feature SQL of them for these seed tables). If they return a feature SQL, validate it first (the complete program SQL first); explore the tables and extend the SQL only to improve on it. compose_features compiles chosen definitions (by key) into a feature SQL.""" if self.arm.get("feature_memory") else "") + (
            "\n\nMemory: retrieve_trajectory returns how the most similar earlier task on this database was explored; call it before you start. "
            "schema_linking asks a schema linking agent to map a task to tables, columns and joins. The other extra tools run tool sequences "
            "that agents often call together." if self.arm.get("agentsm") else "") + (
            "\n\n" + open(os.path.join(ACE_DIR, "appworld_playbook_block.txt")).read().replace(
                "{{ playbook }}", self.playbooks.get(f"{tname(t)}-agent", ACE_EMPTY_PLAYBOOK)).rstrip()
            + "\nWhen you call validate_features or submit, list in bullet_ids the playbook bullets you used." if self.arm.get("ace") else "")

    def target(self, t, k):
        """Validation score of this run's previous-cutoff model of task t, refit on cutoff k (none at the first cutoff)."""
        return (self.targets.get((t, k)) or {}).get("val")

    def incumbent(self, t, k, seeds):
        """Refit the previous cutoff's final feature SQL on cutoff k and score it on the validation seeds (no LLM)."""
        prev = self.prev_sql.get(t)
        if not prev or prev[0] != k - 1:
            return {"val": None, "why": "no previous model"}
        e = self.tasks[t]
        ec, yc = e["entity_col"].lower(), e["target_col"].lower()
        t0 = time.time()
        try:
            xtr, _ = features(self.url, prev[1], f"task.{tname(t)}_train_sample", seeds["train_sample"], ec)
            xva, _ = features(self.url, prev[1], f"task.{tname(t)}_val", seeds["val"], ec)
            p, _, _ = train_predict(e["task_type"], xtr, seeds["train_sample"][yc], xva)
            val = score(e["task_type"], seeds["val"][yc], p)
        except Exception as err:  # noqa: BLE001 - a previous model that no longer runs gives no goal
            return {"val": None, "why": f"previous model failed: {str(err)[:200]}", "seconds": time.time() - t0}
        leak = self.audit(t, k, prev[1], seeds)
        if leak.get("result") == "leak":
            return {"val": None, "why": "previous model reads rows after seed_time on this cutoff", "seconds": time.time() - t0}
        return {"val": val, "from_cutoff": prev[0], "seconds": time.time() - t0}

    def tool_specs(self):
        def fn(name, desc, props, req):
            return {"type": "function", "function": {"name": name, "description": desc,
                                                     "parameters": {"type": "object", "properties": props, "required": req}}}
        s = {"type": "string"}
        return [
            fn("list_tables", "List the tables with estimated row counts and comments.", {}, []),
            fn("describe_table", "Profile a table: columns, types, null ratios, distinct counts, common values, sample rows.", {"table": s}, ["table"]),
            fn("join_path", "Find join paths between two tables, checked on the data.", {"table_a": s, "table_b": s}, ["table_a", "table_b"]),
            fn("check_join", "Check a join between two tables on given column pairs: key uniqueness and match rates.",
               {"left": s, "right": s, "on": {"type": "array", "items": {"type": "array", "items": s}, "description": "[[left_col, right_col], ...]"}},
               ["left", "right", "on"]),
            fn("run_sql", "Run one read-only SQL query on PostgreSQL; returns at most 50 rows.", {"sql": s}, ["sql"]),
            fn("validate_features", "Compute the features of a feature SQL (must use {seeds}) on the training sample and validation seeds, train the fixed model, return the validation score.",
               {"sql": s, **({"bullet_ids": {"type": "array", "items": s, "description": "ids of the playbook bullets you used"}} if self.arm.get("ace") else {})}, ["sql"]),
            fn("submit", "Finish the session with this feature SQL (must use {seeds}). Omit sql to submit your best validated features.",
               {"sql": s, **({"bullet_ids": {"type": "array", "items": s, "description": "ids of the playbook bullets you used"}} if self.arm.get("ace") else {})}, []),
        ] + ([
            fn("find_features", "List verified feature definitions shared by all agents for an entity table (key, name, meaning, aggregated table, measure, look-back window), with a feature SQL of them for this task's seed tables, ready for validate_features.",
               {"entity": s, "query": {"type": "string", "description": "words describing the features you want"}}, ["entity"]),
            fn("compose_features", "Compile verified feature definitions (keys from find_features or find_program) into one feature SQL that uses {seeds}.",
               {"keys": {"type": "array", "items": s}}, ["keys"]),
            fn("find_program", "The latest verified feature program for this task (from an earlier cutoff): its validation score and its still-valid definitions compiled into one feature SQL, ready for validate_features.",
               {}, []),
        ] if self.arm.get("feature_memory") else []) + (self.asm.tool_specs() if self.asm else [])

    def session(self, t, k, seeds, middle):
        e = self.tasks[t]
        agent = f"{tname(t)}-agent"
        sid = f"{self.a.arm}-r{self.a.run}-{tname(t)}-k{k}"
        metric, higher = metric_of(e["task_type"])
        if (t, k) not in self.targets:
            self.targets[(t, k)] = self.incumbent(t, k, seeds) if k > 1 else {"val": None, "why": "first cutoff"}
        ec, yc = e["entity_col"].lower(), e["target_col"].lower()
        rec = {"arm": self.a.arm, "run": self.a.run, "task": t, "k": k, "agent": agent, "session": sid, "metric": metric, "target": self.target(t, k),
               "target_detail": self.targets.get((t, k)),
               "higher_is_better": higher, "llm": [], "tools": [], "validations": [], "stop": None, "error": None}
        task_line = f"Build features for {t} at cutoff {e['cutoffs'][k - 1]['test_timestamp'][:10]}."
        msgs = [{"role": "system", "content": self.system_prompt(t, k, seeds)}, {"role": "user", "content": task_line}]
        gmem_tokens = [0, 0]
        if self.gmem:
            g = self.gmem.send({"op": "begin", "task_main": f"{self.task_desc[t]['description']} (task {t}, cutoff {e['cutoffs'][k - 1]['test_timestamp'][:10]})",
                                "task_description": task_line})
            gmem_tokens = [g.get("prompt_tokens", 0), g.get("completion_tokens", 0)]
            if g.get("prompt"):
                msgs[1]["content"] = g["prompt"]
            rec["gmemory_begin"] = {k2: g.get(k2) for k2 in ("n_success", "n_insights", "error")}
        best, best_sql, streak, idle, submitted = None, None, 0, 0, None
        goal_hit = None  # model calls made when a validation first reached the goal
        t_start = time.time()

        def better(x):
            return best is None or (x > best if higher else x < best)

        while True:
            if goal_hit is not None and len(rec["llm"]) - goal_hit >= POST_GOAL_LLM_CALLS:
                rec["stop"] = "reached_previous"
                break
            if len(rec["llm"]) >= MAX_LLM_CALLS:
                rec["stop"] = "llm_budget"
                break
            try:
                r = self.llm.chat(msgs, self.tool_specs())
            except Exception as err:
                rec["error"] = f"llm: {err}"
                rec["stop"] = "llm_error"
                break
            m = r.pop("message")
            rec["llm"].append({**r, "tool_calls": len(m.get("tool_calls") or []), "content_chars": len(m.get("content") or "")})
            with open(os.path.join(self.a.out, "sessions", f"{tname(t)}-k{k}.partial.json"), "w") as f:
                json.dump({**rec, "messages": msgs}, f, ensure_ascii=False, default=str)
            msgs.append(self.llm.history(m))
            calls = m.get("tool_calls") or []
            if not calls:
                idle += 1
                if idle >= 3:
                    rec["stop"] = "no_tool_calls"
                    break
                msgs.append({"role": "user", "content": "Use a tool, or call submit to finish."})
                continue
            idle = 0
            stop = None
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                t0 = time.time()
                entry = {"i": len(rec["tools"]), "llm_i": len(rec["llm"]) - 1, "name": name, "args": args}
                if stop:
                    out = {"error": "session already ended"}
                elif name in FEATURE_TOOLS and self.arm.get("feature_memory"):
                    # the harness fills in what the agent cannot know: the seed table's entity column and this task's id
                    if name in ("compose_features", "find_features"):
                        args["seed_key"] = ec
                    if name == "find_program":
                        args["task"] = t
                    try:
                        out = middle.call(name, agent, sid, sid, args)
                    except Exception as err:
                        out = {"error": f"{err}"}
                    entry["category"] = "memory"
                elif self.asm and name in self.asm.names():
                    sub = []
                    try:
                        if name == "retrieve_trajectory":
                            out = self.asm.retrieve(args.get("query") or self.task_desc[t]["description"], args.get("phase") or "exploration")
                            entry["category"] = "memory"
                        elif name == "schema_linking":
                            out = self.asm.schema_linking(args.get("question") or self.task_desc[t]["description"], middle, agent, sid, self.llm, sub)
                            entry["category"] = "schema"
                        else:
                            out = self.asm.composite(name, args, middle, agent, sid, lambda a2: self.agentsm_sql(middle, agent, sid, a2, rec))
                            entry["category"] = "schema"
                    except Exception as err:
                        out = {"error": f"{err}"}
                        entry.setdefault("category", "memory")
                    rec.setdefault("llm_sub", []).extend({**x, "role": name} for x in sub)
                    if isinstance(out, dict) and "_sub_tool_calls" in out:
                        entry["sub_tool_calls"] = out.pop("_sub_tool_calls")
                elif name in ("list_tables", "describe_table", "join_path", "check_join", "run_sql"):
                    if self.asm and name == "run_sql":
                        out = self.agentsm_sql(middle, agent, sid, args, rec)
                    else:
                        try:
                            out = middle.call(name, agent, sid, sid, args)
                        except Exception as err:
                            out = {"error": f"{err}"}
                    entry["category"] = "probe" if name == "run_sql" else "schema"
                elif name == "validate_features":
                    entry["category"] = "validate"
                    sql = args.get("sql", "")
                    if args.get("bullet_ids"):
                        rec["bullet_ids"] = [str(b) for b in args["bullet_ids"]]
                    try:
                        xtr, s1 = features(self.url, sql, f"task.{tname(t)}_train_sample", seeds["train_sample"], ec)
                        xva, s2 = features(self.url, sql, f"task.{tname(t)}_val", seeds["val"], ec)
                        p, imp, tt = train_predict(e["task_type"], xtr, seeds["train_sample"][yc], xva)
                        val = score(e["task_type"], seeds["val"][yc], p)
                        # leak check at validation time (README §1.2, 10-21): a leaking validation does not count, so that
                        # neither the goal nor the best score can be reached with data after seed_time
                        ta = time.time()
                        leak = self.audit(t, k, sql, seeds)
                        audit_s = time.time() - ta
                        leaking = leak.get("result") == "leak"
                        improved = (not leaking) and better(val)
                        if improved:
                            best, best_sql, streak = val, sql, 0
                        elif not leaking:
                            streak += 1
                        rec["validations"].append({"tool_i": entry["i"], "val": val, "improved": improved, "sql_seconds": s1 + s2,
                                                   "train_seconds": tt, "audit_seconds": audit_s, "leak": leaking,
                                                   "leaking_columns": leak.get("columns_differing"), "n_features": xtr.shape[1],
                                                   "sql": sql, "importance": [c for c, _ in imp[:30]]})
                        out = {f"validation_{metric}": round(val, 5), "improved": improved,
                               "n_features": xtr.shape[1], "train_rows": len(xtr), "val_rows": len(xva),
                               "top_features_by_gain": imp[:15],
                               "validations_left": MAX_VALIDATIONS - len(rec["validations"])}
                        if best is not None:
                            out["best_so_far"] = round(best, 5)
                        if leaking:
                            out["leak"] = {"counted": False, "columns_reading_data_after_seed_time": leak.get("columns_differing"),
                                           "note": "these columns change when rows after seed_time are hidden; this validation does not count"}
                        entry.update(sql_seconds=s1 + s2, train_seconds=tt, audit_seconds=audit_s)
                    except Exception as err:  # noqa: BLE001 - contract errors and anything unexpected go back to the agent
                        # a failed validation uses one of the validations but does not count as "no improvement"
                        msg = str(err) if isinstance(err, FeatureError) else f"validation failed: {type(err).__name__}: {str(err)[:300]}"
                        out = {"error": msg, "validations_left": MAX_VALIDATIONS - len(rec["validations"]) - 1}
                        rec["validations"].append({"tool_i": entry["i"], "error": msg[:500], "sql": sql})
                    goal = self.target(t, k)
                    if goal_hit is not None:
                        # rule B (README §1.2, 10-21 user decision): the one validation allowed after the goal ends the session
                        stop = "reached_previous"
                    elif goal is not None and best is not None and (best >= goal if higher else best <= goal):
                        goal_hit = len(rec["llm"])
                        rec["goal_reached"] = {"validation": len(rec["validations"]), "llm_calls": goal_hit}
                        if len(rec["validations"]) >= MAX_VALIDATIONS:
                            stop = "reached_previous"
                        else:
                            out["goal_reached"] = (f"This reaches the goal. You may make one more attempt to improve: one more validate_features "
                                                   f"within the next {POST_GOAL_LLM_CALLS} model calls, after which the session ends with your "
                                                   f"best validated features. Call submit to finish now.")
                    elif len(rec["validations"]) >= MAX_VALIDATIONS:
                        stop = "validation_budget"
                    elif streak >= PATIENCE and best is not None:
                        stop = "patience"
                elif name == "submit":
                    entry["category"] = "submit"
                    sql = args.get("sql") or best_sql
                    leak = self.audit(t, k, sql, seeds) if sql and sql != best_sql else {}
                    if not sql:
                        out = {"error": "nothing validated yet; validate features first or pass sql"}
                    elif leak.get("result") == "leak":
                        out = {"error": "not submitted: these features read rows after seed_time",
                               "columns_reading_data_after_seed_time": leak.get("columns_differing")}
                    else:
                        submitted, stop = sql, "submitted"
                        if args.get("bullet_ids"):
                            rec["bullet_ids"] = [str(b) for b in args["bullet_ids"]]
                        out = {"ok": True}
                else:
                    out = {"error": f"unknown tool {name}"}
                entry["seconds"] = time.time() - t0
                text = json.dumps(out, ensure_ascii=False, default=str)
                entry["output_chars"] = len(text)
                entry["error"] = bool(isinstance(out, dict) and out.get("error"))
                rec["tools"].append(entry)
                if self.gmem:
                    g = self.gmem.send({"op": "step", "agent": agent, "action": f"{name}: {json.dumps(args, ensure_ascii=False)[:GMEMORY_OBS_CHARS]}",
                                        "observation": text[:GMEMORY_OBS_CHARS], "reward": -1 if entry["error"] else 0})
                    gmem_tokens = [gmem_tokens[0] + g.get("prompt_tokens", 0), gmem_tokens[1] + g.get("completion_tokens", 0)]
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": text[:TOOL_OUTPUT_CHARS]})
            if stop:
                rec["stop"] = stop
                break
        rec["audit_seconds"] = sum(v.get("audit_seconds", 0) for v in rec["validations"])
        rec["agent_seconds"] = time.time() - t_start - rec["audit_seconds"]
        rec["final_sql"] = submitted or best_sql
        rec["final_source"] = "submitted" if submitted else ("best_validated" if best_sql else None)
        rec["best_val"] = best
        if rec["final_sql"]:
            if self.a.eval_now:
                try:
                    rec["eval"] = self.evaluate(t, k, rec["final_sql"], seeds)
                except Exception as err:
                    rec["eval"] = {"error": str(err)[:500]}
            else:
                rec["eval"] = {"pending": True}
            try:
                rec["audit"] = self.audit(t, k, rec["final_sql"], seeds)
            except Exception as err:
                rec["audit"] = {"result": "error", "why": str(err)[:300]}
        if rec["final_sql"] and (rec.get("audit") or {}).get("result") == "clean":
            self.prev_sql[t] = (k, rec["final_sql"])
        if self.arm.get("feature_memory") and rec["final_sql"]:
            try:
                rec["learning"] = self.learn(t, k, rec, seeds, middle, agent, sid)
            except Exception as err:
                rec["learning"] = {"error": str(err)[:500]}
        if self.arm.get("ace"):
            try:
                rec["learning"] = self.ace_update(t, k, rec, msgs, agent)
            except Exception as err:
                rec["learning"] = {"error": str(err)[:500]}
        if self.gmem:
            ref = self.refs.get((t, k)) or {}
            best = rec["best_val"]
            label = best is not None and ref.get("val") is not None and (best > ref["val"] if higher else best < ref["val"])
            t0 = time.time()
            g = self.gmem.send({"op": "end", "label": label, "feedback": f"best validation {metric} {best}; reference {ref.get('val')}; "
                                f"session ended by {rec['stop']}"})
            gmem_tokens = [gmem_tokens[0] + g.get("prompt_tokens", 0), gmem_tokens[1] + g.get("completion_tokens", 0)]
            rec["learning"] = {"seconds": time.time() - t0, "input_tokens": gmem_tokens[0], "output_tokens": gmem_tokens[1],
                               "label": label, "memory_size": g.get("memory_size"), "error": g.get("error")}
        sub_calls = rec.get("llm_sub") or []
        rec["totals"] = {
            # AgentSM's schema-linking sub-agent and SQL repair calls are counted here (they are not in the planner budget)
            "llm_calls": len(rec["llm"]) + len(sub_calls),
            "planner_llm_calls": len(rec["llm"]),
            "tool_calls": len(rec["tools"]) + sum(x.get("sub_tool_calls", 0) for x in rec["tools"]),
            "tool_calls_by_category": {c: sum(1 for x in rec["tools"] if x.get("category") == c) for c in ("schema", "probe", "validate", "memory", "submit")},
            "input_tokens": sum(x["input_tokens"] for x in rec["llm"] + sub_calls),
            "output_tokens": sum(x["output_tokens"] for x in rec["llm"] + sub_calls),
            "llm_seconds": sum(x["seconds"] for x in rec["llm"] + sub_calls),
            "llm_retry_seconds": sum(x.get("retry_seconds", 0) for x in rec["llm"] + sub_calls),
            "tool_seconds": sum(x["seconds"] for x in rec["tools"]),
            "validation_sql_seconds": sum(x.get("sql_seconds", 0) for x in rec["validations"]),
            "validation_train_seconds": sum(x.get("train_seconds", 0) for x in rec["validations"]),
        }
        rec["totals"]["tokens"] = rec["totals"]["input_tokens"] + rec["totals"]["output_tokens"]
        lr = rec.get("learning") or {}
        # learning is charged to the session that triggered it (README §1.4); its time is background work, reported apart
        rec["totals"]["learn_tokens"] = lr.get("input_tokens", 0) + lr.get("output_tokens", 0)
        rec["totals"]["learn_seconds"] = lr.get("seconds", 0)
        rec["totals"]["tokens_with_learning"] = rec["totals"]["tokens"] + rec["totals"]["learn_tokens"]
        rec["messages"] = msgs
        with open(os.path.join(self.a.out, "sessions", f"{tname(t)}-k{k}.json"), "w") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1, default=str)
        partial = os.path.join(self.a.out, "sessions", f"{tname(t)}-k{k}.partial.json")
        if os.path.exists(partial):
            os.remove(partial)
        ev = rec.get("eval") or {}
        log(f"{t} k{k}: stop={rec['stop']} llm={rec['totals']['llm_calls']} tools={rec['totals']['tool_calls']} "
            f"tok={rec['totals']['tokens']} t={rec['agent_seconds']:.0f}s val={best} test={ev.get('test')} audit={(rec.get('audit') or {}).get('result')}")
        return rec

    def evaluate_after_run(self, ks):
        """Test scores of every session, after the last cutoff, on the database as it was at the session's cutoff: views
        that keep the rows with time <= that cutoff's test timestamp, which are exactly the rows the database held then
        (the template holds time <= test_1 without null times, every append adds (previous, current]). The seed tables
        of the cutoff are rebuilt and the final SQL is scored as `evaluate` scores it at the end of a session."""
        t0 = time.time()
        for k in ks:
            todo = [(f, json.load(open(f))) for f in glob.glob(os.path.join(self.a.out, "sessions", f"*-k{k}.json"))]
            todo = [(f, r) for f, r in todo if r.get("final_sql") and (r.get("eval") or {}).get("pending")]
            if not todo:
                continue
            cut = next(iter(self.tasks.values()))["cutoffs"][k - 1]["test_timestamp"]
            schema = f"replay_k{k}"
            seeds = self.seed_tables(k)
            with psycopg.connect(self.url, autocommit=True) as con:
                con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
                con.execute(f"CREATE SCHEMA {schema}")
                for name, spec in self.manifest["tables"].items():
                    tc = spec.get("time_col")
                    cond = f" WHERE {tc.lower()} <= '{pd.Timestamp(cut)}'" if tc else ""
                    con.execute(f"CREATE VIEW {schema}.{name.lower()} AS SELECT * FROM public.{name.lower()}{cond}")
            try:
                for f, r in todo:
                    sql = re.sub(r"\bpublic\s*\.", f"{schema}.", r["final_sql"], flags=re.I)
                    try:
                        r["eval"] = {**self.evaluate(r["task"], k, sql, seeds[r["task"]], search_path=f"{schema}, public"), "after_run": True}
                    except Exception as err:
                        r["eval"] = {"error": str(err)[:500], "after_run": True}
                    with open(f, "w") as fh:
                        json.dump(r, fh, ensure_ascii=False, indent=1, default=str)
                    log(f"{r['task']} k{k}: test={r['eval'].get('test')}")
            finally:
                with psycopg.connect(self.url, autocommit=True) as con:
                    con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        log(f"test scores after the run: {time.time() - t0:.0f}s")

    def learn(self, t, k, rec, seeds, middle, agent, sid):
        """Learning after a session (README §1.6, amended before any P2 result): when the submission beats the reference.
        Columns the audit found leaking are left out of the extractor's input; every definition still has to pass F1-F4,
        and a leaking column cannot pass F3 (the compiled SQL is bounded by seed_time) or F4."""
        e = self.tasks[t]
        ec = e["entity_col"].lower()
        ref = self.refs.get((t, k)) or {}
        best, higher = rec["best_val"], rec["higher_is_better"]
        beats = best is not None and ref.get("val") is not None and (best > ref["val"] if higher else best < ref["val"])
        audit = rec.get("audit") or {}
        if not beats:
            return {"skipped": "validation score not better than the reference"}
        leaking = {c.lower() for c in audit.get("columns_differing") or []}
        imp = next((v.get("importance") for v in reversed(rec["validations"]) if v.get("sql") == rec["final_sql"] and v.get("importance")), [])
        imp = [c for c in imp if c.lower() not in leaking]
        tstar = seeds["train_sample"]["seed_time"].max()
        sub = seeds["train_sample"][seeds["train_sample"]["seed_time"] == tstar].sort_values(ec).head(AUDIT_SEEDS)
        schema = f"learn_{tname(t)}_k{k}"
        with psycopg.connect(self.url, autocommit=True) as con:
            con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            con.execute(f"CREATE SCHEMA {schema}")
            for name, spec in self.manifest["tables"].items():
                tc = spec.get("time_col")
                cond = f" WHERE {tc.lower()} <= '{tstar}'" if tc else ""
                con.execute(f"CREATE VIEW {schema}.{name.lower()} AS SELECT * FROM public.{name.lower()}{cond}")
            con.execute(f"CREATE TABLE {schema}.seeds AS SELECT * FROM task.{tname(t)}_train_sample WHERE false")
            copy_rows(con, f"{schema}.seeds", sub)
        body = {"agent": agent, "session": sid, "task": t, "description": self.task_desc[t]["description"],
                "cutoff": e["cutoffs"][k - 1]["test_timestamp"], "seed_key": ec, "entity_table": e["entity_table"].lower(),
                "entity_key": self.manifest["tables"][e["entity_table"]]["pkey"].lower(), "sql": rec["final_sql"], "importance": imp,
                "seeds": f"(select * from task.{tname(t)}_train_sample order by {ec}, seed_time limit {AUDIT_SEEDS})",
                "audit_schema": schema, "audit_seeds": f"(select * from {schema}.seeds)", "val_score": best, "metric": rec["metric"],
                "audit_clean": audit.get("result") == "clean", "val_table": f"task.{tname(t)}_val"}
        t0 = time.time()
        try:
            r = middle.post("/v1/learn_features", body)
        finally:
            with psycopg.connect(self.url, autocommit=True) as con:
                con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        ex = r.get("extraction") or {}
        events = [{k2: f.get(k2) for k2 in ("event", "key", "revision", "failed_gate", "reason")} for f in r.get("features") or []]
        log(f"{t} k{k}: learning {len(events)} drafts -> {sum(1 for x in events if x['event'] in ('promoted', 'corroborated'))} published")
        return {"seconds": time.time() - t0, "input_tokens": ex.get("input_tokens", 0), "output_tokens": ex.get("output_tokens", 0),
                "events": events, "program": r.get("program"), "error": r.get("error"), "audit": audit.get("result"),
                "excluded_leaking_columns": sorted(leaking), "raw": r}

    def agentsm_sql(self, middle, agent, sid, args, rec):
        """AgentSM's SQL tool: a failing statement is repaired once by the model and run again."""
        import agentsm

        try:
            out = middle.call("run_sql", agent, sid, sid, args)
        except Exception as err:
            out = {"error": f"{err}"}
        if isinstance(out, dict) and out.get("error") and args.get("sql"):
            sub = []
            fixed = agentsm.repair_sql(self.llm, args["sql"], out["error"], sub)
            rec.setdefault("llm_sub", []).extend({**x, "role": "sql_repair"} for x in sub)
            try:
                out2 = middle.call("run_sql", agent, sid, sid, {**args, "sql": fixed})
            except Exception as err:
                out2 = {"error": f"{err}"}
            out = {**out2, "repaired_sql": fixed, "original_error": out["error"]}
        return out

    def ace_update(self, t, k, rec, msgs, agent):
        """ACE after a session (online, no ground truth): Reflector (REFLECTOR_PROMPT_NO_GT), counters, Curator
        (CURATOR_PROMPT_NO_GT, ADD operations), each one call to the agent's model at temperature 0."""
        playbook = self.playbooks.get(agent, ACE_EMPTY_PLAYBOOK)
        self.ace_steps[agent] = self.ace_steps.get(agent, 0) + 1
        e = self.tasks[t]
        question = f"{self.task_desc[t]['description']} (task {t}, cutoff {e['cutoffs'][k - 1]['test_timestamp'][:10]})"
        parts = []
        for m in msgs[1:]:
            if m["role"] == "assistant":
                if m.get("content"):
                    parts.append(f"ASSISTANT: {m['content']}")
                for c in m.get("tool_calls") or []:
                    parts.append(f"TOOL CALL {c['function']['name']}: {c['function'].get('arguments', '')}")
            elif m["role"] == "tool":
                parts.append(f"TOOL OUTPUT: {m['content'][:TOOL_OUTPUT_CHARS]}")
            else:
                parts.append(f"{m['role'].upper()}: {m['content']}")
        trace = "\n".join(parts)
        vals = [f"validation {i + 1}: " + (f"{rec['metric']} = {v['val']:.5f}" if "val" in v else f"error: {v.get('error')}")
                for i, v in enumerate(rec["validations"])]
        feedback = "\n".join(vals + [f"best validation {rec['metric']}: {rec['best_val']}", f"session ended by: {rec['stop']}"])
        bullets = ace_pb.extract_playbook_bullets(playbook, rec.get("bullet_ids") or [])
        t0, tok_in, tok_out = time.time(), 0, 0
        r = self.llm.chat([{"role": "user", "content": ace_reflector.REFLECTOR_PROMPT_NO_GT.format(
            question, trace, rec.get("final_sql") or "(no features submitted)", feedback, bullets)}], temperature=0)
        tok_in, tok_out = tok_in + r["input_tokens"], tok_out + r["output_tokens"]
        reflection = r["message"].get("content") or ""
        parsed = ace_pb.extract_json_from_text(reflection) or {}
        tags = parsed.get("bullet_tags") or [] if isinstance(parsed, dict) else []
        if tags:
            playbook = ace_pb.update_bullet_counts(playbook, tags)
        r = self.llm.chat([{"role": "user", "content": ace_curator.CURATOR_PROMPT_NO_GT.format(
            current_step=self.ace_steps[agent], total_samples=self.timeline["K"], token_budget=ACE_TOKEN_BUDGET,
            playbook_stats=json.dumps(ace_pb.get_playbook_stats(playbook), indent=2), recent_reflection=reflection,
            current_playbook=playbook, question_context=question)}], temperature=0)
        tok_in, tok_out = tok_in + r["input_tokens"], tok_out + r["output_tokens"]
        cur = ace_pb.extract_json_from_text(r["message"].get("content") or "") or {}
        ops = [o for o in (cur.get("operations") or []) if isinstance(o, dict) and o.get("type") == "ADD"] if isinstance(cur, dict) else []
        if ops:
            playbook, _ = ace_pb.apply_curator_operations(playbook, ops, ace_pb.get_next_global_id(playbook))
        self.playbooks[agent] = playbook
        os.makedirs(os.path.join(self.a.out, "playbooks"), exist_ok=True)
        with open(os.path.join(self.a.out, "playbooks", f"{agent}-k{k}.txt"), "w") as f:
            f.write(playbook)
        n = ace_pb.get_playbook_stats(playbook)["total_bullets"]
        log(f"{t} k{k}: ACE {len(tags)} tags, {len(ops)} additions, playbook {n} bullets")
        return {"seconds": time.time() - t0, "input_tokens": tok_in, "output_tokens": tok_out, "bullet_tags": tags,
                "operations": ops, "playbook_bullets": n}

    def main(self):
        a = self.a
        arm = ARMS[a.arm]
        log(f"run {a.arm} r{a.run}: database {self.db_name} from {a.template}")
        create_run_db(self.url_admin, a.template, self.db_name)
        middle = None
        summary = {"arm": a.arm, "run": a.run, "db": self.db_name, "template": a.template, "smoke": a.smoke, "settings": {
            "MAX_LLM_CALLS": MAX_LLM_CALLS, "MAX_VALIDATIONS": MAX_VALIDATIONS, "PATIENCE": PATIENCE, "SAMPLE_SIZE": SAMPLE_SIZE,
            "LGB_PARAMS": LGB_PARAMS, "model": self.llm.model, "reasoning_effort": self.llm.effort,
            "test_scores": "now" if a.eval_now else "after the run"}, "cutoffs": []}
        try:
            middle = Middle(self.url, arm["middle_mode"], a.out, a.port or 18100 + (os.getpid() % 800), a.llm if arm.get("extractor") else None, a.reasoning_effort, self.llm.prefix)
            if arm.get("gmemory"):
                self.gmem = GMemoryService(self.env, a.out, self.llm)
            if arm.get("agentsm"):
                import agentsm

                self.asm = agentsm.Memory(a.agentsm_memory, self, a.out)
            ks = range(1, self.timeline["K"] + 1) if not a.cutoffs else [int(x) for x in a.cutoffs]
            prev = None
            for k in ks:
                cut = next(iter(self.tasks.values()))["cutoffs"][k - 1]
                rec = {"k": k, "test_timestamp": cut["test_timestamp"]}
                if prev is not None:
                    rec["append"] = self.append(pd.Timestamp(prev), pd.Timestamp(cut["test_timestamp"]))
                    log(f"k{k}: appended {rec['append']['rows']}")
                elif k > 1:
                    first = next(iter(self.tasks.values()))["cutoffs"][0]["test_timestamp"]
                    rec["append"] = self.append(pd.Timestamp(first), pd.Timestamp(cut["test_timestamp"]))
                prev = cut["test_timestamp"]
                seeds = self.seed_tables(k)
                rec["reference"] = {}
                for t in self.tasks:
                    try:
                        rec["reference"][t] = self.evaluate(t, k, self.reference_sql(t), seeds[t])
                    except Exception as err:
                        rec["reference"][t] = {"error": str(err)[:300]}
                log(f"k{k}: reference {json.dumps({t: (v.get('val'), v.get('test')) for t, v in rec['reference'].items()})}")
                self.refs.update({(t, k): v for t, v in rec["reference"].items()})
                if k > 1:
                    with cf.ThreadPoolExecutor(len(self.tasks)) as ex:
                        goals = {t: ex.submit(self.incumbent, t, k, seeds[t]) for t in self.tasks}
                        self.targets.update({(t, k): g.result() for t, g in goals.items()})
                    log(f"k{k}: goals {json.dumps({t: (self.targets[(t, k)] or {}).get('val') for t in self.tasks})}")
                order = list(self.tasks)
                random.Random(a.run * 1000 + k).shuffle(order)
                rec["order"] = order
                if arm["parallel_ok"] and a.parallel > 1:
                    with cf.ThreadPoolExecutor(a.parallel) as ex:
                        futs = [ex.submit(self.session, t, k, seeds[t], middle) for t in order]
                        for f in futs:
                            f.result()
                else:
                    for t in order:
                        self.session(t, k, seeds[t], middle)
                summary["cutoffs"].append(rec)
                with open(os.path.join(a.out, "run.json"), "w") as f:
                    json.dump(summary, f, indent=1, default=str)
            if not a.eval_now:
                self.evaluate_after_run(ks)
        except Exception:
            traceback.print_exc()
            summary["error"] = traceback.format_exc()[-2000:]
            raise
        finally:
            with open(os.path.join(a.out, "run.json"), "w") as f:
                json.dump(summary, f, indent=1, default=str)
            if self.gmem:
                self.gmem.close()
            if self.asm:
                self.asm.close()
            if middle:
                if arm.get("feature_memory"):
                    try:
                        with open(os.path.join(a.out, "features.json"), "w") as f:
                            json.dump(middle.get("/v1/features"), f, ensure_ascii=False, indent=1)
                    except Exception as err:
                        log(f"could not export features: {err}")
                middle.close()
            if not a.keep_db:
                drop_db(self.url_admin, self.db_name)
        log("run done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(ARMS))
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--prep", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--cutoffs", nargs="*", help="subset of cutoffs (smoke tests)")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--port", type=int)
    ap.add_argument("--keep-db", action="store_true")
    ap.add_argument("--agentsm-memory", help="memory.json from tools/relbench/agentsm.py build (arm agentsm)")
    ap.add_argument("--targets-from", help="run folder whose sessions at the cutoff before the first one give the retraining goals")
    ap.add_argument("--llm", default="deepseek", choices=list(PROVIDERS), help="model service (pilot: river; since 10-21: deepseek)")
    ap.add_argument("--reasoning-effort", default="high",
                    help="reasoning effort of the agents and of MAVRA's extractor; DeepSeek's API offers low/high/max and treats medium as high")
    ap.add_argument("--eval-now", action="store_true", help="score each session on the test seeds right after it (default: after the run)")
    ap.add_argument("--smoke", action="store_true", help="pipeline check only: 8 LLM calls, 2 validations; results are not used")
    a = ap.parse_args()
    if a.smoke:
        global MAX_LLM_CALLS, MAX_VALIDATIONS
        MAX_LLM_CALLS, MAX_VALIDATIONS = 8, 2
    os.makedirs(a.out, exist_ok=True)
    Run(a).main()


if __name__ == "__main__":
    main()

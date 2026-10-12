"""Run the official ReFoRCE pipeline (third_party/reforce, unmodified) on one question over PostgreSQL.

metric-bench (modes reforce, reforce-traj, reforce-static, reforce-mavra) starts this script once per scored question
and writes one JSON request to stdin:
  {"ex_id", "question", "knowledge", "tables", "dsn", "work_dir", "provider", "votes", "max_iter", "sql_timeout_secs"}
The script writes ReFoRCE's input (prompts.txt: each table with column types, column comments and three sample rows, then
the external-knowledge slot, then the table list), runs the four steps of ReFoRCE's scripts/run_main.sh for this one
question, and prints one JSON line on stdout: the answer (first cell of the chosen result), the chosen SQL, the step that
decided, the number of candidates, LLM calls and tokens. ReFoRCE's own prints and logs go to stderr and work_dir.

Usage: PYTHONPATH=.pydeps-reforce python3 tools/reforce/mavra_reforce.py < request.json
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# httpx would route through the SOCKS proxy of ALL_PROXY (needs socksio); use HTTP(S)_PROXY like the Rust client
for k in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

OUT = sys.stdout
sys.stdout = sys.stderr


def stub(name, parent=None):
    """ReFoRCE's sql.py imports the BigQuery and Snowflake SDKs at module level; only their backends use them."""
    m = types.ModuleType(name)
    sys.modules[name] = m
    if parent is not None:
        setattr(sys.modules[parent], name.rsplit(".", 1)[1], m)
    return m


stub("google")
stub("google.cloud", "google")
stub("google.cloud.bigquery", "google.cloud")
stub("google.oauth2", "google")
stub("google.oauth2.service_account", "google.oauth2")
stub("snowflake")
stub("snowflake.connector", "snowflake")
sys.path.insert(0, str(ROOT / "third_party" / "reforce"))

import psycopg  # noqa: E402
from openai import OpenAI  # noqa: E402

import agent as r_agent  # noqa: E402
import chat as r_chat  # noqa: E402
import prompt as r_prompt  # noqa: E402
import run as r_run  # noqa: E402
import sql as r_sql  # noqa: E402
import utils as r_utils  # noqa: E402

REQ = json.load(sys.stdin)


def env_config(prefix):
    cfg = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip("\"'")
    cfg.update({k: v for k, v in os.environ.items() if v})
    return lambda k: cfg.get(f"{prefix}_{k}") or None


get = env_config(REQ.get("provider", "happy").upper())
MODEL = get("MODEL")
REQUIRE = get("REQUIRE_MODEL")
EXTRA = {}
if get("REASONING_EFFORT"):
    EXTRA["reasoning_effort"] = get("REASONING_EFFORT")
if get("THINKING"):
    EXTRA["thinking"] = {"type": get("THINKING")}
CLIENT = OpenAI(base_url=get("BASE_URL"), api_key=get("API_KEY"), timeout=600, max_retries=6)

LOCK = threading.Lock()
STATS = collections.Counter()
SERVED = collections.Counter()


class TrackedChat(r_chat.BaseChat):
    """ReFoRCE's GPTChat for an OpenAI-compatible endpoint: same message handling, plus token counts and the
    served-model check of the Rust provider (replies from another model are discarded and the request is resent)."""

    def __init__(self, azure=False, model=None, temperature=1.0):
        super().__init__(MODEL, temperature)

    def get_response(self, prompt):
        self.messages.append({"role": "user", "content": prompt})
        for _ in range(6):
            try:
                r = CLIENT.chat.completions.create(model=self.model, messages=self.messages, temperature=self.temperature,
                                                   extra_body=EXTRA or None)
            except Exception:
                with LOCK:
                    STATS["llm_errors"] += 1
                raise
            u = r.usage
            details = getattr(u, "completion_tokens_details", None) if u else None
            with LOCK:
                if REQUIRE and r.model != REQUIRE:
                    STATS["discarded"] += 1
                    STATS["discarded_tokens"] += (u.total_tokens if u else 0)
                    continue
                STATS["calls"] += 1
                STATS["input_tokens"] += u.prompt_tokens if u else 0
                STATS["output_tokens"] += u.completion_tokens if u else 0
                STATS["reasoning_tokens"] += (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
                SERVED[r.model or "?"] += 1
            break
        else:
            raise RuntimeError(f"served model differs from {REQUIRE} in 6 replies")
        content = r.choices[0].message.content or ""
        self.messages.append({"role": "assistant", "content": content})
        return content


# ───────── PostgreSQL backend for ReFoRCE's SqlEnv ─────────

DSN = REQ["dsn"]
TIMEOUT_MS = int(REQ.get("sql_timeout_secs", 60)) * 1000


def exec_sql_pg(self, sql_query, save_path, max_len):
    cursor = self.conns["pg"].cursor()
    try:
        cursor.execute(sql_query)
        if cursor.description is None:
            columns, rows = [], []
        else:
            columns = [d.name for d in cursor.description]
            rows = self.get_rows(cursor, max_len)
    except Exception as e:  # noqa: BLE001 — returned to ReFoRCE as an execution error, as in its SQLite backend
        return "##ERROR##" + str(e)
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass
    if not rows:
        return "No data found for the specified query.\n"
    csv_content = self.get_csv(columns, rows)
    if save_path:
        with open(save_path, "w", newline="") as f:
            f.write(csv_content)
        return 0
    return r_utils.hard_cut(csv_content, max_len)


_execute_sql_api = r_sql.SqlEnv.execute_sql_api


def execute_sql_api(self, sql_query, ex_id, save_path=None, api="sqlite", max_len=30000, sqlite_path=None, timeout=300):
    if api != "postgres":
        return _execute_sql_api(self, sql_query, ex_id, save_path, api, max_len, sqlite_path, timeout)
    if "pg" not in self.conns:
        self.conns["pg"] = psycopg.connect(
            DSN, autocommit=True, options=f"-c default_transaction_read_only=on -c statement_timeout={TIMEOUT_MS}")
    with LOCK:
        STATS["sql"] += 1
    result = exec_sql_pg(self, sql_query, save_path, max_len)
    if "##ERROR##" in str(result):
        with LOCK:
            STATS["sql_errors"] += 1
        return {"status": "error", "error_msg": str(result)}
    return str(result)


r_sql.SqlEnv.execute_sql_api = execute_sql_api


def get_api_name(sql_data):
    return "postgres" if sql_data.startswith("pg") else _get_api_name(sql_data)


_get_api_name = r_utils.get_api_name
r_utils.get_api_name = get_api_name
r_agent.get_api_name = get_api_name

_basic = r_prompt.Prompts.get_prompt_dialect_basic
_nested = r_prompt.Prompts.get_prompt_dialect_nested


def dialect_basic(self, api):
    if api == "postgres":
        return ("```sql\nSELECT DISTINCT \"column_name\" FROM \"table_name\" WHERE ... ``` (PostgreSQL. Replace \"table_name\" "
                "with the actual table name; table and column names are lower case.)")
    return _basic(self, api)


def dialect_nested(self, api):
    if api == "postgres":
        return ("Extract a specific key from a JSON column: SELECT t.\"column_name\" ->> 'key_name' AS \"value\" FROM "
                "\"table_name\" AS t;\n")
    return _nested(self, api)


r_prompt.Prompts.get_prompt_dialect_basic = dialect_basic
r_prompt.Prompts.get_prompt_dialect_nested = dialect_nested

# Format restriction (ReFoRCE's own input): one row, one column named answer, as the question asks for one value
ANSWER_FORMAT = "```csv\nanswer\n```"
r_agent.REFORCE.format_answer = lambda self, task, chat_session: ANSWER_FORMAT


# ───────── ReFoRCE input ─────────

def table_prompt(conn, tables):
    """prompts.txt in ReFoRCE's layout for Spider 2.0 (table, columns with type and description, sample rows, separator)."""
    out = ""
    for t in tables:
        cols = conn.execute(
            "select c.column_name, c.data_type, col_description(format('%%I', c.table_name)::regclass, c.ordinal_position) "
            "from information_schema.columns c where c.table_schema = 'public' and c.table_name = %s order by c.ordinal_position",
            (t,)).fetchall()
        comment = conn.execute("select obj_description(format('%%I', %s::text)::regclass, 'pg_class')", (t,)).fetchone()[0]
        out += "Table full name: " + t + "\n"
        if comment:
            out += "Table description: " + comment + "\n"
        for name, typ, des in cols:
            out += "Column name: " + name + " Type: " + typ + (" Description: " + des if des else "") + "\n"
        cur = conn.execute(f'select * from "{t}" limit 3')
        names = [d.name for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
        out += "Sample rows:\n" + json.dumps(rows, ensure_ascii=False, default=str) + "\n"
        out += "\n" + "-" * 50 + "\n"
    return out


def main():
    t0 = time.time()
    ex = REQ["ex_id"]
    work = Path(REQ["work_dir"])
    examples, output = work / "examples", work / "output"
    (examples / ex).mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(DSN, autocommit=True, options="-c default_transaction_read_only=on") as conn:
        prompts = table_prompt(conn, REQ["tables"])
    prompts = r_utils.clear_sample_rows(prompts, byte_limit=1000)
    prompts += f"External knowledge that might be helpful: \n{REQ.get('knowledge') or None}\n"
    prompts += "The table structure information is (table names): \n" + str(REQ["tables"]) + "\n"
    (examples / ex / "prompts.txt").write_text(prompts, encoding="utf-8")

    r_run.prompt_all = r_prompt.Prompts()
    r_run.full_db_id, r_run.full_tb_info, r_run.full_gold_sql = {}, {}, {}
    r_run.task_dict = {ex: REQ["question"]}
    r_run.dictionaries = [ex]
    r_run.ChatClass = TrackedChat
    base = dict(task="lite", subtask=None, db_path=str(examples), output_path=str(output),
                do_format_restriction=True, use_gold_format=False, format_model=MODEL,
                do_column_exploration=False, column_exploration_model=MODEL,
                do_self_refinement=False, do_self_consistency=False, generation_model=None, azure=False,
                max_iter=int(REQ.get("max_iter", 5)), temperature=1.0, early_stop=False,
                do_vote=True, revote=False, num_votes=int(REQ.get("votes", 8)), random_vote_for_tie=False, model_vote=None,
                final_choose=False, save_all_results=False, rerun=False, overwrite_unfinished=False, num_workers=1,
                omnisql_format_pth=None, gold_result_path=str(work / "gold"))
    # The four steps of scripts/run_main.sh, for this one question
    steps = [
        ("vote", dict(do_self_refinement=True, generation_model=MODEL, early_stop=True)),
        ("explore", dict(do_self_refinement=True, generation_model=MODEL, do_column_exploration=True, early_stop=True,
                         rerun=True, overwrite_unfinished=True)),
        ("tie", dict(random_vote_for_tie=True)),
        ("final", dict(random_vote_for_tie=True, final_choose=True)),
    ]
    out_dir = output / ex
    decided = None
    for name, extra in steps:
        r_run.args = argparse.Namespace(**{**base, **extra})
        r_run.process_sql_data(ex)
        if (out_dir / "result.sql").exists():
            decided = name
            break
    answer, header, sql = None, None, None
    if (out_dir / "result.csv").exists():
        with open(out_dir / "result.csv", newline="") as f:
            rows = list(csv.reader(f))
        if rows:
            header = rows[0]
        if len(rows) > 1 and rows[1]:
            answer = rows[1][0]
    if (out_dir / "result.sql").exists():
        sql = (out_dir / "result.sql").read_text()
    candidates = len(glob.glob(str(out_dir / "[0-9]*result.sql")))
    return {"answer": answer, "header": header, "sql": sql, "decided": decided, "candidates": candidates,
            "seconds": round(time.time() - t0, 2), "prompt_chars": len(prompts)}


if __name__ == "__main__":
    try:
        res = main()
    except Exception as e:  # noqa: BLE001 — reported to metric-bench as an error, like a failed agent run
        import traceback
        traceback.print_exc()
        res = {"error": f"{type(e).__name__}: {e}"}
    res.update({"llm_calls": STATS["calls"], "input_tokens": STATS["input_tokens"], "output_tokens": STATS["output_tokens"],
                "reasoning_tokens": STATS["reasoning_tokens"], "discarded": STATS["discarded"],
                "discarded_tokens": STATS["discarded_tokens"], "llm_errors": STATS["llm_errors"], "sql_runs": STATS["sql"],
                "sql_errors": STATS["sql_errors"], "served_models": dict(SERVED)})
    OUT.write(json.dumps(res, ensure_ascii=False) + "\n")
    OUT.flush()

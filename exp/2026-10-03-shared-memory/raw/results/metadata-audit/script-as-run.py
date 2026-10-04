#!/usr/bin/env python3
"""Exploratory HTTP audit of profile sharing and metadata freshness boundaries.

Uses a disposable database only. Credentials stay in the environment and are
never written to the report or passed on a command line. This is a diagnostic,
not an LLM benchmark or a claim that live catalog refresh has been implemented.
"""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="results/shared-memory-main/inputs/agentdb-mid")
    parser.add_argument("--out", default="results/metadata-audit")
    args = parser.parse_args()
    out, binary = Path(args.out), Path(args.binary).resolve()
    if out.exists():
        raise SystemExit("Use a fresh output directory; preserve prior diagnostic results.")
    out.mkdir(parents=True)
    env = os.environ.copy()
    for line in Path(".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env.setdefault(k, v.strip().strip('"').strip("'"))
    url = urllib.parse.urlparse(env["AGENTDB_URL"])
    password_env = env.copy()
    password_env["PGPASSWORD"] = urllib.parse.unquote(url.password or "")
    dbname = f"agentdb_metadata_{os.getpid()}_{time.time_ns()}"
    pg = ["psql", "-w", "-X", "-Atq", "-v", "ON_ERROR_STOP=1", "-h", url.hostname,
          "-p", str(url.port or 5432), "-U", urllib.parse.unquote(url.username or "postgres")]

    def sql(text, database=dbname):
        return subprocess.check_output(pg+["-d", database, "-c", text], env=password_env, text=True)

    sql(f"create database {dbname}", url.path.lstrip("/"))
    env["AGENTDB_URL"] = urllib.parse.urlunparse(url._replace(path="/"+dbname))
    server = None
    records = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = (out/"server.log").open("w")
    report = {"binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "rows": 100_000,
              "methodology": "Exploratory diagnostic predicted by code inspection; no LLM. Fresh HTTP agents share one process. DML invalidation uses explicit ETL batch notification. Comment-only and additive DDL changes test startup-catalog boundaries. Restart is a separate intervention, not live refresh."}
    try:
        sql("create table store_returns (sr_ticket_number int, sr_item_sk int, sr_return_amt numeric); "
            "insert into store_returns select x, 1, x::numeric from generate_series(1,100000) x; "
            "comment on column store_returns.sr_return_amt is 'Amount excluding tax'; analyze store_returns;")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        def request(path, body=None):
            req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=30) as response:
                return json.load(response)

        def start():
            process = subprocess.Popen([str(binary), "--pool", "4", "serve", "--addr", f"127.0.0.1:{port}"],
                                       env=env, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("HTTP server exited before readiness; inspect server.log")
                try:
                    request("/v1/tools")
                    return process
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            process.terminate(); process.wait(timeout=10)
            raise RuntimeError("HTTP server readiness timeout")

        server = start()

        def describe(stage):
            before = request("/v1/stats")["db"]
            answer = request("/v1/tools/describe_table", {"agent": stage, "session": "fresh", "task": stage,
                                                         "tables": ["store_returns"], "args": {"table": "store_returns"}})
            after = request("/v1/stats")["db"]
            records.append({"stage": stage, "response": answer,
                            "queries": after["queries"]-before["queries"],
                            "probe_queries": after["by_kind"]["probe"][0]-before["by_kind"]["probe"][0],
                            "db_ms": after["db_ms"]-before["db_ms"]})
            (out/"records.json").write_text(json.dumps(records, indent=2)+"\n")
            return answer

        first = describe("producer")
        shared = describe("new-consumer")
        sql("insert into store_returns values (100001,1,100001,'完成'); "
            "insert into etl_batch_log values ('store_returns',2,'DML audit',now()); analyze store_returns")
        time.sleep(0.3)
        dml = describe("after-notified-dml")
        sql("comment on column store_returns.sr_return_amt is 'Amount in cents excluding tax'")
        time.sleep(0.3)
        comment = describe("after-comment-only")
        sql("alter table store_returns add column sr_currency text default 'CNY'; "
            "comment on column store_returns.sr_currency is 'Currency code'; analyze store_returns")
        time.sleep(0.3)
        ddl = describe("after-additive-ddl")
        server.terminate(); server.wait(timeout=10); server = start()
        restarted = describe("after-explicit-restart")
        column = lambda v, name: next((x for x in v["profile"]["columns"] if x["name"] == name), None)
        report["findings"] = {
            "first_source": first["source"], "shared_source": shared["source"],
            "shared_probe_queries": records[1]["probe_queries"],
            "notified_dml_row_count": dml["profile"]["row_count"],
            "comment_only_fresh": column(comment, "sr_return_amt").get("comment") == "Amount in cents excluding tax",
            "additive_ddl_column_visible": column(ddl, "sr_currency") is not None,
            "restart_comment_fresh": column(restarted, "sr_return_amt").get("comment") == "Amount in cents excluding tax",
            "restart_column_visible": column(restarted, "sr_currency") is not None}
    finally:
        if server is not None and server.poll() is None:
            server.terminate(); server.wait(timeout=10)
        log.close()
        sql(f"drop database {dbname} with (force)", url.path.lstrip("/"))
        report["database_cleaned_up"] = True
        report["records"] = records
        (out/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report["findings"], indent=2))


if __name__ == "__main__":
    main()

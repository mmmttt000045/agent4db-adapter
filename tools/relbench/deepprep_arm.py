#!/usr/bin/env python3
"""DeepPrep (Fan et al., PVLDB 19(11), 2026) as a RelBench baseline (exp/2026-10-20-relbench/reproduction-notes.md).

DeepPrep's own code (third_party/deepprep, from ruc-datalab/DeepPrep @ b4e64b0) runs unchanged: its tree-based agentic
reasoning loop (TreeBasedAgenticReasoningAgent.reasoning_step: <think>, exploratory <operator> chains executed with
their observations, a final <solution> chain ending in Terminate, at most max_explore_turn exploration turns and
agent_max_err_cnt errors per turn), its prompts (PromptGenerator.tree_based_agentic_reasoning_generate), its 31
operators and its rule executor, with the settings of its API-model configuration
(_CONFIG_tree_based_agentic_reasoning_claude.yaml: max_explore_turn 5, max_explore_op 50, agent_max_err_cnt 5).
Replaced, as the paper's environment cannot run here: the LLM client (the study's model and service, every call
recorded), the FastAPI/Redis execution service (the same executor calls, in process: copy, step, simulate), and the
target-table description (the task's feature table; DeepPrep's benchmarks give a fixed target schema). Two changes
only speed it up and leave what the agent sees unchanged: tables are printed from their first rows (df_to_cotable
deep-copies the whole table to print its first rows), and a simulation shares the unmodified tables instead of
copying all of them (the operators copy the table they change).

Per task and cutoff (DeepPrep keeps nothing between tasks): the input tables are the database at the cutoff (rows
dated at or before test_k), plus "seeds" (entity key, seed_time): 2,000 training seeds while exploring, then the
50,000-seed training sample, the validation seeds and the test seeds for the final solution. The solution's table is
the feature table; the study's fixed LightGBM gives the validation and test scores. A solution is checked for leakage
as every method's features are (recomputed with rows after the latest training seed time hidden); a leaking solution
is returned to the agent as an error, as DeepPrep returns any failed solution.

  python3 tools/relbench/deepprep_arm.py --data results/relbench-data/rel-stack --prep results/relbench-data/rel-stack-prep \
      --out results/relbench-pilot3/deepprep-rel-stack-r1
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402

DEEPPREP = os.path.join(ROOT, "third_party", "deepprep")
CONFIG = "tree_based_agentic_reasoning_claude"  # DeepPrep's configuration for API models
EXPLORE_SEEDS = 2000
AUDIT_SEEDS = H.AUDIT_LEAK_SEEDS


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def import_deepprep(workdir):
    """DeepPrep resolves its configuration and logs relative to its own directory: run a copy in a scratch folder."""
    shutil.copytree(DEEPPREP, workdir, dirs_exist_ok=True)
    base = os.path.join(workdir, "_config", "base_config.yaml")
    text = open(base).read()
    # no benchmark data is loaded at import (DataPool); caches and logs stay in the scratch folder
    text = text.replace("data_root: <local_data_root>/autoprep2", f"data_root: {workdir}/_data")
    text = text.replace("filecachedir: ./_tmp", f"filecachedir: {workdir}/_tmp")
    text = text.split("total_benchmarks:")[0] + "total_benchmarks: []\nversion: 1.0.0\n"
    open(base, "w").write(text)
    # its API-model configuration lacks the display settings its server takes from the full one: DeepPrep's base defaults
    import yaml

    base_cfg = yaml.safe_load(open(base))
    path = os.path.join(workdir, "_config", f"_CONFIG_{CONFIG}.yaml")
    cfg = yaml.safe_load(open(path))
    cfg.update({k: v for k, v in base_cfg.items() if k not in cfg})
    yaml.safe_dump(cfg, open(path, "w"))
    # the released prompt loader splits every file name at "_" into agent and module; one system message of the release
    # has two underscores and stops the import, and the reasoning agent does not use it
    odd = os.path.join(workdir, "src", "prompt", "system_message", "TreeBasedAgenticReasoning_TreeBasedAgenticReasoning_Buildings.md")
    if os.path.exists(odd):
        os.rename(odd, odd + ".unused")
    os.makedirs(os.path.join(workdir, "_data"), exist_ok=True)
    os.makedirs(os.path.join(workdir, "_tmp", "schema_description"), exist_ok=True)
    os.chdir(workdir)
    sys.path.insert(0, workdir)
    import src.module.executor as dp_executor
    import src.tools.utils as dp_utils
    from src.agent.tree_based_agentic_reasoning import TreeBasedAgenticReasoningAgent
    from src.agent.base_agent import BaseAgent
    from src.data.trial import Trial, Task
    from src.physicalop import auto_parse_op, Terminate
    from src.tools.helper import Config

    printed = dp_utils.df_to_cotable

    def head_only(tbl, cut_line=10, cut_col=20, max_len=6000):
        if tbl is None or cut_line == -1:
            return printed(tbl, cut_line=cut_line, cut_col=cut_col, max_len=max_len)
        return printed(tbl.head(cut_line + 1), cut_line=cut_line, cut_col=cut_col, max_len=max_len)

    dp_executor.df_to_cotable = head_only
    import src.data.trial as dp_trial
    dp_trial.df_to_cotable = head_only
    return {"executor_mod": dp_executor, "Agent": TreeBasedAgenticReasoningAgent, "BaseAgent": BaseAgent, "Trial": Trial,
            "Task": Task, "auto_parse_op": auto_parse_op, "Terminate": Terminate, "Config": Config}


class LlmGone(BaseException):
    """The model service failed after all retries: not an Exception, so DeepPrep's error loop does not retry it."""


class StudyLlm:
    """DeepPrep's GPT.query interface over the study's model; every call is kept for the session's totals."""

    def __init__(self, llm):
        self.llm, self.calls = llm, []

    def query(self, messages, get_thinking=False):
        try:
            r = self.llm.chat(messages)
        except H.LlmUnavailable as err:
            raise LlmGone(str(err))
        m = r.pop("message")
        self.calls.append(r)
        out = m.get("content") or ""
        return (out, m.get("reasoning_content") or "") if get_thinking else out


class LocalClient:
    """The calls of DeepPrep's ApiClient that the reasoning agent makes, on DeepPrep's executor, in process."""

    def __init__(self, dp, executor, trials, tools):
        self.dp, self.executor, self.trials, self.tools = dp, executor, trials, tools

    def copy_trial(self, trial_id):
        old = self.trials[trial_id]
        new = self.dp["Trial"](exp_id=f"{trial_id}-copy{len(self.trials)}", task=old.task)
        new.tables = dict(old.tables)
        new.ops, new.obs = list(old.ops), list(old.obs)
        new.generated_tbls = dict(old.generated_tbls) if old.generated_tbls else {}
        self.trials[new.exp_id] = new
        return new.exp_id, old.task.id, old.task.split

    def add_step(self, trial_id, op, mode="rule"):
        t0 = time.time()
        trial = self.trials[trial_id]
        op_object = self.dp["auto_parse_op"](op)
        name, tbl = self.executor.execute_op(op_object, trial, mode)
        self.executor.step_op(op_object, trial, name, tbl)
        self.tools.append({"name": "add_step", "category": "probe", "seconds": time.time() - t0, "error": False})
        return "Step added successfully."

    def get_simulate_trial_exe_obs(self, trial_id, operators, mode="rule"):
        # app/server.py simulate_trial + app/client.py get_simulate_trial_exe_obs
        t0 = time.time()
        old = self.trials[trial_id]
        new = self.dp["Trial"](exp_id=f"sim-{trial_id}", task=old.task)
        new.tables = dict(old.tables)
        new.ops, new.obs = list(old.ops), list(old.obs)
        new.generated_tbls = dict(old.generated_tbls) if old.generated_tbls else {}
        error = False
        for i, op in enumerate(operators):
            try:
                op_object = self.dp["auto_parse_op"](op)
                name, tbl = self.executor.execute_op(op_object, new, mode)
                self.executor.step_op(op_object, new, name, tbl)
            except Exception as e:  # noqa: BLE001 - as the service: the error becomes the observation
                new.add_op(operators[i], f"Error raised when executing operator {i + 1}: {str(operators[i])}. Error: {str(e)}\n "
                                         "Since the error is raised, the following operators will not be executed!")
                error = True
                break
        self.tools.append({"name": "simulate", "category": "probe", "seconds": time.time() - t0, "error": error})
        return [(f"** Op {i + 1} **: {op}", f"** Output {i + 1} **: {ob}") for i, (op, ob) in enumerate(zip(new.ops, new.obs))]


def run_chain(dp, executor, tables, chain, task):
    """Execute a solution's operator chain on fresh tables and return the table its Terminate outputs."""
    trial = dp["Trial"](exp_id="final", task=task)
    trial.tables = dict(tables)
    out = None
    for op in [x.strip() for x in chain.split("-->") if x.strip()]:
        op_object = dp["auto_parse_op"](op)
        name, tbl = executor.execute_op(op_object, trial, "rule")
        executor.step_op(op_object, trial, name, tbl)
        if isinstance(op_object, dp["Terminate"]):
            names = op_object.result if isinstance(op_object.result, list) else [op_object.result]
            out = trial.tables.get(names[0], tbl) if names else tbl
    if out is None:
        raise ValueError("the solution has no Terminate operator")
    return out


def features_from(table, seeds, ec):
    """One numeric row per seed, in the seeds' order (the study's feature contract)."""
    df = table.copy()
    df.columns = [str(c) for c in df.columns]
    if ec not in df.columns or "seed_time" not in df.columns:
        raise ValueError(f"the target table needs columns {ec!r} and 'seed_time'; it has {list(df.columns)[:20]}")
    df["seed_time"] = pd.to_datetime(df["seed_time"])
    df = df.drop_duplicates([ec, "seed_time"])
    x = seeds[[ec, "seed_time"]].merge(df, on=[ec, "seed_time"], how="left").drop(columns=[ec, "seed_time"])
    keep = []
    for c in x.columns:
        if not pd.api.types.is_numeric_dtype(x[c]):
            conv = pd.to_numeric(x[c], errors="coerce")
            if conv.notna().sum() < x[c].notna().sum():
                continue
            x[c] = conv
        keep.append(c)
    x = x[keep[:H.MAX_FEATURES]].astype(float)
    if x.shape[1] == 0:
        x = pd.DataFrame({"constant": np.zeros(len(seeds))})
    return x


class Cell:
    def __init__(self, a):
        self.a = a
        self.manifest = __import__("yaml").safe_load(open(os.path.join(a.data, "manifest.yaml")))
        self.timeline = json.load(open(os.path.join(a.prep, "timeline.json")))
        self.tasks = {t: e for t, e in self.timeline["tasks"].items() if not a.tasks or t in a.tasks}
        self.desc = {t: __import__("yaml").safe_load(open(os.path.join(a.data, "tasks", t, "manifest.yaml"))) for t in self.tasks}
        env = H.load_env(os.path.join(ROOT, ".env"))
        self.llm = H.Llm(env, a.llm)

    def tables_at(self, upto):
        import pyarrow.parquet as pq

        out = {}
        for name, spec in self.manifest["tables"].items():
            path = os.path.join(self.a.data, "db", f"{name}.parquet")
            tc = spec.get("time_col")
            df = pq.read_table(path, filters=[(tc, "<=", upto)]).to_pandas() if tc else pd.read_parquet(path)
            df.columns = [c.lower() for c in df.columns]
            out[name.lower()] = df
        return out

    def seeds(self, t, k, split):
        e = self.tasks[t]
        df = pd.read_parquet(os.path.join(self.a.prep, "tasks", t, f"k{k}", f"{split}.parquet"))
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={e["time_col"].lower(): "seed_time"})
        df["seed_time"] = pd.to_datetime(df["seed_time"])
        if split == "train" and len(df) > H.SAMPLE_SIZE:
            df = df.iloc[np.random.RandomState(H.SAMPLE_SEED).permutation(len(df))[:H.SAMPLE_SIZE]].reset_index(drop=True)
        return df

    def target_description(self, t, tables):
        e = self.tasks[t]
        ec = e["entity_col"].lower()
        times = [f"{n.lower()}.{s['time_col'].lower()}" for n, s in self.manifest["tables"].items() if s.get("time_col")]
        keys = [f"{n.lower()}.{c.lower()} -> {p.lower()}" for n, s in self.manifest["tables"].items() for c, p in (s.get("fkeys") or {}).items()]
        return "\n".join([
            f"We transform the input tables to complete the task: {self.desc[t]['description'].strip()} The target table gives, for "
            f"every row of the table \"seeds\" (one entity \"{ec}\" at one time \"seed_time\"), numeric features of that entity that "
            f"help predict the task. A feature may only use rows of the other tables whose time is at or before that row's "
            f"seed_time (rows after seed_time must not be used). Time columns: {', '.join(times)}. Foreign keys: {', '.join(keys)}.",
            "The column schema of the target table is as follows:",
            f'- Name of Column: "{ec}"', "  - Description: the entity key, copied from seeds",
            '- Name of Column: "seed_time"', "  - Description: the seed time, copied from seeds",
            '- Name of Column: "<feature columns>"',
            "  - Description: numeric features of the entity at seed_time (for example counts, sums, averages, or days since an event), at most 100 columns",
            "  - Requirements", "    - exactly one row for every row of seeds", "    - only rows dated at or before seed_time",
        ])

    def audit(self, dp, executor, chain, task, tables, train, t, k):
        """The study's leak check on DeepPrep's chain: latest training seeds, rows after their time hidden."""
        e = self.tasks[t]
        ec = e["entity_col"].lower()
        tstar = train["seed_time"].max()
        sub = train[train["seed_time"] == tstar].sort_values(ec).head(AUDIT_SEEDS).reset_index(drop=True)[[ec, "seed_time"]]
        hidden = {}
        for name, spec in self.manifest["tables"].items():
            df = tables[name.lower()]
            tc = spec.get("time_col")
            hidden[name.lower()] = df[df[tc.lower()] <= tstar] if tc else df
        normal = features_from(run_chain(dp, executor, {**tables, "seeds": sub}, chain, task), sub, ec)
        hid = features_from(run_chain(dp, executor, {**hidden, "seeds": sub}, chain, task), sub, ec)
        cols = [c for c in normal.columns if c in hid.columns and not np.allclose(normal[c].to_numpy(), hid[c].to_numpy(), rtol=1e-6, atol=1e-9, equal_nan=True)]
        return {"result": "leak" if cols else "clean", "seed_time": str(tstar), "seeds": len(sub), "columns_differing": cols[:20]}

    def session(self, dp, t, k, tables):
        e = self.tasks[t]
        ec, yc = e["entity_col"].lower(), e["target_col"].lower()
        metric, higher = H.metric_of(e["task_type"])
        train, val, test = self.seeds(t, k, "train"), self.seeds(t, k, "val"), self.seeds(t, k, "test")
        explore = train.sample(n=min(EXPLORE_SEEDS, len(train)), random_state=H.SAMPLE_SEED)[[ec, "seed_time"]].reset_index(drop=True)
        cfg = dp["Config"](name=CONFIG)
        description = self.target_description(t, tables)
        dp["Trial"].generate_schema_description = staticmethod(lambda task: description)
        task = dp["Task"](id=f"relbench-{t}-k{k}", inp_tbl_names=list(tables) + ["seeds"], tgt_tbl_name="features", split="test", type_="RELBENCH")
        executor = dp["executor_mod"].Executor(cfg=cfg, debug=False)
        trial = dp["Trial"](exp_id=f"{t}-k{k}", task=task)
        trial.tables = {**tables, "seeds": explore}
        tools, llm = [], StudyLlm(self.llm)
        agent = dp["Agent"].__new__(dp["Agent"])
        dp["BaseAgent"].__init__(agent, "Tree-Based Agentic Reasoning Agent", cfg, "_MAIN")
        agent.llm, agent.mode = llm, cfg.get("execute_mode")
        agent.client = LocalClient(dp, executor, {trial.exp_id: trial}, tools)
        cell = self
        check = agent._check_solution

        def check_with_audit(trial_, solution):
            check(trial_, solution)  # DeepPrep's own check: ends in Terminate and runs on the exploration seeds
            leak = cell.audit(dp, executor, solution, task, tables, train, t, k)
            if leak["result"] == "leak":
                raise Exception(f"The solution's features read rows after seed_time (columns {leak['columns_differing']}): "
                                f"every row used for a seed must have a time at or before that seed's seed_time. Fix the operator chain.")
            return True

        agent._check_solution = check_with_audit
        rec = {"arm": "deepprep", "run": self.a.run, "task": t, "k": k, "agent": f"{H.tname(t)}-agent", "metric": metric,
               "higher_is_better": higher, "target": None, "target_detail": {"val": None, "why": "DeepPrep keeps no goal"},
               "goal_reached": None, "tools": tools, "validations": [], "stop": None, "error": None, "learning": None}
        t0 = time.time()
        solution = None
        try:
            solution = agent.reasoning_step(trial)
            rec["stop"] = "solution"
        except Exception as err:  # noqa: BLE001 - DeepPrep gave up (errors or turns): no solution
            rec["stop"], rec["error"] = "no_solution", str(err)[:500]
        reasoning_s = time.time() - t0
        rec["llm"] = llm.calls
        rec["final_sql"], rec["final_source"] = solution, "deepprep" if solution else None
        rec["messages"] = trial.recording.get("messages")
        audit_s = 0.0
        if solution:
            try:
                tv = time.time()
                xtr = features_from(run_chain(dp, executor, {**tables, "seeds": train[[ec, "seed_time"]]}, solution, task), train, ec)
                xva = features_from(run_chain(dp, executor, {**tables, "seeds": val[[ec, "seed_time"]]}, solution, task), val, ec)
                sql_s = time.time() - tv
                pv, _, tt = H.train_predict(e["task_type"], xtr, train[yc], xva)
                vscore = H.score(e["task_type"], val[yc], pv)
                rec["validations"].append({"val": vscore, "sql_seconds": sql_s, "train_seconds": tt, "leak": False, "n_features": xtr.shape[1]})
                rec["best_val"] = vscore
                xte = features_from(run_chain(dp, executor, {**tables, "seeds": test[[ec, "seed_time"]]}, solution, task), test, ec)
                labels = pd.read_parquet(os.path.join(self.a.prep, "tasks", t, f"k{k}", "test.parquet"))
                labels.columns = [c.lower() for c in labels.columns]
                labels = labels.rename(columns={e["time_col"].lower(): "seed_time"})
                labels["seed_time"] = pd.to_datetime(labels["seed_time"])
                ytest = test[[ec, "seed_time"]].merge(labels[[ec, "seed_time", yc]], on=[ec, "seed_time"], how="left")[yc]
                pt, _, _ = H.train_predict(e["task_type"], xtr, train[yc], xte)
                rec["eval"] = {"val": vscore, "test": H.score(e["task_type"], ytest, pt), "n_features": xtr.shape[1]}
                ta = time.time()
                rec["audit"] = self.audit(dp, executor, solution, task, tables, train, t, k)
                audit_s = time.time() - ta
            except Exception as err:  # noqa: BLE001 - the solution failed on the full seeds
                rec["error"] = f"final execution: {str(err)[:400]}"
                rec["stop"] = "solution_failed"
        val_s = sum(v.get("sql_seconds", 0) + v.get("train_seconds", 0) for v in rec["validations"])
        rec["audit_seconds"] = audit_s
        rec["agent_seconds"] = reasoning_s + val_s  # reasoning (LLM and exploration) plus the one validation, as other arms
        rec.setdefault("best_val", None)
        rec.setdefault("eval", {})
        rec.setdefault("audit", {"result": None})
        rec["totals"] = {
            "llm_calls": len(llm.calls), "planner_llm_calls": len(llm.calls), "tool_calls": len(tools),
            "tool_calls_by_category": {"schema": 0, "probe": len(tools), "validate": len(rec["validations"]), "memory": 0, "submit": 0},
            "input_tokens": sum(c["input_tokens"] for c in llm.calls), "output_tokens": sum(c["output_tokens"] for c in llm.calls),
            "llm_seconds": sum(c["seconds"] for c in llm.calls), "llm_retry_seconds": sum(c.get("retry_seconds", 0) for c in llm.calls),
            "tool_seconds": sum(x["seconds"] for x in tools), "validation_sql_seconds": sum(v.get("sql_seconds", 0) for v in rec["validations"]),
            "validation_train_seconds": sum(v.get("train_seconds", 0) for v in rec["validations"]),
            "learn_tokens": 0, "learn_seconds": 0}
        rec["totals"]["tokens"] = rec["totals"]["input_tokens"] + rec["totals"]["output_tokens"]
        rec["totals"]["tokens_with_learning"] = rec["totals"]["tokens"]
        with open(os.path.join(self.a.out, "sessions", f"{H.tname(t)}-k{k}.json"), "w") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1, default=str)
        log(f"{t} k{k}: stop={rec['stop']} llm={len(llm.calls)} tools={len(tools)} tok={rec['totals']['tokens']} "
            f"t={rec['agent_seconds']:.0f}s val={rec['best_val']} test={rec['eval'].get('test')} audit={rec['audit'].get('result')}")
        return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--prep", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--cutoffs", nargs="*")
    ap.add_argument("--llm", default="deepseek", choices=list(H.PROVIDERS))
    ap.add_argument("--reference-from", help="run.json of another arm on the same database (reference scores per cutoff)")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    for k in ("data", "prep"):
        setattr(a, k, os.path.abspath(getattr(a, k)))
    if a.reference_from:
        a.reference_from = os.path.abspath(a.reference_from)
    os.makedirs(os.path.join(a.out, "sessions"), exist_ok=True)
    with open(os.path.join(a.out, "harness.pid"), "w") as f:
        f.write(str(os.getpid()))
    cell = Cell(a)
    ks = [int(x) for x in a.cutoffs] if a.cutoffs else list(range(1, cell.timeline["K"] + 1))
    ref = {}
    if a.reference_from:
        for c in json.load(open(a.reference_from))["cutoffs"]:
            ref[c["k"]] = c
    summary = {"arm": "deepprep", "run": a.run, "settings": {"deepprep_config": CONFIG, "explore_seeds": EXPLORE_SEEDS,
               "model": cell.llm.model, "llm": cell.llm.provider, "reasoning_effort": cell.llm.effort, "thinking": cell.llm.thinking,
               "deepprep_commit": "b4e64b0"}, "cutoffs": []}
    work = tempfile.mkdtemp(prefix="deepprep-")
    dp = import_deepprep(work)
    try:
        for k in ks:
            cut = next(iter(cell.tasks.values()))["cutoffs"][k - 1]["test_timestamp"]
            tables = cell.tables_at(pd.Timestamp(cut))
            log(f"k{k}: tables up to {cut}: " + ", ".join(f"{n} {len(df)}" for n, df in tables.items()))
            order = (ref.get(k) or {}).get("order") or list(cell.tasks)
            for t in order:
                if t in cell.tasks:
                    cell.session(dp, t, k, tables)
            summary["cutoffs"].append({"k": k, "test_timestamp": cut, "order": order, "reference": (ref.get(k) or {}).get("reference", {})})
            with open(os.path.join(a.out, "run.json"), "w") as f:
                json.dump(summary, f, indent=1, default=str)
        summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        import traceback

        summary["error"] = traceback.format_exc()[-2000:]
        raise
    finally:
        with open(os.path.join(a.out, "run.json"), "w") as f:
            json.dump(summary, f, indent=1, default=str)
        os.chdir(ROOT)
        shutil.rmtree(work, ignore_errors=True)
    log("run done")


if __name__ == "__main__":
    main()

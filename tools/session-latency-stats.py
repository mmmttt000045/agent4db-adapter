#!/usr/bin/env python3
"""Analyze fixed-library session-bench outputs without double-counting nested spans."""

import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

POLICIES = ["no-share", "definition", "definition-cache", "condition"]
PHASES = ["cold", "warm", "after-append", "after-status", "burst-status"]
STAGES = ["llm", "exploration", "validation", "repair", "shared_wait", "execution", "pool_wait", "metadata", "other"]
SLOS = [30, 60, 120]


def read_json(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        return json.load(f)


def read_lines(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def category(kind):
    # Precedence makes parent maintenance/repair spans inclusive of their own overhead,
    # while follower waits and pool waits remain separately visible.
    if kind == "llm":
        return 100, "llm"
    if kind == "shared_wait":
        return 90, "shared_wait"
    if kind == "pool_wait":
        return 85, "pool_wait"
    if kind in ("repair", "db:repair"):
        return 80, "repair"
    if kind == "maintenance":
        return 70, "validation"
    if kind in ("db:metric", "db:guard", "db:check", "tool:check_join"):
        return 60, "validation"
    if kind == "db:exec":
        return 50, "execution"
    if kind == "db:probe" or kind in ("tool:list_tables", "tool:describe_table", "tool:join_path"):
        return 40, "exploration"
    if kind == "db:meta":
        return 30, "metadata"
    return 10, "other"


def partition(profile):
    """Sweep span boundaries, assigning each interval to a single stage."""
    wall = profile["wall_ms"]
    spans = []
    points = {0.0, wall}
    for span in profile["spans"]:
        start = max(0.0, min(wall, span["start_ms"]))
        end = max(start, min(wall, span["end_ms"]))
        spans.append((start, end, *category(span["kind"])))
        points.update((start, end))
    points = sorted(points)
    result = dict.fromkeys(STAGES, 0.0)
    for start, end in zip(points, points[1:]):
        mid = (start + end) / 2
        candidates = [(priority, stage) for a, b, priority, stage in spans if a <= mid < b]
        stage = max(candidates)[1] if candidates else "other"
        result[stage] += end - start
    if not math.isclose(sum(result.values()), wall, abs_tol=1e-5):
        raise ValueError("exclusive stage decomposition does not equal service time")
    return result


def quantile(values, p):
    """Empirical nearest-rank quantile; P95 of a small group may be its maximum."""
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * p) - 1)]


def summarize(records, phases):
    correct = sum(r["outcome"] == "correct" for r in records)
    wall_s = sum(p["wall_ms"] for p in phases) / 1000
    stages = dict.fromkeys(STAGES + ["queue"], 0.0)
    for record in records:
        for key, value in partition(record["profile"]).items():
            stages[key] += value
        stages["queue"] += record["queue_ms"]
    tokens = {
        k: sum(r["profile"]["llm"][k] for r in records)
        for k in ["input_tokens", "output_tokens", "discarded_tokens"]
    }
    db_by_kind = defaultdict(lambda: {"queries": 0, "db_ms": 0.0})
    for record in records:
        for kind, (queries, elapsed) in record["profile"]["db"]["by_kind"].items():
            db_by_kind[kind]["queries"] += queries
            db_by_kind[kind]["db_ms"] += elapsed
    goodput = {}
    for slo in SLOS:
        passed = sum(r["outcome"] == "correct" and r["completion_ms"] <= slo * 1000 for r in records)
        goodput[str(slo)] = {"correct_within_slo": passed, "tasks_per_minute": passed * 60 / wall_s if wall_s else 0}
    return {
        "n": len(records), "correct": correct, "accuracy_pct": 100 * correct / len(records),
        "errors": sum(r["outcome"] == "error" for r in records),
        "clarifications": sum(r["outcome"] == "clarify" for r in records),
        "mean_completion_s": sum(r["completion_ms"] for r in records) / len(records) / 1000,
        "median_completion_s": quantile([r["completion_ms"] / 1000 for r in records], .5),
        "p95_completion_s": quantile([r["completion_ms"] / 1000 for r in records], .95),
        "stage_ms_per_task": {k: v / len(records) for k, v in stages.items()},
        "llm_share_pct": 100 * stages["llm"] / sum(r["completion_ms"] for r in records),
        "llm_service_share_pct": 100 * stages["llm"] / sum(r["profile"]["wall_ms"] for r in records),
        "tokens": tokens,
        "tokens_per_correct": {k: v / correct if correct else None for k, v in tokens.items()},
        "db_ms": sum(r["profile"]["db"]["db_ms"] for r in records),
        "db_queries": sum(r["profile"]["db"]["queries"] for r in records),
        "db_by_kind": dict(db_by_kind),
        "mean_llm_replies": sum(r["profile"]["llm"]["replies"] for r in records) / len(records),
        "window_s": wall_s, "goodput": goodput,
    }


def analyze(directories):
    records, phases, startups, manifests = [], [], [], []
    imported_libraries = {}
    for directory in directories:
        directory = Path(directory)
        report_path = directory / "report.json"
        if not report_path.exists():
            report_path = directory / "report.json.gz"
        report = read_json(report_path)
        if not report["database_cleaned_up"]:
            raise ValueError(f"experiment database was not cleaned up: {directory}")
        manifests.append(report["manifest"])
        sessions = directory / "sessions.jsonl"
        if not sessions.exists():
            sessions = directory / "sessions.jsonl.gz"
        current = read_lines(sessions)
        for cell in report["cells"]:
            entries = cell["initial_library"]["entries"]
            logical = {e["key"]: e["metric"] for e in entries}
            if cell["policy"] == "no-share":
                if logical:
                    raise ValueError("no-share unexpectedly imported metric definitions")
            else:
                if len(entries) != len(cell["seeds"]) or any(e["status"] != "Valid" for e in entries):
                    raise ValueError("not all imported definitions passed admission")
                previous = imported_libraries.setdefault(cell["library"], logical)
                if previous != logical:
                    raise ValueError("sharing methods did not use identical fixed definitions")
            startups.append({"library": cell["library"], "policy": cell["policy"], "wall_ms": cell["startup"]["wall_ms"],
                             "db_ms": cell["startup"]["db"]["db_ms"], "seeded": len(cell["seeds"])})
            for phase in cell["phases"]:
                subset = [r for r in current if (r["library"], r["policy"], r["phase"]) ==
                          (cell["library"], cell["policy"], phase["phase"])]
                if len(subset) != phase["sessions"]:
                    raise ValueError("session count does not match completed phase")
                if sum(r["profile"]["db"]["queries"] for r in subset) != phase["db"]["queries"]:
                    raise ValueError("request-local SQL attribution does not match phase")
                if not math.isclose(sum(r["profile"]["db"]["db_ms"] for r in subset),
                                    phase["db"]["db_ms"], abs_tol=.001):
                    raise ValueError("request-local SQL time does not match phase")
                phases.append(phase)
        if len(current) != sum(p["sessions"] for c in report["cells"] for p in c["phases"]):
            raise ValueError("sessions exist outside the completed phase matrix")
        for record in current:
            if not math.isclose(record["completion_ms"], record["queue_ms"] + record["profile"]["wall_ms"], abs_tol=.001):
                raise ValueError("completion time does not equal queue plus service time")
        records.extend(current)
    identities = [(r["library"], r["policy"], r["phase"], r["task"], r["copy"]) for r in records]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate scored session identities")
    grouped, per_library = defaultdict(list), defaultdict(list)
    for record in records:
        grouped[record["policy"], record["phase"]].append(record)
        per_library[record["library"], record["policy"], record["phase"]].append(record)
    rows = []
    for (policy, phase), rs in sorted(grouped.items(), key=lambda x: (PHASES.index(x[0][1]), POLICIES.index(x[0][0]))):
        windows = [p for p in phases if (p["policy"], p["phase"]) == (policy, phase)]
        rows.append({"policy": policy, "phase": phase, **summarize(rs, windows)})
    library_rows = []
    for (library, policy, phase), rs in sorted(per_library.items()):
        windows = [p for p in phases if (p["library"], p["policy"], p["phase"]) == (library, policy, phase)]
        library_rows.append({"library": library, "policy": policy, "phase": phase, **summarize(rs, windows)})
    policy_rows = [{"policy": policy, **summarize([r for r in records if r["policy"] == policy],
                                              [p for p in phases if p["policy"] == policy])}
                   for policy in POLICIES if any(r["policy"] == policy for r in records)]
    library_policy_rows = [{"library": library, "policy": policy,
                            **summarize([r for r in records if (r["library"], r["policy"]) == (library, policy)],
                                        [p for p in phases if (p["library"], p["policy"]) == (library, policy)])}
                           for library, policy in sorted({(r["library"], r["policy"]) for r in records})]
    served_models = sum((Counter(r["profile"]["llm"]["served_models"]) for r in records), Counter())
    return {"sessions": len(records), "libraries": sorted({r["library"] for r in records}),
            "served_models": dict(served_models),
            "rows": rows, "per_library": library_rows, "by_policy": policy_rows,
            "by_library_policy": library_policy_rows, "startup": startups, "manifests": manifests}


def outputs(result, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    fields = ["phase", "policy", "n", "correct", "errors", "mean_completion_s", "median_completion_s", "p95_completion_s",
              "llm_share_pct", "llm_service_share_pct", "mean_llm_replies", "db_ms", "db_queries"]
    with (out / "summary.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: row[k] for k in fields} for row in result["rows"])
    text = ["| phase | policy | correct / n | mean s | P95 s | LLM % of completion | replies | DB ms (sum) | goodput@60s / min |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        text.append(f"| {row['phase']} | {row['policy']} | {row['correct']}/{row['n']} | {row['mean_completion_s']:.2f} | "
                    f"{row['p95_completion_s']:.2f} | {row['llm_share_pct']:.1f} | {row['mean_llm_replies']:.2f} | "
                    f"{row['db_ms']:.1f} | {row['goodput']['60']['tasks_per_minute']:.3f} |")
    (out / "summary.md").write_text("\n".join(text) + "\n")
    text = ["| phase | policy | queue s | LLM s | explore s | validate s | repair s | merge wait s | execute s | pool s | meta+other s |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        s = row["stage_ms_per_task"]
        values = [s[k] / 1000 for k in ["queue", "llm", "exploration", "validation", "repair", "shared_wait", "execution", "pool_wait"]]
        values.append((s["metadata"] + s["other"]) / 1000)
        text.append(f"| {row['phase']} | {row['policy']} | " + " | ".join(f"{v:.4f}" for v in values) + " |")
    (out / "decomposition.md").write_text("\n".join(text) + "\n")
    text = ["| library | policy | correct / n | mean s | P95 s | replies | DB ms (sum) |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for row in result["by_library_policy"]:
        text.append(f"| {row['library']} | {row['policy']} | {row['correct']}/{row['n']} | "
                    f"{row['mean_completion_s']:.2f} | {row['p95_completion_s']:.2f} | "
                    f"{row['mean_llm_replies']:.2f} | {row['db_ms']:.1f} |")
    (out / "per-library.md").write_text("\n".join(text) + "\n")
    text = ["| phase | policy | within 30 s / n | tasks/min | within 60 s / n | tasks/min | within 120 s / n | tasks/min |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        values = []
        for slo in SLOS:
            g = row["goodput"][str(slo)]
            values.extend([f"{g['correct_within_slo']}/{row['n']}", f"{g['tasks_per_minute']:.3f}"])
        text.append(f"| {row['phase']} | {row['policy']} | " + " | ".join(values) + " |")
    (out / "slo.md").write_text("\n".join(text) + "\n")
    text = ["| phase | policy | input/task | output/task | input/correct | output/correct | discarded (sum) |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        attempt = [row["tokens"][k] / row["n"] for k in ["input_tokens", "output_tokens"]]
        correct = [row["tokens_per_correct"][k] for k in ["input_tokens", "output_tokens"]]
        values = [f"{v:.0f}" if v is not None else "—" for v in attempt + correct]
        text.append(f"| {row['phase']} | {row['policy']} | " + " | ".join(values) +
                    f" | {row['tokens']['discarded_tokens']} |")
    (out / "cost.md").write_text("\n".join(text) + "\n")
    text = ["| library | policy | imported | startup s | DB s |",
            "|---|---|---:|---:|---:|"]
    for row in result["startup"]:
        text.append(f"| {row['library']} | {row['policy']} | {row['seeded']} | "
                    f"{row['wall_ms']/1000:.3f} | {row['db_ms']/1000:.3f} |")
    (out / "startup.md").write_text("\n".join(text) + "\n")


def plot(result, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out)
    labels = {"no-share": "No shared definitions", "definition": "Definition revalidation",
              "definition-cache": "Version-keyed cache", "condition": "MAVRA"}
    phase_labels = {"cold": "First use", "warm": "Warm reuse", "after-append": "After append",
                    "after-status": "After breaking update", "burst-status": "Burst after update"}
    colors = {"queue": "#b9bcc6", "llm": "#4678b8", "exploration": "#5aab84", "validation": "#ecad4a",
              "repair": "#d7655f", "shared_wait": "#9977b3", "execution": "#57b6c2", "pool_wait": "#b5a689", "other": "#e2e3e7"}
    lookup = {(r["policy"], r["phase"]): r for r in result["rows"]}
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), layout="constrained")
    positions = []
    y = 0
    for phase in PHASES:
        for policy in POLICIES:
            if (policy, phase) in lookup:
                positions.append((y, lookup[policy, phase]))
                y += 1
        y += .65
    for ax, include_llm in zip(axes, [True, False]):
        for pos, row in positions:
            stages = row["stage_ms_per_task"].copy()
            stages["other"] += stages.pop("metadata")
            left = 0
            for stage in ["queue", "llm", "exploration", "validation", "repair", "shared_wait", "execution", "pool_wait", "other"]:
                if stage in ("llm", "queue") and not include_llm:
                    continue
                value = stages[stage] / 1000
                ax.barh(pos, value, left=left, color=colors[stage], height=.76)
                left += value
        ax.set_yticks([p for p, _ in positions], [f"{phase_labels[r['phase']]} · {labels[r['policy']]}" for _, r in positions], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Mean time per offered task (seconds)")
        ax.grid(axis="x", alpha=.2)
        ax.set_axisbelow(True)
        ax.set_title("Session latency (all outcomes)" if include_llm else "Tools (LLM and admission queue removed)")
    axes[1].tick_params(axis="y", labelleft=False)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=color, label=stage.replace("_", " ")) for stage, color in colors.items()],
               loc="outside lower center", ncol=5, frameon=False, fontsize=8)
    for ext in ["svg", "pdf", "png"]:
        fig.savefig(out / f"latency-decomposition.{ext}", dpi=180)
    plt.close(fig)


def tex_outputs(result, directories, out):
    """Generate the manuscript table and its numbers from the same audited sessions."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cells = {(r["policy"], r["phase"]): r for r in result["rows"]}
    if set(cells) != {(p, h) for p in POLICIES for h in PHASES}:
        raise ValueError("paper output requires all four methods and five phases")
    methods = {r["policy"]: r for r in result["by_policy"]}
    macros = {"SlSessions": str(result["sessions"]), "SlLibraries": str(len(result["libraries"]))}
    for policy, prefix in [("no-share", "SlNone"), ("definition", "SlDef"),
                           ("definition-cache", "SlCache"), ("condition", "SlCond")]:
        row = methods[policy]
        macros[prefix + "N"] = str(row["n"])
        macros[prefix + "Correct"] = str(row["correct"])
        for suffix, key, digits in [("Mean", "mean_completion_s", 2), ("Rounds", "mean_llm_replies", 2)]:
            macros[prefix + suffix] = f"{row[key]:.{digits}f}"
        startups = [r["wall_ms"] / 1000 for r in result["startup"] if r["policy"] == policy]
        macros[prefix + "Startup"] = f"{sum(startups)/len(startups):.2f}"
        for phase, suffix in [("after-append", "AppendChecks"), ("after-status", "StatusChecks")]:
            stages = cells[policy, phase]["stage_ms_per_task"]
            macros[prefix + suffix] = f"{(stages['validation']+stages['repair'])/1000:.2f}"
    cond, cache, none = (methods[p] for p in ["condition", "definition-cache", "no-share"])
    macros["SlCondDBSaveCache"] = f"{100*(1-cond['db_ms']/cache['db_ms']):.1f}"
    macros["SlCondInputSaveNone"] = f"{100*(1-cond['tokens']['input_tokens']/cond['n']/(none['tokens']['input_tokens']/none['n'])):.1f}"
    warm_llm = [r["llm_service_share_pct"] for r in result["rows"]
                if r["policy"] != "no-share" and r["phase"] in ("cold", "warm")]
    macros["SlWarmLLMMin"], macros["SlWarmLLMMax"] = f"{min(warm_llm):.1f}", f"{max(warm_llm):.1f}"
    records = []
    for directory in map(Path, directories):
        path = directory / "sessions.jsonl"
        records.extend(read_lines(path if path.exists() else directory / "sessions.jsonl.gz"))
    slow = max((r for r in records if r["policy"] == "condition"), key=lambda r: r["completion_ms"])
    macros["SlSlowTotal"] = f"{slow['completion_ms']/1000:.2f}"
    macros["SlSlowLLM"] = f"{partition(slow['profile'])['llm']/1000:.2f}"
    header = "% Generated by tools/session-latency-stats.py; do not edit.\n"
    (out / "session-latency.tex").write_text(header + "".join(
        f"\\newcommand{{\\{name}}}{{{value}}}\n" for name, value in macros.items()))
    labels = {"cold": r"\bt{First use}{首次使用}", "warm": r"\bt{Warm reuse}{热复用}",
              "after-append": r"\bt{After append}{追加后}", "after-status": r"\bt{After status history}{状态流水后}",
              "burst-status": r"\bt{Burst after status}{状态流水后突发}"}
    lines = [header.rstrip(), r"\begin{tabularx}{\linewidth}{@{}Lrrrr@{}}", r"\toprule",
             r"\bt{Phase}{阶段} & \bt{No share}{不共享} & \bt{Def.}{定义级} & \bt{Cache}{缓存} & \system\\", r"\midrule"]
    for phase in PHASES:
        lines.append(labels[phase] + " & " + " & ".join(f"{cells[p, phase]['mean_completion_s']:.2f}" for p in POLICIES) + r"\\")
    lines.extend([r"\midrule", r"\bt{Pooled mean}{全矩阵平均} & " +
                  " & ".join(f"{methods[p]['mean_completion_s']:.2f}" for p in POLICIES) + r"\\",
                  r"\bt{Correct/attempted}{正确/尝试} & " +
                  " & ".join(f"{methods[p]['correct']}/{methods[p]['n']}" for p in POLICIES) + r"\\", r"\midrule",
                  r"\multicolumn{5}{@{}l@{}}{\bt{Correct tasks/min within deadline}{时限内正确任务/分钟}}\\"])
    for slo in SLOS:
        lines.append(f"{slo}\\,s & " + " & ".join(f"{methods[p]['goodput'][str(slo)]['tasks_per_minute']:.3f}" for p in POLICIES) + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabularx}"])
    (out / "session-latency-table.tex").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--tex-out", help="Generate the paper's session table and numeric macros")
    args = parser.parse_args()
    result = analyze(args.directories)
    outputs(result, args.out)
    if args.plot:
        plot(result, args.out)
    if args.tex_out:
        tex_outputs(result, args.directories, args.tex_out)
    print(f"{result['sessions']} sessions, {len(result['libraries'])} paired libraries; {args.out}")


if __name__ == "__main__":
    main()

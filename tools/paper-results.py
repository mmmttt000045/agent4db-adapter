#!/usr/bin/env python3
"""论文结果：从实验原始输出生成 overleaf/gen/ 下的表格、pgfplots 坐标与正文数值宏，并写出汇总 JSON。

用法（在 noctis 的仓库根目录）：
  python3 tools/paper-results.py --scen results/scen-20260930 --out overleaf/gen \
      --json exp/2026-10-01-scenarios/paper-results.json

场景实验（metric-bench，三个模型 × 六种方法 × 十种数据变化）的口径：
- 计分题：留出与各变化场景中的题目，不含学习题与 *-relearn 重新学习题。
- 模型服务因用量上限失败的题（outcome = error）不进分母，单独计数；答对、答错与请求澄清都进分母。
- 学习阶段（学习题或提炼）出现服务失败的组整组剔除：没有学到定义的组不能代表该方法。
  撤销重学组某场景的重新学习失败时，剔除该组这一场景的计分题。
- 方法之间按模型宏平均：先在每个模型内求正确率，再对有数据的模型取平均；汇总行再对场景等权平均。
- 分模型的图只用该模型下六种方法都有有效题的场景，区间为场景内按题重抽样的 95% 百分位区间。
- 过期使用：计分题中 find_metric 返回、或 SQL 声明了在该场景开始时审计为答错的修订（metric_use.bad_found / bad_executed）。
- 维护数据库时间：maintenance 事件内计量的数据库时间（与 metric-bench 报告相同），按组求和后对组取平均。
受控维护实验（maint-bench）的比值取正反两轮各自比值的算术平均，与论文表述一致。
"""

import argparse
import collections
import glob
import json
import math
import os
import random

MODELS = [  # (任务目录前缀, 显示名)；前缀长的先匹配
    ("glm53flash", "GLM-5.3 Flash"),
    ("glm53", "GLM-5.3"),
    ("dsv41flash", "DeepSeek V4.1 Flash"),
]
MODEL_ORDER = ["DeepSeek V4.1 Flash", "GLM-5.3", "GLM-5.3 Flash"]
METHODS = [  # (mode, 英文, 中文)
    ("middle", "No sharing", "不共享"),
    ("metric-global-noguard", "Unguarded", "无守护"),
    ("metric-global-schema", "Schema-only", "只看结构"),
    ("metric-global-revoke", "Revoke", "撤销重学"),
    ("metric-global-def", "Definition", "定义级"),
    ("metric-global", r"Condition (\system)", "条件级"),
]
HEAD = {  # 表头用的两行英文
    "middle": r"No\\sharing",
    "metric-global-noguard": r"Unguarded\\sharing",
    "metric-global-schema": r"Schema\\only",
    "metric-global-revoke": r"Revoke\\on write",
    "metric-global-def": r"Definition\\level",
    "metric-global": r"Condition\\(\system)",
}
CLASSES = {  # 类别：英文、中文
    "none": ("None", "无变化"),
    "benign": ("Benign", "正常"),
    "grain": ("Grain", "粒度"),
    "fanout": ("Fan-out", "连接放大"),
    "coverage": ("Coverage", "覆盖"),
    "unmodeled": ("Not modeled", "未建模"),
}
PHASES = [  # (phase, 类别, 英文, 中文, 英文说明, 中文说明)
    ("holdout", "none", "Held-out", "留出", "No update; new parameters and question types", "无更新；新参数与新题型"),
    ("append", "benign", "Append", "正常追加", "Copy one month of sales under new tickets", "复制一个月销售并换新小票号"),
    ("backfill", "benign", "Late backfill", "迟到回填", "Add returns with new keys", "补写新键的退货"),
    ("correct", "benign", "In-place fix", "原地更正", "Update net paid of some sales", "原地修改部分销售的净支付额"),
    ("addcol", "benign", "New column", "新增无关列", "Add an empty column to returns", "退货表新增空列"),
    ("status", "grain", "Status history", "状态流水", "Add an application-state row per return", "每笔退货追加申请状态行"),
    ("revision", "grain", "Versioning", "版本化更正", "Keep old sales versions as non-current rows", "旧版本销售保留为非当前行"),
    ("dupload", "grain", "Duplicate load", "重复装载", "Reload four months of identical sales rows", "四个月销售整批重复装载"),
    ("dimhist", "fanout", "Dim.\\ history", "维表拉链", "Add old-version rows to the item dimension", "商品维表增加旧版本行"),
    ("latekey", "coverage", "Key format", "日期键格式", "Append sales whose date keys use yyyymmdd", "追加日期键为 yyyymmdd 的销售"),
    ("unit", "unmodeled", "Unit change", "金额单位", "Multiply sales amounts by 100 from 2002-07", "2002-07 起销售金额乘以 100"),
]
QUOTA = ("INFERENCE_CAP_ERROR", "HTTP 429", "HTTP 402", "限流", "用量上限")


def model_of(job):
    for prefix, name in MODELS:
        if job.startswith(prefix):
            return name
    return job


def provider_failure(x):
    s = json.dumps(x, ensure_ascii=False)
    return any(q in s for q in QUOTA)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def load_scenarios(root):
    cells, dropped = [], []
    for f in sorted(glob.glob(os.path.join(root, "*", "metric-*", "cell-*.json"))):
        job = os.path.relpath(f, root).split(os.sep)[0]
        d = json.load(open(f, encoding="utf-8"))
        learn = [r for r in d["records"] if r["phase"] == "learn"]
        if any(r["outcome"] == "error" for r in learn) or provider_failure(d.get("learning", [])):
            dropped.append({"file": f, "reason": "learning failed (provider quota)"})
            continue
        bad_phases = set()
        for r in d["records"]:
            if r["phase"].endswith("-relearn") and r["outcome"] == "error":
                bad_phases.add(r["phase"][: -len("-relearn")])
        for x in d.get("relearning", []):
            if provider_failure(x.get("step", {})):
                bad_phases.add(x.get("phase"))
        cells.append({"file": f, "job": job, "model": model_of(job), "mode": d["mode"], "d": d, "bad_phases": bad_phases})
    return cells, dropped


def scored(cell):
    for r in cell["d"]["records"]:
        p = r["phase"]
        if p == "learn" or p.endswith("-relearn") or p in cell["bad_phases"]:
            continue
        yield r


def analyze(cells):
    acc = collections.defaultdict(lambda: [0, 0])  # (model, mode, phase) -> [correct, valid]
    err = collections.Counter()
    stale = collections.defaultdict(lambda: [0, 0])  # (mode, phase) -> [stale tasks, valid]
    tokens = collections.defaultdict(list)  # (model, mode) -> input tokens per valid task
    turns = collections.defaultdict(list)
    hold_tokens = collections.defaultdict(list)
    hold_turns = collections.defaultdict(list)
    maint = collections.defaultdict(list)  # (model, mode) -> per-cell maintenance DB s over valid phases
    maint_phase = collections.defaultdict(list)  # (mode, phase) -> per-cell s
    events = collections.defaultdict(collections.Counter)  # (mode, phase) -> event counts (summed over cells)
    ncells = collections.Counter()
    relearn = collections.defaultdict(list)  # model -> relearning tokens per cell (revoke)
    for c in cells:
        mode, model = c["mode"], c["model"]
        ncells[(model, mode)] += 1
        for r in scored(c):
            if r["outcome"] == "error":
                err[(model, mode)] += 1
                continue
            k = (model, mode, r["phase"])
            acc[k][0] += r["outcome"] == "correct"
            acc[k][1] += 1
            u = r.get("metric_use") or {}
            s = stale[(mode, r["phase"])]
            s[0] += (u.get("bad_found", 0) or 0) > 0 or (u.get("bad_executed", 0) or 0) > 0
            s[1] += 1
            tokens[(model, mode)].append(r["run"]["input_tokens"])
            turns[(model, mode)].append(r["run"]["steps"])
            if r["phase"] == "holdout":
                hold_tokens[(model, mode)].append(r["run"]["input_tokens"])
                hold_turns[(model, mode)].append(r["run"]["steps"])
        total = 0.0
        for p, *_ in PHASES[1:]:
            if p in c["bad_phases"]:
                continue
            evs = c["d"]["events"].get(p, [])
            ms = sum((e.get("db") or {}).get("ms", 0.0) for e in evs if e.get("event") == "maintenance") / 1000.0
            total += ms
            maint_phase[(mode, p)].append(ms)
            for e in evs:
                events[(mode, p)][e.get("event", "?")] += 1
        maint[(model, mode)].append(total)
        if mode == "metric-global-revoke":
            tok = sum(r["run"]["input_tokens"] + r["run"]["output_tokens"] for r in c["d"]["records"] if r["phase"].endswith("-relearn"))
            tok += sum(
                (x.get("step", {}).get("extraction", {}) or {}).get("input_tokens", 0)
                + (x.get("step", {}).get("extraction", {}) or {}).get("output_tokens", 0)
                for x in c["d"].get("relearning", [])
            )
            relearn[model].append(tok)
    return dict(acc=acc, err=err, stale=stale, tokens=tokens, turns=turns, hold_tokens=hold_tokens, hold_turns=hold_turns,
                maint=maint, maint_phase=maint_phase,
                events=events, ncells=ncells, relearn=relearn)


def rate(acc, model, mode, phases):
    k = sum(acc[(model, mode, p)][0] for p in phases)
    n = sum(acc[(model, mode, p)][1] for p in phases)
    return k, n


def macro(acc, mode, phases):
    vals = []
    for m in MODEL_ORDER:
        k, n = rate(acc, m, mode, phases)
        if n:
            vals.append(k / n)
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def phase_mean(acc, mode, phases):
    """各场景等权：先求每个场景的模型宏平均，再对有数据的场景取平均（避免缺失场景改变题目构成）。"""
    vals = [v for v in (macro(acc, mode, [p])[0] for p in phases) if v is not None]
    return mean(vals)


def common_phases(acc, model):
    """该模型下六种方法都有有效题的场景。"""
    return [p for p, *_ in PHASES if all(acc[(model, mode, p)][1] for mode, *_ in METHODS)]


def per_model(acc, model, mode, reps=4000, seed=7):
    """该模型在共同场景上的正确率（场景等权平均），95% 区间为场景内按题有放回重抽样（固定种子）的百分位区间。"""
    ps = common_phases(acc, model)
    if not ps:
        return None, None, None, 0
    kn = [acc[(model, mode, p)] for p in ps]
    point = mean([k / n for k, n in kn])
    rnd = random.Random(seed)
    boots = sorted(mean([sum(rnd.random() < k / n for _ in range(n)) / n for k, n in kn]) for _ in range(reps))
    return point, boots[int(0.025 * reps)], boots[int(0.975 * reps) - 1], len(ps)


# ───────────────────────── LaTeX 输出 ─────────────────────────


def heat(v):
    """正确率 → 单色蓝阶底纹（\\cellcolor{accent!x}），越深越高；文字保持黑色。"""
    return f"\\cellcolor{{accent!{round(8 + 52 * v)}}}"


def tex_heat_table(A):
    allp = [p for p, *_ in PHASES]
    lines = []
    lines.append(r"\begin{tabularx}{\textwidth}{@{}llL" + "r" * len(METHODS) + r"@{}}")
    lines.append(r"\toprule")
    head = " & ".join(rf"\bh{{{HEAD.get(mode, en)}}}{{{zh}}}" for mode, en, zh in METHODS)
    lines.append(rf"\bt{{Class}}{{类别}} & \bt{{Change}}{{数据变化}} & \bt{{What the update does}}{{更新内容}} & {head}\\")
    lines.append(r"\midrule")
    prev = None
    for p, cls, en, zh, den, dzh in PHASES:
        cen, czh = CLASSES[cls]
        first = cls != prev
        if first and prev is not None:
            lines.append(r"\addlinespace[2pt]")
        prev = cls
        label = rf"\bt{{{cen}}}{{{czh}}}" if first else ""
        cells = []
        for mode, *_ in METHODS:
            v, _ = macro(A["acc"], mode, [p])
            if v is None:
                cells.append("--")
                continue
            s = A["stale"][(mode, p)]
            mark = r"$^\dagger$" if s[1] and s[0] / s[1] >= 0.25 else ""
            cells.append(f"{heat(v)}{round(100 * v)}{mark}")
        lines.append(rf"{label} & \bt{{{en}}}{{{zh}}} & \bt{{{den}}}{{{dzh}}} & " + " & ".join(cells) + r"\\")
    lines.append(r"\midrule")
    cells = []
    for mode, *_ in METHODS:
        cells.append(rf"\textbf{{{round(100 * phase_mean(A['acc'], mode, allp))}}}")
    lines.append(r"\multicolumn{3}{@{}l}{\bt{Mean over the 11 settings}{11 种情形平均}} & " + " & ".join(cells) + r"\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabularx}")
    return "\n".join(lines) + "\n"


def tex_model_bars(A):
    """pgfplots：每个模型一条 \\addplot（方法序号 → 正确率，误差线为 Wilson 95% 区间），样式 mavraA/B/C 在正文导言定义。"""
    allp = [p for p, *_ in PHASES]
    out = []
    for i, m in enumerate(MODEL_ORDER):
        pts = []
        for j, (mode, *_rest) in enumerate(METHODS):
            p, lo, hi, _ = per_model(A["acc"], m, mode)
            if p is None:
                continue
            pts.append(f"({j},{100 * p:.1f}) += (0,{100 * max(0.0, hi - p):.1f}) -= (0,{100 * max(0.0, p - lo):.1f})")
        out.append(rf"\addplot[mavra{chr(65 + i)}] coordinates {{" + " ".join(pts) + "};")
        out.append(rf"\addlegendentry{{{m}}}")
    return "\n".join(out) + "\n"


def tex_cost_table(A):
    allp = [p for p, *_ in PHASES]
    changed = [p for p, *_ in PHASES[1:]]
    lines = [r"\begin{tabular}{@{}lrrrrr@{}}", r"\toprule"]
    lines.append(
        r"\bt{Method}{方法} & \bh{Correct\\(\%)}{正确率} & \bh{Stale\\(tasks)}{过期使用} & \bh{Revoked /\\repaired}{撤销／修复}"
        r" & \bh{Maint.\\DB (s)}{维护 DB 秒} & \bh{Input tok.\\(k)}{输入千 token}\\"
    )
    lines.append(r"\midrule")
    for mode, en, zh in METHODS:
        v = phase_mean(A["acc"], mode, allp)
        st = sum(A["stale"][(mode, p)][0] for p in changed)
        nc = sum(n for (m, mo), n in A["ncells"].items() if mo == mode)
        rev = sum(A["events"][(mode, p)]["revoked"] for p in changed) / nc if nc else 0
        rep = sum(A["events"][(mode, p)]["repair_promoted"] for p in changed) / nc if nc else 0
        ms = mean([x for (m, mo), xs in A["maint"].items() if mo == mode for x in xs])
        tk = mean([mean(xs) for (m, mo), xs in A["hold_tokens"].items() if mo == mode and xs])
        ms_s = "--" if mode in ("middle",) else f"{ms:.0f}"
        rr = "--" if mode in ("middle", "metric-global-noguard", "metric-global-schema") else f"{rev:.1f} / {rep:.1f}"
        lines.append(rf"\bhl{{{en}}}{{{zh}}} & {100 * v:.0f} & {st} & {rr} & {ms_s} & {tk / 1000:.1f}\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def load_maint(path):
    rows = {}
    for line in open(path, encoding="utf-8"):
        parts = [x.strip() for x in line.split("|")]
        if not parts or parts[0] in ("cell", "") or len(parts) < 15:
            continue
        rows[parts[0]] = {"db_ms": float(parts[13]), "wait_s": float(parts[14]), "stale": int(parts[1]),
                          "false_rev": int(parts[2]), "unavail": int(parts[3])}
    return rows


def maint_ratios(fwd, rev):
    """比值 = 条件级（或仅范围）DB 时间 / 定义级，正反两轮各自比值的算术平均。"""
    out = {}
    for arr, tag in (("staggered", "staggered"), ("burst", "simultaneous")):
        for pol in ("condition", "condition-scope"):
            pts = []
            for k, ndef in ((1, 4), (2, 8), (4, 15), (6, 19)):
                rs = []
                for rows in (fwd, rev):
                    a = rows.get(f"r1-k{k}-{pol}-{arr}")
                    b = rows.get(f"r1-k{k}-definition-{arr}")
                    if a and b and b["db_ms"]:
                        rs.append(a["db_ms"] / b["db_ms"])
                pts.append((ndef, 100 * sum(rs) / len(rs)))
            out[(pol, tag)] = pts
    return out


def tex_maint_plot(R):
    """pgfplots：条件级与仅范围两种方法 × 错峰与同时到达，样式在正文导言定义（颜色区分方法，线型区分到达方式）。"""
    out = []
    legend = {("condition", "staggered"): (r"\system, staggered", "条件级，错峰"),
              ("condition-scope", "staggered"): ("Scope only, staggered", "仅范围，错峰"),
              ("condition", "simultaneous"): (r"\system, simultaneous", "条件级，同时"),
              ("condition-scope", "simultaneous"): ("Scope only, simultaneous", "仅范围，同时")}
    for key in [("condition", "staggered"), ("condition-scope", "staggered"), ("condition", "simultaneous"), ("condition-scope", "simultaneous")]:
        pol, arr = key
        style = ("maintCond" if pol == "condition" else "maintScope") + ("Stag" if arr == "staggered" else "Sim")
        out.append(rf"\addplot[{style}] coordinates {{" + " ".join(f"({x},{y:.1f})" for x, y in R[key]) + "};")
        en, zh = legend[key]
        out.append(rf"\addlegendentry{{\bt{{{en}}}{{{zh}}}}}")
    return "\n".join(out) + "\n"


def numbers(A, dropped, cells, R):
    allp = [p for p, *_ in PHASES]
    modeled = [p for p, cls, *_ in PHASES if cls in ("grain", "fanout", "coverage")]
    assert len(modeled) == 5
    q = {}
    q["ScenModels"] = len({c["model"] for c in cells})
    q["ScenCells"] = len(cells)
    q["ScenCellsDropped"] = len(dropped)
    q["ScenValidTasks"] = sum(n for (_, _, _), (_, n) in A["acc"].items())
    q["ScenQuotaTasks"] = sum(A["err"].values())
    for mode, en, _ in METHODS:
        key = {"middle": "NoShare", "metric-global-noguard": "Noguard", "metric-global-schema": "Schema",
               "metric-global-revoke": "Revoke", "metric-global-def": "Def", "metric-global": "Cond"}[mode]
        q[f"ScenAcc{key}"] = f"{100 * phase_mean(A['acc'], mode, allp):.0f}"
        vh, _ = macro(A["acc"], mode, ["holdout"])
        q[f"ScenHoldout{key}"] = f"{100 * vh:.0f}"
        q[f"ScenModeled{key}"] = f"{100 * phase_mean(A['acc'], mode, modeled):.0f}"
        q[f"ScenBenign{key}"] = f"{100 * phase_mean(A['acc'], mode, ['append', 'backfill', 'correct', 'addcol']):.0f}"
        q[f"ScenStale{key}"] = sum(A["stale"][(mode, p)][0] for p in allp if p != "holdout")
        q[f"ScenStaleModeled{key}"] = sum(A["stale"][(mode, p)][0] for p in modeled)
        q[f"ScenStaleUnit{key}"] = A["stale"][(mode, "unit")][0]
        tk = mean([mean(xs) for (m, mo), xs in A["tokens"].items() if mo == mode and xs])
        q[f"ScenTok{key}"] = f"{tk / 1000:.1f}"
        ms = mean([x for (m, mo), xs in A["maint"].items() if mo == mode for x in xs])
        q[f"ScenMaint{key}"] = f"{ms:.1f}" if ms is not None else "--"
    cond = mean([x for (m, mo), xs in A["maint"].items() if mo == "metric-global" for x in xs])
    dfn = mean([x for (m, mo), xs in A["maint"].items() if mo == "metric-global-def" for x in xs])
    q["ScenMaintRatio"] = f"{100 * cond / dfn:.0f}"
    q["ScenRelearnTok"] = f"{mean([t for ts in A['relearn'].values() for t in ts]) / 1e6:.2f}"
    for p in ("dupload", "latekey", "unit", "status", "revision", "dimhist"):
        for mode, key in (("metric-global", "Cond"), ("middle", "NoShare"), ("metric-global-schema", "Schema"), ("metric-global-def", "Def")):
            v, _ = macro(A["acc"], mode, [p])
            q[f"ScenAcc{key}{p.capitalize()}"] = f"{100 * v:.0f}"
    ev = A["events"]
    q["ScenRepairFailedDupload"] = ev[("metric-global", "dupload")]["repair_failed"]
    q["ScenRepairSkippedLatekey"] = ev[("metric-global", "latekey")]["repair_skipped"]
    q["ScenRevokedDupload"] = ev[("metric-global", "dupload")]["revoked"]
    q["ScenRevokedLatekey"] = ev[("metric-global", "latekey")]["revoked"]
    q["ScenUnitStaleTasks"] = A["stale"][("metric-global", "unit")][0]
    q["ScenUnitTasks"] = A["stale"][("metric-global", "unit")][1]
    for m, tag in zip(MODEL_ORDER, "ABC"):
        for mode, key in (("metric-global", "Cond"), ("middle", "NoShare"), ("metric-global-def", "Def")):
            v, _, _, nph = per_model(A["acc"], m, mode)
            q[f"ScenAcc{key}Model{tag}"] = f"{100 * v:.0f}" if v is not None else "--"
            q[f"ScenCommonPhasesModel{tag}"] = nph
        a, b = mean(A["hold_tokens"][(m, "middle")]), mean(A["hold_tokens"][(m, "metric-global")])
        q[f"ScenHoldTokSaveModel{tag}"] = f"{100 * (1 - b / a):.0f}"
        a, b = mean(A["hold_turns"][(m, "middle")]), mean(A["hold_turns"][(m, "metric-global")])
        q[f"ScenHoldTurnsNoShareModel{tag}"] = f"{a:.1f}"
        q[f"ScenHoldTurnsCondModel{tag}"] = f"{b:.1f}"
    q["MaintStagMin"] = f"{min(y for _, y in R[('condition', 'staggered')]):.1f}"
    q["MaintStagMax"] = f"{max(y for _, y in R[('condition', 'staggered')]):.1f}"
    q["MaintSimMin"] = f"{min(y for _, y in R[('condition', 'simultaneous')]):.1f}"
    q["MaintSimMax"] = f"{max(y for _, y in R[('condition', 'simultaneous')]):.1f}"
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scen", required=True)
    ap.add_argument("--maint", default="exp/2026-09-29-maint-share/cells.txt")
    ap.add_argument("--maint-rev", default="exp/2026-09-30-maint-share-rev/cells.txt")
    ap.add_argument("--out", default="overleaf/gen")
    ap.add_argument("--json", default=None)
    o = ap.parse_args()
    cells, dropped = load_scenarios(o.scen)
    A = analyze(cells)
    R = maint_ratios(load_maint(o.maint), load_maint(o.maint_rev))
    os.makedirs(o.out, exist_ok=True)
    gen = "% 由 tools/paper-results.py 生成，请勿手改。\n"
    open(os.path.join(o.out, "scen-heat.tex"), "w", encoding="utf-8").write(gen + tex_heat_table(A))
    open(os.path.join(o.out, "scen-models.tex"), "w", encoding="utf-8").write(gen + tex_model_bars(A))
    open(os.path.join(o.out, "scen-cost.tex"), "w", encoding="utf-8").write(gen + tex_cost_table(A))
    open(os.path.join(o.out, "maint-ratio.tex"), "w", encoding="utf-8").write(gen + tex_maint_plot(R))
    q = numbers(A, dropped, cells, R)
    with open(os.path.join(o.out, "numbers.tex"), "w", encoding="utf-8") as f:
        f.write(gen)
        for k, v in q.items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    summary = {
        "numbers": q,
        "cells": [{"file": c["file"], "model": c["model"], "mode": c["mode"], "excluded_phases": sorted(c["bad_phases"])} for c in cells],
        "dropped": dropped,
        "accuracy": {f"{m}|{mo}|{p}": v for (m, mo, p), v in A["acc"].items()},
        "quota_failed_tasks": {f"{m}|{mo}": v for (m, mo), v in A["err"].items()},
        "stale": {f"{mo}|{p}": v for (mo, p), v in A["stale"].items()},
        "events": {f"{mo}|{p}": dict(v) for (mo, p), v in A["events"].items()},
        "maintenance_db_s_per_cell": {f"{m}|{mo}": v for (m, mo), v in A["maint"].items()},
        "maint_ratios": {f"{pol}|{arr}": pts for (pol, arr), pts in R.items()},
    }
    if o.json:
        os.makedirs(os.path.dirname(o.json), exist_ok=True)
        json.dump(summary, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in q.items():
        print(f"{k} = {v}")
    print(f"cells {len(cells)}, dropped {len(dropped)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""论文结果：从实验原始输出生成 overleaf/gen/ 下的代价表与正文数值宏，并写出汇总 JSON。
逐情形正确率热力图由 tools/figures/scenario_changes.py 读取 --json 的输出绘制。

用法（在 noctis 的仓库根目录）：
  python3 tools/paper-results.py --scen results/scen-20260930 --out overleaf/gen \
      --json exp/2026-10-01-scenarios/paper-results.json
  可给多个 --scen 目录；--models 只取部分模型（显示名，逗号分隔）。方法、场景与模型都按数据中实际出现的取
  （例如 2026-10-02 起的 DeepSeek 主实验含轨迹检索基线 traj-global 与备份副本场景 mirror）。

场景实验（metric-bench，三个模型 × 六种方法 × 十种数据变化）的口径：
- 计分题：留出与各变化场景中的题目，不含学习题与 *-relearn 重新学习题。
- 模型服务因用量上限失败的题（outcome = error）不进分母，单独计数；答对、答错与请求澄清都进分母。
- 学习阶段（学习题或提炼）出现服务失败的组整组剔除：没有学到定义的组不能代表该方法。
  撤销重学组某场景的重新学习失败时，剔除该组这一场景的计分题。
- 方法之间按模型宏平均：先在每个模型内求正确率，再对有数据的模型取平均；汇总行再对场景等权平均。
- 分模型的数值只用该模型下六种方法都有有效题的场景，区间为场景内按题重抽样的 95% 百分位区间。
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
METHODS = [  # (mode, 英文, 中文)；全文统一的方法名（表 2）。metric-global-noguard（共享但从不重验证）
    # 2026-10-07 起不再进入论文：在这组变化里它与模式变更时失效只差 0–1 个点，其运行不计入任何统计。
    ("middle", "No memory", "无记忆"),
    ("traj-global", "Example retrieval", "示例检索"),
    ("traj-verify", "Example retrieval + self-verification", "示例检索 + 自行核验"),
    ("metric-global-schema", "Invalidate on schema change", "模式变更时失效"),
    ("metric-global-revoke", "Invalidate on every write", "每次写入即失效"),
    ("metric-global-def", "Full recheck per definition", "整定义重查"),
    ("metric-global-snap", r"\system\ (ours)", r"\system（本文）"),
    ("metric-global-exref", r"\system, regression on current data", r"\system，回归测试用当前数据"),
    ("metric-global", r"\system, gold-SQL reference", r"\system，标准答案作参照"),
]
# 论文中的 MAVRA：G8 以智能体自己的 SQL 为参照、在学习时快照上比较（metric-global-snap）；metric-global-exref 是同一参照
# 在当前数据上比较（消融）；metric-global 是 MAVRA (gold SQL)。较早的数据里没有前者时依次退回 exref、metric-global。
MAVRA, CUR, GOLD = "metric-global-snap", "metric-global-exref", "metric-global"
KEYS = {"middle": "NoShare", "traj-global": "Traj", "traj-verify": "TrajVerify", "metric-global-noguard": "Noguard",
        "metric-global-schema": "Schema", "metric-global-revoke": "Revoke", "metric-global-def": "Def", MAVRA: "Cond",
        CUR: "CondCur", GOLD: "CondGold"}
COLOR = {  # 与正文导言的方法颜色一致
    "middle": "mNoShare",
    "traj-global": "mTraj",
    "traj-verify": "mTrajVerify",
    "metric-global-noguard": "mUnguarded",
    "metric-global-schema": "mSchema",
    "metric-global-revoke": "mRevoke",
    "metric-global-def": "mDef",
    MAVRA: "mCond",
    CUR: "mCondCur",
    GOLD: "mCondGold",
}


TABLE_EN = {"traj-verify": r"Example retrieval\\+ self-verification",  # 窄栏表格里需要断行的方法名
            "metric-global-exref": r"\system, regression\\on current data"}


def main_mode():
    """数据中的 MAVRA：依次取 metric-global-snap、metric-global-exref、metric-global 中第一个出现的。"""
    present = {m for m, *_ in METHODS}
    return next((m for m in (MAVRA, CUR, GOLD) if m in present), GOLD)


def shown_modes():
    """代价表与逐情形热力图列出的方法：有 metric-global-snap 时不列 MAVRA (gold SQL)，它只在正文里出现。"""
    present = {m for m, *_ in METHODS}
    return [m for m, *_ in METHODS if not (m == GOLD and MAVRA in present)]


def key_of(mode):
    return "Cond" if mode == main_mode() else KEYS[mode]
CLASSES = {  # 类别：英文、中文
    "none": ("None", "无变化"),
    "benign": ("Benign", "正常"),
    "grain": ("Grain", "粒度"),
    "fanout": ("Join fan-out", "连接放大"),
    "coverage": ("Completeness", "完整性"),
    "unmodeled": ("Not covered", "条件未覆盖"),
    "ambiguous": ("Ambiguous fix", "修复有歧义"),
}
PHASES = [  # (phase, 类别, 英文, 中文, 英文说明, 中文说明)
    ("holdout", "none", "Held-out", "留出", "No update; new parameters and question types", "无更新；新参数与新题型"),
    ("append", "benign", "Append", "正常追加", "Copy one month of sales under new tickets", "复制一个月销售并换新小票号"),
    ("backfill", "benign", "Late-arriving", "迟到事实", "Add returns with new keys", "补写新键的退货"),
    ("correct", "benign", "In-place fix", "原地更正", "Update net paid of some sales", "原地修改部分销售的净支付额"),
    ("addcol", "benign", "New column", "新增无关列", "Add an empty column to returns", "退货表新增空列"),
    ("status", "grain", "Status-change rows", "状态流水", "Add an application-state row per return", "退货改为状态流水，每笔退货追加一行申请状态"),
    ("revision", "grain", "Restatement", "更正保留旧行", "Keep old sales versions as non-current rows", "被更正销售的旧行保留为非当前行"),
    ("dupload", "grain", "Duplicate load", "重复加载", "Reload four months of identical sales rows", "四个月销售整批重复加载"),
    ("dimhist", "fanout", "SCD Type 2", "缓慢变化维", "Add old-version rows to the item dimension", "商品维表增加旧版本行"),
    ("latekey", "coverage", "Date-key format", "日期键格式", "Append sales whose date keys use yyyymmdd", "追加日期键为 yyyymmdd 的销售"),
    ("unit", "unmodeled", "Unit change", "金额单位", "Multiply sales amounts by 100 from 2002-07", "2002-07 起销售金额乘以 100"),
    ("mirror", "ambiguous", "Backup copy", "备份副本", "Append a full backup copy that keeps old amounts", "追加保留旧金额的整份备份副本"),
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
    # 被整组重跑替换的原组（每行 “组目录/cell-r1-方法-named”），统计时排除
    rp = os.path.join(root, "replaced.txt")
    replaced = {x.strip() for x in open(rp, encoding="utf-8")} if os.path.exists(rp) else set()
    for f in sorted(glob.glob(os.path.join(root, "*", "metric-*", "cell-*.json"))):
        job = os.path.relpath(f, root).split(os.sep)[0]
        if f"{job}/{os.path.basename(f)[:-5]}" in replaced:
            dropped.append({"file": f, "reason": "replaced by a rerun (provider failure during learning or relearning)"})
            continue
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
    """该模型下各方法都有有效题的场景。"""
    return [p for p, *_ in PHASES if all(acc[(model, mode, p)][1] for mode, *_ in METHODS)]


def per_model(acc, model, mode, reps=4000, seed=7):
    """该模型在共同场景上的正确率（场景等权平均），95% 区间为场景内按题有放回重抽样（固定种子）的百分位区间。"""
    ps = common_phases(acc, model)
    if not ps or any(acc[(model, mode, p)][1] == 0 for p in ps):
        return None, None, None, 0
    kn = [acc[(model, mode, p)] for p in ps]
    point = mean([k / n for k, n in kn])
    rnd = random.Random(seed)
    boots = sorted(mean([sum(rnd.random() < k / n for _ in range(n)) / n for k, n in kn]) for _ in range(reps))
    return point, boots[int(0.025 * reps)], boots[int(0.975 * reps) - 1], len(ps)


# ───────────────────────── LaTeX 输出 ─────────────────────────


def tex_cost_table(A):
    allp = [p for p, *_ in PHASES]
    changed = [p for p, *_ in PHASES[1:]]
    covered = [p for p, cls, *_ in PHASES if cls in ("grain", "fanout", "coverage")]
    other = [p for p in changed if p not in covered]
    lines = [r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule"]
    lines.append(
        r"\bt{Method}{方法} & \bh{Correct\\(\%)}{正确率} & \bh{Stale tasks\\covered / other}{过期使用\\覆盖／其他}"
        r" & \bh{Maint.\\DB (s)}{维护 DB 秒} & \bh{Input tok.\\(k)}{输入千 token}\\"
    )
    lines.append(r"\midrule")
    shown = shown_modes()
    for mode, en, zh in METHODS:
        if mode not in shown:
            continue
        v = phase_mean(A["acc"], mode, allp)
        st = f"{sum(A['stale'][(mode, p)][0] for p in covered)} / {sum(A['stale'][(mode, p)][0] for p in other)}"
        nc = sum(n for (m, mo), n in A["ncells"].items() if mo == mode)
        rev = sum(A["events"][(mode, p)]["revoked"] for p in changed) / nc if nc else 0
        rep = sum(A["events"][(mode, p)]["repair_promoted"] for p in changed) / nc if nc else 0
        ms = mean([x for (m, mo), xs in A["maint"].items() if mo == mode for x in xs])
        tk = mean([mean(xs) for (m, mo), xs in A["hold_tokens"].items() if mo == mode and xs])
        ms_s = "--" if mode in ("middle", "traj-global", "traj-verify") or ms is None else f"{ms:.0f}"
        en = TABLE_EN.get(mode, en)  # 窄栏表格里把长方法名断成两行
        lines.append(rf"\swatch{{{COLOR[mode]}}}\ \bhl{{{en}}}{{{zh}}} & {100 * v:.0f} & {st} & {ms_s} & {tk / 1000:.1f}\\")
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


def numbers(A, dropped, cells, R):
    allp = [p for p, *_ in PHASES]
    modeled = [p for p, cls, *_ in PHASES if cls in ("grain", "fanout", "coverage")]
    q = {}
    q["ScenModels"] = len({c["model"] for c in cells})
    q["ScenCells"] = len(cells)
    q["ScenCellsDropped"] = len(dropped)
    q["ScenValidTasks"] = sum(n for (_, _, _), (_, n) in A["acc"].items())
    q["ScenQuotaTasks"] = sum(A["err"].values())
    main = main_mode()
    for mode, en, _ in METHODS:
        key = key_of(mode)
        pct = lambda v: f"{100 * v:.0f}" if v is not None else "--"
        q[f"ScenAcc{key}"] = pct(phase_mean(A["acc"], mode, allp))
        q[f"ScenHoldout{key}"] = pct(macro(A["acc"], mode, ["holdout"])[0])
        q[f"ScenModeled{key}"] = pct(phase_mean(A["acc"], mode, modeled))
        q[f"ScenBenign{key}"] = pct(phase_mean(A["acc"], mode, ["append", "backfill", "correct", "addcol"]))
        q[f"ScenStale{key}"] = sum(A["stale"][(mode, p)][0] for p in allp if p != "holdout")
        q[f"ScenStaleModeled{key}"] = sum(A["stale"][(mode, p)][0] for p in modeled)
        q[f"ScenStaleUnit{key}"] = A["stale"][(mode, "unit")][0]
        tk = mean([mean(xs) for (m, mo), xs in A["tokens"].items() if mo == mode and xs])
        q[f"ScenTok{key}"] = f"{tk / 1000:.1f}" if tk is not None else "--"
        ms = mean([x for (m, mo), xs in A["maint"].items() if mo == mode for x in xs])
        q[f"ScenMaint{key}"] = f"{ms:.1f}" if ms is not None else "--"
    cond = mean([x for (m, mo), xs in A["maint"].items() if mo == main for x in xs])
    dfn = mean([x for (m, mo), xs in A["maint"].items() if mo == "metric-global-def" for x in xs])
    q["ScenMaintRatio"] = f"{100 * cond / dfn:.0f}" if cond is not None and dfn else "--"
    rl = [t for ts in A["relearn"].values() for t in ts]
    q["ScenRelearnTok"] = f"{mean(rl) / 1e6:.2f}" if rl else "--"
    for p in ("dupload", "latekey", "unit", "status", "revision", "dimhist", "mirror"):
        for mode, key in ((main, "Cond"), ("middle", "NoShare"), ("metric-global-schema", "Schema"), ("metric-global-def", "Def"),
                          ("traj-global", "Traj")):
            v, _ = macro(A["acc"], mode, [p])
            if v is not None:
                q[f"ScenAcc{key}{p.capitalize()}"] = f"{100 * v:.0f}"
    ev = A["events"]
    q["ScenRepairFailedDupload"] = ev[(main, "dupload")]["repair_failed"]
    q["ScenRepairSkippedLatekey"] = ev[(main, "latekey")]["repair_skipped"]
    q["ScenRevokedDupload"] = ev[(main, "dupload")]["revoked"]
    q["ScenRevokedLatekey"] = ev[(main, "latekey")]["revoked"]
    q["ScenUnitStaleTasks"] = A["stale"][(main, "unit")][0]
    q["ScenUnitTasks"] = A["stale"][(main, "unit")][1]
    for m, tag in zip(MODEL_ORDER, "ABC"):
        for mode, key in ((main, "Cond"), ("middle", "NoShare"), ("metric-global-def", "Def"), ("traj-global", "Traj")):
            if mode not in {x for x, *_ in METHODS}:
                continue
            v, _, _, nph = per_model(A["acc"], m, mode)
            q[f"ScenAcc{key}Model{tag}"] = f"{100 * v:.0f}" if v is not None else "--"
            q[f"ScenCommonPhasesModel{tag}"] = nph
        a, b = mean(A["hold_tokens"][(m, "middle")]), mean(A["hold_tokens"][(m, main)])
        q[f"ScenHoldTokSaveModel{tag}"] = f"{100 * (1 - b / a):.0f}" if a and b else "--"
        a, b = mean(A["hold_turns"][(m, "middle")]), mean(A["hold_turns"][(m, main)])
        q[f"ScenHoldTurnsNoShareModel{tag}"] = f"{a:.1f}" if a else "--"
        q[f"ScenHoldTurnsCondModel{tag}"] = f"{b:.1f}" if b else "--"
    q["MaintStagMin"] = f"{min(y for _, y in R[('condition', 'staggered')]):.1f}"
    q["MaintStagMax"] = f"{max(y for _, y in R[('condition', 'staggered')]):.1f}"
    q["MaintSimMin"] = f"{min(y for _, y in R[('condition', 'simultaneous')]):.1f}"
    q["MaintSimMax"] = f"{max(y for _, y in R[('condition', 'simultaneous')]):.1f}"
    # 实验规模：分析所用各组的全部智能体任务（含学习与重新学习，不含服务失败）及提炼
    tasks = calls = tokens = 0
    secs = 0.0
    for c in cells:
        for r in c["d"]["records"]:
            if r["outcome"] == "error":
                continue
            tasks += 1
            calls += r["run"]["steps"]
            tokens += r["run"]["input_tokens"] + r["run"]["output_tokens"]
            secs += r["run"]["seconds"]
        for x in c["d"].get("learning", []) + [y.get("step", {}) for y in c["d"].get("relearning", [])]:
            e = x.get("extraction") or {}
            tokens += (e.get("input_tokens") or 0) + (e.get("output_tokens") or 0)
    q["ScenAgentTasks"] = f"{tasks:,}"
    q["ScenLLMCalls"] = f"{calls:,}"
    q["ScenTokensM"] = f"{tokens / 1e6:.0f}"
    q["ScenAgentHours"] = f"{secs / 3600:.0f}"
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scen", required=True, action="append")
    ap.add_argument("--models", default=None, help="只取这些模型（显示名，逗号分隔）")
    ap.add_argument("--maint", default="exp/2026-09-29-maint-share/cells.txt")
    ap.add_argument("--maint-rev", default="exp/2026-09-30-maint-share-rev/cells.txt")
    ap.add_argument("--out", default="overleaf/gen")
    ap.add_argument("--json", default=None)
    ap.add_argument("--prefix", default="Scen", help="数值宏中 Scen 开头的名字改用这个前缀（如 PrevScen，保留旧一轮的数值）")
    ap.add_argument("--numbers-only", default=None, help="只把数值宏写到这个文件（不写表格与图）")
    o = ap.parse_args()
    global METHODS, PHASES, MODEL_ORDER
    cells, dropped = [], []
    for root in o.scen:
        c, d = load_scenarios(root)
        cells += c
        dropped += d
    if o.models:
        keep = {m.strip() for m in o.models.split(",")}
        cells = [c for c in cells if c["model"] in keep]
    # 方法、场景与模型按数据中实际出现的取，顺序沿用上面的全文约定
    modes = {c["mode"] for c in cells}
    phases = {r["phase"] for c in cells for r in c["d"]["records"]}
    METHODS = [x for x in METHODS if x[0] in modes]
    cells = [c for c in cells if c["mode"] in {m for m, *_ in METHODS}]  # 不在论文里的方法不计入任何统计
    PHASES = [x for x in PHASES if x[0] in phases]
    MODEL_ORDER = [m for m in MODEL_ORDER if any(c["model"] == m for c in cells)] + \
        sorted({c["model"] for c in cells} - set(MODEL_ORDER))
    A = analyze(cells)
    R = maint_ratios(load_maint(o.maint), load_maint(o.maint_rev))
    os.makedirs(o.out, exist_ok=True)
    gen = "% 由 tools/paper-results.py 生成，请勿手改。\n"
    if o.numbers_only:
        q = numbers(A, dropped, cells, R)
        with open(o.numbers_only, "w", encoding="utf-8") as f:
            f.write(gen + f"% --scen {' '.join(o.scen)}\n")
            for k, v in q.items():
                if k.startswith("Scen"):
                    f.write(f"\\newcommand{{\\{o.prefix}{k[4:]}}}{{{v}}}\n")
        return
    open(os.path.join(o.out, "scen-cost.tex"), "w", encoding="utf-8").write(gen + tex_cost_table(A))
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

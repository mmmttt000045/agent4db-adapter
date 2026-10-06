#!/usr/bin/env python3
"""正文中回应评审的实验数值：从 exp/2026-10-02-cache-baseline-tpcds 的存档生成 overleaf/gen 下的文件。

用法：python3 tools/review-results.py [--exp DIR] [--out overleaf/gen]
输出：
  review.tex           数值宏（\\Rp* 定义库回放，\\Sn* 快照绑定，\\Cb* 通用缓存基线，\\Eone* 规模，\\Tp* TPC-DS，\\Wr* 等待修复，\\Du* 声明使用）
  snapshot-stress.tex  随机并发表的数据行
图 3 由 tools/figures/maintenance_cost.py 直接读取同一存档中的 cb-1m-share-stats.json。
"""

import argparse
import collections
import gzip
import json
import os


def load(d, name):
    p = os.path.join(d, name)
    if name.endswith(".gz"):
        return json.load(gzip.open(p, "rt", encoding="utf-8"))
    return json.load(open(p, encoding="utf-8"))


def fmt(x, nd=1):
    if isinstance(x, int):
        return f"{x:,}".replace(",", "{,}")
    return f"{x:.{nd}f}"


# 定义库回放的方法与宏名。MAVRA 与各基线共用主参照 snapshot：智能体自己的 SQL，G8 在学习时快照上比较。
# Cur = MAVRA 的 G8 在当前数据上比较（example）；Gold = MAVRA (gold SQL)（judge）。没有 snapshot 的存档以 example 为主参照。
def replay_groups(tl):
    primary = "snapshot" if "condition/snapshot" in tl else "example"
    groups = [("Cond", f"condition/{primary}"), ("Gold", "condition/judge"), ("Def", f"definition/{primary}"),
              ("Cache", f"definition-cache/{primary}"), ("Schema", f"schema/{primary}"), ("Revoke", f"revoke/{primary}"),
              ("Table", f"tabletest/{primary}")]
    if primary != "example":
        groups.insert(1, ("Cur", "condition/example"))
    return primary, groups


def group(tl, g):
    """不修复的方法与参照无关：较早的存档里它们记在 judge 或 example 下。MAVRA 的各参照不互相替代。"""
    if g in tl:
        return g
    policy, _ = g.split("/")
    for alt in ("judge", "example"):
        if policy != "condition" and f"{policy}/{alt}" in tl:
            return f"{policy}/{alt}"
    return None


def key_of(x):
    return (x["lib"], x["change"], x["entry"], x["task"])


def common_keys(outs):
    groups = collections.defaultdict(set)
    for x in outs:
        groups[(x["policy"], x["oracle"])].add(key_of(x))
    return set.intersection(*groups.values()) if groups else set()


def reference_pair(m, prefix, tag, outs, paired, primary, other):
    """同一批题上 MAVRA 的主参照与另一种参照：各自答对数、主参照多出的答错数、答对率之差（主参照 − 另一种，
    百分点，按库整群自助区间），以及三种会修复的变化上的分项。宏名 {prefix}{tag}…，Cond 为主参照，Other 为另一种。"""
    idx = {(x["oracle"],) + key_of(x): x for x in outs if x["policy"] == "condition"}
    both = [(x, idx[(other,) + k[1:]]) for k, x in idx.items() if k[0] == primary and (other,) + k[1:] in idx]
    m[f"{prefix}{tag}PairN"] = len(both)
    m[f"{prefix}{tag}PairCond"] = sum(a["class"] == "correct" for a, _ in both)
    m[f"{prefix}{tag}PairOther"] = sum(b["class"] == "correct" for _, b in both)
    m[f"{prefix}{tag}PairExtraWrong"] = sum(a["class"] == "served_wrong" for a, _ in both) - sum(b["class"] == "served_wrong" for _, b in both)
    m[f"{prefix}{tag}Diff"] = paired["correct_diff_pp"]
    m[f"{prefix}{tag}DiffLo"] = paired["ci95_pp"][0]
    m[f"{prefix}{tag}DiffHi"] = paired["ci95_pp"][1]
    for ch, name in [("revision", "Revision"), ("dimhist", "Dimhist"), ("status", "Status")]:
        sel = [(a, b) for a, b in both if a["change"] == ch]
        m[f"{prefix}{tag}{name}N"] = len(sel)
        m[f"{prefix}{tag}{name}Cond"] = sum(a["class"] == "correct" for a, _ in sel)
        m[f"{prefix}{tag}{name}Other"] = sum(b["class"] == "correct" for _, b in sel)


def replay_macros(m, prefix, stats, outs):
    """一次定义库回放（合成数据或 TPC-DS）的题次级宏：各组在共同题上的结果、条件覆盖的变化下的答错数、维护 DB 时间。"""
    tl = stats["task_level_common"]
    primary, groups = replay_groups(tl)
    common = common_keys(outs)
    wrong_mod = collections.Counter((x["policy"], x["oracle"]) for x in outs
                                    if x["class"] == "served_wrong" and x["change"] != "unit" and key_of(x) in common)
    for key, g in groups:
        g = group(tl, g)
        if g is None:
            continue
        t = tl[g]
        m[f"{prefix}{key}N"] = t["n"]
        m[f"{prefix}{key}Correct"] = t["correct"]
        m[f"{prefix}{key}Wrong"] = t["served_wrong"]
        m[f"{prefix}{key}Needed"] = t["unavailable_needed"]
        m[f"{prefix}{key}Unneeded"] = t["unavailable_unneeded"]
        m[f"{prefix}{key}CorrectPct"] = t["correct_pct"]
        m[f"{prefix}{key}DB"] = stats["maintenance_db_s"][g]["total"]
        m[f"{prefix}{key}WrongModeled"] = wrong_mod[tuple(g.split("/"))]
        policy, oracle = g.split("/")
        if policy == "condition":
            m[f"{prefix}{key}RepairedTasks"] = sum(1 for x in outs if x["policy"] == "condition" and x["oracle"] == oracle
                                                   and x["repaired"] and key_of(x) in common)
    pair = stats["paired"].get(f"condition/{primary} vs " + (group(tl, f"tabletest/{primary}") or ""))
    if pair:
        m[f"{prefix}TableVsCondDiff"] = pair["correct_diff_pp"]
        m[f"{prefix}TableVsCondLo"] = pair["ci95_pp"][0]
        m[f"{prefix}TableVsCondHi"] = pair["ci95_pp"][1]
        m[f"{prefix}TableOnlyCond"] = pair["cond_only_correct"]
        m[f"{prefix}TableOnlyTable"] = pair["other_only_correct"]
    for tag, other in (("Cur", "example"), ("Gold", "judge")):
        key = f"condition/{primary} vs condition/{other}"
        if other != primary and key in stats["paired"]:
            reference_pair(m, prefix, tag, outs, stats["paired"][key], primary, other)
    return primary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp/2026-10-02-cache-baseline-tpcds")
    ap.add_argument("--out", default="overleaf/gen")
    o = ap.parse_args()
    m = {}

    # ── 定义库回放 ──（题次一律取各组共同的题）
    rs = load(o.exp, "replay-stats.json")
    ro = load(o.exp, "replay-outcomes.json.gz")
    m["RpLibs"] = len(ro["libraries"])
    m["RpDefs"] = sum(len(l["entries"]) for l in ro["libraries"])
    m["RpChanges"] = len(ro["changes"])
    primary = replay_macros(m, "Rp", rs, ro["outcomes"])
    db = rs["maintenance_db_s"]
    m["RpCacheVsCond"] = db[f"definition-cache/{primary}"]["total"] / db[f"condition/{primary}"]["total"]
    m["RpDefVsCond"] = db[f"definition/{primary}"]["total"] / db[f"condition/{primary}"]["total"]
    m["RpSameCondDef"] = rs["paired"][f"condition/{primary} vs definition/{primary}"]["same_class_pct"]
    m["RpSameCondCache"] = rs["paired"][f"condition/{primary} vs definition-cache/{primary}"]["same_class_pct"]

    # ── 快照绑定 ──
    sn = load(o.exp, "snapshot-binding-stats.json")
    il = {(x["case"], x["mode"]): x for x in sn["interleavings"]}
    m["SnTrials"] = sn["trials"]
    m["SnPausePre"] = il[("write_during_pause", "precheck")]["violation"]
    m["SnPauseSnap"] = il[("write_during_pause", "snapshot")]["violation"]
    m["SnBeforePre"] = il[("write_before_call", "precheck")]["violation"]
    m["SnBeforeSnapRej"] = il[("write_before_call", "snapshot")]["rejected"]
    st = sn["stress"]
    pre_un = [x for x in st if x["mode"] == "precheck" and not x["notify"]]
    pre_an = [x for x in st if x["mode"] == "precheck" and x["notify"]]
    snap = [x for x in st if x["mode"] == "snapshot"]
    m["SnStressTrials"] = st[0]["trials"]
    m["SnPreUnannMin"] = min(x["violation_pct_of_answered"] for x in pre_un)
    m["SnPreUnannMax"] = max(x["violation_pct_of_answered"] for x in pre_un)
    m["SnPreUnannTrials"] = min(x["trials_with_violation"] for x in pre_un)
    m["SnPreUnannViol"] = sum(x["violation"] for x in pre_un)
    m["SnPreAnnMin"] = min(x["violation_pct_of_answered"] for x in pre_an)
    m["SnPreAnnMax"] = max(x["violation_pct_of_answered"] for x in pre_an)
    m["SnPreAnnViol"] = sum(x["violation"] for x in pre_an)
    m["SnSnapViol"] = sum(x["violation"] for x in snap)
    m["SnSnapAnswered"] = sum(x["served"] + x["violation"] for x in snap)
    m["SnSnapUpper"] = max(x["violation_wilson95_upper_pct"] for x in snap)
    m["SnUnannLagMax"] = max(x["violation_start_minus_commit_ms"].get("max", 0) for x in pre_un)
    # 随机并发表：写者协议 × 读者查询，两种模式
    rows = []
    for notify, distinct in [(False, False), (False, True), (True, False), (True, True)]:
        pre = next(x for x in st if x["mode"] == "precheck" and x["notify"] == notify and x["distinct"] == distinct)
        sb = next(x for x in st if x["mode"] == "snapshot" and x["notify"] == notify and x["distinct"] == distinct)
        ans = lambda x: x["served"] + x["violation"]
        proto = "\\bt{announced}{提交后通知}" if notify else "\\bt{unannounced}{不通知}"
        reads = "\\bt{different}{不同}" if distinct else "\\bt{same}{相同}"
        rows.append(f"{proto} & {reads} & {fmt(pre['violation'])} / {fmt(ans(pre))} ({pre['violation_pct_of_answered']:.2f}\\%) & "
                    f"{pre['trials_with_violation']} & {fmt(sb['violation'])} / {fmt(ans(sb))}\\\\")
    head = [
        "\\begin{tabularx}{\\linewidth}{@{}llLrr@{}}",
        "\\toprule",
        "& & \\multicolumn{2}{c}{\\bh{Check-then-execute}{先检查后执行}} & \\bh{Same-snapshot}{同快照验证}\\\\",
        "\\cmidrule(lr){3-4}",
        "\\bt{Writer}{写者} & \\bt{Months}{月份} & \\bt{violations / answered}{违规／作答} & \\bh{trials}{试验} & \\bh{violations / answered}{违规／作答}\\\\",
        "\\midrule",
    ]
    tail = ["\\bottomrule", "\\end{tabularx}"]
    open(os.path.join(o.out, "snapshot-stress.tex"), "w").write(
        "% generated by tools/review-results.py\n" + "\n".join(head + rows + tail) + "\n")
    rp = sn["reader_p50_ms"]
    m["SnSteadyPre"] = rp["precheck"]["steady_ms"]
    m["SnSteadySnap"] = rp["snapshot"]["steady_ms"]
    m["SnFirstPre"] = rp["precheck"]["first_after_write_ms"]
    m["SnFirstSnap"] = rp["snapshot"]["first_after_write_ms"]
    raw = load(o.exp, "snapshot-binding-report.json")
    p50 = [x["latency_ms"]["p50"] for x in raw["stress"]]
    m["SnStressPFiftyLo"] = min(p50)
    m["SnStressPFiftyHi"] = max(p50)
    sh = load(o.exp, "snapshot-binding-shards-stats.json")["writer_ratio_over_none"]
    m["SnWriteSeq"] = sh["shards16"]["sequential_stmt_per_s"]
    m["SnWriteConcEight"] = sh["shards16"]["concurrent8_stmt_per_s"]
    m["SnWriteConcTT"] = sh["shards16"]["concurrent32_stmt_per_s"]
    m["SnWriteHotTT"] = sh["shards1"]["concurrent32_stmt_per_s"]
    m["SnWriteBulk"] = sh["shards16"]["bulk_ms_per_stmt"]

    # ── 通用缓存基线 ──
    cb = load(o.exp, "cb-1m-share-stats.json")["rows"]
    get = lambda rows, k, arr, p: next(r for r in rows if r["share"] == k and r["arrival"] == arr and r["policy"] == p)
    for arr, A in [("staggered", "Stag"), ("burst", "Burst")]:
        for k, K in [(1, "One"), (6, "Six")]:
            for p, P in [("definition-cache", "Cache"), ("condition", "Cond"), ("condition-scope", "Scope")]:
                m[f"Cb{A}{P}{K}"] = 100 * get(cb, k, arr, p)["vs_definition"]
            m[f"Cb{A}Def{K}"] = get(cb, k, arr, "definition")["db_s"]
    m["CbCondStagMin"] = min(get(cb, k, "staggered", "condition")["db_s"] for k in (1, 2, 4, 6))
    m["CbCondStagMax"] = max(get(cb, k, "staggered", "condition")["db_s"] for k in (1, 2, 4, 6))
    m["CbCacheStagMin"] = min(get(cb, k, "staggered", "definition-cache")["db_s"] for k in (1, 2, 4, 6))
    m["CbCacheStagMax"] = max(get(cb, k, "staggered", "definition-cache")["db_s"] for k in (1, 2, 4, 6))
    zero = load(o.exp, "cb-1m-zero-stats.json")["rows"]
    ratios = [r["vs_definition"] for r in zero if r["policy"] != "definition"]
    m["CbZeroMin"] = 100 * min(ratios)
    m["CbZeroMax"] = 100 * max(ratios)
    four = load(o.exp, "cb-4m-stats.json")["rows"]
    m["CbFourStagCache"] = 100 * get(four, 6, "staggered", "definition-cache")["vs_definition"]
    m["CbFourStagCond"] = 100 * get(four, 6, "staggered", "condition")["vs_definition"]
    m["CbFourBurstCache"] = 100 * get(four, 6, "burst", "definition-cache")["vs_definition"]
    m["CbFourBurstCond"] = 100 * get(four, 6, "burst", "condition")["vs_definition"]
    a32 = load(o.exp, "e1b-4m-a32-stats.json")["rows"]
    m["CbAgentsStagCache"] = 100 * get(a32, 6, "staggered", "definition-cache")["vs_definition"]
    m["CbAgentsStagCond"] = 100 * get(a32, 6, "staggered", "condition")["vs_definition"]
    m["CbAgentsBurstCache"] = 100 * get(a32, 6, "burst", "definition-cache")["vs_definition"]
    m["CbAgentsBurstCond"] = 100 * get(a32, 6, "burst", "condition")["vs_definition"]
    m["CbAgentsUses"] = get(a32, 6, "burst", "condition")["uses"]
    e1 = load(o.exp, "e1-scaling-stats.json")["rows"]
    for d, D in [("e1-maint-1m", "One"), ("e1-maint-4m", "Four"), ("e1-maint-16m", "Sixteen")]:
        rows = [r for r in e1 if r["dir"] == d]
        m[f"EoneDef{D}"] = get(rows, 6, "staggered", "definition")["db_s"]
        m[f"EoneCond{D}"] = get(rows, 6, "staggered", "condition")["db_s"]
        m[f"EoneRatio{D}"] = 100 * get(rows, 6, "staggered", "condition")["vs_definition"]

    # ── TPC-DS 自然共享 ──
    tp = load(o.exp, "tpcds-sharing.json")
    m["TpTemplates"] = tp["templates"]
    m["TpQueries"] = tp["queries_with_definitions"]
    m["TpDefs"] = tp["definitions"]
    m["TpInst"] = tp["condition_instances"]
    m["TpConds"] = tp["distinct_conditions"]
    m["TpPer"] = tp["instances_per_distinct"]
    m["TpSharedPct"] = tp["instances_on_shared_conditions_pct"]
    ss = tp["per_table_update"]["store_sales"]
    m["TpSalesDefs"] = ss["affected_definitions"]
    m["TpSalesDefChecks"] = ss["definition_level_checks"]
    m["TpSalesConds"] = ss["condition_level_checks"]

    # ── 等待修复、声明使用 ──
    wr = load(o.exp, "wait-repair-stats.json")["rows"]
    off = [r for r in wr if r["dir"] == "wr-200k-nowait"]
    on = [r for r in wr if r["dir"] == "wr-200k-wait"]
    m["WrDefOff"] = next(r["unavailable"] for r in off if r["policy"] == "definition")
    m["WrCondOff"] = next(r["unavailable"] for r in off if r["policy"] == "condition")
    m["WrDefOn"] = next(r["unavailable"] for r in on if r["policy"] == "definition")
    m["WrCondOn"] = next(r["unavailable"] for r in on if r["policy"] == "condition")
    m["WrUses"] = next(r["uses"] for r in on if r["policy"] == "condition")
    du = load(o.exp, "declared-use.json")
    c = du["counts"]
    m["DuDeviate"] = c["deviate"]
    m["DuValid"] = c["follow"] + c["deviate"]
    m["DuDevPct"] = du["deviate_pct_of_valid_def"]
    m["DuUndeclared"] = c["undeclared"]
    m["DuRecords"] = du["records"]
    m["DuUndeclPct"] = 100.0 * c["undeclared"] / du["records"]

    # ── TPC-DS 上的定义库回放（第二个负载；文件不存在时跳过）──
    if os.path.exists(os.path.join(o.exp, "tpcds-replay-stats.json")):
        ts = load(o.exp, "tpcds-replay-stats.json")
        to = load(o.exp, "tpcds-replay-outcomes.json.gz")
        lib = load(o.exp, "tpcds-library.json")["metric_report"]["entries"]
        m["TrDefs"] = len(lib)
        facts = collections.Counter(e["metric"]["fact"] for e in lib)
        m["TrStoreDefs"] = facts["store_sales"] + facts["store_returns"]
        m["TrJoinDefs"] = sum(1 for e in lib if e["metric"]["joins"])
        m["TrFilterDefs"] = sum(1 for e in lib if e["metric"]["filters"])
        m["TrChanges"] = len(to["changes"])
        primary = replay_macros(m, "Tr", ts, to["outcomes"])
        seed = next(s_ for s_ in to["seeds"] if s_["policy"] == "condition" and s_["oracle"] == primary)
        m["TrSeeded"] = seed["seeded"]
        m["TrSeedFailed"] = len(seed["failed"])
        if "dupload" in ts["maintenance_db_s"].get(f"condition/{primary}", {}):
            m["TrCondDuploadDB"] = ts["maintenance_db_s"][f"condition/{primary}"]["dupload"]

    lines = ["% generated by tools/review-results.py from " + o.exp + "; do not edit"]
    for k in sorted(m):
        v = m[k]
        nd = 2 if isinstance(v, float) and k in ("RpCacheVsCond", "RpDefVsCond", "SnWriteSeq", "SnWriteConcEight", "SnWriteConcTT",
                                                  "SnWriteHotTT", "SnWriteBulk", "SnPreAnnMin", "SnPreAnnMax", "SnSnapUpper") else 1
        if isinstance(v, float) and k.startswith("Cb") and ("Def" in k and "Stag" not in k or k.endswith("Min") or k.endswith("Max")) and k not in ("CbZeroMin", "CbZeroMax"):
            nd = 1
        if isinstance(v, float) and k in ("CbZeroMin", "CbZeroMax", "SnStressPFiftyLo", "SnStressPFiftyHi", "SnFirstPre", "SnFirstSnap", "SnUnannLagMax"):
            nd = 0
        lines.append(f"\\newcommand{{\\{k}}}{{{fmt(v, nd)}}}")
    open(os.path.join(o.out, "review.tex"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

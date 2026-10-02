#!/usr/bin/env python3
"""正文中回应评审的实验数值与图坐标：从 exp/2026-10-02-cache-baseline-tpcds 的存档生成 overleaf/gen 下的文件。

用法：python3 tools/review-results.py [--exp DIR] [--out overleaf/gen]
输出：
  review.tex           数值宏（\\Rp* 配对回放，\\Sn* 快照绑定，\\Cb* 通用缓存基线，\\Eone* 规模，\\Tp* TPC-DS，\\Wr* 等待修复，\\Du* 声明使用）
  cache-ratio-stag.tex 维护 DB 时间相对定义级的坐标（错峰）
  cache-ratio-burst.tex 同上（同时到达）
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp/2026-10-02-cache-baseline-tpcds")
    ap.add_argument("--out", default="overleaf/gen")
    o = ap.parse_args()
    m = {}

    # ── 配对回放 ──
    rs = load(o.exp, "replay-stats.json")
    ro = load(o.exp, "replay-outcomes.json.gz")
    tl = rs["task_level"]
    m["RpLibs"] = len(ro["libraries"])
    m["RpDefs"] = sum(len(l["entries"]) for l in ro["libraries"])
    m["RpChanges"] = len(ro["changes"])
    for key, g in [("Cond", "condition/judge"), ("Ex", "condition/example"), ("Def", "definition/judge"),
                   ("Cache", "definition-cache/judge"), ("Schema", "schema/judge"), ("Revoke", "revoke/judge"),
                   ("Table", "tabletest/judge")]:
        if g not in tl:
            continue
        t = tl[g]
        m[f"Rp{key}N"] = t["n"]
        m[f"Rp{key}Correct"] = t["correct"]
        m[f"Rp{key}Wrong"] = t["served_wrong"]
        m[f"Rp{key}Needed"] = t["unavailable_needed"]
        m[f"Rp{key}Unneeded"] = t["unavailable_unneeded"]
        m[f"Rp{key}CorrectPct"] = t["correct_pct"]
        m[f"Rp{key}DB"] = rs["maintenance_db_s"][g]["total"]
    outs = ro["outcomes"]
    wrong_mod = collections.Counter((x["policy"], x["oracle"]) for x in outs if x["class"] == "served_wrong" and x["change"] != "unit")
    m["RpSchemaWrongModeled"] = wrong_mod[("schema", "judge")]
    m["RpCondWrongModeled"] = wrong_mod[("condition", "judge")]
    if "tabletest/judge" in tl:
        m["RpTableWrongModeled"] = wrong_mod[("tabletest", "judge")]
        pair = rs["paired"].get("condition/judge vs tabletest/judge")
        if pair:
            m["RpTableVsCondDiff"] = pair["correct_diff_pp"]
            m["RpTableVsCondLo"] = pair["ci95_pp"][0]
            m["RpTableVsCondHi"] = pair["ci95_pp"][1]
            m["RpTableOnlyCond"] = pair["cond_only_correct"]
            m["RpTableOnlyTable"] = pair["other_only_correct"]
    m["RpCacheVsCond"] = rs["maintenance_db_s"]["definition-cache/judge"]["total"] / rs["maintenance_db_s"]["condition/judge"]["total"]
    m["RpDefVsCond"] = rs["maintenance_db_s"]["definition/judge"]["total"] / rs["maintenance_db_s"]["condition/judge"]["total"]
    pair = rs["paired"]["condition/example vs definition/example"]
    m["RpSameCondDef"] = rs["paired"]["condition/judge vs definition/judge"]["same_class_pct"]
    # 参照：同一批题次上 judge 与 example 的答对数
    idx = {(x["oracle"], x["lib"], x["change"], x["entry"], x["task"]): x for x in outs if x["policy"] == "condition"}
    common = [(x, idx.get(("example",) + k[1:])) for k, x in idx.items() if k[0] == "judge"]
    common = [(a, b) for a, b in common if b is not None]
    m["RpPairN"] = len(common)
    m["RpPairJudge"] = sum(a["class"] == "correct" for a, _ in common)
    m["RpPairEx"] = sum(b["class"] == "correct" for _, b in common)
    m["RpPairExWrong"] = sum(b["class"] == "served_wrong" for _, b in common) - sum(a["class"] == "served_wrong" for a, _ in common)
    ref = rs["paired"].get("condition/example vs definition-cache/judge")
    m["RpRefDiff"] = -ref["correct_diff_pp"]
    m["RpRefLo"] = -ref["ci95_pp"][1]
    m["RpRefHi"] = -ref["ci95_pp"][0]
    for ch, name in [("revision", "Revision"), ("dimhist", "Dimhist"), ("status", "Status")]:
        a = [x for x, _ in common if x["change"] == ch]
        m[f"Rp{name}N"] = len(a)
        m[f"Rp{name}Judge"] = sum(x["class"] == "correct" for x, _ in common if x["change"] == ch)
        m[f"Rp{name}Ex"] = sum(y["class"] == "correct" for x, y in common if x["change"] == ch)
    del pair

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
        "& & \\multicolumn{2}{c}{\\bt{Pre-check}{预检查}} & \\bh{Snapshot-bound}{绑定快照}\\\\",
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
        lines = []
        for p, style, label in [("condition-scope", "costScope", "Scope-only"), ("definition-cache", "costCache", "Definition + cache"),
                                ("condition", "costCond", "MAVRA")]:
            pts = " ".join(f"({get(cb, k, arr, p)['specs']},{100 * get(cb, k, arr, p)['vs_definition']:.1f})" for k in (1, 2, 4, 6))
            lines.append(f"\\addplot[{style}] coordinates {{{pts}}};")
        open(os.path.join(o.out, f"cache-ratio-{'stag' if arr == 'staggered' else 'burst'}.tex"), "w").write(
            "% generated by tools/review-results.py\n" + "\n".join(lines) + "\n")
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

    # ── TPC-DS 上的配对回放（第二个负载；文件不存在时跳过）──
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
        seeded = {f"{s['policy']}/{s['oracle']}": s["seeded"] for s in to["seeds"]}
        m["TrSeeded"] = seeded.get("condition/judge", 0)
        m["TrSeedFailed"] = len(next((s["failed"] for s in to["seeds"] if s["policy"] == "condition" and s["oracle"] == "judge"), []))
        for key, g in [("Cond", "condition/judge"), ("Ex", "condition/example"), ("Def", "definition/judge"),
                       ("Cache", "definition-cache/judge"), ("Schema", "schema/judge"), ("Revoke", "revoke/judge"),
                       ("Table", "tabletest/judge")]:
            if g not in ts["task_level"]:
                continue
            t = ts["task_level"][g]
            m[f"Tr{key}N"] = t["n"]
            m[f"Tr{key}Correct"] = t["correct"]
            m[f"Tr{key}Wrong"] = t["served_wrong"]
            m[f"Tr{key}Needed"] = t["unavailable_needed"]
            m[f"Tr{key}Unneeded"] = t["unavailable_unneeded"]
            m[f"Tr{key}CorrectPct"] = t["correct_pct"]
            m[f"Tr{key}DB"] = ts["maintenance_db_s"][g]["total"]
        wrong_mod = collections.Counter((x["policy"], x["oracle"]) for x in to["outcomes"] if x["class"] == "served_wrong" and x["change"] != "unit")
        for key, g in [("Cond", ("condition", "judge")), ("Schema", ("schema", "judge")), ("Table", ("tabletest", "judge")),
                       ("Cache", ("definition-cache", "judge")), ("Ex", ("condition", "example"))]:
            m[f"Tr{key}WrongModeled"] = wrong_mod[g]
        repaired = collections.Counter(x["change"] for x in to["outcomes"] if x["policy"] == "condition" and x["oracle"] == "judge" and x["repaired"])
        m["TrCondRepairedTasks"] = sum(repaired.values())
        pair = ts["paired"].get("condition/judge vs tabletest/judge")
        if pair:
            m["TrTableVsCondDiff"] = pair["correct_diff_pp"]
            m["TrTableOnlyCond"] = pair["cond_only_correct"]
            m["TrTableOnlyTable"] = pair["other_only_correct"]
        same = ts["paired"].get("condition/judge vs definition-cache/judge") or ts["paired"].get("condition/judge vs definition/judge")
        if same:
            m["TrSameCondDef"] = same["same_class_pct"]
        ex = ts["paired"].get("condition/example vs definition-cache/judge") or ts["paired"].get("condition/example vs schema/judge")
        idx = {(x["oracle"], x["lib"], x["change"], x["entry"], x["task"]): x for x in to["outcomes"] if x["policy"] == "condition"}
        common = [(x, idx.get(("example",) + k[1:])) for k, x in idx.items() if k[0] == "judge"]
        common = [(a, b) for a, b in common if b is not None]
        if common:
            m["TrPairN"] = len(common)
            m["TrPairJudge"] = sum(a["class"] == "correct" for a, _ in common)
            m["TrPairEx"] = sum(b["class"] == "correct" for _, b in common)
            m["TrPairExWrong"] = sum(b["class"] == "served_wrong" for _, b in common)
        del ex

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

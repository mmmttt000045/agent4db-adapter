"""Combine explicitly selected measured runs; do not infer benchmark provenance."""
import argparse
import json
import os
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = [(p, read(p)) for p in args.reports]
    lines = ["# 2026-09-28 研究评测实测结果", "",
             "结论：共享降低了本机工作负载的重复探索、检查和恢复成本；统计反馈和 Mock 的额外收益不稳定。复杂 SQL 语义边界仍有误拦截和误放行。真实 LLM 未运行。", "",
             "## 实际完成的规模", "",
             "|运行|每域事实行|总数据行|表与索引 GiB|agent|完整轮数|测量任务|符合预期|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    total_tasks = 0
    for path, report in reports:
        o = report["options"]
        capacity = report.get("capacity_only", False)
        phases = [r[s] for r in report.get("runs", []) for s in ("stable", "shifted")]
        tasks = sum(p["tasks"] for p in phases)
        total_tasks += tasks
        correct = sum(p["correct"] for p in phases)
        label = "容量校验" if capacity else ("公开结构适配" if o["corpus"] else f'{o["agents"]} agent / 缓存{"关" if o["no_result_cache"] else "开"}')
        rel = Path(os.path.relpath(path.parent / "report.md", args.output.parent)).as_posix()
        lines.append(f'|[{label}]({rel})|{o["rows"]:,}|{report["dataset"]["rows"]:,}|{report["dataset"]["relation_bytes"]/2**30:.3f}|'
                     f'{"—" if capacity else o["agents"]}|{"—" if capacity else o["rounds"]}|{tasks:,}|{correct:,}|')
        if capacity:
            lines.extend(["", f'容量校验另有 {report["capacity_checks"]} 个查询通过候选/参考结果核对。容量行不含消融，不能作为十 GB 级策略收益证据。', ""])
    lines += ["", f"以上主负载合计 {total_tasks:,} 个任务执行。正确率不包含下述独立语义边界专项；不能解释为任意 SQL 都正确。", "",
              "## 配对全程数据库成本降幅", "", "每轮先配对，再对降幅求均值。正数是节约，负数是退化。全程包括训练与恢复；DB 耗时之和不是墙钟。", "",
              "|运行|共享 B 对 A|反馈 C 对 A|共享后反馈 D 对 B|Mock M 对 B|", "|---|---:|---:|---:|---:|"]
    for _, report in reports:
        if report.get("capacity_only"):
            continue
        o = report["options"]
        values = []
        for base, target in [("A", "B"), ("A", "C"), ("B", "D"), ("B", "M")]:
            e = next(e for e in report["contrasts"]["paired"] if e["baseline"] == base and e["target"] == target and e["metric"] == "db_ms")
            values.append(f'{e["mean_reduction_percent"]:+.2f}%')
        label = "公开结构适配混合负载" if o["corpus"] else f'{o["agents"]} agent / 缓存{"关" if o["no_result_cache"] else "开"}'
        lines.append(f'|{label}|' + "|".join(values) + "|")
    boundaries = [e for _, r in reports for run in r.get("runs", []) for e in run.get("robustness", {}).get("events", [])]
    lines += ["", "## 没有掩盖的语义失败", "", "|边界用例|符合预期|总次数|", "|---|---:|---:|"]
    for name in ["legal_many_to_many_distinct", "grain_predicate_or_bypass"]:
        selected = [e for e in boundaries if e["case"] == name]
        lines.append(f'|{name}|{sum(e["correct"] for e in selected)}|{len(selected)}|')
    lines += ["", "合法多对多 COUNT(DISTINCT) 被保守规则误拦截；状态条件被 OR 放宽后，文本匹配仍可能放行重复计费。这两类问题来自现有轻量审查的能力边界，不能用主负载的 100% 覆盖掉。", "",
              "## 可解释的成本证据", ""]
    cached = next((r for _, r in reports if not r.get("capacity_only") and r["options"]["agents"] == 64 and not r["options"]["no_result_cache"]), None)
    if cached:
        def cost(mode, kind):
            return sum(r["total_database"]["by_kind"][kind][1] for r in cached["runs"] if r["mode"] == mode) / 1000
        lines.append(f'64 agent 开缓存运行中，A 的检查成本合计 {cost("A", "check"):.2f} 秒，C 为 {cost("C", "check"):.2f} 秒。'
                     '因此该组反馈退化可以定位到检查阶段，而不能简单归因于业务 SQL 变慢。'
                     f'B 的检查成本为 {cost("B", "check"):.2f} 秒，修复成本由 A 的 {cost("A", "repair"):.2f} 秒降至 {cost("B", "repair"):.2f} 秒。')
    lines += ["", "## 解释范围", "",
              "- 24 agent 主运行因应用与数据库关闭中断，保留 19 个单元并补跑 6 个；详见该目录 oracle-note.md。源代码的恢复和报告能力有变化，不能声称完全连续的专用环境实验。",
              "- 64 agent 的两次缓存实验参数一致，各自在内部轮换五组；缓存开/关两大块没有交叉随机化。可以观察关缓存后共享仍获益，不能把两个百分比的差直接当作无偏缓存效应。",
              "- 24 与 64 agent 运行的数据规模、任务数不同，不用于推断单独增加 agent 数量的因果效应。",
              "- 15 张表来自三个同构自建业务域，16 种结构、48 个领域查询族；SQL 文本参数实例不等于结构数量。",
              "- 公开参照只有两个带来源的 TPC-DS 结构改写例子，不是原始 TPC-DS 或 Spider 全套工作负载。",
              "- 漂移检测使用显式 ETL 通知；恢复时间不是自动发现延迟。业务查询多为有界范围，不能解释为全表扫描吞吐。",
              "- 五轮 bootstrap 区间是描述性区间，单机、缓存与调度背景限制了外推。结果不证明真实 LLM 自我进化。",
              "", "复现与完整方法见 [研究协议](research-protocol.md)。原始结果保存在 results 中且被 Git 忽略；新克隆需要运行脚本重新生成。", ""]
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

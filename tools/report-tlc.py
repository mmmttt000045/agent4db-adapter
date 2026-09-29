"""Summarize paired real-data runs without treating non-adoption as optimization."""
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
GROUPS=['A','B','C','oldD','D','M']
DEFAULT=['KeyUnique','RowConservation','SampleFanout']

def read(p):return json.loads(p.read_text(encoding='utf-8'))

def summarize(directory):
    cells=read(directory/'cells.json')
    assert len(cells)==36, 'Expected all six arms and six balanced rounds'
    groups={}
    for g in GROUPS:
        selected=[c for c in cells if c['group']==g]
        reordered=orders=applies=0
        for c in selected:
            r=read(directory/c['directory']/'report.json')
            for trace in r['traces']:
                for event in trace:
                    e=event['detail']
                    if e.get('event')=='planned_order':
                        orders+=1;reordered+=e['checks']!=DEFAULT
            applies+=sum(isinstance(d.get('apply',{}).get('Ok'),dict) for d in r['decisions'])
        groups[g]=dict(db_seconds=statistics.mean(c['db_ms'] for c in selected)/1000,
            wall_seconds=statistics.mean(c['wall_seconds'] for c in selected),
            correct=sum(c['correct'] for c in selected),tasks=sum(c['tasks'] for c in selected),
            reordered=reordered,orders=orders,model_applies=applies)
    contrasts={}
    for baseline,policy in [('A','B'),('A','C'),('B','D'),('oldD','D'),('B','M')]:
        savings=[]
        for round in range(6):
            a=next(c for c in cells if c['group']==baseline and c['round']==round)
            b=next(c for c in cells if c['group']==policy and c['round']==round)
            savings.append(100*(a['db_ms']-b['db_ms'])/a['db_ms'])
        mean=statistics.mean(savings);half=2.571*statistics.stdev(savings)/math.sqrt(6)
        contrasts[f'{policy}/{baseline}']=dict(mean_percent=mean,ci95=[mean-half,mean+half],per_round=savings)
    return dict(groups=groups,contrasts=contrasts,directory=str(directory.relative_to(ROOT)))


def main():
    on=summarize(ROOT/'results/tlc-final-cache-on')
    off=summarize(ROOT/'results/tlc-final-cache-off')
    studies=[read(ROOT/'results'/name/'check-study.json') for name in ['tlc-final-checks',*[f'tlc-final-checks-{i}' for i in range(2,6)]]]
    manifest=read(ROOT/'results/tlc-real-data/manifest.json')
    checks=[]
    for index in range(2):
        experiment=studies[0]['experiments'][index]
        events=[e for study in studies for e in study['experiments'][index]['events']]
        per_round=[]
        for study in studies:
            one=study['experiments'][index]['events']
            c=sum(next(p['db_ms'] for p in e['paired_execution'] if p['candidate']) for e in one)
            b=sum(next(p['db_ms'] for p in e['paired_execution'] if not p['candidate']) for e in one)
            per_round.append(100*(b-c)/b)
        candidate=sum(next(p['db_ms'] for p in e['paired_execution'] if p['candidate']) for e in events)
        baseline=sum(next(p['db_ms'] for p in e['paired_execution'] if not p['candidate']) for e in events)
        checks.append(dict(key_probe_required=experiment['key_probe_required'],
            attempts=len(events),adopted=sum(e['adopted_before_execution'] for e in events),
            reordered=sum(e['order']!=DEFAULT for e in events),
            matching_verdicts=sum(e['paired_execution'][0]['pass']==e['paired_execution'][1]['pass'] for e in events),
            candidate_ms=candidate,baseline_ms=baseline,gross_saving_percent=100*(baseline-candidate)/baseline,
            per_round_gross_saving_percent=per_round,
            mean_round_gross_saving_percent=statistics.mean(per_round),
            mean_round_ci95=[statistics.mean(per_round)+sign*2.776*statistics.stdev(per_round)/math.sqrt(5) for sign in [-1,1]],
            observation_ms=sum(e['full_observation_db_ms'] for e in events)))
    summary=dict(cache_on=on,cache_off=off,check_study=checks,dataset=manifest)
    target=ROOT/'docs/real-data-validation.json'
    target.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 真实数据验证：反馈排序修正与 NYC TLC 实验','',
        '结论：本次确认了成本归集、训练/验证隔离和手动模式退化监测的修正；常规真实数据负载没有启用反馈换序，不能把组间耗时差解释为反馈获得加速。真实 LLM 未调用。','',
        '## 数据与处理','',
        '- 来源：[NYC TLC 官方行程数据](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)，2024 年 1、2 月 Yellow Taxi 与 Taxi Zone Lookup。官方提示数据由服务提供商提交，不保证全部记录准确。',
        f'- 原始行程 {manifest["counts"]["trips"]:,} 行；区域 {manifest["counts"]["zones"]} 行；从原始记录聚合得到区域日表 {manifest["counts"]["zone_day"]:,} 行。没有复制行程放大规模。',
        f'- PostgreSQL 表和索引 {manifest["relation_bytes"]:,} 字节（{manifest["relation_bytes"]/2**30:.3f} GiB）；这不是原始 Parquet 大小。',
        f'- 保留负金额 {manifest["quality"]["negative_total"]:,} 行、乘客数为空 {manifest["quality"]["null_passengers"]:,} 行、上车时间落在两个月之外 {manifest["quality"]["pickup_outside_two_months"]} 行；异常不做静默清洗。',
        '- 选择原始列并重命名；金额转为两位小数 NUMERIC；添加仅用于稳定排序的行号。zone_day 是派生汇总，不是第三份独立真实数据集。','',
        '## 实验设计','',
        '- 24 个并发脚本 agent，连接池 16；真实模型费用/调用次数为零。A=独立经验库+固定顺序，B=共享+固定顺序，C=独立经验库+修正版反馈，D=共享+修正版反馈；另有 oldD（提交 6fb11ba 的共享反馈）和 M（共享+Mock）。',
        '- 每种缓存条件 6 轮，每轮轮换 6 组的位置；每个组独立启动、清空 adapter 状态。所有组关闭 singleflight。两个缓存条件是先后运行，不把它们的差视为无偏缓存因果效应。',
        '- 10 种结构 × 16 个繁忙区域/日期参数 × 2 个月 = 320 条 SQL；包括关联聚合、HAVING、CTE、窗口排名、条件聚合、去重和 Top-N。每个 agent 执行同一套任务，组内随机顺序的种子一致。',
        '- 每组每轮 7,680 次任务，每个缓存条件 276,480 次；两个条件合计 552,960 次。参数文本数量不等于独立 SQL 结构数量。',
        '- 先执行 1 月参数，再执行 2 月参数；数据在实验前已全部装载。这是时间参数迁移，**不是在线 ETL 或未知数据漂移实验**。',
        '- 参考结果由只读 PostgreSQL 直连执行同一 SQL 得到，验证 adapter 的结果保持性；不是独立业务规格证明。参考执行和导入成本不计入测量组。',
        '- 数据库成本是并发查询耗时之和，包含 adapter 初始化、检查、守护与业务执行，不等于墙钟时间。不清空 OS/PG 缓存，本机热缓存下结果不能外推生产吞吐。','',
        '## 全流程结果','',
        '|组|缓存开 DB 秒/轮|缓存关 DB 秒/轮|两条件正确/任务|两条件实际换序/排序次数|',
        '|---|---:|---:|---:|---:|']
    for g in GROUPS:
        a,b=on['groups'][g],off['groups'][g]
        lines.append(f'|{g}|{a["db_seconds"]:.3f}|{b["db_seconds"]:.3f}|{a["correct"]+b["correct"]:,}/{a["tasks"]+b["tasks"]:,}|{a["reordered"]+b["reordered"]}/{a["orders"]+b["orders"]}|')
    lines+=['','降幅按同一轮配对后求均值，正数表示节约。括号为跨 6 轮的 Student-t 95% 描述性区间；不进行多重检验显著性宣称。','',
        '|比较|缓存开降幅 %（区间）|缓存关降幅 %（区间）|','|---|---:|---:|']
    for k in on['contrasts']:
        values=[]
        for result in [on,off]:
            c=result['contrasts'][k]
            values.append(f'{c["mean_percent"]:+.2f} [{c["ci95"][0]:+.2f}, {c["ci95"][1]:+.2f}]')
        lines.append(f'|{k}|{values[0]}|{values[1]}|')
    lines+=['','上述正常关联全部通过，没有失败候选供门槛验证。D/oldD 的细小差异包含并发时序、冷启动重复检查及系统噪声，**不能归因于自适应排序**。M 也没有应用模型策略。','',
        '## 真实失败候选的专项测量','',
        '直接执行真实 PostgreSQL 检查 SQL：以每天的真实行程和区域表构造右键不唯一的候选。1 月 24 天 + 2 月 24 天，分别测试“仍需补查键以决定修复”和“修复已穷尽，无需补查”两个状态，独立重启重复 5 轮。未伪造检查耗时或失败率。','',
        '冻结评分器后用后续不同日期候选组验证；每个候选分别实际执行默认/候选顺序，交替先后顺序。每次另执行全部三项以收集观测，100% 补充观测的费用单列。这是单连接、无缓存的检查级专项，不是 24 agent 的完整 adapter 运行。第二个状态由实验显式指定，未证明生产负载会经常到达它。','',
        '|修复状态|候选数|已采纳/实际换序|判定一致|候选成本 ms|默认成本 ms|额外全量观测 ms|','|---|---:|---:|---:|---:|---:|---:|']
    for e in checks:
        lines.append(f'|{"需补查键" if e["key_probe_required"] else "修复已穷尽"}|{e["attempts"]}|{e["adopted"]}/{e["reordered"]}|{e["matching_verdicts"]}/{e["attempts"]}|{e["candidate_ms"]:.1f}|{e["baseline_ms"]:.1f}|{e["observation_ms"]:.1f}|')
    e=checks[1]
    lines+=['',f'修复已穷尽条件下，跨 5 轮平均检查成本降幅 **{e["mean_round_gross_saving_percent"]:.2f}%**，描述性区间 [{e["mean_round_ci95"][0]:.2f}%, {e["mean_round_ci95"][1]:.2f}%]。这是扣除额外证据收集成本之前的检查执行收益。']
    lines+=['','只比较候选与默认执行会忽略获取证据的代价。必须同时看额外观测成本、真实部署中失败比例与复用频率；本专项不支持“整个系统净加速”的结论。','',
        '## 修正与回归验证','',
        '- 历史执行成本不可变；后续命中不能再次折扣它，复用观测自身为零。已执行的键检查不重复收费。',
        '- 评分器冻结；训练候选排除；重复候选组内平均；完整批次只决策一次。监测使用新的非重叠时间批次。',
        '- 模型候选等待证据时不会被周期性重建；已完成且被拒绝的候选不能追加样本反复试到通过。',
        '- HTTP 手动应用也有退化监测。集成测试用受控遥测验证自动回滚、且不生成新建议；受控测试数值不是上述真实数据性能证据。',
        '- 31 项测试通过（包含两项 PostgreSQL 集成测试）；Clippy -D warnings、格式检查通过。已有复杂 SQL 语义边界问题未在本次修复范围内。','',
        '## 复现与文件','',
        '在项目目录安装实验依赖、启动已配置的 PostgreSQL 后：','',
        '```powershell',
        'python -m pip install --target target/realdata-deps -r tools/requirements-real-data.txt',
        'python tools/prepare-tlc.py',
        'cargo build --locked --release',
        './tools/build-tlc-baseline.ps1',
        'python tools/run-tlc-suite.py --agents 24 --variants 16 --rounds 6 --out results/tlc-final-cache-on',
        'python tools/run-tlc-suite.py --agents 24 --variants 16 --rounds 6 --no-result-cache --out results/tlc-final-cache-off',
        '$env:AGENTDB_URL = (Get-Content results/tlc-real-data/connection.txt -Raw).Trim()',
        './target/release/agentdb-mid.exe --out results/tlc-final-checks real-bench --oracle unused --check-study',
        '2..5 | ForEach-Object { ./target/release/agentdb-mid.exe --out "results/tlc-final-checks-$_" real-bench --oracle unused --check-study }',
        'python tools/report-tlc.py',
        '```','',
        '- 导入会新建独立持久实验库，不修改 .env 指定的原数据库。连接信息保存在被 Git 忽略的 results/tlc-real-data/connection.txt。请勿上传该文件。',
        '- 主结果：results/tlc-final-cache-on、results/tlc-final-cache-off；每个目录包含原始逐请求结果、检查轨迹、参考结果、源码与二进制 SHA-256、实际运行的 old/new 二进制。',
        '- 专项：results/tlc-final-checks/check-study.json 及 tlc-final-checks-2 至 -5。整理后不含凭据的数值见 [JSON 汇总](real-data-validation.json)。',
        '- 早期 results/tlc-validation-main、results/tlc-validation-hotspots 是调试阶段运行，未混入本报告。',
        '- 原始文件 SHA-256 如下，便于发现官方文件后续替换：','']
    for f in manifest['files']:lines.append(f'- `{f["file"]}`：`{f["sha256"]}`')
    lines+=['','## 导出图','', '![真实数据全流程成本与反馈对照](figures/tlc-validation.png)']
    (ROOT/'docs/real-data-validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(contrasts_on=on['contrasts'],contrasts_off=off['contrasts'],checks=checks),indent=2))

if __name__=='__main__':main()

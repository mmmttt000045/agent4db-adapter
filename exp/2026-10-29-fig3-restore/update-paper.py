"""Apply the user's narrow correction; do not alter front matter or tables."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PAPER = ROOT/'overleaf'
protected_paths = ['sections/01-introduction.tex', 'sections/abstract.tex',
                   'sections/10-conclusion.tex', 'sections/02-background.tex',
                   'sections/03-overview.tex', 'sections/04-sharing.tex',
                   'sections/08-related-work.tex', 'sections/evaluation/setup.tex',
                   'sections/evaluation/cost.tex', 'sections/evaluation/changes.tex',
                   'paper.tex', 'latex/preamble.tex', 'figures/metric-record.tex',
                   'figures/metric-record.pdf', 'figures/metric-record-zh.pdf',
                   'figures/reuse-work.pdf', 'figures/reuse-work-zh.pdf']
protected_paths += [p.relative_to(PAPER).as_posix() for folder in ['tables','gen']
                    for p in (PAPER/folder).rglob('*') if p.is_file()]
protected={p:hashlib.sha256((PAPER/p).read_bytes()).hexdigest() for p in protected_paths}
before=json.loads((ROOT/'exp/2026-10-29-fig5-review/github-before.json').read_text(encoding='utf-8'))
old={f['path']:f for f in before['files']}
restored={}
for rel in ['figures/relbench-cumulative.pdf', 'figures/relbench-cumulative-zh.pdf',
            'figures/relbench-cumulative.tex']:
    source=ROOT/'tmp/paper-sync'/rel
    b=source.read_bytes() if source.suffix=='.pdf' else source.read_text(encoding='utf-8').encode()
    sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    assert sha==old[rel]['sha'],rel
    (PAPER/rel).write_bytes(b)
    restored[rel]=sha

eval_path=PAPER/'sections/07-evaluation.tex'
evaluation=eval_path.read_text(encoding='utf-8')
assert evaluation.count('\\input{sections/evaluation/quality}')==1
evaluation=evaluation.replace('\\input{sections/evaluation/quality}\n','')
eval_path.write_text(evaluation,encoding='utf-8',newline='\n')

rel_path=PAPER/'sections/evaluation/relbench.tex'
relbench=rel_path.read_text(encoding='utf-8')
official_start=relbench.index(r'\bi{\emph{Official-API study: tasks and time separation.}')
official_end=relbench.index('% Full official-API rows remain')
official_protocol=relbench[official_start:official_end].strip()
historical=relbench[:official_start]
historical=historical.replace('Table~\\ref{tab:relbench} reports the archived seven-method study:',
                              'Table~\\ref{tab:relbench} and Figure~\\ref{fig:relbench-cumulative} use the archived seven-method study:')
historical=historical.replace('表~\\ref{tab:relbench}报告归档的七方法实验：',
                              '表~\\ref{tab:relbench}与图~\\ref{fig:relbench-cumulative}使用归档的七方法实验：')
historical=historical.replace('\\input{tables/relbench}', '\\input{tables/relbench}\n\\input{figures/relbench-cumulative}')
historical+=r'''\bi{\emph{Historical cumulative cost.} Figure~\ref{fig:relbench-cumulative} retains the original five-cutoff results and includes memory operations from initial learning onward. It plots the six LLM-based methods; FeatPilot uses no LLM and remains in Table~\ref{tab:relbench}. Across all five cutoffs, \system\ uses \RbStackMavraTokSaveAll\% fewer tokens than no memory on rel-stack and \RbTrialMavraTokSaveAll\% fewer on rel-trial. The table's reuse-only reductions are \RbStackMavraTokSave\% and \RbTrialMavraTokSave\%. These results use the earlier gateway runs; the separate official-API study below supplies the agent-work figure.}
{\emph{历史累计代价。}图~\ref{fig:relbench-cumulative}保留原来的五截点结果，从初始学习起计入记忆操作。图中包含六种使用LLM的方法；FeatPilot不调用LLM，仍列于表~\ref{tab:relbench}。全部五个截点上，\system\ 相对无记忆在rel-stack与rel-trial分别减少\RbStackMavraTokSaveAll\%与\RbTrialMavraTokSaveAll\%的token；表中仅复用阶段的降幅为\RbStackMavraTokSave\%与\RbTrialMavraTokSave\%。这些结果来自较早的网关运行；下文独立的官方API实验用于智能体工作量图。}
'''
rel_path.write_text(historical,encoding='utf-8',newline='\n')

sharing_path=PAPER/'sections/evaluation/sharing.tex'
sharing=sharing_path.read_text(encoding='utf-8')
sharing=sharing.replace('\\input{figures/reuse-work}', '\\input{figures/reuse-work}\n'+official_protocol)
sharing=sharing.replace("Internal memory-model work is included in Figure~\\ref{fig:official-cumulative}'s accounting.",
                        "Internal memory-model work is included in the official study's total-token accounting, archived with all task scores.")
sharing=sharing.replace('记忆内部的模型工作计入图~\\ref{fig:official-cumulative}。',
                        '记忆内部的模型工作计入官方实验的总token，随全部任务分数一并归档。')
summary=r'''\bi{\emph{Quality and accounting context.} The complete official study retains all 90 sessions and their incurred costs. Relative to no memory, total tokens fall by \OfStackSaveAll\% on rel-stack and \OfTrialSaveAll\% on rel-trial; the reuse-stage reductions are \OfStackSaveReuse\% and \OfTrialSaveReuse\%. Across all three cutoffs, \OfFullQualityCount/6 tasks meet the predeclared quality margins. The study-adverse MAE is \OfAdverseRegression\% higher, outside the margin. \system\ produces nine valid rel-stack solutions and six valid rel-trial solutions; ACE, AWM, and G-Memory each produce seven on rel-trial. On site-success, only one of \system's three attempts is valid. The artifact retains every method's task scores, fallback outcomes, and memory costs. Each method has one sequence per database; its cutoffs are dependent observations.}
{\emph{质量与计量背景。}完整官方实验保留全部90个会话及已发生成本。相对无记忆，rel-stack与rel-trial的总token分别减少\OfStackSaveAll\%与\OfTrialSaveAll\%，复用阶段分别减少\OfStackSaveReuse\%与\OfTrialSaveReuse\%。全部三个截点上，\OfFullQualityCount/6项任务满足预设质量门槛；study-adverse MAE高\OfAdverseRegression\%，未达到门槛。\system\ 在rel-stack得到九个有效方案，在rel-trial得到六个；ACE、AWM与G-Memory在rel-trial各得到七个。site-success上，\system\ 的三次尝试仅一次有效。工件保留各方法全部任务分数、回退结果与记忆开销。每种方法在每个数据库只有一条序列，截点之间并非独立观测。}

'''
index=sharing.index(r'\bi{\emph{Reuse trace audit.}')
sharing=sharing[:index]+summary+sharing[index:]
sharing_path.write_text(sharing,encoding='utf-8',newline='\n')

fig=PAPER/'figures/reuse-work.tex'
text=fig.read_text(encoding='utf-8')
text=text.replace("Internal memory-model work is included in Figure~\\ref{fig:official-cumulative}'s total tokens.",
                  "The artifact's official-study total tokens include internal memory-model work.")
text=text.replace('内部记忆模型工作计入图~\\ref{fig:official-cumulative}的总token。',
                  '工件中的官方实验总token包含内部记忆模型工作。')
fig.write_text(text,encoding='utf-8',newline='\n')

population=PAPER/'sections/evaluation/population.tex'
text=population.read_text(encoding='utf-8')
text=text.replace('in Figures~\\ref{fig:official-cumulative}--\\ref{fig:reuse-work}',
                  'in Section~\\ref{sec:relbench-eval} and Figure~\\ref{fig:reuse-work}')
text=text.replace('见图~\\ref{fig:official-cumulative}--\\ref{fig:reuse-work}',
                  '见第~\\ref{sec:relbench-eval}节与图~\\ref{fig:reuse-work}')
population.write_text(text,encoding='utf-8',newline='\n')

readme=PAPER/'README.md';text=readme.read_text(encoding='utf-8')
start=text.index('官方 API 比较已完成：')
end=text.index('\n\n10-29逐会话复核',start)
text=text[:start]+'''官方 API 比较已完成：无记忆、ACE、AWM、G-Memory、MAVRA，两库、三任务、三截点，共90个正式会话。按用户最新要求，删除新增的六任务质量图；Fig.3 恢复 01daa213 的 `relbench-cumulative` 原图、图注与历史五截点数据。昨晚官方API实验仅用于原 Fig.5 的 `reuse-work` 工作量图；删除前一图后，它自动编号为 Fig.4。官方实验的设置、质量边界与来源审计集中在该图对应小节，完整数据仍在工件中。Table III、含旧数据的 Table IV、引言、摘要、结论及 Fig.1 位置均保持本轮修改前状态。历史网关结果与官方API结果分别陈述。'''+text[end:]
text=text.replace('当前 Fig.5 不作为结构化组合有效的独立证明','工作量图不作为结构化组合有效的独立证明')
start=text.index('Fig.4/5 的生成入口为')
text=text[:start]+'''工作量图沿用 `exp/2026-10-29-fig45-official/build-figures.py` 已生成的原 Fig.5 PDF，数据和版式本轮不变。此前生成的质量图与官方累计图从正文移除，文件作为历史版本留档，不再参与当前编译。恢复记录与源文件保护哈希见 `exp/2026-10-29-fig3-restore/`。\n'''
readme.write_text(text,encoding='utf-8',newline='\n')
assert protected=={p:hashlib.sha256((PAPER/p).read_bytes()).hexdigest() for p in protected}
(HERE/'protected-files.json').write_text(json.dumps(protected,indent=2)+'\n',encoding='utf-8',newline='\n')
(HERE/'restored-fig3.json').write_text(json.dumps({'source_commit':before['head'],'files':restored},indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'fig3_exact_old_files':list(restored),'quality_figure_in_paper':False,
                  'work_figure_pdf_unchanged':True,'protected_files':len(protected),'added_model_calls':0}))

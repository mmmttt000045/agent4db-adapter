"""Refactor official results without changing the user's table/Fig.1 choices."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / 'overleaf'
HERE = Path(__file__).resolve().parent
protected = ['tables/capabilities.tex', 'tables/relbench.tex', 'gen/relbench.tex',
             'gen/relbench-table.tex', 'figures/metric-record.tex', 'paper.tex',
             'sections/01-introduction.tex']
digests = {p: hashlib.sha256((PAPER/p).read_bytes()).hexdigest() for p in protected}
rel = PAPER / 'sections/evaluation/relbench.tex'
text = rel.read_text(encoding='utf-8')
trace = text[text.index(r'\bi{\emph{Reuse trace audit.}') :].strip()
assert trace.endswith('}')
text = text[:text.index(r'\bi{\emph{Quality and amortization.}')]
text += r'''\bi{\emph{Cost including learning.} Figure~\ref{fig:official-cumulative} charges memory construction from the first cutoff. Relative to no memory, \system\ reduces total tokens by \OfStackSaveAll\% on rel-stack and \OfTrialSaveAll\% on rel-trial, and reuse-stage tokens by \OfStackSaveReuse\% and \OfTrialSaveReuse\%. Relative to ACE, AWM, and G-Memory, respectively, it uses 45.7\%, 49.9\%, and 65.1\% fewer total tokens on rel-stack, and 36.7\%, 33.1\%, and 49.5\% fewer on rel-trial. Figure~\ref{fig:official-quality} reports the quality and valid-solution outcomes accompanying these savings. All incurred cost and completed failures are retained.}
{\emph{包含学习的代价。}图~\ref{fig:official-cumulative}从首截点起计入记忆构建。相对无记忆，\system\ 在rel-stack与rel-trial上的总token分别减少\OfStackSaveAll\%与\OfTrialSaveAll\%，复用阶段分别减少\OfStackSaveReuse\%与\OfTrialSaveReuse\%。相对ACE、AWM和G-Memory，rel-stack总token分别减少45.7\%、49.9\%和65.1\%，rel-trial分别减少36.7\%、33.1\%和49.5\%。图~\ref{fig:official-quality}报告这些节省对应的质量与有效方案情况；全部已发生成本与已完成的失败均予保留。}
'''
rel.write_text(text, encoding='utf-8', newline='\n')

sharing = r'''\subsection{\bt{Agent work and reuse behavior}{智能体工作与复用行为}}
\label{sec:sharing-eval}
\input{figures/reuse-work}
\bi{\emph{Where the work changes (Q2).} Figure~\ref{fig:reuse-work} decomposes the same official-API reuse sessions for no memory, ACE, AWM, G-Memory, and \system. On rel-stack, \system\ makes \OfStackExplore\ schema/probe calls per session versus \OfStackNoneExplore\ without memory, while retaining \OfStackValidate\ validation calls. On rel-trial these counts are \OfTrialExplore\ versus \OfTrialNoneExplore\ exploration calls and \OfTrialValidate\ validations. The published memory baselines make 14.5--21.3 exploration calls on rel-stack and 26.2--31.2 on rel-trial. The observed reduction is thus concentrated in schema inspection and SQL probing, with validation still performed. These counts include failed attempts and describe work distribution, not equal-cost operations or an isolated latency speedup. Internal memory-model work is included in Figure~\ref{fig:official-cumulative}'s accounting.}
{\emph{工作量在哪里改变（Q2）。}图~\ref{fig:reuse-work}分解无记忆、ACE、AWM、G-Memory与\system\ 的同一组官方API复用会话。rel-stack上，\system\ 每个会话进行\OfStackExplore{}次结构检查或SQL探查，无记忆为\OfStackNoneExplore{}次，同时保留\OfStackValidate{}次验证。rel-trial分别为\OfTrialExplore{}与\OfTrialNoneExplore{}次探索，以及\OfTrialValidate{}次验证。已发表记忆基线在rel-stack进行14.5--21.3次探索，在rel-trial为26.2--31.2次。观察到的减少因此主要来自结构检查与SQL探查，同时仍执行验证。这些次数包含失败尝试，描述工作量分布，不假设调用代价相等，也不构成隔离的延迟加速结论；记忆内部的模型工作计入图~\ref{fig:official-cumulative}。}

'''
sharing += trace + '\n'
(PAPER/'sections/evaluation/sharing.tex').write_text(sharing, encoding='utf-8', newline='\n')

pop = PAPER/'sections/evaluation/population.tex'
text = pop.read_text(encoding='utf-8').replace(r'\input{figures/population}'+'\n','')
start = text.index(r'\bi{\emph{What sharing saves.}')
end = text.index(r'\bi{\emph{Why memory must be shared.}')
text = text[:start] + r'''\bi{\emph{Memory-scope ablation.} Over \PpAgents\ agents, shared \system\ memory uses \PpMavraTotalTokM\,M tokens, \PpMavraTokSaveNone\% fewer than no memory, and answers \PpMavraAcc\% correctly versus \PpNoneAcc\%. Early sessions perform \PpMavraLearns\ extractions per run for five metrics; \PpMavraReused\% of all questions reuse a definition. Table~\ref{tab:popcost} reports the late-session work and accuracy. This controlled comparison varies memory scope within \system; the external-method comparison is reported in Figures~\ref{fig:official-cumulative}--\ref{fig:reuse-work}.}
{\emph{记忆作用域消融。}\PpAgents\ 个智能体使用共享\system\ 记忆时共花\PpMavraTotalTokM\,M token，比无记忆少\PpMavraTokSaveNone\%，正确率为\PpMavraAcc\%，无记忆为\PpNoneAcc\%。早期会话每次运行为五个指标提取\PpMavraLearns\ 次；全部问题中\PpMavraReused\%复用定义。表~\ref{tab:popcost}报告后期会话的工作量与正确率。该受控对照改变\system\ 内部的记忆作用域；外部方法比较见图~\ref{fig:official-cumulative}--\ref{fig:reuse-work}。}

''' + text[end:]
morning = (ROOT/'exp/2026-10-28-official/manuscript/sections/evaluation/sharing.tex').read_text(encoding='utf-8')
publication = morning[morning.index(r'\bi{\emph{Publication fidelity in the metric studies.}'):].strip()
text += '\n'+publication+'\n'
pop.write_text(text, encoding='utf-8', newline='\n')

readme = PAPER/'README.md'
text = readme.read_text(encoding='utf-8')
text = text.replace('Fig.5 已恢复本次推送前的 `consumer-cost` 散点图，展示独立受控指标实验的每题时间与 token 代价。',
                    'Fig.4 改为同一官方API实验五方法、六任务的质量与有效方案对照（`official-quality`）；Fig.5 恢复今早五方法的工作量分解版（`reuse-work`），仅修正内部记忆开销的说明。两图与 Fig.3 分别回答质量、工作变化和含学习总成本问题。')
text = text.replace('官方 API 复用轨迹审计保留在 RelBench 正文与审计工件中。','官方 API 复用轨迹审计保留在 Fig.5 对应正文与审计工件中。')
text += '\nFig.4/5 的生成入口为 `exp/2026-10-29-fig45-official/build-figures.py`；逐点数值与输入哈希见同目录 `figure-data.json`。全部90个官方API会话都进入质量图，失败按冻结协议保留回退分数并显示有效次数。Fig.5 使用每方法、每库六个复用会话；不将不同工具次数当作相同代价，也不把策略级结果解释为已完成组件消融。原 Fig.4 作用域消融保留正文和表格，旧图文件留档。\n'
readme.write_text(text, encoding='utf-8', newline='\n')
assert digests == {p:hashlib.sha256((PAPER/p).read_bytes()).hexdigest() for p in protected}
(HERE/'protected-files.json').write_text(json.dumps(digests,indent=2)+'\n',encoding='utf-8')
print('Rebuilt figure narrative; Table III, Table IV, Fig.1 and their sources unchanged.')

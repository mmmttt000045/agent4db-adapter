# MAVRA 用词与句式润色清单

## 1. 评审信息与范围

审阅对象：*MAVRA: Sharing and Maintaining Executable Knowledge for Data Agents*，2026-10-29 润色前的工作区稿件。英文入口为 `overleaf/main-en.tex`，中英对照入口为 `overleaf/main.tex`；两者共用正文。基准仓库提交为 `d9b91779ce9da762af998f94a4af3d21f36a2991`，本次判断针对已包含未提交修改的工作区内容。

Template: ccfa-review-1；Mode: writing；Detail: detailed；Rubric: writing，采用定性判断；Contribution type: 数据库系统论文。

检查了当前入口实际引用的 17 个正文源文件，并补查相关图注、表注与优化统计实现。重点是英文用词、句子语义、段落负担和术语一致性，中文建议针对对照稿中的典型表达。下文的局部候选措辞使用 `ccf-paper-writer` 的 polish 模式形成，供选用；已于 2026-10-29 按本清单同步润色中英文正文；原表达和候选措辞保留用于对照。本轮不评价科研新颖性、实验充分性或投稿格式合规性。

下文保留审阅时的源文件行号，一行可能包含整个段落；正文拆段后行号会顺延，可结合小节和原表达定位。报告内链接相对于本报告所在目录。

## 2. 写作结论与关键理由

全文的研究对象和主要机制能够读懂，优先工作是精确表达和拆分密集段落。最值得先改的是优化部分的统计量主语：低于零的是候选版本与原版本的配对执行时间差的置信区间，现稿却把“执行时间”写成了这个主语。其次是 `consuming snapshot`、`grain fails` 等过度压缩的表达，以及背景和优化结果段落中一次承担过多任务的长段落。

`spending LLM calls`、`Published memories`、`It extracts ... times` 等属于局部搭配或指称问题，可以直接润色。涉及数据观察和机制作用的句子，应区分“观察到错误集中在哪里”与“共享定义已解决这些错误”，而不是统一添加模糊限定词。

## 3. 论证与结构重建

| 位置 | 现有段落承担的作用 | 最小调整方向 |
| --- | --- | --- |
| 引言 | 从重复探索引出共享可执行定义，再介绍验证与维护 | 主线保留；三项挑战对应实际问题，无需为消除枚举形式而删除 |
| 背景第一小节 | 给出跨任务知识重复统计，并比较数据库缓存与智能体探索 | 将统计口径、重复程度、成本与错误类型分段说明 |
| 方法 | 定义共享对象，再解释发布、条件、维护、优化与特征复用 | 保留技术顺序；优化段落区分候选生成、等价性与成本准入 |
| 实验 | 分别陈述历史五截点比较、官方 API 比较和机制对照 | 保留实验批次及各自结论；展开影响解释的缩写和比较分母 |
| 讨论与结论 | 概括共享、验证及快照作用，并说明特征预实验的边界 | 将抽象名词串改为明确操作；保留尚未分离组合收益的事实 |

## 4. 主要优势

引言第 11 行能从同一营业额定义用于不同时段的例子说明参数化复用的必要性，具体对象先于系统细节，适合保留这一写法。[对应位置](../overleaf/sections/01-introduction.tex:11)

方法第 11 行将定义拆为业务含义、结构化实现、条件、学习记录和版本号，给后文提供了明确术语锚点。润色时应继续区分这些对象，不能把所有 `evidence` 机械替换为 `check results`。[对应位置](../overleaf/sections/04-sharing.tex:11)

RelBench 的历史五截点结果与官方 API 三截点结果分别陈述了质量和成本边界。两者的“六项任务满足质量界限”和“五项满足”分别对应不同实验，不能在润色时统一成同一个结论。[历史实验](../overleaf/sections/evaluation/relbench.tex:7)、[官方 API 实验](../overleaf/sections/evaluation/sharing.tex:9)

## 5. 写作问题与严重程度

### C001: 置信区间缺少正确的统计量主语

Type: confirmed_flaw
Severity: major
Location: `overleaf/sections/04-sharing.tex:71`；`overleaf/sections/evaluation/cost.tex:9`
Evidence: 方法写作 `the paired execution times ... must have a 95\% confidence interval below zero`；结果写作 `every 95\% interval below zero`。`src/feedback.rs` 的 `summarize` 先计算 `policy_ms - baseline_ms`，再对配对差值构造区间。
Countercheck: 已检查统计实现第 194—223 行以及 `tools/opt-stats.py` 的结果展示。负区间对应候选减基准的时间差；这里保留的是措辞错误，不是实验数值错误。
Judgment: 原句字面上要求执行时间的区间小于零，容易使读者误解成本准入规则。
Criterion: 科学表达精度、方法可读性。
Resolution: 明确比较量为 candidate minus current revision 的配对执行时间差，并在结果处使用相同定义。
Status: resolved

方法末句可改为：

> Cost: Within the same snapshot, we measure candidate and current execution times in alternating order over at least eight periods. The 95\% confidence interval for the mean paired difference, candidate minus current, must lie entirely below zero, and the mean saving must be at least 10\%.

结果中的括号可改为：

> mean \OptSaveMean\%, with every 95\% confidence interval for the mean paired execution-time difference lying entirely below zero

上述候选保留原有期间数、测量顺序、阈值与宏，不增加检验结论。

### C002: 英文搭配和动词宾语不够自然

Type: confirmed_flaw
Severity: minor
Location: 下表逐项定位。
Evidence: 存在把调用当作花费对象、把记忆方法简称为记忆，以及动词缺少提取对象等表达。
Countercheck: 不需要额外实验；已在所在段落检查实际对象，未将正常技术术语判为错误。
Judgment: 不妨碍大体理解，但会让读者停下来还原作者省略的动作或对象。
Criterion: 用词自然度、指称清晰度。
Resolution: 采用下列局部替换，保持对应技术对象。
Status: resolved

| 位置 | 原表达 | 建议表达 | 修改原因 |
| --- | --- | --- | --- |
| [摘要:2](../overleaf/sections/abstract.tex:2) | `spending LLM calls rediscovering calculations and structural assumptions from earlier sessions` | `using LLM calls to rediscover calculation logic and structural assumptions identified in earlier sessions` | 将动作写成重新发现计算逻辑和结构假设，避免把调用本身直接写成花费对象 |
| [背景:15](../overleaf/sections/02-background.tex:15) | `the agent still spends the LLM call that issues the lookup and reads its result` | `the agent still incurs the cost of an LLM call to issue the lookup and interpret its result` | 明确承担的是调用成本；`interpret` 对应前文的结果解释 |
| [背景:5](../overleaf/sections/02-background.tex:5) | `Half of LiveSQLBench's uses of knowledge` | `Half of the knowledge uses in LiveSQLBench` | 调整名词关系，保留知识使用次数这一统计对象 |
| [背景:15](../overleaf/sections/02-background.tex:15) | `prepared statements and the result cache, which answers 34\% of the reads, serve them well` | 单独陈述 `The result cache answers 34\% of read queries.`；预编译语句的作用另起一句 | `serve them well` 不明确；缓存命中数字不能同时解释两个组件的作用 |
| [设计:22](../overleaf/sections/04-sharing.tex:22) | `Data-only updates break learned SQL while the schema stays the same` | `Data updates can invalidate learned SQL even when the schema remains unchanged` | `break SQL` 容易让人想到语法或执行失败，实际讨论的是有效性条件失效 |
| [设计:48](../overleaf/sections/04-sharing.tex:48) | `When a fact-table grain fails` | `When the fact table violates grain uniqueness` | 失效的是粒度唯一性条件，粒度本身不会“失败” |
| [设计:75](../overleaf/sections/04-sharing.tex:75) | `the generated SQL of a key-range revision returns on $D$ what that of its previous revision returns` | `the key-range revision and its previous revision return the same result on $D$` | 去掉多层 `of` 和代词 `that`，保留原句前面的连续月份条件 |
| [设计:93](../overleaf/sections/04-sharing.tex:93) | `After a session whose features beat the entity-table reference` | `After a session produces features that outperform the entity-table reference` | 明确会话产生特征，再比较特征的预测表现 |
| [群体实验:6](../overleaf/sections/evaluation/population.tex:6) | `It extracts \PpMavraLearns\ times per run` | `It performs \PpMavraLearns\ extraction operations per run` | `extracts` 缺少对象；建议保留提取操作次数口径，不改写成成功发布的定义数 |
| [RelBench标题:1](../overleaf/sections/evaluation/relbench.tex:1) | `Published memories on RelBench` | `Published agent-memory methods on RelBench` | 明确比较对象是已发表方法 |
| [官方API实验:9](../overleaf/sections/evaluation/sharing.tex:9) | `Published memories use ... exploration calls` | `The published agent-memory methods use ... exploration calls` | 与标题及基线介绍保持相同指称 |
| [官方API实验:6](../overleaf/sections/evaluation/sharing.tex:6) | `Each validation fits fixed LightGBM` | `Each validation attempt trains a LightGBM model with a fixed configuration` | 将固定对象写清楚，避免被理解为复用同一个已训练模型 |

### C003: 术语和缩略表达要求读者反复还原对象

Type: clarification
Severity: minor
Location: 摘要第 2 行、设计第 3 行、官方 API 实验第 6 行、检查共享实验第 4 行、结论第 6 行。
Evidence: `consuming snapshot`、`two non-improvements`、`paired database-time ratios`、`snapshot lifetime connecting checks to execution` 等表达压缩了关键关系。
Countercheck: 图 `fixed-sharing` 的图注已说明配对耗时比以相同运行块中的 full-recheck 为分母，因此这一项是正文需要明确比较对象，不是分母缺失于整个稿件。
Judgment: 熟悉实现的读者能够推断含义，首次阅读者需要回查定义、图注或实现。
Criterion: 术语一致性、实验叙述和方法可读性。
Resolution: 使用稳定名称，明确事件、比较对象和条件。
Status: resolved

| 位置 | 原表达 | 建议或编辑方向 |
| --- | --- | --- |
| [摘要:2](../overleaf/sections/abstract.tex:2)、[设计:3](../overleaf/sections/04-sharing.tex:3) | `consuming snapshot` | `the snapshot used to execute the consuming query`；首次说明后可用 `query snapshot` |
| [摘要:2](../overleaf/sections/abstract.tex:2)、[设计:3](../overleaf/sections/04-sharing.tex:3) | `condition results` | 若指缓存的条件检查结论，与方法小标题统一为 `check results`；不要把学习记录等其他证据一并替换 |
| [官方API实验:6](../overleaf/sections/evaluation/sharing.tex:6)、[历史实验:3](../overleaf/sections/evaluation/relbench.tex:3) | `two non-improvements` | 写明 `two validation attempts without improvement`；是否需要 `consecutive` 应按实际停止逻辑决定 |
| [实验设置:5](../overleaf/sections/evaluation/setup.tex:5) | `highest month`、`largest monthly rise` | `the month with the highest metric value`、`the largest month-to-month increase`，补齐最高和增长的对象 |
| [检查共享:4](../overleaf/sections/evaluation/check-sharing.tex:4) | `paired database-time ratios` | `database-time ratios relative to the matched full-recheck baseline`，保留交错和同时到达两组的对应关系 |
| [结论:6](../overleaf/sections/10-conclusion.tex:6) | `with SQL/version caching a strong comparator` | 如指当前观察结果，可写 `SQL/version caching achieves similar reuse of identical checks`，直接说明相近的是哪项能力 |
| [结论:6](../overleaf/sections/10-conclusion.tex:6) | `isolate the snapshot lifetime connecting checks to execution` | `isolate the effect of retaining the validation snapshot until query execution`，直接描述快照保持到执行这一操作 |

### C004: 背景、优化和结果段落承担过多任务

Type: confirmed_flaw
Severity: minor
Location: `overleaf/sections/02-background.tex:5,15`；`overleaf/sections/04-sharing.tex:14,71`；`overleaf/sections/evaluation/cost.tex:9`。
Evidence: 背景第 15 行依次放入 Redset 模板重复、智能体模板多样性、事实重复、LLM 调用成本、外部研究、错误类型和唯一性检查。优化第 71 行同时介绍候选生成、可选 LLM 建议、发布策略及三类准入测试。成本第 9 行把优化收益与另一项失效回退实验接在一个长段落内。
Countercheck: G1—G7 和三类优化测试对应真实检查步骤，不能因分号较多就删减检查条件。引言的三项挑战也具有实际并列关系。
Judgment: 核心信息都有，但单段频繁切换问题，使读者难以保留主结论。单纯换同义词不会解决。
Criterion: 段落逻辑、句子负担和实验叙述。
Resolution: 在主题转换处拆段，将条件、指标和结论留在各自对应的解释旁。
Status: resolved

| 位置 | 建议分段点 | 每段保留的主句 |
| --- | --- | --- |
| [背景:5](../overleaf/sections/02-background.tex:5) | 在 `Table ... shows` 之前分段 | 第一段定义词汇统计口径；第二段报告跨任务重复及其随任务数的变化 |
| [背景:15](../overleaf/sections/02-background.tex:15) | 在 `Even with exact or semantic result caching` 和 `Incorrect answers can occur` 前分段 | 查询文本重复与知识重复不同；结果缓存仍保留 LLM 成本；指标定义和唯一性检查解释另外两类问题 |
| [设计:14](../overleaf/sections/04-sharing.tex:14) | 在 `Extraction is therefore model-based` 前分段 | 第一段解释候选来源与输入；第二段解释确定性发布检查，保留 G1—G7 |
| [设计:71](../overleaf/sections/04-sharing.tex:71) | 在 `A candidate must pass` 前分段 | 第一段说明候选如何生成和采用；第二段分别解释假设、等价性及成本准入 |
| [维护成本:9](../overleaf/sections/evaluation/cost.tex:9) | 在 `A separate system-level test` 前分段 | 第一段报告优化与复用收益；第二段报告连续性失效后的回退测试及正确性 |

### C005: 观察结果与机制效果的措辞需要分开

Type: clarification
Severity: minor
Location: `overleaf/sections/02-background.tex:5,15`。
Evidence: `Every task is answered by a new agent session` 未在本句说明独立会话设置；`Knowledge ... removes exploration` 未明确消除的是哪些重复步骤；`31 of the 32 wrong answers ... exactly where a shared definition helps` 从错误分布直接转向共享定义的作用。
Countercheck: 引言已使用 `When sessions run independently`；方法也说明检索未命中时会回到探索。因此不将这些句子理解为系统承诺消除所有探索，也不据此判定机制无效。
Judgment: 建议在这几个具体位置把设置和推论写清，避免读者把局部观察读成普遍结论。
Criterion: 主张表达精度、相邻句逻辑。
Resolution: 点明独立会话前提；区分观测到的错误分布与由此提出的共享定义动机。
Status: resolved

| 位置 | 原句或片段 | 候选表达 |
| --- | --- | --- |
| [背景:5](../overleaf/sections/02-background.tex:5) | `Every task is answered by a new agent session, which explores the knowledge again.` | `When tasks are answered by independent agent sessions, each session repeats this knowledge discovery.` |
| [背景:15](../overleaf/sections/02-background.tex:15) | `Knowledge that an agent has before it starts removes exploration` | `Providing relevant database knowledge before execution can reduce repeated exploration`；若要保留更强的动词，直接列出被省去的具体步骤 |
| [背景:15](../overleaf/sections/02-background.tex:15) | `31 of the 32 wrong answers occur when a question names a metric without defining it, exactly where a shared definition helps` | `Of the 32 incorrect answers, 31 occur when a question names a metric without defining it. This concentration motivates sharing explicit metric definitions across sessions.` |

第三项保留错误分布和研究动机，不把这项计数写成纠错效果实验。这里的建议针对这句话与其所引数字的对应关系。

### C006: 中文对照稿存在口语表达和直译痕迹

Type: confirmed_flaw
Severity: minor
Location: 背景第 6、16 行，设计第 40、69 行标题，结论第 7 行。
Evidence: `它把这些知识重新探索一遍`、`那次大模型调用照样要花` 等带口语色彩；`一次性维护` 容易被理解为整个生命周期只维护一次。
Countercheck: 英文方法明确是每次相关变化后由消费者共享维护结果，并非永久一次性完成；中文标题应保留这一含义。
Judgment: 不影响英文投稿版，但对照稿用于讨论时容易产生额外解释负担。
Criterion: 中文自然度、技术含义一致性。
Resolution: 使用明确动作和成本对象；将“同一次维护服务所有智能体”与“一次性维护”区分。
Status: resolved

| 位置 | 原表达 | 建议表达 |
| --- | --- | --- |
| [背景:6](../overleaf/sections/02-background.tex:6) | `每个任务都由一个新的智能体会话回答，它把这些知识重新探索一遍。` | `在独立会话设置下，每个新会话都会重复发现这些知识。` |
| [背景:16](../overleaf/sections/02-background.tex:16) | `发出这次查找、读取其结果的那次大模型调用照样要花` | `智能体仍需承担发起查找和解释结果的大模型调用开销` |
| [背景:16](../overleaf/sections/02-background.tex:16) | `答案在没有任何报错的情况下出错` | `SQL 未报告执行错误时，答案仍可能不正确` |
| [背景:16](../overleaf/sections/02-background.tex:16) | `这正是共享定义能帮上忙的地方` | `这一错误分布提示了跨会话共享明确指标定义的需求`；若与前句合写，优先使用上表对应的“研究动机”表述 |
| [设计标题:40](../overleaf/sections/04-sharing.tex:40) | `为所有智能体一次性维护` | `跨智能体共享维护结果` |
| [设计标题:69](../overleaf/sections/04-sharing.tex:69) | `为所有智能体一次性优化` | `一次优化供所有智能体复用` |
| [结论:7](../overleaf/sections/10-conclusion.tex:7) | `分离了将检查关联到执行所需的快照生命周期` | `分离检验了将验证快照保留至查询执行的作用` |

## 6. 读者视角与综合意见

从首次阅读者的角度，最需要帮助的是知道“哪个对象发生了什么变化”：执行时间还是时间差、粒度还是唯一性条件、记忆还是记忆方法、快照本身还是保留快照的操作。[C001]、[C002]、[C003] 直接影响这些判断。

从逐段阅读的角度，背景第 15 行和优化第 71 行的负担最大。应先按主题拆段，再处理个别词语；保留对实验设置和负面结果的必要交代。[C004]、[C005]

以上是同一次审阅中的不同阅读视角，没有使用独立评审者，也不构成多人共识。

## 7. 写作评分与置信度

本轮交付逐句润色诊断，采用定性评价。未计算综合写作分或录用分。

| 写作维度 | 判断 | 依据与修复方向 |
| --- | --- | --- |
| 故事线与动机 | 主线清楚，背景解释负担偏高 | 依据背景段落的实际主题切换进行拆分，[C004] |
| 贡献展示 | 主要贡献对象明确 | 保留可执行定义、共享验证及维护三个对象，不为变化措辞而更名 |
| 段落逻辑 | 局部需要调整 | 背景、优化准入与优化结果的分段点已经定位，[C004] |
| 主张与证据的表达对应 | 需要局部精确化；不评价证据充分性 | 明确时间差，并将错误分布作为动机陈述，[C001]、[C005] |
| 方法可读性 | 定义清楚，少数动作省略过多 | 将 `grain fails`、`consuming snapshot` 等展开，[C002]、[C003] |
| 实验叙述 | 批次有区分，部分比较对象需展开 | 说明耗时比分母和无改进事件，[C003] |
| 相关工作定位 | 仅评价文字可读性 | 枚举密度较高；本轮不验证被引工作或新颖性 |
| 术语与符号一致性 | 局部可统一 | 统一同一类检查结果的名称，同时保留学习记录与条件证据的区别，[C003] |
| 语言自然度 | 存在可直接修复的搭配和直译 | 依据英文及中文局部替换表，[C002]、[C006] |
| LaTeX 与格式纪律 | 未评估 | 本轮没有更改源文件或进行版面审查 |
| 用词引起的读者误解 | 主要集中在少数句子 | 优先处理统计量主语，再调整缩略表达，[C001]、[C003] |

对局部词语定位和统计量修复的置信度高；对全篇段落节奏的判断为中高。未以这些语言判断推断科研正确性或投稿结果。

## 8. 作者关键问题与改判条件

已核对停止逻辑：改进时连续计数清零，未改进时递增，连续两次未改进即停止。英文已补充 `consecutive validation attempts without improvement`，中文同步明确“连续两次验证未改进”。[C003] 已解决。

[C001] 已按实现明确时间差方向；[C005] 已将错误分布与共享定义的研究动机分别表述。两项修改均未改变实验数字或实验结论。

## 9. 修改优先级与复审记录

| ID | 优先级 | 修改动作 | 完成条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| [C001] | 先改 | 统一方法与结果中的配对时间差及区间方向 | 读者能明确负值表示候选执行更快；不改变原有数值和阈值 | resolved |
| [C003] | 先改 | 展开快照、耗时比分母和停止事件 | 不依赖实现背景即可理解对应对象；停止逻辑核对后选词 | resolved |
| [C004] | 随后 | 拆分背景、发布、优化及回退结果段落 | 每段集中回答一个问题，原检查条件与数据保留 | resolved |
| [C005] | 随后 | 明确独立会话前提及观察与动机的关系 | 不把计数直接表述为干预效果 | resolved |
| [C002] | 最后逐项处理 | 替换生硬搭配、补齐动词对象 | 保持计量单位、操作次数及方法对象不变 | resolved |
| [C006] | 与英文对应修改 | 修复中文口语、直译及一次性维护歧义 | 中英的前提、动作及范围保持一致 | resolved |

已完成 10 个正文源文件的中英文同步润色，并按主题拆分密集段落。修改前后逐项比较了数字、实验结果宏、公式、引用和交叉引用，均保持一致；57 组双语段落通过结构检查，未发现缺失的交叉引用。再次运行 CCFA 语言检查器后，对句长和分号密度提示进行了上下文复核，保留了发布检查等必要枚举。英文与双语入口均尝试编译，但本机未检测到可用的 TeX Live，备用 Tectonic 也因无法读取格式文件而失败，未生成新 PDF；分页与版面尚未验证。

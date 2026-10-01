# 参考文献全文核对（2026-10-01）

对象：`overleaf/main.tex` 的 59 条参考文献及正文中引用它们的全部句子。每条都在官方来源核对（DOI／Crossref、出版方页面、会议论文集、arXiv、OpenReview，产品文档核对现行页面），并逐句对照原文判断能否支撑。核对后删 1 条、增 2 条，现为 60 条；正文改写约 25 处（中英文同步）。

## 结论

- 59 条全部真实存在，没有虚构条目。预印本只有 AgentSM（arXiv 2601.15709）与 MemGPT（arXiv 2310.08560），条目已注明 preprint。
- 元数据需改 4 条：Databricks 页面标题、Ivanova 加文章号与页数、BIRD 标题大小写、APC 加 DOI。
- 问题主要在引用方式：约 20 处句子比原文说得更多、换了原文的意思，或把一篇文献用来支撑它没有讨论的内容。

## 删除

| 文献 | 原因 |
| --- | --- |
| li2024dawn（NL2SQL360，PVLDB 2024） | 被引来支撑“业务知识对真实表结构很重要”，但原文是 Spider／BIRD 上的方法评测平台，不讨论业务知识或企业表结构；没有其他合适位置 |

## 新增

| 文献 | 用途 | 核对 |
| --- | --- | --- |
| ma2018querybot（Ma et al., SIGMOD 2018, pp. 631–645） | 第 2.1 节：应用以不同参数反复调用相同查询，数百万条查询可归并为数千个模板 | Crossref；原文 §3：“the application invokes the same queries with different input parameters (e.g., prepared statements)”；表 2：“from millions to at most thousands of templates” |
| redset2024dataset（Redset 数据集与文档，GitHub） | 第 2.1 节：特征指纹“A proxy for query-likeness … Will overestimate repetition”；“non-representative biased random sample” | 数据集 README（论文本身不讨论这两点） |

另加 libpg\_query 脚注（指纹忽略常量与格式，README “Fingerprinting a query”），并在第 2.1 节加入 Redset 结果缓存命中率 34%（本组从 Redset 统计，见 `exp/2026-10-01-workload-characterization/redset/`）。

## 改写（按严重程度）

| 文献 | 原句问题 | 改为 |
| --- | --- | --- |
| li2026agenticmemory | 被引为“教程把过时记忆和变化的数据列为数据智能体的开放问题”；原文是通用智能体记忆教程，开放问题（§2.6）不含这两项，只在 §2.1 说记忆会积累 “redundant, outdated, or conflicting information” | 只引用后者；“变化的数据”只归 luo2026dataagents（§2.4.4） |
| curino2008prism、zhang2025evoschema | 被称为“按表结构变化失效”；PRISM 是模式演化下的影响评估与查询改写，EvoSchema 是鲁棒性基准，都没有失效机制 | “模式演化支持针对表和列的变化，因此按表结构变化维护会漏掉……” |
| lenz1997、mazon2009（引言） | “这些性质（含日期角色）是可汇总性条件的实例”；日期角色不是可汇总性条件，与正文第 2.3 节自相矛盾 | “前两项是可汇总性条件的实例，第三项规定日期关系” |
| mazon2009（第 2.3 节） | “条件是数据实例的性质，因此每次更新都要重查”；Mazón 认为一半条件属模式层，“每次更新都检查”只针对实例层方法 | 改为 Lenz §4.1 的原意（实例上的检查只对当前数据成立，任何变化都需重查）＋ Mazón 对实例层方法的描述 |
| zhou2007lazy | 直接挂在“定义级懒重验证标记待验证、首次使用时检查、通过检查与修复保持正确”上；原文是视图懒维护，不涉及定义与检查 | “把物化视图的懒维护用到定义上” |
| biswal2026agentsm | “把成功轨迹组织成语义记忆”“定义从查询历史学得”；AgentSM 不按成功筛选（合成题轨迹不判题），也不用查询历史、不学定义 | “把既往执行轨迹组织成语义记忆”；查询历史只归 DataLab |
| redyuk2021dynamic | 被引为“从数据中推断约束”；原文明确不用约束，用批次统计做新颖性检测 | “学习可接受的批次画像” |
| lei2025spider2 | 被引为“业务知识的重要性”；Spider 2.0 强调大表结构、方言与文档，错误以数据分析与模式链接为主 | 归入“真实企业表结构、术语与文档仍然困难” |
| breck2019validation | “数据验证系统声明式地执行这类（唯一性、依赖）检查”；Breck 的 schema 无唯一性与依赖约束 | 这类检查只归 Deequ；Breck 改为“按模式验证每个新批次” |
| ilyas2004cords | 与 Godfrey 并列为“当前数据上成立的软约束”；CORDS 的 soft FD 是概率依赖，用于选择率估计 | 分开表述 |
| liu2026agents | 引言首句“正在成为主要使用者”，原文是预测（“likely to become the dominant workload”）；“50 次尝试中不同子计划 10–20%”漏了“各种规模”“GPT-4o-mini 独立尝试” | “预期成为数据系统的主要负载”；补全限定词 |
| luo2026dataagents | 被用来支撑“主要使用者”“过时记忆”“重复探索” | 只支撑“新兴且快速增长”和“变化的数据” |
| li2023bird | 34.9% → 54.9% 是测试集数字（开发集为 30.9 → 46.4），证据是专家标注 | 注明“测试集”“专家标注” |
| databricks2026metricviews | 相关工作写“键与连接性质都不在运行时验证”；该页只说连接性质 `at_most_one_match` 不验证 | 只说连接性质；更正页面标题 |
| mazon2009（相关工作） | “综述多维模型如何违反这些条件”；原文只综述结构性违反，不含类型相容与数据层完备性 | 限定为非严格层次、事实与维度多对多等结构 |
| ivanova2010recycling | “在更新中复用中间结果”；实现只做按列失效，增量传播是展望 | “复用中间结果，并使受更新影响的结果失效” |
| kimball2013toolkit | “各数据集市间一致的定义”；第 3 版说跨业务过程（事实表）一致化维度与事实 | 照第 3 版改 |
| schelter2018deequ | “不断变化的数据集”；增量模式只支持追加 | “不断增长的数据集” |
| nishtala2013memcache | “避免惊群”；原文 “mitigates thundering herds” | “缓解惊群” |
| guo2024dsagent | “缓存既往方案”；原文是案例库 | “保存和复用既往方案” |

## 核对无误、未改的条目

abedjan2015profiling、abedjan2014swan、agarwal2025cachecraft、blakeley1986efficiently、blakeley1989irrelevant、ceri1990constraint、chhikara2025mem0、colby1996deferred、dar1996semantic、floratou2024nl2sql、furst2025datamodel、garrod2008ferdinand、giannikis2012shareddb、godfrey2001soft、gunda2010nectar、gupta1995maintenance（Data Eng. Bull. 邀稿综述）、hammer2014adapton、harizopoulos2005qpipe、horner2004additivity、huo2026birdinteract、hyde2024measures、jiang2025siriusbi、mokhov2018build、nicolas1982integrity（全文付费，只核对到摘要）、ouyang2026reasoningbank、packer2023memgpt、ports2010txcache、schirmer2019dynfd、sellis1988mqo、sequeda2024kg（数字按 arXiv 版核对，ACM 全文被拦）、song2021autovalidate、vanrenen2024redset、wang2025awm、weng2025datalab、xu2025amem、zhang2025apc、zhang2026ace、zhao2024expel。

## 仍需注意

- Liu26 的例子是表结构更新与新增表，不是纯数据变化；正文只引用其“记忆库与数据不一致”的提醒，没有超出原意。
- Redset 论文“一半集群中 80% 的查询是完全重复”来自 Redshift 全体集群一个月的数据，不是 Redset；正文写作 “Redshift's own analysis”，不要改成 Redset 的结论。
- 441 M 是本组对 Redset 400 个集群的计数，不是论文或数据集声明的数字。

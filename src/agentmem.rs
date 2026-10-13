//! 单智能体记忆的对照基线（群体评测）：按各自论文的记忆设计在同一测评框架里重新实现，
//! 模型、工具、题目与学习信号都与其他组相同，只有跨会话的记忆不同。
//! - AWM（Agent Workflow Memory，Wang et al.）：从判定成功的任务归纳可复用的工作流（题目取值换成占位符），全部放进系统提示；
//! - ACE（Agentic Context Engineering，Zhang et al.）：每次任务后由反思者总结经验、整理者以增量条目更新经验手册，
//!   条目带“有用 / 有害”计数，整本手册放进系统提示；
//! - Mem0（Chhikara et al.）：从每次会话提取事实，再对照最相似的已有记忆决定新增、更新、删除或不变；
//!   作答前按题面检索最相关的事实放进提示；
//! - AgentSM（Biswal et al.）：保存判定成功的任务轨迹，按阶段分成探索段与执行段，写成带小标题的 Markdown；
//!   智能体用工具取回最相似题目的探索段。原文的组合工具与离线合成题不在实现之内（前者是智能体架构，后者不是边用边学）。
//! 默认每个智能体一份记忆（与原设计相同）；`-shared` 变体所有智能体共用一份。
//! 检索相似度用字符二元组包含度（与示例检索相同），代替原文的向量检索。
//! 写记忆的模型调用与提炼一样计入触发它的会话（token 与秒数）。

use crate::llm::{AgentRun, Provider, Turn};
use parking_lot::Mutex;
use serde_json::{json, Value};
use std::collections::{BTreeSet, HashMap};
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Awm,
    Ace,
    Mem0,
    AgentSm,
}

#[derive(Clone, Debug)]
struct Item {
    id: u32,
    /// AWM：工作流标题；ACE：所属小节；Mem0：空；AgentSM：来源题面
    title: String,
    text: String,
    helpful: i32,
    harmful: i32,
}

#[derive(Default)]
pub struct Store {
    kind: Option<Kind>,
    shared: bool,
    items: Mutex<HashMap<String, Vec<Item>>>,
    next: Mutex<u32>,
}

/// 一次会话的结果，写记忆时用。
pub struct Session<'a> {
    pub question: &'a str,
    pub run: &'a AgentRun,
    pub correct: bool,
    /// 参与最终答案的 SQL（AgentSM 用来区分执行段与探索段）
    pub used_sqls: &'a [String],
}

const ACE_CAP: usize = 40;
const MEM0_TOPK: usize = 10;

fn grams(s: &str) -> BTreeSet<(char, char)> {
    let cs: Vec<char> = s.chars().filter(|c| !c.is_whitespace() && !c.is_ascii_punctuation()).flat_map(char::to_lowercase).collect();
    cs.windows(2).map(|w| (w[0], w[1])).collect()
}

/// 查询的二元组有多少出现在文本里。
fn containment(query: &str, text: &str) -> f64 {
    let (q, t) = (grams(query), grams(text));
    if q.is_empty() {
        return 0.0;
    }
    q.intersection(&t).count() as f64 / q.len() as f64
}

fn clip(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        format!("{}…", s.chars().take(n).collect::<String>())
    }
}

/// 会话轨迹的文本形式：每次工具调用一行，结果截断。
fn transcript(run: &AgentRun, out_chars: usize) -> String {
    let mut lines = vec![];
    for (k, step) in run.transcript.iter().enumerate() {
        let tool = step["tool"].as_str().unwrap_or_default();
        let input = clip(&step["input"].to_string(), 600);
        let output = clip(step["output"].as_str().unwrap_or_default(), out_chars);
        lines.push(format!("{}. {tool} {input}\n   → {output}", k + 1));
    }
    lines.join("\n")
}

/// 模型输出里的第一个 JSON 值（对象或数组）。
fn first_json(text: &str) -> Option<Value> {
    let start = text.find(['{', '['])?;
    let close = if text[start..].starts_with('{') { '}' } else { ']' };
    let end = text.rfind(close)?;
    (end > start).then(|| serde_json::from_str(&text[start..=end]).ok()).flatten()
}

const AWM_SYSTEM: &str = "你负责为一个数据分析智能体归纳可复用的工作流（Agent Workflow Memory）。输入是它成功完成的一次任务：题目和按顺序的工具调用与结果。\
请归纳出能复用到同类问题的工作流：每个工作流有一个标题（描述它解决的一类问题）和若干步骤，步骤写清用到的表、关联、过滤条件和 SQL 写法，\
把题目里的具体取值（年份、月份、季度等）换成占位符，如 {year}、{month}。只保留对完成任务必要的步骤，去掉走错的弯路。\
只输出一个 JSON 数组，最多 2 项：[{\"title\": \"...\", \"steps\": [\"...\", \"...\"]}]。";

const ACE_SYSTEM: &str = "你负责维护一个数据分析智能体的经验手册（Agentic Context Engineering 中的反思者与整理者）。\
手册是条目化的经验清单，整本放在智能体的提示里，帮助它更快、更准地回答之后的问题。输入是现有手册（带编号）和一次任务的完整过程，\
以及这次答案是否被判定正确。请先反思：哪些做法有效，哪些出错或浪费了步骤，哪些知识（表、列、关联、过滤、SQL 写法、业务口径）值得记住；\
再给出要加入手册的新条目（每条一到三句，具体可操作，不要与已有条目重复），并标出这次任务中有帮助或有害的已有条目编号。\
只输出一个 JSON 对象：{\"add\": [{\"section\": \"schema|sql|metric|pitfall\", \"content\": \"...\"}], \"helpful\": [编号], \"harmful\": [编号]}；add 最多 4 条。";

const MEM0_EXTRACT: &str = "你负责从一个数据分析智能体的会话中提取值得长期记住的事实（Mem0 的提取阶段）。\
事实是关于这个数据库与业务的简短陈述：表与列的含义、表之间如何关联、指标口径怎么算、取值与过滤条件、需要注意的坑。\
每条一句，彼此独立，不写本题的具体答案数值。只输出一个 JSON 数组，最多 8 条：[\"...\", \"...\"]。";

const MEM0_UPDATE: &str = "你负责更新一个记忆库（Mem0 的更新阶段）。输入是新提取的事实，以及记忆库中与它们最相似的已有记忆（带编号）。\
对每条新事实决定一个操作：ADD（新增）、UPDATE（用更完整或更正的内容替换某条已有记忆，给出编号与新内容）、DELETE（某条已有记忆与新事实矛盾、应删除，给出编号）、\
NONE（已有记忆已覆盖）。只输出一个 JSON 数组：[{\"op\": \"ADD\", \"text\": \"...\"}, {\"op\": \"UPDATE\", \"id\": 3, \"text\": \"...\"}, \
{\"op\": \"DELETE\", \"id\": 5}, {\"op\": \"NONE\"}]。";

pub const AGENTSM_TOOL: &str = "find_past_exploration";
pub const AGENTSM_SYSTEM: &str = "find_past_exploration 返回以往最相似问题的探索过程（看过哪些表与列、怎样关联、查到哪些取值）。\
开始探索前先调用它，据此省去重复的探索；最多查找三次，没有相符的过程时直接查看表结构计算。";

impl Store {
    pub fn for_mode(mode: &str) -> Store {
        let kind = match mode.trim_end_matches("-shared") {
            "mem-awm" => Some(Kind::Awm),
            "mem-ace" => Some(Kind::Ace),
            "mem-mem0" => Some(Kind::Mem0),
            "mem-agentsm" => Some(Kind::AgentSm),
            _ => None,
        };
        Store { kind, shared: mode.ends_with("-shared"), ..Default::default() }
    }

    pub fn kind(&self) -> Option<Kind> {
        self.kind
    }

    fn scope(&self, agent: &str) -> String {
        if self.shared {
            "*".into()
        } else {
            agent.into()
        }
    }

    fn items(&self, agent: &str) -> Vec<Item> {
        self.items.lock().get(&self.scope(agent)).cloned().unwrap_or_default()
    }

    fn id(&self) -> u32 {
        let mut n = self.next.lock();
        *n += 1;
        *n
    }

    /// 报告用：每份记忆的条目数与内容。
    pub fn dump(&self) -> Value {
        let items = self.items.lock();
        json!(items
            .iter()
            .map(|(k, v)| (k.clone(), json!(v.iter().map(|i| json!({"id": i.id, "title": i.title, "text": i.text,
                "helpful": i.helpful, "harmful": i.harmful})).collect::<Vec<_>>())))
            .collect::<serde_json::Map<_, _>>())
    }

    /// 放进系统提示的记忆（AWM 的工作流、ACE 的手册、Mem0 检索到的事实）；AgentSM 用工具，不进提示。
    pub fn prompt(&self, agent: &str, question: &str) -> String {
        let items = self.items(agent);
        if items.is_empty() {
            return String::new();
        }
        match self.kind {
            Some(Kind::Awm) => {
                let body: Vec<String> = items.iter().map(|i| format!("## {}\n{}", i.title, i.text)).collect();
                format!("\n以下是从以往任务归纳出的工作流，遇到同类问题时按其步骤完成：\n{}", body.join("\n"))
            }
            Some(Kind::Ace) => {
                let body: Vec<String> = items.iter().map(|i| format!("[{}] ({}) {}", i.id, i.title, i.text)).collect();
                format!("\n以下是经验手册，作答时参考：\n{}", body.join("\n"))
            }
            Some(Kind::Mem0) => {
                let mut scored: Vec<(f64, &Item)> = items.iter().map(|i| (containment(question, &i.text), i)).collect();
                scored.sort_by(|a, b| b.0.total_cmp(&a.0));
                let body: Vec<String> = scored.iter().take(MEM0_TOPK).map(|(_, i)| format!("- {}", i.text)).collect();
                format!("\n以下是与本题相关的记忆：\n{}", body.join("\n"))
            }
            _ => String::new(),
        }
    }

    /// AgentSM 的检索工具：最相似题目的探索段。
    pub fn find_exploration(&self, agent: &str, query: &str) -> Value {
        let items = self.items(agent);
        let best = items.iter().map(|i| (containment(query, &i.title), i)).filter(|(s, _)| *s >= 0.3).max_by(|a, b| a.0.total_cmp(&b.0));
        match best {
            Some((s, i)) => json!({"similarity": (s * 100.0).round() / 100.0, "question": i.title, "exploration": i.text}),
            None => json!({"note": "没有相似问题的探索过程；请直接查看表结构计算"}),
        }
    }

    /// 会话结束后写记忆；返回写记忆的代价（与提炼同样记在 learning.extraction 下）。
    pub async fn write(&self, p: &Provider, agent: &str, s: &Session<'_>) -> Value {
        let Some(kind) = self.kind else { return Value::Null };
        let t0 = Instant::now();
        let (mut tin, mut tout, mut calls) = (0u64, 0u64, 0u32);
        let mut ask = |system: &'static str, input: String| {
            calls += 1;
            async move {
                match p.chat(system, &[Turn::User(input)], &[]).await {
                    Ok(r) => (r.input_tokens, r.output_tokens, first_json(&r.text)),
                    Err(_) => (0, 0, None),
                }
            }
        };
        let scope = self.scope(agent);
        let mut changes = 0usize;
        match kind {
            Kind::Awm => {
                if !s.correct {
                    return json!({"kind": "awm", "skipped": "not judged correct"});
                }
                let input = format!("题目：{}\n\n过程：\n{}\n\n最终答案：{}", s.question, transcript(s.run, 900), s.run.answer.clone().unwrap_or_default());
                let (i, o, v) = ask(AWM_SYSTEM, input).await;
                (tin, tout) = (tin + i, tout + o);
                for w in v.and_then(|v| v.as_array().cloned()).unwrap_or_default() {
                    let title = w["title"].as_str().unwrap_or_default().trim().to_string();
                    let steps: Vec<String> = w["steps"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect()).unwrap_or_default();
                    if title.is_empty() || steps.is_empty() {
                        continue;
                    }
                    let text = steps.iter().enumerate().map(|(k, x)| format!("{}. {x}", k + 1)).collect::<Vec<_>>().join("\n");
                    let id = self.id();
                    let mut all = self.items.lock();
                    let list = all.entry(scope.clone()).or_default();
                    // 同名工作流以新归纳的为准
                    list.retain(|x| containment(&title, &x.title) < 0.9);
                    list.push(Item { id, title, text, helpful: 0, harmful: 0 });
                    changes += 1;
                }
            }
            Kind::Ace => {
                let book: Vec<String> = self.items(agent).iter().map(|i| format!("[{}] ({}) {}", i.id, i.title, i.text)).collect();
                let input = format!(
                    "现有手册：\n{}\n\n题目：{}\n\n过程：\n{}\n\n最终答案：{}；判定：{}",
                    if book.is_empty() { "（空）".to_string() } else { book.join("\n") },
                    s.question,
                    transcript(s.run, 900),
                    s.run.answer.clone().unwrap_or_default(),
                    if s.correct { "正确" } else { "错误" }
                );
                let (i, o, v) = ask(ACE_SYSTEM, input).await;
                (tin, tout) = (tin + i, tout + o);
                let v = v.unwrap_or(Value::Null);
                let ids = |k: &str| -> Vec<u32> { v[k].as_array().map(|a| a.iter().filter_map(|x| x.as_u64().map(|n| n as u32)).collect()).unwrap_or_default() };
                let (good, bad) = (ids("helpful"), ids("harmful"));
                let adds: Vec<(String, String)> = v["add"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .filter_map(|x| Some((x["section"].as_str().unwrap_or("sql").to_string(), x["content"].as_str()?.trim().to_string())))
                            .filter(|(_, c)| !c.is_empty())
                            .collect()
                    })
                    .unwrap_or_default();
                let new_ids: Vec<u32> = adds.iter().map(|_| self.id()).collect();
                let mut all = self.items.lock();
                let list = all.entry(scope.clone()).or_default();
                for x in list.iter_mut() {
                    x.helpful += i32::from(good.contains(&x.id));
                    x.harmful += i32::from(bad.contains(&x.id));
                }
                for ((section, content), id) in adds.into_iter().zip(new_ids) {
                    // 增量更新：与已有条目几乎相同的不重复加入
                    if list.iter().any(|x| containment(&content, &x.text) > 0.85) {
                        continue;
                    }
                    list.push(Item { id, title: section, text: content, helpful: 0, harmful: 0 });
                    changes += 1;
                }
                // 精简：被判有害多于有用的条目删去；超出上限时删去净得分最低的
                list.retain(|x| x.harmful <= x.helpful + 1);
                while list.len() > ACE_CAP {
                    let worst = list.iter().enumerate().min_by_key(|(_, x)| (x.helpful - x.harmful, x.id)).map(|(k, _)| k).unwrap_or(0);
                    list.remove(worst);
                }
            }
            Kind::Mem0 => {
                let input = format!("题目：{}\n\n过程：\n{}\n\n最终答案：{}", s.question, transcript(s.run, 900), s.run.answer.clone().unwrap_or_default());
                let (i, o, v) = ask(MEM0_EXTRACT, input).await;
                (tin, tout) = (tin + i, tout + o);
                let facts: Vec<String> = v.and_then(|v| v.as_array().cloned()).unwrap_or_default().iter().filter_map(|x| x.as_str().map(str::to_string)).collect();
                if !facts.is_empty() {
                    let existing = self.items(agent);
                    let mut near: Vec<&Item> = vec![];
                    for f in &facts {
                        let mut scored: Vec<(f64, &Item)> = existing.iter().map(|x| (containment(f, &x.text), x)).collect();
                        scored.sort_by(|a, b| b.0.total_cmp(&a.0));
                        for (_, x) in scored.into_iter().take(5) {
                            if !near.iter().any(|y| y.id == x.id) {
                                near.push(x);
                            }
                        }
                    }
                    let input = json!({"new_facts": facts, "existing": near.iter().map(|x| json!({"id": x.id, "text": x.text})).collect::<Vec<_>>()});
                    let (i, o, v) = ask(MEM0_UPDATE, serde_json::to_string_pretty(&input).unwrap_or_default()).await;
                    (tin, tout) = (tin + i, tout + o);
                    let ops = v.and_then(|v| v.as_array().cloned()).unwrap_or_default();
                    let new_ids: Vec<u32> = ops.iter().map(|_| self.id()).collect();
                    let mut all = self.items.lock();
                    let list = all.entry(scope.clone()).or_default();
                    for (op, id) in ops.iter().zip(new_ids) {
                        let text = op["text"].as_str().unwrap_or_default().trim().to_string();
                        let target = op["id"].as_u64().map(|n| n as u32);
                        match op["op"].as_str().unwrap_or_default() {
                            "ADD" if !text.is_empty() => {
                                list.push(Item { id, title: String::new(), text, helpful: 0, harmful: 0 });
                                changes += 1;
                            }
                            "UPDATE" if !text.is_empty() => {
                                if let Some(x) = list.iter_mut().find(|x| Some(x.id) == target) {
                                    x.text = text;
                                    changes += 1;
                                }
                            }
                            "DELETE" => {
                                let before = list.len();
                                list.retain(|x| Some(x.id) != target);
                                changes += before - list.len();
                            }
                            _ => {}
                        }
                    }
                }
            }
            Kind::AgentSm => {
                if !s.correct {
                    return json!({"kind": "agentsm", "skipped": "not judged correct"});
                }
                // 按阶段分段：参与最终答案的 SQL 为执行段，其余工具调用（看表、找关联、探查 SQL）为探索段；小标题由调用生成
                let mut explore = vec![];
                for step in &s.run.transcript {
                    let tool = step["tool"].as_str().unwrap_or_default();
                    let input = &step["input"];
                    let output = clip(step["output"].as_str().unwrap_or_default(), 700);
                    let header = match tool {
                        "list_tables" => "### 列出表".to_string(),
                        "describe_table" => format!("### 查看表 {}", input["table"].as_str().unwrap_or_default()),
                        "join_path" => format!("### 关联路径 {} → {}", input["table_a"].as_str().unwrap_or_default(), input["table_b"].as_str().unwrap_or_default()),
                        "check_join" => format!("### 检验关联 {} ⋈ {}", input["left"].as_str().unwrap_or_default(), input["right"].as_str().unwrap_or_default()),
                        "run_sql" => {
                            let sql = input["sql"].as_str().unwrap_or_default();
                            if s.used_sqls.iter().any(|u| u.trim() == sql.trim()) {
                                continue;
                            }
                            format!("### 探查 SQL\n`{}`", clip(sql, 400))
                        }
                        _ => continue,
                    };
                    explore.push(format!("{header}\n{output}"));
                }
                if explore.is_empty() {
                    return json!({"kind": "agentsm", "skipped": "no exploration"});
                }
                let text = format!("## 探索\n{}", explore.join("\n"));
                let id = self.id();
                self.items.lock().entry(scope.clone()).or_default().push(Item {
                    id,
                    title: s.question.to_string(),
                    text,
                    helpful: 0,
                    harmful: 0,
                });
                changes += 1;
            }
        }
        let size = self.items.lock().get(&scope).map_or(0, Vec::len);
        json!({"kind": format!("{kind:?}").to_lowercase(), "extraction": {"input_tokens": tin, "output_tokens": tout,
               "seconds": t0.elapsed().as_secs_f64(), "attempts": calls}, "changes": changes, "size": size})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_inside_text() {
        assert_eq!(first_json("说明 [1, 2] 结束"), Some(json!([1, 2])));
        assert_eq!(first_json("x {\"a\": 1} y"), Some(json!({"a": 1})));
        assert_eq!(first_json("没有"), None);
    }

    #[test]
    fn modes() {
        assert_eq!(Store::for_mode("mem-ace").kind(), Some(Kind::Ace));
        assert!(Store::for_mode("mem-agentsm-shared").shared);
        assert_eq!(Store::for_mode("metric-global-snap").kind(), None);
    }
}

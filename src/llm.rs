//! 真实 LLM Agent：Anthropic Messages API 与 OpenAI 兼容接口（DeepSeek / 通义 / Kimi / OpenAI 等），
//! 以及一个脚本化的 mock（无 key 时测试工具循环）。Agent 只能通过中间层的工具访问数据库。

use crate::db::Db;
use crate::etl;
use crate::middle::{tool_specs, Ctx, GuardMode, Middle, MiddleConfig, Scope, ToolSpec};
use crate::sim::{diff, md_table};
use crate::workload::{grade, questions, Question};
use anyhow::{anyhow, bail, Context, Result};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(Clone, Debug)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub input: Value,
}

/// 与厂商无关的对话记录；各 Provider 自己转换成请求格式。
#[derive(Clone, Debug)]
pub enum Turn {
    User(String),
    /// raw：厂商原样返回的助手消息（Anthropic 为 content 数组，需原样回传，含 thinking 块）
    Assistant {
        raw: Value,
    },
    ToolResults(Vec<(String, String, bool)>),
}

#[derive(Debug, Default)]
pub struct Reply {
    pub raw: Value,
    pub text: String,
    pub calls: Vec<ToolCall>,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub usage: Value,
}

#[derive(Default)]
pub struct OpenAiOptions {
    reasoning_effort: Option<String>,
    thinking: Option<String>,
    preserve_reasoning: bool,
}

/// OpenAi.vendor：报告中的服务名；openai 配置记为 openai-compatible，与旧报告一致
pub enum Provider {
    Anthropic { key: String, base: String, model: String, http: reqwest::Client },
    OpenAi { vendor: &'static str, key: String, base: String, model: String, options: OpenAiOptions, http: reqwest::Client },
    Mock,
}

/// OpenAI 兼容服务的内置配置：(provider 名, 环境变量前缀, 默认 base URL)。
/// 各服务的 key 与模型分别写在 .env（如 DEEPSEEK_API_KEY、ZHIPU_MODEL），切换或对照时只改 provider 名。
const OPENAI_PROFILES: [(&str, &str, &str); 3] = [
    ("openai", "OPENAI", "https://api.openai.com/v1"),
    ("deepseek", "DEEPSEEK", "https://api.deepseek.com"),
    ("zhipu", "ZHIPU", "https://open.bigmodel.cn/api/paas/v4"),
];

fn http() -> reqwest::Client {
    reqwest::Client::builder().timeout(Duration::from_secs(900)).build().expect("http client")
}

impl Provider {
    pub fn from_env(kind: &str) -> Result<Provider> {
        Self::from_lookup(kind, |k| std::env::var(k).ok().filter(|v| !v.is_empty()))
    }

    fn from_lookup(kind: &str, env: impl Fn(&str) -> Option<String>) -> Result<Provider> {
        if let Some(&(name, prefix, default_base)) = OPENAI_PROFILES.iter().find(|p| p.0 == kind) {
            let var = |k: &str| env(&format!("{prefix}_{k}"));
            let base = var("BASE_URL").unwrap_or_else(|| default_base.into());
            let thinking = var("THINKING");
            anyhow::ensure!(
                thinking.as_deref().is_none_or(|v| matches!(v, "enabled" | "disabled")),
                "{prefix}_THINKING 必须为 enabled 或 disabled"
            );
            // DeepSeek 与智谱 BigModel 的思考模式都要求在工具调用循环中原样回传 reasoning_content
            let preserve_reasoning =
                reqwest::Url::parse(&base).ok().is_some_and(|u| matches!(u.host_str(), Some("api.deepseek.com" | "open.bigmodel.cn")));
            return Ok(Provider::OpenAi {
                vendor: if name == "openai" { "openai-compatible" } else { name },
                key: var("API_KEY").ok_or_else(|| anyhow!("缺少 {prefix}_API_KEY（写在 .env 里）"))?,
                model: var("MODEL").ok_or_else(|| anyhow!("缺少 {prefix}_MODEL（如 deepseek-flash、glm-5.3、gpt-5）"))?,
                base,
                http: http(),
                options: OpenAiOptions { reasoning_effort: var("REASONING_EFFORT"), thinking, preserve_reasoning },
            });
        }
        Ok(match kind {
            "claude" | "anthropic" => Provider::Anthropic {
                key: env("ANTHROPIC_API_KEY").ok_or_else(|| anyhow!("缺少 ANTHROPIC_API_KEY（写在 .env 里）"))?,
                base: env("ANTHROPIC_BASE_URL").unwrap_or_else(|| "https://api.anthropic.com".into()),
                model: env("ANTHROPIC_MODEL").ok_or_else(|| anyhow!("缺少 ANTHROPIC_MODEL"))?,
                http: http(),
            },
            "mock" => Provider::Mock,
            _ => bail!("未知 provider：{kind}（可选 openai / deepseek / zhipu / claude / mock）"),
        })
    }

    pub fn label(&self) -> String {
        match self {
            Provider::Anthropic { model, .. } => format!("anthropic:{model}"),
            Provider::OpenAi { vendor, model, .. } => format!("{vendor}:{model}"),
            Provider::Mock => "mock".into(),
        }
    }

    /// 报告中记录的模型配置（不含 key）
    pub fn config(&self) -> Value {
        match self {
            Provider::Anthropic { base, model, .. } => json!({"provider": "anthropic", "base_url": base, "model": model}),
            Provider::OpenAi { vendor, base, model, options, .. } => json!({"provider": vendor, "base_url": base, "model": model,
                "reasoning_effort": options.reasoning_effort, "thinking": options.thinking}),
            Provider::Mock => json!({"provider": "mock"}),
        }
    }

    pub async fn chat(&self, system: &str, turns: &[Turn], tools: &[ToolSpec]) -> Result<Reply> {
        match self {
            Provider::Anthropic { key, base, model, http } => anthropic_chat(http, base, key, model, system, turns, tools).await,
            Provider::OpenAi { key, base, model, options, http, .. } => {
                openai_chat(http, base, key, (model, options), system, turns, tools).await
            }
            Provider::Mock => mock_chat(turns),
        }
    }
}

async fn post_json(req: reqwest::RequestBuilder, body: &Value) -> Result<Value> {
    let mut last = String::new();
    for attempt in 0..4 {
        let resp = req.try_clone().ok_or_else(|| anyhow!("请求无法重试"))?.json(body).send().await;
        match resp {
            Ok(r) => {
                let status = r.status();
                let text = r.text().await.unwrap_or_default();
                if status.is_success() {
                    return serde_json::from_str(&text).context("响应不是 JSON");
                }
                last = format!("HTTP {status}: {}", text.chars().take(500).collect::<String>());
                let retry = (status.as_u16() == 429 && !futile_429(&text)) || status.as_u16() == 529 || status.is_server_error();
                if !retry {
                    bail!(last);
                }
            }
            Err(e) => last = e.to_string(),
        }
        tokio::time::sleep(Duration::from_secs(2u64.pow(attempt + 1))).await;
    }
    bail!("多次重试后仍失败：{last}")
}

/// 智谱 BigModel 也用 429 表示欠费（1113）、内容审核拦截（1301）和额度用尽（1308 / 1310），重试无效
fn futile_429(body: &str) -> bool {
    let v: Value = serde_json::from_str(body).unwrap_or_default();
    let code = &v["error"]["code"];
    matches!(code.as_str().map_or_else(|| code.to_string(), str::to_string).as_str(), "1113" | "1301" | "1308" | "1310")
}

// ───────────────────────── Anthropic Messages API（原始 HTTP） ─────────────────────────

async fn anthropic_chat(
    http: &reqwest::Client,
    base: &str,
    key: &str,
    model: &str,
    system: &str,
    turns: &[Turn],
    tools: &[ToolSpec],
) -> Result<Reply> {
    let messages: Vec<Value> = turns
        .iter()
        .map(|t| match t {
            Turn::User(s) => json!({"role": "user", "content": s}),
            Turn::Assistant { raw } => json!({"role": "assistant", "content": raw}),
            Turn::ToolResults(rs) => json!({"role": "user", "content": rs.iter().map(|(id, c, err)| json!({
                "type": "tool_result", "tool_use_id": id, "content": c, "is_error": err
            })).collect::<Vec<_>>()}),
        })
        .collect();
    let tools: Vec<Value> = tools.iter().map(|t| json!({"name": t.name, "description": t.description, "input_schema": t.schema})).collect();
    let mut body = json!({"model": model, "max_tokens": 16000, "system": system, "messages": messages});
    if !tools.is_empty() {
        body["tools"] = json!(tools);
    }
    let mut req = http
        .post(format!("{}/v1/messages", base.trim_end_matches('/')))
        .header("x-api-key", key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json");
    // Opus 5 / Fable 5.1：安全分类器拒答时由服务端自动换模型重试
    if model.starts_with("claude-opus-5") || model.starts_with("claude-fable-5") {
        body["fallbacks"] = json!("default");
        req = req.header("anthropic-beta", "server-side-fallback-2026-07-01");
    }
    let v = post_json(req, &body).await?;
    let stop = v["stop_reason"].as_str().unwrap_or_default();
    if stop == "refusal" {
        bail!("模型拒绝回答：{}", v["stop_details"]);
    }
    let content = v["content"].clone();
    let mut r = Reply {
        raw: content.clone(),
        input_tokens: v["usage"]["input_tokens"].as_u64().unwrap_or(0),
        output_tokens: v["usage"]["output_tokens"].as_u64().unwrap_or(0),
        usage: v["usage"].clone(),
        ..Default::default()
    };
    for b in content.as_array().into_iter().flatten() {
        match b["type"].as_str() {
            Some("text") => r.text.push_str(b["text"].as_str().unwrap_or_default()),
            Some("tool_use") => r.calls.push(ToolCall {
                id: b["id"].as_str().unwrap_or_default().into(),
                name: b["name"].as_str().unwrap_or_default().into(),
                input: b["input"].clone(),
            }),
            _ => {}
        }
    }
    Ok(r)
}

// ───────────────────────── OpenAI 兼容 Chat Completions ─────────────────────────

async fn openai_chat(
    http: &reqwest::Client,
    base: &str,
    key: &str,
    (model, options): (&str, &OpenAiOptions),
    system: &str,
    turns: &[Turn],
    tools: &[ToolSpec],
) -> Result<Reply> {
    let mut messages = vec![json!({"role": "system", "content": system})];
    for t in turns {
        match t {
            Turn::User(s) => messages.push(json!({"role": "user", "content": s})),
            Turn::Assistant { raw } => {
                let mut m = raw.clone();
                if !options.preserve_reasoning {
                    if let Some(o) = m.as_object_mut() {
                        o.remove("reasoning_content");
                    }
                }
                messages.push(m);
            }
            Turn::ToolResults(rs) => {
                for (id, c, _) in rs {
                    messages.push(json!({"role": "tool", "tool_call_id": id, "content": c}));
                }
            }
        }
    }
    let tools: Vec<Value> = tools
        .iter()
        .map(|t| json!({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}))
        .collect();
    let mut body = json!({"model": model, "messages": messages});
    if let Some(effort) = &options.reasoning_effort {
        body["reasoning_effort"] = json!(effort);
    }
    if let Some(thinking) = &options.thinking {
        body["thinking"] = json!({"type":thinking});
    }
    if !tools.is_empty() {
        body["tools"] = json!(tools);
    }
    let req = http.post(format!("{}/chat/completions", base.trim_end_matches('/'))).bearer_auth(key);
    let v = post_json(req, &body).await?;
    // 智谱 BigModel：输出被内容审核截断或超出上下文窗口时回复不完整，按调用失败处理
    if let Some(r @ ("sensitive" | "model_context_window_exceeded")) = v["choices"][0]["finish_reason"].as_str() {
        bail!("模型回复不完整：finish_reason={r}");
    }
    let msg = v["choices"][0]["message"].clone();
    let mut r = Reply {
        raw: msg.clone(),
        text: msg["content"].as_str().unwrap_or_default().to_string(),
        input_tokens: v["usage"]["prompt_tokens"].as_u64().unwrap_or(0),
        output_tokens: v["usage"]["completion_tokens"].as_u64().unwrap_or(0),
        usage: v["usage"].clone(),
        ..Default::default()
    };
    for c in msg["tool_calls"].as_array().into_iter().flatten() {
        let args = c["function"]["arguments"].as_str().unwrap_or("{}");
        r.calls.push(ToolCall {
            id: c["id"].as_str().unwrap_or_default().into(),
            name: c["function"]["name"].as_str().unwrap_or_default().into(),
            input: serde_json::from_str(args).unwrap_or(json!({})),
        });
    }
    Ok(r)
}

// ───────────────────────── Mock：脚本化“马虎”Agent，用于无 key 时测试 ─────────────────────────

/// 先按只用单号关联的错误写法执行；被中间层拦下就改用标准 SQL；拿到结果后提交答案。
fn mock_chat(turns: &[Turn]) -> Result<Reply> {
    let Some(Turn::User(q)) = turns.first() else { bail!("mock：缺少问题") };
    let gold = questions().into_iter().find(|x| q.contains(x.text)).map(|x| x.gold_sql).unwrap_or("select 1");
    let trap = gold.replace(" and r.sr_item_sk = s.ss_item_sk", "").replace(" and r.cr_item_sk = s.cs_item_sk", "");
    let last = turns.iter().rev().find_map(|t| match t {
        Turn::ToolResults(rs) => rs.first().map(|r| r.1.clone()),
        _ => None,
    });
    let n_asst = turns.iter().filter(|t| matches!(t, Turn::Assistant { .. })).count();
    let call = |name: &str, input: Value| {
        let id = format!("mock_{n_asst}");
        let raw = json!([{"type": "tool_use", "id": id, "name": name, "input": input}]);
        Ok(Reply { raw, calls: vec![ToolCall { id, name: name.into(), input }], ..Default::default() })
    };
    match n_asst {
        0 => call("list_tables", json!({})),
        1 => call("run_sql", json!({"sql": trap})),
        _ => {
            let last: Value = serde_json::from_str(&last.unwrap_or_default()).unwrap_or_default();
            if last["rejected"].as_bool() == Some(true) || last.get("result").is_none() {
                call("run_sql", json!({"sql": gold}))
            } else {
                let ans = last["result"]["rows"][0][0].as_str().unwrap_or_default().to_string();
                call("final_answer", json!({"answer": ans, "sql": ""}))
            }
        }
    }
}

// ───────────────────────── Agent 循环 ─────────────────────────

const SYSTEM: &str = "你是一个数据分析 Agent，通过工具查询 PostgreSQL 上的 TPC-DS 零售数仓（门店 / 目录 / 网店三个渠道）。\
先弄清表结构与关联方式，再写 SQL；不要猜测列的含义。得到结果后调用 final_answer：answer 只写最终值（数字或类别名，不带单位与说明），sql 写得到它的那条 SQL。";

pub(crate) const SYSTEM_MIDDLE: &str = "工具由数据中间层提供：join_path 返回两表验证过的关联方式（含需要的行过滤）；\
run_sql 可能拒绝不可靠的写法并说明原因与建议，请按提示修改后重试；返回中的 notices 是中间层对你此前结果的提醒。";

/// `chain`：要求 Agent 给出参与答案的查询编号与算式（指标经验评测用）。
pub fn final_answer_spec(chain: bool) -> ToolSpec {
    let mut schema =
        json!({"type": "object", "properties": {"answer": {"type": "string"}, "sql": {"type": "string"}}, "required": ["answer"]});
    if chain {
        schema["properties"]["used"] = json!({"type": "array", "items": {"type": "string"},
            "description": "参与计算最终答案的查询编号（run_sql 返回的 ref，如 r2）"});
        schema["properties"]["derivation"] = json!({"type": "string",
            "description": "用查询编号写出的最终答案算式，如 r2 - r3；答案直接来自一条查询时写 r2。rN 取第 N 条查询结果第一行第一列的值，\
                            参与计算的查询请把所需的值放在第一列；只写算式，不加说明"});
    }
    ToolSpec { name: "final_answer", description: "提交最终答案。", schema }
}

pub fn clarification_spec() -> ToolSpec {
    ToolSpec {
        name: "ask_clarification",
        description: "题目中的业务口径不明确、且无法从数据或工具得到可靠定义时，请求澄清。调用后任务结束。",
        schema: json!({"type": "object", "properties": {"question": {"type": "string", "description": "需要澄清的内容"}}, "required": ["question"]}),
    }
}

fn parse_used(v: &Value) -> Vec<String> {
    v.as_array()
        .into_iter()
        .flatten()
        .filter_map(|x| match x {
            Value::String(s) => crate::metric::ref_index(s),
            Value::Number(n) => n.as_u64().and_then(|n| usize::try_from(n).ok()),
            _ => None,
        })
        .map(|n| format!("r{n}"))
        .collect()
}

#[derive(Debug, Default, serde::Serialize)]
pub struct AgentRun {
    pub answer: Option<String>,
    pub sql: Option<String>,
    pub steps: usize,
    pub tool_calls: usize,
    pub tool_errors: usize,
    pub rejections: usize,
    pub notices: usize,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub seconds: f64,
    pub used: Vec<String>,
    pub derivation: Option<String>,
    /// 调用了 ask_clarification（任务随即结束）
    pub clarification: Option<String>,
}

pub async fn run_agent(p: &Provider, mid: &Middle, ctx: &Ctx, question: &str, middle_tools: bool, max_steps: usize) -> Result<AgentRun> {
    let mut tools = tool_specs(middle_tools);
    tools.push(final_answer_spec(false));
    let system = if middle_tools { format!("{SYSTEM}\n{SYSTEM_MIDDLE}") } else { SYSTEM.to_string() };
    run_agent_with(p, mid, ctx, question, &system, &tools, max_steps).await
}

/// 通用 Agent 循环：由调用方给出系统提示与工具。final_answer 与 ask_clarification 结束任务，其余工具交给中间层。
pub async fn run_agent_with(
    p: &Provider,
    mid: &Middle,
    ctx: &Ctx,
    question: &str,
    system: &str,
    tools: &[ToolSpec],
    max_steps: usize,
) -> Result<AgentRun> {
    let mut turns = vec![Turn::User(question.to_string())];
    let mut run = AgentRun::default();
    let t0 = Instant::now();
    for _ in 0..max_steps {
        let r = p.chat(system, &turns, tools).await?;
        run.steps += 1;
        run.input_tokens += r.input_tokens;
        run.output_tokens += r.output_tokens;
        turns.push(Turn::Assistant { raw: r.raw.clone() });
        if r.calls.is_empty() {
            run.answer = Some(r.text.trim().to_string());
            break;
        }
        let mut results = vec![];
        let mut done = false;
        for c in &r.calls {
            run.tool_calls += 1;
            if c.name == "final_answer" {
                run.answer = c.input["answer"].as_str().map(str::to_string).or_else(|| Some(c.input["answer"].to_string()));
                run.sql = c.input["sql"].as_str().map(str::to_string);
                run.used = parse_used(&c.input["used"]);
                run.derivation = c.input["derivation"].as_str().map(str::trim).filter(|s| !s.is_empty()).map(str::to_string);
                done = true;
                results.push((c.id.clone(), "已记录".to_string(), false));
                continue;
            }
            if c.name == "ask_clarification" {
                run.clarification = Some(c.input["question"].as_str().unwrap_or_default().to_string());
                done = true;
                results.push((c.id.clone(), "已记录；本实验没有人工答复，任务结束。".to_string(), false));
                continue;
            }
            match mid.call_tool(ctx, &c.name, &c.input).await {
                Ok(v) => {
                    if v["rejected"].as_bool() == Some(true) {
                        run.rejections += 1;
                    }
                    run.notices += v["notices"].as_array().map_or(0, |a| a.len());
                    let s = v.to_string();
                    results.push((c.id.clone(), s.chars().take(12000).collect(), false));
                }
                Err(e) => {
                    run.tool_errors += 1;
                    results.push((c.id.clone(), format!("错误：{e:#}"), true));
                }
            }
        }
        if done {
            break;
        }
        turns.push(Turn::ToolResults(results));
    }
    run.seconds = t0.elapsed().as_secs_f64();
    Ok(run)
}

// ───────────────────────── LLM 实验：直连 vs 中间层 ─────────────────────────

fn llm_cfg(mode: &str) -> Result<(MiddleConfig, bool)> {
    Ok(match mode {
        "direct" => (
            MiddleConfig {
                name: mode.into(),
                scope: Scope::Session,
                singleflight: false,
                guard: GuardMode::Off,
                feedback: false,
                validate_sql: false,
                result_cache: false,
                ..Default::default()
            },
            false,
        ),
        "middle" => (MiddleConfig { name: mode.into(), ..Default::default() }, true),
        _ => bail!("未知模式 {mode}（可选 direct / middle）"),
    })
}

pub async fn llm_eval(
    db: Arc<Db>,
    admin: Arc<Db>,
    agents: Vec<(String, Provider)>,
    modes: &[String],
    qids: Option<Vec<String>>,
    max_steps: usize,
) -> Result<(Value, String)> {
    etl::setup(&admin).await?;
    etl::reset(&admin).await?;
    let qs: Vec<Question> = questions().into_iter().filter(|q| qids.as_ref().is_none_or(|v| v.iter().any(|x| x == q.id))).collect();
    let mut gold = std::collections::HashMap::new();
    for q in &qs {
        let r = admin.query(crate::db::QKind::Meta, q.gold_sql).await?;
        gold.insert(q.id, r.cell(0, 0).unwrap_or_default().to_string());
    }
    let mut runs = vec![];
    let mut rows = vec![];
    for mode in modes {
        let (cfg, mid_tools) = llm_cfg(mode)?;
        let mid = Middle::new(db.clone(), cfg).await?;
        for phase in ["v1", "v2"] {
            if phase == "v2" {
                etl::apply_v2(&admin).await?;
                mid.invalidate_versions();
            }
            for q in qs.iter().filter(|q| phase == "v1" || q.affected_by_v2) {
                for (agent, p) in &agents {
                    let ctx = Ctx::new(agent, &format!("{mode}-{phase}-{}", q.id), q.id);
                    let before = db.meter.snap();
                    let r = run_agent(p, &mid, &ctx, q.text, mid_tools, max_steps).await;
                    let d = diff(&before, &db.meter.snap());
                    let (ok, run) = match r {
                        Ok(run) => (run.answer.as_deref().is_some_and(|a| grade(a, &gold[q.id], q.numeric)), run),
                        Err(e) => {
                            eprintln!("    {agent} {} 出错：{e:#}", q.id);
                            (false, AgentRun::default())
                        }
                    };
                    eprintln!(
                        "  {mode:<6} {phase} {} {agent:<12} → {:<14} {} | 工具 {:>2} 次 | 拦下 {} | 数据库 {:>3} 条 {:>5.1} s | token {}/{}",
                        q.id,
                        run.answer.clone().unwrap_or_default().chars().take(14).collect::<String>(),
                        if ok { "✓" } else { "✗" },
                        run.tool_calls,
                        run.rejections,
                        d.queries,
                        d.db_ms / 1000.0,
                        run.input_tokens,
                        run.output_tokens
                    );
                    rows.push(vec![
                        mode.clone(),
                        phase.into(),
                        q.id.into(),
                        agent.clone(),
                        if ok { "✓".into() } else { "✗".into() },
                        run.answer.clone().unwrap_or_default(),
                        gold[q.id].clone(),
                        run.tool_calls.to_string(),
                        run.rejections.to_string(),
                        d.queries.to_string(),
                        format!("{:.1}", d.db_ms / 1000.0),
                        format!("{}", run.input_tokens + run.output_tokens),
                    ]);
                    runs.push(json!({"mode": mode, "phase": phase, "question": q.id, "agent": agent, "provider": p.label(),
                                     "correct": ok, "gold": gold[q.id], "run": run, "db_queries": d.queries, "db_seconds": d.db_ms / 1000.0}));
                }
            }
        }
        etl::reset(&admin).await?;
    }
    let md = format!(
        "### LLM Agent：直连 vs 中间层\n\n{}",
        md_table(&["模式", "数据", "题", "Agent", "对错", "回答", "标准答案", "工具调用", "拦下", "DB 查询", "DB s", "token"], &rows)
    );
    Ok((
        json!({"experiment": "llm", "agents": agents.iter().map(|(a, p)| json!({"agent": a, "provider": p.label()})).collect::<Vec<_>>(), "runs": runs}),
        md,
    ))
}

#[cfg(test)]
mod provider_tests {
    use super::*;
    use axum::{routing::post, Json, Router};

    #[tokio::test]
    async fn management_request_uses_configured_model_without_tools() {
        let app = Router::new().route(
            "/v1/chat/completions",
            post(|Json(body): Json<Value>| async move {
                assert_eq!(body["model"], "test-model");
                assert_eq!(body["messages"][0]["role"], "system");
                assert!(body.get("tools").is_none());
                Json(json!({"choices": [{"message": {"role": "assistant", "content": "{\"ok\":true}"}}]}))
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let provider = Provider::OpenAi {
            vendor: "openai-compatible",
            key: "test-key".into(),
            base: format!("http://{addr}/v1"),
            model: "test-model".into(),
            options: OpenAiOptions::default(),
            http: reqwest::Client::builder().no_proxy().build().unwrap(),
        };
        let reply = provider.chat("Return JSON", &[Turn::User("aggregate metrics".into())], &[]).await.unwrap();
        assert_eq!(reply.text, r#"{"ok":true}"#);
        assert!(reply.calls.is_empty());
        server.abort();
    }

    #[tokio::test]
    async fn deepseek_max_and_tool_history_are_preserved() {
        let app = Router::new().route(
            "/chat/completions",
            post(|Json(body): Json<Value>| async move {
                assert_eq!(body["model"], "deepseek-flash");
                assert_eq!(body["reasoning_effort"], "max");
                assert_eq!(body["thinking"]["type"], "enabled");
                assert_eq!(body["messages"][2]["reasoning_content"], "test fixture reasoning");
                assert_eq!(body["messages"][3]["tool_call_id"], "call-test");
                assert!(body["tools"].is_array());
                Json(json!({"choices":[{"message":{"role":"assistant","content":"OK"}}]}))
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let provider = Provider::OpenAi {
            vendor: "openai-compatible",
            key: "test-key".into(),
            base: format!("http://{addr}"),
            model: "deepseek-flash".into(),
            options: OpenAiOptions { reasoning_effort: Some("max".into()), thinking: Some("enabled".into()), preserve_reasoning: true },
            http: reqwest::Client::builder().no_proxy().build().unwrap(),
        };
        let turns = vec![
            Turn::User("test".into()),
            Turn::Assistant {
                raw: json!({"role":"assistant","content":null,
            "reasoning_content":"test fixture reasoning","tool_calls":[{"id":"call-test","type":"function",
            "function":{"name":"describe_table","arguments":"{}"}}]}),
            },
            Turn::ToolResults(vec![("call-test".into(), "{}".into(), false)]),
        ];
        let reply = provider.chat("test", &turns, &tool_specs(true)).await.unwrap();
        assert_eq!(reply.text, "OK");
        server.abort();
    }

    #[test]
    fn named_profiles_read_their_own_variables() {
        let vars = std::collections::HashMap::from([
            ("ZHIPU_API_KEY", "zhipu-key"),
            ("ZHIPU_MODEL", "glm-5.3"),
            ("OPENAI_API_KEY", "openai-key"),
            ("OPENAI_MODEL", "other"),
        ]);
        let lookup = |k: &str| vars.get(k).map(|v| v.to_string());
        let zhipu = Provider::from_lookup("zhipu", lookup).unwrap();
        assert_eq!(zhipu.label(), "zhipu:glm-5.3");
        let Provider::OpenAi { key, base, options, .. } = &zhipu else { panic!("zhipu 应为 OpenAI 兼容") };
        assert_eq!((key.as_str(), base.as_str()), ("zhipu-key", "https://open.bigmodel.cn/api/paas/v4"));
        assert!(options.preserve_reasoning);
        assert_eq!(Provider::from_lookup("openai", lookup).unwrap().label(), "openai-compatible:other");
        assert!(Provider::from_lookup("deepseek", lookup).is_err());
    }

    #[tokio::test]
    async fn zhipu_content_filter_fails_without_retry() {
        use axum::http::StatusCode;
        let app = Router::new().route(
            "/chat/completions",
            post(|Json(body): Json<Value>| async move {
                if body["model"] == "blocked-input" {
                    (StatusCode::TOO_MANY_REQUESTS, Json(json!({"error": {"code": "1301", "message": "test fixture"}})))
                } else {
                    (
                        StatusCode::OK,
                        Json(json!({"choices": [{"finish_reason": "sensitive", "message": {"role": "assistant", "content": ""}}]})),
                    )
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        for model in ["blocked-input", "blocked-output"] {
            let provider = Provider::OpenAi {
                vendor: "zhipu",
                key: "test-key".into(),
                base: format!("http://{addr}"),
                model: model.into(),
                options: OpenAiOptions::default(),
                http: reqwest::Client::builder().no_proxy().build().unwrap(),
            };
            let start = Instant::now();
            assert!(provider.chat("test", &[Turn::User("test".into())], &[]).await.is_err());
            assert!(start.elapsed() < Duration::from_secs(2), "{model} 不应重试");
        }
        server.abort();
    }
}

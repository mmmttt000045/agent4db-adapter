#!/usr/bin/env python3
"""Apply the analytical-task adapter in an isolated study checkout only.

Published memory algorithms/prompts are imported from the existing, attributed
adapters. The production checkout and the upstream G-Memory core are not edited.
"""
import hashlib
import json
from pathlib import Path


def replace(s, old, new, count=1):
    if s.count(old) != count:
        raise ValueError(f"Expected {count} occurrences, got {s.count(old)}: {old[:90]}")
    return s.replace(old, new)


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def main():
    root = Path.cwd()
    if root.name != "agentdb-published-scenarios-20261030":
        raise SystemExit("Use the separate study checkout")
    manifest = {}
    p = root / "src/metricbench.rs"
    s = p.read_text()
    manifest[str(p.relative_to(root))] = {"base_sha256_lf": sha(s)}
    s = replace(s, '"mem-reasoningbank", "mem-apc", "mem-reasoningbank-shared", "mem-apc-shared"]',
                '"mem-reasoningbank", "mem-apc", "mem-reasoningbank-shared", "mem-apc-shared", "paper-ace", "paper-awm", "paper-gmemory"]')
    s = replace(s, '"middle" | "reforce" => (base, true, false),',
                '"middle" | "reforce" | "paper-ace" | "paper-awm" | "paper-gmemory" => (base, true, false),')
    helper = '''async fn paper_memory(mode: &str, mut body: Value) -> Result<Value> {
    if !mode.starts_with("paper-") { return Ok(Value::Null); }
    body["key"] = json!(std::env::var("FIG6_CELL_KEY").context("FIG6_CELL_KEY missing")?);
    body["arm"] = json!(mode.trim_start_matches("paper-"));
    let url = std::env::var("FIG6_MEMORY_URL").context("FIG6_MEMORY_URL missing")?;
    let response = reqwest::Client::builder().no_proxy().timeout(std::time::Duration::from_secs(900)).build()?
        .post(url).json(&body).send().await?;
    let status = response.status();
    let value: Value = response.json().await?;
    ensure!(status.is_success() && value["error"].is_null(), "Published-memory adapter failed: {status}: {value}");
    Ok(value)
}

'''
    s = replace(s, "async fn run_task(ph: &Phase<'_>", helper + "async fn run_task(ph: &Phase<'_>")
    old = '''        let (memory, cost) = mid.amem.lookup(env.extractor, agent, &question).await;
        lookup = cost;
        let system = format!("{}{}", cell.system, memory);
        let mut r = llm::run_agent_with(env.agent, mid, &ctx, &question, &system, &cell.tools, env.o.max_steps as usize).await;'''
    new = '''        let (memory, actual_question) = if cell.mode.starts_with("paper-") {
            lookup = paper_memory(cell.mode, json!({"op":"begin", "question":question, "task":t.id,
                "metric":t.def.id, "agent":agent, "phase":ph.name, "ask":t.ask})).await?;
            (lookup["system_prompt"].as_str().unwrap_or_default().to_string(),
             format!("{}{}", question, lookup["user_prompt"].as_str().unwrap_or_default()))
        } else {
            let (memory, cost) = mid.amem.lookup(env.extractor, agent, &question).await;
            lookup = cost;
            (memory, question.clone())
        };
        let system = format!("{}{}", cell.system, memory);
        let mut tools = cell.tools.clone();
        if cell.mode == "paper-ace" {
            if let Some(tool) = tools.iter_mut().find(|t| t.name == "final_answer") {
                tool.schema["properties"]["bullet_ids"] = json!({"type":"array", "items":{"type":"string"},
                    "description":"IDs of ACE playbook bullets used for this answer"});
            }
        }
        let mut r = llm::run_agent_with(env.agent, mid, &ctx, &actual_question, &system, &tools, env.o.max_steps as usize).await;'''
    s = replace(s, old, new)
    marker = '    let plan = if env.o.no_explain || reforce'
    addition = '''    // Only binary outcome and the agent's own trace cross the memory boundary.
    let published_memory = if cell.mode.starts_with("paper-") {
        paper_memory(cell.mode, json!({"op":"end", "question":question, "task":t.id,
            "metric":t.def.id, "agent":agent, "phase":ph.name, "ask":t.ask, "correct":correct,
            "answer":run.answer, "sql":run.sql, "error":error, "transcript":run.transcript})).await?
    } else { Value::Null };
'''
    s = replace(s, marker, addition + marker)
    s = replace(s, '"sql_calls": log.calls.len(), "rejections": log.rejections, "reforce": reforce_info, "memory_lookup": lookup,',
                '"sql_calls": log.calls.len(), "rejections": log.rejections, "reforce": reforce_info, "memory_lookup": lookup, "published_memory": published_memory,')
    s = replace(s, '            None => checkpoint = Some(mid.checkpoint()),',
                '''            None => {
                checkpoint = Some(mid.checkpoint());
                paper_memory(cell.mode, json!({"op":"checkpoint"})).await?;
            },''')
    s = replace(s, '                mid.restore(checkpoint.as_ref().context("缺少留出后的经验库快照")?).await?;',
                '''                mid.restore(checkpoint.as_ref().context("缺少留出后的经验库快照")?).await?;
                paper_memory(cell.mode, json!({"op":"restore", "phase":phase})).await?;''')
    s = replace(s, 'format!("agentdb_metric_{}_{stamp}",', 'format!("agentdb_fig6pub_{}_{stamp}",')
    s = replace(s, '        let tasks = tasks_with(&o.metrics, o.question_set == "v2");',
                '        let tasks: Vec<_> = tasks_with(&o.metrics, o.question_set == "v2").into_iter().filter(|t| matches!(t.ask, Ask::Single { .. })).collect();')
    # Persist every task before a later memory/DB failure could abort a cell.
    s = replace(s, '    Ok(TaskRec { json, run, log, ctx, question, correct })',
                '''    use std::io::Write;
    let mut journal = std::fs::OpenOptions::new().create(true).append(true).open(format!("{}/task-journal.jsonl", env.dir))?;
    writeln!(journal, "{}", json)?;
    Ok(TaskRec { json, run, log, ctx, question, correct })''')
    p.write_text(s)
    manifest[str(p.relative_to(root))]["patched_sha256_lf"] = sha(s)
    p = root / "tools/relbench/gmemory_service.py"
    s = p.read_text()
    manifest[str(p.relative_to(root))] = {"base_sha256_lf": sha(s)}
    s = s.replace("relational database and feature engineering tasks", "relational database and analytical SQL tasks")
    s = replace(s, "The reason for the failure is that the submitted features did not reach a better validation score than the reference features.",
                "The reason for the failure is that the final answer was incorrect.")
    s = replace(s, "    - Whether the submitted feature SQL ran and returned one row per seed.\n    - Whether the features describe the target entity before the seed time.",
                "    - Whether the agent's SQL ran and used the required aggregation, joins, time filters and business definition.\n    - Whether the agent's own observations support its final answer.")
    s = replace(s, '    thinking = os.environ.get("GMEMORY_THINKING")', '''    # The official client returns an empty string after a transport error.
    # Surface that failure instead of silently treating absent memory as a result.
    native_call = gllm.GPTChat.__call__
    def checked_call(self, *args, **kwargs):
        answer = native_call(self, *args, **kwargs)
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("G-Memory received an empty model reply or transport failure")
        return answer
    gllm.GPTChat.__call__ = checked_call

    thinking = os.environ.get("GMEMORY_THINKING")''')
    p.write_text(s)
    manifest[str(p.relative_to(root))]["patched_sha256_lf"] = sha(s)
    p = root / "src/llm.rs"
    s = p.read_text()
    manifest[str(p.relative_to(root))] = {"base_sha256_lf": sha(s)}
    s = replace(s, '            let preserve_reasoning = reqwest::Url::parse(&base)',
                '            let preserve_reasoning = std::env::var_os("FIG6_PRESERVE_REASONING").is_some() || reqwest::Url::parse(&base)')
    s = replace(s, '    #[serde(skip)]\n    pub transcript: Vec<Value>,', '    pub transcript: Vec<Value>,')
    s = replace(s, '        turns.push(Turn::Assistant { raw: r.raw.clone() });',
                '''        run.transcript.push(json!({"kind":"assistant", "message":r.raw}));
        turns.push(Turn::Assistant { raw: r.raw.clone() });''')
    s = replace(s, 'run.transcript.push(json!({"tool": c.name, "input": c.input, "output": shown.chars().take(2000).collect::<String>()}));',
                'run.transcript.push(json!({"kind":"tool", "call_id":c.id, "status":status, "tool":c.name, "input":c.input, "output":shown.chars().take(12000).collect::<String>()}));')
    s = replace(s, '            if let Some(trace) = &mid.trace {',
                '''            if c.name == "final_answer" || c.name == "ask_clarification" {
                run.transcript.push(json!({"kind":"tool", "call_id":c.id, "status":status, "tool":c.name, "input":c.input, "output":"recorded"}));
            }
            if let Some(trace) = &mid.trace {''')
    p.write_text(s)
    manifest[str(p.relative_to(root))]["patched_sha256_lf"] = sha(s)
    out = root / "exp/2026-10-30-published-scenarios/runtime-patch-manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()

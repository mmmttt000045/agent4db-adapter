//! HTTP 接口：异构的用户 Agent 只和中间层对话（工具级 API，MCP 风格）。
//!
//!   GET  /v1/tools              工具列表与 JSON Schema
//!   POST /v1/tools/{name}       调用工具，body: {"agent": "...", "session": "...", "tables": [可选：角色可访问的表], "args": {...}}
//!   GET  /v1/stats              中间层统计
//!   GET  /v1/knowledge          经验库内容

use crate::middle::{tool_specs, Ctx, Middle, Role};
use crate::optimizer::Optimizer;
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::Arc;

#[derive(Deserialize)]
struct CallReq {
    agent: String,
    session: Option<String>,
    task: Option<String>,
    tables: Option<Vec<String>>,
    #[serde(default)]
    args: Value,
}

async fn list_tools() -> Json<Value> {
    Json(json!(tool_specs(true)))
}

async fn call(State(mid): State<Arc<Middle>>, Path(name): Path<String>, Json(req): Json<CallReq>) -> (StatusCode, Json<Value>) {
    let ctx = Ctx {
        agent: req.agent,
        session: req.session.unwrap_or_else(|| "default".into()),
        task: req.task.unwrap_or_default(),
        role: Role { name: "http".into(), tables: req.tables.map(|t| t.into_iter().collect()) },
    };
    match mid.call_tool(&ctx, &name, &req.args).await {
        Ok(v) => (StatusCode::OK, Json(v)),
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"error": format!("{e:#}")}))),
    }
}

async fn stats(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(mid.stats_json())
}

async fn knowledge(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(json!(mid.knowledge()))
}

struct Management {
    mid: Arc<Middle>,
    optimizer: Arc<Optimizer>,
}

// Cancelling the HTTP server must also stop its optimizer loop.
struct BackgroundTask(tokio::task::JoinHandle<()>);

impl Drop for BackgroundTask {
    fn drop(&mut self) {
        self.0.abort();
    }
}

fn management_result(result: anyhow::Result<Value>) -> (StatusCode, Json<Value>) {
    match result {
        Ok(v) => (StatusCode::OK, Json(v)),
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"error": format!("{e:#}")}))),
    }
}

async fn optimization_status(State(s): State<Arc<Management>>) -> Json<Value> {
    Json(s.optimizer.snapshot(&s.mid.fb))
}

async fn propose(State(s): State<Arc<Management>>) -> (StatusCode, Json<Value>) {
    management_result(s.optimizer.propose(&s.mid.fb).await.map(|p| json!(p)))
}

async fn apply_policy(State(s): State<Arc<Management>>, Path(id): Path<u64>) -> (StatusCode, Json<Value>) {
    management_result(s.optimizer.apply(id, &s.mid.fb))
}

async fn rollback_policy(State(s): State<Arc<Management>>) -> (StatusCode, Json<Value>) {
    management_result(s.optimizer.rollback(&s.mid.fb))
}

pub async fn serve(
    mid: Arc<Middle>,
    addr: &str,
    optimizer: Option<Arc<Optimizer>>,
    interval_secs: Option<usize>,
    auto_apply: bool,
) -> anyhow::Result<()> {
    let mut app = Router::new()
        .route("/v1/tools", get(list_tools))
        .route("/v1/tools/:name", post(call))
        .route("/v1/stats", get(stats))
        .route("/v1/knowledge", get(knowledge))
        .with_state(mid.clone());
    let listener = tokio::net::TcpListener::bind(addr).await?;
    let mut background = None;
    if let Some(optimizer) = optimizer {
        let management = Arc::new(Management { mid, optimizer });
        let routes = Router::new()
            .route("/v1/optimizer", get(optimization_status))
            .route("/v1/optimizer/propose", post(propose))
            .route("/v1/optimizer/apply/:id", post(apply_policy))
            .route("/v1/optimizer/rollback", post(rollback_policy))
            .with_state(management.clone());
        app = app.merge(routes);
        {
            let seconds = interval_secs.unwrap_or(30);
            background = Some(BackgroundTask(tokio::spawn(async move {
                let mut interval = tokio::time::interval(std::time::Duration::from_secs(seconds as u64));
                interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
                let mut last_runs = 0;
                let mut pending = None;
                loop {
                    interval.tick().await;
                    // 先看已应用策略在新证据上是否退化，再决定是否生成新建议。
                    match management.optimizer.watch(&management.mid.fb) {
                        Ok(Some(event)) => eprintln!("回放显示当前策略退化，已自动回滚：{}", event["replay"]),
                        Ok(None) => {}
                        Err(e) => eprintln!("退化监测失败，原策略保持：{e:#}"),
                    }
                    // Monitoring remains active even when proposal generation is manual.
                    if interval_secs.is_none() {
                        continue;
                    }
                    if let Some(id) = pending {
                        if management.optimizer.apply(id, &management.mid.fb).is_ok() {
                            pending = None;
                        } else if management.optimizer.pending_valid(id) {
                            continue;
                        } else {
                            pending = None;
                        }
                    }
                    let runs: u64 = management.mid.fb.snapshot().values().map(|s| s.runs).sum();
                    if runs == last_runs {
                        continue;
                    }
                    match management.optimizer.propose(&management.mid.fb).await {
                        Ok(p) => {
                            last_runs = runs;
                            eprintln!("优化建议 #{}：{}", p.id, p.policy.reason);
                            if auto_apply {
                                if let Err(e) = management.optimizer.apply(p.id, &management.mid.fb) {
                                    eprintln!("优化策略未应用：{e:#}");
                                    pending = Some(p.id);
                                }
                            }
                        }
                        Err(e) => eprintln!("优化周期保持原策略：{e:#}"),
                    }
                }
            })));
        }
    }
    eprintln!("中间层已启动：http://{addr}/v1/tools");
    let result = axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await;
    drop(background);
    result?;
    Ok(())
}

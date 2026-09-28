//! HTTP 接口：异构的用户 Agent 只和中间层对话（工具级 API，MCP 风格）。
//!
//!   GET  /v1/tools              工具列表与 JSON Schema
//!   POST /v1/tools/{name}       调用工具，body: {"agent": "...", "session": "...", "tables": [可选：角色可访问的表], "args": {...}}
//!   GET  /v1/stats              中间层统计
//!   GET  /v1/knowledge          经验库内容

use crate::middle::{tool_specs, Ctx, Middle, Role};
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

pub async fn serve(mid: Arc<Middle>, addr: &str) -> anyhow::Result<()> {
    let app = Router::new()
        .route("/v1/tools", get(list_tools))
        .route("/v1/tools/:name", post(call))
        .route("/v1/stats", get(stats))
        .route("/v1/knowledge", get(knowledge))
        .with_state(mid);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    eprintln!("中间层已启动：http://{addr}/v1/tools");
    axum::serve(listener, app).await?;
    Ok(())
}

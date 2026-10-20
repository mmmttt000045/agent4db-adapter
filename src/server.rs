//! HTTP 接口：异构的用户 Agent 只和中间层对话（工具级 API，MCP 风格）。
//!
//!   GET  /v1/tools              工具列表与 JSON Schema（含 find_metric，run_sql 带 metrics 声明）
//!   POST /v1/tools/{name}       调用工具，body: {"agent": "...", "session": "...", "tables": [可选：角色可访问的表], "args": {...}}
//!   GET  /v1/stats              中间层统计
//!   GET  /v1/knowledge          经验库内容
//!   POST /v1/learn_features     特征定义的学习（RelBench）：body 为 {"agent": "...", "session": "...", ...LearnReq}
//!   GET  /v1/features           已发布的特征定义

use crate::llm::Provider;
use crate::middle::{served_tool_specs, Ctx, LearnReq, Middle, Role};
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::{Arc, OnceLock};

/// /v1/learn_features 用的提炼模型（`serve --extractor`）。
static EXTRACTOR: OnceLock<Provider> = OnceLock::new();

#[derive(Deserialize)]
struct CallReq {
    agent: String,
    session: Option<String>,
    task: Option<String>,
    tables: Option<Vec<String>>,
    #[serde(default)]
    args: Value,
}

async fn list_tools(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(json!(served_tool_specs(&mid.cfg)))
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

#[derive(Deserialize)]
struct LearnHttp {
    agent: String,
    session: Option<String>,
    #[serde(flatten)]
    req: LearnReq,
}

async fn learn_features(State(mid): State<Arc<Middle>>, Json(body): Json<LearnHttp>) -> (StatusCode, Json<Value>) {
    let Some(p) = EXTRACTOR.get() else {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": "serve 没有指定 --extractor"})));
    };
    if !mid.cfg.feature_memory {
        return (StatusCode::BAD_REQUEST, Json(json!({"error": "本实例没有开启特征记忆"})));
    }
    let ctx = Ctx {
        agent: body.agent,
        session: body.session.unwrap_or_else(|| "default".into()),
        task: body.req.task.clone(),
        role: Role { name: "http".into(), tables: None },
    };
    match mid.learn_features(&ctx, p, &body.req).await {
        Ok(v) => (StatusCode::OK, Json(v)),
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"error": format!("{e:#}")}))),
    }
}

async fn features(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(mid.feature_report())
}

async fn stats(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(mid.stats_json())
}

async fn knowledge(State(mid): State<Arc<Middle>>) -> Json<Value> {
    Json(json!(mid.knowledge()))
}

pub async fn serve(mid: Arc<Middle>, extractor: Option<Provider>, addr: &str) -> anyhow::Result<()> {
    if let Some(p) = extractor {
        let _ = EXTRACTOR.set(p);
    }
    let app = Router::new()
        .route("/v1/tools", get(list_tools))
        .route("/v1/tools/:name", post(call))
        .route("/v1/stats", get(stats))
        .route("/v1/knowledge", get(knowledge))
        .route("/v1/learn_features", post(learn_features))
        .route("/v1/features", get(features))
        .with_state(mid);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    eprintln!("中间层已启动：http://{addr}/v1/tools");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}

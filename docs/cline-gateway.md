# Cline 网关与 ClinePass 模型

记录日期：2026-09-30。实验通过 Cline 的 OpenAI 兼容网关调用模型，代码里对应 `cline` provider（`src/llm.rs`）。

## 接入方式

| 项 | 值 |
| --- | --- |
| Base URL | `https://api.cline.bot/api/v1` |
| 鉴权 | `Authorization: Bearer <key>` |
| 必需请求头 | `x-client-type: cline-cli` |
| 响应格式 | 外面多包一层：`{"data": {"choices": [...]}}`，代码里会解包 |
| 环境变量 | `CLINE_API_KEY`、`CLINE_MODEL`（写在 `.env`，已 gitignore） |
| 用法 | `metric-bench --agent cline --extractor cline` |

模型 id 带厂商前缀，如 `deepseek/deepseek-v4.1-flash`。key 只放在 noctis 的 `/root/agentdb-mid/.env`，不进仓库。

## 两类模型 id

- **普通网关模型**：`厂商/模型名`，`/models` 列表里有 389 个（不含 `:batch`），按 token 计费。
- **ClinePass 模型**：`cline-pass/模型名`，**不出现在 `/models` 列表里**，但可直接调用。同一次调用返回的 `cost` 恰为 `gateway_cost` 的一半，`cost_details` 为空，看起来是订阅或折扣通道（依据是返回字段，官方未说明）。实验为控制成本改用 pass。

### ClinePass 模型清单（来自 Cline 文档，标注为已针对 coding agent 测试和基准评测）

| 模型 | Model ID |
| --- | --- |
| GLM-5.3 | `cline-pass/glm-5.3` |
| GLM-5.3 Flash | `cline-pass/glm-5.3-flash` |
| Kimi K3 | `cline-pass/kimi-k3` |
| DeepSeek V4 Pro | `cline-pass/deepseek-v4-pro` |
| DeepSeek V4.1 Flash | `cline-pass/deepseek-v4.1-flash` |
| MiMo-V2.5 | `cline-pass/mimo-v2.5` |
| MiMo-V2.5-Pro | `cline-pass/mimo-v2.5-pro` |
| MiniMax M3 | `cline-pass/minimax-m3` |
| Muse Spark 1.3 Contributor | `cline-pass/muse-spark-1.3-contributor` |
| Qwen3.8 Max | `cline-pass/qwen3.8-max` |
| Qwen3.7 Max | `cline-pass/qwen3.7-max` |
| Qwen3.7 Plus | `cline-pass/qwen3.7-plus` |

**只有 `cline-pass/deepseek-v4.1-flash` 在本项目里实际测过**，其余为文档所列，使用前先按下面的检查做一遍。

## 普通网关模型概览（`/models`，共 389 个）

Anthropic（claude-fable-5.1、opus-5.5、sonnet-5.5、haiku-4.5 等）、OpenAI（gpt-6.1-sol、gpt-6-luna、gpt-5.x、o3 等）、DeepSeek（v4-pro、v4-flash、v4.1-flash、v3.2、r1 等）、Z.ai（glm-5.3、glm-5.3-prime、glm-5.3-flash、glm-5.x、glm-4.x）、Google（gemini-3.x、gemma）、Qwen（qwen3.8-*、3.7-*、3.6-*、coder 系列）、Moonshot（kimi-k3、k2.x）、xAI（grok-4.x）、MiniMax、Mistral、Meta Llama、xiaomi mimo、stepfun、bytedance-seed、tencent、amazon nova、cohere、perplexity、nvidia nemotron 等。

- 带 `~` 前缀的（如 `~deepseek/deepseek-pro-latest`）是“始终指向最新版”的别名，实验不要用。
- `:batch` 后缀是批量异步版本。
- `:free` 后缀共 17 个，均为中小模型或预览版；见下文实测，不适合做实验。

## 实测记录（noctis，经 `ssh noctis-dmit`）

检查方法：发 “Reply with exactly OK.” 看 `prompt_tokens`，再做一次工具调用往返（get_number → 42）。

| 模型 | “OK” prompt_tokens | 工具调用两步 prompt_tokens | 结论 |
| --- | --- | --- | --- |
| `z-ai/glm-5.3` | 18 | 151 → 162 | 正常，官方 API 同提示为 17 |
| `z-ai/glm-5.3-prime` | 17 | 150 → 184 | 正常 |
| `openai/gpt-6-luna` | 11 | 48 → 74 | 正常 |
| `deepseek/deepseek-v4-flash` | 88 | 351 → 410 | 偏高，未见 4.4k 那种明显注入，无官方基线可比 |
| `deepseek/deepseek-v4.1-flash` | 35 | 284 → 344 | 略高于 GLM，无官方基线可比 |
| `cline-pass/deepseek-v4.1-flash` | 35 | 284 → 323 | 与 `deepseek/…` 一致，计费为其一半 |
| `qwen/qwen3.8-27b:free` | 302（带工具） | — | 20 轮串行失败 8 次（40%），均为 HTTP 500（上游 OpenRouter 免费档失败）；8 路并发失败 1 次。**不可用于实验** |

要点：
- 网关没有 dddai.dev 那种约 4.4k 的隐藏 prompt token 注入。
- DeepSeek 系列的 prompt_tokens 比 GLM 高，可能是 DeepSeek 自己的 chat template，也可能是网关，noctis 上没有官方 DeepSeek key，无法区分。**只要一次对比里 query agent 与 extractor 用同一模型，固定开销对各组一致**；需要和官方 API 比绝对 token 数时才有影响。
- 每次换模型或 provider，先做上面的两步检查再跑实验。

## 实验记录

- 2026-09-30：`metric-bench --agent cline --extractor cline --metrics M1,M2,M3 --phrasings named`，6 种模式，模型 `cline-pass/deepseek-v4.1-flash`，日志 `results/metric-cline-pass-v41flash.log`（noctis）。
- 先用 `deepseek/deepseek-v4.1-flash` 启动的一轮因改用 pass 中止，已完成约 13 题、无报错，日志为 `results/metric-cline-v41flash-partial-nonpass.log`，不作为结果。
- 报告里的模型名会是 `cline:cline-pass/deepseek-v4.1-flash`，论文里写成 DeepSeek V4.1 Flash，注明经 Cline 网关调用。

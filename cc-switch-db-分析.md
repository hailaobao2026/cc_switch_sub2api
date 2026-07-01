# CC Switch 数据库 (`cc-switch.db`) 模型使用信息分析

## 基本信息

- **数据库位置**：`C:\Users\Administrator\.cc-switch\cc-switch.db`
- **类型**：SQLite 3.x 数据库（约 1.3 MB，user version 11）
- **程序安装目录**：`D:\Program Files\CC Switch`（仅含可执行文件，不存数据）
- **历史**：早期使用 `config.json`，后迁移为 SQLite 数据库（见 `config.json.migrated`、`migrated.copies.v1`）

## 全部数据表

```
mcp_servers          model_pricing        prompts
provider_endpoints   provider_health      providers
proxy_config         proxy_live_backup    proxy_request_logs
session_log_sync     settings             skill_repos
skills               sqlite_sequence      stream_check_logs
usage_daily_rollups
```

---

## 核心结论

模型使用信息主要存放在 **3 张表**，其中最核心的是 `proxy_request_logs`（明细）和 `usage_daily_rollups`（按天汇总）。

---

## 1. `proxy_request_logs` — 请求级明细日志 ⭐主表（1779 行）

每一次经过 CC Switch 代理的 API 请求记录一行。这是最详细的原始数据。

| 字段 | 含义 |
|---|---|
| `request_id` | 请求唯一 ID（主键） |
| `provider_id` / `provider_type` | 供应商 ID / 类型 |
| `app_type` | 应用类型（`claude` / `codex`） |
| `model` / `request_model` | 实际计费模型 / 请求时指定的模型 |
| `input_tokens` | 输入 token 数 |
| `output_tokens` | 输出 token 数 |
| `cache_read_tokens` | 缓存读取 token |
| `cache_creation_tokens` | 缓存写入 token |
| `input_cost_usd` / `output_cost_usd` | 输入/输出费用（USD） |
| `cache_read_cost_usd` / `cache_creation_cost_usd` | 缓存读/写费用 |
| `total_cost_usd` | 单次总费用 |
| `latency_ms` / `first_token_ms` / `duration_ms` | 延迟、首 token 时间、总耗时 |
| `status_code` / `error_message` | HTTP 状态码 / 错误信息 |
| `session_id` | 会话 ID |
| `is_streaming` | 是否流式 |
| `cost_multiplier` / `pricing_model` / `data_source` | 费率倍数 / 计价模型 / 数据来源 |
| `created_at` | 创建时间（Unix 时间戳） |

**统计维度**：单次请求的 token 消耗、费用、延迟、成败、流式与否。

---

## 2. `usage_daily_rollups` — 每日用量汇总 ⭐报表用（40 行）

把明细按"日期 + app + 供应商 + 模型"聚合，用于做用量统计图表。覆盖日期 `2026-01-05` ~ `2026-05-24`。

复合主键：`date` + `app_type` + `provider_id` + `model` + `request_model` + `pricing_model`

| 字段 | 含义 |
|---|---|
| `request_count` / `success_count` | 请求总数 / 成功数 |
| `input_tokens` / `output_tokens` | 输入/输出 token 累计 |
| `cache_read_tokens` / `cache_creation_tokens` | 缓存 token 累计 |
| `total_cost_usd` | 当日该模型总费用 |
| `avg_latency_ms` | 平均延迟 |

---

## 3. `model_pricing` — 模型价目表（160 行）

费用计算的基础数据，定义每个模型的单价（每百万 token）。

| 字段 | 含义 |
|---|---|
| `model_id` | 模型 ID（主键，如 `claude-opus-4-8`） |
| `display_name` | 显示名（如 `Claude Opus 4.8`） |
| `input_cost_per_million` | 每百万输入 token 价格 |
| `output_cost_per_million` | 每百万输出 token 价格 |
| `cache_read_cost_per_million` | 缓存读单价 |
| `cache_creation_cost_per_million` | 缓存写单价 |

---

## 辅助相关表

| 表 | 说明 |
|---|---|
| `stream_check_logs` | 流式连通性测试日志（含 `model_used`、`response_time_ms`），用于探活，不是真实用量 |
| `provider_health` | 供应商健康状态（连续失败次数、最后成功/失败时间） |
| `session_log_sync` | 会话日志文件同步进度（记录从哪些 jsonl 文件、读到第几行）——用量数据的采集来源 |

---

## 实际数据预览（按模型聚合，来自 `proxy_request_logs`）

| 模型 | 请求数 | 输入 token | 输出 token | 总费用 |
|---|---|---|---|---|
| gpt-5.5 | 1306 | 150.3M | 602K | $141.82 |
| glm-5.1 | 201 | 3.5M | 70.9K | $4.83 |
| gpt-5.4 | 173 | 20.9M | 89.6K | $11.10 |
| claude-opus-4-8 | 35 | 305K | 38.9K | $15.13 |
| glm-5.2 | 31 | 408K | 51.8K | $1.49 |
| mimo-v2.5-pro | 19 | 1.0M | 7.2K | $0.08 |
| step-3.7-flash | 13 | 2.1M | 2.9K | $0.12 |
| claude-opus-4-6 | 1 | 26.8K | 58 | $0.38 |
| ernie-4.5-turbo | 1 | 9.1K | 11 | $0 |

---

## 使用建议

- **明细分析**：查 `proxy_request_logs`，可按任意维度（模型 / 供应商 / 时间 / app）聚合。
- **快速报表**：直接读 `usage_daily_rollups`，已按天预聚合，查询更快。
- **费用解释 / 单价**：参照 `model_pricing`。

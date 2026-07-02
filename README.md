# CC Switch → sub2api 用量上报插件

把本机 **CC Switch** 记录的模型调用用量上报到 **sub2api** 旁路统计表，按用户名/邮箱关联到 sub2api 用户。
推荐部署方式是独立 **sidecar** 服务：不修改 sub2api 源码，只连接同一个 PostgreSQL，降低后续升级成本。

## 背景

- **CC Switch** 的用量数据在本地 SQLite：`~/.cc-switch/cc-switch.db`，核心表是
  `proxy_request_logs`（每请求一行，含 token、费用、模型、时间）。详见
  [`cc-switch-db-分析.md`](./cc-switch-db-分析.md)。
- **sub2api** 的 `/admin/usage` 是只读统计，`usage_logs` 由网关代理请求时内部写入，没有稳定的外部用量导入接口。
- 因此本项目改为：**客户端聚合上报** + **独立 sidecar 摄取服务** + **独立外部用量表**。

## 组成

| 目录 | 内容 | 语言 |
|---|---|---|
| [`cc_usage_reporter/`](./cc_usage_reporter/) | 上报客户端：读本地 db → 天×模型聚合 → 去重 → 上报 sidecar | Python 3.10+（纯标准库） |
| [`sidecar/`](./sidecar/) | 独立摄取服务：token 鉴权 → 解析 sub2api 用户 → upsert `external_usage_daily` | Go + PostgreSQL |
| [`backend_patch/`](./backend_patch/) | 可选嵌入式集成参考；不再是推荐路径 | Go + SQL |
| [`cc-switch-db-分析.md`](./cc-switch-db-分析.md) | cc-switch.db 结构分析 | — |

## 数据流

```text
 CC Switch 本地 db                         sidecar                         sub2api PostgreSQL
 ────────────────                          ───────                         ─────────────────
 proxy_request_logs                        POST /api/v1/usage/report        users
   │ 只读、按 UTC 天×模型聚合                      │ Bearer token 鉴权             │ 按 username/email 解析 user_id
   │ signature 去重                              │ 校验 + 规范化                 ▼
   ▼                                            ▼                         external_usage_daily
 天×模型 用量桶  ───────── HTTP(JSON) ───────► 幂等 upsert ───────────────► 管理端/SQL 视图查询
```

## 幂等设计

CC Switch 的「当天」聚合桶会随请求持续累加，所以：

- 客户端只发新增或数值变化的桶（本地状态文件记录指纹）。
- sidecar 按 `(user_id, source, usage_date, app_type, model, requested_model)` 唯一键 `ON CONFLICT DO UPDATE`。
- 重复上报覆盖而非累加，不会重复计数。

## 快速上手

### 本地运行

```powershell
# 1) 启动 sidecar
cd sidecar
Copy-Item config.example.json config.json
# 编辑 database_url / report_token
go run . -config config.json

# 2) 客户端本地预览聚合是否正确
cd ..\cc_usage_reporter
python -m cc_usage_reporter preview

# 3) 客户端上报到 sidecar
Copy-Item config.sidecar.example.json config.sidecar.json
# 编辑 username/email/token/db_path
python -m cc_usage_reporter run --config config.sidecar.json --dry-run
python -m cc_usage_reporter run --config config.sidecar.json
```

### Docker Compose 运行

如果你使用 `sub2api/deploy/docker-compose.yml` 部署 sub2api，可以叠加 sidecar overlay：

```powershell
cd sub2api\deploy
Copy-Item .env.example .env
Get-Content .env.cc-switch-sidecar.example | Add-Content .env
# 编辑 .env：POSTGRES_PASSWORD / CC_USAGE_SIDECAR_REPORT_TOKEN
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build
```

详细说明：

- sidecar：[`sidecar/README.md`](./sidecar/README.md)
- Docker 部署：[`sub2api/deploy/CC_SWITCH_SIDECAR.md`](./sub2api/deploy/CC_SWITCH_SIDECAR.md)
- 客户端：[`cc_usage_reporter/README.md`](./cc_usage_reporter/README.md)
- Windows EXE 打包：[`cc_usage_reporter/README.md`](./cc_usage_reporter/README.md#打包为-windows-exe)
- 嵌入式参考补丁：[`backend_patch/README.md`](./backend_patch/README.md)

## 管理端统计页面

完成 sidecar 部署并使用本地补丁版 `sub2api:cc-switch-local` 镜像后，可以在管理端访问：

```text
/admin/external-usage
```

这个页面基于 `external_usage_daily` 表和 `admin_external_usage_v` 视图，当前提供两层统计视角：

- **用量明细**：保留 `user + usage_date + app_type + model + requested_model + source` 粒度，适合排查某天某模型的具体消耗。
- **用户汇总**：对当前筛选范围内的多条桶数据再次按用户聚合，适合查看员工总体消耗情况。

页面包含以下能力：

- 顶部总览卡片：总请求数、总 Token、总消费、总用户数、成功率。
- 模型 / 应用 / 来源分布图。
- 按日期聚合的趋势图。
- **用户消费排行榜**：默认按总消费降序展示 Top 10。
- **排行榜周期切换**：支持 `日榜 / 月榜 / 年榜`。
- **排行榜 CSV 导出**：导出当前榜单周期下的完整用户排行。
- **用户汇总表**：展示活跃天数、模型数、应用数、请求数、成功率、总 Token、总费用、最近上报时间。

排行榜和用户汇总均支持复用页面筛选条件：

- 时间范围
- 用户（用户名 / 邮箱）
- 模型
- 应用类型
- 来源

其中排行榜额外支持独立周期切换：

- `日榜`：取锚点日期当天数据
- `月榜`：取锚点日期所在自然月数据
- `年榜`：取锚点日期所在自然年数据

说明：

- 排行榜的锚点日期优先取页面的 `结束日期`；如果未设置，则使用当天日期。
- CSV 导出内容不仅限于 Top 10，而是导出当前榜单周期下的完整用户排行。

当前新增的用户聚合接口为：

```text
GET /api/v1/admin/usage/external/users
```

接口返回的核心字段包括：

- `active_days`
- `models_count`
- `app_types_count`
- `request_count`
- `success_count`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_creation_tokens`
- `total_tokens`
- `total_cost`
- `last_reported_at`

## 升级策略

推荐长期保持 sidecar 独立运行，不改 sub2api 主仓库。sub2api 升级时，只需确认 PostgreSQL 连接和 `users` 表核心字段仍存在：`id`、`email`、`username`、`deleted_at`。

## 合规提示

本插件仅做本地用量统计的聚合上报，不参与任何代理或绕过；请在已获授权的环境中使用。

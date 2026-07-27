# CC Switch → sub2api 用量上报插件

把本机 **CC Switch** 记录的模型调用用量上报到 **sub2api** 旁路统计表，按用户名/邮箱关联到 sub2api 用户。

推荐部署方式：

- **摄取路径**：独立 **sidecar** 服务，只连接同一个 PostgreSQL，不改上游网关写入逻辑。
- **展示路径**：在本地维护的 `sub2api/` 上叠加 CC-Switch 统计页面与 API 补丁，构建 `sub2api:cc-switch-local` 镜像。

当前对齐上游版本：`sub2api v0.1.165`（镜像构建参数默认 `VERSION=0.1.165`）。

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
| [`sub2api/`](./sub2api/) | 基于上游 sub2api 的本地 fork：含 CC-Switch 用量页面 / API / backend mode 放行补丁 | Go + Vue |
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

### 多电脑同用户

如果同一个 sub2api 用户在多台电脑上安装 `cc_usage_reporter`，请给每台电脑配置不同 `source`，例如：

```json
{
  "source": "cc-switch-pc-a"
}
```

并在 sidecar 的 `allowed_sources` 中加入这些来源：

```json
{
  "allowed_sources": ["cc-switch", "cc-switch-pc-a", "cc-switch-laptop"]
}
```

Docker Compose 部署可在 `sub2api/deploy/.env` 中配置：

```env
CC_USAGE_SIDECAR_ALLOWED_SOURCES=cc-switch,cc-switch-pc-a,cc-switch-laptop
```

原因是 `source` 是服务端唯一键的一部分。多台电脑如果都使用默认 `source = cc-switch`，同一天同用户同模型的桶会互相覆盖；使用不同 `source` 后，服务端会保留多行，管理端按用户汇总时会自然叠加。

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
# 编辑 username/email/token/db_path/source
python -m cc_usage_reporter run --config config.sidecar.json --dry-run
python -m cc_usage_reporter run --config config.sidecar.json
```

### Docker Compose 运行

如果你使用 `sub2api/deploy/docker-compose.yml` 部署 sub2api，可以叠加 sidecar overlay。

`docker-compose.yml` 中的 `sub2api` 服务已配置为本地构建镜像 `sub2api:cc-switch-local`（含 CC-Switch 统计补丁），不要直接使用官方 `weishaw/sub2api:latest`，否则管理端没有 `CC-Switch 用量` 页面。

```powershell
cd sub2api\deploy
Copy-Item .env.example .env
Get-Content .env.cc-switch-sidecar.example | Add-Content .env
# 编辑 .env：POSTGRES_PASSWORD / CC_USAGE_SIDECAR_REPORT_TOKEN / CC_USAGE_SIDECAR_ALLOWED_SOURCES
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build --force-recreate
```

Linux / macOS：

```bash
cd sub2api/deploy
cp .env.example .env
cat .env.cc-switch-sidecar.example >> .env
# 编辑 .env：POSTGRES_PASSWORD / CC_USAGE_SIDECAR_REPORT_TOKEN / CC_USAGE_SIDECAR_ALLOWED_SOURCES
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build --force-recreate
```

#### 重要：为什么有时版本还是旧的

如果 compose 里 `sub2api` 只有 `image:`、没有 `build:`，执行：

```bash
docker compose ... up -d --build
```

时 **只会重建有 build 配置的 sidecar**，主程序 `sub2api` 只会 `Recreated`，仍复用旧的 `sub2api:cc-switch-local` 镜像，版本会继续显示旧号（例如 `0.1.141`）。

当前仓库已在 `sub2api/deploy/docker-compose.yml` 补上 build 配置，例如：

```yaml
sub2api:
  build:
    context: ..
    dockerfile: Dockerfile
    args:
      VERSION: ${SUB2API_VERSION:-0.1.165}
      GOPROXY: ${GOPROXY:-https://goproxy.cn,direct}
      GOSUMDB: ${GOSUMDB:-sum.golang.google.cn}
  image: sub2api:cc-switch-local
```

升级源码或补丁后，请强制重建主程序镜像：

```bash
# 在 sub2api 根目录单独构建
cd sub2api
docker build -t sub2api:cc-switch-local \
  --build-arg VERSION=0.1.165 \
  --build-arg GOPROXY=https://goproxy.cn,direct \
  --build-arg GOSUMDB=sum.golang.google.cn \
  -f Dockerfile .

# 回到 deploy 重建并启动
cd deploy
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --force-recreate sub2api
```

或一条命令让 compose 负责构建：

```bash
cd sub2api/deploy
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build --force-recreate sub2api
```

校验版本：

```bash
docker logs sub2api 2>&1 | head
# 期望看到：Sub2API 0.1.165 ...
docker exec sub2api /app/sub2api -version
```

可选环境变量：

| 变量 | 说明 | 默认 |
|---|---|---|
| `SUB2API_VERSION` | 写入二进制的版本号 | `0.1.165` |
| `GOPROXY` | Go 模块代理 | `https://goproxy.cn,direct` |
| `GOSUMDB` | Go checksum DB | `sum.golang.google.cn` |
| `CC_USAGE_SIDECAR_REPORT_TOKEN` | sidecar 上报鉴权 token | 必填 |
| `CC_USAGE_SIDECAR_ALLOWED_SOURCES` | 允许的 `source` 白名单（逗号分隔） | `cc-switch` |

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

普通用户也可以访问对应页面：

```text
/external-usage
```

这个页面基于 `external_usage_daily` 表和 `admin_external_usage_v` 视图，当前提供两层统计视角：

- **用量明细**：保留 `user + usage_date + app_type + model + requested_model + source` 粒度，适合排查某天某模型的具体消耗。
- **用户汇总**：对当前筛选范围内的多条桶数据再次按用户聚合，适合查看员工总体消耗情况。

不同角色的页面能力如下：

- **管理员**：可查看 `用户汇总` + `用量明细` 两个视角，并可按用户名 / 邮箱筛选指定用户。
- **普通用户**：可查看排行榜、趋势图、分布图和 `用户汇总`，用于了解整体排名情况；默认不展示管理员排查用的明细 Tab。

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

本次同时补充了普通用户接口：

```text
GET /api/v1/usage/external
GET /api/v1/usage/external/stats
GET /api/v1/usage/external/trend
GET /api/v1/usage/external/users
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

### Backend Mode 兼容说明

如果 sub2api 开启了 `backend mode`，本补丁额外放开了普通用户访问 `cc-switch` 排行模块所需的最小能力：

- 前端普通用户侧边栏会显示 `CC-Switch Usage` 入口。
- 前端路由守卫会允许普通用户访问 `/external-usage`。
- 后端 `BackendModeUserGuard` 会精确放行以下接口：

```text
/api/v1/usage/external
/api/v1/usage/external/stats
/api/v1/usage/external/trend
/api/v1/usage/external/users
```

也就是说，在 `backend mode` 下，普通用户不会恢复完整自助功能，只会被定向允许查看 `cc-switch` 排行与汇总页面。

## 升级策略

### 分层原则

1. **sidecar / reporter 尽量独立**：摄取逻辑在 `sidecar/` 与 `cc_usage_reporter/`，不依赖 sub2api 内部 Go 代码。
2. **展示与查询补丁维护在本地 `sub2api/`**：管理端/用户端 `CC-Switch 用量` 页面、API、backend mode 放行属于本地补丁，升级上游后需要重新合入。
3. **数据库兼容点**：确认 PostgreSQL 中 `users` 表核心字段仍在：`id`、`email`、`username`、`deleted_at`；外部用量表/视图由 sidecar 迁移维护：
   - `external_usage_daily`
   - `admin_external_usage_v`

### 当前基线

- 上游对齐：`Wei-Shaw/sub2api` tag **`v0.1.165`**
- 本地镜像：`sub2api:cc-switch-local`
- 本地补丁能力：
  - 管理端 `/admin/external-usage`
  - 普通用户 `/external-usage`
  - API：`/api/v1/admin/usage/external*` 与 `/api/v1/usage/external*`
  - backend mode 最小放行
  - compose 本地构建与 sidecar overlay

### 升级 sub2api 上游时建议步骤

```bash
# 1) 备份本地补丁相关文件（至少）
# - backend handler/routes/middleware
# - frontend ExternalUsageView / router / sidebar / i18n / api
# - deploy/docker-compose.cc-switch-sidecar.yml 与 CC_SWITCH_SIDECAR.md

# 2) 同步上游目标版本源码到 sub2api/

# 3) 重新合入 CC-Switch 补丁后构建
cd sub2api
docker build -t sub2api:cc-switch-local --build-arg VERSION=<新版本号> -f Dockerfile .

# 4) 重建容器
cd deploy
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --force-recreate sub2api cc-switch-usage-sidecar

# 5) 验证
docker logs sub2api 2>&1 | head
curl -sS http://127.0.0.1:8080/api/v1/health || true
```

### 本地补丁关键文件（升级后勿丢）

**后端**

- `sub2api/backend/internal/handler/admin/usage_handler.go`（External usage 查询 + `db` 注入）
- `sub2api/backend/cmd/server/wire_gen.go`（`admin.NewUsageHandler(..., db)`）
- `sub2api/backend/internal/server/routes/admin.go`
- `sub2api/backend/internal/server/routes/user.go`
- `sub2api/backend/internal/server/middleware/backend_mode_guard.go`
- `sub2api/backend/internal/server/middleware/backend_mode_guard_test.go`

**前端**

- `sub2api/frontend/src/views/admin/ExternalUsageView.vue`
- `sub2api/frontend/src/api/admin/usage.ts`
- `sub2api/frontend/src/api/usage.ts`
- `sub2api/frontend/src/router/index.ts`
- `sub2api/frontend/src/components/layout/AppSidebar.vue`
- `sub2api/frontend/src/i18n/locales/zh/common.ts`
- `sub2api/frontend/src/i18n/locales/en/common.ts`

**部署**

- `sub2api/deploy/docker-compose.yml`（`build` + `image: sub2api:cc-switch-local`）
- `sub2api/deploy/docker-compose.cc-switch-sidecar.yml`
- `sub2api/deploy/.env.cc-switch-sidecar.example`
- `sub2api/deploy/CC_SWITCH_SIDECAR.md`

### 常见问题

**Q: `up -d --build` 后版本还是旧的？**  
A: 确认 `sub2api` 服务有 `build:`，并使用 `--force-recreate`；必要时先 `docker build -t sub2api:cc-switch-local ...` 再 recreate。

**Q: 官方镜像能不能直接用？**  
A: 官方 `weishaw/sub2api:latest` **不含** 本项目的 CC-Switch 统计页面与 API，只能完成网关本身；要看 `/admin/external-usage` 必须用本地镜像。

**Q: sidecar 和 sub2api 版本要一起升吗？**  
A: 不强制。sidecar 只要仍能连同一 PostgreSQL 并解析 `users` 表即可；sub2api 展示补丁随上游升级单独合入。

## 合规提示

本插件仅做本地用量统计的聚合上报，不参与任何代理或绕过；请在已获授权的环境中使用。

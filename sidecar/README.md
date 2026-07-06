# CC Switch Usage Sidecar

独立运行的 CC Switch 用量摄取服务。它不修改 sub2api 源码，只连接 sub2api 使用的 PostgreSQL，维护独立的 `external_usage_daily` 表。

## 架构

```text
cc_usage_reporter  ->  sidecar  ->  sub2api PostgreSQL
本地 SQLite 聚合       token 鉴权     external_usage_daily
```

- 与 Python 客户端兼容：`POST /api/v1/usage/report`。
- 使用插件专用 Bearer token 鉴权，不依赖 sub2api JWT 内部实现。
- 按 `username` 或 `email` 查询 sub2api `users` 表解析 `user_id`。
- 按 `(user_id, source, usage_date, app_type, model, requested_model)` upsert，重复上报不会重复计数。
- 可启动时自动创建 `external_usage_daily` 表和 `admin_external_usage_v` 视图。

## 配置

复制示例配置：

```powershell
Copy-Item config.example.json config.json
```

关键项：

| 字段 | 说明 |
|---|---|
| `listen_addr` | sidecar 监听地址，默认建议 `127.0.0.1:8788` |
| `database_url` | sub2api PostgreSQL DSN |
| `report_token` | 客户端上报专用长随机 token |
| `auto_migrate` | 启动时自动建表/建视图 |
| `allowed_sources` | 允许写入的来源，默认 `cc-switch`；多电脑同用户上报时需要加入每台电脑的 `source` |
| `max_items` | 单次上报最大 item 数 |

也支持环境变量覆盖：

| 环境变量 | 对应配置 |
|---|---|
| `CC_USAGE_SIDECAR_LISTEN_ADDR` | `listen_addr` |
| `CC_USAGE_SIDECAR_DATABASE_URL` | `database_url` |
| `CC_USAGE_SIDECAR_REPORT_TOKEN` | `report_token` |
| `CC_USAGE_SIDECAR_AUTO_MIGRATE` | `auto_migrate` |
| `CC_USAGE_SIDECAR_ALLOWED_SOURCES` | `allowed_sources`，英文逗号分隔 |

## 运行

### 本地运行

```powershell
go mod tidy
go run . -config config.json
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8788/healthz
```

### Docker Compose 运行

推荐与 sub2api 的 Docker 栈一起启动，使用 `sub2api/deploy/docker-compose.cc-switch-sidecar.yml` 覆盖文件：

```powershell
cd ..\sub2api\deploy
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build
```

详细说明见 `sub2api/deploy/CC_SWITCH_SIDECAR.md`。

## 客户端配置

`cc_usage_reporter` 使用 `config.sidecar.example.json`，重点是：

```json
{
  "base_url": "http://127.0.0.1:8788",
  "token": "change-me-to-the-same-long-random-token-as-sidecar",
  "username": "alice",
  "source": "cc-switch"
}
```

如果同一个 sub2api 用户在多台电脑上安装客户端，请给每台电脑设置不同 `source`，并同步加入 sidecar 的 `allowed_sources`：

```json
{
  "allowed_sources": ["cc-switch", "cc-switch-pc-a", "cc-switch-laptop"]
}
```

Docker Compose 部署时可直接在 `.env` 中配置：

```env
CC_USAGE_SIDECAR_ALLOWED_SOURCES=cc-switch,cc-switch-pc-a,cc-switch-laptop
```

否则多台电脑使用默认 `cc-switch` 时，同一天同模型的桶会互相覆盖，表现为最后一次上传的数据生效。

然后运行：

```powershell
python -m cc_usage_reporter run --config config.sidecar.json --dry-run
python -m cc_usage_reporter run --config config.sidecar.json
```

## 查询数据

```sql
SELECT *
FROM external_usage_daily
ORDER BY reported_at DESC
LIMIT 20;
```

```sql
SELECT *
FROM admin_external_usage_v
ORDER BY reported_at DESC
LIMIT 20;
```

## 与 sub2api 升级的关系

sidecar 不改 sub2api 源码，因此 sub2api 后续升级时通常不需要合并补丁。只要 sub2api 仍使用 PostgreSQL 且 `users` 表保留 `id`、`email`、`username`、`deleted_at` 字段，sidecar 就可以继续工作。

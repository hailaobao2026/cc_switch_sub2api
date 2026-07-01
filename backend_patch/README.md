# sub2api 后端补丁：外部用量上报接口

> 当前推荐方案已改为独立 `sidecar/` 服务：不修改 sub2api 源码，只连接同一个 PostgreSQL。
> 本目录保留为“嵌入式集成参考”，仅在你明确希望把接口编译进 sub2api 主服务时使用。

让 sub2api 接收来自 **CC Switch 上报客户端**（`cc_usage_reporter`）的本地模型用量，
按用户关联，并在管理端统计中体现「平台内 vs 平台外」用量对比。

> ⚠️ 说明：sub2api 原生 `/admin/usage` 是**只读**的，`usage_logs` 仅由网关代理请求时
> 内部写入，没有对外的用量导入接口。本补丁新增一个 `POST /api/v1/usage/report`
> 摄取接口 + 一张独立的 `external_usage_daily` 表来承载外部上报数据，**不改动**
> `usage_logs` 的计费语义与唯一约束。

## 新增接口

```
POST /api/v1/usage/report      (JWT 鉴权，复用现有用户登录态)
```

请求体（客户端按「天 × 模型」聚合后发送）：

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "source": "cc-switch",
  "granularity": "daily",
  "items": [
    {
      "date": "2026-06-20",
      "app_type": "codex",
      "model": "gpt-5.5",
      "request_model": "gpt-5.5",
      "request_count": 478,
      "success_count": 478,
      "input_tokens": 59257043,
      "output_tokens": 283828,
      "cache_read_tokens": 0,
      "cache_creation_tokens": 0,
      "total_cost_usd": 64.726135
    }
  ]
}
```

响应：

```json
{ "accepted": 1, "rejected": 0, "user_id": 12 }
```

### 关联与安全模型

- **普通用户**：忽略 body 中的 `username`，强制写入**当前登录用户**的 `user_id`，
  避免冒名给他人写用量。
- **管理员**：可用 `username` 或 `email` 指定目标用户代上报；不指定则写自己。

### 幂等

`external_usage_daily` 以 `(user_id, source, usage_date, app_type, model, requested_model)`
为唯一键，`ON CONFLICT DO UPDATE` 覆盖。客户端每次发送的是该桶的**最新累计值**，
因此重复上报不会重复计数，当天数据可多次刷新。

## 文件清单

| 文件 | 放置位置（建议） | 作用 |
|---|---|---|
| `migrations/0001_external_usage_daily.sql` | 你的迁移目录 | 建表 + 唯一索引 |
| `migrations/0002_admin_usage_unified_view.sql` | 你的迁移目录 | 合并视图（可选） |
| `repository/external_usage_repo.go` | `backend/internal/repository/` | 批量 upsert 仓储（用 `*sql.DB`） |
| `handler/usage_report_handler.go` | `backend/internal/handler/` | 接口处理器 |
| `handler/usage_report_helpers.go` | `backend/internal/handler/` | 上下文取值/格式化 |
| `handler/user_resolver_adapter.go` | `backend/internal/handler/` | Ent 实现的用户名/邮箱→user_id |
| `routes_snippet.go` | 参考，拷贝注册行 | 路由注册 + 依赖注入示例 |

## 与 sub2api 现有代码的契合点（已对齐）

我对照了 sub2api 源码，补丁已按其真实约定编写：

- **数据库**：`usage_log_repo.go` 中 `usageLogRepository` 持有 `db *sql.DB` 并用
  `database/sql` 执行 raw SQL。本补丁的 `ExternalUsageRepo` 同样接收 `*sql.DB`
  （`sqlExecutor` 接口，`*sql.DB`/`*sql.Tx` 均满足），用 `ExecContext` 执行 upsert，
  装配时直接复用你已有的 `*sql.DB`。
- **Ent**：repository 层用 Ent（`*ent.Client` / `ent/user`）。`user_resolver_adapter.go`
  即用 `client.User.Query().Where(dbuser.Email(...))` 解析 user_id。
- **鉴权**：用户/管理端路由由 `JWTAuthMiddleware` / `AdminAuthMiddleware`
  （`backend/internal/server/router.go`）保护，claims 含 user id + role。
  上报接口挂到已认证的 `/api/v1` 组即复用同一鉴权。

> 仍需你按本机 schema 确认的 2 处（代码已用 `>>> 集成对接点 <<<` 标注）：
> ① JWT 写入 context 的键名（默认按 `userID`/`role` + 常见别名兼容）；
> ② user schema 是否有 `username` 字段（没有则把 `dbuser.Username` 换成 `dbuser.Name`
> 或仅用 email 关联）。

## 集成步骤

1. **执行迁移**：先跑 `0001`，确认 `external_usage_daily` 建好；`0002` 视图按需。
   - 若要启用外键，先确认 `users` 表名与主键，再取消 `0001` 末尾注释。

2. **放入 Go 文件**：把 `repository/` 与 `handler/` 下文件复制到对应包目录，
   调整 `import` 路径中的 module 名（`github.com/Wei-Shaw/sub2api/...`）以匹配实际。

3. **确认 2 个集成点**（已在代码中用 `>>> 集成对接点 <<<` 标注；其余已对齐 sub2api 真实类型）：
   - `currentUserID` / `currentUserIsAdmin`（`usage_report_helpers.go`）：
     默认按 `userID` / `role` 取值并兼容常见别名。打开 `backend/internal/server/router.go`
     里的 `JWTAuthMiddleware`，确认 `c.Set(...)` 的实际键名/claims 类型，不一致就改 keys 列表。
   - `user_resolver_adapter.go`：用 Ent 按 `dbuser.Username` / `dbuser.Email` 查询。
     若 user schema 没有 `username` 字段，把 `dbuser.Username` 换成 `dbuser.Name`，
     或让 `GetIDByUsername` 也走 email。

   > DB 层无需改动：`ExternalUsageRepo` 直接接收 sub2api 现有的 `*sql.DB`。

4. **注册路由 + 依赖注入**：参考 `routes_snippet.go`，在已认证的 `/api/v1` 用户路由组
   加上 `v1.POST("/usage/report", usageReportHandler.Report)`，并在装配处构造：
   ```go
   externalRepo := repository.NewExternalUsageRepo(db)        // db: *sql.DB
   userResolver := handler.NewEntUserResolver(entClient)      // entClient: *ent.Client
   usageReportHandler := handler.NewUsageReportHandler(externalRepo, userResolver)
   ```

5. **（可选）前端展示**：新增一个「外部用量 / CC Switch」标签页，查询
   `admin_external_usage_v` 或 `admin_usage_combined_v` 视图，即可看到本地上报数据
   及与平台用量的对比。

## 与原生 usage_logs 的关系

本补丁刻意**不写** `usage_logs`，原因：
- `usage_logs` 唯一键是 `(request_id, api_key_id)` 且 `api_key_id` 多半有外键约束，
  外部聚合数据没有真实 `request_id`/`api_key_id`，强行写入需要造 sentinel key，易破坏计费。
- daily 桶是累计值，写 `usage_logs` 明细会与「每请求一行」的语义冲突，且 `DO NOTHING`
  无法更新当天变化。

如果你确有强需求要让数据出现在原生 `/admin/usage` 列表，再单独评估「合成 request_id +
专用导入 API key + DO UPDATE」方案；本补丁优先保证安全与幂等。

## 验证

```bash
# 1) 迁移后，用任意 JWT 调接口
curl -X POST https://<your-sub2api>/api/v1/usage/report \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"source":"cc-switch","granularity":"daily","items":[
        {"date":"2026-06-20","app_type":"codex","model":"gpt-5.5",
         "request_count":1,"input_tokens":100,"output_tokens":10,"total_cost_usd":0.01}]}'

# 2) 查库确认
#   SELECT * FROM external_usage_daily ORDER BY reported_at DESC LIMIT 5;
```

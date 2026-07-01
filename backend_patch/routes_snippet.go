// routes_snippet.go — 路由注册示例（非完整文件，仅供拷贝到 sub2api 路由层）。
//
// sub2api 的 JWTAuthMiddleware / AdminAuthMiddleware 在 backend/internal/server/router.go，
// 用户级路由组 /api/v1 已套用 JWTAuthMiddleware。把上报接口加到该已认证组即可。
//
// 1) 注册路由（在已认证的 /api/v1 用户路由组里，伪代码按实际变量名调整）：
//
//	v1 := r.Group("/api/v1")
//	v1.Use(JWTAuthMiddleware(...))   // 现有
//	// >>> 新增：外部用量上报（复用同一 JWT 鉴权）<<<
//	v1.POST("/usage/report", usageReportHandler.Report)
//
// 2) 依赖注入（在装配 repository / handler 处；db 即 sub2api 已有的 *sql.DB）：
//
//	externalRepo := repository.NewExternalUsageRepo(db)          // db: *sql.DB
//	userResolver := handler.NewEntUserResolver(entClient)        // entClient: *ent.Client
//	usageReportHandler := handler.NewUsageReportHandler(externalRepo, userResolver)
//
// 这样 handler / repository / resolver 三者均使用 sub2api 既有的连接池与 Ent client，
// 无需新增基础设施。
package routes

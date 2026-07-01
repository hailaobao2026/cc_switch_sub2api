// usage_report_helpers.go — 上报接口的辅助函数与「集成对接点」。
//
// 本文件里的 currentUserID / currentUserIsAdmin 是与 sub2api 现有 JWT 中间件
// 对接的关键点。集成时请替换为你工程里真实的上下文取值方式。
package handler

import (
	"errors"
	"strconv"

	"github.com/gin-gonic/gin"

	servermiddleware "github.com/Wei-Shaw/sub2api/internal/server/middleware"
	"github.com/Wei-Shaw/sub2api/internal/service"
)

var (
	errUnauthenticated = errors.New("未认证或无法识别当前用户")
	errUserNotFound    = errors.New("目标用户不存在")
)

// formatCost 把浮点美元成本格式化为 numeric 可接受的十进制字符串，避免科学计数法。
func formatCost(v float64) string {
	if v < 0 {
		v = 0
	}
	return strconv.FormatFloat(v, 'f', 10, 64)
}

// currentUserID 从 gin 上下文取当前登录用户 ID。
//
// >>> 集成对接点 <<<
// sub2api 的 JWTAuthMiddleware（在 backend/internal/server/router.go）会把
// JWT claims 中的 user id / role 写入 gin context。社区版常用键名为 "userID" 与 "role"，
// 本函数已按此默认 + 常见别名做兼容。请打开你的 router.go 确认 c.Set(...) 的实际键名，
// 若不同则改这里（只需改 keys 列表）。
func currentUserID(c *gin.Context) int64 {
	if subject, ok := servermiddleware.GetAuthSubjectFromContext(c); ok {
		return subject.UserID
	}
	for _, key := range []string{"userID", "user_id", "uid"} {
		if v, ok := c.Get(key); ok {
			switch id := v.(type) {
			case int64:
				return id
			case int:
				return int64(id)
			case uint:
				return int64(id)
			case uint64:
				return int64(id)
			case float64:
				return int64(id)
			case string:
				n, _ := strconv.ParseInt(id, 10, 64)
				return n
			}
		}
	}
	return 0
}

// currentUserIsAdmin 判断当前用户是否管理员。
//
// >>> 集成对接点 <<<
// 同样取自 JWTAuthMiddleware 写入的 role/claims。sub2api 用 role 字段区分管理员；
// 按你 router.go / claims 的实际值（如 "admin"/"super_admin" 或布尔 is_admin）调整。
func currentUserIsAdmin(c *gin.Context) bool {
	if role, ok := servermiddleware.GetUserRoleFromContext(c); ok {
		return role == service.RoleAdmin
	}
	for _, key := range []string{"is_admin", "isAdmin"} {
		if v, ok := c.Get(key); ok {
			if b, ok := v.(bool); ok {
				return b
			}
		}
	}
	for _, key := range []string{"role", "userRole"} {
		if v, ok := c.Get(key); ok {
			if s, ok := v.(string); ok {
				return s == "admin" || s == "super_admin"
			}
		}
	}
	return false
}

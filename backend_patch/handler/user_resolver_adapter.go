// user_resolver_adapter.go — UserResolver 的 Ent 实现示例（sub2api 后端补丁）。
//
// sub2api 的 repository 使用 Ent（*ent.Client，见 usage_log_repo.go 的 dbent.Client
// 与 ent/user 包）。本适配器用 Ent 按 username / email 查 user_id，供上报 handler 关联用户。
//
// 放置位置：backend/internal/handler/user_resolver_adapter.go
// 集成时把 import 的 module 路径、Ent 字段谓词名按你的 schema 实际调整：
//   - 若 user schema 没有 username 字段，可让 GetIDByUsername 也走 email，
//     或改成查 name/nickname 字段。
package handler

import (
	"github.com/gin-gonic/gin"

	dbent "github.com/Wei-Shaw/sub2api/ent"
	dbuser "github.com/Wei-Shaw/sub2api/ent/user"
)

// EntUserResolver 用 Ent client 解析用户 ID。
type EntUserResolver struct {
	client *dbent.Client
}

func NewEntUserResolver(client *dbent.Client) *EntUserResolver {
	return &EntUserResolver{client: client}
}

// GetIDByUsername 按用户名查 user_id。
// 注意：dbuser.Username 谓词要求 user schema 存在 username 字段；若你的 schema 用的是
// Name/Nickname，请把 dbuser.Username(username) 换成对应谓词（如 dbuser.Name(username)）。
func (r *EntUserResolver) GetIDByUsername(c *gin.Context, username string) (int64, error) {
	u, err := r.client.User.Query().
		Where(dbuser.Username(username)).
		Only(c.Request.Context())
	if err != nil {
		return 0, err
	}
	return int64(u.ID), nil
}

// GetIDByEmail 按邮箱查 user_id。
func (r *EntUserResolver) GetIDByEmail(c *gin.Context, email string) (int64, error) {
	u, err := r.client.User.Query().
		Where(dbuser.Email(email)).
		Only(c.Request.Context())
	if err != nil {
		return 0, err
	}
	return int64(u.ID), nil
}

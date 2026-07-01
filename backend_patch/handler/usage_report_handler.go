// usage_report_handler.go — 外部用量上报接口（sub2api 后端补丁）。
//
// 路由：POST /api/v1/usage/report   （JWT 鉴权，登录用户上报自己的本地用量）
//
// 安全模型：
//   - 默认关联到「当前登录用户」（user_id 取自 JWT 上下文），忽略 body 里的 username，
//     防止普通用户冒名给他人写用量。
//   - 若当前登录者是管理员，且 body 指定了 username/email，则解析为目标用户（代上报）。
//
// 集成时：放到 backend/internal/handler/usage_report_handler.go，
// 并按你的工程把 userService / 取登录用户的方式替换为现有实现。
package handler

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/Wei-Shaw/sub2api/internal/repository"
)

// ---- 依赖接口（集成时对接现有 service）-------------------------------------

// UserResolver 把 username/email 解析为 user_id。sub2api 中应已有等价方法，
// 例如 userService.GetByEmail / GetByUsername；这里抽象成最小接口。
type UserResolver interface {
	GetIDByUsername(ctx *gin.Context, username string) (int64, error)
	GetIDByEmail(ctx *gin.Context, email string) (int64, error)
}

// UsageReportHandler 处理外部用量上报。
type UsageReportHandler struct {
	repo  *repository.ExternalUsageRepo
	users UserResolver
}

func NewUsageReportHandler(repo *repository.ExternalUsageRepo, users UserResolver) *UsageReportHandler {
	return &UsageReportHandler{repo: repo, users: users}
}

// ---- 请求/响应 DTO ---------------------------------------------------------

type usageReportItem struct {
	Date                string  `json:"date"`            // YYYY-MM-DD (UTC)
	AppType             string  `json:"app_type"`        // claude | codex
	Model               string  `json:"model"`           // 计费模型（必填）
	RequestModel        string  `json:"request_model"`   // 请求时模型
	RequestCount        int     `json:"request_count"`
	SuccessCount        int     `json:"success_count"`
	InputTokens         int64   `json:"input_tokens"`
	OutputTokens        int64   `json:"output_tokens"`
	CacheReadTokens     int64   `json:"cache_read_tokens"`
	CacheCreationTokens int64   `json:"cache_creation_tokens"`
	TotalCostUSD        float64 `json:"total_cost_usd"`
}

type usageReportRequest struct {
	Username    string            `json:"username"`
	Email       string            `json:"email"`
	Source      string            `json:"source"`      // 默认 cc-switch
	Granularity string            `json:"granularity"` // daily
	Items       []usageReportItem `json:"items"`
}

type usageReportResponse struct {
	Accepted int    `json:"accepted"`
	Rejected int    `json:"rejected"`
	UserID   int64  `json:"user_id"`
	Message  string `json:"message,omitempty"`
}

// ---- Handler ---------------------------------------------------------------

const maxReportItems = 5000

var allowedReportSources = map[string]struct{}{
	"cc-switch": {},
}

// Report 处理 POST /api/v1/usage/report。
func (h *UsageReportHandler) Report(c *gin.Context) {
	var req usageReportRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体解析失败: " + err.Error()})
		return
	}
	if len(req.Items) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "items 不能为空"})
		return
	}
	if len(req.Items) > maxReportItems {
		c.JSON(http.StatusBadRequest, gin.H{"error": "items 过多，单次最多 5000 条"})
		return
	}

	targetUserID, err := h.resolveTargetUser(c, &req)
	if err != nil {
		c.JSON(http.StatusForbidden, gin.H{"error": err.Error()})
		return
	}

	source := strings.TrimSpace(req.Source)
	if source == "" {
		source = "cc-switch"
	}
	if _, ok := allowedReportSources[source]; !ok {
		c.JSON(http.StatusBadRequest, gin.H{"error": "source 不允许: " + source})
		return
	}
	if req.Granularity != "" && req.Granularity != "daily" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "granularity 仅支持 daily"})
		return
	}

	rows := make([]repository.ExternalUsageDaily, 0, len(req.Items))
	rejected := 0
	for _, it := range req.Items {
		if err := validateUsageReportItem(it); err != nil {
			rejected++
			continue
		}
		model := strings.TrimSpace(it.Model)
		requestModel := strings.TrimSpace(it.RequestModel)
		if requestModel == "" {
			requestModel = model
		}
		appType := strings.TrimSpace(it.AppType)
		if appType == "" {
			appType = "unknown"
		}
		rows = append(rows, repository.ExternalUsageDaily{
			UserID:              targetUserID,
			Source:              source,
			UsageDate:           it.Date,
			AppType:             appType,
			Model:               model,
			RequestedModel:      requestModel,
			RequestCount:        it.RequestCount,
			SuccessCount:        it.SuccessCount,
			InputTokens:         it.InputTokens,
			OutputTokens:        it.OutputTokens,
			CacheReadTokens:     it.CacheReadTokens,
			CacheCreationTokens: it.CacheCreationTokens,
			TotalCost:           formatCost(it.TotalCostUSD),
		})
	}

	if len(rows) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "所有 items 均无效（缺少 date 或 model）"})
		return
	}

	accepted, err := h.repo.UpsertBatch(c.Request.Context(), rows)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "写入失败: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, usageReportResponse{
		Accepted: accepted,
		Rejected: rejected,
		UserID:   targetUserID,
	})
}

// resolveTargetUser 决定本次上报写到哪个 user_id。
func (h *UsageReportHandler) resolveTargetUser(c *gin.Context, req *usageReportRequest) (int64, error) {
	authedID := currentUserID(c)   // 取自 JWT 中间件写入的上下文
	isAdmin := currentUserIsAdmin(c)

	// 普通用户：只能上报自己的用量
	if !isAdmin {
		if authedID == 0 {
			return 0, errUnauthenticated
		}
		return authedID, nil
	}

	// 管理员：可代上报指定用户；未指定则默认自己
	if u := strings.TrimSpace(req.Username); u != "" {
		id, err := h.users.GetIDByUsername(c, u)
		if err != nil {
			return 0, errUserNotFound
		}
		return id, nil
	}
	if e := strings.TrimSpace(req.Email); e != "" {
		id, err := h.users.GetIDByEmail(c, e)
		if err != nil {
			return 0, errUserNotFound
		}
		return id, nil
	}
	if authedID == 0 {
		return 0, errUnauthenticated
	}
	return authedID, nil
}

func validateUsageReportItem(it usageReportItem) error {
	if strings.TrimSpace(it.Date) == "" {
		return fmt.Errorf("date 不能为空")
	}
	if _, err := time.Parse("2006-01-02", it.Date); err != nil {
		return fmt.Errorf("date 格式必须为 YYYY-MM-DD")
	}
	if strings.TrimSpace(it.Model) == "" {
		return fmt.Errorf("model 不能为空")
	}
	if it.RequestCount < 0 || it.SuccessCount < 0 {
		return fmt.Errorf("request_count/success_count 不能为负数")
	}
	if it.SuccessCount > it.RequestCount {
		return fmt.Errorf("success_count 不能大于 request_count")
	}
	if it.InputTokens < 0 || it.OutputTokens < 0 || it.CacheReadTokens < 0 || it.CacheCreationTokens < 0 {
		return fmt.Errorf("token 计数不能为负数")
	}
	if it.TotalCostUSD < 0 {
		return fmt.Errorf("total_cost_usd 不能为负数")
	}
	return nil
}

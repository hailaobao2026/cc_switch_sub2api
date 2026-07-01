// Package repository — 外部用量上报仓储层（sub2api 后端补丁）。
//
// 风格对齐 sub2api 现有 internal/repository：usageLogRepository 内部持有 `db *sql.DB`
// 并用 database/sql 执行 raw SQL（见 usage_log_repo.go）。本仓储沿用同一连接池类型，
// 集成时直接复用你装配 repository 时已有的 *sql.DB 即可。
//
// 放置位置：backend/internal/repository/external_usage_repo.go
package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"
)

// sqlExecutor 抽象出本仓储用到的最小执行接口，*sql.DB 与 *sql.Tx 均满足。
// （sub2api 同包内已有一个同名/同义的 sqlExecutor；若编译冲突，删除此处定义、
//  直接复用同包既有接口即可。）
type sqlExecutor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

// ExternalUsageDaily 对应 external_usage_daily 表一行。
type ExternalUsageDaily struct {
	UserID              int64
	Source              string
	UsageDate           string // YYYY-MM-DD (UTC)
	AppType             string
	Model               string
	RequestedModel      string
	RequestCount        int
	SuccessCount        int
	InputTokens         int64
	OutputTokens        int64
	CacheReadTokens     int64
	CacheCreationTokens int64
	TotalCost           string // 十进制字符串，直接交给 numeric
}

// ExternalUsageRepo 负责外部用量的幂等 upsert。
type ExternalUsageRepo struct {
	db sqlExecutor
}

// NewExternalUsageRepo 接收与 usageLogRepository 相同的 *sql.DB（或任意 sqlExecutor）。
func NewExternalUsageRepo(db sqlExecutor) *ExternalUsageRepo {
	return &ExternalUsageRepo{db: db}
}

// UpsertBatch 批量 upsert（按唯一键覆盖，幂等，不重复计数）。
// 返回写入/更新的行数。
func (r *ExternalUsageRepo) UpsertBatch(ctx context.Context, rows []ExternalUsageDaily) (int, error) {
	if len(rows) == 0 {
		return 0, nil
	}

	const cols = 13
	valueClauses := make([]string, 0, len(rows))
	args := make([]any, 0, len(rows)*cols)

	for i, row := range rows {
		base := i * cols
		ph := make([]string, cols)
		for j := 0; j < cols; j++ {
			ph[j] = fmt.Sprintf("$%d", base+j+1)
		}
		valueClauses = append(valueClauses, "("+strings.Join(ph, ",")+")")

		source := row.Source
		if source == "" {
			source = "cc-switch"
		}
		appType := row.AppType
		if appType == "" {
			appType = "unknown"
		}
		cost := row.TotalCost
		if cost == "" {
			cost = "0"
		}

		args = append(args,
			row.UserID,              // user_id
			source,                  // source
			row.UsageDate,           // usage_date
			appType,                 // app_type
			row.Model,               // model
			row.RequestedModel,      // requested_model
			row.RequestCount,        // request_count
			row.SuccessCount,        // success_count
			row.InputTokens,         // input_tokens
			row.OutputTokens,        // output_tokens
			row.CacheReadTokens,     // cache_read_tokens
			row.CacheCreationTokens, // cache_creation_tokens
			cost,                    // total_cost
		)
	}

	query := `
INSERT INTO external_usage_daily (
    user_id, source, usage_date, app_type, model, requested_model,
    request_count, success_count, input_tokens, output_tokens,
    cache_read_tokens, cache_creation_tokens, total_cost
) VALUES ` + strings.Join(valueClauses, ",") + `
ON CONFLICT (user_id, source, usage_date, app_type, model, requested_model)
DO UPDATE SET
    request_count          = EXCLUDED.request_count,
    success_count          = EXCLUDED.success_count,
    input_tokens           = EXCLUDED.input_tokens,
    output_tokens          = EXCLUDED.output_tokens,
    cache_read_tokens      = EXCLUDED.cache_read_tokens,
    cache_creation_tokens  = EXCLUDED.cache_creation_tokens,
    total_cost             = EXCLUDED.total_cost,
    reported_at            = now();`

	if _, err := r.db.ExecContext(ctx, query, args...); err != nil {
		return 0, fmt.Errorf("upsert external_usage_daily: %w", err)
	}
	return len(rows), nil
}

-- ============================================================================
-- 0001_external_usage_daily.sql
-- sub2api 后端补丁：外部（CC Switch 等）每日用量上报表
--
-- 设计要点：
--   * cc-switch 的 daily 聚合桶在当天会持续累加，客户端每次上报「该桶的最新累计值」。
--   * 因此这里用 UPSERT（ON CONFLICT DO UPDATE）按唯一键覆盖，天然幂等、不会重复计数。
--   * 该表独立于 usage_logs，避免破坏其 (request_id, api_key_id) 唯一约束与计费语义；
--     再通过下方 VIEW 合并进管理端统计（见 0002）。
-- ============================================================================

CREATE TABLE IF NOT EXISTS external_usage_daily (
    id                      BIGSERIAL    PRIMARY KEY,
    user_id                 BIGINT       NOT NULL,
    source                  TEXT         NOT NULL DEFAULT 'cc-switch',  -- 数据来源
    usage_date              DATE         NOT NULL,                      -- UTC 日期
    app_type                TEXT         NOT NULL DEFAULT 'unknown',    -- claude | codex
    model                   TEXT         NOT NULL,                      -- 计费模型
    requested_model         TEXT         NOT NULL DEFAULT '',           -- 请求时模型
    request_count           INTEGER      NOT NULL DEFAULT 0,
    success_count           INTEGER      NOT NULL DEFAULT 0,
    input_tokens            BIGINT       NOT NULL DEFAULT 0,
    output_tokens           BIGINT       NOT NULL DEFAULT 0,
    cache_read_tokens       BIGINT       NOT NULL DEFAULT 0,
    cache_creation_tokens   BIGINT       NOT NULL DEFAULT 0,
    total_cost              NUMERIC(20,10) NOT NULL DEFAULT 0,          -- USD
    reported_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),        -- 最近一次上报时间
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 唯一键：同一用户/来源/日期/app/模型 只保留一行，重复上报即更新
CREATE UNIQUE INDEX IF NOT EXISTS uq_external_usage_daily_bucket
    ON external_usage_daily (user_id, source, usage_date, app_type, model, requested_model);

-- 常用查询索引
CREATE INDEX IF NOT EXISTS idx_external_usage_daily_user_date
    ON external_usage_daily (user_id, usage_date);
CREATE INDEX IF NOT EXISTS idx_external_usage_daily_model
    ON external_usage_daily (model);

-- 如需外键（确认 users 表名/主键后再启用）：
-- ALTER TABLE external_usage_daily
--   ADD CONSTRAINT fk_external_usage_daily_user
--   FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

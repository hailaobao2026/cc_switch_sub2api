CREATE TABLE IF NOT EXISTS external_usage_daily (
    id                      BIGSERIAL       PRIMARY KEY,
    user_id                 BIGINT          NOT NULL,
    source                  TEXT            NOT NULL DEFAULT 'cc-switch',
    usage_date              DATE            NOT NULL,
    app_type                TEXT            NOT NULL DEFAULT 'unknown',
    model                   TEXT            NOT NULL,
    requested_model         TEXT            NOT NULL DEFAULT '',
    request_count           INTEGER         NOT NULL DEFAULT 0,
    success_count           INTEGER         NOT NULL DEFAULT 0,
    input_tokens            BIGINT          NOT NULL DEFAULT 0,
    output_tokens           BIGINT          NOT NULL DEFAULT 0,
    cache_read_tokens       BIGINT          NOT NULL DEFAULT 0,
    cache_creation_tokens   BIGINT          NOT NULL DEFAULT 0,
    total_cost              NUMERIC(20,10)  NOT NULL DEFAULT 0,
    reported_at             TIMESTAMPTZ     NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_usage_daily_bucket
    ON external_usage_daily (user_id, source, usage_date, app_type, model, requested_model);

CREATE INDEX IF NOT EXISTS idx_external_usage_daily_user_date
    ON external_usage_daily (user_id, usage_date);

CREATE INDEX IF NOT EXISTS idx_external_usage_daily_model
    ON external_usage_daily (model);

DROP VIEW IF EXISTS admin_external_usage_v;

CREATE VIEW admin_external_usage_v AS
SELECT
    e.user_id,
    u.username,
    u.email,
    e.source,
    e.usage_date,
    e.app_type,
    e.model,
    e.requested_model,
    e.request_count,
    e.success_count,
    e.input_tokens,
    e.output_tokens,
    e.cache_read_tokens,
    e.cache_creation_tokens,
    e.total_cost,
    e.reported_at
FROM external_usage_daily e
LEFT JOIN users u ON u.id = e.user_id;

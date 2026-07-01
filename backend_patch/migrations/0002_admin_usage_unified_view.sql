-- ============================================================================
-- 0002_admin_usage_unified_view.sql  （可选）
-- 把 external_usage_daily 合并进管理端用量视图，使 CC Switch 上报的数据
-- 也能出现在「按模型 / 按用户 / 按天」的统计里。
--
-- 说明：sub2api 原生 /admin/usage 直接查 usage_logs。若你希望最小侵入地展示
-- 外部用量，有两种用法：
--   A) 前端新增一个「外部用量」标签页，直接查询本视图（推荐，零侵入）。
--   B) 修改 dashboard 聚合 SQL，UNION ALL 本视图（侵入大，需改 Go 聚合层）。
-- ============================================================================

CREATE OR REPLACE VIEW admin_external_usage_v AS
SELECT
    e.user_id,
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
FROM external_usage_daily e;

-- 便于「本地(CC Switch) vs 平台(sub2api)」对比的按天×用户×模型汇总：
--   platform_cost 来自 usage_logs（平台内消耗）
--   external_cost 来自 external_usage_daily（本地上报）
-- 注意：按需调整 usage_logs 的列名/时间列以匹配你的版本。
CREATE OR REPLACE VIEW admin_usage_combined_v AS
WITH platform AS (
    SELECT
        ul.user_id,
        (ul.created_at AT TIME ZONE 'UTC')::date AS usage_date,
        ul.model,
        SUM(ul.input_tokens)                      AS input_tokens,
        SUM(ul.output_tokens)                     AS output_tokens,
        SUM(ul.total_cost)                        AS cost,
        COUNT(*)                                  AS request_count
    FROM usage_logs ul
    GROUP BY ul.user_id, (ul.created_at AT TIME ZONE 'UTC')::date, ul.model
),
external AS (
    SELECT
        e.user_id,
        e.usage_date,
        e.model,
        SUM(e.input_tokens)   AS input_tokens,
        SUM(e.output_tokens)  AS output_tokens,
        SUM(e.total_cost)     AS cost,
        SUM(e.request_count)  AS request_count
    FROM external_usage_daily e
    GROUP BY e.user_id, e.usage_date, e.model
)
SELECT
    COALESCE(p.user_id, x.user_id)       AS user_id,
    COALESCE(p.usage_date, x.usage_date) AS usage_date,
    COALESCE(p.model, x.model)           AS model,
    COALESCE(p.cost, 0)                  AS platform_cost,
    COALESCE(x.cost, 0)                  AS external_cost,
    COALESCE(p.request_count, 0)         AS platform_requests,
    COALESCE(x.request_count, 0)         AS external_requests
FROM platform p
FULL OUTER JOIN external x
    ON p.user_id = x.user_id
   AND p.usage_date = x.usage_date
   AND p.model = x.model;

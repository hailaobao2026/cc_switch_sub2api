"""读取 cc-switch.db 并按 天 × 模型 聚合用量。

源表: ``proxy_request_logs``（每次代理请求一行）。字段见 cc-switch-db-分析.md。
聚合输出对齐 sub2api ``usage_logs`` 的 token / cost 维度，便于后端写入。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class DailyModelUsage:
    """某用户 在 某天 对 某模型(某 app) 的聚合用量。"""

    date: str            # YYYY-MM-DD (UTC)
    app_type: str        # claude | codex
    model: str           # 计费模型
    request_model: str   # 请求时指定的模型（回退到 model）
    request_count: int
    success_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    total_cost_usd: float
    # 用于幂等去重：该聚合桶的稳定指纹
    dedup_key: str = ""

    def to_payload(self) -> dict:
        d = asdict(self)
        d.pop("dedup_key", None)
        return d


def _utc_date(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d")


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _readonly_sqlite_uri(db_path: str) -> str:
    """Build a SQLite file URI that is safe for Windows paths and special chars."""
    return f"{Path(db_path).expanduser().resolve().as_uri()}?mode=ro&immutable=1"


def read_daily_model_usage(
    db_path: str,
    app_types: list[str],
    only_success: bool,
    since_epoch: int | None = None,
) -> list[DailyModelUsage]:
    """从 proxy_request_logs 聚合出 天×模型 用量列表。

    Args:
        db_path: cc-switch.db 路径
        app_types: 需要包含的 app_type（claude/codex）
        only_success: 仅统计 status_code 2xx 的请求
        since_epoch: 仅统计该 Unix 时间戳（秒）之后创建的请求；None 表示全部
    """
    # 只读方式打开，避免锁住正在运行的 CC Switch
    uri = _readonly_sqlite_uri(db_path)
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        clauses = []
        params: list = []
        if app_types:
            placeholders = ",".join("?" for _ in app_types)
            clauses.append(f"app_type IN ({placeholders})")
            params.extend(app_types)
        if since_epoch is not None:
            clauses.append("created_at > ?")
            params.append(since_epoch)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        # 在 SQL 内完成大部分聚合，Python 侧再做日期换算后二次聚合
        rows = con.execute(
            f"""
            SELECT
                created_at,
                app_type,
                COALESCE(NULLIF(model, ''), 'unknown')        AS model,
                COALESCE(NULLIF(request_model, ''), model)     AS request_model,
                COALESCE(input_tokens, 0)                      AS input_tokens,
                COALESCE(output_tokens, 0)                     AS output_tokens,
                COALESCE(cache_read_tokens, 0)                 AS cache_read_tokens,
                COALESCE(cache_creation_tokens, 0)             AS cache_creation_tokens,
                total_cost_usd,
                status_code
            FROM proxy_request_logs
            {where}
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    # 桶: (date, app_type, model, request_model) -> 累加
    buckets: dict[tuple, DailyModelUsage] = {}
    for r in rows:
        created = r["created_at"]
        if created is None:
            continue
        is_success = 200 <= (r["status_code"] or 0) < 300
        if only_success and not is_success:
            continue

        date = _utc_date(int(created))
        key = (date, r["app_type"], r["model"], r["request_model"])
        bucket = buckets.get(key)
        if bucket is None:
            bucket = DailyModelUsage(
                date=date,
                app_type=r["app_type"] or "unknown",
                model=r["model"],
                request_model=r["request_model"],
                request_count=0,
                success_count=0,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                total_cost_usd=0.0,
            )
            buckets[key] = bucket

        bucket.request_count += 1
        if is_success:
            bucket.success_count += 1
        bucket.input_tokens += int(r["input_tokens"])
        bucket.output_tokens += int(r["output_tokens"])
        bucket.cache_read_tokens += int(r["cache_read_tokens"])
        bucket.cache_creation_tokens += int(r["cache_creation_tokens"])
        bucket.total_cost_usd += _to_float(r["total_cost_usd"])

    result = sorted(buckets.values(), key=lambda b: (b.date, b.app_type, b.model))
    for b in result:
        b.total_cost_usd = round(b.total_cost_usd, 6)
        b.dedup_key = f"{b.date}|{b.app_type}|{b.model}|{b.request_model}"
    return result


def max_created_at(db_path: str) -> int:
    """返回表中最大的 created_at（用于推进增量水位线）。"""
    uri = _readonly_sqlite_uri(db_path)
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute("SELECT MAX(created_at) FROM proxy_request_logs").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        con.close()

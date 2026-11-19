"""上报编排：读取 → 聚合 → 去重 → 批量上报 → 落状态。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import magpie as magpie_source
from .config import Config
from .database import DailyModelUsage, read_daily_model_usage, max_created_at
from .state import State
from .sub2api_client import Sub2ApiClient, Sub2ApiError


def _bucket_signature(b: DailyModelUsage) -> str:
    """对桶的累计数值取指纹，用于判断是否有变化需重发。"""
    raw = (
        f"{b.request_count}|{b.success_count}|{b.input_tokens}|{b.output_tokens}|"
        f"{b.cache_read_tokens}|{b.cache_creation_tokens}|{b.total_cost_usd}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class ReportSummary:
    total_buckets: int = 0
    changed_buckets: int = 0
    sent_buckets: int = 0
    skipped_unchanged: int = 0
    batches: int = 0
    dry_run: bool = False
    cc_switch_buckets: int = 0
    magpie_buckets: int = 0


def _watermark(cfg: Config) -> int:
    """CC Switch 水位线；数据库不存在（纯 magpie 模式）时不推进。"""
    try:
        if Path(cfg.db_path).exists():
            return max_created_at(cfg.db_path)
    except Exception:
        pass
    return 0


def collect_buckets(cfg: Config, logger=print) -> tuple[list[DailyModelUsage], int, int]:
    """采集所有启用的数据源，返回 (桶列表, cc-switch 桶数, magpie 桶数)。

    两个来源的输出结构完全一致，混在一个批次里上报：
    CC Switch 的桶 app_type 是 claude/codex，magpie 的桶 app_type 默认是 magpie，
    服务端按 (user, source, date, app_type, model, requested_model) upsert，天然互不覆盖。
    """
    buckets: list[DailyModelUsage] = []
    cc_count = 0

    db_exists = Path(cfg.db_path).exists()
    if not cfg.cc_switch_enabled:
        logger("CC Switch 采集已关闭")
    elif db_exists:
        cc_buckets = read_daily_model_usage(
            db_path=cfg.db_path,
            app_types=cfg.app_types,
            only_success=cfg.only_success,
            since_epoch=None,
        )
        cc_count = len(cc_buckets)
        buckets.extend(cc_buckets)
    elif cfg.magpie_enabled:
        logger(f"跳过 CC Switch：找不到数据库 {cfg.db_path}（仅上报 magpie）")
    else:
        raise FileNotFoundError(f"找不到数据库: {cfg.db_path}")

    magpie_count = 0
    if cfg.magpie_enabled:
        try:
            read = magpie_source.read_daily_model_usage(
                api_url=cfg.magpie_api_url,
                usage_path=cfg.magpie_path,
                app_type=cfg.magpie_app_type,
                agents=cfg.magpie_agents,
                only_success=cfg.only_success,
                include_logged=cfg.magpie_include_logged,
                since_days=cfg.magpie_since_days,
                prefer_api=cfg.magpie_prefer_api,
                timeout=cfg.timeout,
                verify_tls=cfg.verify_tls,
                logger=logger,
            )
        except Exception as exc:
            # magpie 是附加源：它失败不应让 CC Switch 的正常上报一起失败
            logger(f"magpie 采集失败，已跳过: {exc}")
        else:
            for note in read.notes:
                logger(note)
            logger(read.describe())
            if read.unpriced_rows and read.mode == "api":
                logger(
                    f"magpie 有 {read.unpriced_rows} 行没有价格表条目，成本按 0 计入"
                    "（与 magpie 界面上的「未计价」口径一致）"
                )
            magpie_count = len(read.buckets)
            buckets.extend(read.buckets)

    return buckets, cc_count, magpie_count


def build_payload(cfg: Config, buckets: list[DailyModelUsage]) -> dict:
    """组装单批上报体。用户名优先关联，邮箱兜底。"""
    return {
        "username": cfg.username or None,
        "email": cfg.email or None,
        "source": cfg.source.strip(),
        "granularity": "daily",
        "items": [b.to_payload() for b in buckets],
    }


def run(cfg: Config, *, dry_run: bool = False, incremental: bool = True,
        logger=print) -> ReportSummary:
    # incremental 参数保留以兼容 CLI；当前实现始终全量扫描 + signature 去重，
    # 故该参数不改变行为（water-mark 仅信息性记录）。
    _ = incremental
    cfg.validate()
    state = State(cfg.state_path)
    with state.locked():
        state._load()
        return _run_locked(cfg, state, dry_run=dry_run, logger=logger)


def _run_locked(cfg: Config, state: State, *, dry_run: bool = False,
                logger=print) -> ReportSummary:
    summary = ReportSummary(dry_run=dry_run)

    # 设计要点：daily 聚合桶在当天会持续累加，若按 created_at 水位线截断会少算当天数据。
    # 因此始终「全量读取 → 按桶数值 signature 去重」：只有新增或数值变化的桶才上报，
    # 后端再按 (date, model, ...) upsert，保证幂等。water-mark 仅作信息记录。
    buckets, cc_count, magpie_count = collect_buckets(cfg, logger=logger)
    summary.cc_switch_buckets = cc_count
    summary.magpie_buckets = magpie_count
    summary.total_buckets = len(buckets)
    if cfg.magpie_enabled:
        logger(f"数据源桶数: CC Switch={cc_count}  magpie={magpie_count}  合计={summary.total_buckets}")

    # 去重：仅发送「新增」或「数值发生变化」的桶
    pending: list[DailyModelUsage] = []
    sig_map: dict[str, str] = {}
    source_prefix = cfg.source.strip()
    for b in buckets:
        sig = _bucket_signature(b)
        state_key = f"{source_prefix}|{b.dedup_key}"
        sig_map[state_key] = sig
        if state.signature(state_key) != sig:
            pending.append(b)
    summary.changed_buckets = len(pending)
    summary.skipped_unchanged = summary.total_buckets - summary.changed_buckets

    logger(f"聚合桶: {summary.total_buckets}  待上报(变化): {summary.changed_buckets}  "
           f"未变化跳过: {summary.skipped_unchanged}")

    if not pending:
        logger("没有需要上报的变化。")
        if not dry_run:
            state.last_max_created_at = _watermark(cfg)
            state.save()
        return summary

    if dry_run:
        preview = pending[: min(10, len(pending))]
        for b in preview:
            logger(f"  [DRY] {b.date} {b.app_type:6} {b.model:24} "
                   f"req={b.request_count} in={b.input_tokens} out={b.output_tokens} "
                   f"cost=${b.total_cost_usd}")
        if len(pending) > len(preview):
            logger(f"  ... 其余 {len(pending) - len(preview)} 个桶省略")
        return summary

    # 实际上报
    client = Sub2ApiClient(timeout=cfg.timeout, verify_tls=cfg.verify_tls)
    if cfg.token:
        client.set_token(cfg.token)
        logger("使用配置中的 token（跳过登录）")
    else:
        client.login(cfg.login_url, cfg.email, cfg.password)
        logger(f"登录成功: {cfg.email}")

    for i in range(0, len(pending), cfg.batch_size):
        chunk = pending[i : i + cfg.batch_size]
        payload = build_payload(cfg, chunk)
        resp = client.report(cfg.report_url, payload)
        accepted = resp.get("accepted", len(chunk)) if isinstance(resp, dict) else len(chunk)
        rejected = resp.get("rejected", 0) if isinstance(resp, dict) else 0
        if accepted != len(chunk) or rejected:
            raise Sub2ApiError(
                f"批次部分失败：sent={len(chunk)} accepted={accepted} rejected={rejected}",
                body=str(resp),
            )
        summary.batches += 1
        summary.sent_buckets += len(chunk)
        logger(f"批次 {summary.batches}: 上报 {len(chunk)} 桶, 服务端 accepted={accepted}")
        # 仅在该批成功后写入对应 signature
        for b in chunk:
            state_key = f"{source_prefix}|{b.dedup_key}"
            state.mark(state_key, sig_map[state_key])
        state.save()

    state.last_max_created_at = _watermark(cfg)
    state.save()
    logger(f"完成：共上报 {summary.sent_buckets} 个桶，分 {summary.batches} 批。")
    return summary

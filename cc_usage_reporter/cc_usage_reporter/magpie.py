"""读取 magpie 网关的模型用量，按 天 × 模型 聚合。

magpie 不使用数据库：网关每服务一次模型调用，就往 ``usage.jsonl`` 追加一行 JSON
（上游实现见 magpie ``internal/usage/usage.go`` 的 ``Append``）。本模块提供两种
读取方式，输出与 ``database.py`` 完全一致的 :class:`DailyModelUsage`，因此上报
流水线与成本口径都不用改：

1. **本地 HTTP API（首选）** —— ``GET {api_url}/v1/magpie/usage/requests``。
   返回的每一行都带 magpie 自己按价格表算好的 ``cost``，所以金额是准的。
   分页参数 ``offset`` / ``limit``（默认 100，上限 500）。
2. **直接解析 usage.jsonl（回退）** —— magpie 没在运行也能离线统计；但记录里
   不存金额，此时 ``total_cost_usd`` 恒为 0，日志里会标注「未计价」。

口径说明
--------
* **只上报经过 magpie 网关的真实调用**。``/requests`` 还会返回 ``source="log"``
  的行（magpie 从 Claude Code / Codex 自己的会话文件里补读的历史调用，本机
  26134 行），这些很可能与 CC Switch 上报的桶重复，默认排除；需要时把
  ``include_logged`` 打开。
* ``source="search"`` 是搜索 API，不产生模型 token，两种模式都排除。
* 日期与 CC Switch 保持一致：按 **UTC** 取 ``YYYY-MM-DD``，便于服务端按
  ``usage_date`` 做幂等 upsert。
* ``reasoning`` 已包含在 ``out`` 里（各家厂商都把推理 token 计为输出），不再重复累加。
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from .database import DailyModelUsage

# magpie 网关默认监听（界面上「网关 127.0.0.1:3425」）
DEFAULT_API_URL = "http://127.0.0.1:3425"
# 与 CC Switch 的 claude / codex 并列、互不覆盖的 app_type
DEFAULT_APP_TYPE = "magpie"
# /v1/magpie/usage/requests 单页上限
PAGE_LIMIT = 500
# 单次拉取的默认窗口（天）；0 表示全部历史
DEFAULT_SINCE_DAYS = 30

# 来源标记：search 不产生模型 token，永远跳过
_SOURCE_SEARCH = "search"
# 从 agent 会话文件补读的调用（默认跳过，避免与其它上报源重复计数）
_SOURCE_LOG = "log"

Logger = Callable[[str], None]


@dataclass
class MagpieRead:
    """一次 magpie 采集的结果与过程信息（供日志展示）。"""

    buckets: list[DailyModelUsage] = field(default_factory=list)
    mode: str = "api"          # api | file
    source_path: str = ""      # file 模式的 usage.jsonl 路径
    rows: int = 0              # 参与聚合的记录数
    scanned: int = 0           # 扫描到的记录数（含被过滤的）
    unpriced_rows: int = 0     # 没有价格、成本按 0 计的行
    skipped_logged: int = 0    # 因 include_logged=False 被跳过的 source=log 行
    skipped_search: int = 0    # 被跳过的 source=search 行
    notes: list[str] = field(default_factory=list)

    def describe(self) -> str:
        where = f" file={self.source_path}" if self.source_path else ""
        return (
            f"magpie 采集: 模式={self.mode}{where} 扫描={self.scanned} 采用={self.rows} "
            f"桶={len(self.buckets)} 未计价行={self.unpriced_rows} "
            f"跳过log={self.skipped_logged} 跳过search={self.skipped_search}"
        )


# --------------------------------------------------------------------------- #
# 路径探测
# --------------------------------------------------------------------------- #

def candidate_usage_paths() -> tuple[Path, ...]:
    """按 magpie 自己的目录规则列出候选 usage.jsonl。

    magpie 的 ``internal/appdir.installed`` 在**所有平台**都用 XDG 风格：
    ``$XDG_CONFIG_HOME/magpie``，未设置时 ``~/.config/magpie``。
    macOS 上也一样，**不是** ``~/Library/Application Support``。

    便携模式把 data 目录放在 **magpie 程序自己旁边**（Windows 是 exe 同级，
    Mac 是 Magpie.app 同级）——那是另一个程序的位置，本程序猜不到，
    所以便携版请用户在界面上手动选择 ``usage.jsonl``。
    """
    home = Path.home()
    bases: list[Path] = [
        # 便携模式：magpie 与本程序恰好同目录时能命中（其余情况请手动选择）
        Path(sys.executable).parent / "data",
        Path.cwd() / "data",
    ]
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and Path(xdg).is_absolute():
        bases.append(Path(xdg) / "magpie")
    bases.append(home / ".config" / "magpie")

    out: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        for cand in (base / "usage.jsonl", base):
            key = str(cand).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
    return tuple(out)


def resolve_usage_path(raw: str = "") -> Path | None:
    """把用户配置解析成 usage.jsonl 路径。

    允许填文件本身，也允许只填所在目录（会自动补 ``usage.jsonl``）。
    未填时按 :func:`candidate_usage_paths` 自动探测。
    """
    value = (raw or "").strip()
    if value:
        path = Path(value).expanduser()
        if path.is_dir():
            path = path / "usage.jsonl"
        return path

    for cand in candidate_usage_paths():
        try:
            if cand.is_file() and cand.name == "usage.jsonl":
                return cand
            if cand.is_dir() and (cand / "usage.jsonl").is_file():
                return cand / "usage.jsonl"
        except OSError:
            continue
    return None


# --------------------------------------------------------------------------- #
# 时间 / 数值工具
# --------------------------------------------------------------------------- #

def _parse_time(value: object) -> datetime | None:
    """解析 magpie 记录里的 RFC3339 时间（形如 2026-11-19T10:25:42.9+08:00）。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _to_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _to_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_agents(agents: Sequence[str] | None) -> set[str]:
    return {str(a).strip().lower() for a in (agents or ()) if str(a).strip()}


# --------------------------------------------------------------------------- #
# HTTP API 方式
# --------------------------------------------------------------------------- #

def _period_of(since_days: int) -> str:
    if since_days and since_days > 0:
        return f"last:{int(since_days) * 24}h"
    return "all"


def _ssl_context(verify_tls: bool) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_api_rows(
    api_url: str,
    *,
    since_days: int = DEFAULT_SINCE_DAYS,
    timeout: float = 10.0,
    verify_tls: bool = True,
) -> list[dict]:
    """分页拉取 ``/v1/magpie/usage/requests`` 的全部行。

    :raises urllib.error.URLError: 网关不可达（调用方负责回退到文件）。
    """
    base = (api_url or DEFAULT_API_URL).rstrip("/")
    period = _period_of(since_days)
    ctx = _ssl_context(verify_tls)

    rows: list[dict] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {"period": period, "offset": offset, "limit": PAGE_LIMIT}
        )
        url = f"{base}/v1/magpie/usage/requests?{query}"
        request = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "cc-usage-reporter"}
        )
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))

        page = payload.get("rows") or []
        total = _to_int(payload.get("total"))
        rows.extend(page)
        offset += len(page)
        if not page or offset >= total:
            break
        # 防御：服务端 total 异常时不要无限翻页
        if offset > 2_000_000:
            break
    return rows


# --------------------------------------------------------------------------- #
# usage.jsonl 方式
# --------------------------------------------------------------------------- #

def fetch_file_rows(path: Path) -> tuple[list[dict], int]:
    """逐行解析 usage.jsonl，返回 (记录, 坏行数)。

    文件由 magpie 以 O_APPEND 追加，正常不会出现半行；偶发的坏行跳过即可，
    不应让一次上报整体失败。
    """
    rows: list[dict] = []
    bad = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(record, dict):
                rows.append(record)
    return rows, bad


# --------------------------------------------------------------------------- #
# 聚合
# --------------------------------------------------------------------------- #

def aggregate(
    rows: Sequence[dict],
    *,
    app_type: str = DEFAULT_APP_TYPE,
    agents: Sequence[str] | None = None,
    only_success: bool = True,
    include_logged: bool = False,
    since: datetime | None = None,
    has_cost: bool = True,
) -> MagpieRead:
    """把 magpie 记录聚合成 天 × 模型 桶。

    Args:
        has_cost: 数据源是否带 ``cost``（API 有、usage.jsonl 没有）。
        since: 只统计该时刻之后的调用；None 表示不截断。
    """
    wanted = _normalize_agents(agents)
    app = (app_type or DEFAULT_APP_TYPE).strip() or DEFAULT_APP_TYPE

    result = MagpieRead(mode="api" if has_cost else "file")
    buckets: dict[tuple[str, str, str, str], DailyModelUsage] = {}

    for record in rows:
        result.scanned += 1

        source = str(record.get("source") or "").strip().lower()
        if source == _SOURCE_SEARCH:
            result.skipped_search += 1
            continue
        if source == _SOURCE_LOG and not include_logged:
            result.skipped_logged += 1
            continue

        when = _parse_time(record.get("t"))
        if when is None:
            continue
        if since is not None and when < since:
            continue

        agent = str(record.get("agent") or "").strip()
        if wanted and agent.lower() not in wanted:
            continue

        model = str(record.get("model") or "").strip() or "unknown"
        requested = str(record.get("req") or record.get("requested") or "").strip()
        if not requested:
            requested = model

        status = _to_int(record.get("status"))
        succeeded = 200 <= status < 300
        if only_success and not succeeded:
            continue

        priced = record.get("priced")
        is_priced = has_cost and (priced is None or bool(priced))
        if has_cost and not is_priced:
            result.unpriced_rows += 1

        date = _utc_date(when)
        key = (date, app, model, requested)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = DailyModelUsage(
                date=date,
                app_type=app,
                model=model,
                request_model=requested,
                request_count=0,
                success_count=0,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                total_cost_usd=0.0,
                dedup_key=f"magpie|{date}|{app}|{model}|{requested}",
            )
            buckets[key] = bucket

        bucket.request_count += 1
        if succeeded:
            bucket.success_count += 1
        bucket.input_tokens += _to_int(record.get("in"))
        bucket.output_tokens += _to_int(record.get("out"))
        bucket.cache_read_tokens += _to_int(record.get("cache_read"))
        bucket.cache_creation_tokens += _to_int(record.get("cache_write"))
        if is_priced:
            bucket.total_cost_usd += _to_float(record.get("cost"))
        result.rows += 1

    ordered = sorted(buckets.values(), key=lambda b: (b.date, b.app_type, b.model))
    for bucket in ordered:
        bucket.total_cost_usd = round(bucket.total_cost_usd, 6)
    result.buckets = ordered
    return result


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #

def read_daily_model_usage(
    *,
    api_url: str = DEFAULT_API_URL,
    usage_path: str = "",
    app_type: str = DEFAULT_APP_TYPE,
    agents: Sequence[str] | None = None,
    only_success: bool = True,
    include_logged: bool = False,
    since_days: int = DEFAULT_SINCE_DAYS,
    prefer_api: bool = True,
    timeout: float = 10.0,
    verify_tls: bool = True,
    logger: Logger | None = None,
) -> MagpieRead:
    """采集 magpie 用量：优先走本地 HTTP API，失败则回退到 usage.jsonl。

    :raises FileNotFoundError: API 不可用且找不到 usage.jsonl。
    """
    log: Logger = logger or (lambda _msg: None)
    since = (
        datetime.now(timezone.utc) - timedelta(days=int(since_days))
        if since_days and since_days > 0
        else None
    )

    api_error: str = ""
    if prefer_api and (api_url or "").strip():
        try:
            rows = fetch_api_rows(
                api_url, since_days=since_days, timeout=timeout, verify_tls=verify_tls
            )
            read = aggregate(
                rows,
                app_type=app_type,
                agents=agents,
                only_success=only_success,
                include_logged=include_logged,
                since=since,
                has_cost=True,
            )
            read.mode = "api"
            read.notes.insert(0, f"magpie 数据源: HTTP API {api_url}")
            return read
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            api_error = str(exc)
            log(f"magpie API 不可用（{api_url}）: {api_error}，回退到 usage.jsonl")

    path = resolve_usage_path(usage_path)
    if path is None or not path.exists():
        probed = "\n  ".join(str(p) for p in candidate_usage_paths()[:6])
        raise FileNotFoundError(
            "找不到 magpie 的 usage.jsonl。请在界面「magpie 数据采集」中选择文件"
            f"（便携版一般在 magpie.exe 同级 data/usage.jsonl）。已探测:\n  {probed}"
        )

    rows, bad = fetch_file_rows(path)
    read = aggregate(
        rows,
        app_type=app_type,
        agents=agents,
        only_success=only_success,
        include_logged=include_logged,
        since=since,
        has_cost=False,
    )
    read.mode = "file"
    read.source_path = str(path)
    read.notes.insert(0, f"magpie 数据源: usage.jsonl {path}（无金额字段，成本按 0 计）")
    if bad:
        read.notes.append(f"usage.jsonl 有 {bad} 行无法解析，已跳过")
    return read
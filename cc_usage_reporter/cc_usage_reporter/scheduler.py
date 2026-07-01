from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .config import Config, load_config
from .reporter import ReportSummary, run
from .sub2api_client import Sub2ApiError


DEFAULT_SCHEDULE_TIMES = ["10:00", "18:00"]


@dataclass
class ScheduleInfo:
    next_run: datetime | None = None
    source: str = ""
    message: str = ""


def parse_schedule_times(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        values = list(DEFAULT_SCHEDULE_TIMES)
    elif isinstance(value, (list, tuple)):
        values = [str(x).strip() for x in value if str(x).strip()]
    else:
        values = [x.strip() for x in str(value).split(",") if x.strip()]

    if not values:
        raise ValueError("请至少配置一个定时上传时间，例如 10:00")

    parsed: list[str] = []
    for item in values:
        try:
            datetime.strptime(item, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"无效时间格式: {item}，请使用 HH:MM") from exc
        parsed.append(item)
    return parsed


def compute_next_run(times: list[str], now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    candidates: list[datetime] = []
    for item in times:
        hour, minute = map(int, item.split(":"))
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        candidates.append(candidate)
    return min(candidates)


class BackgroundScheduler:
    def __init__(
        self,
        *,
        config_path: str | None = None,
        logger: Callable[[str], None] = print,
        status_callback: Callable[[ScheduleInfo], None] | None = None,
    ):
        self.config_path = config_path
        self.logger = logger
        self.status_callback = status_callback
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._run_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def wake(self) -> None:
        self._wake_event.set()

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def run_once(self, source: str = "手动触发") -> ReportSummary | None:
        with self._run_lock:
            try:
                cfg = load_config(self.config_path)
                cfg.validate()
            except Exception as exc:
                self.logger(f"[{source}] 配置加载/校验失败: {exc}")
                return None

            try:
                self.logger(f"[{source}] 开始上传")
                summary = run(cfg, dry_run=False, incremental=True, logger=self.logger)
                self.logger(
                    f"[{source}] 完成: 总桶={summary.total_buckets} 变化={summary.changed_buckets} 已发送={summary.sent_buckets}"
                )
                return summary
            except Sub2ApiError as exc:
                self.logger(f"[{source}] 上传失败: {exc}")
                if exc.body:
                    self.logger(f"服务端响应: {exc.body[:500]}")
                return None
            except Exception as exc:
                self.logger(f"[{source}] 运行出错: {exc}")
                return None

    def _notify(self, *, next_run: datetime | None = None, source: str = "", message: str = "") -> None:
        if self.status_callback:
            self.status_callback(ScheduleInfo(next_run=next_run, source=source, message=message))

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                cfg = load_config(self.config_path)
            except Exception as exc:
                self.logger(f"调度器配置读取失败: {exc}")
                self._notify(message=f"配置读取失败: {exc}")
                if self._stop_event.wait(30):
                    break
                continue

            if not cfg.auto_upload:
                self._notify(message="自动上传未启用")
                if self._wait_interruptible(10):
                    continue
                continue

            try:
                times = parse_schedule_times(cfg.schedule_times)
            except Exception as exc:
                self.logger(f"定时上传配置错误: {exc}")
                self._notify(message=f"定时配置错误: {exc}")
                if self._wait_interruptible(30):
                    continue
                continue

            next_run = compute_next_run(times)
            self._notify(next_run=next_run, message=f"下次自动上传: {next_run:%Y-%m-%d %H:%M:%S}")

            while not self._stop_event.is_set():
                remaining = (next_run - datetime.now()).total_seconds()
                if remaining <= 0:
                    break
                timeout = min(remaining, 30)
                if self._wait_interruptible(timeout):
                    break

            if self._stop_event.is_set():
                break

            if self._wake_event.is_set():
                self._wake_event.clear()
                continue

            self.run_once(source="定时任务")

    def _wait_interruptible(self, timeout: float) -> bool:
        if timeout <= 0:
            return False
        if self._stop_event.wait(timeout):
            return True
        if self._wake_event.is_set():
            self._wake_event.clear()
            return True
        return False

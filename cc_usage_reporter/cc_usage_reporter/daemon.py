from __future__ import annotations

import signal
import sys
import threading
import time
from datetime import datetime

from .scheduler import BackgroundScheduler


class DaemonService:
    def __init__(self, *, config_path: str | None = None, logger=print):
        self.config_path = config_path
        self.logger = logger
        self.scheduler = BackgroundScheduler(config_path=config_path, logger=self._log)
        self._stop = threading.Event()

    def _log(self, message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger(f"[{ts}] {message}")

    def start(self) -> int:
        self._install_signal_handlers()
        self._log("后台模式启动")
        self.scheduler.start()
        try:
            while not self._stop.is_set():
                time.sleep(1)
        finally:
            self.scheduler.stop()
            self._log("后台模式退出")
        return 0

    def stop(self, *_args) -> None:
        self._stop.set()
        self.scheduler.stop()

    def _install_signal_handlers(self) -> None:
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            signal.signal(sig, self.stop)


def run_daemon(*, config_path: str | None = None) -> int:
    service = DaemonService(config_path=config_path)
    return service.start()

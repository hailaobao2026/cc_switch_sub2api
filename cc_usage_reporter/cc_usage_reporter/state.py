"""上报状态持久化。

用途：
1. 记录最近一次成功上报覆盖的最大 created_at（增量水位线，可选）。
2. 记录已成功上报的「天×模型」桶指纹及其当时的累计值，避免重复/或仅在数值变化时重发。

注意：daily 聚合桶在当天会持续累加，因此默认按「值是否变化」决定是否重发，
后端再用 (date, model, ...) 做 upsert 保证幂等。
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        self._data: dict = {"last_max_created_at": 0, "buckets": {}}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self._data.update(loaded)
            except (json.JSONDecodeError, OSError):
                # 状态损坏不应阻断上报，重建即可
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    @property
    def last_max_created_at(self) -> int:
        return int(self._data.get("last_max_created_at", 0))

    @last_max_created_at.setter
    def last_max_created_at(self, value: int) -> None:
        self._data["last_max_created_at"] = int(value)

    def signature(self, dedup_key: str) -> str | None:
        """返回该桶上次上报时记录的数值指纹（不存在则 None）。"""
        return self._data.get("buckets", {}).get(dedup_key)

    def mark(self, dedup_key: str, signature: str) -> None:
        self._data.setdefault("buckets", {})[dedup_key] = signature

    @contextlib.contextmanager
    def locked(self):
        """Best-effort process lock for scheduled tasks and manual runs."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_file = None
        try:
            if os.name == "nt":
                import msvcrt

                lock_file = open(lock_path, "a+b")
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                lock_file = open(lock_path, "a+b")
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if lock_file is not None:
                try:
                    if os.name == "nt":
                        import msvcrt

                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                finally:
                    lock_file.close()

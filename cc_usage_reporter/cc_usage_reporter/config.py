"""配置加载。

配置优先级（高 → 低）：命令行参数 > 环境变量 > 配置文件 > 默认值。
配置文件默认查找顺序会兼容 Windows / Linux / macOS 的常见目录，
并保留历史 `~/.cc-switch` 路径。
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field, fields
from pathlib import Path


def _dedup_paths(paths: list[Path]) -> tuple[Path, ...]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return tuple(result)


def get_platform_data_dirs() -> tuple[Path, ...]:
    home = Path.home()
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            candidates.append(Path(appdata) / "cc-switch")
        if localappdata:
            candidates.append(Path(localappdata) / "cc-switch")
        candidates.append(home / ".cc-switch")
    elif system == "Darwin":
        candidates.extend([
            home / "Library" / "Application Support" / "cc-switch",
            home / ".config" / "cc-switch",
            home / ".cc-switch",
        ])
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            candidates.append(Path(xdg) / "cc-switch")
        candidates.extend([
            home / ".config" / "cc-switch",
            home / ".cc-switch",
        ])

    return _dedup_paths(candidates)


PLATFORM_DATA_DIRS = get_platform_data_dirs()
DEFAULT_DATA_DIR = next((p for p in PLATFORM_DATA_DIRS if p.exists()), PLATFORM_DATA_DIRS[0])
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "cc-switch.db"
DEFAULT_STATE_PATH = DEFAULT_DATA_DIR / "usage_reporter_state.json"
DEFAULT_GUI_CONFIG_PATH = DEFAULT_DATA_DIR / "usage_reporter.gui.json"
CONFIG_SEARCH_PATHS = (Path("config.json"),) + tuple(
    base / "usage_reporter.json" for base in PLATFORM_DATA_DIRS
)

# 配置项 -> 环境变量名
_ENV_MAP = {
    "base_url": "SUB2API_BASE_URL",
    "username": "SUB2API_USERNAME",
    "email": "SUB2API_EMAIL",
    "password": "SUB2API_PASSWORD",
    "token": "SUB2API_TOKEN",
    "report_path": "SUB2API_REPORT_PATH",
    "login_path": "SUB2API_LOGIN_PATH",
    "db_path": "CC_SWITCH_DB_PATH",
    "state_path": "CC_SWITCH_STATE_PATH",
    "verify_tls": "SUB2API_VERIFY_TLS",
}


@dataclass
class Config:
    # --- sub2api 连接 ---
    base_url: str = ""                       # 例: https://sub2api.example.com
    login_path: str = "/api/v1/auth/login"   # 登录获取 JWT
    report_path: str = "/api/v1/usage/report"  # 用量摄取接口（后端补丁新增）

    # --- 身份关联（用户名优先，回退到邮箱） ---
    username: str = ""   # 关联到 sub2api 的用户名
    email: str = ""      # sub2api 登录邮箱（登录用）
    password: str = ""   # sub2api 登录密码（登录用）
    token: str = ""      # 直接提供 JWT/Bearer（提供则跳过登录）

    # --- 本地数据 ---
    db_path: str = str(DEFAULT_DB_PATH)
    state_path: str = str(DEFAULT_STATE_PATH)

    # --- 行为 ---
    app_types: list[str] = field(default_factory=lambda: ["claude", "codex"])
    only_success: bool = True   # 仅上报 status_code 2xx 的请求
    timeout: float = 30.0       # HTTP 超时（秒）
    batch_size: int = 200       # 每次 HTTP 上报的聚合条数
    verify_tls: bool = True     # 是否校验 TLS 证书
    auto_upload: bool = True    # GUI/daemon 启动后是否启用定时上传
    schedule_times: list[str] = field(default_factory=lambda: ["10:00", "18:00"])
    start_hidden: bool = True   # GUI / autostart 是否隐藏启动
    minimize_to_tray: bool = True  # 关闭窗口时是否进入系统托盘

    @property
    def login_url(self) -> str:
        return self.base_url.rstrip("/") + self.login_path

    @property
    def report_url(self) -> str:
        return self.base_url.rstrip("/") + self.report_path

    def validate(self) -> None:
        if not self.base_url:
            raise ValueError("缺少 base_url（sub2api 地址）")
        if not self.token and not (self.email and self.password):
            raise ValueError("需提供 token，或 email+password 用于登录")
        if not self.username and not self.email:
            raise ValueError("需提供 username 或 email 用于关联 sub2api 用户")
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"找不到数据库: {self.db_path}")


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_config(config_path: str | None = None, overrides: dict | None = None) -> Config:
    """合并配置文件、环境变量与命令行覆盖项，返回 Config。"""
    data: dict = {}

    candidates = [Path(config_path)] if config_path else list(CONFIG_SEARCH_PATHS)
    for path in candidates:
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data.update(json.load(fh))
            break

    for key, env_name in _ENV_MAP.items():
        if env_name in os.environ and os.environ[env_name] != "":
            data[key] = os.environ[env_name]

    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    valid = {f.name for f in fields(Config)}
    clean: dict = {}
    for key, value in data.items():
        if key not in valid:
            continue
        if key in {"only_success", "verify_tls", "auto_upload", "start_hidden", "minimize_to_tray"}:
            clean[key] = _coerce_bool(value)
        elif key in {"timeout"}:
            clean[key] = float(value)
        elif key in {"batch_size"}:
            clean[key] = int(value)
        elif key in {"app_types", "schedule_times"} and isinstance(value, str):
            clean[key] = [s.strip() for s in value.split(",") if s.strip()]
        else:
            clean[key] = value

    return Config(**clean)

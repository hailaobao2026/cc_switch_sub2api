from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .config import DEFAULT_DATA_DIR


APP_NAME = "CC Usage Reporter"
APP_ID = "cc-usage-reporter"


@dataclass
class AutostartStatus:
    enabled: bool
    platform: str
    path: str


def _platform_name() -> str:
    return platform.system()


def _quote(value: str) -> str:
    if not value:
        return '""'
    return '"' + value.replace('"', '\\"') + '"'


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _startup_dir_windows() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("未找到 APPDATA，无法安装 Windows 自启动")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _autostart_file_windows() -> Path:
    return _startup_dir_windows() / f"{APP_ID}.cmd"


def _desktop_file_linux() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "autostart" / f"{APP_ID}.desktop"


def _launch_agent_macos() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.local.{APP_ID}.plist"


def install_autostart(*, config_path: str | None = None, start_hidden: bool = True) -> str:
    system = _platform_name()
    if system == "Windows":
        return _install_windows(config_path=config_path, start_hidden=start_hidden)
    if system == "Darwin":
        return _install_macos(config_path=config_path, start_hidden=start_hidden)
    return _install_linux(config_path=config_path, start_hidden=start_hidden)


def uninstall_autostart() -> str:
    system = _platform_name()
    if system == "Windows":
        path = _autostart_file_windows()
    elif system == "Darwin":
        path = _launch_agent_macos()
    else:
        path = _desktop_file_linux()

    if path.exists():
        path.unlink()
        return f"已移除开机自启: {path}"
    return f"开机自启未安装: {path}"


def get_autostart_status() -> AutostartStatus:
    system = _platform_name()
    if system == "Windows":
        path = _autostart_file_windows()
    elif system == "Darwin":
        path = _launch_agent_macos()
    else:
        path = _desktop_file_linux()
    return AutostartStatus(enabled=path.exists(), platform=system, path=str(path))


def _install_windows(*, config_path: str | None, start_hidden: bool) -> str:
    path = _autostart_file_windows()
    path.parent.mkdir(parents=True, exist_ok=True)

    if _is_frozen():
        args = [sys.executable]
        if config_path:
            args.extend(["--config", config_path])
        if start_hidden:
            args.append("--start-hidden")
    else:
        python = shutil.which("pythonw") or shutil.which("python") or sys.executable
        args = [python, "-m", "cc_usage_reporter", "gui"]
        if config_path:
            args.extend(["--config", config_path])
        if start_hidden:
            args.append("--start-hidden")

    content = "@echo off\r\nstart \"\" " + " ".join(_quote(x) for x in args) + "\r\n"
    path.write_text(content, encoding="utf-8")
    return f"已安装 Windows 开机自启: {path}"


def _install_linux(*, config_path: str | None, start_hidden: bool) -> str:
    path = _desktop_file_linux()
    path.parent.mkdir(parents=True, exist_ok=True)

    if _is_frozen():
        args = [sys.executable]
    else:
        python = shutil.which("python3") or shutil.which("python") or sys.executable
        args = [python, "-m", "cc_usage_reporter", "gui"]

    if config_path:
        args.extend(["--config", config_path])
    if start_hidden:
        args.append("--start-hidden")

    exec_line = " ".join(_quote(x) for x in args)
    content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={APP_NAME}
Comment=Upload CC Switch usage to sub2api
Exec={exec_line}
Terminal=false
X-GNOME-Autostart-enabled=true
"""
    path.write_text(content, encoding="utf-8")
    return f"已安装 Linux 开机自启: {path}"


def _install_macos(*, config_path: str | None, start_hidden: bool) -> str:
    path = _launch_agent_macos()
    path.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if _is_frozen():
        args = [sys.executable]
    else:
        python = shutil.which("python3") or shutil.which("python") or sys.executable
        args = [python, "-m", "cc_usage_reporter", "gui"]

    if config_path:
        args.extend(["--config", config_path])
    if start_hidden:
        args.append("--start-hidden")

    program_args = "\n".join(f"        <string>{escape(arg)}</string>" for arg in args)
    stdout_path = escape(str(DEFAULT_DATA_DIR / 'cc-usage-reporter.stdout.log'))
    stderr_path = escape(str(DEFAULT_DATA_DIR / 'cc-usage-reporter.stderr.log'))
    content = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>com.local.{APP_ID}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
</dict>
</plist>
"""
    path.write_text(content, encoding="utf-8")
    return f"已安装 macOS 开机自启: {path}"

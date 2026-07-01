from __future__ import annotations

import importlib
import platform
from dataclasses import dataclass


@dataclass
class DependencyCheckResult:
    ok: bool
    messages: list[str]


def check_tray_dependencies() -> DependencyCheckResult:
    messages: list[str] = []
    ok = True

    for module in ("pystray", "PIL"):
        try:
            importlib.import_module(module)
            messages.append(f"OK: 已找到模块 {module}")
        except Exception as exc:
            ok = False
            messages.append(f"缺少模块 {module}: {exc}")

    system = platform.system()
    if system == "Linux":
        messages.append("提示: Linux 托盘通常还需要桌面环境与系统托盘支持（如 GNOME/KDE/Xfce）")
    elif system == "Darwin":
        messages.append("提示: macOS 托盘功能需要图形会话运行")
    elif system == "Windows":
        messages.append("提示: Windows 托盘功能通常可直接使用")

    if not ok:
        messages.append("安装建议: pip install pystray Pillow")

    return DependencyCheckResult(ok=ok, messages=messages)

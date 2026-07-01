from __future__ import annotations

import threading
from datetime import datetime

from .scheduler import BackgroundScheduler


def run_tray(*, config_path: str | None = None) -> int:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception as exc:
        print(f"系统托盘不可用，请先安装 pystray 和 Pillow: {exc}")
        return 1

    logs: list[str] = []

    def logger(message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}"
        logs.append(line)
        print(line)

    scheduler = BackgroundScheduler(config_path=config_path, logger=logger)
    scheduler.start()

    def create_image():
        image = Image.new("RGB", (64, 64), (35, 110, 180))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 56, 56), outline=(255, 255, 255), width=3)
        draw.text((18, 18), "CC", fill=(255, 255, 255))
        return image

    def on_upload(icon, _item):
        threading.Thread(target=lambda: scheduler.run_once(source="托盘手动上传"), daemon=True).start()

    def on_show_logs(icon, _item):
        print("--- 最近日志 ---")
        for line in logs[-20:]:
            print(line)

    def on_exit(icon, _item):
        scheduler.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("立即上传", on_upload),
        pystray.MenuItem("打印最近日志", on_show_logs),
        pystray.MenuItem("退出", on_exit),
    )

    icon = pystray.Icon("cc-usage-reporter", create_image(), "CC Usage Reporter", menu)
    icon.run()
    return 0

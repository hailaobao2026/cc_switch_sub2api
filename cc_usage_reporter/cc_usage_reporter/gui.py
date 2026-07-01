from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .autostart import get_autostart_status, install_autostart, uninstall_autostart
from .config import Config, DEFAULT_GUI_CONFIG_PATH, load_config
from .scheduler import BackgroundScheduler, ScheduleInfo, compute_next_run, parse_schedule_times
from .sub2api_client import Sub2ApiError


DEFAULT_SCHEDULE_TIMES = ["10:00", "18:00"]


class GuiLogger:
    def __init__(self, q: queue.Queue[str]):
        self.q = q

    def __call__(self, message: object) -> None:
        self.q.put(str(message))


class ReporterApp:
    def __init__(self, root: tk.Tk, *, config_path: str | None = None, start_hidden: bool = False):
        self.root = root
        self.root.title("CC Usage Reporter")
        self.root.geometry("920x760")
        self.root.minsize(800, 660)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.gui_config_path = Path(config_path).expanduser() if config_path else DEFAULT_GUI_CONFIG_PATH
        self.fields: dict[str, tk.Variable] = {}
        self.scheduler: BackgroundScheduler | None = None
        self.tray_icon = None
        self.tray_thread: threading.Thread | None = None

        self._build_ui()
        self._load_gui_config()
        self._refresh_autostart_status()
        self._start_scheduler()
        self.root.after(300, self._drain_logs)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if start_hidden:
            self.root.after(50, self.minimize_to_background)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(main, text="配置", padding=12)
        form.pack(fill=tk.X)

        self._add_entry(form, "db_path", "数据库路径", row=0, width=72)
        ttk.Button(form, text="选择...", command=self._pick_db).grid(row=0, column=2, padx=(8, 0), sticky="w")

        self._add_entry(form, "base_url", "上报地址", row=1, width=72)
        self._add_entry(form, "token", "Token", row=2, width=72, show="*")
        self._add_entry(form, "email", "邮箱", row=3, width=32)
        self._add_entry(form, "username", "用户名", row=3, column=2, width=24)
        self._add_entry(form, "state_path", "状态文件", row=4, width=72)
        ttk.Button(form, text="选择...", command=self._pick_state).grid(row=4, column=2, padx=(8, 0), sticky="w")

        self.fields["verify_tls"] = tk.BooleanVar(value=True)
        self.fields["only_success"] = tk.BooleanVar(value=True)
        self.fields["auto_upload"] = tk.BooleanVar(value=True)
        self.fields["schedule_times"] = tk.StringVar(value=", ".join(DEFAULT_SCHEDULE_TIMES))
        self.fields["start_hidden"] = tk.BooleanVar(value=True)
        self.fields["minimize_to_tray"] = tk.BooleanVar(value=True)

        opts = ttk.Frame(form)
        opts.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Checkbutton(opts, text="校验 TLS 证书", variable=self.fields["verify_tls"]).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(opts, text="仅统计成功请求", variable=self.fields["only_success"]).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(opts, text="启动后后台定时上传", variable=self.fields["auto_upload"], command=self._restart_scheduler).pack(side=tk.LEFT)

        schedule = ttk.Frame(form)
        schedule.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Label(schedule, text="定时上传时间").pack(side=tk.LEFT)
        ttk.Entry(schedule, textvariable=self.fields["schedule_times"], width=30).pack(side=tk.LEFT, padx=(8, 8))
        ttk.Label(schedule, text="多个时间用英文逗号分隔，例如 10:00,18:00").pack(side=tk.LEFT)

        auto = ttk.LabelFrame(main, text="开机自启 / 托盘", padding=10)
        auto.pack(fill=tk.X, pady=(12, 0))
        ttk.Checkbutton(auto, text="开机自启时隐藏窗口启动", variable=self.fields["start_hidden"]).pack(anchor="w")
        ttk.Checkbutton(auto, text="关闭窗口时最小化到系统托盘", variable=self.fields["minimize_to_tray"]).pack(anchor="w", pady=(4, 0))
        btns_auto = ttk.Frame(auto)
        btns_auto.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btns_auto, text="安装开机自启", command=self.enable_autostart).pack(side=tk.LEFT)
        ttk.Button(btns_auto, text="移除开机自启", command=self.disable_autostart).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns_auto, text="最小化到托盘", command=self.minimize_to_background).pack(side=tk.LEFT, padx=(8, 0))
        self.autostart_var = tk.StringVar(value="开机自启状态未知")
        ttk.Label(auto, textvariable=self.autostart_var, foreground="#555").pack(anchor="w", pady=(8, 0))

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=12)
        ttk.Button(btns, text="保存配置", command=self.save_config).pack(side=tk.LEFT)
        ttk.Button(btns, text="立即上传", command=self.trigger_upload).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="测试读取", command=self.preview_config).pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        self.scheduler_var = tk.StringVar(value="定时上传未启用")
        status = ttk.Frame(main)
        status.pack(fill=tk.X)
        ttk.Label(status, textvariable=self.status_var, foreground="#0a5").pack(anchor="w")
        ttk.Label(status, textvariable=self.scheduler_var, foreground="#555").pack(anchor="w", pady=(4, 0))

        log_frame = ttk.LabelFrame(main, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = scrolledtext.ScrolledText(log_frame, height=24, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        for i in range(4):
            form.columnconfigure(i, weight=1 if i in {1, 3} else 0)

    def _add_entry(self, parent, key: str, label: str, row: int, width: int = 40,
                   column: int = 0, show: str | None = None) -> None:
        if key not in self.fields:
            self.fields[key] = tk.StringVar()
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.fields[key], width=width, show=show).grid(
            row=row, column=column + 1, sticky="ew", pady=6, padx=(8, 0)
        )

    def _pick_db(self) -> None:
        path = filedialog.askopenfilename(title="选择 cc-switch.db", filetypes=[("SQLite DB", "*.db"), ("All Files", "*.*")])
        if path:
            self.fields["db_path"].set(path)

    def _pick_state(self) -> None:
        path = filedialog.asksaveasfilename(title="选择状态文件", defaultextension=".json", filetypes=[("JSON", "*.json"), ("All Files", "*.*")])
        if path:
            self.fields["state_path"].set(path)

    def _load_gui_config(self) -> None:
        try:
            cfg = load_config(str(self.gui_config_path)) if self.gui_config_path.exists() else Config()
        except Exception:
            cfg = Config()

        data = asdict(cfg)
        data.setdefault("schedule_times", DEFAULT_SCHEDULE_TIMES)
        data.setdefault("auto_upload", True)
        data.setdefault("start_hidden", True)
        data.setdefault("minimize_to_tray", True)

        try:
            if self.gui_config_path.exists():
                raw = json.loads(self.gui_config_path.read_text(encoding="utf-8"))
                data["start_hidden"] = raw.get("start_hidden", data["start_hidden"])
                data["minimize_to_tray"] = raw.get("minimize_to_tray", data["minimize_to_tray"])
        except Exception:
            pass

        for key, var in self.fields.items():
            if isinstance(var, tk.BooleanVar):
                var.set(bool(data.get(key, var.get())))
            else:
                value = data.get(key, "")
                if isinstance(value, list):
                    value = ",".join(value)
                var.set(str(value) if value is not None else "")

        if not self.fields["state_path"].get():
            self.fields["state_path"].set(str(Config().state_path))

    def collect_form_data(self, *, validate: bool = True) -> dict:
        data: dict[str, object] = {
            "db_path": self.fields["db_path"].get().strip(),
            "base_url": self.fields["base_url"].get().strip(),
            "token": self.fields["token"].get().strip(),
            "email": self.fields["email"].get().strip(),
            "username": self.fields["username"].get().strip(),
            "state_path": self.fields["state_path"].get().strip(),
            "verify_tls": bool(self.fields["verify_tls"].get()),
            "only_success": bool(self.fields["only_success"].get()),
            "auto_upload": bool(self.fields["auto_upload"].get()),
            "schedule_times": self.fields["schedule_times"].get().strip(),
            "start_hidden": bool(self.fields["start_hidden"].get()),
            "minimize_to_tray": bool(self.fields["minimize_to_tray"].get()),
            "report_path": "/api/v1/usage/report",
        }
        if validate:
            if not data["db_path"]:
                raise ValueError("请填写数据库路径")
            if not data["base_url"]:
                raise ValueError("请填写上报地址")
            if not data["token"]:
                raise ValueError("请填写 token")
            if not data["email"] and not data["username"]:
                raise ValueError("请至少填写邮箱或用户名")
            parse_schedule_times(data["schedule_times"])
        return data

    def save_config(self) -> None:
        try:
            data = self.collect_form_data(validate=True)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        payload = {
            "base_url": data["base_url"],
            "token": data["token"],
            "email": data["email"],
            "username": data["username"],
            "db_path": data["db_path"],
            "state_path": data["state_path"],
            "verify_tls": data["verify_tls"],
            "only_success": data["only_success"],
            "auto_upload": data["auto_upload"],
            "schedule_times": parse_schedule_times(data["schedule_times"]),
            "start_hidden": data["start_hidden"],
            "minimize_to_tray": data["minimize_to_tray"],
            "app_types": ["claude", "codex"],
            "report_path": "/api/v1/usage/report",
        }
        self.gui_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.gui_config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(f"配置已保存: {self.gui_config_path}")
        self.set_status("配置已保存")
        self._refresh_autostart_status()
        self._restart_scheduler()

    def build_runtime_config(self) -> Config:
        data = self.collect_form_data(validate=True)
        cfg = load_config(str(self.gui_config_path) if self.gui_config_path.exists() else None, overrides={
            "base_url": data["base_url"],
            "token": data["token"],
            "email": data["email"],
            "username": data["username"],
            "db_path": data["db_path"],
            "state_path": data["state_path"],
            "verify_tls": data["verify_tls"],
            "only_success": data["only_success"],
            "auto_upload": data["auto_upload"],
            "schedule_times": parse_schedule_times(data["schedule_times"]),
        })
        cfg.validate()
        return cfg

    def preview_config(self) -> None:
        try:
            cfg = self.build_runtime_config()
        except Exception as exc:
            messagebox.showerror("校验失败", str(exc))
            return
        self.log(f"配置校验通过: db={cfg.db_path} base_url={cfg.base_url}")
        self.set_status("配置校验通过")

    def enable_autostart(self) -> None:
        try:
            self.save_config()
            msg = install_autostart(config_path=str(self.gui_config_path), start_hidden=bool(self.fields["start_hidden"].get()))
            self.log(msg)
            self._refresh_autostart_status()
            messagebox.showinfo("开机自启", msg)
        except Exception as exc:
            messagebox.showerror("开机自启安装失败", str(exc))

    def disable_autostart(self) -> None:
        try:
            msg = uninstall_autostart()
            self.log(msg)
            self._refresh_autostart_status()
            messagebox.showinfo("开机自启", msg)
        except Exception as exc:
            messagebox.showerror("开机自启移除失败", str(exc))

    def _refresh_autostart_status(self) -> None:
        try:
            status = get_autostart_status()
            text = f"平台={status.platform} | 已安装={status.enabled} | 路径={status.path}"
        except Exception as exc:
            text = f"开机自启状态读取失败: {exc}"
        self.autostart_var.set(text)

    def _start_scheduler(self) -> None:
        self.scheduler = BackgroundScheduler(
            config_path=str(self.gui_config_path),
            logger=self.log,
            status_callback=self._on_schedule_update,
        )
        self.scheduler.start()

    def _restart_scheduler(self) -> None:
        if self.scheduler:
            self.scheduler.stop()
        self._start_scheduler()

    def _on_schedule_update(self, info: ScheduleInfo) -> None:
        message = info.message or "调度器已更新"
        self.root.after(0, lambda: self.scheduler_var.set(message))

    def trigger_upload(self) -> None:
        if not self.scheduler:
            self._start_scheduler()

        def worker() -> None:
            try:
                self.scheduler.run_once(source="手动上传")
                self.set_status("手动上传已触发")
            except Sub2ApiError as exc:
                self.log(f"上传失败: {exc}")
                self.set_status("上传失败")
            except Exception as exc:
                self.log(f"运行出错: {exc}")
                self.set_status("运行出错")

        threading.Thread(target=worker, daemon=True).start()

    def minimize_to_background(self) -> None:
        self.root.withdraw()
        self.set_status("已最小化到后台")
        self._ensure_tray()

    def restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.set_status("窗口已恢复")

    def _ensure_tray(self) -> None:
        if self.tray_thread and self.tray_thread.is_alive():
            return

        def runner() -> None:
            try:
                import pystray
                from PIL import Image, ImageDraw
            except Exception as exc:
                self.log(f"系统托盘不可用，请安装 pystray 和 Pillow: {exc}")
                self.root.after(0, self.root.deiconify)
                return

            def create_image():
                image = Image.new("RGB", (64, 64), (35, 110, 180))
                draw = ImageDraw.Draw(image)
                draw.rectangle((8, 8, 56, 56), outline=(255, 255, 255), width=3)
                draw.text((18, 18), "CC", fill=(255, 255, 255))
                return image

            def on_open(icon, _item):
                self.root.after(0, self.restore_from_tray)

            def on_upload(icon, _item):
                self.trigger_upload()

            def on_exit(icon, _item):
                icon.stop()
                self.tray_icon = None
                self.root.after(0, self._real_close)

            menu = pystray.Menu(
                pystray.MenuItem("打开窗口", on_open),
                pystray.MenuItem("立即上传", on_upload),
                pystray.MenuItem("退出", on_exit),
            )
            self.tray_icon = pystray.Icon("cc-usage-reporter", create_image(), "CC Usage Reporter", menu)
            self.tray_icon.run()

        self.tray_thread = threading.Thread(target=runner, daemon=True)
        self.tray_thread.start()

    def set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def log(self, text: str) -> None:
        self.log_queue.put(f"[{Path.cwd()}] {text}" if text.startswith("[") else f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}")

    def _drain_logs(self) -> None:
        lines: list[str] = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if lines:
            self.log_text.configure(state=tk.NORMAL)
            for line in lines:
                self.log_text.insert(tk.END, line + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.root.after(300, self._drain_logs)

    def on_close(self) -> None:
        if bool(self.fields["minimize_to_tray"].get()):
            self.minimize_to_background()
            return
        self._real_close()

    def _real_close(self) -> None:
        if self.scheduler:
            self.scheduler.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()


def launch_gui(*, config_path: str | None = None, start_hidden: bool = False) -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"GUI 启动失败: {exc}")
        print("当前环境缺少图形界面；请在 Windows / Linux / macOS 的桌面环境中运行该程序。")
        return 1
    ttk.Style(root).theme_use("clam")
    ReporterApp(root, config_path=config_path, start_hidden=start_hidden)
    root.mainloop()
    return 0

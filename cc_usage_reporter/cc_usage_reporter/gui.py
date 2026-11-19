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
from .deps import check_tray_dependencies
from .reporter import collect_buckets
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
        # macOS 笔记本常见 1440x900（扣掉菜单栏/Dock 只剩 800 出头），
        # 直接把 860 高的窗口摆上去会顶出屏幕，所以先按屏幕收缩。
        width, height = self._fit_to_screen(940, 860)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(840, width), min(560, height))

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.gui_config_path = Path(config_path).expanduser() if config_path else DEFAULT_GUI_CONFIG_PATH
        self.fields: dict[str, tk.Variable] = {}
        self.scheduler: BackgroundScheduler | None = None
        self.tray_icon = None
        self.tray_thread: threading.Thread | None = None
        self._tray_available: bool | None = None
        self._closing = False

        self._build_ui()
        self._load_gui_config()
        self._refresh_autostart_status()
        self._start_scheduler()
        self.root.after(300, self._drain_logs)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if start_hidden:
            self.root.after(50, self.minimize_to_background)

    def _fit_to_screen(self, width: int, height: int) -> tuple[int, int]:
        """把期望的窗口尺寸收进当前屏幕，避免在小屏/笔记本上顶出可视区。"""
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
        except tk.TclError:
            return width, height
        if screen_w <= 1 or screen_h <= 1:
            return width, height
        width = min(width, max(760, screen_w - 60))
        height = min(height, max(520, screen_h - 120))
        return width, height

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        # 用 grid 而不是 pack：第 0 行（配置区）吃掉所有剩余高度，
        # 第 1 行（日志）只占自己的固定行高，永远不会被挤掉。
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # 上方配置区放进可滚动容器：窗口再小也能滚动到每一个控件
        host = ttk.Frame(main)
        host.grid(row=0, column=0, sticky="nsew")
        self._scroll_host = host

        self._canvas = tk.Canvas(host, borderwidth=0, highlightthickness=0, height=220)
        self._vbar = ttk.Scrollbar(host, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vbar.set)
        self._vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(self._canvas)
        self._scroll_window = self._canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", self._on_scroll_content)
        self._canvas.bind("<Configure>", self._on_scroll_canvas)
        self._bind_scroll_wheel()

        # 运行日志固定在底部（最后一行，weight=0）
        log_frame = ttk.LabelFrame(main, text="运行日志", padding=8)
        log_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._log_frame = log_frame
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(inner, text="配置", padding=12)
        form.pack(fill=tk.X)

        self._add_entry(form, "db_path", "数据库路径", row=0, width=72)
        ttk.Button(form, text="选择...", command=self._pick_db).grid(row=0, column=2, padx=(8, 0), sticky="w")

        self._add_entry(form, "base_url", "上报地址", row=1, width=72)
        self._add_entry(form, "token", "Token", row=2, width=72, show="*")
        self._add_entry(form, "email", "邮箱", row=3, width=32)
        self._add_entry(form, "username", "用户名", row=3, column=2, width=24)
        self._add_entry(form, "source", "来源标识", row=4, width=32)
        self._add_entry(form, "state_path", "状态文件", row=5, width=72)
        ttk.Button(form, text="选择...", command=self._pick_state).grid(row=5, column=2, padx=(8, 0), sticky="w")

        self.fields["verify_tls"] = tk.BooleanVar(value=True)
        self.fields["only_success"] = tk.BooleanVar(value=True)
        self.fields["auto_upload"] = tk.BooleanVar(value=True)
        self.fields["schedule_times"] = tk.StringVar(value=", ".join(DEFAULT_SCHEDULE_TIMES))
        self.fields["start_hidden"] = tk.BooleanVar(value=True)
        self.fields["minimize_to_tray"] = tk.BooleanVar(value=True)

        opts = ttk.Frame(form)
        opts.grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Checkbutton(opts, text="校验 TLS 证书", variable=self.fields["verify_tls"]).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(opts, text="仅统计成功请求", variable=self.fields["only_success"]).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(opts, text="启动后后台定时上传", variable=self.fields["auto_upload"], command=self._restart_scheduler).pack(side=tk.LEFT)

        schedule = ttk.Frame(form)
        schedule.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Label(schedule, text="定时上传时间").pack(side=tk.LEFT)
        ttk.Entry(schedule, textvariable=self.fields["schedule_times"], width=30).pack(side=tk.LEFT, padx=(8, 8))
        ttk.Label(schedule, text="多个时间用英文逗号分隔，例如 10:00,18:00").pack(side=tk.LEFT)

        mag = ttk.LabelFrame(inner, text="magpie 数据采集（第二个来源，与 CC Switch 并列上报）", padding=10)
        mag.pack(fill=tk.X, pady=(12, 0))

        self.fields["magpie_enabled"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(mag, text="启用 magpie 用量采集", variable=self.fields["magpie_enabled"]).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self._add_entry(mag, "magpie_api_url", "网关地址", row=1, width=38)
        ttk.Label(mag, text="magpie 界面底部「网关」后的地址，走它可拿到 magpie 算好的金额",
                  foreground="#777").grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0))

        self._add_entry(mag, "magpie_path", "usage.jsonl", row=2, width=56)
        ttk.Button(mag, text="选择...", command=self._pick_magpie).grid(row=2, column=2, padx=(8, 0), sticky="w")
        ttk.Label(mag, text="API 不可用时回退到此文件；便携版在 magpie.exe 同级 data/ 下",
                  foreground="#777").grid(row=3, column=2, columnspan=2, sticky="w", padx=(8, 0))

        self._add_entry(mag, "magpie_app_type", "app_type", row=4, width=14)
        self._add_entry(mag, "magpie_agents", "仅统计 agent", row=4, column=2, width=22)
        self._add_entry(mag, "magpie_since_days", "采集最近(天)，0=全部", row=5, width=8)
        ttk.Label(mag, text="agent 留空表示全部；多个用英文逗号分隔，如 claude,codex,dsh",
                  foreground="#777").grid(row=5, column=2, columnspan=2, sticky="w", padx=(8, 0))
        for i in range(4):
            mag.columnconfigure(i, weight=1 if i in {1, 3} else 0)

        auto = ttk.LabelFrame(inner, text="开机自启 / 托盘", padding=10)
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

        # 操作按钮与状态放在可滚动区之外：无论窗口多小，「保存配置 / 立即上传 /
        # 测试读取」始终可见，不需要先滚动去找。
        btns = ttk.Frame(main)
        btns.grid(row=1, column=0, sticky="ew", pady=(12, 6))
        ttk.Button(btns, text="保存配置", command=self.save_config).pack(side=tk.LEFT)
        ttk.Button(btns, text="立即上传", command=self.trigger_upload).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="测试读取", command=self.preview_config).pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        self.scheduler_var = tk.StringVar(value="定时上传未启用")
        status = ttk.Frame(main)
        status.grid(row=2, column=0, sticky="ew")
        ttk.Label(status, textvariable=self.status_var, foreground="#0a5").pack(anchor="w")
        ttk.Label(status, textvariable=self.scheduler_var, foreground="#555").pack(anchor="w", pady=(4, 0))

        for i in range(4):
            form.columnconfigure(i, weight=1 if i in {1, 3} else 0)

        self.root.after(60, self._sync_scrollregion)

    # ------------------------------------------------------------------ #
    # 配置区滚动
    # ------------------------------------------------------------------ #

    def _on_scroll_content(self, _event=None) -> None:
        """内容尺寸变化时刷新可滚动范围。"""
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_scroll_canvas(self, event) -> None:
        """让内层容器始终和可视宽度一致（否则会出现横向留白）。"""
        try:
            self._canvas.itemconfigure(self._scroll_window, width=event.width)
        except tk.TclError:
            pass

    def _sync_scrollregion(self) -> None:
        self._on_scroll_content()
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    def _widget_in_log(self, widget) -> bool:
        """判断事件是否发生在日志框内部（那里应由 ScrolledText 自己滚）。"""
        node = widget
        while node is not None:
            if node is self.log_text:
                return True
            node = getattr(node, "master", None)
        return False

    def _bind_scroll_wheel(self) -> None:
        def wheel(event):
            if self._widget_in_log(getattr(event, "widget", None)):
                return None
            delta = getattr(event, "delta", 0)
            if delta:
                step = -1 if delta > 0 else 1
                if abs(delta) >= 120:
                    step = int(-delta / 120) or step
            else:
                num = getattr(event, "num", None)
                if num == 4:
                    step = -1
                elif num == 5:
                    step = 1
                else:
                    return None
            try:
                self._canvas.yview_scroll(step, "units")
            except tk.TclError:
                return None
            return "break"

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.root.bind_all(sequence, wheel, add="+")
            except tk.TclError:
                pass

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

    def _pick_magpie(self) -> None:
        """选择 magpie 的 usage.jsonl。

        便携版 magpie 把它放在 exe 同级的 ``data/`` 里（例如 D:\\apps\\magpie\\data\\usage.jsonl）；
        安装版在 ``%APPDATA%\\magpie\\``（macOS / Linux 在 ``~/.config/magpie/``）。
        """
        path = filedialog.askopenfilename(
            title="选择 magpie 的 usage.jsonl（便携版：magpie.exe 同级 data 目录）",
            filetypes=[("magpie usage 日志", "usage.jsonl"), ("JSON Lines", "*.jsonl"), ("All Files", "*.*")],
        )
        if not path:
            picked_dir = filedialog.askdirectory(title="或直接选择 usage.jsonl 所在目录")
            path = f"{picked_dir}/usage.jsonl" if picked_dir else ""
        if path:
            self.fields["magpie_path"].set(path)

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
            "source": self.fields["source"].get().strip() or "cc-switch",
            "state_path": self.fields["state_path"].get().strip(),
            "verify_tls": bool(self.fields["verify_tls"].get()),
            "only_success": bool(self.fields["only_success"].get()),
            "auto_upload": bool(self.fields["auto_upload"].get()),
            "schedule_times": self.fields["schedule_times"].get().strip(),
            "start_hidden": bool(self.fields["start_hidden"].get()),
            "minimize_to_tray": bool(self.fields["minimize_to_tray"].get()),
            "magpie_enabled": bool(self.fields["magpie_enabled"].get()),
            "magpie_api_url": self.fields["magpie_api_url"].get().strip(),
            "magpie_path": self.fields["magpie_path"].get().strip(),
            "magpie_app_type": self.fields["magpie_app_type"].get().strip() or "magpie",
            "magpie_agents": self.fields["magpie_agents"].get().strip(),
            "magpie_since_days": self.fields["magpie_since_days"].get().strip() or "30",
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
            try:
                if int(str(data["magpie_since_days"]).strip() or "30") < 0:
                    raise ValueError
            except ValueError:
                raise ValueError("「采集最近(天)」必须填非负整数，0 表示全部历史") from None
            if data["magpie_enabled"] and not data["magpie_api_url"] and not data["magpie_path"]:
                raise ValueError("启用 magpie 采集后，请填写网关地址或 usage.jsonl 路径（至少一个）")
            if not data["source"]:
                raise ValueError("请填写来源标识")
            parse_schedule_times(data["schedule_times"])
        return data

    def _config_payload(self, data: dict) -> dict:
        """把表单数据整理成写入配置文件的 JSON。"""
        return {
            "base_url": data["base_url"],
            "token": data["token"],
            "email": data["email"],
            "username": data["username"],
            "source": data["source"],
            "db_path": data["db_path"],
            "state_path": data["state_path"],
            "verify_tls": data["verify_tls"],
            "only_success": data["only_success"],
            "auto_upload": data["auto_upload"],
            "schedule_times": parse_schedule_times(data["schedule_times"]),
            "start_hidden": data["start_hidden"],
            "minimize_to_tray": data["minimize_to_tray"],
            "cc_switch_enabled": True,
            "magpie_enabled": data["magpie_enabled"],
            "magpie_api_url": data["magpie_api_url"],
            "magpie_path": data["magpie_path"],
            "magpie_app_type": data["magpie_app_type"],
            "magpie_agents": [s.strip() for s in str(data["magpie_agents"]).split(",") if s.strip()],
            "magpie_since_days": int(str(data["magpie_since_days"]).strip() or 30),
            "app_types": ["claude", "codex"],
            "report_path": "/api/v1/usage/report",
        }

    def save_config(self, *, auto: bool = False) -> bool:
        """保存配置；返回是否保存成功。

        auto=True 表示由「立即上传 / 安装开机自启」等动作自动触发：校验失败时
        仍然弹窗告知，但不会继续后面的动作。
        """
        try:
            data = self.collect_form_data(validate=True)
        except Exception as exc:
            messagebox.showerror("配置校验失败" if auto else "保存失败", str(exc))
            self.log(f"{'自动保存' if auto else '保存'}配置失败: {exc}")
            self.set_status("配置有误，未保存")
            return False

        payload = self._config_payload(data)
        self.gui_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.gui_config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(("已自动保存配置: " if auto else "配置已保存: ") + str(self.gui_config_path))
        self.set_status("配置已保存")
        self._refresh_autostart_status()
        self._restart_scheduler()
        return True

    def _pending_config_changes(self) -> bool:
        """界面上的值是否与已保存的配置文件不一致（文件不存在也算不一致）。

        只比对会写入的键，避免因为文件里有额外键（password / timeout …）误判。
        """
        if not self.gui_config_path.exists():
            return True
        try:
            saved = json.loads(self.gui_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        if not isinstance(saved, dict):
            return True
        payload = self._config_payload(self.collect_form_data(validate=True))
        return any(payload.get(key) != saved.get(key) for key in payload)

    def build_runtime_config(self) -> Config:
        data = self.collect_form_data(validate=True)
        cfg = load_config(str(self.gui_config_path) if self.gui_config_path.exists() else None, overrides={
            "base_url": data["base_url"],
            "token": data["token"],
            "email": data["email"],
            "username": data["username"],
            "source": data["source"],
            "db_path": data["db_path"],
            "state_path": data["state_path"],
            "verify_tls": data["verify_tls"],
            "only_success": data["only_success"],
            "auto_upload": data["auto_upload"],
            "schedule_times": parse_schedule_times(data["schedule_times"]),
            "magpie_enabled": data["magpie_enabled"],
            "magpie_api_url": data["magpie_api_url"],
            "magpie_path": data["magpie_path"],
            "magpie_app_type": data["magpie_app_type"],
            "magpie_agents": data["magpie_agents"],
            "magpie_since_days": data["magpie_since_days"],
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
        if cfg.magpie_enabled:
            self.log(
                f"magpie: api={cfg.magpie_api_url or '(未填)'} "
                f"path={cfg.magpie_path or '(自动探测)'} app_type={cfg.magpie_app_type} "
                f"最近={cfg.magpie_since_days}天 agent={cfg.magpie_agents or '全部'}"
            )
        self.set_status("配置校验通过，正在读取...")

        def worker() -> None:
            try:
                buckets, cc_count, magpie_count = collect_buckets(cfg, logger=self.log)
                total_cost = sum(b.total_cost_usd for b in buckets)
                total_in = sum(b.input_tokens for b in buckets)
                total_out = sum(b.output_tokens for b in buckets)
                self.log(
                    f"读取完成: 桶={len(buckets)} (CC Switch={cc_count}, magpie={magpie_count}) "
                    f"input={total_in:,} output={total_out:,} cost=${total_cost:.4f}"
                )
                self.set_status("读取完成")
            except Exception as exc:
                self.log(f"读取失败: {exc}")
                self.set_status("读取失败")

        threading.Thread(target=worker, daemon=True).start()

    def enable_autostart(self) -> None:
        try:
            # 开机自启会引用配置文件，先确保配置真的写进去了
            if not self.save_config(auto=True):
                return
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

    def _ui_call(self, fn) -> None:
        """从后台线程安全地更新界面；窗口已销毁时静默忽略（关闭瞬间的竞态）。"""
        try:
            self.root.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    def _on_schedule_update(self, info: ScheduleInfo) -> None:
        message = info.message or "调度器已更新"
        self._ui_call(lambda: self.scheduler_var.set(message))

    def trigger_upload(self) -> None:
        """立即上传。

        上传读的是**配置文件**（scheduler.run_once 会重新 load_config），所以
        用户改完界面却没点「保存配置」时，用的是旧值甚至默认值，直接上传就会
        失败。这里先校验并同步一次配置，再发起上传。
        """
        try:
            changed = self._pending_config_changes()
        except Exception as exc:
            messagebox.showerror("配置校验失败", str(exc))
            self.log(f"上传前配置校验失败，已取消上传: {exc}")
            self.set_status("配置有误，未上传")
            return

        if changed:
            self.log("检测到界面上有未保存的配置，先自动保存再上传")
            if not self.save_config(auto=True):
                self.log("配置未能保存，已取消上传")
                return

        if not self.scheduler:
            self._start_scheduler()

        self.set_status("正在上传...")

        def worker() -> None:
            try:
                summary = self.scheduler.run_once(source="手动上传")
                if summary is None:
                    # 失败原因 run_once 已经写进运行日志
                    self.set_status("上传未完成，请看运行日志")
                else:
                    self.set_status(f"上传完成：发送 {summary.sent_buckets} 个桶")
            except Sub2ApiError as exc:
                self.log(f"上传失败: {exc}")
                if getattr(exc, "body", ""):
                    self.log(f"服务端响应: {exc.body[:300]}")
                self.set_status("上传失败")
            except Exception as exc:
                self.log(f"运行出错: {exc}")
                self.set_status("运行出错")

        threading.Thread(target=worker, daemon=True).start()

    def minimize_to_background(self) -> None:
        if not self._can_use_tray():
            messagebox.showwarning("系统托盘不可用", "当前环境缺少 pystray 或 Pillow，无法最小化到系统托盘。")
            self.set_status("系统托盘不可用")
            return
        self.root.withdraw()
        self.set_status("已最小化到后台")
        self._ensure_tray()

    def restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.set_status("窗口已恢复")

    def _can_use_tray(self) -> bool:
        if self._tray_available is None:
            result = check_tray_dependencies()
            self._tray_available = result.ok
            if not result.ok:
                self.log("系统托盘不可用，将回退为正常关闭窗口")
                for message in result.messages:
                    self.log(message)
        return self._tray_available

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
        self._ui_call(lambda: self.status_var.set(text))

    def log(self, text: str) -> None:
        self.log_queue.put(f"[{Path.cwd()}] {text}" if text.startswith("[") else f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}")

    def _drain_logs(self) -> None:
        if self._closing:
            return
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
        try:
            self.root.after(300, self._drain_logs)
        except (RuntimeError, tk.TclError):
            pass

    def on_close(self) -> None:
        if bool(self.fields["minimize_to_tray"].get()) and self._can_use_tray():
            self.minimize_to_background()
            return
        self._real_close()

    def _real_close(self) -> None:
        self._closing = True
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

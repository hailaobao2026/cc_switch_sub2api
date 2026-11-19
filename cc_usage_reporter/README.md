# cc_usage_reporter — CC Switch / magpie 用量上报客户端

把本机 **CC Switch** 数据库与 **magpie** 网关记录的模型调用用量，按 **天 × 模型** 聚合后上报到本项目的 **sidecar** 服务，再由 sidecar 写入 sub2api 使用的 PostgreSQL 外部用量表。

## 工作原理

```text
【数据源 1：CC Switch】
Windows: %APPDATA%\cc-switch\cc-switch.db
Linux:   ~/.config/cc-switch/cc-switch.db  或 ~/.cc-switch/cc-switch.db
macOS:   ~/Library/Application Support/cc-switch/cc-switch.db
    └─ proxy_request_logs (每次请求一行)

【数据源 2：magpie】（--magpie 打开，默认关闭）
    GET http://127.0.0.1:3425/v1/magpie/usage/requests   ← 首选，行内带 magpie 算好的 cost
    或 magpie 的 usage.jsonl（便携版在 magpie.exe 同级 data/）← 回退，无金额
            │  读取 + 按 UTC 天×模型 聚合；magpie 桶的 app_type 固定为 magpie
            ▼
   天×模型 用量桶 (DailyModelUsage)
            │  signature 去重(仅发送新增/变化的桶)
            ▼
   POST /api/v1/usage/report  (Bearer token)
            ▼
   sidecar → external_usage_daily (按唯一键 upsert，幂等)
```

- 只读打开数据库（`mode=ro&immutable=1`），不影响正在运行的 CC Switch。
- 客户端用本地状态文件记录每个桶上次上报的数值指纹，未变化不重发。
- 提供 `token` 时会直接使用 Bearer token 上报，适合 sidecar；没有 `token` 时仍保留旧的登录模式。
- 零第三方依赖：仅用 Python 标准库（`sqlite3` / `urllib` / `json`）。

## 安装

无需安装依赖，Python ≥ 3.10 即可。可选安装为命令：

```bash
cd cc_usage_reporter
pip install -e .
```

## 快速开始

### 1) 本地预览

```bash
python -m cc_usage_reporter preview
python -m cc_usage_reporter show
```

### 2) 配置 sidecar 上报

先启动 `../sidecar`，然后复制客户端示例配置：

```powershell
Copy-Item config.sidecar.example.json config.sidecar.json
```

重点配置：

```json
{
  "base_url": "http://127.0.0.1:8788",
  "token": "与 sidecar report_token 一致的长随机 token",
  "username": "alice",
  "source": "cc-switch",
  "db_path": "/home/alice/.config/cc-switch/cc-switch.db"
}
```

### 3) 演练与正式上报

```bash
python -m cc_usage_reporter run --config config.sidecar.json --dry-run
python -m cc_usage_reporter run --config config.sidecar.json
```

## 配置项

优先级：命令行 > 环境变量 > 配置文件 > 默认值。

| 配置 | 环境变量 | 说明 |
|---|---|---|
| `base_url` | `SUB2API_BASE_URL` | sidecar 地址，如 `http://127.0.0.1:8788` |
| `username` | `SUB2API_USERNAME` | 关联的 sub2api 用户名 |
| `email` | `SUB2API_EMAIL` | 关联邮箱；sidecar 可用它解析用户 |
| `password` | `SUB2API_PASSWORD` | 旧登录模式使用；sidecar 模式通常留空 |
| `token` | `SUB2API_TOKEN` | Bearer token；sidecar 模式必须与 `report_token` 一致 |
| `source` | `CC_USAGE_SOURCE` | 上报来源，默认 `cc-switch`；多电脑同用户建议每台配置不同值 |
| `report_path` | `SUB2API_REPORT_PATH` | 默认 `/api/v1/usage/report` |
| `login_path` | `SUB2API_LOGIN_PATH` | 旧登录模式使用，默认 `/api/v1/auth/login` |
| `db_path` | `CC_SWITCH_DB_PATH` | 默认按系统自动选择：Windows `%APPDATA%\cc-switch`；Linux `~/.config/cc-switch`；macOS `~/Library/Application Support/cc-switch`；同时兼容旧 `~/.cc-switch` |
| `state_path` | `CC_SWITCH_STATE_PATH` | 上报状态文件，默认与 `db_path` 同目录 |
| `app_types` | — | 默认 `['claude', 'codex']` |
| `only_success` | — | 仅上报 2xx 请求（`--all` 可包含失败） |
| `verify_tls` | `SUB2API_VERIFY_TLS` | HTTPS 自签名证书可设 false / `--no-verify-tls` |
| `cc_switch_enabled` | `CC_SWITCH_ENABLED` | 是否采集 CC Switch，默认 true（`--no-cc-switch` 关闭） |
| `magpie_enabled` | `MAGPIE_ENABLED` | 是否采集 magpie，默认 false（`--magpie` 打开） |
| `magpie_api_url` | `MAGPIE_API_URL` | magpie 网关地址，默认 `http://127.0.0.1:3425` |
| `magpie_path` | `MAGPIE_USAGE_PATH` | magpie `usage.jsonl` 或其目录；只在 API 不可用时回退使用 |
| `magpie_app_type` | `MAGPIE_APP_TYPE` | magpie 桶的 `app_type`，默认 `magpie` |
| `magpie_agents` | `MAGPIE_AGENTS` | 只统计这些 agent（逗号分隔），空=全部 |
| `magpie_since_days` | `MAGPIE_SINCE_DAYS` | 只拉最近 N 天，默认 30；0=全部历史 |
| `magpie_include_logged` | `MAGPIE_INCLUDE_LOGGED` | 是否包含 magpie 从 agent 会话文件补读的调用，默认 false |
| `magpie_prefer_api` | `MAGPIE_PREFER_API` | 是否优先走 HTTP API（有金额），默认 true |

## magpie 用量采集

magpie 不用数据库，网关每服务一次调用就往 `usage.jsonl` 追加一行 JSON。打开 `--magpie` 后，客户端会额外采集它，并和 CC Switch 的桶一起上报：

- **金额口径**：优先走 magpie 的 HTTP API，成立原因是它把每行的 `cost` 用价格表算好并返回；API 不可用时回退解析 `usage.jsonl`，此时记录里没有金额，`total_cost_usd` 记 0，日志会提示。
- **app_type 隔离**：magpie 桶的 `app_type` 固定为 `magpie`。服务端按 `(user_id, source, usage_date, app_type, model, requested_model)` upsert，所以与既有 `claude` / `codex` 行互不覆盖，**默认 `source=cc-switch` 时 sidecar 无需改配置**。
- **默认排除 `source=log` 的行**：`/requests` 还会返回 magpie 从 Claude Code / Codex 会话文件里补读的历史调用（本机历史上约 2.6 万行），它们很可能与 CC Switch 上报的桶重复计数，默认跳过；需要时用 `--magpie-include-logged` 打开。`source=search` 的搜索调用不产生模型 token，永远排除。
- **日期口径**：与 CC Switch 一致，按 **UTC** 取 `YYYY-MM-DD`。

magpie 的 `usage.jsonl` 位置。注意 magpie 的 `internal/appdir.installed()` 在**所有平台（含 macOS）都用 XDG 风格**，macOS 上并不是 `~/Library/Application Support`：

| 场景 | 路径 |
|---|---|
| 便携版（Windows） | `<magpie.exe 同级>\data\usage.jsonl`，例如 `D:\apps\magpie\data\usage.jsonl` |
| 便携版（macOS） | `<Magpie.app 同级>/data/usage.jsonl` |
| 安装版（Windows / macOS / Linux） | `~/.config/magpie/usage.jsonl`（Windows 为 `%USERPROFILE%\.config\magpie\usage.jsonl`） |
| 设了 `XDG_CONFIG_HOME` | `$XDG_CONFIG_HOME/magpie/usage.jsonl` |

便携版的 `data` 目录在 **magpie 程序自己旁边**（另一个程序的位置），本程序探测不到，请用界面上的「选择...」手动指定；只有 magpie 与本程序恰好装在同一目录时自动探测才命中。

只想上报 magpie、或者想把 magpie 单独归到一个来源：

```powershell
# 两个来源一起上报（默认）
python -m cc_usage_reporter run --config config.sidecar.json --magpie

# 只报 magpie，单独用一个来源（sidecar 的 allowed_sources 需含 magpie）
python -m cc_usage_reporter run --config config.sidecar.json --source magpie --magpie --no-cc-switch
```

## 多电脑同用户上报

服务端按 `(user_id, source, usage_date, app_type, model, requested_model)` 做幂等 upsert。

如果多台电脑使用同一个 sub2api 用户，并且都使用默认 `source = cc-switch`，同一天同模型的桶会写到同一行，后上传的电脑会覆盖前一台电脑的累计值。

要让多台电脑的数据叠加统计，请给每台电脑配置不同 `source`：

```json
{
  "source": "cc-switch-pc-a"
}
```

也可以用命令行或环境变量覆盖：

```bash
python -m cc_usage_reporter run --config config.sidecar.json --source cc-switch-laptop
CC_USAGE_SOURCE=cc-switch-laptop python -m cc_usage_reporter run --config config.sidecar.json
```

同时需要在 sidecar 的 `allowed_sources` 中加入这些来源，例如：

```json
{
  "allowed_sources": ["cc-switch", "cc-switch-pc-a", "cc-switch-laptop"]
}
```



## 跨平台说明

默认会优先查找这些目录：

- **Windows**
  - `%APPDATA%\cc-switch\cc-switch.db`
  - `%APPDATA%\cc-switch\usage_reporter_state.json`
- **Linux**
  - `$XDG_CONFIG_HOME/cc-switch/cc-switch.db`
  - `~/.config/cc-switch/cc-switch.db`
  - 兼容旧路径：`~/.cc-switch/cc-switch.db`
- **macOS**
  - `~/Library/Application Support/cc-switch/cc-switch.db`
  - 兼容路径：`~/.config/cc-switch/cc-switch.db` / `~/.cc-switch/cc-switch.db`

如果你的数据库不在默认位置，仍可手动指定：

```bash
python -m cc_usage_reporter run --db-path "/custom/path/cc-switch.db"
```

## 命令

| 命令 | 作用 |
|---|---|
| `preview` | 本地聚合概览（前 20 桶），不联网 |
| `show` | 打印全部聚合桶，不联网 |
| `run` | 上报变化的桶 |
| `run --dry-run` | 演练，打印将要上报的桶但不发送 |
| `gui` | 启动桌面版，支持保存配置、按钮上传、后台定时上传 |
| `daemon` | 真后台常驻模式，无 GUI，按定时计划自动上传 |
| `tray` | 仅系统托盘模式，适合桌面后台运行 |
| `autostart-install` | 安装当前系统的开机自启（默认启动 GUI） |
| `autostart-uninstall` | 移除开机自启 |
| `autostart-status` | 查看开机自启状态 |

常用参数：`--config` `--base-url` `--username` `--email` `--password` `--token` `--source` `--db-path` `--state-path` `--all` `--no-verify-tls` `--no-incremental`。

magpie 相关参数：

| 参数 | 作用 |
|---|---|
| `--magpie` / `--no-magpie` | 打开 / 关闭 magpie 采集（默认关闭） |
| `--magpie-api-url` | magpie 网关地址，默认 `http://127.0.0.1:3425` |
| `--magpie-path` | `usage.jsonl` 路径或所在目录（API 不可用时回退） |
| `--magpie-app-type` | magpie 桶的 `app_type`，默认 `magpie` |
| `--magpie-agents` | 逗号分隔的 agent 过滤，如 `claude,codex,dsh`；空=全部 |
| `--magpie-since-days` | 只采集最近 N 天；`0`=全部历史 |
| `--magpie-include-logged` | 包含 magpie 从会话文件补读的调用（默认排除） |
| `--no-cc-switch` | 不采集 CC Switch，只报 magpie |

## 打包与分发（Windows / Linux / macOS）

### Windows

CLI 版：

```powershell
pyinstaller .\cc-usage-reporter.spec
```

## GitHub Releases 自动发布

仓库已增加 GitHub Actions 发布工作流：

- 标签格式：`cc-usage-reporter-v1.0.0`
- 推送标签后会分别在 `Windows`、`Linux`、`macOS` 上构建
- 构建完成后会自动创建 GitHub Release 并上传 3 个平台附件

发布命令：

```bash
git tag cc-usage-reporter-v1.0.0
git push origin cc-usage-reporter-v1.0.0
```

Release 中的附件名称示例：

- `cc-usage-reporter-v1.0.0-windows.zip`
- `cc-usage-reporter-v1.0.0-linux.tar.gz`
- `cc-usage-reporter-v1.0.0-macos.tar.gz`

GUI 版：

```powershell
pyinstaller .\cc-usage-reporter-gui.spec
```

产物通常位于：

```powershell
.\dist\cc-usage-reporter.exe
.\dist\cc-usage-reporter-gui.exe
```

### Linux

建议直接分发源码或用 PyInstaller 打包：

```bash
python3 -m pip install pyinstaller
pyinstaller cc-usage-reporter.spec
pyinstaller cc-usage-reporter-gui.spec
```

注意：

- GUI 版依赖桌面环境与 Tk。
- 若目标机器没有图形界面，仍可使用 CLI 版。

### macOS

macOS 需要区分 **Apple Silicon（arm64）** 与 **Intel（x86_64）**，PyInstaller 不能交叉编译：产物架构由「跑打包的那个 Python」决定。用打包脚本可以显式指定：

```bash
# 本机架构
bash packaging/macos/build.sh

# 显式指定（可写 arm64 / x86_64 / universal2）
bash packaging/macos/build.sh arm64
bash packaging/macos/build.sh x86_64
bash packaging/macos/build.sh universal2      # 一个二进制同时含两种架构
TARGET_ARCH=arm64 bash packaging/macos/build.sh   # CI 里用环境变量
```

脚本会做三件事：确认当前 Python 能否产出目标架构（不对就直接报错，不给你一份架构错误的包）、跑 PyInstaller、最后用 `lipo -archs` 自检真实架构。

| 目标 | 需要什么 Python | 产物 |
|---|---|---|
| `arm64` | arm64 原生 Python（Apple Silicon 上默认） | 仅 Apple Silicon 可运行 |
| `x86_64` | x86_64 Python（Intel 机器，或 arm64 上用 Rosetta 启动的 x86_64 Python） | Intel + Rosetta 下可运行 |
| `universal2` | python.org 的 universal2 版 Python | 两种机器都可运行 |

没有 universal2 版 Python 又想要一份包同时覆盖两种机器时，**分别在两台机器上各打一次**即可，发布目录会自动带上架构名：

```
release/cc-usage-reporter-v1.1.0-darwin-arm64-20261119-XXXXXX/
release/cc-usage-reporter-v1.1.0-darwin-x86_64-20261119-XXXXXX/
```

（`CC_USAGE_RELEASE_ARCH` 环境变量可以覆盖架构名，`manifest.json` 里也会记录 `"arch"`。）

其他注意：

- GUI 版需要系统自带或已安装的 Tk；PyInstaller 的 onefile 产物在 macOS 上是普通可执行文件（不带 `.app` 包），首次运行未签名应用时需要在“系统设置 → 隐私与安全性”里允许打开。
- 系统托盘（pystray）在 macOS 上要求图标运行在主线程，本项目的实现可能无法弹出托盘图标；不影响主窗口和上报功能。
- 窗口初始尺寸会按屏幕可用区域自动收缩（`gui._fit_to_screen`），1440×900 的 MacBook 不会顶出屏幕。

### 跨平台运行示例

Linux / macOS：

```bash
python3 -m cc_usage_reporter gui
python3 -m cc_usage_reporter run --config ./config.sidecar.json
```

Windows：

```powershell
python -m cc_usage_reporter gui
python -m cc_usage_reporter run --config .\config.sidecar.json
```

## 定时自动上报（Windows / Linux / macOS）

Windows 可用 `dev/register_task.ps1` 注册计划任务（例如 `10:00,18:00`）：

```powershell
powershell -ExecutionPolicy Bypass -File dev\register_task.ps1 -ConfigPath "F:\...\config.sidecar.json" -AtTimes "10:00,18:00"
```

Linux / macOS 则可用 `cron` / `launchd` / `systemd --user`，或直接保持 GUI 常驻。

也可以手动运行：

```powershell
python -m cc_usage_reporter run --config <path>
```

## 安全提示

- `config.sidecar.json` 含 token，请勿提交到版本库。
- `token` 建议使用 32 字符以上随机字符串，并与 sidecar 的 `report_token` 保持一致。
- sidecar 会按 `username` 或 `email` 解析 sub2api 用户；建议每台客户端只配置自己的用户标识。


## 桌面工具（GUI）

现在支持桌面版：

```bash
python -m cc_usage_reporter gui
```

打包后的 EXE 也可直接这样启动：

```powershell
.\cc-usage-reporter.exe gui
```

GUI 提供：

- 配置 `db_path`、`base_url`、`token`、`email`、`username`
- **「magpie 数据采集」分组**：勾选启用后，可填网关地址、选 `usage.jsonl`、设 `app_type`、agent 过滤和采集天数
- 保存配置到系统默认配置目录（Windows / Linux / macOS 自动识别）
- 点击“立即上传”手动上传；**上传前会先校验配置，界面上的改动若还没保存会自动保存一次再上传**（上传本身读的是配置文件，避免用旧配置上传失败）
- 点击“测试读取”会真的读一遍两个数据源并打印桶数与成本（后台线程，不卡界面）
- 勾选“启动后后台定时上传”后，程序驻留运行并按设定时间自动上传
- 默认定时：`10:00,18:00`

说明：

- 自动上传依赖程序保持运行；关闭窗口后定时任务也会停止。
- 如需开机自启，可再配合 Windows 启动项、Linux systemd/桌面自启动、或 macOS Login Items / launchd。
- 仍沿用原有状态文件去重逻辑，不会因定时运行而重复累计。


GUI 建议单独打包为无控制台窗口版本：

```powershell
pyinstaller .\cc-usage-reporter-gui.spec
```

如需保留命令行版，则继续使用：

```powershell
pyinstaller .\cc-usage-reporter.spec
```


## 开机自启（跨平台）

现在支持直接通过命令安装或移除开机自启：

```bash
python -m cc_usage_reporter autostart-install --config ./config.sidecar.json
python -m cc_usage_reporter autostart-status
python -m cc_usage_reporter autostart-uninstall
```

行为说明：

- **Windows**：写入启动菜单 `Startup` 目录
- **Linux**：写入 `~/.config/autostart/cc-usage-reporter.desktop`
- **macOS**：写入 `~/Library/LaunchAgents/com.local.cc-usage-reporter.plist`
- 默认会以 **GUI 模式** 启动
- 默认附带 `--start-hidden`，即开机后最小化启动并继续后台定时上传

如果你只想用纯命令行定时执行，也可以继续使用系统计划任务：

- Windows：任务计划程序 / `dev/register_task.ps1`
- Linux：`cron` / `systemd --user`
- macOS：`launchd`


## 真后台模式

现在支持两种后台模式：

### 1) daemon

适合无桌面环境或服务器：

```bash
python -m cc_usage_reporter daemon --config ./config.sidecar.json
```

特点：

- 不启动 GUI
- 常驻进程
- 按 `schedule_times` 定时上传
- 适合 systemd / launchd / supervisor

### 2) tray

适合桌面用户：

```bash
python -m cc_usage_reporter tray --config ./config.sidecar.json
```

特点：

- 仅显示系统托盘图标
- 可从托盘菜单触发“立即上传”
- 可从托盘退出程序
- 适合 Windows / Linux 桌面 / macOS

### GUI 最小化到托盘

GUI 现在支持：

- 关闭窗口时最小化到系统托盘
- 从托盘恢复窗口
- 从托盘立即上传
- 从托盘退出

> 注意：系统托盘功能依赖可选包 `pystray` 与 `Pillow`。


## 服务模板与安装脚本

项目已内置三端后台服务模板：

- Linux: `service_templates/linux/cc-usage-reporter.service`
- macOS: `service_templates/macos/com.local.cc-usage-reporter.plist`
- Windows: `service_templates/windows/cc-usage-reporter.xml`

对应安装脚本：

- Linux systemd user: `packaging/linux/install_systemd_user.sh`
- macOS launchd: `packaging/macos/install_launchd.sh`
- Windows WinSW: `packaging/windows/install_winsw.ps1`

### Linux 安装 systemd 用户服务

```bash
bash packaging/linux/install_systemd_user.sh ~/.config/cc-switch/usage_reporter.json
```

### macOS 安装 launchd

```bash
bash packaging/macos/install_launchd.sh "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
```

### Windows 安装 WinSW 服务

先准备 WinSW 可执行文件，再执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\install_winsw.ps1 -ConfigPath "$env:USERPROFILE\.config\cc-switch\usage_reporter.json"
```


## 打包脚本

项目已内置三端打包脚本：

- Windows: `packaging/windows/build.ps1`
- Linux: `packaging/linux/build.sh`
- macOS: `packaging/macos/build.sh`

示例：

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

### Linux

```bash
bash packaging/linux/build.sh
```

### macOS

```bash
bash packaging/macos/build.sh
```


## 自动下载 WinSW

Windows 服务安装脚本现在会自动尝试下载最新的 WinSW。

单独下载：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\download_winsw.ps1 -OutputPath .\WinSW-x64.exe
```

更常见的是直接执行安装脚本；它会在缺少 WinSW 时自动调用下载：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\install_winsw.ps1 -ConfigPath "$env:USERPROFILE\.config\cc-switch\usage_reporter.json"
```

## tray 依赖检查

可用下面命令检查系统托盘依赖是否齐全：

```bash
python -m cc_usage_reporter deps-check
```

若缺少依赖，安装：

```bash
pip install pystray Pillow
```


## 一键生成发布目录

可用下面命令把文档、示例配置、服务模板、打包脚本、以及 `dist/` 产物汇总到一个发布目录：

```bash
python -m cc_usage_reporter release-dir
python -m cc_usage_reporter release-pack
```

也可用平台脚本：

- Windows: `packaging/windows/release_dir.ps1`
- Linux: `packaging/linux/release_dir.sh`
- macOS: `packaging/macos/release_dir.sh`


## 标准化发布目录结构

`release-dir` 现在会生成如下结构：

```text
release/cc-usage-reporter-<platform>-<timestamp>/
  bin/
  dist/
  config/
  scripts/
  services/
  docs/
  metadata/
  install.sh / install.ps1
```

说明：

- `bin/`：规范化命名的可执行文件副本，例如 `cc-usage-reporter` / `cc-usage-reporter-gui`
- 若当前尚未 build，`bin/` 可能为空；先执行打包脚本再生成 release 目录即可
- `dist/`：原始打包产物
- `config/`：示例配置
- `scripts/`：安装、打包、辅助脚本
- `services/`：服务模板
- `docs/`：说明文档
- `metadata/`：依赖与 manifest

发布目录内还会自动生成：

- `install.sh`
- `install-linux.sh`
- `install-macos.sh`
- `install-windows.ps1`

用于指导或直接执行部署。


## 一键安装脚本

标准化发布目录中会自动生成：

- `install.sh`
- `install-linux.sh`
- `install-macos.sh`
- `install-windows.ps1`

用法示例：

### Linux

```bash
bash ./install-linux.sh
```

### macOS

```bash
bash ./install-macos.sh
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

这些脚本会优先调用发布目录中已经准备好的 `scripts/` 和 `services/` 内容。


## 统一一键发布脚本

项目已提供统一发布脚本：

- POSIX（Linux / macOS）：`packaging/common/publish.sh`
- Windows：`packaging/windows/publish.ps1`

功能：

1. 安装依赖
2. 检查 tray 依赖
3. 执行平台打包脚本
4. 自动生成带版本号的标准化发布目录
5. 自动生成压缩包与 SHA256 校验

### Linux / macOS

```bash
bash packaging/common/publish.sh
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\publish.ps1
```


## release 压缩包与校验

现在支持直接生成带压缩包和校验文件的发布目录：

```bash
python -m cc_usage_reporter release-pack
```

效果：

- 生成标准化 release 目录
- 自动生成 `.zip`
- 自动生成 `.tar.gz`
- 自动在 `metadata/SHA256SUMS.txt` 中写入校验值
- release 目录名自动带版本号，例如：

```text
release/cc-usage-reporter-v1.0.0-linux-20260701-xxxxxx/
```

同时 `metadata/manifest.json` 也会写入：

- `version`
- `platform`
- `generated_at`

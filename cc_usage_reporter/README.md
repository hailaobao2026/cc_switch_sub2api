# cc_usage_reporter — CC Switch 用量上报客户端

把本机 **CC Switch**（`~/.cc-switch/cc-switch.db`）记录的模型调用用量，按 **天 × 模型** 聚合后上报到本项目的 **sidecar** 服务，再由 sidecar 写入 sub2api 使用的 PostgreSQL 外部用量表。

## 工作原理

```text
~/.cc-switch/cc-switch.db
    └─ proxy_request_logs (每次请求一行)
            │  读取(只读) + 按 UTC 天×模型 聚合
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
  "db_path": "C:\\Users\\Administrator\\.cc-switch\\cc-switch.db"
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
| `report_path` | `SUB2API_REPORT_PATH` | 默认 `/api/v1/usage/report` |
| `login_path` | `SUB2API_LOGIN_PATH` | 旧登录模式使用，默认 `/api/v1/auth/login` |
| `db_path` | `CC_SWITCH_DB_PATH` | 默认 `~/.cc-switch/cc-switch.db` |
| `state_path` | `CC_SWITCH_STATE_PATH` | 上报状态文件 |
| `app_types` | — | 默认 `['claude', 'codex']` |
| `only_success` | — | 仅上报 2xx 请求（`--all` 可包含失败） |
| `verify_tls` | `SUB2API_VERIFY_TLS` | HTTPS 自签名证书可设 false / `--no-verify-tls` |

## 命令

| 命令 | 作用 |
|---|---|
| `preview` | 本地聚合概览（前 20 桶），不联网 |
| `show` | 打印全部聚合桶，不联网 |
| `run` | 上报变化的桶 |
| `run --dry-run` | 演练，打印将要上报的桶但不发送 |

常用参数：`--config` `--base-url` `--username` `--email` `--password` `--token` `--db-path` `--state-path` `--all` `--no-verify-tls` `--no-incremental`。

## 打包为 Windows EXE

可以用 PyInstaller 把客户端打包成单文件 EXE，安装后直接读取 `C:\Users\Administrator\.cc-switch\cc-switch.db` 并上报。

### 1) 进入客户端目录

```powershell
cd F:\work\code\other\20260626\CC_Switch_plugin\cc_usage_reporter
```

### 2) 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止执行脚本，先在当前窗口临时放开执行策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 3) 安装 PyInstaller

```powershell
python -m pip install --upgrade pip
python -m pip install pyinstaller
```

### 4) 打包前确认客户端可运行

```powershell
python -m cc_usage_reporter preview --db-path "C:\Users\Administrator\.cc-switch\cc-switch.db"
```

### 5) 打包单文件 EXE

```powershell
pyinstaller `
  --onefile `
  --name cc-usage-reporter `
  --console `
  --clean `
  cc_usage_reporter\__main__.py
```

打包完成后，EXE 位于：

```powershell
F:\work\code\other\20260626\CC_Switch_plugin\cc_usage_reporter\dist\cc-usage-reporter.exe
```

### 6) 测试 EXE

本地预览：

```powershell
.\dist\cc-usage-reporter.exe preview --db-path "C:\Users\Administrator\.cc-switch\cc-switch.db"
```

sidecar 上报演练：

```powershell
.\dist\cc-usage-reporter.exe run `
  --base-url "http://127.0.0.1:8788" `
  --token "你的-sidecar-report-token" `
  --username "alice" `
  --db-path "C:\Users\Administrator\.cc-switch\cc-switch.db" `
  --state-path "C:\Users\Administrator\.cc-switch\usage_reporter_state.json" `
  --dry-run
```

正式上报时去掉 `--dry-run`：

```powershell
.\dist\cc-usage-reporter.exe run `
  --base-url "http://127.0.0.1:8788" `
  --token "你的-sidecar-report-token" `
  --username "alice" `
  --db-path "C:\Users\Administrator\.cc-switch\cc-switch.db" `
  --state-path "C:\Users\Administrator\.cc-switch\usage_reporter_state.json"
```

### 7) 使用配置文件运行

复制并编辑 sidecar 示例配置：

```powershell
Copy-Item .\config.sidecar.example.json .\config.sidecar.json
notepad .\config.sidecar.json
```

通过配置文件运行：

```powershell
.\dist\cc-usage-reporter.exe run --config .\config.sidecar.json --dry-run
```

打包产物只需要分发 `dist\cc-usage-reporter.exe`。配置文件和状态文件建议放在 `C:\Users\Administrator\.cc-switch\` 下。

## 定时自动上报（Windows）

用 `dev/register_task.ps1` 注册计划任务（每小时一次）：

```powershell
powershell -ExecutionPolicy Bypass -File dev\register_task.ps1 -ConfigPath "F:\...\config.sidecar.json"
```

或手动用「任务计划程序」运行：

```powershell
python -m cc_usage_reporter run --config <path>
```

## 安全提示

- `config.sidecar.json` 含 token，请勿提交到版本库。
- `token` 建议使用 32 字符以上随机字符串，并与 sidecar 的 `report_token` 保持一致。
- sidecar 会按 `username` 或 `email` 解析 sub2api 用户；建议每台客户端只配置自己的用户标识。

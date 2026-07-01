# Install on Windows

## 推荐顺序

1. 编辑 `config\config.sidecar.example.json`
2. 使用 `bin\cc-usage-reporter-gui.exe` 进行桌面配置
3. 如需后台服务，执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install_winsw.ps1 -ConfigPath "$env:USERPROFILE\.config\cc-switch\usage_reporter.json"
```

## 可执行文件

- `bin\cc-usage-reporter.exe`：CLI / daemon
- `bin\cc-usage-reporter-gui.exe`：GUI

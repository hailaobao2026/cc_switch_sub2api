# Install on macOS

## 推荐顺序

1. 编辑 `config/config.sidecar.example.json`
2. 运行 GUI 或 daemon：

```bash
./bin/cc-usage-reporter-gui
# 或
./bin/cc-usage-reporter daemon --config "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
```

3. 如需 launchd：

```bash
bash ./scripts/macos/install_launchd.sh "$HOME/Library/Application Support/cc-switch/usage_reporter.json"
```

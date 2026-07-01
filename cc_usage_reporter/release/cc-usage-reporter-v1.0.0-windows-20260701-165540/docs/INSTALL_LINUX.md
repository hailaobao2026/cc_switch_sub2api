# Install on Linux

## 推荐顺序

1. 编辑 `config/config.sidecar.example.json`
2. 运行 GUI 或 daemon：

```bash
./bin/cc-usage-reporter-gui
# 或
./bin/cc-usage-reporter daemon --config ~/.config/cc-switch/usage_reporter.json
```

3. 如需 systemd 用户服务：

```bash
bash ./scripts/linux/install_systemd_user.sh ~/.config/cc-switch/usage_reporter.json
```

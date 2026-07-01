# Release Layout

- `bin/`：规范化命名后的可执行文件副本（如存在）
- `dist/`：原始打包产物
- `config/`：示例配置文件
- `scripts/`：安装/打包/辅助脚本
- `services/`：三端服务模板
- `docs/`：项目文档与安装说明
- `metadata/`：manifest / requirements / pyproject / 校验信息

推荐交付流程：

1. 编辑 `config/config.sidecar.example.json` 为实际配置
2. 优先分发 `bin/` 中的规范化可执行文件
3. 按系统执行对应安装脚本
4. 如需对外发布，可分发压缩包与 `SHA256SUMS.txt`

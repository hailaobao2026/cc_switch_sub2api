"""cc_usage_reporter — 将 CC Switch 本地模型用量上报到 sub2api 平台。

读取 CC Switch 数据库中的 ``proxy_request_logs``，按天 × 模型聚合后，
通过 HTTP 上报到 sub2api 的用量摄取接口，以用户名/邮箱关联。
默认兼容 Windows / Linux / macOS 常见配置目录，并保留旧 ``~/.cc-switch`` 路径。
"""

__version__ = "1.0.0"

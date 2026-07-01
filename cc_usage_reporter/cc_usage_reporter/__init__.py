"""cc_usage_reporter — 将 CC Switch 本地模型用量上报到 sub2api 平台。

读取 ``~/.cc-switch/cc-switch.db`` 中的 ``proxy_request_logs``，按
天 × 模型聚合后，通过 HTTP 上报到 sub2api 的用量摄取接口，以用户名/邮箱关联。
"""

__version__ = "1.0.0"

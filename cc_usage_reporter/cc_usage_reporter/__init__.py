"""cc_usage_reporter — 将 CC Switch / magpie 本地模型用量上报到 sub2api 平台。

两个数据源，输出同一套「天 × 模型」桶后统一上报：

* **CC Switch**：读取数据库中的 ``proxy_request_logs``；
* **magpie**（``--magpie`` 开启）：优先走其网关 HTTP API（行内带算好的 cost），
  不可用时回退解析 ``usage.jsonl``。

通过 HTTP 上报到 sub2api 的用量摄取接口，以用户名/邮箱关联。
默认兼容 Windows / Linux / macOS 常见配置目录，并保留旧 ``~/.cc-switch`` 路径。
"""

__version__ = "1.1.0"

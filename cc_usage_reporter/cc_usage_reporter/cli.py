"""命令行入口。

用法示例：
  python -m cc_usage_reporter --config config.json --dry-run
  python -m cc_usage_reporter --base-url https://s.example.com \
      --email me@x.com --password secret --username alice
  python -m cc_usage_reporter run            # 读取默认配置并上报
  python -m cc_usage_reporter preview        # 仅打印聚合，不联网
"""

from __future__ import annotations

import argparse
import sys

from .config import load_config
from .database import read_daily_model_usage
from .reporter import run
from .sub2api_client import Sub2ApiError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cc_usage_reporter",
        description="将 CC Switch 本地模型用量上报到 sub2api（按用户名/邮箱关联，每日聚合）。",
    )
    p.add_argument("command", nargs="?", default="run",
                   choices=["run", "preview", "show"],
                   help="run=上报; preview=仅本地预览聚合; show=打印将要上报的桶")
    p.add_argument("--config", help="配置文件路径")
    p.add_argument("--base-url", dest="base_url", help="sub2api 地址")
    p.add_argument("--username", help="关联的 sub2api 用户名")
    p.add_argument("--email", help="sub2api 登录邮箱")
    p.add_argument("--password", help="sub2api 登录密码")
    p.add_argument("--token", help="直接提供 Bearer token（跳过登录）")
    p.add_argument("--db-path", dest="db_path", help="cc-switch.db 路径")
    p.add_argument("--state-path", dest="state_path", help="状态文件路径")
    p.add_argument("--report-path", dest="report_path", help="上报接口路径")
    p.add_argument("--login-path", dest="login_path", help="登录接口路径")
    p.add_argument("--app-types", dest="app_types", help="逗号分隔, 如 claude,codex")
    p.add_argument("--all", dest="only_success", action="store_false",
                   help="包含失败请求（默认仅成功）")
    p.add_argument("--no-verify-tls", dest="verify_tls", action="store_false",
                   help="不校验 TLS 证书（自签名时用）")
    p.add_argument("--no-incremental", dest="incremental", action="store_false",
                   help="忽略状态水位线（不影响 signature 去重）")
    p.add_argument("--dry-run", action="store_true", help="演练，不实际上报")
    p.set_defaults(only_success=None, verify_tls=None, incremental=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    overrides = {
        "base_url": args.base_url,
        "username": args.username,
        "email": args.email,
        "password": args.password,
        "token": args.token,
        "db_path": args.db_path,
        "state_path": args.state_path,
        "report_path": args.report_path,
        "login_path": args.login_path,
        "app_types": args.app_types,
        "only_success": args.only_success,
        "verify_tls": args.verify_tls,
    }

    try:
        cfg = load_config(args.config, overrides)
    except (OSError, ValueError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    # 本地预览：不需要网络/凭据
    if args.command in {"preview", "show"}:
        try:
            buckets = read_daily_model_usage(
                db_path=cfg.db_path,
                app_types=cfg.app_types,
                only_success=cfg.only_success,
                since_epoch=None,
            )
        except Exception as exc:  # noqa: BLE001 - CLI 边界，统一兜底
            print(f"读取数据库失败: {exc}", file=sys.stderr)
            return 1
        print(f"聚合桶总数: {len(buckets)}（app_types={cfg.app_types}, "
              f"only_success={cfg.only_success}）")
        total_cost = sum(b.total_cost_usd for b in buckets)
        total_in = sum(b.input_tokens for b in buckets)
        total_out = sum(b.output_tokens for b in buckets)
        print(f"合计: input={total_in:,}  output={total_out:,}  cost=${total_cost:.4f}")
        limit = len(buckets) if args.command == "show" else min(20, len(buckets))
        for b in buckets[:limit]:
            print(f"  {b.date} {b.app_type:6} {b.model:26} "
                  f"req={b.request_count:4} in={b.input_tokens:>10} "
                  f"out={b.output_tokens:>8} cost=${b.total_cost_usd}")
        if limit < len(buckets):
            print(f"  ... 其余 {len(buckets) - limit} 个桶（用 show 查看全部）")
        return 0

    # 上报
    try:
        cfg.validate()
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"配置校验失败: {exc}", file=sys.stderr)
        return 2

    try:
        summary = run(cfg, dry_run=args.dry_run, incremental=args.incremental)
    except Sub2ApiError as exc:
        print(f"上报失败: {exc}", file=sys.stderr)
        if exc.body:
            print(f"服务端响应: {exc.body[:500]}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"运行出错: {exc}", file=sys.stderr)
        return 1

    if summary.dry_run:
        print("（dry-run，未实际上报）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

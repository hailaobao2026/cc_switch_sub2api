"""sub2api HTTP 客户端（仅依赖标准库 urllib）。

负责：
- 用 email+password 登录获取 JWT（POST /api/v1/auth/login）
- 携带 Bearer 调用用量摄取接口（POST /api/v1/usage/report，后端补丁新增）
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request


class Sub2ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


class Sub2ApiClient:
    def __init__(self, timeout: float = 30.0, verify_tls: bool = True):
        self.timeout = timeout
        if verify_tls:
            self._ssl_ctx = ssl.create_default_context()
        else:
            self._ssl_ctx = ssl._create_unverified_context()
        self._token: str | None = None

    # ------------------------------------------------------------------ #
    def _request(self, method: str, url: str, *, body: dict | None = None,
                 token: str | None = None) -> dict:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_ctx) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise Sub2ApiError(
                f"{method} {url} -> HTTP {exc.code}", status=exc.code, body=detail
            ) from exc
        except urllib.error.URLError as exc:
            raise Sub2ApiError(f"{method} {url} 连接失败: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise Sub2ApiError(f"{method} {url} 返回非 JSON: {exc}") from exc

    # ------------------------------------------------------------------ #
    def login(self, login_url: str, email: str, password: str) -> str:
        """登录并缓存 access_token，返回该 token。"""
        resp = self._request("POST", login_url, body={"email": email, "password": password})
        # sub2api AuthResponse: {"access_token": "...", "token_type": "Bearer", ...}
        token = resp.get("access_token") or resp.get("token")
        if not token and isinstance(resp.get("data"), dict):
            token = resp["data"].get("access_token") or resp["data"].get("token")
        if not token:
            raise Sub2ApiError(f"登录成功但未返回 access_token: {resp}")
        self._token = token
        return token

    def set_token(self, token: str) -> None:
        self._token = token

    def report(self, report_url: str, payload: dict) -> dict:
        """上报一批聚合用量。"""
        if not self._token:
            raise Sub2ApiError("未登录：缺少 access_token")
        return self._request("POST", report_url, body=payload, token=self._token)

"""临时联调用 mock sub2api 服务（仅供本地验证，非交付物）。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        if self.path == "/api/v1/auth/login":
            assert data.get("email") and data.get("password")
            return self._json(200, {"access_token": "MOCK.JWT.TOKEN", "token_type": "Bearer"})
        if self.path == "/api/v1/usage/report":
            auth = self.headers.get("Authorization", "")
            assert auth == "Bearer MOCK.JWT.TOKEN", f"bad auth: {auth}"
            items = data.get("items", [])
            print(f"[MOCK] report user={data.get('username')} items={len(items)}")
            return self._json(200, {"accepted": len(items), "duplicated": 0})
        return self._json(404, {"error": "not found"})


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8799), H)
    srv.serve_forever()

"""A stub of the account server's test surface, for `test_testrun_start_account.py`.

Launched by a fake `npx` as `python3 testrun_stub_server.py <port> <log> <mode>`, so it is the process that holds the port, exactly as the real server is the grandchild of the `npx` wrapper. Every request is appended to the log as one JSON line. The mode selects a failure: `ensure-login-500`, `no-subscription`, `no-token`, `login-fails`, `never-healthy`. The server's own environment is recorded (its `ACCOUNT_*` and `TEST_*` entries), which is how a test sees what the runner started it with.
"""

import http.server
import json
import os
import sys

PORT = int(sys.argv[1])
LOG = sys.argv[2] if len(sys.argv) > 2 else "/dev/null"
MODE = sys.argv[3] if len(sys.argv) > 3 else ""
SEEN = {k: v for k, v in os.environ.items() if k.startswith(("ACCOUNT_", "TEST_"))}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def reply(self, code: int, payload: object, cookie: bool = False) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", "sid=abc; Path=/")
        self.end_headers()
        self.wfile.write(body)

    def record(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        entry = {
            "method": self.command,
            "path": self.path,
            "body": json.loads(body) if body else None,
            "cookie": bool(self.headers.get("Cookie")),
            "test_mode": SEEN.get("TEST_MODE"),
            "key_lengths": {
                k: len(SEEN.get(k, "")) for k in ("ACCOUNT_SERVER_API_KEY", "ACCOUNT_JWT_SECRET")
            },
            "has_keys": all(
                SEEN.get(k) for k in ("ACCOUNT_ED25519_PRIVATE_KEY", "ACCOUNT_X25519_PUBLIC_KEY")
            ),
        }
        with open(LOG, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
        return body

    def do_GET(self) -> None:
        self.record()
        if self.path == "/health":
            self.reply(200, {"ok": True})
        elif self.path.endswith("/portal/subscription"):
            self.reply(200, {} if MODE == "no-subscription" else {"id": "sub_1"})
        else:
            self.reply(404, {})

    def do_POST(self) -> None:
        self.record()
        if self.path.endswith("/test/ensure-login"):
            self.reply(500 if MODE == "ensure-login-500" else 200, {"ok": True})
        elif self.path.endswith("/test/ensure-subscription"):
            self.reply(200, {"ok": True})
        elif self.path.endswith("/auth/login"):
            self.reply(
                200,
                {"error": "no"} if MODE == "login-fails" else {"user": {"id": "u1"}},
                cookie=True,
            )
        elif self.path.endswith("/api-tokens"):
            self.reply(200, {} if MODE == "no-token" else {"token": "rdt_stub_token_0123456789"})
        else:
            self.reply(404, {})


if MODE == "never-healthy":
    import time

    time.sleep(600)
    sys.exit(0)
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

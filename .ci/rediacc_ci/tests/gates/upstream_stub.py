"""A stand-in upstream for the three pin freshness gate tests, served over real HTTP on 127.0.0.1.

WHY A SERVER AND NOT A FIXTURE MAP. Each gate has a fixture seam that replaces the network with a JSON file, and that seam cannot reach the code the fail-closed ruling is about: the request, the status handling and the retry in `scripts/lib/pin-upstream.ts`. Each gate therefore also takes another base URL (`REAL_PROVIDER_API_BASE`, `DEVCONTAINER_API_BASE`, `EMBED_UPSTREAM_BASE`), and the tests point it here.

THE SCRIPT IS KEYED BY PATH, query string removed. Each path answers its scripted responses in order and the last one repeats, so `[status(503), ok(body)]` is a failure that clears and `[status(503)]` is one that does not. A path with no script answers 404, which is what a real host says about a route it does not have.

EVERY REQUEST IS RECORDED as (method, path, carried an Authorization header), so a test can assert how many times a path was asked and that the gate's token never reached the stub.

`closed_port()` is the offline case: a port nothing listens on, so the connection is refused the way an unreachable host refuses it.
"""

import contextlib
import http.server
import json
import socket
import threading

RATE_LIMITED = (
    403,
    {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1791000000"},
    {"message": "API rate limit exceeded"},
)


def sentinel() -> str:
    """A NON-SECRET stand-in the gate is handed as its credential, so a test can prove the value reaches neither the stub nor the output."""
    return "not-a-real-credential-sentinel"


def ok(body: object, **headers: str) -> tuple:
    """A 200. `body` is sent as JSON unless it is already bytes; `headers` use `_` for `-`."""
    return (200, {name.replace("_", "-"): value for name, value in headers.items()}, body)


def status(code: int) -> tuple:
    return (code, {}, {"message": "stubbed %d" % code})


def closed_port() -> int:
    """A port that was free a moment ago and has no listener."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class StubUpstream:
    """Each path answers its scripted responses in order, and the last one repeats."""

    def __init__(self, script: dict[str, list[tuple]]) -> None:
        self.script = {path: list(answers) for path, answers in script.items()}
        self.requests: list[tuple[str, str, bool]] = []
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def answer(self, method: str) -> None:
                route = self.path.split("?")[0]
                stub.requests.append((method, route, self.headers.get("Authorization") is not None))
                answers = stub.script.get(route) or [status(404)]
                code, headers, body = answers.pop(0) if len(answers) > 1 else answers[0]
                payload = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if method != "HEAD":
                    self.wfile.write(payload)

            def do_GET(self) -> None:
                self.answer("GET")

            def do_HEAD(self) -> None:
                self.answer("HEAD")

            def log_message(self, *_args: object) -> None:
                """Silence the per-request line; `requests` is the record."""

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def asked(self, path: str, method: str = "GET") -> int:
        return sum(1 for verb, seen, _ in self.requests if seen == path and verb == method)

    def tokens_seen(self) -> int:
        """How many requests carried an Authorization header. The gates must keep this at zero."""
        return sum(1 for _, _, sent in self.requests if sent)


@contextlib.contextmanager
def stub_upstream(script: dict[str, list[tuple]]):
    stub = StubUpstream(script)
    thread = threading.Thread(target=stub.server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        stub.server.shutdown()
        stub.server.server_close()
        thread.join(timeout=5)


def assert_no_token(gate, result) -> None:
    gate.assert_not_contains(result.combined, sentinel(), "the output never carries the token")
    gate.assert_not_contains(result.combined, "Bearer", "the output never carries a header")

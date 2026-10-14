"""A stand-in upstream for the external gate tests, served on 127.0.0.1: HTTP for the gates that fetch, DNS for the DKIM gate.

WHY A SERVER AND NOT A FIXTURE MAP. Each gate has a fixture seam that replaces the network with a JSON file, and that seam cannot reach the code the fail-closed ruling is about: the request, the status handling and the retry in `scripts/lib/upstream.ts` (and its Python copy `rediacc_ci.core.upstream`). Each gate therefore also takes another base URL or resolver (`REAL_PROVIDER_API_BASE`, `DEVCONTAINER_API_BASE`, `EMBED_UPSTREAM_BASE`, `ACTIONS_API_BASE`, `GO_DEPS_OSV_URL` and GOPROXY, `DKIM_RESOLVERS`, and links pointing at the stub under `EXTERNAL_LINKS_FIXTURE_ROOT`), and the tests point it here.

THE HTTP SCRIPT IS KEYED BY PATH, query string removed. Each path answers its scripted responses in order and the last one repeats, so `[status(503), ok(body)]` is a failure that clears and `[status(503)]` is one that does not. A path with no script answers the `default` script when one is given, and 404 otherwise, which is what a real host says about a route it does not have.

EVERY REQUEST IS RECORDED as (method, path, carried an Authorization header), so a test can assert how many times a path was asked and that the gate's token never reached the stub.

THE DNS STUB answers A-less questions only: TXT and MX, from a map of `(name, type)` to records, NXDOMAIN for a name it does not hold, and SERVFAIL for a name scripted as `SERVFAIL`. It parses exactly the query shape a resolver sends (one question, no compression in the question) and nothing more general.

`closed_port()` is the offline case: a port nothing listens on, so the connection is refused the way an unreachable host refuses it.
"""

import contextlib
import http.server
import json
import socket
import socketserver
import struct
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

    def __init__(self, script: dict[str, list[tuple]], default: list[tuple] | None = None) -> None:
        self.script = {path: list(answers) for path, answers in script.items()}
        self.default = list(default) if default else None
        self.requests: list[tuple[str, str, bool]] = []
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def answer(self, method: str) -> None:
                route = self.path.split("?")[0]
                stub.requests.append((method, route, self.headers.get("Authorization") is not None))
                answers = stub.script.get(route) or stub.default or [status(404)]
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

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                self.answer("POST")

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
def stub_upstream(script: dict[str, list[tuple]], default: list[tuple] | None = None):
    stub = StubUpstream(script, default)
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


# --------------------------------------------------------------------------- DNS

DNS_TYPES = {"TXT": 16, "MX": 15}


def _labels(name: str) -> bytes:
    return (
        b"".join(bytes([len(part)]) + part.encode() for part in name.rstrip(".").split(".")) + b"\0"
    )


def _rdata(rrtype: str, record: object) -> bytes:
    if rrtype == "TXT":
        text = str(record).encode()
        return b"".join(
            bytes([len(text[i : i + 255])]) + text[i : i + 255] for i in range(0, len(text), 255)
        )
    if not isinstance(record, tuple) or len(record) != 2:
        raise TypeError("an MX record is (preference, exchange), got %r" % (record,))
    preference, exchange = record
    return struct.pack("!H", preference) + _labels(exchange)


class StubDns:
    """Answers TXT and MX from `records`, keyed by (name, type). A name held under no type is NXDOMAIN; a value of "SERVFAIL" is a server failure."""

    def __init__(self, records: dict[tuple[str, str], object]) -> None:
        self.records = records
        self.asked: list[tuple[str, int]] = []
        stub = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                data, sock = self.request
                ident, _flags, _qd = struct.unpack("!HHH", data[:6])
                cursor, parts = 12, []
                while data[cursor]:
                    length = data[cursor]
                    parts.append(data[cursor + 1 : cursor + 1 + length].decode())
                    cursor += 1 + length
                qtype = struct.unpack("!H", data[cursor + 1 : cursor + 3])[0]
                question = data[12 : cursor + 5]
                name = ".".join(parts).lower()
                stub.asked.append((name, qtype))
                rrtype = next((k for k, v in DNS_TYPES.items() if v == qtype), "")
                held = stub.records.get((name, rrtype))
                known = any(n == name for n, _ in stub.records)
                rcode, answers = 0, b""
                count = 0
                if held == "SERVFAIL":
                    rcode = 2
                elif not known:
                    rcode = 3
                elif held is not None:
                    for record in held if isinstance(held, list) else [held]:
                        body = _rdata(rrtype, record)
                        answers += (
                            b"\xc0\x0c" + struct.pack("!HHIH", qtype, 1, 60, len(body)) + body
                        )
                        count += 1
                header = struct.pack("!HHHHHH", ident, 0x8180 | rcode, 1, count, 0, 0)
                sock.sendto(header + question + answers, self.client_address)

        self.server = socketserver.ThreadingUDPServer(("127.0.0.1", 0), Handler)
        self.address = "127.0.0.1:%d" % self.server.server_address[1]


@contextlib.contextmanager
def stub_dns(records: dict[tuple[str, str], object]):
    stub = StubDns(records)
    thread = threading.Thread(target=stub.server.serve_forever, daemon=True)
    thread.start()
    try:
        yield stub
    finally:
        stub.server.shutdown()
        stub.server.server_close()
        thread.join(timeout=5)

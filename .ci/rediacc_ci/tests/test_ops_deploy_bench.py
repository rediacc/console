"""rediacc_ci.ops.deploy_bench.seed_root: the bench root principal is created once and confirmed after.

A real local HTTP server stands in for the account Worker's POST /account/api/v1/auth/register (and 404s any other path), so the curl the module runs is the curl under test.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rediacc_ci.ops import deploy_bench

REGISTER_PATH = "/account/api/v1/auth/register"


class _Server:
    def __init__(self, refuse=None):
        self.users: set[str] = set()
        self.bodies: list[dict] = []
        self.refuse = refuse
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append(body)
                # The Worker serves its API under /account/api/v1 (private/account/src/routes/index.ts); any other path is the live 404 a bare /auth/register got on 2026-10-26.
                if self.path != REGISTER_PATH:
                    status, answer = 404, {}
                elif outer.refuse:
                    status, answer = outer.refuse
                elif body["email"] in outer.users:
                    status, answer = 409, {"error": "exists", "code": "EMAIL_EXISTS"}
                else:
                    outer.users.add(body["email"])
                    status, answer = 201, {"user": {"email": body["email"]}}
                data = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    made = []

    def make(refuse=None):
        made.append(_Server(refuse))
        return made[-1]

    yield make
    for s in made:
        s.close()


def test_first_run_creates_and_second_is_a_noop(server):
    srv = server()
    slept: list[float] = []
    assert deploy_bench.seed_root(srv.url, "root@example.test", sleep=slept.append) == "created"
    assert deploy_bench.seed_root(srv.url, "root@example.test", sleep=slept.append) == "exists"
    assert srv.users == {"root@example.test"}
    assert slept == []
    assert len(srv.bodies[0]["password"]) >= 8
    assert srv.bodies[0]["password"] != srv.bodies[1]["password"]


def test_refusal_is_a_named_error_without_the_password(server):
    srv = server(refuse=(400, {"error": "Validation error"}))
    with pytest.raises(deploy_bench.SeedError) as exc:
        deploy_bench.seed_root(srv.url, "root@example.test", sleep=lambda _: None)
    message = str(exc.value)
    assert "HTTP 400: Validation error" in message
    assert "ISSUER_OWNER_UNKNOWN" in message
    assert srv.bodies[0]["password"] not in message
    assert len(srv.bodies) == 1  # a 4xx is final, not retried


def test_server_errors_are_retried_then_named(server):
    srv = server(refuse=(503, {"error": "warming"}))
    slept: list[float] = []
    with pytest.raises(deploy_bench.SeedError, match="HTTP 503"):
        deploy_bench.seed_root(srv.url, "root@example.test", attempts=3, sleep=slept.append)
    assert len(srv.bodies) == 3
    assert slept == [5, 5]


def test_unreachable_server_is_named(server):
    srv = server()
    url = srv.url
    srv.close()
    with pytest.raises(deploy_bench.SeedError, match="no HTTP answer"):
        deploy_bench.seed_root(url, "root@example.test", attempts=1, sleep=lambda _: None)


def test_missing_root_email_is_named(monkeypatch):
    monkeypatch.delenv("ROOT_EMAIL", raising=False)
    with pytest.raises(deploy_bench.SeedError, match="ROOT_EMAIL is not set"):
        deploy_bench.seed_root("http://127.0.0.1:1")


def test_main_rejects_other_arguments_but_takes_seed_root(monkeypatch):
    assert deploy_bench.main(["--dry-run"]) == 2
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_bench.PROFILE)
    seen: list[int] = []

    def fake() -> str:
        seen.append(1)
        return "exists"

    monkeypatch.setattr(deploy_bench, "seed_root", fake)
    assert deploy_bench.main(["--seed-root"]) == 0
    assert seen == [1]


def test_curl_is_bounded_so_a_silent_worker_cannot_hang_the_seed(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 28, stdout="", stderr="timed out")

    monkeypatch.setattr(deploy_bench.subprocess, "run", fake_run)
    with pytest.raises(deploy_bench.SeedError, match="no HTTP answer"):
        deploy_bench.seed_root(
            "http://x.test", "root@example.test", attempts=2, sleep=lambda _: None
        )
    assert len(seen) == 2
    argv = seen[0]
    assert argv[argv.index("--max-time") + 1] == str(deploy_bench.CURL_MAX_TIME_S)
    assert "--connect-timeout" in argv


def test_seed_only_needs_curl_but_not_npx(monkeypatch):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_bench.PROFILE)
    monkeypatch.setattr(
        deploy_bench.shutil, "which", lambda cmd: None if cmd == "npx" else "/bin/x"
    )
    monkeypatch.setattr(deploy_bench, "seed_root", lambda: "exists")
    assert deploy_bench.main(["--seed-root"]) == 0


def test_seed_step_names_the_address(monkeypatch):
    monkeypatch.setenv("ROOT_EMAIL", "root@example.test")
    steps: list[str] = []
    monkeypatch.setattr(deploy_bench.log, "step", steps.append)
    monkeypatch.setattr(deploy_bench.log, "info", lambda _m: None)
    monkeypatch.setattr(deploy_bench, "seed_root", lambda: "created")
    deploy_bench._seed_and_report()
    assert "root@example.test" in steps[0]
    assert "(ROOT_EMAIL)" not in steps[0]


def test_deploy_seeds_the_root_after_the_secrets_push(monkeypatch, tmp_path):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text("")
    (worker / "node_modules").mkdir()
    web = tmp_path / "private" / "account" / "web"
    (web / "node_modules").mkdir(parents=True)
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_GLOBAL_API_KEY",
        "CF_API_KEY",
        "CF_EMAIL",
    ):
        monkeypatch.setenv(name, "x")
    events: list[str] = []
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda: {"K": "v"})
    monkeypatch.setattr(deploy_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(deploy_bench.bench_preflight, "lockfile", lambda _p: 0)
    monkeypatch.setattr(deploy_bench.bench_preflight, "buckets", lambda _c: 0)
    monkeypatch.setattr(deploy_bench, "capture_bookmark", lambda _d: None)
    monkeypatch.setattr(deploy_bench, "_rotation_check", lambda _r: events.append("rotation"))
    monkeypatch.setattr(
        deploy_bench, "_run", lambda argv, *_a, **_k: events.append(" ".join(argv[:4]))
    )
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda: events.append("seed"))
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert events[-1] == "seed"
    assert events[-2] == "npx wrangler secret bulk"
    assert events.count("seed") == 1

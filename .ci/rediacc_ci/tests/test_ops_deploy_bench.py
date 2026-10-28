"""rediacc_ci.ops.deploy_bench.seed_root: the bench root principal is created once and confirmed after.

A real local HTTP server stands in for the account Worker's POST /account/api/v1/auth/register (and 404s any other path), so the curl the module runs is the curl under test.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench
from rediacc_ci.well_known import BENCH_ORIGIN

REGISTER_PATH = "/account/api/v1/auth/register"
# The [assets] block deploy_bench requires before it builds the keyless portal (bench_assets_refusal).
BENCH_ASSETS_TOML = '[assets]\ndirectory = "./bench/dist"\n'


class _Server:
    def __init__(self, refuse=None):
        self.users: set[str] = set()
        self.bodies: list[dict] = []
        self.reset_with: list[dict] = []
        self.forgot_for: list[str] = []
        self.refuse = refuse
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append(body)
                # The Worker serves its API under /account/api/v1 (private/account/src/routes/index.ts); any other path is the live 404 a bare /auth/register got on 2026-10-26.
                status: int
                answer: dict
                if self.path.endswith("/auth/forgot"):
                    outer.forgot_for.append(body["email"])
                    status, answer = 200, {"message": "sent"}
                elif self.path.endswith("/auth/reset"):
                    outer.reset_with.append(body)
                    ok = body["token"] == "tok_ABC-123"
                    status, answer = (200, {"reset": True}) if ok else (400, {"error": "bad"})
                elif self.path != REGISTER_PATH:
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


PASSWORD = "stored-bench-root-pw"


@pytest.fixture(autouse=True)
def _stored_password(monkeypatch):
    monkeypatch.setenv(deploy_bench.ROOT_LOGIN_ENV, PASSWORD)


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
    # The stored value, on both runs: a run never invents a password the next run cannot know.
    assert [b["password"] for b in srv.bodies] == [PASSWORD, PASSWORD]


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


def test_unset_or_short_stored_password_is_a_named_error_before_any_request(monkeypatch, server):
    srv = server()
    monkeypatch.delenv(deploy_bench.ROOT_LOGIN_ENV)
    with pytest.raises(deploy_bench.SeedError, match="BENCH_ROOT_PASSWORD is not set"):
        deploy_bench.seed_root(srv.url, "root@example.test")
    monkeypatch.setenv(deploy_bench.ROOT_LOGIN_ENV, "short")
    with pytest.raises(deploy_bench.SeedError, match=r"8 to 128 characters .*not 5"):
        deploy_bench.seed_root(srv.url, "root@example.test")
    assert srv.bodies == []


def test_a_403_names_the_bench_access_fix(server):
    srv = server(refuse=(403, {}))
    with pytest.raises(deploy_bench.SeedError) as exc:
        deploy_bench.seed_root(srv.url, "root@example.test", sleep=lambda _: None)
    assert "HTTP 403" in str(exc.value)
    assert "rediacc_ci.ops.bench_access add-current" in str(exc.value)


def test_deploy_refuses_an_unset_password_before_the_first_remote_write(monkeypatch, tmp_path):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(BENCH_ASSETS_TOML)
    monkeypatch.delenv(deploy_bench.ROOT_LOGIN_ENV)
    ran: list[str] = []
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda: {"K": "v"})
    monkeypatch.setattr(deploy_bench, "_run", lambda argv, *_a, **_k: ran.append(argv[0]))
    with pytest.raises(deploy_bench.SeedError, match="BENCH_ROOT_PASSWORD"):
        deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert ran == []


def test_set_root_password_runs_the_reset_flow_from_the_captured_mail(server):
    srv = server()
    queries: list[str] = []

    def rows(sql):
        queries.append(sql)
        link = f"Reset: {BENCH_ORIGIN}/account/reset-password?token=tok_ABC-123 ok"
        return [{"text_body": link}]

    deploy_bench.set_root_password(srv.url, "root@example.test", rows=rows)
    assert srv.forgot_for == ["root@example.test"]
    assert srv.reset_with == [{"token": "tok_ABC-123", "password": PASSWORD}]
    assert "recipient = 'root@example.test'" in queries[0]
    assert "kind = 'password-reset'" in queries[0]


def test_set_root_password_waits_for_the_mail_then_names_its_absence(server):
    srv = server()
    slept: list[float] = []
    with pytest.raises(deploy_bench.SeedError, match="no password-reset mail") as exc:
        deploy_bench.set_root_password(
            srv.url, "root@example.test", sleep=slept.append, rows=lambda _s: []
        )
    assert len(slept) == deploy_bench.MAIL_ATTEMPTS - 1
    assert srv.reset_with == []
    assert PASSWORD not in str(exc.value)


def test_set_root_password_refuses_an_address_that_is_not_plain():
    with pytest.raises(deploy_bench.SeedError, match="not a plain address"):
        deploy_bench.set_root_password(
            "http://127.0.0.1:1", "x'; DROP TABLE users;--@e.test", rows=lambda _s: []
        )


def test_main_takes_set_root_password(monkeypatch):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", deploy_bench.PROFILE)
    seen: list[int] = []
    monkeypatch.setattr(deploy_bench, "set_root_password", lambda: seen.append(1))
    monkeypatch.setenv("ROOT_EMAIL", "root@example.test")
    assert deploy_bench.main(["--set-root-password"]) == 0
    assert seen == [1]


def test_deploy_seeds_the_root_after_the_secrets_push(monkeypatch, tmp_path):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(BENCH_ASSETS_TOML)
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
        deploy_bench,
        "_run",
        lambda argv, *_a, **_k: events.append(" ".join(argv[:5])) or "Current Version ID: " + VID,
    )
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda: events.append("seed"))
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        deploy_bench,
        "record_version",
        lambda _r, out, live: (events.append("record"), recorded.append((out, live))),
    )
    monkeypatch.setattr(deploy_bench.deploy_record, "worker_version", lambda *_a: (True, "live"))
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert recorded == [("Current Version ID: " + VID, "live")]
    assert events[-1] == "record"
    assert events[-2] == "seed"
    assert events[-3] == "npx --no-install wrangler secret bulk"
    assert events.count("seed") == 1


VID = "0b1f2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


def _fake_identity(_root, surfaces):
    return {
        "tree": "t",
        "head": "h",
        "dirty": [],
        "inputs": "i",
        "surfaces": sorted(surfaces),
        "submodules": {},
        "renet": None,
    }


def test_a_parsed_version_id_writes_bench_json(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy_bench.receipt, "identity", _fake_identity)
    out = "Uploaded\nDeployed rediacc-account-bench\nCurrent Version ID: %s\n" % VID
    got = deploy_bench.record_version(tmp_path, out, VID)
    written = json.loads((tmp_path / ".ci/cache/live-deploys/bench.json").read_text())
    assert written == got
    assert written["version_id"] == VID
    assert written["head"] == "h"
    assert written["surfaces"] == ["account", "account-worker"]
    assert written["at"].endswith("Z")
    assert set(written) >= {"version_id", "head", "tree", "dirty", "submodules", "at"}


def test_the_live_version_after_the_secrets_push_is_the_recorded_one(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy_bench.receipt, "identity", _fake_identity)
    live = "bb3e1ba3-ef59-4a56-9926-1e6a6ec47cec"
    got = deploy_bench.record_version(tmp_path, "Current Version ID: " + VID, live)
    assert got["version_id"] == live
    assert got["deployed_version_id"] == VID


def test_output_without_a_version_id_is_a_named_error_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy_bench.receipt, "identity", _fake_identity)
    with pytest.raises(deploy_bench.DeployError, match="Current Version ID"):
        deploy_bench.record_version(tmp_path, "Deployed rediacc-account-bench\n", VID)
    assert not (tmp_path / ".ci/cache/live-deploys/bench.json").exists()


def test_an_existing_bench_json_is_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy_bench.receipt, "identity", _fake_identity)
    path = tmp_path / ".ci/cache/live-deploys/bench.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"version_id": "old"}')
    deploy_bench.record_version(tmp_path, "Current Version ID: " + VID, VID)
    assert json.loads(path.read_text())["version_id"] == VID


def test_a_blank_live_version_is_refused_not_replaced_by_the_printed_id(monkeypatch, tmp_path):
    monkeypatch.setattr(deploy_bench.receipt, "identity", _fake_identity)
    for blank in ("", "  ", None):
        with pytest.raises(deploy_bench.DeployError, match="live bench version"):
            deploy_bench.record_version(tmp_path, "Current Version ID: " + VID, blank)
    assert not (tmp_path / ".ci/cache/live-deploys/bench.json").exists()


def test_a_missing_live_version_after_the_deploy_fails_the_deploy(monkeypatch, tmp_path):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(BENCH_ASSETS_TOML)
    (worker / "node_modules").mkdir()
    (tmp_path / "private/account/web/node_modules").mkdir(parents=True)
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_GLOBAL_API_KEY",
        "CF_API_KEY",
        "CF_EMAIL",
    ):
        monkeypatch.setenv(name, "x")
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda: {"K": "v"})
    monkeypatch.setattr(deploy_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(deploy_bench.bench_preflight, "lockfile", lambda _p: 0)
    monkeypatch.setattr(deploy_bench.bench_preflight, "buckets", lambda _c: 0)
    monkeypatch.setattr(deploy_bench, "capture_bookmark", lambda _d: None)
    monkeypatch.setattr(deploy_bench, "_rotation_check", lambda _r: None)
    monkeypatch.setattr(deploy_bench, "_run", lambda *_a, **_k: "Current Version ID: " + VID)
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda: None)
    wrote: list[str] = []
    monkeypatch.setattr(deploy_bench, "record_version", lambda *_a: wrote.append("x"))
    for answer in ((False, None), (True, None)):
        monkeypatch.setattr(deploy_bench.deploy_record, "worker_version", lambda *_a, a=answer: a)
        with pytest.raises(deploy_bench.DeployError, match="no live version"):
            deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert wrote == []


def test_captured_output_is_echoed_as_it_arrives_and_returned(capsys, tmp_path):
    out = deploy_bench._run(
        ["python3", "-c", "import sys; print('a'); print('b', file=sys.stderr)"],
        tmp_path,
        "echo",
        capture=True,
    )
    assert sorted(out.splitlines()) == ["a", "b"]
    assert sorted(capsys.readouterr().out.splitlines()) == ["a", "b"]
    with pytest.raises(deploy_bench.DeployError, match="exit 3"):
        deploy_bench._run(["python3", "-c", "raise SystemExit(3)"], tmp_path, "x", capture=True)


def test_captured_run_whose_child_exits_without_reading_stdin_reports_its_own_failure(
    capsys, tmp_path
):
    """c7233ce0.1: a child that exits before consuming stdin raises DeployError (not BrokenPipeError) and its output is still echoed."""
    script = "import sys; print('wrangler: bad token'); sys.exit(4)"
    with pytest.raises(deploy_bench.DeployError, match="exit 4"):
        deploy_bench._run(
            ["python3", "-c", script],
            tmp_path,
            "secret put",
            stdin="x" * (8 * 1024 * 1024),
            capture=True,
        )
    assert "wrangler: bad token" in capsys.readouterr().out


def test_captured_run_feeds_stdin_to_a_child_that_reads_it(tmp_path):
    out = deploy_bench._run(
        ["python3", "-c", "import sys; print(sys.stdin.read().upper())"],
        tmp_path,
        "echo",
        stdin="abc",
        capture=True,
    )
    assert out.strip() == "ABC"


def _bench_env(monkeypatch, **overrides):
    values = {
        "ACCOUNT_ED25519_PRIVATE_KEY": "e1",
        "ACCOUNT_ED25519_PUBLIC_KEY": "e2",
        "ACCOUNT_X25519_PRIVATE_KEY": "x1",
        "ACCOUNT_X25519_PUBLIC_KEY": "x2",
        "ACCOUNT_SERVER_API_KEY": "ak",
        "ACCOUNT_JWT_SECRET": "jw",
        "ACCOUNT_CONFIG_SERVER_KEY": "ck",
        "ROOT_EMAIL": "root@example.invalid",
        "AWS_SES_ACCESS_KEY_ID": "sk",
        "AWS_SES_SECRET_ACCESS_KEY": "ss",
        "CLOUDFLARE_TURNSTILE_SECRET_KEY": "ts",
        "OBS_OTLP_CREDENTIALS": '{"user":"u","pass":"p"}',
        **overrides,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(deploy_bench, "_backup_values", lambda: ("https://e", "bk", "bs"))
    monkeypatch.setattr(deploy_bench, "bench_bucket", lambda: "bucket")


def test_the_payload_carries_the_config_server_key(monkeypatch):
    """Layer 3 of the config store: the bench key reaches the Worker under its Worker name (PLAN-config-server-key K2)."""
    _bench_env(monkeypatch)
    payload = deploy_bench.secrets_payload()
    assert payload["ACCOUNT_CONFIG_SERVER_KEY"] == "ck"
    assert "CONFIG_SERVER_KEY" not in payload


def test_an_empty_config_server_key_refuses_the_bench_push(monkeypatch):
    _bench_env(monkeypatch, ACCOUNT_CONFIG_SERVER_KEY="")
    with pytest.raises(deploy_bench.DeployError, match="ACCOUNT_CONFIG_SERVER_KEY"):
        deploy_bench.secrets_payload()


def _deploy_bench_profile() -> dict:
    supply = json.loads(paths.from_root(".ci", "config", "secret-supply.json").read_text("utf-8"))
    return supply["consumers"]["deploy-bench"]


def test_bench_signs_licences_with_the_production_ed25519_pair():
    """Operator ruling 2026-10-27: the licence signer is the unsuffixed production pair the edge and stable account-secrets profiles bind, never the DEV one."""
    required = _deploy_bench_profile()["required"]
    assert "ACCOUNT_ED25519_PRIVATE_KEY" in required
    assert "ACCOUNT_ED25519_PUBLIC_KEY" in required
    assert not any(line.startswith("ACCOUNT_ED25519_") and "_DEV" in line for line in required)


def test_bench_keeps_the_dev_x25519_envelope_key():
    """The X25519 pair is the E2E envelope key every bench config already holds as its e2ePublicKey; it is not the licence signer and stays DEV."""
    required = _deploy_bench_profile()["required"]
    assert "ACCOUNT_X25519_PRIVATE_KEY_DEV > ACCOUNT_X25519_PRIVATE_KEY" in required
    assert "ACCOUNT_X25519_PUBLIC_KEY_DEV > ACCOUNT_X25519_PUBLIC_KEY" in required


# --------------------------------------------------------------------------- The keyless bench portal never lands where production uploads from (2026-10-28) ---------------------------------------------------------------------------


def test_the_real_bench_config_builds_outside_the_production_assets():
    worker = paths.repo_root() / "workers" / "account"
    assert deploy_bench.bench_assets_refusal(worker) is None
    out = deploy_bench.portal_out_dir(worker)
    assert worker / "dist" not in out.parents
    assert out == worker / "bench" / "dist" / "account"


@pytest.mark.parametrize(
    ("toml", "needle"),
    [
        # The 2026-10-28 shape: bench serving, and so building, the production directory.
        ('[assets]\ndirectory = "./dist"\n', "not ./bench/dist"),
        ('[assets]\ndirectory = "./dist/bench"\n', "not ./bench/dist"),
        ("", "not ./bench/dist"),
        ("[assets\n", "cannot be read"),
    ],
)
def test_a_bench_config_that_points_at_production_assets_is_refused(tmp_path, toml, needle):
    (tmp_path / deploy_bench.CONFIG).write_text(toml)
    refusal = deploy_bench.bench_assets_refusal(tmp_path)
    assert refusal is not None
    assert needle in refusal


def _deploy_world(monkeypatch, tmp_path, toml, events):
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / deploy_bench.CONFIG).write_text(toml)
    (worker / "node_modules").mkdir()
    (tmp_path / "private/account/web/node_modules").mkdir(parents=True)
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda: {"K": "v"})
    monkeypatch.setattr(deploy_bench, "root_password", lambda: "p")
    monkeypatch.setattr(deploy_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(deploy_bench.bench_preflight, "lockfile", lambda _p: 0)
    monkeypatch.setattr(deploy_bench.bench_preflight, "buckets", lambda _c: 0)
    monkeypatch.setattr(deploy_bench, "capture_bookmark", lambda _d: None)
    monkeypatch.setattr(deploy_bench, "_rotation_check", lambda _r: None)
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda: None)
    monkeypatch.setattr(deploy_bench, "record_version", lambda *_a: None)
    monkeypatch.setattr(deploy_bench.deploy_record, "worker_version", lambda *_a: (True, "live"))
    monkeypatch.setattr(
        deploy_bench,
        "_run",
        lambda argv, *_a, **_k: events.append(list(argv)) or "Current Version ID: " + VID,
    )
    return worker


def test_the_bench_build_writes_into_bench_dist_and_never_dist(monkeypatch, tmp_path):
    events: list[list[str]] = []
    worker = _deploy_world(monkeypatch, tmp_path, BENCH_ASSETS_TOML, events)
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    builds = [e for e in events if "vite" in e]
    assert len(builds) == 1
    out = builds[0][builds[0].index("--outDir") + 1]
    assert out == str(worker / "bench" / "dist" / "account")
    assert str(worker / "dist") not in out


def test_a_bench_config_on_production_assets_stops_before_any_build_or_write(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _deploy_world(monkeypatch, tmp_path, '[assets]\ndirectory = "./dist"\n', events)
    with pytest.raises(deploy_bench.DeployError, match=r"not \./bench/dist"):
        deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path)
    assert events == []

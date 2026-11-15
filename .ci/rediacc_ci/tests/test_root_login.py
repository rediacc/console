"""rediacc_ci.ops.root_login against a fake account server: the token session, bind, rotation, probes and controls, and the older password path (challenge answered, wrong code refused, missing value refused naming its entry), with no secret ever printed."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rediacc_ci.ops import root_login, totp
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN

SEED = "JBSWY3DPEHPK3PXP"
EMAIL = "root@example.invalid"
PASSWORD = "root-Password-424242"
CHALLENGE = "challenge-token-abcdef"
SESSION = "session-cookie-value-98765"
CLOCK = 1_700_000_010.0  # the start of a 30 s window; the next window opens 30 s on


def _values(**over: str) -> dict[str, str]:
    base = {"ROOT_EMAIL": EMAIL, "ROOT_PASSWORD": PASSWORD, "ROOT_TOTP_SEED": SEED}
    base.update(over)
    return base


class _Account:
    """A fake `/account/api/v1/auth/` that accepts the codes in `accept` and records every body."""

    def __init__(
        self,
        accept: set[str],
        two_factor: bool = True,
        login_status: int = 200,
        login_error: object = None,
        cookie: bool = True,
    ):
        self.accept = accept
        self.two_factor = two_factor
        self.login_status = login_status
        self.login_error = login_error
        self.cookie = cookie
        self.bodies: list[tuple[str, dict]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence the test server
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                route = self.path.rsplit("/auth/", 1)[1]
                outer.bodies.append((route, body))
                status, payload, cookie = 404, {}, False
                if route == "login":
                    status = outer.login_status
                    if status == 200 and outer.two_factor:
                        payload = {"requiresTwoFactor": True, "challengeToken": CHALLENGE}
                    elif status == 200:
                        cookie = outer.cookie
                    elif outer.login_error is not None:
                        payload = {"error": outer.login_error}
                elif route == "2fa/verify":
                    ok = (
                        body.get("challengeToken") == CHALLENGE and body.get("code") in outer.accept
                    )
                    status, cookie = (200, True) if ok else (401, False)
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                if cookie:
                    self.send_header("Set-Cookie", "session=%s; Path=/; HttpOnly" % SESSION)
                self.end_headers()
                self.wfile.write(raw)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.origin = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def account_factory():
    made: list[_Account] = []

    def make(*args, **kwargs):
        account = _Account(*args, **kwargs)
        made.append(account)
        return account

    yield make
    for account in made:
        account.close()


def _now_sleep():
    state = {"t": CLOCK}
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        state["t"] += seconds

    return (lambda: state["t"]), sleep, slept


def _pin_clock(monkeypatch, account) -> None:
    """Point `main` at the fake server with the fixed clock and no real sleep."""
    now, sleep, _ = _now_sleep()
    real = root_login.open_session
    monkeypatch.setattr(root_login, "origin_for", lambda *_: account.origin)
    monkeypatch.setattr(
        root_login, "open_session", lambda origin, values: real(origin, values, now, sleep)
    )


def test_challenge_answered_with_the_seed_code(account_factory):
    good = totp.code(SEED, at=CLOCK)
    account = account_factory({good})
    now, sleep, slept = _now_sleep()
    root_login.open_session(account.origin, _values(), now, sleep)
    routes = [route for route, _ in account.bodies]
    assert routes == ["login", "2fa/verify"]
    assert account.bodies[0][1] == {"email": EMAIL, "password": PASSWORD}
    assert slept == []


def test_first_code_refused_then_next_window_code_accepted(account_factory):
    later = totp.code(SEED, at=CLOCK + 30.5)
    account = account_factory({later})
    now, sleep, slept = _now_sleep()
    root_login.open_session(account.origin, _values(), now, sleep)
    assert [r for r, _ in account.bodies] == ["login", "2fa/verify", "2fa/verify"]
    assert len(slept) == 1


def test_wrong_code_refused_twice_names_the_entry_and_stops(account_factory):
    account = account_factory(set())
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="ROOT_TOTP_SEED") as caught:
        root_login.open_session(account.origin, _values(), now, sleep)
    assert "refused in two consecutive" in str(caught.value)
    assert [r for r, _ in account.bodies].count("2fa/verify") == 2


def test_password_refused_stops_before_any_code(account_factory):
    account = account_factory(set(), login_status=401)
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="HTTP 401"):
        root_login.open_session(account.origin, _values(), now, sleep)
    assert [r for r, _ in account.bodies] == ["login"]


@pytest.mark.parametrize(
    ("error", "quoted"),
    [
        ("Captcha verification required", "HTTP 400: Captcha verification required"),
        (
            {"code": "ACCOUNT_LOCKED", "message": "too many attempts"},
            "HTTP 423 ACCOUNT_LOCKED: too many attempts",
        ),
    ],
)
def test_a_refused_login_quotes_the_server_error(account_factory, error, quoted):
    """Stable eu answered 2026-11-15 `400 {"error": "Captcha verification required"}`; the refusal used to say "the root address or password was refused" for every non-200, hiding the captcha."""
    status = 400 if isinstance(error, str) else 423
    account = account_factory(set(), login_status=status, login_error=error)
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError) as caught:
        root_login.open_session(account.origin, _values(), now, sleep)
    assert quoted in str(caught.value)
    assert "password was refused" not in str(caught.value)


def test_no_challenge_with_a_cookie_opens_a_session(account_factory):
    account = account_factory(set(), two_factor=False)
    now, sleep, _ = _now_sleep()
    root_login.open_session(account.origin, _values(), now, sleep)
    assert [r for r, _ in account.bodies] == ["login"]


def test_answer_without_a_session_cookie_is_not_a_session(account_factory):
    account = account_factory(set(), two_factor=False, cookie=False)
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="no session cookie"):
        root_login.open_session(account.origin, _values(), now, sleep)


@pytest.mark.parametrize("missing", ["ROOT_EMAIL", "ROOT_PASSWORD", "ROOT_TOTP_SEED"])
def test_missing_env_refused_naming_the_bws_entry(missing):
    env = _values()
    del env[missing]
    with pytest.raises(root_login.RootLoginError, match=missing) as caught:
        root_login.read_values(env)
    assert caught.value.rc == 2
    assert "Bitwarden entry" in str(caught.value)


def test_placeholder_refused():
    with pytest.raises(root_login.RootLoginError, match="ROOT_PASSWORD"):
        root_login.read_values(_values(ROOT_PASSWORD=root_login.PLACEHOLDER))


def test_values_control_passes():
    assert root_login.read_values(_values())["ROOT_EMAIL"] == EMAIL


def test_arguments_and_origins():
    assert root_login.parse_args(["--target", "edge", "--region", "us"]) == root_login.Options(
        "edge", "us"
    )
    for bad in (
        ["--target", "bench", "--region", "eu"],
        ["--target", "edge"],
        ["--x"],
        ["--target", "edge", "--region", "eu", "--probe", "users"],
        ["--target", "edge", "--region", "eu", "--check", "--control"],
        ["--target", "edge", "--region", "eu", "--probe", "stats", "--rotate"],
    ):
        with pytest.raises(root_login.RootLoginError) as caught:
            root_login.parse_args(bad)
        assert caught.value.rc == 2
    assert root_login.origin_for("stable", "eu") == root_login.origin_for("edge", "eu")
    assert root_login.origin_for("edge", "eu") == ACCOUNT_DEFAULT_ORIGIN


def test_password_main_prints_only_the_fact_never_a_secret(account_factory, monkeypatch, capsys):
    good = totp.code(SEED, at=CLOCK)
    account = account_factory({good})
    _pin_clock(monkeypatch, account)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", root_login.PROFILE)
    for name, value in _values().items():
        monkeypatch.setenv(name, value)
    assert root_login.main(["--target", "edge", "--region", "eu", "--password"]) == 0
    out, err = capsys.readouterr()
    assert out.strip() == "root session opened (edge eu)"
    for secret in (PASSWORD, SEED, good, SESSION, CHALLENGE):
        assert secret not in out + err


def test_password_failure_output_never_carries_a_secret(account_factory, monkeypatch, capsys):
    account = account_factory(set())
    _pin_clock(monkeypatch, account)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", root_login.PROFILE)
    for name, value in _values().items():
        monkeypatch.setenv(name, value)
    assert root_login.main(["--target", "stable", "--region", "eu", "--password"]) == 1
    out, err = capsys.readouterr()
    for secret in (PASSWORD, SEED, SESSION, CHALLENGE, totp.code(SEED, at=CLOCK)):
        assert secret not in out + err


def test_main_reexecs_under_the_profile_when_unbound(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(argv, _env) -> int:
        seen.append(list(argv))
        return 0

    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    rc = root_login.main(["--target", "edge", "--region", "eu"], run=fake_run)
    assert rc == 0
    assert seen[0][seen[0].index("--profile") + 1] == root_login.PROFILE
    assert seen[0][-4:] == ["--target", "edge", "--region", "eu"]


# --- token mode -------------------------------------------------------------

TOKEN = "rdr_" + "ab12" * 16
NEW_TOKEN = "rdr_" + "cd34" * 16
DAY_MS = 86_400_000


def _token_env(**over: str) -> dict[str, str]:
    base = {"ROOT_API_TOKEN": TOKEN, "ROOT_TOTP_SEED": SEED}
    base.update(over)
    return base


class _Admin:
    """A fake `/account/api/v1` root token surface. Codes in `accept` are valid and are spent once; `mismatch` answers ROOT_TOKEN_IP_MISMATCH to the session call until a bind (`sticky` keeps answering it); `leak` makes the session-less stats call answer 200."""

    def __init__(
        self,
        accept: set[str],
        mismatch: bool = False,
        sticky: bool = False,
        fault: int = 0,
        leak: bool = False,
        captcha: bool = True,
        token_days: int = 30,
    ):
        self.accept = accept
        self.mismatch = mismatch
        self.sticky = sticky
        self.fault = fault
        self.leak = leak
        self.captcha = captcha
        self.token_days = token_days
        self.spent: set[str] = set()
        self.session_open = False
        self.requests: list[tuple[str, str, str, dict]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else {}
                route = self.path.split("/account/api/v1", 1)[1]
                outer.requests.append((method, route, self.headers.get("Authorization", ""), body))
                if route == "/auth/login":
                    if outer.captcha:
                        return self._answer(400, {"error": "Captcha verification required"})
                    return self._answer(401, {"error": "bad password"})
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    return self._answer(401, {"error": "invalid token", "code": "UNAUTHORIZED"})
                path = route.split("?")[0]
                if method == "POST" and path in (
                    "/admin/root-token/session",
                    "/admin/root-token/bind",
                ):
                    return self._code_route(path, body)
                if path == "/admin/root-token/session" and method == "DELETE":
                    outer.session_open = False
                    return self._answer(200, {"closed": True})
                if not outer.session_open and not (path == "/admin/stats" and outer.leak):
                    return self._answer(
                        403, {"error": "session needed", "code": "ROOT_TOKEN_SESSION_REQUIRED"}
                    )
                if path == "/admin/stats" and method == "GET":
                    return self._answer(200, {"users": 1, "orgs": 2, "teams": 3})
                if path == "/admin/activity" and method == "GET":
                    rows = [{"type": "root_token.session_opened", "createdAt": "2026-11-15T17:00Z"}]
                    return self._answer(200, {"items": rows})
                if path == "/admin/root-token/rotate" and method == "POST":
                    expires = (CLOCK * 1000) + outer.token_days * DAY_MS
                    return self._answer(201, {"token": NEW_TOKEN, "tokenExpiresAt": expires})
                return self._answer(404, {"error": "no route"})

            def _code_route(self, path: str, body: dict) -> None:
                if outer.fault:
                    return self._answer(outer.fault, {"error": "busy"})
                if outer.mismatch and path.endswith("session"):
                    return self._answer(
                        403, {"error": "other address", "code": "ROOT_TOKEN_IP_MISMATCH"}
                    )
                code = body.get("code")
                if code not in outer.accept:
                    return self._answer(400, {"error": "bad code", "code": "TOTP_INVALID"})
                if code in outer.spent:
                    return self._answer(409, {"error": "spent", "code": "TOTP_REPLAYED"})
                outer.spent.add(code)
                if path.endswith("bind"):
                    outer.mismatch = outer.sticky
                    return self._answer(
                        200, {"rebound": True, "family": "v4", "bound": {"v4": "1.2.3.4"}}
                    )
                outer.session_open = True
                return self._answer(
                    200,
                    {
                        "sessionExpiresAt": (CLOCK + 600) * 1000,
                        "tokenExpiresAt": (CLOCK * 1000) + outer.token_days * DAY_MS,
                        "bound": {},
                    },
                )

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_DELETE(self):
                self._handle("DELETE")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.origin = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def routes(self) -> list[str]:
        return ["%s %s" % (m, r.split("?")[0]) for m, r, _, _ in self.requests]

    def codes(self) -> list[str]:
        return [b["code"] for _, _, _, b in self.requests if "code" in b]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _steps(*offsets: float) -> set[str]:
    return {totp.code(SEED, at=CLOCK + o) for o in offsets}


@pytest.fixture
def admin_factory():
    made: list[_Admin] = []

    def make(*args, **kwargs):
        admin = _Admin(*args, **kwargs)
        made.append(admin)
        return admin

    yield make
    for admin in made:
        admin.close()


def _token_main(monkeypatch, admin, env=None, capture=None):
    """`main` against the fake, on the fixed clock; returns (call, slept)."""
    now, sleep, slept = _now_sleep()
    monkeypatch.setattr(root_login, "origin_for", lambda *_: admin.origin)
    monkeypatch.setattr(root_login, "_clock", lambda: (now, sleep))
    monkeypatch.setenv("REDIACC_BWS_PROFILES", root_login.PROFILE)
    monkeypatch.delenv("ROOT_LOGIN_AUTOROTATE", raising=False)
    for name, value in (env or _token_env()).items():
        monkeypatch.setenv(name, value)
    kwargs = {"capture": capture} if capture else {}
    return (lambda *argv: root_login.main(list(argv), **kwargs)), slept


@pytest.mark.parametrize(
    "bad", ["", root_login.PLACEHOLDER, "not-a-root-token", "rdt_" + "ab" * 32]
)
def test_unusable_token_refused_rc2_before_any_request(admin_factory, monkeypatch, bad, capsys):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN=bad))
    assert call("--target", "stable", "--region", "eu") == 2
    assert admin.requests == []
    assert "ROOT_API_TOKEN" in capsys.readouterr().err


def test_valid_token_control_passes_values():
    assert root_login.read_token_values(_token_env())["ROOT_API_TOKEN"] == TOKEN


def test_missing_seed_refused_naming_the_entry():
    with pytest.raises(root_login.RootLoginError, match="ROOT_TOTP_SEED") as caught:
        root_login.read_token_values({"ROOT_API_TOKEN": TOKEN})
    assert caught.value.rc == 2


def test_session_opens_with_one_code_and_no_bind(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    call, slept = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 0
    assert admin.routes() == ["POST /admin/root-token/session"]
    assert admin.requests[0][2] == "Bearer " + TOKEN
    assert slept == []
    assert capsys.readouterr().out.strip() == (
        "root session opened (stable eu, token, session until 22:23Z, token expires in 30 days)"
    )


def test_ip_mismatch_binds_once_then_opens_in_the_next_step(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0, 30, 60), mismatch=True)
    call, slept = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 0
    assert admin.routes() == [
        "POST /admin/root-token/session",
        "POST /admin/root-token/bind",
        "POST /admin/root-token/session",
    ]
    # The mismatch is answered before any code is judged, so the bind may reuse the window's code; the second session needs the next step's (the account spends a code once).
    _, bind_code, second_code = admin.codes()
    assert second_code != bind_code
    assert len(slept) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "ip rebound (v4)"
    assert out[1].startswith("root session opened (stable eu, token")


def test_mismatch_that_persists_after_a_bind_is_a_failure_not_a_loop(admin_factory):
    admin = admin_factory(_steps(0, 30, 60), mismatch=True, sticky=True)
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="ROOT_TOKEN_IP_MISMATCH"):
        root_login._open_token(admin.origin, _token_env(), now, sleep)
    assert admin.routes().count("POST /admin/root-token/bind") == 1


def test_code_refused_twice_is_rc1_with_no_third_try(admin_factory, monkeypatch, capsys):
    admin = admin_factory(set())
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 1
    assert admin.routes() == ["POST /admin/root-token/session"] * 2
    err = capsys.readouterr().err
    assert "refused in two consecutive" in err
    assert "ROOT_TOTP_SEED" in err


def test_replayed_code_is_retried_once_from_the_next_window(admin_factory, monkeypatch):
    admin = admin_factory(_steps(0, 30))
    admin.spent.add(totp.code(SEED, at=CLOCK))
    call, slept = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 0
    assert admin.routes() == ["POST /admin/root-token/session"] * 2
    assert len(slept) == 1


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limit_and_server_fault_are_a_fault_not_a_refusal(
    admin_factory, monkeypatch, capsys, status
):
    admin = admin_factory(_steps(0), fault=status)
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 1
    assert admin.routes() == ["POST /admin/root-token/session"]
    err = capsys.readouterr().err
    assert "HTTP %d" % status in err
    assert "not a refusal of the code" in err
    assert "stale or wrong" not in err


def test_other_refusal_is_named_and_not_retried(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN="rdr_" + "00" * 32))
    assert call("--target", "stable", "--region", "eu") == 1
    assert admin.routes() == ["POST /admin/root-token/session"]
    assert "HTTP 401 UNAUTHORIZED" in capsys.readouterr().err


@pytest.mark.parametrize("region", ["us", "asia"])
def test_other_regions_refused_with_the_name_their_token_would_take(
    admin_factory, monkeypatch, capsys, region
):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", region) == 2
    assert admin.requests == []
    assert "ROOT_API_TOKEN_%s" % region.upper() in capsys.readouterr().err


def test_check_makes_no_request(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--check") == 0
    assert admin.requests == []
    assert capsys.readouterr().out.strip() == "root login values ok (stable eu)"


def test_check_still_refuses_a_bad_value(admin_factory, monkeypatch):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN=root_login.PLACEHOLDER))
    assert call("--target", "stable", "--region", "eu", "--check") == 2


@pytest.mark.parametrize("name", ["stats", "audit"])
def test_probe_is_one_get_from_the_allowlist(admin_factory, monkeypatch, capsys, name):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--probe", name) == 0
    assert [m for m, *_ in admin.requests] == ["POST", "GET"]
    assert admin.requests[1][1] == root_login.PROBES[name]
    out = capsys.readouterr().out
    assert "GET /admin/%s 200" % ("stats" if name == "stats" else "activity") in out
    if name == "stats":
        assert "3 keys" in out
    else:
        assert "root_token.session_opened 2026-11-15T17:00Z" in out


def test_probe_allowlist_is_get_only_admin_paths():
    assert set(root_login.PROBES) == {"stats", "audit"}
    assert all(route.startswith("/admin/") for route in root_login.PROBES.values())


def test_admin_client_get_sends_no_body(admin_factory):
    admin = admin_factory(_steps(0))
    now, sleep, _ = _now_sleep()
    client = root_login._open_token(admin.origin, _token_env(), now, sleep)
    assert client.get("/admin/stats")[0] == 200
    assert admin.requests[-1][0] == "GET"
    assert admin.requests[-1][3] == {}


def test_control_passes_when_both_refusals_hold(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--control") == 0
    assert admin.routes() == [
        "POST /admin/root-token/session",
        "DELETE /admin/root-token/session",
        "GET /admin/stats",
        "POST /auth/login",
    ]
    assert capsys.readouterr().out.count("control ok") == 2


def test_control_fails_when_the_session_less_call_answers_200(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0), leak=True)
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--control") == 1
    assert "control FAILED" in capsys.readouterr().err
    assert "POST /auth/login" not in admin.routes()


def test_control_fails_when_login_stops_asking_for_a_captcha(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0), captcha=False)
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--control") == 1
    assert "Captcha verification required" in capsys.readouterr().err


def _capture_recorder(rc: int = 0):
    seen: list[tuple[list[str], dict[str, str]]] = []

    def capture(argv, env):
        seen.append((list(argv), dict(env)))
        return rc, "ROOT_API_TOKEN MATCH\n"

    return capture, seen


def test_rotate_writes_the_vault_entry_through_the_child_environment(
    admin_factory, monkeypatch, capsys
):
    admin = admin_factory(_steps(0))
    capture, seen = _capture_recorder()
    call, _ = _token_main(monkeypatch, admin, capture=capture)
    assert call("--target", "stable", "--region", "eu", "--rotate") == 0
    argv, env = seen[0]
    assert argv[-2:] == ["store-from-env", "ROOT_API_TOKEN > ROOT_API_TOKEN_NEW"]
    assert env["ROOT_API_TOKEN_NEW"] == NEW_TOKEN
    assert NEW_TOKEN not in " ".join(argv)
    assert TOKEN not in " ".join(argv)
    out, err = capsys.readouterr()
    assert "token rotated and stored as ROOT_API_TOKEN" in out
    assert NEW_TOKEN not in out + err
    assert TOKEN not in out + err


def test_failed_vault_write_after_rotation_is_named(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    capture, _ = _capture_recorder(rc=1)
    call, _ = _token_main(monkeypatch, admin, capture=capture)
    assert call("--target", "stable", "--region", "eu", "--rotate") == 1
    err = capsys.readouterr().err
    assert "writing ROOT_API_TOKEN" in err
    assert NEW_TOKEN not in err


def test_no_rotation_with_plenty_of_days_even_when_enabled(admin_factory, monkeypatch):
    admin = admin_factory(_steps(0))
    capture, seen = _capture_recorder()
    call, _ = _token_main(monkeypatch, admin, capture=capture)
    monkeypatch.setenv("ROOT_LOGIN_AUTOROTATE", "1")
    assert call("--target", "stable", "--region", "eu") == 0
    assert seen == []
    assert "POST /admin/root-token/rotate" not in admin.routes()


def test_autorotate_fires_under_14_days_only_when_enabled(admin_factory, monkeypatch):
    capture, seen = _capture_recorder()
    off = admin_factory(_steps(0), token_days=5)
    call, _ = _token_main(monkeypatch, off, capture=capture)
    assert call("--target", "stable", "--region", "eu") == 0
    assert seen == []
    on = admin_factory(_steps(0), token_days=5)
    call, _ = _token_main(monkeypatch, on, capture=capture)
    monkeypatch.setenv("ROOT_LOGIN_AUTOROTATE", "1")
    assert call("--target", "stable", "--region", "eu") == 0
    assert len(seen) == 1


def test_token_mode_output_never_carries_a_secret(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0, 30, 60), mismatch=True)
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--probe", "stats") == 0
    out, err = capsys.readouterr()
    for secret in (TOKEN, SEED, *_steps(0, 30, 60)):
        assert secret not in out + err


def test_failure_output_never_carries_a_secret_in_token_mode(admin_factory, monkeypatch, capsys):
    admin = admin_factory(set())
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu") == 1
    out, err = capsys.readouterr()
    for secret in (TOKEN, SEED, totp.code(SEED, at=CLOCK)):
        assert secret not in out + err


def test_open_token_session_is_importable_and_get_only(admin_factory, monkeypatch):
    admin = admin_factory(_steps(0, 30, 60))
    monkeypatch.setattr(root_login, "origin_for", lambda *_: admin.origin)
    monkeypatch.setattr(root_login.time, "time", lambda: CLOCK)
    monkeypatch.setattr(root_login.time, "sleep", lambda _s: None)
    client = root_login.open_token_session("stable", "eu", _token_env())
    assert client.get("/admin/stats")[0] == 200
    assert not hasattr(client, "put")
    assert not hasattr(client, "patch")


def test_instant_reads_epoch_milliseconds_and_iso():
    assert root_login._instant(1_700_000_010_000) == datetime(2023, 11, 14, 22, 13, 30, tzinfo=UTC)
    assert root_login._instant("2026-11-15T17:00:00Z") == datetime(2026, 11, 15, 17, tzinfo=UTC)
    assert root_login._instant("not a time") is None
    assert root_login._instant(True) is None

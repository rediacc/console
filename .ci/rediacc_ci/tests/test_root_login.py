"""rediacc_ci.ops.root_login against a fake account server: the token session, bind, rotation, probes and controls, and the older password path (challenge answered, wrong code refused, missing value refused naming its entry), with no secret ever printed."""

from __future__ import annotations

import json
import pathlib
import re
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
        login_payload: dict | None = None,
        verify_statuses: tuple[int, ...] = (),
    ):
        self.accept = accept
        self.two_factor = two_factor
        self.login_status = login_status
        self.login_error = login_error
        self.cookie = cookie
        self.login_payload = login_payload
        self.verify_statuses = list(verify_statuses)
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
                    elif outer.login_payload is not None:
                        payload = outer.login_payload
                    elif outer.login_error is not None:
                        payload = {"error": outer.login_error}
                elif route == "2fa/verify":
                    ok = (
                        body.get("challengeToken") == CHALLENGE and body.get("code") in outer.accept
                    )
                    status, cookie = (200, True) if ok else (401, False)
                    if outer.verify_statuses:
                        status, cookie = outer.verify_statuses.pop(0), False
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


def test_a_short_password_is_refused_and_a_short_value_is_not_masked():
    with pytest.raises(root_login.RootLoginError, match="shorter than") as caught:
        root_login.read_values(_values(ROOT_PASSWORD="abc"))
    assert caught.value.rc == 2
    assert root_login.masked("a cat sat", {"ROOT_PASSWORD": "a"}) == "a cat sat"
    long_env = {"ROOT_PASSWORD": "abcdefgh"}
    assert root_login.masked("x abcdefgh y", long_env) == "x <ROOT_PASSWORD> y"


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
    base = {"ROOT_API_TOKEN_EU": TOKEN, "ROOT_TOTP_SEED": SEED}
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
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN_EU=bad))
    assert call("--target", "stable", "--region", "eu") == 2
    assert admin.requests == []
    assert "ROOT_API_TOKEN_EU" in capsys.readouterr().err


def test_valid_token_control_passes_values():
    assert root_login.read_token_values(_token_env(), "eu")[root_login.BEARER_KEY] == TOKEN


@pytest.mark.parametrize(
    ("region", "entry"),
    [("eu", "ROOT_API_TOKEN_EU"), ("us", "ROOT_API_TOKEN_US"), ("asia", "ROOT_API_TOKEN_ASIA")],
)
def test_token_entry_is_the_region_suffixed_name(region, entry):
    assert root_login.token_entry(region) == entry


def test_unsuffixed_name_is_not_read_for_any_region():
    with pytest.raises(root_login.RootLoginError, match="ROOT_API_TOKEN_EU") as caught:
        root_login.read_token_values({"ROOT_API_TOKEN": TOKEN, "ROOT_TOTP_SEED": SEED}, "eu")
    assert caught.value.rc == 2


def test_unknown_region_is_refused():
    with pytest.raises(root_login.RootLoginError, match="no region 'mars'") as caught:
        root_login.token_entry("mars")
    assert caught.value.rc == 2


@pytest.mark.parametrize("region", ["eu", "us", "asia"])
def test_placeholder_is_refused_per_region_naming_its_entry(region):
    entry = root_login.token_entry(region)
    env = {entry: root_login.PLACEHOLDER, "ROOT_TOTP_SEED": SEED}
    with pytest.raises(root_login.RootLoginError, match=entry) as caught:
        root_login.read_token_values(env, region)
    assert caught.value.rc == 2


@pytest.mark.parametrize("region", ["us", "asia"])
def test_other_region_reads_its_own_entry_and_not_the_eu_one(region):
    entry = root_login.token_entry(region)
    other = "rdr_" + "ef56" * 16
    values = root_login.read_token_values(_token_env(**{entry: other}), region)
    assert values[root_login.BEARER_KEY] == other
    with pytest.raises(root_login.RootLoginError, match=entry):
        root_login.read_token_values(_token_env(), region)


def test_missing_seed_refused_naming_the_entry():
    with pytest.raises(root_login.RootLoginError, match="ROOT_TOTP_SEED") as caught:
        root_login.read_token_values({"ROOT_API_TOKEN_EU": TOKEN}, "eu")
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
        root_login._open_token(
            admin.origin, root_login.read_token_values(_token_env(), "eu"), now, sleep
        )
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
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN_EU="rdr_" + "00" * 32))
    assert call("--target", "stable", "--region", "eu") == 1
    assert admin.routes() == ["POST /admin/root-token/session"]
    assert "HTTP 401 UNAUTHORIZED" in capsys.readouterr().err


@pytest.mark.parametrize("region", ["us", "asia"])
def test_other_region_without_its_token_is_refused_naming_its_entry(
    admin_factory, monkeypatch, capsys, region
):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", region) == 2
    assert admin.requests == []
    assert "ROOT_API_TOKEN_%s" % region.upper() in capsys.readouterr().err


@pytest.mark.parametrize("region", ["us", "asia"])
def test_other_region_values_check_with_its_own_token_alone(admin_factory, monkeypatch, region):
    admin = admin_factory(_steps(0))
    entry = root_login.token_entry(region)
    call, _ = _token_main(monkeypatch, admin, _token_env(**{entry: TOKEN}))
    monkeypatch.delenv("ROOT_API_TOKEN_EU", raising=False)
    assert call("--target", "stable", "--region", region, "--check") == 0
    assert admin.requests == []


@pytest.mark.parametrize("region", ["us", "asia"])
def test_other_region_opens_a_session_with_its_own_token(admin_factory, monkeypatch, region):
    admin = admin_factory(_steps(0))
    entry = root_login.token_entry(region)
    call, _ = _token_main(monkeypatch, admin, _token_env(**{entry: TOKEN}))
    monkeypatch.delenv("ROOT_API_TOKEN_EU", raising=False)
    assert call("--target", "stable", "--region", region) == 0
    assert admin.routes() == ["POST /admin/root-token/session"]


def test_the_module_text_names_no_unsuffixed_token_entry():
    """Review 727d194e.1: the code reads only ROOT_API_TOKEN_<secretSuffix>, so the module text never tells an operator to fill the bare `ROOT_API_TOKEN`."""
    text = pathlib.Path(root_login.__file__).read_text(encoding="utf-8")
    assert not re.search(r"ROOT_API_TOKEN(?![_A-Za-z0-9])", text)


def test_check_makes_no_request(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin)
    assert call("--target", "stable", "--region", "eu", "--check") == 0
    assert admin.requests == []
    assert capsys.readouterr().out.strip() == "root login values ok (stable eu)"


def test_check_still_refuses_a_bad_value(admin_factory, monkeypatch):
    admin = admin_factory(_steps(0))
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN_EU=root_login.PLACEHOLDER))
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
    values = root_login.read_token_values(_token_env(), "eu")
    client = root_login._open_token(admin.origin, values, now, sleep)
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
        return rc, "ROOT_API_TOKEN_EU MATCH\n"

    return capture, seen


def test_rotate_writes_the_vault_entry_through_the_child_environment(
    admin_factory, monkeypatch, capsys
):
    admin = admin_factory(_steps(0))
    capture, seen = _capture_recorder()
    call, _ = _token_main(monkeypatch, admin, capture=capture)
    assert call("--target", "stable", "--region", "eu", "--rotate") == 0
    argv, env = seen[0]
    assert argv[-2:] == ["store-from-env", "ROOT_API_TOKEN_EU > ROOT_API_TOKEN_EU_NEW"]
    assert env["ROOT_API_TOKEN_EU_NEW"] == NEW_TOKEN
    assert NEW_TOKEN not in " ".join(argv)
    assert TOKEN not in " ".join(argv)
    out, err = capsys.readouterr()
    assert "token rotated and stored as ROOT_API_TOKEN_EU" in out
    assert NEW_TOKEN not in out + err
    assert TOKEN not in out + err


def test_rotate_in_another_region_writes_that_regions_entry(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    capture, seen = _capture_recorder()
    call, _ = _token_main(monkeypatch, admin, _token_env(ROOT_API_TOKEN_US=TOKEN), capture=capture)
    assert call("--target", "stable", "--region", "us", "--rotate") == 0
    argv, env = seen[0]
    assert argv[-2:] == ["store-from-env", "ROOT_API_TOKEN_US > ROOT_API_TOKEN_US_NEW"]
    assert env["ROOT_API_TOKEN_US_NEW"] == NEW_TOKEN
    assert "ROOT_API_TOKEN_EU_NEW" not in env
    assert "token rotated and stored as ROOT_API_TOKEN_US" in capsys.readouterr().out


def test_masked_hides_every_regions_token_entry_and_staged_successor():
    for name in ("ROOT_API_TOKEN_EU", "ROOT_API_TOKEN_ASIA_NEW"):
        value = "tok-" + "z" * 20
        assert root_login.masked("echo " + value, {name: value}) == "echo <%s>" % name


def test_failed_vault_write_after_rotation_is_named(admin_factory, monkeypatch, capsys):
    admin = admin_factory(_steps(0))
    capture, _ = _capture_recorder(rc=1)
    call, _ = _token_main(monkeypatch, admin, capture=capture)
    assert call("--target", "stable", "--region", "eu", "--rotate") == 1
    err = capsys.readouterr().err
    assert "writing ROOT_API_TOKEN_EU" in err
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


def test_a_rate_limit_or_fault_on_the_password_challenge_is_not_a_refused_code(account_factory):
    """6ff21f1b.2: a 429 or 5xx on 2fa/verify is a fault to rerun later, never a refused code to retry from the next window."""
    first = account_factory(set(), verify_statuses=(429,))
    now, sleep, slept = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="HTTP 429: a rate-limit or server fault"):
        root_login.open_session(first.origin, _values(), now, sleep)
    assert [r for r, _ in first.bodies].count("2fa/verify") == 1
    assert slept == []
    # the second window's answer is judged the same way
    second = account_factory(set(), verify_statuses=(401, 503))
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="HTTP 503: a rate-limit or server fault"):
        root_login.open_session(second.origin, _values(), now, sleep)
    assert [r for r, _ in second.bodies].count("2fa/verify") == 2
    # control: a plain refusal twice is still the stale-seed message, not a fault
    plain = account_factory(set())
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError, match="refused in two consecutive"):
        root_login.open_session(plain.origin, _values(), now, sleep)


@pytest.mark.parametrize(
    ("payload", "quoted"),
    [
        (
            {"code": "CAPTCHA_REQUIRED", "message": "solve it"},
            "HTTP 400 CAPTCHA_REQUIRED: solve it",
        ),
        ({"error": 7, "message": "odd error field"}, "HTTP 400: odd error field"),
        ({"error": None, "code": "LOCKED"}, "HTTP 400 LOCKED"),
    ],
)
def test_a_login_refusal_without_an_error_object_reads_code_and_message_from_the_top(
    account_factory, payload, quoted
):
    """b2978e7c.2: the fallback reads `code` and `message` from the answer body when `error` is absent or neither an object nor a string."""
    account = account_factory(set(), login_status=400, login_payload=payload)
    now, sleep, _ = _now_sleep()
    with pytest.raises(root_login.RootLoginError) as caught:
        root_login.open_session(account.origin, _values(), now, sleep)
    assert quoted in str(caught.value)


def test_a_server_message_that_echoes_a_secret_is_masked_before_it_is_printed(
    account_factory, monkeypatch, capsys
):
    """b2978e7c.1: the server's message goes to a CI log, so the claim that it carries no secret is enforced by masking, not assumed."""
    echoed = {
        "error": {
            "code": "BAD",
            "message": "password %s and seed %s refused" % (PASSWORD, SEED),
        }
    }
    account = account_factory(set(), login_status=401, login_payload=echoed)
    monkeypatch.setattr(root_login, "origin_for", lambda *_: account.origin)
    monkeypatch.setattr(root_login, "_reexec_under_profile", lambda *_: None)
    for name, value in _values().items():
        monkeypatch.setenv(name, value)
    assert root_login.main(["--target", "edge", "--region", "eu", "--password"]) == 1
    err = capsys.readouterr().err
    assert "HTTP 401 BAD: password <ROOT_PASSWORD> and seed <ROOT_TOTP_SEED> refused" in err
    assert PASSWORD not in err
    assert SEED not in err
    # control: a message with no secret in it is quoted whole
    plain = account_factory(set(), login_status=401, login_error="bad password")
    monkeypatch.setattr(root_login, "origin_for", lambda *_: plain.origin)
    assert root_login.main(["--target", "edge", "--region", "eu", "--password"]) == 1
    assert "HTTP 401: bad password" in capsys.readouterr().err


def test_masked_hides_a_secret_the_200_character_cut_would_split_and_any_root_token():
    env = {"ROOT_PASSWORD": "p" * 190 + "SECRETTAIL", "ROOT_API_TOKEN_US": "rdr_" + "ab" * 32}
    described = root_login._describe(
        401, {"error": {"code": "X", "message": "m" + env["ROOT_PASSWORD"]}}, env
    )
    assert "SECRET" not in described
    assert "<ROOT_PASSWORD>" in described
    assert root_login.masked("sent rdr_0123abcd and more", {}) == "sent <root token> and more"
    placeholder = {"ROOT_PASSWORD": root_login.PLACEHOLDER}
    assert root_login.masked(root_login.PLACEHOLDER, placeholder) == root_login.PLACEHOLDER


class _Truncating:
    """A server that promises a body and closes after one byte: http.client raises IncompleteRead, an HTTPException that is no OSError."""

    def __init__(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _truncate(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"{")

            def do_GET(self):
                self._truncate()

            def do_POST(self):
                self._truncate()

            def do_DELETE(self):
                self._truncate()

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.origin = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_a_truncated_answer_is_a_named_refusal_not_a_traceback():
    """91e01289.1: IncompleteRead is an HTTPException, not an OSError; it used to escape main as a traceback."""
    server = _Truncating()
    try:
        now, sleep, _ = _now_sleep()
        with pytest.raises(
            root_login.RootLoginError, match=r"POST .*login reached no answer \(IncompleteRead\)"
        ):
            root_login.open_session(server.origin, _values(), now, sleep)
        with pytest.raises(
            root_login.RootLoginError,
            match=r"GET .*admin/stats reached no answer \(IncompleteRead\)",
        ):
            root_login.AdminClient(server.origin, "rdr_" + "00" * 32).get("/admin/stats")
    finally:
        server.close()

"""rediacc_ci.ops.root_login against a fake account server: the challenge answered, a wrong code refused, a missing value refused naming its entry, and no secret ever printed."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rediacc_ci.ops import root_login, totp

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
        cookie: bool = True,
    ):
        self.accept = accept
        self.two_factor = two_factor
        self.login_status = login_status
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
    assert root_login.parse_args(["--target", "edge", "--region", "us"]) == ("edge", "us")
    for bad in (["--target", "bench", "--region", "eu"], ["--target", "edge"], ["--x"]):
        with pytest.raises(root_login.RootLoginError) as caught:
            root_login.parse_args(bad)
        assert caught.value.rc == 2
    assert root_login.origin_for("stable", "eu") == root_login.origin_for("edge", "eu")
    assert root_login.origin_for("edge", "eu") == "https://eu.rediacc.cloud"


def test_main_prints_only_the_fact_never_a_secret(account_factory, monkeypatch, capsys):
    good = totp.code(SEED, at=CLOCK)
    account = account_factory({good})
    _pin_clock(monkeypatch, account)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", root_login.PROFILE)
    for name, value in _values().items():
        monkeypatch.setenv(name, value)
    assert root_login.main(["--target", "edge", "--region", "eu"]) == 0
    out, err = capsys.readouterr()
    assert out.strip() == "root session opened (edge eu)"
    for secret in (PASSWORD, SEED, good, SESSION, CHALLENGE):
        assert secret not in out + err


def test_failure_output_never_carries_a_secret(account_factory, monkeypatch, capsys):
    account = account_factory(set())
    _pin_clock(monkeypatch, account)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", root_login.PROFILE)
    for name, value in _values().items():
        monkeypatch.setenv(name, value)
    assert root_login.main(["--target", "stable", "--region", "eu"]) == 1
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

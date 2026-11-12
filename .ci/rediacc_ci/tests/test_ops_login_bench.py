"""rediacc_ci.ops.login_bench with a fake runner: bench-only refusals, placeholder refusals, and no secret on any child's argv."""

import base64
import json

import pytest

from rediacc_ci.ops import login_bench, totp
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN, BENCH_ORIGIN, SITE_ORIGIN

SEED = base64.b32encode(b"bench-seed-0123456789").decode().rstrip("=")
VALUES = {
    login_bench.EMAIL_ENV: "operator@example.invalid",
    login_bench.PW_ENV: "pw-Secret-31337",
    login_bench.TOTP_SEED_ENV: SEED,
    login_bench.MASTER_PW_ENV: "store-Secret-4242",
}
NEW_SEED = base64.b32encode(b"enrolled-seed-9876543").decode().rstrip("=")
FIXED_NOW = 1_800_000_010.0  # 20 s left in the window


class FakeRunner:
    def __init__(self, fail_at: int | None = None, enable: tuple[int, str] = (0, "")):
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.captured: list[tuple[list[str], dict[str, str]]] = []
        self.fail_at = fail_at
        self.enable = enable

    def __call__(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        return 7 if self.fail_at == len(self.calls) - 1 else 0

    def capture(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        self.captured.append((list(argv), dict(env)))
        return self.enable


def _env(**overrides):
    env = {
        "PATH": "/usr/bin",
        "RDC_DEV": "1",
        "REDIACC_CONFIG": "dev",
        "REDIACC_TOKEN": "tok-inherited",
        "REDIACC_ACCOUNT_SERVER": "http://localhost:1",
        **VALUES,
    }
    env.update(overrides)
    return env


class FakeApi:
    """The account's /auth routes: a TOTP challenge by default, `challenge=False` for an account with TOTP off."""

    def __init__(
        self,
        challenge: bool = True,
        verify: int = 200,
        fail: dict | None = None,
        satisfied: bool = True,
        accept_records: bool = True,
        status_body: dict | None = None,
        reread_status: int = 0,
        reread_body: dict | None = None,
    ):
        self.calls: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.satisfied = satisfied
        self.accept_records = accept_records
        self.status_body = status_body
        self.reread_status = reread_status
        self.reread_body = reread_body
        self.challenge = challenge
        self.verify = verify
        self.fail = fail or {}

    def get(self, route):
        self.gets.append(route)
        if self.reread_status and len(self.gets) > 1:
            return self.reread_status, {}
        if self.reread_body is not None and len(self.gets) > 1:
            return 200, self.reread_body
        if route in self.fail:
            return self.fail[route], {}
        if self.status_body is not None:
            return 200, self.status_body
        return 200, {
            "satisfied": self.satisfied,
            "current": {"version": "2026-11-11", "sha256": "a" * 64},
        }

    def post(self, route, body=None):
        self.calls.append((route, dict(body or {})))
        if route in self.fail:
            return self.fail[route], {}
        if route == "login":
            if self.challenge:
                return 200, {"requiresTwoFactor": True, "challengeToken": "chal-1"}
            return 200, {"user": {"id": "u"}}
        if route == "2fa/verify":
            return self.verify, {}
        if route == "2fa/setup":
            return 200, {"secret": NEW_SEED, "uri": "otpauth://x"}
        if route == "/account/api/v1/portal/terms/accept":
            self.satisfied = self.accept_records
            return 201, {}
        if route == "2fa/enable":
            return 200, {"enabled": True, "backupCodes": ["bk-1111"]}
        return 200, {}


def _login(runner, argv=(), env=None, api=None):
    login_bench.login(
        list(argv),
        env or _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
        api=api or FakeApi(),
    )


def _secrets(env) -> list[str]:
    code = totp.code(SEED, at=FIXED_NOW)
    return [*VALUES.values(), code, env.get("REDIACC_TOKEN", "")]


# ---- bench-only ---------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--server", SITE_ORIGIN],
        ["--server=" + ACCOUNT_DEFAULT_ORIGIN],
        ["--server", BENCH_ORIGIN.replace("https:", "http:")],
        ["--server", BENCH_ORIGIN + ".evil.invalid"],
    ],
)
def test_another_server_is_refused_with_rc_2_before_any_child(argv, capsys):
    runner = FakeRunner()
    assert login_bench.main(argv, runner) == 2
    assert runner.calls == []
    assert "refuses server" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv", [["--config", "eu-edge"], ["--config=rediacc"], ["--config", "dev"]]
)
def test_another_config_is_refused_with_rc_2_before_any_child(argv, capsys):
    runner = FakeRunner()
    assert login_bench.main(argv, runner) == 2
    assert runner.calls == []
    assert "refuses config" in capsys.readouterr().err


def test_an_unknown_argument_is_refused():
    runner = FakeRunner()
    assert login_bench.main(["--password", "x"], runner) == 2
    assert runner.calls == []


def test_the_explicit_bench_target_is_accepted():
    assert login_bench.parse_args(["--server", BENCH_ORIGIN + "/", "--config", "eu-bench"]) == (
        login_bench.SERVER,
        login_bench.CONFIG,
    )
    assert login_bench.SERVER == BENCH_ORIGIN


# ---- the profile ---------------------------------------------------------------


def test_unbound_it_reexecutes_under_the_bench_login_profile(monkeypatch):
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    for name in VALUES:
        monkeypatch.delenv(name, raising=False)
    runner = FakeRunner()
    assert login_bench.main([], runner) == 0
    assert len(runner.calls) == 1
    argv = runner.calls[0][0]
    assert argv[1:6] == ["-m", "rediacc_ci.core.bws_env", "exec", "--profile", "bench-login"]
    assert argv[-2:] == ["-m", "rediacc_ci.ops.login_bench"]


# ---- placeholder and missing values ---------------------------------------------


@pytest.mark.parametrize("name", login_bench.SOURCE_NAMES)
def test_a_placeholder_value_is_refused_naming_its_bitwarden_entry(name):
    runner = FakeRunner()
    with pytest.raises(login_bench.LoginError) as caught:
        _login(runner, env=_env(**{name: login_bench.PLACEHOLDER}))
    assert caught.value.rc == 2
    assert name in str(caught.value)
    assert "PLACEHOLDER-operator-fills" in str(caught.value)
    assert runner.calls == []


def test_the_refusal_names_the_entry_uuid():
    with pytest.raises(login_bench.LoginError) as caught:
        login_bench.read_values(_env(REDIACC_BENCH_PASSWORD=login_bench.PLACEHOLDER))
    assert "59049d02-7e18-46b7-a6fd-b4f0011b2ecc" in str(caught.value)


@pytest.mark.parametrize("name", login_bench.SOURCE_NAMES)
def test_a_missing_value_is_refused(name):
    env = _env()
    del env[name]
    runner = FakeRunner()
    with pytest.raises(login_bench.LoginError) as caught:
        _login(runner, env=env)
    assert caught.value.rc == 2
    assert name in str(caught.value)
    assert runner.calls == []


def test_a_bad_seed_is_refused_without_echoing_it():
    with pytest.raises(login_bench.LoginError) as caught:
        login_bench.read_values(_env(REDIACC_BENCH_TOTP_SEED="ABC18"))
    assert caught.value.rc == 2
    assert "ABC18" not in str(caught.value)


# ---- the run -------------------------------------------------------------------


def test_the_steps_run_in_order_against_bench_and_eu_bench():
    runner = FakeRunner()
    _login(runner)
    argvs = [argv for argv, _env_ in runner.calls]
    assert argvs[0][-3:] == ["-m", "rediacc_ci.ops.bench_access", "add-current"]
    assert argvs[1][1:] == [
        "--config",
        "eu-bench",
        "subscription",
        "login",
        "--server",
        BENCH_ORIGIN,
    ]
    assert argvs[2][1:] == [
        "--config",
        "eu-bench",
        "-o",
        "json",
        "config",
        "remote",
        "enable",
        "--master-password",
        "--config-id",
        login_bench.CONFIG_ID,
        "--api-url",
        BENCH_ORIGIN,
    ]
    assert argvs[3][1:] == ["--config", "eu-bench", "config", "remote", "status"]
    assert all(argv[0].endswith("/rdc.sh") for argv in argvs[1:])


def test_no_child_argv_holds_a_secret():
    runner = FakeRunner()
    env = _env()
    _login(runner, env=env)
    secrets = [s for s in _secrets(env) if s]
    for argv, _child_env in runner.calls + runner.captured:
        joined = "\0".join(argv)
        for secret in secrets:
            assert secret not in joined


def test_each_child_gets_only_its_own_values_by_name():
    runner = FakeRunner()
    _login(runner)
    access, login, enable, status = (child_env for _argv, child_env in runner.calls)
    # The probe spent the code of this window, so the CLI gets the next window's.
    code = totp.code(SEED, at=FIXED_NOW + 20.5)
    assert login["REDIACC_LOGIN_EMAIL"] == VALUES[login_bench.EMAIL_ENV]
    assert login["REDIACC_LOGIN_PASSWORD"] == VALUES[login_bench.PW_ENV]
    assert login["REDIACC_LOGIN_TOTP"] == code
    assert "REDIACC_STORE_MASTER_PASSWORD" not in login
    assert enable["REDIACC_STORE_MASTER_PASSWORD"] == VALUES[login_bench.MASTER_PW_ENV]
    assert "REDIACC_LOGIN_PASSWORD" not in enable
    for child in (access, login, enable, status):
        for name in login_bench.SOURCE_NAMES:
            assert name not in child
        for name in login_bench.SCRUBBED_SELECTORS:
            assert name not in child
    for child in (access, status):
        assert not set(child) & set(login_bench.CHILD_SECRET_NAMES)


def test_a_failed_step_names_itself_and_stops():
    runner = FakeRunner(fail_at=1)
    with pytest.raises(login_bench.LoginError) as caught:
        _login(runner)
    assert caught.value.rc == 1
    assert "subscription login" in str(caught.value)
    assert "exit 7" in str(caught.value)
    assert len(runner.calls) == 2


def test_nothing_secret_is_printed(capsys):
    runner = FakeRunner()
    env = _env()
    _login(runner, env=env)
    out, err = capsys.readouterr()
    for secret in _secrets(env):
        if secret:
            assert secret not in out + err


def test_the_code_comes_from_the_next_window_when_the_current_one_is_closing():
    clock = [1_800_000_028.0]  # 2 s left
    slept: list[float] = []

    def sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    code = login_bench.fresh_code(SEED, now=lambda: clock[0], sleep=sleep)
    assert slept
    assert slept[0] > 2
    assert code == totp.code(SEED, at=1_800_000_031.0)


ENABLE_REENROLLED = (0, "This device is enrolled again.\n")
ENABLE_REFUSED_CAN_OPEN = (
    2,
    json.dumps(
        {
            "success": False,
            "errors": [
                {
                    "code": "VALIDATION_ERROR",
                    "message": 'Config "eu-bench" is already linked to remote storage and this device can open it, so there is nothing to enable. To unlink it, run: rdc config remote disable',
                }
            ],
        }
    ),
)


def test_enable_always_runs_and_status_is_not_consulted():
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner)
    assert len(runner.captured) == 1
    assert "enable" in runner.captured[0][0]
    assert [argv[-1] for argv, _e in runner.calls].count("status") == 1
    assert runner.calls[-1][0][1:] == ["--config", "eu-bench", "config", "remote", "status"]


def test_enable_exit_0_reenroll_is_success():
    _login(FakeRunner(enable=ENABLE_REENROLLED))


def test_enable_refusal_that_the_device_can_open_it_is_success():
    runner = FakeRunner(enable=ENABLE_REFUSED_CAN_OPEN)
    _login(runner)
    assert runner.calls[-1][0][-1] == "status"


@pytest.mark.parametrize(
    "result",
    [
        (2, '{"success": false, "errors": [{"code": "VALIDATION_ERROR", "message": "bad flag"}]}'),
        (2, ""),
        (
            2,
            '{"success": false, "errors": [{"code": "VALIDATION_ERROR", "message": "Config \\"eu-bench\\" has no store, so there is nothing to enable."}]}',
        ),
        (2, "Config is linked, so there is nothing to enable."),
        (2, "not json: " + json.loads(ENABLE_REFUSED_CAN_OPEN[1])["errors"][0]["message"]),
        (1, ENABLE_REFUSED_CAN_OPEN[1]),
        (3, "boom"),
    ],
)
def test_any_other_enable_failure_is_a_login_error(result):
    runner = FakeRunner(enable=result)
    with pytest.raises(login_bench.LoginError) as caught:
        _login(runner)
    assert caught.value.rc == 1
    assert "config remote enable" in str(caught.value)
    assert runner.calls[-1][0][-1] != "status"


def test_enable_non_json_exit_2_names_the_output():
    runner = FakeRunner(enable=(2, "plain text refusal"))
    with pytest.raises(login_bench.LoginError) as caught:
        _login(runner)
    assert "plain text refusal" in str(caught.value)


def test_enable_runs_json_and_pins_the_cli_language_to_english():
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner)
    argv, env = runner.captured[0]
    assert argv[argv.index("-o") + 1] == "json"
    assert env[login_bench.CLI_LANG_ENV] == "en"
    assert env["REDIACC_LANG"] == "en"


def test_enable_pins_english_over_an_inherited_locale():
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner, env=_env(REDIACC_LANG="de"))
    assert runner.captured[0][1]["REDIACC_LANG"] == "en"


# ---- whose step it is (operator order 2026-10-30) ----


@pytest.mark.parametrize(
    "text",
    [
        "The config token could not be renewed because this device's login is tied to another network address.",
        "Your IP address changed, and this login only works from the old one.",
        "Not logged in. Humans should run `rdc subscription login`.",
    ],
)
def test_the_cli_login_failures_read_as_login_needed(text):
    assert login_bench.login_needed(text)


def test_an_unrelated_failure_is_not_login_needed():
    assert not login_bench.login_needed("connection reset by peer")


@pytest.mark.parametrize(
    ("argv", "want"),
    [
        (["./rdc.sh", "--config", "eu-bench", "machine", "status", "hostinger"], True),
        (["./rdc.sh", "--config=eu-bench", "subscription", "status"], True),
        (["./rdc.sh", "--config", "eu-remote", "machine", "status", "hostinger"], False),
        (["./rdc.sh", "machine", "status", "eu-bench"], False),
        (["./rdc.sh", "--config"], False),
    ],
)
def test_targets_config_reads_only_the_eu_bench_selection(argv, want):
    assert login_bench.targets_config(argv) is want


def test_the_remedy_is_the_npm_script():
    assert login_bench.REMEDY == "npm run login:bench"
    assert login_bench.REMEDY_ARGV[-1] == "login:bench"
    scripts = json.loads(
        (login_bench.paths.repo_root() / "package.json").read_text(encoding="utf-8")
    )["scripts"]
    assert "rediacc_ci.ops.login_bench" in scripts["login:bench"]


# ---- the two-factor probe and the re-enrolment -------------------------------------


class EnrolCapture:
    """capture() for a run that re-enrols: the mail-token child and the bws writer, recorded, plus the enable answer."""

    def __init__(self, runner, mail_value="tok-reauth-1", write_rc=0):
        self.runner = runner
        self.mail_value = mail_value
        self.write_rc = write_rc
        self.order: list[str] = []
        self.envs: list[dict] = []

    def __call__(self, argv, env):
        argv = list(argv)
        if "store-from-env" in argv:
            self.order.append("bws")
            self.envs.append(dict(env))
            return self.write_rc, "REDIACC_BENCH_TOTP_SEED MATCH\n"
        if login_bench.MAIL_MODE in argv:
            self.order.append("mail")
            self.envs.append(dict(env))
            return 0, self.mail_value + "\n"
        return self.runner.capture(argv, env)


def _enrol_login(api, cap=None, env=None, runner=None):
    runner = runner or (cap.runner if cap else FakeRunner())
    cap = cap or EnrolCapture(runner)
    login_bench.login(
        [],
        env or _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=cap,
        api=api,
    )
    return runner, cap


def test_a_challenge_takes_the_normal_path_and_never_enrols():
    api = FakeApi(challenge=True)
    runner, cap = _enrol_login(api)
    assert [r for r, _b in api.calls] == ["login", "2fa/verify"]
    assert api.calls[1][1] == {"challengeToken": "chal-1", "code": totp.code(SEED, at=FIXED_NOW)}
    assert cap.order == []
    assert len(runner.calls) == 4


def test_no_challenge_enrols_through_setup_store_and_enable_in_order():
    api = FakeApi(challenge=False)
    runner, cap = _enrol_login(api)
    assert [r for r, _b in api.calls] == [
        "login",
        "reauth",
        "reauth/verify",
        "2fa/setup",
        "2fa/enable",
    ]
    assert api.calls[2][1] == {"token": "tok-reauth-1"}
    assert api.calls[4][1] == {"code": totp.code(NEW_SEED, at=FIXED_NOW)}
    assert cap.order == ["mail", "bws"]
    assert cap.envs[1][login_bench.TOTP_SEED_NEW_ENV] == NEW_SEED
    # The CLI login uses the NEW seed, from a window after the one enable spent.
    login_env = runner.calls[1][1]
    assert login_env["REDIACC_LOGIN_TOTP"] == totp.code(NEW_SEED, at=FIXED_NOW + 20.5)


def test_the_seed_is_stored_before_it_is_enabled():
    seen: list[str] = []

    class Api(FakeApi):
        def post(self, route, body=None):
            seen.append(route)
            return super().post(route, body)

    runner = FakeRunner()
    cap = EnrolCapture(runner)
    inner = cap.__call__

    def capture(argv, env):
        if "store-from-env" in argv:
            seen.append("bws")
        return inner(argv, env)

    login_bench.login(
        [],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=capture,
        api=Api(challenge=False),
    )
    assert seen.index("2fa/setup") < seen.index("bws") < seen.index("2fa/enable")


def test_a_failed_bws_write_stops_before_enable():
    api = FakeApi(challenge=False)
    runner = FakeRunner()
    cap = EnrolCapture(runner, write_rc=1)
    with pytest.raises(login_bench.LoginError) as caught:
        _enrol_login(api, cap)
    assert "TOTP stays off" in str(caught.value)
    assert "2fa/enable" not in [r for r, _b in api.calls]


def test_the_writer_argv_carries_names_never_the_seed(capsys):
    api = FakeApi(challenge=False)
    captured: list[list[str]] = []
    runner = FakeRunner()
    cap = EnrolCapture(runner)

    def capture(argv, env):
        captured.append(list(argv))
        return cap(argv, env)

    login_bench.login(
        [],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=capture,
        api=api,
    )
    write = next(a for a in captured if "store-from-env" in a)
    assert write[-1] == "REDIACC_BENCH_TOTP_SEED > REDIACC_BENCH_TOTP_SEED_NEW"
    out, err = capsys.readouterr()
    for secret in (NEW_SEED, SEED, "bk-1111", "tok-reauth-1", VALUES[login_bench.PW_ENV]):
        assert secret not in out + err
        assert all(secret not in "\0".join(a) for a in captured)
        assert all(secret not in "\0".join(a) for a, _e in runner.calls)


def test_a_refused_code_is_the_stale_seed_refusal_and_does_not_loop():
    api = FakeApi(challenge=True, verify=400)
    runner = FakeRunner()
    with pytest.raises(login_bench.LoginError) as caught:
        _enrol_login(api, EnrolCapture(runner))
    message = str(caught.value)
    assert "stale" in message
    assert "REDIACC_BENCH_TOTP_SEED" in message
    assert SEED not in message
    assert [r for r, _b in api.calls] == ["login", "2fa/verify"]
    assert [a[-1] for a, _e in runner.calls] == ["add-current"]


def test_a_refused_password_stops_before_any_cli_login():
    api = FakeApi(fail={"login": 401})
    runner = FakeRunner()
    with pytest.raises(login_bench.LoginError) as caught:
        _enrol_login(api, EnrolCapture(runner))
    assert "401" in str(caught.value)
    assert len(runner.calls) == 1


def test_the_mail_mode_reads_only_a_reauth_token(monkeypatch, capsys):
    rows = [{"text_body": "open https://bench/account/reauth/verify?token=abc_DEF-1 now"}]
    seen: list[str] = []

    def fake_rows(sql):
        seen.append(sql)
        return rows

    monkeypatch.setattr(login_bench, "_d1_rows", fake_rows)
    assert login_bench.mail_token_main("o'x@example.invalid", "2026-11-11T10:00:00") == 0
    assert capsys.readouterr().out == "abc_DEF-1\n"
    assert "kind = 'reauth'" in seen[0]
    assert "'o''x@example.invalid'" in seen[0]


def test_control_a_satisfied_account_accepts_nothing():
    api = FakeApi(satisfied=True)
    _login(FakeRunner(), api=api)
    assert api.gets == [login_bench.TERMS_STATUS]
    assert login_bench.TERMS_ACCEPT not in [route for route, _ in api.calls]


def test_an_unaccepted_bench_account_accepts_the_version_the_server_reports():
    api = FakeApi(satisfied=False)
    runner = FakeRunner()
    _login(runner, api=api)
    routes = [route for route, _ in api.calls]
    assert routes.index("2fa/verify") < routes.index(login_bench.TERMS_ACCEPT)
    body = dict(api.calls)[login_bench.TERMS_ACCEPT]
    assert body == {
        "version": "2026-11-11",
        "sha256": "a" * 64,
        "locale": "en",
        "method": "web-checkbox",
    }
    # The CLI login runs only after the acceptance.
    assert any("login" in call[0] for call in runner.calls)


def test_an_unreadable_terms_status_or_a_refused_accept_stops_the_run():
    with pytest.raises(login_bench.LoginError, match="Terms status is unreadable"):
        _login(FakeRunner(), api=FakeApi(fail={login_bench.TERMS_STATUS: 500}))
    with pytest.raises(login_bench.LoginError, match="acceptance was refused"):
        _login(
            FakeRunner(),
            api=FakeApi(satisfied=False, fail={login_bench.TERMS_ACCEPT: 403}),
        )


def test_a_status_without_a_boolean_satisfied_accepts_nothing():
    api = FakeApi(status_body={"current": {"version": "2026-11-11", "sha256": "a" * 64}})
    with pytest.raises(login_bench.LoginError, match="no boolean `satisfied`"):
        _login(FakeRunner(), api=api)
    assert login_bench.TERMS_ACCEPT not in [route for route, _ in api.calls]


def test_an_accept_the_status_does_not_reflect_stops_the_run():
    api = FakeApi(satisfied=False, accept_records=False)
    with pytest.raises(
        login_bench.LoginError, match="does not report version 2026-11-11 satisfied"
    ):
        _login(FakeRunner(), api=api)
    assert api.gets == [login_bench.TERMS_STATUS, login_bench.TERMS_STATUS]


def test_a_failed_reread_after_the_accept_stops_the_run_and_says_so():
    api = FakeApi(satisfied=False, reread_status=503)
    with pytest.raises(login_bench.LoginError, match=r"re-read GET .* answered HTTP 503"):
        _login(FakeRunner(), api=api)


def test_a_reread_satisfied_for_another_version_stops_the_run():
    api = FakeApi(
        satisfied=False,
        reread_body={"satisfied": True, "current": {"version": "2026-12-01", "sha256": "b" * 64}},
    )
    with pytest.raises(login_bench.LoginError, match="it reports '2026-12-01'"):
        _login(FakeRunner(), api=api)

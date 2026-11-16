"""rediacc_ci.ops.login_bench with a fake runner: bench-only refusals, placeholder refusals, and no secret on any child's argv."""

import base64
import json
from typing import ClassVar

import pytest

from rediacc_ci.enterprise import lab
from rediacc_ci.ops import bench_preflight, login_bench, totp
from rediacc_ci.well_known import (
    ACCOUNT_DEFAULT_ORIGIN,
    BENCH_ORIGIN,
    BENCH_RETIRING_ORIGIN,
    PRODUCT_DOMAIN,
    SITE_ORIGIN,
)

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
    def __init__(
        self,
        fail_at: int | None = None,
        enable: tuple[int, str] | list[tuple[int, str]] = (0, ""),
    ):
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
        if isinstance(self.enable, list):
            return self.enable[min(len(self.captured), len(self.enable)) - 1]
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


STORE_MADE = {"store": {"id": "store-1"}, "initialToken": "tok-initial"}


def fake_crypto(request):
    """The product helper's `setup` answer: a request body, and the CEK that never leaves the helper."""
    assert request["op"] == "setup"
    return {"body": {"slots": [{"kind": "password"}], "from": request["password"]}, "cek": "cek-1"}


class FakeApi:
    """The account's /auth routes: a TOTP challenge by default, `challenge=False` for an account with TOTP off."""

    def __init__(
        self,
        challenge: bool = True,
        verify: int | list[int] = 200,
        fail: dict | None = None,
        satisfied: bool = True,
        accept_records: bool = True,
        status_body: dict | None = None,
        reread_status: int = 0,
        reread_body: dict | None = None,
        setup: tuple[int, dict] | None = None,
    ):
        self.calls: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.satisfied = satisfied
        self.accept_records = accept_records
        self.status_body = status_body
        self.reread_status = reread_status
        self.reread_body = reread_body
        self.challenge = challenge
        self.setup = setup if setup is not None else (201, STORE_MADE)
        self.verify = list(verify) if isinstance(verify, list) else [verify]
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
            index = sum(1 for r, _b in self.calls if r == "2fa/verify") - 1
            return self.verify[min(index, len(self.verify) - 1)], {}
        if route == "2fa/setup":
            return 200, {"secret": NEW_SEED, "uri": "otpauth://x"}
        if route == "/account/api/v1/portal/terms/accept":
            self.satisfied = self.accept_records
            return 201, {}
        if route == login_bench.STORE_SETUP_PATH:
            return self.setup
        if route == "2fa/enable":
            return 200, {"enabled": True, "backupCodes": ["bk-1111"]}
        return 200, {}


def _login(runner, argv=(), env=None, api=None, linked=None):
    login_bench.login(
        list(argv),
        env or _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
        api=api or FakeApi(),
        crypto=fake_crypto,
        config_exists=lambda _c, _e: True,
        linked_url=lambda _c, _e: linked,
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
    assert argv[1:6] == ["-m", "rediacc_ci.core.bws_env", "exec", "--profile", "bench-login-eu"]
    assert argv[-2:] == ["-m", "rediacc_ci.ops.login_bench"]


def test_unbound_a_us_run_reexecutes_under_the_us_login_profile(monkeypatch):
    """`bench-login-eu` binds the eu bench's password and seed; a us run under it signed in to bench-us with the eu credentials."""
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    runner = FakeRunner()
    assert login_bench.main(["--region", "us"], runner) == 0
    argv = runner.calls[0][0]
    assert argv[argv.index("--profile") + 1] == "bench-login-us"
    assert argv[-2:] == ["--region", "us"]


def test_another_benchs_login_profile_bound_is_refused(monkeypatch):
    """`bws_env exec` keeps a name already set, so nesting bench-login-us under bench-login-eu would keep the eu values."""
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "bench-login-eu")
    with pytest.raises(
        login_bench.LoginError, match="refuses to run under bench-login-eu"
    ) as caught:
        login_bench._reexec_under_profile(["--region", "us"], FakeRunner(), "us")
    assert caught.value.rc == 2


def test_the_home_profile_bound_runs_an_eu_login_in_place(monkeypatch):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "bench-login-eu")
    assert login_bench._reexec_under_profile([], FakeRunner(), "eu") is None


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


def test_the_refusal_names_the_regions_own_entry_and_its_uuid():
    with pytest.raises(login_bench.LoginError) as caught:
        login_bench.read_values(_env(BENCH_ROOT_PASSWORD=login_bench.PLACEHOLDER), "us")
    assert "BENCH_ROOT_PASSWORD_US (%s)" % "f3cd94c2-486a-4d0f-86ee-b503012389d1" in str(
        caught.value
    )


def test_the_eu_refusal_names_the_eu_entry_not_the_unsuffixed_one():
    with pytest.raises(login_bench.LoginError) as caught:
        login_bench.read_values(_env(BENCH_ROOT_PASSWORD=login_bench.PLACEHOLDER))
    assert "BENCH_ROOT_PASSWORD_EU" in str(caught.value)


def test_the_unset_refusal_names_the_profile_of_its_region():
    env = _env()
    del env["BENCH_ROOT_PASSWORD"]
    with pytest.raises(login_bench.LoginError) as caught:
        login_bench.read_values(env, "asia")
    assert "bws_env exec --profile bench-login-asia" in str(caught.value)
    assert "BENCH_ROOT_PASSWORD_ASIA" in str(caught.value)


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
        login_bench.read_values(_env(BENCH_ROOT_TOTP_SEED="ABC18"))
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
        "--force",
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


def _argvs(runner):
    return [" ".join(argv) for argv, _e in runner.calls]


def test_a_config_linked_to_the_pre_rename_origin_is_unlinked_and_enabled_with_force():
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner, linked=BENCH_RETIRING_ORIGIN)
    calls = _argvs(runner)
    disable = [i for i, c in enumerate(calls) if c.endswith("config remote disable --local -y")]
    enable = [i for i, c in enumerate(calls) if "config remote enable" in c]
    assert len(disable) == 1
    assert len(enable) == 1
    assert disable[0] < enable[0]
    assert "--force" in calls[enable[0]].split()


def test_a_rerun_after_a_failed_enable_still_passes_force():
    """Run 1: linked elsewhere, `disable --local` ok, enable fails. Run 2: the config is now unlinked and enable still gets `--force`."""
    first = FakeRunner(enable=(1, "boom"))
    with pytest.raises(login_bench.LoginError):
        _login(first, linked=BENCH_RETIRING_ORIGIN)
    assert any(c.endswith("config remote disable --local -y") for c in _argvs(first))
    second = FakeRunner(enable=ENABLE_REENROLLED)
    _login(second, linked=None)
    enable = [c for c in _argvs(second) if "config remote enable" in c]
    assert len(enable) == 1
    assert "--force" in enable[0].split()


def test_an_unlinked_config_is_enabled_with_force_and_not_disabled():
    """A rerun after a failed enable finds the config unlinked (the earlier `disable --local` stuck): it still gets `--force`."""
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner, linked=None)
    calls = _argvs(runner)
    assert not any("remote disable" in c for c in calls)
    enable = [c for c in calls if "config remote enable" in c]
    assert len(enable) == 1
    assert "--force" in enable[0].split()


@pytest.mark.parametrize("linked", [BENCH_ORIGIN, BENCH_ORIGIN + "/"])
def test_a_config_already_on_the_target_gets_neither_disable_nor_force(linked):
    runner = FakeRunner(enable=ENABLE_REENROLLED)
    _login(runner, linked=linked)
    calls = _argvs(runner)
    assert not any("remote disable" in c for c in calls)
    assert not any("--force" in c.split() for c in calls)


def test_linked_api_url_reads_the_remote_pointer_and_refuses_a_broken_file(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert login_bench.linked_api_url("eu-bench", env) is None
    d = tmp_path / login_bench.CONFIG_DIR_NAME
    d.mkdir()
    (d / "eu-bench.json").write_text(json.dumps({"remote": {"apiUrl": BENCH_RETIRING_ORIGIN}}))
    assert login_bench.linked_api_url("eu-bench", env) == BENCH_RETIRING_ORIGIN
    (d / "eu-bench.json").write_text('{"account": {}}')
    assert login_bench.linked_api_url("eu-bench", env) is None
    (d / "eu-bench.json").write_text("{not json")
    with pytest.raises(login_bench.LoginError, match=r"eu-bench\.json"):
        login_bench.linked_api_url("eu-bench", env)


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
            return self.write_rc, "BENCH_ROOT_TOTP_SEED MATCH\n"
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
        crypto=fake_crypto,
        config_exists=lambda _c, _e: True,
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
    assert write[-1] == "BENCH_ROOT_TOTP_SEED_EU > BENCH_ROOT_TOTP_SEED_NEW"
    mail = next(a for a in captured if login_bench.MAIL_MODE in a)
    assert mail[mail.index("--profile") + 1] == "deploy-bench-eu"
    out, err = capsys.readouterr()
    for secret in (NEW_SEED, SEED, "bk-1111", "tok-reauth-1", VALUES[login_bench.PW_ENV]):
        assert secret not in out + err
        assert all(secret not in "\0".join(a) for a in captured)
        assert all(secret not in "\0".join(a) for a, _e in runner.calls)


def _ticking_login(api, runner):
    clock = [FIXED_NOW]

    def sleep(seconds):
        clock[0] += seconds

    login_bench.login(
        [],
        _env(),
        runner,
        now=lambda: clock[0],
        sleep=sleep,
        capture=EnrolCapture(runner),
        api=api,
    )


def test_a_refused_code_is_retried_once_in_the_next_window():
    api = FakeApi(challenge=True, verify=[400, 200])
    runner = FakeRunner()
    _ticking_login(api, runner)
    assert [r for r, _b in api.calls if r in ("login", "2fa/verify")] == [
        "login",
        "2fa/verify",
        "2fa/verify",
    ]
    first, second = [b for r, b in api.calls if r == "2fa/verify"]
    assert first["challengeToken"] == second["challengeToken"] == "chal-1"
    assert first["code"] == totp.code(SEED, at=FIXED_NOW)
    assert second["code"] == totp.code(SEED, at=FIXED_NOW + 30)
    assert first["code"] != second["code"]


def test_two_refused_windows_are_the_stale_seed_refusal_and_do_not_loop():
    api = FakeApi(challenge=True, verify=400)
    runner = FakeRunner()
    with pytest.raises(login_bench.LoginError) as caught:
        _ticking_login(api, runner)
    message = str(caught.value)
    assert "stale" in message
    assert "two consecutive 30 s windows" in message
    assert "BENCH_ROOT_TOTP_SEED" in message
    assert SEED not in message
    assert [r for r, _b in api.calls] == ["login", "2fa/verify", "2fa/verify"]
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

    def fake_rows(sql, _target=None):
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


def test_a_server_fault_on_verify_is_not_called_a_stale_seed():
    """38201847.1 and a316d763.2: 5xx and 429 name a fault, never the stale-seed refusal."""
    for status in (500, 429):
        api = FakeApi(challenge=True, verify=status)
        with pytest.raises(login_bench.LoginError) as caught:
            _ticking_login(api, FakeRunner())
        assert "stale" not in str(caught.value)
        assert "fault" in str(caught.value)
        assert [r for r, _b in api.calls].count("2fa/verify") == 1
    # A fault on the retry is reported as a fault too.
    api = FakeApi(challenge=True, verify=[400, 503])
    with pytest.raises(login_bench.LoginError, match="HTTP 503: a rate-limit or server fault"):
        _ticking_login(api, FakeRunner())


def test_a_two_factor_answer_without_a_challenge_never_re_enrols():
    """a316d763.1: requiresTwoFactor with no challengeToken is refused before reauth or 2fa/setup."""

    class Odd(FakeApi):
        def post(self, route, body=None):
            if route == "login":
                self.calls.append((route, {}))
                return 200, {"requiresTwoFactor": True}
            return super().post(route, body)

    api = Odd()
    with pytest.raises(login_bench.LoginError, match="named no challengeToken"):
        _enrol_login(api)
    assert [r for r, _b in api.calls] == ["login"]


@pytest.mark.parametrize("route", ["reauth", "reauth/verify", "2fa/setup", "2fa/enable"])
def test_a_non_200_on_each_enrolment_route_stops_the_run(route):
    """a316d763.3: the failure path of every enrolment call."""
    api = FakeApi(challenge=False, fail={route: 500})
    with pytest.raises(login_bench.LoginError, match="HTTP 500"):
        _enrol_login(api)


class _Headers:
    def get_all(self, _name):
        return ["sid=abc; Path=/; HttpOnly"]


class _Resp:
    status = 200
    headers = _Headers()

    def read(self):
        return b'{"ok": true}'


class _Conn:
    seen: ClassVar[list[tuple]] = []

    def __init__(self, host, **_kw):
        self.host = host

    def request(self, method, path, payload, headers):
        _Conn.seen.append((method, path, payload, dict(headers)))

    def getresponse(self):
        return _Resp()

    def close(self):
        pass


def test_the_account_api_sends_the_cookie_it_was_given_and_reads_json(monkeypatch):
    """a316d763.3: the real AccountApi over a recorded connection."""
    _Conn.seen = []
    monkeypatch.setattr(login_bench.http.client, "HTTPSConnection", _Conn)
    api = login_bench.AccountApi("https://bench.example")
    assert api.post("login", {"a": 1}) == (200, {"ok": True})
    assert api.get("/account/api/v1/portal/terms") == (200, {"ok": True})
    assert "Cookie" not in _Conn.seen[0][3]
    assert _Conn.seen[1][3]["Cookie"] == "sid=abc"
    assert _Conn.seen[1][1] == "/account/api/v1/portal/terms"
    assert _Conn.seen[0][1].endswith("login")


def test_the_account_api_names_a_transport_failure(monkeypatch):
    class Dead(_Conn):
        def request(self, *_a):
            raise OSError("down")

    monkeypatch.setattr(login_bench.http.client, "HTTPSConnection", Dead)
    with pytest.raises(login_bench.LoginError, match="reached no answer"):
        login_bench.AccountApi("https://bench.example").post("login")


def test_the_d1_reader_needs_the_key_pair_and_parses_the_results(monkeypatch):
    monkeypatch.delenv("CF_GLOBAL_API_KEY", raising=False)
    monkeypatch.delenv("CF_EMAIL", raising=False)
    with pytest.raises(login_bench.LoginError, match="CF_GLOBAL_API_KEY"):
        login_bench._d1_rows("SELECT 1")
    monkeypatch.setenv("CF_GLOBAL_API_KEY", "k")
    monkeypatch.setenv("CF_EMAIL", "e@example.invalid")

    class Done:
        returncode = 0
        stdout = '[{"results": [{"text_body": "x"}, 5]}]'

    monkeypatch.setattr(login_bench.subprocess, "run", lambda *_a, **_k: Done())
    assert login_bench._d1_rows("SELECT 1") == [{"text_body": "x"}]
    Done.returncode = 1
    with pytest.raises(login_bench.LoginError, match="exit 1"):
        login_bench._d1_rows("SELECT 1")


# ---- the three benches (PLAN-multi-region-bench W5) -----------------------------


def _regions_bench() -> dict[str, dict]:
    doc = json.loads((login_bench.paths.repo_root() / "regions.json").read_text(encoding="utf-8"))
    return {row["id"]: row["bench"] for row in doc["regions"]}


def _bench_host(region: str) -> str:
    """The bench host regions.json names for `region`, through the registry reader every bench tool shares (`bench_preflight.bench_object`), so no test file carries its own copy of the parse."""
    return str(bench_preflight.bench_object(region)["host"])


def test_the_config_table_is_regions_json():
    bench = _regions_bench()
    assert {r: b["config"] for r, b in bench.items()} == login_bench.REGION_CONFIGS
    assert set(login_bench.REGION_CONFIGS.values()) <= set(login_bench.BENCH_CONFIGS)
    assert "bench" in login_bench.BENCH_CONFIGS


@pytest.mark.parametrize("region", ["us", "asia"])
def test_a_regional_bench_targets_its_own_host_config_and_database(region):
    bench = _regions_bench()[region]
    target = login_bench.parse_target(["--region", region])
    assert target.server == "https://" + bench["host"]
    assert target.config == f"{region}-bench"
    assert target.d1_name == bench["d1"]["name"]
    assert target.d1_config == f"wrangler.bench-{region}.toml"
    assert target.config_id is None
    assert login_bench.parse_args([f"--region={region}"]) == (target.server, target.config)


def test_control_the_home_bench_is_unchanged():
    target = login_bench.parse_target([])
    assert (target.server, target.config, target.config_id) == (
        login_bench.SERVER,
        login_bench.CONFIG,
        login_bench.CONFIG_ID,
    )
    assert target == login_bench.parse_target(["--region", "eu"])
    bench = _regions_bench()["eu"]
    assert (target.d1_name, target.d1_config) == (bench["d1"]["name"], "wrangler.bench-eu.toml")


def test_a_config_name_selects_its_region():
    assert login_bench.parse_target(["--config", "us-bench"]).region == "us"
    assert login_bench.parse_target(["--config=asia-bench"]).region == "asia"


@pytest.mark.parametrize(
    "argv",
    [
        ["--region", "us", "--config", "eu-bench"],
        ["--region", "asia", "--server", BENCH_ORIGIN],
        ["--region", "us", "--server", "https://%s" % _bench_host("asia")],
        ["--region", "eu", "--config", "us-bench"],
    ],
)
def test_a_region_refuses_another_regions_server_or_config(argv, capsys):
    runner = FakeRunner()
    assert login_bench.main(argv, runner) == 2
    assert runner.calls == []
    assert "refuses" in capsys.readouterr().err


def test_an_unknown_region_is_refused_before_any_child(capsys):
    runner = FakeRunner()
    assert login_bench.main(["--region", "mars"], runner) == 2
    assert runner.calls == []
    assert "refuses region" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("config", "region"), [("eu-bench", "eu"), ("us-bench", "us"), ("asia-bench", "asia")]
)
def test_targets_config_reads_each_regional_selection(config, region):
    for argv in (["./rdc.sh", "--config", config, "x"], ["./rdc.sh", f"--config={config}"]):
        assert login_bench.targets_config(argv) is True
        assert login_bench.config_region(argv) == region
    assert login_bench.config_region(["./rdc.sh", "--config", "eu-remote"]) is None


def test_the_remedy_names_the_region_it_logs_in():
    assert login_bench.remedy_for("eu") == (
        "npm run login:bench -- --region eu",
        (*login_bench.REMEDY_ARGV, "--", "--region", "eu"),
    )
    text, argv = login_bench.remedy_for("us")
    assert text == "npm run login:bench -- --region us"
    assert argv[-3:] == ("--", "--region", "us")


def test_a_regional_login_runs_rdc_on_its_config_and_enables_without_a_config_id():
    runner = FakeRunner()
    login_bench.login(
        ["--region", "us"],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
        api=FakeApi(),
    )
    us = _regions_bench()["us"]
    rdc = [argv for argv, _ in runner.calls if "--config" in argv and "us-bench" in argv]
    assert rdc, runner.calls
    assert all("eu-bench" not in argv for argv, _ in runner.calls)
    login_argv = next(a for a in rdc if "login" in a)
    assert login_argv[-2:] == ["--server", "https://" + us["host"]]
    enable = next(a for a in rdc if "enable" in a)
    assert "--config-id" not in enable
    assert enable[-2:] == ["--api-url", "https://" + us["host"]]


def test_control_the_home_login_still_passes_its_config_id():
    runner = FakeRunner()
    login_bench.login(
        [],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
        api=FakeApi(),
    )
    enable = next(a for a, _ in runner.calls if "enable" in a)
    assert enable[enable.index("--config-id") + 1] == login_bench.CONFIG_ID


def test_the_mail_child_carries_its_region_for_every_region():
    class Cap:
        def __init__(self):
            self.argv = []

        def __call__(self, argv, _env):
            self.argv.append(list(argv))
            return 0, "tok-1\n"

    for region, tail in (("us", ["us"]), ("eu", ["eu"])):
        cap = Cap()
        login_bench._mail_token("o@example.invalid", "2026-11-11T10:00:00", {}, cap, region)
        want = [login_bench.MAIL_MODE, "2026-11-11T10:00:00", *tail]
        assert cap.argv[0][-len(want) :] == want
        assert len(cap.argv[0][cap.argv[0].index(login_bench.MAIL_MODE) :]) == len(want)


def test_the_mail_mode_reads_the_regional_database(monkeypatch, capsys):
    seen = []

    def fake_run(argv, **_k):
        seen.append(argv)

        class Done:
            returncode = 0
            stdout = '[{"results": [{"text_body": "go reauth/verify?token=abc_1 now"}]}]'

        return Done()

    monkeypatch.setenv("CF_GLOBAL_API_KEY", "k")
    monkeypatch.setenv("CF_EMAIL", "e@example.invalid")
    monkeypatch.setattr(login_bench.subprocess, "run", fake_run)
    assert login_bench.mail_token_main("o@example.invalid", "2026-11-11T10:00:00", "asia") == 0
    argv = seen[0]
    assert argv[argv.index("execute") + 1] == _regions_bench()["asia"]["d1"]["name"]
    assert argv[argv.index("--config") + 1] == "wrangler.bench-asia.toml"
    assert capsys.readouterr().out == "abc_1\n"


def test_a_us_reenrolment_writes_the_us_seed_entry_never_the_eu_one():
    """The re-enrolled seed went to BENCH_ROOT_TOTP_SEED whatever the region, overwriting the eu bench's seed with the us account's."""
    api = FakeApi(challenge=False)
    captured: list[list[str]] = []
    runner = FakeRunner()
    cap = EnrolCapture(runner)

    def capture(argv, env):
        captured.append(list(argv))
        return cap(argv, env)

    login_bench.login(
        ["--region", "us"],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=capture,
        api=api,
    )
    write = next(a for a in captured if "store-from-env" in a)
    assert write[-1] == "BENCH_ROOT_TOTP_SEED_US > BENCH_ROOT_TOTP_SEED_NEW"
    mail = next(a for a in captured if login_bench.MAIL_MODE in a)
    assert mail[mail.index("--profile") + 1] == "deploy-bench-us"


@pytest.mark.parametrize(
    ("region", "entry"),
    [
        ("eu", "BENCH_ROOT_TOTP_SEED_EU"),
        ("us", "BENCH_ROOT_TOTP_SEED_US"),
        ("asia", "BENCH_ROOT_TOTP_SEED_ASIA"),
    ],
)
def test_seed_entry_names_each_benchs_own_entry(region, entry):
    assert login_bench.seed_entry(region) == entry


# ---- a first link: the store is set up on the elevated session, and the rdc config is created ----------

NO_STORE = (
    1,
    json.dumps(
        {
            "success": False,
            "errors": [
                {
                    "code": "VALIDATION_ERROR",
                    "message": "Config storage is not configured for your organization. Set it up from the portal (Config Storage), then retry.",
                }
            ],
        }
    ),
)


def test_a_no_store_refusal_sets_the_store_up_on_an_elevated_session_and_enables_again():
    runner = FakeRunner(enable=[NO_STORE, ENABLE_REENROLLED])
    api = FakeApi()
    _enrol_login(api, runner=runner)
    routes = [r for r, _b in api.calls]
    assert routes == [
        "login",
        "2fa/verify",
        "reauth",
        "reauth/verify",
        login_bench.STORE_SETUP_PATH,
    ]
    assert api.calls[-1][1] == {
        "slots": [{"kind": "password"}],
        "from": VALUES[login_bench.MASTER_PW_ENV],
    }
    assert len(runner.captured) == 2
    assert runner.captured[0][0] == runner.captured[1][0]
    assert runner.calls[-1][0][-1] == "status"


def test_an_enable_that_settles_never_touches_the_store_setup():
    """Control: the same run without the refusal posts no setup and elevates nothing."""
    api = FakeApi()
    _enrol_login(api, runner=FakeRunner(enable=ENABLE_REENROLLED))
    assert login_bench.STORE_SETUP_PATH not in [r for r, _b in api.calls]
    assert "reauth" not in [r for r, _b in api.calls]


def test_a_refusal_that_is_not_the_missing_store_is_not_repaired():
    api = FakeApi()
    refused = (1, NO_STORE[1].replace("Config storage is not configured", "Device refused"))
    with pytest.raises(login_bench.LoginError) as caught:
        _enrol_login(api, runner=FakeRunner(enable=refused))
    assert caught.value.rc == 1
    assert login_bench.STORE_SETUP_PATH not in [r for r, _b in api.calls]


@pytest.mark.parametrize(
    "setup",
    [(200, STORE_MADE), (201, {"store": {"id": "s"}}), (201, {"initialToken": "t"}), (403, {})],
)
def test_a_store_setup_that_is_not_a_201_with_store_and_token_stops_the_run(setup):
    runner = FakeRunner(enable=[NO_STORE, ENABLE_REENROLLED])
    with pytest.raises(login_bench.LoginError, match="answered HTTP"):
        _enrol_login(FakeApi(setup=setup), runner=runner)
    assert len(runner.captured) == 1


def test_a_second_no_store_refusal_after_the_setup_is_a_login_error():
    runner = FakeRunner(enable=NO_STORE)
    with pytest.raises(login_bench.LoginError, match="config remote enable"):
        _enrol_login(FakeApi(), runner=runner)
    assert len(runner.captured) == 2


def test_a_setup_without_a_request_body_from_the_helper_is_refused():
    with pytest.raises(login_bench.LoginError, match="no request body"):
        login_bench.setup_store(FakeApi(), "pw", lambda _r: {})


def test_the_setup_path_is_the_labs():
    assert login_bench.STORE_SETUP_PATH == lab.SETUP_PATH


def test_a_missing_regional_config_is_created_before_the_subscription_login():
    runner = FakeRunner()
    login_bench.login(
        ["--region", "us"],
        _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
        api=FakeApi(),
        crypto=fake_crypto,
        config_exists=lambda _c, _e: False,
    )
    argvs = [argv for argv, _e in runner.calls]
    init = argvs[1]
    assert init[0].endswith("/rdc.sh")
    assert init[1:] == [
        "config",
        "init",
        "us-bench",
        "--server",
        "https://bench-us." + PRODUCT_DOMAIN,
    ]
    assert argvs[2][1:4] == ["--config", "us-bench", "subscription"]


def test_an_existing_config_is_not_initialised():
    """Control: the default fake world has the config, so no init runs."""
    runner = FakeRunner()
    _login(runner)
    assert all("init" not in argv for argv, _e in runner.calls)


def test_the_config_file_is_looked_up_under_xdg_then_home(tmp_path):
    (tmp_path / "rediacc").mkdir()
    (tmp_path / "rediacc" / "us-bench.json").write_text("{}", encoding="utf-8")
    assert login_bench.config_file_exists("us-bench", {"XDG_CONFIG_HOME": str(tmp_path)})
    assert not login_bench.config_file_exists("asia-bench", {"XDG_CONFIG_HOME": str(tmp_path)})
    home = tmp_path / "home"
    (home / ".config" / "rediacc").mkdir(parents=True)
    (home / ".config" / "rediacc" / "asia-bench.json").write_text("{}", encoding="utf-8")
    assert login_bench.config_file_exists("asia-bench", {"HOME": str(home)})


# --------------------------------------------------------------------------- review findings


def test_the_real_crypto_helper_answers_the_shape_setup_store_reads():
    """No fake: the product's own helper through tsx, so a renamed op or a changed return shape fails here and not in a live bench run."""
    answer = login_bench._default_crypto({"op": "setup", "password": "pw-test-0123456789"})
    assert isinstance(answer.get("body"), dict)
    assert answer["body"].get("slots")


def test_with_no_home_and_no_xdg_a_stray_relative_config_is_not_read(tmp_path, monkeypatch):
    stray = tmp_path / ".config" / "rediacc"
    stray.mkdir(parents=True)
    (stray / "eu-bench.json").write_text(json.dumps({"remote": {"apiUrl": "https://x"}}))
    monkeypatch.chdir(tmp_path)
    assert login_bench.config_file_exists("eu-bench", {}) is False
    assert login_bench.linked_api_url("eu-bench", {}) is None


def test_control_a_set_home_still_finds_its_config(tmp_path):
    cfg = tmp_path / ".config" / "rediacc"
    cfg.mkdir(parents=True)
    (cfg / "eu-bench.json").write_text(json.dumps({"remote": {"apiUrl": "https://x"}}))
    env = {"HOME": str(tmp_path)}
    assert login_bench.config_file_exists("eu-bench", env) is True
    assert login_bench.linked_api_url("eu-bench", env) == "https://x"

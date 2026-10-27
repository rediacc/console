"""rediacc_ci.ops.login_bench with a fake runner: bench-only refusals, placeholder refusals, and no secret on any child's argv."""

import base64
import json

import pytest

from rediacc_ci.ops import login_bench, totp

SEED = base64.b32encode(b"bench-seed-0123456789").decode().rstrip("=")
VALUES = {
    login_bench.EMAIL_ENV: "operator@example.invalid",
    login_bench.PW_ENV: "pw-Secret-31337",
    login_bench.TOTP_SEED_ENV: SEED,
    login_bench.STORE_PW_ENV: "store-Secret-4242",
}
FIXED_NOW = 1_800_000_010.0  # 20 s left in the window


class FakeRunner:
    def __init__(self, fail_at: int | None = None, status: tuple[int, str] = (1, "")):
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.captured: list[tuple[list[str], dict[str, str]]] = []
        self.fail_at = fail_at
        self.status = status

    def __call__(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        return 7 if self.fail_at == len(self.calls) - 1 else 0

    def capture(self, argv, env):
        self.captured.append((list(argv), dict(env)))
        return self.status


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


def _login(runner, argv=(), env=None):
    login_bench.login(
        list(argv),
        env or _env(),
        runner,
        now=lambda: FIXED_NOW,
        sleep=lambda _s: None,
        capture=runner.capture,
    )


def _secrets(env) -> list[str]:
    code = totp.code(SEED, at=FIXED_NOW)
    return [*VALUES.values(), code, env.get("REDIACC_TOKEN", "")]


# ---- bench-only ---------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--server", "https://www.rediacc.com"],
        ["--server=https://edge.rediacc.com"],
        ["--server", "http://bench.rediacc.com"],
        ["--server", "https://bench.rediacc.com.evil.invalid"],
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
    assert login_bench.parse_args(
        ["--server", "https://bench.rediacc.com/", "--config", "eu-bench"]
    ) == (login_bench.SERVER, login_bench.CONFIG)
    assert login_bench.SERVER == "https://bench.rediacc.com"


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
        "https://bench.rediacc.com",
    ]
    assert argvs[2][1:] == [
        "--config",
        "eu-bench",
        "config",
        "remote",
        "enable",
        "--password",
        "--config-id",
        login_bench.CONFIG_ID,
        "--api-url",
        "https://bench.rediacc.com",
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
    code = totp.code(SEED, at=FIXED_NOW)
    assert login["REDIACC_LOGIN_EMAIL"] == VALUES[login_bench.EMAIL_ENV]
    assert login["REDIACC_LOGIN_PASSWORD"] == VALUES[login_bench.PW_ENV]
    assert login["REDIACC_LOGIN_TOTP"] == code
    assert "REDIACC_CONFIG_PASSWORD" not in login
    assert enable["REDIACC_CONFIG_PASSWORD"] == VALUES[login_bench.STORE_PW_ENV]
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


def _status(
    config_id=login_bench.CONFIG_ID, api_url="https://bench.rediacc.com", status="connected"
):
    return (
        0,
        json.dumps(
            {
                "success": True,
                "data": {"status": status, "configId": config_id, "apiUrl": api_url},
            }
        ),
    )


def test_an_already_linked_config_skips_enable():
    runner = FakeRunner(status=_status())
    _login(runner)
    argvs = [argv for argv, _e in runner.calls]
    assert not any("enable" in argv for argv in argvs)
    assert argvs[-1][1:] == ["--config", "eu-bench", "config", "remote", "status"]
    assert len(runner.captured) == 1
    assert runner.captured[0][0][1:] == ["--config", "eu-bench", "config", "remote", "status"]
    assert not set(runner.captured[0][1]) & set(login_bench.CHILD_SECRET_NAMES)


@pytest.mark.parametrize(
    "status",
    [
        _status(config_id="00000000-0000-0000-0000-000000000000"),
        _status(api_url="https://www.rediacc.com"),
        _status(status="disconnected"),
        (2, ""),
        (0, "not json"),
    ],
)
def test_anything_but_this_link_runs_enable(status):
    runner = FakeRunner(status=status)
    _login(runner)
    assert any("enable" in argv for argv, _e in runner.calls)

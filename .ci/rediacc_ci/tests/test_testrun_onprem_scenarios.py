"""Tests for the on-premise scenario runner and its `smoke` and `daemon` suites, against a fake runtime: no stack, no CLI, no network."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.testrun import onprem_scenarios as mod
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import Result, failed, passed

if TYPE_CHECKING:
    import pathlib

TOKEN = "tok-secret-value"
OTHER = "tok-other-value"
DAEMON = "http://127.0.0.1:8480"
ACCOUNT_HEALTH = "http://127.0.0.1:4910/health"
TLS_URL = "https://127.0.0.1:8492/v1/server-info"
PLAIN_URL = "http://127.0.0.1:8492/v1/server-info"


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeRuntime(onprem_stack.Runtime):
    """Scripted CLI answers and HTTP answers; records every call."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []
        self.http: dict[str, tuple[int, str]] = {}
        self.listening: set[int] = set()
        self.rdc_rc: dict[str, int] = {}
        self.stdout: dict[str, str] = {}
        self.spawned: list[list[str]] = []
        self.killed: list[int] = []
        self.exit_codes: list[int | None] = []
        self.other_token_refused = False
        self.lsof = "node 1 u 3u IPv4 TCP 127.0.0.1:8480 (LISTEN)"

    def run(self, argv, env=None, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        del cwd, timeout  # the fake takes the real signature and ignores both
        self.calls.append((argv, env))
        if argv[0] == "lsof":
            return done(argv, 0 if self.lsof else 1, self.lsof)
        if self.other_token_refused and env and env.get("REDIACC_TOKEN") == OTHER:
            return done(argv, 1, "", "forbidden")
        joined = " ".join(argv)
        for key, rc in self.rdc_rc.items():
            if key in joined:
                return done(argv, rc, self.stdout.get(key, ""), "failure text" if rc else "")
        for key, out in self.stdout.items():
            if key in joined:
                return done(argv, 0, out)
        return done(argv)

    def http_get(self, url: str, *_unused) -> tuple[int, str]:
        return self.http.get(url, (0, ""))

    def port_answers(self, port: int) -> bool:
        return port in self.listening

    def spawn_group(self, argv, *_unused) -> int:
        self.spawned.append(argv)
        return 4242

    def exited(self, _pgid: int) -> int | None:
        return self.exit_codes.pop(0) if self.exit_codes else None

    def kill_group(self, pgid: int) -> None:
        self.killed.append(pgid)

    def sleep(self, _seconds: float) -> None:
        return


@pytest.fixture
def stack_env(tmp_path: pathlib.Path) -> pathlib.Path:
    for name, value in (("executor", TOKEN), ("other", OTHER)):
        (tmp_path / ("%s.token" % name)).write_text(value + "\n", encoding="utf-8")
    values = {
        "ONPREM_ACCOUNT_URL": "http://127.0.0.1:4910",
        "ONPREM_DAEMON_URL": DAEMON,
        "ONPREM_DAEMON_PORT": "8480",
        "ONPREM_DAEMON_HOME": str(tmp_path),
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_MACHINE_NAME": "onprem-1",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(tmp_path / "executor.token"),
        "ONPREM_OTHER_TOKEN_FILE": str(tmp_path / "other.token"),
    }
    path = tmp_path / "stack.env"
    path.write_text("".join("%s=%s\n" % kv for kv in values.items()), encoding="utf-8")
    return path


@pytest.fixture
def rt() -> FakeRuntime:
    runtime = FakeRuntime()
    runtime.http[ACCOUNT_HEALTH] = (200, "ok")
    runtime.http[DAEMON + "/v1/server-info"] = (200, '{"mode":"daemon"}')
    return runtime


@pytest.fixture
def lines() -> list[dict]:
    return []


def _main(rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict], *argv: str) -> int:
    return mod.main(
        [*argv, "--env", str(stack_env)], runtime=rt, root=stack_env.parent, emit=lines.append
    )


@pytest.fixture
def scratch(monkeypatch: pytest.MonkeyPatch) -> dict:
    """An empty registry the test fills, so the shipped suites do not run."""
    registry: dict = {}
    monkeypatch.setattr(onprem_suites, "SUITES", registry)
    return registry


def _verdict(lines: list[dict], name: str) -> dict:
    return next(line for line in lines if line["scenario"] == name)


# ── registration and verdict lines ──────────────────────────────────────────


def test_the_shipped_suites_register_their_scenarios() -> None:
    registry = onprem_suites.load_all()
    assert {"smoke", "daemon"} <= set(registry)
    assert {"account_health", "config_current", "repo_list", "machine_listed"} <= set(
        registry["smoke"]
    )
    assert "server_info_is_daemon" in registry["daemon"]
    assert registry["smoke"]["repo_list"].targets == ("onprem", "bench")
    assert registry["daemon"]["repo_list_through_daemon"].targets == ("onprem",)


@pytest.mark.usefixtures("scratch")
def test_a_duplicate_scenario_or_unknown_target_raises() -> None:
    def one(_ctx: object) -> Result:
        return passed()

    onprem_suites.scenario("t", "one")(one)
    with pytest.raises(ValueError, match="registered twice"):
        onprem_suites.scenario("t", "one")(one)
    with pytest.raises(ValueError, match="targets"):
        onprem_suites.scenario("t", "two", targets=("moon",))
    with pytest.raises(ValueError, match="targets"):
        onprem_suites.scenario("t", "three", targets=())


@pytest.mark.usefixtures("scratch")
def test_each_scenario_is_one_json_verdict_line(
    rt: FakeRuntime, stack_env: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    onprem_suites.scenario("t", "good")(lambda _ctx: passed("fine", 200))
    onprem_suites.scenario("t", "bad")(lambda _ctx: failed("nope", 7))
    assert (
        mod.main(["--suite", "t", "--env", str(stack_env)], runtime=rt, root=stack_env.parent) == 1
    )
    out = capsys.readouterr().out.splitlines()
    base = {"suite": "t", "target": "onprem"}
    assert [json.loads(line) for line in out] == [
        {**base, "scenario": "good", "ok": True, "code": 200, "detail": "fine"},
        {**base, "scenario": "bad", "ok": False, "code": 7, "detail": "nope"},
    ]


@pytest.mark.usefixtures("scratch")
def test_all_passing_is_exit_0(rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]) -> None:
    onprem_suites.scenario("t", "good")(lambda _ctx: passed())
    assert _main(rt, stack_env, lines, "--suite", "t") == 0
    assert lines[0]["ok"] is True


@pytest.mark.usefixtures("scratch")
def test_a_raising_scenario_is_a_failed_verdict_and_the_rest_still_run(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    def boom(ctx: mod.Context) -> Result:
        ctx.value("ONPREM_NO_SUCH_KEY")
        return passed()

    onprem_suites.scenario("t", "boom")(boom)
    onprem_suites.scenario("t", "after")(lambda _ctx: passed())
    assert _main(rt, stack_env, lines, "--suite", "t") == 1
    assert lines[0]["ok"] is False
    assert "KeyError" in lines[0]["detail"]
    assert lines[1]["scenario"] == "after"
    assert lines[1]["ok"] is True


@pytest.mark.usefixtures("scratch")
def test_token_values_never_reach_a_verdict(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    onprem_suites.scenario("t", "leak")(
        lambda ctx: failed("the server said %s" % ctx.token("executor"))
    )
    assert _main(rt, stack_env, lines, "--suite", "t") == 1
    assert TOKEN not in json.dumps(lines)
    assert "***" in lines[0]["detail"]


@pytest.mark.usefixtures("scratch")
def test_usage_errors_exit_2(rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]) -> None:
    onprem_suites.scenario("t", "good")(lambda _ctx: passed())
    assert _main(rt, stack_env, lines) == 2
    assert _main(rt, stack_env, lines, "--suite", "nope") == 2
    missing = str(stack_env.parent / "missing.env")
    assert mod.main(["--suite", "t", "--env", missing], runtime=rt) == 2


def test_a_suite_with_nothing_for_the_target_is_a_usage_error(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict], scratch: dict
) -> None:
    scratch["empty"] = {}
    assert _main(rt, stack_env, lines, "--suite", "empty") == 2


def test_list_prints_every_scenario(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    assert _main(rt, stack_env, lines, "--list") == 0
    names = {(line["suite"], line["scenario"]) for line in lines}
    assert ("smoke", "account_health") in names
    assert ("daemon", "other_org_token_refused") in names


# ── --compare ───────────────────────────────────────────────────────────────


def _both(onprem_result: Result, bench_result: Result) -> None:
    onprem_suites.scenario("t", "shared", targets=("onprem", "bench"))(
        lambda ctx: onprem_result if ctx.target == "onprem" else bench_result
    )


@pytest.mark.usefixtures("scratch")
def test_compare_passes_when_the_verdicts_and_codes_match(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    _both(passed("a", 0), passed("different words", 0))
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 0
    assert lines[0]["match"] is True


@pytest.mark.usefixtures("scratch")
def test_compare_fails_on_a_planted_code_mismatch(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    _both(passed("ok", 0), passed("ok", 3))
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 1
    assert lines[0]["match"] is False
    assert lines[0]["bench"]["code"] == 3


@pytest.mark.usefixtures("scratch")
def test_compare_fails_on_a_planted_verdict_mismatch(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    _both(passed("ok", 0), failed("bench broke", 0))
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 1


@pytest.mark.usefixtures("scratch")
def test_compare_lists_an_onprem_only_scenario_as_skipped(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    _both(passed(), passed())
    onprem_suites.scenario("t", "local")(lambda _ctx: failed("would fail"))
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 0
    assert {"compare": "t/local", "skipped": "onprem only"} in lines


@pytest.mark.usefixtures("scratch")
def test_an_empty_comparison_is_a_failure(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    onprem_suites.scenario("t", "local")(lambda _ctx: passed())
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 1


@pytest.mark.usefixtures("scratch")
def test_compare_runs_bench_against_the_bench_config(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    onprem_suites.scenario("t", "cfg", targets=("onprem", "bench"))(
        lambda ctx: passed(code=ctx.rdc("repo", "list").returncode)
    )
    assert _main(rt, stack_env, lines, "--suite", "t", "--compare", "bench") == 0
    configs = [argv[argv.index("--config") + 1] for argv, _ in rt.calls]
    assert configs == ["onprem-stack", "eu-bench"]
    onprem_env, bench_env = rt.calls[0][1], rt.calls[1][1]
    assert onprem_env is not None
    assert bench_env is not None
    assert onprem_env["REDIACC_ACCOUNT_SERVER"] == "http://127.0.0.1:4910"
    assert bench_env.get("REDIACC_ACCOUNT_SERVER") != "http://127.0.0.1:4910"


# ── the smoke suite ─────────────────────────────────────────────────────────


def test_smoke_passes_on_a_healthy_stack(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.stdout["config current"] = "Active config: onprem-stack"
    rt.stdout["machine list"] = '[{"name":"onprem-1"}]'
    assert _main(rt, stack_env, lines, "--suite", "smoke") == 0
    assert [line["scenario"] for line in lines] == [
        "account_health",
        "config_current",
        "repo_list",
        "machine_listed",
    ]


def test_smoke_fails_each_way(rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]) -> None:
    rt.http[ACCOUNT_HEALTH] = (503, "")
    rt.stdout["config current"] = "Active config: somewhere-else"
    rt.rdc_rc["repo list"] = 1
    rt.stdout["machine list"] = "[]"
    assert _main(rt, stack_env, lines, "--suite", "smoke") == 1
    assert [line["ok"] for line in lines] == [False, False, False, False]
    assert lines[0]["code"] == 503
    assert lines[2]["code"] == 1


# ── the daemon suite ────────────────────────────────────────────────────────


def test_daemon_suite_passes_on_a_healthy_daemon(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.stdout["machine list"] = '[{"name":"scenario-extra"}]'
    rt.other_token_refused = True
    # The non-loopback refusal exits non-zero; the TLS probe stays up and answers HTTPS only.
    rt.exit_codes = [2]
    rt.http[TLS_URL] = (200, '{"mode":"daemon"}')
    assert _main(rt, stack_env, lines, "--suite", "daemon") == 0, lines
    assert len(lines) == 7


def test_the_other_orgs_token_being_served_fails_the_refusal_scenario(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    assert _main(rt, stack_env, lines, "--suite", "daemon") == 1
    verdict = _verdict(lines, "other_org_token_refused")
    assert verdict["ok"] is False
    assert "another org was served" in verdict["detail"]


def test_the_refusal_scenario_needs_its_control_to_pass(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.rdc_rc["repo list"] = 1
    _main(rt, stack_env, lines, "--suite", "daemon")
    verdict = _verdict(lines, "other_org_token_refused")
    assert verdict["ok"] is False
    assert "control" in verdict["detail"]


def test_a_wildcard_listener_fails_the_loopback_default(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.lsof = "node 1 u 3u IPv4 TCP *:8480 (LISTEN)"
    _main(rt, stack_env, lines, "--suite", "daemon")
    assert _verdict(lines, "default_bind_is_loopback")["ok"] is False


def test_a_plain_http_daemon_on_a_wildcard_host_fails_and_is_stopped(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.exit_codes = []  # the probe never exits: it kept serving
    _main(rt, stack_env, lines, "--suite", "daemon")
    assert _verdict(lines, "non_loopback_host_without_tls_refused")["ok"] is False
    assert 4242 in rt.killed
    assert "--host" in rt.spawned[0]
    assert "--tls-cert" not in rt.spawned[0]


def test_a_probe_port_already_answering_fails_the_probe(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.listening = {8491, 8492}
    _main(rt, stack_env, lines, "--suite", "daemon")
    names = ("non_loopback_host_without_tls_refused", "non_loopback_host_with_tls_serves_https")
    assert [line["ok"] for line in lines if line["scenario"] in names] == [False, False]
    assert rt.spawned == []


def test_a_tls_daemon_that_also_answers_plain_http_fails(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.http[TLS_URL] = (200, '{"mode":"daemon"}')
    rt.http[PLAIN_URL] = (200, "{}")
    _main(rt, stack_env, lines, "--suite", "daemon")
    verdict = _verdict(lines, "non_loopback_host_with_tls_serves_https")
    assert verdict["ok"] is False
    assert "plain HTTP" in verdict["detail"]
    assert 4242 in rt.killed


def test_a_tls_daemon_that_exits_fails(
    rt: FakeRuntime, stack_env: pathlib.Path, lines: list[dict]
) -> None:
    rt.exit_codes = [2, 1]
    _main(rt, stack_env, lines, "--suite", "daemon")
    verdict = _verdict(lines, "non_loopback_host_with_tls_serves_https")
    assert verdict["ok"] is False
    assert "exited 1" in verdict["detail"]

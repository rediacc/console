"""Tests for the `local-mcp` on-premise suite against a recorded stack env and a fake of the SDK driver and the CLI: no stack, no network.

The fake answers the Node driver the way the stdio server would (the real parity snapshot is the listing, the real policy codes are the refusals), so each scenario's judgement is checked against state that changes, and each failure mode has a control that makes it fail.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci.testrun import onprem_scenarios as scenarios
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import local_mcp

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXECUTOR = "tok-executor-value"


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


def ok_envelope() -> dict:
    return {"success": True, "data": {}, "errors": None}


def refusal_envelope(code: str = "VALIDATION_ERROR", detail: str = "AGENT_OPT_IN_MISSING") -> dict:
    return {"success": False, "data": None, "errors": [{"code": code, "details": [detail]}]}


class FakeStack(onprem_stack.Runtime):
    """The `rdc` CLI plus the Node driver; the driver answers each call from the flags a control flips."""

    def __init__(self) -> None:
        super().__init__()
        self.repos: set[str] = set()
        self.drivers: list[tuple[dict, dict]] = []
        self.era = "modern"
        self.tools_override: list[dict] | None = None
        self.admit_without_opt_in = False
        self.ignore_opt_in = False
        self.driver_rc = 0

    def listing(self) -> list[dict]:
        if self.tools_override is not None:
            return self.tools_override
        snapshot = json.loads((REPO_ROOT / local_mcp.SNAPSHOT).read_text(encoding="utf-8"))
        local_only = {"name": "version", "description": "d", "inputSchema": {}, "annotations": {}}
        return [*snapshot, local_only]

    def call(self, name: str, args: dict, env: dict) -> dict:
        grand = args.get("ref", "")
        if name == "repo_up" and ":" not in grand:
            opted = grand in env.get(local_mcp.GRAND_VAR, "").split(",") and not self.ignore_opt_in
            if not (opted or self.admit_without_opt_in):
                return {"name": name, "isError": True, "envelope": refusal_envelope()}
        return {"name": name, "isError": False, "envelope": ok_envelope()}

    def driver(self, argv: list[str], env: dict) -> subprocess.CompletedProcess:
        plan = json.loads(argv[-1])
        self.drivers.append((plan, env))
        if self.driver_rc:
            return done(argv, self.driver_rc, "", "boom")
        out: dict = {
            "era": self.era,
            "calls": [self.call(c["name"], c["arguments"], env) for c in plan["calls"]],
        }
        if plan["list"]:
            out["tools"] = self.listing()
        return done(argv, 0, "noise\n" + json.dumps(out) + "\n")

    def run(self, argv, env=None, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        del cwd, timeout
        if argv[0] == "node":
            return self.driver(argv, env or {})
        args = argv[argv.index("--config") + 2 :]
        if args[:2] == ["repo", "create"]:
            self.repos.add(args[2])
        elif args[:2] == ["repo", "delete"]:
            self.repos.discard(args[2])
        return done(argv)


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "executor.token").write_text(EXECUTOR + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def stack() -> FakeStack:
    return FakeStack()


def _ctx(stack: FakeStack, home: pathlib.Path, target: str = "onprem") -> scenarios.Context:
    env = {
        "ONPREM_ACCOUNT_URL": "http://127.0.0.1:4910",
        "ONPREM_DAEMON_HOME": str(home),
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_MACHINE_NAME": "onprem-1",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(home / "executor.token"),
    }
    return scenarios.Context(target, env, REPO_ROOT, stack)


def _run(ctx: scenarios.Context, name: str) -> dict:
    return scenarios.run_scenario(onprem_suites.load_all()["local-mcp"][name], ctx)


def test_the_suite_registers_five_scenarios_and_only_the_read_ones_name_bench() -> None:
    suite = onprem_suites.load_all()["local-mcp"]
    assert set(suite) == {
        "tools_list_matches_parity_snapshot",
        "read_tool_answers",
        "fork_write_admitted",
        "grand_write_refused_without_opt_in",
        "grand_write_admitted_with_opt_in",
    }
    both = {n for n, s in suite.items() if s.targets == ("onprem", "bench")}
    assert both == {"tools_list_matches_parity_snapshot", "read_tool_answers"}


def test_every_scenario_passes_against_a_server_that_behaves(
    stack: FakeStack, home: pathlib.Path
) -> None:
    ctx = _ctx(stack, home)
    for name in onprem_suites.load_all()["local-mcp"]:
        verdict = _run(ctx, name)
        assert verdict["ok"] is True, verdict
    assert stack.repos == set()


def test_the_opt_in_is_in_the_clients_environment_only_for_the_admitted_write(
    stack: FakeStack, home: pathlib.Path
) -> None:
    ctx = _ctx(stack, home)
    _run(ctx, "grand_write_refused_without_opt_in")
    _run(ctx, "grand_write_admitted_with_opt_in")
    refused_env, admitted_env = stack.drivers[0][1], stack.drivers[1][1]
    assert local_mcp.GRAND_VAR not in refused_env
    assert admitted_env[local_mcp.GRAND_VAR] == stack.drivers[1][0]["calls"][0]["arguments"]["ref"]
    assert admitted_env["REDIACC_TOKEN"] == EXECUTOR


# -- the controls ------------------------------------------------------------


def test_a_wrong_expected_code_is_a_failed_verdict_the_control() -> None:
    call = {"isError": True, "envelope": refusal_envelope()}
    assert local_mcp.check_refusal(call, "VALIDATION_ERROR", "AGENT_OPT_IN_MISSING", "w").ok is True
    wrong = local_mcp.check_refusal(call, "POLICY_DENIED", "AGENT_OPT_IN_MISSING", "w")
    assert wrong.ok is False
    assert "expected 'POLICY_DENIED'" in wrong.detail
    assert local_mcp.check_refusal(call, "VALIDATION_ERROR", "OTHER", "w").ok is False


def test_a_write_that_is_not_refused_fails_the_refusal_scenario(
    stack: FakeStack, home: pathlib.Path
) -> None:
    stack.admit_without_opt_in = True
    verdict = _run(_ctx(stack, home), "grand_write_refused_without_opt_in")
    assert verdict["ok"] is False
    assert "was admitted" in verdict["detail"]
    assert stack.repos == set()


def test_an_opt_in_that_is_ignored_fails_the_admitted_scenario(
    stack: FakeStack, home: pathlib.Path
) -> None:
    stack.ignore_opt_in = True
    verdict = _run(_ctx(stack, home), "grand_write_admitted_with_opt_in")
    assert verdict["ok"] is False
    assert "failed" in verdict["detail"]


def test_a_listing_missing_a_proxy_tool_fails(stack: FakeStack, home: pathlib.Path) -> None:
    stack.tools_override = stack.listing()[1:]
    verdict = _run(_ctx(stack, home), "tools_list_matches_parity_snapshot")
    assert verdict["ok"] is False
    assert "missing" in verdict["detail"]


def test_a_tool_whose_annotations_drifted_fails(stack: FakeStack, home: pathlib.Path) -> None:
    tools = stack.listing()
    tools[0] = {**tools[0], "annotations": {"readOnlyHint": "drift"}}
    stack.tools_override = tools
    verdict = _run(_ctx(stack, home), "tools_list_matches_parity_snapshot")
    assert verdict["ok"] is False
    assert "annotations" in verdict["detail"]


def test_a_driver_that_fails_or_negotiates_an_old_era_is_a_failed_verdict(
    stack: FakeStack, home: pathlib.Path
) -> None:
    stack.driver_rc = 1
    assert _run(_ctx(stack, home), "read_tool_answers")["ok"] is False
    stack.driver_rc = 0
    stack.era = "legacy"
    verdict = _run(_ctx(stack, home), "read_tool_answers")
    assert verdict["ok"] is False
    assert "era" in verdict["detail"]


def test_the_bench_read_names_no_machine(stack: FakeStack, home: pathlib.Path) -> None:
    ctx = _ctx(stack, home, "bench")
    assert _run(ctx, "read_tool_answers")["ok"] is True
    assert stack.drivers[0][0]["calls"] == [{"name": "repo_list", "arguments": {}}]

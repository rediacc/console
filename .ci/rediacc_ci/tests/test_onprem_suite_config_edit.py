"""Tests for the `config-edit` on-premise suite against a recorded stack env and a stateful fake of the CLI and the config store: no stack, no network.

The fake keeps a store version the way the account server would, and refuses `config edit --apply` and `config field rotate` for an agent environment unless a control flips it, so each failure mode of the suite has a control that makes it fail.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci.testrun import onprem_scenarios as scenarios
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import config_edit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXECUTOR = "tok-executor-value"
REFUSAL = "Editing the config is blocked in agent environments.\nAlternatives:\n  rdc config edit --dump --redacted"
VERSIONS_ARGS = ["--output", "json", "config", "remote", "versions"]


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeStore(onprem_stack.Runtime):
    def __init__(self) -> None:
        super().__init__()
        self.versions = 3
        self.calls: list[tuple[list[str], dict]] = []
        # Behaviours a control flips.
        self.admit_agent_edit = False
        self.refusal_text = REFUSAL
        self.silent_refusal = False
        self.dump_refused = False

    def run(self, argv, env=None, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        del cwd, timeout
        env = env or {}
        args = argv[argv.index("--config") + 2 :]
        self.calls.append((args, env))
        agent = env.get("CLAUDECODE") == "1"
        if args == VERSIONS_ARGS:
            return done(argv, 0, json.dumps([{"version": i} for i in range(self.versions)]))
        if args[:3] == ["config", "edit", "--dump"]:
            return done(argv, 1 if (agent and self.dump_refused) else 0, "{}", "")
        mutating = args[:3] in (["config", "edit", "--apply"], ["config", "field", "rotate"])
        if mutating and agent and not self.admit_agent_edit:
            return done(argv, 1, "", "" if self.silent_refusal else self.refusal_text)
        if mutating:
            self.versions += 1
            return done(argv)
        return done(argv, 2, "", "unscripted: %s" % " ".join(args))


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "executor.token").write_text(EXECUTOR + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _ctx(store: FakeStore, home: pathlib.Path, target: str = "onprem") -> scenarios.Context:
    env = {
        "ONPREM_ACCOUNT_URL": "http://127.0.0.1:4910",
        "ONPREM_DAEMON_HOME": str(home),
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(home / "executor.token"),
    }
    return scenarios.Context(target, env, REPO_ROOT, store)


def _run(ctx: scenarios.Context, name: str) -> dict:
    return scenarios.run_scenario(onprem_suites.load_all()["config-edit"][name], ctx)


def test_the_suite_registers_three_scenarios_naming_both_targets() -> None:
    suite = onprem_suites.load_all()["config-edit"]
    assert set(suite) == {
        "apply_refused_for_an_agent",
        "rotate_refused_for_an_agent",
        "redacted_dump_allowed_for_an_agent",
    }
    assert all(s.targets == ("onprem", "bench") for s in suite.values())


def test_every_scenario_passes_when_the_agent_is_refused(
    store: FakeStore, home: pathlib.Path
) -> None:
    ctx = _ctx(store, home)
    for name in onprem_suites.load_all()["config-edit"]:
        verdict = _run(ctx, name)
        assert verdict["ok"] is True, verdict
    assert store.versions == 3


def test_the_old_var_and_the_agent_marker_reach_the_refused_command_and_the_store_is_read_twice(
    store: FakeStore, home: pathlib.Path
) -> None:
    _run(_ctx(store, home), "rotate_refused_for_an_agent")
    rotate_env = next(env for args, env in store.calls if args[:3] == ["config", "field", "rotate"])
    assert rotate_env[config_edit.OLD_VAR] == "*"
    assert rotate_env["CLAUDECODE"] == "1"
    assert sum(1 for args, _ in store.calls if args == VERSIONS_ARGS) == 2


# -- the controls ------------------------------------------------------------


@pytest.mark.parametrize("name", ["apply_refused_for_an_agent", "rotate_refused_for_an_agent"])
def test_an_edit_that_is_admitted_for_an_agent_fails_the_suite(
    store: FakeStore, home: pathlib.Path, name: str
) -> None:
    store.admit_agent_edit = True
    verdict = _run(_ctx(store, home), name)
    assert verdict["ok"] is False
    assert "was admitted" in verdict["detail"]
    assert store.versions == 4


@pytest.mark.parametrize("name", ["apply_refused_for_an_agent", "rotate_refused_for_an_agent"])
def test_a_refusal_that_names_a_hosted_only_page_fails(
    store: FakeStore, home: pathlib.Path, name: str
) -> None:
    store.refusal_text = REFUSAL + "\nSee https://rediacc.cloud/account/config-edit"
    verdict = _run(_ctx(store, home), name)
    assert verdict["ok"] is False
    assert "hosted-only page" in verdict["detail"]


def test_a_silent_refusal_fails(store: FakeStore, home: pathlib.Path) -> None:
    store.silent_refusal = True
    verdict = _run(_ctx(store, home), "apply_refused_for_an_agent")
    assert verdict["ok"] is False
    assert "nothing on stderr" in verdict["detail"]


def test_a_store_that_moved_under_a_refusal_fails() -> None:
    assert config_edit.assert_unchanged(3, 3, "x") is None
    moved = config_edit.assert_unchanged(3, 4, "x")
    assert moved is not None
    assert "from version 3 to 4" in moved.detail


def test_a_refused_redacted_dump_fails(store: FakeStore, home: pathlib.Path) -> None:
    store.dump_refused = True
    verdict = _run(_ctx(store, home), "redacted_dump_allowed_for_an_agent")
    assert verdict["ok"] is False
    assert "--dump --redacted" in verdict["detail"]

"""Tests for the `writeback` on-premise suite against a recorded stack env and a stateful fake of the CLI and the config store: no stack, no network.

The fake keeps a version list, a repository set and a machine set the way the account store would, so each scenario's arithmetic is checked against state that changes, and each failure mode of the suite has a control that makes it fail.
"""

from __future__ import annotations

import json
import signal
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.testrun import onprem_scenarios as scenarios
from rediacc_ci.testrun import onprem_stack, onprem_suites
from rediacc_ci.testrun.onprem_suites import writeback

if TYPE_CHECKING:
    import pathlib

EXECUTOR = "tok-executor-value"
ENROLL = "tok-enroll-value"
MACHINE_SECRET = "machine-secret-value"
ACCOUNT_PGID = 7001


def done(argv: list[str], rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, rc, out, err)


class FakeStore(onprem_stack.Runtime):
    """The CLI, the daemon and the config store in one state machine."""

    def __init__(self, daemon_home: str) -> None:
        super().__init__()
        self.daemon_home = daemon_home
        self.versions = 1
        self.repos: set[str] = set()
        self.host_repos: set[str] = set()
        self.machines: set[str] = {"onprem-1"}
        self.paused = False
        self.signals: list[tuple[int, int]] = []
        self.calls: list[list[str]] = []
        # Behaviours a control flips.
        self.versions_per_push = 1
        self.second_device_sees_repos = True
        self.lose_laptop_edit = False
        self.create_survives_pause = False
        self.host_job_despite_pause = False

    def device2(self, env: dict[str, str] | None) -> bool:
        return bool(env) and str(env["XDG_CONFIG_HOME"]).endswith("device2")

    def push(self) -> None:
        self.versions += self.versions_per_push

    def run(self, argv, env=None, **_unused) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        if argv[0] == "docker":
            self.paused = argv[1] == "pause"
            return done(argv)
        args = argv[argv.index("--config") + 2 :]
        proxied = args[0] == "--proxy"
        if proxied:
            args = args[2:]
        if args[0] == "--output":
            args = args[2:]
        if args[:3] == ["config", "remote", "versions"]:
            return done(argv, 0, json.dumps([{"version": i} for i in range(self.versions)]))
        if args[:2] == ["config", "init"] or args[:3] == ["config", "remote", "enable"]:
            return done(argv)
        if args[:2] == ["repo", "list"]:
            if "--machine" in args:
                return done(argv, 0, json.dumps(sorted(self.host_repos)))
            names = (
                self.repos if (not self.device2(env) or self.second_device_sees_repos) else set()
            )
            return done(argv, 0, json.dumps(sorted(names)))
        if args[:2] == ["repo", "create"]:
            if proxied and self.paused:
                if self.host_job_despite_pause:
                    self.host_repos.add(args[2])
                if not self.create_survives_pause:
                    return done(argv, 1, "", "account server unreachable")
            self.repos.add(args[2])
            self.host_repos.add(args[2])
            self.push()
            return done(argv)
        if args[:2] == ["repo", "delete"]:
            self.repos.discard(args[2])
            self.host_repos.discard(args[2])
            self.push()
            return done(argv)
        if args[:2] == ["repo", "fork"]:
            fork = "%s:%s" % (args[2], args[args.index("--tag") + 1])
            self.repos.add(fork)
            self.host_repos.add(fork)
            self.push()
            return done(argv)
        if args[:2] == ["machine", "add"]:
            if not self.lose_laptop_edit:
                self.machines.add(args[2])
            self.push()
            return done(argv)
        if args[:2] == ["machine", "remove"]:
            self.machines.discard(args[2])
            return done(argv)
        if args[:2] == ["machine", "list"]:
            return done(argv, 0, json.dumps(sorted(self.machines)))
        return done(argv, 2, "", "unscripted: %s" % " ".join(args))

    def signal_group(self, pgid: int, sig: int) -> None:
        self.signals.append((pgid, sig))
        self.paused = sig == signal.SIGSTOP


@pytest.fixture
def home(tmp_path: pathlib.Path) -> pathlib.Path:
    for name, value in (
        ("executor.token", EXECUTOR),
        ("enroll.token", ENROLL),
        ("machine-secret.token", MACHINE_SECRET),
    ):
        (tmp_path / name).write_text(value + "\n", encoding="utf-8")
    return tmp_path


def _stack_env(home: pathlib.Path, groups: list[dict] | None = None) -> dict[str, str]:
    state = home / "stack.json"
    state.write_text(
        json.dumps(
            {
                "groups": [{"name": "account", "pgid": ACCOUNT_PGID}] if groups is None else groups,
                "containers": [],
                "compose": [],
            }
        ),
        encoding="utf-8",
    )
    return {
        "ONPREM_ACCOUNT_URL": "http://127.0.0.1:4910",
        "ONPREM_DAEMON_URL": "http://127.0.0.1:8480",
        "ONPREM_DAEMON_HOME": str(home),
        "ONPREM_CONFIG_NAME": "onprem-stack",
        "ONPREM_MACHINE_NAME": "onprem-1",
        "ONPREM_EXECUTOR_TOKEN_FILE": str(home / "executor.token"),
        "ONPREM_ENROLL_TOKEN_FILE": str(home / "enroll.token"),
        "ONPREM_MACHINE_SECRET_FILE": str(home / "machine-secret.token"),
        "ONPREM_MACHINE_SECRET_ID": "ms-1",
        "ONPREM_STATE_FILE": str(state),
    }


@pytest.fixture
def store(home: pathlib.Path) -> FakeStore:
    return FakeStore(str(home))


def _ctx(
    store: FakeStore, home: pathlib.Path, groups: list[dict] | None = None
) -> scenarios.Context:
    return scenarios.Context("onprem", _stack_env(home, groups), home, store)


def _run(ctx: scenarios.Context, name: str) -> dict:
    return scenarios.run_scenario(onprem_suites.load_all()["writeback"][name], ctx)


def test_the_suite_registers_five_onprem_only_scenarios() -> None:
    suite = onprem_suites.load_all()["writeback"]
    assert set(suite) == {
        "create_pushes_one_version",
        "delete_pushes_one_version",
        "fork_pushes_one_version",
        "racing_pushes_keep_both_edits",
        "account_unreachable_fails_without_a_host_job",
    }
    assert all(s.targets == ("onprem",) for s in suite.values())


def test_every_scenario_passes_against_a_store_that_behaves(
    store: FakeStore, home: pathlib.Path
) -> None:
    ctx = _ctx(store, home)
    for name in onprem_suites.load_all()["writeback"]:
        verdict = _run(ctx, name)
        assert verdict["ok"] is True, verdict
    assert store.repos == set()
    assert store.host_repos == set()
    assert "wb-laptop" not in " ".join(store.machines)


def test_the_second_device_is_enrolled_once_with_the_machine_secret_in_its_environment(
    store: FakeStore, home: pathlib.Path
) -> None:
    ctx = _ctx(store, home)
    _run(ctx, "create_pushes_one_version")
    _run(ctx, "delete_pushes_one_version")
    enables = [argv for argv in store.calls if "enable" in argv]
    assert len(enables) == 1
    assert MACHINE_SECRET not in " ".join(enables[0])
    assert (home / "device2" / ".enrolled").exists()


# ── the version arithmetic and its controls ─────────────────────────────────


def test_a_wrong_expected_count_is_a_failed_verdict_the_control(
    store: FakeStore, home: pathlib.Path
) -> None:
    ctx = _ctx(store, home)
    device2 = writeback.device2_home(ctx)
    right = writeback.check_new_versions(
        ctx, device2, lambda: writeback._create(ctx, "wb-x"), expected=1, what="create"
    )
    wrong = writeback.check_new_versions(
        ctx, device2, lambda: writeback._create(ctx, "wb-y"), expected=2, what="create"
    )
    assert right.ok is True
    assert wrong.ok is False
    assert "pushed 1 new version(s), expected 2" in wrong.detail


@pytest.mark.parametrize("pushed", [0, 2])
def test_a_command_that_pushes_the_wrong_number_of_versions_fails(
    store: FakeStore, home: pathlib.Path, pushed: int
) -> None:
    store.versions_per_push = pushed
    verdict = _run(_ctx(store, home), "create_pushes_one_version")
    assert verdict["ok"] is False
    assert "expected 1" in verdict["detail"]


def test_a_record_the_second_device_cannot_read_fails_create(
    store: FakeStore, home: pathlib.Path
) -> None:
    store.second_device_sees_repos = False
    verdict = _run(_ctx(store, home), "create_pushes_one_version")
    assert verdict["ok"] is False
    assert "second device" in verdict["detail"]


def test_a_delete_that_leaves_the_record_visible_fails(
    store: FakeStore, home: pathlib.Path
) -> None:
    ctx = _ctx(store, home)

    original = store.run

    def run(argv, env=None, **kw):
        out = original(argv, env=env, **kw)
        if "delete" in argv and "--proxy" in argv:
            store.repos.add(argv[argv.index("delete") + 1])
        return out

    store.run = run
    verdict = _run(ctx, "delete_pushes_one_version")
    assert verdict["ok"] is False
    assert "still shows" in verdict["detail"]


def test_a_fork_the_second_device_cannot_see_fails(store: FakeStore, home: pathlib.Path) -> None:
    ctx = _ctx(store, home)
    original = store.run

    def run(argv, env=None, **kw):
        out = original(argv, env=env, **kw)
        if "fork" in argv:
            store.repos = {r for r in store.repos if ":" not in r}
        return out

    store.run = run
    verdict = _run(ctx, "fork_pushes_one_version")
    assert verdict["ok"] is False
    assert ":t1" in verdict["detail"]


# ── the race ────────────────────────────────────────────────────────────────


def test_a_lost_laptop_edit_fails_the_race_scenario(store: FakeStore, home: pathlib.Path) -> None:
    store.lose_laptop_edit = True
    verdict = _run(_ctx(store, home), "racing_pushes_keep_both_edits")
    assert verdict["ok"] is False
    assert "laptop's machine edit was lost" in verdict["detail"]


def test_a_lost_served_create_fails_the_race_scenario(store: FakeStore, home: pathlib.Path) -> None:
    store.second_device_sees_repos = False
    verdict = _run(_ctx(store, home), "racing_pushes_keep_both_edits")
    assert verdict["ok"] is False
    assert "served repo create was lost" in verdict["detail"]


# ── the account server going away ───────────────────────────────────────────


def test_the_account_is_stopped_and_resumed_and_the_command_fails_without_a_host_job(
    store: FakeStore, home: pathlib.Path
) -> None:
    verdict = _run(_ctx(store, home), "account_unreachable_fails_without_a_host_job")
    assert verdict["ok"] is True, verdict
    assert store.signals == [(ACCOUNT_PGID, signal.SIGSTOP), (ACCOUNT_PGID, signal.SIGCONT)]
    assert store.host_repos == set()


def test_a_create_that_succeeds_with_the_account_stopped_fails(
    store: FakeStore, home: pathlib.Path
) -> None:
    store.create_survives_pause = True
    verdict = _run(_ctx(store, home), "account_unreachable_fails_without_a_host_job")
    assert verdict["ok"] is False
    assert "succeeded while the account server could not be reached" in verdict["detail"]
    assert store.signals[-1] == (ACCOUNT_PGID, signal.SIGCONT)


def test_a_host_job_started_despite_the_failed_record_fails(
    store: FakeStore, home: pathlib.Path
) -> None:
    store.host_job_despite_pause = True
    verdict = _run(_ctx(store, home), "account_unreachable_fails_without_a_host_job")
    assert verdict["ok"] is False
    assert "host job created" in verdict["detail"]


def test_the_account_is_resumed_even_when_the_command_raises(
    store: FakeStore, home: pathlib.Path
) -> None:
    original = store.run

    def run(argv, env=None, **kw):
        if "--size" in argv and store.paused:
            raise OSError("spawn failed")
        return original(argv, env=env, **kw)

    store.run = run
    verdict = _run(_ctx(store, home), "account_unreachable_fails_without_a_host_job")
    assert verdict["ok"] is False
    assert store.signals[-1] == (ACCOUNT_PGID, signal.SIGCONT)


def test_an_image_run_account_server_is_paused_through_docker(
    store: FakeStore, home: pathlib.Path
) -> None:
    verdict = _run(_ctx(store, home, groups=[]), "account_unreachable_fails_without_a_host_job")
    docker = [argv[:2] for argv in store.calls if argv[0] == "docker"]
    assert ["docker", "pause"] in docker
    assert ["docker", "unpause"] in docker
    assert store.signals == []
    assert verdict["ok"] is True, verdict


def test_no_secret_reaches_a_verdict(store: FakeStore, home: pathlib.Path) -> None:
    store.versions_per_push = 0
    ctx = _ctx(store, home)
    lines = [_run(ctx, name) for name in onprem_suites.load_all()["writeback"]]
    text = json.dumps(lines)
    for secret in (EXECUTOR, ENROLL, MACHINE_SECRET):
        assert secret not in text

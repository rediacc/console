"""Tests for `rediacc_ci.testrun.onprem_stack` against a fake runtime: no docker, no account server, no network. One test drives the real process-group helpers with a real sleeping process tree."""

from __future__ import annotations

import json
import os
import pathlib
import socket
import stat
import subprocess
import sys
import time

import pytest

from rediacc_ci.testrun import onprem_stack as mod

TOKEN_VALUE = "rdc_secret_token_value"
MACHINE_SECRET = "machine-secret-value-xyz"


class FakeRuntime(mod.Runtime):
    """Replaces every side effect; `fail` names the step that raises."""

    def __init__(self, answering: set[int] | None = None, fail: str = "") -> None:
        self.answering = answering or set()
        self.listening: set[int] = set()
        self.fail = fail
        self.groups: list[tuple[list[str], dict[str, str]]] = []
        self.killed: list[int] = []
        self.runs: list[tuple[list[str], dict[str, str] | None]] = []
        self.rustfs_started = False
        self.rustfs_up = False
        self.next_pid = 5000
        self.daemon_mode = "daemon"

    def port_answers(self, port: int) -> bool:
        return port in self.answering or port in self.listening

    def spawn_group(self, argv, env, *_unused) -> int:
        self.groups.append((argv, env))
        self.next_pid += 1
        return self.next_pid

    def kill_group(self, pgid: int) -> None:
        self.killed.append(pgid)

    def run(self, argv, env=None, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        del cwd, timeout  # the fake takes the real signature and ignores both
        self.runs.append((argv, env))
        joined = " ".join(argv)
        if argv[0] == "ssh-keygen":
            key = pathlib.Path(argv[-1])
            key.write_text("PRIVATE", encoding="utf-8")
            pathlib.Path(str(key) + ".pub").write_text("ssh-ed25519 AAAA test\n", encoding="utf-8")
        if argv[:2] == ["docker", "run"] and "-p" in argv:
            self.listening.add(int(argv[argv.index("-p") + 1].split(":")[1]))
        if self.fail and self.fail in joined:
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def http_get(self, url: str, *_unused) -> tuple[int, str]:
        if self.fail == "health" and url.endswith("/health"):
            return 0, ""
        if url.endswith("/v1/server-info"):
            return 200, json.dumps({"mode": self.daemon_mode})
        return 200, "{}"

    def sleep(self, _seconds: float) -> None:
        return

    def seed(self, _port: int, _email: str, name: str, _scopes: list[str]) -> str:
        if self.fail == "seed":
            raise mod.StackError("seeding failed")
        return "%s-%s" % (TOKEN_VALUE, name)

    def seed_store(self, _port: int, _email: str) -> dict:
        return {"machineSecretId": "ms-1", "machineSecret": MACHINE_SECRET}

    def rustfs_alive(self, port: int) -> bool:
        if self.fail == "rustfs":
            return False
        return self.rustfs_started or port in self.answering

    def start_rustfs(self) -> None:
        self.rustfs_started = True

    def keys(self) -> dict[str, str]:
        return {"edPriv": "a", "edPub": "b", "xPriv": "c", "xPub": "d"}


@pytest.fixture
def layout(tmp_path: pathlib.Path) -> mod.Layout:
    return mod.Layout(tmp_path)


def _up(layout: mod.Layout, rt: FakeRuntime, *extra: str) -> int:
    return mod.main(["up", "--from-source", *extra], runtime=rt, root=layout.root)


def test_up_writes_an_env_file_naming_every_piece_and_no_secret(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert _up(layout, rt) == 0
    env = dict(
        line.split("=", 1) for line in layout.env_file.read_text(encoding="utf-8").splitlines()
    )
    assert env["ONPREM_ACCOUNT_URL"] == "http://127.0.0.1:4910"
    assert env["ONPREM_DAEMON_URL"] == "http://127.0.0.1:8480"
    assert env["ONPREM_CONFIG_NAME"] == mod.CONFIG_NAME
    assert env["ONPREM_MACHINES"] == "container"
    assert env["ONPREM_MACHINE_IP"] == "127.0.0.1"
    assert env["ONPREM_ACCOUNT_SQLITE"] == str(layout.sqlite)
    text = layout.env_file.read_text(encoding="utf-8")
    assert TOKEN_VALUE not in text
    assert MACHINE_SECRET not in text
    for key in ("EXECUTOR", "ENROLL", "OTHER"):
        token_path = pathlib.Path(env["ONPREM_%s_TOKEN_FILE" % key])
        assert token_path.read_text(encoding="utf-8").startswith(TOKEN_VALUE)
        assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_up_starts_the_pieces_in_order_and_records_them(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert _up(layout, rt) == 0
    names = [argv[0] for argv, _ in rt.groups]
    assert names == ["npx", str(layout.root / "rdc.sh")]
    assert rt.groups[0][0][-1] == "src/entry/on-premise.ts"
    assert rt.groups[0][1]["TEST_MODE"] == "true"
    assert rt.groups[0][1]["ON_PREMISE_MODE"] == "true"
    daemon_argv = rt.groups[1][0]
    assert daemon_argv[daemon_argv.index("--host") + 1] == "127.0.0.1"
    state = json.loads(layout.state_file.read_text(encoding="utf-8"))
    assert [g["name"] for g in state["groups"]] == ["account", "daemon"]
    assert state["containers"] == [mod.MACHINE_CONTAINER]
    assert state["compose"] == [["config-rustfs", "config-rustfs-init"]]


def test_machine_secret_travels_in_the_environment_only(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert _up(layout, rt) == 0
    enable = [(a, e) for a, e in rt.runs if "enable" in a]
    assert len(enable) == 1
    argv, env = enable[0]
    assert MACHINE_SECRET not in " ".join(argv)
    assert env is not None
    assert env["REDIACC_MACHINE_SECRET"] == MACHINE_SECRET
    assert "ms-1" in argv


@pytest.mark.parametrize(
    "port", [mod.DEFAULT_ACCOUNT_PORT, mod.DEFAULT_DAEMON_PORT, mod.DEFAULT_SSH_PORT]
)
def test_a_port_that_answers_is_refused_before_anything_starts(
    layout: mod.Layout, port: int
) -> None:
    rt = FakeRuntime(answering={port})
    assert _up(layout, rt) == 1
    assert rt.groups == []
    assert rt.runs == []
    assert not rt.rustfs_started
    assert not layout.state_file.exists()


def test_a_stale_rustfs_listener_is_refused(layout: mod.Layout) -> None:
    rt = FakeRuntime(answering={mod.RUSTFS_PORT})
    assert _up(layout, rt) == 1
    assert not rt.rustfs_started
    assert rt.groups == []


def test_a_free_port_is_the_control_that_starts(layout: mod.Layout) -> None:
    assert _up(layout, FakeRuntime(answering={9})) == 0


@pytest.mark.parametrize(
    "fail",
    [
        "rustfs",
        "health",
        "seed",
        "ssh-keygen",
        "docker run",
        "config init",
        "machine add",
        "remote enable",
    ],
)
def test_every_failure_tears_down_everything_started(layout: mod.Layout, fail: str) -> None:
    rt = FakeRuntime(fail=fail)
    assert _up(layout, rt) == 1
    started = len(rt.groups)
    assert len(rt.killed) == started
    removed = [a for a, _ in rt.runs if a[:3] == ["docker", "rm", "-f"]]
    stopped = [a for a, _ in rt.runs if a[:3] == ["docker", "compose", "stop"]]
    assert len(stopped) == 1
    # A container is recorded just before its `docker run`, so it is removed from the machine step on.
    recorded_containers = 0 if fail in {"rustfs", "health", "seed", "ssh-keygen"} else 1
    assert len(removed) == recorded_containers
    assert not layout.env_file.exists()
    if fail == "rustfs":
        # The fake also fails `docker compose stop rustfs`, so that service stays recorded for a later `down` (review b7004c9a.1).
        assert json.loads(layout.state_file.read_text())["compose"]
    else:
        assert not layout.state_file.exists()


def test_a_daemon_that_answers_as_a_container_fails_the_run(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    rt.daemon_mode = "container"
    assert _up(layout, rt) == 1
    assert len(rt.killed) == 2
    assert not layout.env_file.exists()


def test_an_interrupt_mid_up_still_tears_down(layout: mod.Layout) -> None:
    class Interrupted(FakeRuntime):
        def seed(self, *_unused):
            raise KeyboardInterrupt

    rt = Interrupted()
    with pytest.raises(KeyboardInterrupt):
        _up(layout, rt)
    assert len(rt.killed) == 1
    assert not layout.state_file.exists()


def test_down_stops_every_recorded_piece_and_clears_the_files(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert _up(layout, rt) == 0
    down_rt = FakeRuntime()
    assert mod.main(["down"], runtime=down_rt, root=layout.root) == 0
    assert len(down_rt.killed) == 2
    assert any(a[:3] == ["docker", "rm", "-f"] for a, _ in down_rt.runs)
    assert any(a[:3] == ["docker", "compose", "stop"] for a, _ in down_rt.runs)
    assert not layout.state_file.exists()
    assert not layout.env_file.exists()


def test_down_with_nothing_recorded_is_a_clean_no_op(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert mod.main(["down"], runtime=rt, root=layout.root) == 0
    assert rt.runs == []


def test_down_reports_a_container_that_will_not_go(layout: mod.Layout) -> None:
    assert _up(layout, FakeRuntime()) == 0
    rt = FakeRuntime(fail="docker rm")
    assert mod.main(["down"], runtime=rt, root=layout.root) == 1
    assert len(rt.killed) == 2
    # The container that would not go stays recorded, so a second `down` retries it (review b7004c9a.1).
    assert layout.state_file.exists()
    kept = json.loads(layout.state_file.read_text())
    assert kept["containers"]
    assert kept["groups"] == []
    assert mod.main(["down"], runtime=FakeRuntime(), root=layout.root) == 0
    assert not layout.state_file.exists()


def test_up_over_a_recorded_stack_is_refused(layout: mod.Layout) -> None:
    assert _up(layout, FakeRuntime()) == 0
    rt = FakeRuntime()
    assert _up(layout, rt) == 1
    assert rt.groups == []


def test_image_with_the_node_entry_is_refused(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert mod.main(["up", "--entry", "node"], runtime=rt, root=layout.root) == 1
    assert rt.groups == []


def test_image_run_passes_keys_by_name_never_by_value(layout: mod.Layout) -> None:
    rt = FakeRuntime()
    assert mod.main(["up"], runtime=rt, root=layout.root) == 0
    (argv, _) = next((a, e) for a, e in rt.runs if a[:2] == ["docker", "run"] and mod.IMAGE in a)
    assert "ACCOUNT_ED25519_PRIVATE_KEY" in argv
    assert not any(part.startswith("ACCOUNT_ED25519_PRIVATE_KEY=") for part in argv)
    assert "DATABASE_PATH=/data/account.db" in argv


def test_status_names_a_gone_group(layout: mod.Layout) -> None:
    layout.dir.mkdir()
    layout.state_file.write_text(
        json.dumps(
            {
                "groups": [{"name": "account", "pgid": 2**22 + 12345}],
                "containers": [],
                "compose": [],
            }
        ),
        encoding="utf-8",
    )
    assert mod.main(["status"], runtime=FakeRuntime(), root=layout.root) == 0


def test_status_without_a_stack_is_nonzero(layout: mod.Layout) -> None:
    assert mod.main(["status"], runtime=FakeRuntime(), root=layout.root) == 1


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["bogus"],
        ["up", "--machines", "metal"],
        ["up", "--entry", "x"],
        ["up", "--account-port", "0"],
        ["up", "--ssh-port"],
        ["down", "--from-source"],
    ],
)
def test_bad_usage_exits_2(layout: mod.Layout, argv: list[str]) -> None:
    assert mod.main(argv, runtime=FakeRuntime(), root=layout.root) == 2


def test_kill_group_ends_the_whole_process_tree() -> None:
    """The real helpers: a leader that forks a sleeper is gone, children included, after kill_group."""
    runtime = mod.Runtime()
    log_file = pathlib.Path(os.devnull)
    pgid = runtime.spawn_group(
        [
            sys.executable,
            "-c",
            "import subprocess,time; subprocess.Popen(['sleep','60']); time.sleep(60)",
        ],
        dict(os.environ),
        pathlib.Path.cwd(),
        log_file,
    )
    time.sleep(0.5)
    os.killpg(pgid, 0)
    runtime.kill_group(pgid)
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)


def test_kill_group_of_a_gone_group_is_done() -> None:
    mod.Runtime().kill_group(2**22 + 54321)


def test_port_answers_sees_a_real_listener() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert mod.Runtime().port_answers(port)
    assert not mod.Runtime().port_answers(port)

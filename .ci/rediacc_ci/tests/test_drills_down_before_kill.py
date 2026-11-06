"""`rediacc_ci.drills.down_before_kill`: the CLI-free pieces of the K1 step (box K0 of PLAN-renet-down-before-kill) and every live row on a fake worker. The live rows run against the KVM fleet through `npm run vm:check` (box K1); here the probe runs under bash, the root scripts run against a fake `systemctl`, and each row's verdict is driven both ways, the CONTROL being a log with no `down` line before the restart."""

from __future__ import annotations

import os
import pathlib
import re
import shlex
import socket
import subprocess
from typing import Any

import pytest

from rediacc_ci.drills import down_before_kill as k
from rediacc_ci.drills import upgrade_converge, vm_check

NID_A, NID_B = 8601, 8602
GUID_A = "aaaaaaaa-1111-4111-8111-111111111111"
GUID_B = "bbbbbbbb-2222-4222-8222-222222222222"


def unit_text(nid: int, guid: str, *, stop: bool = True, env: bool = True) -> str:
    """A docker unit the way S1 renders it (stop side on), or today's (stop side off)."""
    after = "After=network-online.target"
    lines = ["# /etc/systemd/system/rediacc-docker-%d.service" % nid, "[Unit]"]
    if stop:
        after += " %s %s" % (k.SHUTDOWN_UNIT, k.mount_unit(guid))
    lines += [after, "", "[Service]"]
    if env:
        lines.append("Environment=DOCKER_RAMDISK=true")
    lines.append("ExecStart=/usr/bin/renet daemon start --network-id=%d" % nid)
    if stop:
        lines += [
            "ExecStop=/usr/bin/renet daemon stop-hook --network-id=%d" % nid,
            "TimeoutStopSec=17min",
        ]
    else:
        lines.append("TimeoutStopSec=120")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- registration and probe


def test_step_registration_tuple() -> None:
    assert ("K1", ("P5",), k.run) == k.STEP
    assert k.STEP in vm_check.EXTRA_RENET_STEPS
    assert "K1" in vm_check.PHASE_STEPS[vm_check.SIDE_RENET]


def _run_probe(tmp_path: pathlib.Path, fn: str) -> str:
    """Source the probe Rediaccfile under bash with `sleep` stubbed to record its argument, call `fn`, return the log."""
    rf = tmp_path / "Rediaccfile"
    rf.write_text(k.probe_rediaccfile())
    script = 'source "$1"; sleep() { echo "slept $1" >> "$REDIACC_WORKING_DIR/sleeps"; }; %s' % fn
    env = {**os.environ, "REDIACC_WORKING_DIR": str(tmp_path)}
    subprocess.run(["bash", "-c", script, "_", str(rf)], env=env, check=True, timeout=30)
    return (tmp_path / k.LOG_FILE).read_text()


def test_probe_up_and_down_append_epoch_lines(tmp_path: pathlib.Path) -> None:
    _run_probe(tmp_path, "up")
    text = _run_probe(tmp_path, "down")
    events = k.parse_log(text)
    assert [kind for kind, _ in events] == ["up", "down"]
    assert all(ts > 1_700_000_000 for _, ts in events)
    assert (tmp_path / "sleeps").read_text() == "slept %d\n" % k.DOWN_SLEEP_S


def test_probe_down_writes_its_line_before_it_sleeps() -> None:
    body = k.probe_rediaccfile()
    down = body[body.index("down() {") :]
    assert down.index('echo "down $(date +%s)"') < down.index("sleep %d" % k.DOWN_SLEEP_S)
    assert k.DOWN_SLEEP_S == 20
    assert k.LOG_FILE == "downproof.log"


# --------------------------------------------------------------------------- escape, scripts


@pytest.mark.parametrize(
    ("path", "want"),
    [
        # Each expectation is what `systemd-escape --path` printed for the same input (systemd 255).
        ("/mnt/rediacc/mounts/ab-cd.ef_g:h", "mnt-rediacc-mounts-ab\\x2dcd.ef_g:h"),
        ("/.x/y", "\\x2ex-y"),
        ("//a//b/", "a-b"),
        ("/", "-"),
        ("/a b", "a\\x20b"),
    ],
)
def test_systemd_escape_path_matches_systemd_escape(path: str, want: str) -> None:
    assert k.systemd_escape_path(path) == want


def test_mount_unit_escapes_the_guid_dashes() -> None:
    unit = k.mount_unit(GUID_A)
    assert unit.endswith(".mount")
    assert "\\x2d1111\\x2d" in unit
    assert unit.startswith(k.systemd_escape_path(k.MOUNTS) + "-")


@pytest.mark.parametrize(
    "script",
    [
        k.state_script(NID_A),
        k.unit_text_script(NID_A),
        k.restart_script(NID_A),
        k.drop_environment_script(NID_A),
        k.drop_stop_side_script(NID_A),
        k.remove_stamp_script(NID_A),
        k.plant_skew_script(NID_A),
        k.daemon_restart_script(NID_A),
        k.read_log_script(GUID_A),
        k.reconcile_script(),
        k.boot_script(),
        k.reboot_script(),
        k.job_timeout_script(),
        k.build_main_renet_script("/tmp/s r c", "/tmp/out", "abc123"),
    ],
)
def test_root_scripts_are_valid_shell(script: str) -> None:
    subprocess.run(["bash", "-n", "-c", script], check=True, timeout=30)


def _fake_bin(tmp_path: pathlib.Path, name: str, body: str) -> dict[str, str]:
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return {**os.environ, "PATH": "%s:%s" % (tmp_path / "bin", os.environ["PATH"])}


def test_state_script_reads_pid_start_and_active_through_date(tmp_path: pathlib.Path) -> None:
    env = _fake_bin(
        tmp_path,
        "systemctl",
        'case "$*" in\n'
        "  *MainPID*) echo 4242;;\n"
        '  *ExecMainStartTimestamp*) echo "Thu 2026-11-05 10:00:00 UTC";;\n'
        "  is-active*) echo active;;\n"
        "esac\n",
    )
    out = subprocess.run(
        ["sh", "-c", k.state_script(NID_A)], env=env, capture_output=True, text=True, check=True
    ).stdout
    st = k.parse_state(out)
    assert st["pid"] == 4242
    assert st["start"] == 1793872800
    assert st["active"] == "active"
    assert st["now"] > 1_700_000_000


def _edit(tmp_path: pathlib.Path, script: str, text: str) -> str:
    """Run an edit script against a unit file through a fake systemctl that names it and records the reload."""
    unit = tmp_path / "unit.service"
    unit.write_text(text)
    env = _fake_bin(
        tmp_path,
        "systemctl",
        'case "$*" in\n  *FragmentPath*) echo %s;;\n  daemon-reload) echo reloaded > %s;;\nesac\n'
        % (unit, tmp_path / "reload"),
    )
    res = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "reload").exists()
    return unit.read_text()


def test_drop_environment_removes_only_the_first_environment_line(tmp_path: pathlib.Path) -> None:
    text = unit_text(NID_A, GUID_A).replace(
        "Environment=DOCKER_RAMDISK=true", "Environment=A=1\nEnvironment=B=2"
    )
    edited = k.parse_unit(_edit(tmp_path, k.drop_environment_script(NID_A), text))
    assert edited["environment"] == ["B=2"]
    assert edited["exec_stop"]


def test_drop_stop_side_removes_execstop_and_timeout_only(tmp_path: pathlib.Path) -> None:
    edited = k.parse_unit(_edit(tmp_path, k.drop_stop_side_script(NID_A), unit_text(NID_A, GUID_A)))
    assert edited["exec_stop"] == []
    assert edited["timeout_stop_s"] is None
    assert edited["environment"] == ["DOCKER_RAMDISK=true"]
    assert k.SHUTDOWN_UNIT in edited["after"]


def test_build_main_renet_script_builds_in_a_shared_clone_without_touching_bin() -> None:
    script = k.build_main_renet_script("/w/src", "/w/renet-main", "deadbeef")
    assert "git clone --quiet --shared --no-checkout private/renet /w/src" in script
    assert "checkout --quiet deadbeef" in script
    assert "./build.sh dev" in script
    assert "install -m 0755 /w/src/bin/renet /w/renet-main" in script
    assert "private/renet/bin" not in script


def test_remove_stamp_targets_the_runtime_stamp() -> None:
    assert upgrade_converge.runtime_stamp_path(NID_A) in k.remove_stamp_script(NID_A)


# --------------------------------------------------------------------------- parsers


def test_parse_log_keeps_up_and_down_lines_in_order() -> None:
    text = "up 100\ngarbage\ndown 130\n  up 200  \ndown x\nupdown 5\n"
    assert k.parse_log(text) == [("up", 100), ("down", 130), ("up", 200)]
    assert k.parse_log("") == []


def test_parse_state_defaults_missing_fields_to_zero() -> None:
    assert k.parse_state("NOW=5\nACTIVE=failed\n") == {
        "now": 5,
        "pid": 0,
        "start": 0,
        "active": "failed",
    }
    assert k.parse_state("")["active"] == ""


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("1020", 1020.0),
        ("17min", 1020.0),
        ("17m", 1020.0),
        ("30min", 1800.0),
        ("1h 30min", 5400.0),
        ("30min 5s", 1805.0),
        ("500ms", 0.5),
        ("infinity", float("inf")),
        ("", None),
        ("soon", None),
        ("5 parsecs", None),
        ("5min junk", None),
    ],
)
def test_parse_timespan(text: str, want: float | None) -> None:
    assert k.parse_timespan(text) == want


def test_parse_unit_reads_the_stop_side_and_skips_comments() -> None:
    unit = k.parse_unit(unit_text(NID_A, GUID_A))
    assert unit["exec_stop"] == ["/usr/bin/renet daemon stop-hook --network-id=%d" % NID_A]
    assert {k.SHUTDOWN_UNIT, k.mount_unit(GUID_A), "network-online.target"} <= unit["after"]
    assert unit["timeout_stop_s"] == k.STOP_TIMEOUT_S
    assert unit["environment"] == ["DOCKER_RAMDISK=true"]


@pytest.mark.parametrize(
    ("command", "nid", "want"),
    [
        ("/usr/bin/renet daemon stop-hook --network-id=8601", 8601, True),
        ("/usr/bin/renet daemon  stop-hook --network-id 8601", 8601, True),
        ("/usr/bin/renet daemon stop-hook --network-id=86011", 8601, False),
        ("/usr/bin/renet daemon stop-hook --network-id=8602", 8601, False),
        ("/usr/bin/renet daemon stop --network-id=8601", 8601, False),
        ("/bin/kill -TERM $MAINPID", 8601, False),
    ],
)
def test_runs_stop_hook(command: str, nid: int, want: bool) -> None:
    assert k.runs_stop_hook(command, nid) is want


# --------------------------------------------------------------------------- verdicts


def test_unit_order_verdict_on_the_new_and_the_old_unit() -> None:
    ok, why = k.unit_order_verdict(k.parse_unit(unit_text(NID_A, GUID_A)), NID_A, GUID_A)
    assert ok, why
    # CONTROL: today's unit (no ExecStop, no ordering) fails K1.1.
    ok, why = k.unit_order_verdict(
        k.parse_unit(unit_text(NID_A, GUID_A, stop=False)), NID_A, GUID_A
    )
    assert not ok
    assert "stop_hook=False" in why
    # Another repo's mount unit is not this one's.
    ok, _ = k.unit_order_verdict(k.parse_unit(unit_text(NID_A, GUID_B)), NID_A, GUID_A)
    assert not ok


def test_stop_side_verdict_needs_the_timeout() -> None:
    assert k.stop_side_verdict(k.parse_unit(unit_text(NID_A, GUID_A)), NID_A, GUID_A)[0]
    short = unit_text(NID_A, GUID_A).replace("TimeoutStopSec=17min", "TimeoutStopSec=120")
    assert not k.stop_side_verdict(k.parse_unit(short), NID_A, GUID_A)[0]
    gone = unit_text(NID_A, GUID_A).replace("TimeoutStopSec=17min\n", "")
    assert not k.stop_side_verdict(k.parse_unit(gone), NID_A, GUID_A)[0]


def test_down_before_verdict_passes_a_finished_down() -> None:
    ok, why = k.down_before_verdict([("up", 50), ("down", 100)], 99, 125)
    assert ok, why
    assert "25s before" in why


def test_down_before_verdict_control_no_down_line_fails() -> None:
    """The plan's CONTROL: a log with no `down` line before the restart is a FAIL."""
    ok, why = k.down_before_verdict([("up", 50), ("up", 130)], 99, 125)
    assert not ok
    assert "no down line" in why
    assert not k.down_before_verdict([], 99, 125)[0]


@pytest.mark.parametrize(
    ("events", "issued", "at", "needle"),
    [
        # A down() killed part way: the restart came 5 s after it started.
        ([("down", 100)], 99, 105, "did not finish"),
        # A stale line from an earlier stop does not count.
        ([("down", 10)], 99, 125, "no down line"),
        # A down line after the new start is not before it.
        ([("down", 130)], 99, 125, "did not finish"),
        # Nothing restarted.
        ([("down", 100)], 99, 99, "nothing restarted"),
        # No reading at all.
        ([("down", 100)], 0, 125, "no reading"),
        ([("down", 100)], 99, 0, "no reading"),
    ],
)
def test_down_before_verdict_fails(
    events: list[tuple[str, int]], issued: int, at: int, needle: str
) -> None:
    ok, why = k.down_before_verdict(events, issued, at)
    assert not ok
    assert needle in why


def test_down_before_verdict_same_second_restart_is_a_restart() -> None:
    """vm:check run vmc-11060119-8cbbc0 K1.9: the daemon restarted within the second the drill acted (start 1793929092, action 1793929092) with a new MainPID, and down() never ran; the row must say no down() ran, not that nothing restarted."""
    ok, why = k.down_before_verdict(
        [("up", 1793929093)], 1793929092, 1793929092, pids=(84380, 85230)
    )
    assert not ok
    assert "nothing restarted" not in why
    assert "no down line" in why
    ok, why = k.down_before_verdict([], 1793929092, 1793929092, pids=(84380, 84380))
    assert not ok
    assert "nothing restarted" in why
    assert "MainPID stayed 84380" in why


@pytest.mark.parametrize(
    ("issued", "at", "pids", "want"),
    [
        (100, 101, None, True),
        (100, 100, None, False),
        (100, 100, (7, 8), True),
        (100, 100, (7, 7), False),
        (100, 100, (0, 8), False),
        (100, 101, (7, 7), True),
    ],
)
def test_restarted(issued: int, at: int, pids: tuple[int, int] | None, want: bool) -> None:
    assert k.restarted(issued, at, pids) is want


def test_up_after_and_up_written_verdicts() -> None:
    assert k.up_after_verdict([("down", 100), ("up", 130)], 125)[0]
    assert not k.up_after_verdict([("up", 120)], 125)[0]
    assert not k.up_after_verdict([("up", 120)], 0)[0]
    assert k.up_written_verdict([("up", 1)])[0]
    assert not k.up_written_verdict([("down", 1)])[0]


def test_pid_unchanged_verdict() -> None:
    assert k.pid_unchanged_verdict(10, 10)[0]
    assert not k.pid_unchanged_verdict(10, 11)[0]
    assert not k.pid_unchanged_verdict(0, 0)[0]


@pytest.mark.parametrize(
    ("text", "want"),
    [("30min\n", True), ("1h", True), ("infinity", True), ("29min", False), ("x", False)],
)
def test_job_timeout_verdict(text: str, want: bool) -> None:
    assert k.job_timeout_verdict(text)[0] is want


def test_repo_names_and_config_name_are_run_scoped() -> None:
    grand, tag = k.repo_names(("vmc-11051000-abcdef-a", "vmc-11051000-abcdef-b"))
    assert grand == "k1-vmc-11051000-abcdef"
    assert tag == "k1b"
    # A grand is never a fork of the run's parent, so the stale-fork sweep cannot take it.
    assert not vm_check.FORK_TAG.match(grand)
    assert k.config_name("vmc-1") == "k1-vmc-1"


# --------------------------------------------------------------------------- the live rows on a fake worker


class _Res:
    def __init__(self, rc: int = 0, out: str = "", err: str = "") -> None:
        self.rc, self.out, self.err = rc, out, err

    def text(self) -> str:
        return self.out + self.err


class FakeWorker:
    """The worker's side of K1: two repositories with a unit, a MainPID, a start time and a probe log each, and a clock. `hook` decides whether a stop runs down() first (the fixed renet) or not (today's). The boolean fields let a test break one behaviour."""

    def __init__(self, *, hook: bool = True) -> None:
        self.hook = hook
        self.now = 1_800_000_000
        self.boot = 1_799_000_000
        self.nets: dict[int, dict[str, Any]] = {
            NID_A: {"guid": GUID_A, "pid": 100, "start": self.now - 500, "active": "active"},
            NID_B: {"guid": GUID_B, "pid": 200, "start": self.now - 500, "active": "active"},
        }
        self.units = {nid: unit_text(nid, n["guid"]) for nid, n in self.nets.items()}
        self.logs: dict[str, list[str]] = {GUID_A: [], GUID_B: []}
        self.job_timeout = "30min"
        self.reconcile_restores = True
        self.reconcile_restarts = False
        self.setup_restarts = False
        self.up_writes = True
        self.repo_up_restarts = True
        self.repo_up_rc = 0
        self.delete_grand_rc = 0
        self.comes_back = True
        # A skewed daemon's restart: down() through the old socket first (renet b63746a and the stop hook's fallback), or the heal restart first and down() after it (the order before b63746a).
        self.skew_down_first = True
        # A mount-only up whose restart ran down(): up() after it (renet b52db1b), or none (MountWithDocker before it).
        self.mount_restart_up = True
        self.plant_rc = 0
        self.root_calls: list[str] = []

    def tick(self, secs: int = 1) -> None:
        self.now += secs

    def nid_of(self, command: str) -> int:
        m = re.search(r"rediacc-docker-(\d+)|net-(\d+)\.json", command)
        assert m, command
        return int(m.group(1) or m.group(2))

    def ref_nid(self, ref: str) -> int:
        return NID_B if ref.endswith(":k1b") else NID_A

    def down(self, nid: int) -> None:
        self.logs[self.nets[nid]["guid"]].append("down %d" % self.now)
        self.tick(k.DOWN_SLEEP_S)

    def up(self, nid: int) -> None:
        self.tick()
        if self.up_writes:
            self.logs[self.nets[nid]["guid"]].append("up %d" % self.now)

    def restart(self, nid: int, *, down_first: bool) -> None:
        if down_first:
            self.down(nid)
        self.tick()
        net = self.nets[nid]
        net["pid"] += 1
        net["start"] = self.now
        net["active"] = "active"

    def restart_any(self, nid: int) -> None:
        """A renet-driven restart of `nid`: a skewed daemon follows `skew_down_first`, any other one `hook`."""
        net = self.nets[nid]
        if not net.pop("skewed", False):
            self.restart(nid, down_first=self.hook)
        elif self.skew_down_first:
            self.restart(nid, down_first=True)
        else:
            self.restart(nid, down_first=False)
            self.down(nid)

    def stop_side_on(self, nid: int) -> bool:
        return "ExecStop=" in self.units[nid]

    # -- root and rdc ---------------------------------------------------------

    def root(self, command: str) -> _Res:
        self.root_calls.append(command)
        self.tick()
        if "echo NOW=" in command:
            n = self.nets[self.nid_of(command)]
            return _Res(
                out="NOW=%d\nMAINPID=%d\nSTART=%d\nACTIVE=%s\n"
                % (self.now, n["pid"], n["start"], n["active"])
            )
        if command.startswith("systemctl cat"):
            return _Res(out=self.units[self.nid_of(command)])
        if command.startswith("cat ") and k.LOG_FILE in command:
            guid = GUID_A if GUID_A in command else GUID_B
            return _Res(out="".join(line + "\n" for line in self.logs[guid]))
        if command.startswith("systemctl restart"):
            nid = self.nid_of(command)
            self.restart(nid, down_first=self.hook and self.stop_side_on(nid))
            return _Res()
        if "FragmentPath" in command:
            return self._edit(command)
        if "repository reconcile" in command:
            return self._reconcile()
        if command.startswith("rm -f") and "runtime" in command:
            return _Res(out="REMOVED\n")
        if "JobTimeoutUSec" in command:
            return _Res(out=self.job_timeout + "\n")
        if "BOOT=" in command:
            return _Res(out="BOOT=%d\n" % self.boot)
        if command == "systemctl reboot":
            return self._reboot()
        if "PLANTED=" in command:
            m = re.search(r"/docker-(\d+)\.sock", command)
            assert m, command
            if self.plant_rc:
                return _Res(rc=self.plant_rc)
            self.nets[int(m.group(1))]["skewed"] = True
            return _Res(out="PLANTED=%s\n" % k.legacy_socket(m.group(1)))
        if command.startswith("renet daemon restart"):
            m = re.search(r"--network-id=(\d+)", command)
            assert m, command
            self.restart_any(int(m.group(1)))
            self.up(int(m.group(1)))
            return _Res()
        raise AssertionError("unexpected root command: %s" % command)

    def _edit(self, command: str) -> _Res:
        nid = self.nid_of(command)
        if "Environment=" in command:
            self.units[nid] = self.units[nid].replace("Environment=DOCKER_RAMDISK=true\n", "")
        else:
            self.units[nid] = re.sub(r"(?m)^(ExecStop|TimeoutStopSec)=.*\n", "", self.units[nid])
        return _Res(out="EDITED=/etc/systemd/system/x\n")

    def _reconcile(self) -> _Res:
        if self.reconcile_restarts:
            self.restart(NID_A, down_first=True)
        if self.reconcile_restores:
            for nid, n in self.nets.items():
                self.units[nid] = unit_text(nid, n["guid"], env="Environment=" in self.units[nid])
        return _Res()

    def _reboot(self) -> _Res:
        if not self.comes_back:
            return _Res(rc=255)
        if self.hook:
            for n in self.nets.values():
                self.logs[n["guid"]].append("down %d" % self.now)
        self.tick(k.DOWN_SLEEP_S + 30)
        self.boot = self.now
        self.nets[NID_A]["pid"] += 1
        self.nets[NID_A]["start"] = self.now + 5
        self.tick(10)
        self.logs[GUID_A].append("up %d" % self.now)
        self.nets[NID_B]["active"] = "inactive"
        return _Res(rc=255)

    def rdc(self, *args: str) -> _Res:
        self.tick()
        if args[:2] == ("repo", "up"):
            if self.repo_up_rc:
                return _Res(rc=self.repo_up_rc)
            nid = self.ref_nid(args[2])
            drifted = "Environment=" not in self.units[nid]
            if "--no-start" in args:
                # MountWithDocker: the same BeforeRestart down(), then up() only on a renet whose mount restart path runs it.
                if self.repo_up_restarts and drifted:
                    self.restart(nid, down_first=self.hook)
                    self.units[nid] = unit_text(nid, self.nets[nid]["guid"])
                    if self.mount_restart_up:
                        self.up(nid)
                return _Res()
            if self.repo_up_restarts and "Environment=" not in self.units[nid]:
                # The start side differs from the render: BeforeRestart runs down() (fixed renet) or not.
                self.restart(nid, down_first=self.hook)
                self.units[nid] = unit_text(nid, self.nets[nid]["guid"])
            self.up(nid)
            return _Res()
        if args[:2] == ("machine", "converge"):
            self.restart_any(NID_A)
            self.up(NID_A)
            return _Res()
        if args[:2] == ("machine", "setup"):
            if self.setup_restarts:
                self.restart(NID_A, down_first=True)
            return _Res()
        if args[:2] == ("repo", "delete") and ":" not in args[2]:
            return _Res(rc=self.delete_grand_rc)
        return _Res()


class FakeCtx:
    """The parts of a running VmCheck that K1 touches, routed to a FakeWorker."""

    machine = "ops-worker"
    run_id = "vmc-11051000-abcdef"
    tags = ("vmc-11051000-abcdef-a", "vmc-11051000-abcdef-b")
    ssh_user, ssh_key, worker_ip = "u", "k", "192.168.111.12"

    def __init__(self, tmp_path: pathlib.Path, worker: FakeWorker) -> None:
        self.work = str(tmp_path)
        self.root = str(tmp_path)
        self.worker = worker
        self.environ: dict[str, str] = {"ACCOUNT_ED25519_PUBLIC_KEY": "pub"}
        self.sweep_leftovers: list[str] = []
        self.rows: list[tuple[str, bool, str]] = []
        self.calls: list[tuple[str, ...]] = []
        self.host_hook: Any = None

    def rdc(self, *args: str, **_kw: Any) -> _Res:
        self.calls.append(("rdc", *args))
        return self.worker.rdc(*args)

    def host_run(self, argv: list[str], **kw: Any) -> _Res:
        command = argv[-1]
        if command.startswith("sudo sh -c "):
            return self.worker.root(shlex.split(command)[3])
        if self.host_hook is not None:
            return self.host_hook(argv, **kw)
        self.calls.append(("host", *argv))
        return _Res()

    def repo_list(self) -> tuple[_Res, list[dict[str, Any]]]:
        grand = k.repo_names(self.tags)[0]
        return _Res(), [
            {"name": grand, "guid": GUID_A, "networkId": NID_A},
            {"name": grand + ":k1b", "guid": GUID_B, "networkId": NID_B},
        ]

    def check(self, step: str, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        assert step == "K1"
        del res
        self.rows.append((desc, ok, evidence))
        return ok

    def remote_evidence(self, res: Any) -> str:
        return res.text()

    def scrub(self, text: str) -> str:
        return text


def _live(tmp_path: pathlib.Path, worker: FakeWorker) -> tuple[k._LiveK1, FakeCtx]:
    ctx = FakeCtx(tmp_path, worker)
    live = k._LiveK1(ctx)
    live.sleep = lambda _s: worker.tick(k.POLL_S)
    return live, ctx


def _ready(tmp_path: pathlib.Path, worker: FakeWorker) -> tuple[k._LiveK1, FakeCtx]:
    live, ctx = _live(tmp_path, worker)
    assert live._ids()
    ctx.rows.clear()
    return live, ctx


def _oks(ctx: FakeCtx, prefix: str) -> list[bool]:
    return [ok for desc, ok, _e in ctx.rows if desc.startswith(prefix)]


def test_k1_0_brings_up_a_grand_with_autostart_and_a_fork_without(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    live, ctx = _live(tmp_path, worker)
    assert live.k1_0_bring_up(), ctx.rows
    assert all(ok for _d, ok, _e in ctx.rows), ctx.rows
    rdc = [c for c in ctx.calls if c[0] == "rdc"]
    grand = live.grand
    assert rdc[0][1:4] == ("repo", "create", grand)
    fork_call = next(c for c in rdc if c[1:3] == ("repo", "fork"))
    assert fork_call[3:] == (grand, "--tag", "k1b", "--up")
    uploads = [c[4] for c in rdc if c[1:4] == ("repo", "sync", "upload")]
    assert uploads == [grand, grand + ":k1b"]
    enable = next(c for c in rdc if c[1:4] == ("repo", "admin", "autostart"))
    assert enable[4:] == ("enable", grand)
    probe = tmp_path / ("k1-%s" % ctx.run_id) / "probe" / "Rediaccfile"
    assert probe.read_text() == k.probe_rediaccfile()


def test_k1_0_fails_when_up_wrote_no_line(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.up_writes = False
    live, ctx = _live(tmp_path, worker)
    assert not live.k1_0_bring_up()
    assert _oks(ctx, "K1.0 k1-") == [False, False]


def test_k1_1_passes_on_the_new_unit_and_fails_on_the_old(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    live, ctx = _ready(tmp_path, worker)
    live.k1_1_unit_order()
    assert _oks(ctx, "K1.1") == [True]
    worker.units[NID_A] = unit_text(NID_A, GUID_A, stop=False)
    live.k1_1_unit_order()
    assert _oks(ctx, "K1.1") == [True, False]


@pytest.mark.parametrize("hook", [True, False])
def test_k1_2_raw_restart(tmp_path: pathlib.Path, hook: bool) -> None:
    worker = FakeWorker(hook=hook)
    live, ctx = _ready(tmp_path, worker)
    live.k1_2_raw_restart()
    # CONTROL (hook off): the restart writes no down line, so the row is FAIL.
    assert _oks(ctx, "K1.2") == [hook], ctx.rows
    assert "systemctl restart rediacc-docker-%d" % NID_A in worker.root_calls
    assert ctx.calls[-1][1:4] == ("repo", "up", live.ref_a)


@pytest.mark.parametrize("hook", [True, False])
def test_k1_3_unit_rewrite(tmp_path: pathlib.Path, hook: bool) -> None:
    worker = FakeWorker(hook=hook)
    live, ctx = _ready(tmp_path, worker)
    live.k1_3_unit_rewrite()
    assert _oks(ctx, "K1.3 A's unit") == [True]
    assert _oks(ctx, "K1.3 repo up") == [hook], ctx.rows


def test_k1_3_fails_when_repo_up_does_not_restart(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.repo_up_restarts = False
    live, ctx = _ready(tmp_path, worker)
    live.k1_3_unit_rewrite()
    assert _oks(ctx, "K1.3 repo up") == [False]
    assert "nothing restarted" in ctx.rows[-1][2]


def test_k1_4_restores_the_stop_side_without_a_restart(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    live, ctx = _ready(tmp_path, worker)
    live.k1_4_stop_side_drift()
    assert _oks(ctx, "K1.4") == [True, True], ctx.rows
    # CONTROL: a reconcile that does not patch the stop side.
    worker.reconcile_restores = False
    live.k1_4_stop_side_drift()
    assert _oks(ctx, "K1.4 one") == [True, False]


def test_k1_4_fails_when_the_tick_restarts_the_daemon(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.reconcile_restarts = True
    live, ctx = _ready(tmp_path, worker)
    live.k1_4_stop_side_drift()
    assert _oks(ctx, "K1.4 one") == [False]
    assert "MainPID before=100 after=101" in ctx.rows[-1][2]


@pytest.mark.parametrize("hook", [True, False])
def test_k1_5_converge(tmp_path: pathlib.Path, hook: bool) -> None:
    worker = FakeWorker(hook=hook)
    live, ctx = _ready(tmp_path, worker)
    live.k1_5_converge()
    assert _oks(ctx, "K1.5 A's") == [True]
    assert _oks(ctx, "K1.5 machine") == [hook], ctx.rows
    assert ("rdc", "machine", "converge", "ops-worker") in ctx.calls
    assert any("net-%d.json" % NID_A in c for c in worker.root_calls)


@pytest.mark.parametrize("down_first", [True, False])
def test_k1_9_skewed_restart(tmp_path: pathlib.Path, down_first: bool) -> None:
    worker = FakeWorker()
    worker.skew_down_first = down_first
    live, ctx = _ready(tmp_path, worker)
    live.k1_9_skewed_restart()
    assert _oks(ctx, "K1.9 A's daemon is skewed") == [True, True], ctx.rows
    # CONTROL (down_first off, the order before renet b63746a): the heal restarts the daemon first and down() runs after the new start, so both rows FAIL.
    assert _oks(ctx, "K1.9 machine converge") == [down_first], ctx.rows
    assert _oks(ctx, "K1.9 renet daemon restart") == [down_first], ctx.rows
    if not down_first:
        assert "did not finish first" in ctx.rows[1][2]
    plants = [c for c in worker.root_calls if "PLANTED=" in c]
    assert len(plants) == 2
    assert k.current_socket(NID_A) in plants[0]
    assert k.legacy_socket(NID_A) in plants[0]
    assert "renet daemon restart --network-id=%d" % NID_A in worker.root_calls
    assert ("rdc", "machine", "converge", "ops-worker") in ctx.calls


def test_k1_9_skips_the_restart_when_the_plant_fails(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.plant_rc = 1
    live, ctx = _ready(tmp_path, worker)
    live.k1_9_skewed_restart()
    assert _oks(ctx, "K1.9 A's daemon is skewed") == [False, False]
    assert not _oks(ctx, "K1.9 machine converge")
    assert not any(c.startswith("renet daemon restart") for c in worker.root_calls)


@pytest.mark.parametrize(
    ("hook", "mount_up", "want"),
    [
        (True, True, True),
        # CONTROL: MountWithDocker before renet b52db1b, restart with down() and no up() after it.
        (True, False, False),
        # CONTROL: a restart with no down() first.
        (False, True, False),
    ],
)
def test_k1_10_mount_restart(
    tmp_path: pathlib.Path, hook: bool, mount_up: bool, want: bool
) -> None:
    worker = FakeWorker(hook=hook)
    worker.mount_restart_up = mount_up
    live, ctx = _ready(tmp_path, worker)
    live.k1_10_mount_restart()
    assert _oks(ctx, "K1.10 A's unit") == [True]
    assert _oks(ctx, "K1.10 repo up") == [want], ctx.rows
    assert ("rdc", "repo", "up", live.ref_a, "--no-start") in ctx.calls
    if hook and not mount_up:
        assert "no up line" in ctx.rows[-1][2]


def test_k1_10_fails_when_the_mount_does_not_restart(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.repo_up_restarts = False
    live, ctx = _ready(tmp_path, worker)
    live.k1_10_mount_restart()
    assert _oks(ctx, "K1.10 repo up") == [False]
    assert "nothing restarted" in ctx.rows[-1][2]


def test_skew_sockets_follow_the_runtime_layout() -> None:
    assert k.current_socket(NID_A) == "%s/net-%d/docker-%d.sock" % (k.RUNTIME_DIR, NID_A, NID_A)
    assert k.legacy_socket(NID_A) == "%s/docker-%d.sock" % (k.RUNTIME_DIR, NID_A)


def test_plant_skew_script_moves_the_live_socket_to_the_old_path(tmp_path: pathlib.Path) -> None:
    """The plant run against a real listening unix socket in a scratch runtime dir: it moves to the old-layout path, still answers there, and nothing is left at the current path."""
    runtime = tmp_path / "run"
    (runtime / ("net-%d" % NID_A)).mkdir(parents=True)
    script = k.plant_skew_script(NID_A).replace(k.RUNTIME_DIR, str(runtime))
    cur = runtime / ("net-%d" % NID_A) / ("docker-%d.sock" % NID_A)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(str(cur))
        srv.listen(1)
        out = subprocess.run(
            ["bash", "-c", script], check=True, capture_output=True, text=True, timeout=30
        ).stdout
        old = runtime / ("docker-%d.sock" % NID_A)
        assert out.strip() == "PLANTED=%s" % old
        assert not cur.exists()
        cli = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        cli.connect(str(old))
        cli.close()
    finally:
        srv.close()


def _k1_6(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, worker: FakeWorker
) -> tuple[k._LiveK1, FakeCtx]:
    home = tmp_path / "home"
    (home / ".config" / "rediacc").mkdir(parents=True)
    (home / ".config" / "rediacc" / "dev.json").write_text('{"id": "x", "renetPath": "/r"}')
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)
    live, ctx = _ready(tmp_path, worker)
    binary = tmp_path / "renet-main"
    binary.write_bytes(b"main")
    sha = upgrade_converge.file_sha256(binary)
    monkeypatch.setattr(live, "_main_binary", lambda: binary)

    def host_hook(argv: list[str], **_kw: Any) -> _Res:
        if "INSTALLED" in argv[-1]:
            ctx.calls.append(("install", argv[-1]))
            return _Res(out="INSTALLED %s\n" % sha)
        ctx.calls.append(("host", *argv))
        return _Res()

    ctx.host_hook = host_hook
    return live, ctx


def _cfg_path(live: k._LiveK1) -> pathlib.Path:
    return pathlib.Path.home() / ".config" / "rediacc" / ("%s.json" % live.cfg)


def test_k1_6_rollout_passes_without_a_restart(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = FakeWorker()
    live, ctx = _k1_6(tmp_path, monkeypatch, worker)
    live.k1_6_rollout()
    assert all(ok for _d, ok, _e in ctx.rows), ctx.rows
    assert len(_oks(ctx, "K1.6 k1-")) == 2
    assert not live.main_installed
    steps = [c for c in ctx.calls if c[0] in ("rdc", "install")]
    assert steps[0][0] == "install"
    assert steps[1][1:4] == ("repo", "up", live.ref_a)
    assert steps[2][1:3] == ("machine", "setup")
    cfg = _cfg_path(live)
    assert oct(cfg.stat().st_mode & 0o777) == "0o600"
    assert '"renetPath": "%s"' % (tmp_path / "renet-main") in cfg.read_text()


def test_k1_6_fails_when_setup_restarts_a_daemon(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = FakeWorker()
    worker.setup_restarts = True
    live, ctx = _k1_6(tmp_path, monkeypatch, worker)
    live.k1_6_rollout()
    assert _oks(ctx, "K1.6 k1-") == [False, True], ctx.rows


def test_k1_6_fails_when_the_tick_leaves_the_old_stop_side(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = FakeWorker()
    worker.reconcile_restores = False
    worker.units = {nid: unit_text(nid, n["guid"], stop=False) for nid, n in worker.nets.items()}
    live, ctx = _k1_6(tmp_path, monkeypatch, worker)
    live.k1_6_rollout()
    assert _oks(ctx, "K1.6 k1-") == [False, False], ctx.rows


def test_k1_6_cleanup_reverts_a_worker_left_on_the_main_renet(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = FakeWorker()
    worker.repo_up_rc = 1
    live, ctx = _k1_6(tmp_path, monkeypatch, worker)
    live.k1_6_rollout()
    assert live.main_installed
    assert _oks(ctx, "K1.6 repo up") == [False]
    live.cleanup()
    setups = [c for c in ctx.calls if c[1:3] == ("machine", "setup")]
    assert len(setups) == 1
    assert not _cfg_path(live).exists()


def test_k1_6_main_binary_builds_the_main_pointer_with_the_key(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    live, ctx = _ready(tmp_path, worker)
    seen: list[tuple[list[str], dict[str, str]]] = []

    def host_hook(argv: list[str], **kw: Any) -> _Res:
        seen.append((argv, dict(kw.get("env") or {})))
        if argv[:2] == ["git", "rev-parse"]:
            return _Res(out="feedface\n")
        return _Res()

    ctx.host_hook = host_hook
    out = live._main_binary()
    assert out == tmp_path / ("k1-%s" % ctx.run_id) / "renet-main"
    assert seen[0][0] == ["git", "rev-parse", k.MAIN_POINTER]
    assert seen[1][0][:2] == ["bash", "-c"]
    assert "checkout --quiet feedface" in seen[1][0][2]
    assert seen[1][1]["ACCOUNT_ED25519_PUBLIC_KEY"] == "pub"
    assert all(ok for _d, ok, _e in ctx.rows)


def test_k1_8_job_timeout(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    live, ctx = _ready(tmp_path, worker)
    live.k1_8_job_timeout()
    worker.job_timeout = "15min"
    live.k1_8_job_timeout()
    assert _oks(ctx, "K1.8") == [True, False]


@pytest.mark.parametrize("hook", [True, False])
def test_k1_7_reboot(tmp_path: pathlib.Path, hook: bool) -> None:
    worker = FakeWorker(hook=hook)
    live, ctx = _ready(tmp_path, worker)
    live.k1_7_reboot()
    assert _oks(ctx, "K1.7 the worker") == [True, True]
    # CONTROL (no stop hook): neither repository wrote a down line before the boot.
    assert _oks(ctx, "K1.7 A's down") == [hook], ctx.rows
    assert _oks(ctx, "K1.7 B's down") == [hook], ctx.rows
    assert _oks(ctx, "K1.7 A is back") == [True]
    assert ("rdc", "repo", "up", live.ref_b, "--no-start") in ctx.calls
    assert "systemctl reboot" in worker.root_calls


def test_k1_7_fails_when_the_worker_never_comes_back(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.comes_back = False
    live, ctx = _ready(tmp_path, worker)
    live.k1_7_reboot()
    assert _oks(ctx, "K1.7 the worker comes") == [False]
    assert not _oks(ctx, "K1.7 A's down")


def test_execute_runs_the_rows_in_order_and_always_cleans_up(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live, _ctx = _live(tmp_path, FakeWorker())
    order: list[str] = []
    names = (
        "k1_0_bring_up",
        "k1_1_unit_order",
        "k1_2_raw_restart",
        "k1_3_unit_rewrite",
        "k1_4_stop_side_drift",
        "k1_5_converge",
        "k1_9_skewed_restart",
        "k1_10_mount_restart",
        "k1_6_rollout",
        "k1_8_job_timeout",
        "k1_7_reboot",
        "cleanup",
    )
    for name in names:
        monkeypatch.setattr(live, name, lambda n=name: order.append(n) or True)
    live.execute()
    assert order == list(names)


def test_execute_cleans_up_when_bring_up_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live, _ctx = _live(tmp_path, FakeWorker())
    order: list[str] = []
    monkeypatch.setattr(live, "k1_0_bring_up", lambda: order.append("k1_0") and False)
    monkeypatch.setattr(live, "k1_1_unit_order", lambda: order.append("k1_1"))
    monkeypatch.setattr(live, "cleanup", lambda: order.append("cleanup"))
    live.execute()
    assert order == ["k1_0", "cleanup"]


def test_cleanup_deletes_the_fork_before_the_grand(tmp_path: pathlib.Path) -> None:
    worker = FakeWorker()
    worker.delete_grand_rc = 1
    live, ctx = _live(tmp_path, worker)
    live.created_grand = live.created_fork = live.autostart_enabled = True
    live.cleanup()
    verbs = [c[1:4] for c in ctx.calls if c[0] == "rdc"]
    assert verbs == [
        ("repo", "admin", "autostart"),
        ("repo", "delete", live.ref_b),
        ("repo", "delete", live.ref_a),
    ]
    assert ctx.sweep_leftovers == ["K1 grand %s (delete rc=1)" % live.ref_a]


def test_no_hardcoded_mount_root() -> None:
    source = pathlib.Path(k.__file__).read_text()
    assert '"/mnt/rediacc' not in source

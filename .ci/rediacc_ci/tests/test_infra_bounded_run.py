"""`rediacc_ci.infra.bounded_run`, driven as a real process against stubs that outlive their limit.

Each case runs the module with `python3 -m`, exactly as the workflow step does, so the exit code, the heartbeat on stderr and the kill are observed from outside rather than inferred from a function's return value. The stub that stands in for `ops up` forks a child that stays in its process group and a second one that leaves through `setsid` and records its pid in a file, which is the shape QEMU's `-daemonize` produces.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from rediacc_ci.infra import bounded_run

CI_ROOT = pathlib.Path(__file__).resolve().parents[2]

STUB = textwrap.dedent(
    """\
    import os, subprocess, sys, time
    pidfile = sys.argv[1]
    member = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    guest = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], start_new_session=True)
    with open(pidfile + ".tmp", "w") as fh:
        fh.write(str(guest.pid))
    os.replace(pidfile + ".tmp", pidfile)
    with open(pidfile + ".member", "w") as fh:
        fh.write(str(member.pid))
    print("stub: started", flush=True)
    time.sleep(300)
    """
)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed child of an exited parent is reparented and reaped by init; a zombie still answers kill 0.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return True


class Run:
    """The wrapper as a child process whose streams go to files, not pipes: a guest that escapes the kill would hold a pipe open and hang `communicate`."""

    def __init__(self, tmp_path: pathlib.Path, *args: str) -> None:
        self.out_path, self.err_path = tmp_path / "stdout", tmp_path / "stderr"
        with (
            open(self.out_path, "w", encoding="utf-8") as out,
            open(self.err_path, "w", encoding="utf-8") as err,
        ):
            self.proc = subprocess.Popen(
                [sys.executable, "-m", bounded_run.__name__, *args],
                cwd=tmp_path,
                env=dict(os.environ, PYTHONPATH=str(CI_ROOT)),
                stdout=out,
                stderr=err,
            )

    def finish(self, timeout: float = 60) -> tuple[int, str, str]:
        rc = self.proc.wait(timeout=timeout)
        return (
            rc,
            self.out_path.read_text(encoding="utf-8"),
            self.err_path.read_text(encoding="utf-8"),
        )


def launch(tmp_path: pathlib.Path, *args: str) -> Run:
    return Run(tmp_path, *args)


def stub_cmd(tmp_path: pathlib.Path) -> tuple[list[str], pathlib.Path]:
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    vm_dir = tmp_path / "vm-1"
    vm_dir.mkdir()
    return [sys.executable, str(stub), str(vm_dir / "qemu.pid")], vm_dir


def assert_all_gone(vm_dir: pathlib.Path) -> None:
    guest = int((vm_dir / "qemu.pid").read_text())
    member = int((vm_dir / "qemu.pid.member").read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and (alive(guest) or alive(member)):
        time.sleep(0.1)
    assert not alive(member), f"process-group member {member} survived"
    assert not alive(guest), f"setsid guest {guest} survived"


def test_limit_kills_the_command_its_group_and_the_reaped_guest(tmp_path: pathlib.Path) -> None:
    cmd, vm_dir = stub_cmd(tmp_path)
    proc = launch(
        tmp_path,
        "--limit",
        "3",
        "--heartbeat",
        "1",
        "--reap-pidfiles",
        str(tmp_path / "vm-*" / "qemu.pid"),
        "--",
        *cmd,
    )
    rc, out, err = proc.finish()
    assert rc == 124, err
    assert "stub: started" in out
    assert "bounded_run" not in out, "diagnostics must stay off stdout"
    assert err.count("heartbeat ") >= 2, err
    assert "load=[" in err
    assert "top pid=" in err
    assert "TIMEOUT: still running after 3s" in err
    assert "every process the command started is gone" in err
    assert_all_gone(vm_dir)


def test_without_reap_the_setsid_guest_escapes_the_group_kill(tmp_path: pathlib.Path) -> None:
    """The control for the case above: the group kill alone does not reach a daemonized guest, which is why `--reap-pidfiles` exists."""
    cmd, vm_dir = stub_cmd(tmp_path)
    proc = launch(tmp_path, "--limit", "2", "--heartbeat", "5", "--", *cmd)
    rc, _, err = proc.finish()
    assert rc == 124, err
    guest = int((vm_dir / "qemu.pid").read_text())
    try:
        assert alive(guest), "the setsid guest was expected to survive a group-only kill"
    finally:
        os.kill(guest, signal.SIGKILL)


def test_a_command_that_finishes_keeps_its_exit_code_and_reaps_nothing(
    tmp_path: pathlib.Path,
) -> None:
    keep = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )
    (tmp_path / "vm-1").mkdir()
    (tmp_path / "vm-1" / "qemu.pid").write_text(str(keep.pid))
    try:
        proc = launch(
            tmp_path,
            "--limit",
            "30",
            "--reap-pidfiles",
            str(tmp_path / "vm-*" / "qemu.pid"),
            "--",
            sys.executable,
            "-c",
            "print('ok'); raise SystemExit(7)",
        )
        rc, out, err = proc.finish()
        assert rc == 7, err
        assert out == "ok\n"
        assert keep.poll() is None, "a finished run must leave the VMs it started running"
    finally:
        keep.kill()
        keep.wait()


def test_sigterm_from_the_runner_kills_everything(tmp_path: pathlib.Path) -> None:
    cmd, vm_dir = stub_cmd(tmp_path)
    proc = launch(
        tmp_path,
        "--limit",
        "60",
        "--heartbeat",
        "30",
        "--reap-pidfiles",
        str(tmp_path / "vm-*" / "qemu.pid"),
        "--",
        *cmd,
    )
    deadline = time.monotonic() + 20
    while not (vm_dir / "qemu.pid.member").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    proc.proc.send_signal(signal.SIGTERM)
    rc, _, err = proc.finish()
    assert rc == 128 + signal.SIGTERM, err
    assert "received signal" in err
    assert_all_gone(vm_dir)


@pytest.mark.parametrize("argv", [[], ["--limit", "0", "--", "true"], ["--limit", "5"]])
def test_refuses_a_missing_command_or_a_non_positive_limit(
    tmp_path: pathlib.Path, argv: list[str]
) -> None:
    proc = launch(tmp_path, *argv)
    rc, _, err = proc.finish()
    assert rc == 2, err

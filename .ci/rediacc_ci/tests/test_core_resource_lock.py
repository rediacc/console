"""`core.resource_lock`: one flock per named resource, a bounded wait that names the holder, and a wrapper for callers that are not Python (PLAN-push-decoupling.md L1).

Every test points `XDG_RUNTIME_DIR` at its own temporary directory, so no test meets a live vm:check's fleet lock. A holder is a separate process (`_Holder`), so the pid the waiter prints is provably the other process's.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

import pytest

from rediacc_ci.core import resource_lock
from rediacc_ci.drills import vm_check

CI_ROOT = pathlib.Path(__file__).resolve().parents[2]

HOLD_SCRIPT = """
import sys, time
from rediacc_ci.core import resource_lock
lock = resource_lock.ResourceLock(sys.argv[1])
lock.acquire(sys.argv[2], 5.0, session="holder01")
print("held", flush=True)
time.sleep(float(sys.argv[3]))
lock.release()
"""


@pytest.fixture
def runtime(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run_dir))
    monkeypatch.setenv("PYTHONPATH", str(CI_ROOT))
    return run_dir


class _Holder:
    """A second process holding `resource` until it is stopped or `hold_s` passes."""

    def __init__(self, resource: str, purpose: str, hold_s: float = 30.0) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-c", HOLD_SCRIPT, resource, purpose, str(hold_s)],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert self.proc.stdout is not None
        assert self.proc.stdout.readline().strip() == "held"

    @property
    def pid(self) -> int:
        return self.proc.pid

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait()
        if self.proc.stdout is not None:
            self.proc.stdout.close()


def test_second_holder_waits_and_names_the_first(runtime: pathlib.Path) -> None:
    holder = _Holder("fleet", "e2e-local reset")
    said: list[str] = []
    try:
        lock = resource_lock.ResourceLock("fleet", say=said.append)
        started = time.monotonic()
        with pytest.raises(resource_lock.ResourceBusyError) as exc:
            lock.acquire("second", wait_s=1.0)
        assert time.monotonic() - started >= 1.0
        message = str(exc.value)
        assert "pid %d" % holder.pid in message
        assert "purpose e2e-local reset" in message
        assert "session holder01" in message
        assert "since 20" in message
        assert said and "pid %d" % holder.pid in said[0]
    finally:
        holder.stop()


def test_waiter_takes_the_lock_once_the_holder_ends(runtime: pathlib.Path) -> None:
    holder = _Holder("bench-eu", "deploy", hold_s=0.6)
    try:
        lock = resource_lock.ResourceLock("bench-eu", say=lambda _line: None)
        waited = lock.acquire("reset", wait_s=10.0)
        assert waited > 0.1
        assert "purpose reset" in lock.holder()
        lock.release()
    finally:
        holder.stop()


def test_two_resources_do_not_block_each_other(runtime: pathlib.Path) -> None:
    holder = _Holder("bench-eu", "deploy")
    try:
        with resource_lock.held("bench-us", purpose="reset", wait_s=0.0) as lock:
            assert lock.path.name == "rediacc-bench-us.lock"
        with resource_lock.held("fleet", purpose="ops", wait_s=0.0):
            pass
        # Control: the same resource the holder has does block at once.
        with pytest.raises(resource_lock.ResourceBusyError):
            resource_lock.ResourceLock("bench-eu", say=lambda _line: None).acquire("x", wait_s=0.0)
    finally:
        holder.stop()


def _wrapper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.resource_lock", "run", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_wrapper_returns_the_child_exit_code(runtime: pathlib.Path) -> None:
    assert _wrapper("--resource", "fleet", "--", "sh", "-c", "exit 7").returncode == 7
    assert _wrapper("--resource", "fleet", "--", "true").returncode == 0


def test_wrapper_holds_the_lock_for_the_child(runtime: pathlib.Path) -> None:
    path = resource_lock.lock_path("fleet")
    probe = (
        "import fcntl,os,sys; fd=os.open(%r, os.O_RDONLY)\n"
        "try:\n fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB); sys.exit(0)\n"
        "except BlockingIOError: sys.exit(9)\n" % str(path)
    )
    done = _wrapper("--resource", "fleet", "--purpose", "probe", "--", sys.executable, "-c", probe)
    assert done.returncode == 9, done.stderr


def test_wrapper_frees_the_lock_when_the_child_is_killed(runtime: pathlib.Path) -> None:
    done = _wrapper("--resource", "fleet", "--", "sh", "-c", "kill -9 $$")
    assert done.returncode == 128 + 9
    with resource_lock.held("fleet", purpose="after", wait_s=0.0):
        pass


def test_wrapper_busy_exits_75_naming_the_holder_before_the_child(runtime: pathlib.Path, tmp_path: pathlib.Path) -> None:
    marker = tmp_path / "ran"
    holder = _Holder("fleet", "vm:check")
    try:
        done = _wrapper("--resource", "fleet", "--wait", "0.5", "--", "touch", str(marker))
    finally:
        holder.stop()
    assert done.returncode == resource_lock.EXIT_BUSY
    assert "pid %d" % holder.pid in done.stderr
    assert not marker.exists()


def test_fleet_is_the_vm_check_lock_file(runtime: pathlib.Path, tmp_path: pathlib.Path) -> None:
    assert resource_lock.lock_path("fleet") == vm_check.lock_path()
    # The /tmp fallback agrees too, when no runtime directory is this user's.
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "missing")}
    if not os.path.isdir("/run/user/%d" % os.getuid()):
        assert resource_lock.lock_path("fleet", env) == vm_check.lock_path(env)
    assert resource_lock.lock_path("bench-eu").parent == vm_check.lock_path().parent


def test_vm_check_holder_reads_in_the_module(runtime: pathlib.Path) -> None:
    """A payload vm:check's own Lock wrote (no purpose key) still names its pid."""
    path = vm_check.lock_path()
    path.write_text('{"pid": 4242, "session": "abcd1234", "since": "2026-11-18T10:00:00Z"}')
    assert resource_lock.ResourceLock("fleet").holder() == "pid 4242, purpose -, session abcd1234, since 2026-11-18T10:00:00Z"


def test_bad_resource_name_is_refused(runtime: pathlib.Path) -> None:
    with pytest.raises(ValueError):
        resource_lock.lock_path("../etc")
    assert resource_lock.bench_resource("EU") == "bench-eu"


NEST_SCRIPT = """
import subprocess, sys
from rediacc_ci.core import resource_lock
lock = resource_lock.ResourceLock("fleet")
lock.acquire("parent", 5.0)
child = (
    "import sys\\n"
    "from rediacc_ci.core import resource_lock\\n"
    "lock = resource_lock.ResourceLock('fleet', say=lambda _l: None)\\n"
    "try:\\n"
    "    lock.acquire('child', 0.0, nest=sys.argv[1] == 'nest')\\n"
    "except resource_lock.ResourceBusyError:\\n"
    "    print('busy'); sys.exit(0)\\n"
    "print('nested' if lock.nested else 'held')\\n"
)
for mode in ("nest", "flat"):
    print(subprocess.run([sys.executable, "-c", child, mode], capture_output=True, text=True).stdout.strip())
lock.release()
"""


def test_a_descendant_of_the_holder_enters_nested(runtime: pathlib.Path) -> None:
    done = subprocess.run([sys.executable, "-c", NEST_SCRIPT], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    # The descendant enters as nested; the control with nesting off is refused like any other waiter.
    assert done.stdout.split() == ["nested", "busy"]


def test_ancestors_names_the_parent_chain() -> None:
    chain = resource_lock.ancestors()
    assert chain and chain[0] == os.getppid()

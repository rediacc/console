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


@pytest.mark.usefixtures("runtime")
def test_second_holder_waits_and_names_the_first() -> None:
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
        assert said
        assert "pid %d" % holder.pid in said[0]
    finally:
        holder.stop()


@pytest.mark.usefixtures("runtime")
def test_waiter_takes_the_lock_once_the_holder_ends() -> None:
    holder = _Holder("bench-eu", "deploy", hold_s=0.6)
    try:
        lock = resource_lock.ResourceLock("bench-eu", say=lambda _line: None)
        waited = lock.acquire("reset", wait_s=10.0)
        assert waited > 0.1
        assert "purpose reset" in lock.holder()
        lock.release()
    finally:
        holder.stop()


@pytest.mark.usefixtures("runtime")
def test_two_resources_do_not_block_each_other() -> None:
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


@pytest.mark.usefixtures("runtime")
def test_wrapper_returns_the_child_exit_code() -> None:
    assert _wrapper("--resource", "fleet", "--", "sh", "-c", "exit 7").returncode == 7
    assert _wrapper("--resource", "fleet", "--", "true").returncode == 0


@pytest.mark.usefixtures("runtime")
def test_wrapper_holds_the_lock_for_the_child() -> None:
    path = resource_lock.lock_path("fleet")
    probe = (
        "import fcntl,os,sys; fd=os.open(%r, os.O_RDONLY)\n"
        "try:\n fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB); sys.exit(0)\n"
        "except BlockingIOError: sys.exit(9)\n" % str(path)
    )
    done = _wrapper("--resource", "fleet", "--purpose", "probe", "--", sys.executable, "-c", probe)
    assert done.returncode == 9, done.stderr


@pytest.mark.usefixtures("runtime")
def test_wrapper_frees_the_lock_when_the_child_is_killed() -> None:
    done = _wrapper("--resource", "fleet", "--", "sh", "-c", "kill -9 $$")
    assert done.returncode == 128 + 9
    with resource_lock.held("fleet", purpose="after", wait_s=0.0):
        pass


@pytest.mark.usefixtures("runtime")
def test_wrapper_busy_exits_75_naming_the_holder_before_the_child(tmp_path: pathlib.Path) -> None:
    marker = tmp_path / "ran"
    holder = _Holder("fleet", "vm:check")
    try:
        done = _wrapper("--resource", "fleet", "--wait", "0.5", "--", "touch", str(marker))
    finally:
        holder.stop()
    assert done.returncode == resource_lock.EXIT_BUSY
    assert "pid %d" % holder.pid in done.stderr
    assert not marker.exists()


@pytest.mark.usefixtures("runtime")
def test_fleet_is_the_vm_check_lock_file(tmp_path: pathlib.Path) -> None:
    assert resource_lock.lock_path("fleet") == vm_check.lock_path()
    # The /tmp fallback agrees too, when no runtime directory is this user's.
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "missing")}
    if not os.path.isdir("/run/user/%d" % os.getuid()):
        assert resource_lock.lock_path("fleet", env) == vm_check.lock_path(env)
    assert resource_lock.lock_path("bench-eu").parent == vm_check.lock_path().parent


@pytest.mark.usefixtures("runtime")
def test_vm_check_holder_reads_in_the_module() -> None:
    """A payload in the shape vm:check's own Lock writes (the same keys, no purpose) still names its pid."""
    path = vm_check.lock_path()
    path.write_text('{"pid": 4242, "session": "abcd1234", "since": "2026-11-18T10:00:00Z"}')
    assert (
        resource_lock.ResourceLock("fleet").holder()
        == "pid 4242, purpose -, session abcd1234, since 2026-11-18T10:00:00Z"
    )


@pytest.mark.usefixtures("runtime")
def test_bad_resource_name_is_refused() -> None:
    with pytest.raises(ValueError, match="lower-case letters"):
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


@pytest.mark.usefixtures("runtime")
def test_a_descendant_of_the_holder_enters_nested() -> None:
    done = subprocess.run(
        [sys.executable, "-c", NEST_SCRIPT], capture_output=True, text=True, timeout=30, check=False
    )
    assert done.returncode == 0, done.stderr
    # The descendant enters as nested; the control with nesting off is refused like any other waiter.
    assert done.stdout.split() == ["nested", "busy"]


def test_ancestors_names_the_parent_chain() -> None:
    chain = resource_lock.ancestors()
    if os.getppid() > 1:
        assert chain
        assert chain[0] == os.getppid()
    else:
        # The chain stops before pid 1, so a parent of 1 (a container entrypoint) is an empty chain.
        assert chain == []


def test_a_planted_symlink_is_refused_not_followed(
    runtime: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The /tmp fallback name is predictable: a link another user plants there must not be opened, and its target must stay untouched."""
    target = tmp_path / "victim"
    target.write_text("keep")
    link = resource_lock.lock_path("planted")
    assert link.parent == runtime
    link.symlink_to(target)
    lock = resource_lock.ResourceLock("planted")
    with pytest.raises(resource_lock.LockFileRefusedError, match="refusing lock file"):
        lock.acquire("test", 0.1)
    assert target.read_text() == "keep"
    assert lock.fd is None


def test_a_group_writable_lock_file_is_refused(runtime: pathlib.Path) -> None:
    path = resource_lock.lock_path("shared")
    assert path.parent == runtime
    path.write_text("")
    path.chmod(0o666)
    with pytest.raises(resource_lock.LockFileRefusedError, match="not group or world writable"):
        resource_lock.ResourceLock("shared").acquire("test", 0.1)
    assert path.exists()


def test_a_blank_bench_region_is_refused_not_one_shared_lock() -> None:
    """Finding 9297ee6f.2: `bench-` passed the name check, so an unset region took one lock for every caller."""
    for blank in ("", "  "):
        with pytest.raises(ValueError, match="bench region is required"):
            resource_lock.bench_resource(blank)
    with pytest.raises(ValueError, match="bench region is required"):
        with resource_lock.bench_held("", "test"):
            pass


@pytest.mark.parametrize("raw", ["abc", "1.5x", "nan", "inf", "-3"])
def test_a_bad_wait_setting_is_a_named_refusal_not_a_traceback(raw: str) -> None:
    """Finding 941d86d6.1: a ValueError out of `float()` reached no caller's handler."""
    with pytest.raises(resource_lock.WaitSettingError, match="BENCH_LOCK_WAIT_S"):
        resource_lock.env_wait("BENCH_LOCK_WAIT_S", {"BENCH_LOCK_WAIT_S": raw})
    assert issubclass(resource_lock.WaitSettingError, resource_lock.ResourceBusyError)


def test_a_blank_or_unset_wait_setting_is_the_default_and_a_number_is_read() -> None:
    assert resource_lock.env_wait("X", {}) == resource_lock.DEFAULT_WAIT_S
    assert resource_lock.env_wait("X", {"X": "  "}) == resource_lock.DEFAULT_WAIT_S
    assert resource_lock.env_wait("X", {"X": " 2.5 "}) == 2.5
    assert resource_lock.env_wait("X", {"X": "0"}) == 0.0


@pytest.mark.usefixtures("runtime")
def test_the_wrapper_refuses_a_bad_wait_setting_with_a_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESOURCE_LOCK_WAIT_S", "abc")
    done = _wrapper("--resource", "fleet", "--", "true")
    assert done.returncode == 2
    assert "RESOURCE_LOCK_WAIT_S" in done.stderr
    assert "Traceback" not in done.stderr


def test_bench_regions_are_taken_in_sorted_order_and_released_when_a_later_one_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 941d86d6.2: the deadlock-avoidance claim, driven through a recording `held`."""
    import contextlib

    events: list[str] = []

    @contextlib.contextmanager
    def held(name, *, purpose, wait_s):
        if name == "bench-us":
            raise resource_lock.ResourceBusyError(name, pathlib.Path("p"), "pid 1", wait_s)
        events.append("take " + name)
        try:
            yield name
        finally:
            events.append("release " + name)

    monkeypatch.setattr(resource_lock, "held", held)
    with pytest.raises(resource_lock.ResourceBusyError):
        with resource_lock.bench_held(["us", "eu", "asia", "eu"], "test"):
            raise AssertionError("the body must not run when a region is refused")
    assert events == ["take bench-asia", "take bench-eu", "release bench-eu", "release bench-asia"]


def test_parent_pid_falls_back_to_ps_when_proc_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 96e6f543.3: the macOS path, with /proc unreadable and `ps` answering."""
    seen: list[list[str]] = []

    def no_proc(_self: pathlib.Path, *_a: object, **_k: object) -> str:
        raise FileNotFoundError

    def ps(argv: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="  4321\n", stderr="")

    monkeypatch.setattr(pathlib.Path, "read_text", no_proc)
    monkeypatch.setattr(resource_lock.subprocess, "run", ps)
    assert resource_lock.parent_pid(99) == 4321
    assert seen == [["ps", "-o", "ppid=", "-p", "99"]]


def test_a_second_lock_object_in_the_holding_process_is_nested(runtime: pathlib.Path) -> None:
    """Finding 96e6f543.1/.2: the documented own-pid rule, and the release order it needs."""
    first = resource_lock.ResourceLock("fleet")
    second = resource_lock.ResourceLock("fleet", say=lambda _l: None)
    first.acquire("outer", 1.0)
    try:
        second.acquire("inner", 0.0)
        assert second.nested
        assert second.fd is None
    finally:
        second.release()
        first.release()
    with resource_lock.held("fleet", purpose="after", wait_s=0.0):
        pass


def test_a_fifo_at_the_lock_path_is_refused_by_open_and_unknown_to_holder(
    runtime: pathlib.Path,
) -> None:
    """Findings 546cdc58.1/.2: the type check of `open_lock_file`, and a `holder` that does not block on a planted FIFO."""
    path = resource_lock.lock_path("planted-fifo")
    os.mkfifo(path, 0o600)
    with pytest.raises(resource_lock.LockFileRefusedError, match="regular file"):
        resource_lock.open_lock_file("planted-fifo", path)
    assert resource_lock.ResourceLock("planted-fifo").holder() == "holder unknown"


def test_a_lock_file_owned_by_another_user_is_refused(
    runtime: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 546cdc58.2: the owner check, with the uid this process reports moved off the file's owner."""
    path = resource_lock.lock_path("foreign")
    path.write_text("")
    path.chmod(0o600)
    monkeypatch.setattr(resource_lock.os, "getuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(resource_lock.LockFileRefusedError, match="owned by uid"):
        resource_lock.open_lock_file("foreign", path)

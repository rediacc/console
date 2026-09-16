"""`rediacc_hooks.proc` against the real process table, on both backends.

THE ORACLE IS THE REAL TOOL, as in the shellscan differential: a live child
process is started, and `pgrep -f` / `ps` are asked about it alongside this
module. A test that only checked internal consistency would pass on a module
that read the wrong file, as long as it read it the same way twice.

BOTH BACKENDS RUN HERE, forced through `REDIACC_PROC_BACKEND`. The `ps` backend
is the macOS one, and it is exercised on Linux on purpose: a backend that is
only ever run on the platform nobody tests is a backend that is broken on the
day it is needed, and the guards it serves go quietly to sleep rather than
failing.
"""

import os
import shutil
import subprocess
import time
import uuid

import pytest

from rediacc_hooks import proc

BACKENDS = ("proc", "ps")

# The interpreter the fixture runs, by absolute path. See the fixture.
BASH = "/bin/bash"


@pytest.fixture
def child(tmp_path):
    """A real `bash <script>` process, which is the shape both guards hunt.

    Not a bare `sleep`: the guards look for an INTERPRETER executing a named
    script, so the fixture has to produce one or the assertions below would be
    about a shape that never occurs.
    """
    if not os.path.exists(BASH):
        pytest.skip("%s is not present on this host" % BASH)
    token = "shellscan-probe-%s" % uuid.uuid4().hex[:12]
    script = tmp_path / ("%s.sh" % token)
    # LONG ENOUGH THAT A LOADED SCHEDULER CANNOT OUTRUN IT. This was 9 seconds,
    # which is not a margin on a CI runner executing 15,968 tests across 22 xdist
    # workers: the child simply EXITED mid-test, both cmdline readers returned
    # "", and the trailing-space invariant below failed as `assert '' == ' '` --
    # a message describing a string comparison rather than the dead process that
    # caused it. Observed in job 104713219233.
    #
    # Teardown kills this unconditionally in a `finally`, so a generous lifetime
    # cannot leak: the child dies when the test does, not when its timer expires.
    lifetime_s = 600
    script.write_text("#!/usr/bin/env bash\nsleep %d\n" % lifetime_s, encoding="utf-8")
    # AN ABSOLUTE PATH, not `bash`. On this machine `bash` on PATH is a
    # coverage shim (`bashcov-sup`) that execs the real one, so the fixture
    # produced a process whose `comm` was `bashcov-sup` and, for a moment, TWO
    # processes matching the token -- which made the pgrep comparison below
    # race. The guards care about a real interpreter, so the fixture starts one.
    #
    # A SCRUBBED ENVIRONMENT, and that is not tidiness either. This repo sets
    # `BASH_ENV` and `BASHCOV_*` to a shell profiler, and an inherited
    # `BASHCOV_SHAPE` makes the spawned bash re-exec itself under a supervisor:
    # the process at this pid then reads
    # `.../bashcov-sup -- /bin/bash -B -- <script>` with `comm` = `bashcov-sup`,
    # and the real interpreter is its CHILD. The fixture wants a plain
    # interpreter, so it asks for one.
    popen = subprocess.Popen(
        [BASH, str(script)],
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/")},
    )
    # The process must be in the table before anything asks about it. Polling
    # beats a fixed pause: a fixed one is either flaky on a loaded machine or
    # slow on an idle one, and this suite runs on both.
    deadline = time.time() + 10
    while time.time() < deadline:
        if os.path.exists("/proc/%d/cmdline" % popen.pid):
            break
        time.sleep(0.02)
    try:
        yield {"pid": popen.pid, "token": token, "script": str(script)}
    finally:
        popen.kill()
        popen.wait()


@pytest.fixture
def forced(monkeypatch):
    def _force(name):
        monkeypatch.setenv(proc.BACKEND_ENV, name)
        assert proc.backend_name() == name

    return _force


def test_auto_picks_the_backend_the_host_can_serve(monkeypatch):
    monkeypatch.delenv(proc.BACKEND_ENV, raising=False)
    expected = "proc" if os.path.exists("/proc/self/cmdline") else "ps"
    assert proc.backend_name() == expected


def test_an_unknown_backend_is_refused_rather_than_silently_defaulted(monkeypatch):
    monkeypatch.setenv(proc.BACKEND_ENV, "procfs")
    with pytest.raises(proc.ProcError):
        proc.backend_name()


def test_the_seam_is_read_at_call_time(monkeypatch):
    """Flipping the variable between two calls must change the answer."""
    monkeypatch.setenv(proc.BACKEND_ENV, "ps")
    assert proc.backend_name() == "ps"
    monkeypatch.setenv(proc.BACKEND_ENV, "proc")
    assert proc.backend_name() == "proc"


@pytest.mark.parametrize("backend", BACKENDS)
def test_finds_a_live_shell_running_a_script(forced, child, backend):
    forced(backend)
    hits = proc.pgrep_full(child["token"])
    assert child["pid"] in hits, "backend %s did not see pid %d" % (backend, child["pid"])
    assert proc.comm(child["pid"]) == "bash"
    assert proc.is_shell(child["pid"])
    assert child["script"] in proc.cmdline(child["pid"])


@pytest.mark.parametrize("backend", BACKENDS)
def test_matches_real_pgrep(forced, child, backend):
    """The differential half: same pattern, same answer as procps."""
    if shutil.which("pgrep") is None:
        pytest.skip("pgrep is not installed on this host")
    forced(backend)
    real = subprocess.run(["pgrep", "-f", "--", child["token"]], capture_output=True, check=False)
    expected = sorted(int(p) for p in real.stdout.split())
    # The token is a fresh uuid, so exactly one process on the machine can
    # match it. Pinning that first turns any later disagreement into a real
    # difference rather than a race between two listings taken microseconds
    # apart on a machine where processes come and go.
    assert expected == [child["pid"]]
    assert proc.pgrep_full(child["token"]) == expected


@pytest.mark.parametrize("backend", BACKENDS)
def test_cmdline_forms_agree_with_the_shell_pipeline(forced, child, backend):
    """`cmdline` is the pgrep form; `cmdline_tr` is the `tr` form.

    The two differ by exactly one trailing space, and the guards consume the
    second one. Measured on a live `sleep 19`: `pgrep -f 'sleep 19$'` matches
    and `pgrep -f 'sleep 19 $'` does not.
    """
    forced(backend)
    pid = child["pid"]
    # SAY WHICH THING BROKE, AND TEST THE RIGHT THING. A pid that is fully gone
    # reads as None (pinned below in test_a_dead_process_is_absent_and_not_an_error),
    # but job 104713219233 produced `assert '' == ' '` -- an EMPTY string, not
    # None. That is a ZOMBIE: the child had exited, `/proc/<pid>/cmdline` still
    # existed, and reading it returned nothing. So `os.path.exists` is the wrong
    # precondition here, because it passes for exactly the state that broke it.
    # The honest precondition is that the read produced something.
    live = proc.cmdline(pid)
    assert live, (
        "the fixture's child is not running -- an empty cmdline means it exited "
        "(zombie) or was reaped. That is a test-lifetime problem, not a "
        "disagreement between the two cmdline forms"
    )
    assert proc.cmdline_tr(pid) == live + " "
    assert not live.endswith(" ")
    assert proc.argv(pid)[0] == BASH


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_dead_process_is_absent_and_not_an_error(forced, backend):
    """A pid that exited between the listing and the read reads as None.

    The distinction matters to the guards: "gone" means the script is not being
    run, while an exception would take down the hook and, with it, every other
    guard in the chain.
    """
    forced(backend)
    dead = 2**22 - 1  # above the default pid_max, so it cannot be live
    assert proc.comm(dead) is None
    assert proc.argv(dead) is None
    assert proc.cmdline(dead) is None
    assert proc.is_shell(dead) is False


@pytest.mark.parametrize("backend", BACKENDS)
def test_kernel_threads_are_invisible_the_way_pgrep_makes_them(forced, backend):
    """`pgrep -f '^$'` matches nothing, and neither may this."""
    forced(backend)
    assert proc.pgrep_full("^$") == []


def test_both_backends_see_this_very_process(monkeypatch):
    """The one comparison that is not about a fixture: the running pytest.

    Its pid must appear in both backends' listings, which is the cheapest
    possible proof that the ps backend is reading the same table and not, say,
    silently returning an empty list on a host where its flags are wrong.
    """
    seen = {}
    for backend in BACKENDS:
        monkeypatch.setenv(proc.BACKEND_ENV, backend)
        seen[backend] = proc.pids()
        assert os.getpid() in seen[backend], "%s backend lost its own process" % backend
    # Not an equality: processes start and exit between the two listings, and a
    # test that demanded identical sets would be flaky on a busy machine for a
    # reason that has nothing to do with the code.
    overlap = set(seen["proc"]) & set(seen["ps"])
    assert len(overlap) > 10

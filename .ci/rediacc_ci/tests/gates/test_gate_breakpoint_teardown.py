"""Port of `.ci/scripts/test/gates/test-breakpoint-teardown.sh`.

Proves that breakpoint teardown kills what it started and NOTHING ELSE, and that it is safe to run again.

THE BUG CLASS THIS TARGETS, BY NAME. The deleted `.github/actions/tmate` action tore down with a pattern-kill over `tmate.*new-session` and an `rm -f` glob under `/tmp`. Both reach outside their own job. On a runner hosting two concurrent jobs, the first to finish killed the other's live session and deleted its logs, and the victim job saw an unexplained disconnect. A pattern-kill
cannot tell "my process" from "a process that looks like mine", so `.ci/breakpoint/lib/breakpoint-common.sh` records PIDs and kills only those. That is a property no amount of reading proves, so this file starts REAL processes: some recorded in the state dir, one deliberately not, and then checks which ones survive.

Idempotence gets the same treatment. Teardown runs from `if: always()` and again from the nightly sweeper, so "already clean" is the NORMAL second call. A second run that exits 1 turns every swept session into a red workflow, and a red-by-default gate is one nobody reads.

`HOME` IS A TEMP DIR IN EVERY INVOCATION, deliberately and not for tidiness: `stop-breakpoint.sh` ends by removing `~/.cloudflared/*.json`, which on a developer laptop would take out real cloudflared credentials. This file must not be the thing that demonstrates that.

WHAT THE PORT RESPELLS. The twin needs a `bp_alive` helper because a killed child of the test's own shell is a ZOMBIE until it is reaped and `kill -0` succeeds on a zombie, so the naive liveness test reports every successfully killed process as still running. `Popen.poll()` reaps as it reports, so the zombie window cannot exist here and the helper is not reproduced. The BOUNDED
wait is reproduced, for the twin's stated reason: an unbounded wait on a teardown that failed to kill hangs the suite instead of failing it.

WHY THE DRIVER PORTED THIS AND NOT AN AGENT. `agent/8f55d4f0/W7P3-batch5-brief.md` records six `test-breakpoint-*.sh` subjects as unportable by any agent under the standard brief and NOT on merit, because plant-verifying one means temporarily writing under `.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching. The brief's two ways out are to hand one batch owner
that path explicitly or to exclude them in the derivation with the reason recorded, and it adds "Do not silently drop them a fourth time." This is the first option: `.ci/breakpoint` is the driver's path.

`xdist_group` IS DECLARED, and this is the case the brief means. These cases spawn real processes and assert which of them are alive afterwards, and the subject under test is a script whose entire job is killing things. Running two copies concurrently is not a risk worth taking on the reasoning that each only kills what it recorded.
"""

import os
import subprocess
import time

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-breakpoint-teardown.sh"

pytestmark = pytest.mark.xdist_group("breakpoint-teardown")

STOP = paths.from_root(".ci", "breakpoint", "scripts", "stop-breakpoint.sh")
WORKFLOW = paths.from_root(".ci", "breakpoint", "workflow", "breakpoint.yml")

# The twin polls for up to ~10s, then gives up. Bounded ON PURPOSE.
GONE_TIMEOUT_S = 10.0
GONE_POLL_S = 0.05

# How long a fixture process stays alive if nothing kills it. Long enough that the assertions below are about teardown rather than about a race with its own exit.
FIXTURE_LIFETIME_S = "300"


def start_sleeper() -> subprocess.Popen:
    """A long-lived background child whose streams go nowhere.

    The discarded stdout is load-bearing in the twin, where the helper is called through command substitution and a child inheriting that pipe blocks the caller for the full lifetime. It is kept here because a child holding a pipe nobody drains is a hazard in any language, not because Python needs it.
    """
    return subprocess.Popen(
        ["sleep", FIXTURE_LIFETIME_S],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def alive(proc: subprocess.Popen) -> bool:
    """`poll()` reaps as it reports, so a killed child is never a zombie here."""
    return proc.poll() is None


def wait_gone(proc: subprocess.Popen) -> bool:
    deadline = time.monotonic() + GONE_TIMEOUT_S
    while time.monotonic() < deadline:
        if not alive(proc):
            return True
        time.sleep(GONE_POLL_S)
    return not alive(proc)


def kill_quietly(proc: subprocess.Popen) -> None:
    if alive(proc):
        proc.kill()
    proc.wait(timeout=10)


def record_pid(state, name: str, pid: int) -> None:
    """Write the pidfile exactly as `bp_record_pid` does, WITHOUT sourcing
    `breakpoint-common.sh`: the test must exercise the FILE LAYOUT contract, not share
    an implementation with the thing it is testing."""
    pids = state / "pids"
    pids.mkdir(parents=True, exist_ok=True)
    (pids / ("%s.pid" % name)).write_text("%d\n" % pid, encoding="utf-8")


def run_stop(tmp, **extra: str) -> harness.RunResult:
    """Invoke teardown against the temp state dir, streams MERGED as the twin merges
    them, and the environment REPLACED as the twin's `env -i` replaces it."""
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.fspath(tmp / "home"),
        "RUNNER_TEMP": os.fspath(tmp),
    }
    env.update(extra)
    result = harness.run([bash, os.fspath(STOP)], env=env, env_replace=True)
    return harness.RunResult(result.rc, result.combined, "")


def prepared(tmp):
    (tmp / "home").mkdir(parents=True, exist_ok=True)
    return tmp / "breakpoint"


def test_the_subject_is_present(gate):
    if not os.access(STOP, os.X_OK):
        gate.log_fail(
            "subject under test is missing or not executable: %s" % paths.relative_to_root(STOP)
        )
    gate.log_pass("stop-breakpoint.sh is present and executable")


def test_kills_recorded_pids(gate):
    with harness.temp_dir() as tmp:
        state = prepared(tmp)
        tmate = start_sleeper()
        origin = start_sleeper()
        try:
            record_pid(state, "tmate", tmate.pid)
            record_pid(state, "origin", origin.pid)
            if not alive(tmate) or not alive(origin):
                gate.log_fail("fixture is broken: a fixture process never started")

            run = run_stop(tmp)
            gate.assert_exit_code(
                0, run.rc, "teardown with live recorded pids must succeed: %s" % run.out
            )
            if not wait_gone(tmate):
                gate.log_fail("tmate pid %d survived teardown" % tmate.pid)
            if not wait_gone(origin):
                gate.log_fail("origin pid %d survived teardown" % origin.pid)
            if state.is_dir():
                gate.log_fail("teardown left the state dir %s behind" % state)
        finally:
            kill_quietly(tmate)
            kill_quietly(origin)
    gate.log_pass("teardown kills every recorded pid and removes the state dir")


def test_second_teardown_is_clean(gate):
    """`GITHUB_RUN_ID` is set for BOTH calls so the second one still has a derivable
    identity and walks the whole script (the sweeper's shape) rather than taking the early "nothing to do" exit. That is the call that has to be green, and the early
    exit would hide it."""
    with harness.temp_dir() as tmp:
        state = prepared(tmp)
        proc = start_sleeper()
        try:
            record_pid(state, "cloudflared", proc.pid)
            run = run_stop(tmp, GITHUB_RUN_ID="990011")
            gate.assert_exit_code(0, run.rc, "first teardown must succeed: %s" % run.out)
            if not wait_gone(proc):
                gate.log_fail("recorded pid %d survived the first teardown" % proc.pid)

            run = run_stop(tmp, GITHUB_RUN_ID="990011")
            gate.assert_exit_code(
                0,
                run.rc,
                "SECOND teardown against clean state must exit 0, not 1: %s" % run.out,
            )
        finally:
            kill_quietly(proc)
    gate.log_pass("a second teardown over already-clean state exits 0 (sweeper re-run is normal)")


def test_no_state_dir_at_all(gate):
    with harness.temp_dir() as tmp:
        state = prepared(tmp)
        if state.is_dir():
            gate.log_fail("fixture is broken: the state dir should not exist yet")
        run = run_stop(tmp)
        gate.assert_exit_code(0, run.rc, "teardown with no state at all must exit 0: %s" % run.out)
        gate.assert_contains(
            run.out, "nothing to stop", "it should say why there was nothing to do"
        )
    gate.log_pass("teardown with no state dir and no derivable identity exits 0")


def test_stale_pidfile_is_not_an_error(gate):
    """A pid that has already exited: the normal state after a runner reboot, or when
    the process died on its own before teardown ran."""
    with harness.temp_dir() as tmp:
        state = prepared(tmp)
        dead = subprocess.Popen(["true"])
        dead.wait(timeout=10)
        if alive(dead):
            gate.log_fail("fixture is broken: pid %d should be gone already" % dead.pid)

        record_pid(state, "tmate", dead.pid)
        record_pid(state, "cloudflared", dead.pid)

        run = run_stop(tmp)
        gate.assert_exit_code(0, run.rc, "a stale pidfile must not fail teardown: %s" % run.out)
        gate.assert_not_contains(
            run.out, "No such process", "a stale pid must not leak a kill(1) error"
        )
    gate.log_pass("a stale pidfile is handled silently and exits 0")


def test_does_not_touch_unrecorded_processes(gate):
    """BLAST RADIUS -- the assertion the deleted tmate action would have failed."""
    with harness.temp_dir() as tmp:
        state = prepared(tmp)
        mine = start_sleeper()
        # A process breakpoint never started and never recorded. It is the same binary
        # with the same argv as the recorded one, ON PURPOSE: that is exactly what a
        # concurrent job's tmate looked like to a pattern-kill.
        theirs = start_sleeper()
        try:
            record_pid(state, "tmate", mine.pid)
            run = run_stop(tmp)
            gate.assert_exit_code(0, run.rc, "teardown must succeed: %s" % run.out)
            if not wait_gone(mine):
                gate.log_fail("recorded pid %d survived teardown" % mine.pid)
            if not alive(theirs):
                gate.log_fail(
                    "BLAST RADIUS: teardown killed unrecorded pid %d "
                    "(a concurrent job's process)" % theirs.pid
                )
        finally:
            kill_quietly(mine)
            kill_quietly(theirs)
    gate.log_pass("an identical-looking process breakpoint never recorded is left alive")


def test_no_pattern_kill_or_tmp_glob(gate):
    """The banned constructs are present in the header comment as an explanation of what
    NOT to do, so the scan has to look at code only."""
    body = STOP.read_text(encoding="utf-8")
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    gate.assert_not_contains(code, "pkill -f", "pkill -f reaches into a concurrent job's processes")
    gate.assert_not_contains(code, "pkill", "no pattern-kill of any shape")
    gate.assert_not_contains(
        code, "rm -f /tmp/", "an rm glob under /tmp reaches another job's files"
    )
    gate.assert_not_contains(code, "killall", "killall is a pattern-kill by another name")
    # And the reason is written down where the next editor will see it.
    gate.assert_contains(
        body, "KILLS ONLY RECORDED PIDS", "the header must state the rule it obeys"
    )
    gate.log_pass("stop-breakpoint.sh contains no pkill / killall / rm -f /tmp glob")


def test_workflow_teardown_is_always(gate):
    """`if: always()` is what makes teardown run after a FAILED or CANCELLED session.
    Without it the tunnel outlives the job on exactly the runs where something went
    wrong -- the runs most likely to have left a shell open."""
    if not WORKFLOW.is_file():
        gate.log_fail("workflow template is missing: %s" % paths.relative_to_root(WORKFLOW))
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    anchor = "      - name: Teardown"
    step = ""
    for index, line in enumerate(lines):
        if line == anchor:
            step = "\n".join(lines[index : index + 3])
            break
    if not step:
        gate.log_fail("no 'Teardown' step found in %s" % paths.relative_to_root(WORKFLOW))
    gate.assert_contains(step, "if: always()", "the Teardown step must carry if: always()")
    gate.log_pass("workflow Teardown step is guarded by if: always()")

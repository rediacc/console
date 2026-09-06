"""`rediacc_ci.proc` against GNU `timeout(1)` and against `common.sh`, three ways.

THE THINGS BEING REPLACED, and every case below runs the real one:

  * GNU `timeout(1)` -- 12 live invocation sites in 4 files, none of which guards
    for its absence, and all of which are already forbidden by
    `.ci/scripts/security/check-commands.sh:38` under a matcher that does not
    fire (see `rediacc_ci.proc`'s docstring for the two reasons).
  * `.ci/scripts/lib/common.sh:233-262` `run_with_timeout` -- the portable bash
    replacement that already exists.
  * `.ci/scripts/lib/common.sh:187-210` `retry_with_backoff` -- 8 call sites.

HOW THE RETRY SCHEDULE IS OBSERVED WITHOUT WAITING FOR IT. `retry_with_backoff`
calls `sleep "$delay"`, and a bash FUNCTION named `sleep` shadows the binary. The
differential defines one that prints its argument instead of sleeping, so the
exact schedule the bash implementation would follow is read out in milliseconds
rather than in the 6 to 62 seconds the real call sites take. The Python side gets
the same treatment through `proc.retry_with_backoff(sleep=...)`, which is why
that parameter exists.

WHAT A GREEN HERE DOES NOT MEAN. These cases prove the two implementations agree
on exit codes, on the backoff schedule, and on which of them enforces a deadline.
They say nothing about behaviour under a filled pipe buffer or a signal storm,
because neither implementation is exercised that way anywhere in this tree.
"""

import os
import pathlib
import shlex
import signal
import subprocess
import time

import pytest

from rediacc_ci import proc
from rediacc_ci.tests import differential as diff

COMMON_SH = ".ci/scripts/lib/common.sh"

# Short on purpose. Every case below waits for real wall clock, and a suite that
# takes a minute is a suite people stop running. 0.4s is comfortably longer than
# process startup on this host and comfortably shorter than a human's patience.
FAST = 0.4


def bash_rc(script: str) -> int:
    """The exit code of a bash snippet, with two traps handled once rather than per case.

    TRAP ONE: common.sh sets `set -euo pipefail` when sourced, so
    `run_with_timeout 1 false; echo $?` never reaches the echo -- the shell aborts
    at the non-zero. Every case that wants a code has to capture it with
    `|| rc=$?`, and having one helper stops a case silently measuring 0 because it
    forgot.

    TRAP TWO, and it is a measurement rather than a preference: the whole script
    is run with both streams on /dev/null. `common.sh:246-249` backgrounds a
    watchdog SUBSHELL that runs `sleep "$timeout_secs"`, then kills the subshell
    and not the sleep. The orphaned sleep inherits the harness's pipes, and
    `subprocess.run` waits for EOF on those pipes rather than merely for the child
    to exit -- so `run_with_timeout 5 true` took 5.15 SECONDS to observe before
    this redirect, for a command that had finished in milliseconds. The exit code
    is unaffected, and it is the only thing these cases read.

    That is the same leak `test_the_bash_timeout_leaks_grandchildren...` asserts
    directly, showing up here as a cost rather than as a failure.
    """
    rc, _out, _err = diff.bash_streams("{ %s\n} >/dev/null 2>&1" % script)
    return rc


# ---------------------------------------------------------------------------
# ANTI-VACUITY: the things being compared against must actually be here
# ---------------------------------------------------------------------------


def test_gnu_timeout_is_present_for_the_differential():
    """Without it, every timeout comparison below silently compares nothing.

    This is also the measurement behind the module's central claim: `timeout(1)`
    is a GNU coreutils binary that this repo assumes and macOS does not ship.
    """
    found = proc.which("timeout")
    assert found, "GNU timeout(1) is required to run this differential"
    assert os.access(found, os.X_OK)


def test_common_sh_defines_both_functions_being_replaced():
    """ANTI-VACUITY for the bash side of every case below."""
    with open("%s/%s" % (diff.repo(), COMMON_SH), encoding="utf-8") as handle:
        body = handle.read()
    assert "run_with_timeout() {" in body
    assert "retry_with_backoff() {" in body
    assert "return 124" in body, "the 124 convention must still be in the original"


# ---------------------------------------------------------------------------
# The exit-code matrix: three implementations, same answers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["true"], 0),
        (["false"], 1),
        (["sh", "-c", "exit 7"], 7),
        (["sh", "-c", "exit 42"], 42),
    ],
)
def test_exit_codes_agree_across_gnu_timeout_bash_and_python(command, expected):
    """A command that finishes in time reports its own code through all three."""
    quoted = " ".join(shlex.quote(word) for word in command)
    gnu = bash_rc("timeout 5 %s" % quoted)
    bash = bash_rc(
        "source %s; rc=0; run_with_timeout 5 %s || rc=$?; exit $rc" % (COMMON_SH, quoted)
    )
    python = proc.run_with_timeout(command, 5).returncode
    assert (gnu, bash, python) == (expected, expected, expected)


def test_a_timeout_is_124_in_all_three():
    """The one code the whole tree keys on. `scripts/ci-runner/pool.ts:39` names it."""
    gnu = bash_rc("timeout 1 sleep 5")
    bash = bash_rc("source %s; rc=0; run_with_timeout 1 sleep 5 || rc=$?; exit $rc" % COMMON_SH)
    result = proc.run_with_timeout(["sleep", "5"], 1)
    assert (gnu, bash, result.returncode) == (124, 124, 124)
    assert result.timed_out is True


def test_the_timeout_actually_fires_rather_than_the_command_finishing():
    """CONTROL for the case above.

    `sleep 5` under a 1-second bound must be cut short. Without this, a machine
    where `sleep` failed instantly would give 124 for the wrong reason on one
    side and 0 on the others -- and the assertion above would have caught that,
    but only by accident. This states the property directly.
    """
    started = time.monotonic()
    result = proc.run_with_timeout(["sleep", "5"], FAST)
    elapsed = time.monotonic() - started
    assert result.timed_out
    assert elapsed < 3.0, "the deadline was not enforced (%.2fs)" % elapsed


def test_a_missing_binary_is_127_and_not_an_exception():
    """Matching wl_git.py:110 and wl_reggate.py:763, and matching the shell.

    The shell's own answer for "command not found" is 127, so a Python wrapper
    that raised FileNotFoundError instead would force every call site to grow a
    try/except that none of the bash sites needed.
    """
    result = proc.run(["definitely-not-a-real-binary-9f3a"], timeout=5)
    assert result.returncode == proc.SPAWN_FAILED_RC
    assert result.ok is False
    assert bash_rc("definitely-not-a-real-binary-9f3a") == 127


# ---------------------------------------------------------------------------
# The three defects the port does not reproduce
# ---------------------------------------------------------------------------


def test_neither_bash_timeout_enforces_its_deadline_and_this_one_does():
    """DEFECT 1, measured in both directions.

    A child that traps SIGTERM outlives both bash bounds. GNU timeout reports 124
    but only once the child finished on its own; common.sh reports **0**, so the
    timeout is not merely late, it is invisible. SIGKILL cannot be trapped, so
    the Python side ends at its deadline.

    ASSERTED IN BOTH DIRECTIONS on purpose. If a future coreutils starts passing
    `--kill-after` by default, or common.sh grows one, this fails and the
    divergence gets re-decided rather than silently disappearing.
    """
    trapper = r'bash -c "trap \"\" TERM; sleep 2"'

    started = time.monotonic()
    gnu = bash_rc("timeout 1 %s" % trapper)
    gnu_elapsed = time.monotonic() - started
    assert gnu == 124
    assert gnu_elapsed > 1.5, "GNU timeout still waits for a TERM-ignoring child"

    started = time.monotonic()
    bash = bash_rc(
        "source %s; rc=0; run_with_timeout 1 %s || rc=$?; exit $rc" % (COMMON_SH, trapper)
    )
    bash_elapsed = time.monotonic() - started
    assert bash == 0, "common.sh reports SUCCESS for a command it failed to stop"
    assert bash_elapsed > 1.5

    started = time.monotonic()
    result = proc.run_with_timeout(["bash", "-c", 'trap "" TERM; sleep 2'], 1)
    python_elapsed = time.monotonic() - started
    assert result.returncode == 124
    assert result.timed_out is True
    assert python_elapsed < 2.0, "SIGKILL must end it at the deadline (%.2fs)" % python_elapsed


def test_the_bash_timeout_leaks_grandchildren_and_this_one_does_not(tmp_path):
    """DEFECT 2, proven by asking the operating system whether the pid is alive.

    `common.sh:248` signals exactly one pid, so a shell that backgrounds work and
    waits leaves that work running after the wrapper has "timed out". The
    grandchild writes its own pid before sleeping, and signal 0 then asks "does
    this process exist" without delivering anything.

    THE `>/dev/null 2>&1` IS LOAD-BEARING, and finding out why cost a confusing
    red. A leaked grandchild INHERITS the pipes the harness gave the outer bash,
    and `subprocess.run` waits for EOF on those pipes, not merely for the child
    to exit. So without the redirect the harness blocks for the grandchild's full
    five seconds, the grandchild is dead by the time the assertion runs, and the
    leak that is really happening reads as absent. The redirect hands the
    grandchild /dev/null so the harness returns when the wrapper does.

    That is worth stating beyond this test: a process that outlives its parent
    while holding its parent's stdout is invisible to anything that measures the
    parent, which is one of the ways a hung CI job reports nothing at all.
    """
    marker = tmp_path / "grandchild.pid"
    inner = "(echo $BASHPID > '%s'; sleep 5) & wait" % marker

    bash_rc(
        "source %s; rc=0; run_with_timeout 1 bash -c %s >/dev/null 2>&1 || rc=$?; exit $rc"
        % (COMMON_SH, shlex.quote(inner))
    )
    leaked = int(marker.read_text().strip())
    assert _alive(leaked), "common.sh:248 signals one pid, so the grandchild survives"
    os.kill(leaked, signal.SIGKILL)  # do not leave it behind for the rest of the suite

    marker.unlink()
    proc.run_with_timeout(["bash", "-c", inner], 1)
    tracked = int(marker.read_text().strip())
    # The group kill is asynchronous, so poll rather than assert instantly. A bare
    # assertion here would be flaky in the one direction that matters least.
    for _ in range(40):
        if not _alive(tracked):
            break
        time.sleep(0.05)
    assert not _alive(tracked), "the session kill must reach the grandchild"


def _alive(pid: int) -> bool:
    """Does this pid exist? Signal 0 asks without delivering anything."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_the_bash_retry_discards_the_exit_code_and_this_one_keeps_it():
    """DEFECT 3, both directions.

    `common.sh:208-209` is `log_error ...; return 1`, so 127 (not installed), 7
    (a real finding) and 124 (timed out every time) all arrive at the caller as
    1. `retry_command` returns the last Result intact.
    """
    bash = bash_rc(
        "source %s; sleep() { :; }; rc=0; retry_with_backoff 3 1 sh -c 'exit 5' || rc=$?; exit $rc"
        % COMMON_SH
    )
    assert bash == 1, "bash collapses every failure to 1"

    result = proc.retry_command(["sh", "-c", "exit 5"], attempts=3, delay=1, sleep=lambda _s: None)
    assert result.returncode == 5
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# The backoff schedule, compared against what bash would actually sleep
# ---------------------------------------------------------------------------


def bash_schedule(attempts: int, delay: int) -> list[int]:
    """The delays `common.sh:retry_with_backoff` would sleep, read out instantly.

    A bash function named `sleep` shadows the binary, so this replaces the wait
    with a print. `6 2` -- the parameterisation at `run-account-e2e.sh:194` --
    would otherwise take 62 seconds to observe.
    """
    script = (
        "source %s\n"
        "sleep() { printf 'SLEPT %%s\\n' \"$1\"; }\n"
        "rc=0\n"
        "retry_with_backoff %d %d sh -c 'exit 1' || rc=$?\n" % (COMMON_SH, attempts, delay)
    )
    _rc, out, _err = diff.bash_streams(script)
    return [int(line.split()[1]) for line in out.splitlines() if line.startswith("SLEPT ")]


@pytest.mark.parametrize(
    ("attempts", "delay"),
    [
        (3, 2),  # cleanup-versions.sh x6
        (3, 10),  # install-deps.sh x2
        (6, 2),  # run-account-e2e.sh:194
        (1, 5),  # the degenerate case: one attempt, no sleep at all
        (2, 1),
    ],
)
def test_the_backoff_schedule_matches_common_sh_exactly(attempts, delay):
    """Every parameterisation in the tree, compared delay by delay."""
    assert bash_schedule(attempts, delay) == [int(d) for d in proc.backoff_delays(attempts, delay)]


def test_the_schedule_probe_really_sees_the_sleeps():
    """CONTROL: if the `sleep` shadow stopped working, every list would be empty
    and every comparison above would compare [] to [] for the 1-attempt case and
    fail loudly for the rest. This pins the interesting direction directly."""
    assert bash_schedule(3, 2) == [2, 4]
    assert bash_schedule(1, 5) == []


def test_there_are_attempts_minus_one_delays_never_attempts():
    """`common.sh:200` sleeps only when another attempt is coming.

    An off-by-one here adds a final unused delay to every exhausted retry in the
    tree -- 32 wasted seconds on the `6 2` call site alone, invisible in a log.
    """
    for attempts in range(1, 7):
        assert len(proc.backoff_delays(attempts, 1)) == attempts - 1


def test_the_backoff_is_exponential_base_two_with_no_jitter_and_no_cap():
    """Pinned because all fifteen bash implementations agree on it.

    None uses jitter and none has a cap, so a port that added either would be
    quietly different from every call site it replaces -- and jitter in
    particular would make the differential above non-deterministic.
    """
    assert proc.backoff_delays(5, 1) == [1.0, 2.0, 4.0, 8.0]
    assert proc.backoff_delays(4, 3, factor=3.0) == [3.0, 9.0, 27.0]


# ---------------------------------------------------------------------------
# retry_with_backoff's own behaviour
# ---------------------------------------------------------------------------


def test_it_stops_at_the_first_success_and_sleeps_only_between_failures():
    calls = []
    slept = []
    outcome = proc.retry_with_backoff(
        lambda: calls.append(1) or (len(calls) >= 2),
        attempts=5,
        delay=1,
        sleep=slept.append,
    )
    assert outcome.ok is True
    assert outcome.attempts == 2
    assert len(calls) == 2
    assert slept == [1.0]


def test_it_retries_on_any_falsy_result_matching_every_bash_loop():
    """No implementation in the tree distinguishes retryable from fatal."""
    for falsy in (False, 0, "", None, []):
        seen = []
        outcome = proc.retry_with_backoff(
            lambda: seen.append(1) or falsy,  # noqa: B023
            attempts=3,
            delay=0,
            sleep=lambda _s: None,
        )
        assert outcome.ok is False
        assert len(seen) == 3


def test_an_exception_propagates_rather_than_being_retried():
    """A TypeError in the action is a caller defect, not a flaky network."""
    seen = []

    def boom():
        seen.append(1)
        raise TypeError("caller is wrong")

    with pytest.raises(TypeError):
        proc.retry_with_backoff(boom, attempts=3, delay=0, sleep=lambda _s: None)
    assert len(seen) == 1, "it must not be retried"


def test_on_retry_sees_every_intermediate_failure():
    """The hook that replaces common.sh:201's `Attempt N/M failed` log line."""
    seen = []
    proc.retry_with_backoff(
        lambda: False,
        attempts=3,
        delay=2,
        sleep=lambda _s: None,
        on_retry=lambda a, t, d, _r: seen.append((a, t, d)),
    )
    assert seen == [(1, 3, 2.0), (2, 3, 4.0)]


def test_zero_attempts_is_refused_rather_than_silently_doing_nothing():
    """A retry that never calls its action is a check that cannot fail."""
    with pytest.raises(ValueError, match="at least 1"):
        proc.retry_with_backoff(lambda: True, attempts=0)
    with pytest.raises(ValueError, match="at least 1"):
        proc.backoff_delays(0)


# ---------------------------------------------------------------------------
# run()'s own contract
# ---------------------------------------------------------------------------


def test_stdout_and_stderr_are_returned_separately():
    """Rule 3, and the 2026-09-06 stream-swap incident. There is no merge option."""
    result = proc.run(["bash", "-c", "printf OUT; printf ERR >&2; exit 3"], timeout=5)
    assert result.stdout == "OUT"
    assert result.stderr == "ERR"
    assert result.returncode == 3
    assert not hasattr(result, "output")


def test_partial_output_survives_a_timeout():
    """The second communicate() after the kill. Partial output is the evidence.

    A child that prints and then hangs is the single most common real timeout,
    and dropping what it printed removes the only clue about where it got to.
    """
    result = proc.run(["bash", "-c", "printf HALF; sleep 5"], timeout=FAST)
    assert result.timed_out
    assert result.stdout == "HALF"


def test_stdin_is_closed_by_default():
    """A command that decides to prompt must fail, not hang.

    `cat` with no argument reads stdin; against /dev/null it gets EOF at once.
    Inheriting the caller's stdin is the latent hang the module docstring names,
    and only one of the tree's nineteen Python call sites closes it today.
    """
    result = proc.run(["cat"], timeout=2)
    assert result.ok
    assert result.stdout == ""


def test_input_text_is_the_only_way_stdin_is_open():
    result = proc.run(["cat"], input_text="fed in", timeout=5)
    assert result.stdout == "fed in"


def test_env_replaces_rather_than_extends():
    """Matching subprocess itself. A silent extend is how a differential lies."""
    result = proc.run(["env"], env={"ONLY": "this"}, timeout=5)
    assert result.stdout.strip() == "ONLY=this"


def test_cwd_is_honoured_and_accepts_a_path_object(tmp_path):
    result = proc.run(["pwd"], cwd=tmp_path, timeout=5)
    assert result.stdout.strip() == str(pathlib.Path(tmp_path).resolve())


def test_result_is_falsy_on_failure_and_truthy_on_success():
    """`if run(...)` must mean what it reads as. A NamedTuple would always be True."""
    assert bool(proc.run(["true"], timeout=5)) is True
    assert bool(proc.run(["false"], timeout=5)) is False


def test_describe_names_the_command_and_what_happened():
    assert "exited 3" in proc.run(["sh", "-c", "exit 3"], timeout=5).describe()
    described = proc.run_with_timeout(["sleep", "5"], FAST).describe()
    assert "timed out" in described
    assert "sleep 5" in described


def test_there_is_no_shell_form():
    """Every string-form call site is a word-splitting bug waiting for a space."""
    result = proc.run(["echo", "a b; touch /tmp/should-not-exist-9f3a"], timeout=5)
    assert result.stdout.strip() == "a b; touch /tmp/should-not-exist-9f3a"
    assert not pathlib.Path("/tmp/should-not-exist-9f3a").exists()


def test_which_answers_from_the_given_path_only():
    """So a differential can control it rather than inheriting the developer's."""
    assert proc.which("sh", {"PATH": "/bin:/usr/bin"})
    assert proc.which("sh", {"PATH": "/nonexistent"}) is None


def test_subprocess_is_reachable_at_all():
    """ANTI-VACUITY for every case in this file."""
    assert subprocess.run(["true"], check=False, capture_output=True).returncode == 0

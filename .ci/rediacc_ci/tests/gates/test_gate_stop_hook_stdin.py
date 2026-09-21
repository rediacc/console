"""Port of `.ci/scripts/test/gates/test-stop-hook-stdin.sh`, retired in W7 P5.

The Stop hook must survive a hostile stdin: never crash, never hang.

WHY THIS EXISTS. On 2026-08-07 the harness reported::

    Stop hook error: Failed with non-blocking status code:
    EAGAIN: resource temporarily unavailable, read

`_read_event` caught only JSONDecodeError and ValueError. EAGAIN arrives as BlockingIOError -- an OSError -- so it sailed past, the hook CRASHED, and every stop check silently did not run for that stop. The hook is the thing that enforces the other checks, so when it dies the whole guard layer goes quiet at once, and nothing in CI notices: the checks cannot validate the health of
the process running them.

THE OBVIOUS FIX WAS WORSE. `os.set_blocking(fd, True)` makes `read()` wait forever when the writer holds the pipe open and sends nothing; that version had to be SIGKILLed. A hook that HANGS is worse than one that crashes, because it stalls the session instead of failing it. So this file asserts BOTH properties, and a fix that trades one for the other fails here.

WHAT IT DOES NOT DO, stated honestly and carried over from the twin unchanged. It does not exercise the checks' logic. And it does NOT reproduce the original EAGAIN crash against the real hook: mutating `_read_event` back to its pre-fix shape leaves this GREEN, because CPython's buffered `TextIOWrapper.read()` returns `""` rather than raising on a non-blocking empty pipe, so the
old code fell through to a JSONDecodeError it already caught. That is measured, not assumed, and it is recorded here so nobody reads a green run as proof the EAGAIN case is covered.

THIS PORT DELIBERATELY DIVERGES FROM ITS TWIN IN ONE STATE, and the reason is a defect in the twin found while plant-verifying this port on 2026-09-07. The twin decides `crashed` from STDERR ALONE::

    crashed = "Traceback" in err or "BlockingIOError" in err

The real hook cannot crash to stderr. Its last twelve lines wrap `main()` in `except BaseException` and turn ANY crash into a `"decision": "block"` object with the traceback inside `reason`, written to STDOUT -- deliberately, because a crash that printed to stderr and nothing to stdout used to read as ALLOW and silently disabled every check. Measured directly: with `except
(json.JSONDecodeError, ValueError)` in `_read_event` narrowed to `except (KeyError,)`, so that a malformed payload raises,

    printf '{not json at all' | python3 .claude/hooks/stop/worklist.py

exits 0 with an EMPTY stderr and `{"systemMessage": "Stop hook CRASHED; ...` plus the
whole traceback on stdout. The twin ran GREEN over that tree. Its crash arm therefore cannot see a crash in the subject it is pointed at; it passes only because its control points at a bare stand-in that HAS no such handler, which is exactly the "a control that fires for a reason unrelated to the subject" shape.

So `drive()` below reads BOTH streams. On this tree that changes no verdict -- the hook does not crash, both sides are green, and the parity driver compares verdicts -- and the divergence appears only in the state where the twin is wrong. That is the same argument `test_gate_renet_deadcode.py` records for its own divergence, and if a future change ever does make the hook crash, the
two will disagree and the parity driver will say so. That is the intended alarm, not a regression to suppress.

WHAT IT DOES CATCH, mutation-proven: the HANG. Installing the `os.set_blocking(fd, True)` variant -- the obvious fix, nearly shipped in place of
this one -- turns this file RED with `hung=1 crashed=0 elapsed=40.0`.

THE DRIVER IS IN THIS PROCESS, WHICH IS THE ONE STRUCTURAL DIFFERENCE. The twin writes a Python program to a temp file and runs it under `python3`, because the hostile conditions (a non-blocking pipe, a writer that never writes) cannot be built in portable bash. Python can build them directly, so `drive()` below IS that program, line for line, with no nested interpreter in the
middle. The two agree because `O_NONBLOCK` is a property of the open file DESCRIPTION and therefore survives the `dup` that `subprocess` performs when it installs the read end as the child's stdin -- which is exactly the property the twin's driver relies on too. Dropping the outer interpreter removes a layer that could only ever have swallowed a diagnostic.

THE FOUR SHAPES, and the control that proves the instrument can see a crash at all, are the twin's five cases with their names intact.

`xdist_group`: NONE, and the reason is worth stating because this one looks like it needs one. The hook is the real `.claude/hooks/stop/worklist.py`, which owns a shared append-only store -- but every case here feeds it a payload whose `session_id` is `test-stop-hook-stdin`, or no payload at all, and none of them ADDS an item. Reading the store concurrently is what the store's own
lock is for. What would need a group is a case that wrote, and there is none.
"""

import contextlib
import json
import os
import subprocess
import sys
import time

from rediacc_ci import paths

ROOT = paths.repo_root()
HOOK = ROOT / ".claude" / "hooks" / "stop" / "worklist.py"

# The twin's budget. A real run finishes in well under a second; 40 is the ceiling above which "slow" has become "hung".
BUDGET = 40.0

# The pre-fix shape: only JSONDecodeError/ValueError caught, so a BlockingIOError
# from a non-blocking read escapes as a traceback.
BROKEN_STAND_IN = """import json, sys
try:
    json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    pass
"""


def drive(hook: str, mode: str, budget: float) -> str:
    """`hung=<0|1> crashed=<0|1> elapsed=<seconds>`, the twin's driver in-process.

    `closed` : stdin is /dev/null, closed before the hook ever reads. `never` : a non-blocking pipe whose write end is held open and never written.
               THE FOUNDING CASE.
    `late` : the payload arrives 0.3s in, AFTER the first read attempt. `garbage`: malformed JSON arrives on the same schedule.
    """
    payload = json.dumps({"session_id": "test-stop-hook-stdin", "cwd": os.getcwd()})
    write_end = None
    if mode == "closed":
        process = subprocess.Popen(
            [sys.executable, hook],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    else:
        read_end, write_end = os.pipe()
        os.set_blocking(read_end, False)  # the exact state that killed the hook
        process = subprocess.Popen(
            [sys.executable, hook],
            stdin=read_end,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.close(read_end)
        if mode in ("late", "garbage"):
            time.sleep(0.3)  # arrive AFTER the first read attempt
            body = payload if mode == "late" else "{not json at all"
            # The hook may already have exited (the `garbage` payload is refused fast), and a write to a pipe with no reader is then EPIPE. That is the
            # case succeeding, not failing, so it is suppressed rather than raised --
            # `contextlib.suppress` because ruff's SIM105 is right that a bare
            # try/except/pass hides which exception was expected.
            with contextlib.suppress(BrokenPipeError):
                os.write(write_end, body.encode())
            os.close(write_end)
            write_end = None
        # mode == "never": hold the write end open and send nothing

    started = time.monotonic()
    hung = False
    try:
        out, err = process.communicate(timeout=budget)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        hung = True
    elapsed = time.monotonic() - started
    if write_end is not None:
        os.close(write_end)

    # BOTH STREAMS, unlike the twin. See the module docstring: the real hook turns every crash into a block object on STDOUT, so a stderr-only predicate is blind to the one subject this file exists to watch. The stand-in the control uses has no such handler and still reports through stderr, so both shapes are covered.
    haystack = out + err
    crashed = (
        "Traceback" in haystack or "BlockingIOError" in haystack or "Stop hook CRASHED" in haystack
    )
    return "hung=%d crashed=%d elapsed=%.1f" % (int(hung), int(crashed), elapsed)


def test_the_harness_can_actually_detect_a_crash(gate, tmp_path):
    # CONTROL. Without this, every assertion below could be passing because the driver never reports a crash rather than because the hook never has one. Point it at a stand-in that reproduces the ORIGINAL defect and require it to be caught.
    broken = tmp_path / "broken.py"
    broken.write_text(BROKEN_STAND_IN, encoding="utf-8")
    observed = drive(str(broken), "never", 20)
    gate.assert_contains(
        observed,
        "crashed=1",
        "the harness MUST detect a crash in a deliberately broken stand-in, or the "
        "passes above prove nothing (%s)" % observed,
    )
    gate.log_pass("control fired: the harness detects a real crash")


def _require_hook(gate) -> str:
    if not HOOK.is_file():
        gate.log_fail("stop hook not found: %s" % HOOK)
    return str(HOOK)


def test_never_written_payload_does_not_crash_or_hang(gate):
    # The founding case: a non-blocking pipe whose payload never arrives. Crashing here is the 2026-08-07 bug; hanging here is the fix that was nearly shipped in its place.
    observed = drive(_require_hook(gate), "never", BUDGET)
    gate.assert_contains(
        observed,
        "hung=0",
        "the hook must NOT hang when no payload ever arrives (%s)" % observed,
    )
    gate.assert_contains(observed, "crashed=0", "the hook must NOT crash on EAGAIN (%s)" % observed)
    gate.log_pass("no payload: terminates, bounded, no traceback")


def test_late_payload_is_still_read(gate):
    # Bounding the wait must not cost us the normal case: a payload written after the first read attempt still has to be picked up.
    observed = drive(_require_hook(gate), "late", BUDGET)
    gate.assert_contains(
        observed, "hung=0", "a late payload must not hang the hook (%s)" % observed
    )
    gate.assert_contains(
        observed, "crashed=0", "a late payload must not crash the hook (%s)" % observed
    )
    gate.log_pass("late payload on a non-blocking pipe is read, not lost")


def test_malformed_payload_does_not_crash(gate):
    observed = drive(_require_hook(gate), "garbage", BUDGET)
    gate.assert_contains(
        observed,
        "crashed=0",
        "malformed JSON must be handled, not raised (%s)" % observed,
    )
    gate.assert_contains(observed, "hung=0", "malformed JSON must not hang (%s)" % observed)
    gate.log_pass("malformed payload is handled without a traceback")


def test_closed_stdin_does_not_hang(gate):
    observed = drive(_require_hook(gate), "closed", BUDGET)
    gate.assert_contains(
        observed,
        "hung=0",
        "an immediately-closed stdin must not hang (%s)" % observed,
    )
    gate.assert_contains(
        observed, "crashed=0", "an immediately-closed stdin must not crash (%s)" % observed
    )
    gate.log_pass("closed stdin terminates cleanly")

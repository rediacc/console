"""Running a command, bounding it in time, and retrying it. One implementation.

WHAT IT REPLACES, AND THE MEASUREMENT BEHIND EACH CLAIM (2026-09-06).

`timeout(1)`. 12 invocation sites across 4 files: `.ci/lib/setup.sh:582,583,714, 768,787,837`, `.ci/scripts/test/gates/test-profiler-report.sh:399,410,467,491` (retired in W7 P5 census batch A8, its cases carried by `.ci/rediacc_ci/tests/gates/test_gate_profiler_report.py`), and a one-line `bounded()` wrapper in each of `.ci/scripts/ci/scope-shadow.sh:116` and
`.ci/scripts/ci/scope-reconcile-shadow.sh:99`. Not one of the twelve guards
for the binary's absence: there is no `gtimeout` fallback, no `command -v
timeout`, no `TIMEOUT_BIN` anywhere in the tree. GNU coreutils is assumed, and macOS does not ship it.

That assumption is not merely undocumented, it is BANNED and the ban does not fire. `.ci/scripts/security/check-commands.sh:38` lists `"timeout|not on macOS - use background + sleep + kill pattern"` among its forbidden commands, and the gate passes today with all twelve sites live, for two independent reasons in its own matcher -- both reported to the root driver rather than fixed
here, because that file has another writer:

  1. The `$(` alternative in its pattern is written inside DOUBLE quotes as
     `"...|\\$\\(|..."`, which the shell collapses to `$\\(`; ERE then reads the
     `$` as an end-of-line anchor, so `x=$(timeout 5 true)` can never match.
  2. The outer grep includes an `^\\s*if\\s+` alternative and the inner confirming
     grep does not, so every `if timeout ...` finding is found and then silently
     dropped.

`.ci/breakpoint/lib/breakpoint-common.sh:27-29` states the same ban for its own vendored corpus -- "no seq(1), no timeout(1), no mapfile" -- so the intent is consistent; only the enforcement is broken.

`common.sh:run_with_timeout`. `.ci/scripts/lib/common.sh:233-262` already carries a portable bash replacement, and it is the one this module is checked against. It backgrounds the command, backgrounds a watchdog that sleeps then SIGTERMs it, and maps the resulting 143 to 124.

`retry_with_backoff`. `.ci/scripts/lib/common.sh:187-210`: exponential base 2, no jitter, no cap, delay taken from the caller, sleeps only BETWEEN attempts, retries on ANY non-zero exit. 8 call sites in two parameterisations (`3 2` in `cleanup-versions.sh` x6, `3 10` in `install-deps.sh` x2, `6 2` in `run-account-e2e.sh:194`). Beside it live seven hand-rolled loops with three
different shapes -- linear `attempt * k` for k in {5, 15, 30}, and constant-delay
-- in `docker-prepull.sh:34`, `simulate-promotion.sh:79` and `:159`, `initialize.sh:233`, `verify-edge-endpoints.sh:63`, `test-install-methods.sh:840` and `wait-for-preview-worker.sh:99`.

THE EXIT-CODE CONTRACT, WHICH IS NOT AN INVENTION. Every producer in the tree already agrees, so this module adopts rather than proposes:

    124  timed out       common.sh:260, wl_git.py:107, wl_reggate.py:761
    127  could not spawn wl_git.py:110, wl_reggate.py:763
    137  SIGKILL         appears in PROSE only (scripts/eslint-heap.sh:14). Nothing
                         in the repo branches on it, so nothing here produces it.

`scripts/ci-runner/pool.ts:38-40` writes the convention down: "1 is a finding, 2 is usage, 124 is a timeout, 127 is not-found (which is a genuine breakage, not a considered 'cannot run')". 77 is the separate "could not run" code and belongs to gates, not to this layer.

THREE DEFECTS IN THE ORIGINALS THAT THIS MODULE DOES NOT REPRODUCE. Each is measured, each is asserted by a differential test, and each is stated here so a future reader does not "restore compatibility" by putting it back.

  1. NEITHER BASH TIMEOUT ACTUALLY ENFORCES ITS DEADLINE. Measured on this host:
     `timeout 1 bash -c 'trap "" TERM; sleep 3'` returns 124 after 3020 ms, and
     `run_with_timeout 1 bash -c 'trap "" TERM; sleep 3'` returns **0** after
     3037 ms -- the timeout is not merely late, it is not reported at all. Both
     send SIGTERM and then wait forever; GNU timeout needs `--kill-after` for the
     second signal and no call site in this repo passes it. Python's
     `Popen.kill()` sends SIGKILL, which cannot be trapped, so the same case here
     returns 124 after 999 ms.

  2. KILLING THE CHILD LEAVES THE GRANDCHILDREN. `common.sh:248` signals exactly
     one pid. `bash -c 'sleep 300 & wait'` therefore leaves `sleep 300` running
     after the wrapper has "timed out" -- which in CI is a job that finishes and
     a process that does not. This module puts the child in its own session
     (`start_new_session=True`) and signals the whole group.

  3. THE ORIGINAL EXIT CODE IS THROWN AWAY BY THE RETRY. `common.sh:208-209`
     ends `log_error ...; return 1` regardless of what the command actually
     exited with, so a caller cannot tell 127 (not installed) from 1 (failed)
     after three attempts. `retry_command` here returns the LAST Result intact.

WHY EVERY CALL PASSES stdin=DEVNULL. Of the 19 Python subprocess call sites
surveyed in this tree, exactly one closes stdin: `.claude/hooks/context/ precompact-floor.py:59`. The rest inherit it, which is a latent hang: a command
that decides to prompt -- `git` without `GIT_TERMINAL_PROMPT=0`, `gh` when its
token expired, `sudo` -- blocks on a terminal nobody is watching, and the symptom is a CI job that runs to its own 15-minute cap having printed nothing.

WHY stdout AND stderr ARE NEVER MERGED. Rule 3 of this repo's session defaults, and the 2026-09-06 emit-advisory stream-swap incident: merging them destroys the evidence for a whole class of defect. `Result` carries both separately and there is no `combine` option.
"""

import contextlib
import os
import signal
import subprocess
import time

# The codes, named once. See the module docstring for where each already lives.
TIMEOUT_RC = 124
SPAWN_FAILED_RC = 127

# Every call is bounded. There is no `timeout=None` path, and that is the whole
# point of the module: an unbounded subprocess in a gate is a CI job that hangs to the runner's own cap with nothing on either stream to say why. A caller that genuinely needs longer says so with a number, at the call site, where a reviewer sees it.
DEFAULT_TIMEOUT = 60.0

# The default retry shape, matching common.sh:187-210: exponential, base 2, no jitter, no cap. Named rather than inlined so the ONE place the repo's backoff policy is written down is greppable.
DEFAULT_ATTEMPTS = 3
DEFAULT_DELAY = 2.0
DEFAULT_FACTOR = 2.0


class Result:
    """What a command did. Immutable in practice, and never merged.

    Not a NamedTuple: `bool(result)` on a tuple is "is it non-empty", which is always True, and a caller writing `if run(...)` would get a check that cannot fail. `__bool__` is defined below to mean what a reader expects.
    """

    __slots__ = ("argv", "duration", "returncode", "stderr", "stdout", "timed_out")

    def __init__(
        self,
        argv: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        *,
        timed_out: bool = False,
        duration: float = 0.0,
    ) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.duration = duration

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "Result(argv=%r, returncode=%d, timed_out=%r, out=%d B, err=%d B)" % (
            self.argv,
            self.returncode,
            self.timed_out,
            len(self.stdout),
            len(self.stderr),
        )

    def describe(self) -> str:
        """One line naming the command and what happened, for an error message.

        Exists because the alternative every call site writes by hand is `"%s failed" % cmd`, which omits the code, and then the reader has to run the command again to learn anything.
        """
        if self.timed_out:
            return "%s timed out after %.1fs (exit %d)" % (
                " ".join(self.argv),
                self.duration,
                self.returncode,
            )
        # A SIGNALLED CHILD DID NOT "EXIT", and saying so sends the reader after the wrong cause. `subprocess` reports a signalled child as a NEGATIVE returncode and a shell in between reports 128+N; either way the process was terminated from outside rather than deciding to fail, so the thing to suspect is a deadline or an OOM kill, not the command's own logic. Learned the
        # expensive way on 2026-09-08 in `wl_judge`, whose equivalent line read "judge exited 143" and let a reader conclude the model was unreachable -- the remedy that message offers is to DISABLE the gate.
        sig = (
            -self.returncode
            if self.returncode < 0
            else (self.returncode - 128 if 128 < self.returncode < 160 else 0)
        )
        if sig:
            return "%s was KILLED by signal %d (exit %d), not a failure of its own" % (
                " ".join(self.argv),
                sig,
                self.returncode,
            )
        return "%s exited %d" % (" ".join(self.argv), self.returncode)


def _kill(proc: subprocess.Popen, group: bool) -> None:
    """SIGKILL the child, and its whole session when `group` is set.

    SIGKILL AND NOT SIGTERM, deliberately, and it is the difference that makes this module's deadline real: a TERM handler can ignore the signal, and both bash originals then wait for the process to finish on its own -- 3020 ms for a 1-second timeout, measured. A deadline a program can decline is a comment, not a deadline.

    The group kill is tried FIRST and its failure is not fatal: the session may already be gone (a race with normal exit), or `start_new_session` may not have been requested. Either way the direct child is killed after it.
    """
    if group:
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(OSError, ProcessLookupError):
        proc.kill()


def run(
    argv: list[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    input_text: str | None = None,
    kill_group: bool = True,
) -> Result:
    """Run `argv`, bounded. Never raises for a non-zero exit; never merges streams.

    ARGV IS A LIST, ALWAYS. There is no `shell=True` and no string form. Every
    bash call site this replaces is a word-splitting bug waiting for a path with a space in it, and passing a list is how that class stops existing rather than being quoted around.

    `env` REPLACES the environment when given rather than extending it, matching `subprocess` itself. Extending silently is how a differential passes on the machine that wrote it and fails on the machine that runs it.

    `input_text` is the only reason stdin is ever not /dev/null. Without it the child gets DEVNULL, for the hang reason in the module docstring.
    """
    started = time.monotonic()
    stdin = subprocess.PIPE if input_text is not None else subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            argv,
            cwd=None if cwd is None else str(cwd),
            env=env,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Its own session, so a timeout can signal the whole tree. This is defect 2 in the module docstring: common.sh:248 signals one pid and `bash -c 'sleep 300 & wait'` outlives its own wrapper.
            start_new_session=kill_group,
        )
    except (OSError, ValueError) as exc:
        # 127, matching wl_git.py:110 and wl_reggate.py:763. A command that is not installed is a genuine breakage and must not look like a finding.
        return Result(
            argv,
            SPAWN_FAILED_RC,
            "",
            str(exc),
            duration=time.monotonic() - started,
        )

    try:
        out, err = proc.communicate(input=input_text, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill(proc, kill_group)
        # A SECOND communicate() AFTER THE KILL, and it is not optional. The pipes still hold whatever the child wrote before it died, and without this call they are never drained -- the partial output is lost and the file descriptors leak. Partial output is usually the only evidence of WHY something hung.
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - a SIGKILLed pipe holder
            proc.kill()
            out, err = "", ""
        timed_out = True

    duration = time.monotonic() - started
    if timed_out:
        return Result(argv, TIMEOUT_RC, out or "", err or "", timed_out=True, duration=duration)
    return Result(argv, proc.returncode, out or "", err or "", duration=duration)


def run_with_timeout(argv: list[str], timeout: float, **kwargs) -> Result:
    """`run` with the timeout first, matching the shape of what it replaces.

    `timeout 30 docker info` and `run_with_timeout 30 docker info` both put the seconds before the command, and 12 `timeout(1)` sites plus 8 `common.sh` sites are spelled that way. Keeping the order makes a port a transcription rather than a re-reading, which is where argument-order mistakes come from.
    """
    return run(argv, timeout=timeout, **kwargs)


class RetryOutcome:
    """The whole history of a retry, not just its verdict.

    The bash original prints `Attempt 1/3 failed, retrying in 2s...` and then throws every one of those facts away, returning a bare 1. A caller that wants to say "gave up after 3 attempts over 6 seconds, last error was X" has to re-derive all of it. This carries it.
    """

    __slots__ = ("attempts", "delays", "last", "ok")

    def __init__(self, ok: bool, attempts: int, delays: list[float], last: object) -> None:
        self.ok = ok
        self.attempts = attempts
        self.delays = delays
        self.last = last

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "RetryOutcome(ok=%r, attempts=%d, delays=%r)" % (
            self.ok,
            self.attempts,
            self.delays,
        )


def backoff_delays(
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY,
    factor: float = DEFAULT_FACTOR,
) -> list[float]:
    """The delays a full run of `attempts` would sleep, in order.

    A PURE FUNCTION, SEPARATE FROM THE LOOP, because a schedule that can only be observed by waiting for it is a schedule nobody tests. The differential against `common.sh:187-210` compares this list against what the bash function actually printed, so the formula is checked rather than the docstring.

    There are `attempts - 1` delays, never `attempts`: bash sleeps only when another attempt is coming (`if [[ $attempt -lt $max_attempts ]]`, line 200). An off-by-one here would add a full final delay to every failing retry in the tree, which is exactly the kind of cost nobody notices for months.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1 (got %d)" % attempts)
    out = []
    current = float(delay)
    for _ in range(attempts - 1):
        out.append(current)
        current *= factor
    return out


def retry_with_backoff(
    action,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY,
    factor: float = DEFAULT_FACTOR,
    sleep=time.sleep,
    on_retry=None,
) -> RetryOutcome:
    """Call `action()` until it returns something truthy, backing off between tries.

    RETRIES ON ANY FALSY RESULT, which is the same policy as every one of the fifteen bash loops in this tree: `if "$@"; then return 0; fi` and nothing
    else. No implementation anywhere in the repo distinguishes a retryable
    failure from a fatal one, so this does not invent a distinction that the call sites would then have to be taught. A caller that wants one returns truthy early or raises.

    `sleep` IS INJECTABLE, and that is the difference between a tested backoff and an untested one. With the real `time.sleep`, asserting the `3 2` schedule
    from `cleanup-versions.sh` costs six seconds of wall clock per assertion; the
    tests pass a recorder instead and assert the schedule directly.

    AN EXCEPTION IS NOT A FAILED ATTEMPT. It propagates. The bash original cannot express the difference -- everything is an exit code -- but in Python a TypeError inside `action` means the caller is wrong, and retrying it three times with backoff turns a one-line traceback into a slow one.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1 (got %d)" % attempts)
    schedule = backoff_delays(attempts, delay, factor)
    slept: list[float] = []
    result = None
    for attempt in range(1, attempts + 1):
        result = action()
        if result:
            return RetryOutcome(True, attempt, slept, result)
        if attempt < attempts:
            pause = schedule[attempt - 1]
            if on_retry is not None:
                on_retry(attempt, attempts, pause, result)
            sleep(pause)
            slept.append(pause)
    return RetryOutcome(False, attempts, slept, result)


def retry_command(
    argv: list[str],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY,
    factor: float = DEFAULT_FACTOR,
    sleep=time.sleep,
    on_retry=None,
    **run_kwargs,
) -> Result:
    """`retry_with_backoff` over `run`, returning the LAST Result.

    THE LAST RESULT, NOT A BARE 1. `common.sh:208-209` ends every exhausted retry
    with `return 1`, so a caller cannot tell "the tool is not installed" (127)
    from "the tool ran and found something" (1) from "it timed out every time"
    (124). Three very different next actions, collapsed into one number. This keeps the code, both output streams, and the duration.
    """
    outcome = retry_with_backoff(
        lambda: run(argv, **run_kwargs),
        attempts=attempts,
        delay=delay,
        factor=factor,
        sleep=sleep,
        on_retry=on_retry,
    )
    return outcome.last


def which(name: str, env: dict[str, str] | None = None) -> str | None:
    """The absolute path of `name` on PATH, or None.

    Here rather than in a caller because the twelve `timeout(1)` sites exist precisely because nobody asked this question first. `shutil.which` with an explicit PATH, so a differential can pass a controlled environment.
    """
    import shutil  # noqa: PLC0415 -- a stdlib import used by one function

    environ = os.environ if env is None else env
    return shutil.which(name, path=environ.get("PATH"))


__all__ = [
    "DEFAULT_ATTEMPTS",
    "DEFAULT_DELAY",
    "DEFAULT_FACTOR",
    "DEFAULT_TIMEOUT",
    "SPAWN_FAILED_RC",
    "TIMEOUT_RC",
    "Result",
    "RetryOutcome",
    "backoff_delays",
    "retry_command",
    "retry_with_backoff",
    "run",
    "run_with_timeout",
    "which",
]

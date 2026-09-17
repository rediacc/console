#!/usr/bin/env python3
"""Port of `.ci/scripts/private/compose-healthcheck-smoke-test.sh`.

Deploys the `app-postgres` template on the worker VM through the production
`rdc` orchestration path and asserts that the `db` container's Docker
healthcheck (`pg_isready -h localhost`, which traverses the eBPF connect4
rewrite `127.0.0.1 -> SERVICE_IP4`) converges to `healthy` inside a bounded
window, then that the `app` container reached `running` on the strength of its
`depends_on: db.condition: service_healthy`.

THE BASH TWIN REMAINS THE LIVE CALL SITE. Nothing in `package.json`,
`scripts/ci-runner/manifest.ts` or any workflow points at this module, and this
module carries NO `---- gate ----` header, exactly as the twin carries none: the
twin is invoked by hand and by the private CT lane, not by the gate estate.
Cutover is a separate, later, driver-only step and is not done here.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHY EVEN THE CLOCK IS
-----------------------------------------------------------------------------
Four externals, each with the twin's argv verbatim: `rdc`, `ssh`, `date` and
`sleep`. Two of those could obviously have been done in-process and are not:

  * `date +%s` could have been `time.time()`. It is not, because the recorded
    call log is the only place the polling cadence is observable at all, and
    because a port whose clock is a syscall cannot be driven to a deterministic
    timeout by a differential. Shelling out makes the clock injectable through
    the same PATH every other external comes from.
  * `sleep 5` could have been `time.sleep(5)`. It is not, for the same reason
    plus one more: a differential that really slept would take minutes and would
    be quietly deleted the first time someone ran the suite in a hurry.

`whoami` is a FIFTH external, reached only when both `SSH_USER` and `USER` are
unset or empty.

-----------------------------------------------------------------------------
THE EXIT TRAP RUNS TWICE ON EVERY SUCCESSFUL RUN, AND THAT IS THE TWIN
-----------------------------------------------------------------------------
`cleanup` is installed with `trap cleanup EXIT` AND called once explicitly as a
pre-clean before `repo create`. So "Cleanup (best-effort)" appears twice on a
healthy run and the four `rdc repo down` / `rdc repo delete` calls appear in
pairs. Reproduced exactly, including the doubled log line.

The trap is installed AFTER the environment block, so a run that dies parsing
`VM_WORKERS` or `HOME` produces NO cleanup at all. That ordering is load-bearing
(there is nothing to clean up yet) and is reproduced: the `try` starts where the
`trap` does, not at the top of `main`.

Bash preserves the status that triggered an EXIT trap unless the handler exits
itself; this one does not, so a `rdc repo up` failing with 7 leaves the script
exiting 7 after cleanup. Driven with a fake `rdc` returning 7; pinned.

-----------------------------------------------------------------------------
THE POLL CAPTURE IS AN OUTPUT FORMAT, NOT JUST A READ
-----------------------------------------------------------------------------
`state=$(_ssh "..." 2>/dev/null || echo "ssh-error|")` has four consequences and
the third is the one a port gets wrong:

  1. ssh's STDERR IS DISCARDED. A connection diagnostic never reaches the
     transcript during polling, only during the diagnostic dump (which has no
     such redirection).
  2. A MISSING `ssh` IS INDISTINGUISHABLE FROM A FAILING ONE. Bash performs the
     redirection before the lookup fails, so `command not found` also lands in
     `/dev/null`, and the `||` arm supplies `ssh-error|` for both.
  3. THE FALLBACK IS APPENDED TO WHATEVER ssh ALREADY PRINTED, not substituted
     for it, because the substitution captures the whole AND-OR list. An ssh
     that prints `starting|1` and then exits 4 yields the two-line string
     `starting|1\nssh-error|`, whose `%%|*` split is `starting` and whose `#*|`
     split is `1\nssh-error|`. Pinned by its own differential case.
  4. `$()` strips ALL trailing newlines, so a reply of `healthy|0\n\n\n` and one
     of `healthy|0` are the same string.

`${state%%|*}` / `${state#*|}` are NOT symmetric: with no `|` in the reply at
all, `status` and `streak` are BOTH the whole string. `split_state` reproduces
that rather than tidying it.

-----------------------------------------------------------------------------
TIMEOUT_SECS IS EVALUATED AS BASH ARITHMETIC, WHICH IS A REAL DEFECT
-----------------------------------------------------------------------------
`deadline=$(($(date +%s) + TIMEOUT_SECS))` puts the variable inside `$(( ))`, so
its value is an ARITHMETIC EXPRESSION and not a decimal count of seconds. A
LEADING ZERO THEREFORE SELECTS OCTAL: `TIMEOUT_SECS=060` waits 48 seconds, not
60, while the log line one row above still prints `timeout 060s` because that
one is a plain string interpolation. Measured 2026-09-14 against a stepped clock
fake: 5 poll iterations at `120`, 2 at `060`.

Reported as a finding against the twin and REPRODUCED here rather than repaired,
because a port whose window differed from its twin's would not be a port.

`arith` covers the literal forms bash accepts for a value of this shape -- signed
decimal, `0`-prefixed octal, `0x` hex, surrounding whitespace -- plus the two
error shapes below. IT DELIBERATELY DOES NOT IMPLEMENT OPERATORS: `TIMEOUT_SECS`
is documented by the twin as "Max seconds to wait", and `TIMEOUT_SECS=1+1` is
outside the ported subset. That boundary is stated here rather than discovered.

Both error shapes are reproduced because they behave DIFFERENTLY, and the
difference is a bash quirk nobody would guess:

  * An UNSET IDENTIFIER (`TIMEOUT_SECS=abc`) is a `set -u` violation. It is
    fatal: one diagnostic, exit 1.
  * AN INVALID TOKEN (`TIMEOUT_SECS=12abc`) is an arithmetic expansion error,
    and in a SCRIPT FILE `set -e` DOES NOT FIRE ON IT. `deadline` is left unset,
    execution continues, and the very next line dies on `deadline: unbound
    variable`. Two diagnostics for one cause. Confirmed 2026-09-14 to be
    file-specific: the identical fragment under `bash -c` exits at the first.

-----------------------------------------------------------------------------
LOG GLYPHS ARE DOUBLED, AND THAT TOO IS THE TWIN
-----------------------------------------------------------------------------
`log_info` already prefixes a green check, so `log_info "<check> db reached
healthy"` prints TWO of them. Cosmetic, reported, reproduced.

Two authored strings carry U+2014. They are SPELLED AS ESCAPES, not as the
character: `check:ci-em-dash-surfaces` scans `.ci/rediacc_ci/**/*.py` against a
shrink-only baseline and a literal here would be a new finding in a gate that is
right to object. The escape emits the identical bytes, which is what the
differential compares.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
Eight variables, each read with `os.environ.get` AT ITS CALL SITE rather than
through any `env = dict(os.environ)` alias, so the env-registry AST scanner can
see every name:

    VM_NET_BASE   default 192.168.111
    VM_WORKERS    default "11"; whitespace-split, FIRST id used
    SSH_USER      default $USER, then `whoami`
    USER          consulted only for that default
    SSH_KEY       default $HOME/.ssh/id_ed25519
    HOME          consulted only for that default
    MACHINE_NAME  default worker-1
    TIMEOUT_SECS  default 120

`${VAR:-default}` means UNSET OR EMPTY both take the default. `HOME` is the
exception in shape: it is a BARE `$HOME` inside another default, so it is only
read when `SSH_KEY` is unset or empty, and it is a `set -u` violation when that
happens and `HOME` is not set. Both halves reproduced.

`read -ra WORKER_IDS <<<"..."` reads ONE LINE and splits it on spaces and tabs.
A value that is only whitespace therefore yields an EMPTY ARRAY, and
`${WORKER_IDS[0]}` under `set -u` is fatal before the trap is installed.
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
import sys

from rediacc_ci import log

# `VM_NET_BASE="${VM_NET_BASE:-192.168.111}"` and its five neighbours.
DEFAULT_VM_NET_BASE = "192.168.111"
DEFAULT_VM_WORKERS = "11"
DEFAULT_MACHINE_NAME = "worker-1"
DEFAULT_TIMEOUT_SECS = "120"

# `REPO_NAME="healthcheck-smoke"`. Not overridable, in either subject.
REPO_NAME = "healthcheck-smoke"

# `sleep 5` between polls. A string because it is an argv element, never a
# number: the differential compares the recorded argument, not an int.
POLL_INTERVAL = "5"

# The `ssh` options, in the twin's order. `StrictHostKeyChecking=no` is right
# for a throwaway lab VM and wrong everywhere else; it is the twin's choice.
SSH_OPTIONS = ("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15")

# ---------------------------------------------------------------------------
# THE FOUR REMOTE PROGRAMS, BYTE FOR BYTE.
#
# Each is ONE argument to ssh, newlines and indentation included, and each was
# extracted from a recorded run of the twin rather than retyped from the source:
# the twin writes them inside double quotes with `\"` and `\$` escapes, and
# transcribing those by eye is how a port ends up sending `$sock` where the twin
# sent a literal `$sock` that the REMOTE shell expands. The differential asserts
# every one of them character for character against the twin's recorded argv.
# ---------------------------------------------------------------------------

POLL_REMOTE = """sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S "$sock" ] || continue
        cid=$(docker -H unix://$sock ps -a --filter name=^db$ --format "{{.ID}}" 2>/dev/null | head -1)
        if [ -n "$cid" ]; then
          docker -H unix://$sock inspect --format "{{.State.Health.Status}}|{{.State.Health.FailingStreak}}" "$cid" 2>/dev/null && exit 0
        fi
      done
      echo "missing|"
    '"""

DIAG_REMOTE = """sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S "$sock" ] || continue
        cid=$(docker -H unix://$sock ps -a --filter name=^db$ --format "{{.ID}}" 2>/dev/null | head -1)
        if [ -n "$cid" ]; then
          echo "=== $sock ==="
          docker -H unix://$sock inspect --format "State={{.State.Status}} Health={{.State.Health.Status}}/{{.State.Health.FailingStreak}}" "$cid"
          echo "--- last 5 health log entries ---"
          docker -H unix://$sock inspect --format "{{json .State.Health.Log}}" "$cid" 2>&1 | head -100
          echo "--- last 30 container log lines ---"
          docker -H unix://$sock logs --tail 30 "$cid" 2>&1
        fi
      done
    '"""

SS_REMOTE = "sudo ss -tlnp 'sport = :5432' 2>&1"

APP_REMOTE = """sudo bash -c '
  for sock in /var/run/rediacc/docker-*.sock; do
    [ -S "$sock" ] || continue
    cid=$(docker -H unix://$sock ps -a --filter name=^app$ --format "{{.ID}}" 2>/dev/null | head -1)
    if [ -n "$cid" ]; then
      docker -H unix://$sock inspect --format "{{.State.Status}}" "$cid" 2>/dev/null && exit 0
    fi
  done
  echo "missing"
'"""

# The fallbacks the `||` arms of the two command substitutions supply. They
# differ by one character (`|`) and the difference matters: the poll reply is
# split on `|` and the app reply is compared whole.
POLL_FALLBACK = "ssh-error|"
APP_FALLBACK = "ssh-error"

# U+2713 and U+2014 AS ESCAPES, NOT AS CHARACTERS. See the docstring: a literal
# em dash here would be a new finding in `check:ci-em-dash-surfaces`, which
# scans this directory against a shrink-only baseline and is right to object.
# The check glyph is spelled the same way only so the two look alike in source.
# Both emit the identical bytes, which is what the differential compares.
_CHECK = "\u2713"
_EMDASH = "\u2014"

# `read -ra` splits on IFS, whose default is space, tab and newline; the newline
# is what TERMINATED the line, so only the first two can appear inside it.
_IFS_WHITESPACE = " \t"

# The literal forms bash's arithmetic accepts for a value of this shape. Order
# matters: octal must be tried before decimal or `060` reads as sixty.
_HEX = re.compile(r"0[xX][0-9a-fA-F]+\Z")
_OCTAL = re.compile(r"0[0-7]*\Z")
_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class BashUnboundVariableError(Exception):
    """`set -u` fired. Bash prints `<name>: unbound variable` and EXITS."""


class BashArithmeticError(Exception):
    """An arithmetic expansion error. Bash prints
    `<token>: value too great for base (error token is "<token>")` and, in a
    SCRIPT FILE, DOES NOT EXIT. The caller decides what happens next, because
    what happens next is the interesting half."""


class _BashExitError(Exception):
    """`set -e` or an explicit `exit`. Carries the status to leave with."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def worker_ids(value: str) -> list[str]:
    """`read -ra WORKER_IDS <<<"$value"`, as a list.

    ONE LINE ONLY: a here-string is fed to `read`, which stops at the first
    newline, so `$'11\\n12'` yields `["11"]` and not two ids. Leading and
    trailing IFS whitespace is discarded, runs of it collapse, and an
    all-whitespace value yields an EMPTY LIST -- which is not a quiet default
    but the `set -u` failure the twin dies on.

    Exported so the differential can exercise the splitting directly.
    """
    line = value.split("\n", 1)[0].strip(_IFS_WHITESPACE)
    if not line:
        return []
    return re.split(r"[ \t]+", line)


def arith(text: str) -> int:
    """One bash arithmetic OPERAND, evaluated as bash would evaluate it.

    Empty is 0, which is what `$(( ))` and `[[ "" -lt 1 ]]` both do, and is the
    value a command substitution of a missing `date` collapses to.

    Raises `BashUnboundVariableError` for a bare name that is not in the environment
    and `BashArithmeticError` for anything else that is not a literal. See the
    module docstring for why the two are not interchangeable and for the
    operators this deliberately does not implement.
    """
    token = text.strip()
    if not token:
        return 0

    sign = 1
    body = token
    while body[:1] in ("+", "-"):
        if body[0] == "-":
            sign = -sign
        body = body[1:].lstrip()
    if not body:
        raise BashArithmeticError(token)

    if _HEX.match(body):
        return sign * int(body, 0)
    if _OCTAL.match(body):
        # THE DEFECT THIS LINE REPRODUCES. `060` is 48, not 60. `08` reaches
        # neither this branch nor the decimal one and is bash's "value too great
        # for base", which is exactly right: `8` is not an octal digit.
        return sign * int(body, 8)
    if _DECIMAL.match(body):
        return sign * int(body, 10)
    if _IDENTIFIER.match(body):
        # Bash resolves the name as a shell variable. An exported one is a shell
        # variable; an unset one is a `set -u` violation.
        resolved = os.environ.get(body)
        if resolved is None:
            raise BashUnboundVariableError(body)
        return sign * arith(resolved)
    raise BashArithmeticError(token)


def split_state(state: str) -> tuple[str, str]:
    """`status="${state%%|*}"` and `streak="${state#*|}"`, together.

    ASYMMETRIC ON PURPOSE. With no `|` present, `%%|*` leaves the string
    untouched and `#*|` also leaves it untouched, so BOTH come back as the whole
    reply. A port that returned `("healthy", "")` there would be tidier and
    would not be the same script.

    Only the FIRST `|` splits, on both sides: a reply of `a|b|c` is `a` and
    `b|c`, never `a` and `c`.
    """
    head, sep, tail = state.partition("|")
    return head, tail if sep else state


def ssh_argv(key: str, user: str, host: str, command: str) -> list[str]:
    """The `_ssh` wrapper's full argv. Exported so the differential can assert
    the option order without reaching into this module's private state."""
    return ["ssh", "-i", key, *SSH_OPTIONS, "%s@%s" % (user, host), command]


def _diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, read from the live frame rather than
    hard-coded, so it cannot go stale when this file is reflowed. The
    differential masks the whole prefix on both sides, because the two can never
    be equal, and pins that the mask hides only the prefix.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def _warn_to_stderr(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _reconfigure_streams() -> None:
    """Let bytes that are not UTF-8 travel through this process unharmed.

    A container name, a docker error or an ssh banner is whatever the remote
    host sent. Bash moves those bytes without decoding them; a port that decoded
    strictly would raise where the twin merely printed, so both streams are put
    into `surrogateescape` and every capture is decoded the same way.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="surrogateescape")


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def _strict(argv: list[str], *, stdout=None) -> None:
    """One command under `set -e`: return on 0, raise `_BashExitError` otherwise.

    A missing binary becomes bash's own `command not found` on STDERR and status
    127, because the only redirection at these call sites is on stdout.
    """
    try:
        completed = subprocess.run(argv, stdout=stdout, check=False)
    except FileNotFoundError:
        _warn_to_stderr(_diagnostic("%s: command not found" % argv[0]))
        raise _BashExitError(127) from None
    if completed.returncode != 0:
        raise _BashExitError(completed.returncode)


def _quiet(argv: list[str]) -> int:
    """`<cmd> 2>/dev/null || true`: status returned, stderr and ENOENT swallowed.

    THE ENOENT IS THE SUBTLE PART. Bash applies the redirection BEFORE the
    lookup fails, so its own `command not found` goes to `/dev/null` too and the
    caller sees a silent 127. Verified directly against bash, not assumed.
    """
    try:
        with open(os.devnull, "wb") as devnull:
            return subprocess.run(argv, stderr=devnull, check=False).returncode
    except FileNotFoundError:
        return 127


def _loud(argv: list[str]) -> None:
    """`<cmd> || true` with NO redirection: both streams inherited, status and a
    missing binary both swallowed, but the `command not found` IS printed."""
    try:
        subprocess.run(argv, check=False)
    except FileNotFoundError:
        _warn_to_stderr(_diagnostic("%s: command not found" % argv[0]))


def _capture_or(argv: list[str], fallback: str) -> str:
    """`$(<cmd> 2>/dev/null || echo "<fallback>")`.

    The fallback is APPENDED to whatever the command already printed, not
    substituted for it, because the substitution captures the AND-OR list as a
    whole. Trailing newlines are then stripped from the result, once, exactly as
    `$()` strips them.
    """
    try:
        with open(os.devnull, "wb") as devnull:
            completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=devnull, check=False)
        captured = _decode(completed.stdout or b"")
        status = completed.returncode
    except FileNotFoundError:
        captured = ""
        status = 127
    if status != 0:
        captured += fallback + "\n"
    return captured.rstrip("\n")


def _clock() -> tuple[str, int]:
    """`$(date +%s)`: stdout captured and newline-stripped, STDERR INHERITED.

    Returns the text and the status, because the two call sites disagree about
    the status: inside the `deadline=` assignment a failing `date` is fatal
    under `set -e`, while inside the `while [[ ... ]]` condition it is not.
    A missing `date` prints bash's diagnostic and reports 127 in both.
    """
    try:
        completed = subprocess.run(["date", "+%s"], stdout=subprocess.PIPE, check=False)
    except FileNotFoundError:
        _warn_to_stderr(_diagnostic("date: command not found"))
        return "", 127
    return _decode(completed.stdout or b"").rstrip("\n"), completed.returncode


def _cleanup(machine: str) -> None:
    """The EXIT trap, and also a hand-called pre-clean. Both, on every run.

    Nothing here can fail the script: each `rdc` call has its stderr discarded
    and its status swallowed, which is what "best-effort" means and also why a
    completely absent `rdc` leaves no trace in the transcript at this point.
    """
    log.step("Cleanup (best-effort)")
    target = "%s@%s" % (REPO_NAME, machine)
    _quiet(["rdc", "repo", "down", target])
    _quiet(["rdc", "repo", "delete", target, "--yes"])


def _resolve_ssh_user() -> str:
    """`SSH_USER="${SSH_USER:-${USER:-$(whoami)}}"`, one env read per name.

    The `whoami` arm is a command substitution inside an ASSIGNMENT, so its
    failure is fatal under `set -e` and its status is the script's.
    """
    explicit = os.environ.get("SSH_USER", "")
    if explicit:
        return explicit
    from_env = os.environ.get("USER", "")
    if from_env:
        return from_env
    try:
        completed = subprocess.run(["whoami"], stdout=subprocess.PIPE, check=False)
    except FileNotFoundError:
        _warn_to_stderr(_diagnostic("whoami: command not found"))
        raise _BashExitError(127) from None
    if completed.returncode != 0:
        raise _BashExitError(completed.returncode)
    return _decode(completed.stdout or b"").rstrip("\n")


def _resolve_ssh_key() -> str:
    """`SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"`.

    `$HOME` is BARE, not `${HOME:-}`, and it sits inside the default word: it is
    read only when `SSH_KEY` is unset or empty, and it is a `set -u` violation
    when that happens and `HOME` is not set.
    """
    explicit = os.environ.get("SSH_KEY", "")
    if explicit:
        return explicit
    home = os.environ.get("HOME")
    if home is None:
        _warn_to_stderr(_diagnostic("HOME: unbound variable"))
        raise _BashExitError(1)
    return "%s/.ssh/id_ed25519" % home


def _poll(key: str, user: str, vm_ip: str, timeout_text: str) -> tuple[str, str]:
    """Phase 2. Returns the last `(status, streak)` seen, healthy or not.

    The loop's shape is the twin's, including the two things a tidier port would
    change: the deadline is tested BEFORE the first probe (so `TIMEOUT_SECS=0`
    never probes at all and reports `unknown`), and the `sleep` happens AFTER
    the last probe even when the next deadline test is certain to end the loop.
    """
    log.step("Polling db healthcheck (timeout %ss)" % timeout_text)

    now_text, status_code = _clock()
    if status_code != 0:
        # A failing or missing `date` inside the ASSIGNMENT is fatal: the
        # assignment takes the substitution's status and `set -e` fires.
        raise _BashExitError(status_code)
    try:
        deadline: int | None = arith(now_text) + arith(timeout_text)
    except BashUnboundVariableError as exc:
        _warn_to_stderr(_diagnostic("%s: unbound variable" % exc.args[0]))
        raise _BashExitError(1) from None
    except BashArithmeticError as exc:
        # NOT FATAL IN A SCRIPT FILE. The diagnostic is printed, `deadline` is
        # left UNSET, and the next line is the one that kills the run.
        _warn_to_stderr(
            _diagnostic(
                '%s: value too great for base (error token is "%s")' % (exc.args[0], exc.args[0])
            )
        )
        deadline = None

    status = "unknown"
    streak = ""
    while True:
        # `while [[ $(date +%s) -lt $deadline ]]`. THE ORDER OF THESE THREE
        # STEPS IS BASH'S, not a convenience. Word expansion runs left to right
        # and completes BEFORE `[[` evaluates any arithmetic, so the clock runs
        # first, then an unset `$deadline` is a fatal `set -u` violation, and
        # only then is either side read as a number.
        now_text, _ = _clock()
        if deadline is None:
            _warn_to_stderr(_diagnostic("deadline: unbound variable"))
            raise _BashExitError(1)
        try:
            left = arith(now_text)
        except BashUnboundVariableError as exc:
            _warn_to_stderr(_diagnostic("%s: unbound variable" % exc.args[0]))
            raise _BashExitError(1) from None
        except BashArithmeticError as exc:
            # Inside `[[ ]]` bash prefixes its own name to the diagnostic and
            # the test returns FALSE, which ends the loop WITHOUT `set -e`
            # firing: a `while` condition is exempt. The run then takes the
            # timeout path with whatever status it last saw.
            _warn_to_stderr(
                _diagnostic(
                    '[[: %s: value too great for base (error token is "%s")'
                    % (exc.args[0], exc.args[0])
                )
            )
            break
        if left >= deadline:
            break

        state = _capture_or(ssh_argv(key, user, vm_ip, POLL_REMOTE), POLL_FALLBACK)
        status, streak = split_state(state)
        if status == "healthy":
            log.info("%s db reached healthy (streak=%s)" % (_CHECK, streak))
            break
        log.step("  status=%s streak=%s %s waiting..." % (status, streak, _EMDASH))
        _strict(["sleep", POLL_INTERVAL])

    return status, streak


def _dump_diagnostics(key: str, user: str, vm_ip: str) -> None:
    """The failure dump. Neither call redirects stderr and neither can fail the
    run; the container listing lands on STDOUT, where a caller collecting the
    transcript will find it next to whatever ssh wrote to stderr."""
    log.step("[diag] db container state + recent logs")
    _loud(ssh_argv(key, user, vm_ip, DIAG_REMOTE))
    log.step("[diag] postgres listening sockets on host")
    _loud(ssh_argv(key, user, vm_ip, SS_REMOTE))


def _body(argv: list[str]) -> int:
    """Everything from `trap cleanup EXIT` onward. The caller owns the trap."""
    del argv

    vm_net_base = os.environ.get("VM_NET_BASE", "") or DEFAULT_VM_NET_BASE
    ids = worker_ids(os.environ.get("VM_WORKERS", "") or DEFAULT_VM_WORKERS)
    if not ids:
        # `${WORKER_IDS[0]}` on an empty array under `set -u`. This fires BEFORE
        # the trap is installed, so no cleanup runs; see the module docstring.
        _warn_to_stderr(_diagnostic("WORKER_IDS[0]: unbound variable"))
        return 1
    vm_ip = "%s.%s" % (vm_net_base, ids[0])
    ssh_user = _resolve_ssh_user()
    ssh_key = _resolve_ssh_key()
    machine = os.environ.get("MACHINE_NAME", "") or DEFAULT_MACHINE_NAME
    timeout_text = os.environ.get("TIMEOUT_SECS", "") or DEFAULT_TIMEOUT_SECS
    target = "%s@%s" % (REPO_NAME, machine)

    try:
        # -- Phase 0: register the worker VM with the rdc CLI (idempotent) ----
        log.step("Registering worker %s as machine '%s'" % (vm_ip, machine))
        with open(os.devnull, "wb") as devnull:
            _strict(["rdc", "config", "ssh", "set", "--key", ssh_key], stdout=devnull)
        if _quiet(["rdc", "machine", "add", machine, "--ip", vm_ip, "--user", ssh_user]) != 0:
            # EVERY failure warns, including "rdc is not installed" and "that IP
            # is malformed". The twin's own wording says "already registered",
            # which is a guess it does not verify; `rdc machine setup` on the
            # next line is what actually catches the other cases.
            log.warn("Machine '%s' already registered (continuing)" % machine)
        log.step("Provisioning renet on worker")
        _strict(["rdc", "machine", "setup", machine])

        # Pre-clean any debris from prior runs so create does not conflict.
        _cleanup(machine)

        # -- Phase 1: bring up app-postgres ----------------------------------
        log.step("Creating repo + applying app-postgres template")
        _strict(["rdc", "repo", "create", REPO_NAME, "-m", machine, "--size", "2G"])
        _strict(["rdc", "repo", "admin", "template", "apply", target, "--template", "app-postgres"])

        log.step("Bringing repo up (db must converge to healthy via pg_isready)")
        _strict(["rdc", "repo", "up", target])

        # -- Phase 2: poll the db healthcheck --------------------------------
        status, streak = _poll(ssh_key, ssh_user, vm_ip, timeout_text)

        if status != "healthy":
            log.error(
                "db did not reach healthy within %ss (last status=%s streak=%s)"
                % (timeout_text, status, streak)
            )
            log.error("Diagnostic dump follows")
            _dump_diagnostics(ssh_key, ssh_user, vm_ip)
            return 1

        # -- Phase 3: the depends_on chain must have started `app` -----------
        log.step("Confirming app container is running (depends_on db.healthy)")
        app_state = _capture_or(ssh_argv(ssh_key, ssh_user, vm_ip, APP_REMOTE), APP_FALLBACK)
        if app_state != "running":
            log.error("app container state=%s (want 'running')" % app_state)
            return 1
        log.info("%s app container running" % _CHECK)
        log.info(
            "PASS: app-postgres compose converged %s eBPF rewrites + healthchecks intact" % _EMDASH
        )
        return 0
    except _BashExitError as exc:
        return exc.code
    finally:
        # `trap cleanup EXIT`. It runs on the healthy path, on every `set -e`
        # death after this point, and on both explicit `exit 1`s -- and it does
        # NOT change the status, which is why it is a `finally` and not a
        # `return`.
        _cleanup(machine)


def main(argv: list[str]) -> int:
    """The twin ignores its arguments entirely; so does this, and `argv` is
    accepted only so the signature matches every other module in the package."""
    _reconfigure_streams()
    try:
        return _body(argv)
    except _BashExitError as exc:
        # The environment block, which runs BEFORE the trap is installed. A
        # death here produces no cleanup, exactly as in the twin.
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

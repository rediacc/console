#!/usr/bin/env python3
"""Port of `.ci/scripts/private/concurrent-fork-isolation-test.sh`.

Reproduces the renet#60 race (and its renet#59 prerequisite) on a worker VM
provisioned by `renet ops up`, then rules on four things: that `rdc repo up` of
a fork of a RUNNING parent exits 0, that the two postgres listeners are distinct
`127.0.x.x:5432` and never `0.0.0.0:5432`, that no per-network docker daemon
owns more than one compose project, and that `repo fork --checkpoint` restores
process state in the fork while the parent keeps running (console#440).

THE BASH TWIN REMAINS THE ONLY CALL SITE, AND IT IS NOT A REGISTERED GATE.
Nothing in `package.json`, `scripts/ci-runner/manifest.ts` or any workflow
invokes either subject; the twin is a hand-run private reproduction script
(`private/renet/docs/CRIU_STATUS.md:137` is the only reference to it). NEITHER
FILE CARRIES A `---- gate ----` HEADER, and this one must not grow one: that
header is what `scripts/gate-bind.ts` reads, and a second owner for an id would
break the parity meta-gates. Cutover is a separate, later, driver-only step.

-----------------------------------------------------------------------------
WHY THIS IS PORTABLE AT ALL, GIVEN IT NEEDS A VM
-----------------------------------------------------------------------------
Everything this script knows about the world arrives as the STDOUT of a child
process: `ssh` (eight distinct remote command strings), `rdc` (23 invocations on
a passing run, twelve of them the two cleanups), and the small pipeline tools it
composes them with. There is no socket it opens itself, no file under `/proc` it
reads, and no library it links. The VM decides what the fakes would have said;
it does not decide what the script does with the answer. So the differential
drives BOTH subjects through the same
recording fakes on a scratch PATH, and what it pins is the whole of the script's
own contribution: argument parsing, the argv of every child, the order they run
in, the four verdicts, the message bytes and the exit code.

WHAT THAT DELIBERATELY DOES NOT PROVE: that a real `ss -Hltnp4` prints what the
fixture prints, or that CRIU restores anything. Neither subject can prove that
either; only a live run can, and a live run is what the twin is for.

-----------------------------------------------------------------------------
EVERY EXTERNAL IS SHELLED OUT TO, INCLUDING THE ONES PYTHON COULD DO ITSELF
-----------------------------------------------------------------------------
`cat` writes the two sidecar files, `sort -u` deduplicates the bind list,
`head -1` takes a first line, `mktemp`/`rm` manage two temp paths, `sleep` waits,
`grep`/`tail`/`tee` inspect one log. Every one of those has a one-line Python
equivalent, and none of them is used, because THE RECORDED CALL LOG IS THE
COMPARISON. A port that wrote the compose file with `pathlib.write_text` would
produce byte-identical output on both streams and a different process tree, and
the differential exists precisely to notice that.

THE ONE EXTERNAL THE PORT DOES NOT MAKE: `uname`. The twin sources
`.ci/scripts/lib/common.sh`, whose line 509 runs `CI_OS="$(detect_os)"` at
source time; that is the LIBRARY probing its host, not this script doing
anything, it writes nothing to either stream, and no branch here reads the
result. `rediacc_ci.log` replaces the whole of common.sh's logging without it.
The differential therefore keeps a REAL `uname` on the scratch PATH rather than
a recording fake, so the twin's two probes leave no trace to diverge on. Named
here because an unrecorded external is exactly the kind of thing that should be
stated rather than discovered.

-----------------------------------------------------------------------------
THREE PROPERTIES OF THE TWIN THAT A NAIVE PORT LOSES, ALL PINNED
-----------------------------------------------------------------------------
1. `trap cleanup EXIT` RUNS ON EVERY PATH, including the `set -e` aborts and
   including success, and it does NOT change the exit status unless it fails
   itself. `main` reproduces both halves: the body's status is carried through
   the cleanup, and a cleanup that dies under `set -e` replaces it.

2. `set -e` IS IGNORED FOR A NON-FINAL MEMBER OF AN AND-OR LIST. `[[ -n
   "$COUNTER_DIR" ]] && rm -rf "$COUNTER_DIR"` therefore does NOT abort the
   cleanup when the variable is empty, which is the normal case on a successful
   run, and `rm` failing DOES abort it, because `rm` is the last member. Same
   rule keeps the `[[ ... ]] && break` in the counter-wait loop and the
   `[[ ... ]] && fork_sock=...` in the fork-socket loop from ending the run.

3. `$(...)` STRIPS ALL TRAILING NEWLINES, and `|| true` INSIDE a substitution
   swallows the child's status while keeping whatever it had already printed.
   `_capture` and `_capture_lenient` are those two, separately, because the
   difference decides whether a broken `ssh` aborts the run (phase 4, no
   `|| true`) or produces an empty bind list (phase 3, with one).

-----------------------------------------------------------------------------
BASH ARITHMETIC IS AN OUTPUT FORMAT HERE, NOT AN IMPLEMENTATION DETAIL
-----------------------------------------------------------------------------
Five comparisons (`-gt`, `-ge`, `-lt`, `-le`) take a string that came off a
remote `docker logs | grep -o | cut`, so what bash DOES with a non-numeric one
is observable. Driven against bash 5 on 2026-09-14, and `_arith` reproduces each:

    ""      -> 0            "  7  " -> 7        "010"  -> 8 (octal)
    "0x1f"  -> 31           "+5"    -> 5        "-3"   -> -3
    "abc"   -> NOUNSET: `abc: unbound variable` on stderr and the whole
               script exits 1, even inside an `if` condition
    "1 2"   -> `[[: 1 2: arithmetic syntax error in expression (error token
               is "2")` on stderr, and the test evaluates FALSE (status 1)
    "08"    -> `[[: 08: value too great for base (error token is "08")`,
               likewise FALSE

`_arith` does NOT implement operators, `base#digits`, or arrays. Nothing in this
script can produce one: every operand is either a literal from the source or a
single field of remote output. A shape it cannot classify is reported as the
same syntax error bash reports for `1 2`, and the differential drives only the
eight shapes above, which is the honest boundary rather than a silent one.

-----------------------------------------------------------------------------
TWO DEFECTS IN THE TWIN, REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
* THE DOUBLE TICK. Four `log_info` calls open their message with a literal
  U+2713, and `log_info` already prefixes one, so the twin prints
  `(tick) (tick) 2 distinct loopback binds ...`. It is cosmetic and it is
  reproduced exactly; a port that tidied it would not be a port.

* THE WAIT LOOP SLEEPS ONE TIME TOO MANY ON THE FAILURE PATH. `sleep 2` comes
  AFTER the `&& break`, so a run whose counter never reaches 15 does thirty
  readings and thirty sleeps: the thirtieth sleep happens after the last
  reading the loop will ever take, and nothing observes anything during it. The
  success path is unaffected, because the `break` fires first. Reproduced and
  pinned at exactly thirty; the repair is a cutover-box decision.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
Six variables, each read with `os.environ.get` AT ITS CALL SITE and never
through an `env = dict(os.environ)` alias, so the env-registry AST scanner sees
every name:

    VM_NET_BASE   default 192.168.111
    VM_WORKERS    default "11"; SPLIT ON IFS, FIRST FIELD ONLY
    SSH_USER      default $USER, and `whoami` only if that is unset or empty
    SSH_KEY       default $HOME/.ssh/id_ed25519
    MACHINE_NAME  default worker-1
    HOME          consulted only to build the SSH_KEY default, and UNSET IS
                  FATAL there because `set -u` makes `$HOME` unbound

`${VAR:-default}` means UNSET OR EMPTY both take the default. `VM_WORKERS="  "`
is NOT empty, so it takes no default: `read -ra` yields an empty array and
`${WORKER_IDS[0]}` is an unbound-variable abort BEFORE the EXIT trap is
installed, so that one path runs no cleanup at all.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import re
import subprocess
import sys

from rediacc_ci import log

# The repo and tag names, verbatim. `FORK_REPO`/`CP_FORK_REPO` are the composed
# `name:tag` refs the CLI takes as a positional.
PARENT_REPO = "bindrace-parent"
FORK_TAG = "child"
FORK_REPO = "%s:%s" % (PARENT_REPO, FORK_TAG)
CP_FORK_TAG = "cpchild"
CP_FORK_REPO = "%s:%s" % (PARENT_REPO, CP_FORK_TAG)

# `${VM_NET_BASE:-192.168.111}` and its neighbours.
DEFAULT_NET_BASE = "192.168.111"
DEFAULT_WORKERS = "11"
DEFAULT_MACHINE = "worker-1"

# EM DASHES ARE SPELLED AS ESCAPES, NOT AS THE CHARACTER. The twin's messages
# carry literal U+2014; `check:ci-em-dash-surfaces` scans
# `.ci/rediacc_ci/**/*.py` against a shrink-only baseline and would be right to
# call a literal one here a new finding. The escape emits the identical byte
# sequence, which is what the differential compares.
DASH = "\u2014"
TICK = "\u2713"

# `[[ "$b" =~ ^127\.0\.[0-9]+\.[0-9]+:5432$ ]]`. Bash's `=~` is an ERE and `$`
# there is end-of-STRING, not end-of-line, which `fullmatch` is.
LOOPBACK_BIND = re.compile(r"127\.0\.[0-9]+\.[0-9]+:5432")

# The two wildcard spellings the bind-rewrite contract forbids (services.md:101).
WILDCARD_BINDS = ("0.0.0.0:5432", "*:5432")

# The counter must reach this before the checkpoint fork is taken, so that a
# freshly started container cannot be mistaken for a restored one.
COUNTER_TARGET = 15
COUNTER_ATTEMPTS = 30

# The two sidecar files, byte for byte as the quoted heredocs write them. BOTH
# HEREDOCS ARE QUOTED (`<<'COMPOSE'`, `<<'REDIACCFILE'`), so `$$` and `$i` reach
# the file UNEXPANDED and must not be interpolated here either.
COMPOSE_YML = """services:
  counter:
    image: alpine:3.20
    network_mode: host
    labels:
      - "rediacc.checkpoint=true"
    command: sh -c 'i=0; while true; do i=$$((i+1)); echo "count=$$i"; sleep 1; done'
"""

REDIACCFILE = """up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
"""

# ---------------------------------------------------------------------------
# The eight remote command strings, exactly as bash's double-quote processing
# hands them to `ssh` as ONE argument. Recovered on 2026-09-14 by running the
# twin under a recording `ssh` and printing the repr of argv[-1], not by
# re-typing them: `\\$` and `\\"` inside the twin's outer quotes collapse, and a
# hand transcription that got one wrong would send a subtly different script to
# a real VM.
# ---------------------------------------------------------------------------

# Phase 3. `awk` runs REMOTELY, inside this string; it is not a local external.
BINDS_CMD = "ss -Hltnp4 'sport = :5432' 2>/dev/null | awk '{print $4}'"

# Phase 4. NOTE THE LEADING AND TRAILING NEWLINES: the twin opens the argument
# on the line after `_ssh "` and closes it on its own line.
PROJECTS_CMD = """
sudo bash -c '
set -e
for sock in /var/run/rediacc/docker-*.sock; do
    [ -S "$sock" ] || continue
    projects=$(docker -H unix://$sock ps -a --format "{{index .Labels \\"com.docker.compose.project\\"}}" 2>/dev/null | sort -u | grep -v "^$" || true)
    project_count=$(echo "$projects" | grep -c . || true)
    if [ "$project_count" -gt 1 ]; then
        echo "$sock owns $project_count projects: $projects" >&2
        echo "$project_count"
        exit 0
    fi
done
echo 0
'
"""

# Phase 5. Every per-network socket that runs a counter container.
COUNTER_SOCKETS_CMD = """sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S "$sock" ] || continue
        if docker -H unix://$sock ps --filter name=counter --format "{{.Names}}" 2>/dev/null | grep -q counter; then
          echo "$sock"
        fi
      done
    '"""

# The five phase-2 diagnostics, in the order the twin dumps them.
DIAG_CGROUP_TREE = "sudo find /sys/fs/cgroup/rediacc.slice -maxdepth 4 -type d | head -50"
DIAG_BINDS = "sudo ss -tlnp4 'sport = :5432' 2>&1"
DIAG_BPF_MAP = "sudo bpftool map dump pinned /sys/fs/bpf/rediacc/cgroup_configs 2>&1 | head -60"
DIAG_BPF_TREE = "sudo bpftool cgroup tree /sys/fs/cgroup/rediacc.slice 2>&1 | head -30"
DIAG_DB_LOGS = """sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        echo "=== $sock ==="
        docker -H unix://$sock ps -a --format "{{.ID}} {{.Names}} {{.Status}}" 2>/dev/null || true
        cid=$(docker -H unix://$sock ps -a --filter name=db --format "{{.ID}}" 2>/dev/null | head -1)
        if [ -n "$cid" ]; then
          echo "--- inspect cgroup ---"
          docker -H unix://$sock inspect --format "{{.HostConfig.CgroupParent}}" "$cid" 2>&1 || true
          echo "--- logs ---"
          docker -H unix://$sock logs --tail 50 "$cid" 2>&1 || true
        fi
      done
    '"""


def counter_value_cmd(sock: str) -> str:
    """`counter_value <socket>`, with `$1` expanded by the LOCAL shell.

    The socket path is interpolated into the single-quoted remote script by the
    caller's own shell, so an odd socket name would break the remote quoting on
    both sides identically. Exported so the differential can build the expected
    argv without reading this module's private state.
    """
    return (
        "sudo bash -c '\n"
        '      name=$(docker -H unix://%s ps --filter name=counter --format "{{.Names}}"'
        " 2>/dev/null | head -1)\n"
        '      [ -n "$name" ] || exit 0\n'
        "      # silent-failure-ok: this line is INSIDE the quoted remote command string;"
        " the remote shell runs without pipefail\n"
        '      docker -H unix://%s logs --tail 5 "$name" 2>/dev/null | grep -o "count=[0-9]*"'
        " | tail -1 | cut -d= -f2\n"
        "    '" % (sock, sock)
    )


def counter_diag_cmd(sock: str) -> str:
    """The `[diag] raw counter container state + logs` remote script."""
    return (
        "sudo bash -c '\n"
        '      name=$(docker -H unix://%s ps -a --filter name=counter --format "{{.Names}}"'
        " | head -1)\n"
        "      docker -H unix://%s ps -a --filter name=counter\n"
        '      [ -n "$name" ] && docker -H unix://%s logs --tail 5 "$name" 2>&1\n'
        "    '" % (sock, sock, sock)
    )


class _ExitScriptError(Exception):
    """`set -e` fired, or the script reached an explicit `exit`.

    Carries the status bash would carry. Raised rather than returned so a helper
    six frames down can abort the run the way a failed command does, and so the
    EXIT trap can be a `finally` rather than a call at every exit point.
    """

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class _ArithError(Exception):
    """Bash's arithmetic evaluator refused the operand.

    `fatal` separates the two outcomes, which are NOT the same: a nounset error
    kills the shell (status 1) even inside an `if` condition, while a syntax
    error prints and lets `[[ ]]` return false.
    """

    def __init__(self, message: str, *, fatal: bool) -> None:
        super().__init__(message)
        self.message = message
        self.fatal = fatal


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, read off the live frame rather than
    hard-coded, so it cannot go stale when this file is reflowed. The
    differential masks the whole prefix on both sides, because the two can never
    name the same file.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def _diagnose(message: str) -> None:
    """One bash diagnostic on stderr, flushed."""
    print(_shell_diagnostic(message), file=sys.stderr, flush=True)


def _status(code: int) -> int:
    """A child's status as BASH reports it: a signal becomes 128 + signum.

    `subprocess` returns -N for a child killed by signal N, and `pipefail`
    compares statuses, so the two spellings must be reconciled before any
    comparison or the SIGPIPE a `| head -1` produces would read as success.
    """
    return 128 - code if code < 0 else code


# ---------------------------------------------------------------------------
# Bash arithmetic, to the extent this script can reach it. See the module
# docstring for the eight driven shapes and the stated boundary.
# ---------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DECIMAL = re.compile(r"[1-9][0-9]*\Z")
_OCTAL = re.compile(r"0[0-7]*\Z")
_HEX = re.compile(r"0[xX][0-9a-fA-F]+\Z")
_DIGIT_LED = re.compile(r"[0-9]")


def _literal(text: str, token: str) -> int:
    """One arithmetic token to its value, or the error bash would print.

    `text` is the WHOLE operand and `token` the piece being read, because bash's
    message names both: `[[: <text>: value too great for base (error token is
    "<token>")`.
    """
    body = token
    sign = 1
    while body[:1] in ("+", "-"):
        if body[0] == "-":
            sign = -sign
        body = body[1:]
    if _HEX.match(body):
        return sign * int(body, 16)
    if _OCTAL.match(body):
        return sign * int(body, 8)
    if _DECIMAL.match(body):
        return sign * int(body, 10)
    if _IDENTIFIER.match(body):
        # `set -u` and an unset variable: bash names the variable and DIES,
        # even from inside an `if` condition. Driven with "abc" and "abc def".
        raise _ArithError("%s: unbound variable" % body, fatal=True)
    if _DIGIT_LED.match(body[:1]):
        raise _ArithError(
            '[[: %s: value too great for base (error token is "%s")' % (text, token),
            fatal=False,
        )
    raise _ArithError(
        '[[: %s: arithmetic syntax error in expression (error token is "%s")' % (text, token),
        fatal=False,
    )


def arith(text: str) -> int:
    """`[[ <text> -gt ... ]]`'s reading of one operand.

    Exported so the differential can exercise it directly, without a subject.
    Whitespace-only and empty are BOTH zero, which is why `${x:-0}` and a
    remote command that printed nothing agree.
    """
    tokens = text.split()
    if not tokens:
        return 0
    value = _literal(text, tokens[0])
    if len(tokens) > 1:
        raise _ArithError(
            '[[: %s: arithmetic syntax error in expression (error token is "%s")'
            % (text, tokens[1]),
            fatal=False,
        )
    return value


def _compare(left: str, op: str, right: str) -> bool:
    """`[[ left <op> right ]]`, with bash's two failure modes intact.

    A nounset error aborts the whole run with status 1; a syntax error prints
    and makes the test FALSE, which is what bash's `[[ ]]` returns when its
    arithmetic did not evaluate.
    """
    try:
        lhs = arith(left)
        rhs = arith(right)
    except _ArithError as exc:
        _diagnose(exc.message)
        if exc.fatal:
            raise _ExitScriptError(1) from exc
        return False
    return {
        "-gt": lhs > rhs,
        "-ge": lhs >= rhs,
        "-lt": lhs < rhs,
        "-le": lhs <= rhs,
    }[op]


# ---------------------------------------------------------------------------
# Running children the way `set -euo pipefail` runs them.
# ---------------------------------------------------------------------------


def _spawn(argv: list[str], **kwargs) -> subprocess.Popen:
    """`Popen`, with bash's `command not found` in place of `FileNotFoundError`.

    Raises `_ExitScriptError(127)` after printing the diagnostic, which is what a
    missing binary does under `set -e` in a simple command. Callers that swallow
    the status catch it back.
    """
    try:
        return subprocess.Popen(argv, **kwargs)
    except FileNotFoundError as exc:
        _diagnose("%s: command not found" % argv[0])
        raise _ExitScriptError(127) from exc


def _strict(argv: list[str], **kwargs) -> None:
    """One foreground command under `set -e`: non-zero ends the run."""
    proc = _spawn(argv, **kwargs)
    code = _status(proc.wait())
    if code != 0:
        raise _ExitScriptError(code)


def _lenient(argv: list[str]) -> None:
    """`cmd 2>/dev/null || true`: the status, the stderr AND the missing-binary
    case are all discarded.

    The third is the one to read twice: bash's own `command not found` goes to
    the stderr that `2>/dev/null` throws away, and `|| true` eats the 127.
    """
    with open(os.devnull, "wb") as devnull, contextlib.suppress(FileNotFoundError):
        subprocess.run(argv, stderr=devnull, check=False)


def _capture(argv: list[str], **kwargs) -> str:
    """`x=$(cmd)` under `set -e`: output with ALL trailing newlines stripped.

    Stderr is NOT captured, matching the twin: a remote script's `>&2` lines
    reach this script's stderr and are part of the transcript.
    """
    proc = _spawn(argv, stdout=subprocess.PIPE, **kwargs)
    out, _ = proc.communicate()
    code = _status(proc.returncode)
    if code != 0:
        raise _ExitScriptError(code)
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def _capture_lenient(argv: list[str], **kwargs) -> str:
    """`x=$(cmd || true)`: whatever it printed before failing, status discarded.

    A missing binary is swallowed too, because the `|| true` is INSIDE the
    substitution and bash's 127 never reaches the assignment.
    """
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, **kwargs)
    except FileNotFoundError:
        _diagnose("%s: command not found" % argv[0])
        return ""
    out, _ = proc.communicate()
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def _lines(text: str) -> list[str]:
    """`while IFS= read -r line; do [[ -z "$line" ]] && continue; ...` fed by
    `printf '%s\\n' "$text"`.

    The `printf` re-terminates the (already newline-stripped) capture, so every
    field is newline-delimited and the empty ones are dropped. A text that is
    itself empty yields ONE empty line and therefore an empty list.
    """
    return [line for line in text.split("\n") if line]


class _State:
    """The two temp paths the EXIT trap has to know about, plus the identity of
    the worker. A class rather than module globals so the differential can build
    one without importing side effects."""

    def __init__(self) -> None:
        self.vm_ip = ""
        self.ssh_user = ""
        self.ssh_key = ""
        self.machine_name = ""
        self.counter_dir = ""
        self.cp_up_log = ""

    def ssh_argv(self, command: str) -> list[str]:
        """`_ssh()`: the remote command reaches ssh as ONE argument."""
        return [
            "ssh",
            "-i",
            self.ssh_key,
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=15",
            "%s@%s" % (self.ssh_user, self.vm_ip),
            command,
        ]

    def ref(self, repo: str) -> str:
        """`<repo>@<machine>`, the positional ref every repo command takes."""
        return "%s@%s" % (repo, self.machine_name)


def resolve(state: _State) -> None:
    """The six environment reads, in the twin's order and with its `set -u`.

    ORDER MATTERS: `VM_WORKERS` is consumed before `SSH_KEY`, so a
    whitespace-only `VM_WORKERS` aborts with `WORKER_IDS[0]: unbound variable`
    even on a host with no `$HOME`.
    """
    net_base = os.environ.get("VM_NET_BASE", "") or DEFAULT_NET_BASE

    # `read -ra WORKER_IDS <<<"${VM_WORKERS:-11}"` reads ONE line and splits it
    # on IFS. A second line in the value is silently unreachable, which is the
    # twin's behaviour and not a transcription slip.
    workers = (os.environ.get("VM_WORKERS", "") or DEFAULT_WORKERS).split("\n")[0].split()
    if not workers:
        # This fires BEFORE `trap cleanup EXIT` is installed, so no cleanup runs.
        _diagnose("WORKER_IDS[0]: unbound variable")
        raise _ExitScriptError(1)
    state.vm_ip = "%s.%s" % (net_base, workers[0])

    ssh_user = os.environ.get("SSH_USER", "") or os.environ.get("USER", "")
    if not ssh_user:
        ssh_user = _capture(["whoami"])
    state.ssh_user = ssh_user

    ssh_key = os.environ.get("SSH_KEY", "")
    if not ssh_key:
        home = os.environ.get("HOME")
        if home is None:
            # `$HOME` under `set -u`. Only reachable when SSH_KEY is unset or
            # empty, because `${SSH_KEY:-...}` does not expand its default
            # otherwise.
            _diagnose("HOME: unbound variable")
            raise _ExitScriptError(1)
        ssh_key = "%s/.ssh/id_ed25519" % home
    state.ssh_key = ssh_key

    state.machine_name = os.environ.get("MACHINE_NAME", "") or DEFAULT_MACHINE


def cleanup(state: _State) -> None:
    """`cleanup()` and the EXIT trap it is installed as.

    THE `&&` GUARDS ARE NOT `if` STATEMENTS. `[[ -n "$x" ]] && rm ...` is an
    AND-OR list: an empty variable makes the list fail WITHOUT aborting the
    function, because the failing member is not the last one. A failing `rm` IS
    the last member and does abort, which is why the two are spelled
    differently below.
    """
    log.step("Cleanup (best-effort)")
    if state.counter_dir:
        _strict(["rm", "-rf", state.counter_dir])
    if state.cp_up_log:
        _strict(["rm", "-f", state.cp_up_log])
    for repo in (CP_FORK_REPO, FORK_REPO, PARENT_REPO):
        _lenient(["rdc", "repo", "down", state.ref(repo)])
    for repo in (CP_FORK_REPO, FORK_REPO, PARENT_REPO):
        _lenient(["rdc", "repo", "delete", state.ref(repo), "--yes"])


def _phase_0(state: _State) -> None:
    """Register the worker with the CLI and provision renet on it."""
    log.step("Registering worker %s as machine '%s'" % (state.vm_ip, state.machine_name))
    with open(os.devnull, "wb") as devnull:
        _strict(["rdc", "config", "ssh", "set", "--key", state.ssh_key], stdout=devnull)

    # `rdc machine add ... 2>/dev/null || log_warn`. The stdout is NOT
    # suppressed, only the stderr, so a CLI that reports the conflict on stdout
    # still shows it.
    with open(os.devnull, "wb") as devnull:
        try:
            proc = subprocess.Popen(
                [
                    "rdc",
                    "machine",
                    "add",
                    state.machine_name,
                    "--ip",
                    state.vm_ip,
                    "--user",
                    state.ssh_user,
                ],
                stderr=devnull,
            )
            code = _status(proc.wait())
        except FileNotFoundError:
            code = 127
    if code != 0:
        log.warn("Machine '%s' already registered (continuing)" % state.machine_name)

    log.step("Provisioning renet on worker")
    _strict(["rdc", "machine", "setup", state.machine_name])

    # Pre-clean any debris from prior runs so create does not conflict. This is
    # the SAME function the EXIT trap runs, called directly.
    cleanup(state)


def _phase_1(state: _State) -> None:
    """Create the parent, apply the template, upload the counter sidecar, up it."""
    log.step("Creating parent repo + applying app-postgres template")
    _strict(["rdc", "repo", "create", PARENT_REPO, "-m", state.machine_name, "--size", "2G"])
    _strict(
        [
            "rdc",
            "repo",
            "admin",
            "template",
            "apply",
            state.ref(PARENT_REPO),
            "--template",
            "app-postgres",
        ]
    )

    log.step("Uploading checkpoint counter sidecar (Zcounter/)")
    state.counter_dir = _capture(["mktemp", "-d"])
    _write_via_cat(os.path.join(state.counter_dir, "docker-compose.yml"), COMPOSE_YML)
    _write_via_cat(os.path.join(state.counter_dir, "Rediaccfile"), REDIACCFILE)
    _strict(
        [
            "rdc",
            "repo",
            "sync",
            "upload",
            state.ref(PARENT_REPO),
            "--local",
            state.counter_dir,
            "--remote",
            "Zcounter",
        ]
    )
    _strict(["rm", "-rf", state.counter_dir])
    state.counter_dir = ""

    log.step("Bringing parent up (parent's postgres will bind first)")
    _strict(["rdc", "repo", "up", state.ref(PARENT_REPO)])


def _write_via_cat(path: str, payload: str) -> None:
    """`cat >"$path" <<'EOF'`, as a real `cat` with a real redirection.

    `pathlib.write_text` would be one line and would not appear in the call log.
    The redirection is opened FIRST, exactly as bash does, so a directory that
    does not exist fails before `cat` is ever looked up.
    """
    with contextlib.ExitStack() as stack:
        # OPENED INSIDE ITS OWN `try`, because the redirection failing is a
        # DIFFERENT event from `cat` failing: bash reports it as its own
        # diagnostic and never looks the command up at all.
        try:
            handle = stack.enter_context(open(path, "wb"))
        except OSError as exc:
            _diagnose("%s: %s" % (path, exc.strerror))
            raise _ExitScriptError(1) from exc
        proc = _spawn(["cat"], stdin=subprocess.PIPE, stdout=handle)
        proc.communicate(payload.encode("utf-8"))
        code = _status(proc.returncode)
    if code != 0:
        raise _ExitScriptError(code)


def _phase_2(state: _State) -> None:
    """Fork the RUNNING parent and bring the fork up. This is the failure path
    on main: without the fix the fork's postgres cannot bind."""
    log.step("Forking parent into '%s' (parent stays running)" % FORK_TAG)
    _strict(["rdc", "repo", "fork", state.ref(PARENT_REPO), "--tag", FORK_TAG])

    log.step("Bringing fork up %s must succeed (renet#60 regression guard)" % DASH)
    proc = _spawn(["rdc", "repo", "up", state.ref(FORK_REPO)])
    if _status(proc.wait()) == 0:
        return

    log.error("rdc repo up '%s' failed" % FORK_REPO)
    log.error("Diagnostic dump follows %s db logs + cgroup state + listening sockets" % DASH)
    for message, command in (
        ("[diag] cgroup hierarchy under /sys/fs/cgroup/rediacc.slice", DIAG_CGROUP_TREE),
        ("[diag] postgres binds on host (any source port :5432)", DIAG_BINDS),
        (
            (
                "[diag] cgroup_configs BPF map contents"
                " (pinned at /sys/fs/bpf/rediacc/cgroup_configs)"
            ),
            DIAG_BPF_MAP,
        ),
        ("[diag] BPF programs attached to rediacc.slice", DIAG_BPF_TREE),
        ("[diag] db container logs (parent + fork sockets)", DIAG_DB_LOGS),
    ):
        log.step(message)
        # `_ssh ... || true`: every diagnostic is best-effort, including a
        # missing `ssh`, whose 127 the `|| true` also swallows.
        with contextlib.suppress(_ExitScriptError):
            _strict(state.ssh_argv(command))

    log.error("(see diagnostic dump above)")
    raise _ExitScriptError(1)


def _phase_3(state: _State) -> None:
    """Bind isolation: two distinct `127.0.x.x:5432`, no wildcard."""
    log.step("Reading postgres binds on worker (sport = :5432)")
    binds = _lines(_capture_lenient(state.ssh_argv(BINDS_CMD)))

    log.step("Found %d listener(s):" % len(binds))
    # `for b in "${binds[@]:-}"` yields ONE EMPTY ELEMENT when the array is
    # empty, so an empty result still prints a bare indented line. Reproduced
    # rather than tidied.
    for bind in binds or [""]:
        log.step("  %s" % bind)

    if len(binds) < 2:
        log.error("expected >=2 postgres listeners (parent + fork), got %d" % len(binds))
        raise _ExitScriptError(1)

    for bind in binds:
        if bind in WILDCARD_BINDS:
            log.error(
                "found wildcard bind '%s' %s bind-rewrite did not fire (renet#60 regressed)"
                % (bind, DASH)
            )
            raise _ExitScriptError(1)
        if not LOOPBACK_BIND.fullmatch(bind):
            log.error("unexpected bind '%s' %s expected 127.0.x.x:5432" % (bind, DASH))
            raise _ExitScriptError(1)

    # `printf '%s\n' "${binds[@]}" | sort -u`, inside a process substitution. A
    # process substitution's status is NEVER checked, not even under pipefail,
    # so a failing or missing `sort` silently yields no unique addresses and the
    # run fails on the count below rather than on the tool.
    unique = _lines(_sort_unique(binds))
    if len(unique) < 2:
        log.error(
            "all binds collapsed to a single IP (%s) %s isolation violated" % (binds[0], DASH)
        )
        raise _ExitScriptError(1)
    log.info("%s %d distinct loopback binds %s isolation holds" % (TICK, len(unique), DASH))


def _sort_unique(binds: list[str]) -> str:
    """`printf '%s\\n' "${binds[@]}" | sort -u`, status deliberately ignored."""
    try:
        proc = subprocess.Popen(["sort", "-u"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    except FileNotFoundError:
        _diagnose("sort: command not found")
        return ""
    out, _ = proc.communicate("".join("%s\n" % bind for bind in binds).encode("utf-8"))
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def _phase_4(state: _State) -> None:
    """renet#59: no per-network daemon may own more than one compose project."""
    log.step("Asserting no per-network daemon hosts more than one compose-project (renet#59)")
    # NO `|| true` HERE, unlike phase 3: a broken `ssh` ends the run rather than
    # being read as "zero foreign projects".
    foreign = _capture(state.ssh_argv(PROJECTS_CMD))
    if _compare(foreign or "0", "-gt", "1"):
        log.error(
            "a per-network daemon hosts %s compose projects %s renet#59 regressed" % (foreign, DASH)
        )
        raise _ExitScriptError(1)
    log.info("%s each per-network daemon hosts at most one compose project" % TICK)


def _counter_sockets(state: _State) -> list[str]:
    """Every per-network socket running a counter container, as a word-split list."""
    return _capture(state.ssh_argv(COUNTER_SOCKETS_CMD)).split()


def _counter_value(state: _State, sock: str) -> str:
    """The counter container's last logged count on one socket, or empty."""
    return _capture(state.ssh_argv(counter_value_cmd(sock)))


def _pipe2(
    left: list[str],
    right: list[str],
    *,
    left_stderr_to_pipe: bool = False,
    capture: bool = False,
) -> tuple[int, bytes]:
    """`left | right` the way bash builds it, including both ENOENT arms.

    A REAL PIPE, NOT A PYTHON HAND-OFF, and the difference is observable in
    three places that a `Popen(stdin=other.stdout)` chain gets wrong:

      * A MISSING RIGHT-HAND SIDE STILL LEAVES THE LEFT ONE RUNNING. Bash forks
        both members before either execs, so `grep ... | tail -20` with `grep`
        absent STILL INVOKES `tail`, and `rdc ... | tee log` with `tee` absent
        still invokes `rdc`. Driven: a port that returned early on the first
        ENOENT lost a recorded call in one case and leaked `rdc`'s output onto
        this script's stdout in the other, because `rdc`'s stdout was the pipe
        and the pipe had no reader.
      * THE PARENT CLOSES BOTH ENDS IMMEDIATELY, which is what turns "nobody is
        reading" into the left-hand side's SIGPIPE rather than a hang.
      * A LEFT-HAND SIDE WITH `2>&1` PUTS BASH'S OWN `command not found` INTO
        THE PIPE, not onto this script's stderr, so the log file the guard reads
        afterwards contains the diagnostic. `left_stderr_to_pipe` is that.

    Returns the PIPEFAIL status (the last member to exit non-zero) and, when
    asked, the right-hand side's stdout.
    """
    read_fd, write_fd = os.pipe()
    left_proc: subprocess.Popen | None = None
    left_code = 0
    try:
        left_proc = subprocess.Popen(
            left,
            stdout=write_fd,
            stderr=write_fd if left_stderr_to_pipe else None,
        )
    except FileNotFoundError:
        message = (_shell_diagnostic("%s: command not found" % left[0]) + "\n").encode("utf-8")
        if left_stderr_to_pipe:
            os.write(write_fd, message)
        else:
            sys.stderr.buffer.write(message)
            sys.stderr.buffer.flush()
        left_code = 127

    right_proc: subprocess.Popen | None = None
    right_code = 0
    try:
        right_proc = subprocess.Popen(
            right, stdin=read_fd, stdout=subprocess.PIPE if capture else None
        )
    except FileNotFoundError:
        _diagnose("%s: command not found" % right[0])
        right_code = 127

    os.close(write_fd)
    os.close(read_fd)

    out = b""
    if right_proc is not None:
        out, _ = right_proc.communicate()
        right_code = _status(right_proc.returncode)
    if left_proc is not None:
        left_code = _status(left_proc.wait())
    # pipefail: the status of the LAST (rightmost) member to exit non-zero.
    return (right_code or left_code), out


def _first_counter_socket(state: _State) -> str:
    """`counter_sockets | head -1`, with pipefail.

    A real pipeline rather than a slice of the captured list, because `head` is
    an external and the call log is what the differential compares.
    """
    code, out = _pipe2(state.ssh_argv(COUNTER_SOCKETS_CMD), ["head", "-1"], capture=True)
    if code != 0:
        raise _ExitScriptError(code)
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


def _phase_5(state: _State) -> None:
    """console#440: a `--checkpoint` fork of the RUNNING parent must restore
    process state in the fork while the parent keeps running."""
    log.step("Locating parent's counter container")
    parent_sock = _first_counter_socket(state)
    if not parent_sock:
        log.error("parent has no running counter container %s sidecar upload or up failed" % DASH)
        raise _ExitScriptError(1)

    log.step("Waiting for parent counter to reach 15 (restore-vs-fresh margin)")
    parent_count = "0"
    for _attempt in range(COUNTER_ATTEMPTS):
        parent_count = _counter_value(state, parent_sock)
        # `[[ ... ]] && break` is an AND-OR list, so a false test does NOT abort
        # the loop under `set -e`; and the `sleep` below runs even on the last
        # pass, which is the wasted minute named in the module docstring.
        if _compare(parent_count or "0", "-ge", str(COUNTER_TARGET)):
            break
        _strict(["sleep", "2"])

    if _compare(parent_count or "0", "-lt", str(COUNTER_TARGET)):
        log.error(
            "parent counter stuck at '%s' %s counter container unhealthy"
            % (parent_count or "0", DASH)
        )
        log.step("[diag] raw counter container state + logs")
        with contextlib.suppress(_ExitScriptError):
            _strict(state.ssh_argv(counter_diag_cmd(parent_sock)))
        raise _ExitScriptError(1)
    log.info("parent counter at %s before checkpoint" % parent_count)

    log.step("Forking running parent with --checkpoint into '%s'" % CP_FORK_TAG)
    _strict(["rdc", "repo", "fork", state.ref(PARENT_REPO), "--tag", CP_FORK_TAG, "--checkpoint"])

    log.step("Bringing checkpoint fork up %s restore must fire (console#440)" % DASH)
    state.cp_up_log = _capture(["mktemp"])
    if _up_through_tee(state) != 0:
        log.error("rdc repo up '%s' failed" % CP_FORK_REPO)
        raise _ExitScriptError(1)

    if not _grep_quiet("restored from checkpoint", state.cp_up_log):
        log.error("fork up succeeded but no checkpoint restore happened (console#440 regressed:")
        log.error(
            "either the dump never reached the fork %s cow_sync %s or restore failed"
            " and fell back to fresh)" % (DASH, DASH)
        )
        _grep_tail(state.cp_up_log)
        raise _ExitScriptError(1)
    _strict(["rm", "-f", state.cp_up_log])
    state.cp_up_log = ""

    log.step("Reading fork's counter (restored process)")
    fork_sock = ""
    for sock in _counter_sockets(state):
        if sock != parent_sock:
            fork_sock = sock
    if not fork_sock:
        log.error("no counter container in the fork's daemon")
        raise _ExitScriptError(1)

    fork_count = _counter_value(state, fork_sock)
    if _compare(fork_count or "0", "-lt", parent_count):
        log.error(
            "fork counter %s < pre-checkpoint %s %s process state NOT restored"
            % (fork_count or "0", parent_count, DASH)
        )
        raise _ExitScriptError(1)
    log.info(
        "%s fork counter continued at %s (>= %s) %s CRIU state preserved"
        % (TICK, fork_count, parent_count, DASH)
    )

    log.step("Asserting parent kept running through fork + restore")
    parent_after = _counter_value(state, parent_sock)
    _strict(["sleep", "3"])
    parent_after2 = _counter_value(state, parent_sock)
    if _compare(parent_after2 or "0", "-le", parent_after or "0"):
        log.error(
            "parent counter stalled (%s -> %s) %s parent disturbed by fork restore"
            % (parent_after, parent_after2, DASH)
        )
        raise _ExitScriptError(1)
    log.info("%s parent counter still advancing (%s -> %s)" % (TICK, parent_after, parent_after2))


def _up_through_tee(state: _State) -> int:
    """`rdc repo up <ref> --debug 2>&1 | tee "$log"`, with pipefail.

    `2>&1` IS APPLIED TO `rdc`, NOT TO THE PIPELINE, so a missing `rdc` puts
    bash's own diagnostic INTO the log file rather than onto this script's
    stderr, and the checkpoint guard below then reads a log that says
    `command not found`. Driven, not assumed.
    """
    argv = ["rdc", "repo", "up", state.ref(CP_FORK_REPO), "--debug"]
    code, _ = _pipe2(argv, ["tee", state.cp_up_log], left_stderr_to_pipe=True)
    return code


def _grep_quiet(pattern: str, path: str) -> bool:
    """`grep -q <pattern> <path>`. A missing `grep` is a 127, which is not 0, so
    the guard fires exactly as it would for an absent line."""
    try:
        return subprocess.run(["grep", "-q", pattern, path], check=False).returncode == 0
    except FileNotFoundError:
        _diagnose("grep: command not found")
        return False


def _grep_tail(path: str) -> None:
    """`grep -iE "checkpoint|restor" <log> | tail -20 || true`.

    ITS OUTPUT GOES TO STDOUT while the two `log_error` lines above it go to
    stderr, so a caller reading only one stream sees half the report. That is
    the twin's shape and it is reproduced.

    The trailing `|| true` means the status is discarded, so `_pipe2`'s return
    is deliberately dropped.
    """
    _pipe2(["grep", "-iE", "checkpoint|restor", path], ["tail", "-20"])


def _body(state: _State) -> None:
    """Everything between the `trap` and the final `log_info`."""
    _phase_0(state)
    _phase_1(state)
    _phase_2(state)
    _phase_3(state)
    _phase_4(state)
    _phase_5(state)
    log.info(
        "PASS: parent + fork running, distinct binds, no foreign containers,"
        " checkpoint fork restored"
    )


def main(argv: list[str]) -> int:
    """The twin ignores its arguments entirely; so does this, and `argv` is
    accepted only so the signature matches every other module in the package.

    THE TRAP IS INSTALLED AFTER `resolve`, NOT BEFORE, because the twin installs
    it on line 67 and reads `VM_WORKERS` on line 35. The unbound-array abort
    therefore runs NO cleanup, and a reader who moved the `finally` up would
    silently add six `rdc` calls to that path.
    """
    del argv
    state = _State()
    try:
        resolve(state)
    except _ExitScriptError as exc:
        return exc.code

    try:
        _body(state)
    except _ExitScriptError as exc:
        code = exc.code
    else:
        code = 0

    # `trap cleanup EXIT`. The body's status survives a clean cleanup and is
    # REPLACED by a cleanup that dies under `set -e`, which is what bash does.
    try:
        cleanup(state)
    except _ExitScriptError as exc:
        return exc.code
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

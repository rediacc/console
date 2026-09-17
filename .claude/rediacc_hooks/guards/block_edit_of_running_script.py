"""Refuse to edit a shell script that a process is CURRENTLY RUNNING.

WHY A HOOK. This is written down in full at docs/agent-reference/TRAPS.md
("Editing a shell script while a background job is RUNNING it"), with the
mechanism, the 2026-08-09 incident, and the tell. It was hit again on
2026-08-26, on the SAME file, with the SAME signature: a backgrounded
test-hooks.sh died at `line 1179: syntax error near unexpected token 'else'`
while `bash -n` on that exact file was clean. Cost a full suite pass. A trap
documented in that much detail and walked into anyway is one that needs a gate
rather than another paragraph.

THE MECHANISM, because the error never points at it. Bash reads a script
LAZILY, by byte offset, not into memory. Rewrite the file mid-run and the
interpreter resumes at its old offset inside the NEW bytes, so it starts
parsing mid-token. The line it names is innocent and may not even exist at
that number any more. `bash -n` being clean is the tell: a syntax error the
syntax checker cannot reproduce is not in the file, it is in the READER.

HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB. Every guard in a chain executes on
every tool call in that chain, including the call carrying your edit -- so
editing a pre-edit guard finds that guard "running", permanently, with no
moment of quiet to wait for. Its Bash-side sibling hit this on 2026-08-27 and
blocked four commands including its own repair. A chain evaluator lives for
milliseconds and is re-read from scratch next call, so the lazy-read window
below does not exist for it; a suite or background job running for minutes,
which is what this guard is for, still matches and still blocks.

SCOPE: shell scripts only, and only while something is actually running one.
A .ts or .py file is read once into memory by its interpreter, so editing it
mid-run is merely confusing rather than corrupting. Narrow on purpose -- a
guard that refused every edit to any file with a live process would be the
over-matching this repo has switched guards off for.

PORT NOTE ON THE THREE PROCESS READS. `pgrep -f`, `ps -o comm=` and
`tr '\\0' ' ' < /proc/<pid>/cmdline` are `proc.pgrep_full`, `proc.is_shell` and
`proc.cmdline_tr`. That module exists because these two guards are the only
consumers of the process table and each read has a trap attached: `comm` is
truncated to 15 characters on Linux, `ps -o args=` cannot say where the NUL
separators were, and a kernel thread's empty cmdline is invisible to `pgrep -f`.
`cmdline_tr` in particular keeps the TRAILING SPACE that `tr` leaves behind,
which `cut -d' ' -f1-4` and the grep below cannot see and which a port would
therefore drop by accident.

PORT NOTE ON WHY THIS GUARD'S FIXTURE STARTS A REAL PROCESS. Every branch that
produces output is behind "an interpreter is executing this script right now",
and nothing in the payload or the environment can fake that: the bash twin
consults the real process table through real pgrep. So the fixture below
LAUNCHES two `bash <script>` processes, in their own session, and kills them
when the interpreter that built them exits. Both sides then read the same two
processes, and the pids in the message are identical because it is literally the
same process. Its Bash-side sibling
(block-bash-write-to-running-script.sh) reads the same world through the same
token rather than starting two more.
"""

import atexit
import os
import re
import signal
import subprocess
import tempfile

from rediacc_hooks import hookio, proc

CHAIN = "pre-edit"
TWIN = "pre-edit/block-edit-of-running-script.sh"
ORDER = 7

# HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and dropping the exclusion is not a small over-block: every guard in a chain runs on the call carrying your edit, so the refusal is PERMANENT and no amount of waiting clears it. Its Bash-side sibling cost four blocked commands that way on 2026-08-27, one of them its own repair.
DEFECT = (
    "if hookio.grep_q(HOOK_CHAIN, rargs):\n            continue",
    "if False:\n            continue",
)

HOOK_CHAIN = r"\.claude/hooks/(pre-bash|pre-edit|pre-ask|post-bash)/"

# The characters `sed 's/[.[\*^$()+?{}|]/\\&/g'` escapes. Note that inside a
# POSIX bracket expression a backslash is an ORDINARY character, so `\` is a member of the set rather than an escape.
META = r"([.\[\\*^$()+?{}|])"

MESSAGE = """BLOCKED: '%(base)s' is being executed by a live process right now.

  %(running)s

Bash reads a script LAZILY, by byte offset, not into memory. Editing it now
makes the running interpreter resume at its old offset inside your new bytes,
so it starts parsing mid-token and dies with a syntax error naming an INNOCENT
line -- often one that no longer exists at that number. `bash -n` on the file
stays clean throughout, which is what makes the failure so expensive to chase.

This is docs/agent-reference/TRAPS.md, "Editing a shell script while a
background job is RUNNING it". It cost a suite pass on 2026-08-09 and again on
2026-08-26, both times on test-hooks.sh.

Pick one:

  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on anyway, so editing now costs you the result twice.
  2. Edit a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first -- then the
     edit is safe and this guard goes quiet on its own.
"""

# --------------------------------------------------------------------------- The fixture world: two live shells, at deterministic paths ---------------------------------------------------------------------------

WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-running")
LIVE_SCRIPT = "%s/long-running-suite.sh" % WORLD
SIBLING_SCRIPT = "%s/hook-chain-sibling.sh" % WORLD
IDLE_SCRIPT = "%s/nothing-is-running-this.sh" % WORLD

# The second statement is not decoration. bash EXECs a script's final simple command in place when it can, which would replace the shell with `sleep` --
# `ps -o comm=` would then answer `sleep`, the shell test below would reject it,
# and the fixture would silently stop being a running shell script.
_BODY = "#!/usr/bin/env bash\nsleep 600\nexit 0\n"

_CHILDREN = []


def _reap():
    """Kill the world by PATH, not by the pids `Popen` handed back.

    MEASURED 2026-09-06: on this host `bash` is not `/usr/bin/bash`. A wrapper
    at ~/.local/share/rediacc/bin/bashcov-sup takes its place on PATH and
    re-execs the real interpreter as a CHILD, so `Popen(["bash", script])`
    yields a supervisor plus a grandchild, and killing the supervisor's process
    group left the grandchild alive and re-parented -- four such shells were
    still running after a clean pytest exit. Reaping by cmdline finds both,
    which is the same predicate `_kill_stale` uses on the way in.
    """
    _kill_stale((LIVE_SCRIPT, SIBLING_SCRIPT))


def _running_world(_unused):
    """Two live `bash <script>` processes and one script nobody runs.

    `start_new_session=True` puts each in its own process group so the whole
    group can be killed; `atexit` does that when the test interpreter exits, and
    the 600-second `sleep` is the backstop if it never gets the chance.
    """
    os.makedirs(WORLD, exist_ok=True)
    for path in (LIVE_SCRIPT, SIBLING_SCRIPT, IDLE_SCRIPT):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_BODY)
        # No chmod: the shells below are started as `bash <script>`, so the execute bit is never consulted, and setting one would only trip the permissive-mask lint for no behaviour.
    if not _CHILDREN:
        _hold_world_lock(WORLD)
        _kill_stale((LIVE_SCRIPT, SIBLING_SCRIPT))
        _CHILDREN.append(_spawn([LIVE_SCRIPT]))
        # Launched with an argument that names a chain directory, which is the only way to reach the sibling exclusion from a controlled world.
        _CHILDREN.append(_spawn([SIBLING_SCRIPT, ".claude/hooks/pre-edit/marker"]))
        atexit.register(_reap)
        _await_visible()
    return WORLD


def _spawn(argv):
    return subprocess.Popen(
        ["bash", *argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# One session at a time in this world. TWO pytest runs of this suite were live on this machine at once on 2026-09-06 (a peer agent's and this one's), and they fought: each `_kill_stale` killed the other's shells, and the case that names a running script reported different pids on the two sides of one differential. The world has to sit at a FIXED path -- a static payload names
# it -- so it cannot be made per-process; an advisory lock held for the life of
# the interpreter makes the second run wait instead.
_LOCK_FDS = []


def _hold_world_lock(world):
    """flock the world, or proceed after a bounded wait rather than hang.

    The descriptor is deliberately never closed: the lock is released by the
    kernel when this interpreter exits, which is exactly the lifetime the
    spawned shells have.
    """
    import fcntl  # noqa: PLC0415
    import time  # noqa: PLC0415

    fd = os.open(os.path.join(world, ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + 300.0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if time.monotonic() >= deadline:
                # A five-minute wait means the other run is wedged, not busy.
                # Proceeding is better than a suite that never finishes; the
                # differential will say so loudly if the worlds then collide.
                break
            time.sleep(0.2)
            continue
        break
    _LOCK_FDS.append(fd)


def _kill_stale(paths):
    """Kill any leftover fixture shells from an EARLIER run before spawning.

    THIS IS NOT TIDINESS, it is the difference between a green differential and
    a red one. The world sits at a fixed path so the payloads can name it, and
    `atexit` does not fire when the interpreter is killed by a timeout -- so a
    previous run can leave its shells alive. `head -3` in the loop below then
    keeps the FIRST few matches, and a set that changes between the bash sweep
    and the Python sweep reports different pids for the same case. Observed
    exactly that: three processes for one script, two of them from runs that had
    already finished, and the two sides disagreed on which two they saw.

    Only processes running THESE fixture scripts are touched -- nothing else on
    the machine can match a path under this world -- and each was started with
    `start_new_session=True`, so it leads its own group and killing the group
    takes its `sleep` child with it.
    """
    import time  # noqa: PLC0415

    for _ in range(500):
        stale = [p for p in proc.pids() if any(t in (proc.cmdline(p) or "") for t in paths)]
        if not stale:
            return
        for pid in stale:
            try:
                if os.getpgid(pid) == pid:
                    os.killpg(pid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                continue
        time.sleep(0.01)


def _await_visible():
    """Both shells must be in the process table before any case runs.

    `Popen` returns before the exec completes, and the differential's bash sweep
    starts immediately afterwards. A case that ran in that gap would see one
    process on one side and two on the other, and the disagreement would be
    reported as a port defect.
    """
    for _ in range(500):
        seen = 0
        for child in _CHILDREN:
            line = proc.cmdline(child.pid)
            if line and ".sh" in line:
                seen += 1
        if seen == len(_CHILDREN):
            return
        _pause()


def _pause():
    # Deliberately not `time.sleep` at module scope: this is a 10 ms poll, and naming it once keeps the loop above readable.
    import time  # noqa: PLC0415

    time.sleep(0.01)


FIXTURES = {"running-scripts": _running_world}

# The variable is never read by this guard; resolving the token is what starts
# the world. Its Bash-side sibling names the same token.
ENVS = [("running", {"REDIACC_RUNNING_WORLD": "{FIXTURE:running-scripts}"}, {})]

EDGE_CASES = [
    ("a script an interpreter is executing", {"tool_input": {"file_path": LIVE_SCRIPT}}),
    # HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB.
    ("a chain evaluator is not a running job", {"tool_input": {"file_path": SIBLING_SCRIPT}}),
    ("a script nobody is running", {"tool_input": {"file_path": IDLE_SCRIPT}}),
    # SCOPE: shell scripts only.
    ("a TypeScript file is read into memory", {"tool_input": {"file_path": "packages/cli/a.ts"}}),
    ("a Python file is read into memory", {"tool_input": {"file_path": "a.py"}}),
    # ESCAPE THE DOTS: `[b].sh` unescaped matches **/bin/bash**, i.e. every bash process on the machine. Measured on the twin 2026-09-01.
    ("a one-letter script name", {"tool_input": {"file_path": "b.sh"}}),
    ("no file_path at all", {"tool_input": {"new_string": "x"}}),
]


def pattern_for(base):
    """`(^|[/[:space:]])[<first>]<escaped rest>`, built exactly as the bash does.

    BRACKET CLASS ON THE FIRST CHARACTER, and it is not decoration: without it
    this pgrep matches the shell running this very hook, whose command line
    contains the path it was handed. That is the self-matching trap block-
    self-matching-pgrep.sh exists for, and writing this guard is exactly where it
    would have bitten again.

    ANCHOR TO A PATH BOUNDARY. A bare basename matches any process whose command
    line merely CONTAINS it as a substring (`ver.sh` inside a running
    `wslServer.sh`). The basename must start at the beginning, after a `/`, or
    after whitespace. Fixed here 2026-08-30 to match the Bash-side sibling
    (block-bash-write-to-running-script.sh), which got this anchor on 2026-08-27
    and this guard never did -- a sibling drift, not a design choice.

    ESCAPE THE DOTS, same defect and same fix as the Bash-side twin. `.` is a regex
    wildcard and the basename was interpolated raw, so a one-letter name plus the shell
    suffix produced `[x].sh` -- which for `b` matches **/bin/bash**, i.e. every bash process
    alive. Measured on the twin 2026-09-01: an edit was refused naming
    `/bin/bash --init-file ...` as the job it would corrupt, with no such script running.
    Found here by sweeping the class rather than by being bitten a second time; the two
    guards build this pattern identically, so a fix to one that skipped the other would have
    left the same hole open on the Edit door.
    """
    esc = re.sub(META, r"\\\1", base[1:])
    return hookio.rx(r"(^|[/{S}])[") + base[:1] + r"]" + esc


def live_shells(pat, limit):
    """The `for RPID in $(pgrep -f -- "$PAT")` loop, as its accumulated text.

    `pgrep -af` matches any process whose ARGUMENTS mention the name, which is
    the very trap this guard exists to prevent, wearing a different hat. Fixed
    here 2026-08-30, mirroring the Bash-side sibling's 2026-08-27 fix
    (review-found on PR #579, on a different guard, same class): a running
    `claude -p '<huge prompt text>'` invocation -- the stop-hook judge itself --
    has this exact filename embedded in its prompt (an example inside
    docs/agent-reference/TRAPS.md, quoted in this very file's own comments) and
    was scored as "executing" it. No interpreter was running the script at all.

    A process is RUNNING the script only if an interpreter is executing it. So
    require the matching process to BE a shell, and the name to sit in the first
    few argv slots where a script argument lives, rather than buried in a prose
    payload.
    """
    try:
        pids = proc.pgrep_full(pat)
    except (proc.ProcError, re.error):
        # `pgrep ... 2>/dev/null` in a `$( )`: a pattern pgrep refuses, or a process table it cannot read, both yield an empty word list and the loop simply never runs.
        pids = []
    running = ""
    for rpid in pids:
        if not proc.is_shell(rpid):
            continue
        rargs = proc.cmdline_tr(rpid)
        if rargs is None:
            rargs = ""
        # `cut -d' ' -f1-4`: the first four SPACE-delimited fields, with runs of spaces counting as empty fields exactly as cut reads them.
        first4 = " ".join(rargs.split(" ")[:4])
        if not hookio.grep_q(pat, first4):
            continue
        if hookio.grep_q(HOOK_CHAIN, rargs):
            continue
        running += "%d %s\n" % (rpid, rargs[:80])
    # `$(printf '%s' "$running" | head -N)`
    kept = running.split("\n")[:limit] if running != "" else []
    return hookio._command_substitution("\n".join(kept))


def indented(running):
    """`$(printf '%s\\n' "$RUNNING" | sed 's/^/    /')`, inside the heredoc."""
    return hookio._command_substitution(hookio.sed_sub(r"^", "    ", hookio._printf_line(running)))


def run(ev):
    path = ev.field("tool_input", "file_path")
    if path == "":
        return hookio.ALLOW
    if not hookio.case_glob(path, "*.sh"):
        return hookio.ALLOW

    base = path.rsplit("/", 1)[-1]
    running = live_shells(pattern_for(base), 3)
    if running == "":
        return hookio.ALLOW

    ev.warn_raw(MESSAGE % {"base": base, "running": indented(running)})
    return hookio.DENY

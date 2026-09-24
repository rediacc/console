"""The Bash half of block-edit-of-running-script.

WHY A SECOND FILE. The pre-EDIT guard only sees the Edit/Write tools. Within an hour of shipping it I walked into the same trap through Bash instead -- a `python3 - <<PY ... p.write_text(...) PY` rewriting test-hooks.sh while FOUR copies of it were executing. The guard did not fire because it never saw the call. A guard that covers one of two doors is a guard you will walk around
without noticing, which is exactly what happened.

THE MECHANISM, since the error never points at it: bash reads a script LAZILY, by byte offset. Rewrite it mid-run and the interpreter resumes at its old offset inside the new bytes and starts parsing mid-token. It dies naming an INNOCENT line while `bash -n` on that same file stays clean. Documented at docs/agent-reference/TRAPS.md, and hit three times on 2026-08-26/27.

HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and excluding them is not a loophole -- it is the difference between this guard working and this guard making a whole directory uneditable. Every pre-bash guard executes on EVERY Bash call, including the one carrying your edit. So while you edit block-binary-deploy.sh, that guard is running, as a sibling in the chain evaluating that very
edit. This fired on exactly that on 2026-08-27, and the block is PERMANENT: there is no moment when a pre-bash guard is not running during a Bash call, so no amount of waiting clears it. It cost four blocked commands before the cause was visible, one of them the fix itself.

The exclusion costs close to nothing. A chain evaluator lives for milliseconds and is re-read from scratch on the next call, so the lazy-read corruption below needs a window that does not exist here. What this guard is actually for -- a suite, a build, a background job running for minutes -- is untouched, test-hooks.sh included: that runs from the hooks ROOT, not a chain directory,
so it still matches and still blocks.

WRITE INTENT IS REQUIRED, not merely the filename. Every second command in this repo mentions a .sh path -- running it, grepping it, checking its processes. Blocking on the name alone would be the over-matching that gets a guard switched off, so this needs a write operator AND a live process.

PORT NOTE ON THE DUPLICATION WITH ITS EDIT-TOOL SIBLING. `pattern_for` and the pgrep loop below are the same twenty lines as block_edit_of_running_script.py, and that is deliberate: the two BASH files duplicate them too, and the duplication is exactly what produced the sibling drift their comments record (the path anchor reached the Edit-side guard on 2026-08-30, three days after
this one got it on 2026-08-27). A port whose job is fidelity does not get to unify them, because each half is judged against its own twin; unifying is a P6 change, once there is no twin left to diverge from.

PORT NOTE ON `for cand in $TARGETS`. That is an UNQUOTED expansion, so bash splits on IFS -- dropping empty fields, which is why an empty first line from `printf '%s\\n%s'` costs nothing -- and then GLOBS each word against the filesystem. The globbing has never mattered here (a `.sh` path holding a `*` or a `?` would already have been skipped by the `$` test or failed to match a
process) and is not reproduced; the splitting is, because the empty-field case happens on every command that reaches the fallback with no redirect targets.

PORT NOTE ON `sort -u`. Under `LC_ALL=C` sort orders by BYTE, so the key below
is the UTF-8 encoding rather than Python's default codepoint comparison. The two agree on every ASCII path and can differ on anything else, and the order is observable: it decides which of several targets is reported first.
"""

import atexit
import os
import re
import signal
import subprocess
import tempfile

from rediacc_hooks import hookio, proc

CHAIN = "pre-bash"
TWIN = "pre-bash/block-bash-write-to-running-script.sh"
ORDER = 16

# AN ASCII ARROW IS NOT A REDIRECT, and this is the FIFTH round of the same
# class. Measured 2026-09-01: writing a plain markdown file was refused because
# its PROSE contained `check:ci-hook-worklist-suite -> .claude/hooks/stop/test-worklist-v5.sh`. The `->` scored as a redirect and the path after it as the target, so a document describing a script was treated as a command overwriting it. Widening the class back to "any character" restores that block exactly.
DEFECT = ('NOT_ARROW = r"(^|[^->])"', 'NOT_ARROW = r"(^|[^ZZ])"')

# A real redirect's `>` is preceded by whitespace, start-of-string, or a digit (`2>`). Never by `-`. Requiring that keeps every true positive and drops the arrow. One constant, used by BOTH the intent test and the target harvest, because the two disagreeing about what a redirect is was how the class kept coming back.
NOT_ARROW = r"(^|[^->])"

_S = hookio.SPACE
_NOT_SEP = r"[^|&;" + _S + r"]"

# A write indicator: a redirect, an in-place edit, a copy/move onto it, or a python/perl write. Reading, running and grepping are none of these. The write-detector. It recognised `write_text` -- the exact idiom in the header comment above -- but NOT `open(path, "w").write(...)`, which is the commoner one, so the door this guard exists to close was open for that spelling. Verified
# 2026-08-27: the header's own example was caught and its sibling was not.
WRITE_INTENT = (
    NOT_ARROW
    + r">>?["
    + _S
    + r"]*"
    + _NOT_SEP
    + r"*\.sh|sed["
    + _S
    + r"]+-i|tee["
    + _S
    + r"]|write_text|write_bytes|writelines|\.write\(|open\([^)]*[\"']]?[wa]"
    r"|shutil\.(copy|move)|truncate|\bcp[" + _S + r"]|\bmv[" + _S + r"]|\bshfmt[" + _S + r"]+-w"
)

# Only .sh paths that are actually the TARGET of a write. Collecting every .sh token anywhere in the command blocked a heredoc that merely MENTIONED a running script while writing a different file -- and a false block on a safety guard is how a guard gets worked around, which costs more than the block saved.
TARGET_SPAN = (
    NOT_ARROW
    + r">>?["
    + _S
    + r"]*"
    + _NOT_SEP
    + r"+\.sh|tee["
    + _S
    + r"]+(-[a-z]+["
    + _S
    + r"]+)*"
    + _NOT_SEP
    + r"+\.sh|sed["
    + _S
    + r"]+-i[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh|shfmt["
    + _S
    + r"]+-w[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh|\b(cp|mv)["
    + _S
    + r"]+[^|&;]*["
    + _S
    + r"]"
    + _NOT_SEP
    + r"+\.sh"
)

# `$` IS IN THE CHARACTER CLASS so a variable expansion is RECOGNISED and then skipped. Without it, `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the tail of a variable name plus the suffix, a filename that appears nowhere. The guard cannot know what `$ver` expands to, so it must not guess.
SH_PATH = r"[A-Za-z0-9_.$/-]+\.sh"

# A python/perl heredoc can name its target in ways no redirect grep will see, so fall back to the old broad scan whenever the command opens one. Broad and noisy beats silent here: this is the door the pre-edit guard cannot cover.
PY_HEREDOC = r"write_text|open\(|<<[" + _S + r"]*.?(PY|EOPY|PYTHON)"

# A python write target appears in a target POSITION: assigned to a name, or passed to open()/Path(). A mention inside prose does not.
#
# THE `=` BRANCH NEEDS A SPACE BEFORE IT, and this is the third round of the
# same class. Measured 2026-08-28: a python heredoc's REPLACEMENT STRING held
# `ROUTE="./run.sh devbox exec -- $CMD"` -- valid bash SOURCE TEXT the script
# was writing INTO a hook file, never executed by the outer command -- and the
# bare `=` alternative scored it as a real python assignment because it looks
# identical in shape to one.
#
# The two are not identical in FORM, only in shape: this repo's own python is
# ruff-formatted (PEP8), so a real target assignment reads `p = 'x.sh'` with a
# space on both sides of `=`; a bash env-assignment payload being written out
# as DATA is valid bash, which forbids the space (`VAR=value`, no spaces,
# or it is a syntax error). Requiring a preceding space keeps every documented
# true positive (all authored `NAME = value` in this repo) while dropping the
# embedded-bash-as-data shape. `open(`/`Path(` are untouched -- neither of those idioms exists as bash syntax, so they carry no equivalent ambiguity.
# `p = "x.txt"` AND `p="x.txt"`: the spaced form alone missed the compact assignment every short heredoc uses, so its target read as unidentifiable and the broad scan blocked a payload that only MENTIONED a running script (./rdc.sh, 2026-09-24). The leading `[^=!<>]` keeps `==`, `!=`, `<=`, `>=` out, and it stays plain ERE so the bash oracle can carry the identical pattern.
ASSIGN_TARGET = (
    r"([^=!<>"
    + _S
    + r"]["
    + _S
    + r"]*=["
    + _S
    + r"]*|open\(|Path\()["
    + _S
    + r"]*[\"'][^\"']+\.[A-Za-z0-9]+"
)

# Targets come from TWO places, and looking in only one of them was the bug.
# A `cat > notes.txt <<'PY'`-shaped command names its target in the REDIRECT;
# the earlier cut only harvested redirect targets ending in .sh, so a redirect to any other extension contributed nothing and the command read as "target unidentifiable" while its target sat in plain sight. Measured 2026-08-27: writing two commit-message files was refused because their TEXT discussed write_text and named a running script.
REDIR_TARGET = NOT_ARROW + r">>?[" + _S + r']*"?[^|&;<' + _S + r'"]+\.[A-Za-z0-9]+'

ANY_TAIL = r"[A-Za-z0-9_.$/-]+\.[A-Za-z0-9]+$"

HOOK_CHAIN = r"\.claude/hooks/((pre-bash|pre-edit|pre-ask|post-bash)/|chain-head\.sh)"

META = r"([.\[\\*^$()+?{}|])"

MESSAGE = """BLOCKED: '%(base)s' is being executed right now, and this command writes to it.

  %(running)s

Bash reads a script LAZILY, by byte offset. Editing it now makes the running
interpreter resume at its old offset inside your new bytes, so it parses
mid-token and dies at an INNOCENT line -- while `bash -n` on the file stays
clean, which is what makes the failure so expensive to chase.

This is TRAPS.md, "Editing a shell script while a background job is RUNNING it".
Hit three times on 2026-08-26/27, twice on this very file. Its Edit-tool sibling
(block-edit-of-running-script.sh) covers the other door; this one exists because
covering only that door meant walking through this one within the hour.

Pick one:
  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on, so editing now costs you the result twice.
  2. Write a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first.
"""

# --------------------------------------------------------------------------- The fixture world ---------------------------------------------------------------------------
#
# ITS OWN WORLD, not the Edit-side guard's. The two could share one, and sharing would halve the processes; they do not, because the pgrep pattern is built
# from a BASENAME and two worlds holding the same basename would each report the
# other's process in the message. Distinct names keep each guard's output about its own world.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-bashwrite")
LIVE_SCRIPT = "%s/bash-side-suite.sh" % WORLD
SIBLING_SCRIPT = "%s/bash-side-chain-evaluator.sh" % WORLD
IDLE_SCRIPT = "%s/bash-side-nobody-runs-this.sh" % WORLD

# The second statement stops bash EXECing the final simple command in place,
# which would replace the shell with `sleep` and make `ps -o comm=` answer
# `sleep` -- failing the interpreter test below and silently emptying the world.
_BODY = "#!/usr/bin/env bash\nsleep 600\nexit 0\n"

_CHILDREN = []


def _reap():
    """Kill the world by PATH, not by the pids `Popen` handed back.

    MEASURED 2026-09-06: on this host `bash` is not `/usr/bin/bash`. A wrapper at ~/.local/share/rediacc/bin/bashcov-sup takes its place on PATH and re-execs the real interpreter as a CHILD, so `Popen(["bash", script])` yields a supervisor plus a grandchild, and killing the supervisor's process group left the grandchild alive and re-parented -- four such shells were still running
    after a clean pytest exit. Reaping by cmdline finds both, which is the same predicate `_kill_stale` uses on the way in.
    """
    _kill_stale((LIVE_SCRIPT, SIBLING_SCRIPT))


def _spawn(argv):
    return subprocess.Popen(
        ["bash", *argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# One session at a time in this world. TWO pytest runs of this suite were live on this machine at once on 2026-09-06 (a peer agent's and this one's), and they fought: each `_kill_stale` killed the other's shells, and the case that names a running script reported different pids on the two sides of one differential. The world has to sit at a FIXED path -- a static payload names it --
# so it cannot be made per-process; an advisory lock held for the life of the interpreter makes the second run wait instead.
_LOCK_FDS = []


def _hold_world_lock(world):
    """flock the world, or proceed after a bounded wait rather than hang.

    The descriptor is deliberately never closed: the lock is released by the kernel when this interpreter exits, which is exactly the lifetime the spawned shells have.
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
                # A five-minute wait means the other run is wedged, not busy. Proceeding is better than a suite that never finishes; the differential will say so loudly if the worlds then collide.
                break
            time.sleep(0.2)
            continue
        break
    _LOCK_FDS.append(fd)


def _kill_stale(paths):
    """Kill any leftover fixture shells from an EARLIER run before spawning.

    THIS IS NOT TIDINESS, it is the difference between a green differential and a red one. The world sits at a fixed path so the payloads can name it, and `atexit` does not fire when the interpreter is killed by a timeout -- so a previous run can leave its shells alive. `head -2` in the loop below then keeps the FIRST few matches, and a set that changes between the bash sweep and
    the Python sweep reports different pids for the same case. Observed exactly that: three processes for one script, two of them from runs that had already finished, and the two sides disagreed on which two they saw.

    Only processes running THESE fixture scripts are touched -- nothing else on the machine can match a path under this world -- and each was started with
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

    `Popen` returns before the exec completes and the bash sweep starts immediately afterwards; a case that ran in that gap would see one process on one side and two on the other, reported as a port defect.
    """
    import time  # noqa: PLC0415

    for _ in range(500):
        seen = sum(1 for c in _CHILDREN if (proc.cmdline(c.pid) or "").find(".sh") >= 0)
        if seen == len(_CHILDREN):
            return
        time.sleep(0.01)


def _bashwrite_world(_unused):
    """Two live `bash <script>` processes and one script nobody runs."""
    os.makedirs(WORLD, exist_ok=True)
    for path in (LIVE_SCRIPT, SIBLING_SCRIPT, IDLE_SCRIPT):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_BODY)
        # No chmod: the shells below are started as `bash <script>`, so the execute bit is never consulted, and setting one would only trip the permissive-mask lint for no behaviour.
    if not _CHILDREN:
        _hold_world_lock(WORLD)
        _kill_stale((LIVE_SCRIPT, SIBLING_SCRIPT))
        _CHILDREN.append(_spawn([LIVE_SCRIPT]))
        # An argument naming a chain directory: the only way to reach the hook-chain-sibling exclusion from a controlled world.
        _CHILDREN.append(_spawn([SIBLING_SCRIPT, ".claude/hooks/pre-bash/marker"]))
        atexit.register(_reap)
        _await_visible()
    return WORLD


FIXTURES = {"bashwrite-scripts": _bashwrite_world}

ENVS = [("running", {"REDIACC_BASHWRITE_WORLD": "{FIXTURE:bashwrite-scripts}"}, {})]

_PY = "python3 - <<'PY'\n%s\nPY"

EDGE_CASES = [
    ("a redirect onto a running script", "echo x > %s" % LIVE_SCRIPT),
    ("an append onto a running script", "echo x >> %s" % LIVE_SCRIPT),
    ("a copy onto a running script", "cp /tmp/new.sh %s" % LIVE_SCRIPT),
    # WRITE INTENT IS REQUIRED, not merely the filename.
    ("reading it is not writing it", "cat %s" % LIVE_SCRIPT),
    ("grepping it is not writing it", "grep -n foo %s" % LIVE_SCRIPT),
    ("running it is not writing it", "bash %s --help" % LIVE_SCRIPT),
    # ... and the live process is required too.
    ("a write to a script nobody runs", "echo x > %s" % IDLE_SCRIPT),
    ("a chain evaluator is not a running job", "echo x > %s" % SIBLING_SCRIPT),
    # The 2026-09-01 arrow, in the exact prose that produced it.
    (
        "an ASCII arrow is not a redirect",
        "echo 'check:ci-hook-worklist-suite -> %s'" % LIVE_SCRIPT,
    ),
    # The python-heredoc door this guard exists for, both ways round.
    (
        "a python heredoc naming its target",
        _PY % ('p = \'%s\'\nopen(p, "w").write("x")' % LIVE_SCRIPT),
    ),
    (
        "a python heredoc that merely MENTIONS a running script",
        _PY % ('p = "notes.py"\np.write_text("see %s")' % LIVE_SCRIPT),
    ),
    # A variable expansion is recognised and then skipped.
    ("a variable in the target", "echo x > $SP/mp-$ver.sh"),
]


def _sort_u(lines):
    """`sort -u` under LC_ALL=C: unique, ordered by byte."""
    return sorted(set(lines), key=lambda s: s.encode("utf-8", "surrogateescape"))


def _pipe(pattern, text):
    """One `grep -oE` stage, feeding the next one grep's own output shape."""
    return hookio._grep_out(hookio.grep_o(pattern, text))


def pattern_for(base):
    """`(^|[/[:space:]])[<first>]<escaped rest>`.

    BRACKET THE FIRST CHARACTER so this pgrep cannot match the shell running this hook, whose command line carries the path it was handed. That is the self-matching trap block-self-matching-pgrep exists for, and this is exactly where it would bite again.

    ANCHOR TO A PATH BOUNDARY. `pgrep -f` matches anywhere in a command line, so a bare basename matches any process whose command line merely CONTAINS it as a substring: `ver.sh` matched a running `wslServer.sh`, and the guard reported VS Code's server as the job about to be corrupted. The basename must start at the beginning, after a `/`, or after whitespace.

    ESCAPE THE DOTS. `.` is a regex wildcard and the basename was interpolated raw, so a target whose name is one letter plus `.sh` produced the pattern `[x].sh`, which matches any process containing `x<any>sh` -- and for the letter `b` that is **/bin/bash**, i.e. every bash process on the machine.

    Measured 2026-09-01: writing a TypeScript control whose FIXTURE filename was one letter plus the shell suffix was refused, naming `/bin/bash --init-file ...` as the job it would corrupt. No script of that name was running anywhere. Round six of this guard's over-matching, and the first that is not about command shape at all -- the previous five were all "a mention scored as a
    target"; this one is the TARGET name itself becoming a wildcard.
    """
    esc = re.sub(META, r"\\\1", base[1:])
    return r"(^|[/" + _S + r"])[" + base[:1] + r"]" + esc


def live_shells(pat, limit):
    """The pgrep loop, as its accumulated text.

    `pgrep -af` matches any process whose ARGUMENTS mention the name, which is the very trap this guard exists to prevent, wearing a different hat. Measured 2026-08-27: an edit to the hook suite was refused because a PEER session's `claude -p` carried a long prompt that happened to contain that filename. No interpreter was executing the script at all, and the refusal was
    unarguable.

    A process is RUNNING the script only if an interpreter is executing it. So require the matching process to BE a shell, and the name to sit in the first few argv slots where a script argument lives, rather than buried in a prose payload.
    """
    try:
        pids = proc.pgrep_full(pat)
    except (proc.ProcError, re.error):
        pids = []
    running = ""
    for rpid in pids:
        if not proc.is_shell(rpid):
            continue
        rargs = proc.cmdline_tr(rpid)
        if rargs is None:
            rargs = ""
        first4 = " ".join(rargs.split(" ")[:4])
        if not hookio.grep_q(pat, first4):
            continue
        if hookio.grep_q(HOOK_CHAIN, rargs):
            continue
        running += "%d %s\n" % (rpid, rargs[:80])
    kept = running.split("\n")[:limit] if running != "" else []
    return hookio._command_substitution("\n".join(kept))


def _targets(cmd):
    """Every .sh path this command actually writes to, `sort -u` order."""
    # Which .sh files does this command name at all?
    targets = "\n".join(_sort_u(hookio.grep_o(SH_PATH, _pipe(TARGET_SPAN, cmd))))

    if not hookio.grep_q(PY_HEREDOC, cmd):
        return targets

    # PRECISE FIRST, BROAD ONLY IF THAT FINDS NOTHING.
    #
    # The old line took EVERY .sh token in the command. That is correct for a python heredoc naming its target, and badly wrong for one whose payload merely MENTIONS a script -- which is what documentation, a hook message, or a commit body routinely does. Measured 2026-08-27: patching this very guard's sibling was refused twice because the replacement TEXT contained `./run.sh
    # devbox remove` while a peer ran that script. No interpreter was executing the file being written, and the same false-positive class is already recorded twice in this file's own comments.
    #
    # ASK "COULD I IDENTIFY THE TARGET AT ALL", not "did I find a .sh". The first cut of this asked the second question and fell back to the broad scan whenever no .sh sat in a target position -- which is precisely the shape of the false positive (real target a .py, payload mentioning a script), so the narrowing changed nothing. Control 1 caught it.
    anytarget = "\n".join(
        _sort_u(
            hookio.grep_o(ANY_TAIL, _pipe(ASSIGN_TARGET, cmd))
            + hookio.grep_o(ANY_TAIL, _pipe(REDIR_TARGET, cmd))
        )
    )
    precise = "\n".join(_sort_u(hookio.grep_lines(r"\.sh$", hookio._printf_line(anytarget))))
    if anytarget != "":
        # Targets were identifiable. If none is a shell script, this command writes none, however many it happens to NAME in its payload.
        if precise != "":
            targets = "\n".join(_sort_u(("%s\n%s" % (targets, precise)).split("\n")))
    else:
        # Nothing looked like a target, so keep the old broad-and-noisy scan rather than going silent: a missed corruption costs more than a false positive, which is why the broad form was chosen originally.
        broad = hookio._command_substitution(_pipe(SH_PATH, cmd))
        targets = "\n".join(_sort_u(("%s\n%s" % (targets, broad)).split("\n")))
    return targets


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if not hookio.grep_q(WRITE_INTENT, cmd):
        return hookio.ALLOW

    for cand in _targets(cmd).split():
        if hookio.case_glob(cand, "*$*"):
            continue
        base = cand.rsplit("/", 1)[-1]
        running = live_shells(pattern_for(base), 2)
        if running == "":
            continue
        body = hookio._command_substitution(
            hookio.sed_sub(r"^", "    ", hookio._printf_line(running))
        )
        ev.warn_raw(MESSAGE % {"base": base, "running": body})
        return hookio.DENY
    return hookio.ALLOW

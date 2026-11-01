"""The Bash half of block-edit-of-running-script.

WHY A SECOND FILE. The pre-EDIT guard only sees the Edit/Write tools. Within an hour of shipping it I walked into the same trap through Bash instead -- a `python3 - <<PY ... p.write_text(...) PY` rewriting test-hooks.sh while FOUR copies of it were executing. The guard did not fire because it never saw the call. A guard that covers one of two doors is a guard you will walk around
without noticing, which is exactly what happened.

THE MECHANISM, since the error never points at it: bash reads a script LAZILY, by byte offset. Rewrite it mid-run and the interpreter resumes at its old offset inside the new bytes and starts parsing mid-token. It dies naming an INNOCENT line while `bash -n` on that same file stays clean. Documented at docs/agent-reference/TRAPS.md, and hit three times on 2026-08-26/27.

HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and excluding them is not a loophole -- it is the difference between this guard working and this guard making a whole directory uneditable. Every pre-bash guard executes on EVERY Bash call, including the one carrying your edit. So while you edit block-binary-deploy.sh, that guard is running, as a sibling in the chain evaluating that very
edit. This fired on exactly that on 2026-08-27, and the block is PERMANENT: there is no moment when a pre-bash guard is not running during a Bash call, so no amount of waiting clears it. It cost four blocked commands before the cause was visible, one of them the fix itself.

The exclusion costs close to nothing. A chain evaluator lives for milliseconds and is re-read from scratch on the next call, so the lazy-read corruption below needs a window that does not exist here. What this guard is actually for -- a suite, a build, a background job running for minutes -- is untouched, test-hooks.sh included: that runs from the hooks ROOT, not a chain directory,
so it still matches and still blocks.

WRITE INTENT IS REQUIRED, not merely the filename. Every second command in this repo mentions a .sh path -- running it, grepping it, checking its processes. Blocking on the name alone would be the over-matching that gets a guard switched off, so this needs a write operator AND a live process.

A WRITE IS SOMETHING THAT RUNS, NOT TEXT THAT SPELLS ONE (worklist #0c331972). The write patterns below were matched over the RAW command, so `echo 'echo x > <running>.sh'` -- a sentence quoting a redirect -- was refused as a write. The guard now asks the shell's own walk: the redirects bash performs (`shellscan.write_targets`), the write verbs it runs (`tee`, `sed -i`, `cp`/`mv` onto a destination, `shfmt -w`, `truncate`, `dd of=`, each read off its argv by `_verb_targets`, behind `sudo`, `xargs`, `sh -c` or `find -exec`), and the program texts it hands an interpreter (`block_worktree_add.interpreter_programs`: `python3 -c`, `python3 - <<PY`, `node -e`, `perl -e`, a here-string or a piped `cat`). Only a program text is still read with the patterns, because a python write names its target in ways no shell walk sees. An `echo` or a commit message quoting any of it is data and passes.

`pattern_for` AND THE PGREP LOOP NOW LIVE IN `rediacc_hooks.runningscript`, shared with the Edit-tool sibling (PLAN-retire-bash-oracles A3: "unifying is a P6 change, once there is no twin left to diverge from" -- this is that change). Until then each guard carried its own copy of the same twenty lines, because the two BASH originals duplicated them too and a port whose job was fidelity
did not get to unify what its twin kept apart; that duplication is exactly what produced the sibling drift their comments recorded (the path anchor reached the Edit-side guard on 2026-08-30, three days after this one got it on 2026-08-27).

PORT NOTE ON `for cand in $TARGETS`. That is an UNQUOTED expansion, so bash splits on IFS -- dropping empty fields, which is why an empty first line from `printf '%s\\n%s'` costs nothing -- and then GLOBS each word against the filesystem. The globbing has never mattered here (a `.sh` path holding a `*` or a `?` would already have been skipped by the `$` test or failed to match a
process) and is not reproduced; the splitting is, because the empty-field case happens on every command that reaches the fallback with no redirect targets.

PORT NOTE ON `sort -u`. Under `LC_ALL=C` sort orders by BYTE, so the key below
is the UTF-8 encoding rather than Python's default codepoint comparison. The two agree on every ASCII path and can differ on anything else, and the order is observable: it decides which of several targets is reported first.
"""

import atexit
import os
import signal
import subprocess
import tempfile

from rediacc_hooks import hookio, proc, runningscript, shellscan
from rediacc_hooks.guards import block_worktree_add as WT

CHAIN = "pre-bash"
ORDER = 15

# AN ASCII ARROW IS NOT A REDIRECT, and this is the FIFTH round of the same
# class. Since #0c331972 the patterns read only interpreter program texts, so the witness is a python program printing an arrow (EDGE_CASES); a quoted shell sentence never reaches them at all. Measured 2026-09-01: writing a plain markdown file was refused because
# its PROSE contained `check:ci-hook-worklist-suite -> .claude/hooks/stop/test-worklist-v5.sh`. The `->` scored as a redirect and the path after it as the target, so a document describing a script was treated as a command overwriting it. Widening the class back to "any character" restores that block exactly.
DEFECT = ('NOT_ARROW = r"(^|[^->])"', 'NOT_ARROW = r"(^|[^ZZ])"')

# A real redirect's `>` is preceded by whitespace, start-of-string, or a digit (`2>`). Never by `-`. Requiring that keeps every true positive and drops the arrow. One constant, used by BOTH the intent test and the target harvest, because the two disagreeing about what a redirect is was how the class kept coming back.
#
# RULE T DECISION (PLAN-retire-bash-oracles A4, A0 L14), 2026-09-24: THE ARROW RULE STAYS FOR THE RAW-TEXT PATTERNS, AND IS NO LONGER THE WHOLE ANSWER. The premise above is false for bash: an UNQUOTED `x->f.sh` is the word `x-` followed by a real `>` opening `f.sh` (`echo x->/dev/null` prints nothing). What made the arrow worth excluding was prose, and prose that names an arrow is QUOTED, which a regex over the raw command cannot tell from a real redirect. The lexer can, so `shellscan.write_targets` now supplies the redirects bash actually performs (quote-aware, so the 2026-09-01 arrow inside `echo '... -> x.sh'` is still no target) and `run` unions them with the regex harvest. `NOT_ARROW` keeps doing the one job it is still right for: stopping a quoted or heredoc'd arrow from scoring in the raw-text patterns. The same union closes `>|`, which truncates even under noclobber and which `_NOT_SEP`'s `|` exclusion made invisible to every pattern here.
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

# A copy or move inside a program names its destination as a call ARGUMENT, which `ASSIGN_TARGET` does not see, so such a program takes the precise-then-broad branch too.
PY_COPY = r"shutil\.(copy|move)"

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
# NO WHITESPACE INSIDE THE QUOTED TARGET (2026-09-24, #a655c5f5): `grep -n "source\\|PATS=" a.sh; ls lib/b.sh` read the CLOSING quote after `PATS=` as an opening one, and `[^"']+` then ran across `; ls` to the next `.sh`, refusing a command that only listed a running script. A real target literal holds no whitespace.
# THE QUOTE MUST CLOSE RIGHT AFTER THE EXTENSION (2026-09-24, found by PLAN-retire-bash-oracles A4's full hook-suite run): with the whitespace ban alone, `ROUTE=".<live>.sh devbox exec"` still scored `<live>.sh` as a target, because nothing required the quoted span to END there, and the round-3 control in test_hooks_procs.py ("a bash-shaped assignment MENTION inside replacement text") went red at 0868e3a53. A real target literal is the WHOLE quoted string, so a lookahead now demands its closing quote.
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
    + r"]*[\"'][^\"'"
    + _S
    + r"]+\.[A-Za-z0-9]+(?=[\"'])"
)

# Targets come from TWO places, and looking in only one of them was the bug.
# A `cat > notes.txt <<'PY'`-shaped command names its target in the REDIRECT;
# the earlier cut only harvested redirect targets ending in .sh, so a redirect to any other extension contributed nothing and the command read as "target unidentifiable" while its target sat in plain sight. Measured 2026-08-27: writing two commit-message files was refused because their TEXT discussed write_text and named a running script.
REDIR_TARGET = NOT_ARROW + r">>?[" + _S + r']*"?[^|&;<' + _S + r'"]+\.[A-Za-z0-9]+'

ANY_TAIL = r"[A-Za-z0-9_.$/-]+\.[A-Za-z0-9]+$"

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
    import fcntl
    import time

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


def _sleep_children(parent):
    """The pids of `sleep` processes whose parent is `parent`, read from /proc; empty where /proc has no such file."""
    found = []
    for pid in proc.pids():
        try:
            with open("/proc/%s/stat" % pid, encoding="utf-8") as handle:
                # The fields after the parenthesised comm, which may itself hold spaces: state, then ppid.
                ppid = int(handle.read().rpartition(")")[2].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        if ppid == parent and proc.comm(pid) == "sleep":
            found.append(pid)
    return found


def _kill_stale(paths):
    """Kill any leftover fixture shells from an EARLIER run before spawning.

    THIS IS NOT TIDINESS, it is the difference between a green differential and a red one. The world sits at a fixed path so the payloads can name it, and `atexit` does not fire when the interpreter is killed by a timeout -- so a previous run can leave its shells alive. `head -2` in the loop below then keeps the FIRST few matches, and a set that changes between the bash sweep and
    the Python sweep reports different pids for the same case. Observed exactly that: three processes for one script, two of them from runs that had already finished, and the two sides disagreed on which two they saw.

    Only processes running THESE fixture scripts are touched -- nothing else on the machine can match a path under this world -- and each was started with
    `start_new_session=True`, so it leads its own group and killing the group
    takes its `sleep` child with it.
    """
    import time

    for _ in range(500):
        stale = [p for p in proc.pids() if any(t in (proc.cmdline(p) or "") for t in paths)]
        if not stale:
            return
        # The children are read before anything dies. The bashcov-sup wrapper matches too and comes first in `stale`; killing it takes its script with it, and the script's child is then reparented, out of reach (measured 2026-11-01, about three orphans per run). Only a script's own child goes: a group the script does not lead may hold an unrelated process, since anything naming a fixture path matches `stale`.
        children = [c for pid in stale for c in _sleep_children(pid)]
        for pid in children:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                continue
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
    import time

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
    # Rule T, A0 L14: an UNQUOTED arrow is a real redirect, and `>|` truncates even under noclobber. The quoted arrow above stays prose.
    ("an unquoted arrow is a redirect onto a running script", "echo x->%s" % LIVE_SCRIPT),
    ("a noclobber-proof redirect onto a running script", "echo x >| %s" % LIVE_SCRIPT),
    ("a double-quoted arrow is still prose", 'echo "x->%s"' % LIVE_SCRIPT),
    # 2026-09-24, #a655c5f5: a closing quote after `PATS=` read as an opening one ran across `; ls` to a running script.
    (
        "a closing quote does not open a target that spans a listing",
        _PY % "p = 'other.sh'\nopen(p, 'w').write('x')"
        + '\ngrep -n "source\\|PATS=" other.sh; ls %s' % LIVE_SCRIPT,
    ),
    # #0c331972: a quoted write is a sentence, and every write that runs is still one.
    ("an echo quoting a redirect onto a running script", "echo 'echo x > %s'" % LIVE_SCRIPT),
    ("a commit message quoting a copy onto it", "git commit -m 'cp a.sh %s' -- a.md" % LIVE_SCRIPT),
    (
        "a python program printing an arrow names no target",
        "python3 -c \"print('see -> %s')\"" % LIVE_SCRIPT,
    ),
    ("tee onto a running script", "echo x | tee -a %s" % LIVE_SCRIPT),
    ("sudo tee onto a running script", "echo x | sudo tee %s" % LIVE_SCRIPT),
    ("sed -i on a running script", "sed -i 's/a/b/' %s" % LIVE_SCRIPT),
    ("a copy into the running script's directory", "cp /tmp/x/bash-side-suite.sh %s/" % WORLD),
    ("copying the running script AWAY is a read", "cp %s /tmp/backup.sh" % LIVE_SCRIPT),
    # Review 0bbd6471.5: a destination without `.sh` is a FILE unless `-t`, a trailing slash or the filesystem makes it a directory.
    (
        "copying it to a file with no suffix is a read",
        "cp %s /tmp/rediacc-bashwrite-backup" % LIVE_SCRIPT,
    ),
    ("copying a script into its directory by -t", "cp -t %s /tmp/x/bash-side-suite.sh" % WORLD),
    ("copying a script into its existing directory", "cp /tmp/x/bash-side-suite.sh %s" % WORLD),
    # Review 88362611.1: the destination as bash expands it.
    ("a copy onto a variable set to the running script", "F=%s; cp /tmp/x.sh $F" % LIVE_SCRIPT),
    # Review 126f2a9f.1: bash expands `~` and braces in an echo word before xargs reads it.
    (
        "a fed tilde word is read as unknown, not as a literal path",
        "echo ~/x.sh | xargs cp /tmp/y.sh",
    ),
    ("a fed brace word is read as unknown", "echo {/tmp/z,%s} | xargs cp /tmp/y.sh" % LIVE_SCRIPT),
    # Review 0bbd6471.4: xargs appends its feed, so a fed running script is the operand or the destination.
    ("xargs feeds the running script to cp", "echo %s | xargs cp /tmp/x.sh" % LIVE_SCRIPT),
    ("xargs feeds the running script to sed -i", "echo %s | xargs sed -i s/a/b/" % LIVE_SCRIPT),
    # #6378e10e: perl edits in place too.
    ("perl -pi on a running script", "perl -pi -e 's/a/b/' %s" % LIVE_SCRIPT),
    ("perl -i -pe on a running script", "perl -i -pe 's/a/b/' %s" % LIVE_SCRIPT),
    ("perl -i.bak on a running script", "perl -i.bak -pe 's/a/b/' %s" % LIVE_SCRIPT),
    ("perl -pe without -i only prints", "perl -pe 's/a/b/' %s" % LIVE_SCRIPT),
    ("gsed -i on a running script", "gsed -i 's/a/b/' %s" % LIVE_SCRIPT),
    ("xargs feeds the running script to tee", "echo %s | xargs tee" % LIVE_SCRIPT),
    ("xargs feeds the running script to truncate", "echo %s | xargs truncate -s 0" % LIVE_SCRIPT),
    (
        "xargs feeds a script to cp -t its directory",
        "echo /tmp/x/bash-side-suite.sh | xargs cp -t %s" % WORLD,
    ),
    ("a redirect inside sh -c", "sh -c 'echo x > %s'" % LIVE_SCRIPT),
    ("a python -c write", "python3 -c \"open('%s', 'w').write('x')\"" % LIVE_SCRIPT),
    ("a python here-string write", "python3 <<< \"open('%s', 'w').write('x')\"" % LIVE_SCRIPT),
    (
        "a heredoc piped to python",
        "cat <<'PY' | python3 -\nopen('%s', 'w').write('x')\nPY" % LIVE_SCRIPT,
    ),
    (
        "a data heredoc naming a write is data",
        "cat > /tmp/notes.md <<'EOF'\nopen('%s', 'w')\nEOF" % LIVE_SCRIPT,
    ),
    ("truncate a running script", "truncate -s 0 %s" % LIVE_SCRIPT),
    ("dd onto a running script", "dd if=/dev/null of=%s" % LIVE_SCRIPT),
]


def _sort_u(lines):
    """`sort -u` under LC_ALL=C: unique, ordered by byte."""
    return sorted(set(lines), key=lambda s: s.encode("utf-8", "surrogateescape"))


def _pipe(pattern, text):
    """One `grep -oE` stage, feeding the next one grep's own output shape."""
    return hookio._grep_out(hookio.grep_o(pattern, text))


def _targets(cmd):
    """Every .sh path an interpreter program text writes to, `sort -u` order. Called only with a program `interpreter_programs` found, never with the command line itself."""
    # Which .sh files does this program name at all?
    targets = "\n".join(_sort_u(hookio.grep_o(SH_PATH, _pipe(TARGET_SPAN, cmd))))

    if not hookio.grep_q(PY_HEREDOC, cmd) and not hookio.grep_q(PY_COPY, cmd):
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


def _operands(run_):
    """A write verb's operands: its own non-option words, then what xargs appends from its feed (`echo a.sh | xargs sed -i s/x/y/` edits `a.sh`). What a producer prints is not computed, so every fed word counts, the direction this guard fails safe in (review 0bbd6471.4)."""
    words = [a for a in run_.argv if not (a.startswith("-") and len(a) > 1)]
    if run_.feed and "xargs" in run_.via:
        words += run_.feed.split()
    return words


def _verb_targets(run_, cwd):
    """The `.sh` files one run's write verb writes: `tee`, `truncate`, `shfmt -w` and `sed -i` write their operands, `cp`/`mv` where `shellscan.copy_landings` puts the copy, `dd` its `of=`. Every arm reads the xargs feed as `_operands` does. Anything else writes nothing here."""
    base = shellscan._base(run_.name)
    args = list(run_.argv)
    if base in ("tee", "truncate"):
        found = _operands(run_)
    elif base == "shfmt":
        found = _operands(run_) if any(a in ("-w", "--write") for a in args) else []
    elif shellscan.in_place_edit(run_) is not None:
        # EVERY IN-PLACE EDITOR, by its own option parse (#6378e10e): sed, gsed and `perl -i`/`-pi` rewrite the files they name, and `perl -pi -e ... <running>.sh` was allowed while only sed was asked. The files are `in_place_edit`'s (an attached `-e` script is not a file, review 3f53e99e.2), plus what xargs appends.
        edit = shellscan.in_place_edit(run_)
        fed = run_.feed.split() if run_.feed and "xargs" in run_.via else []
        found = [*edit[1], *fed]
    elif base in ("cp", "mv"):
        found = [path for path, _into in shellscan.copy_landings(run_, cwd, ("cp", "mv"))]
    elif base == "dd":
        found = [a[3:] for a in args if a.startswith("of=")]
    else:
        found = []
    return [t for t in found if t.endswith(".sh")]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    # The redirects bash really performs onto a `.sh` (see the Rule T note at NOT_ARROW), then the write verbs it runs, then what each interpreter program writes.
    cands = [t for t in shellscan.write_targets(cmd) if t.endswith(".sh")]
    cwd = ev.field("cwd") or str(hookio.repo_root())
    for run_ in shellscan.every_run(cmd):
        cands += _verb_targets(run_, cwd)
    for _family, code in WT.interpreter_programs(cmd):
        if hookio.grep_q(WRITE_INTENT, code):
            cands += _targets(code).split()
    for cand in dict.fromkeys(cands):
        if hookio.case_glob(cand, "*$*"):
            continue
        base = cand.rsplit("/", 1)[-1]
        running = runningscript.live_shells(runningscript.pattern_for(base), 2, cand, cwd)
        if running == "":
            continue
        body = hookio._command_substitution(
            hookio.sed_sub(r"^", "    ", hookio._printf_line(running))
        )
        ev.warn_raw(MESSAGE % {"base": base, "running": body})
        return hookio.DENY
    return hookio.ALLOW

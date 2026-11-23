"""The test tables of `block_bash_write_to_running_script`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import atexit
import fcntl
import os
import signal
import subprocess
import tempfile
import time

from rediacc_hooks import proc

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
    `start_new_session=True`. A process that leads its group loses the group, and any other loses itself and its direct `sleep` children, read before anything dies.
    """

    for _ in range(500):
        stale = [p for p in proc.pids() if any(t in (proc.cmdline(p) or "") for t in paths)]
        if not stale:
            return
        # The children are read before anything dies. The bashcov-sup wrapper matches too and comes first in `stale`; killing it takes its script with it, and the script's child is then reparented, out of reach (measured 2026-11-01, about three orphans per run). Only a script's own child goes: a group the script does not lead may hold an unrelated process, since anything naming a fixture path matches `stale`.
        children = [c for pid in stale for c in proc.children_named(pid, "sleep")]
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

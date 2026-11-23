"""The test tables of `block_bash_write_to_running_script`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import atexit
import fcntl
import os
import signal
import subprocess
import tempfile
import time

from rediacc_hooks import proc
from rediacc_hooks.tests.fixtures.guards.loader import load_table

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


_CHILDREN: list = []


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
_LOCK_FDS: list = []


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


ENVS: list = [("running", {"REDIACC_BASHWRITE_WORLD": "{FIXTURE:bashwrite-scripts}"}, {})]


_PY = "python3 - <<'PY'\n%s\nPY"


EDGE_CASES = load_table("block_bash_write_to_running_script", "EDGE_CASES")

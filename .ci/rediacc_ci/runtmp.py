"""A per-run temp directory that a LATER run removes when this one is killed.

WHY NOT `atexit` OR `try/finally` ALONE. Both run only when the interpreter gets to unwind. A suite killed on its timeout (SIGKILL, or SIGTERM with no handler) unwinds nothing, so every `mkdtemp` it made stays in /tmp. On 2026-09-24 /tmp here (a tmpfs capped at 1,048,576 inodes) hit 100% that way and Bash could no longer write its own output; the worst single leaker held 538,000 inodes in 81 orphaned PATH shims.

THE SHAPE. `run_dir(prefix)` makes ONE directory per process, named `<prefix><pid>-n<pidns>-<random>`, registers it for removal at exit, and first calls `sweep_dead(prefix)`, which removes every sibling with the same prefix whose pid is no longer alive. The atexit handler covers the normal exit; the sweep covers the killed one, on the next run of the same suite. Everything a suite creates goes UNDER that directory (`tempfile.mkdtemp(dir=RUN_TMP)`), so one sweep reclaims all of it.

WHICH DIRECTION IS EXPENSIVE. A wrong removal deletes a LIVE run's fixture out from under it, which reads as a flaky suite with nothing pointing here. So the sweep is conservative on purpose:
  - a pid that cannot be parsed is left alone;
  - a pid that is alive is left alone, even when it has been reused by an unrelated process (the directory then waits for a later sweep);
  - a directory stamped in a DIFFERENT pid namespace is left alone, because a pid from a container sharing /tmp would look dead from here while its run is live;
  - an unreaped zombie counts as alive (`os.kill(pid, 0)` succeeds on it), so a caller that kills a child must `wait()` it before sweeping.

`.claude` suites LOAD THIS FILE BY PATH (`importlib.util.spec_from_file_location`), not through a `sys.path` hop: .ci/rediacc_ci/tests/test_canonical_sys_path_hop.py freezes hops in a shrink-only baseline, and a by-file load needs none. That is why this module imports nothing outside the standard library. There is deliberately one copy.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import tempfile

__all__ = ["run_dir", "stamp", "sweep_dead"]

_PREFIX_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*-$")


def _pid_namespace() -> str:
    """The pid namespace's inode, or "0" where /proc does not expose one (macOS)."""
    try:
        return str(os.stat("/proc/self/ns/pid").st_ino)
    except OSError:
        return "0"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Someone else's live process: alive, and certainly not ours to sweep.
        return True
    except OverflowError:
        return False
    return True


def _check_prefix(prefix: str) -> None:
    # A prefix must END in a dash so the pid that follows it is delimited, and must not be empty, or one suite's sweep would parse another suite's directory names.
    if not _PREFIX_SHAPE.match(prefix):
        raise ValueError(
            "runtmp prefix %r must be non-empty, start with a letter and end with '-'" % prefix
        )


def stamp(prefix: str, pid: int | None = None) -> str:
    """The name prefix a run with `pid` gets: `<prefix><pid>-n<pidns>-`."""
    _check_prefix(prefix)
    return "%s%d-n%s-" % (prefix, os.getpid() if pid is None else pid, _pid_namespace())


def sweep_dead(prefix: str, base: str | None = None) -> list[str]:
    """Remove every `<prefix><pid>-n<ns>-*` directory in `base` whose pid is dead in THIS namespace.

    Returns the removed paths, so a caller or a test can see what the sweep did rather than trust it.
    """
    _check_prefix(prefix)
    base = base or tempfile.gettempdir()
    shape = re.compile(r"^%s(\d+)-n(\d+)-" % re.escape(prefix))
    here = _pid_namespace()
    removed: list[str] = []
    try:
        names = os.listdir(base)
    except OSError:
        return removed
    for name in names:
        m = shape.match(name)
        if not m or m.group(2) != here:
            continue
        pid = int(m.group(1))
        if pid == os.getpid() or _alive(pid):
            continue
        path = os.path.join(base, name)
        if os.path.islink(path) or not os.path.isdir(path):
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.lexists(path):
            removed.append(path)
    return removed


def run_dir(prefix: str, base: str | None = None) -> str:
    """Sweep dead runs of `prefix`, then create and return this process's run directory.

    Removed at interpreter exit; removed by the next run's sweep when the exit never happens.
    """
    sweep_dead(prefix, base)
    path = tempfile.mkdtemp(prefix=stamp(prefix), dir=base)
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path

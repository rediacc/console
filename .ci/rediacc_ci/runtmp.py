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
import contextlib
import os
import re
import shutil
import stat
import tempfile

__all__ = [
    "SHELL_MKTEMP",
    "SHELL_PREFIX",
    "remove_tree",
    "run_dir",
    "shared",
    "shell_mktemp",
    "stamp",
    "sweep_dead",
    "sweep_dead_basetemps",
]

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


def _make_writable(_func: object, path: str, _exc: BaseException) -> None:
    """`rmtree`'s `onexc`: a test that chmods a file or directory read-only leaves a tree plain `rmtree` cannot finish. Owner write+execute on the entry and on its parent, then one retry; anything still refused (another user's file) is left, never raised."""
    for target in (os.path.dirname(path), path):
        try:
            mode = os.lstat(target).st_mode
            if not stat.S_ISLNK(mode):
                os.chmod(target, stat.S_IMODE(mode) | stat.S_IRWXU)
        except OSError:
            pass
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            os.rmdir(path)
        else:
            os.unlink(path)
    except OSError:
        pass


def remove_tree(path: str) -> None:
    """`shutil.rmtree` that also clears entries a test made read-only. Never raises."""
    with contextlib.suppress(OSError):
        shutil.rmtree(path, onexc=_make_writable)


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
        remove_tree(path)
        if not os.path.lexists(path):
            removed.append(path)
    return removed


#: The one prefix every BASH script shares, because a bash script cannot import this module and a sweep keyed per script would need one sweeper per script.
SHELL_PREFIX = "rediacc-sh-"

#: THE BASH SPELLING, verbatim; `%s` is the script's tag (`[a-z0-9-]+`). It is a CONTRACT rather than a sourced helper for two measured reasons: `check_language_policy.py` refuses a NEW bash file under `.ci` and `.claude`, and `.ci/scripts/lib/common.sh`, which most scripts source, is a twin kept byte-stable for W7P5-c. So each script carries this one line, `test_runtmp.py` runs it under a real bash to prove the sweep below removes what it makes, and a tree scan there fails any `rediacc-sh-` use that drifts from it.
#: `stat -Lc %i /proc/self/ns/pid` is the pid namespace `_pid_namespace` reads, and falls back to `0` exactly where that does (no /proc: macOS).
SHELL_MKTEMP = 'mktemp -d "${TMPDIR:-/tmp}/rediacc-sh-$$-n$(stat -Lc %%i /proc/self/ns/pid 2>/dev/null || echo 0)-%s-XXXXXXXX"'


def shell_mktemp(tag: str) -> str:
    """`SHELL_MKTEMP` for one script's tag."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", tag):
        raise ValueError("runtmp shell tag %r must be lowercase words joined by '-'" % tag)
    return SHELL_MKTEMP % tag


def run_dir(prefix: str, base: str | None = None) -> str:
    """Sweep dead runs of `prefix`, then create and return this process's run directory.

    Removed at interpreter exit; removed by the next run's sweep when the exit never happens. Every call ALSO sweeps `SHELL_PREFIX`, which is how a killed bash script's directory gets reclaimed: bash has no sweeper of its own, and this is called on every suite and gate start.
    """
    sweep_dead(prefix, base)
    sweep_dead(SHELL_PREFIX, base)
    path = tempfile.mkdtemp(prefix=stamp(prefix), dir=base)
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path


_SHARED: dict[tuple[str, str | None], str] = {}


def shared(prefix: str, base: str | None = None) -> str:
    """`run_dir(prefix)`, made once per process and handed back on every later call.

    For a module that makes a temp directory per call (a case, a side, a selftest): `tempfile.mkdtemp(dir=runtmp.shared("x-"))` keeps each call's own directory and its own cleanup, and puts all of them under ONE run directory the next run can sweep. Made again if something removed it.
    """
    key = (prefix, base)
    path = _SHARED.get(key)
    if path is None or not os.path.isdir(path):
        path = _SHARED[key] = run_dir(prefix, base)
    return path


_BASETEMP = re.compile(r"^pytest-[0-9]+$")


def sweep_dead_basetemps(root: str) -> list[str]:
    """Remove every `pytest-N` under `root` (a `pytest-of-<user>` directory) whose `.lock` names a dead pid.

    WHY THIS EXISTS. pytest writes its pid into `<basetemp>/.lock` and removes the lock at exit; its own cleanup then deletes a numbered basetemp only once that lock is older than `LOCK_TIMEOUT`, three DAYS (`_pytest/pathlib.py`). So every killed or timed-out run, xdist workers and all, keeps its whole tree for three days: on 2026-09-24 ten of them held most of /tmp's 1,048,576 inodes. A lock whose pid is dead belongs to a run that can never finish, so the tree is reclaimed now, and pytest's own retention still governs every run that exited.

    What is LEFT: a basetemp with no lock (it exited, so pytest's retention owns it), an unreadable or non-numeric lock, and a live pid. pytest records the pid without its namespace, so unlike `sweep_dead` this cannot tell a live run in another pid namespace from a dead one here; that is safe only because `pytest-of-<user>` sits on a /tmp no container shares with this host.
    """
    removed: list[str] = []
    try:
        names = os.listdir(root)
    except OSError:
        return removed
    for name in names:
        if not _BASETEMP.match(name):
            continue
        path = os.path.join(root, name)
        try:
            with open(os.path.join(path, ".lock"), encoding="ascii") as fh:
                text = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            continue
        if not text.isdigit():
            continue
        pid = int(text)
        if pid == os.getpid() or _alive(pid):
            continue
        remove_tree(path)
        if not os.path.lexists(path):
            removed.append(path)
    return removed

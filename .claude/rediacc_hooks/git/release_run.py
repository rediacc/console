"""The release-run record: the one way a local release (`python3 -m rediacc_ci.release.local`, box W2-B of agent/plans/PLAN-local-release.md) gets its own pushes past the git-level `pre-push` refusal of `main` (box W1-D).

THE RECORD. The entry writes `.ci/cache/release/run-<id>.json` of the console root through `write_release_run` below, and exports `REDIACC_RELEASE_RUN=<that path>` to the git commands it runs:

    {"pid": <the entry's pid>, "pid_start": <field 22 of /proc/<pid>/stat>, "cmdline": [<argv>],
     "tree": <console HEAD^{tree}>, "version": "<V>", "channel": "edge|stable",
     "pushes": [{"toplevel": "<abs repo path>", "remote": "<name>", "remote_ref": "refs/heads/main", "oid": "<sha>"}]}

`remote` is the first argument git hands `pre-push`: the remote's name, or the URL itself for a push to a bare URL.

THE ENTRY INVOCATION, the one shape `entry_refusal` admits, so the module that ran can only be the console's tracked file:

    PYTHONPATH=<console>/.ci PYTHONPYCACHEPREFIX=/dev/null python3 -P -s -m rediacc_ci.release.local ...

  - `-P` (or PYTHONSAFEPATH): `python3 -m` otherwise puts the cwd first on sys.path, so a planted `rediacc_ci/release/local.py` in any directory would run as the entry (review finding 875b0384.1). With it, the first PYTHONPATH entry, `<console>/.ci` by its real path, is where `rediacc_ci` resolves.
  - `-s` (or PYTHONNOUSERSITE): the user site directory runs any `.pth` file in it at start-up, before the module.
  - PYTHONPYCACHEPREFIX=/dev/null: no `__pycache__` file is ever read. A timestamp `.pyc` is trusted on its header alone (mtime and size), so a planted one runs other code under a pristine source; `/dev/null/...` can never exist.
  - nothing between the interpreter and `-m` but those flags (`-B`, `-u` too): `python3 evil.py -m rediacc_ci.release.local` and `python3 -c <code> -m ...` carry the same two words and run other code.
  - no other PYTHON* variable (each one listed in the refusal), and no LD_* variable (LD_PRELOAD runs native code inside the interpreter).

THE PACKAGE ON DISK, read when the hook runs: `.ci/rediacc_ci/__init__.py`, `.ci/rediacc_ci/release/__init__.py` and `.ci/rediacc_ci/release/local.py` are tracked regular files; nothing under `.ci/rediacc_ci` differs from HEAD, is untracked or is ignored, `__pycache__` aside (an untracked `tag/` package shadows a tracked `tag.py`, an ignored `.so` shadows a source); and nothing there changed less than `SETTLE_S` before the entry started, so a file swapped for the start and restored afterwards (the hook reads it later) is caught by its ctime, which no unprivileged caller can set back.

WHAT ADMITS A PUSHED LINE, all of it, or the line falls through to the hook's ordinary rules unchanged:

  1. `REDIACC_RELEASE_RUN` names a readable record whose real path is under `.ci/cache/release/` of the console root;
  2. the record's pid is in the hook's parent process chain, its `/proc/<pid>/stat` start time equals `pid_start` (a recycled pid fails here), its live argv equals the recorded `cmdline`, and `entry_refusal` passes it: the invocation and the package above;
  3. the record's tree equals the console's `git rev-parse HEAD^{tree}`;
  4. the exact `(toplevel, remote, remote_ref, oid)` of the line is listed in `pushes`.

WHY A PROCESS-CHAIN PROOF, NOT A TOKEN. A file an agent can write and a variable an agent can set prove nothing on their own. The record is admitted only while the process it names is alive, ran the console's committed entry, and is an ancestor of this very hook, so a forged record names either a process that is not our ancestor, one whose start time or argv disagrees, or one that ran something else. `block_git_hook_bypass` refuses an agent command that sets `REDIACC_RELEASE_RUN`, and W2-C refuses agent writes under `.ci/cache/release/`.

WHAT THIS DOES NOT PROVE. An interpreter installation the user can write (its stdlib, or a venv's own site-packages) can still run other code before the module; the system `/usr/bin/python3` is root-owned. A committed change to the entry is admitted like any commit: the tree check binds the record to HEAD, and review judges HEAD.

LINUX `/proc` ONLY. Without `/proc` (macOS) no chain can be read, so nothing is admitted and every line meets the ordinary rules: fail closed, said in the reason.

LOADED BY FILE, like every module beside it (`githooks.py` says why); it imports nothing outside the standard library.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time

ENV = "REDIACC_RELEASE_RUN"
RECORD_DIR = pathlib.PurePosixPath(".ci/cache/release")
ENTRY_MODULE = "rediacc_ci.release.local"
# The flags admitted between the interpreter and `-m`; anything else there (a script path, `-c <code>`, `-X ...`) refuses.
ENTRY_FLAGS = frozenset({"-P", "-s", "-B", "-u"})
PYCACHE_PREFIX = "/dev/null"
PACKAGE = pathlib.PurePosixPath(".ci/rediacc_ci")
# The files `-m rediacc_ci.release.local` executes before anything the entry imports itself.
ENTRY_CHAIN = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/release/__init__.py",
    ".ci/rediacc_ci/release/local.py",
)
# The PYTHON* variables the entry may carry; every other one is refused (PYTHONHOME swaps the stdlib, PYTHONWARNINGS imports a category's module, PYTHONSTARTUP and PYTHONINSPECT run code).
PY_ENV_ALLOWED = frozenset(
    {
        "PYTHONPATH",
        "PYTHONSAFEPATH",
        "PYTHONNOUSERSITE",
        "PYTHONPYCACHEPREFIX",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONHASHSEED",
    }
)
# Seconds before the entry's start inside which a change under `.ci/rediacc_ci` refuses; covers the tick and clock error of `start_epoch`.
SETTLE_S = 1.0
# The variables git exports into a hook that point a `git` call at the PUSHING repository; the console question must not inherit them.
_REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR")
_CHAIN_LIMIT = 64
# A push entry's fields, in the order of an admission key.
PUSH_KEYS = ("toplevel", "remote", "remote_ref", "oid")


class RecordError(Exception):
    """The record cannot admit anything; the message says why."""


def _stat_fields(pid: int) -> list[str] | None:
    """The fields of `/proc/<pid>/stat` after the `(comm)`, so index 0 is field 3 (state). None when unreadable."""
    try:
        raw = pathlib.Path("/proc/%d/stat" % pid).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    return raw[close + 1 :].split()


def proc_start(pid: int) -> int | None:
    """Field 22 of `/proc/<pid>/stat`, the start time in clock ticks since boot; None when unreadable."""
    fields = _stat_fields(pid)
    if not fields or len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def proc_ppid(pid: int) -> int | None:
    fields = _stat_fields(pid)
    if not fields or len(fields) < 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def proc_cmdline(pid: int) -> list[str] | None:
    try:
        raw = pathlib.Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return None
    return [w.decode("utf-8", "surrogateescape") for w in raw.split(b"\0")[:-1]] if raw else []


def parent_chain(start: int | None = None) -> list[int]:
    """The ancestors of this process, nearest first, from `start` (default: the parent) up to pid 1."""
    pid = os.getppid() if start is None else start
    out: list[int] = []
    while pid and pid > 0 and pid not in out and len(out) < _CHAIN_LIMIT:
        out.append(pid)
        pid = proc_ppid(pid) or 0
    return out


def entry_flags(argv: list[str]) -> list[str] | None:
    """The flags of `<interpreter> <flags...> -m rediacc_ci.release.local ...` when argv has exactly that shape, else None.

    The two words alone prove nothing: in `python3 evil.py -m rediacc_ci.release.local` and `python3 -c <code> -m ...` they are arguments of other code. So every word between the interpreter and `-m` must be one of `ENTRY_FLAGS`.
    """
    for i in range(1, len(argv) - 1):
        if argv[i] == "-m":
            return argv[1:i] if argv[i + 1] == ENTRY_MODULE else None
        if argv[i] not in ENTRY_FLAGS:
            return None
    return None


def is_entry_argv(argv: list[str]) -> bool:
    """`<interpreter> [ENTRY_FLAGS...] -m rediacc_ci.release.local ...`: `rediacc_ci.release.local_gates`, a script or `-c` ahead of the words, and prose mentioning the module do not count."""
    return entry_flags(argv) is not None


def proc_environ(pid: int) -> dict[str, str] | None:
    """The environment `pid` was started with, from `/proc/<pid>/environ`; None when unreadable."""
    try:
        raw = pathlib.Path("/proc/%d/environ" % pid).read_bytes()
    except OSError:
        return None
    out: dict[str, str] = {}
    for word in raw.split(b"\0"):
        key, sep, value = word.partition(b"=")
        if sep:
            out[key.decode("utf-8", "surrogateescape")] = value.decode("utf-8", "surrogateescape")
    return out


def start_epoch(ticks: int) -> float:
    """A `/proc/<pid>/stat` start time (clock ticks since boot, CLOCK_BOOTTIME based) as seconds since the epoch, to compare with a file's ctime."""
    boot = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME)
    return boot + ticks / os.sysconf("SC_CLK_TCK")


def _console_git(
    console_root: str | os.PathLike, args: list[str]
) -> subprocess.CompletedProcess | None:
    env = {k: v for k, v in os.environ.items() if k not in _REPO_ENV}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(console_root),
            capture_output=True,
            timeout=60,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def invocation_refusal(
    console_root: str | os.PathLike, argv: list[str], environ: dict[str, str]
) -> str:
    """ "" when argv and the start-up environment can only have loaded `rediacc_ci` from `<console>/.ci`, else why not (THE ENTRY INVOCATION above)."""
    flags = entry_flags(argv)
    if flags is None:
        return "its argv %r is not `python3 [%s] -m %s ...`" % (
            argv[:6],
            " ".join(sorted(ENTRY_FLAGS)),
            ENTRY_MODULE,
        )
    if "-P" not in flags and not environ.get("PYTHONSAFEPATH"):
        return "it runs without -P (or PYTHONSAFEPATH), so `-m` searched its cwd first and a planted `rediacc_ci` there would have run"
    if "-s" not in flags and not environ.get("PYTHONNOUSERSITE"):
        return "it runs without -s (or PYTHONNOUSERSITE), so a `.pth` file in the user site directory ran before the module"
    if environ.get("PYTHONPYCACHEPREFIX") != PYCACHE_PREFIX:
        return (
            "its PYTHONPYCACHEPREFIX is %r, not %s, so a planted `__pycache__` file could have run in place of a pristine source"
            % (
                environ.get("PYTHONPYCACHEPREFIX"),
                PYCACHE_PREFIX,
            )
        )
    extra = sorted(
        k
        for k in environ
        if (k.startswith("PYTHON") and k not in PY_ENV_ALLOWED) or k.startswith("LD_")
    )
    if extra:
        return "it was started with %s set; unset %s for the release" % (
            ", ".join(extra),
            "it" if len(extra) == 1 else "them",
        )
    first = environ.get("PYTHONPATH", "").split(os.pathsep)[0]
    want = os.path.join(os.path.realpath(console_root), ".ci")
    if (
        not first
        or not os.path.isabs(first)
        or os.path.realpath(first) != want
        or os.path.realpath(want) != want
    ):
        return (
            "its first PYTHONPATH entry is %r, not the console's %s, so `rediacc_ci` may have come from elsewhere"
            % (
                first,
                want,
            )
        )
    return ""


def package_refusal(console_root: str | os.PathLike, started: float) -> str:
    """ "" when `.ci/rediacc_ci` is HEAD's, untouched since `SETTLE_S` before `started` (epoch seconds), else why not (THE PACKAGE ON DISK above)."""
    staged = _console_git(console_root, ["ls-files", "-s", "-z", "--", *ENTRY_CHAIN])
    if staged is None or staged.returncode != 0:
        return "git cannot list the console's entry files"
    modes = {}
    for row in staged.stdout.split(b"\0"):
        meta, tab, path = row.partition(b"\t")
        if tab:
            modes[path.decode("utf-8", "surrogateescape")] = meta.split(b" ")[0].decode()
    for path in ENTRY_CHAIN:
        if modes.get(path) not in ("100644", "100755"):
            return "%s is not a tracked regular file of the console" % path
    status = _console_git(
        console_root,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
            "--",
            str(PACKAGE),
        ],
    )
    if status is None or status.returncode != 0:
        return "git cannot read the status of %s" % PACKAGE
    dirty = []
    for row in status.stdout.split(b"\0"):
        path = row[3:].decode("utf-8", "surrogateescape")
        if len(row) > 3 and "__pycache__" not in pathlib.PurePosixPath(path).parts:
            dirty.append(row[:2].decode() + " " + path)
    if dirty:
        return (
            "%s is not HEAD's (%s%s); the entry may have imported any of it, so release from a clean package"
            % (
                PACKAGE,
                ", ".join(dirty[:3]),
                ", ..." if len(dirty) > 3 else "",
            )
        )
    root = pathlib.Path(console_root) / PACKAGE
    limit = started - SETTLE_S
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in [".", *files]:
            path = os.path.join(folder, name) if name != "." else folder
            try:
                changed = os.lstat(path).st_ctime
            except OSError:
                return "%s cannot be read" % path
            if changed > limit:
                return (
                    "%s changed %.2fs after the entry started (less than %.1fs before counts), so the entry may have run another version of it"
                    % (
                        os.path.relpath(path, console_root),
                        changed - started,
                        SETTLE_S,
                    )
                )
    return ""


def entry_refusal(console_root: str | os.PathLike, pid: int) -> str:
    """ "" when the live process `pid` provably ran the console's tracked, unmodified entry, else why not."""
    argv = proc_cmdline(pid)
    environ = proc_environ(pid)
    ticks = proc_start(pid)
    if argv is None or environ is None or ticks is None:
        return "/proc/%d cannot be read" % pid
    return invocation_refusal(console_root, argv, environ) or package_refusal(
        console_root, start_epoch(ticks)
    )


def record_dir(console_root: str | os.PathLike) -> pathlib.Path:
    return pathlib.Path(console_root) / RECORD_DIR


def console_tree(console_root: str | os.PathLike) -> str:
    env = {k: v for k, v in os.environ.items() if k not in _REPO_ENV}
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=str(console_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _norm_toplevel(path: str) -> str:
    return os.path.realpath(path) if path else ""


def write_release_run(
    console_root: str | os.PathLike,
    run_id: str,
    *,
    tree: str,
    version: str,
    channel: str,
    pushes: list[dict],
    pid: int | None = None,
) -> pathlib.Path:
    """Write `.ci/cache/release/run-<run_id>.json` for `pid` (default: this process) and return its path; the caller exports it as `REDIACC_RELEASE_RUN`.

    The start time and argv are read from `/proc` here, never passed in, so the record always describes a real process. Refuses (RecordError) a pid that `entry_refusal` refuses or that cannot be read, and a push entry missing a field: a record the reader would refuse is never written.
    """
    pid = os.getpid() if pid is None else pid
    start = proc_start(pid)
    argv = proc_cmdline(pid)
    if start is None or argv is None:
        raise RecordError("/proc/%d cannot be read, so no release run can be recorded" % pid)
    why = entry_refusal(console_root, pid)
    if why:
        raise RecordError("pid %d is not the console's release entry: %s" % (pid, why))
    if not run_id or "/" in run_id or run_id.startswith("."):
        raise RecordError("run id %r is not a plain file-name part" % run_id)
    rows = []
    for push in pushes:
        fields = [push.get(k) for k in PUSH_KEYS]
        if not all(isinstance(f, str) for f in fields):
            raise RecordError("push entry %r needs %s strings" % (push, ", ".join(PUSH_KEYS)))
        if not all(fields):
            raise RecordError("push entry %r has an empty field" % push)
        toplevel, remote, ref, oid = fields
        rows.append(
            {"toplevel": _norm_toplevel(toplevel), "remote": remote, "remote_ref": ref, "oid": oid}
        )
    record = {
        "pid": pid,
        "pid_start": start,
        "cmdline": argv,
        "tree": tree,
        "version": version,
        "channel": channel,
        "pushes": rows,
    }
    folder = record_dir(console_root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("run-%s.json" % run_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_record(console_root: str | os.PathLike, named: str) -> dict:
    """The record `named` (the variable's value), or RecordError with the reason."""
    if not named:
        raise RecordError("%s is not set" % ENV)
    base = os.path.realpath(record_dir(console_root))
    real = os.path.realpath(named)
    if os.path.commonpath([base, real]) != base or real == base:
        raise RecordError("%s names %s, which is not under %s" % (ENV, named, base))
    try:
        record = json.loads(pathlib.Path(real).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordError("the record %s cannot be read (%s)" % (named, exc)) from exc
    if not isinstance(record, dict):
        raise RecordError("the record %s is not an object" % named)
    pid, start, argv = record.get("pid"), record.get("pid_start"), record.get("cmdline")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        raise RecordError("the record's pid %r is not a process id" % (pid,))
    if not isinstance(start, int) or isinstance(start, bool):
        raise RecordError("the record's pid_start %r is not a start time" % (start,))
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise RecordError("the record's cmdline is not an argv list")
    if not isinstance(record.get("tree"), str) or not isinstance(record.get("pushes"), list):
        raise RecordError("the record carries no tree or no pushes list")
    return record


def admitted_pushes(
    console_root: str | os.PathLike,
    environ: dict | None = None,
    chain: list[int] | None = None,
) -> set[tuple[str, str, str, str]]:
    """The `(toplevel, remote, remote_ref, oid)` keys a live release run admits, or RecordError naming the first condition that fails."""
    environ = os.environ if environ is None else environ
    record = load_record(console_root, environ.get(ENV, ""))
    pid = record["pid"]
    if not os.path.exists("/proc/self/stat"):
        raise RecordError("there is no /proc here, so no parent chain can be read")
    chain = parent_chain() if chain is None else chain
    if pid not in chain:
        raise RecordError(
            "the record's pid %d is not in this hook's parent chain %s" % (pid, chain)
        )
    live_start = proc_start(pid)
    if live_start != record["pid_start"]:
        raise RecordError(
            "pid %d started at %s, the record says %s" % (pid, live_start, record["pid_start"])
        )
    live_argv = proc_cmdline(pid) or []
    if live_argv != record["cmdline"]:
        raise RecordError("pid %d's argv differs from the recorded cmdline" % pid)
    why = entry_refusal(console_root, pid)
    if why:
        raise RecordError("pid %d is not the console's release entry: %s" % (pid, why))
    tree = console_tree(console_root)
    if not tree or tree != record["tree"]:
        raise RecordError(
            "the console HEAD^{tree} is %s, the record says %s"
            % (tree or "(unreadable)", record["tree"])
        )
    out = set()
    for push in record["pushes"]:
        if not isinstance(push, dict):
            continue
        fields = [push.get(k) for k in PUSH_KEYS]
        if all(isinstance(f, str) and f for f in fields):
            toplevel, remote, ref, oid = fields
            out.add((_norm_toplevel(toplevel), remote, ref, oid))
    return out


def admission_key(
    toplevel: str, remote: str, remote_ref: str, oid: str
) -> tuple[str, str, str, str]:
    return (_norm_toplevel(toplevel), remote, remote_ref, oid)


def admits(
    keys: set[tuple[str, str, str, str]], toplevel: str, remote: str, remote_ref: str, oid: str
) -> bool:
    return admission_key(toplevel, remote, remote_ref, oid) in keys

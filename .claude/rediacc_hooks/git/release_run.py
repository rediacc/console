"""The release-run record: the one way a local release (`python3 -m rediacc_ci.release.local`, box W2-B of agent/plans/PLAN-local-release.md) gets its own pushes past the git-level `pre-push` refusal of `main` (box W1-D).

THE RECORD. The entry writes `.ci/cache/release/run-<id>.json` of the console root through `write_release_run` below, and exports `REDIACC_RELEASE_RUN=<that path>` to the git commands it runs:

    {"pid": <the entry's pid>, "pid_start": <field 22 of /proc/<pid>/stat>, "cmdline": [<argv>],
     "tree": <console HEAD^{tree}>, "version": "<V>", "channel": "edge|stable",
     "pushes": [{"toplevel": "<abs repo path>", "remote_ref": "refs/heads/main", "oid": "<sha>"}]}

WHAT ADMITS A PUSHED LINE, all of it, or the line falls through to the hook's ordinary rules unchanged:

  1. `REDIACC_RELEASE_RUN` names a readable record whose real path is under `.ci/cache/release/` of the console root;
  2. the record's pid is in the hook's parent process chain, its `/proc/<pid>/stat` start time equals `pid_start` (a recycled pid fails here), and its live argv carries `-m rediacc_ci.release.local` as two adjacent words and equals the recorded `cmdline`;
  3. the record's tree equals the console's `git rev-parse HEAD^{tree}`;
  4. the exact `(toplevel, remote_ref, oid)` of the line is listed in `pushes`.

WHY A PROCESS-CHAIN PROOF, NOT A TOKEN. A file an agent can write and a variable an agent can set prove nothing on their own. The record is admitted only while the process it names is alive, is the release entry, and is an ancestor of this very hook, so a forged record names either a process that is not our ancestor or one whose start time or argv disagrees. `block_git_hook_bypass` refuses an agent command that sets `REDIACC_RELEASE_RUN`, and W2-C refuses agent writes under `.ci/cache/release/`.

LINUX `/proc` ONLY. Without `/proc` (macOS) no chain can be read, so nothing is admitted and every line meets the ordinary rules: fail closed, said in the reason.

LOADED BY FILE, like every module beside it (`githooks.py` says why); it imports nothing outside the standard library.
"""

from __future__ import annotations

import itertools
import json
import os
import pathlib
import subprocess

ENV = "REDIACC_RELEASE_RUN"
RECORD_DIR = pathlib.PurePosixPath(".ci/cache/release")
ENTRY_MODULE = "rediacc_ci.release.local"
# The variables git exports into a hook that point a `git` call at the PUSHING repository; the console question must not inherit them.
_REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR")
_CHAIN_LIMIT = 64


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


def is_entry_argv(argv: list[str]) -> bool:
    """`-m rediacc_ci.release.local` as two adjacent words: `rediacc_ci.release.local_gates` and prose mentioning the module do not count."""
    return any(a == "-m" and b == ENTRY_MODULE for a, b in itertools.pairwise(argv))


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

    The start time and argv are read from `/proc` here, never passed in, so the record always describes a real process. Refuses (RecordError) a pid that is not the release entry or cannot be read, and a push entry missing a field: a record the reader would refuse is never written.
    """
    pid = os.getpid() if pid is None else pid
    start = proc_start(pid)
    argv = proc_cmdline(pid)
    if start is None or argv is None:
        raise RecordError("/proc/%d cannot be read, so no release run can be recorded" % pid)
    if not is_entry_argv(argv):
        raise RecordError("pid %d is not `python3 -m %s` (argv %r)" % (pid, ENTRY_MODULE, argv[:4]))
    if not run_id or "/" in run_id or run_id.startswith("."):
        raise RecordError("run id %r is not a plain file-name part" % run_id)
    rows = []
    for push in pushes:
        toplevel, ref, oid = push.get("toplevel"), push.get("remote_ref"), push.get("oid")
        if not (isinstance(toplevel, str) and isinstance(ref, str) and isinstance(oid, str)):
            raise RecordError("push entry %r needs toplevel, remote_ref and oid strings" % push)
        if not (toplevel and ref and oid):
            raise RecordError("push entry %r has an empty field" % push)
        rows.append({"toplevel": _norm_toplevel(toplevel), "remote_ref": ref, "oid": oid})
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
) -> set[tuple[str, str, str]]:
    """The `(toplevel, remote_ref, oid)` triples a live release run admits, or RecordError naming the first condition that fails."""
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
    if not is_entry_argv(live_argv):
        raise RecordError("pid %d is not `python3 -m %s`" % (pid, ENTRY_MODULE))
    if live_argv != record["cmdline"]:
        raise RecordError("pid %d's argv differs from the recorded cmdline" % pid)
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
        toplevel, ref, oid = push.get("toplevel"), push.get("remote_ref"), push.get("oid")
        if isinstance(toplevel, str) and isinstance(ref, str) and isinstance(oid, str):
            out.add((_norm_toplevel(toplevel), ref, oid))
    return out


def admits(triples: set[tuple[str, str, str]], toplevel: str, remote_ref: str, oid: str) -> bool:
    return (_norm_toplevel(toplevel), remote_ref, oid) in triples

"""Host temp disposal: sweep finished leases, dead run dirs and legacy leftovers (agent/plans/PLAN-host-temp-disposal.md D6, D8, D10, Design 7).

    python3 -m rediacc_ci.dev.host_temp sweep [--lock-held]
    python3 -m rediacc_ci.dev.host_temp reclaim --legacy [--write]
    python3 -m rediacc_ci.dev.host_temp status

`sweep` runs from the Stop hook, detached. A lease is finished when SubagentStop left a marker `<common>/rediacc-worktrees/<id>.finished`, the marker and the transcript are both at least GRACE_S old, the harness meta has not been cleared by a resume, and nothing names or holds the lease. A finished lease loses its leftover processes, its temp, and (when gc's rules allow) its tree. Every action is appended to `sweeps.jsonl` and returned as a printable line.

`reclaim --legacy` lists the unstamped leftovers made before the run-dir stamp existed, and deletes them only with `--write`.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable
from typing import Any, NamedTuple

from rediacc_ci import runtmp
from rediacc_ci.dev import worktree_lease

GRACE_S = 1800
TERM_WAIT_S = 5.0
KILL_ROUNDS = 3
RECORD_DIR = "rediacc-worktrees"
MARKER_SUFFIX = ".finished"
SWEEPS = "sweeps.jsonl"
LOCK_NAME = "sweep.lock"
GUARD_NAME = "sweep.guard"
#: A lock older than this is a hung sweeper's and is taken over, whatever its pid says.
LOCK_STALE_S = 3600
#: The handoff token rides from the Stop hook to the sweeper in this variable; the sweeper releases only the lock that carries it.
LOCK_HANDOFF_ENV = "HOST_TEMP_LOCK_HANDOFF"

#: Every `runDir` / `run_dir` / `shared` prefix a tool of this tree stamps, so the host sweep can remove a SIGKILLed run's directory in each base.
PREFIXES = (
    "agent-browser-exit-",
    "backfill-pathmask-",
    "check-source-rules-",
    "dead-python-",
    "difftest-",
    "env-file-adoption-",
    "env-manifest-",
    "gate-harness-",
    "gate-harness-children-",
    "harness-",
    "install-sh-config-",
    "mutate-check-gate-",
    "path-trace-",
    "plan-housekeeping-test-",
    "r2-stub-",
    "renet-markers-",
    "renet-types-",
    "rediacc-pytest-",
    "rediacc-vitest-",
    "svc-stub-",
    "trace-honest-",
    "vm-check-tmp-",
)

#: Prefixes whose unstamped directories `reclaim --legacy` may remove.
LEGACY_PREFIXES = (
    "path-trace-",
    "trace-honest-",
    "rediacc-pytest-",
    "renet-markers-",
    "check-source-rules-",
    "gen-docs-precommit-",
    "rediacc-vitest-",
    "elite-",
    "inbox-",
    "churn-store-",
    "rdc-mcp-call-",
    "rdc-cli-test-home-",
)
LEGACY_AGE_S = 1800
LIVE_ERRORS = (OSError, ValueError, RuntimeError, AttributeError, TypeError, KeyError, ImportError)

GcFn = Callable[[pathlib.Path, str], tuple[int, list[str]]]
BusyFn = Callable[[str], str]


class Proc(NamedTuple):
    pid: int
    start: int
    cwd: str
    tmp: str
    comm: str


# ---- paths ------------------------------------------------------------------


def _under(path: str, parent: str) -> bool:
    return bool(parent) and (path == parent or path.startswith(parent.rstrip(os.sep) + os.sep))


def default_bases() -> list[str]:
    candidates = [os.environ.get("CLAUDE_CODE_TMPDIR") or "", "/var/tmp/r%d" % os.getuid(), "/tmp"]
    seen: list[str] = []
    for base in candidates:
        if base and os.path.isdir(base) and base not in seen:
            seen.append(base)
    return seen


def main_checkout(start: str | os.PathLike[str]) -> pathlib.Path:
    """The main checkout of the repository `start` sits in, found through the common git dir."""
    done = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(start),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0 or not done.stdout.strip():
        raise SystemExit("host_temp: %s is no git checkout" % start)
    return pathlib.Path(done.stdout.strip()).parent


def tree_size(path: str) -> int:
    """Bytes on disk under `path`, symlinks not followed."""
    total = 0
    stack = [path]
    while stack:
        here = stack.pop()
        try:
            with os.scandir(here) as it:
                for entry in it:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    total += st.st_blocks * 512
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue
    return total


def human(size: int) -> str:
    return "%.1f GB" % (size / 1e9) if size >= 1e8 else "%.1f MB" % (size / 1e6)


def typecheck_dir(root: str, home: str) -> str:
    """`cacheDirFor` of scripts/ci-runner/typecheck-cache-dir.ts."""
    return os.path.join(home, ".cache", "rediacc-typecheck", root.lstrip("/").replace("/", "-"))


def gen_docs_dir(git_dir: str, base: str) -> str:
    """`scratch_for` of githooks.py: one fixed directory per worktree git dir."""
    key = hashlib.sha1(git_dir.encode("utf-8")).hexdigest()[:12]
    return os.path.join(base, "gen-docs-precommit-%s" % key)


# ---- processes --------------------------------------------------------------


def _stat_fields(pid: int) -> list[str] | None:
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    return text[text.rfind(")") + 2 :].split()


def start_time(pid: int) -> int:
    """Field 22 of /proc/<pid>/stat, or -1 when the process is gone or a zombie."""
    fields = _stat_fields(pid)
    if not fields or fields[0] == "Z":
        return -1
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return -1


def _environ_tmpdir(pid: int) -> str:
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            blob = fh.read()
    except OSError:
        return ""
    for item in blob.split(b"\0"):
        if item.startswith(b"TMPDIR="):
            return item[7:].decode("utf-8", "replace")
    return ""


def scan_procs() -> list[Proc]:
    """This uid's processes with their cwd, start time and TMPDIR."""
    out: list[Proc] = []
    uid = os.getuid()
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            if os.stat("/proc/%d" % pid).st_uid != uid:
                continue
            cwd = os.readlink("/proc/%d/cwd" % pid)
            with open("/proc/%d/comm" % pid, encoding="utf-8", errors="replace") as fh:
                comm = fh.read().strip()
        except OSError:
            continue
        start = start_time(pid)
        if start >= 0:
            out.append(Proc(pid, start, cwd, _environ_tmpdir(pid), comm))
    return out


def _ancestors() -> set[int]:
    seen = {os.getpid()}
    pid = os.getppid()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        fields = _stat_fields(pid)
        if not fields:
            break
        pid = int(fields[1])
    return seen


def _targets(procs: list[Proc], dirs: list[str], shield: set[int]) -> list[Proc]:
    return [
        p
        for p in procs
        if p.pid not in shield
        and "claude" not in p.comm.lower()
        and any(_under(p.cwd, d) or _under(p.tmp, d) for d in dirs if d)
    ]


def _signal(proc: Proc, sig: int) -> bool:
    """Signal `proc` only while it is still the process the scan saw (same pid and start time)."""
    if start_time(proc.pid) != proc.start:
        return False
    try:
        os.kill(proc.pid, sig)
    except OSError:
        return False
    return True


def kill_in(
    dirs: list[str],
    *,
    scan: Callable[[], list[Proc]] = scan_procs,
    term_wait: float = TERM_WAIT_S,
) -> list[str]:
    """Kill every process of this uid working in, or with TMPDIR under, `dirs`; the command names killed. SIGTERM, then SIGKILL after `term_wait`, up to KILL_ROUNDS rounds to catch new forks. Never an ancestor of this process and never a `claude` process."""
    shield = _ancestors()
    killed: list[str] = []
    for _ in range(KILL_ROUNDS):
        found = _targets(scan(), dirs, shield)
        if not found:
            break
        hit = [p for p in found if _signal(p, signal.SIGTERM)]
        killed += [p.comm for p in hit]
        deadline = time.monotonic() + term_wait
        while hit and time.monotonic() < deadline:
            hit = [p for p in hit if start_time(p.pid) == p.start]
            if hit:
                time.sleep(0.05)
        for proc in hit:
            _signal(proc, signal.SIGKILL)
    return killed


def open_paths() -> tuple[set[str], list[str]]:
    """(every cwd and open-fd target of any process, every strace `-o` argument): one /proc scan."""
    seen: set[str] = set()
    strace_out: list[str] = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        base = "/proc/%s" % name
        with contextlib.suppress(OSError):
            seen.add(os.readlink(base + "/cwd"))
        with contextlib.suppress(OSError):
            for fd in os.listdir(base + "/fd"):
                with contextlib.suppress(OSError):
                    seen.add(os.readlink("%s/fd/%s" % (base, fd)))
        try:
            with open(base + "/cmdline", "rb") as fh:
                argv = fh.read().split(b"\0")
        except OSError:
            continue
        if os.path.basename(argv[0].decode("utf-8", "replace")) == "strace":
            strace_out += [
                argv[i + 1].decode("utf-8", "replace")
                for i, arg in enumerate(argv[:-1])
                if arg == b"-o"
            ]
    return seen, strace_out


# ---- finished leases (D6) ---------------------------------------------------


def _read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def finished_problem(
    common: pathlib.Path,
    lease_id: str,
    now: float,
    *,
    grace: float = GRACE_S,
    busy: BusyFn = lambda _id: "",
) -> str:
    """ "" when D6 holds for `lease_id`, else the reason it does not."""
    marker = _read_json(common / RECORD_DIR / (lease_id + MARKER_SUFFIX))
    if not isinstance(marker, dict):
        return "no marker"
    finished_at = marker.get("finished_at")
    if not isinstance(finished_at, int | float):
        return "marker without finished_at"
    if now - finished_at < grace:
        return "finished %d s ago" % (now - finished_at)
    transcript = str(marker.get("transcript") or "")
    if transcript:
        try:
            quiet = now - os.stat(transcript).st_mtime
        except OSError as exc:
            # An unreadable fact counts as busy (default_busy's rule): a transcript that cannot be stat'ed proves nothing about the agent's quiet time (review f2b58581.1).
            return "transcript unreadable (%s)" % (exc.strerror or exc)
        if quiet < grace:
            return "transcript written %d s ago" % quiet
        meta = _read_json(pathlib.Path(transcript).with_suffix(".meta.json"))
        if isinstance(meta, dict) and meta.get("finished") is not True:
            return "resumed (meta not finished)"
    return busy(lease_id)


# ---- sweep (D8) -------------------------------------------------------------


def _remove(path: str) -> int:
    """Bytes freed by removing `path` (0 when it is absent)."""
    if not os.path.lexists(path):
        return 0
    size = tree_size(path) if os.path.isdir(path) and not os.path.islink(path) else 0
    runtmp.remove_tree(path)
    if os.path.lexists(path):
        with contextlib.suppress(OSError):
            os.unlink(path)
    return size


def _kept_rule(lines: list[str], lease_id: str) -> str:
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0] == "KEEP" and parts[1] == lease_id:
            return parts[2].split(";")[0]
    return ""


def _summary(comms: list[str]) -> str:
    return ", ".join("%s x%d" % (c, n) for c, n in sorted(Counter(comms).items()))


def sweep_lease(
    root: pathlib.Path,
    common: pathlib.Path,
    lease_id: str,
    *,
    now: float,
    busy: BusyFn,
    gc: GcFn,
    scan: Callable[[], list[Proc]] = scan_procs,
    home: str | None = None,
    gen_bases: list[str] | None = None,
    term_wait: float = TERM_WAIT_S,
) -> list[str]:
    """D8 for one lease: re-judge, kill, delete temp, gc. The printable rows, [] when the lease is not finished or nothing was left to do."""
    if finished_problem(common, lease_id, now, busy=busy):
        return []
    record = _read_json(common / RECORD_DIR / (lease_id + ".json"))
    record = record if isinstance(record, dict) else {}
    tree = str(record.get("path") or root / ".claude" / "worktrees" / lease_id)
    tmpdir = str(record.get("tmpdir") or "")
    killed = kill_in([tree, *([tmpdir] if tmpdir else [])], scan=scan, term_wait=term_wait)
    freed = _remove(tmpdir) if tmpdir else 0
    freed += _remove(typecheck_dir(tree, home or os.path.expanduser("~")))
    git_dir = str(common / "worktrees" / lease_id)
    for base in default_bases() if gen_bases is None else gen_bases:
        freed += _remove(gen_docs_dir(git_dir, base))
    existed = os.path.lexists(tree)
    size = tree_size(tree) if existed else 0
    rc, lines = gc(root, lease_id)
    left = os.path.lexists(tree)
    if rc == 0 and not left:
        (common / RECORD_DIR / (lease_id + MARKER_SUFFIX)).unlink(missing_ok=True)
    out = []
    temp = " and its temp (%s)" % human(freed) if freed else ""
    if existed and not left:
        out.append("removed tree %s (%s)%s" % (lease_id, human(size), temp))
    elif existed and (freed or killed):
        rule = _kept_rule(lines, lease_id) or "gc kept it"
        out.append(
            "kept tree %s (%s)%s"
            % (lease_id, rule, ", temp removed (%s)" % human(freed) if freed else "")
        )
    elif freed:
        out.append("removed temp of %s (%s)" % (lease_id, human(freed)))
    if killed:
        out.append("killed %d processes in %s (%s)" % (len(killed), lease_id, _summary(killed)))
    return out


def sweep_dead_runs(bases: list[str], prefixes: tuple[str, ...] = PREFIXES) -> list[str]:
    """D10: dead-pid run dirs of every registered prefix in every base."""
    removed: list[str] = []
    for base in bases:
        for prefix in prefixes:
            removed += runtmp.sweep_dead(prefix, base)
    return removed


def typecheck_orphans(root: pathlib.Path, cache_root: str, apply: bool = True) -> list[str]:
    """Typecheck cache dirs of lease trees that are gone. Only names that start with this checkout's munged `.claude/worktrees/` path are judged."""
    head = str(root / ".claude" / "worktrees").lstrip("/").replace("/", "-") + "-"
    out: list[str] = []
    try:
        names = sorted(os.listdir(cache_root))
    except OSError:
        return out
    for name in names:
        lease_id = name[len(head) :]
        if not name.startswith(head) or not lease_id:
            continue
        if os.path.lexists(root / ".claude" / "worktrees" / lease_id):
            continue
        path = os.path.join(cache_root, name)
        if apply:
            _remove(path)
        out.append(path)
    return out


def _record_rows(common: pathlib.Path, lines: list[str], now: float) -> None:
    path = common / RECORD_DIR / SWEEPS
    try:
        seq = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
        with open(path, "a", encoding="utf-8") as fh:
            for line in lines:
                seq += 1
                fh.write(json.dumps({"seq": seq, "ts": int(now), "text": line}) + "\n")
    except OSError as exc:
        # The sweep already acted; a log row that cannot be written is said once instead of vanishing (review f2b58581.3).
        print("host_temp: cannot append to %s: %s" % (path, exc), file=sys.stderr)


def _heartbeat(common: pathlib.Path) -> None:
    """Refresh the lock's mtime while its holder is still sweeping, so `lock_is_stale`'s age rule judges a HUNG holder (no refresh for LOCK_STALE_S) and not a slow one (review 2872d8fe.3)."""
    with contextlib.suppress(OSError):
        os.utime(common / RECORD_DIR / LOCK_NAME, None)


def lock_body(pid: int, token: str = "", now: float | None = None) -> dict[str, Any]:
    """The lock record: the holder's pid and start time (so a reused pid is not taken for it) and the handoff token. The Stop hook's `wl_hosttemp` writes the same shape."""
    body: dict[str, Any] = {
        "pid": pid,
        "start": start_time(pid),
        "at": time.time() if now is None else now,
    }
    if token:
        body["token"] = token
    return body


def lock_is_stale(path: pathlib.Path, now: float | None = None) -> bool:
    """A lock whose recorded process is gone (dead, a zombie, or a reused pid) is stale; so is one older than LOCK_STALE_S, or one that cannot be parsed. Raises OSError when the lock vanished."""
    age = (time.time() if now is None else now) - path.stat().st_mtime
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return True
    if not isinstance(rec, dict) or not isinstance(rec.get("pid"), int):
        return True
    start = start_time(rec["pid"])
    if start < 0 or (
        isinstance(rec.get("start"), int) and rec["start"] >= 0 and start != rec["start"]
    ):
        return True
    return age >= LOCK_STALE_S


@contextlib.contextmanager
def _guard(records: pathlib.Path):
    """The flock on `sweep.guard`, so two stale takeovers run in turn instead of both deleting one fresh lock."""
    records.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(records / GUARD_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def take_lock(common: pathlib.Path, token: str = "", now: float | None = None) -> bool:
    """O_EXCL lock with dead-pid takeover, under the guard flock. True when this process now holds it."""
    records = common / RECORD_DIR
    path = records / LOCK_NAME
    with _guard(records):
        for _ in range(2):
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    stale = lock_is_stale(path, now)
                except OSError:
                    continue
                if not stale:
                    return False
                path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(lock_body(os.getpid(), token, now), fh)
            return True
    return False


def release_lock(common: pathlib.Path, token: str) -> bool:
    """Remove the lock only while it carries `token`: a lock another sweeper took since is left alone. True when removed."""
    records = common / RECORD_DIR
    path = records / LOCK_NAME
    if not token:
        return False
    with _guard(records):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(rec, dict) or rec.get("token") != token:
            return False
        path.unlink(missing_ok=True)
    return True


def sweep(
    root: pathlib.Path,
    *,
    now: float | None = None,
    busy: BusyFn | None = None,
    gc: GcFn | None = None,
    scan: Callable[[], list[Proc]] = scan_procs,
    bases: list[str] | None = None,
    home: str | None = None,
    lock_held: bool = True,
    token: str = "",
    term_wait: float = TERM_WAIT_S,
) -> list[str]:
    """One sweep of every finished lease plus the host-level dead-run sweep. Returns the printed rows and appends them to sweeps.jsonl."""
    root = pathlib.Path(root)
    common = root / ".git"
    now = time.time() if now is None else now
    if not lock_held:
        token = token or uuid.uuid4().hex
        if not take_lock(common, token):
            return []
    try:
        busy = busy or default_busy(root)
        gc = gc or default_gc
        bases = default_bases() if bases is None else bases
        home = home or os.path.expanduser("~")
        rows: list[str] = []
        records = common / RECORD_DIR
        _heartbeat(common)
        for marker in sorted(records.glob("*" + MARKER_SUFFIX)) if records.is_dir() else []:
            lease_id = marker.name[: -len(MARKER_SUFFIX)]
            _heartbeat(common)
            tree = root / ".claude" / "worktrees" / lease_id
            if not (records / (lease_id + ".json")).exists() and not os.path.lexists(tree):
                marker.unlink(missing_ok=True)
                continue
            rows += sweep_lease(
                root,
                common,
                lease_id,
                now=now,
                busy=busy,
                gc=gc,
                scan=scan,
                home=home,
                gen_bases=bases,
                term_wait=term_wait,
            )
        dead = sweep_dead_runs(bases)
        if dead:
            where = ", ".join(sorted({os.path.dirname(d) for d in dead}))
            rows.append("swept %d dead run dirs (%s)" % (len(dead), where))
        orphans = typecheck_orphans(root, os.path.join(home, ".cache", "rediacc-typecheck"))
        if orphans:
            rows.append("removed %d typecheck caches of gone trees" % len(orphans))
        _record_rows(common, rows, now)
        return rows
    finally:
        # A sweeper the Stop hook started (`--lock-held`) releases the lock the hook took for it; the token proves it is still that lock.
        if token:
            release_lock(common, token)


# ---- defaults wired to the real tree ---------------------------------------


def default_gc(root: pathlib.Path, lease_id: str) -> tuple[int, list[str]]:
    return worktree_lease.run_gc(root, write=True, only=lease_id)


def default_busy(root: pathlib.Path) -> BusyFn:
    """D6's last two clauses: no live worklist item names the lease and no live roster row holds it. A fact that cannot be read counts as busy."""
    wl = worktree_lease
    cache: dict[str, Any] = {}

    def check(lease_id: str) -> str:
        path = str(root / ".claude" / "worktrees" / lease_id)
        try:
            with wl._project_env(root):
                live = cache.setdefault("live", wl._read_live(root, named=True))
                if live["leases"] is None:
                    return "worklist unreadable"
                item = wl._hook_module("wl_scratch").lease_holder(lease_id, path, live["leases"])
                if item:
                    return "worklist item #%s names it" % item
                record = _read_json(root / ".git" / RECORD_DIR / (lease_id + ".json")) or {}
                rows = wl._roster_of(root, str(record.get("owner") or ""))
                if rows is None:
                    return "roster cannot say"
                holder = wl._agent_holding(rows, lease_id, os.path.realpath(path), record)
                return "live writer %s holds it" % holder if holder else ""
        except LIVE_ERRORS as exc:
            return "cannot judge: %s" % exc

    return check


# ---- reclaim --legacy -------------------------------------------------------

_STAMPED = re.compile(r"-\d+-n\d+-")


def _newest_mtime(path: str, young_after: float) -> float:
    """The newest mtime of `path` and everything under it, symlinks not followed. A directory's own mtime moves only when an entry is added or removed directly in it, so a tree whose files are rewritten in place needs the walk (review f2b58581.4). The walk stops at the first entry newer than `young_after`: the caller only needs to know whether anything is young. Raises OSError when `path` itself cannot be read."""
    newest = os.lstat(path).st_mtime
    stack = [path]
    while stack and newest <= young_after:
        here = stack.pop()
        try:
            with os.scandir(here) as it:
                for entry in it:
                    try:
                        newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return newest


def reclaim_legacy(
    bases: list[str],
    *,
    write: bool = False,
    now: float | None = None,
    prefixes: tuple[str, ...] = LEGACY_PREFIXES,
    open_scan: Callable[[], tuple[set[str], list[str]]] = open_paths,
) -> list[str]:
    """Rows `REMOVE|WOULD-REMOVE|KEEP <path> <why>` for every unstamped leftover; removed only with `write`. An entry stays when any process has a cwd or open fd under it, when it is younger than LEGACY_AGE_S, or when a running strace writes under it."""
    now = time.time() if now is None else now
    held, strace_out = open_scan()
    rows: list[str] = []
    for base in bases:
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            path = os.path.join(base, name)
            if not name.startswith(prefixes) or _STAMPED.search(name) or os.path.islink(path):
                continue
            try:
                age = now - _newest_mtime(path, now - LEGACY_AGE_S)
            except OSError:
                continue
            why = ""
            if age < LEGACY_AGE_S:
                why = "modified %d s ago" % age
            elif any(_under(h, path) for h in held):
                why = "a process has it open"
            elif name.startswith("path-trace-") and any(_under(o, path) for o in strace_out):
                why = "a running strace writes to it"
            if why:
                rows.append("KEEP %s %s" % (path, why))
                continue
            verb = "REMOVE" if write else "WOULD-REMOVE"
            rows.append("%s %s %s" % (verb, path, human(tree_size(path))))
            if write:
                _remove(path)
    return rows


# ---- status and CLI ---------------------------------------------------------


def status(
    root: pathlib.Path, *, now: float | None = None, busy: BusyFn | None = None
) -> list[str]:
    """What the next sweep would do, read-only."""
    now = time.time() if now is None else now
    common = pathlib.Path(root) / ".git"
    busy = busy or default_busy(pathlib.Path(root))
    rows = []
    records = common / RECORD_DIR
    for marker in sorted(records.glob("*" + MARKER_SUFFIX)) if records.is_dir() else []:
        lease_id = marker.name[: -len(MARKER_SUFFIX)]
        why = finished_problem(common, lease_id, now, busy=busy)
        rows.append("%s %s%s" % ("WAIT" if why else "SWEEP", lease_id, ": " + why if why else ""))
    return rows or ["no finished leases"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="host_temp")
    ap.add_argument("--root", default=os.getcwd())
    sub = ap.add_subparsers(dest="verb", required=True)
    sw = sub.add_parser("sweep")
    sw.add_argument("--lock-held", action="store_true")
    rc = sub.add_parser("reclaim")
    rc.add_argument("--legacy", action="store_true", required=True)
    rc.add_argument("--write", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    root = main_checkout(args.root)
    if args.verb == "sweep":
        token = os.environ.get(LOCK_HANDOFF_ENV, "") if args.lock_held else ""
        if args.lock_held:
            # Started detached by the Stop hook: yield the CPU to every session's interactive work.
            with contextlib.suppress(OSError):
                os.nice(19)
        for row in sweep(root, lock_held=args.lock_held, token=token):
            print("host-temp: " + row)
    elif args.verb == "reclaim":
        for row in reclaim_legacy(default_bases(), write=args.write):
            print(row)
    else:
        for row in status(root):
            print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())

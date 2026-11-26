"""wl_resprofile: one resource record per python3 exit, and a per-shape rollup.

WHY THIS EXISTS. The Stop hook can only surface an optimisation it can see. Today nothing records what a hook invocation cost, so "sequential work that could parallelise" and "a wait that could be event-driven" are invisible by construction. This module is the CHEAP half of the profiling layer: at interpreter exit it writes ONE JSON line with what the kernel already accounted for.
The tree SAMPLER (per-child lifetimes at a cadence, the thing E1/E2/E3 need) is a separate component; conflating the two is how a profiler ends up sampling itself.

WHAT IS RECORDED, and what is deliberately NOT.
  * `cpu` user+sys for SELF and CHILDREN via getrusage -- the only place a
    child's peak memory exists (ru_maxrss, KiB on Linux, a MAX over children and
    never a sum).
  * `io` all FOUR of rchar/wchar/read_bytes/write_bytes from /proc/self/io.
    Never one without the other: read_bytes is 0 for a page-cache hit and rchar
    bills cache hits at device prices. ru_inblock/ru_oublock are NOT used --
    measured 0 after 50 MB of I/O on this kernel.
  * `psi` the delta of /proc/pressure/{cpu,io} some.total across the process's
    life, labelled `scope: container` when /proc/self/cgroup is `0::/` (the devbox)
    and `scope: machine` otherwise (the host's shared init.scope). It is AMBIENT
    context -- what the box was doing while this ran -- and is never attributed to
    the process. The two scopes must never be compared as if they were one thing.
  * `avail` flags for the signals that are STRUCTURALLY dead here
    (kernel.sched_schedstats=0, kernel.task_delayacct=0). They are emitted as
    {available: false}, never as a value: an instrument that reports "0 runqueue
    wait" when it cannot see the runqueue is the same defect as a profiler that
    reports "0 CPU" because it sampled nothing (.ci/scripts/ci/profiler/report.awk).
  * `shape` is `py:<repo-relative argv[0]>[#<--verb>]`. NEVER argv beyond that,
    never cwd beyond a boolean, never environment. This is a public repo and a
    command line can carry a secret; the shape key's whole image is a set of
    strings that already exist in the public tree. The selftest plants a
    secret-shaped token in argv and asserts it is absent from the record.

SAFETY. This runs at the exit of every python3 that imports wl_core -- the ~880 invocations the case suite makes, every Stop hook, every CLI verb. It must never change an exit code, never write to stdout/stderr, never raise. Every path
is wrapped; the off switch is WORKLIST_PROFILE=off (the WORKLIST_* prefix is what
the suite's ambient scrub already unsets). Scope is by cwd: a python3 run outside the repo root records nothing.

STORAGE. Tier 0 is an append-only JSONL beside the worklist store, <worklist>.resprofile.jsonl, written with O_APPEND so concurrent exits never need a lock (a line under PIPE_BUF is atomic). Tier 1, <worklist>.resprofile.json, is the per-shape rollup with the SAME record shape as .ci/cache/gate-durations.json
({ewma, recent[5]}), because that shape already paid for one lesson: a single
overlapping run pushed a 4.5 s gate's ewma to 21 s, and the FLOOR of five recent measurements is what stayed honest. `fold()` folds tier 0 into tier 1 and truncates tier 0. One battery run of tier-0 lines is larger than the whole worklist event log took three days to become, so tier 0 must not persist.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import re
import resource
import sys
import tempfile
import time
from pathlib import Path

RECENT_KEEP = 5
# Per-shape day counts kept in the rollup: enough to tell a shape that ran yesterday from one that last ran a month ago, which is the question a retirement decision asks.
DAYS_KEEP = 30
# A lease or landing tree records under its own slug, and its script paths are repo-relative to the main checkout when run from there: the `.claude/<trees>/<id>/` prefix is folded away so one script is one shape.
_WORKTREE_PREFIX = re.compile(r"^(py|sh):\.claude/worktrees/[^/]+/")
# A slug made from a temporary directory: pytest base temps and anything under /tmp or /var/tmp. Such a directory is gone the moment its run ends, so its records are fixtures and its folder is removed outright. A pytest base temp is `pytest-of-<user>-pytest-<n>`, so the `pytest-of-` alternative needs its `-pytest-<n>` tail: a repo whose path merely contains `pytest-of-` is not a fixture (review 30d7d05c.3).
_TMP_SLUG = re.compile(r"^(tmp|var-tmp)-|pytest-of-.+?-pytest-\d+")
# Raw day folders older than this are pruned by fold(). Two weeks is enough to bisect a regression; the ROLLUP and RANK.md are kept forever and are what anyone actually reads.
RAW_RETENTION_DAYS = 14
EWMA_ALPHA = 0.3
# A Bash tool call's id: `<pid>-<start ns>`, exported once by bash_env.sh and inherited by every process the call starts.
CALL_ID = re.compile(r"^\d+-\d+$")
# Days whose per-id counts stay in the rollup (the percentiles of older days are kept, the ids dropped).
CALL_IDS_DAYS = 2
_T0 = time.monotonic()
_PSI0: dict[str, int] = {}
# install() has armed this process. Module state, not the environment: a child inherits the environment, never this.
_ARMED: list[bool] = []


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _psi_some_total(name: str) -> int | None:
    """some.total in microseconds, or None when PSI is absent."""
    txt = _read("/proc/pressure/%s" % name)
    for line in txt.splitlines():
        if line.startswith("some "):
            for tok in line.split():
                if tok.startswith("total="):
                    try:
                        return int(tok[6:])
                    except ValueError:
                        return None
    return None


def _scope() -> str:
    cg = _read("/proc/self/cgroup").strip()
    return "container" if cg == "0::/" else "machine"


def _sysctl_on(name: str) -> bool:
    return _read("/proc/sys/kernel/%s" % name).strip() == "1"


def _run_delay_ns() -> int | None:
    """Cumulative nanoseconds this task spent RUNNABLE-but-not-running, or None.

    Field 2 of /proc/self/schedstat. None means the field is absent or unparseable -- the only honest reading of "unavailable". A value of 0 is a MEASUREMENT (the task never waited), not an absence.
    """
    try:
        f = _read("/proc/self/schedstat").split()
        return int(f[1]) if len(f) >= 3 else None
    except (ValueError, IndexError):
        return None


def repo_root() -> Path | None:
    """The repo this module lives in: <repo>/.claude/hooks/stop/wl_resprofile.py."""
    try:
        return Path(__file__).resolve().parents[3]
    except (IndexError, OSError):
        return None


def in_scope(cwd: str | None = None) -> bool:
    root = repo_root()
    if root is None:
        return False
    try:
        c = Path(cwd or os.getcwd()).resolve()
    except OSError:
        return False
    return c == root or root in c.parents


def shape_key(argv: list[str] | None = None, root: Path | None = None) -> str:
    """`py:<repo-relative script>[#<--verb>]`; argv beyond the verb is never read."""
    argv = sys.argv if argv is None else argv
    root = repo_root() if root is None else root
    script = argv[0] if argv else ""
    try:
        rel = str(Path(script).resolve().relative_to(root)) if root else Path(script).name
    except (ValueError, OSError):
        rel = "<external>"
    verb = ""
    if (
        len(argv) > 1
        and argv[1].startswith("--")
        and len(argv[1]) <= 24
        and argv[1][2:].replace("-", "").isalnum()
    ):
        verb = "#" + argv[1][2:]
    return "py:%s%s" % (rel, verb)


def stats_root() -> Path | None:
    """~/.claude/resprofile/<repo-slug>/ -- durable, outside the tree, per repo.

    THE OPERATOR'S RULING (2026-09-03): keep the statistics in a folder, TIME-BASED, so what to optimise can be decided from results ranked high to low impact. That supersedes the earlier "tier 0 never persists": the raw stream is kept, one folder per day, because ranking needs the history and no record carries command text. RESPROFILE_ROOT overrides it (the suite points it at a
    fixture).
    """
    override = os.environ.get("RESPROFILE_ROOT")
    if override:
        return Path(override)
    root = repo_root()
    if root is None:
        return None
    slug = str(root).strip("/").replace("/", "-")
    return Path.home() / ".claude" / "resprofile" / slug


def day_dir(when: float | None = None) -> Path | None:
    base = stats_root()
    if base is None:
        return None
    d = base / time.strftime("%Y-%m-%d", time.gmtime(when if when is not None else time.time()))
    with contextlib.suppress(OSError):
        d.mkdir(parents=True, exist_ok=True)
    return d


def store_paths() -> tuple[Path, Path] | None:
    """(today's exit-record jsonl, the per-shape rollup) under the day folder."""
    d = day_dir()
    if d is None:
        return None
    return d / "exit.jsonl", stats_root() / "rollup.json"


def _call_field() -> dict[str, str]:
    """{"call": <id>} when this process descends from a profiled Bash tool call, else nothing: a malformed value is left out rather than recorded."""
    call = os.environ.get("BASHCOV_CALL", "")
    return {"call": call} if CALL_ID.match(call) else {}


def record(argv: list[str] | None = None) -> dict | None:
    """The tier-0 record for THIS process, or None when out of scope / switched off."""
    if os.environ.get("WORKLIST_PROFILE") == "off":
        return None
    if not in_scope():
        return None
    rs = resource.getrusage(resource.RUSAGE_SELF)
    rc = resource.getrusage(resource.RUSAGE_CHILDREN)
    io: dict[str, int] = {}
    for line in _read("/proc/self/io").splitlines():
        k, _, v = line.partition(":")
        if k in ("rchar", "wchar", "read_bytes", "write_bytes"):
            with contextlib.suppress(ValueError):
                io[k] = int(v)
    hwm = None
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmHWM:"):
            with contextlib.suppress(IndexError, ValueError):
                hwm = int(line.split()[1])
    psi = {}
    for name in ("cpu", "io"):
        now = _psi_some_total(name)
        then = _PSI0.get(name)
        psi[name] = (now - then) if (now is not None and then is not None) else None
    return {
        "v": 1,
        "t": int(time.time() * 1000),
        "shape": shape_key(argv),
        **_call_field(),
        "wall_ms": int((time.monotonic() - _T0) * 1000),
        "cpu_ms": int((rs.ru_utime + rs.ru_stime) * 1000),
        "child_cpu_ms": int((rc.ru_utime + rc.ru_stime) * 1000),
        "rss_kb": hwm if hwm is not None else rs.ru_maxrss,
        "child_rss_kb_max": rc.ru_maxrss,
        "io": io,
        "psi_us": psi,
        "scope": _scope(),
        "run_delay_ns": _run_delay_ns(),
        "avail": {
            # PROBED, not read from the sysctl, and that correction is measured. kernel.sched_schedstats is 0 on this kernel and field 2 of /proc/<pid>/schedstat is live anyway: two burners pinned to one core
            # read run_delay=752ms while a third alone on its own core read 0. The
            # old line reported a working instrument as dead, which is the mirror image of trusting a flag over a measurement -- and run-delay is the counter-signal that stops a "parallelise this" verdict on a box that is already oversubscribed, so throwing it away was expensive.
            #
            # Read it on an IDLE process and it is 0, which looks exactly like the sysctl being right. The probe asks whether the FIELD PARSES, never whether this particular process happened to wait.
            "run_delay": _run_delay_ns() is not None,
            "delayacct": _sysctl_on("task_delayacct"),
        },
        "fixture": bool(
            os.environ.get("TMPDIR", "").startswith(tempfile.gettempdir())
            and "hookfix" in os.environ.get("TMPDIR", "")
        ),
    }


def append(rec: dict, paths: tuple[Path, Path] | None = None) -> bool:
    paths = store_paths() if paths is None else paths
    if paths is None:
        return False
    t0, _ = paths
    try:
        line = (json.dumps(rec, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(str(t0), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def fold(paths: tuple[Path, Path] | None = None) -> dict | None:
    """Fold tier 0 into the per-shape tier-1 rollup, then truncate tier 0.

    Only `cpu_ms` and `rss_kb` are rolled up -- the two numbers this repo has actually been burned by (shellcheck at 2714 MB peak OOM-killing the shell gate).
    Same {ewma, recent[5]} shape as gate-durations.json, and the FLOOR of `recent`
    is the oracle a consumer should judge, never the ewma alone.
    """
    paths = store_paths() if paths is None else paths
    if paths is None:
        return None
    t0, t1 = paths
    try:
        roll = json.loads(t1.read_text(encoding="utf-8")) if t1.exists() else {}
    except (OSError, ValueError):
        roll = {}
    if roll.get("format") not in (None, 1):
        return None  # a future format is refused by name, never reinterpreted
    if _stop_process():
        # OFF THE STOP PATH (agent/plans/PLAN-tooling-speed.md D3): the Stop hook reads the rollup as it stands; the sampler (wl_ressample --watch, started for every gate of a local CI run) does the folding.
        return roll
    import fcntl

    try:
        # tree-write: safe t1 is the rollup under stats_root(), ~/.claude/resprofile/<slug> or $RESPROFILE_ROOT, outside every checkout
        with open(str(t1) + ".lock", "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return roll  # another fold holds the lock and folds these lines
            return _fold_locked(roll, t0, t1)
    except OSError:
        return None


def _read_new(path: Path, cursors: dict) -> tuple[bytes, int]:
    """The bytes of `path` past its stored cursor and the length of their complete-line prefix; the cursor moves to the end of that prefix."""
    start = int(cursors.get(str(path), 0))
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            if start > size:
                start = 0  # the stream was replaced under the cursor: fold it from the top
            fh.seek(start)
            data = fh.read(size - start)
    except OSError:
        data = b""
    end = data.rfind(b"\n") + 1
    cursors[str(path)] = start + end
    return data, end


def _fold_calls(roll: dict, t0: Path, cursors: dict, exit_rows: list[dict]) -> None:
    """Per-call process counts: every row of one Bash tool call carries the same `call` id (bash_env.sh exports it once), so a call's process count is the number of rows with its id.

    Rows from exit.jsonl (python processes) and its sibling bash.jsonl (the supervisor's shells) are counted together. A row without a usable id is UNKEYED: counted per day and in `unkeyed_rows`, never merged into a call and never dropped. The per-id counts are kept for the last CALL_IDS_DAYS days only, so a call whose rows span two folds still adds up; the percentiles are recomputed from them each fold.
    """
    rows = list(exit_rows)
    data, end = _read_new(t0.parent / "bash.jsonl", cursors)
    for ln in data[:end].decode("utf-8", "replace").splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("shape") and not row.get("fixture"):
            rows.append(row)
    ids = roll.setdefault("call_ids", {})
    per_call = roll.setdefault("per_call", {})
    for row in rows:
        t = row.get("t")
        day = (
            time.strftime("%Y-%m-%d", time.gmtime(t / 1000))
            if isinstance(t, int)
            else t0.parent.name
        )
        call = row.get("call")
        if isinstance(call, str) and CALL_ID.match(call):
            slot = ids.setdefault(day, {})
            slot[call] = int(slot.get(call, 0)) + 1
        else:
            ent = per_call.setdefault(day, {})
            ent["unkeyed"] = int(ent.get("unkeyed", 0)) + 1
            roll["unkeyed_rows"] = int(roll.get("unkeyed_rows", 0)) + 1
    for day, slot in ids.items():
        counts = sorted(slot.values())
        ent = per_call.setdefault(day, {})
        ent.update(calls=len(counts), p50=_pct(counts, 50), p90=_pct(counts, 90), max=counts[-1])
    for old in sorted(ids)[:-CALL_IDS_DAYS]:
        del ids[old]
    for old in sorted(per_call)[:-DAYS_KEEP]:
        del per_call[old]


def _pct(sorted_counts: list[int], pct: int) -> int:
    """Nearest-rank percentile of an ascending list."""
    rank = -(-len(sorted_counts) * pct // 100)
    return sorted_counts[max(rank, 1) - 1]


def _stop_process() -> bool:
    """True when this process is worklist.py running a Stop (its `_RUN["stop"]` flag)."""
    run = getattr(sys.modules.get("__main__"), "_RUN", None)
    return isinstance(run, dict) and bool(run.get("stop"))


def _fold_locked(roll: dict, t0: Path, t1: Path) -> dict | None:
    """The fold itself, under the rollup lock. Reads from the stored BYTE cursor to the last complete line, so a fold costs the new records only, never the whole day's stream."""
    shapes = roll.setdefault("shapes", {})
    n_lines = 0
    n_fixture = 0
    cursors = roll.setdefault("cursor_bytes", {})
    if str(t0) not in cursors and str(t0) in roll.get("cursor", {}):
        # A rollup folded by the LINE cursor: its position in today's stream becomes a byte offset once, so no record is folded twice.
        lines_done = int(roll["cursor"][str(t0)])
        with contextlib.suppress(OSError), open(t0, "rb") as fh:
            cursors[str(t0)] = sum(len(next(fh, b"")) for _ in range(lines_done))
    data, end = _read_new(t0, cursors)
    roll.pop("cursor", None)
    exit_rows: list[dict] = []
    for ln in data[:end].decode("utf-8", "replace").splitlines():
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if rec.get("v") != 1 or not rec.get("shape"):
            continue
        if rec.get("fixture"):
            # A test fixture's process is not the tool's cost: folding it ranked the suite's own scaffolding beside real work.
            n_fixture += 1
            continue
        n_lines += 1
        exit_rows.append(rec)
        ent = shapes.setdefault(canonical_shape(rec["shape"]), {"n": 0})
        ent["n"] = int(ent.get("n", 0)) + 1
        if isinstance(rec.get("t"), int):
            day = time.strftime("%Y-%m-%d", time.gmtime(rec["t"] / 1000))
            days = ent.setdefault("days", {})
            days[day] = int(days.get(day, 0)) + 1
            for old in sorted(days)[:-DAYS_KEEP]:
                del days[old]
            if day > str(ent.get("last_seen", "")):
                ent["last_seen"] = day
        for key in ("cpu_ms", "rss_kb"):
            val = rec.get(key)
            if not isinstance(val, int):
                continue
            slot = ent.setdefault(key, {"ewma": val, "recent": []})
            slot["ewma"] = round(slot["ewma"] * (1 - EWMA_ALPHA) + val * EWMA_ALPHA)
            slot["recent"] = ([*slot.get("recent", []), val])[-RECENT_KEEP:]
    _fold_calls(roll, t0, cursors, exit_rows)
    roll["format"] = 1
    roll["pruned"] = prune_all_daily()
    roll["refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    roll["folded_lines"] = n_lines
    roll["skipped_fixture_lines"] = n_fixture
    try:
        # tree-write: safe t1 is the rollup under stats_root(), ~/.claude/resprofile/<slug> or $RESPROFILE_ROOT, outside every checkout
        fd, tmp = tempfile.mkstemp(dir=str(t1.parent), prefix=t1.name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(roll, fh, indent=1, sort_keys=True)
        # tree-write: safe the same rollup, replaced atomically beside itself
        os.replace(tmp, t1)
        # NOT truncated any more: the day folder IS the corpus (operator ruling, see stats_root). The rollup remembers how far it has folded via `cursor_bytes`.
    except OSError:
        return None
    return roll


def canonical_shape(shape: str) -> str:
    """`shape` with a lease tree's `.claude/<trees>/<id>/` prefix folded away, so a script run from a lease tree and from the main checkout is one shape."""
    return _WORKTREE_PREFIX.sub(r"\1:", shape)


def prune(root: Path | None = None, keep_days: int = RAW_RETENTION_DAYS) -> list[str]:
    """Delete raw day folders older than keep_days; return the names removed.

    The rollup and RANK.md live at the ROOT, not inside a day folder, so pruning raw captures never costs a ranked number -- fold() has already extracted them. Measured 2026-09-03: one day of real use is 32 MB / 2,363 files, so an unbounded corpus is ~1 GB a month of data whose only consumer already read it.
    """
    import re
    import shutil

    base = root or stats_root()
    if base is None or not base.is_dir():
        return []
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - keep_days * 86400))
    gone = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name) or d.name >= cutoff:
            continue
        with contextlib.suppress(OSError):
            shutil.rmtree(d)
            gone.append(d.name)
    return gone


def prune_top() -> Path | None:
    """~/.claude/resprofile, the folder every repo's slug sits in. None under RESPROFILE_ROOT: that override names ONE repo's folder (a fixture), and what sits beside it is not the profiler's to delete."""
    if os.environ.get("RESPROFILE_ROOT"):
        return None
    base = stats_root()
    return base.parent if base is not None else None


def _cutoff(keep_days: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - keep_days * 86400))


def _newest_day(slug: Path) -> str:
    """The newest `YYYY-MM-DD` folder name under `slug`, "" when there is none."""
    names = [
        d.name for d in slug.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
    ]
    return max(names, default="")


def prune_all(
    top: Path | None = None, keep_days: int = RAW_RETENTION_DAYS, keep: Path | None = None
) -> dict:
    """Prune every repo folder under the resprofile top directory, not only this repo's; return what went, counted.

    * a temporary or pytest slug (`_TMP_SLUG`) is removed outright, whatever its age, unless it is the `keep` folder (a repo checked out under /tmp owns a tmp-named live profile): its directory no longer exists and its records are fixtures;
    * a stray day folder at the top (written while a recorder resolved its root to `/`) goes once it is past `keep_days`;
    * every other slug loses its day folders past `keep_days` (prune), and the whole slug goes when no day folder is left and its newest one is past `keep_days` too: a lease or clone nobody has run in that long. `keep` (this repo's own folder) is never removed whole, so its rollup stays.

    Measured 2026-11-23: 37,291 folders under ~/.claude/resprofile, most of them per-test pytest slugs and per-lease slugs that the per-repo prune never visited. A folder that cannot be removed is counted under `errors`, never skipped unsaid.
    """
    import shutil

    top = top or prune_top()
    keep = keep if keep is not None else stats_root()
    out = {"tmp": 0, "stale": 0, "days": 0, "errors": 0}
    if top is None or not top.is_dir():
        return out
    cutoff = _cutoff(keep_days)
    for d in sorted(top.iterdir()):
        if not d.is_dir() or d.is_symlink():
            continue
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name):
                if d.name < cutoff:
                    shutil.rmtree(d)
                    out["days"] += 1
                continue
            is_keep = keep is not None and d.resolve() == keep.resolve()
            if _TMP_SLUG.search(d.name) and not is_keep:
                shutil.rmtree(d)
                out["tmp"] += 1
                continue
            # Judged before the day prune below, which itself moves the folder's mtime to now.
            stale = (
                _newest_day(d) < cutoff and (time.time() - d.stat().st_mtime) > keep_days * 86400
            )
            if stale and not is_keep:
                shutil.rmtree(d)
                out["stale"] += 1
                continue
            out["days"] += len(prune(d, keep_days))
        except OSError:
            out["errors"] += 1
    return out


def prune_all_daily(top: Path | None = None) -> dict | None:
    """prune_all at most once a UTC day per top directory (a stamp file beside the slugs), since a fold runs many times a day and the top holds tens of thousands of folders. None when today's prune already ran; this repo's folder alone under RESPROFILE_ROOT."""
    top = top or prune_top()
    if top is None:
        # Under RESPROFILE_ROOT only that folder's own day folders are pruned, as before the walk existed.
        return {"tmp": 0, "stale": 0, "days": len(prune()), "errors": 0}
    stamp = top / ".pruned-day"
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with contextlib.suppress(OSError):
        if stamp.read_text(encoding="utf-8").strip() == today:
            return None
    got = prune_all(top)
    with contextlib.suppress(OSError):
        stamp.write_text(today + "\n", encoding="utf-8")
    return got


def _on_exit() -> None:
    try:
        rec = record()
        if rec is not None:
            append(rec)
    # swallowed-failure-ok: this runs at interpreter exit of every hook process, so a failure here must never change that process's exit status or output; a dropped record shows as a missing row in the rollup, never as a failed hook.
    except BaseException:
        pass


def install() -> None:
    """Arm the exit recorder. Idempotent; never raises."""
    try:
        if os.environ.get("WORKLIST_PROFILE") == "off":
            return
        # CLAIM THE PROCESS. sitecustomize.py (.claude/hooks/profile/py/) arms a minimal recorder in EVERY python3 at interpreter startup; this module is the richer one and runs only where wl_core is imported. The marker tells the minimal handler to stand down at exit, so a hook process writes one record, not two. It names THIS pid: a child inherits the environment, and a marker naming its parent must not stand the child down.
        # Idempotent across module objects too: the env marker names THIS pid, so a second copy of this module (loaded under another name) finds it and stands down, while a child process (another pid) is not fooled by its parent's marker.
        mine = "super:%d" % os.getpid()
        if _ARMED or os.environ.get("_WL_SITEPROFILE") == mine:
            return
        os.environ["_WL_SITEPROFILE"] = mine
        _ARMED.append(True)
        for name in ("cpu", "io"):
            v = _psi_some_total(name)
            if v is not None:
                _PSI0[name] = v
        atexit.register(_on_exit)
    # swallowed-failure-ok: install() runs at import of wl_core in every hook process, so a failure to arm must never take the hook down; an unarmed process shows as a missing row in the rollup.
    except BaseException:
        pass


def selftest() -> int:
    """Control-first, on a scratch store. Returns the failure count."""
    import shutil

    import wl_common

    check = wl_common.Checker("indent")

    d = Path(tempfile.mkdtemp(prefix="resprofile-"))
    paths = (d / "wl.resprofile.jsonl", d / "wl.resprofile.json")
    # HERMETIC: every fold below runs the daily prune, and without the override that walk is the real ~/.claude/resprofile, every repo's folder. The selftest prunes only its own scratch root.
    saved_root = os.environ.get("RESPROFILE_ROOT")
    os.environ["RESPROFILE_ROOT"] = str(d / "rp")
    try:
        # THE LEAK CONTROL, first because it is the one that matters on a public repo.
        planted = "ghp_THISLOOKSLIKEATOKEN0000000000000000"
        rec = record(argv=[__file__, "--tick", "74de73ca", planted])
        check("a record is produced inside the repo", rec is not None)
        blob = json.dumps(rec)
        check(
            "PLANT: a secret-shaped argv token never reaches the record",
            planted not in blob,
            blob[:200],
        )
        check(
            "shape carries only the repo-relative script and the verb",
            rec is not None and rec["shape"] == "py:.claude/hooks/stop/wl_resprofile.py#tick",
            str(rec and rec["shape"]),
        )
        check(
            "all four io counters present, never one without the other",
            rec is not None and set(rec["io"]) == {"rchar", "wchar", "read_bytes", "write_bytes"},
            str(rec and rec["io"]),
        )
        check(
            "dead signals are emitted as availability flags, not values",
            rec is not None
            and set(rec["avail"]) == {"run_delay", "delayacct"}
            and all(isinstance(v, bool) for v in rec["avail"].values()),
        )
        check(
            "scope is labelled machine|container",
            rec is not None and rec["scope"] in ("machine", "container"),
        )

        check(
            "append writes one line",
            rec is not None and append(rec, paths) and paths[0].read_text().count("\n") == 1,
        )
        for _ in range(6):
            append(rec, paths)
        roll = fold(paths)
        check("fold produces the rollup", roll is not None and roll.get("format") == 1)
        ent = (roll or {}).get("shapes", {}).get(rec["shape"], {}) if rec else {}
        check("rollup counts every line", ent.get("n") == 7, str(ent))
        check(
            "recent is capped at RECENT_KEEP=5 (the floor oracle, like gate-durations.json)",
            len(ent.get("cpu_ms", {}).get("recent", [])) == 5,
            str(ent.get("cpu_ms")),
        )
        check(
            "fold KEEPS the day stream (durable, time-based) and advances a cursor instead of truncating",
            paths[0].exists()
            and paths[0].stat().st_size > 0
            and roll is not None
            and roll["cursor_bytes"].get(str(paths[0])) == paths[0].stat().st_size,
            str((roll or {}).get("cursor_bytes")),
        )
        # A second fold with an EMPTY tier 0 must not disturb the rollup.
        n_before = ent.get("n")
        roll2 = fold(paths)
        check(
            "an empty fold is a no-op on counts",
            (roll2 or {}).get("shapes", {}).get(rec["shape"], {}).get("n") == n_before,
        )

        # CONTROLS on the two silence conditions.
        os.environ["WORKLIST_PROFILE"] = "off"
        check("CONTROL: WORKLIST_PROFILE=off records nothing", record() is None)
        del os.environ["WORKLIST_PROFILE"]
        old = day_dir(time.time() - (RAW_RETENTION_DAYS + 3) * 86400)
        fresh = day_dir()
        removed = prune(stats_root())
        check(
            "retention: a day folder past RAW_RETENTION_DAYS is pruned, today's is kept",
            old is not None and fresh is not None and old.name in removed and fresh.is_dir(),
            "removed=%s" % removed,
        )
        check(
            "CONTROL: a cwd outside the repo is out of scope", not in_scope(tempfile.gettempdir())
        )
        check("CONTROL: the repo root itself is in scope", in_scope(str(repo_root())))

        # A future rollup format must be refused, not reinterpreted.
        paths[1].write_text(json.dumps({"format": 99, "shapes": {}}), encoding="utf-8")
        append(rec, paths)
        check("CONTROL: an unknown rollup format is refused by name", fold(paths) is None)
        check(
            "the selftest's prune stayed in its scratch root",
            prune_top() is None and stats_root() == d / "rp",
        )
    finally:
        if saved_root is None:
            os.environ.pop("RESPROFILE_ROOT", None)
        else:
            os.environ["RESPROFILE_ROOT"] = saved_root
        shutil.rmtree(d, ignore_errors=True)
    return check.failures


if __name__ == "__main__":
    if "--prune" in sys.argv:
        # The walk on demand, outside the daily stamp: its counts on stdout, nonzero when a folder could not be removed.
        got = prune_all()
        print(json.dumps(got, sort_keys=True))
        sys.exit(1 if got["errors"] else 0)
    if "--selftest" in sys.argv:
        n = selftest()
        print("%s resprofile selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        sys.exit(1 if n else 0)
    if "--fold" in sys.argv:
        r = fold()
        print(
            json.dumps(
                {
                    "ok": r is not None,
                    "shapes": len((r or {}).get("shapes", {})),
                    "folded_lines": (r or {}).get("folded_lines"),
                }
            )
        )
        sys.exit(0 if r is not None else 1)
    print("usage: wl_resprofile.py --selftest | --fold | --prune", file=sys.stderr)
    sys.exit(2)

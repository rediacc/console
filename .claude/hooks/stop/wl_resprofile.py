"""wl_resprofile: one resource record per python3 exit, and a per-shape rollup.

WHY THIS EXISTS. The Stop hook can only surface an optimisation it can see. Today
nothing records what a hook invocation cost, so "sequential work that could
parallelise" and "a wait that could be event-driven" are invisible by
construction. This module is the CHEAP half of the profiling layer: at interpreter
exit it writes ONE JSON line with what the kernel already accounted for. The tree
SAMPLER (per-child lifetimes at a cadence, the thing E1/E2/E3 need) is a separate
component; conflating the two is how a profiler ends up sampling itself.

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

SAFETY. This runs at the exit of every python3 that imports wl_core -- the
~880 invocations the case suite makes, every Stop hook, every CLI verb. It must
never change an exit code, never write to stdout/stderr, never raise. Every path
is wrapped; the off switch is WORKLIST_PROFILE=off (the WORKLIST_* prefix is what
the suite's ambient scrub already unsets). Scope is by cwd: a python3 run outside
the repo root records nothing.

STORAGE. Tier 0 is an append-only JSONL beside the worklist store,
<worklist>.resprofile.jsonl, written with O_APPEND so concurrent exits never need
a lock (a line under PIPE_BUF is atomic). Tier 1, <worklist>.resprofile.json, is
the per-shape rollup with the SAME record shape as .ci/cache/gate-durations.json
({ewma, recent[5]}), because that shape already paid for one lesson: a single
overlapping run pushed a 4.5 s gate's ewma to 21 s, and the FLOOR of five recent
measurements is what stayed honest. `fold()` folds tier 0 into tier 1 and
truncates tier 0. One battery run of tier-0 lines is larger than the whole
worklist event log took three days to become, so tier 0 must not persist.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

RECENT_KEEP = 5
# Raw day folders older than this are pruned by fold(). Two weeks is enough to bisect a
# regression; the ROLLUP and RANK.md are kept forever and are what anyone actually reads.
RAW_RETENTION_DAYS = 14
EWMA_ALPHA = 0.3
_T0 = time.monotonic()
_PSI0: dict[str, int] = {}


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

    THE OPERATOR'S RULING (2026-09-03): keep the statistics in a folder, TIME-BASED,
    so what to optimise can be decided from results ranked high to low impact. That
    supersedes the earlier "tier 0 never persists": the raw stream is kept, one folder
    per day, because ranking needs the history and no record carries command text.
    RESPROFILE_ROOT overrides it (the suite points it at a fixture).
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
        "wall_ms": int((time.monotonic() - _T0) * 1000),
        "cpu_ms": int((rs.ru_utime + rs.ru_stime) * 1000),
        "child_cpu_ms": int((rc.ru_utime + rc.ru_stime) * 1000),
        "rss_kb": hwm if hwm is not None else rs.ru_maxrss,
        "child_rss_kb_max": rc.ru_maxrss,
        "io": io,
        "psi_us": psi,
        "scope": _scope(),
        "avail": {
            "run_delay": _sysctl_on("sched_schedstats"),
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

    Only `cpu_ms` and `rss_kb` are rolled up -- the two numbers this repo has
    actually been burned by (shellcheck at 2714 MB peak OOM-killing the shell gate).
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
    shapes = roll.setdefault("shapes", {})
    n_lines = 0
    cursors = roll.setdefault("cursor", {})
    start = int(cursors.get(str(t0), 0))
    try:
        lines = t0.read_text(encoding="utf-8").splitlines() if t0.exists() else []
    except OSError:
        lines = []
    cursors[str(t0)] = len(lines)
    for ln in lines[start:]:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if rec.get("v") != 1 or not rec.get("shape"):
            continue
        n_lines += 1
        ent = shapes.setdefault(rec["shape"], {"n": 0})
        ent["n"] = int(ent.get("n", 0)) + 1
        for key in ("cpu_ms", "rss_kb"):
            val = rec.get(key)
            if not isinstance(val, int):
                continue
            slot = ent.setdefault(key, {"ewma": val, "recent": []})
            slot["ewma"] = round(slot["ewma"] * (1 - EWMA_ALPHA) + val * EWMA_ALPHA)
            slot["recent"] = ([*slot.get("recent", []), val])[-RECENT_KEEP:]
    roll["format"] = 1
    roll["pruned"] = prune()
    roll["refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    roll["folded_lines"] = n_lines
    try:
        fd, tmp = tempfile.mkstemp(dir=str(t1.parent), prefix=t1.name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(roll, fh, indent=1, sort_keys=True)
        os.replace(tmp, t1)
        # NOT truncated any more: the day folder IS the corpus (operator ruling, see
        # stats_root). The rollup remembers how far it has folded via `cursor`.
    except OSError:
        return None
    return roll


def prune(root: Path | None = None, keep_days: int = RAW_RETENTION_DAYS) -> list[str]:
    """Delete raw day folders older than keep_days; return the names removed.

    The rollup and RANK.md live at the ROOT, not inside a day folder, so pruning raw
    captures never costs a ranked number -- fold() has already extracted them. Measured
    2026-09-03: one day of real use is 32 MB / 2,363 files, so an unbounded corpus is
    ~1 GB a month of data whose only consumer already read it.
    """
    import re  # noqa: PLC0415
    import shutil  # noqa: PLC0415

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


def _on_exit() -> None:
    try:
        rec = record()
        if rec is not None:
            append(rec)
    except BaseException:  # noqa: BLE001 -- an instrument must never change the thing it measures
        pass


def install() -> None:
    """Arm the exit recorder. Idempotent; never raises."""
    try:
        if os.environ.get("WORKLIST_PROFILE") == "off":
            return
        # CLAIM THE PROCESS. sitecustomize.py (.claude/hooks/profile/py/) arms a
        # minimal recorder in EVERY python3 at interpreter startup; this module is
        # the richer one and runs only where wl_core is imported. The marker tells
        # the minimal handler to stand down at exit, so a hook process writes one
        # record, not two.
        os.environ["_WL_SITEPROFILE"] = "super"
        for name in ("cpu", "io"):
            v = _psi_some_total(name)
            if v is not None:
                _PSI0[name] = v
        atexit.register(_on_exit)
    except BaseException:  # noqa: BLE001
        pass


def selftest() -> int:
    """Control-first, on a scratch store. Returns the failure count."""
    import shutil  # noqa: PLC0415

    bad = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal bad
        print(
            "  %s  %s%s"
            % (
                "PASS" if ok else "FAIL",
                name,
                ("\n        " + detail) if (detail and not ok) else "",
            )
        )
        if not ok:
            bad += 1

    d = Path(tempfile.mkdtemp(prefix="resprofile-"))
    paths = (d / "wl.resprofile.jsonl", d / "wl.resprofile.json")
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
            and roll["cursor"].get(str(paths[0])) == 7,
            str((roll or {}).get("cursor")),
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
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return bad


if __name__ == "__main__":
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
    print("usage: wl_resprofile.py --selftest | --fold", file=sys.stderr)
    sys.exit(2)

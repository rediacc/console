"""The gate OUTCOME LEDGER: every gate execution this machine has seen, local and CI, append-only (PLAN-gate-scheduling-learned section 1).

WHY IT EXISTS. Receipts rotate at 50 (`.ci/cache/receipts/`), `lane-durations.json` and `gate-costs.json` hold timing only, and nothing kept a cross-run pass/fail history. `rediacc_ci.ci.gate_model` derives clock gates, flakes, clusters and the run order from THIS file set, so a row that is wrong here is a scheduling decision that is wrong everywhere.

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_ledger append   < rows.jsonl     long-lived; one row per line
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_ledger backfill [--root R ...] [--export DIR [--gates-with-reds]]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_ledger fold-ci  [--repo O/R] [--limit N] [--no-logs]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_ledger status

LOCATION. `$REDIACC_GATE_LEDGER_DIR`, else `${XDG_STATE_HOME:-~/.local/state}/rediacc-gate-ledger/<origin-slug>/`. Per MACHINE and per origin, shared by every worktree, session and the push clone; state rather than cache, because history older than the receipt window cannot be rebuilt. OFF under `CI=true` unless the variable names a directory (a CI runner is disposable and its rows come in through `fold-ci`).

FILES. `outcomes-YYYY-MM.jsonl` (monthly segments), `ledger.lock` (the append flock, `rediacc_ci.core.jsonl_append`), `fold.lock` + `seen.idx` (one line per folded source, so `backfill` and `fold-ci` are idempotent), and the model's own `model.json`, `reports/`, `claims/`.

ROWS (v1), each one JSON object with `t`:
    run  {t, v, id, src, at, branch, head, tree, salt, clean, whole, base_tree, changed, changed_n, lock_sha, classes, ci}
    g    {t, v, run, gate, outcome, wall_ms, t0_ms, key, key_kind, findings, attr}
    end  {t, v, run, wall_ms, exit, cut}
`src` is one of SOURCES and `outcome` one of OUTCOMES. `at` is the run's START (ISO-8601 UTC); `t0_ms` is the gate's own start offset inside the run, because a clock-driven red is about when the GATE ran, not when the run began (the 2026-10-08 replay has a run that started at 23:48 UTC and ran the gate that went red at 00:00:31). `base_tree` is the tree of the previous run of the same checkout and `changed` the paths between it and `tree`, capped at CHANGED_PATHS_MAX with `changed_n` the uncapped count. `classes` is what the writer derived at write time; the model recomputes classes from `changed` against the CURRENT lock, so they never go stale. `whole` is the receipt's own `whole` (no narrowing flag), which cold start counts. `ci` is null locally and `{run, attempt, job, job_id, event, category}` for a CI job.

THE INPUT KEY (`input_key`): `inputHash` when the receipt has one (kind `input`); else, for a gate that DECLARES paths, sha(defHash, filesHash, salt) (kind `paths`); else the head tree (kind `tree`), or tree plus dirty digest outside a clean checkout (kind `tree+dirty`). `filesHash` alone is NOT a key for a path-less gate: in the 10-08 replay a version gate went green, red, red, red, green with one unchanged filesHash, because the fix was in a file its globs do not name. CARRIED VERDICTS ARE NEVER WRITTEN: a carried gate did not run.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import logging
import os
import pathlib
import queue
import re
import sys
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import TYPE_CHECKING, Any

from rediacc_ci import check_pytest, gitx, log, paths
from rediacc_ci.ci import budget_report, ci_diagnose
from rediacc_ci.core import jsonl_append
from rediacc_ci.well_known import GH_REPO

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

SCHEMA = 1
LEDGER_ENV = "REDIACC_GATE_LEDGER_DIR"
LEDGER_SUBDIR = "rediacc-gate-ledger"
SEGMENT_RE = re.compile(r"^outcomes-(\d{4})-(\d{2})\.jsonl$")
LOCK_NAME = "ledger.lock"
FOLD_LOCK_NAME = "fold.lock"
SEEN_NAME = "seen.idx"
RECEIPTS_REL = (".ci", "cache", "receipts")
LOCK_REL = "scripts/ci-runner/gates.lock.json"

SOURCES = ("prepush", "quick", "ci-step", "ci-nightly", "probe", "backfill")
OUTCOMES = ("pass", "fail", "timeout", "skip", "cancel", "blocked")
ROW_TYPES = ("run", "g", "end")
ATTRIBUTIONS = ("own", "shared-step", "test")
KEY_KINDS = ("input", "paths", "tree", "tree+dirty", "commit")

# The receipt's per-gate verdicts (run.ts's `verdict` union) as ledger outcomes. `deferred` and `ciOnly` gates did not run here: they are written as `skip`, which the model never counts as an observation.
RECEIPT_OUTCOMES = {
    "ok": "pass",
    "fail": "fail",
    "blocked": "blocked",
    "deferred": "skip",
    "ciOnly": "skip",
}
# A CI step's `conclusion` as a ledger outcome; a step with none (still running, never started) writes no row.
STEP_OUTCOMES = {
    "success": "pass",
    "failure": "fail",
    "timed_out": "timeout",
    "cancelled": "cancel",
    "skipped": "skip",
}

# ---- tunables (plan section 8) -------------------------------------------------
# About 32 KB per run x 25 runs a day: 120 days stays near 100 MB, and history older than four months describes a gate set that no longer exists.
LEDGER_RETENTION_DAYS = 120
# The hard ceiling under the retention window, in case run volume grows: oldest segments go first, never the current month.
LEDGER_MAX_BYTES = 256 * 1024 * 1024
# INFERRED (the plan says "changed paths (capped)" without a number): a commit touching more files than this is a sweep, and its classes, not its full path list, are what associations learn from. `changed_n` keeps the true count.
CHANGED_PATHS_MAX = 400
# CI fold-in: the newest completed `ci.yml` runs per event, as budget_report's own sample reads them (one API page each).
CI_EVENTS = ("pull_request", "push", "schedule")
CI_WORKFLOW = "ci.yml"
CI_RUNS_PER_EVENT = 100
# MEASURED 2026-10-08: one run's jobs read costs ~10 s (two paged `gh api` calls of ~160 jobs), serial, so 230 unseen runs would take about 38 min; `gate_model refresh --force` sat silent for 24+ min on that backlog (rc 124, no model.json). A fold now reads the NEWEST unseen runs only, in parallel, inside a deadline.
CI_FOLD_MAX_UNSEEN = 40
CI_FOLD_WORKERS = 6
CI_FOLD_DEADLINE_S = 600.0


# ---------------------------------------------------------------------------- location


class _DaemonPool:
    """A small thread pool whose workers are DAEMON threads. `ThreadPoolExecutor` workers are joined by an interpreter-exit hook, so a worker still inside a `gh` call at the fold deadline would keep the process alive after `shutdown(wait=False)`; a daemon worker is abandoned instead. A raising callable resolves its future with the exception, so the worker survives and the reader sees the error rather than a silent deadline. A BaseException that is not an Exception (SystemExit, KeyboardInterrupt) also resolves the future, then ends that worker thread; the other workers keep running."""

    def __init__(self, workers: int) -> None:
        self._jobs: queue.Queue[tuple[Future[Any], Callable[[], Any]] | None] = queue.Queue()
        self.threads = [
            threading.Thread(target=self._work, daemon=True, name="gate-ledger-fold-%d" % i)
            for i in range(max(1, workers))
        ]
        for t in self.threads:
            t.start()

    def _work(self) -> None:
        while True:
            item = self._jobs.get()
            if item is None:
                return
            fut, call = item
            if fut.set_running_or_notify_cancel():
                try:
                    result = call()
                except Exception as exc:
                    # Handed to the reader through the future; the debug record keeps the traceback.
                    logging.getLogger(__name__).debug("fold worker call raised", exc_info=True)
                    fut.set_exception(exc)
                except BaseException as exc:
                    # SystemExit and KeyboardInterrupt: hand them to the reader, then stop this worker.
                    logging.getLogger(__name__).debug("fold worker call exited", exc_info=True)
                    fut.set_exception(exc)
                    return
                else:
                    fut.set_result(result)

    def submit(self, fn: Callable[..., Any], *args: Any) -> Future[Any]:
        fut: Future[Any] = Future()
        self._jobs.put((fut, lambda: fn(*args)))
        return fut

    def shutdown(self) -> None:
        """Cancel every queued job and tell idle workers to exit; a worker mid-call is left to die with the process."""
        while True:
            try:
                item = self._jobs.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                item[0].cancel()
        for _ in self.threads:
            self._jobs.put(None)


def origin_slug(root: os.PathLike[str] | str | None = None) -> str:
    """`<owner>-<repo>` of `origin`, so two clones of one origin share a ledger and two repositories never do. No origin: `local-<sha(root)[:12]>`."""
    res = gitx.git(["remote", "get-url", "origin"], root=root)
    url = res.stdout.strip() if res.returncode == 0 else ""
    if url:
        tail = re.sub(r"\.git$", "", url.rstrip("/"))
        parts = [p for p in re.split(r"[/:]", tail) if p]
        slug = "-".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        return re.sub(r"[^A-Za-z0-9_.-]", "_", slug)
    where = str(pathlib.Path(root or paths.repo_root()).resolve())
    return "local-" + hashlib.sha256(where.encode("utf-8")).hexdigest()[:12]


def ledger_dir(
    env: dict[str, str] | os._Environ[str] | None = None,
    root: os.PathLike[str] | str | None = None,
) -> pathlib.Path | None:
    """The ledger directory, or None when the ledger is OFF (`CI=true` with no `$REDIACC_GATE_LEDGER_DIR`)."""
    if env is None:
        # Spelled out, one read per name, so the environment registry sees every input this module takes.
        env = {
            LEDGER_ENV: os.environ.get("REDIACC_GATE_LEDGER_DIR", ""),
            "CI": os.environ.get("CI", ""),
            "XDG_STATE_HOME": os.environ.get("XDG_STATE_HOME", ""),
        }
    override = env.get(LEDGER_ENV)
    if override:
        return pathlib.Path(override)
    if env.get("CI") == "true":
        return None
    base = env.get("XDG_STATE_HOME") or str(pathlib.Path.home() / ".local" / "state")
    return pathlib.Path(base) / LEDGER_SUBDIR / origin_slug(root)


def ensure_dir(d: pathlib.Path) -> pathlib.Path:
    # tree-write: safe the ledger directory is $REDIACC_GATE_LEDGER_DIR or under XDG_STATE_HOME / the home directory, never the checkout
    d.mkdir(parents=True, exist_ok=True)
    return d


def segment_name(at: float) -> str:
    t = datetime.datetime.fromtimestamp(at, datetime.UTC)
    return "outcomes-%04d-%02d.jsonl" % (t.year, t.month)


def segments(d: pathlib.Path) -> list[pathlib.Path]:
    """Every outcome segment, oldest month first."""
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if SEGMENT_RE.match(p.name))


# ---------------------------------------------------------------------------- rows


def iso(at: float) -> str:
    return (
        datetime.datetime.fromtimestamp(at, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )


def epoch(stamp: Any) -> float | None:
    """ISO-8601 (`Z` or offset) to epoch seconds; None for anything else."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return None


def sha(*parts: Any) -> str:
    return hashlib.sha256("\n".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def validate(row: Any) -> str | None:
    """None when `row` is a well-formed v1 row, else why not. The model trusts these fields, so the writer refuses what it cannot fold."""
    if not isinstance(row, dict):
        return "not an object"
    t = row.get("t")
    if t not in ROW_TYPES:
        return "t=%r is not one of %s" % (t, "/".join(ROW_TYPES))
    if t == "run":
        if not row.get("id"):
            return "run row without id"
        if row.get("src") not in SOURCES:
            return "src=%r is not one of %s" % (row.get("src"), "/".join(SOURCES))
        if epoch(row.get("at")) is None:
            return "run row without an ISO-8601 at"
        return None
    if not row.get("run"):
        return "%s row without run" % t
    if t == "g":
        if not isinstance(row.get("gate"), str) or not row.get("gate"):
            return "g row without gate"
        if row.get("outcome") not in OUTCOMES:
            return "outcome=%r is not one of %s" % (row.get("outcome"), "/".join(OUTCOMES))
    return None


def append_rows(d: pathlib.Path, rows: list[dict[str, Any]], now: float | None = None) -> int:
    """Append `rows` (already validated) under the ledger lock, each run's rows into the segment of the run's `at` when the batch carries that run row, else the segment of `now`. Returns rows written."""
    if not rows:
        return 0
    ensure_dir(d)
    now = time.time() if now is None else now
    month_of: dict[str, str] = {}
    for r in rows:
        if r.get("t") == "run":
            at = epoch(r.get("at"))
            month_of[str(r["id"])] = segment_name(at if at is not None else now)
    by_seg: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        rid = str(r.get("id") if r.get("t") == "run" else r.get("run"))
        by_seg.setdefault(month_of.get(rid) or segment_name(now), []).append(r)
    for name, batch in sorted(by_seg.items()):
        jsonl_append.append_lines(d / name, d / LOCK_NAME, batch)
    return len(rows)


def read_rows(d: pathlib.Path) -> tuple[list[dict[str, Any]], int]:
    """(rows, malformed line count) across every segment, oldest first. A malformed line (a torn tail, a bad writer) is counted, never fatal: the model reports it as ledger health."""
    rows: list[dict[str, Any]] = []
    bad = 0
    for seg in segments(d):
        try:
            text = seg.read_text(encoding="utf-8")
        except OSError:
            bad += 1
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if validate(row) is None:
                rows.append(row)
            else:
                bad += 1
    return rows, bad


@contextlib.contextmanager
def held(lock_path: pathlib.Path) -> Iterator[None]:
    """An exclusive flock on `lock_path` for the block."""
    with open(lock_path, "w") as handle:
        jsonl_append.flock(handle, jsonl_append.LOCK_EX)
        yield


def rotate(d: pathlib.Path, now: float | None = None) -> list[str]:
    """Drop segments wholly older than LEDGER_RETENTION_DAYS, then the oldest until the set fits LEDGER_MAX_BYTES (never the current month). Returns the names dropped."""
    now = time.time() if now is None else now
    if not d.is_dir():
        return []
    current = segment_name(now)
    cutoff = now - LEDGER_RETENTION_DAYS * 86400
    dropped: list[str] = []
    with held(ensure_dir(d) / LOCK_NAME):
        segs = segments(d)
        for seg in segs:
            m = SEGMENT_RE.match(seg.name)
            if m is None or seg.name == current:
                continue
            year, month = int(m.group(1)), int(m.group(2))
            nxt = datetime.datetime(
                year + (month == 12), month % 12 + 1, 1, tzinfo=datetime.UTC
            ).timestamp()
            if nxt < cutoff:
                seg.unlink()
                dropped.append(seg.name)
        live = segments(d)
        total = sum(p.stat().st_size for p in live)
        for seg in live:
            if total <= LEDGER_MAX_BYTES or seg.name == current:
                break
            total -= seg.stat().st_size
            seg.unlink()
            dropped.append(seg.name)
    return dropped


def read_seen(d: pathlib.Path) -> set[str]:
    try:
        return {ln for ln in (d / SEEN_NAME).read_text(encoding="utf-8").splitlines() if ln}
    except OSError:
        return set()


def mark_seen(d: pathlib.Path, keys: Iterable[str]) -> None:
    blob = "".join(k + "\n" for k in keys)
    if not blob:
        return
    fd = os.open(d / SEEN_NAME, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, blob.encode("utf-8"))
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------- input keys


def clean_digest(dirty: str) -> bool:
    """True when `dirty` is the digest of an EMPTY dirty set: sha256 of no bytes, truncated to the receipt's own width (`_dirty_digest` in the push guard hashes `git status` output)."""
    return bool(dirty) and hashlib.sha256(b"").hexdigest().startswith(dirty)


def global_globs(gates: dict[str, Any]) -> set[str]:
    """The globs EVERY gate of one receipt carries: the runner's global inputs, derived from the receipt itself rather than restated here."""
    sets = [
        set((e.get("inputs") or {}).get("globs") or [])
        for e in gates.values()
        if isinstance(e, dict)
    ]
    return set.intersection(*sets) if sets else set()


def input_key(
    entry: dict[str, Any], *, salt: str, tree: str, dirty: str, globals_: set[str]
) -> tuple[str, str]:
    """(key, kind) for one receipt gate entry; see the module docstring for the rule and why `filesHash` alone is not one."""
    ih = entry.get("inputHash")
    if ih:
        return str(ih), "input"
    own = set((entry.get("inputs") or {}).get("globs") or []) - globals_
    if own and entry.get("defHash") and entry.get("filesHash"):
        return sha("paths", entry["defHash"], entry["filesHash"], salt), "paths"
    if clean_digest(dirty):
        return tree, "tree"
    return sha("tree+dirty", tree, dirty), "tree+dirty"


# ---------------------------------------------------------------------------- receipts


def receipt_rows(
    doc: dict[str, Any],
    *,
    base_tree: str | None,
    changed: list[str] | None,
    lock_sha: str | None,
    src: str = "backfill",
) -> list[dict[str, Any]]:
    """The run, g and end rows of one ci:quick receipt (schema 2). Carried gates are left out."""
    gates = doc.get("gates") or {}
    fin = epoch(doc.get("finishedAt"))
    wall = int(doc.get("wallMs") or 0)
    if fin is None or not isinstance(gates, dict):
        return []
    start = fin - wall / 1000.0
    tree = str(doc.get("headTree") or "")
    salt = str(doc.get("saltHash") or "")
    dirty = str(doc.get("dirtyDigest") or "")
    rid = "bf-" + sha(doc.get("finishedAt"), tree, doc.get("judgedRoot"))[:16]
    changed = list(changed or [])
    run = {
        "t": "run",
        "v": SCHEMA,
        "id": rid,
        "src": src,
        "at": iso(start),
        "branch": doc.get("branch"),
        "head": doc.get("head"),
        "tree": tree,
        "salt": salt,
        "clean": clean_digest(dirty),
        "whole": bool(doc.get("whole")),
        "base_tree": base_tree,
        "changed": changed[:CHANGED_PATHS_MAX],
        "changed_n": len(changed),
        "lock_sha": lock_sha,
        "classes": None,
        "ci": None,
        "root": doc.get("judgedRoot"),
    }
    globals_ = global_globs(gates)
    timeline = doc.get("timeline") or {}
    findings = doc.get("findings") or {}
    out: list[dict[str, Any]] = [run]
    for gid in sorted(gates):
        e = gates[gid]
        if not isinstance(e, dict) or e.get("carriedFrom"):
            continue
        outcome = RECEIPT_OUTCOMES.get(str(e.get("verdict")))
        if outcome is None:
            continue
        tl = timeline.get(gid) or {}
        t_start, t_end = tl.get("start"), tl.get("end")
        key, kind = input_key(e, salt=salt, tree=tree, dirty=dirty, globals_=globals_)
        f = findings.get(gid)
        out.append(
            {
                "t": "g",
                "v": SCHEMA,
                "run": rid,
                "gate": gid,
                "outcome": outcome,
                "wall_ms": (
                    int(t_end - t_start)
                    if isinstance(t_start, int | float) and isinstance(t_end, int | float)
                    else None
                ),
                "t0_ms": int(t_start) if isinstance(t_start, int | float) else None,
                "key": key,
                "key_kind": kind,
                "findings": list(f) if isinstance(f, list) else None,
                "attr": "own",
            }
        )
    out.append(
        {
            "t": "end",
            "v": SCHEMA,
            "run": rid,
            "wall_ms": wall,
            "exit": doc.get("exitCode"),
            "cut": False,
        }
    )
    return out


def worktree_roots(root: pathlib.Path) -> list[pathlib.Path]:
    res = gitx.git(["worktree", "list", "--porcelain"], root=root)
    lines = res.stdout.splitlines() if res.returncode == 0 else []
    out = [pathlib.Path(ln[len("worktree ") :]) for ln in lines if ln.startswith("worktree ")]
    return out or [root]


def load_receipts(roots: Iterable[pathlib.Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(receipts, shape). Every root is searched, and every `judgedRoot` a receipt names is added to the search: the push clone writes receipts that name it, so it is FOUND rather than configured. A receipt read twice (the same finish and tree under two roots) counts once."""
    queue = [pathlib.Path(r) for r in roots]
    searched: list[str] = []
    no_dir: list[str] = []
    unreadable: list[str] = []
    docs: dict[tuple[str, str], dict[str, Any]] = {}
    while queue:
        r = queue.pop(0)
        key = str(r.resolve()) if r.exists() else str(r)
        if key in searched:
            continue
        searched.append(key)
        rdir = r.joinpath(*RECEIPTS_REL)
        if not rdir.is_dir():
            no_dir.append(key)
            continue
        for p in sorted(rdir.glob("*.json")):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unreadable.append(str(p))
                continue
            if not isinstance(doc, dict) or not isinstance(doc.get("gates"), dict):
                unreadable.append(str(p))
                continue
            docs.setdefault((str(doc.get("finishedAt")), str(doc.get("headTree"))), doc)
            jr = doc.get("judgedRoot")
            if isinstance(jr, str) and jr:
                queue.append(pathlib.Path(jr))
    ordered = sorted(docs.values(), key=lambda d: epoch(d.get("finishedAt")) or 0.0)
    return ordered, {"searched": searched, "no_dir": no_dir, "unreadable": unreadable}


def changed_between(root: pathlib.Path, a: str | None, b: str) -> list[str] | None:
    """Paths that differ between trees `a` and `b`, or None when git cannot say (an object this clone lacks)."""
    if not a or not b or a == b:
        return [] if a == b and a else None
    res = gitx.git(["diff", "--name-only", "--no-renames", a, b], root=root)
    if res.returncode != 0:
        return None
    return [ln for ln in res.stdout.splitlines() if ln]


def lock_sha_of(root: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256((root / LOCK_REL).read_bytes()).hexdigest()
    except OSError:
        return None


def backfill_rows(
    docs: list[dict[str, Any]], root: pathlib.Path
) -> tuple[list[tuple[str, list[dict[str, Any]]]], dict[str, int]]:
    """[(seen key, rows)] per receipt in finish order, with `base_tree` the previous receipt of the SAME judged checkout, plus counts."""
    last_tree: dict[str, str] = {}
    lock_sha = lock_sha_of(root)
    out: list[tuple[str, list[dict[str, Any]]]] = []
    counts = {"carried": 0, "no_diff": 0}
    for doc in docs:
        who = str(doc.get("judgedRoot") or "")
        tree = str(doc.get("headTree") or "")
        base = last_tree.get(who)
        changed = changed_between(root, base, tree)
        if changed is None:
            counts["no_diff"] += 1
        counts["carried"] += sum(
            1
            for e in (doc.get("gates") or {}).values()
            if isinstance(e, dict) and e.get("carriedFrom")
        )
        rows = receipt_rows(
            doc, base_tree=base if changed is not None else None, changed=changed, lock_sha=lock_sha
        )
        if rows:
            out.append(("receipt:%s:%s" % (tree, doc.get("finishedAt")), rows))
        last_tree[who] = tree
    return out, counts


def gates_with_reds(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(r["gate"])
        for r in rows
        if r.get("t") == "g" and r.get("outcome") not in ("pass", "skip")
    }


# A replay fixture keeps 16 hex digits of each hash: equality is all the model reads from a key, and 64 bits cannot collide across a few thousand rows.
EXPORT_HASH_LEN = 16
EXPORT_HASH_FIELDS = ("key", "tree", "base_tree", "salt", "head", "lock_sha")
EXPORT_LOCK_FIELDS = ("id", "gate", "slow", "paths", "leaves", "needs", "mutex")
EXPORT_CI_FIELDS = ("kind", "job", "step", "test")


def export(
    dest: pathlib.Path,
    batches: list[tuple[str, list[dict[str, Any]]]],
    root: pathlib.Path,
    only_reds: bool,
) -> dict[str, Any]:
    """Write a replay fixture: `outcomes.jsonl`, `lock.json` (only the lock fields the model reads) and `MANIFEST.json`. With `only_reds`, gates that were green in every receipt are left out; they carry no episode."""
    rows = [r for _k, rs in batches for r in rs]
    keep = gates_with_reds(rows) if only_reds else None
    kept = []
    for r in rows:
        if r.get("t") == "g" and keep is not None and r.get("gate") not in keep:
            continue
        short = dict(r)
        for f in EXPORT_HASH_FIELDS:
            if isinstance(short.get(f), str):
                short[f] = short[f][:EXPORT_HASH_LEN]
        kept.append(short)
    # tree-write: safe --export writes only where its caller points it (a fixture directory the caller then commits, or a temp dir)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "outcomes.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in kept),
        encoding="utf-8",
    )
    lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    slim = []
    for e in lock:
        s = {k: e[k] for k in EXPORT_LOCK_FIELDS if k in e}
        ci = e.get("ci")
        if isinstance(ci, dict):
            s["ci"] = {k: ci[k] for k in EXPORT_CI_FIELDS if k in ci}
        slim.append(s)
    (dest / "lock.json").write_text(
        json.dumps(slim, separators=(",", ":"), sort_keys=True).replace("},{", "},\n{") + "\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_by": "python3 -m rediacc_ci.ci.gate_ledger backfill --export <dir>%s"
        % (" --gates-with-reds" if only_reds else ""),
        "receipts": len(batches),
        "rows": len(kept),
        "rows_dropped_all_green_gates": len(rows) - len(kept),
        "gates_kept": sorted(keep) if keep is not None else "all",
        "hash_chars": EXPORT_HASH_LEN,
        "first": batches[0][1][0]["at"] if batches else None,
        "last": batches[-1][1][0]["at"] if batches else None,
    }
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def backfill(
    d: pathlib.Path | None,
    root: pathlib.Path,
    extra_roots: list[pathlib.Path],
    export_to: pathlib.Path | None = None,
    only_reds: bool = False,
    out: Callable[[str], None] = log.info,
) -> int:
    roots = [*worktree_roots(root), *extra_roots]
    docs, shape = load_receipts(roots)
    for path in shape["unreadable"]:
        log.warn("gate_ledger backfill: unreadable receipt %s" % path)
    if not docs:
        log.error(
            "gate_ledger backfill: 0 receipts under %d root(s) (%s); a backfill that read nothing would report a ledger it did not build"
            % (len(shape["searched"]), ", ".join(shape["searched"]))
        )
        return 1
    batches, counts = backfill_rows(docs, root)
    if export_to is not None:
        man = export(export_to, batches, root, only_reds)
        out(
            "gate_ledger export: %d receipts -> %s (%d rows, %d all-green gate rows dropped)"
            % (man["receipts"], export_to, man["rows"], man["rows_dropped_all_green_gates"])
        )
        return 0
    if d is None:
        log.error("gate_ledger backfill: the ledger is OFF (CI=true and no $%s)" % LEDGER_ENV)
        return 1
    ensure_dir(d)
    written = runs = 0
    with held(d / FOLD_LOCK_NAME):
        seen = read_seen(d)
        fresh = [(k, rs) for k, rs in batches if k not in seen]
        # A crash between the append and mark_seen leaves rows with no seen key; a batch whose deterministic run id is already in the ledger is marked seen and skipped, never appended twice.
        folded = {str(r["id"]) for r in read_rows(d)[0] if r.get("t") == "run"}
        for k, rs in fresh:
            if any(r.get("t") == "run" and str(r.get("id")) in folded for r in rs):
                mark_seen(d, [k])
                continue
            written += append_rows(d, rs)
            mark_seen(d, [k])
            folded.update(str(r["id"]) for r in rs if r.get("t") == "run")
            runs += 1
    dropped = rotate(d)
    out(
        "gate_ledger backfill: %d receipts in %d root(s) (%d without a receipts dir), %d new run(s), %d row(s), %d already folded, %d carried verdict(s) not written, %d without a diff base; rotated %d segment(s); ledger %s"
        % (
            len(docs),
            len(shape["searched"]),
            len(shape["no_dir"]),
            runs,
            written,
            len(batches) - runs,
            counts["carried"],
            counts["no_diff"],
            len(dropped),
            d,
        )
    )
    return 0


# ---------------------------------------------------------------------------- CI fold-in


def _module_of_test(path: str) -> str:
    """`.ci/rediacc_ci/tests/x/test_y.py` -> `.ci.rediacc_ci.tests.x.test_y`, the dotted form pytest-fail finding keys carry."""
    return path[: -len(".py")].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")


def finding_keys(lines: Iterable[str]) -> list[str]:
    """Every `::finding::<key>` in `lines`, in order, de-duplicated; ANSI and timestamps already stripped or tolerated."""
    seen: dict[str, None] = {}
    for line in lines:
        at = line.find(log.FINDING_PREFIX)
        if at < 0:
            continue
        key = line[at + len(log.FINDING_PREFIX) :].strip()
        if log.FINDING_KEY_RE.match(key):
            seen.setdefault(key, None)
    return list(seen)


def lock_ci(root: pathlib.Path) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """({gate: (job id, step)} for step gates, {gate: test path} for test gates), from the lock."""
    steps = budget_report.load_gate_ci_steps(root)
    tests: dict[str, str] = {}
    try:
        lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        lock = []
    for e in lock if isinstance(lock, list) else []:
        ci = e.get("ci") if isinstance(e, dict) else None
        if isinstance(ci, dict) and ci.get("kind") == "test" and isinstance(ci.get("test"), str):
            tests[str(e["id"])] = ci["test"]
    return steps, tests


def _span_ms(obj: dict[str, Any]) -> int | None:
    a, b = epoch(obj.get("started_at")), epoch(obj.get("completed_at"))
    return int((b - a) * 1000) if a is not None and b is not None else None


def ci_rows(
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    steps: dict[str, tuple[str, str]],
    tests: dict[str, str],
    patterns: dict[str, re.Pattern[str]],
    log_lines: Callable[[dict[str, Any]], list[str] | None],
    category_of: Callable[[dict[str, Any], list[str] | None], str | None],
    tree_of: Callable[[str], str | None],
    pytest_hosts: set[str] | frozenset[str] = frozenset(),
    leg_tests: Callable[[str], set[str] | None] | None = None,
) -> list[dict[str, Any]]:
    """Rows for one CI run attempt: one ledger run per JOB that hosts a gate step, its g rows, and its end row.

    A (job, step) pair named by ONE gate gives an `own` row; one shared by several gives each a weak `shared-step` row, because the step's outcome is the sum of all of them. A `ci.kind: test` gate takes its outcome from the pytest step's `pytest-fail:` finding keys (attr `test`): green when its module has none, red when it has one.
    """
    occupancy: dict[tuple[str, str], int] = {}
    for js in steps.values():
        occupancy[js] = occupancy.get(js, 0) + 1
    by_job: dict[str, list[tuple[str, str]]] = {}
    for gid, (job_id, step) in steps.items():
        by_job.setdefault(job_id, []).append((gid, step))
    head = str(run.get("head_sha") or "")
    tree = tree_of(head) if head else None
    key, kind = (tree, "tree") if tree else ("commit:" + head, "commit")
    attempt = run.get("run_attempt") or 1
    event = run.get("event") or ""
    src = "ci-nightly" if event == "schedule" else "ci-step"
    test_modules = {gid: _module_of_test(p) for gid, p in tests.items()}
    out: list[dict[str, Any]] = []
    for job in jobs:
        name = str(job.get("name") or "")
        if job.get("status") != "completed":
            continue
        job_ids = [jid for jid, rx in patterns.items() if rx.fullmatch(name) and jid in by_job]
        if not job_ids:
            continue
        stepmap = {str(s.get("name")): s for s in job.get("steps") or [] if isinstance(s, dict)}
        hosted = [
            (gid, stepmap.get(step), (jid, step)) for jid in job_ids for gid, step in by_job[jid]
        ]
        hosted = [h for h in hosted if h[1] is not None]
        if not hosted:
            continue
        failed = job.get("conclusion") in ("failure", "timed_out", "cancelled")
        lines = (
            log_lines(job)
            if (failed or any((h[1] or {}).get("conclusion") == "failure" for h in hosted))
            else None
        )
        category = category_of(job, lines) if failed else None
        rid = "ci-%s-%s-%s" % (run.get("id"), attempt, job.get("id"))
        at = epoch(job.get("started_at")) or epoch(run.get("run_started_at")) or 0.0
        out.append(
            {
                "t": "run",
                "v": SCHEMA,
                "id": rid,
                "src": src,
                "at": iso(at),
                "branch": run.get("head_branch"),
                "head": head,
                "tree": tree,
                "salt": None,
                "clean": True,
                "whole": False,
                "base_tree": None,
                "changed": [],
                "changed_n": 0,
                "lock_sha": None,
                "classes": None,
                "ci": {
                    "run": run.get("id"),
                    "attempt": attempt,
                    "job": name,
                    "job_id": job.get("id"),
                    "event": event,
                    "category": category,
                },
            }
        )
        keys = finding_keys(lines or [])
        for gid, st, js in hosted:
            outcome = STEP_OUTCOMES.get(str((st or {}).get("conclusion")))
            if outcome is None:
                continue
            s_at = epoch((st or {}).get("started_at"))
            out.append(
                {
                    "t": "g",
                    "v": SCHEMA,
                    "run": rid,
                    "gate": gid,
                    "outcome": outcome,
                    "wall_ms": _span_ms(st or {}),
                    "t0_ms": int((s_at - at) * 1000) if s_at is not None and at else None,
                    "key": key,
                    "key_kind": kind,
                    "findings": keys if outcome == "fail" and lines is not None else None,
                    "attr": "own" if occupancy.get(js, 0) == 1 else "shared-step",
                }
            )
            if gid not in pytest_hosts:
                continue
            # The pytest step: every test gate is judged from its keys. A red step whose keys are unknown (no log) judges none of them.
            if outcome == "fail" and not any(k.startswith("pytest-") for k in keys):
                continue
            if outcome not in ("pass", "fail"):
                continue
            in_leg = leg_tests(name) if leg_tests is not None else None
            for tgid, mod in sorted(test_modules.items()):
                hits = [k for k in keys if k.startswith("pytest-fail:" + mod + "::")]
                # A leg judges only the test files it collects: a green leg says nothing about a module another leg runs. A red key is evidence wherever it appears.
                if not hits and in_leg is not None and tests[tgid] not in in_leg:
                    continue
                out.append(
                    {
                        "t": "g",
                        "v": SCHEMA,
                        "run": rid,
                        "gate": tgid,
                        "outcome": "fail" if hits else "pass",
                        "wall_ms": None,
                        "t0_ms": None,
                        "key": key,
                        "key_kind": kind,
                        "findings": hits or None,
                        "attr": "test",
                    }
                )
        out.append(
            {
                "t": "end",
                "v": SCHEMA,
                "run": rid,
                "wall_ms": _span_ms(job),
                "exit": 0 if job.get("conclusion") == "success" else 1,
                "cut": job.get("conclusion") == "cancelled",
            }
        )
    return out


LEG_RE = re.compile(r"\((\d+)/(\d+)\)\s*$")


def shard_legs(root: pathlib.Path) -> Callable[[str], set[str] | None]:
    """`legs(job display name)`: the test paths the pytest leg `(k/n)` collects per the committed shard manifest, None for an unsharded job, and the EMPTY set when the manifest's leg count is not `n` (a run from before a reshard judges no test gate rather than the wrong ones)."""
    try:
        doc = json.loads((root / check_pytest.QUALITY_PYTEST_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    legs = {
        int(leg["index"]): {str(i).removeprefix("pytest:") for i in leg.get("ids") or []}
        for leg in doc.get("legs") or []
        if isinstance(leg, dict) and isinstance(leg.get("index"), int)
    }

    def of(name: str) -> set[str] | None:
        m = LEG_RE.search(name)
        if m is None:
            return None
        if int(m.group(2)) != doc.get("of"):
            return set()
        return legs.get(int(m.group(1)), set())

    return of


def pytest_hosts(
    root: pathlib.Path, tests: dict[str, str], steps: dict[str, tuple[str, str]]
) -> set[str]:
    """The step gates whose lock `leaves` include the module that EMITS `pytest-fail:` keys (`rediacc_ci.check_pytest`): those steps run the suites the test gates live in. Derived from the emitter's own path, not from a gate name; a path-coverage rule was tried first and matched seven gates whose globs merely contain the tests directory."""
    if not tests:
        return set()
    emitter = paths.relative_to_root(check_pytest.__file__, root=root)
    try:
        lock = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {
        str(e["id"])
        for e in lock
        if isinstance(e, dict) and e.get("id") in steps and emitter in (e.get("leaves") or [])
    }


def _why(exc: BaseException) -> str:
    """The reason an UNCHECKED line carries: the message, or the exception's type when it has none (a bare `sys.exit()` and many OSErrors stringify to empty; review finding de62cb71.3)."""
    return (str(exc) or type(exc).__name__)[:160]


def fold_ci(
    d: pathlib.Path,
    root: pathlib.Path,
    *,
    repo: str,
    limit: int = CI_RUNS_PER_EVENT,
    logs: bool = True,
    fetch_runs: Callable[..., list[dict[str, Any]]] | None = None,
    fetch_jobs: Callable[[str, int], list[dict[str, Any]]] | None = None,
    fetcher: Any = None,
    out: Callable[[str], None] = log.info,
    max_unseen: int = CI_FOLD_MAX_UNSEEN,
    workers: int = CI_FOLD_WORKERS,
    deadline_s: float = CI_FOLD_DEADLINE_S,
    progress: Callable[[str], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Fold completed CI runs into the ledger, idempotently (`ci:<run>:<attempt>` in seen.idx). Exit 1 when any read failed: an unread run is UNCHECKED, never folded as clean.

    Runs already in seen.idx are skipped BEFORE any read. Only the `max_unseen` NEWEST unseen runs are read (older ones are counted, not UNCHECKED: the next fold takes them), their job lists are fetched by a `workers` pool, and one progress line per run goes to stderr. A run whose read is not done when `deadline_s` passes is UNCHECKED and named, so the fold ends instead of hanging."""
    fetch_runs = fetch_runs or budget_report.fetch_runs
    fetch_jobs = fetch_jobs or budget_report.fetch_jobs
    steps, tests = lock_ci(root)
    hosts = pytest_hosts(root, tests, steps)
    legs = shard_legs(root)
    if not steps:
        log.error(
            "gate_ledger fold-ci: the lock maps 0 gates to CI steps; nothing could be attributed"
        )
        return 1
    try:
        patterns = budget_report.lane_display_patterns(root)
    except OSError as exc:
        log.error("gate_ledger fold-ci: cannot read the workflows for job display names: %s" % exc)
        return 1
    if fetcher is None and logs:
        # Two attempts, two seconds apart (the Stop hook's own setting): gh prints an expired log's HTTP 410 as "Server Error (HTTP 410)", which gh_retry reads as transient, so the default 5 s + 15 s backoff cost 20 s per job of every older red run (measured 2026-10-08, run 36348212746).
        fetcher = ci_diagnose.GhFetcher(repo, attempts=2, pause=2)

    def log_lines(job: dict[str, Any]) -> list[str] | None:
        if not logs or fetcher is None:
            return None
        text, _err = ci_diagnose.job_log(fetcher, job.get("id"))
        if text is None:
            return None
        _step, lines, _w = ci_diagnose.evidence(text, job)
        return lines

    def category_of(job: dict[str, Any], lines: list[str] | None) -> str | None:
        if lines is None:
            return "infra-likely" if job.get("conclusion") == "cancelled" and not logs else None
        cat, sig = ci_diagnose.classify(lines)
        return ci_diagnose.cancel_reclassify(job, None, cat, sig)[0]

    trees: dict[str, str | None] = {}

    def tree_of(sha_: str) -> str | None:
        if sha_ not in trees:
            res = gitx.git(["rev-parse", "--verify", "--quiet", sha_ + "^{tree}"], root=root)
            trees[sha_] = res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None
        return trees[sha_]

    unchecked: list[str] = []
    runs: list[dict[str, Any]] = []
    for event in CI_EVENTS:
        try:
            runs.extend(fetch_runs(repo, CI_WORKFLOW, event, None, "completed", limit))
        except (RuntimeError, OSError, ValueError) as exc:  # a failed read is reported as UNCHECKED
            unchecked.append("runs(%s): %s" % (event, _why(exc)))
    runs = list({r.get("id"): r for r in runs}.values())
    ensure_dir(d)
    folded = rows_n = already = 0
    skipped_old = 0
    say = progress or (lambda m: print(m, file=sys.stderr, flush=True))
    t0 = clock()
    with held(d / FOLD_LOCK_NAME):
        seen = read_seen(d)
        todo: list[tuple[str, dict[str, Any]]] = []
        for run in sorted(runs, key=lambda r: str(r.get("created_at") or "")):
            sk = "ci:%s:%s" % (run.get("id"), run.get("run_attempt") or 1)
            if sk in seen:
                already += 1
            else:
                todo.append((sk, run))
        if len(todo) > max_unseen:
            skipped_old = len(todo) - max_unseen
            todo = todo[len(todo) - max_unseen :] if max_unseen > 0 else []
        say(
            "gate_ledger fold-ci: %d unseen run(s) to read (%d older left for the next fold), %d worker(s), %.0f s deadline"
            % (len(todo), skipped_old, workers, deadline_s)
        )

        def read_jobs(run: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str, float]:
            t = clock()
            if t - t0 > deadline_s:
                return None, "deadline", 0.0
            try:
                return fetch_jobs(repo, int(run["id"])), "", clock() - t
            except (RuntimeError, OSError, ValueError, SystemExit) as exc:
                # SystemExit too: left to the future it would re-raise in the reader and exit the folding process.
                return None, _why(exc), clock() - t

        pool = _DaemonPool(workers)
        try:
            futs = [(sk, run, pool.submit(read_jobs, run)) for sk, run in todo]
            for sk, run, fut in futs:
                left = deadline_s - (clock() - t0)
                try:
                    jobs, err, took = fut.result(timeout=max(left, 0.0))
                except FuturesTimeout:
                    jobs, err, took = None, "deadline", 0.0
                if jobs is None:
                    unchecked.append("jobs(%s): %s" % (run.get("id"), err))
                    say("gate_ledger fold-ci: run %s UNCHECKED (%s)" % (run.get("id"), err))
                    continue
                rows = ci_rows(
                    run,
                    jobs,
                    steps=steps,
                    tests=tests,
                    patterns=patterns,
                    log_lines=log_lines,
                    category_of=category_of,
                    tree_of=tree_of,
                    pytest_hosts=hosts,
                    leg_tests=legs,
                )
                rows_n += append_rows(d, rows)
                mark_seen(d, [sk])
                seen.add(sk)
                folded += 1
                say(
                    "gate_ledger fold-ci: run %s folded (%d row(s), jobs read %.1f s) [%d/%d, %.0f s]"
                    % (run.get("id"), len(rows), took, folded, len(todo), clock() - t0)
                )
        finally:
            pool.shutdown()
    rotate(d)
    out(
        "gate_ledger fold-ci: %d run(s) listed over %s, %d folded (%d row(s)), %d already folded, %d older unseen deferred, %d UNCHECKED"
        % (len(runs), "/".join(CI_EVENTS), folded, rows_n, already, skipped_old, len(unchecked))
    )
    for u in unchecked:
        log.error("gate_ledger fold-ci: unchecked %s" % u)
    if not runs and not unchecked:
        log.error(
            "gate_ledger fold-ci: GitHub listed 0 completed runs; a fold that saw nothing is not a clean fold"
        )
        return 1
    return 1 if unchecked else 0


# ---------------------------------------------------------------------------- append / status


def append_stream(
    d: pathlib.Path | None, stream: Iterable[str], out: Callable[[str], None] = log.info
) -> int:
    """The long-lived writer: one JSON row (or a JSON array of rows) per input line, appended as it arrives. A malformed line is refused LOUDLY and the exit is 1 at end of input; the rows around it are still kept."""
    if d is None:
        n = sum(1 for _ in stream)
        out("gate_ledger append: OFF (CI=true and no $%s); %d line(s) discarded" % (LEDGER_ENV, n))
        return 0
    ensure_dir(d)
    rotate(d)
    good = bad = 0
    for line in stream:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            bad += 1
            log.error("gate_ledger append: not JSON: %r" % line[:120])
            continue
        batch = obj if isinstance(obj, list) else [obj]
        ok = []
        for row in batch:
            why = validate(row)
            if why:
                bad += 1
                log.error("gate_ledger append: refused row (%s): %r" % (why, str(row)[:120]))
            else:
                ok.append(row)
        good += append_rows(d, ok)
    out("gate_ledger append: %d row(s) written, %d refused; ledger %s" % (good, bad, d))
    return 1 if bad else 0


def status(d: pathlib.Path | None, out: Callable[[str], None] = log.info) -> int:
    if d is None:
        out("gate_ledger: OFF (CI=true and no $%s)" % LEDGER_ENV)
        return 0
    rows, bad = read_rows(d)
    runs = [r for r in rows if r.get("t") == "run"]
    by_src: dict[str, int] = {}
    for r in runs:
        by_src[str(r.get("src"))] = by_src.get(str(r.get("src")), 0) + 1
    size = sum(p.stat().st_size for p in segments(d))
    out(
        "gate_ledger %s: %d segment(s), %d byte(s), %d run(s) (%s), %d gate row(s), %d malformed line(s), %d folded source(s)"
        % (
            d,
            len(segments(d)),
            size,
            len(runs),
            ", ".join("%s %d" % kv for kv in sorted(by_src.items())) or "none",
            sum(1 for r in rows if r.get("t") == "g"),
            bad,
            len(read_seen(d)),
        )
    )
    return 1 if not runs else 0


def _non_negative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        msg = "must be >= 0, got %d" % value
        raise argparse.ArgumentTypeError(msg)
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gate_ledger", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("append", help="append JSON rows read from stdin, one per line")
    bf = sub.add_parser("backfill", help="fold every ci:quick receipt on this machine")
    bf.add_argument("--root", action="append", default=[], help="an extra checkout to search")
    bf.add_argument(
        "--export", type=pathlib.Path, help="write a replay fixture here instead of the ledger"
    )
    bf.add_argument(
        "--gates-with-reds",
        action="store_true",
        help="with --export: keep only gates that were ever not green",
    )
    fc = sub.add_parser("fold-ci", help="fold completed CI runs (budget_report reads)")
    fc.add_argument("--repo", default=None)
    fc.add_argument("--limit", type=int, default=CI_RUNS_PER_EVENT)
    fc.add_argument("--max-unseen", type=_non_negative_int, default=CI_FOLD_MAX_UNSEEN)
    fc.add_argument("--workers", type=int, default=CI_FOLD_WORKERS)
    fc.add_argument("--deadline", type=float, default=CI_FOLD_DEADLINE_S, help="seconds")
    fc.add_argument(
        "--no-logs",
        action="store_true",
        help="do not read job logs (no categories, no finding keys)",
    )
    sub.add_parser("status", help="print the ledger's shape")
    args = ap.parse_args(argv)
    root = paths.repo_root()
    d = ledger_dir(root=root)
    if args.cmd == "append":
        return append_stream(d, sys.stdin)
    if args.cmd == "backfill":
        return backfill(
            d, root, [pathlib.Path(r) for r in args.root], args.export, args.gates_with_reds
        )
    if args.cmd == "fold-ci":
        if d is None:
            log.error("gate_ledger fold-ci: the ledger is OFF (CI=true and no $%s)" % LEDGER_ENV)
            return 1
        return fold_ci(
            d,
            root,
            repo=args.repo or GH_REPO,
            limit=args.limit,
            logs=not args.no_logs,
            max_unseen=args.max_unseen,
            workers=args.workers,
            deadline_s=args.deadline,
        )
    return status(d)


if __name__ == "__main__":
    raise SystemExit(main())

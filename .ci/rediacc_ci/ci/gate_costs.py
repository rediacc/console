#!/usr/bin/env python3
"""Committed per-gate CPU baseline for ci:quick's scheduler (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.5, task P3).

CI runs each gate as its own workflow step, not through scripts/ci-runner, so no per-gate CPU exists there. The nightly housekeeping job `gate-costs-capture` runs `run.ts --quick --jobs 1 --sched slots --json` serially (so every gate is measured uncontended) and uploads the report as the artifact `gate-costs-<sha>`. This module turns the last `SAMPLE_CAPTURES` of those into `.ci/config/gate-costs.json` (`--refresh`) and checks the committed file against them (`--check`).

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --refresh [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --check
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --validate-capture gate-costs.json

THE FILE'S SCHEMA, defined here beside its only writer:

    {
      "$comment": [...],                 # preserved across --refresh
      "refreshed_at": "2026-10-01T03:30:00Z",
      "source": {"runner": "ubuntu-latest", "cores": 4, "runs": [{"id", "sha", "created_at"}]},
      "gates": {"<gate id>": {"cpu_s", "wall_s", "eff_cores", "capped", "peak_rss_mb", "rank"}},
      "unmeasured": {"<gate id>": "<status in the newest capture that ran it>"},
      "carried": {"<gate id>": "<refreshed_at of the file that measured it>"}
    }

Per gate, each figure is the MEDIAN over the captures in which the gate passed and reported `cpuMs`: `cpu_s` and `wall_s` in seconds, `peak_rss_mb` (null when the sampler captured none). `eff_cores` is cpu_s / wall_s. `capped` is eff_cores >= `CAPPED_FRACTION` x the runner's cores: such a gate used the whole machine, so its width says more about the runner than about the gate and does not port to another machine. `rank` is 1 for the largest cpu_s. A gate the captures ran but never measured (failed, blocked, skipped: the capture runner has no submodules and no Go or uv toolchain) sits in `unmeasured` with its newest status, so a missing baseline is named rather than silently absent.

TWO KINDS OF GATE, BECAUSE `--quick` IS TWO LANES. A capture runs every fast gate, and a slow gate (`slow: true` in the lock, or one whose `needs` reach a slow gate: run.ts's own fixpoint, `sampled_gate_ids`) ONLY when the captured commit's diff touches it (run.ts `quickDiffAdmit`). So a slow gate is DIFF-SAMPLED: present in one capture, absent from the next ones, with nothing wrong. MEASURED 2026-10-07: capture 37294996911 reads `--quick (286 fast gate(s) + 3 diff-selected slow; 66 deferred)`; check:ci-format-scope entered the file from capture 37192382851 (whose diff touched it), and when that capture left the window every PR went red with "no capture measured it (absent in the newest)", the second such red after check:ci-proxy-rdc-update (365933af3). Therefore: a diff-sampled gate absent from EVERY capture in the window is not a finding, and `--refresh` CARRIES its last figures forward (named in `carried`, stamped with when they were measured) rather than dropping them; a diff-sampled gate the captures ran is held to every rule a fast gate is. Both sets are printed by name on every green.

`--check` exits 1 on: a gate in the file that the manifest (`scripts/ci-runner/gates.lock.json`) no longer has (either kind); a FAST gate the fresh captures ran that the file has in neither `gates` nor `unmeasured` (registered after the last refresh); a committed fast gate no fresh capture measured, or a committed diff-sampled gate a fresh capture ran and could not measure; cpu_s drifting more than `DRIFT_THRESHOLD` where either side is at least `MIN_DRIFT_CPU_S`; eff_cores drifting the same way where neither side is capped (the same floor applies, since the width of a sub-second gate is noise); a changed runner core count; zero usable captures. It exits `NO_BASELINE` (3) and prints a notice when the file does not exist yet. Nothing was compared, and its one caller, `rediacc_ci.ci.freshness --check` (`.ci/config/freshness.json`, run per PR as `check:ci-budget-freshness` and nightly by housekeeping.yml's budget-check job), fails on it; that registry also refuses the missing file before this check runs. The first real file comes from `--refresh` after the first nightly capture, never from invented numbers.

The Actions API reads reuse budget_report's `fetch_runs`/`fetch_artifacts`/`download_artifact_zip` (retrying, ghx-backed, a failed call raises rather than reading as empty).
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

from rediacc_ci import paths
from rediacc_ci.ci import budget_report
from rediacc_ci.core import ghx

GATE_COSTS_REL_PATH = ".ci/config/gate-costs.json"
GATES_LOCK_REL_PATH = budget_report.GATES_LOCK_REL_PATH
CAPTURE_WORKFLOW = "housekeeping.yml"
CAPTURE_EVENTS = ("schedule", "workflow_dispatch")
CAPTURE_RUNNER = "ubuntu-latest"
ARTIFACT_PREFIX = "gate-costs-"
# How many captures the medians span, and how many runs per event are listed to find them (a housekeeping run whose capture job failed carries no artifact).
# THREE BECAUSE THE REPOSITORY KEEPS ARTIFACTS 3 DAYS (operator ruling 2026-10-07, "Keep 3 days"; recorded in .ci/config/actions-retention.json and enforced on every `retention-days:` by check:ci-workflows). GitHub caps each upload there whatever the workflow asks for: gate-costs-c277f2ab asked for 30 and expired three days after its 2026-10-05 capture. One nightly capture per day leaves at most three alive, so a window of five was two captures that never existed, and the medians quietly spanned three. housekeeping.yml's slow-gate rotation is 3-way for the same reason. test_sample_captures_fits_the_recorded_retention holds this at or under the record.
SAMPLE_CAPTURES = 3
RUNS_LISTED = 15
# The same 25% budget_report.py's --check applies to lane-durations.json.
DRIFT_THRESHOLD = budget_report.DRIFT_THRESHOLD
MIN_DRIFT_CPU_S = 1.0
CAPPED_FRACTION = 0.9
NO_BASELINE = 3

DEFAULT_COMMENT = [
    "PLAN-ci-quick-cpu-scheduling 2.5: per-gate CPU baseline for ci:quick's scheduler.",
    "Written ONLY by `PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --refresh`, from the",
    "medians of the last 3 `gate-costs-<sha>` artifacts of housekeeping.yml's gate-costs-capture",
    "job (run.ts --quick --jobs 1, serial and uncontended). Checked nightly by `gate_costs --check`.",
    "cpu_s/wall_s in seconds; eff_cores = cpu_s / wall_s; capped = eff_cores >= 0.9 x source.cores",
    "(the gate filled the runner, so its width is not portable); rank 1 = the largest cpu_s.",
    "carried: a slow (diff-sampled) gate no capture in the window ran keeps its last figures,",
    "stamped with when they were measured (gate_costs.py docstring, TWO KINDS OF GATE).",
    "Do not hand-edit: the next --refresh overwrites every figure.",
]

Capture = dict[str, Any]


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_capture(text: str) -> Capture:
    """One run.ts `--json` report. Raises ValueError on unparseable text and TypeError on anything that is not an object with a `gates` list, so a truncated capture is refused, not read as a run that measured nothing."""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("gates"), list):
        raise TypeError("not a run.ts --json report (no `gates` list)")
    return data


def capture_cores(capture: Capture) -> int | None:
    util = capture.get("utilisation")
    if isinstance(util, dict):
        cores = util.get("cores")
        if isinstance(cores, int) and cores > 0:
            return cores
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _rank(gates: dict[str, dict[str, Any]]) -> None:
    """`rank` 1 for the largest cpu_s, in place; ties broken by id."""
    for rank, gid in enumerate(sorted(gates, key=lambda g: (-gates[g]["cpu_s"], g)), start=1):
        gates[gid]["rank"] = rank


def aggregate(captures: Sequence[Capture]) -> dict[str, Any]:
    """Per-gate medians over `captures` (newest first), plus the runner's core count and the gates no capture measured. Pure: the tests drive it with fixture reports."""
    samples: dict[str, dict[str, list[float]]] = {}
    newest_status: dict[str, str] = {}
    cores_seen: list[int] = []
    for capture in captures:
        cores = capture_cores(capture)
        if cores is not None:
            cores_seen.append(cores)
        for gate in capture.get("gates") or []:
            if not isinstance(gate, dict) or not isinstance(gate.get("id"), str):
                continue
            gid = gate["id"]
            newest_status.setdefault(gid, str(gate.get("status")))
            cpu_ms = _num(gate.get("cpuMs"))
            wall_ms = _num(gate.get("ms"))
            if gate.get("status") != "ok" or cpu_ms is None or wall_ms is None or wall_ms <= 0:
                continue
            rec = samples.setdefault(gid, {"cpu": [], "wall": [], "rss": []})
            rec["cpu"].append(cpu_ms / 1000.0)
            rec["wall"].append(wall_ms / 1000.0)
            rss = _num(gate.get("rssMb"))
            if rss is not None:
                rec["rss"].append(rss)

    cores = int(statistics.median(cores_seen)) if cores_seen else None
    gates: dict[str, dict[str, Any]] = {}
    for gid, rec in samples.items():
        cpu_s = statistics.median(rec["cpu"])
        wall_s = statistics.median(rec["wall"])
        eff = cpu_s / wall_s
        gates[gid] = {
            "cpu_s": round(cpu_s, 3),
            "wall_s": round(wall_s, 3),
            "eff_cores": round(eff, 2),
            "capped": cores is not None and eff >= CAPPED_FRACTION * cores,
            "peak_rss_mb": round(statistics.median(rec["rss"])) if rec["rss"] else None,
            "rank": 0,
        }
    _rank(gates)
    unmeasured = {gid: status for gid, status in newest_status.items() if gid not in gates}
    return {
        "cores": cores,
        "gates": dict(sorted(gates.items())),
        "unmeasured": dict(sorted(unmeasured.items())),
    }


def _is_not_found(exc: ghx.GhError) -> bool:
    """GitHub answered 404 for this one run or artifact: it was deleted (or expired) after the run list named it. MEASURED 2026-10-07: runs 37192382851 and 37111522524 answer `gh: Not Found (HTTP 404)` while list reads can still serve them (ci-trace.py records GitHub serving stale run lists). Every other failure (auth, rate limit, network) is not this and still raises."""
    return "HTTP 404" in (exc.stderr or "") or "HTTP 404" in str(exc)


def collect_captures(
    repo: str,
    *,
    limit: int = SAMPLE_CAPTURES,
    list_runs: Callable[..., list[dict[str, Any]]] = budget_report.fetch_runs,
    list_artifacts: Callable[[str, int], list[dict[str, Any]]] = budget_report.fetch_artifacts,
    download: Callable[[str, Any], bytes] = budget_report.download_artifact_zip,
) -> tuple[list[Capture], list[dict[str, Any]], list[str]]:
    """The newest `limit` gate-costs captures across the capture workflow's scheduled and dispatched runs: (captures newest first, their run records, warnings). A run with no live `gate-costs-` artifact (its capture job failed, timed out or was cancelled) is passed over; so is a run or artifact GitHub answers 404 for (deleted after the list named it), named on stderr; an artifact that will not parse is warned about and passed over. Zero captures is still the caller's failure."""
    runs: dict[Any, dict[str, Any]] = {}
    for event in CAPTURE_EVENTS:
        for run in list_runs(
            repo, CAPTURE_WORKFLOW, event, budget_report.DEFAULT_BRANCH, "completed", RUNS_LISTED
        ):
            runs.setdefault(run.get("id"), run)
    ordered = sorted(runs.values(), key=lambda r: r.get("created_at") or "", reverse=True)
    captures: list[Capture] = []
    sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    for run in ordered:
        if len(captures) >= limit:
            break
        run_id = run.get("id")
        if not isinstance(run_id, int):
            continue
        try:
            listed = list_artifacts(repo, run_id)
        except ghx.GhError as exc:
            if not _is_not_found(exc):
                raise
            print(
                "gate_costs: run %s is listed but GitHub answers 404 for it (deleted); passed over."
                % run_id,
                file=sys.stderr,
            )
            continue
        artifact = next(
            (
                a
                for a in listed
                if str(a.get("name", "")).startswith(ARTIFACT_PREFIX) and not a.get("expired")
            ),
            None,
        )
        if artifact is None:
            continue
        try:
            blob = download(repo, artifact.get("id"))
        except ghx.GhError as exc:
            if not _is_not_found(exc):
                raise
            print(
                "gate_costs: run %s artifact %s answers 404 (deleted or expired); passed over."
                % (run_id, artifact.get("name")),
                file=sys.stderr,
            )
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                member = next((n for n in zf.namelist() if n.endswith(".json")), None)
                if member is None:
                    raise ValueError("no .json member")
                capture = parse_capture(zf.read(member).decode("utf-8"))
        except (ValueError, TypeError, zipfile.BadZipFile) as exc:
            warnings.append(
                "run %s artifact %s unreadable: %s" % (run_id, artifact.get("name"), exc)
            )
            continue
        captures.append(capture)
        sources.append(
            {"id": run_id, "sha": run.get("head_sha"), "created_at": run.get("created_at")}
        )
    return captures, sources, warnings


def carry_forward(
    prior: dict[str, Any], agg: dict[str, Any], lock_ids: set[str], sampled: set[str]
) -> dict[str, str]:
    """The prior file's diff-sampled gates that no capture in this window ran at all, still registered and still slow: `{gate id: when its figures were measured}`. A gate a capture ran (measured or not) is the window's to describe, so it is never carried; a fast gate is never carried, since every capture runs it."""
    raw_gates = prior.get("gates")
    prior_gates: dict[str, Any] = raw_gates if isinstance(raw_gates, dict) else {}
    raw_carried = prior.get("carried")
    prior_carried: dict[str, Any] = raw_carried if isinstance(raw_carried, dict) else {}
    seen = set(agg["gates"]) | set(agg["unmeasured"])
    stamp = str(prior.get("refreshed_at") or "unknown")
    return {
        gid: str(prior_carried.get(gid) or stamp)
        for gid in sorted(prior_gates)
        if gid in lock_ids
        and gid in sampled
        and gid not in seen
        and isinstance(prior_gates[gid], dict)
    }


def build_baseline(
    captures: Sequence[Capture],
    sources: Sequence[dict[str, Any]],
    comment: Any,
    refreshed_at: str,
    *,
    prior: dict[str, Any] | None = None,
    lock_ids: set[str] | None = None,
    sampled: set[str] | None = None,
) -> dict[str, Any]:
    agg = aggregate(captures)
    gates = agg["gates"]
    carried: dict[str, str] = {}
    if prior is not None and lock_ids is not None and sampled is not None:
        carried = carry_forward(prior, agg, lock_ids, sampled)
        for gid in carried:
            gates[gid] = dict(prior["gates"][gid])
        _rank(gates)
    return {
        "$comment": comment if comment is not None else DEFAULT_COMMENT,
        "refreshed_at": refreshed_at,
        "source": {"runner": CAPTURE_RUNNER, "cores": agg["cores"], "runs": list(sources)},
        "gates": dict(sorted(gates.items())),
        "unmeasured": agg["unmeasured"],
        "carried": carried,
    }


def load_lock(root: Path) -> list[dict[str, Any]]:
    data = json.loads((root / GATES_LOCK_REL_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("%s holds no gates" % GATES_LOCK_REL_PATH)
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("id"), str)]


def sampled_gate_ids(entries: Sequence[dict[str, Any]]) -> set[str]:
    """The gates a `run.ts --quick` capture runs only when the captured commit's diff touches them: `slow: true`, closed over `needs` (a gate needing a slow gate is demoted with it). The same fixpoint as run.ts's `--quick` lane (scripts/ci-runner/run.ts, "THE LANE IS A FIXPOINT")."""
    slow = {e["id"] for e in entries if e.get("slow") is True}
    while True:
        before = len(slow)
        for e in entries:
            needs = e.get("needs")
            if e["id"] not in slow and isinstance(needs, list) and any(n in slow for n in needs):
                slow.add(e["id"])
        if len(slow) == before:
            return slow


def _drift(committed: Any, measured: Any) -> float | None:
    c, m = _num(committed), _num(measured)
    if c is None or m is None or c == 0:
        return None
    return abs(m - c) / c


def check_findings(
    committed: dict[str, Any],
    fresh: dict[str, Any],
    lock_ids: set[str],
    *,
    sampled: Collection[str] = frozenset(),
) -> list[str]:
    """Every reason the committed baseline no longer describes the manifest or the captures. Pure: `fresh` is `aggregate()`'s output; `sampled` is `sampled_gate_ids()` (see the module docstring, TWO KINDS OF GATE)."""
    findings: list[str] = []
    base = committed.get("gates") or {}
    known = set(base) | set(committed.get("unmeasured") or {})

    findings.extend(
        "gate %r is in %s but not in the manifest (gates.lock.json); run --refresh."
        % (g, GATE_COSTS_REL_PATH)
        for g in sorted(known - lock_ids)
    )
    seen = set(fresh["gates"]) | set(fresh["unmeasured"])
    findings.extend(
        "gate %r ran in the captures but is missing from %s; run --refresh."
        % (g, GATE_COSTS_REL_PATH)
        for g in sorted((seen & lock_ids) - known - set(sampled))
    )
    findings.extend(
        "gate %r has a baseline but no capture measured it (%s)."
        % (
            g,
            "%s in the newest capture that ran it" % fresh["unmeasured"][g]
            if g in fresh["unmeasured"]
            else "absent from every capture, and every --quick capture runs it",
        )
        for g in sorted(set(base) & lock_ids)
        if g not in fresh["gates"] and (g in fresh["unmeasured"] or g not in sampled)
    )

    base_cores = (committed.get("source") or {}).get("cores")
    if fresh["cores"] is not None and base_cores is not None and fresh["cores"] != base_cores:
        findings.append(
            "runner cores changed: baseline %s, captures %s; `capped` no longer means the same thing, run --refresh."
            % (base_cores, fresh["cores"])
        )

    for gid in sorted(set(base) & set(fresh["gates"])):
        old, new = base[gid], fresh["gates"][gid]
        if max(_num(old.get("cpu_s")) or 0.0, new["cpu_s"]) < MIN_DRIFT_CPU_S:
            continue
        d = _drift(old.get("cpu_s"), new["cpu_s"])
        if d is not None and d > DRIFT_THRESHOLD:
            findings.append(
                "gate %r cpu_s: committed %.3g drifts %.0f%% from measured %.3g (over the %.0f%% limit)."
                % (gid, old.get("cpu_s"), d * 100, new["cpu_s"], DRIFT_THRESHOLD * 100)
            )
        if old.get("capped") or new["capped"]:
            continue
        d = _drift(old.get("eff_cores"), new["eff_cores"])
        if d is not None and d > DRIFT_THRESHOLD:
            findings.append(
                "gate %r eff_cores: committed %.3g drifts %.0f%% from measured %.3g (over the %.0f%% limit)."
                % (gid, old.get("eff_cores"), d * 100, new["eff_cores"], DRIFT_THRESHOLD * 100)
            )
    return findings


def sampling_notes(
    committed: dict[str, Any], fresh: dict[str, Any], lock_ids: set[str], sampled: set[str]
) -> dict[str, list[str]]:
    """The two diff-sampled sets `check_findings` deliberately does not judge, for the success line: `not_sampled` (baselined, no capture in the window ran it) and `pending` (a capture ran it, the file does not have it yet; the next --refresh adds it)."""
    base = committed.get("gates") or {}
    known = set(base) | set(committed.get("unmeasured") or {})
    seen = set(fresh["gates"]) | set(fresh["unmeasured"])
    return {
        "not_sampled": sorted(g for g in set(base) & lock_ids & sampled if g not in seen),
        "pending": sorted((seen & lock_ids & sampled) - known),
    }


def refresh(
    path: Path,
    repo: str,
    root: Path,
    *,
    dry_run: bool = False,
    collect: Callable[
        ..., tuple[list[Capture], list[dict[str, Any]], list[str]]
    ] = collect_captures,
    now: Callable[[], str] = _now_iso,
) -> int:
    captures, sources, warnings = collect(repo)
    for w in warnings:
        print("gate_costs --refresh: %s" % w, file=sys.stderr)
    if not captures:
        print(
            "gate_costs --refresh: no %s* artifact in %s's recent runs; nothing to write."
            % (ARTIFACT_PREFIX, CAPTURE_WORKFLOW),
            file=sys.stderr,
        )
        return 1
    comment = None
    prior: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prior = loaded
                comment = loaded.get("$comment")
        except (OSError, json.JSONDecodeError):
            comment = None
    entries = load_lock(root)
    baseline = build_baseline(
        captures,
        sources,
        comment,
        now(),
        prior=prior,
        lock_ids={e["id"] for e in entries},
        sampled=sampled_gate_ids(entries),
    )
    payload = json.dumps(baseline, indent=2) + "\n"
    carried = baseline["carried"]
    print(
        "gate_costs --refresh: %d gate(s) measured, %d unmeasured, %d diff-sampled carried%s, from %d capture(s) on %s core(s)."
        % (
            len(baseline["gates"]) - len(carried),
            len(baseline["unmeasured"]),
            len(carried),
            " (%s)" % ", ".join(carried) if carried else "",
            len(captures),
            baseline["source"]["cores"],
        )
    )
    if dry_run:
        print(payload)
        return 0
    path.write_text(payload, encoding="utf-8")
    print("gate_costs --refresh: wrote %s" % path)
    return 0


def _fail(lines: list[str]) -> int:
    """Print a failing verdict to stderr. The report housekeeping posts is written by `rediacc_ci.ci.freshness --check --report-to`, its one writer, from this output."""
    sys.stderr.write("\n".join(lines) + "\n")
    return 1


def check(
    path: Path,
    repo: str,
    root: Path,
    *,
    collect: Callable[
        ..., tuple[list[Capture], list[dict[str, Any]], list[str]]
    ] = collect_captures,
) -> int:
    if not path.exists():
        print(
            "::notice title=gate-costs::gate_costs --check: NOT CHECKED -- %s does not exist yet "
            "(no baseline). Create it with `PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs "
            "--refresh` once a nightly gate-costs-capture artifact exists." % GATE_COSTS_REL_PATH
        )
        return NO_BASELINE
    try:
        committed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(["gate_costs --check: %s does not parse: %s" % (path, exc)])
    if not isinstance(committed, dict):
        return _fail(["gate_costs --check: %s is not a JSON object" % path])
    entries = load_lock(root)
    lock_ids = {e["id"] for e in entries}
    sampled = sampled_gate_ids(entries)
    captures, sources, warnings = collect(repo)
    findings = ["capture unreadable: %s" % w for w in warnings]
    notes: dict[str, list[str]] = {"not_sampled": [], "pending": []}
    if not captures:
        findings.append(
            "no %s* artifact in %s's recent runs: the nightly capture is not producing one."
            % (ARTIFACT_PREFIX, CAPTURE_WORKFLOW)
        )
    else:
        fresh = aggregate(captures)
        findings.extend(check_findings(committed, fresh, lock_ids, sampled=sampled))
        notes = sampling_notes(committed, fresh, lock_ids, sampled)
    if findings:
        return _fail(
            ["Gate cost baseline check found %d issue(s):" % len(findings)]
            + ["  - %s" % f for f in findings]
        )
    print(
        "Gate cost baseline check: %d gate(s) from %d capture(s) (run %s), all within %.0f%% of %s; %d of %d registered gate(s) are diff-sampled (slow lane)."
        % (
            len(committed.get("gates") or {}),
            len(captures),
            ", ".join(str(src.get("id")) for src in sources) or "?",
            DRIFT_THRESHOLD * 100,
            GATE_COSTS_REL_PATH,
            len(sampled & lock_ids),
            len(lock_ids),
        )
    )
    # Not judged, by design (module docstring, TWO KINDS OF GATE), and so printed by name every run.
    if notes["not_sampled"]:
        print(
            "  %d diff-sampled gate(s) not in this window: %s (baseline kept; run.ts --quick runs a slow gate only when the captured commit's diff touches it)."
            % (len(notes["not_sampled"]), ", ".join(notes["not_sampled"]))
        )
    if notes["pending"]:
        print(
            "  %d diff-sampled gate(s) captured but not yet in the file: %s (the next --refresh adds them)."
            % (len(notes["pending"]), ", ".join(notes["pending"]))
        )
    return 0


def validate_capture(path: Path) -> int:
    """The capture job's own acceptance: `path` must be a run.ts --json report in which at least one gate passed with a cpuMs. Gate reds are expected on the bare capture checkout and are not judged; a report that measured nothing is."""
    try:
        capture = parse_capture(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print("::error::gate_costs: %s is not a usable capture: %s" % (path, exc))
        return 1
    agg = aggregate([capture])
    total = len(capture["gates"])
    print(
        "gate_costs: %d of %d gate(s) measured on %s core(s); %d unmeasured."
        % (len(agg["gates"]), total, agg["cores"], len(agg["unmeasured"]))
    )
    if not agg["gates"]:
        print("::error::gate_costs: %s measured no gate (no passing gate carried cpuMs)." % path)
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="gate_costs",
        description="Per-gate CPU baseline (.ci/config/gate-costs.json) from the nightly gate-costs captures.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--refresh",
        action="store_true",
        help="rewrite the baseline from the last %d captures" % SAMPLE_CAPTURES,
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="exit 1 on >25%% drift or manifest mismatch; exit 3 when no baseline exists yet",
    )
    mode.add_argument(
        "--validate-capture",
        type=Path,
        default=None,
        metavar="REPORT",
        help="exit 1 unless REPORT is a run.ts --json capture that measured at least one gate",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="with --refresh: print instead of writing"
    )
    parser.add_argument("--repo", default=budget_report.DEFAULT_REPO)
    parser.add_argument(
        "--gate-costs", type=Path, default=None, help="override the baseline path (tests)"
    )
    args = parser.parse_args(argv)
    if args.validate_capture is not None:
        return validate_capture(args.validate_capture)
    root = paths.repo_root()
    target = args.gate_costs or (root / GATE_COSTS_REL_PATH)
    try:
        if args.refresh:
            return refresh(target, args.repo, root, dry_run=args.dry_run)
        return check(target, args.repo, root)
    except ghx.GhError as exc:
        print("gate_costs: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

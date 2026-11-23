#!/usr/bin/env python3
"""wl_hookreport: the retirement and merge report over the guard chain ledger, and the two-way hook budgets.

    python3 .claude/hooks/stop/wl_hookreport.py --report            print the report
    python3 .claude/hooks/stop/wl_hookreport.py --snapshot          write .ci/config/hook-ledger.json from the local ledger
    python3 .claude/hooks/stop/wl_hookreport.py --check-snapshot    the freshness check of that snapshot
    python3 .claude/hooks/stop/wl_hookreport.py --check-budgets     the budgets of .ci/policy/hook-exec-baseline.json, both directions
    python3 .claude/hooks/stop/wl_hookreport.py --write-budgets     lower and add those budgets from the tree (never raises one)
    python3 .claude/hooks/stop/wl_hookreport.py --confirm <stem>    record a confirmed true positive of a guard or trapguard rule

agent/plans/PLAN-tooling-code-reduction.md CR8, design D6 second half. CR7 made `dispatch.run_chain` append one line per guard chain run to `.ci/cache/hook-ledger/chains.jsonl` (`{chain, refused_by, rc, ms, slow, crashed, session, ts}`). This module reads it, with the trapguard fire ledgers and the ci:quick gate receipts, and answers the questions the loop needs to retire and merge:

  never fired    a blocking guard with no refusal in NEVER_DAYS days. Judged only when the ledger
                 covers that many days; a shorter window is printed as a window, never as a verdict.
  unconfirmed    a guard or trapguard rule with more than RETIRE_FIRES fires and no confirmed true
                 positive. This GENERALISES wl_trapfires.retire_candidates, which now calls
                 `unconfirmed` here; both share one confirmed.jsonl, so `--confirm` and
                 `wl_trapfires.py --trap-confirm` record the same fact.
  overlapping    two guards whose fire sets overlap: each fire is keyed on (session, minute), and a
                 pair sharing at least OVERLAP_MIN keys at a Jaccard index of at least OVERLAP_JACCARD
                 is a merge candidate (an edit/shell twin pair refusing the same intent twice).
  quiet gates    a gate seen in at least GATE_MIN_RUNS receipts and failing in none, with its CPU cost
                 from .ci/config/gate-costs.json.
  slow guards    the guards the ledger lists under `slow` (over dispatch.SLOW_MS), by count and p50.

STOP-CHECK TIMING IS OWED, AND SAID SO. The report has a Stop-check section because D6 asks for one, but the per-check durations come from PLAN-tooling-speed.md SP3 (a registry runner writing each check's duration into the blocklog row), which is not on this tree. The section prints UNMEASURED with that box named, and the `stopP50Ms` budget carries `owed` instead of a number; nothing reads an absent field as zero.

THE SNAPSHOT. The ledger is gitignored local state, so CI cannot read it. `--snapshot` folds it into `.ci/config/hook-ledger.json` (per-chain run counts and latency percentiles, per-guard fire counts and slow counts over the whole inventory, the overlap pairs), with no session id in it: the repository is public. The freshness registry (.ci/config/freshness.json) runs `--check-snapshot` nightly, which refuses a snapshot older than SNAPSHOT_MAX_DAYS, an empty
window, or an inventory that drifted from the guards on disk.

THE BUDGETS FAIL IN BOTH DIRECTIONS, the shape check:ci-hook-exec-baseline already gives the process counts. Each budget is a ceiling: a measurement above it is GREW; a measurement under `ceiling * (1 - slack)` is SHRANK, with the new value to repin, because a budget that silently absorbs an improvement cannot prove the next one. Every measurement is from committed files (guard sources, lane-durations.json, the snapshot, the baseline's own `perCall`), so CI reaches the same verdict as a laptop.

ANTI-VACUITY. An inventory of zero guards, a budgets block with an empty table, and a snapshot with zero rows are each a refusal (exit 1), never a pass. Every success line prints its counts.
"""

from __future__ import annotations

import datetime
import json
import math
import pathlib
import re
import statistics
import sys
from collections import Counter

import wl_trapfires

# This file is `.claude/hooks/stop/wl_hookreport.py`; the checkout holding the ledger and the guards is three levels up, the same tree dispatch.ledger_path() resolves for the code it runs.
CHECKOUT = pathlib.Path(__file__).resolve().parents[3]
# dispatch.LEDGER_REL, spelled here so a report never imports the guard chain; test_wl_hookreport.py asserts the two agree.
LEDGER_REL = (".ci", "cache", "hook-ledger", "chains.jsonl")
GUARDS_REL = (".claude", "rediacc_hooks", "guards")
GUARD_PREFIXES = ("block_", "warn_", "require_")
SNAPSHOT_REL = (".ci", "config", "hook-ledger.json")
BASELINE_REL = (".ci", "policy", "hook-exec-baseline.json")
DURATIONS_REL = (".ci", "config", "lane-durations.json")
GATE_COSTS_REL = (".ci", "config", "gate-costs.json")
RECEIPTS_REL = (".ci", "cache", "receipts")

NEVER_DAYS = 14
RETIRE_FIRES = wl_trapfires.RETIRE_FIRES
OVERLAP_MIN = 2
OVERLAP_JACCARD = 0.5
GATE_MIN_RUNS = 5
SNAPSHOT_MAX_DAYS = 14
ROWS_SHOWN = 15
TEST_FLOOR_MS = 1000
STOP_TIMING_OWED = (
    "UNMEASURED: per-check Stop durations come from PLAN-tooling-speed.md SP3 (the registry "
    "runner writing each check's duration into the blocklog row), not on this tree"
)

CHAIN_RE = re.compile(r"^CHAIN\s*=\s*[\"']([a-z-]+)[\"']", re.MULTILINE)
# Units of lane-durations.json shared by every guard rather than owned by one; budgeted by unit id.
SHARED_GUARD_UNITS = (
    "pytest:.claude/rediacc_hooks/tests/test_guards_differential.py",
    "pytest:.claude/rediacc_hooks/tests/test_hooks_delegates.py",
)


class ReportError(Exception):
    """The report or a check cannot reach a verdict. Exit 1, never a silent pass."""


# --------------------------------------------------------------------------- reading


def read_jsonl(path):
    """The dict rows of a JSON-lines file; [] when it is absent. A torn line is skipped (the ledger is O_APPEND, so only a hand-edit tears one)."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _read_json(path, what):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError("cannot read %s at %s (%s)" % (what, path, exc)) from exc
    except ValueError as exc:
        raise ReportError("%s at %s is not valid JSON (%s)" % (what, path, exc)) from exc


def inventory(root=CHECKOUT):
    """{stem: {"chain", "lines"}} for every guard module on disk, read statically (no import, so a report never loads the chain)."""
    out = {}
    base = pathlib.Path(root).joinpath(*GUARDS_REL)
    for path in sorted(base.glob("*.py")):
        if not path.name.startswith(GUARD_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = CHAIN_RE.search(text)
        out[path.stem] = {"chain": m.group(1) if m else "", "lines": text.count("\n")}
    return out


def _parse_ts(ts):
    try:
        return datetime.datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )
    except ValueError:
        return None


def _pct(values, q):
    """The q-quantile (0..1) of `values` by nearest rank, or None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


# --------------------------------------------------------------------------- the questions


def window(rows):
    """(first datetime, last datetime, days covered) of the ledger rows; (None, None, 0.0) for none."""
    stamps = [t for t in (_parse_ts(r.get("ts")) for r in rows) if t is not None]
    if not stamps:
        return None, None, 0.0
    first, last = min(stamps), max(stamps)
    return first, last, (last - first).total_seconds() / 86400.0


def fires_by_guard(rows):
    """Counter {stem: refusals}."""
    return Counter(str(r["refused_by"]) for r in rows if r.get("refused_by"))


def never_fired(rows, inv, days=NEVER_DAYS, now=None):
    """(verdict_ready, [stem]) for blocking guards with no refusal in the last `days` days.

    A warn_ guard never refuses, so it is not judged by refusals at all. With a ledger window shorter than `days`, verdict_ready is False and the list is what is silent IN THE WINDOW, which the report labels as such.
    """
    first, last, span = window(rows)
    now = now or last
    blocking = sorted(s for s in inv if s.startswith("block_"))
    if first is None:
        return False, blocking
    cutoff = now - datetime.timedelta(days=days)
    recent = {
        str(r["refused_by"])
        for r in rows
        if r.get("refused_by") and (_parse_ts(r.get("ts")) or first) >= cutoff
    }
    return span >= days, [s for s in blocking if s not in recent]


def unconfirmed(fires, confirmed, cap=RETIRE_FIRES):
    """[(name, fires)] over `cap` fires with no confirmed true positive, most fires first. The one rule for guards and trapguard rules alike."""
    return [(name, n) for name, n in fires.most_common() if n > cap and name not in confirmed]


def fire_keys(rows):
    """{stem: {(session, minute)}}: the fire set of each refusing guard."""
    out: dict = {}
    for r in rows:
        stem = r.get("refused_by")
        if stem:
            out.setdefault(str(stem), set()).add(
                (str(r.get("session") or ""), str(r.get("ts") or "")[:16])
            )
    return out


def overlaps(rows, min_shared=OVERLAP_MIN, min_jaccard=OVERLAP_JACCARD):
    """[(a, b, shared, jaccard)] for guard pairs whose fire sets overlap, most shared first."""
    keys = fire_keys(rows)
    stems = sorted(keys)
    out = []
    for i, a in enumerate(stems):
        for b in stems[i + 1 :]:
            shared = len(keys[a] & keys[b])
            if shared < min_shared:
                continue
            jac = shared / len(keys[a] | keys[b])
            if jac >= min_jaccard:
                out.append((a, b, shared, round(jac, 2)))
    return sorted(out, key=lambda t: (-t[2], t[0], t[1]))


def slow_guards(rows):
    """[(stem, times listed slow, p50 ms)], most often slow first."""
    times: dict = {}
    for r in rows:
        for pair in r.get("slow") or []:
            if isinstance(pair, list) and len(pair) == 2:
                times.setdefault(str(pair[0]), []).append(float(pair[1]))
    return sorted(
        ((s, len(v), round(statistics.median(v), 1)) for s, v in times.items()),
        key=lambda t: (-t[1], t[0]),
    )


def chain_latency(rows):
    """{chain: {"runs", "p50_ms", "p90_ms"}}."""
    by: dict = {}
    for r in rows:
        if isinstance(r.get("ms"), (int, float)):
            by.setdefault(str(r.get("chain") or ""), []).append(float(r["ms"]))
    return {
        c: {"runs": len(v), "p50_ms": round(_pct(v, 0.5), 1), "p90_ms": round(_pct(v, 0.9), 1)}
        for c, v in sorted(by.items())
    }


def quiet_gates(receipts, costs, min_runs=GATE_MIN_RUNS):
    """[(gate, runs, cpu_s or None)] for gates in at least `min_runs` receipts that failed in none, costliest first."""
    runs: Counter = Counter()
    failed: Counter = Counter()
    for rec in receipts:
        runs.update(str(g) for g in rec.get("gates") or {})
        failed.update(str(g) for g in rec.get("failed") or [])
    gates = (costs or {}).get("gates") or {}
    out = []
    for gate, n in runs.items():
        if n >= min_runs and not failed[gate]:
            cpu = (gates.get(gate) or {}).get("cpu_s")
            out.append((gate, n, cpu))
    return sorted(out, key=lambda t: (-(t[2] or 0.0), t[0]))


def read_receipts(root=CHECKOUT):
    """Every ci:quick receipt under .ci/cache/receipts that parses as an object."""
    out = []
    for path in sorted(pathlib.Path(root).joinpath(*RECEIPTS_REL).glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


# --------------------------------------------------------------------------- the report


def report(root=CHECKOUT, rows=None, trap_base=None, receipts=None, now=None):
    """The report text over the ledger, the trapguard ledgers and the receipts at `root`."""
    root = pathlib.Path(root)
    ledger = root.joinpath(*LEDGER_REL)
    rows = read_jsonl(ledger) if rows is None else rows
    inv = inventory(root)
    trap_base = trap_base or wl_trapfires.state_dir()
    receipts = read_receipts(root) if receipts is None else receipts
    try:
        costs = _read_json(root.joinpath(*GATE_COSTS_REL), "gate costs")
    except ReportError:
        costs = {}
    first, last, span = window(rows)
    out = ["HOOK AND GATE REPORT (wl_hookreport.py, PLAN-tooling-code-reduction.md D6)"]
    if first is None:
        out.append("  no rows in %s: the guard chains have recorded nothing to judge" % ledger)
    else:
        out.append(
            "  ledger %s: %d chain runs, %s to %s (%.1f days), %d guards on disk"
            % (ledger, len(rows), first.isoformat(), last.isoformat(), span, len(inv))
        )
    ready, silent = never_fired(rows, inv, now=now)
    head = (
        "never fired in %d days (%d blocking guards)" % (NEVER_DAYS, len(silent))
        if ready
        else "silent in the window, NOT a %d-day verdict (the ledger covers %.1f days): %d"
        % (NEVER_DAYS, span, len(silent))
    )
    out.append("\n" + head + ":")
    out += ["  " + s for s in silent[:ROWS_SHOWN]] or ["  (none)"]
    if len(silent) > ROWS_SHOWN:
        out.append("  ... and %d more" % (len(silent) - ROWS_SHOWN))

    confirmed = {
        str(r.get("rule") or "") for r in wl_trapfires.read_jsonl(trap_base / "confirmed.jsonl")
    }
    fires = fires_by_guard(rows)
    fires.update(
        str(r.get("rule") or "")
        for r in wl_trapfires.read_jsonl(trap_base / "fires.jsonl")
        if r.get("rule")
    )
    cands = unconfirmed(fires, confirmed)
    out.append(
        "\nfired more than %d times, never confirmed (record a real catch with --confirm <name>):"
        % RETIRE_FIRES
    )
    out += ["  %-40s %d fires" % c for c in cands] or ["  (none)"]

    pairs = overlaps(rows)
    out.append(
        "\noverlapping fire sets, merge candidates (shared (session, minute) keys >= %d, Jaccard >= %s):"
        % (OVERLAP_MIN, OVERLAP_JACCARD)
    )
    out += ["  %s + %s: %d shared, J=%s" % p for p in pairs] or ["  (none)"]

    out.append("\nslow guards (listed over the chain's slow threshold):")
    out += ["  %-40s %d times, p50 %s ms" % s for s in slow_guards(rows)[:ROWS_SHOWN]] or [
        "  (none)"
    ]

    quiet = quiet_gates(receipts, costs)
    out.append(
        "\ngates with no failure in %d ci:quick receipts (each seen in >= %d), costliest first:"
        % (len(receipts), GATE_MIN_RUNS)
    )
    out += [
        "  %-48s %d runs, %s CPU-s" % (g, n, "?" if c is None else c)
        for g, n, c in quiet[:ROWS_SHOWN]
    ] or ["  (none)"]
    out.append("\nStop-check timing: " + STOP_TIMING_OWED)
    return "\n".join(out)


def retro_section(root=CHECKOUT):
    """The report as the retro brief's last section; a failure to build it is named in the section, never raised into the brief."""
    try:
        return report(root)
    except (OSError, ReportError) as exc:
        return "HOOK AND GATE REPORT: not built (%s)" % exc


# --------------------------------------------------------------------------- the snapshot


def snapshot(rows, inv, now=None):
    """The committed aggregate of the ledger: no session id, every guard in the inventory."""
    first, last, span = window(rows)
    if first is None:
        raise ReportError(
            "the hook ledger has no rows, so a snapshot would describe nothing; run some tool "
            "calls under the guard chains first"
        )
    fires = fires_by_guard(rows)
    slow = {s: (n, p50) for s, n, p50 in slow_guards(rows)}
    stamp = now or datetime.datetime.now(datetime.UTC)
    return {
        "$comment": [
            "Written ONLY by `python3 .claude/hooks/stop/wl_hookreport.py --snapshot` from the local",
            "guard chain ledger .ci/cache/hook-ledger/chains.jsonl (dispatch.run_chain, CR7). No session id.",
            "Read by `--check-snapshot` (freshness registry, nightly) and by the chainLatencyP50Ms budget.",
        ],
        "refreshed_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {
            "from": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "days": round(span, 2),
            "rows": len(rows),
            "sessions": len({r.get("session") for r in rows if r.get("session")}),
        },
        "chains": chain_latency(rows),
        "guards": {
            s: {
                "chain": inv[s]["chain"],
                "fires": fires.get(s, 0),
                "slow_runs": slow.get(s, (0, None))[0],
                "slow_p50_ms": slow.get(s, (0, None))[1],
            }
            for s in sorted(inv)
        },
        "overlaps": [list(p) for p in overlaps(rows)],
    }


def check_snapshot(doc, inv, now=None, max_days=SNAPSHOT_MAX_DAYS):
    """Every finding against a committed snapshot, as strings. Pure."""
    findings = []
    win = doc.get("window") or {}
    if not isinstance(win.get("rows"), int) or win["rows"] <= 0:
        findings.append("the snapshot window holds no rows, so it measures nothing")
    stamp = _parse_ts(doc.get("refreshed_at"))
    now = now or datetime.datetime.now(datetime.UTC)
    if stamp is None:
        findings.append("refreshed_at %r is not an ISO8601Z stamp" % doc.get("refreshed_at"))
    elif now - stamp > datetime.timedelta(days=max_days):
        findings.append(
            "refreshed_at %s is more than %d days old" % (doc["refreshed_at"], max_days)
        )
    guards = doc.get("guards") or {}
    findings.extend(
        "guard %s is on disk and missing from the snapshot" % s
        for s in sorted(set(inv) - set(guards))
    )
    findings.extend(
        "guard %s is in the snapshot and no longer on disk" % s
        for s in sorted(set(guards) - set(inv))
    )
    if not doc.get("chains"):
        findings.append("the snapshot carries no chain latencies")
    return findings


# --------------------------------------------------------------------------- the budgets


def measure(root=CHECKOUT, baseline=None):
    """{table: {key: measured}} for every budget table, from committed files only."""
    root = pathlib.Path(root)
    inv = inventory(root)
    if not inv:
        raise ReportError(
            "no guard modules under %s: the budgets would measure nothing"
            % root.joinpath(*GUARDS_REL)
        )
    baseline = baseline or _read_json(root.joinpath(*BASELINE_REL), "the hook exec baseline")
    units = (_read_json(root.joinpath(*DURATIONS_REL), "lane durations").get("units")) or {}
    tests = {}
    # A unit under TEST_FLOOR_MS has nothing to budget: its timing is noise at one-decimal seconds.
    for unit, ms in units.items():
        if not isinstance(ms, (int, float)) or ms < TEST_FLOOR_MS:
            continue
        name = unit.split(":", 1)[-1].rsplit("/", 1)[-1]
        if unit in SHARED_GUARD_UNITS:
            tests[unit] = round(ms / 1000.0, 1)
            continue
        for stem in inv:
            if name.startswith(("test_" + stem, "test-" + stem)):
                tests[stem] = round(tests.get(stem, 0.0) + ms / 1000.0, 1)
    snap = _read_json(root.joinpath(*SNAPSHOT_REL), "the hook ledger snapshot")
    per_call = ((baseline.get("perCall") or {}).get("pythonProcesses") or {}).get("total")
    return {
        "processesPerCall": {"Bash": per_call},
        "chainLatencyP50Ms": {c: v.get("p50_ms") for c, v in (snap.get("chains") or {}).items()},
        "guardLines": {s: v["lines"] for s, v in inv.items()},
        "guardTestSeconds": tests,
    }


TABLES = ("processesPerCall", "chainLatencyP50Ms", "guardLines", "guardTestSeconds")


def budget_findings(budgets, measured):
    """Every finding of the budgets against the measurements, both directions. Pure.

    Each table is `{"slack": s, "max": {key: ceiling}}`: above the ceiling is GREW, under `ceiling * (1 - s)` is SHRANK. A key measured and not budgeted, or budgeted and not measured, is a finding too, so the table cannot quietly stop covering a guard.
    """
    findings = []
    for table in TABLES:
        spec = budgets.get(table)
        live = measured.get(table) or {}
        if not isinstance(spec, dict) or not isinstance(spec.get("max"), dict) or not spec["max"]:
            findings.append("budgets.%s.max is missing or empty, so nothing would be held" % table)
            continue
        slack, pinned = spec.get("slack"), spec["max"]
        if not isinstance(slack, (int, float)) or not 0 < slack < 1:
            findings.append("budgets.%s.slack must be between 0 and 1, got %r" % (table, slack))
            continue
        findings.extend(
            "%s %s has no budget (measured %r); add one" % (table, k, live[k])
            for k in sorted(set(live) - set(pinned))
        )
        findings.extend(
            "%s %s has a budget and nothing measures it; drain the entry" % (table, k)
            for k in sorted(set(pinned) - set(live))
        )
        for k in sorted(set(pinned) & set(live)):
            ceiling, got = pinned[k], live[k]
            if not isinstance(got, (int, float)):
                findings.append("%s %s: measured %r is not a number (unmeasured)" % (table, k, got))
            elif got > ceiling:
                findings.append(
                    "%s %s GREW past its budget: %r > %r. Shrink it, or raise the budget in the "
                    "same change with the reason" % (table, k, got, ceiling)
                )
            elif got < ceiling * (1 - slack):
                findings.append(
                    "%s %s SHRANK more than %d%% under its budget: %r against %r. Repin with "
                    "--write-budgets so the next regression is caught"
                    % (table, k, round(slack * 100), got, ceiling)
                )
    return findings


def write_budgets(budgets, measured):
    """(block, added) with every budget repinned at measured * (1 + slack / 2), which sits inside both directions; prose keys are kept.

    LOWERS AND ADDS, NEVER RAISES. A ceiling the measurement has grown past is refused here and named, because a repin that raised it would enshrine the regression the budget exists to catch: raise it by hand, in the change that needs it, with the reason. `added` names every new key so the caller prints them and a reader sees what joined.
    """
    out = dict(budgets)
    added, grew = [], []
    for table in TABLES:
        spec = dict(budgets.get(table) or {})
        slack = spec.get("slack")
        if not isinstance(slack, (int, float)) or not 0 < slack < 1:
            raise ReportError("budgets.%s.slack must be between 0 and 1, got %r" % (table, slack))
        old = spec.get("max") or {}
        new = {}
        for k, v in sorted((measured.get(table) or {}).items()):
            if not isinstance(v, (int, float)):
                continue
            if k in old and v > old[k]:
                grew.append("%s %s: %r > %r" % (table, k, v, old[k]))
                continue
            pin = (
                round(v * (1 + slack / 2), 1)
                if isinstance(v, float)
                else math.ceil(round(v * (1 + slack / 2), 6))
            )
            new[k] = min(pin, old[k]) if k in old else pin
            if k not in old:
                added.append("%s %s" % (table, k))
        spec["max"] = new
        out[table] = spec
    if grew:
        raise ReportError(
            "refusing to raise %d budget(s) by repinning; raise each by hand with the reason: %s"
            % (len(grew), "; ".join(grew))
        )
    return out, added


# --------------------------------------------------------------------------- CLI


def main(argv, root=CHECKOUT):
    root = pathlib.Path(root)
    try:
        if argv == ["--report"]:
            print(report(root))
            return 0
        if argv == ["--snapshot"]:
            rows = read_jsonl(root.joinpath(*LEDGER_REL))
            doc = snapshot(rows, inventory(root))
            path = root.joinpath(*SNAPSHOT_REL)
            path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
            print(
                "wrote %s: %d rows over %.1f days, %d chains, %d guards, %d overlap pair(s)"
                % (
                    path,
                    doc["window"]["rows"],
                    doc["window"]["days"],
                    len(doc["chains"]),
                    len(doc["guards"]),
                    len(doc["overlaps"]),
                )
            )
            return 0
        if argv == ["--check-snapshot"]:
            doc = _read_json(root.joinpath(*SNAPSHOT_REL), "the hook ledger snapshot")
            inv = inventory(root)
            findings = check_snapshot(doc, inv)
            for f in findings:
                print("  " + f, file=sys.stderr)
            if findings:
                print(
                    "hook ledger snapshot: %d finding(s). Refresh: python3 "
                    ".claude/hooks/stop/wl_hookreport.py --snapshot" % len(findings),
                    file=sys.stderr,
                )
                return 1
            print(
                "hook ledger snapshot: %d rows, refreshed %s, %d guards"
                % (doc["window"]["rows"], doc["refreshed_at"], len(inv))
            )
            return 0
        if argv in (["--check-budgets"], ["--write-budgets"]):
            path = root.joinpath(*BASELINE_REL)
            baseline = _read_json(path, "the hook exec baseline")
            measured = measure(root, baseline)
            budgets = baseline.get("budgets")
            if not isinstance(budgets, dict):
                raise ReportError("%s has no `budgets` block" % path)
            if argv == ["--write-budgets"]:
                baseline["budgets"], added = write_budgets(budgets, measured)
                path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
                for name in added:
                    print("  added %s" % name)
                print(
                    "repinned the budgets of %s at measured * (1 + slack / 2), %d added"
                    % (path, len(added))
                )
                return 0
            findings = budget_findings(budgets, measured)
            for f in findings:
                print("  " + f, file=sys.stderr)
            if findings:
                print("hook budgets: %d finding(s) in %s" % (len(findings), path), file=sys.stderr)
                return 1
            print(
                "hook budgets: %s, all within budget in both directions"
                % ", ".join("%d %s" % (len(measured[t]), t) for t in TABLES)
            )
            return 0
        if len(argv) == 2 and argv[0] == "--confirm" and argv[1].strip():
            print("recorded: %s in %s" % (argv[1], wl_trapfires.confirm(argv[1].strip())))
            return 0
    except ReportError as exc:
        print("wl_hookreport: %s" % exc, file=sys.stderr)
        return 1
    print(__doc__.split("\n\n", 1)[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

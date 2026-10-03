"""wl_planenforce: the blocking half of "implement the plans", scoped to the live PR's plan set (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 5, box SC6).

THE RULING. One plan per PR (operator rulings 2026-10-03): the Stop hook blocks on the PR's plan set, its `Plan:` plans and every unfinished plan they depend on, prerequisites first (`plan_gate.pr_plan_set`, read through `wl_prscope.loop_state`). Every other plan is queued and counted in one line, never blocked on. So `evaluate` takes the set as `scope` and judges only those plans, with no ceiling: the same rule P-A1 has followed since 2026-09-26 ("no threshold"). An empty scope (off the loop, or a branch with no PR yet) is silent.

THE BLOCK NAMES EXACTLY ONE BOX: the first open box of the first plan in the set that has one, which is the deepest unfinished prerequisite when one exists. Its exact `wl_planrec.box_sig` signature makes the printed `--plan-investigate` / `--plan-tick` pair copy-pasteable.

THE LIVE-WORK DOWNGRADE. With a background task of this session running (a writer on the box, a `ci-trace --wait`), the same body is an advisory rather than a block: a waited-on step is not a stall, and the box count of one plan is the exit.

THE CLOCK STAYS EXPORTED. `load_clock`, `ceiling` and `CLOCK_KEYS` are no longer read by the hook, but `.ci/scripts/quality/check_plan_implementation.py` imports them (its C10 pins the key tuple across the two halves), so they stay here, unchanged.

Reads no environment variable. This module must never import `wl_checks`, which imports it.
"""

import datetime as dt
import json
import pathlib
import re

import wl_planrec as R

#: The clock, committed, read by BOTH halves. `.ci/scripts/quality/check_plan_implementation.py` reads this same file through this same loader, which is what makes the CI gate and the Stop hook incapable of disagreeing about the number. plan-lifecycle.json's own $comment states the rule being obeyed: duplicating a number into two scripts is exactly what creates a deadlock.
CONFIG_REL = ".ci/config/plan-implementation.json"

#: The keys, and the SAME dict is what C10 pins across the two halves. A default here is a FALLBACK FOR A MISSING FILE, never a silent substitute for a malformed one: `load_clock` reports which of the two happened, and a caller that cannot read the config renders a diagnostic rather than a verdict.
CLOCK_KEYS = ("baseline_open", "baseline_at", "drain_per_day", "warn_slack", "floor_open")

#: What the gate falls back to when the config is absent entirely. Chosen so an absent config cannot ACCUSE anybody: `drain_per_day` 0 freezes the ceiling at the baseline, and a baseline of 0 with a floor of 0 would make every tree over ceiling, so the loader reports the absence instead and the caller goes silent. See `load_clock`.
CLOCK_DEFAULTS = {
    "baseline_open": 0,
    "baseline_at": "",
    "drain_per_day": 0,
    "warn_slack": 0,
    "floor_open": 0,
}

#: Verdict states. `silent` is silent, not quiet-but-present: a check that talks while it is satisfied is a check nobody reads.
SILENT, ADVISORY, BLOCK = "silent", "advisory", "block"


def load_clock(root):
    """(clock, problem). `problem` is "" when the file was read and parsed.

    A MISSING CONFIG IS NOT A PASS AND NOT AN ACCUSATION. It is reported to the caller, which goes silent rather than blocking on numbers it does not have: the config is committed beside the gate, so its absence means a broken checkout rather than a session that failed to drain anything, and accusing one for the other is how a gate earns its way into being switched off.
    """
    path = pathlib.Path(root) / CONFIG_REL
    clock = dict(CLOCK_DEFAULTS)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return clock, "%s cannot be read (%s)" % (CONFIG_REL, exc)
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return clock, "%s does not parse (%s)" % (CONFIG_REL, exc)
    if not isinstance(doc, dict):
        return clock, "%s is not a JSON object" % CONFIG_REL
    missing = [k for k in CLOCK_KEYS if k not in doc]
    if missing:
        return clock, "%s is missing %s" % (CONFIG_REL, ", ".join(missing))
    for key in CLOCK_KEYS:
        clock[key] = doc[key]
    return clock, ""


def _days_since(baseline_at, today):
    """Whole days from `baseline_at` to `today`, never negative and never None.

    Never negative because a clock that runs backwards would hand a session slack it did not earn by setting a landing date in the future, and the honest reading of "not yet started" is day 0.
    """
    try:
        start = dt.date.fromisoformat(str(baseline_at or "").strip())
    except ValueError:
        return 0
    return max(0, (today - start).days)


def ceiling(clock, today=None):
    """(ceiling, days_elapsed) for one day. Pure arithmetic, no I/O.

        ceiling(d) = max(floor_open, baseline_open - floor(d * drain_per_day))

    EXPORTED AND PURE so the controls can assert the clock at THREE points -- day 0 silent, day 1 with nothing closed red, day 1 with a day's drainage silent again. A clock asserted at one point is a constant, and a constant that happens to hold today is the exact shape of a check that cannot fail.
    """
    # dt.datetime.now(dt.UTC).date() rather than dt.date.today(): the ceiling is a claim about a DATE, and a machine in a different timezone must not read a different ceiling off the same committed baseline.
    today = today or dt.datetime.now(dt.UTC).date()
    days = _days_since(clock.get("baseline_at"), today)
    base = int(clock.get("baseline_open") or 0)
    rate = int(clock.get("drain_per_day") or 0)
    floor = int(clock.get("floor_open") or 0)
    return max(floor, base - days * rate), days


def _read_text(root, rel):
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def first_box(root, rel, reader=None):
    """(sig, body) of the FIRST open box in one plan, or None. One file read.

    The signature is `wl_planrec.box_sig`, which is what the committed ledger, the compaction record and the investigation row all speak. `wl_planfid.TASK_MATCH` and `wl_planfile.match_item`'s token overlap are deliberately NOT used: fuzzy matching has no business in a blocking path, and an exact 8-hex signature is what makes the printed recipe copy-pasteable.
    """
    text = (reader or _read_text)(root, rel)
    if not text:
        return None
    try:
        boxes = R.open_boxes(text)
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        return None
    if not boxes:
        return None
    _i, _line, body, sig = boxes[0]
    return sig, body


def plan_rows(root, scope, reader=None):
    """[(rel, open_count, first_box)] for each plan in `scope`, in scope order, keeping only plans with an open box that can be worked before the merge (`after_merge` boxes are left out of both the count and the choice). `first_box` is (sig, body) or None when the parser resolves none in the plan's own text."""
    out = []
    for rel in scope or ():
        text = (reader or _read_text)(root, rel)
        try:
            boxes = R.open_boxes(text) if text else []
        except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
            boxes = []
        workable = [b for b in boxes if not after_merge(b[2])]
        if workable:
            _i, _line, body, sig = workable[0]
            out.append((rel, len(workable), (sig, body)))
    return out


# A box whose own `Depends on:` clause names a merge ("this PR's merge", "GR3 merged to main") cannot be done before the PR merges. It is never the named next box and never holds the turn: the merge gate admits it under the PR body's `Operational-Reason:` (plan_gate.plan_merge_refusal), so blocking on it would hold a PR that is ready to merge (2026-10-03: GR11 and GR12 of PLAN-github-pr-review-restore).
AFTER_MERGE = re.compile(r"Depends on:[^.]*\bmerge(?:d|s)?\b", re.IGNORECASE)


def after_merge(body):
    """True when the box's own `Depends on:` clause waits for a merge."""
    return bool(AFTER_MERGE.search(body or ""))


def render(rows, scope, session_id):
    """The body: the plan set's open counts, then the one named box and the commands that close it. NO LIVE COUNTER, so the advisory delivery's content signature keeps it from repeating while nothing changes."""
    me8 = (session_id or "")[:8]
    lines = [
        "PR PLAN SET OPEN -- %d open box(es) across %d of its %d plan(s), prerequisites first:"
        % (sum(n for _r, n, _f in rows), len(rows), len(scope))
    ]
    lines.extend("    %s  %d open" % (rel, n) for rel, n, _f in rows)
    rel, _n, (sig, body) = rows[0]
    lines.extend(
        [
            "",
            "  THE NEXT BOX (%s):" % rel,
            "    %s  %s" % (sig, body[:120]),
            "",
            "  Real work: do it (inline or through a writer), then tick it. Already landed? Investigate, then tick:",
            (
                "    worklist.py --plan-investigate %s %s %s present|absent|partial "
                "<kind>:<token> -- <what was looked at> --write" % (me8, rel, sig)
            ),
            "    worklist.py --plan-tick %s %s %s '<evidence>' --write" % (me8, rel, sig),
            (
                "  Genuinely the operator's call: worklist.py --defer %s <id> "
                "'<q> DEFAULT: <action> WHY: ... HOW: ...'" % me8
            ),
            "  A finished `Status:` over open boxes is not a door: check:ci-plan-boxes G-A3 refuses it.",
        ]
    )
    return "\n".join(lines)


def evaluate(root, scope, session_id, live=False, read_text=None):
    """(state, text, detail) for one stop: `block` while a plan of `scope` has an open box and `live` is False, `advisory` for the same with a background task of this session running, `silent` otherwise.

    `scope` is the PR's plan set, prerequisites first (`LoopState.plans`); () is silent. A plan whose text resolves no open box is skipped, so the named box is the first one the parser can see. Every read failure degrades to silence with a reason in `detail`, never to a block on numbers this could not read.
    """
    scope = tuple(scope or ())
    detail: dict = {"reason": "", "rows": []}
    if not scope:
        detail["reason"] = "no PR plan set in scope"
        return SILENT, "", detail
    rows = plan_rows(root, scope, read_text)
    detail["rows"] = [(rel, n) for rel, n, _f in rows]
    if not rows:
        detail["reason"] = "every plan of the PR's set is ticked"
        return SILENT, "", detail
    return (ADVISORY if live else BLOCK), render(rows, scope, session_id), detail

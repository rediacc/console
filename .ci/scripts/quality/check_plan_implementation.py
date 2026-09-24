#!/usr/bin/env python3
"""check:ci-plan-implementation -- the plan corpus is being DRAINED, and every box this branch closed can be re-derived rather than believed.

WHY THIS EXISTS. The operator's ask, paraphrased because the verbatim wording carries a first-person pronoun the house style keeps out of prose: the repo plans and does not implement, and the stated aim is to eliminate 'planned but not implemented'. Offered three narrower scopes -- per-PR-diff, per-branch, per-plan-adoption -- the answer was ALL. Design:
agent/plans/PLAN-plan-implementation-enforcement.md.

THIS GATE DOES NOT RE-SCAN `agent/`, AND THAT IS THE WHOLE REASON IT CAN BE SMALL. `.ci/config/plan-boxes.json` is already a committed second reading of every checkbox in the corpus, and check:ci-plan-boxes G-A0 already proves it equals the tree. So P-A0 asks that sibling whether the ledger still agrees and REFUSES TO JUDGE if it does not; every assertion after that reads the
ledger. A second parser here would be a second opinion about what a box is, which is exactly what the ledger exists to prevent.

THE ASYMMETRY WITH THE STOP HOOK IS DELIBERATE AND STATED. `wl_planenforce` knows WHO IS RUNNING and adjusts what it demands of that session: boxes owned by a peer this machine reads as live are subtracted, because demanding drainage of work somebody else is doing right now makes the ceiling unreachable by any action. CI has no liveness oracle and must not invent one, so P-A1
compares the WHOLE in-scope count with no ownership term at all. A branch whose peers are all idle owes all of it.

FORWARD-ONLY, AND THE CUT IS ONE COMMITTED DATE. Measured corpus-wide before this was written: 13 `    (ticked) ` evidence lines across all four plan folders, all of them in ONE file, against 589 done boxes. About 2% of the boxes `--plan-tick` was written for went through it; the rest were flipped with the Edit tool and carry nothing to re-check, ever. So P-A2..P-A4 judge a box
only when the commit that ticked it is dated STRICTLY AFTER `baseline_at`, the landing date in `.ci/config/plan-implementation.json`. On the landing commit that set is empty by construction and this gate is silent, which is the point: nobody is punished for a tick that predates the rule, and the very next day's ticks are bound. A control pins both sides of that cut, because a
date comparison that always answers "exempt" is a gate that cannot fail.

CONTROL-FIRST, the shape `.ci/scripts/quality/check_hint_corpus.py` established here. Before the real corpus is judged at all, every assertion below is driven against synthetic inputs carrying one planted defect apiece, plus a healthy fixture that must stay silent under all of them. If any plant is not caught, this gate declares itself broken and exits non-zero WITHOUT judging
the real corpus.

THE GATE SHIPS WITH NO ALLOWLIST, NO SUPPRESSION AND NO BYPASS. docs/agent-reference/suppressions.md governs every escape hatch in this repo, and an allowlist here would be an allowlist against "implement the plan", which is the whole ask. The clock is in config so it can be RETUNED, which is a different thing from exempting a file.

---- gate ----
step: Plan implementation clock
needs: none
selftest: true
lane: quality-branch
---- end gate ----
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
from typing import Any

import _cipath  # noqa: F401
from rediacc_ci import paths

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
CONFIG_REL = ".ci/config/plan-implementation.json"
LEDGER_REL = ".ci/config/plan-boxes.json"

#: Anti-vacuity floors. Well under the live numbers (120 plans, 810 raw checkbox lines on 2026-09-22) so an added plan is never a failure, and far enough above zero that an emptied, relocated or mis-globbed corpus reds instead of passing over nothing. Same device check_plan_boxes.py's G-A6 uses, same reason.
MIN_PLANS = 20
MIN_BOXES = 60

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def _today():
    """Today's date in UTC.

    `dt.date.today()` reads the machine's local timezone, so a runner an hour either side of midnight would compare the same committed baseline against a different ceiling. The clock is a claim about a DATE and both halves compute it the same way.
    """
    return dt.datetime.now(dt.UTC).date()


def die(msg: str) -> None:
    print(f"{RED}x{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_modules():
    """The Stop-hook module and the sibling gate, with contract guards on both.

    A MISSING MODULE IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE, never a stack trace that reads as flake and never a pass over an absent subject. The two imports are the entire oracle set of this gate: `wl_planenforce` owns the clock and `check_plan_boxes` owns the ledger-versus-tree comparison, and neither is re-implemented here.
    """
    if not os.path.isdir(HOOK_DIR):
        die(f"{HOOK_DIR} not found; cannot read a clock that is not there")
    paths.on_sys_path(HOOK_DIR)
    try:
        import wl_planenforce as E  # noqa: PLC0415
        import wl_planfile as PF  # noqa: PLC0415
        import wl_planrec as R  # noqa: PLC0415
    except ImportError as exc:
        die(
            f"cannot import the Stop-hook plan modules ({exc}). Refusing to pass while "
            "measuring nothing. They live in .claude/hooks/stop/."
        )
    for name, mod, fns in (
        ("wl_planenforce", E, ("load_clock", "ceiling", "CLOCK_KEYS")),
        ("wl_planrec", R, ("resolve", "read_investigations", "ledger_at", "box_sig")),
        ("wl_planfile", PF, ("FINISHED_STATES",)),
    ):
        for fn in fns:
            if not hasattr(mod, fn):
                die(
                    f"{name}.{fn} is missing (renamed? removed?). The contract this gate reads "
                    "changed; update the gate deliberately rather than letting it pass."
                )
    spec = importlib.util.spec_from_file_location(
        "_cpb", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_plan_boxes.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load module spec")
    boxes_gate = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(boxes_gate)
    except Exception as exc:  # noqa: BLE001
        die(f"cannot load check_plan_boxes.py ({exc}); P-A0 has no oracle to ask")
    for fn in (
        "scan",
        "diff_problems",
        "transition_problems",
        "base_ledger",
        "base_ref",
        "_added_plans",
    ):
        if not hasattr(boxes_gate, fn):
            die(
                f"check_plan_boxes.{fn} is missing. P-A0 and P-A5 both read that gate rather "
                "than duplicating it; fix the wiring deliberately."
            )
    return E, PF, R, boxes_gate


# --------------------------------------------------------------------------- P-A1, the clock. Pure arithmetic over three numbers, so the control can assert it at three points rather than at the one that happens to hold today.


def in_scope(ledger_plans, finished_states):
    """(n_plans, n_open) for the ledger rows that are IN SCOPE.

    `finished_states` is IMPORTED from `wl_planfile` by the caller rather than restated, exactly as check_plan_boxes.py's G-A3 does it: the Stop hook's scope and this gate's scope are one frozenset read twice, so the two halves cannot drift into disagreeing about which plans count.

    `NOT_STARTED_STATES` IS DELIBERATELY NOT APPLIED. `draft` is this repo's default header on plans under active execution and carries most of the debt; exempting it would leave this gate asserting almost nothing.
    """
    n_plans = n_open = 0
    for _rel, row in sorted((ledger_plans or {}).items()):
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() in finished_states:
            continue
        open_n = int(row.get("open") or 0)
        if open_n <= 0:
            continue
        n_plans += 1
        n_open += open_n
    return n_plans, n_open


def clock_findings(ceiling_fn, clock, n_open, today):
    """P-A1. [] when the count is at or under today's ceiling.

    The message names the count, the ceiling, the date and how many ticks close the gap, because "over budget" without the number is a verdict a reader cannot act on.
    """
    ceil, days = ceiling_fn(clock, today)
    if n_open <= ceil:
        return []
    return [
        "P-A1 THE CLOCK: %d in-scope open box(es) against a ceiling of %d on %s (day %d of the "
        "clock, draining %s/day from a baseline of %d written at %s). %d tick(s) close the gap. "
        "The ceiling descends every day and does not stop; there is no allowlist for this gate "
        "and no per-plan exemption, because an exemption here would be an exemption from "
        "implementing the plan."
        % (
            n_open,
            ceil,
            today.isoformat(),
            days,
            clock.get("drain_per_day"),
            clock.get("baseline_open"),
            clock.get("baseline_at"),
            n_open - ceil,
        )
    ]


# --------------------------------------------------------------------------- P-A2/P-A3/P-A4, the forward-only proof. Every oracle is injected so the controls drive the same function the real run does.


def moved_to_done(base_plans, head_plans):
    """[(rel, sig)] for every box this branch CLOSED. Two cases, and the second was a gap.

    A box already done at the base is NEVER judged, and neither is a box that is still open. The set this returns is exactly "what this branch claims to have finished", which is the only set a proof rule can honestly bind.

    THE SECOND CASE IS A PLAN THE BASE NEVER HAD, and leaving it out was a hole measured on this gate's own landing tree: the plan being implemented was itself new on the branch, so all sixteen of its boxes were added AND ticked here, `base_plans` held no row for it at all, and the first version of this function returned ZERO judged boxes while reporting a clean run. A session
    could write a plan, tick every box with no evidence and no investigation row, and P-A2 would see nothing.

    It is NOT a false-positive surface, because the date cut still applies downstream: a plan imported with boxes already ticked has `done_commit` dates at or before `baseline_at` and is exempt for the same reason every other pre-landing tick is. What is caught is the case that matters -- a box ticked on this branch AFTER the rule arrived.
    """
    out: list[Any] = []
    for rel, head_row in sorted((head_plans or {}).items()):
        if not isinstance(head_row, dict):
            continue
        base_row = (base_plans or {}).get(rel)
        head_done = sorted(set(head_row.get("done_sigs") or []))
        if not isinstance(base_row, dict):
            out.extend((rel, sig) for sig in head_done)
            continue
        was_open = set(base_row.get("open_sigs") or [])
        was_done = set(base_row.get("done_sigs") or [])
        out.extend((rel, sig) for sig in head_done if sig in was_open and sig not in was_done)
    return out


def after_baseline(baseline_at, when):
    """Is a tick dated STRICTLY AFTER the landing date?

    STRICTLY, so the landing day itself is amnesty: `baseline_at` is the day the rule arrives, and a tick made that same day was made under the old rule. An unknown or unparseable date answers False, which exempts rather than accuses -- the forward-only rule has no business ruling on a commit whose date it could not read.
    """
    try:
        base = dt.date.fromisoformat(str(baseline_at or "").strip())
    except ValueError:
        return False
    if not when:
        return False
    try:
        got = dt.date.fromisoformat(str(when).strip()[:10])
    except ValueError:
        return False
    return got > base


def bound_by_the_rule(judged, done_commit_of, date_of, baseline_at):
    """[(rel, sig)] -- the subset of closed boxes the forward-only rule actually BINDS.

    SEPARATE FROM `tick_findings` SO THE SUMMARY CAN PRINT IT. On the landing tree 619 boxes had moved open -> done and NONE of them was bound, because every one predates `baseline_at` or is not committed yet. A success line that reported the 619 and stayed silent about the 0 would read exactly like a proof that ran, which is the vacuity this whole estate keeps paying for. Print
    both numbers and a reader can see the day the second one starts moving.
    """
    return [
        (rel, sig)
        for rel, sig in judged
        if after_baseline(baseline_at, date_of(done_commit_of(rel, sig)))
    ]


def tick_findings(
    judged, evidence_of, row_of, resolve_fn, done_commit_of, date_of, ancestor_fn, baseline_at
):
    """P-A2, P-A3 and P-A4 over one branch's newly-done boxes. [] when they hold.

    P-A2 every judged box carries an `(ticked)` evidence line in the plan AND a
          matching investigation row.
    P-A3 every pointer on that row is RE-RESOLVED IN THE CI CHECKOUT, never
          trusted from the row's own `resolved` field. A row whose pointers
          resolved locally and not here is a finding, and the message says which
          kind failed. `ancestor` is the kind most likely to differ, which is
          exactly why the row's own answer is not read.
    P-A4 `merge-base --is-ancestor <row.head> <the commit that ticked the box>`.
          Clause 1 of the design, enforced where the full topology is available.

    Every oracle is a parameter. That is not abstraction for its own sake: it is what lets the controls drive THIS function -- the one the real run calls -- against planted inputs, rather than a copy of it that could pass while the real one is broken.
    """
    out = []
    for rel, sig in bound_by_the_rule(judged, done_commit_of, date_of, baseline_at):
        commit = done_commit_of(rel, sig)
        if not evidence_of(rel, sig):
            out.append(
                "P-A2 %s box %s moved open -> done in %s with no `    (ticked) ` evidence line "
                "beneath it. `worklist.py --plan-tick` writes that line; a box flipped with the "
                "Edit tool leaves nothing a later reader can check." % (rel, sig, commit[:12])
            )
        row = row_of(rel, sig)
        if row is None:
            out.append(
                "P-A2 %s box %s was closed with no row in agent/ledgers/plan-investigation.jsonl. "
                "The rule is investigate, then implement, then tick -- so that a box already done "
                "is closed by finding it rather than by doing it again. Record what was looked at:"
                "\n    worklist.py --plan-investigate <me> %s %s <absent|present|partial> "
                "<kind>:<token> <kind>:<token> -- <note> --write" % (rel, sig, rel, sig)
            )
            continue
        for kind, token in row.get("pointers") or []:
            ok, why = resolve_fn(kind, token)
            if not ok:
                out.append(
                    "P-A3 %s box %s: the investigation row's `%s:%s` pointer does not resolve in "
                    "this checkout -- %s. The row's own `resolved` field is deliberately not "
                    "read; a pointer that resolved on one machine and not here is the finding."
                    % (rel, sig, kind, token, why)
                )
        head = str(row.get("head") or "").strip()
        if head and commit and not ancestor_fn(head, commit):
            out.append(
                "P-A4 %s box %s: the investigation recorded HEAD=%s and the commit that ticked "
                "the box (%s) is not a descendant of it, so the investigation was written after "
                "the implementation rather than before it." % (rel, sig, head[:12], commit[:12])
            )
    return out


def vacuity_findings(n_plans_total, n_boxes_total, raw_ledger_rows):
    """P-A6. Zero inputs is a FAILURE, never a pass.

    Three floors, because the three ways this gate could go blind are different: a corpus that shrank below MIN_PLANS, a corpus whose boxes vanished, and a ledger that parsed to nothing at all while the tree plainly holds plans. The success line prints the counts too, so a reader can watch a number collapse instead of reading "OK".
    """
    out = []
    if raw_ledger_rows <= 0:
        out.append(
            "P-A6 VACUOUS: %s parsed to zero plan rows, so every assertion above is true over "
            "nothing, which reads exactly like a healthy corpus." % LEDGER_REL
        )
    if n_plans_total < MIN_PLANS:
        out.append(
            "P-A6 FLOOR: %d plan(s) in the ledger, under MIN_PLANS=%d. An emptied, truncated or "
            "relocated corpus reds instead of passing vacuously." % (n_plans_total, MIN_PLANS)
        )
    if n_boxes_total < MIN_BOXES:
        out.append(
            "P-A6 FLOOR: %d checkbox(es) in the ledger, under MIN_BOXES=%d."
            % (n_boxes_total, MIN_BOXES)
        )
    return out


# --------------------------------------------------------------------------- The controls. Every plant is driven BEFORE the real corpus is judged, and a plant that is not caught makes this gate declare itself broken.


def _clock(base=100, at="2026-01-01", rate=7, slack=20, floor=0):
    return {
        "baseline_open": base,
        "baseline_at": at,
        "drain_per_day": rate,
        "warn_slack": slack,
        "floor_open": floor,
    }


def controls_fired(enforce, planfile):
    """([missed], n_driven). `missed` names every planted defect that was NOT caught.

    THE COUNT IS DERIVED, NEVER A LITERAL. A constant in the success line saying "18 plants" is a claim about this function that nothing checks, and a plant deleted from the middle would leave the constant asserting coverage that is gone. `plant` both records and counts, so the two cannot disagree.
    """
    missed = []
    driven = []

    # NAMED `caught`, NOT `plant`, AND THE NAME IS LOAD-BEARING. `rediacc_ci.controls.plant` is this repo's mutation harness, which raises when a substitution silently does nothing, and `check-control-vacuity` reports any module that defines a local `plant` as one whose plants are unproven -- correctly, because a shadowed name reads as compliance. Nothing here builds a mutant by
    # substitution: every control drives the real judge with injected oracles, so the harness does not apply and borrowing its name would be a claim this file cannot make.
    def caught(label, fired):
        driven.append(label)
        if not fired:
            missed.append(label)

    # CONTROL 0 -- HEALTHY. Every judge must be silent on clean input, or every red below means nothing.
    clock = _clock(base=100, at="2026-01-01", rate=7)
    day0 = dt.date(2026, 1, 1)
    if clock_findings(enforce.ceiling, clock, 100, day0):
        die(
            "CONTROL 0 FAILED: the clock reported a finding at the baseline on day 0, so every planted result below is meaningless"
        )
    healthy_base = {"p.md": {"status": "draft", "open_sigs": ["aaaaaaaa"], "done_sigs": []}}
    healthy_head = {"p.md": {"status": "draft", "open_sigs": [], "done_sigs": ["aaaaaaaa"]}}
    healthy_row = {
        "plan": "p.md",
        "sig": "aaaaaaaa",
        "head": "H0",
        "verdict": "present",
        "pointers": [["fileline", "x.py:1"], ["commit", "C1"]],
    }
    healthy = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    if healthy:
        die(f"CONTROL 0 FAILED: a fully-evidenced tick was reported: {healthy}")
    if vacuity_findings(120, 810, 120):
        die("CONTROL 0 FAILED: a healthy corpus tripped an anti-vacuity floor")

    # C8 -- THE CEILING AT THREE POINTS. A clock asserted at one point is a constant.
    caught(
        "C8a: a corpus AT the baseline on day 0 was reported over the ceiling",
        not (clock_findings(enforce.ceiling, clock, 100, dt.date(2026, 1, 1))),
    )
    caught(
        "C8b: a corpus with ZERO boxes closed on day 1 was NOT reported over the ceiling",
        clock_findings(enforce.ceiling, clock, 100, dt.date(2026, 1, 2)),
    )
    caught(
        "C8c: a corpus that closed exactly drain_per_day boxes by day 1 was reported over the ceiling",
        not (clock_findings(enforce.ceiling, clock, 93, dt.date(2026, 1, 2))),
    )
    msg = " ".join(clock_findings(enforce.ceiling, clock, 100, dt.date(2026, 1, 2)))
    caught(
        "C8d: the over-ceiling message does not name the count, the ceiling, the date and the gap",
        ("100" in msg and "93" in msg and "7 tick" in msg and "2026-01-02" in msg),
    )

    # C1 -- THE INVESTIGATION-LESS TICK, the CI third of it. A box that moved open -> done carrying evidence but NO row must red on P-A2.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "exit 0, done, verified",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "C1: a tick with no investigation row was not reported P-A2",
        any(f.startswith("P-A2") and "plan-investigation" in f for f in got),
    )

    # C1b -- the same box WITH a row but with no `(ticked)` evidence line in the plan.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "C1b: a tick with no evidence line in the plan was not reported P-A2",
        any("no `    (ticked) ` evidence line" in f for f in got),
    )

    # P-A3 -- a pointer that resolved for the author and does NOT resolve here.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: dict(
            healthy_row, resolved=[["fileline", True, "lied"], ["commit", True, "lied"]]
        ),
        lambda k, _t: (k != "commit", "no such commit"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "P-A3: a pointer that fails to resolve in CI was not reported, or the row's own `resolved` field was trusted",
        any(f.startswith("P-A3") and "commit" in f for f in got),
    )

    # P-A4 / C5 -- the investigation written AFTER the implementation commit.
    got = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "ran the gate, exit 0",
        lambda _r, _s: healthy_row,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-05",
        lambda _a, _b: False,
        "2026-01-01",
    )
    caught(
        "P-A4: an investigation row written after the implementation commit was not reported",
        any(f.startswith("P-A4") for f in got),
    )

    # FORWARD-ONLY, BOTH SIDES. A date comparison that always answers "exempt" is a gate that cannot fail, so the cut is pinned in both directions.
    pre = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C0",
        lambda _c: "2026-01-01",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "FORWARD-ONLY: a box ticked ON the landing date was judged; the landing day is amnesty by design",
        not (pre),
    )
    post = tick_findings(
        moved_to_done(healthy_base, healthy_head),
        lambda _r, _s: "",
        lambda _r, _s: None,
        lambda _k, _t: (True, "ok"),
        lambda _r, _s: "C1",
        lambda _c: "2026-01-02",
        lambda _a, _b: True,
        "2026-01-01",
    )
    caught(
        "FORWARD-ONLY: a box ticked the day AFTER the landing date was NOT judged, so the cut exempts everything",
        post,
    )

    # moved_to_done -- a box already done at the base must never be judged.
    already = moved_to_done(
        {"p.md": {"open_sigs": [], "done_sigs": ["aaaaaaaa"]}},
        {"p.md": {"open_sigs": [], "done_sigs": ["aaaaaaaa"]}},
    )
    caught(
        "a box already done at the merge-base was judged, which is the retroactive demand this design forbids",
        not (already),
    )
    still_open = moved_to_done(
        {"p.md": {"open_sigs": ["aaaaaaaa"], "done_sigs": []}},
        {"p.md": {"open_sigs": ["aaaaaaaa"], "done_sigs": []}},
    )
    # THE PLAN THE BASE NEVER HAD. Measured as a live hole on this gate's own landing tree; see moved_to_done.
    caught(
        "a box on a plan this branch ADDED and ticked was not judged, so a new plan is a way past P-A2",
        moved_to_done({}, {"new.md": {"open_sigs": [], "done_sigs": ["bbbbbbbb"]}})
        == [("new.md", "bbbbbbbb")],
    )
    caught(
        "a plan this branch added with a box still OPEN was judged as closed",
        moved_to_done({}, {"new.md": {"open_sigs": ["bbbbbbbb"], "done_sigs": []}}) == [],
    )
    caught(
        "a box that is still open was judged as though it had been closed",
        not (still_open),
    )

    # THE BOUND SET IS THE NUMBER THE SUMMARY PRINTS, so it is controlled in both directions too.
    caught(
        "bound_by_the_rule bound a box ticked ON the landing date",
        bound_by_the_rule(
            [("p.md", "aaaaaaaa")], lambda _r, _s: "C0", lambda _c: "2026-01-01", "2026-01-01"
        )
        == [],
    )
    caught(
        "bound_by_the_rule did NOT bind a box ticked the day after, so the summary would report zero for ever",
        bound_by_the_rule(
            [("p.md", "aaaaaaaa")], lambda _r, _s: "C1", lambda _c: "2026-01-02", "2026-01-01"
        )
        == [("p.md", "aaaaaaaa")],
    )

    # P-A6 -- anti-vacuity, all three floors.
    caught(
        "P-A6: a ledger parsing to zero rows was not refused",
        any("VACUOUS" in f for f in vacuity_findings(120, 810, 0)),
    )
    caught(
        "P-A6: a corpus under MIN_PLANS was not refused",
        any("MIN_PLANS" in f for f in vacuity_findings(3, 810, 3)),
    )
    caught(
        "P-A6: a corpus under MIN_BOXES was not refused",
        any("MIN_BOXES" in f for f in vacuity_findings(120, 5, 120)),
    )

    # C10 -- THE RECURSIVE CLAUSE. Both halves must read the SAME key names out of the SAME file, so a rename in one cannot leave the other reading a default. Asserted as OBJECT IDENTITY rather than by comparing two literals: a copied tuple would satisfy an equality test and still drift.
    caught(
        "C10: in_scope moved out of this module unexpectedly",
        in_scope.__module__ == __name__,
    )
    caught(
        "C10: this gate does not read wl_planenforce's own CLOCK_KEYS, so a key rename could leave the two halves reading different fields",
        not (CLOCK_KEYS is not enforce.CLOCK_KEYS),
    )
    caught(
        "C10: the two halves name different config files (%s vs %s)"
        % (enforce.CONFIG_REL, CONFIG_REL),
        enforce.CONFIG_REL == CONFIG_REL,
    )
    caught(
        "C10: this gate does not read wl_planfile's own FINISHED_STATES, so the two halves could disagree about which plans are in scope",
        not (FINISHED_STATES is not planfile.FINISHED_STATES),
    )

    # in_scope -- the FINISHED filter must actually filter, and must not filter everything.
    scoped = in_scope(
        {
            "live.md": {"status": "draft", "open": 4},
            "hist.md": {"status": "done", "open": 9},
            "clean.md": {"status": "draft", "open": 0},
        },
        planfile.FINISHED_STATES,
    )
    caught(
        "in_scope: the FINISHED/zero-box filter returned %r, wanted (1, 4)" % (scoped,),
        scoped == (1, 4),
    )
    return missed, len(driven)


#: BOUND AT RUN TIME FROM THE STOP-HOOK MODULES, never restated as literals here, and C10 asserts the binding is by IDENTITY rather than by equality. A copied tuple satisfies an equality test and still drifts the day one half is renamed; a shared object cannot.
CLOCK_KEYS = None
FINISHED_STATES = None

#: A FLOOR under the number of plants, not the number itself. The count is derived from `controls_fired` and printed, so a collapse is visible; this catches the other direction, where a plant loop silently stops running and reports a small honest number nobody reads.
MIN_CONTROLS = 15


def main(argv=None) -> int:
    global CLOCK_KEYS, FINISHED_STATES  # noqa: PLW0603 -- see C10: the two halves must share the OBJECT, not a copy

    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_only = "--selftest" in argv or "--selftest-only" in argv

    cfg = os.path.join(REPO_ROOT, CONFIG_REL)
    if not os.path.isfile(cfg):
        print(
            f"{RED}x VACUOUS INPUT{NC}: {CONFIG_REL} does not exist, so there is no clock to "
            "compare against. A missing config makes every assertion true over nothing, which "
            "reads exactly like a drained corpus. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1
    if not os.path.isfile(os.path.join(REPO_ROOT, LEDGER_REL)):
        print(
            f"{RED}x VACUOUS INPUT{NC}: {LEDGER_REL} does not exist, so the corpus this gate "
            "reads is absent. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1

    enforce, planfile, planrec, boxes_gate = load_modules()
    CLOCK_KEYS = enforce.CLOCK_KEYS
    FINISHED_STATES = planfile.FINISHED_STATES

    print("plan implementation clock: controls first, then the verdict")
    missed, n_driven = controls_fired(enforce, planfile)
    if missed:
        print(
            f"{RED}x{NC} CONTROLS DID NOT FIRE, so this gate cannot detect what it exists for; "
            "no verdict is rendered and the real corpus was not judged:",
            file=sys.stderr,
        )
        for m in missed:
            print(f"  {m}", file=sys.stderr)
        # 2, NOT 1, and it is not arbitrary: these gates use 1 for "the tree has a finding" and 2 for "the instrument is broken, so there is no verdict". A caller that collapsed the two would report a defective gate as a defective tree.
        return 2
    if n_driven < MIN_CONTROLS:
        print(
            f"{RED}x{NC} only {n_driven} plant(s) were driven, under MIN_CONTROLS={MIN_CONTROLS}. "
            "A control loop that stopped running reports a small honest number and reads as a "
            "pass; refusing a verdict rather than trusting a shrunken control set.",
            file=sys.stderr,
        )
        return 2
    print(
        f"  {n_driven} planted defect(s) were driven and every one was caught, before anything real was read"
    )
    # `--selftest` STOPS HERE. The controls are the claim that this instrument can fail; the verdict below is a claim about the tree, and a caller that wants only the first must not be made to pay for the second. test-planenforce.py's C10e drives exactly this mode.
    if selftest_only:
        return 0

    clock, problem = enforce.load_clock(REPO_ROOT)
    if problem:
        print(f"{RED}x{NC} {problem}", file=sys.stderr)
        return 1

    with open(os.path.join(REPO_ROOT, LEDGER_REL), encoding="utf-8") as fh:
        head_doc = json.load(fh)
    head_plans = head_doc.get("plans") or {}

    findings = []

    # ---- P-A0: the ledger IS the corpus, and the sibling gate says whether it still agrees with the tree. Refusing here rather than judging is what stops this gate papering over a red sibling.
    scanned = boxes_gate.scan(boxes_gate.ROOT)
    agree_problems = boxes_gate.diff_problems(scanned, head_doc)
    compared = len(scanned)
    if agree_problems:
        print(
            f"{RED}x{NC} P-A0: {LEDGER_REL} disagrees with the tree in "
            f"{len(agree_problems)} place(s), so every count below would be measured against a "
            "stale corpus. check:ci-plan-boxes owns this comparison and reports the remedy; "
            "REFUSING TO JUDGE rather than papering over it:",
            file=sys.stderr,
        )
        for problem_line in agree_problems[:5]:
            print(f"  {problem_line}", file=sys.stderr)
        return 1

    # ---- P-A5: the sibling gate that owns every way a box can DISAPPEAR must still be wired, or 221 boxes could be "drained" with `rm`. The check of the check, which TRAPS.md's check-cannot-fail names as a recursive clause.
    findings.extend(registration_findings(boxes_gate))

    # ---- P-A6 first among the value judgements, so a collapsed corpus cannot satisfy P-A1 by having nothing in it.
    raw_rows = len(head_plans)
    total_boxes = sum(
        int(r.get("open") or 0) + int(r.get("done") or 0)
        for r in head_plans.values()
        if isinstance(r, dict)
    )
    findings.extend(vacuity_findings(raw_rows, total_boxes, raw_rows))

    n_plans, n_open = in_scope(head_plans, planfile.FINISHED_STATES)
    findings.extend(clock_findings(enforce.ceiling, clock, n_open, _today()))

    # ---- P-A2/P-A3/P-A4: the forward-only proof over what this branch actually closed.
    base = boxes_gate.base_ref() or ""
    judged = []
    bound = []
    skipped_reason = ""
    if not base:
        skipped_reason = "no merge-base is available (not a pull_request checkout)"
    else:
        base_doc, err = boxes_gate.base_ledger(base)
        if err:
            skipped_reason = err
        elif not (base_doc.get("plans") or {}):
            skipped_reason = "the base predates the box ledger"
        else:
            judged = moved_to_done(base_doc.get("plans") or {}, head_plans)
            history = planrec.ledger_history(REPO_ROOT)
            rows = planrec.read_investigations(REPO_ROOT)
            bound = bound_by_the_rule(
                judged,
                lambda rel, sig: planrec.done_commit(history, rel, sig),
                lambda commit: planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit),
                clock.get("baseline_at"),
            )
            findings.extend(
                tick_findings(
                    judged,
                    lambda rel, sig: _evidence_line(REPO_ROOT, planrec, rel, sig),
                    lambda rel, sig: planrec.investigation_for(REPO_ROOT, rel, sig, rows),
                    lambda kind, token: planrec.resolve(REPO_ROOT, kind, token),
                    lambda rel, sig: planrec.done_commit(history, rel, sig),
                    lambda commit: planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit),
                    lambda a, b: planrec._git_ok(REPO_ROOT, "merge-base", "--is-ancestor", a, b),
                    clock.get("baseline_at"),
                )
            )

    if findings:
        print(f"{RED}x{NC} plan implementation:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    ceil, days = enforce.ceiling(clock, _today())
    print(
        f"{GREEN}v{NC} plan implementation: {n_open} in-scope open box(es) across {n_plans} plan(s), ceiling {ceil} on day {days}"
    )
    print(
        f"  {raw_rows} plan(s) and {total_boxes} checkbox(es) in {LEDGER_REL}, "
        f"{compared} compared against the tree by check:ci-plan-boxes' own comparison"
    )
    if skipped_reason:
        print(f"  forward-only proof SKIPPED, not passed: {skipped_reason}")
    else:
        print(
            f"  {len(judged)} box(es) moved open -> done on this branch, of which {len(bound)} "
            f"were ticked after {clock.get('baseline_at')} and are BOUND by the forward-only "
            "proof (evidence line, investigation row, pointers re-resolved here, ordering)."
        )
        if not bound:
            print(
                "  P-A2/P-A3/P-A4 therefore asserted NOTHING this run, which is the expected "
                "state on and before the landing day and is said out loud rather than folded "
                "into the green above."
            )
    print("  every plant above was caught first, so this green means the check can fail")
    return 0


def registration_findings(boxes_gate):
    """P-A5. The sibling gate that owns box DISAPPEARANCE must still be reachable.

    NOT A RE-IMPLEMENTATION of G-A1/G-A4/G-A5. This asserts they are still REGISTERED, so that unwiring check:ci-plan-boxes reds here instead of quietly turning `rm` into a way to drain 221 boxes. TRAPS.md's check-cannot-fail states the recursive clause this obeys: the check, and the check of the check.
    """
    out = []
    try:
        import wl_planrec as planrec  # noqa: PLC0415
        import wl_reggate as reggate  # noqa: PLC0415
    except ImportError as exc:
        return ["P-A5: cannot import the reachability oracle (%s)" % exc]
    scripts = planrec._package_scripts(REPO_ROOT)
    for key in ("check:ci-plan-boxes", "check:ci-plan-implementation"):
        if key not in scripts:
            out.append(
                "P-A5 %s is not a key in package.json. This gate reads the ledger that gate "
                "maintains; unwired, `rm` on a plan file becomes a way to drain the clock." % key
            )
        elif not reggate.gate_reachable(scripts, key, REPO_ROOT):
            out.append(
                "P-A5 %s exists in package.json but is NOT reachable from `npm run ci`, so it "
                "is a gate nothing runs." % key
            )
    if not hasattr(boxes_gate, "_added_plans"):
        out.append(
            "P-A5 check_plan_boxes._added_plans is gone, so G-A4 (new debt must name an Owner) cannot be running"
        )
    return out


def _evidence_line(root, planrec, rel, sig):
    """The `    (ticked) ` line beneath the box `sig` names, or "".

    READ FROM THE PLAN'S OWN TEXT, matched by SIGNATURE rather than by position in a list, so a plan that grew a paragraph above the box still answers correctly. `--plan-tick` inserts the evidence line immediately after the box line, which is what makes "the next line" the right place to look.
    """
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    for i, raw in enumerate(lines):
        m = planrec.BOX_LINE_RE.match(raw)
        if not m or m.group(1).lower() != "x":
            continue
        body = re.sub(r"[*_`]+", "", m.group(2)).strip()
        if planrec.box_sig(body) != sig:
            continue
        if i + 1 < len(lines) and planrec.TICK_LINE_RE.match(lines[i + 1]):
            return lines[i + 1].strip()
        return ""
    return ""


if __name__ == "__main__":
    raise SystemExit(main())

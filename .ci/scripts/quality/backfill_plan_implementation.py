#!/usr/bin/env python3
"""Backfill the investigation trail for plan boxes that were closed without one.

    python3 .ci/scripts/quality/backfill_plan_implementation.py --me <prefix>
    python3 .ci/scripts/quality/backfill_plan_implementation.py --me <prefix> --write

WHAT THIS REPAIRS, and why a purpose-built tool rather than a loop over the live CLI. Dispatched implementation sub-agents flipped plan checkboxes from `[ ]` to `[x]` with the Edit tool, doing real and verified work, and skipped the sanctioned `worklist.py --plan-investigate` / `--plan-tick` pipeline that stamps an evidence line into the plan and an investigation row into
`agent/ledgers/plan-investigation.jsonl`. `check:ci-plan-implementation` reports every one of those boxes under P-A2. The work is not in question; the audit trail is missing.

THE LIVE VERBS CANNOT BE RE-RUN ON THESE BOXES. `plan_investigate` and `plan_tick` both reach their box through `wl_planrec.open_boxes`, which returns only boxes whose mark is not `x`, so both refuse outright on a box that is already closed. That refusal is correct for their own job and leaves no path back. `wl_planrec.plan_backfill_investigation` is the narrow verb that does
have one, and this script is the batch driver for it. Design: agent/plans/PLAN-fix-plan-implementation-check-regression.md.

THE ENUMERATION IS THE GATE'S OWN. `moved_to_done`, `bound_by_the_rule` and `_evidence_line` are imported from `check_plan_implementation.py` rather than restated, so the set repaired here is the set the gate reports by construction, and a corpus that moved since the design was written is caught by the count assertion rather than worked around.

NOTHING HERE WRITES `.ci/config/plan-boxes.json`. A backfill inserts an evidence line beneath a box, which `wl_planfid.BULLET_RE` cannot see, and never touches a box mark -- so no signature moves and the committed box ledger stays true. `plan_backfill_investigation` asserts that invariant per box and refuses rather than writing.

NOT A GATE. This file carries no `---- gate ----` block and is not registered: it is a one-off recovery tool kept beside the gate it repairs, so a future session that hits the same class has the instrument rather than the archaeology.
"""

from __future__ import annotations

import argparse
import collections
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
GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_plan_implementation.py")

#: The plan this backfill executes, cited in every note so a later reader reaches the design rather than guessing at the intent.
DESIGN_PLAN = "PLAN-fix-plan-implementation-check-regression"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def die(msg: str) -> None:
    print(f"{RED}x{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_gate():
    """The gate module, with its own `load_modules` already run.

    Imported as a module rather than shelled out to, because the point is to enumerate through the SAME functions the verdict comes from. A copy of `moved_to_done` here would be a second opinion about which boxes are in scope, which is the failure the gate's own docstring spends a paragraph on.
    """
    paths.on_sys_path(HOOK_DIR)
    spec = importlib.util.spec_from_file_location("_cpi", GATE)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load module spec")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        die(f"cannot load {GATE} ({exc}); there is no enumeration to drive")
    for fn in ("load_modules", "moved_to_done", "bound_by_the_rule", "_evidence_line"):
        if not hasattr(mod, fn):
            die(
                f"check_plan_implementation.{fn} is missing. This script enumerates through the "
                "gate's own functions on purpose; fix the wiring deliberately rather than "
                "restating it here."
            )
    return mod


def enumerate_violations(gate, planrec, planenforce, boxes_gate):
    """(violations, judged, bound, history, meta). `violations` is [(rel, sig, commit, has_evidence)].

    A violation is a BOUND box -- one this branch closed, after the forward-only cut -- that is missing its investigation row, its evidence line, or both. The two are enumerated separately because they need different repairs: 95 boxes on the branch this was written for already carried a well-formed evidence line citing real commits, and overwriting one of those with a
    reconstruction would be strictly worse than leaving it alone.
    """
    with open(os.path.join(REPO_ROOT, gate.LEDGER_REL), encoding="utf-8") as fh:
        head_doc = json.load(fh)
    head_plans = head_doc.get("plans") or {}
    base = boxes_gate.base_ref() or ""
    if not base:
        die("no merge-base is available, so there is nothing to enumerate against")
    base_doc, err = boxes_gate.base_ledger(base)
    if err:
        die(err)
    if not (base_doc.get("plans") or {}):
        die("the base predates the box ledger; the gate itself would skip, so this must too")

    clock, problem = planenforce.load_clock(REPO_ROOT)
    if problem:
        die(problem)

    judged = gate.moved_to_done(base_doc.get("plans") or {}, head_plans)
    history = planrec.ledger_history(REPO_ROOT)
    rows = planrec.read_investigations(REPO_ROOT)

    commits: dict = {}

    def done_commit_of(rel, sig):
        key = (rel, sig)
        if key not in commits:
            commits[key] = planrec.done_commit(history, rel, sig)
        return commits[key]

    dates: dict = {}

    def date_of(commit):
        if commit not in dates:
            dates[commit] = planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit)
        return dates[commit]

    bound = gate.bound_by_the_rule(judged, done_commit_of, date_of, clock.get("baseline_at"))

    violations = []
    for rel, sig in bound:
        evidence = gate._evidence_line(REPO_ROOT, planrec, rel, sig)
        row = planrec.investigation_for(REPO_ROOT, rel, sig, rows)
        if row is not None and evidence:
            continue
        violations.append((rel, sig, done_commit_of(rel, sig), evidence))
    meta = {"base": base, "baseline_at": clock.get("baseline_at"), "date_of": date_of}
    return violations, judged, bound, history, meta


def commit_facts(planrec, commit):
    """(short, date, subject) for one closing commit, read out of git rather than assumed."""
    date = planrec._git_out(REPO_ROOT, "log", "-1", "--format=%cI", commit)[:10]
    subject = planrec._git_out(REPO_ROOT, "log", "-1", "--format=%s", commit)
    return commit[:9], date, subject


_HEX = re.compile(r"(?<![0-9a-zA-Z])([0-9a-f]{7,40})(?![0-9a-zA-Z])")


def reuse_pointers(planrec, checks, evidence, commit):
    """Extra pointers lifted from an evidence line that already exists, every one re-resolved here.

    REUSED RATHER THAN INVENTED, and only when it still resolves. A line written contemporaneously by a session that did the work usually names the artifact better than anything a batch tool can compose, so lifting its tokens makes the row point at the real thing. A token that no longer resolves is DROPPED rather than recorded: `plan_backfill_investigation` refuses the whole
    row on a dead pointer, and a reconstruction is not worth failing a repair over.
    """
    out: list[Any] = []
    if not evidence:
        return out
    for m in checks.CITE_RE.finditer(evidence):
        token = m.group(0)
        ok, _why = planrec.resolve(REPO_ROOT, "fileline", token)
        if ok:
            out.append("fileline:%s" % token)
            break
    for m in _HEX.finditer(evidence):
        token = m.group(1)
        if token == commit[: len(token)]:
            continue
        ok, _why = planrec.resolve(REPO_ROOT, "commit", token)
        if ok:
            out.append("commit:%s" % token)
            break
    return out


def compose(planrec, rel, commit, evidence, checks):
    """(pointers, note, evidence_line) for one box.

    The BASE PAIR is always `commit:<the commit that ticked the box>` plus `plan:<the plan>`, which is two pointers of two distinct kinds and is the floor `vet_pointers_and_note` enforces. Both are re-resolved by the verb and again by P-A3 in CI, so the pair is a triangulation rather than a formality: the commit is an object in the history and the plan is a file on disk.

    THE NOTE RUNS PAST 600 CHARACTERS ON A LONG SUBJECT and the verb clips it there, exactly as `plan_investigate` clips its own. That is the module's contract rather than a defect here, and the clipped tail only restates what the row's `backfill.head_is` field already says in a form a machine can read. The box itself is identified by the row's `sig` and `box` fields, so the
    note does not repeat them.
    """
    short, date, subject = commit_facts(planrec, commit)
    pointers = ["commit:%s" % commit, "plan:%s" % rel]
    pointers.extend(reuse_pointers(planrec, checks, evidence, commit))
    note = (
        "RETROACTIVE RECORD, written by %s.py under %s. This box was closed by real work that "
        "landed in %s (%s, %s) and was flipped to [x] with the Edit tool, so it never went "
        "through --plan-investigate/--plan-tick and carried no row here. The verdict is "
        "`present` because the work is in the tree at that commit; `head` is that commit's "
        "PARENT, the last tree in which the box's question was still open, rather than the live "
        "HEAD this row was written at."
        % (os.path.basename(__file__)[:-3], DESIGN_PLAN, short, date, subject[:80])
    )
    line = (
        "retroactive record: closed by %s (%s) %s -- trail backfilled under %s, which explains "
        "why this line post-dates the commit it cites" % (short, date, subject[:70], DESIGN_PLAN)
    )
    return pointers, note, line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--me", required=True, help="the session-id prefix the rows are attributed to")
    ap.add_argument("--write", action="store_true", help="write the plans and append the rows")
    ap.add_argument(
        "--expect-boxes",
        type=int,
        default=0,
        help="refuse unless exactly this many violations are enumerated; the design's own count",
    )
    ap.add_argument(
        "--expect-plans",
        type=int,
        default=0,
        help="refuse unless the violations span exactly this many plans",
    )
    args = ap.parse_args(argv)

    gate = load_gate()
    planenforce, _planfile, planrec, boxes_gate = gate.load_modules()
    import wl_checks as checks  # noqa: PLC0415 -- the hook dir is on sys.path only after load_gate

    if not hasattr(planrec, "plan_backfill_investigation"):
        die(
            "wl_planrec.plan_backfill_investigation is missing. This script is the batch driver "
            "for that verb and has no repair of its own; land Phase 0 first."
        )

    violations, judged, bound, history, meta = enumerate_violations(
        gate, planrec, planenforce, boxes_gate
    )
    plans = sorted({rel for rel, _s, _c, _e in violations})
    by_commit = collections.Counter(c for _r, _s, c, _e in violations)
    have_line = sum(1 for _r, _s, _c, e in violations if e)

    print("backfill: the enumeration comes from the gate's own functions, not from a list")
    print(f"  base {meta['base'][:12]}, forward-only cut {meta['baseline_at']}")
    print(f"  {len(judged)} box(es) moved open -> done on this branch, {len(bound)} are BOUND")
    print(f"  {len(violations)} violation(s) across {len(plans)} plan(s)")
    print(
        f"  {have_line} already carry a `    (ticked) ` line; {len(violations) - have_line} do not"
    )
    for commit, n in sorted(by_commit.items(), key=lambda kv: -kv[1]):
        short, date, subject = commit_facts(planrec, commit)
        parent = planrec._git_out(REPO_ROOT, "rev-parse", "--verify", "--quiet", "%s^" % commit)
        if not parent:
            # A root commit, or a failed rev-parse: say so instead of printing an empty sha.
            parent = "(none)"
        print(f"    {n:4d}  {short} {date} {subject[:62]}")
        print(f"          head = {parent[:9]} (its parent)")

    if args.expect_boxes and len(violations) != args.expect_boxes:
        die(
            f"{len(violations)} violation(s) enumerated but --expect-boxes said "
            f"{args.expect_boxes}. The corpus moved since this was planned; re-derive the "
            "numbers rather than working off a stale list."
        )
    if args.expect_plans and len(plans) != args.expect_plans:
        die(
            f"{len(plans)} plan(s) enumerated but --expect-plans said {args.expect_plans}. "
            "Re-derive rather than working off a stale list."
        )
    if not violations:
        print(f"{GREEN}v{NC} nothing to backfill")
        return 0

    # CHAINED PER PLAN, top to bottom by the verb's own re-derivation. Each call recomputes line indices from the text it was handed, so an insertion cannot shift a later box onto the wrong line, and one plan is written exactly once.
    texts: dict = {}
    rows = []
    refusals = []
    for rel, sig, commit, evidence in violations:
        pointers, note, line = compose(planrec, rel, commit, evidence, checks)
        try:
            row, _resolved, new_text = planrec.plan_backfill_investigation(
                REPO_ROOT,
                rel,
                sig,
                pointers,
                note,
                args.me,
                evidence=line,
                text=texts.get(rel),
                history=history,
            )
        except planrec.RecordError as exc:
            refusals.append("%s %s: %s" % (rel, sig, exc))
            continue
        texts[rel] = new_text
        rows.append(row)

    if refusals:
        print(f"{RED}x{NC} {len(refusals)} box(es) were REFUSED by the verb:", file=sys.stderr)
        for r in refusals:
            print(f"  {r}", file=sys.stderr)
        print(
            "  Nothing was written. A refusal here is the verb declining to manufacture a "
            "trail, which is the one thing it exists to not do.",
            file=sys.stderr,
        )
        return 1

    inserted = sum(1 for rel, sig, _c, e in violations if not e and rel in texts)
    print(f"  {len(rows)} row(s) composed, {inserted} evidence line(s) to insert")
    if not args.write:
        print("\n---- NOTHING was written. Re-run with --write. ----")
        return 0

    # THE PLANS FIRST, THEN THE LEDGER, the same ordering --plan-tick uses: a crash between them leaves plans carrying evidence lines and a ledger short of rows, which one more run of this script finishes. The other order leaves rows attesting lines no file carries.
    for rel, text in sorted(texts.items()):
        planrec.write_atomic(os.path.join(REPO_ROOT, rel), text)
    for row in rows:
        planrec.append_investigation(REPO_ROOT, row)
    print(
        f"{GREEN}v{NC} wrote {len(texts)} plan(s) and appended {len(rows)} row(s) to "
        f"{'/'.join(planrec.INVESTIGATION_REL)}"
    )
    print("  .ci/config/plan-boxes.json was NOT touched: no box mark moved and no signature did")
    print("  NOT COMMITTED. The plans and the ledger must land in the SAME commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""check:ci-plan-folders -- a plan lives in `agent/plans/`, moves once, and expires.

Logic is in `rediacc_ci.quality.plan_lifecycle`, which pytest and this file's `--selftest` import directly; contract section 5d puts the entry point where `scripts/gate-bind.ts` can see it. The reasoning for the shape, the two clocks and the stub is in that module's docstring and is not repeated here.

WHAT THIS GATE ADDS TO THE ONES ALREADY IN THE FAMILY. `check:ci-plan-housekeeping` asks how OLD a plan is, `check:ci-plan-boxes` asks whether its boxes survived, `check:ci-plan-record` asks whether a compaction record is honest. None of the three has ever asked WHERE a plan is or WHEN it leaves, which is why `agent/` accumulated 103 files at its root with no rule either way.

NINE FINDINGS, EACH WITH A PLANTED CONTROL:

    F1  a plan at the legacy path rather than under agent/plans/**
    F2  the folder disagrees with `Status:`
    F3  a terminal plan past terminal_days
    F4  a not-started plan past backlog_days, an open keep-or-archive question for the operator
    F5  a stub pointing at a stub, at itself, or at nothing
    F6  `moved_at` disagrees with the git history of the new path
    F7  a citation resolving to neither a file nor a tombstone
    F8  a tombstone whose blob does not resolve
    F9  the vacuity floor

F1 IS FATAL SINCE THE MIGRATION LANDED. It spent exactly one stage as an advisory, because a gate cannot red on the day it arrives over a tree where all 103 plans still sit at the legacy path: that is the shape that gets suppressed within a day, which is the failure docs/agent-reference/suppressions.md exists to prevent. The 103 moved in S4, so the escape hatch that made the
advisory possible is gone rather than left behind switched off -- a flag whose only job is finished is a suppression waiting for a reader who does not know why it is there.

THE VERBS.

    --check    (the default) the verdict
    --status   what is where, with no verdict at all
    --move P   git mv P into its folder, leave a stub, stamp First-Seen and moved_at, and
               remap every commit citation a rebase-merge rewrote (refuses an unprovable one);
               a move into _done/ or _removed/ also retires P's numbered entry from
               `## Promoted` in agent/plans/QUEUE.md and renumbers the rest
    --retire-promoted
               retire every `## Promoted` entry whose plan is already a moved stub (the
               repair for a queue that predates the retirement; check:ci-plan-record
               RQ-MOVED names each one)
    --sweep    what the terminal clock would delete, REFUSING to act without --write, and
               the backlog plans past backlog_days as an operator keep-or-archive question
    --keep P --asked <YYYY-MM-DDTHH:MMZ>
               the operator kept P: write `Kept: <today> ASKED:<minute>` under Status:,
               which restarts P's backlog clock from today
    --archive P --asked <YYYY-MM-DDTHH:MMZ>
               the operator archived P: set `Status: removed` with a `Removed-Why:` naming
               the answer, then --move it into _removed/, where the terminal clock takes over
    --update   write the tombstone section of agent/INDEX.md

THE SWEEP DELETES TERMINAL PLANS ONLY. A plan in `_done/` or `_removed/` past terminal_days is deleted and leaves a tombstone. A backlog plan past backlog_days is NEVER deleted or moved by the sweep, by the operator's ruling of 2026-10-28 (ASKED:2026-10-28T10:58Z, "they should be asked to the operator to keep or archive"): both the dry run and `--write` print it under an OPERATOR QUESTION heading with its path, title, Status and age, plus the `--keep` and `--archive` commands that record the answer. Both answer verbs refuse without a well-formed ASKED minute, so no agent can answer the question on the operator's behalf without naming when it was asked.

`--sweep` WITHOUT `--write` IS A REPORT AND EXITS 0. A sweeper that deleted by default is a program whose dry run is the dangerous one, and every other destructive verb in this repository is opt-in the same way.

WHAT A GREEN HERE DOES NOT MEAN. It does not mean the plans are good, or that their contents are current: this gate reads headers, paths and dates. It also cannot see a plan nobody ever wrote down, which is the failure mode the worklist covers and this file does not.

---- gate ----
step: Plan folders and retention
needs: none
selftest: true
lane: quality-branch
why: a plan lives under agent/plans/, moves exactly once at close into _done/ or
     _removed/ leaving a stub, and expires on one of two clocks. Nothing else in
     the plan family asks where a plan is or when it leaves, so without this the
     layout holds only by the care of whoever last touched it.
---- end gate ----
"""

import datetime as dt
import importlib
import json
import pathlib
import sys

import _cipath
from rediacc_ci import controls, gitx, paths
from rediacc_ci.controls import plant
from rediacc_ci.quality import plan_lifecycle as PL

CONTROL_FLOOR = 24


class CannotRunError(RuntimeError):
    """The instrument is missing, which is never a verdict about the tree."""


# --------------------------------------------------------------------------- The fixtures the controls plant into. Clean by construction, mutated per control.

CLEAN_ACTIVE = "# PLAN: sample\nStatus: in-progress\nOwner: abcd1234\n\n- [ ] one box\n"
CLEAN_BACKLOG = "# PLAN: sketch\nStatus: draft\nFirst-Seen: 2026-09-01\n\n- [ ] one box\n"
CLEAN_DONE = "# PLAN: closed\nStatus: done\nFirst-Seen: 2026-01-01\n\n- [x] one box\n"
CLEAN_STUB = PL.stub_text("agent/PLAN-closed.md", "agent/plans/_done/PLAN-closed.md", "closed")
CLEAN_LEDGER = json.dumps(
    {
        "plans": {
            "agent/plans/_done/PLAN-closed.md": {
                "folder": PL.DONE_DIR,
                "moved_at": "2026-09-15",
            }
        }
    },
    indent=2,
)
CLEAN_INDEX = (
    "# Compacted plan records\n\nNothing cites a path that is not here.\n\n"
    "agent/plans/PLAN-sample.md is the live one.\n"
)
CLEAN_LISTING = (
    "agent/plans/PLAN-sample.md\nagent/plans/PLAN-sketch.md\nagent/plans/_done/PLAN-closed.md\n"
)
BLOB_A = "a" * 40
BLOB_B = "b" * 40
CLEAN_TOMBSTONE_ROW = (
    "| `agent/plans/_done/PLAN-gone.md` | gone | 2026-01-01 | 2026-09-01 | `%s` |" % BLOB_A
)

TODAY = dt.date(2026, 9, 21)
CONFIG = {"terminal_days": 40, "backlog_days": 90}


def _plans(pairs: list[tuple[str, str]], ledger_text: str = CLEAN_LEDGER) -> list[PL.Plan]:
    """`Plan` objects from (path, text) pairs, clocks taken from a ledger STRING.

    The ledger arrives as text rather than as a dict so a control can plant into it with the same harness it plants into a plan with, which is what keeps every mutation in this file subject to `plant()`'s refusals.
    """
    rows = (json.loads(ledger_text) or {}).get("plans") or {}
    out = []
    for rel, text in pairs:
        row = rows.get(rel) or {}
        out.append(
            PL.parse_plan(
                rel,
                text,
                moved_at=str(row.get("moved_at") or ""),
                last_commit=str(row.get("last_commit") or ""),
                move_commit=str(row.get("move_commit") or ""),
            )
        )
    return out


def _codes(found: list[PL.Finding]) -> set[str]:
    return {f.code for f in found}


def selftest() -> int:
    """Every finding, planted and mirrored. The mirror is half the control.

    A control that only proves the red case cannot tell a detector apart from a function that returns a finding unconditionally, so each plant below is paired with the clean fixture it was built from.
    """
    tally = controls.Controls("plan folders", floor=CONTROL_FLOOR)

    # F1. The path is the defect, so the path is what gets planted.
    clean_rel = "agent/plans/PLAN-sample.md"
    tally.check("F1 clean", _codes(PL.finding_f1(_plans([(clean_rel, CLEAN_ACTIVE)]))), set())
    legacy_rel = plant(clean_rel, "agent/plans/", "agent/")
    tally.check(
        "F1 planted",
        _codes(PL.finding_f1(_plans([(legacy_rel, CLEAN_ACTIVE)]))),
        {"F1"},
    )
    tally.check(
        "F1 spares a stub at the legacy path",
        _codes(PL.finding_f1(_plans([("agent/PLAN-closed.md", CLEAN_STUB)]))),
        set(),
    )

    # F2. A done plan in _done/ is right; the same folder under a live status is not.
    done_rel = "agent/plans/_done/PLAN-closed.md"
    tally.check("F2 clean", _codes(PL.finding_f2(_plans([(done_rel, CLEAN_DONE)]))), set())
    live_in_done = plant(CLEAN_DONE, "Status: done", "Status: in-progress")
    tally.check("F2 planted", _codes(PL.finding_f2(_plans([(done_rel, live_in_done)]))), {"F2"})
    finished_in_active = plant(CLEAN_ACTIVE, "Status: in-progress", "Status: shipped")
    tally.check(
        "F2 fires the other way too",
        _codes(PL.finding_f2(_plans([(clean_rel, finished_in_active)]))),
        {"F2"},
    )

    # F3. The clock lives in the ledger, so the ledger is what gets planted.
    tally.check(
        "F3 clean",
        _codes(PL.finding_f3(_plans([(done_rel, CLEAN_DONE)]), CONFIG, TODAY)),
        set(),
    )
    aged_ledger = plant(CLEAN_LEDGER, '"moved_at": "2026-09-15"', '"moved_at": "2026-05-01"')
    tally.check(
        "F3 planted",
        _codes(PL.finding_f3(_plans([(done_rel, CLEAN_DONE)], aged_ledger), CONFIG, TODAY)),
        {"F3"},
    )
    tally.check(
        "F3 spares a plan that never moved",
        _codes(PL.finding_f3(_plans([(clean_rel, CLEAN_ACTIVE)], aged_ledger), CONFIG, TODAY)),
        set(),
    )

    backlog_rel = "agent/plans/PLAN-sketch.md"
    tally.check(
        "F4 clean",
        _codes(PL.finding_f4(_plans([(backlog_rel, CLEAN_BACKLOG)]), CONFIG, TODAY)),
        set(),
    )
    stale_backlog = plant(CLEAN_BACKLOG, "First-Seen: 2026-09-01", "First-Seen: 2025-09-01")
    tally.check(
        "F4 planted",
        _codes(PL.finding_f4(_plans([(backlog_rel, stale_backlog)]), CONFIG, TODAY)),
        {"F4"},
    )
    tally.check(
        "F4 spares an active plan of the same age",
        _codes(
            PL.finding_f4(
                _plans(
                    [(clean_rel, plant(CLEAN_ACTIVE, "Owner:", "First-Seen: 2025-09-01\nOwner:"))]
                ),
                CONFIG,
                TODAY,
            )
        ),
        set(),
    )

    # Q. The keep-or-archive split (ruling ASKED:2026-10-28T10:58Z): a stale backlog plan is a question, never a deletion; a stale terminal plan is still swept.
    stale_plans = _plans([(backlog_rel, stale_backlog)])
    tally.check(
        "Q1 a stale backlog plan is in the question",
        [p.rel for p, _age in PL.stale_backlog(stale_plans, CONFIG, TODAY)],
        [backlog_rel],
    )
    tally.check(
        "Q2 a stale backlog plan is never due for the sweep",
        [p.rel for p in _expired(stale_plans, CONFIG, TODAY)],
        [],
    )
    tally.check(
        "Q3 a stale terminal plan is still due for the sweep",
        [p.rel for p in _expired(_plans([(done_rel, CLEAN_DONE)], aged_ledger), CONFIG, TODAY)],
        [done_rel],
    )
    kept_text = PL.with_kept(stale_backlog, "2026-09-20", "2026-09-20T10:00Z")
    tally.check(
        "Q4 a Kept: answer restarts the clock",
        PL.stale_backlog(_plans([(backlog_rel, kept_text)]), CONFIG, TODAY),
        [],
    )
    old_kept = PL.with_kept(stale_backlog, "2025-01-01", "2025-01-01T10:00Z")
    tally.check(
        "Q5 a Kept: older than the clock changes nothing",
        len(PL.stale_backlog(_plans([(backlog_rel, old_kept)]), CONFIG, TODAY)),
        1,
    )
    tally.check(
        "Q6 a second Kept: replaces the first",
        PL.with_kept(kept_text, "2026-09-21", "2026-09-21T09:00Z").count("Kept:"),
        1,
    )
    tally.check(
        "Q7 an archived plan classifies as removed",
        PL.classify(PL.parse_plan(backlog_rel, PL.with_archived(stale_backlog, "why"))),
        PL.STATE_REMOVED,
    )
    tally.check(
        "Q8 a well-formed ASKED minute parses", bool(PL.asked_minute("2026-10-28T10:58Z")), True
    )
    tally.check("Q9 a malformed ASKED minute is refused", PL.asked_minute("2026-10-28 10:58"), None)
    tally.check(
        "Q10 an impossible ASKED minute is refused", PL.asked_minute("2026-13-40T25:99Z"), None
    )

    # F5. Two stubs, and the mutant points the first at the second.
    stub_rel = "agent/PLAN-closed.md"
    other_stub_rel = "agent/PLAN-other.md"
    other_stub = PL.stub_text(other_stub_rel, "agent/plans/_done/PLAN-other.md", "other")
    exists = {"agent/plans/_done/PLAN-closed.md", "agent/plans/_done/PLAN-other.md", other_stub_rel}
    tally.check(
        "F5 clean",
        _codes(
            PL.finding_f5(_plans([(stub_rel, CLEAN_STUB), (other_stub_rel, other_stub)]), exists)
        ),
        set(),
    )
    chained = plant(CLEAN_STUB, "agent/plans/_done/PLAN-closed.md", other_stub_rel)
    tally.check(
        "F5 planted",
        _codes(PL.finding_f5(_plans([(stub_rel, chained), (other_stub_rel, other_stub)]), exists)),
        {"F5"},
    )
    dangling = plant(
        CLEAN_STUB, "agent/plans/_done/PLAN-closed.md", "agent/plans/_done/PLAN-nope.md"
    )
    tally.check(
        "F5 fires on a target that is not a file",
        _codes(PL.finding_f5(_plans([(stub_rel, dangling)]), exists)),
        {"F5"},
    )

    # F6. moved_at against the commit date of the new path.
    agreeing = plant(
        CLEAN_LEDGER,
        '"moved_at": "2026-09-15"',
        '"moved_at": "2026-09-15",\n      "move_commit": "2026-09-15"',
    )
    tally.check(
        "F6 clean",
        _codes(PL.finding_f6(_plans([(done_rel, CLEAN_DONE)], agreeing))),
        set(),
    )
    backdated = plant(agreeing, '"moved_at": "2026-09-15"', '"moved_at": "2026-06-15"')
    tally.check(
        "F6 planted", _codes(PL.finding_f6(_plans([(done_rel, CLEAN_DONE)], backdated))), {"F6"}
    )
    one_day = plant(agreeing, '"moved_at": "2026-09-15"', '"moved_at": "2026-09-16"')
    tally.check(
        "F6 tolerates a one-day straddle",
        _codes(PL.finding_f6(_plans([(done_rel, CLEAN_DONE)], one_day))),
        set(),
    )

    # F7. A citation in a GENERATED file, against what exists.
    live = {"agent/plans/PLAN-sample.md"}
    clean_refs = [(PL.INDEX_REL, m.group(0)) for m in PL.PLAN_REF_RE.finditer(CLEAN_INDEX)]
    tally.check("F7 clean", _codes(PL.finding_f7(clean_refs, live, set())), set())
    broken_index = plant(CLEAN_INDEX, "PLAN-sample.md", "PLAN-vanished.md")
    broken_refs = [(PL.INDEX_REL, m.group(0)) for m in PL.PLAN_REF_RE.finditer(broken_index)]
    tally.check("F7 planted", _codes(PL.finding_f7(broken_refs, live, set())), {"F7"})
    tally.check(
        "F7 accepts a tombstone as a resolution",
        _codes(PL.finding_f7(broken_refs, live, {"agent/plans/PLAN-vanished.md"})),
        set(),
    )
    tally.truthy("F7 saw a citation at all", clean_refs)

    # F8. The blob a tombstone names.
    clean_stones = PL.parse_tombstones(PL.render_tombstones([]) + CLEAN_TOMBSTONE_ROW + "\n")
    tally.check("F8 parsed one row", len(clean_stones), 1)
    tally.check("F8 clean", _codes(PL.finding_f8(clean_stones, {BLOB_A})), set())
    dead_row = plant(CLEAN_TOMBSTONE_ROW, BLOB_A, BLOB_B)
    dead_stones = PL.parse_tombstones(dead_row + "\n")
    tally.check("F8 planted", _codes(PL.finding_f8(dead_stones, {BLOB_A})), {"F8"})

    # F9. The floor, planted by deleting a path from the enumeration.
    clean_rels = [ln for ln in CLEAN_LISTING.splitlines() if ln]
    tally.check(
        "F9 clean",
        _codes(PL.finding_f9(_plans([(r, CLEAN_ACTIVE) for r in clean_rels]), floor=3)),
        set(),
    )
    thin = plant(CLEAN_LISTING, "agent/plans/PLAN-sketch.md\n", "")
    thin_rels = [ln for ln in thin.splitlines() if ln]
    tally.check(
        "F9 planted",
        _codes(PL.finding_f9(_plans([(r, CLEAN_ACTIVE) for r in thin_rels]), floor=3)),
        {"F9"},
    )
    tally.check(
        "F9 does not count stubs toward the floor",
        _codes(PL.finding_f9(_plans([(stub_rel, CLEAN_STUB)] * 3), floor=3)),
        {"F9"},
    )

    # The round trips the verbs depend on, and the mirror against the hook.
    tally.check("a stub parses as a stub", PL.is_stub(_plans([(stub_rel, CLEAN_STUB)])[0]), True)
    tally.check("a stub is cheap to spot", PL.looks_like_stub(CLEAN_STUB), True)
    tally.check("a plan is not a stub", PL.looks_like_stub(CLEAN_ACTIVE), False)
    tally.check("folder_of reads the deepest folder", PL.folder_of(done_rel), PL.DONE_DIR)
    tally.check("folder_of ignores a session note", PL.folder_of("agent/abcd1234/STATE.md"), "")
    tally.check(
        "the tombstone render round-trips",
        [t.rel for t in PL.parse_tombstones(PL.render_tombstones(dead_stones))],
        [t.rel for t in dead_stones],
    )
    tally.check("an empty tombstone table renders as nothing", PL.render_tombstones([]), "")

    # M. The citation remap `--move` applies. The git half (fork point, subject index, patch-ids) is driven against real rebased histories in .ci/rediacc_ci/tests/gates/test_gate_plan_folders.py; these pin the decision and the rewrite, both directions each.
    tally.check(
        "M1 one proven copy remaps",
        PL.remap_verdict("p1", [("m1", "p1"), ("m2", "p2")]),
        (PL.REMAP_OK, "m1"),
    )
    tally.check(
        "M2 no same-subject commit refuses", PL.remap_verdict("p1", []), (PL.REMAP_NONE, "")
    )
    tally.check(
        "M3 a subject match with another patch refuses",
        PL.remap_verdict("p1", [("m1", "p2")]),
        (PL.REMAP_DIFFERS, ""),
    )
    tally.check(
        "M4 two proven copies refuse",
        PL.remap_verdict("p1", [("m1", "p1"), ("m2", "p1")]),
        (PL.REMAP_AMBIGUOUS, ""),
    )
    tally.check(
        "M5 an empty patch proves nothing", PL.remap_verdict("", [("m1", "")]), (PL.REMAP_EMPTY, "")
    )
    fenced = "commit:abc123def x\n```\nabc123def quoted\n```\n20261007 1234567890ab\n"
    tally.check(
        "M6 tokens skip fences and all-digit runs",
        PL.unfenced_tokens(fenced),
        ["abc123def", "1234567890ab"],
    )
    tally.check(
        "M7 the rewrite touches unfenced lines only",
        PL.apply_remap(fenced, {"abc123def": "fedcba987"}),
        "commit:fedcba987 x\n```\nabc123def quoted\n```\n20261007 1234567890ab\n",
    )
    tally.check("M8 an empty mapping is the identity", PL.apply_remap(fenced, {}), fenced)
    digits = "3253893064" + "ab" + "0" * 28
    tally.check(
        "M9 an all-digit rewrite is lengthened until it carries a letter, and the reader sees it",
        PL.unfenced_tokens("commit:" + PL.citable_token(digits, digits[:9])),
        [digits[:11]],
    )
    tally.check(
        "M10 a rewrite that already carries a letter is kept as abbreviated",
        PL.citable_token("abc" + "0" * 37, "abc000000"),
        "abc000000",
    )

    return 0 if tally.report() else 1


# --------------------------------------------------------------------------- The tree-reading half.


def _gather(root: pathlib.Path):
    rels, why = PL.enumerate_plans(root)
    if why:
        raise CannotRunError(why)
    ledger = PL.ledger_rows(root)
    plans = PL.load_plans(root, rels, ledger)
    try:
        index_text = (root / PL.INDEX_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        index_text = ""
    stones = PL.parse_tombstones(index_text)
    return plans, set(rels), stones


def run(root: pathlib.Path, config: dict) -> int:
    plans, existing, stones = _gather(root)
    found = PL.findings(
        plans,
        config=config,
        today=dt.datetime.now(dt.UTC).date(),
        existing=existing,
        refs=PL.citation_refs(root),
        tombstones=stones,
        blob_resolves=PL.blob_resolves(root, {t.blob for t in stones}),
    )
    for finding in found:
        print("✗ %s %s" % (finding.code, finding.message), file=sys.stderr)
    if found:
        return 1
    print(
        "✓ plan folders: %d plan(s) and %d stub(s) across %s, %d tombstone(s)"
        % (
            len([p for p in plans if not PL.is_stub(p)]),
            len([p for p in plans if PL.is_stub(p)]),
            ", ".join(PL.PLAN_DIRS),
            len(stones),
        )
    )
    print(
        "  Blind spot: headers, paths and dates only. A plan whose TEXT went stale reads "
        "exactly like one that did not."
    )
    return 0


def status(root: pathlib.Path, config: dict) -> int:
    plans, _existing, stones = _gather(root)
    today = dt.datetime.now(dt.UTC).date()
    buckets: dict[str, list[PL.Plan]] = {}
    for plan in plans:
        buckets.setdefault(PL.classify(plan), []).append(plan)
    for state in sorted(buckets):
        keep = PL.retention_days(state, config)
        print(
            "%-8s %3d  folder %-22s retention %s"
            % (
                state,
                len(buckets[state]),
                PL.folder_for(state) + "/",
                "none" if keep is None else "%d day(s)" % keep,
            )
        )
    print("tombstone %3d  %s" % (len(stones), PL.INDEX_REL))
    due = _expired(plans, config, today)
    print("due for sweep: %d" % len(due))
    print("awaiting keep-or-archive: %d" % len(PL.stale_backlog(plans, config, today)))
    return 0


def _expired(plans: list[PL.Plan], config: dict, today: dt.date) -> list[PL.Plan]:
    """Every plan a `--sweep --write` would delete. The ONE predicate, shared.

    `--sweep`'s report and `--sweep --write`'s action read this same list, so a dry run cannot describe something the real run would not do.

    TERMINAL ONLY. A backlog plan past its clock is an operator question (`PL.stale_backlog`, ruling ASKED:2026-10-28T10:58Z), so the state test below admits nothing outside TERMINAL_STATES however old it is.
    """
    out = []
    for plan in plans:
        if PL.is_stub(plan):
            continue
        state = PL.classify(plan)
        if state not in PL.TERMINAL_STATES:
            continue
        keep = PL.retention_days(state, config)
        if keep is None:
            continue
        age = PL.age_days(PL.as_date(plan.moved_at), today)
        if age is not None and age > keep:
            out.append(plan)
    return out


_SELF = ".ci/scripts/quality/check_plan_folders.py"
RULING = "ASKED:2026-10-28T10:58Z"


def _print_question(plans: list[PL.Plan], config: dict, today: dt.date) -> int:
    """The backlog plans past backlog_days, as the operator's keep-or-archive question. Returns how many."""
    stale = PL.stale_backlog(plans, config, today)
    limit = int(config["backlog_days"])
    if not stale:
        print("✓ keep-or-archive: no backlog plan is past the %d-day backlog_days" % limit)
        return 0
    print(
        "\nOPERATOR QUESTION: keep or archive %d backlog plan(s) past the %d-day backlog_days.\n"
        "  The sweep never deletes or moves a backlog plan (ruling %s); each one waits for "
        "the operator's answer." % (len(stale), limit, RULING)
    )
    for plan, age in stale:
        when = PL.last_touch(plan)
        print("  %s" % plan.rel)
        print("    title:  %s" % (plan.title or "(no heading)"))
        print("    Status: %s" % plan.status)
        print(
            "    age:    %d day(s), clock from %s" % (age, when.isoformat() if when else "unknown")
        )
        print("    keep:    python3 %s --keep %s --asked <YYYY-MM-DDTHH:MMZ>" % (_SELF, plan.rel))
        print(
            "    archive: python3 %s --archive %s --asked <YYYY-MM-DDTHH:MMZ>" % (_SELF, plan.rel)
        )
    print(
        "  <YYYY-MM-DDTHH:MMZ> is the UTC minute the operator answered. Keep writes `Kept:` and "
        "restarts the clock; archive sets `Status: removed` and moves the plan into _removed/."
    )
    return len(stale)


def sweep(root: pathlib.Path, config: dict, *, write: bool) -> int:
    plans, _existing, stones = _gather(root)
    today = dt.datetime.now(dt.UTC).date()
    due = _expired(plans, config, today)
    if not due:
        print(
            "✓ sweep: no terminal plan has aged past the %d-day terminal_days"
            % int(config["terminal_days"])
        )
        _print_question(plans, config, today)
        return 0
    for plan in due:
        print("  %s (%s)" % (plan.rel, PL.classify(plan)))
    if not write:
        print(
            "Refusing to delete %d file(s) without --write. A sweeper whose default is "
            "destructive is a program whose dry run is the dangerous one." % len(due),
            file=sys.stderr,
        )
        _print_question(plans, config, today)
        return 0
    rows = list(stones)
    for plan in due:
        blob = gitx.git(["hash-object", "--", plan.rel], root=root).stdout.strip()
        if len(blob) != 40:
            print(
                "✗ cannot hash %s; refusing to delete text nothing preserves" % plan.rel,
                file=sys.stderr,
            )
            return 1
        rows.append(
            PL.Tombstone(
                rel=plan.rel,
                title=plan.title or plan.rel.rsplit("/", 1)[-1],
                first_seen=plan.first_seen or (plan.last_commit or "")[:10],
                expired_at=today.isoformat(),
                blob=blob,
            )
        )
        result = gitx.git(["rm", "-q", "--", plan.rel], root=root)
        if not result.ok:
            print("✗ git rm %s failed: %s" % (plan.rel, result.stderr.strip()), file=sys.stderr)
            return 1
    _write_tombstones(root, rows)
    print(
        "✓ swept %d terminal plan(s); %d tombstone row(s) in %s"
        % (len(due), len(rows), PL.INDEX_REL)
    )
    print(
        "  Regenerate the ledgers: npm run check:ci-plan-boxes -- --update && npm run check:ci-plan-record -- --update"
    )
    _print_question(plans, config, today)
    return 0


def _answer_target(root: pathlib.Path, rel: str, asked: str, verb: str):
    """The (text, plan, minute) an answer verb acts on, or None after printing why it refused.

    Both verbs share every refusal: a malformed or future ASKED minute, a path that is not a plan, a stub, and a plan that is not backlog. The question is about backlog plans only, so an answer to anything else is a misdirected command rather than an answer.
    """
    minute = PL.asked_minute(asked)
    if minute is None:
        print(
            "✗ %s needs --asked <YYYY-MM-DDTHH:MMZ>, the UTC minute the operator answered the "
            "keep-or-archive question; got %r. An answer that names no minute is not an answer."
            % (verb, asked),
            file=sys.stderr,
        )
        return None
    if minute > dt.datetime.now(dt.UTC):
        print(
            "✗ --asked %s is in the future, so it cannot name an answer already given" % asked,
            file=sys.stderr,
        )
        return None
    if not PL.is_plan_path(rel) or not (root / rel).is_file():
        print("✗ %s is not a plan file" % rel, file=sys.stderr)
        return None
    text = (root / rel).read_text(encoding="utf-8", errors="replace")
    plan = PL.parse_plan(rel, text)
    state = PL.classify(plan)
    if state != PL.STATE_BACKLOG:
        print(
            "✗ %s is %s (`Status: %s`), not backlog; the keep-or-archive question covers "
            "backlog plans only" % (rel, state, plan.status),
            file=sys.stderr,
        )
        return None
    return text, plan, minute


def keep(root: pathlib.Path, rel: str, asked: str) -> int:
    """`--keep`: the operator kept a backlog plan, so its clock restarts today."""
    target = _answer_target(root, rel, asked, "--keep")
    if target is None:
        return 2
    text, _plan, _minute = target
    today = dt.datetime.now(dt.UTC).date().isoformat()
    body = PL.with_kept(text, today, asked)
    if PL.parse_plan(rel, body).kept != today:
        print(
            "✗ the Kept: line written into %s does not parse back within the first %d lines, so "
            "the clock would not restart; nothing was written" % (rel, PL.HEADER_LINES),
            file=sys.stderr,
        )
        return 1
    (root / rel).write_text(body, encoding="utf-8")
    print(
        "✓ kept %s: Kept: %s ASKED:%s, the backlog clock restarts from %s"
        % (rel, today, asked, today)
    )
    return 0


def archive(root: pathlib.Path, rel: str, asked: str, config: dict) -> int:
    """`--archive`: the operator archived a backlog plan, so it becomes `removed` and moves."""
    target = _answer_target(root, rel, asked, "--archive")
    if target is None:
        return 2
    text, plan, _minute = target
    why = "archived on the operator's keep-or-archive answer ASKED:%s (Status was %s)" % (
        asked,
        plan.status,
    )
    (root / rel).write_text(PL.with_archived(text, why), encoding="utf-8")
    rc = move(root, rel, config)
    if rc != 0 and (root / rel).is_file() and not PL.looks_like_stub(PL.read_probe(root / rel)):
        # The move refused before touching the tree, so the plan goes back to the text it had.
        (root / rel).write_text(text, encoding="utf-8")
        print("✗ %s was not archived; its text is unchanged" % rel, file=sys.stderr)
        return rc
    if rc == 0:
        print(
            "✓ archived %s: Status: removed, now on the %d-day terminal clock"
            % (rel, int(config["terminal_days"]))
        )
    return rc


def _flag_value(argv: list[str], flag: str) -> str:
    if flag not in argv:
        return ""
    i = argv.index(flag)
    return argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("--") else ""


def _write_tombstones(root: pathlib.Path, rows: list[PL.Tombstone]) -> None:
    """Replace the tombstone section of `agent/INDEX.md`, keeping everything else.

    The section is rewritten in place rather than appended so the file stays a pure render of its inputs, which is the byte-equality `check:ci-plan-record`'s R8 compares against.
    """
    path = root / PL.INDEX_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    head = text.split(PL.TOMBSTONE_SECTION, 1)[0].rstrip("\n")
    path.write_text((head + "\n" + PL.render_tombstones(rows)).lstrip("\n"), encoding="utf-8")


def _dependents(root: pathlib.Path, rel: str) -> list[str]:
    """Required plans whose `Depends-On:` names `rel`, from the one grammar in the Stop hook (`wl_plandeps`). Imported by name at call time: only a move into `_removed/` asks, and a tree without the hook directory must still move other plans."""
    paths.on_sys_path(paths.hooks_stop_dir())
    graph = importlib.import_module("wl_plandeps").Graph.load(root)
    return list(graph.dependents(rel))


def _planqueue():
    """`wl_planqueue`, the one reader and writer of agent/plans/QUEUE.md's format, imported by name at call time like `_dependents`."""
    paths.on_sys_path(paths.hooks_stop_dir())
    return importlib.import_module("wl_planqueue")


def _report_retired(pq, root: pathlib.Path, retired: list[tuple[str, str]]) -> None:
    """One line per retired entry, then any kept entry whose note cites an entry number, since renumbering cannot rewrite prose."""
    for rel, target in retired:
        print("  retired Promoted entry %s (moved to %s) from %s" % (rel, target, pq.QUEUE_REL))
    if retired:
        text = (root / pq.QUEUE_REL).read_text(encoding="utf-8")
        for rel in pq.number_notes(text):
            print(
                "  ⚠ the entries were renumbered and %s's note cites an entry by number; "
                "check it still names the right one" % rel
            )


def retire_promoted(root: pathlib.Path) -> int:
    """`--retire-promoted`: every Promoted entry naming a moved stub leaves the queue."""
    pq = _planqueue()
    if not (root / pq.QUEUE_REL).is_file():
        print(
            "✗ %s is absent, so there is no Promoted list to retire from" % pq.QUEUE_REL,
            file=sys.stderr,
        )
        return 1
    before = len(pq.promoted_numbered((root / pq.QUEUE_REL).read_text(encoding="utf-8")))
    try:
        retired = pq.retire_promoted(root)
    except pq.QueueContendedError as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return 1
    _report_retired(pq, root, retired)
    print(
        "✓ retired %d Promoted entr%s naming a moved stub, %d of %d kept"
        % (len(retired), "y" if len(retired) == 1 else "ies", before - len(retired), before)
    )
    return 0


def move(root: pathlib.Path, rel: str, config: dict) -> int:
    """`git mv` one plan into its folder, leave a stub, stamp both clocks."""
    source = root / rel
    if not source.is_file():
        print("✗ %s is not a file" % rel, file=sys.stderr)
        return 1
    text = source.read_text(encoding="utf-8", errors="replace")
    plan = PL.parse_plan(rel, text)
    if PL.is_stub(plan):
        print("✗ %s is already a stub; a plan moves exactly once" % rel, file=sys.stderr)
        return 1
    target_dir = PL.folder_for(PL.classify(plan))
    new_rel = "%s/%s" % (target_dir, rel.rsplit("/", 1)[-1])
    if new_rel == rel:
        print("✓ %s is already in %s/" % (rel, target_dir))
        return 0
    if target_dir == PL.REMOVED_DIR:
        waiting = _dependents(root, rel)
        if waiting:
            print(
                "✗ %s cannot move into %s/ while %d required plan(s) still depend on it:\n%s\n"
                '  Point each at something else first (`check_plan_deps.py --set <plan> "<value>" '
                "--write`), or finish %s instead of withdrawing it."
                % (
                    rel,
                    target_dir,
                    len(waiting),
                    "\n".join("    %s" % w for w in waiting),
                    rel.rsplit("/", 1)[-1],
                ),
                file=sys.stderr,
            )
            return 1
    if target_dir in PL.TERMINAL_DIRS and rel not in PL.ledger_rows(root):
        print(
            "✗ %s has no row in %s, so the move would record no moved_at and the %d-day "
            "retention clock would never start. Run `npm run check:ci-plan-boxes -- "
            "--update` first; a terminal move that starts no clock is a file that lives "
            "in _done/ for ever." % (rel, PL.LEDGER_REL, int(config["terminal_days"])),
            file=sys.stderr,
        )
        return 1
    remap = PL.plan_remap(root, text)
    if remap.refused:
        print(
            "✗ %s cites %d commit(s) that are not on %s and cannot be remapped unambiguously, "
            "so the move would carry citations a fresh clone cannot resolve:"
            % (rel, len(remap.refused), remap.main or "main"),
            file=sys.stderr,
        )
        for token, why in remap.refused:
            print("  %s -- %s" % (token, why), file=sys.stderr)
        print(
            "  Nothing was moved. Point each one at the main commit it became (subject and "
            "`git patch-id --stable` equal) or at a blob id (`git hash-object <file>`), then "
            "re-run --move.",
            file=sys.stderr,
        )
        return 1
    when = gitx.git(["log", "-1", "--format=%cI", "--", rel], root=root).stdout.strip()
    first_seen = (plan.first_seen or when)[:10]
    if not first_seen:
        print(
            "✗ %s has no commit and no First-Seen:, so the 90-day clock would start today. "
            "Commit it first; a move must not buy freshness." % rel,
            file=sys.stderr,
        )
        return 1
    (root / target_dir).mkdir(parents=True, exist_ok=True)
    # A PLAN WRITTEN AND FINISHED INSIDE ONE SESSION IS UNTRACKED, and `git mv` refuses an untracked source with "not under version control" -- found 2026-09-24 moving a plan that was drafted, implemented and closed before its first commit. A plain rename is the whole of what `git mv` would have done for it; the stub and the `git add` below then run exactly as for a tracked plan.
    tracked = gitx.git(["ls-files", "--error-unmatch", "--", rel], root=root).ok
    if tracked:
        result = gitx.git(["mv", "--", rel, new_rel], root=root)
    else:
        (root / rel).rename(root / new_rel)
        result = gitx.git(["status", "--porcelain", "--", new_rel], root=root)
    if not result.ok:
        print(
            "✗ git mv %s -> %s failed: %s" % (rel, new_rel, result.stderr.strip()), file=sys.stderr
        )
        return 1
    body = PL.apply_remap(text, remap.mapping)
    if not plan.first_seen:
        body = _stamp(body, first_seen)
    if body != text:
        (root / new_rel).write_text(body, encoding="utf-8")
    (root / rel).write_text(PL.stub_text(rel, new_rel, plan.title), encoding="utf-8")
    gitx.git(["add", "--", rel, new_rel], root=root)
    _record_move(root, rel, new_rel, target_dir)
    print("✓ %s -> %s (First-Seen: %s)" % (rel, new_rel, first_seen))
    _report_remap(remap)
    if target_dir in PL.TERMINAL_DIRS:
        # Worklist #7b9fe4f1: a plan that left for _done/ or _removed/ has nothing left to order, and before this line its Promoted entry stayed behind for good.
        pq = _planqueue()
        try:
            retired = pq.retire_promoted(root, {rel})
        except pq.QueueContendedError as exc:
            # The move itself is done and staged (review 5fceaed6.2): only the entry stayed, which RQ-MOVED names until the repair verb runs.
            print(
                "⚠ %s; the move stands, run --retire-promoted once the queue is quiet" % exc,
                file=sys.stderr,
            )
            return 0
        _report_retired(pq, root, retired)
        if retired:
            # Review 5d1b9889.1: the queue rewrite rides the move's own staging, so a commit of the move never leaves HEAD's Promoted pointing at a stub.
            gitx.git(["add", "--", pq.QUEUE_REL], root=root)
    return 0


def _report_remap(remap: PL.Remap) -> None:
    """The shape of the citation remap, so a reader can see it ran and on what."""
    print(
        "  commit citations: %d cited, %d on %s, %d remapped, %d still on this branch"
        % (
            remap.commits,
            len(remap.on_main),
            remap.main or "main",
            len(remap.mapping),
            len(remap.on_branch),
        )
    )
    for old, new in remap.mapping.items():
        print("    remapped %s -> %s (%s)" % (old, new, remap.subjects.get(old, "")))
    for token in remap.on_branch:
        print(
            "    kept %s: reachable from HEAD and not from %s, so this PR's rebase-merge will "
            "rewrite it; close a plan after its merge so --move can remap it" % (token, remap.main)
        )


def _stamp(text: str, first_seen: str) -> str:
    """Insert `First-Seen:` directly under the `Status:` line.

    Under rather than above, because `Status:` is what every other reader in the family anchors on and inserting above it would push it past `wl_checks.PLAN_HEADER_LINES` in a plan whose header is already ten lines deep.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if PL.STATUS_RE.match(line):
            lines.insert(i + 1, "First-Seen: %s\n" % first_seen)
            return "".join(lines)
    return "First-Seen: %s\n%s" % (first_seen, text)


def _record_move(root: pathlib.Path, old_rel: str, new_rel: str, folder: str) -> None:
    """Re-key the plan-boxes row and stamp `folder` and `moved_at`.

    The row is CARRIED rather than recomputed. Its signatures describe boxes that did not change, and recomputing them here would be a second implementation of `check_plan_boxes.scan` living in the mover.
    """
    path = root / PL.LEDGER_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    plans = doc.get("plans") or {}
    row = plans.pop(old_rel, None)
    if row is None:
        return
    row["folder"] = folder
    row["moved_at"] = dt.datetime.now(dt.UTC).date().isoformat()
    plans[new_rel] = row
    doc["plans"] = {k: plans[k] for k in sorted(plans)}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def update(root: pathlib.Path) -> int:
    _plans_unused, _existing, stones = _gather(root)
    _write_tombstones(root, stones)
    print("✓ wrote the tombstone section of %s: %d row(s)" % (PL.INDEX_REL, len(stones)))
    return 0


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()

        print("plan folders: controls first, then the verdict")
        if selftest() != 0:
            print(
                "✗ instrument control failed; every verdict below would be meaningless",
                file=sys.stderr,
            )
            return 2

        root = PL.repo_root()
        if not gitx.is_work_tree(root):
            raise CannotRunError("%s is not a git work tree, so no plan can be enumerated" % root)
        try:
            config = PL.load_config(root)
            for key in ("terminal_days", "backlog_days"):
                int(config[key])
        except (OSError, ValueError, KeyError) as exc:
            print(
                "✗ %s must carry terminal_days and backlog_days (%s). One number, one "
                "place: a default here would be a second definition of the retention."
                % (PL.DEFAULT_CONFIG_REL, exc),
                file=sys.stderr,
            )
            return 2

        if "--status" in argv:
            return status(root, config)
        if "--move" in argv:
            target = argv[argv.index("--move") + 1] if len(argv) > argv.index("--move") + 1 else ""
            if not target:
                print("✗ --move needs a plan path", file=sys.stderr)
                return 2
            return move(root, target, config)
        for verb in ("--keep", "--archive"):
            if verb in argv:
                target = _flag_value(argv, verb)
                if not target:
                    print("✗ %s needs a plan path" % verb, file=sys.stderr)
                    return 2
                asked = _flag_value(argv, "--asked")
                if verb == "--keep":
                    return keep(root, target, asked)
                return archive(root, target, asked, config)
        if "--retire-promoted" in argv:
            return retire_promoted(root)
        if "--sweep" in argv:
            return sweep(root, config, write="--write" in argv)
        if "--update" in argv:
            return update(root)
        return run(root, config)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

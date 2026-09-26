#!/usr/bin/env python3
"""check:ci-plan-folders -- a plan lives in `agent/plans/`, moves once, and expires.

Logic is in `rediacc_ci.quality.plan_lifecycle`, which pytest and this file's `--selftest` import directly; contract section 5d puts the entry point where `scripts/gate-bind.ts` can see it. The reasoning for the shape, the two clocks and the stub is in that module's docstring and is not repeated here.

WHAT THIS GATE ADDS TO THE ONES ALREADY IN THE FAMILY. `check:ci-plan-housekeeping` asks how OLD a plan is, `check:ci-plan-boxes` asks whether its boxes survived, `check:ci-plan-record` asks whether a compaction record is honest. None of the three has ever asked WHERE a plan is or WHEN it leaves, which is why `agent/` accumulated 103 files at its root with no rule either way.

NINE FINDINGS, EACH WITH A PLANTED CONTROL:

    F1  a plan at the legacy path rather than under agent/plans/**
    F2  the folder disagrees with `Status:`
    F3  a terminal plan past terminal_days
    F4  a not-started plan past backlog_days
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
    --move P   git mv P into its folder, leave a stub, stamp First-Seen and moved_at
    --sweep    what the retention clocks would delete; REFUSES to act without --write
    --update   write the tombstone section of agent/INDEX.md

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
import json
import pathlib
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, gitx
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
    return 0


def _expired(plans: list[PL.Plan], config: dict, today: dt.date) -> list[PL.Plan]:
    """Every plan a `--sweep --write` would delete. The ONE predicate, shared.

    `--sweep`'s report and `--sweep --write`'s action read this same list, so a dry run cannot describe something the real run would not do.
    """
    out = []
    for plan in plans:
        if PL.is_stub(plan):
            continue
        state = PL.classify(plan)
        keep = PL.retention_days(state, config)
        if keep is None:
            continue
        when = PL.as_date(plan.moved_at) if state in PL.TERMINAL_STATES else PL.last_touch(plan)
        age = PL.age_days(when, today)
        if age is not None and age > keep:
            out.append(plan)
    return out


def sweep(root: pathlib.Path, config: dict, *, write: bool) -> int:
    plans, _existing, stones = _gather(root)
    today = dt.datetime.now(dt.UTC).date()
    due = _expired(plans, config, today)
    if not due:
        print("✓ sweep: nothing has aged past its retention")
        return 0
    for plan in due:
        print("  %s (%s)" % (plan.rel, PL.classify(plan)))
    if not write:
        print(
            "Refusing to delete %d file(s) without --write. A sweeper whose default is "
            "destructive is a program whose dry run is the dangerous one." % len(due),
            file=sys.stderr,
        )
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
    print("✓ swept %d plan(s); %d tombstone row(s) in %s" % (len(due), len(rows), PL.INDEX_REL))
    print(
        "  Regenerate the ledgers: npm run check:ci-plan-boxes -- --update && npm run check:ci-plan-record -- --update"
    )
    return 0


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
    if target_dir in PL.TERMINAL_DIRS and rel not in PL.ledger_rows(root):
        print(
            "✗ %s has no row in %s, so the move would record no moved_at and the %d-day "
            "retention clock would never start. Run `npm run check:ci-plan-boxes -- "
            "--update` first; a terminal move that starts no clock is a file that lives "
            "in _done/ for ever." % (rel, PL.LEDGER_REL, int(config["terminal_days"])),
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
    if not plan.first_seen:
        (root / new_rel).write_text(_stamp(text, first_seen), encoding="utf-8")
    (root / rel).write_text(PL.stub_text(rel, new_rel, plan.title), encoding="utf-8")
    gitx.git(["add", "--", rel, new_rel], root=root)
    _record_move(root, rel, new_rel, target_dir)
    print("✓ %s -> %s (First-Seen: %s)" % (rel, new_rel, first_seen))
    return 0


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

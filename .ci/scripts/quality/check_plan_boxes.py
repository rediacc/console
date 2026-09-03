#!/usr/bin/env python3
"""check:ci-plan-boxes -- the committed ledger of every open checkbox in agent/PLAN-*.md.

WHY A LEDGER AND NOT A GREP. Two reasons, both measured on this tree.

1. A NAIVE GREP REDS ON NON-TASKS. `grep -F -- '- [ ]'` finds 93 hits; the anchored
   line count finds 89; `wl_planfid.plan_tasks` -- the parser the Stop hook actually
   uses -- finds 88. The five differences are four bits of PROSE ABOUT the checkbox
   grammar and one fenced CODE SAMPLE at agent/PLAN-fix-in-session-rule.md:352, which
   depicts a line the hook prints. A CI gate built on grep fails the build on a code
   sample. So this gate IMPORTS the real parser rather than reimplementing it, which
   makes the fence rule a structural property instead of a test: there is no second
   parser that can drift, and the same rule that makes :352 a non-finding makes
   wrapping a real box in a fence a DETECTABLE cheat.

2. A GATE THAT REDS ON OPEN BOXES GETS SWITCHED OFF. An audit of all 88 open boxes on
   2026-09-02 found 14 done-but-unticked and 58 legitimately open -- most of them other
   sessions' work. Failing on the mere existence of an open box would have been red on
   eight files at once, on the branch introducing the gate. So this asserts the LEDGER
   AGREES WITH THE TREE, and leaves the stock visible in one reviewable file where
   `open: 22 -> 21` beside a `- [x]` is the whole story in two lines.

WHAT IS ASSERTED (agent/PLAN-plan-file-lifecycle.md's A0-A6):

  A0  every plan on disk has a ledger entry whose status, owner, open/done counts and
      task signatures match, and every ledger entry names a plan that exists.
  A1  no box open at the MERGE-BASE may be gone at HEAD. It must be ticked, still
      open, moved to another plan, archived, or in a plan A5 permitted deleting.
      This one assertion subsumes most of the ways a box can be made to disappear:
      deleting the line, un-checkboxing it, rewriting its text, wrapping it in a
      fence, or renaming the plan out of the glob all end the same way.
  A2  the archive is APPEND-ONLY and takes only byte-identical renames. `git diff
      -M100% BASE...HEAD` compares TREES, so editing a plan and archiving it in a
      separate commit is still R09x -- there is no commit-ordering dodge.
  A3  a FINISHED `Status:` may not sit over open boxes. This INVERTS the Stop hook's
      own frozenset: there the status means "stop nagging", here it means "that
      header switches the advisory off over live boxes". Same constant, imported,
      so the two halves cannot drift.
  A4  a plan this branch ADDS with open boxes must resolve an `Owner:`, because the
      advisory only chases plans a session owns.
  A5  a plan may only be DELETED wholesale once it is older than delete_days AND
      only when deleting it actually loses a box.
  A6  the scan is not vacuous: a floor on plan files, a floor on total open boxes, and
      a refusal to judge when the parser resolves NOTHING from a tree that plainly
      contains checkbox lines.

A1-A5 NEED A BASE, so they run in quality-branch (pull_request only). When there is
no base, or the base predates the ledger, they are SKIPPED and the summary says so --
a skip must never read as a clean result.

THE DEADLOCK THIS AVOIDS, and a control found half of it. The housekeeping gate
DEMANDS deletion past delete_days; A5 REFUSES deletion before it. Both read
.ci/config/plan-lifecycle.json, so the predicates are complements over one number
and no plan can be in both. A1 has the SAME edge -- a plan legitimately retired by
age takes its boxes with it -- so A1 stands down for those plans too. The plan
foresaw this for A5; the A1 half turned up only when a control asserted that MOVING
a box between plans must be silent.

TASK SIGNATURES are the first 8 hex of sha256 over `wl_planfid._norm(task)[:120]` --
EXACTLY the key the parser already dedups on. Not the raw text: re-wrapping a line must
be free, and rewriting what it says must not be. That choice is what lets the later
transition rule ask "did this box survive?" as set membership rather than as a
token-overlap guess.

REGENERATE with `--update`. The ledger is committed, so a stale one is a red with a
one-command fix, and the regeneration is what makes the base-vs-head comparison
meaningful later: A1 reads the BASE ledger via `git show`, which no working tree can
rewrite.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PLAN_BOXES_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))

try:
    import wl_checks as CK
    import wl_planfid as PFID
    import wl_planfile as PF
except ImportError as _exc:  # pragma: no cover -- exercised by test-gate-anti-vacuity.sh
    # NOT a traceback. Importing the Stop hook's parser is this gate's ONLY way of
    # reading a checkbox (see the docstring), so a tree without .claude/hooks/stop is a
    # tree this gate cannot judge -- and a crash there reads to a reader, and to the
    # anti-vacuity harness, as an unrelated bug rather than as blindness. A check that
    # cannot see must SAY it cannot see.
    print(
        f"VACUOUS INPUT: cannot import the Stop hook's plan parser from "
        f"{ROOT / '.claude' / 'hooks' / 'stop'} ({_exc}). This gate reads checkboxes "
        f"ONLY through wl_planfid.plan_tasks -- a grep gets the answer wrong on fenced "
        f"code samples -- so without it there is nothing to compare and no verdict to "
        f"give.",
        file=sys.stderr,
    )
    sys.exit(1)

LEDGER = ROOT / ".ci" / "config" / "plan-boxes.json"
PLAN_GLOB = "PLAN-*.md"

# Floors. Measured 2026-09-02: 10 plan files carry boxes out of 70 total, 83 open and 37
# ticked. The file floor is deliberately well under the total -- it guards against the
# glob losing the corpus, not against ordinary housekeeping -- and the box floor guards
# against a parser that silently resolves nothing.
MIN_PLAN_FILES = int(os.environ.get("PLAN_BOXES_MIN_PLANS", "20"))
MIN_OPEN_BOXES = int(os.environ.get("PLAN_BOXES_MIN_OPEN", "1"))

LIFECYCLE = ROOT / ".ci" / "config" / "plan-lifecycle.json"
# FINISHED comes from the Stop hook, imported rather than restated: A3 INVERTS it
# (there the status means "stop nagging"; here it means "this header switches the
# advisory off over live boxes"), and the two halves must never drift apart.
FINISHED = PF.FINISHED_STATES


def _lifecycle() -> dict:
    """warn_days / delete_days / archive_dir, shared with the housekeeping gate.

    Not inlined. A5 REFUSES a deletion that gate DEMANDS, so the two predicates
    must be complements over one number or a plan can be simultaneously
    must-delete and must-not-delete.
    """
    try:
        return json.loads(LIFECYCLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"delete_days": 33, "archive_dir": "agent/archive/plans"}


ARCHIVE_DIR = _lifecycle().get("archive_dir", "agent/archive/plans")


def sig(task: str) -> str:
    """The parser's OWN dedup key, hashed. See the module docstring."""
    return hashlib.sha256(PFID._norm(task)[:120].encode("utf-8")).hexdigest()[:8]


def scan(root: Path) -> dict:
    """{relpath: {status, owner, open, done, task_sigs}} for every plan under agent/."""
    out: dict[str, dict] = {}
    for rel, status, _lines in CK.plan_records(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        open_t, done_t = PF.plan_boxes(text)
        out[rel] = {
            "status": status,
            "owner": CK.plan_owner(root, rel) or "unowned",
            "open": len(open_t),
            "done": len(done_t),
            "open_sigs": sorted({sig(t) for t in open_t}),
            "done_sigs": sorted({sig(t) for t in done_t}),
        }
    return out


def raw_box_lines(root: Path) -> int:
    """Checkbox-shaped lines counted with NO parser at all.

    The anti-vacuity oracle, and the only thing that can tell "there are no boxes" apart
    from "the parser stopped seeing them". It is deliberately dumber than plan_boxes --
    it counts the fenced sample and the prose too -- so it is only ever compared as
    `plainly non-zero`, never for equality.
    """
    n = 0
    for rel, _s, _l in CK.plan_records(root):
        for ln in (root / rel).read_text(encoding="utf-8", errors="replace").splitlines():
            if PF.OPEN_BOX_LINE.match(ln) or PF.DONE_BOX_LINE.match(ln):
                n += 1
    return n


def vacuity_problems(scanned: dict, raw: int) -> list[str]:
    """A6. Every way this scan can see nothing and report success."""
    out = []
    if len(scanned) < MIN_PLAN_FILES:
        out.append(
            f"VACUOUS INPUT: scanned {len(scanned)} plan file(s) under agent/, floor is "
            f"{MIN_PLAN_FILES}. The glob lost the corpus; refusing a verdict rather than "
            f"reporting a clean ledger for files nobody read"
        )
    total_open = sum(p["open"] for p in scanned.values())
    total_done = sum(p["done"] for p in scanned.values())
    if raw > 0 and total_open + total_done == 0:
        out.append(
            f"VACUOUS INPUT: {raw} checkbox-shaped line(s) exist in agent/PLAN-*.md and "
            f"the parser resolved NONE of them. wl_planfid.plan_tasks has stopped seeing "
            f"tasks; a clean report here would be indistinguishable from a broken parser"
        )
    elif total_open < MIN_OPEN_BOXES and raw > 0:
        out.append(
            f"VACUOUS INPUT: {total_open} open box(es) against {raw} raw checkbox line(s), "
            f"floor is {MIN_OPEN_BOXES}"
        )
    return out


def diff_problems(scanned: dict, ledger: dict) -> list[str]:
    """A0. The ledger and the tree, in both directions."""
    out = []
    plans = ledger.get("plans") or {}
    out.extend(
        f"{rel} carries {scanned[rel]['open']} open and {scanned[rel]['done']} ticked "
        f"box(es) but has no ledger entry -- a plan nothing records is a plan whose "
        f"boxes can vanish unnoticed"
        for rel in sorted(set(scanned) - set(plans))
    )
    out.extend(
        f"{LEDGER.name} still has an entry for {rel}, which is not in agent/ any more"
        for rel in sorted(set(plans) - set(scanned))
    )
    for rel in sorted(set(scanned) & set(plans)):
        got, want = scanned[rel], plans[rel]
        out.extend(
            f"{rel}: {field} is {got[field]!r}, ledger says {want.get(field)!r}"
            for field in ("status", "owner", "open", "done")
            if got[field] != want.get(field)
        )
        for field in ("open_sigs", "done_sigs"):
            if sorted(got[field]) != sorted(want.get(field) or []):
                gone = sorted(set(want.get(field) or []) - set(got[field]))
                new = sorted(set(got[field]) - set(want.get(field) or []))
                out.append(
                    f"{rel}: {field} disagree -- {len(gone)} in the ledger and not the "
                    f"tree ({', '.join(gone[:4]) or 'none'}), {len(new)} in the tree and "
                    f"not the ledger ({', '.join(new[:4]) or 'none'})"
                )
    return out


def base_ref() -> str | None:
    """The commit this branch diverged from, or None when there is no base.

    CI hands us `GITHUB_BASE_REF` (a branch name on a `pull_request` event and
    nothing at all on `push`), so the merge-base is computed rather than assumed:
    diffing against the tip of main would attribute every commit main gained
    since the branch started to this branch.

    None is not a failure. A0 and A6 read only the working tree and still run;
    the transition rules simply have nothing to compare against, and say so.
    """
    cand = os.environ.get("PLAN_BOXES_BASE") or ""
    if not cand:
        br = os.environ.get("GITHUB_BASE_REF") or ""
        cand = f"origin/{br}" if br else "origin/main"
    for ref in (cand, cand.replace("origin/", ""), "origin/main", "main"):
        if not ref:
            continue
        r = _git("merge-base", "HEAD", ref)
        if r:
            return r.strip()
    return None


def _git(*args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def base_ledger(base: str) -> tuple[dict, str | None]:
    """The ledger AS OF the base commit. This is what makes A1 unforgeable.

    A0 forces the head ledger to match the head tree, so a session that deletes a
    box must regenerate it -- and then the head ledger agrees with the tree and
    says nothing. The BASE ledger is read out of git, which a working tree cannot
    rewrite, so the two together make "did this box survive?" answerable.
    """
    raw = _git("show", f"{base}:{LEDGER.relative_to(ROOT)}")
    if raw is None:
        # ABSENT IS EXPECTED EXACTLY ONCE: on the branch that introduces the
        # ledger, the base predates it. Failing here would make the gate
        # unshippable on its own branch, which is the shape the plan warned
        # against. It is a SKIP, not a pass -- main() says so in the summary,
        # so "A1-A5 did not run" can never read as "A1-A5 found nothing".
        return {}, None
    try:
        return json.loads(raw), None
    except ValueError as exc:
        # A ledger that EXISTS and does not parse is a different thing entirely:
        # something is wrong with a file this gate depends on, and skipping would
        # hide it.
        return {}, f"the ledger at {base[:9]} does not parse ({exc}); A1 is blind"


def renames_into_archive(base: str) -> tuple[set[str], list[str]]:
    """({new archive paths that are byte-identical renames}, {problems}).

    A2a. `git diff --find-renames -M100%` compares TREES, not commits, which is
    the whole reason the two-commit dodge cannot work: editing a plan and then
    archiving it in a separate commit still leaves the net content different from
    base, so the similarity is below 100 and it reports R09x rather than R100.
    """
    out = _git("diff", "--name-status", "--find-renames", "-M100%", f"{base}...HEAD")
    if out is None:
        return set(), [f"cannot diff {base[:9]}...HEAD; A2 is blind"]
    ok, problems = set(), []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R") and parts[2].startswith(ARCHIVE_DIR):
            if parts[0] == "R100":
                ok.add(parts[2])
            else:
                problems.append(
                    f"{parts[1]} -> {parts[2]} is {parts[0]}, not R100: the content changed "
                    f"between {base[:9]} and HEAD. Archiving is for history you did NOT "
                    f"touch, so archiving it now would retire boxes this branch is "
                    f"responsible for. Two commits do not help -- this compares TREES"
                )
        elif len(parts) == 2 and parts[0] in ("M", "D") and parts[1].startswith(ARCHIVE_DIR):
            problems.append(
                f"{parts[1]} was {'modified' if parts[0] == 'M' else 'deleted'} in the "
                f"archive. The archive is APPEND-ONLY: a plan retired there is frozen, "
                f"which is what keeps its boxes findable and its age clock ticking"
            )
        elif len(parts) == 2 and parts[0] == "A" and parts[1].startswith(ARCHIVE_DIR):
            problems.append(
                f"{parts[1]} was ADDED to the archive rather than renamed into it. Use "
                f"`git mv` on an untouched plan; a fresh file there is a plan whose "
                f"history -- and whose boxes -- were left behind"
            )
    return ok, problems


def _name_status(base: str) -> list[tuple[str, str]]:
    out = _git(
        "diff", "--name-status", "--find-renames", "-M100%", f"{base}...HEAD", "--", "agent/"
    )
    rows = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


def _touched_plans(base: str) -> set[str]:
    return {p for st, p in _name_status(base) if st != "D" and p.startswith("agent/PLAN-")}


def _added_plans(base: str) -> set[str]:
    return {p for st, p in _name_status(base) if st == "A" and p.startswith("agent/PLAN-")}


def _content_age_days(rel: str, base: str) -> int | None:
    """Days since the newest commit that CHANGED this file, as of the base.

    Content age, not "last commit touching the path": otherwise moving a plan
    would reset its clock and archiving would become a way to cheat the age gate.
    """
    when = _git("log", "-1", "--format=%cI", base, "--", rel)
    if not when or not when.strip():
        return None
    try:
        then = dt.datetime.fromisoformat(when.strip())
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    return (dt.datetime.now(dt.UTC) - then).days


def transition_problems(scanned: dict, base: str) -> tuple[list[str], int]:
    """A1-A5. Returns (problems, boxes_compared).

    A1 is the load-bearing one and it subsumes most of the cheats: deleting a box
    line, un-checkboxing it, rewriting its text, fencing it, or renaming the plan
    out of the glob all end the same way -- a signature that was open at base has
    no legal home at head.
    """
    problems: list[str] = []
    ledger, err = base_ledger(base)
    if err:
        return [err], -1
    if not ledger:
        return [], -1
    archived_ok, arch_problems = renames_into_archive(base)
    problems += arch_problems

    head_open: dict[str, str] = {}
    head_done: dict[str, str] = {}
    for rel, rec in scanned.items():
        for sig in rec["open_sigs"]:
            head_open.setdefault(sig, rel)
        for sig in rec["done_sigs"]:
            head_done.setdefault(sig, rel)

    base_plans = ledger.get("plans") or {}
    lifecycle = _lifecycle()

    # Plans this branch RETIRED BY AGE. Computed before A1 runs, because their
    # boxes are legitimately gone and A1 must stand down for them -- otherwise the
    # housekeeping gate DEMANDS a deletion that A1 then REFUSES, which is the
    # deadlock .ci/config/plan-lifecycle.json exists to prevent. The plan foresaw
    # that for A5; a control here found that A1 has the same edge.
    retired: set[str] = set()
    for rel in set(base_plans) - set(scanned):
        age = _content_age_days(rel, base)
        if age is not None and age > lifecycle["delete_days"]:
            retired.add(rel)

    compared = 0
    for rel, rec in sorted(base_plans.items()):
        if rel in retired:
            continue
        for sig in rec.get("open_sigs") or []:
            compared += 1
            if sig in head_open or sig in head_done:
                continue
            where = "deleted" if rel not in scanned else "gone from"
            problems.append(
                f"{rel}: a box open at {base[:9]} (sig {sig}) is GONE at HEAD -- not "
                f"ticked, not moved to another plan, not archived. A box is the only "
                f"durable record of a task once a context ends; deleting the line does "
                f"not finish the work, it hides it. If you did it, tick it. If it is "
                f"blocked, mark it `- [?]`. If the plan is history, `git mv` it "
                f"untouched into {ARCHIVE_DIR}/ ({where} that plan)"
            )

    # A5: a plan may only be DELETED wholesale once it is older than delete_days
    # -- and only when deleting it actually LOSES something. If every box it held
    # survives in another plan, the file is a husk and removing it costs nothing;
    # firing here would punish exactly the tidying this whole check wants.
    for rel in sorted(set(base_plans) - set(scanned)):
        if rel in retired:
            continue
        if any(a.endswith("/" + rel.split("/")[-1]) for a in archived_ok):
            continue
        lost = [
            g
            for g in (base_plans[rel].get("open_sigs") or [])
            if g not in head_open and g not in head_done
        ]
        if not lost:
            continue
        age = _content_age_days(rel, base)
        problems.append(
            f"{rel} was DELETED, losing {len(lost)} open box(es) that survive nowhere, and "
            f"is only {age if age is not None else 'an unknown number of'} day(s) old. "
            f"Deletion is for a plan the housekeeping gate has already demanded "
            f"(> {lifecycle['delete_days']} days); before that, archive it or close its boxes"
        )

    # A3/A4 are properties of HEAD alone, but only for plans this branch touched --
    # judging a plan the branch never opened would be a demand about somebody
    # else's file.
    touched = _touched_plans(base)
    for rel in sorted(touched & set(scanned)):
        rec = scanned[rel]
        if rec["status"] in FINISHED and rec["open"]:
            problems.append(
                f"{rel} says Status: {rec['status']} but has {rec['open']} open box(es). "
                f"The Stop hook exempts finished plans from its advisory, so that header "
                f"switches the check off for this file -- which is why CI treats it as a "
                f"red rather than as an exemption"
            )
    for rel in sorted(_added_plans(base) & set(scanned)):
        if scanned[rel]["open"] and scanned[rel]["owner"] == "unowned":
            problems.append(
                f"{rel} is NEW on this branch and carries {scanned[rel]['open']} open "
                f"box(es) with no resolvable `Owner:`. The Stop hook's advisory only "
                f"blocks on plans a session owns, so unowned debt is debt nothing chases"
            )
    return problems, compared


def selftest() -> int:
    """Control-first: every verdict below is meaningless if these do not fire.

    C-FENCE is the load-bearing one. It plants the exact defect that motivated the
    parser choice -- a fenced code sample and a line of prose about the grammar, beside
    one real box -- and then plants the NAIVE implementation and requires it to get the
    answer WRONG. A defect detector that cannot detect the historical defect is broken,
    and saying so is cheaper than a clean run that means nothing.
    """
    bad = 0
    fixture = (
        "Status: executing\n\n# F\n\n"
        "## Tasks\n\n"
        "- [ ] a real open task that is long enough to parse\n"
        "- [x] a real ticked task that is long enough to parse\n\n"
        "States are `- [ ]` open and `- [x]` done, described in prose.\n\n"
        "```\n"
        "  - [ ] #<id> (upd <age>) a SAMPLE of a printed line, not a task\n"
        "```\n"
    )
    open_t, done_t = PF.plan_boxes(fixture)
    ok = len(open_t) == 1 and len(done_t) == 1
    print(f"  {'PASS' if ok else 'FAIL'}  C-FENCE: a fenced sample and grammar prose are not tasks")
    if not ok:
        print(f"        open={open_t}\n        done={done_t}")
        bad += 1
    naive = fixture.count("- [ ]")
    ok = naive == 3 and len(open_t) == 1
    print(
        f"  {'PASS' if ok else 'FAIL'}  C-FENCE CONTROL: the naive grep gets it WRONG "
        f"({naive} vs 1), so the parser choice is load-bearing"
    )
    if not ok:
        bad += 1

    # The signature must survive re-wrapping and must NOT survive a rewrite.
    a = sig("close   the   shadow   compare\nbefore deleting")
    b = sig("Close the shadow compare before deleting.")
    c = sig("delete the org secrets before the shadow compare")
    ok = a == b and a != c
    print(
        f"  {'PASS' if ok else 'FAIL'}  a re-wrapped box keeps its signature, a rewritten one does not"
    )
    if not ok:
        bad += 1

    # ---- A1-A5, the transition rules ---------------------------------------
    # These are the assertions most able to go silently vacuous: they compare two
    # trees, and a comparison that resolves to nothing looks exactly like a
    # comparison that found nothing wrong. Each rule is planted, and each plant
    # has a pair proving the legitimate path is NOT reported -- a gate that reds
    # on ticking a box teaches sessions not to tick boxes.
    def tp(base_plans, head, **kw):
        """transition_problems with git and the lifecycle stubbed out."""
        saved = {
            k: globals()[k]
            for k in (
                "base_ledger",
                "renames_into_archive",
                "_touched_plans",
                "_added_plans",
                "_content_age_days",
            )
        }
        globals()["base_ledger"] = lambda _b: ({"plans": base_plans}, None)
        globals()["renames_into_archive"] = lambda _b: (set(kw.get("archived", [])), [])
        globals()["_touched_plans"] = lambda _b: set(kw.get("touched", head))
        globals()["_added_plans"] = lambda _b: set(kw.get("added", []))
        globals()["_content_age_days"] = lambda _r, _b: kw.get("age", 1)
        try:
            return transition_problems(head, "0123456789abcdef")[0]
        finally:
            globals().update(saved)

    open_row = {
        "status": "executing",
        "owner": "x",
        "open": 1,
        "done": 0,
        "open_sigs": ["aa"],
        "done_sigs": [],
    }
    ticked_row = dict(open_row, open=0, done=1, open_sigs=[], done_sigs=["aa"])
    gone_row = dict(open_row, open=0, done=0, open_sigs=[], done_sigs=[])

    a1_cases = [
        (
            "A1: a box open at base and GONE at head is reported",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": gone_row},
            "is GONE at HEAD",
        ),
        (
            "A1: renaming the plan out of the glob does not hide its boxes",
            {"agent/PLAN-a.md": open_row},
            {},
            "is GONE at HEAD",
        ),
    ]
    for label, b, h, needle in a1_cases:
        got = tp(b, h)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label}")
        if not hit:
            bad += 1
            print(f"        got {got}")

    a1_pairs = [
        (
            "A1 CONTROL: TICKING a box is silent -- the legitimate path",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": ticked_row},
        ),
        (
            "A1 CONTROL: MOVING a box to another plan is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-b.md": open_row},
        ),
        (
            "A1 CONTROL: leaving it open is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": open_row},
        ),
    ]
    for label, b, h in a1_pairs:
        got = tp(b, h)
        print(f"  {'PASS' if got == [] else 'FAIL'}  {label}")
        if got:
            bad += 1
            print(f"        got {got}")

    # A5: a whole-file deletion. Young = refused, aged = permitted, and the age
    # comes from the SHARED lifecycle number so it cannot drift from the gate
    # that demands the deletion.
    young = tp({"agent/PLAN-a.md": open_row}, {}, age=1)
    ok = any("was DELETED, losing" in g for g in young)
    print(f"  {'PASS' if ok else 'FAIL'}  A5: deleting a young plan with open boxes is refused")
    if not ok:
        bad += 1
    aged = tp({"agent/PLAN-a.md": open_row}, {}, age=999)
    ok = not any("was DELETED, losing" in g for g in aged)
    print(
        f"  {'PASS' if ok else 'FAIL'}  A5 CONTROL: deleting an AGED plan is permitted, or it deadlocks the age gate"
    )
    if not ok:
        bad += 1

    # A3: a finished status over open boxes. The pair matters -- a status the
    # advisory still admits must NOT be reported, or every live plan reds.
    fin = next(iter(FINISHED))
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, status=fin)})
    ok = any("switches the check off" in g for g in got)
    print(f"  {'PASS' if ok else 'FAIL'}  A3: Status: {fin} over open boxes is refused")
    if not ok:
        bad += 1
    got = tp({}, {"agent/PLAN-a.md": open_row})
    print(
        f"  {'PASS' if got == [] else 'FAIL'}  A3 CONTROL: an in-scope status over open boxes is silent"
    )
    if got:
        bad += 1
    # And the plan this branch never TOUCHED is not judged -- demanding a header
    # change in somebody else's file is how a gate gets routed around.
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, status=fin)}, touched=set())
    print(f"  {'PASS' if got == [] else 'FAIL'}  A3 CONTROL: an untouched plan is not judged")
    if got:
        bad += 1

    # A4: new debt must name an owner.
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, owner="unowned")}, added={"agent/PLAN-a.md"})
    ok = any("no resolvable" in g for g in got)
    print(f"  {'PASS' if ok else 'FAIL'}  A4: a NEW plan with open boxes and no Owner is refused")
    if not ok:
        bad += 1
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, owner="unowned")}, added=set())
    print(
        f"  {'PASS' if got == [] else 'FAIL'}  A4 CONTROL: an EXISTING unowned plan is not judged"
    )
    if got:
        bad += 1

    # A0 must fire in both directions, and stay silent on agreement.
    tree = {
        "p.md": {
            "status": "executing",
            "owner": "x",
            "open": 2,
            "done": 1,
            "open_sigs": ["aa", "bb"],
            "done_sigs": ["cc"],
        }
    }
    same = {"plans": {"p.md": dict(tree["p.md"])}}
    cases = [
        ("a plan with no ledger entry", tree, {"plans": {}}, "has no ledger entry"),
        ("a ledger entry with no plan", {}, same, "not in agent/ any more"),
        (
            "a count the ledger disagrees with",
            tree,
            {"plans": {"p.md": dict(tree["p.md"], open=1)}},
            "ledger says",
        ),
        (
            "a box the ledger still lists",
            tree,
            {"plans": {"p.md": dict(tree["p.md"], open_sigs=["aa", "bb", "zz"])}},
            "open_sigs disagree",
        ),
    ]
    for label, t, led, needle in cases:
        got = diff_problems(t, led)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label} is reported")
        if not hit:
            bad += 1
            print(f"        got {got}")
    ok = diff_problems(tree, same) == []
    print(f"  {'PASS' if ok else 'FAIL'}  CONTROL: a ledger that agrees is silent")
    if not ok:
        bad += 1

    # A6, whose whole job is to refuse rather than pass.
    ok = any("glob lost the corpus" in m for m in vacuity_problems({}, 0))
    print(f"  {'PASS' if ok else 'FAIL'}  an empty corpus refuses rather than passing")
    if not ok:
        bad += 1
    blind = {f"p{i}.md": {"open": 0, "done": 0} for i in range(MIN_PLAN_FILES)}
    ok = any("resolved NONE of them" in m for m in vacuity_problems(blind, 40))
    print(f"  {'PASS' if ok else 'FAIL'}  raw checkbox lines the parser resolves to zero refuse")
    if not ok:
        bad += 1
    return bad


def main(argv: list[str]) -> int:
    update = "--update" in argv
    print("plan checkbox ledger: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    scanned = scan(ROOT)
    raw = raw_box_lines(ROOT)
    problems = vacuity_problems(scanned, raw)
    if problems:
        print(f"✗ plan checkbox ledger ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1

    if update:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "$comment": (
                "GENERATED by .ci/scripts/quality/check_plan_boxes.py --update. Do not "
                "hand-edit: the point of this file is that it is a SECOND reading of the "
                "plan files, so a hand-edit is the one thing that can make it agree with "
                "a tree it does not describe. Signatures are the parser's own dedup key "
                "hashed, so re-wrapping a box is free and rewriting it is not."
            ),
            "plans": {k: scanned[k] for k in sorted(scanned)},
        }
        LEDGER.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(
            f"✓ wrote {LEDGER.relative_to(ROOT)}: {len(scanned)} plan(s), "
            f"{sum(p['open'] for p in scanned.values())} open, "
            f"{sum(p['done'] for p in scanned.values())} ticked"
        )
        return 0

    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"✗ {LEDGER.relative_to(ROOT)} is missing, so nothing can be compared.\n"
            f"  Generate and commit it:\n"
            f"    npm run check:ci-plan-boxes -- --update\n"
            f"    git add {LEDGER.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(
            f"✗ cannot read {LEDGER.relative_to(ROOT)} ({exc}); refusing a verdict", file=sys.stderr
        )
        return 1

    problems = diff_problems(scanned, ledger)
    # A1-A5. Only once A0 agrees: comparing a base ledger against a head tree the
    # head ledger does not describe would report the ledger's own staleness as a
    # vanished box, which blames the wrong thing.
    compared = 0
    base = None if problems else base_ref()
    if base:
        tprob, compared = transition_problems(scanned, base)
        problems += tprob
    if problems:
        print(
            f"✗ plan checkbox ledger: {len(problems)} disagreement(s) with the tree",
            file=sys.stderr,
        )
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        print(
            "\n  A box is the only durable record of a task once a context ends, so the\n"
            "  ledger exists to make one disappearing visible in a diff.\n"
            "  If you ticked, added or moved a box on purpose, regenerate and commit:\n"
            "    npm run check:ci-plan-boxes -- --update\n"
            f"    git add {LEDGER.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ plan boxes: {len(scanned)} plan file(s) (floor {MIN_PLAN_FILES}) agree with "
        f"{LEDGER.relative_to(ROOT)} -- {sum(p['open'] for p in scanned.values())} open, "
        f"{sum(p['done'] for p in scanned.values())} ticked, "
        f"{raw} raw checkbox line(s) seen"
    )
    if base and compared < 0:
        print(
            f"  A1-A5 DID NOT RUN: {base[:9]} carries no {LEDGER.name}, so there is no "
            f"base to compare against. Expected exactly once -- on the branch that "
            f"introduces the ledger. This is a SKIP, not a clean result."
        )
    elif base:
        print(
            f"✓ transitions: {compared} box(es) open at {base[:9]} all survive at HEAD "
            f"(ticked, moved, or still open); the archive took only byte-identical "
            f"renames; no finished-status plan hides open boxes; no new plan carries "
            f"unowned debt"
        )
    else:
        print("  NO BASE REF: A1-A5 did not run. A0 and A6 above still did.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

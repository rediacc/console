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

WHAT IS ASSERTED HERE (assertions A0 and A6 of agent/PLAN-plan-file-lifecycle.md; the
transition rules A1-A5 need a base ref and land separately):

  A0  every plan on disk has a ledger entry whose status, owner, open/done counts and
      task signatures match, and every ledger entry names a plan that exists.
  A6  the scan is not vacuous: a floor on plan files, a floor on total open boxes, and
      a refusal to judge when the parser resolves NOTHING from a tree that plainly
      contains checkbox lines.

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

import hashlib
import json
import os
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
    print("  Blind spot: this proves the ledger DESCRIBES the tree. Whether a box that")
    print("  left the set was ticked, moved or deleted needs a base ref, and is A1.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Controls for wl_planindex: the `agent/INDEX.md` plan census and its three states.

WHAT THIS HAS TO PROVE, and why a one-directional suite would be worthless here.

W12 P1.7 replaced a plans block that opened every `agent/PLAN-*.md` with one that reads a committed census. That trade is only safe if TWO things hold, and they pull in opposite directions:

  1. when the census is fresh, the listing is the SAME listing and no plan is
     opened -- otherwise the change is a lie about its own cost, and
  2. when the census is stale or absent, the listing is REBUILT and the session is
     TOLD -- otherwise the change is a silent correctness regression, which is
     strictly worse than the 2 MB it saves.

So every state below is asserted with its opposite beside it. The one that matters most is the perturbation control: a staleness check that cannot fire looks exactly like a repo that is never stale, and the only way to tell them apart is to break the census on purpose and watch it be caught.

Run: python3 .claude/hooks/stop/test-planindex.py Reached by: .claude/hooks/test-hooks.sh (the per-module suite loop).
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import wl_checks as CK
import wl_planfile
import wl_planindex as PI
import wl_planrec as R


class Tally:
    """A class attribute rather than a module global, matching test-planrec.py.
    Same reason there: `global` in every assertion helper is the shape that lets
    a counter silently stop counting when one helper forgets the declaration."""

    count = 0
    fails = 0


def ck(name, cond, detail=""):
    Tally.count += 1
    if cond:
        print("  PASS  %s" % name)
    else:
        Tally.fails += 1
        print("  FAIL  %s%s" % (name, ("  -- " + str(detail)) if detail else ""))


def eq(name, got, want):
    ck(name, got == want, "got %r want %r" % (got, want))


PLAN = """# PLAN-%s

Status: %s
Owner: unowned

## Design

%s

## Tasks

%s
"""


def plan_text(slug, status="draft", body="Prose.", open_n=0, done_n=0, pad=0):
    boxes = "\n".join(["- [ ] open task %d" % i for i in range(open_n)])
    boxes += "\n" + "\n".join(["- [x] done task %d" % i for i in range(done_n)])
    return PLAN % (slug, status, body + ("\n" + "x" * pad if pad else ""), boxes)


class Tree:
    """A throwaway repo root with an agent/ directory. NOTHING under the real
    agent/ is touched by this suite -- W12's standing decision is never-delete, and a test that perturbs the live corpus to prove a staleness check would be
    the exact accident that decision exists to prevent."""

    def __init__(self, plans):
        self.td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.td.name)
        (self.root / "agent").mkdir()
        for name, text in plans:
            (self.root / "agent" / name).write_text(text, encoding="utf-8")

    def write_index(self, extra=""):
        rows = PI.census_rows(self.root)
        (self.root / PI.INDEX_REL).write_text(PI.render_census(rows) + extra, encoding="utf-8")
        return rows

    def block(self):
        return CK.plans_block(self.root)

    def close(self):
        self.td.cleanup()


def reads_during(fn):
    """(result, [paths read]). The measurement the whole change is judged on:
    the fresh path must open ZERO plan files, and asserting that needs the actual
    call list, not a timing that a fast disk would make meaningless."""
    seen = []
    orig = pathlib.Path.read_text

    def spy(self, *a, **k):
        seen.append(str(self))
        return orig(self, *a, **k)

    pathlib.Path.read_text = spy
    try:
        return fn(), seen
    finally:
        pathlib.Path.read_text = orig


print("== 0. the two restated constants agree with their originals ==")
# wl_planindex restates INDEX_REL rather than importing wl_planrec, to keep the hook path free of the record machinery's git dependency. A restated constant is only safe if something asserts the restatement, which is this.
eq("INDEX_REL matches wl_planrec's", PI.INDEX_REL, R.INDEX_REL)
eq("plan_dir matches wl_checks'", str(PI.plan_dir("/x")), str(CK.plan_dir("/x")))

print("== 1. render/parse round trip ==")
t = Tree(
    [
        ("PLAN-alpha.md", plan_text("alpha", "draft", open_n=2, done_n=1)),
        ("PLAN-beta.md", plan_text("beta", "done", open_n=0, done_n=3)),
        ("PLAN-gamma.md", plan_text("gamma", "ready")),
    ]
)
rows = t.write_index()
eq("census_rows finds every plan", len(rows), 3)
eq("parse_census round-trips the rows", PI.parse_census(PI.render_census(rows)), sorted(rows))
by_rel = {r[0]: r for r in rows}
eq(
    "a plan's boxes reach its row",
    by_rel["agent/PLAN-alpha.md"][3:5],
    (2, 1),
)
eq("  and a done plan's ticked boxes do too", by_rel["agent/PLAN-beta.md"][3:5], (0, 3))
eq("  and a box-free plan carries zeros", by_rel["agent/PLAN-gamma.md"][3:5], (0, 0))
# ANTI-VACUITY: an empty census must render "" and NOT a table with no rows, or `render_index(rows) + census` would grow a generated section that says nothing and R8's zero-record controls would start failing for an unrelated reason.
eq("render_census([]) is the empty string", PI.render_census([]), "")
eq("parse_census over text with no section is []", PI.parse_census("# nothing here"), [])

print("== 2. THE FRESH PATH: right answer, zero plan opens ==")
(rows2, state2, detail2), seen = reads_during(lambda: PI.index_census(t.root))
eq("a matching index reads FRESH", state2, PI.CENSUS_FRESH)
eq("  and hands back every row", len(rows2), 3)
eq("  and its detail is empty", detail2, ())
eq("  and it opened exactly one file", len(seen), 1)
ck("  and that file was the index", seen[0].endswith("agent/INDEX.md"), seen)
ck(
    "CONTROL: no PLAN-*.md was opened on the fresh path",
    not [p for p in seen if "PLAN-" in p],
    seen,
)
eq("a fresh index emits NO banner", PI.banner(state2, detail2, 3), "")

fresh_listing, fresh_live = t.block()
eq("the fresh listing names both live plans", len(fresh_live), 2)
ck("  and carries no banner", "!!" not in fresh_listing, fresh_listing)

print("== 3. THE STALE PATH, one perturbation per kind ==")
# 3a. A PLAN THE INDEX DOES NOT KNOW.
(t.root / "agent" / "PLAN-delta.md").write_text(plan_text("delta", "draft"), encoding="utf-8")
_r, state, detail = PI.index_census(t.root)
eq("a plan added since the index reads STALE", state, PI.CENSUS_STALE)
eq("  and it is reported as ADDED", detail[0], ["agent/PLAN-delta.md"])
eq("  and nothing is reported as removed or resized", (detail[1], detail[2]), ([], []))
b = PI.banner(state, detail, 4)
ck("  and the banner shouts STALE", "!! PLAN INDEX STALE" in b, b)
ck("  and names the offending plan", "PLAN-delta.md" in b, b)
ck("  and names the regeneration command", PI.REGEN_CMD in b, b)
# THE CONTROL FOR 3a: regenerating clears it. Without this the STALE verdict could be a permanent state the fresh path can never reach, which reports "always broken" just as loudly as it reports a real drift.
t.write_index()
eq(
    "CONTROL: regenerating the index makes it FRESH again",
    PI.index_census(t.root)[1],
    PI.CENSUS_FRESH,
)

# 3b. A PLAN THE INDEX STILL NAMES.
(t.root / "agent" / "PLAN-delta.md").unlink()
_r, state, detail = PI.index_census(t.root)
eq("a plan removed since the index reads STALE", state, PI.CENSUS_STALE)
eq("  and it is reported as REMOVED", detail[1], ["agent/PLAN-delta.md"])
ck(
    "  and the banner says so",
    "indexed but gone" in PI.banner(state, detail, 3),
    PI.banner(state, detail, 3),
)
t.write_index()

# 3c. AN EDIT THAT CHANGES THE BYTE COUNT. This is the signal the hook actually has: it cannot hash the plans without reading them, which is the cost it exists to avoid, so size is what it compares. The blind spot -- a same-length edit -- is asserted below rather than hidden, because a documented gap that a CI gate closes is honest and an undocumented one is a trap.
p_alpha = t.root / "agent" / "PLAN-alpha.md"
p_alpha.write_text(p_alpha.read_text(encoding="utf-8") + "\nappended prose\n", encoding="utf-8")
_r, state, detail = PI.index_census(t.root)
eq("a plan whose size changed reads STALE", state, PI.CENSUS_STALE)
eq("  and it is reported as RESIZED", detail[2], ["agent/PLAN-alpha.md"])
ck("  and the banner says so", "changed size" in PI.banner(state, detail, 3))

# 3d. THE NAMED BLIND SPOT, asserted so it cannot quietly widen. A same-length edit is invisible to `stat` -- and `Status: draft` -> `Status: ready` is exactly that, which is why the gap is worth an assertion rather than a footnote. R8's byte-equality in check_plan_record.py is what catches it. If this control ever starts FAILING, the hook grew a stronger signal and this comment is
# the thing
# to update; it must never be deleted to make a red go away.
before = p_alpha.read_text(encoding="utf-8")
t.write_index()
swapped = before.replace("Status: draft", "Status: ready", 1)
ck(
    "CONTROL: the status swap really is the same length",
    swapped != before and len(swapped) == len(before),
    "%d vs %d" % (len(swapped), len(before)),
)
p_alpha.write_text(swapped, encoding="utf-8")
eq(
    "KNOWN GAP: `draft` -> `ready` is NOT seen by the stat check (R8 catches it)",
    PI.index_census(t.root)[1],
    PI.CENSUS_FRESH,
)
# AND THE CONSEQUENCE, stated as an assertion rather than left to the reader: the listing keeps printing the OLD status until the index is regenerated. It is a stale field, never a short or empty list, which is the distinction that makes the gap tolerable at all.
_gap_listing, _gap_live = t.block()
eq(
    "  and the listing shows the stale status, not a missing plan",
    [r[1] for r in _gap_live if r[0] == "agent/PLAN-alpha.md"],
    ["draft"],
)
t.write_index()
eq(
    "  CONTROL: regenerating picks the new status up",
    [r[1] for r in t.block()[1] if r[0] == "agent/PLAN-alpha.md"],
    ["ready"],
)
p_alpha.write_text(before, encoding="utf-8")
t.write_index()

print("== 4. THE ABSENT PATH, and it is not the same as EMPTY ==")
(t.root / PI.INDEX_REL).unlink()
_r, state, detail = PI.index_census(t.root)
eq("no index at all reads ABSENT", state, PI.CENSUS_ABSENT)
b = PI.banner(state, detail, 3)
ck("  and the banner shouts ABSENT", "!! PLAN INDEX ABSENT" in b, b)
ck("  and it is NOT confused with STALE", "STALE" not in b, b)
# An index that exists but carries only the record table is ABSENT for this reader's purposes, and must say ABSENT rather than parse to zero rows and be mistaken for "there are no plans".
(t.root / PI.INDEX_REL).write_text("# INDEX\n\nrecord table only, no census\n", encoding="utf-8")
eq(
    "an index with no census section also reads ABSENT",
    PI.index_census(t.root)[1],
    PI.CENSUS_ABSENT,
)
# AND THE THIRD NOTHING: a census HEADING whose rows do not parse. This is the
# case the "empty must be distinguishable from absent" rule is really about -- a
# section that is present but yields zero rows must never read as "there are no plans", because the directory says otherwise. It is STALE: every plan on disk is missing from the census, which is exactly what the diff says.
(t.root / PI.INDEX_REL).write_text(
    PI.CENSUS_SECTION + "\n\n| Plan | Status |\n|---|---|\n| garbled | row |\n",
    encoding="utf-8",
)
_r, _state, _detail = PI.index_census(t.root)
eq("a census section whose rows do not parse reads STALE, not empty", _state, PI.CENSUS_STALE)
eq("  and every plan on disk is reported as missing from it", len(_detail[0]), 3)
ck("  and no rows are handed back", _r == [], _r)

print("== 5. THE FALLBACK IS NOT SHORT, AND NOT EMPTY ==")
# THE FAILURE THIS SUITE EXISTS FOR. A hook that printed a short or empty list because its index was missing would be worse than the cost the index saves.
#
# The baseline is RE-TAKEN here rather than reused from section 2: section 3 perturbed the fixture on purpose, so section 2's listing describes a tree that no longer exists. Comparing against it would fail for a reason that has nothing to do with the fallback, which is a test that cries wolf about its own setup. Section 4 left a junk index behind on purpose, so regenerate before
# baselining.
t.write_index()
fresh_listing, fresh_live = t.block()
eq(
    "CONTROL: the re-taken baseline is on the FRESH path",
    PI.index_census(t.root)[1],
    PI.CENSUS_FRESH,
)
(t.root / PI.INDEX_REL).unlink()
absent_listing, absent_live = t.block()
ck("the absent-index listing carries the banner", "!! PLAN INDEX ABSENT" in absent_listing)
eq("  and it names the SAME live plans as the fresh path", absent_live, fresh_live)
eq(
    "  and its plan lines are byte-identical to the fresh ones",
    [ln for ln in absent_listing.splitlines() if ln.lstrip().startswith("agent/")],
    [ln for ln in fresh_listing.splitlines() if ln.lstrip().startswith("agent/")],
)
(t.root / "agent" / "PLAN-eps.md").write_text(plan_text("eps", "draft"), encoding="utf-8")
t.write_index()
(t.root / "agent" / "PLAN-eps.md").unlink()
stale_listing, stale_live = t.block()
ck("the stale-index listing carries the banner", "!! PLAN INDEX STALE" in stale_listing)
eq("  and it too names the SAME live plans", stale_live, fresh_live)
t.write_index()

print("== 6. EMPTY IS DISTINGUISHABLE FROM ABSENT ==")
# Three different nothings, and the block must not render them the same way.
no_plans = Tree([])
eq("a project with NO agent/PLAN-*.md emits no block at all", no_plans.block(), ("", []))
no_plans.close()

all_done = Tree(
    [
        ("PLAN-old.md", plan_text("old", "done", open_n=0, done_n=2)),
        ("PLAN-older.md", plan_text("older", "superseded")),
    ]
)
all_done.write_index()
dl, dlive = all_done.block()
eq("a project whose plans are ALL done reports no live plan", dlive, [])
ck("  but still emits a block, so 'empty' is not silence", dl != "", repr(dl))
ck("  and the block carries the tree-wide totals", "tree-wide" in dl, dl)
all_done.close()

print("== 7. ORDER AND ARITHMETIC MATCH THE OLD PATH EXACTLY ==")
# plan_status_excerpt takes live[0] as "the newest live plan", so an index that lost mtime order would silently change which plan a compacted session is handed.
# The census is stored by PATH (stable across a clone); the order is re-imposed
# from the same `stat` the freshness check already does.
order = Tree(
    [
        ("PLAN-a.md", plan_text("a", "draft")),
        ("PLAN-b.md", plan_text("b", "draft")),
        ("PLAN-c.md", plan_text("c", "draft")),
    ]
)
os.utime(order.root / "agent" / "PLAN-b.md", (10**9, 10**9))
os.utime(order.root / "agent" / "PLAN-a.md", (2 * 10**9, 2 * 10**9))
os.utime(order.root / "agent" / "PLAN-c.md", (3 * 10**9, 3 * 10**9))
order.write_index()
_l, live_fast = order.block()
eq(
    "the fast path returns plans NEWEST FIRST, as plan_records always did",
    [r[0] for r in live_fast],
    ["agent/PLAN-c.md", "agent/PLAN-a.md", "agent/PLAN-b.md"],
)
(order.root / PI.INDEX_REL).unlink()
_l2, live_slow = order.block()
eq("CONTROL: the fallback agrees with it row for row", live_slow, live_fast)
order.close()

# The box arithmetic is what `plan_box_census` used to own, and the two must not drift: a plan with NO boxes contributes no row to the totals.
arith = Tree(
    [
        ("PLAN-boxed.md", plan_text("boxed", "draft", open_n=2, done_n=1)),
        ("PLAN-prose.md", plan_text("prose", "draft")),
        ("PLAN-scoped.md", plan_text("scoped", "ready", open_n=1, done_n=0)),
    ]
)
arith.write_index()
al, _ = arith.block()
ck(
    "a plan with no boxes grows no box suffix",
    "PLAN-prose.md [draft] (" in al
    and "prose.md [draft] (%d lines)"
    % len((arith.root / "agent" / "PLAN-prose.md").read_text().splitlines())
    in al,
    al,
)
ck(
    "the tree-wide line counts only box-carrying plans",
    "2 plan file(s) carry 3 open box(es) and 1 ticked" in al,
    al,
)
ck("the scope split matches in_scope_status", "1 of them are in scope" in al, al)
eq(
    "CONTROL: in_scope_status still splits these two statuses apart",
    (wl_planfile.in_scope_status("ready"), wl_planfile.in_scope_status("draft")),
    (True, False),
)
arith.close()
t.close()

# ANTI-VACUITY. A suite that plants nothing and asserts nothing exits 0 too, so the floor is asserted rather than assumed: if a future edit breaks the fixture setup, this fails loudly instead of reporting a clean run over no work.
if Tally.count < 40:
    print("VACUOUS: only %d checks ran; this suite has 40+" % Tally.count)
    Tally.fails += 1

print("\n%d checks, %d failures" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)

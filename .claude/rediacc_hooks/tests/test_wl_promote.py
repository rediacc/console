"""`worklist.py --promote` (#dd9b7624): one plan into agent/plans/QUEUE.md `## Promoted`, with its unfinished prerequisites pulled in ahead of it by the RQ-DEPS repair `check:ci-plan-record -- --update` runs.

Every case drives the real CLI through `wlfix` against a fixture checkout whose plans are committed, because the repair's dependency graph reads tracked plans only. Every refusal is paired with the accepted call it differs from by one planted fact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib

PQ = wlfix.import_wl("wl_planqueue")

QUEUE = (
    "# Plan queue\n\n## Promoted\n\n"
    "1. agent/plans/PLAN-head.md -- operator 2026-10-01: the first entry\n\n"
    "## Generated\n\n"
)


def _plan(depends="", opened=1, done=0, status="approved"):
    dep = depends or "no-dep -- a standalone plan in the promote fixture"
    boxes = "".join("- [x] D%d a ticked box sits here\n" % i for i in range(done))
    boxes += "".join("- [ ] O%d an open box sits here\n" % i for i in range(opened))
    return (
        "# PLAN\nStatus: %s\nOwner: d778be9d\nDepends-On: %s\nPriority: P2 -- seed\n"
        "Concurrency: parallel\nOwns: docs/x/**\n\n## Boxes\n%s" % (status, dep, boxes)
    )


def seed(wl) -> pathlib.Path:
    """Plans `head`, `a` (needs `p`), `p` (needs `q`, finished), `q` and `done`, committed; the queue holds `head` alone."""
    wl.reg_repo()
    plans = wl.proj / "agent" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    texts = {
        "head": _plan(),
        "a": _plan(depends="PLAN-p.md"),
        "p": _plan(depends="PLAN-q.md"),
        "q": _plan(opened=0, done=2, status="finished"),
        "done": _plan(opened=0, done=3, status="finished"),
    }
    for name, text in texts.items():
        (plans / ("PLAN-%s.md" % name)).write_text(text, encoding="utf-8")
    queue = wl.proj / PQ.QUEUE_REL
    queue.write_text(QUEUE, encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: plans")
    return queue


def test_promote_appends_the_plan_with_its_unfinished_prerequisite_ahead(wl):
    queue = seed(wl)
    got = wl.cli("--promote", wlfix.ME, "PLAN-a.md", "operator 2026-10-23: ship it")
    assert got.rc == 0, (got.out, got.err)
    after = queue.read_text(encoding="utf-8")
    promoted, _gen = PQ.entries(after)
    # p is unfinished, so it lands ahead of a; q is finished, so it is never pulled in.
    assert promoted == [
        "agent/plans/PLAN-head.md",
        "agent/plans/PLAN-p.md",
        "agent/plans/PLAN-a.md",
    ], after
    assert "3. agent/plans/PLAN-a.md -- operator 2026-10-23: ship it" in after, after
    assert "inserted PLAN-p.md into Promoted ahead of PLAN-a.md" in got.out, got.out
    assert "promoted agent/plans/PLAN-a.md as Promoted entry 3" in got.out, got.out
    assert "git add agent/plans/QUEUE.md" in got.out, got.out
    # The landed file is its own render: the progress block and the generated section agree with it.
    assert PQ.problems(str(wl.proj)) == [], PQ.problems(str(wl.proj))
    # A second promote of the same plan is refused, and nothing moves.
    again = wl.cli("--promote", wlfix.ME, "PLAN-a.md", "operator again")
    assert again.rc == 1, again.err
    assert "already Promoted entry 3" in again.err, again.err
    assert queue.read_text(encoding="utf-8") == after


def test_promote_of_a_plan_with_no_unfinished_prerequisite_adds_only_it(wl):
    """CONTROL for the insert: p's only prerequisite q is finished, so p alone is added."""
    queue = seed(wl)
    got = wl.cli("--promote", wlfix.ME, "agent/plans/PLAN-p.md", "operator 2026-10-23")
    assert got.rc == 0, got.err
    assert PQ.entries(queue.read_text(encoding="utf-8"))[0] == [
        "agent/plans/PLAN-head.md",
        "agent/plans/PLAN-p.md",
    ]
    assert "inserted" not in got.out, got.out


def test_promote_refuses_what_cannot_be_ordered_and_writes_nothing(wl):
    queue = seed(wl)
    before = queue.read_bytes()
    for args, said in (
        (["PLAN-done.md", "operator"], "is finished"),
        (["PLAN-nope.md", "operator"], "does not exist"),
        (["agent/plans/_done/PLAN-a.md", "operator"], "not a live"),
        (["PLAN-head.md", "operator"], "already Promoted entry 1"),
        (["PLAN-a.md", "   "], "carries a note"),
    ):
        got = wl.cli("--promote", wlfix.ME, *args)
        assert got.rc != 0, (args, got.out)
        assert said in got.err, (args, got.err)
        assert "nothing was written" in got.err or got.rc == 2, (args, got.err)
        assert queue.read_bytes() == before, args
    # CONTROL: the same file accepts a live, unfinished plan.
    assert wl.cli("--promote", wlfix.ME, "PLAN-a.md", "operator").rc == 0
    assert queue.read_bytes() != before

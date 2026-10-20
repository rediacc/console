"""Retiring a moved plan's entry from `## Promoted` in agent/plans/QUEUE.md (worklist #7b9fe4f1).

THE DEFECT. `check_plan_folders.py --move` moved a finished plan into `_done/` and left a stub, and nothing took its numbered entry out of `## Promoted`: 13 of 17 entries named stubs, their prose promising they would leave "when PR #600 merges", long after it had. These cases pin the two halves of the fix in `wl_planqueue`: `without_promoted` drops exactly the named entries and renumbers the rest, every other byte kept, and `moved_problems` (check:ci-plan-record RQ-MOVED) fires on a stub entry and stays silent on a live one. Every FIRE has an inverse that differs by one planted fact.
"""

from __future__ import annotations

import pytest

from rediacc_hooks.tests import wlfix

PQ = wlfix.import_wl("wl_planqueue")

LIVE_PLAN = (
    "# P\n\nStatus: approved\n\n## Tasks\n\n- [x] D1 the ticked box\n- [ ] T1 the open box\n"
)
STUB = "# P (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-%s.md\n\nThis plan moved.\n"
DONE_PLAN = "# P\n\nStatus: done\n\n## Tasks\n\n- [x] D1 the ticked box\n"

HAND = (
    "# Plan queue\n\nHand prose, kept   as typed.\n\n"
    "## Settings\n\nnothing here\n\n"
    "## Promoted\n\n"
    "1. agent/plans/PLAN-gone-a.md -- done; leaves this list when PR #1 merges\n"
    "2. agent/plans/PLAN-live-a.md -- operator pick, 1 open\n"
    "3. agent/plans/PLAN-gone-b.md -- done\n"
    "   a continuation line of entry 3\n"
    "4. agent/plans/PLAN-live-b.md -- operator pick -- solo\n"
    "\n"
    "A prose line naming agent/plans/PLAN-gone-a.md stays.\n\n"
    "## Generated\n\n"
    "<!-- queue:generated:begin -->\n"
    "1. agent/plans/PLAN-gone-a.md -- a generated line is not Promoted's\n"
    "<!-- queue:generated:end -->\n"
)

RETIRED = (
    "# Plan queue\n\nHand prose, kept   as typed.\n\n"
    "## Settings\n\nnothing here\n\n"
    "## Promoted\n\n"
    "1. agent/plans/PLAN-live-a.md -- operator pick, 1 open\n"
    "2. agent/plans/PLAN-live-b.md -- operator pick -- solo\n"
    "\n"
    "A prose line naming agent/plans/PLAN-gone-a.md stays.\n\n"
    "## Generated\n\n"
    "<!-- queue:generated:begin -->\n"
    "1. agent/plans/PLAN-gone-a.md -- a generated line is not Promoted's\n"
    "<!-- queue:generated:end -->\n"
)


@pytest.fixture
def root(tmp_path):
    plans = tmp_path / "agent" / "plans"
    (plans / "_done").mkdir(parents=True)
    for slug in ("live-a", "live-b"):
        (plans / ("PLAN-%s.md" % slug)).write_text(LIVE_PLAN, encoding="utf-8")
    for slug in ("gone-a", "gone-b"):
        (plans / ("PLAN-%s.md" % slug)).write_text(STUB % slug, encoding="utf-8")
        (plans / "_done" / ("PLAN-%s.md" % slug)).write_text(DONE_PLAN, encoding="utf-8")
    return tmp_path


def test_without_promoted_drops_only_the_named_entries_and_renumbers_the_rest():
    rels = {"agent/plans/PLAN-gone-a.md", "agent/plans/PLAN-gone-b.md"}
    new, removed = PQ.without_promoted(HAND, rels)
    assert removed == ["agent/plans/PLAN-gone-a.md", "agent/plans/PLAN-gone-b.md"]
    assert new == RETIRED, "every byte outside the two entries is kept, and the rest renumber 1..n"


def test_without_promoted_leaves_the_text_alone_when_nothing_matches():
    new, removed = PQ.without_promoted(HAND, {"agent/plans/PLAN-absent.md"})
    assert (new, removed) == (HAND, [])
    new, removed = PQ.without_promoted(HAND, set())
    assert (new, removed) == (HAND, [])


def test_without_promoted_never_reads_the_progress_block(root):
    once = PQ.with_fresh_progress(root, HAND)
    assert PQ.progress_text(once) is not None, "CONTROL: the block is there to be skipped"
    new, removed = PQ.without_promoted(once, {"agent/plans/PLAN-gone-b.md"})
    assert removed == ["agent/plans/PLAN-gone-b.md"]
    assert PQ.progress_text(new) == PQ.progress_text(once), "the block is the render's, not ours"
    assert PQ.promoted_numbered(new) == [
        ("1", "agent/plans/PLAN-gone-a.md"),
        ("2", "agent/plans/PLAN-live-a.md"),
        ("3", "agent/plans/PLAN-live-b.md"),
    ]


def test_moved_entries_names_the_stubs_and_not_the_live_plans(root):
    got = PQ.moved_entries(root, HAND)
    assert got == [
        ("1", "agent/plans/PLAN-gone-a.md", "agent/plans/_done/PLAN-gone-a.md"),
        ("3", "agent/plans/PLAN-gone-b.md", "agent/plans/_done/PLAN-gone-b.md"),
    ]


def test_moved_problems_fires_on_a_stub_entry(root):
    (root / PQ.QUEUE_REL).write_text(HAND, encoding="utf-8")
    got = PQ.moved_problems(root)
    assert len(got) == 2, got
    assert "PLAN-gone-a.md" in got[0]
    assert "_done/PLAN-gone-a.md" in got[0]
    assert "--retire-promoted" in got[0], "the finding names the fix"


def test_moved_problems_is_silent_on_live_entries(root):
    (root / PQ.QUEUE_REL).write_text(RETIRED, encoding="utf-8")
    assert PQ.moved_problems(root) == []


def test_moved_problems_is_silent_without_a_queue_file(root):
    assert PQ.moved_problems(root) == [], "an absent file is RQ's finding, not this one's"


def test_retire_promoted_rewrites_the_file_and_rerenders_the_progress_block(root):
    path = root / PQ.QUEUE_REL
    path.write_text(PQ.with_fresh_progress(root, HAND), encoding="utf-8")
    assert "| 4 | PLAN-live-b.md |" in path.read_text(encoding="utf-8"), "CONTROL: 4 rows before"
    got = PQ.retire_promoted(root, {"agent/plans/PLAN-gone-a.md"})
    assert got == [("agent/plans/PLAN-gone-a.md", "agent/plans/_done/PLAN-gone-a.md")]
    text = path.read_text(encoding="utf-8")
    assert [r for _n, r in PQ.promoted_numbered(text)] == [
        "agent/plans/PLAN-live-a.md",
        "agent/plans/PLAN-gone-b.md",
        "agent/plans/PLAN-live-b.md",
    ], "only the named stub left; the other stub waits for its own retirement"
    assert PQ.progress_text(text) == PQ.progress_text(PQ.with_fresh_progress(root, text))
    assert "| 3 | PLAN-live-b.md |" in text
    assert "| 4 |" not in text


def test_retire_promoted_skips_a_named_plan_that_is_not_a_stub(root):
    path = root / PQ.QUEUE_REL
    path.write_text(HAND, encoding="utf-8")
    assert PQ.retire_promoted(root, {"agent/plans/PLAN-live-a.md"}) == []
    assert path.read_text(encoding="utf-8") == HAND


def test_retire_promoted_with_no_names_retires_every_stub(root):
    path = root / PQ.QUEUE_REL
    path.write_text(HAND, encoding="utf-8")
    got = PQ.retire_promoted(root)
    assert [r for r, _t in got] == ["agent/plans/PLAN-gone-a.md", "agent/plans/PLAN-gone-b.md"]
    assert PQ.without_progress(path.read_text(encoding="utf-8")) == RETIRED
    assert PQ.moved_problems(root) == []


def test_retire_promoted_without_a_queue_file_writes_nothing(root):
    assert PQ.retire_promoted(root) == []
    assert not (root / PQ.QUEUE_REL).exists()


def test_number_notes_names_a_kept_entry_whose_note_cites_an_entry_number():
    text = HAND.replace("operator pick, 1 open", "depends on entry 3")
    assert PQ.number_notes(text) == ["agent/plans/PLAN-live-a.md"]
    assert PQ.number_notes(RETIRED) == []

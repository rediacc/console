"""The generated progress block under `## Promoted` in agent/plans/QUEUE.md (operator order 2026-10-08, worklist #1420d4b8).

Unit cases drive `wl_planqueue` directly over fixture plan files; the freshness cases go through `problems`, the function check:ci-plan-record calls; the Stop-hook case drives the REAL Stop hook over a fixture checkout (`test_wl_pr_scope_stop.loop_world`) and reads the block back. Every FIRE has an inverse that differs by one planted fact.
"""

from __future__ import annotations

import pytest

from rediacc_hooks.tests import test_wl_pr_scope_stop as PS
from rediacc_hooks.tests import wlfix

PQ = wlfix.import_wl("wl_planqueue")

HAND = (
    "# Plan queue\n\nHand prose, kept   as typed.\n\n"
    "## Promoted\n\n"
    "1. agent/plans/PLAN-half.md -- operator pick, 1 of 4 boxes open (stale prose stays)\n"
    "2. agent/plans/PLAN-all.md -- operator pick -- solo\n"
    "3. agent/plans/PLAN-moved.md -- moved to _done by a stub\n"
    "4. agent/plans/PLAN-gone.md -- the file left agent/plans\n"
    "5. agent/plans/PLAN-boxless.md -- no box yet\n"
    "6. agent/plans/PLAN-missing.md -- nowhere at all\n\n"
)


def _plan(opened: int, done: int) -> str:
    return (
        "# P\n\nStatus: approved\n\n## Tasks\n\n"
        + "".join("- [x] D%d the ticked box number %d\n" % (i, i) for i in range(done))
        + "".join("- [ ] T%d the open box number %d\n" % (i, i) for i in range(opened))
    )


@pytest.fixture
def root(tmp_path):
    plans = tmp_path / "agent" / "plans"
    (plans / "_done").mkdir(parents=True)
    (plans / "PLAN-half.md").write_text(_plan(2, 2), encoding="utf-8")
    (plans / "PLAN-all.md").write_text(_plan(0, 3), encoding="utf-8")
    (plans / "PLAN-moved.md").write_text(
        "# P\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-moved-target.md\n", encoding="utf-8"
    )
    (plans / "_done" / "PLAN-moved-target.md").write_text(_plan(1, 4), encoding="utf-8")
    (plans / "_done" / "PLAN-gone.md").write_text(_plan(0, 5), encoding="utf-8")
    (plans / "PLAN-boxless.md").write_text("# P\n\nStatus: draft\n\nNo boxes.\n", encoding="utf-8")
    return tmp_path


def _rows(root):
    return {r.num: r for r in PQ.promoted_progress(root, HAND)}


def test_counts_follow_stubs_done_folder_and_name_the_unreadable(root):
    rows = _rows(root)
    assert (rows["1"].done, rows["1"].opened, rows["1"].why) == (2, 2, "")
    assert rows["2"].finished
    assert (rows["3"].done, rows["3"].opened) == (4, 1), "a Moved-To stub is followed"
    assert rows["4"].finished, "an entry whose file left agent/plans is read from _done/"
    assert (rows["5"].total, rows["5"].why, rows["5"].finished) == (0, "", False)
    assert rows["6"].why, "a plan that exists nowhere is named, never counted as 0/0"


def test_render_overall_line_and_one_row_per_entry(root):
    body = PQ.render_progress(PQ.promoted_progress(root, HAND))
    # Plans: half, all, moved, gone, boxless, missing = 6; done: all, gone. Boxes: 4 + 3 + 5 + 5 + 0 = 17, done 2 + 3 + 4 + 5 = 14.
    assert body.splitlines()[0] == "Promoted: 2 of 6 plans done, 14 of 17 boxes done (82%)."
    assert "| 1 | PLAN-half.md | 2/4 | 2 open |" in body
    assert "| 2 | PLAN-all.md | 3/3 | done |" in body
    assert "| 3 | PLAN-moved.md | 4/5 | 1 open |" in body
    assert "| 5 | PLAN-boxless.md | 0/0 | no boxes |" in body
    assert "| 6 | PLAN-missing.md | - | unreadable:" in body


def test_a_plan_named_twice_counts_once_in_the_overall_line(root):
    text = HAND.replace(
        "6. agent/plans/PLAN-missing.md -- nowhere at all\n",
        "6. agent/plans/PLAN-half.md -- named again\n",
    )
    body = PQ.render_progress(PQ.promoted_progress(root, text))
    assert body.splitlines()[0] == "Promoted: 2 of 5 plans done, 14 of 17 boxes done (82%)."
    assert "| 6 | PLAN-half.md | 2/4 | 2 open |" in body


def test_no_entries_renders_a_plain_line():
    assert PQ.render_progress(()) == "Promoted: no entries.\n"


def test_insertion_keeps_every_hand_written_byte_and_is_idempotent(root):
    once = PQ.with_fresh_progress(root, HAND)
    assert once != HAND
    assert PQ.without_progress(once) == HAND
    assert once.index(PQ.PROGRESS_BEGIN) > once.index("## Promoted")
    assert once.index(PQ.PROGRESS_END) < once.index("1. agent/plans/PLAN-half.md")
    assert PQ.with_fresh_progress(root, once) == once


def test_a_file_without_a_promoted_heading_is_left_alone(root):
    text = "# Plan queue\n\nNothing promoted.\n"
    assert PQ.with_fresh_progress(root, text) == text


def test_entries_and_solo_never_read_the_block(root):
    once = PQ.with_fresh_progress(root, HAND)
    assert PQ.entries(once) == PQ.entries(HAND)
    assert PQ.solo_plans(once) == PQ.solo_plans(HAND) == {"agent/plans/PLAN-all.md"}
    # Even a numbered entry planted inside the block is not read.
    planted = once.replace(
        PQ.PROGRESS_END, "9. agent/plans/PLAN-planted.md -- solo\n" + PQ.PROGRESS_END, 1
    )
    assert "agent/plans/PLAN-planted.md" not in PQ.entries(planted)[0]
    assert "agent/plans/PLAN-planted.md" not in PQ.solo_plans(planted)


def _queue_root(root):
    path = root / PQ.QUEUE_REL
    path.write_text(HAND, encoding="utf-8")
    PQ.problems(root, update=True)
    return path


def test_the_freshness_check_reports_a_planted_stale_ratio(root):
    path = _queue_root(root)
    fresh = path.read_text(encoding="utf-8")
    assert PQ.problems(root) == [], "CONTROL: the rendered queue is silent"
    stale = fresh.replace("| 2/4 | 2 open |", "| 3/4 | 1 open |", 1)
    assert stale != fresh
    path.write_text(stale, encoding="utf-8")
    got = PQ.problems(root)
    assert got
    assert "Promoted progress block" in got[0]
    assert "generated section" not in got[0], "only the part that is stale is named"


def test_the_freshness_check_reports_a_tick_with_no_render(root):
    _queue_root(root)
    (root / "agent/plans/PLAN-half.md").write_text(_plan(1, 3), encoding="utf-8")
    assert any("Promoted progress block" in p for p in PQ.problems(root))
    assert PQ.problems(root, update=True) == []
    text = (root / PQ.QUEUE_REL).read_text(encoding="utf-8")
    assert "| 1 | PLAN-half.md | 3/4 | 1 open |" in text
    assert PQ.without_progress(text).startswith(HAND)


def test_refresh_the_plan_verb_path_rerenders_the_ratio(root):
    _queue_root(root)
    (root / "agent/plans/PLAN-half.md").write_text(_plan(0, 4), encoding="utf-8")
    assert PQ.refresh(root) is True
    text = (root / PQ.QUEUE_REL).read_text(encoding="utf-8")
    assert "| 1 | PLAN-half.md | 4/4 | done |" in text
    assert PQ.refresh(root) is False


# ---- the Stop hook ------------------------------------------------------------------------------


@pytest.fixture
def hook(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def _progress_of(fix) -> str:
    return PQ.progress_text((fix.proj / PQ.QUEUE_REL).read_text(encoding="utf-8")) or ""


def test_the_stop_hook_heals_a_stale_progress_block(hook):
    own = PS.loop_world(hook)
    path = hook.proj / PQ.QUEUE_REL
    stale = PQ.with_progress(path.read_text(encoding="utf-8"), "Promoted: stale.\n")
    path.write_text(stale, encoding="utf-8")
    PS.run_stop(hook)
    body = _progress_of(hook)
    assert body.splitlines()[0] == "Promoted: 0 of 2 plans done, 1 of 4 boxes done (25%).", body
    assert "| 1 | %s | 1/2 | 1 open |" % own.rsplit("/", 1)[-1] in body, body
    assert "| 2 | PLAN-queued-next.md | 0/2 | 2 open |" in body, body


def test_the_stop_hook_adds_no_block_to_a_queue_without_one(hook):
    """CONTROL for the case above: the stop re-renders an existing block and never inserts one; the first insertion is the gate's --update or a plan verb."""
    PS.loop_world(hook)
    PS.run_stop(hook)
    assert PQ.progress_text((hook.proj / PQ.QUEUE_REL).read_text(encoding="utf-8")) is None


def test_a_short_checkbox_is_still_a_box():
    """A checkbox counts at any length: "- [ ] WC1: e2e." normalises to 7 characters, under the plain-bullet floor, and was dropped, so PLAN-inline-suppressions read 0/10 instead of 0/11."""
    PF = wlfix.import_wl("wl_planfile")
    text = "# P\n\n## Tasks\n\n- [ ] WA1: the long first box.\n- [ ] WC1: e2e.\n- [x] W2: ok.\n"
    opened, done = PF.plan_boxes(text)
    assert [t[:4] for t in opened] == ["WA1:", "WC1:"], opened
    assert len(done) == 1, done


def test_a_short_plain_bullet_stays_screened_out():
    """CONTROL for the case above: the 8-character floor still drops a short plain bullet under an action heading."""
    PFID = wlfix.import_wl("wl_planfid")
    tasks = PFID.plan_tasks("# P\n\n## Tasks\n\n- tiny.\n- a plain bullet long enough to count\n")
    assert tasks == ["a plain bullet long enough to count"], tasks

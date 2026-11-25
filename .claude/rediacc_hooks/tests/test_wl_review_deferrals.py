"""The Stop hook's view of a deferred per-commit review finding (agent/plans/PLAN-deferred-findings-block-merge.md L3, D5).

A legacy `deferred #<item>` is unfinished work: `stop_texts` puts it in the `commit-review` block with the triage command and the plan-and-fix order, a deferral whose triage item is leased `[>]` moves to the note while its writer works, and a fixed finding leaves both. The pr-finish "per-commit reviews clean" box reads `not push_refusals(st)`, and the wait stand-down reads `set(push_refusals(st)) <= {"in_flight"}`
(wl_checks.py, the `_prf_rev` and `_prf_rev_wait` lines), so both are asserted on the same state.

Each world is a real repository holding one committed review record; only the finding's Resolution line differs between the refused worlds and their controls.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

BRANCH = "1008-9"
SHA = "1234abcd" + "0" * 32
FID = "1234abcd.1"
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
RESOLUTIONS = {
    "deferred": "deferred #f32c08e6 | deadbeef 2026-10-08T08:54:08Z",
    "fixed": "fixed %s | deadbeef 2026-10-08T09:00:00Z" % ("9" * 40),
    "open": "open",
}


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV, check=True
    )


def _state(tmp_path, kind, severity="medium", items=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=%s" % BRANCH)
    finding = R.Finding(
        id=FID,
        severity=severity,
        file="f.py",
        line=2,
        anchor="in-diff",
        claim="the guard's 'empty' arm returns before the lock is released",
        resolution=RESOLUTIONS[kind],
    )
    review = R.Review(
        sha=SHA,
        subject="fix(x): y",
        branch=BRANCH,
        reviewed_at="2026-10-08T08:00:00Z",
        model="m",
        verdict="findings",
        findings=[finding],
    )
    target = R.review_path(repo, BRANCH, SHA)
    R.write_atomic(target, R.render(review))
    _git(repo, "add", "--", str(target.relative_to(repo)))
    _git(repo, "commit", "-q", "-m", "chore(reviews): record")
    return R.branch_state(repo, BRANCH, repos=(), items=items)


def _pr_finish_box(st):
    """The two wl_checks readings of the review box: ticked, and the in-flight wait stand-down."""
    refusals = R.push_refusals(st)
    return not refusals, set(refusals) <= {"in_flight"}


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_a_planted_deferral_blocks_a_stop_with_the_triage_command(tmp_path, severity):
    st = _state(tmp_path, "deferred", severity, items={"f32c08e6": " "})
    block, malformed, _note = R.stop_texts(st)
    assert not malformed
    assert "DEFERRED PER-COMMIT REVIEW FINDING(S) on %s (1)" % BRANCH in block, block
    assert "DEFERRED [%s] %s f.py:2" % (severity, FID) in block, block
    assert "worklist.py --triage <me> '%s f.py:2: the guards empty arm" % FID in block, block
    for step in ("INLINE:", "PLAN+SUBAGENT:", "OPERATOR-ONLY:", "not-a-bug"):
        assert step in block, (step, block)
    assert "defer it" not in block, "the block must not offer deferral as a way out"


def test_a_leased_triage_item_turns_the_block_into_a_note(tmp_path):
    """D5 wait stand-down: the triage item that names the finding is `[>]`, so the line waits on its writer; the refusal stays."""
    items = {"f32c08e6": " ", "77aa88bb": (">", "%s f.py:2: guard arm" % FID, "plan-subagent")}
    st = _state(tmp_path, "deferred", items=items)
    block, _malformed, note = R.stop_texts(st)
    assert block == "", block
    assert "DEFERRED [medium] %s f.py:2: its triage item is leased [>]" % FID in note, note
    assert R.push_refusals(st) == ["deferred"]


def test_the_deferrals_own_leased_item_counts_from_a_state_only_fold(tmp_path):
    """The Stop hook passes {id: state} today; the item the deferral names is enough to stand down."""
    st = _state(tmp_path, "deferred", items={"f32c08e6": ">"})
    block, _malformed, note = R.stop_texts(st)
    assert block == "", block
    assert "leased [>]" in note, note


def test_control_an_unleased_unrelated_item_keeps_the_block(tmp_path):
    items = {"f32c08e6": " ", "77aa88bb": (">", "some other work", "inline")}
    block, _malformed, _note = R.stop_texts(_state(tmp_path, "deferred", items=items))
    assert FID in block, block


def test_fixed_clears_both_the_block_and_the_note(tmp_path):
    st = _state(tmp_path, "fixed", items={"f32c08e6": ">"})
    block, malformed, note = R.stop_texts(st)
    assert block == "", block
    assert malformed == "", malformed
    assert "DEFERRED" not in note, note
    assert _pr_finish_box(st) == (True, True)


def test_an_open_finding_named_by_a_leased_item_waits_in_the_note(tmp_path):
    """The same stand-down for an open finding: a leased writer fixing it turns the block into a note; push still refuses it."""
    items = {"77aa88bb": (">", "review %s [high]: guard arm" % FID)}
    st = _state(tmp_path, "open", "high", items=items)
    block, _malformed, note = R.stop_texts(st)
    assert block == "", block
    assert "OPEN [high] %s f.py:2: an item naming it is leased [>]" % FID in note, note
    assert R.push_refusals(st) == ["blocking"]


def test_control_an_open_finding_with_no_leased_item_blocks(tmp_path):
    items = {"77aa88bb": (" ", "review %s [high]: guard arm" % FID)}
    block, _malformed, _note = R.stop_texts(_state(tmp_path, "open", "high", items=items))
    assert "OPEN PER-COMMIT REVIEW FINDING(S)" in block, block
    assert FID in block, block


@pytest.mark.parametrize("items", [None, {"f32c08e6": " "}, {"f32c08e6": ">"}])
def test_the_pr_finish_review_box_stays_unticked_while_a_deferral_stands(tmp_path, items):
    ticked, waiting = _pr_finish_box(_state(tmp_path, "deferred", items=items))
    assert not ticked, "a deferral must keep the per-commit reviews box unticked"
    assert not waiting, "a deferral is not the reviewer-running wait"


@pytest.mark.parametrize(
    ("text", "token", "want"),
    [
        ("operator-only: 71afd29f.12 needs a call", "71afd29f.1", False),
        ("operator-only: x71afd29f.1 needs a call", "71afd29f.1", False),
        ("operator-only: 71afd29f.1 needs a call", "71afd29f.1", True),
        ("operator-only: 71afd29f.1.", "71afd29f.1", True),
        ("operator-only: 71afd29f.1.2 needs a call", "71afd29f.1", False),
        ("operator-only: 71afd29f.1. Next sentence", "71afd29f.1", True),
        ("see pr:8/F12", "pr:8/F1", False),
        ("see pr:8/F1, the rest fixed", "pr:8/F1", True),
    ],
)
def test_a_waiver_item_names_its_finding_as_a_whole_token(text, token, want):
    """Findings b18d31bd.1 and b18d31bd.2: a substring test let an item naming `.12` or `F12` waive `.1` or `F1`."""
    assert R.names_token(text, token) is want


# ---- R20261125.1 (agent/plans/PLAN-stop-hook-retro-20261125.md friction 1): the block names the in-flight route it already honours.
K = wlfix.import_wl("wl_checks")
HOLDER = "e32de9b1"


def _rec(state, worker, **extra):
    return dict({"id": HOLDER, "state": state, "worker": worker, "text": "red-gate fixer"}, **extra)


def test_an_open_finding_with_no_naming_item_prints_the_update_line(tmp_path):
    """The 9a666914.1 shape: a high finding no item names blocks, and the block now says how to hand it to a live writer."""
    st = _state(tmp_path, "open", "high", items=K.review_items([_rec(">", "w-live")], {"w-live"}))
    block, _malformed, _note = R.stop_texts(st, holders=[HOLDER])
    assert "OPEN PER-COMMIT REVIEW FINDING(S)" in block, block
    assert (
        "in flight with a live writer: worklist.py --update <me> %s '%s ...'" % (HOLDER, FID)
        in block
    ), block
    assert "live [>] item(s) of this session: %s" % HOLDER in block, block


def test_with_no_live_item_the_update_line_names_a_placeholder(tmp_path):
    block, _malformed, _note = R.stop_texts(_state(tmp_path, "open", "high", items={}))
    assert "worklist.py --update <me> <its [>] item> '%s ...'" % FID in block, block
    assert "live [>] item(s) of this session" not in block, block


def test_the_finding_in_a_live_items_lease_note_is_a_note_not_a_block(tmp_path):
    """Following the printed route: the id written into a live item's lease note stands the finding down."""
    recs = [_rec(">", "w-live", lease_note="scope added: review %s class" % FID)]
    st = _state(tmp_path, "open", "high", items=K.review_items(recs, {"w-live"}))
    block, _malformed, note = R.stop_texts(st, holders=[HOLDER])
    assert block == "", block
    assert "OPEN [high] %s f.py:2: an item naming it is leased [>]" % FID in note, note
    assert R.push_refusals(st) == ["blocking"]


def test_control_the_same_lease_note_on_a_dead_worker_blocks(tmp_path):
    recs = [_rec(">", "w-dead", lease_note="scope added: review %s class" % FID)]
    st = _state(tmp_path, "open", "high", items=K.review_items(recs, {"w-live"}))
    block, _malformed, note = R.stop_texts(st)
    assert "OPEN PER-COMMIT REVIEW FINDING(S)" in block, block
    assert FID in block, block
    assert "an item naming it is leased" not in note, note


def test_mark_commands_keeps_the_three_resolutions_first():
    got = R.mark_commands(FID)
    assert len(got) == 4, got
    assert [g.split()[4] for g in got[:3]] == ["fixed", "not-a-bug", "waived"], got
    assert got[3].startswith("in flight with a live writer: worklist.py --update <me> "), got


def test_several_live_items_are_all_listed_and_none_is_named_in_the_update_line(tmp_path):
    """Findings 85ee5a27.1 and .2: the list is not cut at the block limit, and the update line does not pick an unrelated first item."""
    ids = ["%08x" % (0xA0000000 + i) for i in range(7)]
    st = _state(tmp_path, "open", "high", items={})
    block, _malformed, _note = R.stop_texts(st, holders=ids)
    assert "live [>] item(s) of this session: %s" % ", ".join(ids) in block, block
    assert "worklist.py --update <me> <its [>] item> '%s ...'" % FID in block, block
    assert ids[0] not in block.split("live [>] item(s)")[0], block

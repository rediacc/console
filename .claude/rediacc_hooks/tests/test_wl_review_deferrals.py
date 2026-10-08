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
        ("see pr:8/F12", "pr:8/F1", False),
        ("see pr:8/F1, the rest fixed", "pr:8/F1", True),
    ],
)
def test_a_waiver_item_names_its_finding_as_a_whole_token(text, token, want):
    """Findings b18d31bd.1 and b18d31bd.2: a substring test let an item naming `.12` or `F12` waive `.1` or `F1`."""
    assert R.names_token(text, token) is want

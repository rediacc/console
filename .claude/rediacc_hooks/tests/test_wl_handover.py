"""wl_handover, the handover contract between the landing and the development tree (agent/plans/PLAN-simple-two-tree-loop.md D5, box B7).

The fold and the per-role findings are driven directly over planted events; the two verbs through the real CLI against a fixture store. The Stop wiring, over a real landing record and two trees, is pinned in .claude/hooks/stop/test-landing-wiring.py (`handover_cases`). Every fire case has a control that differs in one fact.
"""

from __future__ import annotations

import json
import re

import pytest

from rediacc_hooks.tests import wlfix

H = wlfix.import_wl("wl_handover")
ME = wlfix.ME


def opened(hid, kind="stuck", check="Quality / Pytest (3/3)", at="2026-11-21T10:00:00Z"):
    return {
        "ev": "handover",
        "id": hid,
        "at": at,
        "by": "cafe1234",
        "kind": kind,
        "check": check,
        "evidence": "rounds 4, 5, 6 of agent/ledgers/landing-rounds.jsonl",
    }


def answered(hid, answer, at="2026-11-21T11:00:00Z"):
    return {"ev": "handover", "id": hid, "at": at, "by": ME, "answer": answer}


def findings(events, role, landed=None):
    return H.stop_findings(H.fold(None, events=events), role, landed=landed, me8=ME)


def keys(got):
    return [(k, b) for k, b, _t in got]


# ---- the per-role verdicts ---------------------------------------------------------------------


def test_a_stuck_handover_blocks_the_development_stop_and_not_the_landing_stop():
    events = [opened("aaaa0001")]
    assert keys(findings(events, H.ROLE_DEVELOPMENT)) == [(H.KEY_OPEN, True)]
    text = findings(events, H.ROLE_DEVELOPMENT)[0][2]
    assert "HANDOVER #aaaa0001" in text
    assert "--handover-answer %s aaaa0001" % ME in text
    assert "worktree lease --tree landing" in text
    assert "Handover: #aaaa0001" in text
    # Control: the landing tree owes nothing for an unanswered handover.
    assert findings(events, H.ROLE_LANDING) == []
    # Control: a checkout with no role reads nothing.
    assert findings(events, "") == []


def test_a_churn_handover_blocks_and_names_keep_change_undo():
    got = findings([opened("aaaa0002", kind="churn")], H.ROLE_DEVELOPMENT)
    assert keys(got) == [(H.KEY_OPEN, True)]
    assert "keep, change or undo" in got[0][2]


def test_an_answer_with_a_lease_moves_the_block_to_the_landing_stop():
    events = [opened("aaaa0001"), answered("aaaa0001", "lease:fix-ci-1")]
    assert findings(events, H.ROLE_DEVELOPMENT) == []
    got = findings(events, H.ROLE_LANDING, landed=lambda _l: False)
    assert keys(got) == [(H.KEY_LAND, True)]
    assert "./run.sh worktree land fix-ci-1" in got[0][2]
    # An unreadable lease (None) is not a landed one: still blocks.
    assert keys(findings(events, H.ROLE_LANDING, landed=lambda _l: None)) == [(H.KEY_LAND, True)]


def test_a_landed_lease_clears_both_trees():
    events = [opened("aaaa0001"), answered("aaaa0001", "lease:fix-ci-1")]
    seen = []

    def landed(lease):
        seen.append(lease)
        return True

    assert findings(events, H.ROLE_LANDING, landed=landed) == []
    assert seen == ["fix-ci-1"], "the landed reading is asked about the answered lease"
    assert findings(events, H.ROLE_DEVELOPMENT) == []


@pytest.mark.parametrize("answer", ["keep", "change", "undo", "done"])
def test_a_closing_answer_clears_both_trees(answer):
    events = [opened("aaaa0001"), answered("aaaa0001", answer)]
    assert findings(events, H.ROLE_DEVELOPMENT) == []
    assert findings(events, H.ROLE_LANDING, landed=lambda _l: False) == []


def test_done_after_a_lease_answer_clears_the_landing_block():
    events = [
        opened("aaaa0001"),
        answered("aaaa0001", "lease:fix-ci-1"),
        answered("aaaa0001", "done", at="2026-11-21T12:00:00Z"),
    ]
    assert findings(events, H.ROLE_LANDING, landed=lambda _l: False) == []


def test_a_lesson_handover_only_advises():
    got = findings(
        [opened("aaaa0003", kind="lesson", check="Quality / Static")], H.ROLE_DEVELOPMENT
    )
    assert keys(got) == [(H.KEY_LESSON, False)]
    assert "ruling 7" in got[0][2]


def test_the_fold_drops_an_unknown_kind_an_orphan_answer_and_a_bad_answer():
    events = [
        dict(opened("aaaa0004"), kind="panic"),
        answered("bbbb0001", "done"),
        opened("aaaa0005"),
        answered("aaaa0005", "lease:"),
    ]
    got = H.fold(None, events=events)
    assert sorted(got) == ["aaaa0005"]
    assert got["aaaa0005"]["answer"] == ""


def test_valid_answers():
    for good in ("keep", "change", "undo", "done", "lease:fix-ci-1", "lease:a.b_c-9"):
        assert H.valid_answer(good), good
    for bad in ("", "lease:", "lease:../x", "maybe", "lease:a b"):
        assert not H.valid_answer(bad), bad


# ---- the verbs, through the real CLI -----------------------------------------------------------


@pytest.fixture
def world(wl):
    wl.setup()
    return wl


def handover_events(fix):
    return [
        json.loads(line)
        for line in fix.wl_events().splitlines()
        if line.strip() and '"handover"' in line
    ]


def test_the_verbs_append_open_and_answer_events(world):
    got = world.cli("--handover", ME, "stuck", "Quality / Pytest (3/3)", "rounds", "4,", "5,", "6")
    assert got.rc == 0, got.err
    m = re.search(r"handover #([0-9a-f]{8}) recorded", got.out)
    assert m, got.out
    hid = m.group(1)
    rows = handover_events(world)
    assert [(r["kind"], r["check"], r["evidence"]) for r in rows] == [
        ("stuck", "Quality / Pytest (3/3)", "rounds 4, 5, 6")
    ]
    ans = world.cli("--handover-answer", ME, hid, "lease:fix-ci-1")
    assert ans.rc == 0, ans.err
    assert "answered: lease:fix-ci-1" in ans.out
    assert handover_events(world)[-1]["answer"] == "lease:fix-ci-1"


def test_the_verbs_refuse_a_bad_kind_a_bad_answer_and_an_unknown_id(world):
    assert world.cli("--handover", ME, "panic", "x", "y").rc == 2
    assert world.cli("--handover", ME, "stuck", "only-a-check").rc == 2
    got = world.cli("--handover", ME, "lesson", "Quality / Static", "a CI-only failure")
    assert got.rc == 0, got.err
    m = re.search(r"handover #([0-9a-f]{8})", got.out)
    assert m, got.out
    hid = m.group(1)
    assert world.cli("--handover-answer", ME, hid, "maybe").rc == 2
    assert world.cli("--handover-answer", ME, "ffff0000", "done").rc == 2
    # Control: the same answer verb with a valid answer and id is accepted.
    assert world.cli("--handover-answer", ME, hid, "done").rc == 0
    assert len(handover_events(world)) == 2

"""`wl_planrec.done_commit` must not re-derive a plan row's identity for every box it is asked about.

The plan-implementation gate asks `done_commit` once per judged box against every ledger commit; re-deriving `plan_identity` for every row of every ledger on every ask made that quadratic, and one test of the gate took 380 s (Pytest 3/5 timeout, 2026-11-16). The bound here counts calls, never wall time."""

import random

import wl_planrec

COMMITS = 12
PLANS = 40
BOXES = 25


def _history():
    history = []
    for c in range(COMMITS):
        plans = {
            "agent/plans/PLAN-p%d.md" % p: {
                "done_sigs": ["s%d" % b for b in range(BOXES) if c >= 2]
            }
            for p in range(PLANS)
        }
        history.append(("c%d" % c, {"plans": plans}))
    return history


def _count_identity_calls(monkeypatch):
    calls = []
    real = wl_planrec.plan_identity

    def counting(rel):
        calls.append(rel)
        return real(rel)

    monkeypatch.setattr(wl_planrec, "plan_identity", counting)
    return calls


def test_asking_about_every_box_derives_each_rows_identity_once(monkeypatch):
    history = _history()
    calls = _count_identity_calls(monkeypatch)
    moved = "agent/plans/_done/PLAN-p7.md"
    found = [wl_planrec.done_commit(history, moved, "s%d" % b) for b in range(BOXES)]
    assert found == ["c2"] * BOXES
    # One derivation per row per ledger (the index build) plus one per ask; the quadratic form made BOXES * COMMITS * PLANS.
    assert len(calls) <= COMMITS * PLANS + BOXES * COMMITS, len(calls)


def test_control_the_answers_still_distinguish_an_unattested_sig_and_a_reopened_box():
    history = _history()
    moved = "agent/plans/_done/PLAN-p7.md"
    assert wl_planrec.done_commit(history, moved, "nope") == ""
    reopened = [*history, ("c99", {"plans": {"agent/plans/PLAN-p7.md": {"done_sigs": []}}})]
    assert wl_planrec.done_commit(reopened, moved, "s1") == ""


def _reference_done_commit(history, rel, sig):
    """The per-box walk done_commit used before its per-plan index, kept as the oracle."""
    start = ""
    for commit, doc in history:
        start = (start or commit) if wl_planrec.attested_by_identity(doc, rel, sig) else ""
    return start


def test_the_per_plan_index_matches_the_per_box_walk_on_random_histories():
    """Ticks, reopens and re-ticks, a plan moved into _done/ part way (rows under the old path only before the move), and a newest ledger that drops a box: every (plan, sig) answer equals the old walk."""
    rng = random.Random(20261120)
    live, moved = "agent/plans/PLAN-x.md", "agent/plans/_done/PLAN-x.md"
    for trial in range(30):
        history = []
        for c in range(rng.randint(1, 25)):
            here = moved if c > 12 and trial % 2 else live
            sigs = sorted({"s%d" % rng.randint(0, 9) for _ in range(rng.randint(0, 8))})
            plans = {here: {"done_sigs": sigs}}
            if rng.random() < 0.2:
                plans["agent/plans/PLAN-other.md"] = {"done_sigs": ["s1"]}
            history.append(("c%d" % c, {"plans": plans}))
        for rel in (live, moved, "agent/plans/PLAN-other.md"):
            for b in range(10):
                sig = "s%d" % b
                assert wl_planrec.done_commit(history, rel, sig) == _reference_done_commit(
                    history, rel, sig
                ), (
                    trial,
                    rel,
                    sig,
                )

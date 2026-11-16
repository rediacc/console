"""`wl_planrec.done_commit` must not re-derive a plan row's identity for every box it is asked about.

The plan-implementation gate asks `done_commit` once per judged box against every ledger commit; re-deriving `plan_identity` for every row of every ledger on every ask made that quadratic, and one test of the gate took 380 s (Pytest 3/5 timeout, 2026-11-16). The bound here counts calls, never wall time."""

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

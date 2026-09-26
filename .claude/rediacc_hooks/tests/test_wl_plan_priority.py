"""Plan priority order across every "next item" picker (agent/plans/PLAN-plan-priority-concurrency.md sections 2 and 8, T7/T10).

Operator order, 2026-09-25, section X: "Rank the work, not just order it. Depends-On: says what must come first. It doesn't say which of two ready plans matters more. That's why the stop hook kept naming whatever item was oldest in the queue." The order is dependencies, then operator Priority, then AI Priority, then age (ruling D1: literal lexicographic, so an operator P3 beats an AI P0).

EVERY PICKER IS ASKED THE SAME QUESTION: the guide (`guided_slice`, through `--list --open`), the open list (`classify_items`, through the Stop hook's idle-stall rows), the queue (`queue_pick` inside `wl_roster.roster`) and the backlog nomination (`wl_backlog.next_plan`). Each ordering case has a control that flips the answer by one planted fact, and the mutation controls at the end run a PRIVATE COPY of the stop directory with one term of the order removed, so each
case is shown to depend on the rule it names rather than on fixture order.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import (
    VERDICT_SNIPPET,
    linked,
    plant_item,
    plant_lease,
    stamp,
    until,
    verdict,
    write_plan,
)
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# One subprocess answers every picker at once, against the fixture store and plan tree, exactly as the hook would fold them.
PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S, wl_checks as K, wl_planorder as PO, wl_backlog as B, wl_planconc as X
ev = json.loads(sys.stdin.read())
start = C.project_start(ev)
root = C.project_root(start)
wl = C.worklist_for(start)
fold = S.load(wl, sync=True)
ctx, problem = PO.context(root)
openl = S.classify_items(fold, ev["session_id"], order_key=PO.item_key(ctx))[0]
empty = type("Empty", (), {"items": []})()
cand, reason, _stats = B.next_plan(root, K.plan_records(root), empty, ev["session_id"], K.plan_owner, wl, {})
live = X.live_plans(ev["cwd"], ev["session_id"], fold)
mirror = PO.holders([], fold, ev["session_id"])
print(json.dumps({
    "open": openl,
    "problem": problem,
    "next_plan": cand["rel"] if cand else reason,
    "why": (cand or {}).get("why") or [],
    "live_plans": live,
    "holders": mirror,
}))
"""


def probe(fix, stop_dir=None) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(stop_dir or wlfix.STOP_DIR)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, "the probe failed: %s" % proc.stderr[-1200:]
    return json.loads(proc.stdout)


def order_of(text: str, words) -> list[str]:
    """The words in the order they first appear in `text`; a missing word fails the case loudly rather than sorting to the end."""
    missing = [w for w in words if w not in text]
    assert not missing, "not in the output at all: %s\n%s" % (missing, text[:1500])
    return sorted(words, key=text.index)


def guide(fix) -> str:
    got = fix.cli("--list", "--open", wlfix.ME)
    assert got.rc == 0, got.err[:600]
    return got.out


def mutated_stop(fix, filename: str, old: str, new: str):
    """A private copy of the stop and context directories with ONE line of `filename` changed, driven by both the CLI and the probe. The copy asserts the line occurs exactly once, so a drifted control fails as a broken fixture instead of passing vacuously."""
    hooks = fix.base / "hooks"
    if not (hooks / "stop").exists():
        shutil.copytree(
            wlfix.STOP_DIR, hooks / "stop", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copytree(
            wlfix.STOP_DIR.parent / "context",
            hooks / "context",
            ignore=shutil.ignore_patterns("__pycache__", "state"),
        )
        ci = hooks.parents[1] / ".ci"
        if not ci.exists():
            ci.symlink_to(wlfix.STOP_DIR.parents[2] / ".ci")
    path = hooks / "stop" / filename
    src = path.read_text(encoding="utf-8")
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN: %r occurs %d times in %s" % (
        old,
        src.count(old),
        filename,
    )
    path.write_text(src.replace(old, new), encoding="utf-8")
    fix.hook = hooks / "stop" / "worklist.py"
    return hooks / "stop"


# ---- o1: a dependency beats priority -------------------------------------------------------------


def dependency_world(fix, y_status: str = "in-progress", with_z: bool = False) -> None:
    """X is `P0 (operator)` and depends on Y, a P3; X's item is the OLDEST, so age alone would name it first."""
    x = write_plan(fix, "x", priority="P0 (operator) -- the operator's first", dep="PLAN-y.md")
    y = write_plan(fix, "y", status=y_status, priority="P3")
    plant_item(fix, "a0000001", linked(x, "ITEM_X"), age_min=50)
    plant_item(fix, "a0000002", linked(y, "ITEM_Y"), age_min=10)
    if with_z:
        z = write_plan(fix, "z", priority="P1")
        plant_item(fix, "a0000003", linked(z, "ITEM_Z"), age_min=30)


def test_o1_a_dependency_comes_before_the_plan_that_needs_it(wl):  # noqa: F811
    dependency_world(wl)
    got = probe(wl)
    assert got["problem"] == "", got["problem"]
    assert order_of("\n".join(got["open"]), ["ITEM_X", "ITEM_Y"]) == ["ITEM_Y", "ITEM_X"], got[
        "open"
    ]
    assert order_of(guide(wl), ["ITEM_X", "ITEM_Y"]) == ["ITEM_Y", "ITEM_X"]


def test_o1c_control_with_the_dependency_finished_the_urgent_plan_leads(wl):  # noqa: F811
    dependency_world(wl, y_status="done")
    got = probe(wl)
    assert order_of("\n".join(got["open"]), ["ITEM_X", "ITEM_Y"]) == ["ITEM_X", "ITEM_Y"], got[
        "open"
    ]
    assert order_of(guide(wl), ["ITEM_X", "ITEM_Y"]) == ["ITEM_X", "ITEM_Y"]


def test_o1i_inheritance_the_blocker_takes_its_dependents_rank_past_an_unrelated_p1(wl):  # noqa: F811
    """Without inheritance a P0 plan blocked on a P3 waits behind every unrelated P1 (decision D6)."""
    dependency_world(wl, with_z=True)
    got = probe(wl)
    words = ["ITEM_X", "ITEM_Y", "ITEM_Z"]
    assert order_of("\n".join(got["open"]), words) == ["ITEM_Y", "ITEM_Z", "ITEM_X"], got["open"]
    assert order_of(guide(wl), words) == ["ITEM_Y", "ITEM_Z", "ITEM_X"]


def test_o1s_the_stop_hooks_own_open_rows_carry_the_order(wl):  # noqa: F811
    """The wiring, not just the library: the idle-stall rows are `classify_items`' open list as run_stop computed it."""
    wl.brief_now()
    wl.hand_now()
    dependency_world(wl, with_z=True)
    wl.say("stopping here\n\n## Remaining\n- nothing")
    got = wl.run()
    assert "ITEM_X" in got.out, got.out[:1500]
    assert order_of(got.out, ["ITEM_X", "ITEM_Y", "ITEM_Z"]) == ["ITEM_Y", "ITEM_Z", "ITEM_X"]


# ---- o2: operator beats AI (ruling D1, literal) ---------------------------------------------------


def operator_world(fix, a_priority: str) -> None:
    a = write_plan(fix, "a", priority=a_priority)
    b = write_plan(fix, "b", priority="P0")
    plant_item(fix, "b0000001", linked(b, "ITEM_B"), age_min=50)
    plant_item(fix, "b0000002", linked(a, "ITEM_A"), age_min=10)


def test_o2_an_operator_p2_comes_before_an_ai_p0(wl):  # noqa: F811
    operator_world(wl, "P2 (operator)")
    got = probe(wl)
    assert order_of("\n".join(got["open"]), ["ITEM_A", "ITEM_B"]) == ["ITEM_A", "ITEM_B"], got[
        "open"
    ]
    assert order_of(guide(wl), ["ITEM_A", "ITEM_B"]) == ["ITEM_A", "ITEM_B"]


def test_o2c_control_both_ai_the_more_urgent_level_leads(wl):  # noqa: F811
    operator_world(wl, "P2")
    got = probe(wl)
    assert order_of("\n".join(got["open"]), ["ITEM_A", "ITEM_B"]) == ["ITEM_B", "ITEM_A"], got[
        "open"
    ]


# ---- o3: age breaks a tie -------------------------------------------------------------------------


def test_o3_equal_rank_the_older_item_leads_and_the_queue_uses_its_lease_age(wl):  # noqa: F811
    p = write_plan(wl, "p", priority="P1")
    plant_item(wl, "c0000001", linked(p, "ITEM_NEW"), age_min=5)
    plant_item(wl, "c0000002", linked(p, "ITEM_OLD"), age_min=40)
    got = probe(wl)
    assert order_of("\n".join(got["open"]), ["ITEM_NEW", "ITEM_OLD"]) == ["ITEM_OLD", "ITEM_NEW"]
    # The queue: the OLDER queue lease leads, whatever the items' own ages.
    plant_lease(wl, "c0000003", "queue", lease_age_min=5, text=linked(p, "Q_NEW"))
    plant_lease(wl, "c0000004", "queue", lease_age_min=40, text=linked(p, "Q_OLD"))
    v = verdict(wl)
    assert v["queue_start"][:2] == ["c0000004", "c0000003"], v["queue_start"]


# ---- o4: an unlinked item is an AI P2 (decision D3) ----------------------------------------------


def test_o4_an_unlinked_item_sits_between_a_p1_plan_and_a_p3_plan(wl):  # noqa: F811
    hi = write_plan(wl, "hi", priority="P1")
    lo = write_plan(wl, "lo", priority="P3")
    plant_item(wl, "d0000001", linked(lo, "ITEM_LO"), age_min=50)
    plant_item(wl, "d0000002", "(deadbeef) ITEM_FREE with no plan", age_min=40)
    plant_item(wl, "d0000003", linked(hi, "ITEM_HI"), age_min=10)
    got = probe(wl)
    words = ["ITEM_LO", "ITEM_FREE", "ITEM_HI"]
    assert order_of("\n".join(got["open"]), words) == ["ITEM_HI", "ITEM_FREE", "ITEM_LO"]
    # The queue reads the same rank.
    plant_lease(wl, "d0000004", "queue", lease_age_min=50, text=linked(lo, "Q_LO"))
    plant_lease(wl, "d0000005", "queue", lease_age_min=40, text="(deadbeef) Q_FREE no plan")
    plant_lease(wl, "d0000006", "queue", lease_age_min=10, text=linked(hi, "Q_HI"))
    v = verdict(wl)
    assert v["queue_start"] == ["d0000006", "d0000005", "d0000004"], v["queue_start"]


# ---- o5: the guide shows the rank, and never reorders a band --------------------------------------


def test_o5_the_guide_tags_linked_rows_and_a_dead_lease_still_leads(wl):  # noqa: F811
    op = write_plan(wl, "op", priority="P1 (operator)")
    low = write_plan(wl, "low", priority="P3")
    plant_item(wl, "e0000001", linked(op, "ITEM_OP"), age_min=5)
    plant_item(wl, "e0000002", linked(low, "ITEM_LOW"), age_min=50)
    plant_item(wl, "e0000003", "(deadbeef) ITEM_PLAIN unlinked", age_min=60)
    out = guide(wl)
    assert "#e0000001 [P1 op] (upd" in out, out[:1500]
    assert "#e0000002 [P3] (upd" in out, out[:1500]
    assert "#e0000003 (upd" in out, out[:1500]
    # The printed verbs keep the bare id, so a copied command still resolves.
    assert "--tick deadbeef e0000001 '<evidence>'" in out, out[:1500]
    # A LEASE DEAD row (band 0) on the P3 plan leads a fresh in-flight row (band 3) on the operator's P1: obligations first.
    plant_lease(wl, "e0000004", "a9999999999999999", lease_age_min=5, text=linked(op, "LIVE_OP"))
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "e0000005",
                    "at": stamp(600),
                    "by": wlfix.ME,
                    "s": ">",
                    "o": wlfix.ME,
                    "t": linked(low, "DEAD_LOW") + " until:%s worker:a1" % until(-300),
                }
            )
            + "\n"
        )
    out = guide(wl)
    assert "LEASE DEAD" in out, out[:2000]
    assert order_of(out, ["DEAD_LOW", "LIVE_OP"]) == ["DEAD_LOW", "LIVE_OP"], out[:2000]


def test_o5b_a_blocked_plan_is_tagged_and_an_unreadable_order_says_so(wl):  # noqa: F811
    dependency_world(wl)
    out = guide(wl)
    assert "#a0000001 [P0 op, dep-blocked]" in out, out[:1500]
    assert "plan priority order unavailable" not in out, out[:1500]


# ---- the backlog nomination -----------------------------------------------------------------------


def test_b1_the_backlog_nominates_by_rank_before_mtime(wl):  # noqa: F811
    """The NEWEST plan used to win outright; an operator P1 written earlier now does, and the WHY line says so."""
    older = write_plan(wl, "older", status="approved", priority="P1 (operator) -- the ruling")
    newer = write_plan(wl, "newer", status="approved", priority="P3")
    base = wl.proj / "agent" / "plans"
    now = time.time()
    os.utime(base / older, (now - 600, now - 600))
    os.utime(base / newer, (now, now))
    got = probe(wl)
    assert got["next_plan"] == "agent/plans/%s" % older, got
    assert got["why"][0].startswith("Priority P1 (operator) -- the ruling; then NEWEST first"), got[
        "why"
    ]


def test_b1c_control_without_a_priority_the_newest_still_wins(wl):  # noqa: F811
    older = write_plan(wl, "older", status="approved")
    newer = write_plan(wl, "newer", status="approved")
    base = wl.proj / "agent" / "plans"
    now = time.time()
    os.utime(base / older, (now - 600, now - 600))
    os.utime(base / newer, (now, now))
    got = probe(wl)
    assert got["next_plan"] == "agent/plans/%s" % newer, got
    assert "No `Priority:` yet" in got["why"][0], got["why"]


# ---- the roster's live plans agree with the spawn guard's ------------------------------------------


def test_h1_the_rosters_lease_half_matches_live_plans(wl):  # noqa: F811
    """`wl_planorder.holders` restates `wl_planconc.live_plans`' lease half for the roster; on one fold the two must agree, or the guard and the queue would disagree about who holds a plan."""
    e = write_plan(wl, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(wl, "f")
    plant_lease(
        wl, "f1000001", "a7777777777777777", owner="cafe1234", text=linked(e, "PEER_E", "cafe1234")
    )
    plant_lease(
        wl, "f1000002", "a6666666666666666", owner="cafe1234", text=linked(f, "PEER_F", "cafe1234")
    )
    plant_lease(wl, "f1000003", "queue", owner="cafe1234", text=linked(f, "PEER_Q", "cafe1234"))
    got = probe(wl)
    assert got["live_plans"] == got["holders"], got
    assert set(got["holders"]) == {e, f}, got["holders"]


# ---- mutation controls: each case above depends on the term it names --------------------------------


def test_m1_without_the_blocked_term_o1_fails(wl):  # noqa: F811
    dependency_world(wl)
    stop = mutated_stop(
        wl,
        "wl_planconc.py",
        "    return (*ctx.plan_key(rel), age)\n",
        "    return (0, *ctx.plan_key(rel)[1:], age)\n",
    )
    got = probe(wl, stop)
    assert order_of("\n".join(got["open"]), ["ITEM_X", "ITEM_Y"]) == ["ITEM_X", "ITEM_Y"], (
        "m1: o1 does not depend on the blocked term: %s" % got["open"]
    )


def test_m2_with_the_op_and_ai_terms_swapped_o2_fails(wl):  # noqa: F811
    operator_world(wl, "P2 (operator)")
    stop = mutated_stop(
        wl,
        "wl_planconc.py",
        "        return (self._blocked[rel], *self._ranks[rel])\n",
        "        return (self._blocked[rel], *self._ranks[rel][::-1])\n",
    )
    got = probe(wl, stop)
    assert order_of("\n".join(got["open"]), ["ITEM_A", "ITEM_B"]) == ["ITEM_B", "ITEM_A"], (
        "m2: o2 does not depend on the op-before-ai order: %s" % got["open"]
    )


def test_m3_without_the_guides_rank_term_the_guide_falls_back_to_fold_order(wl):  # noqa: F811
    dependency_world(wl)
    mutated_stop(
        wl,
        "wl_checks.py",
        "    rows.sort(key=lambda r: (r[0], r[1]))\n",
        "    rows.sort(key=lambda r: r[0])\n",
    )
    assert order_of(guide(wl), ["ITEM_X", "ITEM_Y"]) == ["ITEM_X", "ITEM_Y"], (
        "m3: the guide's order does not depend on its rank term"
    )


def test_m4_without_the_stops_order_key_its_open_rows_fall_back_to_fold_order(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    dependency_world(wl, with_z=True)
    mutated_stop(
        wl,
        "wl_checks.py",
        "        fold, session_id, live_worker_ids=_live_worker_ids, order_key=_order_key\n    )\n    # THE HOOK RENEWS",
        "        fold, session_id, live_worker_ids=_live_worker_ids\n    )\n    # THE HOOK RENEWS",
    )
    wl.say("stopping here\n\n## Remaining\n- nothing")
    got = wl.run()
    assert order_of(got.out, ["ITEM_X", "ITEM_Y", "ITEM_Z"]) == ["ITEM_X", "ITEM_Z", "ITEM_Y"], (
        "m4: o1s does not depend on run_stop passing the order key"
    )


def test_m5_without_the_queues_rank_the_oldest_lease_leads_again(wl):  # noqa: F811
    hi = write_plan(wl, "hi", priority="P1")
    lo = write_plan(wl, "lo", priority="P3")
    plant_lease(wl, "d0000004", "queue", lease_age_min=50, text=linked(lo, "Q_LO"))
    plant_lease(wl, "d0000006", "queue", lease_age_min=10, text=linked(hi, "Q_HI"))
    stop = mutated_stop(
        wl,
        "wl_roster.py",
        "        order_key = PO.item_key(order_ctx, age=queue_order)\n",
        "        order_key = queue_order\n",
    )
    proc = subprocess.run(
        [sys.executable, "-c", VERDICT_SNIPPET, str(stop)],
        input=wl.event(),
        capture_output=True,
        text=True,
        env=wl.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    got = json.loads(proc.stdout)
    assert got["queue_start"] == ["d0000004", "d0000006"], (
        "m5: o4's queue case does not depend on the roster's rank: %s" % got["queue_start"]
    )

"""The live PR's item scope inside `classify_items` and the guide (agent/plans/PLAN-stop-hook-one-plan-scope.md, SC4, Design 2).

`classify_items(..., in_scope=pred)` sends a plain open item of this session that fails the predicate to a fifth return value, `queued`, instead of the open list, so every consumer of the open list is scoped by construction. A dead claim (a fail-closed lease, a `worker:lead` item with nothing live) is a loop duty and stays open whatever the predicate says. `in_scope=None` is today's behaviour.

The predicate here is built the way production builds it: the union of `wl_epic.plan_epics` over the PR's plan set, prerequisites included (ruling 7). The set itself comes from `wl_prscope.loop_state` (SC2); these cases plant it directly so they test the scoping, not the resolver.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import plant_item, stamp, write_plan
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S, wl_epic as E, wl_checks as K
ev = json.loads(sys.stdin.read())
plans = json.loads(sys.argv[2])
start = C.project_start(ev)
root = C.project_root(start)
wl = C.worklist_for(start)
fold = S.load(wl, sync=True)
scope = set()
for rel in plans or []:
    scope |= E.plan_epics(rel)
pred = None if plans is None else (lambda rec: rec["id"] in scope)
got = S.classify_items(fold, ev["session_id"], in_scope=pred)
base = S.classify_items(S.load(wl, sync=True), ev["session_id"])
guide = K.guided_slice(S.load(wl, sync=True), ev["session_id"], me=ev["session_id"][:8], root=root, in_scope=pred)
print(json.dumps({
    "n": len(got),
    "open": got[0],
    "deferred": [r["id"] for r in got[2]],
    "in_flight": [r["id"] for r in got[3]],
    "queued": [r["id"] for r in got[4]],
    "base_open": base[0],
    "base_queued": [r["id"] for r in base[4]],
    "guide": guide,
}))
"""


def probe(fix, plans) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(wlfix.STOP_DIR), json.dumps(plans)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, "the probe failed: %s" % proc.stderr[-1200:]
    return json.loads(proc.stdout)


def epic_for(fix, plan: str, *items: str) -> str:
    got = fix.cli("--epic", wlfix.ME, "new", "--plan", "agent/plans/%s" % plan, "epic of", plan)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"epic #([0-9a-f]+)", got.out)
    assert found, got.out
    eid = found.group(1)
    if items:
        assert fix.cli("--epic", wlfix.ME, "add", eid, *items).rc == 0
    return eid


def plant_dead_lease(fix, item_id: str, worker: str) -> None:
    """An item whose lease expired two hours ago on a worker nothing runs."""
    past = stamp(120)[:16] + "Z"
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": item_id,
                    "at": stamp(200),
                    "by": wlfix.ME,
                    "s": " ",
                    "o": wlfix.ME,
                    "t": "(deadbeef) dead lease %s" % item_id,
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": item_id,
                    "at": stamp(180),
                    "by": wlfix.ME,
                    "until": past,
                    "worker": worker,
                    "note": "",
                    "worker_verified": True,
                }
            )
            + "\n"
        )


def world(fix):
    """PR plan A, its prerequisite B, an unrelated plan C, and one item each plus one in no epic."""
    pr = write_plan(fix, "pr-own")
    pre = write_plan(fix, "pr-prereq")
    other = write_plan(fix, "unrelated")
    plant_item(fix, "aaaa0001", "(deadbeef) in the PR plan's epic")
    plant_item(fix, "bbbb0002", "(deadbeef) in the prerequisite's epic")
    plant_item(fix, "cccc0003", "(deadbeef) in an unrelated plan's epic")
    plant_item(fix, "dddd0004", "(deadbeef) in no epic at all")
    epic_for(fix, pr, "aaaa0001")
    epic_for(fix, pre, "bbbb0002")
    epic_for(fix, other, "cccc0003")
    return ["agent/plans/%s" % pr, "agent/plans/%s" % pre]


def joined(rows) -> str:
    return "\n".join(rows)


def test_classify_scope_pr_plan_and_prerequisite_items_stay_open(wl):  # noqa: F811
    got = probe(wl, world(wl))
    assert got["n"] == 5, "classify_items must return five values: %s" % got["n"]
    text = joined(got["open"])
    assert "in the PR plan's epic" in text, got
    assert "in the prerequisite's epic" in text, "ruling 7: a prerequisite's items block: %s" % got


def test_classify_scope_unrelated_and_epicless_items_are_queued(wl):  # noqa: F811
    got = probe(wl, world(wl))
    assert set(got["queued"]) == {"cccc0003", "dddd0004"}, got
    text = joined(got["open"])
    assert "unrelated plan's epic" not in text, got
    assert "no epic at all" not in text, got


def test_classify_scope_dead_lease_outside_the_epic_stays_open(wl):  # noqa: F811
    plans = world(wl)
    plant_dead_lease(wl, "eeee0005", "bdead0001")
    plant_dead_lease(wl, "ffff0006", "lead")
    got = probe(wl, plans)
    text = joined(got["open"])
    assert "eeee0005" in text, "a fail-closed lease is a loop duty, never queued: %s" % got
    assert "ffff0006" in text, "a worker:lead item with nothing live stays open: %s" % got
    assert "eeee0005" not in got["queued"], got
    assert "ffff0006" not in got["queued"], got


def test_classify_scope_deferred_items_are_never_queued(wl):  # noqa: F811
    plans = world(wl)
    defer = "q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers"
    assert wl.cli("--defer", wlfix.ME, "dddd0004", *defer.split()).rc == 0
    got = probe(wl, plans)
    assert "dddd0004" in got["deferred"], got
    assert "dddd0004" not in got["queued"], got


def test_classify_scope_none_equals_today(wl):  # noqa: F811
    """CONTROL: no predicate is today's result, every open item in `open_items` and nothing queued."""
    world(wl)
    got = probe(wl, None)
    assert got["open"] == got["base_open"], got
    assert got["queued"] == [], got
    assert got["base_queued"] == [], got
    assert len(got["open"]) == 4, got


def test_classify_scope_guide_lists_in_scope_items_only(wl):  # noqa: F811
    got = probe(wl, world(wl))
    guide = got["guide"]
    assert "#aaaa0001" in guide, guide
    assert "#bbbb0002" in guide, guide
    assert "#cccc0003" not in guide, guide
    assert "#dddd0004" not in guide, guide
    # CONTROL: with no predicate the guide lists all four.
    full = probe(wl, None)["guide"]
    for rid in ("aaaa0001", "bbbb0002", "cccc0003", "dddd0004"):
        assert "#%s" % rid in full, full

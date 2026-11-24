"""Armed actions, finished-worker stand-downs (agent/plans/PLAN-armed-actions.md box AA4).

The roster covers a finished worker's item with `armed:<aid>` only while the item's arm covers it AND the worker's final report is captured; the 45/90/120 ladder skips an item whose arm covers it. Each branch has a control differing by one planted fact: no report, an expired arm, no arm.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import W1, mk_sub, plant_lease, stamp, verdict
from rediacc_hooks.tests.test_wl_stuckshell import TICK_BODY, plant_report

AID = "0123abcd"

LADDER_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S, wl_liveness as L
ev = json.loads(sys.stdin.read())
wl = C.worklist_for(C.project_start(ev))
fold = S.load(wl, sync=True)
pings, inv, res, gones, idles, _ch = L.ladder(fold, ev["session_id"], ev, {})
print(json.dumps({"pings": pings, "inv": inv, "res": res, "gones": gones, "idles": idles}))
"""


def plant_arm(
    fix, item_id: str, exp_minutes: float = 600, verdict_: str = "", ago: float = 2
) -> None:
    """One `arm` event on `item_id` (and its latch when `verdict_` is set), written straight into the store.

    The fold orders events by their `at`, so `ago` (minutes) must be later than the item's own add and lease events or the arm is dropped as naming an unknown item."""
    rows = [
        {
            "ev": "arm",
            "id": item_id,
            "at": stamp(ago),
            "by": wlfix.ME,
            "aid": AID,
            "when": ["TICKED:#other"],
            "run": "agent/x/armed/%s.md" % item_id,
            "cmd": "",
            "sha": "",
            "lease": "",
            "exp": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + exp_minutes * 60)),
        }
    ]
    if verdict_:
        rows.append(
            {
                "ev": "armfire",
                "id": item_id,
                "at": stamp(ago - 0.05),
                "by": wlfix.ME,
                "aid": AID,
                "v": verdict_,
                "why": "fixture",
            }
        )
    with fix.events.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def finished_writer_item(fix, item_id: str = "arm1") -> None:
    mk_sub(fix, W1, "general-purpose", 30, last="end_turn", running=False)
    plant_lease(fix, item_id, W1)


def ladder(fix) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", LADDER_SNIPPET, str(wlfix.STOP_DIR)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)


# ---- roster ----


def test_a_reported_finished_writer_with_a_live_arm_is_covered_not_dead(wl):
    finished_writer_item(wl)
    plant_arm(wl, "arm1")
    plant_report(wl, W1, 20, TICK_BODY)
    v = verdict(wl)
    assert v["leased_dead"] == [], v["leased_dead"]
    assert ["arm1", W1, "armed:" + AID] in [list(c) for c in v["covered"]], v["covered"]
    assert "armed:" + AID not in v["verified"], v["verified"]


def test_the_same_writer_with_no_captured_report_is_leased_dead(wl):
    finished_writer_item(wl)
    plant_arm(wl, "arm1")
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["arm1"], v["leased_dead"]


def test_the_same_writer_with_an_expired_arm_is_leased_dead(wl):
    finished_writer_item(wl)
    plant_arm(wl, "arm1", exp_minutes=-5)
    plant_report(wl, W1, 20, TICK_BODY)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["arm1"], v["leased_dead"]


def test_the_same_writer_with_a_latched_void_arm_is_leased_dead(wl):
    finished_writer_item(wl)
    plant_arm(wl, "arm1", verdict_="void")
    plant_report(wl, W1, 20, TICK_BODY)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["arm1"], v["leased_dead"]


def test_the_same_writer_with_no_arm_and_a_report_is_leased_dead(wl):
    finished_writer_item(wl)
    plant_report(wl, W1, 20, TICK_BODY)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["arm1"], v["leased_dead"]


# ---- ladder ----


def shell_lease(fix, item_id: str, age_min: float) -> None:
    """A lease on an unverifiable worker (no `worker_verified`), backdated, so only the age ladder judges it."""
    with fix.events.open("a", encoding="utf-8") as fh:
        for ev in (
            {
                "ev": "add",
                "id": item_id,
                "at": stamp(age_min + 1),
                "by": wlfix.ME,
                "s": " ",
                "o": wlfix.ME,
                "t": "(%s) ladder fixture item" % wlfix.ME,
            },
            {
                "ev": "lease",
                "id": item_id,
                "at": stamp(age_min),
                "by": wlfix.ME,
                "until": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + 3600)),
                "worker": "namedmate",
                "note": "",
                "worker_verified": False,
            },
        ):
            fh.write(json.dumps(ev) + "\n")


def test_an_unarmed_item_at_46_minutes_still_pings(wl):
    shell_lease(wl, "lad1", 46)
    got = ladder(wl)
    assert any("#lad1" in p for p in got["pings"]), got


def test_an_armed_item_at_46_minutes_fires_no_rung(wl):
    shell_lease(wl, "lad1", 46)
    plant_arm(wl, "lad1", ago=45.8)
    got = ladder(wl)
    assert not any(got[k] for k in ("pings", "inv", "res", "gones", "idles")), got


def test_an_armed_item_with_an_expired_arm_at_46_minutes_pings_again(wl):
    shell_lease(wl, "lad1", 46)
    plant_arm(wl, "lad1", exp_minutes=-5, ago=45.8)
    got = ladder(wl)
    assert any("#lad1" in p for p in got["pings"]), got


def test_an_armed_item_at_125_minutes_fires_no_resolve(wl):
    shell_lease(wl, "lad1", 125)
    plant_arm(wl, "lad1", ago=124.8)
    got = ladder(wl)
    assert got["res"] == [], got
    assert got["inv"] == [], got

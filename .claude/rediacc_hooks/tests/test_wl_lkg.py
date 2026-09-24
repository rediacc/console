"""The last-known-good Stop hook (agent/plans/PLAN-stop-hook-continuity.md P2.5).

The live hook runs from the working tree, so a writer's half-finished edit used to be every session's Stop hook: a NameError inside `run_stop` blocked each stop with a traceback until the edit landed. These cases copy the stop directory, seed a snapshot with one clean stop, plant `undefined_name()` in the copy's `run_stop`, and stop again. The live tree is never touched.
"""

from __future__ import annotations

import json
import shutil

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PLANT = "def run_stop(event, event_ok, worklist, hook_file):\n"


def copied_hook(fix):
    """A private copy of the stop directory, outside any git repository, that the fixture drives instead of the live one."""
    target = fix.base / "hookcopy"
    shutil.copytree(wlfix.STOP_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
    fix.hook = target / "worklist.py"
    return target


def plant_crash(target) -> None:
    path = target / "wl_checks.py"
    src = path.read_text(encoding="utf-8")
    assert src.count(PLANT) == 1, "FIXTURE BROKEN: run_stop's signature moved"
    path.write_text(src.replace(PLANT, PLANT + "    undefined_name()\n"), encoding="utf-8")


def open_item_world(fix) -> None:
    fix.brief_now()
    fix.hand_now()
    fix.add_item("- [ ] (deadbeef) open thing")
    fix.say("working")


def test_k1_a_crashed_live_hook_is_answered_by_the_snapshot(wl):  # noqa: F811
    """CONTROL: before P2.5 this stop printed "Stop hook CRASHED" and none of the battery ran."""
    target = copied_hook(wl)
    open_item_world(wl)
    first = wl.run()
    assert first.decision == "block", first.out[:300]
    assert (wl.base / "tmp" / "claude-worklist" / ".lkg" / "current").is_file(), (
        "no snapshot was seeded"
    )
    plant_crash(target)
    wl.newturn()
    wl.say("working")
    got = wl.run()
    assert "Stop hook CRASHED" not in got.out, got.out[:600]
    reason = json.loads(got.out)["reason"]
    assert reason.startswith("live hook crashed (NameError at wl_checks.py:"), reason[:300]
    assert "last-known-good snapshot" in reason, reason[:300]
    assert "OPEN worklist item" in reason, "the snapshot's battery did not run: %s" % reason[:600]


def test_k1b_inverse_with_no_snapshot_and_no_git_the_crash_block_is_unchanged(wl):  # noqa: F811
    target = copied_hook(wl)
    plant_crash(target)
    open_item_world(wl)
    got = wl.run()
    assert "Stop hook CRASHED" in got.out, got.out[:600]
    assert "NameError" in got.out, got.out[:600]


def test_k1c_inverse_a_broken_snapshot_leaves_the_crash_block_unchanged(wl):  # noqa: F811
    target = copied_hook(wl)
    open_item_world(wl)
    wl.run()
    lkg = wl.base / "tmp" / "claude-worklist" / ".lkg"
    snap = lkg / (lkg / "current").read_text(encoding="utf-8").strip()
    plant_crash(snap)
    plant_crash(target)
    wl.newturn()
    wl.say("working")
    got = wl.run()
    assert "Stop hook CRASHED" in got.out, got.out[:600]

"""The stop-hook retro's inputs (agent/plans/PLAN-stop-hook-retro-20260924.md, section 8).

R.10: `.blocklog-<me8>.jsonl` carries one row per BLOCKED stop, with the key the block led with, every other outstanding key it named, and the judge's flags when the judge blocked. The first retro had to grep a 222 MB transcript to count blocks per key; the next one reads this file.

The retro-order cases (R.11 to R.13) belong in this module as well.
"""

from __future__ import annotations

import json

from rediacc_hooks.tests.test_wl_judge_fixset_scope import timeout_fix_world
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def blocklog_rows(fix) -> list[dict]:
    path = fix.stem(".blocklog-deadbeef.jsonl")
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_r10_a_battery_block_writes_one_row_naming_its_keys(wl):  # noqa: F811
    """CONTROL: before R.10 no block left a row."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.say("answer with no report section")
    got = wl.run()
    assert got.decision == "block", got.out[:300]
    rows = blocklog_rows(wl)
    assert len(rows) == 1, rows
    keys = {rows[0]["key"], *rows[0]["named"]}
    assert "open-items" in keys, rows[0]
    assert "no-remaining" in keys, rows[0]


def test_r10_inverse_an_allowed_stop_writes_no_row(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    got = wl.run()
    assert got.decision == "allow", got.out[:300]
    assert blocklog_rows(wl) == []


def test_r10_a_judge_block_carries_the_judge_flags(wl):  # noqa: F811
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    got = wl.runj()
    assert got.decision == "block", got.out[:300]
    rows = blocklog_rows(wl)
    judged = [r for r in rows if r["judge"]]
    assert judged, rows
    assert judged[-1]["judge"]["sweep"] is True, judged[-1]
    assert judged[-1]["judge"]["verdict"] == "continue", judged[-1]

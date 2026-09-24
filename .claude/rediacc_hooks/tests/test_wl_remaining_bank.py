"""A banked `## Remaining` report survives a world that moved only outside this session's items (agent/plans/PLAN-stop-hook-retro-20260924.md R.4).

The bank key was `state_world_sig`, which hashes the harness task statuses and HEAD. With a babysitter committing and background shells finishing, it moved nearly every turn, so a short progress reply was ordered to restate an unchanged report: 6 `no-remaining` blocks on 2026-09-24 and 45 across nine days. The key is now the owned items' structure alone.

The CONTROL flips a harness task and adds a commit and must not re-demand the report; the INVERSE ticks an owned item and must.
"""

from __future__ import annotations

import re

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# The demand's own words, present whether the stop quotes it in full or names it on one line.
DEMAND = "no '## Remaining' section"

REPORT = "progress\n\n## Remaining\n- #7 thing (pending)\n- the open item, in hand"


def banked_world(fix) -> str:
    """Two harness tasks (7 pending, 8 in progress), one open item of this session's, a fresh STATE.md and a git repo; the last message banks a Remaining report. Returns the item id."""
    fix.brief_now()
    fix.hand_now()
    fix.reg_repo()
    fix.task(7, "pending", "thing")
    fix.task(8, "in_progress", "shell watch")
    added = fix.cli("--add", "deadbeef", "(deadbeef) the open item")
    found = re.search(r"#([0-9a-f]+)", added.out)
    assert found, added.out[:200]
    fix.say(REPORT)
    got = fix.run()
    assert DEMAND not in got.out, "the banking stop itself demanded a report: %s" % got.out[:400]
    return found.group(1)


def test_r4_a_task_flip_and_a_commit_do_not_redemand_the_report(wl):  # noqa: F811
    """CONTROL: before R.4 both moved `st_sig`, and the short reply below drew `no-remaining`."""
    banked_world(wl)
    wl.task(8, "completed", "shell watch")
    wl.fixcommit("src.ts", "chore: a peer's commit")
    wl.newturn()
    wl.say("still on it, the watch finished")
    got = wl.run()
    assert DEMAND not in got.out, got.out[:1200]


def test_r4_inverse_ticking_an_owned_item_redemands_the_report(wl):  # noqa: F811
    item = banked_world(wl)
    ticked = wl.cli("--tick", "deadbeef", item, "landed, suite green, exit 0")
    assert ticked.rc == 0, ticked.err[:300]
    wl.newturn()
    wl.say("ticked it")
    got = wl.run()
    assert DEMAND in got.out, got.out[:1200]

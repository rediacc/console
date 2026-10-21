"""`wisdom-due`: near compaction the Stop hook orders /wisdom (operator 2026-10-21).

The operator asked by hand, at 935,224 of 967,000 tokens, for the session to hand its in-flight work to sub-agents before compaction, because nothing in the hook ever asked: the near-compaction duties were the effort tuner's request at 85% and the STATE.md demand in the late band (98%, 19,340 tokens of headroom on a 1M window). Each case drives the real Stop hook against a planted band state (ctx_budget.state_file under
CTX_BAND_STATE_DIR) at the `low` effort level the queue runs at, and each block case has its clearing twin.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import CONTINUE, saturated
from rediacc_hooks.tests.test_wl_judge_fixset_scope import capturing_judge

ME = wlfix.ME
NEEDLE = "run /wisdom now"
THRESHOLD = 967_000
DELEGATED = (
    "# STATE\n\nBranch 1020-1, three writers out.\n\n"
    "## Delegated\n- a1234567890abcdef #1a07399b owns start_backup_plane.py\n\n"
    "## Next action\nRead each report, commit by path.\n"
)
UNDELEGATED = "# STATE\n\nBranch 1020-1.\n\n## Next action\nKeep going on the plan.\n"


@pytest.fixture
def wl(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    fixture.settings(effort="low")
    return fixture


def band(fix, usage, epoch=1, written=None):
    """The band state band-notice saves, at `usage` of a 1M session's threshold; returns the env pointing the hook at it."""
    d = fix.base / "ctxband"
    d.mkdir(exist_ok=True)
    st = {"epoch": epoch, "band": 0, "usage": usage, "threshold": THRESHOLD}
    if written is not None:
        st["state_written_usage"] = written
    (d / ("%s.json" % ME)).write_text(json.dumps(st), encoding="utf-8")
    return {"CTX_BAND_STATE_DIR": str(d)}


def stop(fix, env, text="still working"):
    fix.say(text)
    return fix.run(env)


def test_w1_past_the_fraction_the_hook_orders_wisdom_at_effort_low(wl):
    wl.plant_state(UNDELEGATED)
    got = stop(wl, band(wl, 920_000))
    assert got.decision == "block", wl.why("w1", "block", got, NEEDLE)
    assert NEEDLE in got.out, got.out[:1500]
    assert "95% OF AUTO-COMPACT" in got.out, got.out[:600]
    assert "agent/%s/STATE.md" % ME in got.out


def test_w1_twin_below_the_fraction_says_nothing(wl):
    wl.plant_state(UNDELEGATED)
    got = stop(wl, band(wl, 880_000))  # 91%
    assert NEEDLE not in got.out, got.out[:1500]


def test_w2_a_delegated_rewrite_after_the_crossing_clears_it(wl):
    wl.plant_state(UNDELEGATED)
    env = band(wl, 920_000)
    assert NEEDLE in stop(wl, env).out
    time.sleep(0.05)
    wl.plant_state(DELEGATED)
    wl.newturn()
    got = stop(wl, env, "delegated; STATE.md rewritten")
    assert NEEDLE not in got.out, got.out[:1500]


def test_w2_twin_a_rewrite_without_the_delegated_section_does_not(wl):
    wl.plant_state(UNDELEGATED)
    env = band(wl, 920_000)
    assert NEEDLE in stop(wl, env).out
    time.sleep(0.05)
    wl.plant_state(UNDELEGATED + "\nmore\n")
    wl.newturn()
    assert NEEDLE in stop(wl, env, "rewrote STATE.md").out


def test_w3_a_delegated_section_from_an_earlier_context_does_not_clear_a_new_one(wl):
    wl.plant_state(DELEGATED)
    old = time.time() - 3600
    os.utime(wl.state_file(), (old, old))
    got = stop(wl, band(wl, 920_000, epoch=2, written=60_000))
    assert NEEDLE in got.out, got.out[:1500]


def test_w3_twin_a_wisdom_run_before_the_first_stop_past_the_line_counts(wl):
    """/wisdom ran at 93% and the first stop came after it: band-notice saw the rewrite at that usage."""
    wl.plant_state(DELEGATED)
    old = time.time() - 600
    os.utime(wl.state_file(), (old, old))
    got = stop(wl, band(wl, 930_000, epoch=2, written=900_000))
    assert NEEDLE not in got.out, got.out[:1500]


def test_w4_a_new_epoch_asks_again(wl):
    wl.plant_state(UNDELEGATED)
    assert NEEDLE in stop(wl, band(wl, 920_000, epoch=1)).out
    wl.plant_state(DELEGATED)
    wl.newturn()
    assert NEEDLE not in stop(wl, band(wl, 925_000, epoch=1), "handed over").out
    old = time.time() - 60
    os.utime(wl.state_file(), (old, old))
    wl.newturn()
    assert NEEDLE in stop(wl, band(wl, 900_000, epoch=2, written=40_000), "after compaction").out


def test_w6_a_rewrite_past_the_line_carrying_the_earlier_section_does_not_clear_it(wl):
    """The section that cleared epoch 1, carried unchanged by a `--state` rewrite at 98% of epoch 2, is not a hand-over for epoch 2."""
    wl.plant_state(UNDELEGATED)
    assert NEEDLE in stop(wl, band(wl, 920_000, epoch=1)).out
    wl.plant_state(DELEGATED)
    wl.newturn()
    assert NEEDLE not in stop(wl, band(wl, 925_000, epoch=1), "handed over").out
    wl.newturn()
    wl.plant_state(DELEGATED.replace("three writers out", "one writer out"))
    got = stop(wl, band(wl, 950_000, epoch=2, written=948_000), "rewrote STATE.md")
    assert NEEDLE in got.out, got.out[:1500]
    wl.plant_state(
        DELEGATED.replace("#1a07399b owns start_backup_plane.py", "#86b5992c owns tests/27")
    )
    wl.newturn()
    got = stop(wl, band(wl, 955_000, epoch=2, written=953_000), "delegated again")
    assert NEEDLE not in got.out, got.out[:1500]


def test_w5_the_cap_saturated_wait_keeps_it(wl):
    """Every writer slot live and the rest queued stands the battery down (test_wl_cap_wait c1); wisdom-due is in wl_standdown.CORE, so it still blocks."""
    saturated(wl)
    capturing_judge(wl, CONTINUE)
    wl.plant_state(UNDELEGATED)
    wl.say("all four writer slots are live; the rest is queued\n\n## Remaining\n- queued")
    got = wl.runj(band(wl, 920_000))
    assert got.decision == "block", wl.why("w5", "block", got, NEEDLE)
    assert NEEDLE in got.out, got.out[:1500]

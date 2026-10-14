"""A turbo batch building locally stands the red-CI block down (operator ruling 2026-10-13: turbo is for local implementation, so "CI IS RED ON PR #n AND NOTHING IS WATCHING IT" does not hold a stop until the prompted plans are complete).

THE WORLD is test_wl_loop_next's `turbo_world`: PR #543 OPEN on BRANCH with a really failed job, turbo on, and the real hook driven against it. THE FIRE CASE differs from each control by one planted fact: `turbo: off`, `turbo_push: pr`, a finished plan set, or an active focus. Every control asserts the block, so a predicate widened past its condition turns that control red; the mutation cases prove it by widening the predicate in a PRIVATE COPY of the hook.

THE PREDICATE is unit-tested in process as well (`wl_checks.turbo_build_parks`) against a LoopState-shaped namespace, including the two unknown sets (empty, unreadable) that must park nothing.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import mutated_hook
from rediacc_hooks.tests.test_wl_focus import CI_RED
from rediacc_hooks.tests.test_wl_loop_next import lstate, ready, stop, turbo_plan, turbo_world
from rediacc_hooks.tests.test_wl_pr_scope_stop import BRANCH, keys_of, reason

wl_checks = wlfix.import_wl("wl_checks")
wl_prscope = wlfix.import_wl("wl_prscope")

HELD = "CI on PR #543 is red on 1 job(s): Quality / Static FAILURE"
STOOD = "Stood down, not blocking: a turbo batch is building locally"
BLOCKS_AGAIN = "It blocks again when every plan of the set is finished"


@pytest.fixture
def fx(tmp_path):
    """One hook sandbox per test (wlfix.Fixture, built as wlfix's own `wl` fixture builds it)."""
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


@pytest.fixture
def repo(tmp_path):
    """A bare git checkout for the in-process predicate cases: the plan boxes are read off disk."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    return root


def building(fix, **kw):
    """The fire world: a red PR, turbo on, `turbo_push: batch-end`, one box of the PR's plan still open."""
    return turbo_world(fix, red=True, turbo_push="batch-end", **kw)


def held_line(got: wlfix.Result) -> str:
    """The one stood-down line of this stop's output, "" when it is absent."""
    return next((ln for ln in reason(got).splitlines() if STOOD in ln), "")


def focus(fix, mode: str) -> None:
    got = fix.cli("--focus", wlfix.ME, mode, "--branch", BRANCH, "--pr", "543")
    assert got.rc == 0, "--focus failed: %s %s" % (got.out, got.err)


# ---- controls first: every state the ruling does not cover blocks as before --------------------


def test_control_turbo_off_blocks_on_the_red(fx):
    building(fx, turbo=False)
    got = stop(fx)
    assert "ci-red" in keys_of(fx, got), reason(got)[:2000]
    assert CI_RED in reason(got), reason(got)[:2000]
    assert STOOD not in got.out, got.out[:2000]


def test_control_turbo_push_pr_blocks_on_the_red(fx):
    turbo_world(fx, red=True, turbo_push="pr")
    got = stop(fx)
    assert "ci-red" in keys_of(fx, got), reason(got)[:2000]
    assert CI_RED in reason(got), reason(got)[:2000]
    assert STOOD not in got.out, got.out[:2000]


def test_control_a_complete_batch_blocks_on_the_red(fx):
    """Every plan of the set finished is the merge offer's own condition (`live_batch_ready`), and the red blocks from that stop on."""
    building(fx, own_open=0)
    got = stop(fx)
    assert "ci-red" in keys_of(fx, got), reason(got)[:2000]
    assert CI_RED in reason(got), reason(got)[:2000]
    assert STOOD not in got.out, got.out[:2000]


@pytest.mark.parametrize("mode", ["babysit", "merge"])
def test_control_focus_keeps_the_red_blocking_under_turbo(fx, mode):
    """Focus governs: a declared PR wind-down is landing the PR, so the building batch parks nothing."""
    building(fx)
    focus(fx, mode)
    got = stop(fx)
    assert "ci-red" in keys_of(fx, got), reason(got)[:2000]
    assert CI_RED in reason(got), reason(got)[:2000]
    assert STOOD not in got.out, got.out[:2000]


# ---- the fire case ------------------------------------------------------------------------------


def test_a_building_batch_stands_the_red_down_and_names_the_job(fx):
    own, _one, _two = building(fx)
    got = stop(fx)
    out = reason(got)
    assert "ci-red" not in keys_of(fx, got), out[:2000]
    assert CI_RED not in got.out, got.out[:2000]
    line = held_line(got)
    assert line, "the stood-down line is missing: %s" % out[:2000]
    assert HELD in line, line
    assert "failing step: " in line, line
    assert "run 30514648812 attempt 1, job 90784763855" in line, line
    assert "still open: %s (1 open)" % own.rsplit("/", 1)[-1] in line, line
    assert BLOCKS_AGAIN in line, line
    assert "TURBO_PUSH_REASON='red-fix: <why>'" in line, line
    assert out.count(STOOD) == 1, "the stood-down line is printed once per stop: %s" % out[:2000]


def writer_running(fix) -> None:
    """A live background task that is no CI watch: the open plan box then advises, so the red is the only thing left to block."""
    fix.bg = json.dumps(
        [{"id": "bw9", "type": "shell", "status": "running", "description": "npm run build"}]
    )


def test_a_stop_whose_only_block_was_the_red_is_allowed_and_still_says_so(fx):
    building(fx)
    writer_running(fx)
    got = stop(fx)
    assert got.decision == "allow", reason(got)[:2000]
    assert HELD in got.out, got.out[:2000]
    assert STOOD in got.out, got.out[:2000]


def test_control_the_same_stop_with_turbo_off_is_blocked_by_the_red_alone(fx):
    building(fx, turbo=False)
    writer_running(fx)
    got = stop(fx)
    assert got.decision == "block", got.out[:2000]
    assert keys_of(fx, got) == {"ci-red"}, reason(got)[:2000]


def test_the_stood_down_key_is_named_on_the_queued_line(fx):
    """The N_PR_SCOPE line counts `ci-red` among the checks this stop stood down, through the PR-loop ledger."""
    building(fx)
    got = stop(fx)
    scope = next((ln for ln in reason(got).splitlines() if "Turbo is on (batch_size" in ln), "")
    assert "Stood down: " in scope, reason(got)[:2000]
    assert "ci-red x1" in scope, scope


def test_the_stood_down_line_rides_every_stop_while_the_red_stands(fx):
    """Not a latch: four stops, four lines. The block budget of two would have silenced a counted block by the third."""
    building(fx)
    for n in range(4):
        if n:
            fx.newturn()
        got = stop(fx)
        assert "ci-red" not in keys_of(fx, got), (n, reason(got)[:2000])
        assert HELD in held_line(got), (n, reason(got)[:2000])


def test_the_red_blocks_again_once_the_batch_completes(fx):
    """The stood-down stops spend none of the red's block budget (wl_ci.ci_trouble `hold`): after more of them than CI_MAX_BLOCKS, ticking the last box brings the full block back."""
    building(fx)
    for n in range(3):
        if n:
            fx.newturn()
        assert "ci-red" not in keys_of(fx, stop(fx))
    turbo_plan(fx, "pr-own", opened=0, done=2)
    fx.newturn()
    got = stop(fx)
    assert "ci-red" in keys_of(fx, got), reason(got)[:2000]
    assert CI_RED in reason(got), reason(got)[:2000]
    assert STOOD not in got.out, got.out[:2000]


# ---- the predicate, in process ------------------------------------------------------------------


def live(root, **kw):
    """A live batch-end PR whose set has one plan finished and one open."""
    return lstate(root, kind=wl_prscope.LIVE, pr=543, local_batch=False, **kw)


def parks(state, root, on_loop=True, focus_event=None):
    return wl_checks.turbo_build_parks(state, root, on_loop, focus_event)


def test_predicate_a_building_batch_parks_exactly_the_red(repo):
    assert parks(live(repo), repo) == frozenset({"ci-red"})


def test_predicate_controls_park_nothing(repo):
    assert parks(live(repo, turbo=False), repo) == frozenset()
    assert parks(live(repo, turbo_push="pr"), repo) == frozenset()
    assert parks(live(repo), repo, on_loop=False) == frozenset()
    assert parks(live(repo), repo, focus_event={"mode": "merge"}) == frozenset()
    assert parks(None, repo) == frozenset()
    done = ready(repo, kind=wl_prscope.LIVE, pr=543, local_batch=False)
    assert parks(done, repo) == frozenset()


def test_predicate_turbo_off_parks_nothing_whatever_the_batch_reads(repo, monkeypatch):
    """The turbo term stands on its own: with the batch read forced to "not ready", turbo off still parks nothing."""
    monkeypatch.setattr(wl_checks, "live_batch_ready", lambda _state, _finished: False)
    assert parks(live(repo), repo) == frozenset({"ci-red"})
    assert parks(live(repo, turbo=False), repo) == frozenset()


def test_predicate_a_state_without_the_push_field_parks_nothing(repo):
    """A LoopState that predates `turbo_push` reads as `pr` (wl_checks.turbo_push_mode), the mode that blocks."""
    st = live(repo)
    del st.turbo_push
    assert parks(st, repo) == frozenset()


def test_predicate_an_empty_set_parks_nothing(repo):
    """An empty set is not finished, and it is not building either: nothing proves there is local work."""
    st = live(repo, plans=())
    assert wl_checks._set_finished(st, repo) is False
    assert parks(st, repo) == frozenset()


def test_predicate_an_unreadable_plan_parks_nothing(repo):
    st = live(repo)
    st.plans = (*st.plans, "agent/plans/PLAN-ghost.md")
    assert wl_checks._set_finished(st, repo) is False
    assert parks(st, repo) == frozenset()


# ---- mutation controls: each widening, in a PRIVATE COPY of the hook, turns one control red -----

BYPASS = (
    "        _turbo_parks = turbo_build_parks(_loop, root, _on_loop, _focus)\n",
    "        _turbo_parks = TURBO_BUILD_PARKS\n",
)
FOCUS_GUARD = (
    '    if focus or not on_loop or state is None or not getattr(state, "turbo", False):\n',
    '    if not on_loop or state is None or not getattr(state, "turbo", False):\n',
)
MODE_GUARD = (
    '    if turbo_push_mode(state) != "batch-end":\n        return frozenset()\n    if live_batch_ready',
    "    if live_batch_ready",
)
READY_GUARD = (
    "    if live_batch_ready(state, _set_finished(state, root)) or _set_unreadable(state, root):\n",
    "    if _set_unreadable(state, root):\n",
)
HOLD_GUARD = ('    if hold:\n        return "trouble", detail\n', "")
REPORT_LINE = (
    "            ci_report = M.CI_NOTE_TURBO_HELD % (\n",
    "            _ = M.CI_NOTE_TURBO_HELD % (\n",
)


def test_m1_with_the_predicate_bypassed_the_turbo_off_control_stands_down(fx):
    """Turbo off is refused twice, by the predicate's own term and by `wl_prscope.batch_ready` (always ready with turbo off), so no single removed term widens it: the widening is the predicate bypassed at its call. The term itself is pinned by test_predicate_turbo_off_parks_nothing_whatever_the_batch_reads."""
    building(fx, turbo=False)
    mutated_hook(fx, "wl_checks.py", *BYPASS)
    got = stop(fx)
    assert "ci-red" not in keys_of(fx, got), (
        "m1: the turbo-off control does not depend on the predicate"
    )
    assert STOOD in got.out, got.out[:900]


def test_m2_without_the_mode_term_the_pr_mode_control_stands_down(fx):
    turbo_world(fx, red=True, turbo_push="pr")
    mutated_hook(fx, "wl_checks.py", *MODE_GUARD)
    got = stop(fx)
    assert "ci-red" not in keys_of(fx, got), "m2: the pr-mode control does not depend on the mode"
    assert STOOD in got.out, got.out[:900]


def test_m3_without_the_batch_term_the_complete_batch_control_stands_down(fx):
    building(fx, own_open=0)
    mutated_hook(fx, "wl_checks.py", *READY_GUARD)
    got = stop(fx)
    assert "ci-red" not in keys_of(fx, got), "m3: the complete-batch control does not depend on it"
    assert STOOD in got.out, got.out[:900]


def test_m4_without_the_focus_term_the_focus_control_stands_down(fx):
    building(fx)
    focus(fx, "babysit")
    mutated_hook(fx, "wl_checks.py", *FOCUS_GUARD)
    got = stop(fx)
    assert "ci-red" not in keys_of(fx, got), (
        "m4: the focus control does not depend on the focus term"
    )
    assert CI_RED not in got.out, got.out[:900]


def test_m5_without_the_budget_hold_the_red_never_blocks_again(fx):
    """With `hold` ignored the stood-down stops spend the block budget, so the completed batch finds it spent and the red only reports."""
    building(fx)
    mutated_hook(fx, "wl_ci.py", *HOLD_GUARD)
    for n in range(3):
        if n:
            fx.newturn()
        stop(fx)
    turbo_plan(fx, "pr-own", opened=0, done=2)
    fx.newturn()
    got = stop(fx)
    assert "ci-red" not in keys_of(fx, got), "m5: the re-block case does not depend on the hold"


def test_m6_without_the_report_the_stand_down_is_silent(fx):
    building(fx)
    mutated_hook(fx, "wl_checks.py", *REPORT_LINE)
    got = stop(fx)
    assert STOOD not in got.out, "m6: the fire case does not depend on the report line"

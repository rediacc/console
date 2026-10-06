"""loop-next: after the PR merges, the Stop hook holds the turn until the next branch, plan and PR exist (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 7, box SC9; operator addition 2026-10-03).

Every case drives the real hook against a fixture checkout and the shared gh shim of test_wl_focus, so `wl_prscope.loop_state` resolves the state from a real git branch and a planted PR read. Each fire case has a control that differs by one planted fact; the mutation control deletes the `merged` arm in a PRIVATE COPY of the hook.

The next branch name is `commit_policy.next_branch_name` on today's local date, the clock `block_second_branch` names branches with; the hook does not take a frozen clock, so the expected name is computed here from the same date and the fixture's own branches.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from rediacc_hooks.tests import test_wl_focus as F
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import mutated_hook
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_running, write_exec
from rediacc_hooks.tests.test_wl_ci_status import ci_rollup as ci_status_rollup
from rediacc_hooks.tests.test_wl_pr_scope_stop import (
    BRANCH,
    keys_of,
    loop_plan,
    pr_node,
    reason,
    write_queue,
)
from rediacc_hooks.tests.test_wl_roster import subagents_dir
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

LOOP_NEXT = "LOOP NEXT:"


def base_world(fix):
    """A git checkout on main with an origin remote, the gh shim, fresh brief and handover; origin/main at the base commit."""
    F.world(fix, ci=True)
    head = fix.git("rev-parse", "HEAD").stdout.strip()
    fix.git("update-ref", "refs/remotes/origin/main", head)


def plans(fix, own_open: int = 1, next_open: int = 2):
    own = loop_plan(fix, "pr-own", opened=own_open)
    nxt = loop_plan(fix, "queued-next", opened=next_open, done=0)
    return own, nxt


def expected_branch(taken: tuple[str, ...] = ()) -> str:
    day = datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- block_second_branch's clock
    used = [int(b.split("-", 1)[1]) for b in taken if b.startswith(day + "-")]
    return "%s-%d" % (day, max(used, default=0) + 1)


def stop(fix) -> wlfix.Result:
    return F.stop(fix)


def merged_world(fix, queue: bool = True, stale: bool = False):
    base_world(fix)
    fix.git("switch", "-q", "-c", BRANCH)
    own, nxt = plans(fix, own_open=0)
    if stale:
        write_queue(fix, own, nxt)
    elif queue:
        write_queue(fix, nxt)
    else:
        write_queue(fix)
    F.merged_nodes(fix, [pr_node("MERGED", "Plan: %s\n" % own)])
    return own, nxt


def test_ln1_merged_with_a_queue_blocks_with_the_step_seven_sequence(wl):  # noqa: F811
    _own, nxt = merged_world(wl)
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "PR #543 on %s is merged and QUEUE.md holds %s" % (BRANCH, nxt) in out, out[:1500]
    for cmd in (
        "git switch main && git pull --ff-only",
        "git fetch origin --prune",
        "git branch -D %s" % BRANCH,
        "git switch -c %s" % expected_branch((BRANCH,)),
        "T0 the open queued-next fixture box",
    ):
        assert cmd in out, (cmd, out[:2000])
    assert "git push origin --delete" not in out, "origin/%s does not exist: %s" % (BRANCH, out)


def test_ln1_the_remote_delete_is_named_while_the_remote_branch_exists(wl):  # noqa: F811
    merged_world(wl)
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    got = stop(wl)
    assert "git push origin --delete %s" % BRANCH in reason(got), reason(got)[:1500]


def test_ln1_control_merged_with_an_empty_queue_allows(wl):  # noqa: F811
    merged_world(wl, queue=False)
    got = stop(wl)
    assert LOOP_NEXT not in got.out, got.out[:1500]
    assert got.decision == "allow", reason(got)[:1500]


def test_ln2_on_main_with_a_queue_cuts_the_next_branch(wl):  # noqa: F811
    base_world(wl)
    _own, nxt = plans(wl)
    write_queue(wl, nxt)
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "on main with no live branch" in out, out[:1500]
    assert "git switch -c %s" % expected_branch() in out, out[:1500]


def test_ln2_control_on_main_with_an_empty_queue_says_nothing(wl):  # noqa: F811
    base_world(wl)
    plans(wl)
    write_queue(wl)
    got = stop(wl)
    assert LOOP_NEXT not in got.out, got.out[:1500]


def test_ln3_a_branch_with_commits_and_no_pr_opens_the_draft(wl):  # noqa: F811
    base_world(wl)
    wl.git("switch", "-q", "-c", BRANCH)
    _own, nxt = plans(wl)
    write_queue(wl, nxt)
    (wl.proj / "b.txt").write_text("b\n", encoding="utf-8")
    wl.git("add", "b.txt")
    wl.git("commit", "-qm", "work")
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "gh pr create --draft --base main --head %s" % BRANCH in out, out[:1500]
    assert "git push -u origin %s" % BRANCH in out, out[:1500]


def test_ln3_control_no_commits_ahead_works_the_queue_head(wl):  # noqa: F811
    base_world(wl)
    wl.git("switch", "-q", "-c", BRANCH)
    _own, nxt = plans(wl)
    write_queue(wl, nxt)
    got = stop(wl)
    out = reason(got)
    assert "gh pr create" not in out, out[:1500]
    assert "has no PR and no commit ahead of origin/main" in out, out[:1500]


def live_world(fix, own_open: int, pre_open: int | None = None):
    base_world(fix)
    fix.git("switch", "-q", "-c", BRANCH)
    dep = ""
    if pre_open is not None:
        loop_plan(fix, "pre", opened=pre_open, done=1)
        dep = "PLAN-pre.md"
    own = loop_plan(fix, "pr-own", opened=own_open, dep=dep)
    nxt = loop_plan(fix, "queued-next", opened=2, done=0)
    write_queue(fix, own, nxt)
    F.merged_nodes(fix, [pr_node("OPEN", "Plan: %s\n" % own)])
    return own


def test_ln4_a_live_pr_with_open_boxes_gives_no_loop_next(wl):  # noqa: F811
    live_world(wl, own_open=1)
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]
    assert LOOP_NEXT not in got.out, got.out[:1500]


def test_ln5_a_live_pr_with_every_box_ticked_names_pr_merge(wl):  # noqa: F811
    live_world(wl, own_open=0)
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "run /pr-merge" in out, out[:1500]


def test_ln5b_a_pending_run_on_the_head_turns_the_merge_order_into_an_advisory(wl):  # noqa: F811
    """PR #597, 2026-10-06: every box ticked and CI running. /pr-merge needs CI Complete SUCCESS, so the merge order blocked each stop of the wait with nothing to do; the push hook's detached watch is not a background task of the session. ln5 (green CI) is the control: it still blocks."""
    live_world(wl, own_open=0)
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    ci_status_rollup(
        wl,
        "PENDING",
        "[%s,%s]" % (ci_job("Quality / Static", "SUCCESS"), ci_running("CI Complete")),
    )
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]


def test_ln6_a_ticked_pr_plan_with_an_open_prerequisite_never_gets_pr_merge(wl):  # noqa: F811
    """Ruling 7: the prerequisite is in the PR's plan set, so the set is not finished and the block names the prerequisite's first open box."""
    live_world(wl, own_open=0, pre_open=1)
    got = stop(wl)
    out = reason(got)
    assert "/pr-merge" not in out, out[:1500]
    assert "plan-unimplemented" in keys_of(wl, got), out[:1500]
    assert "THE NEXT BOX (agent/plans/PLAN-pre.md)" in out, out[:2000]
    assert "T0 the open pre fixture box" in out, out[:2000]


def test_ln7_a_finished_promoted_head_adds_its_removal_line(wl):  # noqa: F811
    own, _nxt = merged_world(wl, stale=True)
    got = stop(wl)
    out = reason(got)
    assert "Then remove the finished Promoted entry %s from agent/plans/QUEUE.md" % own in out, out[
        :2000
    ]


def test_ln7_control_no_stale_head_no_removal_line(wl):  # noqa: F811
    merged_world(wl)
    got = stop(wl)
    assert "Then remove the finished Promoted entry" not in reason(got), reason(got)[:1500]


def test_ln8_a_live_ci_trace_wait_turns_the_merged_block_into_an_advisory(wl):  # noqa: F811
    merged_world(wl)
    wl.bg = json.dumps(
        [{"id": "bw9", "type": "shell", "status": "running", "description": "ci-trace --wait"}]
    )
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]


def test_ln9_gh_down_blocks_at_most_ci_max_blocks_stops_then_advises(wl):  # noqa: F811
    budget = int(wlfix.import_wl("wl_ci").CI_MAX_BLOCKS)
    base_world(wl)
    wl.git("switch", "-q", "-c", BRANCH)
    _own, nxt = plans(wl)
    write_queue(wl, nxt)
    write_exec(wl.base / "binonly" / "gh", "#!/bin/bash\necho 'gh: planted outage' >&2\nexit 1\n")
    seen = []
    for _ in range(budget + 1):
        wl.newturn()
        got = stop(wl)
        seen.append("loop-next" in keys_of(wl, got))
        assert "the loop state could not be read" in got.out, got.out[:1500]
    assert seen == [True] * budget + [False], seen


def test_ln_m1_without_the_merged_arm_the_merged_case_allows(wl):  # noqa: F811
    merged_world(wl)
    mutated_hook(wl, "wl_checks.py", "    if kind == wl_prscope.MERGED:\n", "    if False:\n")
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), (
        "m1: the merged case does not depend on its arm: %s" % reason(got)[:900]
    )


# ---- turbo-next (agent/plans/PLAN-stop-hook-turbo.md D5/D8, box T10) ----------------------------


def turbo_plan(fix, name: str, opened: int = 1, done: int = 0) -> str:
    """A queued plan carrying the Concurrency/Owns fields the turbo picks check (wl_planconc.spawn_verdict fails closed without them)."""
    text = (
        "# PLAN: %s fixture\n\nStatus: approved\nOwner: %s\nDepends-On: no-dep -- a fixture plan that stands alone\n"
        "Concurrency: parallel\nOwns: docs/%s/**\n\n## Tasks\n\n" % (name, wlfix.ME, name)
    )
    text += "".join("- [x] D%d the ticked %s fixture box\n" % (i, name) for i in range(done))
    text += "".join("- [ ] T%d the open %s fixture box\n" % (i, name) for i in range(opened))
    folder = fix.proj / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("PLAN-%s.md" % name)).write_text(text, encoding="utf-8")
    return "agent/plans/PLAN-%s.md" % name


def turbo_world(fix, turbo: bool = True, red: bool = False, own_open: int = 1, batch: int = 2):
    """PR #543 OPEN on BRANCH working PLAN-pr-own.md, two more queued plans with X fields, and the settings block written after the queue."""
    F.world(fix, ci=True, red=red)
    head = fix.git("rev-parse", "HEAD").stdout.strip()
    fix.git("update-ref", "refs/remotes/origin/main", head)
    fix.git("switch", "-q", "-c", BRANCH)
    if red:
        fix.git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    own = turbo_plan(fix, "pr-own", opened=own_open, done=1)
    one = turbo_plan(fix, "turbo-one", opened=2)
    two = turbo_plan(fix, "turbo-two", opened=2)
    write_queue(fix, own, one, two)
    fix.settings(turbo=turbo, batch_size=batch, plan_concurrency=9, writer_cap=4)
    # The session's project directory exists and holds no subagent: an honest zero writers, not a blind roster (a blind roster names no plan).
    subagents_dir(fix).parent.parent.mkdir(parents=True, exist_ok=True)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    F.merged_nodes(fix, [pr_node("OPEN", "Plan: %s\n" % own)])
    return own, one, two


def test_tn1_turbo_names_the_eligible_plans_to_start_on_writers(wl):  # noqa: F811
    """The arm blocks on the first stop; its text is surfaced within the ladder's rotation over the T_MISSION keys that block beside it."""
    _own, one, two = turbo_world(wl)
    got = stop(wl)
    assert "turbo-next" in keys_of(wl, got), reason(got)[:2000]
    out = reason(got)
    for _ in range(3):
        # The quoted text, not the one-line name the rotating tail gives the arm on the other stops.
        if "TURBO: start" in out:
            break
        wl.newturn()
        out = reason(stop(wl))
    assert "Start ONLY the plans named here" in out, out[:2000]
    assert "TURBO: start %s on a writer (slot 1 of 4)" % one in out, out[:2000]
    assert "TURBO: start %s on a writer (slot 2 of 4)" % two in out, out[:2000]
    assert "T0 the open turbo-one fixture box" in out, out[:2000]


def test_tn1_the_named_plans_are_recorded_for_the_pr_body(wl):  # noqa: F811
    _own, one, two = turbo_world(wl)
    stop(wl)
    record = pathlib.Path(str(wl.wl)[: -len(".md")] + ".turbo-named.json")
    assert record.is_file(), "the turbo picks were not recorded beside the store"
    assert json.loads(record.read_text(encoding="utf-8")).get(BRANCH) == [one, two]


def test_tn2_turbo_off_never_names_a_plan_and_keeps_the_loop_keys(wl):  # noqa: F811
    turbo_world(wl, turbo=False)
    got = stop(wl)
    out = reason(got)
    assert "turbo-next" not in keys_of(wl, got), out[:2000]
    assert "TURBO" not in got.out, got.out[:2000]
    assert not pathlib.Path(str(wl.wl)[: -len(".md")] + ".turbo-named.json").exists()


def test_tn2_turbo_off_matches_a_queue_with_no_settings_block(wl):  # noqa: F811
    """Turbo off is today's loop: the same keys as a QUEUE.md that has no `## Settings` at all."""
    turbo_world(wl, turbo=False)
    off = keys_of(wl, stop(wl))
    queue = wl.proj / "agent" / "plans" / "QUEUE.md"
    text = queue.read_text(encoding="utf-8")
    queue.write_text(
        text.split("## Settings", 1)[0] + "## Promoted" + text.split("## Promoted", 1)[1],
        encoding="utf-8",
    )
    assert "## Settings" not in queue.read_text(encoding="utf-8")
    wl.newturn()
    bare = keys_of(wl, stop(wl))
    assert off == bare, (off, bare)


def test_tn3_a_red_ci_outranks_the_turbo_arm(wl):  # noqa: F811
    turbo_world(wl, red=True)
    got = stop(wl)
    keys = keys_of(wl, got)
    assert "ci-red" in keys, reason(got)[:2000]
    assert "turbo-next" not in keys, reason(got)[:2000]


def test_tn4_a_finished_set_short_of_the_batch_is_not_offered_for_merge(wl):  # noqa: F811
    """D8: one plan finished of a batch of 2, and eligible plans remain, so the merge waits and the turbo arm names the next plans."""
    turbo_world(wl, own_open=0, batch=2)
    got = stop(wl)
    out = reason(got)
    assert "run /pr-merge" not in out, out[:2000]
    assert "turbo-next" in keys_of(wl, got), out[:2000]


def test_tn4_control_batch_one_offers_the_merge(wl):  # noqa: F811
    turbo_world(wl, own_open=0, batch=1)
    got = stop(wl)
    out = reason(got)
    assert "run /pr-merge" in out, out[:2000]
    assert "turbo-next" not in keys_of(wl, got), out[:2000]


def test_tn_m1_a_turbo_flag_read_as_always_on_fires_the_arm_with_turbo_off(wl):  # noqa: F811
    """Mutation control: with the settings parser reading every `turbo:` as on, the turbo-off world names plans, so tn2 depends on the flag."""
    turbo_world(wl, turbo=False)
    mutated_hook(
        wl,
        "wl_planqueue.py",
        '        return raw == "on"\n',
        '        return True if key == "turbo" else raw == "on"\n',
    )
    got = stop(wl)
    assert "turbo-next" in keys_of(wl, got), (
        "m1: the turbo-off case does not depend on the flag: %s" % reason(got)[:900]
    )

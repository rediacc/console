"""loop-next: after the PR merges, the Stop hook holds the turn until the next branch, plan and PR exist (agent/plans/PLAN-stop-hook-one-plan-scope.md Design 7, box SC9; operator addition 2026-10-03).

Every case drives the real hook against a fixture checkout and the shared gh shim of test_wl_focus, so `wl_prscope.loop_state` resolves the state from a real git branch and a planted PR read. Each fire case has a control that differs by one planted fact; the mutation control deletes the `merged` arm in a PRIVATE COPY of the hook.

The next branch name is `commit_policy.next_branch_name` on today's local date, the clock `block_second_branch` names branches with; the hook does not take a frozen clock, so the expected name is computed here from the same date and the fixture's own branches.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import types

import pytest
import wl_checks
import wl_judge
import wl_prscope
import worklist_messages as M

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
    day = datetime.datetime.now().astimezone().strftime("%m%d")
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


def test_ln1_merged_with_a_queue_blocks_with_the_step_seven_sequence(wl):
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


def test_ln1_the_remote_delete_is_named_while_the_remote_branch_exists(wl):
    merged_world(wl)
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    got = stop(wl)
    assert "git push origin --delete %s" % BRANCH in reason(got), reason(got)[:1500]


def test_ln1_control_merged_with_an_empty_queue_allows(wl):
    merged_world(wl, queue=False)
    got = stop(wl)
    assert LOOP_NEXT not in got.out, got.out[:1500]
    assert got.decision == "allow", reason(got)[:1500]


def test_ln2_on_main_with_a_queue_cuts_the_next_branch(wl):
    base_world(wl)
    _own, nxt = plans(wl)
    write_queue(wl, nxt)
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "on main with no live branch" in out, out[:1500]
    assert "git switch -c %s" % expected_branch() in out, out[:1500]


def test_ln2_control_on_main_with_an_empty_queue_says_nothing(wl):
    base_world(wl)
    plans(wl)
    write_queue(wl)
    got = stop(wl)
    assert LOOP_NEXT not in got.out, got.out[:1500]


def test_ln3_a_branch_with_commits_and_no_pr_opens_the_draft(wl):
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


def test_ln3_control_no_commits_ahead_works_the_queue_head(wl):
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


def test_ln4_a_live_pr_with_open_boxes_gives_no_loop_next(wl):
    live_world(wl, own_open=1)
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]
    assert LOOP_NEXT not in got.out, got.out[:1500]


def test_ln5_a_live_pr_with_every_box_ticked_names_pr_merge(wl):
    live_world(wl, own_open=0)
    got = stop(wl)
    out = reason(got)
    assert "loop-next" in keys_of(wl, got), out[:1500]
    assert "run /pr-merge" in out, out[:1500]


def test_ln5b_a_pending_run_on_the_head_turns_the_merge_order_into_an_advisory(wl):
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


def test_ln6_a_ticked_pr_plan_with_an_open_prerequisite_never_gets_pr_merge(wl):
    """Ruling 7: the prerequisite is in the PR's plan set, so the set is not finished and the block names the prerequisite's first open box."""
    live_world(wl, own_open=0, pre_open=1)
    got = stop(wl)
    out = reason(got)
    assert "/pr-merge" not in out, out[:1500]
    assert "plan-unimplemented" in keys_of(wl, got), out[:1500]
    assert "THE NEXT BOX (agent/plans/PLAN-pre.md)" in out, out[:2000]
    assert "T0 the open pre fixture box" in out, out[:2000]


def test_ln7_a_finished_promoted_head_adds_its_removal_line(wl):
    own, _nxt = merged_world(wl, stale=True)
    got = stop(wl)
    out = reason(got)
    assert "Then remove the finished Promoted entry %s from agent/plans/QUEUE.md" % own in out, out[
        :2000
    ]


def test_ln7_control_no_stale_head_no_removal_line(wl):
    merged_world(wl)
    got = stop(wl)
    assert "Then remove the finished Promoted entry" not in reason(got), reason(got)[:1500]


def test_ln8_a_live_ci_trace_wait_turns_the_merged_block_into_an_advisory(wl):
    merged_world(wl)
    wl.bg = json.dumps(
        [{"id": "bw9", "type": "shell", "status": "running", "description": "ci-trace --wait"}]
    )
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]


def test_ln9_gh_down_blocks_at_most_ci_max_blocks_stops_then_advises(wl):
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


def test_ln_m1_without_the_merged_arm_the_merged_case_allows(wl):
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


def turbo_world(
    fix,
    turbo: bool = True,
    red: bool = False,
    own_open: int = 1,
    batch: int = 2,
    turbo_push: str = "pr",
):
    """PR #543 OPEN on BRANCH working PLAN-pr-own.md, two more queued plans with X fields, and the settings block written after the queue. `turbo_push` defaults to `pr`, the mode in which a live PR takes new plans (agent/plans/PLAN-turbo-local-first.md D3)."""
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
    fix.settings(
        turbo=turbo, turbo_push=turbo_push, batch_size=batch, plan_concurrency=9, writer_cap=4
    )
    # The session's project directory exists and holds no subagent: an honest zero writers, not a blind roster (a blind roster names no plan).
    subagents_dir(fix).parent.parent.mkdir(parents=True, exist_ok=True)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    F.merged_nodes(fix, [pr_node("OPEN", "Plan: %s\n" % own)])
    return own, one, two


def test_tn1_turbo_names_the_eligible_plans_to_start_on_writers(wl):
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


def test_tn1_the_named_plans_are_recorded_for_the_pr_body(wl):
    _own, one, two = turbo_world(wl)
    stop(wl)
    record = pathlib.Path(str(wl.wl)[: -len(".md")] + ".turbo-named.json")
    assert record.is_file(), "the turbo picks were not recorded beside the store"
    assert json.loads(record.read_text(encoding="utf-8")).get(BRANCH) == [one, two]


def test_tn2_turbo_off_never_names_a_plan_and_keeps_the_loop_keys(wl):
    turbo_world(wl, turbo=False)
    got = stop(wl)
    out = reason(got)
    assert "turbo-next" not in keys_of(wl, got), out[:2000]
    assert "TURBO" not in got.out, got.out[:2000]
    assert not pathlib.Path(str(wl.wl)[: -len(".md")] + ".turbo-named.json").exists()


def test_tn2_turbo_off_matches_a_queue_with_no_settings_block(wl):
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


def test_tn3_a_red_ci_outranks_the_turbo_arm(wl):
    turbo_world(wl, red=True)
    got = stop(wl)
    keys = keys_of(wl, got)
    assert "ci-red" in keys, reason(got)[:2000]
    assert "turbo-next" not in keys, reason(got)[:2000]


def test_tn4_a_finished_set_short_of_the_batch_is_not_offered_for_merge(wl):
    """D8: one plan finished of a batch of 2, and eligible plans remain, so the merge waits and the turbo arm names the next plans."""
    turbo_world(wl, own_open=0, batch=2)
    got = stop(wl)
    out = reason(got)
    assert "run /pr-merge" not in out, out[:2000]
    assert "turbo-next" in keys_of(wl, got), out[:2000]


def test_tn4_control_batch_one_offers_the_merge(wl):
    turbo_world(wl, own_open=0, batch=1)
    got = stop(wl)
    out = reason(got)
    assert "run /pr-merge" in out, out[:2000]
    assert "turbo-next" not in keys_of(wl, got), out[:2000]


def test_tn_m1_a_turbo_flag_read_as_always_on_fires_the_arm_with_turbo_off(wl):
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


# ---- turbo local-first (agent/plans/PLAN-turbo-local-first.md D2-D4, D6; boxes LF-W2 and LF-min) ----
#
# UNIT CASES drive wl_checks.loop_next_text / turbo_next_text / wl_judge.sanitize_next_action in process against a real git checkout (the arms count `origin/main..HEAD` and read plan boxes off disk) and a LoopState-shaped namespace carrying wl_prscope's local-first fields directly, so they hold whichever LoopState is on disk.
# The INTEGRATION cases drive the real hook, where wl_prscope computes `local_batch` itself.


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _plan(root, name, opened, done=1):
    text = "# PLAN: %s\n\nStatus: approved\n\n## Tasks\n\n" % name
    text += "".join("- [x] D%d ticked %s box\n" % (i, name) for i in range(done))
    text += "".join("- [ ] T%d open %s box\n" % (i, name) for i in range(opened))
    folder = root / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("PLAN-%s.md" % name)).write_text(text, encoding="utf-8")
    return "agent/plans/PLAN-%s.md" % name


@pytest.fixture
def lrepo(tmp_path):
    """A checkout on BRANCH with origin/main at the base commit and 5 commits ahead of it."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    _git(root, "switch", "-q", "-c", BRANCH)
    for i in range(5):
        (root / ("w%d.txt" % i)).write_text("%d\n" % i, encoding="utf-8")
        _git(root, "add", "w%d.txt" % i)
        _git(root, "commit", "-qm", "work %d" % i)
    return root


def lstate(root, **kw):
    """A no-PR local batch: turbo on, batch-end, batch 1/3 finished, one plan of the set still open, a queued plan eligible."""
    done_plan = _plan(root, "batch-done", opened=0)
    open_plan = _plan(root, "batch-open", opened=1)
    nxt = _plan(root, "queued", opened=2, done=0)
    base = {
        "kind": wl_prscope.NO_PR,
        "branch": BRANCH,
        "pr": 0,
        "plans": (done_plan, open_plan),
        "prereqs": (),
        "epic_items": frozenset(),
        "next_plan": nxt,
        "queue_head": done_plan,
        "stale_promoted": "",
        "next_branch": "",
        "reason": "",
        "turbo": True,
        "batch_size": 3,
        "writer_cap": 4,
        "turbo_picks": (nxt,),
        "turbo_more": True,
        "finished": 1,
        "turbo_push": "batch-end",
        "backup_push_h": 4,
        "local_batch": True,
    }
    base.update(kw)
    return types.SimpleNamespace(**base)


def ready(root, **kw):
    """The same batch, ready: every plan finished and batch_size of them done."""
    a = _plan(root, "batch-a", opened=0)
    b = _plan(root, "batch-b", opened=0)
    c = _plan(root, "batch-c", opened=0)
    return lstate(root, **{"plans": (a, b, c), "queue_head": a, "finished": 3, **kw})


def test_lf1_a_filling_local_batch_is_an_advisory_not_open_it(lrepo):
    text, blocking = wl_checks.loop_next_text(lstate(lrepo), lrepo, {}, False, me="d778be9d")
    assert blocking is False, text
    assert text.startswith("TURBO LOCAL-FIRST: 5 commit(s) on %s" % BRANCH), text
    assert "batch 1/3 finished" in text, text
    assert "No push or PR until the batch completes" in text, text
    assert "Open it" not in text, text
    assert "gh pr create" not in text, text


def test_lf1_the_advisory_names_the_plan_that_is_still_open(lrepo):
    text, _blocking = wl_checks.loop_next_text(lstate(lrepo), lrepo, {}, False, me="d778be9d")
    assert "still open: PLAN-batch-open.md (1 open)" in text, text


def test_lf1_the_open_boxes_are_read_only_where_the_advisory_renders_them(lrepo, monkeypatch):
    """The plan reads behind `still open:` are paid by the advisory arm alone, not by the ready batch."""
    calls: list[tuple] = []
    real = wl_checks._open_in_set

    def spy(*a):
        calls.append(a)
        return real(*a)

    monkeypatch.setattr(wl_checks, "_open_in_set", spy)
    wl_checks.loop_next_text(ready(lrepo), lrepo, {}, False, me="d778be9d")
    assert calls == [], calls
    wl_checks.loop_next_text(lstate(lrepo), lrepo, {}, False, me="d778be9d")
    assert len(calls) == 1, calls


def test_lf1_an_empty_set_does_not_read_as_complete(lrepo):
    text, blocking = wl_checks.loop_next_text(
        lstate(lrepo, plans=()), lrepo, {}, False, me="d778be9d"
    )
    assert blocking is False, text
    assert "still open: no plans in the set" in text, text
    assert "still open: none" not in text, text


def test_lf1_an_unreadable_plan_keeps_the_batch_unfinished(lrepo):
    """A plan whose boxes cannot be read is never finished, so the batch-end push is not ordered."""
    ghost = "agent/plans/PLAN-ghost.md"
    st = ready(lrepo)
    st.plans = (*st.plans[:2], ghost)
    assert wl_checks._set_finished(st, lrepo) is False
    text, blocking = wl_checks.loop_next_text(st, lrepo, {}, False, me="d778be9d")
    assert blocking is False, text
    assert "PLAN-ghost.md (unreadable)" in text, text


def test_lf1_control_a_finished_set_is_finished(lrepo):
    assert wl_checks._set_finished(ready(lrepo), lrepo) is True


def test_lf1_control_turbo_push_pr_blocks_with_open_it(lrepo):
    text, blocking = wl_checks.loop_next_text(
        lstate(lrepo, turbo_push="pr"), lrepo, {}, False, me="d778be9d"
    )
    assert blocking is True, text
    assert "Open it" in text, text


def test_lf1_control_turbo_off_blocks_with_open_it(lrepo):
    text, blocking = wl_checks.loop_next_text(
        lstate(lrepo, turbo=False, local_batch=False), lrepo, {}, False
    )
    assert blocking is True, text
    assert "Open it" in text, text


def test_lf1_control_a_state_without_the_new_fields_is_todays_loop(lrepo):
    """A LoopState that predates wl_prscope's local-first fields reads as `turbo_push: pr`."""
    st = lstate(lrepo)
    for name in ("turbo_push", "local_batch", "backup_push_h"):
        delattr(st, name)
    text, blocking = wl_checks.loop_next_text(st, lrepo, {}, False)
    assert blocking is True, text
    assert "Open it" in text, text


def test_lf2_a_ready_local_batch_blocks_with_the_batch_open_sequence(lrepo):
    st = ready(lrepo)
    text, blocking = wl_checks.loop_next_text(st, lrepo, {}, False, me="d778be9d")
    assert blocking is True, text
    assert text.startswith("LOOP NEXT: the turbo batch on %s is complete" % BRANCH), text
    order = [
        "npm run ci   ",
        "npm run ci:quick",
        "droppedTouched",
        "rediacc_ci.testrun.e2e --workers 1",
        "git push -u origin %s" % BRANCH,
        "worklist.py --batch-body d778be9d",
        "gh pr create --draft --base main --head %s --body-file" % BRANCH,
    ]
    at = [text.find(step) for step in order]
    assert all(i >= 0 for i in at), (at, text)
    assert at == sorted(at), (at, text)
    for rel in st.plans:
        assert rel.rsplit("/", 1)[-1] in text, (rel, text)


def test_lf2_the_printed_body_names_every_batch_plan(wl):
    """`worklist.py --batch-body <me>` prints plan_gate.batch_body: the queue head plus every plan the hook named for the branch."""
    base_world(wl)
    wl.git("switch", "-q", "-c", BRANCH)
    own, nxt = plans(wl)
    other = loop_plan(wl, "named-two", opened=1, done=0)
    write_queue(wl, own, nxt, other)
    record = pathlib.Path(str(wl.wl)[: -len(".md")] + ".turbo-named.json")
    record.write_text(json.dumps({BRANCH: [nxt, other]}), encoding="utf-8")
    got = wl.cli("--batch-body", wlfix.ME)
    assert got.rc == 0, got.err
    line = next((ln for ln in got.out.splitlines() if ln.startswith("Plan:")), "")
    for rel in (own, nxt, other):
        assert rel in line, (rel, got.out)


def test_lf2_control_batch_body_refuses_a_bad_call(wl):
    got = wl.cli("--batch-body")
    assert got.rc == 2, got.err
    assert "usage: --batch-body" in got.err, got.err


def test_lf_mutation_turbo_push_read_as_pr_turns_lf1_and_lf2_red(lrepo, monkeypatch):
    """Mutation control: with turbo_push always read as `pr`, the LF1 world blocks with "Open it" and the LF2 world never names the batch sequence, so both cases depend on the mode."""
    monkeypatch.setattr(wl_checks, "turbo_push_mode", lambda _state: "pr")
    text, blocking = wl_checks.loop_next_text(lstate(lrepo), lrepo, {}, False)
    assert blocking is True, "m: LF1 survived the mutation: %s" % text
    assert "Open it" in text, "m: LF1 survived the mutation: %s" % text
    text, blocking = wl_checks.loop_next_text(ready(lrepo), lrepo, {}, False)
    assert "LOOP NEXT: the turbo batch" not in text, "m: LF2 survived the mutation: %s" % text


def test_lf4_turbo_next_names_picks_on_a_no_pr_local_batch(lrepo):
    st = lstate(lrepo)
    text = wl_checks.turbo_next_text(st, lrepo, 0)
    assert text.startswith("TURBO NEXT:"), text
    assert "the local batch on %s" % BRANCH in text, text
    assert "TURBO: start %s on a writer (slot 1 of 4)" % st.turbo_picks[0] in text, text
    assert "PR #" not in text, text


def test_lf4_turbo_next_is_silent_on_a_live_batch_end_pr(lrepo):
    st = lstate(lrepo, kind=wl_prscope.LIVE, pr=543, local_batch=False)
    assert wl_checks.turbo_next_text(st, lrepo, 0) == ""


def test_lf4_control_pr_mode_names_picks_on_the_live_pr(lrepo):
    st = lstate(lrepo, kind=wl_prscope.LIVE, pr=543, local_batch=False, turbo_push="pr")
    text = wl_checks.turbo_next_text(st, lrepo, 0)
    assert "PR #543 has 4 free writer slot(s) of 4" in text, text
    assert "TURBO: start %s" % st.turbo_picks[0] in text, text


def test_lf4_control_a_no_pr_branch_in_pr_mode_names_nothing(lrepo):
    st = lstate(lrepo, turbo_push="pr", local_batch=False)
    assert wl_checks.turbo_next_text(st, lrepo, 0) == ""


def test_lf4_a_closed_batch_end_pr_is_offered_for_merge_once_its_set_is_finished(lrepo):
    """D3: the batch closed when the PR opened, so a queue that gained an eligible plan since (`turbo_more`) cannot hold the merge while turbo-next stays silent."""
    st = ready(lrepo, kind=wl_prscope.LIVE, pr=543, local_batch=False, finished=1)
    text, blocking = wl_checks.loop_next_text(st, lrepo, {}, False)
    assert blocking is True, text
    assert "run /pr-merge" in text, text
    text, _b = wl_checks.loop_next_text(
        ready(lrepo, kind=wl_prscope.LIVE, pr=543, local_batch=False, finished=1, turbo_push="pr"),
        lrepo,
        {},
        False,
    )
    assert text == "", "control: pr mode still waits for the batch: %s" % text


def test_lf8_the_judge_sanitiser_strips_a_pr_order_only_in_a_local_batch():
    for order in (
        "Run gh pr create --draft for the branch now.",
        "Open the draft PR so CI can run.",
        "open a PR for 1008-1",
    ):
        out = wl_judge.sanitize_next_action({"next_action": order}, local_batch=True)
        assert out["next_action"].startswith("[rejected by the stop gate"), (order, out)
        assert "turbo batch" in out["next_action"], out
        kept = wl_judge.sanitize_next_action({"next_action": order}, local_batch=False)
        assert kept["next_action"] == order, ("pr mode keeps it", kept)
    work = "Tick LF-W2's next box and commit the verified unit."
    assert (
        wl_judge.sanitize_next_action({"next_action": work}, local_batch=True)["next_action"]
        == work
    )


def test_lf8_the_judge_paragraph_rides_only_a_filling_local_batch(lrepo):
    assert wl_checks._judge_local_batch(lstate(lrepo), lrepo) == {"finished": 1, "batch": 3}
    assert wl_checks._judge_local_batch(ready(lrepo), lrepo) is None
    assert wl_checks._judge_local_batch(lstate(lrepo, turbo_push="pr"), lrepo) is None
    assert wl_checks._judge_local_batch(None, lrepo) is None
    text = M.JUDGE_LOCAL_BATCH % {"finished": 1, "batch": 3}
    assert "never advise a\npush, a PR or a CI run" in text.replace("Never", "never"), text


# ---- integration: the real hook, where wl_prscope computes local_batch ----------------------------


def local_world(fix, turbo_push: str = "batch-end", turbo: bool = True):
    base_world(fix)
    fix.git("switch", "-q", "-c", BRANCH)
    own, nxt = plans(fix)
    write_queue(fix, own, nxt)
    fix.settings(turbo=turbo, turbo_push=turbo_push, batch_size=3)
    for i in range(5):
        (fix.proj / ("w%d.txt" % i)).write_text("%d\n" % i, encoding="utf-8")
        fix.git("add", "w%d.txt" % i)
        fix.git("commit", "-qm", "work %d" % i)
    return own, nxt


def test_lf1_live_hook_a_local_batch_never_says_open_it(wl):
    local_world(wl)
    got = stop(wl)
    assert "loop-next" not in keys_of(wl, got), reason(got)[:1500]
    assert "Open it" not in got.out, got.out[:1500]


def test_lf1_live_hook_control_pr_mode_says_open_it(wl):
    local_world(wl, turbo_push="pr")
    got = stop(wl)
    assert "loop-next" in keys_of(wl, got), reason(got)[:1500]
    assert "Open it" in reason(got), reason(got)[:1500]


def test_lf9_a_filling_local_batch_with_nothing_ahead_works_the_queue_head(lrepo):
    """6224a610.2: N_TURBO_LOCAL names the commits on the branch, so with none ahead of origin/main it was a lie; the arm falls through to the queue-head order."""
    _git(lrepo, "update-ref", "refs/remotes/origin/main", _git(lrepo, "rev-parse", "HEAD"))
    text, blocking = wl_checks.loop_next_text(lstate(lrepo), lrepo, {}, False, me="d778be9d")
    assert "TURBO LOCAL-FIRST" not in text, text
    assert blocking is True, text
    assert "0 commit" not in text, text
    assert text.strip(), text


def _finished_world(tmp_path, open_box):
    """A stub at agent/plans/PLAN-moved.md that moved to _done/, whose real text has one box, open or ticked."""
    plans = tmp_path / "agent" / "plans"
    (plans / "_done").mkdir(parents=True)
    (plans / "PLAN-moved.md").write_text(
        "# PLAN: moved (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-moved.md\n",
        encoding="utf-8",
    )
    box = (
        "- [ ] T1 the one remaining unit of work"
        if open_box
        else "- [x] T1 the one remaining unit of work"
    )
    (plans / "_done" / "PLAN-moved.md").write_text(
        "# PLAN: moved\nStatus: draft\n\n## Tasks\n\n%s\n" % box, encoding="utf-8"
    )
    return types.SimpleNamespace(plans=("agent/plans/PLAN-moved.md",))


def test_a_moved_plan_with_an_open_box_is_not_finished(tmp_path):
    """The Stop hook read the stub and saw no box, so it ordered a push the turbo guard then refused (d6a6e18b5). The set is judged through Moved-To."""
    assert wl_checks._set_finished(_finished_world(tmp_path, open_box=True), str(tmp_path)) is False


def test_control_a_moved_plan_with_every_box_ticked_is_finished(tmp_path):
    assert wl_checks._set_finished(_finished_world(tmp_path, open_box=False), str(tmp_path)) is True


def test_an_unreadable_plan_is_not_finished(tmp_path):
    """A stub whose Moved-To points at a missing file cannot be read, and an unreadable plan is never finished."""
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    (plans / "PLAN-gone.md").write_text(
        "# PLAN: gone (moved)\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-missing.md\n",
        encoding="utf-8",
    )
    state = types.SimpleNamespace(plans=("agent/plans/PLAN-gone.md",))
    assert wl_checks._set_finished(state, str(tmp_path)) is False
    assert wl_checks._open_in_set(state, str(tmp_path)) == "PLAN-gone.md (unreadable)"


def test_an_empty_plan_set_is_not_finished(tmp_path):
    """An empty set was vacuously finished, which would order a push for a batch of nothing."""
    assert wl_checks._set_finished(types.SimpleNamespace(plans=()), str(tmp_path)) is False


def test_the_local_batch_advisory_names_the_plans_still_open(tmp_path):
    """ "batch 3/3 finished" alone read as complete while two turbo-named plans were open; the advisory names them."""
    state = _finished_world(tmp_path, open_box=True)
    assert wl_checks._open_in_set(state, str(tmp_path)) == "PLAN-moved.md (1 open)"


def test_control_a_ticked_batch_names_nothing_open(tmp_path):
    state = _finished_world(tmp_path, open_box=False)
    assert wl_checks._open_in_set(state, str(tmp_path)) == "none"

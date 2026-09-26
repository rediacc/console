"""THE PRIORITY LADDER (wl_checks.PRIORITY_LADDER): the ordered, mandatory list that decides which outstanding check a crowded stop actually surfaces, the invariant tier's collapse, and the pr-babysit finish line.

Ported from `.claude/hooks/stop/worklist-cases/23-priority-ladder.sh`, one pytest function per numbered bash case, except where a bash leg continued its predecessor's world with no fresh setup: those legs stay inside one function, where the sequence is visible in one place.

WHY THIS BATTERY EXISTS. Rotation used to break ties on the position of a `vadd` call in a 5,000-line file, and every never-served key ties at -1, so line order decided the FIRST pick of every crowded session. Nothing tested that, because line order is not a behaviour anyone thinks to assert, which is how an owed check came to sort 24th while its escalation
ladder burned a rung per stop, unseen.

The bash file got `clfile`, `cldeliver`, `ci_setup`, `ci_rollup` and `ci_job` by being sourced after 19-checklists.sh and 09-ci-status.sh; here they are imported from the two modules those files became, so there is still exactly one definition of each.
"""

from __future__ import annotations

import json
import re
import shutil

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_checklists import cldeliver, clfile
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_rollup, ci_setup
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# One work loop, the canonical cron shape.
WORK_ONLY_CRONS = '[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'

# The checklist 231b plants: its only mission member is a wave, whose `vadd` sits ~500 lines BELOW `brief` in the battery.
CL_HANDED = """# Handoff checklist: demo
Status: executing
Owner: deadbeef

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: the thing this session was handed
"""


def prf_log(fix, round_no) -> None:
    """(re)write the fixture round log: APPEND ONLY, never a truncating redirect.

    `rm` then append, because block-roundlog-truncate.sh refuses any command that could replace a pr-babysit round log wholesale, and it is right to: a `>` redirect there is byte-for-byte the shape that destroyed a real round history on 2026-08-19. A fixture is not an exception worth carving. This Python writes to a FIXTURE path under the tmp sandbox rather than to a real round
    log, so the hazard is not the same one, but the reason travels with the fixture.
    """
    path = fix.base / "projects" / "reports" / "pr-babysit-agenttest.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            "## Wave header\nintent: the thing\n\n## STATUS (round %s)\nwatching\n" % round_no
        )


def prf_run(fix, message: str = "work done", extra_env=None):
    """A Stop event with the CI check armed AND a projects dir.

    Local to this module: `ci_run` beside `ci_setup` serves the CI battery and carries no WORKLIST_PROJECTS_DIR, which is the one thing the finish-line cases need, and it takes no extra environment.
    """
    payload = json.dumps(
        {
            "session_id": fix.sid,
            "cwd": str(fix.proj),
            "last_assistant_message": message,
            "session_crons": [],
            "background_tasks": [],
        }
    )
    env = dict(fix.env)
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    env["TMPDIR"] = str(fix.base / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    env["WORKLIST_TASKS_DIR"] = str(fix.base / "tasks")
    env["WORKLIST_PUBLISH_REF"] = "pub"
    env["WORKLIST_PROJECTS_DIR"] = str(fix.base / "projects")
    env["WORKLIST_JUDGE"] = "off"
    env["GITHUB_ACTIONS"] = fix.gha
    if extra_env:
        env.update(extra_env)
    return fix.python([], stdin=payload, env=env)


def test_231_the_ladder_decides_the_first_pick_where_line_order_used_to(wl):  # noqa: F811
    """The operator's ask: "There should be list of 'has to show with this order'".

    READ THE SORT KEY IN wl_checks BEFORE CHANGING THIS CASE. Tier sits AFTER `served`, not before it, so the ladder is WALKED rather than camped on: on the first stop every key is unserved and tier decides, and afterwards the least-recently-served wins with tier breaking its ties. Camping on the top tier would starve docs drift, a stale PR body and an unpushed submodule pointer
    for as long as one item is open, which is most of a session. The part of the operator's ask that starvation was reaching for is delivered by guard (F) instead: T_MISSION defeats the cadence pause, so the session is never RELEASED while the job is unfinished (case 214g).

    Two rotating checks, one T_MISSION (the open item) and one T_HYGIENE (the missing session brief), both never served. The mission one must go first, where under the old tiebreak that was decided by which `vadd` call sat earlier in a 5,000-line file. The second stop is the CONTROL and its order is load-bearing, so it stays here rather than in a function of its own.
    """
    wl.hand_now()  # so `agent-state` is not a third check
    wl.add_item("- [ ] (deadbeef) the mission item")
    # No '## Remaining' section, which is the T_HYGIENE member (`no-remaining`; the missing session brief filled this role until that check was deleted 2026-09-24).
    wl.say("status update")
    first = wl.run()
    wl.newturn()
    wl.say("status update again")
    second = wl.run()
    assert "OPEN worklist item" in first.out, (
        "231: the first pick was not the mission item: %s" % first.out[:300]
    )
    assert "OPEN worklist item" not in wlfix.quoted(second.out), (
        "231 CONTROL: the mission tier starved the hygiene tier: %s" % second.out[:300]
    )


def test_231b_a_mission_check_defined_later_in_the_battery_still_wins(wl):  # noqa: F811
    """The same two checks, ORDER REVERSED by the ladder and not by line number. The assertion in 231 is only meaningful if the opposite arrangement produces the opposite first pick for the same reason. `brief` is defined EARLIER in the battery than several mission checks, so under the old line-order tiebreak a hygiene check could and did win a first pick. Here the only mission
    member is a checklist wave, whose `vadd` sits ~500 lines BELOW `brief`, so line order would pick the brief and the ladder must not.
    """
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_HANDED)
    wl.say("status update\n\n## Remaining\n- nothing")
    got = wl.run()
    lineorder = "231b: line order is still deciding the first pick: %s" % got.out[:300]
    assert "w1" in got.out, lineorder
    assert "session brief is missing" not in wlfix.quoted(got.out), lineorder


def plant_unread_report(fix) -> None:
    """An unread teammate report old enough to have graduated, which is the `unread-reports` invariant."""
    store = fix.base / "reports"
    (store / "agenttest").mkdir(parents=True, exist_ok=True)
    (store / "agenttest" / "r.md").write_text(
        "A TEAMMATE FINDING NOBODY READ\nbody", encoding="utf-8"
    )
    (store / "index.jsonl").write_text(
        json.dumps(
            {
                "ev": "report",
                "id": "abcdef123456",
                "at": "2026-01-01T10:00:00Z",
                "branch": "agenttest",
                "agent": "some-teammate",
                "type": "some-teammate",
                "session": "deadbeef",
                "body": "agenttest/r.md",
                "bytes": 900,
                "silent": False,
                "sends": 1,
                "title": "A TEAMMATE FINDING NOBODY READ",
                "transcript": "",
                "src": "hook",
            }
        )
        + "\n",
        encoding="utf-8",
    )


# An announced question with no AskUserQuestion call, which is the `pending-ask` invariant (test_wl_cadence case 223 owns its controls).
PENDING_ASK_MSG = """status

## Remaining
- nothing outstanding

Two questions for you before I pick the branch."""


def test_232_the_collapse_three_invariants_two_quoted_the_third_named(wl):  # noqa: F811
    """The invariant tier buys UN-ROTATABILITY and nothing more. The battery's own warning, that a prompt which fires always is a prompt that gets skimmed, is the constraint, and three promotions in one change is exactly when it bites. NOTHING IS DROPPED: the third is named on one line with its opening sentence.

    THE NEEDLES ARE HEADLINES, NOT KEYS, and that is not a stylistic choice: a QUOTED invariant renders its message, which never contains its own key, so grepping for `unread-reports` passed only for whichever one got collapsed, an assertion that would have gone green on a hook that dropped the other two. A headline matches both ways, because the collapse line is exactly "<key>:
    <that message's first line>".

    Rebuilt 2026-09-24 on three invariants that survive the removal of cross-session messaging (it was a peer request, an unheard ask and an unread report).
    """
    wl.crons = WORK_ONLY_CRONS
    wl.brief_now()
    # invariant 1: no agent/<me>/ folder, so the bootstrap wall.
    shutil.rmtree(wl.proj / "agent" / "deadbeef", ignore_errors=True)
    # invariant 2: an announced question never asked.
    wl.say(PENDING_ASK_MSG)
    # invariant 3: an unread teammate report.
    plant_unread_report(wl)
    got = wl.run()
    assert "ALSO BLOCKING, IN BRIEF" in got.out, (
        "232: no collapse block with three invariants: %s" % got.out[:400]
    )
    # NOTHING SILENTLY DROPPED. Every one of the three is present, in full or as a named line; this is the assertion that separates a collapse from a truncation.
    missing = [
        needle
        for needle in (
            "you have no agent/deadbeef/ folder",
            "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
            "UNREAD SUB-AGENT REPORTS",
        )
        if needle not in got.out
    ]
    assert not missing, "232: the collapse DROPPED an invariant instead of naming it: %s" % missing


def test_232b_control_two_invariants_are_both_quoted_with_no_collapse_line(wl):  # noqa: F811
    """ALWAYS_FULL_MAX is 2, so at the boundary the block must look exactly as it did before this change. A collapse that fired at two would be a regression wearing the new feature's clothes. One planted fact apart from 232: the report store is empty."""
    wl.crons = WORK_ONLY_CRONS
    wl.brief_now()
    shutil.rmtree(wl.proj / "agent" / "deadbeef", ignore_errors=True)
    wl.say(PENDING_ASK_MSG)
    got = wl.run()
    boundary = "232b CONTROL: the boundary is wrong: %s" % got.out[:400]
    assert "you have no agent/deadbeef/ folder" in got.out, boundary
    assert "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT" in got.out, boundary
    assert "ALSO BLOCKING, IN BRIEF" not in got.out, boundary


def test_233_the_pr_babysit_finish_line_blocks_a_green_but_unfinished_wave(wl):  # noqa: F811
    """The operator's example, generalised: reaching green is not reaching the finish line. `.claude/commands/pr-babysit.md` states it, "The console PR rides as a draft until green; stops at green + Claude-reviewed + threads-resolved PRs", and before this change nothing held the wave open once ci-red went quiet.

    233b is the CONTROL and 233c the evidence ladder; both continue on this world with no fresh setup, so they stay here. 233b is the gate that stops this becoming a tax on every session that happens to have a PR open: same PR, same green, no pr-babysit wave, not one word. 233c pins that the hook cannot see a review marker or a resolved thread and refuses to pretend it can: the
    boxes are closed by ticking a worklist item carrying the token, which is the same linkage agent/programs/<slug>/CHECKLIST.md uses.

    The bash quoted every markdown checkbox through `grep -qF --`, because a leading dash reads as an option bundle and dies with an error that looks exactly like a legitimate assertion failure. Python's `in` carries no such hazard, so the boxes below are quoted plainly.
    """
    ci_setup(wl)
    (wl.base / "projects" / "reports").mkdir(parents=True, exist_ok=True)
    prf_log(wl, 3)
    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    got = prf_run(wl)
    unfinished = "233: the finish line did not hold a green-but-unfinished wave: %s" % got.out[:500]
    assert "THE WAVE IS NOT FINISHED" in got.out, unfinished
    assert "- [x] green" in got.out, unfinished
    assert "pr:543/reviewed" in got.out, unfinished

    # 233b CONTROL: no round log for this branch, not one word.
    (wl.base / "projects" / "reports" / "pr-babysit-agenttest.md").unlink(missing_ok=True)
    got = prf_run(wl)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233b CONTROL: fired at a session running no wave at all: %s" % got.out[:400]
    )

    # 233c: the last two boxes are TICKED BY EVIDENCE, and then it stops.
    prf_log(wl, 4)
    reviewed = wl.cli("--add", "deadbeef", "pr:543/reviewed request the Claude review")
    threads = wl.cli("--add", "deadbeef", "pr:543/threads resolve the review threads")
    rid = re.search(r"#([0-9a-f]+)", reviewed.out).group(1)
    tid = re.search(r"#([0-9a-f]+)", threads.out).group(1)
    # FOCUS=off, and the reason is worth stating: adding the two claim items makes `open-items` and the idle-stall gate outstanding too, and the focused block surfaces ONE rotating check per stop.
    # Asserting the finish line's text through a rotation would be asserting the rotation, not the box. This case is about what the finish line SAYS about an open claim, so it reads the dump-all block.
    focus_off = {"WORKLIST_FOCUS": "off"}
    got = prf_run(wl, extra_env=focus_off)
    assert "- [ ] Claude-reviewed" in got.out, (
        "233c: an open claim ticked the box: %s" % got.out[:400]
    )

    wl.cli("--tick", "deadbeef", rid, "https://github.com/fake/repo/pull/543#pullrequestreview-1")
    wl.cli(
        "--tick", "deadbeef", tid, "https://github.com/fake/repo/pull/543#discussion_r1 resolved"
    )
    got = prf_run(wl, extra_env=focus_off)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233c: still blocking after the wave finished: %s" % got.out[:400]
    )

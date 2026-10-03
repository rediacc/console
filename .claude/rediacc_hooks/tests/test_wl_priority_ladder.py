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
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_checklists import cldeliver, clfile
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_running, ci_setup
from rediacc_hooks.tests.test_wl_ci_status import ci_rollup as ci_status_rollup
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


def prf_run(fix, message: str = "work done", extra_env=None, bg=None):
    """A Stop event with the CI check armed AND a projects dir.

    Local to this module: `ci_run` beside `ci_setup` serves the CI battery and carries no WORKLIST_PROJECTS_DIR, which is the one thing the finish-line cases need, and it takes no extra environment.
    """
    payload = json.dumps(
        {
            "session_id": fix.sid,
            "cwd": str(fix.proj),
            "last_assistant_message": message,
            "session_crons": [],
            "background_tasks": wlfix.with_waker(bg or [], fix.waker),
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
    """The operator's example, generalised: reaching green is not reaching the finish line. `.claude/commands/pr-babysit.md` states it (green, ready, per-commit reviews clean, human threads resolved), and before this change nothing held the wave open once ci-red went quiet.

    233b is the CONTROL and 233c the evidence ladder; both continue on this world with no fresh setup, so they stay here. 233b is the gate that stops this becoming a tax on every session that happens to have a PR open: same PR, same green, no pr-babysit wave, not one word. 233c pins that the hook cannot see a resolved thread and refuses to pretend it can: the
    threads box is closed by ticking a worklist item carrying the token, while the per-commit review box is read live off agent/reviews/<branch>/ (this fixture has no branch commits past a base, so it reads clean), which is the same linkage agent/programs/<slug>/CHECKLIST.md uses.

    The bash quoted every markdown checkbox through `grep -qF --`, because a leading dash reads as an option bundle and dies with an error that looks exactly like a legitimate assertion failure. Python's `in` carries no such hazard, so the boxes below are quoted plainly.
    """
    ci_setup(wl)
    (wl.base / "projects" / "reports").mkdir(parents=True, exist_ok=True)
    prf_log(wl, 3)
    # A green head includes the terminal gate: since PLAN-ci-verdict box A, `ci_gate` reads green only when `CI Complete` reported SUCCESS.
    ci_status_rollup(
        wl,
        "SUCCESS",
        "[%s,%s]"
        % (ci_job("Quality / Static", "SUCCESS"), ci_job("CI Complete", "SUCCESS", 90784763856)),
    )
    got = prf_run(wl)
    unfinished = "233: the finish line did not hold a green-but-unfinished wave: %s" % got.out[:500]
    assert "THE WAVE IS NOT FINISHED" in got.out, unfinished
    assert "- [x] green" in got.out, unfinished
    assert "pr:543/threads" in got.out, unfinished
    assert "- [x] per-commit reviews clean" in got.out, unfinished

    # 233b CONTROL: no round log for this branch, not one word.
    (wl.base / "projects" / "reports" / "pr-babysit-agenttest.md").unlink(missing_ok=True)
    got = prf_run(wl)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233b CONTROL: fired at a session running no wave at all: %s" % got.out[:400]
    )

    # 233c: the threads box is TICKED BY EVIDENCE, and then it stops.
    prf_log(wl, 4)
    threads = wl.cli("--add", "deadbeef", "pr:543/threads resolve the review threads")
    tid = re.search(r"#([0-9a-f]+)", threads.out).group(1)
    # FOCUS=off, and the reason is worth stating: adding the claim item makes `open-items` and the idle-stall gate outstanding too, and the focused block surfaces ONE rotating check per stop.
    # Asserting the finish line's text through a rotation would be asserting the rotation, not the box. This case is about what the finish line SAYS about an open claim, so it reads the dump-all block.
    focus_off = {"WORKLIST_FOCUS": "off"}
    got = prf_run(wl, extra_env=focus_off)
    assert "- [ ] threads resolved" in got.out, (
        "233c: an open claim ticked the box: %s" % got.out[:400]
    )

    wl.cli(
        "--tick", "deadbeef", tid, "https://github.com/fake/repo/pull/543#discussion_r1 resolved"
    )
    got = prf_run(wl, extra_env=focus_off)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233c: still blocking after the wave finished: %s" % got.out[:400]
    )


def test_233d_a_live_watch_on_a_head_with_no_verdict_stands_the_finish_line_down(wl):  # noqa: F811
    """While CI is still running, green cannot tick and ready cannot either, so blocking there demanded what no work in the turn can produce (PR #592, 2026-10-03). A running ci-trace watch on this head is the wake-up, the rule ci-red already follows (test_126). The CONTROL is the same world without the watch: it must still block, or the stand-down is unconditional."""
    ci_setup(wl)
    (wl.base / "projects" / "reports").mkdir(parents=True, exist_ok=True)
    prf_log(wl, 5)
    threads = wl.cli("--add", "deadbeef", "pr:543/threads resolve the review threads")
    found = re.search(r"#([0-9a-f]+)", threads.out)
    assert found, threads.out
    tid = found.group(1)
    wl.cli(
        "--tick", "deadbeef", tid, "https://github.com/fake/repo/pull/543#discussion_r1 resolved"
    )
    ci_status_rollup(
        wl,
        "PENDING",
        "[%s,%s]" % (ci_job("Quality / Static", "SUCCESS"), ci_running("CI Complete")),
    )
    watch = [
        {
            "id": "w1",
            "status": "running",
            "description": "watch CI",
            "command": ".ci/scripts/ci/ci-trace.py --wait --until-final",
        }
    ]
    focus_off = {"WORKLIST_FOCUS": "off"}
    got = prf_run(wl, extra_env=focus_off, bg=watch)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233d: a live watch on a running head still blocked the finish line: %s" % got.out[:500]
    )
    # CONTROL: no watch, same world, still blocks.
    got = prf_run(wl, extra_env=focus_off)
    assert "THE WAVE IS NOT FINISHED" in got.out, (
        "233d CONTROL: the finish line stood down with no watch armed: %s" % got.out[:500]
    )

    # 233e: a per-commit reviewer still running is the same kind of wait. One branch commit past origin/main whose reviewer lock is inside its spawn grace window reads `in_flight`; the CONTROL drops the lock, so the commit reads `uncovered` and the finish line blocks again.
    base = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/main", base)
    (wl.proj / "b.txt").write_text("b\n", encoding="utf-8")
    wl.git("add", "b.txt")
    wl.git("commit", "-qm", "branch work")
    sha = wl.git("rev-parse", "HEAD").stdout.strip()
    locks = wl.base / "tmp" / "claude-worklist" / "reviews" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock = locks / ("%s.lock" % sha)
    lock.write_text(json.dumps({"pid": None, "start": time.time()}), encoding="utf-8")
    got = prf_run(wl, extra_env=focus_off, bg=watch)
    assert "THE WAVE IS NOT FINISHED" not in got.out, (
        "233e: a running reviewer on a running head still blocked the finish line: %s"
        % got.out[:500]
    )
    lock.unlink()
    got = prf_run(wl, extra_env=focus_off, bg=watch)
    assert "THE WAVE IS NOT FINISHED" in got.out, (
        "233e CONTROL: an unreviewed commit with no reviewer running stood the finish line down: %s"
        % got.out[:500]
    )


def _prr_state(rc: int, title: str = "", unresolved=()) -> dict:
    """One wl_prreview.check_state() result, shaped as the real one is."""
    return {
        "rc": rc,
        "pr": 543,
        "head": "deadsha0000",
        "summary": "991" if rc != 2 else "",
        "verdict": {0: "answered", 1: "unanswered", 2: "unreadable"}[rc],
        "unresolved": list(unresolved),
        "review_token": title,
        "reason": "summary 991 on PR #543 has no substantive reply" if rc == 1 else "gh down",
    }


def _prr_fake(result: dict):
    calls: list = []

    def check(pr, _runner=None):
        calls.append(pr)
        return dict(result)

    return check, calls


PRR_INFO = {"pr": 543, "sha": "deadsha00001234"}


def test_234_the_pr_review_nudge_names_draft_and_answer_on_an_unanswered_summary():
    """GR9 (agent/plans/PLAN-github-pr-review-restore.md): a green head whose review summary is unanswered blocks with the --draft/--answer line, bounded by wl_ci.CI_MAX_BLOCKS per signature, then rides the advisory queue. The read is memoised per head, so the second stop inside the TTL makes no gh call."""
    checks = wlfix.import_wl("wl_checks")
    wl_ci = wlfix.import_wl("wl_ci")
    check, calls = _prr_fake(_prr_state(1))
    doc: dict = {}
    block, note, once = checks.prreview_nudge(doc, PRR_INFO, check, now=1000.0)
    assert "wl_prreview.py --draft --pr 543" in block, block
    assert "wl_prreview.py --answer <file> --pr 543" in block, block
    assert "BEFORE pushing" in block, block
    assert note == "", note
    assert once == "", once
    assert calls == [543], calls
    # The ceiling: after CI_MAX_BLOCKS blocks the same signature downgrades to the recurring note.
    for _ in range(wl_ci.CI_MAX_BLOCKS - 1):
        block, note, once = checks.prreview_nudge(doc, PRR_INFO, check, now=1001.0)
        assert block, "blocked fewer than CI_MAX_BLOCKS stops"
    block, note, once = checks.prreview_nudge(doc, PRR_INFO, check, now=1002.0)
    assert block == "", block
    assert "wl_prreview.py --draft" in note, note
    assert calls == [543], "the memo did not hold inside the TTL: %s" % calls
    # Focus mode blocks too: `pr-review` is on wl_standdown._FOCUS_ONLY (Review Complete is required, operator ruling 2026-10-03).
    block, note, _ = checks.prreview_nudge({}, PRR_INFO, check, focus=True, now=1000.0)
    assert "wl_prreview.py --answer" in block, block
    assert "pr-review" in wlfix.import_wl("wl_standdown")._FOCUS_ONLY


def test_234b_a_failed_review_run_yields_the_investigate_line():
    """Review Complete is a required check and only an LLM outage is excused, so `failed-run` is a defect to fix: the line names the investigation and the re-dispatch, even with the summary answered (rc 0)."""
    checks = wlfix.import_wl("wl_checks")
    check, _ = _prr_fake(_prr_state(0, title="failed-run"))
    block, note, once = checks.prreview_nudge({}, PRR_INFO, check, now=1000.0)
    assert "REVIEW RUN FAILED" in block, block
    assert "gh workflow run claude-review.yml -f pr_number=543" in block, block
    assert "wl_prreview.py --draft" not in block, block
    assert note == "", note
    assert once == "", once


def test_234c_control_an_answered_review_and_an_outage_say_nothing():
    """CONTROL: rc 0 with no token, and rc 0 with the excused `outage` token, are silent."""
    checks = wlfix.import_wl("wl_checks")
    for title in ("", "outage", "current"):
        check, _ = _prr_fake(_prr_state(0, title=title))
        got = checks.prreview_nudge({}, PRR_INFO, check, now=1000.0)
        assert got == ("", "", ""), (title, got)
    # No PR number or no head sha: no read at all.
    check, calls = _prr_fake(_prr_state(1))
    assert checks.prreview_nudge({}, {"pr": None, "sha": "x"}, check) == ("", "", "")
    assert calls == []


def test_234d_an_unreadable_review_is_noted_once_per_head():
    """rc 2 is one note per head; a new head notes again, and a raising check reads as unreadable rather than escaping."""
    checks = wlfix.import_wl("wl_checks")
    check, _ = _prr_fake(_prr_state(2))
    doc: dict = {}
    first = checks.prreview_nudge(doc, PRR_INFO, check, now=1000.0)
    assert first[:2] == ("", ""), first
    assert "could not be read" in first[2], first
    assert checks.prreview_nudge(doc, PRR_INFO, check, now=2000.0) == ("", "", "")
    other = dict(PRR_INFO, sha="beefsha00009999")
    assert "could not be read" in checks.prreview_nudge(doc, other, check, now=2001.0)[2]

    def boom(_pr, _runner=None):
        raise RuntimeError("no gh")

    got = checks.prreview_nudge({}, PRR_INFO, boom, now=1000.0)
    assert "RuntimeError: no gh" in got[2], got


def test_234e_the_review_runner_is_bounded():
    """The gh budget: a spent wall-clock budget answers rc 124 without running gh, so a hung API cannot hold the stop."""
    checks = wlfix.import_wl("wl_checks")
    run = checks.prreview_runner(".", budget_s=0)
    rc, out, err = run(["api", "user"])
    assert rc == 124, (rc, err)
    assert out == "", out
    assert "budget" in err, err

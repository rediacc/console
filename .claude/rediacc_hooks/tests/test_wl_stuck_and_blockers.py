"""The runner no-op, the stuck-stop counter and what counts as movement, and the cited-blocker requirement. Ported from `.claude/hooks/stop/worklist-cases/04-stuck-and-blockers.sh`.

One test per numbered bash case, with the same assertions in the same order against the same subprocess. Four chains have no fixture of their own and must stay in one function: 47 and 48 flip one environment variable on the world 46 built, 50 and 51 are the third and fourth stop of the sequence 49 starts, 55 continues committing on the repository 54 left at three stops, and 63
asserts about the very output 62 produced.
"""

from __future__ import annotations

import json
import subprocess
import sys

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PROBE = """import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(%s)
"""


def probe(fix, expression: str) -> str:
    """Load the hook as a MODULE and print one expression, returning stdout and stderr together.

    A LOCAL HELPER for cases 62 to 64, which test a function rather than a hook run: the bash used the same importlib snippet, and case 63's whole subject is that this import must not execute the Stop path.
    """
    proc = subprocess.run(
        [sys.executable, "-c", PROBE % expression, str(fix.hook)],
        cwd=str(fix.proj),
        capture_output=True,
        text=True,
        env=fix.env,
        check=False,
    )
    return proc.stdout + proc.stderr


def test_46_an_open_item_blocks_off_a_runner_and_47_48_the_runner_no_op(wl):  # noqa: F811
    """46 is the CONTROL for 47: the same worklist and the same open item, one environment variable different. Without the control, 47 would pass even if the hook had stopped blocking entirely. 48 is the other half: a value other than 'true' is not a runner."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.add_item("- [ ] (deadbeef) an item nobody will ever answer")
    wl.check("block", "OPEN worklist item", "an open item blocks in a normal session")

    wl.gha = "true"
    wl.check("allow", "", "GITHUB_ACTIONS=true never blocks a runner")

    wl.gha = "false"
    wl.check("block", "OPEN worklist item", "GITHUB_ACTIONS=false still blocks")


def test_49_two_identical_stops_are_quiet_50_the_third_fires_51_it_resets(wl):  # noqa: F811
    """49 is the CONTROL that the counter is a counter: two identical stops must NOT trip it. 50 is the fire on the third, and 51 pins that the nag is rate-limited rather than every-stop, so stop 4 is quiet again."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "stop 1 of 3 is quiet")
    wl.check("allow", "", "stop 2 of 3 is still quiet")
    wl.check(
        "block", "EMPLOY A PLANNING OR INVESTIGATION AGENT", "3 stops with nothing moved blocks"
    )
    wl.check("allow", "", "the nag is rate-limited, not every-stop")


def test_51b_control_with_only_deferrals_left_the_stuck_check_stays_quiet(wl):  # noqa: F811
    """THE DEFERRAL BLIND SPOT. The stuck check used to fire on whether something remained, which counts `[?]` deferrals. A `[?]` is BY CONSTRUCTION the one shape a session cannot advance, parked on the operator's decision or on a capability only they hold, so "nothing moved" is the CORRECT outcome there rather than a stall, and the remedy the check prints (delegate to a Plan or
    Explore agent) cannot work: the constraint is authority, not knowledge. Measured 2026-08-15, the two survivors were "set four Worker secrets with the operator's Cloudflare session" and "delete the last restore path once a machine has round-tripped a repo". The only way to satisfy the check was to spawn a decorative agent, that is, to game it.

    `[>]` deliberately still counts as actionable (case 53 covers it): work on a worker genuinely can stall, and the background-wait check reports that separately.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | blocked on the operator | deferred |")
    wl.add_item(
        "- [?] (deadbeef) set the four Worker secrets DEFAULT: hold, it needs the operator session"
    )
    wl.check("allow", "", "deferral-only stop 1 is quiet")
    wl.check("allow", "", "deferral-only stop 2 is quiet")
    # The third identical stop is where case 50 fires. It must NOT here.
    wl.check("allow", "", "deferral-only stop 3 does NOT demand an agent")


def test_51c_one_open_item_alongside_the_deferral_restores_the_demand(wl):  # noqa: F811
    """An open item blocks EVERY stop on its own account, so the first two assert the OTHER blocker by name: the point is that the stuck demand is absent until the third stop, and then present."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.add_item("- [?] (deadbeef) a parked question DEFAULT: hold")
    wl.add_item("- [ ] (deadbeef) something I can actually do")
    wl.check(
        "block", "OPEN worklist item", "mixed stop 1 blocks on the open item, not the stuck check"
    )
    wl.check(
        "block", "OPEN worklist item", "mixed stop 2 blocks on the open item, not the stuck check"
    )
    wl.check(
        "block",
        "EMPLOY A PLANNING OR INVESTIGATION AGENT",
        "an actionable item alongside a deferral still trips it",
    )


def test_52_a_task_changing_status_counts_as_movement(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "fresh signature, stop 1")
    wl.check("allow", "", "fresh signature, stop 2")
    # Same session, but the task moved. The counter must restart, not fire.
    wl.task(7, "in_progress", "thing")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n| #7 | thing | ongoing, me |")
    wl.check("allow", "", "moving a task resets the stuck counter")


def test_53_a_running_background_task_exempts_it(wl):  # noqa: F811
    """An agent IS the remedy the stuck check asks for."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.bg = json.dumps([{"status": "running", "description": "plan agent"}])
    wl.check("allow", "", "stop 1")
    wl.check("allow", "", "stop 2")
    wl.check("allow", "", "a live agent means the remedy is already running")


def test_54_a_commit_moves_the_signature_and_55_buys_slack_not_immunity(wl):  # noqa: F811
    """54 is THE MISSING CONTROL: a COMMIT must move the signature. Its absence is why a dead HEAD leg shipped. The hook resolved the repository from the worklist temporary directory, git returned nothing, and every commit was invisible.

    55 continues the same fixture, because a commit buys SLACK rather than immunity: committing every round leaves the tasks-only signature unmoved, so at twice the stuck rounds it fires. Case 54 already spent 3 stops and tasks-only fires at 6, so exactly 3 more land ON the fire rather than past its reset.
    """
    wl.git("init", "-q")
    wl.git("config", "user.email", "t@t")
    wl.git("config", "user.name", "t")
    (wl.proj / "f").write_text("one\n", encoding="utf-8")
    wl.git("add", "f")
    wl.git("commit", "-qm", "one")
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "stop 1")
    wl.check("allow", "", "stop 2")
    # A real commit between stops. If HEAD is wired, this resets tasks plus head.
    with (wl.proj / "f").open("a", encoding="utf-8") as handle:
        handle.write("two\n")
    wl.git("commit", "-qam", "two")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.check("allow", "", "a commit resets the tasks+head counter")

    last = None
    for round_number in (4, 5, 6):
        with (wl.proj / "f").open("a", encoding="utf-8") as handle:
            handle.write("c%d\n" % round_number)
        wl.git("commit", "-qam", "c%d" % round_number)
        wl.newturn()
        wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
        last = wl.run().out
    assert "EMPLOY A PLANNING OR INVESTIGATION AGENT" in last, (
        "55: committing every round escaped the stuck check: %s" % last[:220]
    )
    assert "Commits do not count as movement here" in last, (
        "55: the tasks-only tier did not name why the commits did not help: %s" % last[:220]
    )


def test_56_the_wave_c_replay_an_uncited_prose_blocker_blocks(wl):  # noqa: F811
    """The exact line that started this, verbatim in shape."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked on Wave B landing |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.check("block", "carries no <path>:<line> citation", "an uncited blocker blocks")


def test_57_citing_a_real_line_clears_it(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    (wl.proj / "docs").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "guide.md").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked, docs/guide.md:3 |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.check("allow", "", "a citation that resolves is accepted")


def test_58_control_a_citation_past_end_of_file_is_not_accepted(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    (wl.proj / "docs").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "guide.md").write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked, docs/guide.md:900 |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.check("block", "has only 5 lines", "a fabricated line number is caught")


def test_59_control_a_citation_to_a_file_that_does_not_exist_is_not_accepted(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked, docs/nope.md:3 |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.check("block", "which does not exist", "an invented path is caught")


def test_60_a_live_background_task_exempts_the_citation_requirement(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked on the agent |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.bg = json.dumps([{"status": "running", "description": "agent"}])
    wl.check("allow", "", "real machinery needs no prose citation")


def test_61_blocked_on_the_operator_keeps_its_own_check(wl):  # noqa: F811
    """Not this one."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #12 | Wave C autopilot | blocked, You (User Thinks So) |")
    wl.task(12, "pending", "Wave C autopilot")
    wl.check("allow", "", "an operator blocker is not asked for a file citation")


def test_62_the_judge_is_handed_the_cited_text_and_63_the_import_is_side_effect_free(wl):  # noqa: F811
    """62: the citation state only proves a source EXISTS, which any real file satisfies. This is the half that lets the judge check whether the source says what the session claimed.

    63 is the CONTROL, and it asserts about the very same output: the bare main() call meant any import executed the whole hook, and if that regresses, 62 silently tests a hook run instead of a function.
    """
    (wl.proj / "docs").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "g.md").write_text(
        "alpha\nbravo\nLands with every stage flag off\ndelta\necho\n", encoding="utf-8"
    )
    out = probe(wl, 'm.cited_excerpts(".", "blocked on Wave B landing, docs/g.md:3")')
    assert "Lands with every stage flag off" in out, "62: excerpt missing: %s" % out[:200]
    assert ">3|" in out, "62: the cited line is quoted but unmarked: %s" % out[:200]
    assert "no such option" not in out, "63: import executed main(); the module is not importable"
    assert '"decision"' not in out, "63: import executed the Stop path: %s" % out[:200]


def test_64_control_a_citation_past_end_of_file_yields_no_excerpt_never_a_crash(wl):  # noqa: F811
    (wl.proj / "docs").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "g.md").write_text(
        "alpha\nbravo\nLands with every stage flag off\ndelta\necho\n", encoding="utf-8"
    )
    out = probe(
        wl,
        '"EXCERPT[" + m.cited_excerpts(".", "blocked, docs/g.md:900 and docs/nope.md:2") + "]"',
    )
    assert "EXCERPT[]" in out, "expected an empty excerpt, got: %s" % out[:200]

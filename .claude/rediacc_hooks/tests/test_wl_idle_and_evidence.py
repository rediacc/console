"""Idle stops and completion evidence, ported from `.claude/hooks/stop/worklist-cases/07-idle-and-evidence.sh`.

Idle-stop detection (I6), tick and completion evidence (I7), path citations, and the crashing-hook fail-closed control. One test per numbered bash case, carrying the same assertions in the same order against the same subprocess.

THE CONTROLS ARE THE POINT of several of these, and they are marked as such: each wake-up source that must suppress the idle block, a confirmed operator-blocked task that is a legitimate idle, an invented `.ci` path that must still be rejected, and the unmodified hook that must still allow a clean stop. Each is a document that must still PASS, so the rule under test cannot be
satisfied by blocking everything.
"""

from __future__ import annotations

import json
import re
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def i6_fixture(fix) -> None:
    """The I6 world: a pending task named in `## Remaining`, and no wake-up at all.

    ONE FIXTURE PER CONTROL, which is why the bash case's four controls are four pytest functions here: chaining them on one fixture walks the stuck counter to its threshold and a later control fails for the wrong reason. pytest's per-test sandbox makes that chaining unrepresentable rather than merely discouraged.
    """
    fix.brief_now()
    fix.hand_now()
    fix.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    fix.task(7, "pending", "thing")
    fix.crons = "[]"


def test_91_a_stop_with_nothing_inbound_blocks_on_the_first_stop(wl):  # noqa: F811
    i6_fixture(wl)
    wl.check(
        "block",
        "NOTHING WILL WAKE THIS SESSION",
        "pending task + no cron + no bg + no lease blocks immediately",
    )


def test_92a_control_a_live_work_cron_is_a_wake_up(wl):  # noqa: F811
    """CONTROL: a wake-up source suppresses the idle block."""
    i6_fixture(wl)
    wl.crons = json.dumps(
        [{"id": "w", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.check("allow", "", "a live work cron is a wake-up")


def test_92b_a_poll_cron_alone_is_not_a_wake_up(wl):  # noqa: F811
    """v9: a poll cron only reacts to others, so on its own it wakes nobody."""
    i6_fixture(wl)
    wl.crons = json.dumps([{"id": "p", "schedule": "*/5 * * * *"}])
    wl.check(
        "block",
        "NOTHING WILL WAKE THIS SESSION",
        "v9: a poll cron ALONE is not a wake-up",
    )


def test_92c_control_a_running_background_task_is_a_wake_up(wl):  # noqa: F811
    """CONTROL: a wake-up source suppresses the idle block."""
    i6_fixture(wl)
    wl.bg = json.dumps([{"status": "running", "description": "agent"}])
    wl.check("allow", "", "a running background task is a wake-up")


def test_92d_control_a_fresh_lease_is_a_wake_up(wl):  # noqa: F811
    """CONTROL: a wake-up source suppresses the idle block."""
    i6_fixture(wl)
    until = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + 30 * 60))
    wl.add_item("- [>] (deadbeef) until:%s delegated to agent" % until)
    wl.check("allow", "", "a fresh [>] lease is a wake-up")


def test_93_a_confirmed_operator_blocked_task_is_a_legitimate_idle(wl):  # noqa: F811
    """CONTROL: waiting on the operator, confirmed in their own words, is a stop that needs no wake-up of its own."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | blocked, You (User Thinks So) |")
    wl.task(7, "pending", "thing")
    wl.crons = "[]"
    wl.check("allow", "", "confirmed 'You (User Thinks So)' waits without a wake-up")


def test_94_a_tick_without_evidence_blocks_and_a_real_pointer_clears_it(wl):  # noqa: F811
    """A fabricated hex pointer must NOT count: it names no real object."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    wl.run()
    wl.add_item("- [x] (deadbeef) fixed the flaky teardown")
    wl.check("block", "COMPLETION WITHOUT EVIDENCE", "an evidence-free tick blocks")
    wl.wl.write_text(
        wl.wl.read_text(encoding="utf-8").replace(
            "fixed the flaky teardown", "fixed the flaky teardown, see 0123abc4567"
        ),
        encoding="utf-8",
    )
    wl.check("block", "COMPLETION WITHOUT EVIDENCE", "a fabricated sha is not evidence")
    sha = wl.git("rev-parse", "--short", "HEAD").stdout.strip()
    wl.wl.write_text(
        wl.wl.read_text(encoding="utf-8").replace("see 0123abc4567", "proof " + sha),
        encoding="utf-8",
    )
    wl.check("allow", "", "a REAL git object in the line is evidence")


def test_95_a_task_flipping_to_completed_needs_evidence_near_its_id(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.reg_repo()
    wl.task(7, "pending", "prove the budget flag binds")
    wl.say("working on it\n\n## Remaining\n| #7 | prove the budget flag binds | pending, me |")
    wl.run()
    wl.task(7, "completed", "prove the budget flag binds")
    wl.newturn()
    wl.say("All done.")
    wl.check(
        "block",
        "COMPLETION WITHOUT EVIDENCE",
        "S-2 REPLAY: completed with no evidence anywhere blocks",
    )
    wl.newturn()
    wl.say("Done: #7 verified, exit 0 from the budget run.")
    wl.check("allow", "", "evidence on the #id line clears it")


def test_96b_the_sha_arm_spends_its_budget_on_the_longest_candidates():
    """THE BUG THIS PINS, found live 2026-08-23.

    `completion_evidence` git-verifies at most five hex candidates to bound the git calls, and it took the first five in TEXT order. Every rendered item line opens with the mandatory session tag TWICE, and cited worklist ids are 8 hex as well, so a tick that cross-references its siblings spent the whole budget before reaching its real SHA: the more carefully an item was written,
    the more certainly it failed. It blocked five consecutive stops on a tick whose tree hash resolves.

    The controls below matter more than the regression case. A predicate that answers True more often is trivially "fixed" by deleting it, so the no-evidence, fabricated-SHA and fabricated-path arms have to keep FAILING, and the git-call count has to stay bounded or the fix is just "check them all".
    """
    core = wlfix.import_wl("wl_core")
    checks = wlfix.import_wl("wl_checks")
    root = str(wlfix.STOP_DIR.parents[2])

    # Counted, not assumed: the cap is the whole reason this arm orders candidates instead of simply checking all of them, so a fix that quietly unbounded the git calls has to red here rather than read as a pass.
    calls: list = []
    original = core._git

    def counting(repo, *args):
        calls.append(args)
        return original(repo, *args)

    core._git = counting
    checks.C._git = counting
    try:
        # Two leading tags is the REAL rendered shape, not a worst case: the session tag is mandatory and `_render_line` emits it on the folded line.
        tag = "- [x] (0ad063bf) (0ad063bf) "
        # A tree hash that genuinely resolves in this checkout. DERIVED, not hardcoded: this was pinned to 444e9c09, the rewritten repo's root tree, which resolves in a full local clone and NOT in the checkout CI builds. It went red in CI on run 32657161009 while passing locally. `HEAD^{tree}` resolves in every checkout that has a HEAD at all: full, blobless, or shallow.
        sha = (core._git(root, "rev-parse", "HEAD^{tree}") or "").strip() or "d" * 40
        ids = "23d99308 ebe8b570 e263d2cc"

        # Verified rather than trusted, because a case built on a SHA that stopped resolving would go green by turning into the no-evidence case.
        assert core._git(root, "rev-parse", "--verify", "--quiet", sha + "^{object}"), (
            "fixture-sha-actually-resolves: %s names no object in this checkout" % sha
        )

        cases = [
            (
                "regression-real-sha-at-position-6",
                tag + "rewrite verified " + ids + " tree " + sha,
                True,
            ),
            # THE CONTROL. Without this arm failing on purpose, the fix above is indistinguishable from deleting the check.
            ("CONTROL-no-evidence-anywhere", tag + "did the thing, it works now, all good", False),
            (
                "CONTROL-fabricated-40-hex-is-not-an-object",
                tag + "verified " + ids + " at " + "d" * 40,
                False,
            ),
            (
                "CONTROL-fabricated-file-line",
                tag + "fixed at .claude/hooks/stop/no_such_file.py:617",
                False,
            ),
            (
                "resolving-file-line-alone-passes",
                tag + "fixed at .claude/hooks/stop/wl_checks.py:617",
                True,
            ),
        ]
        for name, text, want in cases:
            calls.clear()
            got = checks.completion_evidence(root, text)
            assert got == want, "%s (got %s)" % (name, got)
            assert len(calls) <= 5, "%s-git-calls-bounded (%d)" % (name, len(calls))
    finally:
        core._git = original
        checks.C._git = original


def test_96_control_completions_that_predate_the_marker_never_nag(wl):  # noqa: F811
    """CONTROL: an init stop snapshots the world, so nothing that was already finished is ever asked about."""
    wl.brief_now()
    wl.reg_repo()
    wl.task(9, "completed", "long-finished thing")
    wl.say("nothing new")
    wl.check("allow", "", "an init-stop snapshot asks nothing about old completions")
    wl.check("allow", "", "and the next stop sees no transition")


def test_97_a_dot_leading_path_is_a_valid_citation(wl):  # noqa: F811
    """`\\b[\\w]` cannot start on a dot, so `.ci/x.sh:9` matched but CAPTURED `ci/x.sh`, which resolves to nothing. That made most of this repo uncitable while the check looked strict. Caught by I7 firing on a real tick."""
    wl.brief_now()
    wl.hand_now()
    scripts = wl.proj / ".ci" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "thing.sh").write_text("a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n", encoding="utf-8")
    wl.say("answer\n\n## Remaining\n| #7 | thing | blocked, .ci/scripts/thing.sh:3 |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "a .ci path resolves as a citation")


def test_98_control_a_dot_leading_path_that_does_not_exist_is_still_rejected(wl):  # noqa: F811
    """CONTROL: without it, case 97 would pass for a check that accepts any dot-leading string."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | blocked, .ci/scripts/nope.sh:3 |")
    wl.task(7, "pending", "thing")
    wl.check("block", "which does not exist", "an invented .ci path is caught")


def test_99_a_crashing_hook_blocks_it_does_not_wave_the_stop_through(wl):  # noqa: F811
    """The hook's global escape hatch, and nobody put it there on purpose: an unhandled exception writes a traceback to stderr and NOTHING to stdout, the harness sees no decision, and the stop is ALLOWED. One bug anywhere silently disabled every check. A v8 cut really did crash on a tuple unpack and sail through; only a needle assertion caught it."""
    crashed = wl.base / "crashy.py"
    crashed.write_text(
        re.sub(
            r"(?m)^def main\(\):$",
            "def main():\n    raise RuntimeError('planted crash')",
            wl.hook.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    event = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(wl.proj),
            "transcript_path": str(wl.transcript),
        }
    )
    env = dict(wl.env)
    env["CLAUDE_PROJECT_DIR"] = str(wl.proj)
    env["WORKLIST_TASKS_DIR"] = str(wl.base / "tasks")
    env["GITHUB_ACTIONS"] = ""
    wl.hook = crashed
    got = wl.python([], stdin=event, env=env)
    assert got.decision == "block", (
        "a crash produced decision=%s (a crash must never allow); out: %s"
        % (got.decision, got.out[:200])
    )
    assert "planted crash" in got.out, "the block did not carry its traceback: %s" % got.out[:200]


def test_100_control_the_unmodified_hook_still_allows_a_clean_stop(wl):  # noqa: F811
    """CONTROL: without this, case 99 would pass on a hook that blocks unconditionally."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    wl.crons = json.dumps(
        [{"id": "c", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.check("allow", "", "a clean stop is still allowed")

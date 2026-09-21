"""Design-doc drift, loop-death and its opt-out, PR and branch freshness, item state words, and STATE.md staleness windows. Ported from `.claude/hooks/stop/worklist-cases/03-drift-loops-freshness.sh`.

One test per numbered bash case, with the same assertions in the same order against the same subprocess. Three bash cases have no `setup` of their own and continue the fixture above them (32 and 33 ride 31's git repo, 38 rides 37's, 45 re-stamps the section 44 planted), so each of those chains stays inside one function: the bash file marks 44 and 45 as ONE indivisible fixture, and
splitting them would test a different world.
"""

from __future__ import annotations

import json
import os
import stat
import time

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

B_BODY_44B = """Session B is holding the canary campaign: attempt 6 is in flight behind watch id 9be21c, five flags are flipped, and v1.2.24 is released. None of this is session A material and none of it may be silenced by session A writing.

## Next action
Read attempt 6 to completion and record the flag states before touching anything."""

GH_SHIM = """#!/bin/bash
echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":9,"lastEditedAt":"%s","updatedAt":"%s"}]}}}}'
"""

REMAINING = "x\n\n## Remaining\n- #7 thing (pending)"


def banked_sig(fix, prefix: str) -> str:
    """That session's banked world signature, or the empty string.

    A LOCAL HELPER: case 44b reads the sidecar the hook writes beside the worklist, which no `wlfix` method exposes, and the whole point of the assertion is that a blocked stop banks NOTHING.
    """
    path = fix.stem(".state-%s.json" % prefix)
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("state_sig", "")
    except (OSError, ValueError):
        return ""


def write_gh_shim(fix, edited_at: str) -> None:
    """A `gh` on the fixture PATH answering the GraphQL read with one PR body edited at that instant.

    A LOCAL HELPER for cases 37 and 38, which differ by exactly that timestamp: 1970 is long before any commit, 2999 long after. The gate under test is the real one.
    """
    script = fix.base / "binonly" / "gh"
    script.write_text(GH_SHIM % (edited_at, edited_at), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def pr_event(fix) -> str:
    """The Stop event cases 36 to 38 feed in: no transcript, the message carried inline, no crons."""
    return json.dumps(
        {
            "session_id": fix.sid,
            "cwd": str(fix.proj),
            "last_assistant_message": REMAINING,
            "session_crons": [],
        }
    )


def test_31_design_doc_drift_blocks_then_clears_and_session_start_lists_the_docs(wl):  # noqa: F811
    """Cases 31, 32 and 33 as one chain: 32 and 33 have no fixture of their own and read the repository 31 builds.

    31 is the FIRE (twelve code commits with untouched docs), 32 is the control that the same repository stops blocking once the docs move with the code, and 33 is the SessionStart handback that names those docs to a session that has not read them.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    docs = wl.proj / "docs" / "ci-overhaul"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "README.md").write_text("# design\n", encoding="utf-8")
    wl.git("init", "-q")
    wl.git("config", "user.email", "t@t")
    wl.git("config", "user.name", "t")
    (wl.proj / ".ci").mkdir(parents=True, exist_ok=True)
    wl.git("add", "-A")
    wl.git("commit", "-qm", "docs")
    for index in range(1, 13):
        (wl.proj / ".ci" / ("f%d.sh" % index)).write_text("%d\n" % index, encoding="utf-8")
        wl.git("add", "-A")
        wl.git("commit", "-qm", "code %d" % index)
    wl.check("block", "design docs have DRIFTED", "12 code commits with untouched docs block")

    # 32: the docs move with the code, and the same repository clears.
    with (docs / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("# updated\n")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "docs refresh")
    wl.check("allow", "", "docs updated after the code clears the drift")

    # 33: SessionStart hands the design docs to a new session.
    payload = json.dumps({"session_id": wl.sid, "cwd": str(wl.proj)})
    out = wl.python(["--session-start"], stdin=payload).out
    assert "READ ALL OF THEM" in out, "SessionStart did not demand the docs be read: %s" % out[:200]
    assert "docs/ci-overhaul/README.md" in out, (
        "SessionStart did not surface the docs: %s" % out[:200]
    )


def test_34_a_loop_that_died_blocks(wl):  # noqa: F811
    """Had crons, now none."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps(
        [{"id": "bbb", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.run()
    wl.crons = "[]"
    wl.check("block", "WORK LOOP DIED", "losing the last cron blocks")


def test_35_a_session_that_never_had_a_cron_is_not_nagged(wl):  # noqa: F811
    """No cron ever, but a running background agent, so the v8 idle check stays quiet and this case keeps pinning ONLY the loop-died non-fire."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = "[]"
    wl.bg = json.dumps([{"status": "running", "description": "agent"}])
    wl.check("allow", "", "no cron ever means no complaint")


def test_34b_declaring_the_loop_finished_clears_it_and_stays_cleared(wl):  # noqa: F811
    """V_LOOP_DIED offers two exits: recreate the cron, or say the loop is deliberately finished. The second one did not exist, because cron memory never read the message, so a session that retired its cron on purpose and said so was blocked on every stop after, with no wording that could satisfy it.

    The final assertion is the one that matters: the declaration must FORGET the high-water mark rather than skip a single stop, or the block returns next stop forever.

    A live background agent rides along, exactly as case 35 does. Without it the repeated stops here trip the idle check and the three-identical-stops check, and the assertion then fails on THEIR reasons while the loop-died verdict is already clear, a confound that made this very case red on its first run.
    """
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.bg = json.dumps([{"status": "running", "description": "agent"}])
    wl.crons = json.dumps(
        [{"id": "bbb", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.run()
    wl.crons = "[]"
    # CONTROL first: the SAME world without the declaration must still block, or the case proves nothing about the declaration.
    wl.check("block", "WORK LOOP DIED", "CONTROL: no declaration, the dead loop still blocks")
    wl.say(
        "The campaign is done, so the loop is deliberately finished and I retired the cron.\n\n"
        "## Remaining\n- #7 thing (pending)"
    )
    wl.check("allow", "", "declaring the loop deliberately finished clears it")
    wl.check("allow", "", "and it STAYS cleared on the next stop")


def test_34c_control_merely_quoting_the_instruction_does_not_opt_out(wl):  # noqa: F811
    """This is an opt-out, so it must survive being written about: every message that discusses this check quotes its own instruction text back. Stripping quoted and backticked spans before matching is what keeps that honest."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.bg = json.dumps([{"status": "running", "description": "agent"}])
    wl.crons = json.dumps(
        [{"id": "bbb", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.run()
    wl.crons = "[]"
    wl.say(
        'The hook says to recreate it or "say out loud in your message that the loop is '
        'deliberately finished", and `the loop is deliberately finished` is the phrase it wants.'
        "\n\n## Remaining\n- #7 thing (pending)"
    )
    wl.check(
        "block", "WORK LOOP DIED", "a quoted or backticked mention does NOT switch the check off"
    )


def test_36_a_stale_local_branch_sharing_the_publish_name_blocks(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.git("init", "-q")
    wl.git("config", "user.email", "t@t")
    wl.git("config", "user.name", "t")
    (wl.proj / "a.txt").write_text("a\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "base")
    wl.git("branch", "-f", "pub", "HEAD")
    (wl.proj / "b.txt").write_text("b\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "newer")
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/pub", head)
    out = wl.run({"WORKLIST_PUBLISH_REF": "pub"}, event=pr_event(wl)).out
    assert "is a trap for whoever checks it out" in out, (
        "stale local branch not detected: %s" % out[:220]
    )


def test_37_pr_freshness_a_push_after_the_last_body_edit_blocks(wl):  # noqa: F811
    """Cases 37 and 38 as one chain: 38 has no fixture of its own and swaps only the shim's timestamp.

    37 is the FIRE, a body edited in 1970 and therefore long before any commit. 38 is the control that a body newer than the tip does not block, so the gate keys on the ordering rather than on the presence of a PR.
    """
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.git("init", "-q")
    wl.git("config", "user.email", "t@t")
    wl.git("config", "user.name", "t")
    wl.git("remote", "add", "origin", "https://github.com/fake/repo.git")
    (wl.proj / "a.txt").write_text("a\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "base")
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("update-ref", "refs/remotes/origin/pub", head)

    write_gh_shim(wl, "1970-01-01T00:00:00Z")
    env = {
        "WORKLIST_PUBLISH_REF": "pub",
        "PATH": "%s:%s" % (wl.base / "binonly", wl.env.get("PATH", "")),
    }
    out = wl.run(env, event=pr_event(wl)).out
    assert "PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" in out, (
        "stale PR body not detected: %s" % out[:220]
    )

    # 38: a body edited AFTER the tip passes.
    write_gh_shim(wl, "2999-01-01T00:00:00Z")
    out = wl.run(env, event=pr_event(wl)).out
    assert out.strip(), "38: the hook produced no output at all"
    assert "PUSHED AFTER" not in out, "38: a fresh body must not block: %s" % out[:200]


def test_39_an_item_listed_with_no_state_word_blocks(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | me |")
    wl.task(7, "pending", "thing")
    wl.check("block", "listed without a STATE", "a stateless remaining item blocks")


def test_40_saying_ongoing_while_the_app_says_pending_blocks(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | ongoing, me |")
    wl.task(7, "pending", "thing")
    wl.check("block", "DISAGREES with the task list", "message and task list must agree")


def test_41_ongoing_matches_an_in_progress_task(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | ongoing, me |")
    wl.task(7, "in_progress", "thing")
    wl.check("allow", "", "an in_progress task labelled ongoing is fine")


def test_41b_literal_in_progress_is_recognized_as_the_state_word(wl):  # noqa: F811
    """Even with a later 'pending' in the same line."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "answer\n\n## Remaining\n"
        "| #7 | **in_progress** | demo done; another observation still pending, blocked on X |"
    )
    wl.task(7, "in_progress", "thing")
    wl.check(
        "allow",
        "",
        "in_progress spelled with an underscore is not skipped in favour of a later pending",
    )


def test_42_a_found_not_fixed_list_blocks(wl):  # noqa: F811
    """Fix it or track it."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "answer\n\nFound, not fixed: CLAUDE.md points at a dead endpoint.\n\n"
        "## Remaining\n| #7 | thing | pending, me |"
    )
    wl.task(7, "pending", "thing")
    wl.check("block", "CLAUDE.md's rule is to FIX", "reporting instead of fixing blocks")


def test_43b_mentioning_the_phrase_mid_sentence_must_not_block(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "answer\n\nThe hook now blocks on a found, not fixed list, and I described that as\n"
        '"Found, not fixed" is now a blocking phrase.\n\n'
        "## Remaining\n| #7 | thing | pending, me |"
    )
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "describing the check does not trip it")


def test_43_the_same_message_without_that_phrase_passes(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "no found-not-fixed list, no complaint")


def test_44_the_staleness_limit_is_load_bearing_and_bracketed(wl):  # noqa: F811
    """Cases 44 and 45 are ONE indivisible fixture: 45 has no fixture of its own and re-stamps the section 44 planted.

    The section is aged past the default without touching the clock. AGE COMES FROM THE SECTION'S HEADING STAMP since 2026-08-09, not from the file's mtime, so this re-stamps the section rather than touching the file: mtime is per FILE while the obligation is per SESSION, and a peer's write used to reset everyone's clock. Touching the file here would silently exercise the unstamped
    fallback instead of the rule under test.

    The limit is 15 minutes and the pair BRACKETS it: 16 must block, 14 must not. A single far-past fixture would keep passing if the constant were raised to an hour by accident. The world has moved since the handover banked the signature (task 7 landed after), so world-keyed staleness is armed.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.age_state("deadbeef", 16)
    wl.check("block", "STATE.md is stale", "a 16-minute-old STATE.md blocks at the 15-minute limit")
    # 45: and one just inside it does not.
    wl.age_state("deadbeef", 14)
    wl.check("allow", "", "a 14-minute-old STATE.md is inside the 15-minute limit")


def test_44b_staleness_is_per_session(wl):  # noqa: F811
    """One session's write cannot silence another.

    THE OTHER HALF OF THE 2026-08-09 INCIDENT, and the half that made the first half inevitable. Age used to come from the file's MTIME, which is per FILE, while the recorded signature is per SESSION. So a peer's write reset everyone's clock: session B's 30-minute-stale document read "ok" the instant session A wrote, and, worse than a skipped stop, the checks then banked A's world
    signature as B's own, so B adopted a document describing A's world as its own recovery artifact. Reproduced against the real function before the fix: ('stale', 30) became ('ok', 0) purely because A wrote. A mutation that reverts the age source to the file mtime must turn this case red.

    B needs work of its OWN outstanding, because the STATE.md violation only fires when something remains for that session: the tasks in the fixture directory are keyed to `deadbeef`, so without B's own open item the case would pass vacuously by never reaching the check under test.

    FOCUS is off for B's two stops. B legitimately has TWO violations (its open item and its stale section) and the focus mechanism surfaces one, so a focused run would assert the needle's absence for a reason that has nothing to do with the rule under test, and the anti-vacuity control below would then pass on a hook that never computed staleness at all.
    """
    wl.brief_now()
    wl.brief_other("cafe1234")
    wl.hand_now()  # A = deadbeef, stamped now
    wl.state_as("cafe1234", B_BODY_44B)
    wl.age_state("cafe1234", 30)  # B is stale; A is not. A's write above is the peer write.
    wl.cli_as("cafe1234", "--add", "cafe1234", "B's own open item")
    wl.task(7, "pending", "thing")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    sig_before = banked_sig(wl, "cafe1234")

    wl.env["WORKLIST_FOCUS"] = "off"
    wl.check_as("cafe1234", "block", "STATE.md is stale", "44b FIRE: the STALE session B is nagged")
    wl.env.pop("WORKLIST_FOCUS")
    wl.check("allow", "", "44b: session A, fresh, is NOT nagged by B's staleness")

    # THE BANKING HALF, which is worse than the skipped stop it hid behind. On a "stale" verdict nothing may be banked, or the next stop would compare against a signature recorded DURING the block and clear itself. Under the mtime bug B got an "ok" verdict off A's write and banked A's world as its own.
    sig_after = banked_sig(wl, "cafe1234")
    assert sig_before, "44b: B banked no signature at all, so the comparison would be vacuous"
    assert sig_before == sig_after, "44b: B's signature moved during the block (%r -> %r)" % (
        sig_before[:12],
        sig_after[:12],
    )

    # ANTI-VACUITY. Re-stamp B fresh: the nag must go away. Without this the case would pass on a hook that simply blocks every peer for every reason. The second half of the anti-vacuity is that B must still be SPEAKING (it still owns an open item), so the missing needle is the staleness verdict changing rather than the hook having gone quiet.
    wl.age_state("cafe1234", 1)
    wl.env["WORKLIST_FOCUS"] = "off"
    out = wl.run_as("cafe1234").out
    wl.env.pop("WORKLIST_FOCUS")
    assert "STATE.md is stale" not in out, (
        "44b ANTI-VACUITY: B is nagged even when fresh: %s" % out[:220]
    )
    assert "OPEN worklist item" in out, "44b ANTI-VACUITY: B went silent instead: %s" % out[:220]


def test_44c_a_future_heading_stamp_cannot_buy_permanent_freshness(wl):  # noqa: F811
    """FOUND ON THE LIVE DOCUMENT, not imagined: driving this code against the real main-branch STATE.md for the first time showed a peer's hand-written heading stamped 101 minutes AHEAD, almost certainly local time written with a Z. A trusted future stamp makes that section permanently fresh, which is worse than the unstamped fallback it would otherwise have taken, because the
    entire point of per-section staleness is that a section cannot dodge its own clock. A future stamp is therefore treated exactly like an unparseable one.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.task(7, "pending", "thing")
    wl.age_state("deadbeef", -60)  # stamped an hour AHEAD
    honest = time.time() - 40 * 60  # the honest age
    os.utime(wl.state_file(), (honest, honest))
    wl.check(
        "block",
        "STATE.md is stale",
        "44c FIRE: a future-stamped section falls back to mtime and goes stale",
    )

    # CONTROL 1: a stamp inside the tolerated skew is still TRUSTED, so this is a rule about wrong clocks rather than a blanket distrust of the future.
    wl.age_state("deadbeef", -2)
    wl.check("allow", "", "44c CONTROL: a stamp 2 minutes ahead is inside the skew and stays fresh")

    # CONTROL 2: and the fallback is really the mtime, not a hardcoded stale. Same future stamp, fresh file: allowed.
    wl.age_state("deadbeef", -60)
    fresh = time.time() - 60
    os.utime(wl.state_file(), (fresh, fresh))
    wl.task(8, "pending", "moved")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |\n| #8 | moved | pending, me |")
    wl.check(
        "allow", "", "44c CONTROL: the untrusted stamp falls back to mtime, which here is fresh"
    )

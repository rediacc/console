"""The `--state` write path and the multi-section recovery document, ported from `.claude/hooks/stop/worklist-cases/02-state-document.sh`.

Refusals, peers, reaping, adoption, backup and branch follow. One test per numbered bash case, with the same assertions in the same order against the same subprocess; where a bash case ran `setup` four times (29k) it becomes four tests, and where the order inside one fixture is the subject (29b's refusal then byte comparison, 29d's two writes then a peer's two) the sequence stays
inside one function.

SEVERAL ASSERTIONS HERE ARE BYTE COMPARISONS RATHER THAN HOOK VERDICTS, and that is the point of the file: an allow only proves the gate was satisfied, and the thing that failed on 2026-08-09 was never the gate. A peer's entire state document was destroyed and came back only because the single-slot backup was read before the next write overwrote it.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

B_BODY_29F = """This is session B, running the licensing drill on a fork of the bench universe, with the mint tool staged and the activation cap already lifted to five. Nothing here overlaps session A, and losing it would cost the drill.

## Next action
Re-run the license-e2e battery against the fork and read the failure reason verbatim."""

PEER_29K = """Session cafe1234 is mid-migration on the chunk-store cold path and owns every uncommitted file under packages/cli/src/services/backup. Sweeping them into another commit is the concrete harm this note exists to prevent, so it has to be visible from a stop, not only after a compaction.

## Next action
Finish the cold-path cutover and hand the file list back to the lead."""

DEAD_BODY = """Session ghost1234 was driving the ceph cutover rehearsal and has not been seen since. Its last recorded position is the RBD snapshot step on carrier two, with the node sync verified and the fork not yet taken.

## Next action
Take the fork once node sync is confirmed on all three carriers."""

LIVE_BODY = """Session live5678 is watching the nightly on main and is very much alive, which is the whole point of this control: an age in the DOCUMENT must not outvote a transcript that is still being written.

## Next action
Read the nightly job log and diagnose any red."""

LEGACY_BODY = """This document predates the section format entirely. It belongs to whichever session wrote it last, it has no heading, and if the first sectioned write deletes it then this change has reproduced the very incident it was built to prevent.

## Next action
Preserve me verbatim under a legacy heading."""

JUNK = "half a sentence with no heading and no next action, well under the floor"

VICTIM_29C = """This is the document a SECOND session wrote and must be able to get back. It carries the one fact that would otherwise die with it: PR #547 merged to main at 01:30Z, so the nightly is now watchable on main rather than on the branch.

## Next action
Diagnose any red in the nightly from its full log; the run itself is scheduled on main."""

VICT_A_29D = """Victim body, deliberately long enough for the shape gate to accept it as a real state document (the gate refuses anything under 250 characters as thin, and an earlier draft of this very fixture was refused exactly that way, which is why this sentence exists). It carries the one fact only this document holds.

## Next action
Recover me from the backup and nothing else."""

PEER_BODY_29D = """Peer body owned by cafe1234 alone, long enough for the shape gate to accept it as a real state document rather than refusing it as thin, which is a floor of 250 characters and easy to fall under when writing a fixture in a hurry.

## Next action
This text must never appear in another session backup slot."""


def text_of(path) -> str:
    """The file's text, or the empty string when it is not there.

    A LOCAL HELPER, standing in for the bash `grep -qF ... 2>/dev/null` shape: several assertions below are about an archive or a backup slot that a correct build may never have created, and a missing file is a failed match rather than an error.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def state_call(fix, argv, body, timeout=15, env_extra=None):
    """One hook call under a WALL-CLOCK TIMEOUT, returning (rc, stdout+stderr).

    A LOCAL HELPER, because `wlfix.python` has no timeout and case 29e's whole subject is a hang. `body=None` leaves the child's stdin a pipe whose write end this process holds open, which is the only way a read on stdin can block forever; rc 124 stands for the hang exactly as `timeout` reports it.
    """
    env = dict(fix.env)
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    env["WORKLIST_TASKS_DIR"] = str(fix.base / "tasks")
    if env_extra:
        env.update(env_extra)
    command = [sys.executable, str(fix.hook), *argv]
    if body is not None:
        try:
            proc = subprocess.run(
                command,
                input=body,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return 124, ""
        return proc.returncode, proc.stdout + proc.stderr

    read_end, write_end = os.pipe()
    try:
        proc = subprocess.Popen(
            command,
            stdin=read_end,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        os.close(read_end)
        read_end = -1
        try:
            out = proc.communicate(timeout=timeout)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return 124, ""
        return proc.returncode, out
    finally:
        if read_end != -1:
            os.close(read_end)
        os.close(write_end)


def test_29b_state_refuses_a_bad_body_instead_of_accepting_then_blocking(wl):  # noqa: F811
    """The old write path once accepted ANY body and let the Stop check reject it a stop later, leaving the compaction-recovery artifact broken while the session believed it was fine.

    Each rejection is paired with the ALLOW control so the guard cannot pass by refusing everything, and the final assertion is a byte comparison rather than a hook allow: a refused write must leave the previous document IDENTICAL.

    THE CAP IS FLAT AGAIN, and 29g is why that is now safe. It was briefly SCALED by the number of `## SESSION` headings, because the budget was per session while the document was per branch and a flat cap's cheapest remedy was deleting the neighbour's block. Since `--state` merges one owned section, the budget and the document have the same scope, and a multi-section body is not
    an over-budget document at all: it is a whole-document paste, refused for a different and stronger reason.
    """
    wl.brief_now()
    wl.hand_now()  # a GOOD STATE.md is already on disk; a refused write must not destroy it
    state_file = wl.state_file()

    for label, body in (
        ("an over-long body", "## Next action: go " + "x" * 4100 + "\n"),
        ("a stub body", "wip"),
        ("an aimless body (no Next action section)", "y" * 400 + "\n"),
    ):
        got = wl.python(["--state", wlfix.ME], stdin=body)
        merged = got.out + got.err
        why = "--state accepted %s: rc=%d %r" % (label, got.rc, merged[:160])
        assert got.rc != 0, why
        assert "STATE REFUSED" in merged, why

    # CONTROL: a well-shaped body must still be written, or the guard is just a blanket refusal wearing three assertions.
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    assert got.rc == 0, (
        "CONTROL: the refusal guard rejected a valid STATE.md: %r" % (got.out + got.err)[:200]
    )

    good = state_file.read_text(encoding="utf-8")
    wl.python(["--state", wlfix.ME], stdin="x" * 4200 + "\n")
    assert state_file.read_text(encoding="utf-8") == good, (
        "a refused rewrite MUTATED the previous STATE.md"
    )


def test_29f_two_sessions_share_one_branch_and_both_sections_survive(wl):  # noqa: F811
    """THE INCIDENT, 2026-08-09. Three sessions were live in one checkout on main. The staleness gate nagged 99ccf057 about a document 2fd369e0 owned, 99ccf057 rewrote it, and a peer's entire state document (a live canary campaign, attempt 6 in flight, five flag flips, an operator-owned design question) was destroyed. It came back only because the single-slot backup was read before
    the next write overwrote it.

    The assertion is a BYTE COMPARISON of A's rendered section across B's write, not an allow: an allow would prove the gate was satisfied, and the thing that failed was never the gate.
    """
    wl.brief_now()
    wl.hand_now()  # A = deadbeef
    a_before = wl.section_of("deadbeef")
    wl.state_as("cafe1234", B_BODY_29F)
    a_after = wl.section_of("deadbeef")
    assert a_before, "29f: A's section came back empty, so the comparison below would be vacuous"
    assert a_before == a_after, "29f: B's write MUTATED A's section: before=%r after=%r" % (
        a_before[:80],
        a_after[:80],
    )

    # BOTH DOCUMENTS SURVIVE, which is what the merge used to buy inside one file and the directory layout now buys by construction. The third clause is the one with teeth: B's text must be ABSENT from A's file, because a tool that still wrote everything into one document would satisfy the first two.
    state_file = wl.state_file()
    b_file = wl.proj / "agent" / "cafe1234" / "STATE.md"
    assert "This is session B" in text_of(b_file), "29f: B's body is not in B's document"
    assert "ci-overhaul session" in text_of(state_file), "29f: A's body left A's document"
    assert "This is session B" not in text_of(state_file), (
        "29f: the two documents are not separate: A=%r" % text_of(state_file)[:120]
    )

    # CONTROL: B writing AGAIN replaces only B's section. Without this the case would pass on a tool that merely refused to write anything at all.
    b_one = wl.section_of("cafe1234")
    time.sleep(1)  # so an advanced stamp is observable at second resolution
    wl.state_as("cafe1234", B_BODY_29F.replace("session B", "session B, round two", 1))
    assert wl.section_of("deadbeef") == a_before, "29f CONTROL: the second write hit A's section"
    assert wl.section_of("cafe1234") != b_one, "29f CONTROL: B's own section did not move"
    assert "round two" in text_of(b_file), "29f CONTROL: the second body never landed"


def test_29k_a_peer_directory_is_named_on_an_ordinary_stop(wl):  # noqa: F811
    """THE HALF OF THE SPLIT THAT COULD HAVE BEEN LOST SILENTLY. Peers used to be `## SESSION` headings inside one shared file, and this note read them from there. Once each session owns a directory, code that keeps reading only its OWN file goes quiet, while every assertion about the caller's own document keeps passing, because that one is the file it still reads. Nothing in this
    suite covered this note before the move, which is exactly the shape of gap a migration slips through.

    Peers stopped being writable on purpose; they must not stop being VISIBLE. A session that cannot see its peers sweeps their uncommitted files.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    wl.state_as("cafe1234", PEER_29K)
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    out = wl.run().out
    assert "under agent/" in out, "29k: the peer went invisible after the split: %s" % out[:400]
    assert re.search(r"cafe1234 +[0-9]+ min old", out), (
        "29k: the peer is named without its age: %s" % out[:400]
    )


def test_29k_control_a_session_alone_on_its_branch_is_told_about_no_peers(wl):  # noqa: F811
    """CONTROL, one planted fact different: no peer directory, no note. Without it the FIRE could be satisfied by boilerplate printed on every stop."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.check_quiet("under agent/", "29k CONTROL: a peers note appeared with no peer directory")


def test_29k_a_peer_past_the_dead_horizon_is_marked_abandoned(wl):  # noqa: F811
    """The liveness marker: a peer whose owner is past the dead horizon is labelled, because "12 minutes old" and "gone since yesterday" ask different things of the reader. NOT called reap-eligible any more: nothing prunes another session's directory, and a label promising a sweep that never comes is a check that cannot fire.

    THE ROW IS MATCHED, NOT THE WORD: the note's own prose explains the marker, so a bare search for it passes on the explanation alone, which is how a control ends up testing a paragraph instead of a verdict.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    wl.state_as("cafe1234", PEER_29K)
    wl.age_state("cafe1234", 1800)  # 30 hours, past WORKLIST_DEAD_HOURS, no transcript
    (wl.base / "projects").mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base / "projects")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    out = wl.run().out
    assert re.search(r"cafe1234 +[0-9]+ min old +ABANDONED", out), (
        "29k: the dead peer read as a live one: %s" % out[:400]
    )


def test_29k_control_a_fresh_peer_is_listed_without_the_marker(wl):  # noqa: F811
    """CONTROL: the same fixture with ONE fact changed, the peer's stamp. It gets its own world rather than a second stop in the same session, because a class-2 section is released once per stop and a repeat stop would report its absence for a reason that has nothing to do with the marker.

    No end anchor: the note travels inside a JSON string, where the row ends in a literal backslash-n rather than a newline. An anchored pattern would never match and this control would pass on any output at all.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    wl.state_as("cafe1234", PEER_29K)
    wl.age_state("cafe1234", 5)  # minutes, so the owner is alive by any horizon
    (wl.base / "projects").mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base / "projects")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    out = wl.run().out
    assert re.search(r"cafe1234 +[0-9]+ min old", out), (
        "29k CONTROL: the fresh peer is not listed at all: %s" % out[:400]
    )
    assert not re.search(r"min old +ABANDONED", out), (
        "29k CONTROL: the marker is unconditional, so it says nothing: %s" % out[:400]
    )


def test_29g_state_refuses_a_body_carrying_a_session_heading(wl):  # noqa: F811
    """The old habit is pasting the WHOLE document, and that habit is what destroyed a peer's document. The tool now writes the heading itself, so a body with one in it is a whole-document paste; refusing teaches the contract at zero cost, because the previous document is untouched."""
    wl.brief_now()
    wl.hand_now()
    state_file = wl.state_file()
    before = state_file.read_text(encoding="utf-8")
    whole_doc = "## SESSION deadbeef 2026-08-09T18:30:00Z\n\n" + wlfix.STATE_BODY

    got = wl.python(["--state", wlfix.ME], stdin=whole_doc)
    merged = got.out + got.err
    why = "29g: a whole-document paste was accepted: rc=%d %r" % (got.rc, merged[:200])
    assert got.rc != 0, why
    assert "looks like the WHOLE document" in merged, why
    assert state_file.read_text(encoding="utf-8") == before, (
        "29g: a REFUSED whole-document write still mutated the document"
    )

    # CONTROL: the same body WITHOUT the heading is accepted, so the refusal keys on the heading and not on the body being long or familiar.
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    assert got.rc == 0, (
        "29g CONTROL: the heading check refused a plain section body: %r"
        % (got.out + got.err)[:200]
    )


def test_29h_a_dead_peer_section_is_reaped_and_archived_before_it_is_dropped(wl):  # noqa: F811
    """Reaping is the one path that deletes content nobody chose to delete, so it is the one path with an append-only archive rather than a single slot. Liveness is the repo's existing notion (owner age over the transcript directory), with the section's own stamp as the fallback for an owner that has no transcript."""
    wl.brief_now()
    wl.hand_now()
    (wl.base / "projects").mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base / "projects")
    document = "\n".join(
        part.rstrip("\n")
        for part in (
            wl.section_of("deadbeef"),
            wlfix.mk_section("ghost1234", 1800, DEAD_BODY),
            wlfix.mk_section("live5678", 1800, LIVE_BODY),
        )
    )
    wl.plant_doc(document)
    # a fresh transcript for the live peer
    (wl.base / "projects" / "live5678-1111-2222-3333-444444444444.jsonl").write_text(
        "", encoding="utf-8"
    )
    path = wl.python(["--path"]).out.strip()
    reaped = pathlib.Path(path[: -len(".md")] + ".agentstate.reaped.deadbeef.md")
    wl.age_state("deadbeef", 1800)  # the writer's OWN section is 30h old too
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    out = got.out + got.err

    state_file = wl.state_file()
    assert "ghost1234" not in text_of(state_file), (
        "29h: the dead peer's section stayed in the document"
    )
    assert "Session ghost1234" in text_of(reaped), (
        "29h: the dead peer's section was dropped without an archive (archive: %r)"
        % text_of(reaped)[:80]
    )
    assert "Session live5678" in text_of(state_file), (
        "29h CONTROL 1: a LIVE peer's section was reaped despite its fresh transcript"
    )
    # CONTROL 2 asserts the ABSENCE of the writer from the archive, not the presence of its section in the document: the write re-adds its own section either way, so a presence check would pass even on a tool that reaped it first and then wrote it back with the old body lost.
    assert text_of(state_file).count("## SESSION deadbeef") == 1, (
        "29h CONTROL 2: the writer duplicated its own section: %r" % text_of(state_file)[:200]
    )
    assert "SESSION deadbeef" not in text_of(reaped), (
        "29h CONTROL 2: the writer reaped its own 30h-old section"
    )
    why = "29h: the reap was silent: %r" % out[:220]
    assert "sections REAPED as dead" in out, why
    assert str(reaped) in out, why


def test_29i_a_legacy_single_section_document_is_adopted_never_destroyed(wl):  # noqa: F811
    """Three checkouts hold a pre-section STATE.md on disk right now. The first merge on such a branch must keep that text, because it may be an in-flight peer's only record, which is exactly the loss this whole change is about."""
    wl.brief_now()
    wl.plant_doc(LEGACY_BODY)
    wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    state_file = wl.state_file()
    body = text_of(state_file)
    why = "29i: the legacy document was lost: %r" % body[:250]
    assert "## SESSION legacy" in body, why
    assert "predates the section format" in body, why
    assert "## SESSION deadbeef" in body, "29i: the new section never landed: %r" % body[:250]

    # CONTROL: aged past the dead horizon it is REAPED, into the archive and never into nothing. Adoption is a grace period, not a permanent squatter.
    (wl.base / "projects").mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base / "projects")
    path = wl.python(["--path"]).out.strip()
    reaped = pathlib.Path(path[: -len(".md")] + ".agentstate.reaped.deadbeef.md")
    wl.age_state("legacy", 1800)
    wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    assert "predates the section format" not in text_of(state_file), (
        "29i CONTROL: the aged legacy section stayed in the document"
    )
    assert "predates the section format" in text_of(reaped), (
        "29i CONTROL: an aged legacy section was reaped into nothing, not into the archive"
    )


def test_29j_a_malformed_document_is_never_silently_replaced(wl):  # noqa: F811
    """Fail closed: the parser must degrade rather than discard. A document that yields no usable section is still SOMEBODY'S text, and the write that lands beside it must leave it recoverable from the document itself and from the backup slot."""
    wl.brief_now()
    wl.plant_doc(JUNK)
    path = wl.python(["--path"]).out.strip()
    backup = pathlib.Path(path[: -len(".md")] + ".agentstate.prev.deadbeef.md")
    wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    assert JUNK in text_of(wl.state_file()), (
        "29j: the malformed body vanished: %r" % text_of(wl.state_file())[:200]
    )
    assert text_of(backup) == JUNK, (
        "29j: the backup does not hold the original: %r" % text_of(backup)[:80]
    )

    # CONTROL: the caller's own verdict is unaffected by the junk beside it. The junk is under the thin floor, and a shape check that judged the whole FILE would call this document thin and block a session whose own section is fine.
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.check("allow", "", "29j CONTROL: a peer's malformed text never blocks my own good section")


def test_29e_a_short_or_bodyless_state_refuses_instead_of_hanging(wl):  # noqa: F811
    """REGRESSION GATE for the defect session 4c3e095a reported as #7c1c2629. `--state` used to require a second argument to enter its own branch at all, so a BARE `--state` matched nothing and fell through to the Stop-HOOK path, which reads the hook event from stdin and therefore BLOCKED FOREVER on a terminal. It cost the reporter a ten-minute tool timeout, and no test could see
    it: every existing `--state` case pipes a body in, which is exactly the shape that does NOT reproduce it.

    THE TIMEOUT IS THE ASSERTION. A regression re-hangs, the helper returns 124, and the case fails loudly instead of stalling the suite forever, which is what a naive assert-on-exit-code test would have done.
    """
    bare_rc, bare_out = state_call(wl, ["--state"], None)
    assert bare_rc != 124, "a bare --state HUNG again (rc=124): the argv-length guard regressed"
    why = "a bare --state did not refuse with usage: rc=%d %r" % (bare_rc, bare_out[:160])
    assert bare_rc != 0, why
    assert "usage: worklist.py --state" in bare_out, why

    # The second half of the same report: the body is read from STDIN, so passing it as an argument left the body EMPTY and the shape check said `thin: 0 chars`. "Too short" and "never arrived" are different diagnoses, and the reporter chased the wrong one twice. Empty stdin must say so in its own words.
    argv_rc, argv_out = state_call(wl, ["--state", wlfix.ME, "a body passed as an argument"], "")
    assert argv_rc != 124, "--state with an argument body HUNG (rc=124)"
    why = "--state mis-diagnosed an argument body: rc=%d %r" % (argv_rc, argv_out[:200])
    assert "no body arrived on stdin" in argv_out, why
    assert "extra argument" in argv_out, why

    # CONTROL: the empty-stdin message must NOT be a blanket response. A body that genuinely IS too short has to keep saying `thin`, or the new branch has just swallowed the old diagnosis.
    thin_rc, thin_out = state_call(wl, ["--state", wlfix.ME], "wip")
    assert thin_rc != 124, "a thin --state HUNG (rc=124)"
    why = "CONTROL: the absent-stdin branch swallowed the thin diagnosis: %r" % thin_out[:200]
    assert "thin" in thin_out, why
    assert "no body arrived" not in thin_out, why


def test_29c_the_outgoing_document_is_recoverable_from_the_backup(wl):  # noqa: F811
    """Two live sessions share one branch, and `--state` used to be last-write-wins. What was not by design is that the loss was permanent: session 84611aab replaced session b9491d9c's 0-minute-old document twice, and neither body could be recovered, because the event log stores item TEXT and never STATE bodies. The write path keeps exactly one previous DOCUMENT beside the lock.

    Since the merge (2026-08-09) a peer write cannot clobber anything, so this case is no longer about a clobber: 29f owns that property. What is left for the backup to cover is a bug in the WRITE itself, which is why the copy is of the whole outgoing document and why one slot is enough.

    BOTH WRITES ARE THE SAME SESSION since the tree split (2026-08-14). They used to be two, which read as the stronger fixture and stopped being a fixture at all the moment each session got its own file: a peer's write now lands in a peer's slot, so the assertion below would have been checking a slot nothing had written. The property under test was never "a peer overwrote this
    session", it is that the body just replaced is still on disk somewhere.
    """
    wl.brief_now()
    wl.hand_now()  # writes STATE_BODY
    state_file = wl.state_file()
    path = wl.python(["--path"]).out.strip()
    # Branch-scoped since the 2026-07-31 review round: one shared slot let a write on ANOTHER branch destroy this branch's only backup.
    backup = pathlib.Path(path[: -len(".md")] + ".agentstate.prev.deadbeef.md")

    wl.python(["--state", wlfix.ME], stdin=VICTIM_29C)
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    out = got.out + got.err
    assert "PR #547 merged to main at 01:30Z" in text_of(backup), (
        "the backup does not hold the outgoing document: %r" % text_of(backup)[:120]
    )
    # The backup must be the OUTGOING document, never the incoming one: a copy taken after the replace would look like a backup and restore nothing.
    assert "Round 23 went red" not in text_of(backup), (
        "CONTROL: the backup captured the INCOMING body; restoring it is a no-op"
    )
    # The writing session has to be TOLD where the copy went, in the same line that says something was there before.
    why = "the write was silent about recovery: %r" % out[:200]
    assert "previous document saved to" in out, why
    assert str(backup) in out, why

    # CONTROL: the FIRST write on a branch replaces nothing, so it must not claim a backup exists. An unconditional path in that line would send the next session chasing a file holding someone else's unrelated document.
    state_file.unlink()
    backup.unlink()
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    assert "previous document saved to" not in (got.out + got.err), (
        "CONTROL: a first write with nothing to replace still advertised a backup"
    )


def test_29d_the_document_and_its_backup_follow_the_session_across_a_branch(wl):  # noqa: F811
    """This case used to assert the opposite, one backup slot PER BRANCH, and it was right while the document itself was per branch. On 2026-08-18 the branch left the path entirely, so the property it protected inverted: one session now has ONE STATE.md and ONE backup, and a checkout that changes branch under a live session must not fork either. That is not a theoretical inversion.
    Session 97604f47 was found owning three STATE.md files at once (main, 0815-1, backup-storage) because a merge moved the checkout mid-session, and the two it was no longer writing were invisible to it.

    So: write on branch A, then write the SAME session on branch B, and both the document and the backup slot must be the same files. The peer half below is unchanged and still guards the OTHER loss (a peer's write taking the only backup), which is what makes this pair a real control: one asserts a branch cannot separate two writes, the other asserts a SESSION still can.
    """
    wl.brief_now()
    wl.hand_now()  # branch agenttest, STATE_BODY
    state_a = wl.state_file()
    path = wl.python(["--path"]).out.strip()
    backup_branched = pathlib.Path(path[: -len(".md")] + ".agentstate.prev.otherbranch.deadbeef.md")
    backup_a = pathlib.Path(path[: -len(".md")] + ".agentstate.prev.deadbeef.md")

    # Branch A: write VICT_A, then write over it, so the slot holds VICT_A.
    wl.python(["--state", wlfix.ME], stdin=VICT_A_29D)
    wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    # The checkout moves to another branch under the SAME session. No new directory is created for it, deliberately: if one were needed the write would refuse, which is itself the old behaviour this case now forbids.
    other = dict(wl.env)
    other["WORKLIST_AGENT_BRANCH"] = "otherbranch"
    got = wl.python(["--state", wlfix.ME], stdin=VICT_A_29D, env=other)
    out = got.out + got.err
    why = "29d: the branch forked the session's document (out: %r)" % out[:160]
    assert state_a.is_file(), why
    assert "Recover me from the backup" in text_of(state_a), why
    assert not (wl.proj / "agent" / "otherbranch").exists(), (
        "29d: the branch change made a second session directory"
    )
    assert not backup_branched.exists(), "29d: the branch change forked the backup slot"
    # ... and the branch-B write's backup landed in the ONE slot, holding the body the branch-A write had left behind. Without this the case above would pass on a build that simply stopped writing backups at all.
    assert "Round 23 went red" in text_of(backup_a), (
        "29d1: the branch-B write did not back up through the session slot (A: %r)"
        % text_of(backup_a)[:60]
    )

    # THE SESSION SCOPE, which the case above deliberately does NOT cover: a peer writing twice must leave deadbeef's slot alone. Two writes, because the first has nothing to replace and would leave an unwritten slot looking exactly like a respected one. The peer body is a marker no other writer uses: an earlier draft had the peer write STATE_BODY, which both slots already
    # contained, so the "deadbeef's slot is intact" assertion would have held just as well on a build where the peer HAD taken it.
    (wl.proj / "agent" / "cafe1234").mkdir(parents=True, exist_ok=True)
    backup_peer = pathlib.Path(str(backup_a)[: -len(".deadbeef.md")] + ".cafe1234.md")
    for _ in range(2):
        wl.cli_as("cafe1234", "--state", "cafe1234", stdin=PEER_BODY_29D)
    assert "Round 23 went red" in text_of(backup_a), "29d2: a peer write took my slot"
    assert "Peer body owned by cafe1234" in text_of(backup_peer), (
        "29d2: the peer's own slot was never written: %r" % text_of(backup_peer)[:40]
    )
    assert "Peer body owned by cafe1234" not in text_of(backup_a), (
        "29d2: the peer's body landed in my slot"
    )

    # A failed backup copy must be CONFESSED, not advertised as a recovery path.
    backup_a.unlink()
    backup_a.mkdir()  # a directory at the path makes the write raise
    got = wl.python(["--state", wlfix.ME], stdin=wlfix.STATE_BODY)
    out = got.out + got.err
    backup_a.rmdir()
    why = "29d CONTROL: the failed backup was advertised as saved: %r" % out[:200]
    assert "backup copy FAILED" in out, why
    assert "previous document saved to" not in out, why

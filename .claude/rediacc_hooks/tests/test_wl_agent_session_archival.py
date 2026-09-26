"""Archiving `agent/<session>/` must take the session OUT of the peer roster, and a same-named stub would put it back.

THE DESIGN THIS FILE DEFENDS is `check:ci-agent-session-archival --move`, which renames the whole directory under `agent/archive/<label>/` and deliberately LEAVES NOTHING at the old path. Every other move in this repository leaves a stub -- a plan does, so its 523 citations keep resolving -- so the absence here reads as an omission until the mechanism is spelled out, which is
what these three cases do.

THE MECHANISM. `wl_store.agent_peer_sections` reads `<dir>/STATE.md` literally, and `agent_state_parse` "NEVER RAISES, and never discards": a file of that name carrying no `## SESSION` heading becomes one section owned by the `legacy` pseudo-owner, stamped at the FILE'S OWN mtime, and `agent_peer_sections` then re-attributes that section to the DIRECTORY it was found in. A
three-line "Status: moved / Moved-To:" stub is exactly such a file. Written at archival time it is zero seconds old, so the archived session returns to the roster as the FRESHEST peer in the tree -- and returns again, on a new clock, every time anyone re-derives the stub.

WHY IT IS THREE CASES AND NOT ONE. The absence assertion alone cannot tell "the move worked" from "the fixture never produced a peer", so the first case proves the peer is there to lose. The third plants the rejected design and proves the failure is real rather than theorised: it is the control that makes the second case mean something.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

ARCHIVED = """Session cafe1234 finished the chunk-store cold-path cutover weeks ago and has not been seen since. Its directory is the kind this gate archives: abandoned by the hook's own oracle, well past the grace period, and holding nothing anybody is still editing.

## Next action
Nothing. The work landed; this document is a record."""

#: What `--move` would leave behind IF it left a stub, which it does not. Deliberately in the shape every other mover in this repository uses, so the case proves something about THAT shape rather than about a malformed file.
REJECTED_STUB = "Status: moved\nMoved-To: agent/archive/2026-09-22-backfill/cafe1234/STATE.md\n"

PEER_ROW = r"cafe1234 +[0-9]+ min old"

# THE ROSTER, READ WHERE IT LIVES. Until 2026-09-24 every Stop printed it as the `agent-peers` advisory, and these cases read it off the hook's output; that advisory was deleted with the peer listing (agent/plans/PLAN-stop-hook-continuity.md P0.3). The roster itself -- `agent_peer_sections` filtered by `agent_state_dead`, the same pair `check_agent_session_archival.py` reads -- is unchanged, so it is rendered here in the row shape the advisory used.
ROSTER_SNIPPET = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S
root = C.project_root(C.project_start({"cwd": sys.argv[2]}))
secs = S.agent_peer_sections(root, sys.argv[3])
_live, dead = S.agent_state_dead(secs, sys.argv[3], C.projects_dir(root))
gone = {id(x) for x in dead}
now = time.time()
for x in secs:
    print("    %-14s %4d min old%s" % (x["owner"], int(max(0.0, (now - x["ts"]) / 60.0)), "   ABANDONED" if id(x) in gone else ""))
"""


def roster(fix) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", ROSTER_SNIPPET, str(wlfix.STOP_DIR), str(fix.proj), fix.sid],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return proc.stdout


def _abandoned_peer(wl) -> None:  # noqa: F811
    """A peer directory whose owner is past the dead horizon, with no transcript.

    `WORKLIST_PROJECTS_DIR` is pointed at an EMPTY directory on purpose: it is the same pin `check_agent_session_archival.py` makes by passing `projects_dir=""`, so `owner_age_hours` finds nothing and the oracle falls back to the section's own heading stamp. Without it the verdict would depend on whichever transcripts happen to sit on the machine running the suite.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    wl.state_as("cafe1234", ARCHIVED)
    wl.age_state("cafe1234", 1800)  # 30 hours, past WORKLIST_DEAD_HOURS
    (wl.base / "projects").mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base / "projects")
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")


def test_the_fixture_really_produces_an_abandoned_peer(wl):  # noqa: F811
    """THE CONTROL FOR THE TWO CASES BELOW. An absence proves nothing until the presence is established: without this, a fixture that quietly stopped writing a peer directory would satisfy the archival case for a reason that has nothing to do with archiving."""
    _abandoned_peer(wl)
    out = roster(wl)
    assert re.search(PEER_ROW, out), (
        "CONTROL: the fixture produced no peer row at all, so the archival case below "
        "would assert an absence it got for free: %s" % out[:400]
    )
    assert re.search(r"cafe1234 +[0-9]+ min old +ABANDONED", out), (
        "CONTROL: the peer is not ABANDONED, so it is not the kind of directory "
        "--move archives: %s" % out[:400]
    )


def test_an_archived_session_leaves_the_peer_roster_entirely(wl):  # noqa: F811
    """THE POINT OF THE WHOLE DESIGN. `--move` renames the directory away and leaves nothing, so the session stops being a peer -- which is the result the stop-hook note has been unable to reach on its own, because nothing may prune another session's directory as a hook side effect.

    The directory is removed rather than only its STATE.md: that is what `git mv agent/cafe1234 agent/archive/<label>/cafe1234` really does, and `agent_session_dirs` enumerates DIRECTORIES, so deleting only the file would leave a differently-shaped tree from the one the verb produces.
    """
    _abandoned_peer(wl)
    state = wl.owner_state_file("cafe1234")
    assert state.is_file(), "FIXTURE BROKEN: the peer wrote no STATE.md to archive"
    shutil.rmtree(state.parent)

    # A SECOND, LIVE peer, so an absence below is not absence from an empty roster.
    wl.state_as("cafe5678", ARCHIVED)
    out = roster(wl)
    assert "cafe5678" in out, "the roster read nothing at all: %r" % out
    assert not re.search(PEER_ROW, out), (
        "the archived session still carries a peer row under agent/: %s" % out[:400]
    )


def test_a_same_named_stub_resurrects_the_archived_session(wl):  # noqa: F811
    """THE REJECTED DESIGN, PLANTED. A stub left at the old path is read by `agent_state_parse` as an unowned legacy section stamped at the file's own mtime, re-attributed to the directory by `agent_peer_sections`, and reported as the FRESHEST peer in the tree -- minutes old, and no longer ABANDONED, so this gate's own count loses it too.

    This is why `--move` leaves nothing behind, and the assertion is the one that would have to change if anyone ever added a stub: it fails LOUDLY, naming the resurrection, instead of the archived session quietly reappearing in the roster.
    """
    _abandoned_peer(wl)
    state = wl.owner_state_file("cafe1234")
    shutil.rmtree(state.parent)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(REJECTED_STUB, encoding="utf-8")

    out = roster(wl)
    assert re.search(PEER_ROW, out), (
        "the stub did not resurrect the peer, so this control asserts nothing and the "
        "no-stub decision has lost its evidence: %s" % out[:400]
    )
    assert not re.search(r"cafe1234 +[0-9]+ min old +ABANDONED", out), (
        "the resurrected peer is still marked ABANDONED, which would mean the stub's "
        "mtime did not become its age: %s" % out[:400]
    )

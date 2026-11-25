#!/usr/bin/env python3
"""PostToolUse(Bash): name a due /writers-now round inside a long turn, not only at the next stop.

WHY (operator report 2026-11-25: no writers-now rounds were visible at effort high). `writers-now-due` is a Stop-hook check, so it can fire only when a turn ends. Measured on session d778be9d over 2026-11-24/25: rounds started 63 to 107 minutes apart against a 60-minute window, because the lead's turns (landings, merged-tree checks, gate repairs) ran 30 to 90 minutes and the due round waited for the turn to end. This note reads the same `wl_writersnow.due` verdict after every Bash call and, at effort `high`, adds one line of context naming the round as due, at most once per NOTE_EVERY_MIN minutes per session, so the round starts inside the turn.

Informational only: the tool call already ran, nothing is refused, and the exit status is 0 whatever happens.
"""

import json
import os
import pathlib
import sys
import tempfile
import time

HOOKS = pathlib.Path(__file__).resolve().parents[1]
STOP = HOOKS / "stop"

# Minutes between two notes for one session: a due round is named again if the turn keeps running without starting it.
NOTE_EVERY_MIN = 10


def _stamp_path(me8):
    return pathlib.Path(tempfile.gettempdir()) / "claude-worklist" / "writers-now-note" / me8


def _recent(me8, now):
    try:
        return now - _stamp_path(me8).stat().st_mtime < NOTE_EVERY_MIN * 60
    except OSError:
        return False


def _touch(me8):
    path = _stamp_path(me8)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())))


def note_for(doc, now=None):
    """The note text for one PostToolUse payload, or "" when no round is due, effort is below `high`, or a note was given within NOTE_EVERY_MIN minutes."""
    now = time.time() if now is None else now
    session = str(doc.get("session_id") or "")
    if len(session) < 8:
        return ""
    me8 = session[:8]
    if _recent(me8, now):
        return ""
    sys.path.insert(0, str(STOP))
    import wl_core as C
    import wl_planqueue
    import wl_writersnow

    root = C.project_root(C.project_start({"cwd": doc.get("cwd") or os.getcwd()}))
    if root is None:
        return ""
    root = pathlib.Path(root)
    got, _problems = wl_planqueue.settings_for(root)
    if got.effort != "high":
        return ""
    fires, facts = wl_writersnow.due(
        wl_writersnow.read_rounds(root),
        session,
        C.utcnow(),
        wl_writersnow.promoted_open(root),
        None,
        root=root,
    )
    if not fires:
        return ""
    _touch(me8)
    age = facts.get("age")
    since = "no round yet" if age is None else "last round %d min ago" % int(age)
    return (
        "WRITERS-NOW DUE (%s, %d open Promoted box(es), effort high): start the round now, inside "
        "this turn: `.claude/hooks/stop/worklist.py --writers-now-start %s <survey path>` and the "
        "survey agent (.claude/commands/writers-now.md steps 0 and 1). The Stop hook blocks on it "
        "at the next stop anyway; starting it here keeps the hourly cadence."
        % (since, facts["open"], me8)
    )


def render(text):
    return (
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        )
        + "\n"
    )


def main(stdin=None, stdout=None):
    if os.environ.get("COMMIT_REVIEW_CHILD") or os.environ.get("STOPHOOK_CHILD"):
        return 0
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        doc = json.loads(stdin.read() or "{}")
        text = note_for(doc) if isinstance(doc, dict) else ""
        if text:
            stdout.write(render(text))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

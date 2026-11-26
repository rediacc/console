#!/usr/bin/env python3
"""PostToolUse(Bash): name a due /writers-now round inside a long turn, not only at the next stop.

WHY (operator report 2026-11-25: no writers-now rounds were visible at effort high). `writers-now-due` is a Stop-hook check, so it can fire only when a turn ends. Measured on session d778be9d over 2026-11-24/25: rounds started 63 to 107 minutes apart against the then 60-minute window (cut to 30 and then to 20 minutes, `wl_writersnow.WINDOW_MIN`, by the operator requests of 2026-11-26), because the lead's turns (landings, merged-tree checks, gate repairs) ran 30 to 90 minutes and the due round waited for the turn to end. This note reads the same `wl_writersnow.due` verdict after every Bash call and, at effort `high`, adds one line of context naming the round as due, at most once per NOTE_EVERY_MIN minutes per session, so the round starts inside the turn.

The capacity refill rides the same note and the same throttle (operator asks 2026-11-25 and 2026-11-26): whatever the clock says, `wl_writersnow.capacity` and `assess` name every unstaffed startable cluster of the newest survey while the roster's estimate counts fewer than CAPACITY_FLOOR live writers, or name a new round as due once that survey is at least REFRESH_GAP_MIN minutes old and has no free cluster left or REFRESH_TICKS of its boxes were ticked; a clock-due note below the floor names the free slots and those clusters too.

Informational only: the tool call already ran, nothing is refused, and the exit status is 0 whatever happens.
"""

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time

HOOKS = pathlib.Path(__file__).resolve().parents[1]
STOP = HOOKS / "stop"


def _load_syspath():
    """The canonical `.claude` hop, loaded BY PATH: this runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Minutes between two notes for one session: a due round is named again if the turn keeps running without starting it (was 10, halved with the cadence by the operator request of 2026-11-26).
NOTE_EVERY_MIN = 5


# A stamp dated in the future (a clock stepped back) has a negative age and holds nothing, for this throttle and the note throttle above alike.
# Seconds a quiet verdict (nothing due) is reused before the store, QUEUE.md and the roster are read again: the throttle above is set only when a note is emitted, so without this every Bash call of a quiet turn at effort high re-read all three (review 7d036d68.3). A round that falls due inside this gap is named at most this much later.
QUIET_EVERY_SEC = 60


def _stamp_path(me8, quiet=False):
    name = me8 + ".quiet" if quiet else me8
    return pathlib.Path(tempfile.gettempdir()) / "claude-worklist" / "writers-now-note" / name


def _recent_quiet(me8, now):
    try:
        return 0 <= now - _stamp_path(me8, quiet=True).stat().st_mtime < QUIET_EVERY_SEC
    except OSError:
        return False


def _touch_quiet(me8):
    path = _stamp_path(me8, quiet=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())))


def _recent(me8, now):
    try:
        return 0 <= now - _stamp_path(me8).stat().st_mtime < NOTE_EVERY_MIN * 60
    except OSError:
        return False


def _touch(me8):
    path = _stamp_path(me8)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())))


def note_for(doc, now=None):
    """The note text for one PostToolUse payload, or "" when neither a round nor a refill is due, effort is below `high`, or a note was given within NOTE_EVERY_MIN minutes."""
    now = time.time() if now is None else now
    session = str(doc.get("session_id") or "")
    if len(session) < 8:
        return ""
    me8 = session[:8]
    if _recent(me8, now) or _recent_quiet(me8, now):
        return ""
    _load_syspath().on_sys_path(STOP)
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
    rows = wl_writersnow.read_rounds(root)
    fires, facts = wl_writersnow.due(
        rows,
        session,
        C.utcnow(),
        wl_writersnow.promoted_open(root),
        None,
        root=root,
    )
    if not facts or facts.get("why") or not facts.get("open"):
        _touch_quiet(me8)
        return ""
    # A survey or roster read that fails leaves the clock's verdict standing (the Stop segment does the same).
    try:
        cap = wl_writersnow.capacity(
            rows,
            session,
            root,
            _items(doc),
            _live_writers(doc, session),
            lambda: wl_writersnow.promoted_done_sigs(root),
        )
    except Exception:
        cap = None
    kind, why = wl_writersnow.assess(fires, facts, cap)
    if kind == "due" and why == wl_writersnow.WHY_CLOCK:
        _touch(me8)
        age = facts.get("age")
        since = "no round yet" if age is None else "last round %d min ago" % int(age)
        return (
            "WRITERS-NOW DUE (%s, %d open Promoted box(es), effort high): start the round now, "
            "inside this turn: `.claude/hooks/stop/worklist.py --writers-now-start %s <survey "
            "path>` and the survey agent (.claude/commands/writers-now.md steps 0 and 1). The Stop "
            "hook blocks on it at the next stop anyway; starting it here keeps the 20-minute "
            "cadence.%s" % (since, facts["open"], me8, _short_suffix(wl_writersnow, cap))
        )
    if kind == "due":
        _touch(me8)
        return (
            "WRITERS-NOW DUE (%s, %d open Promoted box(es), effort high): start the next round now, "
            "inside this turn: `.claude/hooks/stop/worklist.py --writers-now-start %s <survey "
            "path>` and the survey agent (.claude/commands/writers-now.md steps 0 and 1)."
            % (why, facts["open"], me8)
        )
    if kind == "refill":
        _touch(me8)
        f = wl_writersnow.refill_fields(cap, me8)
        return (
            "WRITERS-NOW REFILL (%d live writer(s) against a floor of %d, %d slot(s) free, effort "
            "high): start %d writer(s) now from round %s's survey %s, no new survey: %s. Each takes "
            "its cluster's section 4 line in a lease, every free cluster in one message (presumed "
            "independent unless the file lists overlap); the item text carries the cluster's sigs."
            % (
                f["live"],
                f["floor"],
                f["slots"],
                f["n"],
                f["round"],
                f["survey"],
                _cluster_list(wl_writersnow, cap),
            )
        )
    _touch_quiet(me8)
    return ""


def _cluster_list(wn, cap):
    """The free clusters a refill names, `CL-<id> <sigs>` joined by `; `."""
    return "; ".join("%s %s" % (cl["id"], " ".join(cl["sigs"])) for cl in wn.refill_shown(cap))


def _short_suffix(wn, cap):
    """The shortfall a clock-due note carries below the floor (wl_writersnow.short), else ""."""
    if not wn.short(cap):
        return ""
    f = wn.refill_fields(cap, "")
    return (
        " Meanwhile %d slot(s) are free below the floor of %d; start writers now from round %s's "
        "survey: %s." % (f["slots"], f["floor"], f["round"], _cluster_list(wn, cap))
    )


def _items(doc):
    """The worklist fold items of this checkout, read through the store (read-only, no markdown sync); `capacity` keeps this session's own."""
    import wl_core as C
    import wl_store as S

    start = C.project_start({"cwd": doc.get("cwd") or os.getcwd()})
    return S.load(C.worklist_for(start), sync=False).items


def _live_writers(doc, session):
    """The live writers the roster estimates for this session, or None when it cannot count (which never refills)."""
    import wl_roster

    rows = wl_roster.live_writers_estimate(doc.get("cwd") or os.getcwd(), session)
    return None if rows is None else len(rows)


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

#!/usr/bin/env python3
"""writers_now_note: a due round at effort high is named once inside the turn, then held for NOTE_EVERY_MIN; a round inside the window, effort below high, and a short session id stay silent."""

import datetime
import importlib
import importlib.util
import pathlib
import sys
import tempfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stop"))
spec = importlib.util.spec_from_file_location("writers_now_note", HERE / "writers_now_note.py")
if spec is None or spec.loader is None:
    raise SystemExit("cannot load %s" % (HERE / "writers_now_note.py"))
note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(note)
wl_core = importlib.import_module("wl_core")
wl_planqueue = importlib.import_module("wl_planqueue")
wl_writersnow = importlib.import_module("wl_writersnow")

FAILURES: list[str] = []
SESSION = "d778be9d-0000-0000-0000-000000000000"
NOW = datetime.datetime(2026, 11, 25, 18, 0, tzinfo=datetime.UTC)


def check(label, got, want):
    if got != want:
        FAILURES.append("%s: got %r, want %r" % (label, got, want))


def run(minutes_ago, effort="high", session=SESSION, stamp_dir=None):
    at = (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"session": session, "at": at, "survey": "/nonexistent"}]
    settings = wl_planqueue.Settings(effort=effort)
    with (
        mock.patch.object(wl_core, "utcnow", return_value=NOW),
        mock.patch.object(wl_core, "project_root", return_value="/repo"),
        mock.patch.object(wl_planqueue, "settings_for", return_value=(settings, [])),
        mock.patch.object(wl_writersnow, "read_rounds", return_value=rows),
        mock.patch.object(wl_writersnow, "promoted_open", return_value=469),
        mock.patch.object(note.tempfile, "gettempdir", return_value=stamp_dir),
    ):
        return note.note_for({"session_id": session, "cwd": "/repo"})


def main():
    with tempfile.TemporaryDirectory() as tmp:
        first = run(75, stamp_dir=tmp)
        want = "WRITERS-NOW DUE (last round 75 min ago, 469 open"
        check("a round 75 min old is named", first.startswith(want), True)
        check("the next call within NOTE_EVERY_MIN is held", run(76, stamp_dir=tmp), "")
    with tempfile.TemporaryDirectory() as tmp:
        check("a round 20 min old is silent", run(20, stamp_dir=tmp), "")
    with tempfile.TemporaryDirectory() as tmp:
        check("effort smart is silent", run(75, effort="smart", stamp_dir=tmp), "")
    with tempfile.TemporaryDirectory() as tmp:
        check("a short session id is silent", run(75, session="d77", stamp_dir=tmp), "")
    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("5 case(s) passed; FAILURES: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

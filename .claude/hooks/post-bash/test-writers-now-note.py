#!/usr/bin/env python3
"""writers_now_note: a due round at effort high is named once inside the turn, then held for NOTE_EVERY_MIN; a round inside the window, effort below high, and a short session id stay silent. The capacity refill rides the same note and throttle: a free survey cluster below the target is named, live writers at the target stay silent, and an exhausted survey names the next round."""

import datetime
import importlib
import importlib.util
import os
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
CASES = [0]
SESSION = "d778be9d-0000-0000-0000-000000000000"
NOW = datetime.datetime(2026, 11, 25, 18, 0, tzinfo=datetime.UTC)


def check(label, got, want):
    CASES[0] += 1
    if got != want:
        FAILURES.append("%s: got %r, want %r" % (label, got, want))


SURVEY = (
    "| a1a1a1a1 | A1 [writer] one | CODE | none | x |\n"
    "| b1b1b1b1 | B1 [writer] two | CODE | none | x |\n\n"
    "## 4. CODE boxes clustered by shared files\n\n### Startable now\n\n"
    "- **CL-A (sonnet)**: plan-a A1 a1a1a1a1. Files: a.py.\n"
    "- **CL-B (sonnet)**: plan-b B1 b1b1b1b1. Files: b.py.\n"
)
LEASED_B = {"id": "1", "state": ">", "owner": SESSION, "text": "b1b1b1b1"}
OPEN_A = {"id": "2", "state": " ", "owner": SESSION, "text": "a1a1a1a1"}


def plant_survey(tmp, age_min):
    path = pathlib.Path(tmp) / "survey.md"
    path.write_text(SURVEY, encoding="utf-8")
    stamp = NOW.timestamp() - age_min * 60
    os.utime(path, (stamp, stamp))
    return str(path)


def run(
    minutes_ago,
    effort="high",
    session=SESSION,
    stamp_dir=None,
    survey="/nonexistent",
    items=(),
    live=2,
):
    at = (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"round": "feedf00d", "session": session, "at": at, "survey": survey}]
    settings = wl_planqueue.Settings(effort=effort)
    with (
        mock.patch.object(wl_core, "utcnow", return_value=NOW),
        mock.patch.object(wl_core, "project_root", return_value="/repo"),
        mock.patch.object(wl_planqueue, "settings_for", return_value=(settings, [])),
        mock.patch.object(wl_writersnow, "read_rounds", return_value=rows),
        mock.patch.object(wl_writersnow, "promoted_open", return_value=469),
        mock.patch.object(wl_writersnow, "promoted_done_sigs", return_value=set()),
        mock.patch.object(note, "_items", return_value=list(items)),
        mock.patch.object(note, "_live_writers", return_value=live),
        mock.patch.object(note.tempfile, "gettempdir", return_value=stamp_dir),
    ):
        return note.note_for({"session_id": session, "cwd": "/repo"})


def refill_cases():
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        got = run(20, stamp_dir=tmp, survey=survey, items=[LEASED_B])
        want = "WRITERS-NOW REFILL (2 live writer(s) of 6, effort high): start 1 writer(s)"
        check("a free cluster below the target is named", got.startswith(want), True)
        check("the refill names the free cluster", "CL-A a1a1a1a1" in got, True)
        check("the refill is held by the same throttle", run(20, stamp_dir=tmp, survey=survey), "")
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        check(
            "live writers at the target stay silent",
            run(20, stamp_dir=tmp, survey=survey, live=6),
            "",
        )
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 16)
        got = run(20, stamp_dir=tmp, survey=survey, items=[LEASED_B, OPEN_A])
        want = "WRITERS-NOW DUE (the survey of round feedf00d has no unstaffed startable cluster"
        check("an exhausted survey names the next round", got.startswith(want), True)


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
    refill_cases()
    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("%d case(s) passed; FAILURES: 0" % CASES[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())

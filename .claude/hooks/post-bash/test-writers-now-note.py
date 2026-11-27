#!/usr/bin/env python3
"""writers_now_note: a due round at effort high is named once inside the turn, then held for NOTE_EVERY_MIN; a round inside the window, effort below high, and a short session id stay silent. The capacity refill rides the same note and throttle: every free survey cluster below the floor of 12 is named with the free slots, live writers at the floor stay silent, a clock-due note below the floor carries the free clusters, and an exhausted survey names the next round."""

import datetime
import importlib
import importlib.util
import os
import pathlib
import sys
import tempfile
import time
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent


def _load_syspath():
    """The canonical `.claude` hop, loaded BY PATH: this runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HERE.parents[1] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_load_syspath().on_sys_path(HERE.parent / "stop")
spec = importlib.util.spec_from_file_location("writers_now_note", HERE / "writers_now_note.py")
if spec is None or spec.loader is None:
    raise SystemExit("cannot load %s" % (HERE / "writers_now_note.py"))
note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(note)
wl_core = importlib.import_module("wl_core")
wl_planqueue = importlib.import_module("wl_planqueue")
wl_writersnow = importlib.import_module("wl_writersnow")
wl_boxready = importlib.import_module("wl_boxready")
wl_roster = importlib.import_module("wl_roster")

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


def roster_rows(count, ids):
    """`count` roster rows, the first ones carrying `ids` as their worker ids."""
    return [{"id": ids[n] if n < len(ids) else "anon%d" % n, "writer": True} for n in range(count)]


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
    live_ids=(),
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
        mock.patch.object(wl_writersnow, "promoted_open_sigs", return_value=set()),
        mock.patch.object(wl_boxready, "vmcheck_admits", return_value=False),
        mock.patch.object(note, "_items", return_value=list(items)),
        mock.patch.object(note, "_live_rows", return_value=roster_rows(live, live_ids)),
        mock.patch.object(note.tempfile, "gettempdir", return_value=stamp_dir),
    ):
        return note.note_for({"session_id": session, "cwd": "/repo"})


def refill_cases():
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        got = run(12, stamp_dir=tmp, survey=survey, items=[LEASED_B])
        want = "WRITERS-NOW REFILL (2 live writer(s) against a floor of 12, 10 slot(s) free, effort high): start 1 writer(s)"
        check("a free cluster below the floor is named", got.startswith(want), True)
        check("the refill names the free cluster", "CL-A a1a1a1a1" in got, True)
        check("the refill is held by the same throttle", run(12, stamp_dir=tmp, survey=survey), "")
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        check(
            "live writers at the floor stay silent",
            run(12, stamp_dir=tmp, survey=survey, live=12),
            "",
        )
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        got = run(12, stamp_dir=tmp, survey=survey, items=[LEASED_B], live=11)
        check("eleven live writers, one below the floor, refill", "1 slot(s) free" in got, True)
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 40)
        got = run(45, stamp_dir=tmp, survey=survey, items=[LEASED_B])
        check(
            "a clock-due note names the round",
            got.startswith("WRITERS-NOW DUE (last round 45 min ago"),
            True,
        )
        check(
            "a clock-due note below the floor carries the free cluster",
            "10 slot(s) are free below the floor of 12" in got and "CL-A a1a1a1a1" in got,
            True,
        )
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 40)
        got = run(45, stamp_dir=tmp, survey=survey, items=[LEASED_B], live=12)
        check(
            "control: at the floor the clock-due note carries no shortfall", "slot(s)" in got, False
        )
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        got = run(12, stamp_dir=tmp, survey=survey, items=[LEASED_B, OPEN_A])
        want = "WRITERS-NOW DUE (the survey of round feedf00d has no unstaffed startable cluster"
        check("an exhausted survey names the next round", got.startswith(want), True)


STAFF_SURVEY = (
    SURVEY
    + "\n## Staffing\n\n| target | startable | runner |\n|---|---|---|\n| bench | 2 | none |\n"
)
BENCH_RUNNER = {
    "id": "3",
    "state": ">",
    "owner": SESSION,
    "text": "live runner runner:bench",
    "worker": "w1",
    "first": "2026-11-25T17:55:00Z",
    "upd": "2026-11-25T17:55:00Z",
}


def staff_cases():
    """A live target with startable boxes and no runner prints the STAFF order naming the target, ahead of the clock; once a runner item staffs it the same call prints nothing staff-shaped."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "survey.md"
        path.write_text(STAFF_SURVEY, encoding="utf-8")
        got = run(12, stamp_dir=tmp, survey=str(path), items=[LEASED_B, OPEN_A])
        check("a staff verdict prints the staff note", got.startswith("WRITERS-NOW STAFF ("), True)
        check("the staff note names the target", "  - bench: 2 startable box(es)" in got, True)
        check(
            "the staff note is held by the throttle", run(12, stamp_dir=tmp, survey=str(path)), ""
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "survey.md"
        path.write_text(STAFF_SURVEY, encoding="utf-8")
        got = run(12, stamp_dir=tmp, survey=str(path), items=[LEASED_B, OPEN_A, BENCH_RUNNER])
        check("control: a staffed target prints no staff note", "STAFF" in got, False)


STALE_RUNNER = dict(
    BENCH_RUNNER, worker="w-live", upd="2026-11-25T15:00:00Z", first="2026-11-25T15:00:00Z"
)


def live_id_cases():
    """The roster's live worker ids reach capacity: a runner item too old to count as fresh still staffs its target while its worker is live, and a roster without that id reads it unstaffed (reviews beddbf39.1, .2). The roster is scanned once per note (beddbf39.4)."""
    items = [LEASED_B, OPEN_A, STALE_RUNNER]
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "survey.md"
        path.write_text(STAFF_SURVEY, encoding="utf-8")
        got = run(12, stamp_dir=tmp, survey=str(path), items=items, live_ids=("w-live",))
        check("a live roster id staffs a stale runner item", "STAFF" in got, False)
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "survey.md"
        path.write_text(STAFF_SURVEY, encoding="utf-8")
        got = run(12, stamp_dir=tmp, survey=str(path), items=items, live_ids=())
        check(
            "control: without the live id the stale runner leaves the target unstaffed",
            got.startswith("WRITERS-NOW STAFF ("),
            True,
        )
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        scans = []

        def counting(_cwd, _session, _now=None):
            scans.append(1)
            return roster_rows(2, ("w-live",))

        with (
            mock.patch.object(wl_core, "utcnow", return_value=NOW),
            mock.patch.object(wl_core, "project_root", return_value="/repo"),
            mock.patch.object(
                wl_planqueue,
                "settings_for",
                return_value=(wl_planqueue.Settings(effort="high"), []),
            ),
            mock.patch.object(
                wl_writersnow,
                "read_rounds",
                return_value=[
                    {
                        "round": "feedf00d",
                        "session": SESSION,
                        "at": (NOW - datetime.timedelta(minutes=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "survey": survey,
                    }
                ],
            ),
            mock.patch.object(wl_writersnow, "promoted_open", return_value=469),
            mock.patch.object(wl_writersnow, "promoted_done_sigs", return_value=set()),
            mock.patch.object(wl_writersnow, "promoted_open_sigs", return_value=set()),
            mock.patch.object(wl_boxready, "vmcheck_admits", return_value=False),
            mock.patch.object(note, "_items", return_value=[LEASED_B]),
            mock.patch.object(wl_roster, "live_writers_estimate", counting),
            mock.patch.object(note.tempfile, "gettempdir", return_value=tmp),
        ):
            note.note_for({"session_id": SESSION, "cwd": "/repo"})
        check("one note scans the roster once", len(scans), 1)


def quiet_cases():
    """A quiet verdict is reused for QUIET_EVERY_SEC: the store is not read again on the next call (review 7d036d68.3)."""
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 10)
        calls = []

        def counting_items(_doc):
            calls.append(1)
            return []

        for _ in range(3):
            # live=12 sits at the floor and the round is inside the window, so every call is quiet
            with mock.patch.object(note, "_items", counting_items):
                got = run_quiet(survey, tmp)
            check("a quiet call stays silent", got, "")
        check("three quiet calls read the store once", len(calls), 1)
        # review 70612d3d.2: the quiet verdict expires; a permanent one would read the store never again
        later = time.time() + note.QUIET_EVERY_SEC + 5
        with mock.patch.object(note, "_items", counting_items):
            run_quiet(survey, tmp, now=later)
        check("a call past QUIET_EVERY_SEC reads the store again", len(calls), 2)
        # a stamp dated in the future has a negative age, which is not "within QUIET_EVERY_SEC"
        with mock.patch.object(note.tempfile, "gettempdir", return_value=tmp):
            stamp = note._stamp_path(SESSION[:8], quiet=True)
        future = time.time() + 3600
        os.utime(stamp, (future, future))
        with mock.patch.object(note, "_items", counting_items):
            run_quiet(survey, tmp)
        check("a future-dated quiet stamp does not hold the verdict", len(calls), 3)


def run_quiet(survey, tmp, now=None):
    at = (NOW - datetime.timedelta(minutes=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"round": "feedf00d", "session": SESSION, "at": at, "survey": survey}]
    with (
        mock.patch.object(wl_core, "utcnow", return_value=NOW),
        mock.patch.object(wl_core, "project_root", return_value="/repo"),
        mock.patch.object(
            wl_planqueue, "settings_for", return_value=(wl_planqueue.Settings(effort="high"), [])
        ),
        mock.patch.object(wl_writersnow, "read_rounds", return_value=rows),
        mock.patch.object(wl_writersnow, "promoted_open", return_value=469),
        mock.patch.object(wl_writersnow, "promoted_done_sigs", return_value=set()),
        mock.patch.object(wl_writersnow, "promoted_open_sigs", return_value=set()),
        mock.patch.object(wl_boxready, "vmcheck_admits", return_value=False),
        mock.patch.object(note, "_live_rows", return_value=roster_rows(12, ())),
        mock.patch.object(note.tempfile, "gettempdir", return_value=tmp),
    ):
        return note.note_for({"session_id": SESSION, "cwd": "/repo"}, now=now)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        first = run(75, stamp_dir=tmp)
        want = "WRITERS-NOW DUE (last round 75 min ago, 469 open"
        check("a round 75 min old is named", first.startswith(want), True)
        check("the next call within NOTE_EVERY_MIN is held", run(76, stamp_dir=tmp), "")
    with tempfile.TemporaryDirectory() as tmp:
        check("a round 12 min old is silent", run(12, stamp_dir=tmp), "")
    # review fd65e8ae.2: the window edge itself, so a window moved anywhere between 12 and 31 minutes turns a case red
    # The round's survey is written (a missing one stops counting after SURVEY_GRACE_MIN) and the roster sits at the floor, so only the clock speaks.
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 18)
        got = run(19, stamp_dir=tmp, survey=survey, live=12)
        check("a round 19 min old is silent (inside the 20-minute window)", got, "")
    with tempfile.TemporaryDirectory() as tmp:
        survey = plant_survey(tmp, 19)
        got = run(20, stamp_dir=tmp, survey=survey, live=12)
        check(
            "a round 20 min old is named (the 20-minute window)",
            got.startswith("WRITERS-NOW DUE (last round 20 min ago"),
            True,
        )
    with tempfile.TemporaryDirectory() as tmp:
        got = run(31, stamp_dir=tmp)
        check(
            "a round 31 min old is named (the 20-minute window)",
            got.startswith("WRITERS-NOW DUE (last round 31 min ago"),
            True,
        )
    with tempfile.TemporaryDirectory() as tmp:
        check("effort smart is silent", run(75, effort="smart", stamp_dir=tmp), "")
    with tempfile.TemporaryDirectory() as tmp:
        check("a short session id is silent", run(75, session="d77", stamp_dir=tmp), "")
    refill_cases()
    staff_cases()
    live_id_cases()
    quiet_cases()
    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("%d case(s) passed; FAILURES: 0" % CASES[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())

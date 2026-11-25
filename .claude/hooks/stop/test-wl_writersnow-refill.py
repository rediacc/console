#!/usr/bin/env python3
"""wl_writersnow capacity refill: the newest survey's unstaffed startable clusters are named while live writers sit below REFILL_TARGET, the survey is re-run once it has none left or REFRESH_TICKS of its boxes were ticked, and the hourly clock still fires on its own. Each branch has a silent control beside it, and the Stop segment renders both messages under the one `writers-now-due` key."""

import datetime
import importlib
import os
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
wl_checks = importlib.import_module("wl_checks")
wl_hints = importlib.import_module("wl_hints")
wl_storestatus = importlib.import_module("wl_storestatus")
W = importlib.import_module("wl_writersnow")

FAILURES: list[str] = []
CASES = [0]
ME = "d778be9d-0000-0000-0000-000000000000"
NOW = datetime.datetime(2026, 11, 25, 18, 0, tzinfo=datetime.UTC)
OPEN = {"why": "", "open": 40}

# Three startable clusters: CL-A (free), CL-B (its sig named by a leased item), CL-C (its one box ticked). The review-finding block after the bold paragraph and the blocked heading are not startable; `#aaaa0001` is an item id and `0badc0de` a commit sha no plan table lists, so neither is read as a box.
SURVEY = """# survey

## 1. Plan tables

| sig8 | box | group | needs | evidence |
|---|---|---|---|---|
| a1a1a1a1 | A1 [writer] first | CODE | none | x |
| a2a2a2a2 | A2 [writer] second | CODE | none | x |
| b1b1b1b1 | B1 [writer] third | CODE | none | x |
| c1c1c1c1 | C1 [writer] fourth | CODE | none | x |
| d1d1d1d1 | D1 [writer] blocked | CODE | none | x |
| e1e1e1e1 | E1 [writer] review | CODE | none | x |

## 4. CODE boxes clustered by shared files

### Startable now

- **CL-A (sonnet)**: plan-a A1 a1a1a1a1 + A2 a2a2a2a2, plus seed #aaaa0001, after 0badc0de. Files: a.py, b1b1b1b1.txt.
- **CL-B (opus, new oracle)**: plan-b B1 b1b1b1b1. Files: b.py.
- **CL-C (sonnet)**: plan-c C1 c1c1c1c1. Files: c.py.

**Review-finding clusters:**

- **CL-RV1 (sonnet)**: e1e1e1e1. Files: r.py.

### Blocked behind another box

- **CL-D (sonnet)**: plan-d D1 d1d1d1d1. Files: d.py.
"""

LEASED_B = {"id": "1", "state": ">", "owner": ME, "text": "CL-B writer b1b1b1b1"}
PEER_A = {"id": "2", "state": ">", "owner": "ffffffff-peer", "text": "a1a1a1a1"}
CLOSED_A = {"id": "3", "state": "x", "owner": ME, "text": "a1a1a1a1"}
OPEN_A2 = {"id": "4", "state": " ", "owner": ME, "text": "a2a2a2a2"}


def check(label, got, want):
    CASES[0] += 1
    if got != want:
        FAILURES.append("%s: got %r, want %r" % (label, got, want))


def at(minutes_ago):
    return (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def plant(tmp, text=SURVEY, survey_age_min=30):
    path = pathlib.Path(tmp) / "survey.md"
    path.write_text(text, encoding="utf-8")
    stamp = NOW.timestamp() - survey_age_min * 60
    os.utime(path, (stamp, stamp))
    return [{"round": "feedf00d", "session": ME, "at": at(40), "survey": str(path)}]


def cap(tmp, items=(LEASED_B,), live=2, done=("c1c1c1c1",), **kw):
    rows = plant(tmp, **kw)
    return W.capacity(rows, ME, tmp, list(items), live, lambda: set(done), now=NOW)


def free_ids(facts):
    return [c["id"] for c in facts["free"]]


def parse_cases():
    clusters, sigs = W.parse_survey(SURVEY)
    check(
        "the startable run holds three clusters",
        [c["id"] for c in clusters],
        ["CL-A", "CL-B", "CL-C"],
    )
    check("only plan-table sigs before Files: count", clusters[0]["sigs"], ["a1a1a1a1", "a2a2a2a2"])
    check("the table sigs are read", "e1e1e1e1" in sigs, True)
    check("a survey with no section 4 is unknown", W.parse_survey("# x\n")[0], None)


def refill_cases(tmp):
    got = cap(tmp)
    check("one leased and one ticked leave one free cluster", free_ids(got), ["CL-A"])
    check("the ticked count reads the table sigs", got["ticked"], 1)
    check("refill fires below the target", W.assess(False, OPEN, got), ("refill", ""))
    fields = W.refill_fields(got, ME[:8])
    check(
        "the refill names the free cluster",
        fields["rows"].startswith("  - CL-A a1a1a1a1 a2a2a2a2: plan-a"),
        True,
    )
    check("the refill names one free cluster", fields["n"], 1)
    roomy = cap(tmp, items=(), done=(), live=W.REFILL_TARGET - 2)
    check("the refill names target minus live at most", len(W.refill_shown(roomy)), 2)
    at_target = cap(tmp, live=W.REFILL_TARGET)
    check("live writers at the target refill nothing", W.assess(False, OPEN, at_target), ("", ""))
    check(
        "an uncountable roster refills nothing",
        W.assess(False, OPEN, cap(tmp, live=None)),
        ("", ""),
    )
    stood = {"why": "the landing tree", "open": 40}
    check("a stand-down silences the refill", W.assess(False, stood, cap(tmp)), ("", ""))
    empty = {"why": "", "open": 0}
    check("an empty Promoted queue silences the refill", W.assess(False, empty, cap(tmp)), ("", ""))
    check(
        "a peer's item does not staff a cluster", free_ids(cap(tmp, items=(PEER_A,)))[:1], ["CL-A"]
    )
    check(
        "a closed item does not staff a cluster",
        free_ids(cap(tmp, items=(CLOSED_A,)))[:1],
        ["CL-A"],
    )
    partly = cap(tmp, items=(), done=("a1a1a1a1", "c1c1c1c1"))
    check(
        "a partly ticked cluster carries only its open sigs",
        partly["free"][0]["sigs"],
        ["a2a2a2a2"],
    )


def refresh_cases(tmp):
    staffed = (LEASED_B, OPEN_A2)
    want = ("due", W.WHY_EXHAUSTED % "feedf00d")
    check(
        "an exhausted survey asks for a new round",
        W.assess(False, OPEN, cap(tmp, items=staffed)),
        want,
    )
    young = cap(tmp, items=staffed, survey_age_min=5)
    check("an exhausted survey younger than the gap waits", W.assess(False, OPEN, young), ("", ""))
    unreadable = cap(tmp, text="# survey with no cluster section\n")
    check("an unreadable survey asks for nothing", W.assess(False, OPEN, unreadable), ("", ""))
    many = ["%08x" % (0x10000000 + i) for i in range(W.REFRESH_TICKS)]
    table = "".join("| %s | X [writer] t | CODE | none | x |\n" % s for s in many)
    text = SURVEY.replace("## 4.", table + "\n## 4.", 1)
    want = ("due", W.WHY_TICKED % (W.REFRESH_TICKS, "feedf00d", W.REFRESH_TICKS))
    check(
        "REFRESH_TICKS ticks ask for a new round",
        W.assess(False, OPEN, cap(tmp, text=text, done=tuple(many))),
        want,
    )
    fewer = cap(tmp, text=text, done=tuple(many[1:]))
    check("one tick fewer refills instead", W.assess(False, OPEN, fewer), ("refill", ""))


def clock_cases(tmp):
    rows = [
        {
            "round": "feedf00d",
            "session": ME,
            "at": at(75),
            "survey": str(pathlib.Path(tmp) / "survey.md"),
        }
    ]
    fires, facts = W.due(rows, ME, NOW, 40, None, root=tmp)
    check(
        "the clock still fires after 60 minutes",
        (fires, W.assess(fires, facts, cap(tmp))),
        (True, ("due", W.WHY_CLOCK)),
    )
    fired = run_segment(tmp, [LEASED_B], rows=rows)
    clock = "WRITERS-NOW DUE: run /writers-now now. This session started no round in the last 60"
    check(
        "the segment renders the clock message",
        [(k, t.startswith(clock)) for k, t in fired],
        [("writers-now-due", True)],
    )


def segment_ns(tmp, items, fired, writers=("w1",)):
    return {
        "_ss_rows": [],
        "me8": ME[:8],
        "vadd": lambda key, _block, text: fired.append((key, text)),
        "root": pathlib.Path(tmp),
        "worklist": pathlib.Path(tmp) / "wl",
        "session_id": ME,
        "_loop": types.SimpleNamespace(role=""),
        "event": {},
        "live_bg": [],
        "fold": types.SimpleNamespace(items=items),
        "_live_worker_ids": set(),
        "_roster": {"writers": list(writers)},
    }


class Patched:
    """Replace the segment's other readers and the round, queue and clock reads for one call."""

    def __init__(self, rows):
        self.rows = rows
        self.saved = []

    def _set(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def __enter__(self):
        self._set(wl_storestatus, "blocking", lambda _rows: False)
        self._set(wl_hints, "weekly_block", lambda *_a, **_k: "")
        self._set(W, "read_rounds", lambda _root: self.rows)
        self._set(W, "promoted_open", lambda _root: 40)
        self._set(W, "promoted_done_sigs", lambda _root: {"c1c1c1c1"})
        self._set(W.C, "utcnow", lambda: NOW)
        self._set(wl_checks.C, "utcnow", lambda: NOW)
        return self

    def __exit__(self, *_exc):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)


def run_segment(tmp, items, writers=("w1",), rows=None):
    fired: list = []
    ns = segment_ns(tmp, items, fired, writers)
    planted = plant(tmp)
    with Patched(rows or planted):
        wl_checks._stop_store_freshness(ns)
    return fired


def segment_cases(tmp):
    refill = "WRITERS-NOW REFILL: start 1 writer(s)"
    fired = run_segment(tmp, [LEASED_B])
    check(
        "the segment renders a refill",
        [(k, t.startswith(refill)) for k, t in fired],
        [("writers-now-due", True)],
    )
    due = "WRITERS-NOW DUE: run /writers-now now. A new round is due before the hour: the survey"
    fired = run_segment(tmp, [LEASED_B, OPEN_A2])
    check(
        "the segment renders an exhausted survey",
        [(k, t.startswith(due)) for k, t in fired],
        [("writers-now-due", True)],
    )
    writers = ["w%d" % i for i in range(W.REFILL_TARGET)]
    check("the segment stays silent at the target", run_segment(tmp, [LEASED_B], writers), [])
    check("no read failure is noted", "writers-now-due" in wl_checks.READ_FAILURES, False)


def main():
    parse_cases()
    for group in (refill_cases, refresh_cases, clock_cases, segment_cases):
        with tempfile.TemporaryDirectory() as tmp:
            group(tmp)
    if FAILURES:
        print("FAILURES: %d" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("%d case(s) passed; FAILURES: 0" % CASES[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())

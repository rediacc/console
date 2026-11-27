#!/usr/bin/env python3
"""wl_writersnow capacity refill: every unstaffed startable cluster of the newest survey is named while live writers sit below CAPACITY_FLOOR, inside the clock's window or not; the survey is re-run once it has none left or REFRESH_TICKS of its boxes were ticked; and the half-hourly clock still fires on its own, carrying the shortfall when the roster is below the floor. Each branch has a silent control beside it, and the Stop segment renders every message under the one `writers-now-due` key."""

import datetime
import importlib
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

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


_load_syspath().on_sys_path(HERE)
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


def plant(tmp, text=SURVEY, survey_age_min=12):
    """One round of this session started two minutes before its survey was written, so the round counts and the clock stays quiet while the survey is younger than WINDOW_MIN minus two."""
    path = pathlib.Path(tmp) / "survey.md"
    path.write_text(text, encoding="utf-8")
    stamp = NOW.timestamp() - survey_age_min * 60
    os.utime(path, (stamp, stamp))
    return [{"round": "feedf00d", "session": ME, "at": at(survey_age_min + 2), "survey": str(path)}]


def cap(tmp, items=(LEASED_B,), live=2, done=("c1c1c1c1",), head_time=lambda: None, **kw):
    rows = plant(tmp, **kw)
    return W.capacity(
        rows, ME, tmp, list(items), live, lambda: set(done), now=NOW, head_time=head_time
    )


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
    roomy = cap(tmp, items=(), done=(), live=W.CAPACITY_FLOOR - 1)
    check("the floor triggers the refill and never caps it", len(W.refill_shown(roomy)), 3)
    roomy_fields = W.refill_fields(roomy, ME[:8])
    check("one slot free below the floor", (roomy_fields["slots"], roomy_fields["n"]), (1, 3))
    at_floor = cap(tmp, live=W.CAPACITY_FLOOR)
    check("live writers at the floor refill nothing", W.assess(False, OPEN, at_floor), ("", ""))
    check("the floor is 12", W.CAPACITY_FLOOR, 12)
    # Control (operator request 2026-11-26): no open CODE box, so no capacity trigger even with no writer alive. Every startable cluster ticked, the survey younger than the refresh gap.
    no_code = cap(
        tmp,
        items=(),
        done=("a1a1a1a1", "a2a2a2a2", "b1b1b1b1", "c1c1c1c1"),
        live=0,
        survey_age_min=W.REFRESH_GAP_MIN - 3,
    )
    check("no open CODE cluster: not short", W.short(no_code), False)
    check("no open CODE cluster: no trigger", W.assess(False, OPEN, no_code), ("", ""))
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
    # Cluster C staffed by an item rather than closed by a tick, so the survey is exhausted with zero ticks since it was written.
    quiet = (*staffed, {"id": "9", "state": ">", "owner": ME, "text": "CL-C writer c1c1c1c1"})
    still = cap(tmp, items=quiet, done=(), head_time=lambda: NOW.timestamp() - 3600)
    check(
        "an exhausted survey with no tick and no commit since waits for the clock",
        W.assess(False, OPEN, still),
        ("", ""),
    )
    landed = cap(tmp, items=quiet, done=(), head_time=NOW.timestamp)
    check(
        "a commit after the survey makes the exhausted survey due",
        W.assess(False, OPEN, landed),
        want,
    )
    unknown = cap(tmp, items=quiet, done=(), head_time=lambda: None)
    check("an unknown HEAD time counts as moved", W.assess(False, OPEN, unknown), want)
    young = cap(tmp, items=staffed, survey_age_min=3)
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
    check("the refresh numbers are 1.5x faster", (W.REFRESH_TICKS, W.REFRESH_GAP_MIN), (5, 5))


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
        "the clock still fires after 20 minutes",
        (fires, W.assess(fires, facts, cap(tmp))),
        (True, ("due", W.WHY_CLOCK)),
    )
    check("the window is 20 minutes", (W.WINDOW_MIN, W.SURVEY_GRACE_MIN), (20, 15))
    fresh = [dict(rows[0], at=at(15))]
    check(
        "a round 15 minutes old keeps the clock quiet",
        W.due(fresh, ME, NOW, 40, None, root=tmp)[0],
        False,
    )
    fired = run_segment(tmp, [LEASED_B], rows=rows)
    clock = "WRITERS-NOW DUE: run /writers-now now. This session started no round in the last 20"
    check(
        "the segment renders the clock message",
        [(k, t.startswith(clock)) for k, t in fired],
        [("writers-now-due", True)],
    )
    # Below the floor with a free cluster, the clock message names the slots and the cluster to start while the new survey runs.
    check(
        "the clock message carries the shortfall below the floor",
        [
            (
                "Meanwhile the roster counts 1 live writer(s) against a floor of 12 (11 slot(s) free)"
                in t
                and "  - CL-A a1a1a1a1 a2a2a2a2" in t
            )
            for _k, t in fired
        ],
        [True],
    )
    writers = ["w%d" % i for i in range(W.CAPACITY_FLOOR)]
    full = run_segment(tmp, [LEASED_B], writers, rows=rows)
    check(
        "control: at the floor the clock message carries no shortfall",
        [(t.startswith(clock), "Meanwhile" in t) for _k, t in full],
        [(True, False)],
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
    check(
        "the refill names the free slots",
        "against a floor of 12 (11 slot(s) free)" in fired[0][1]
        and "presumed independent" in fired[0][1],
        True,
    )
    due = "WRITERS-NOW DUE: run /writers-now now. A new round is due before the window closes: the survey"
    fired = run_segment(tmp, [LEASED_B, OPEN_A2])
    check(
        "the segment renders an exhausted survey",
        [(k, t.startswith(due)) for k, t in fired],
        [("writers-now-due", True)],
    )
    writers = ["w%d" % i for i in range(W.CAPACITY_FLOOR)]
    check("the segment stays silent at the floor", run_segment(tmp, [LEASED_B], writers), [])
    seven = ["w%d" % i for i in range(W.CAPACITY_FLOOR - 1)]
    check(
        "seven live writers, one below the floor, still refill",
        [k for k, _t in run_segment(tmp, [LEASED_B], seven)],
        ["writers-now-due"],
    )
    check("no read failure is noted", "writers-now-due" in wl_checks.READ_FAILURES, False)


REVIEW_SURVEY = SURVEY.replace(
    "- **CL-C (sonnet)**: plan-c C1 c1c1c1c1. Files: c.py.\n",
    "- **CL-C (sonnet)**: plan-c C1 c1c1c1c1. Files: c.py.\n"
    "- **CL-W-CI-PY-1**: 30 findings (10 medium, 0 high), box none, console. Findings: de7bea05.1. Files: x.py.\n"
    "- **CL-W-ROOT**: 11 findings, box none, console. Findings: 77d836f1.3. Files: knip.jsonc.\n",
)


def review_cases(tmp):
    """A review cluster (`box none`) is startable work: free until an item of this round names its id, in any spelling (review of the r40/r41 misfire, where a survey of open review clusters read as exhausted)."""
    clusters, _sigs = W.parse_survey(REVIEW_SURVEY)
    check(
        "review clusters are read beside the box clusters",
        [c["id"] for c in clusters],
        ["CL-A", "CL-B", "CL-C", "CL-W-CI-PY-1", "CL-W-ROOT"],
    )
    new = {
        "id": "9",
        "state": ">",
        "owner": ME,
        "text": "(me) writer r41 CL W ROOT",
        "first": at(1),
    }
    old = {"id": "8", "state": "x", "owner": ME, "text": "writer r40 CL-W-CI-PY-1", "first": at(60)}
    peer = {
        "id": "7",
        "state": ">",
        "owner": "ffffffff-peer",
        "text": "CL-W-CI-PY-1",
        "first": at(1),
    }
    facts = cap(tmp, items=(LEASED_B, new, old, peer), text=REVIEW_SURVEY)
    check(
        "a review cluster an item of the round names is staffed",
        "CL-W-ROOT" in free_ids(facts),
        False,
    )
    check(
        "control: an item from before the round, or a peer's, leaves it free",
        "CL-W-CI-PY-1" in free_ids(facts),
        True,
    )
    done = {**new, "state": "x"}
    facts = cap(tmp, items=(LEASED_B, done), text=REVIEW_SURVEY)
    check(
        "a finished writer of the round keeps its cluster off the free list",
        "CL-W-ROOT" in free_ids(facts),
        False,
    )
    facts = cap(
        tmp,
        items=(LEASED_B, OPEN_A2, new, {**old, "first": at(1), "text": "CL-W-CI-PY-1 writer"}),
        text=REVIEW_SURVEY,
        survey_age_min=20,
    )
    check(
        "a survey whose review clusters are all staffed is exhausted",
        W.assess(False, {"open": 3}, facts)[0],
        "due",
    )


PREFIX_SURVEY = REVIEW_SURVEY.replace(
    "- **CL-W-ROOT**",
    "- **CL-W-CI**: 2 findings, box none, console. Findings: aaaa1111.1. Files: y.py.\n- **CL-W-ROOT**",
)


def prefix_cases(tmp):
    """f6904b91.1/.2: a review cluster whose id is a prefix of another named id (`CL-W-CI` beside `CL-W-CI-PY-1`) is not staffed by the longer one's item."""
    longer = {"id": "5", "state": ">", "owner": ME, "text": "writer CL-W-CI-PY-1", "first": at(1)}
    facts = cap(tmp, items=(LEASED_B, longer), text=PREFIX_SURVEY)
    check("the shorter prefix id stays free", "CL-W-CI" in free_ids(facts), True)
    check("the longer id is staffed", "CL-W-CI-PY-1" in free_ids(facts), False)
    shorter = {"id": "6", "state": ">", "owner": ME, "text": "writer CL W CI", "first": at(1)}
    facts = cap(tmp, items=(LEASED_B, longer, shorter), text=PREFIX_SURVEY)
    check("control: an item naming the shorter id staffs it", "CL-W-CI" in free_ids(facts), False)
    check("control: and the longer one stays staffed", "CL-W-CI-PY-1" in free_ids(facts), False)
    # ac243a48.2: the longer id need not be a survey cluster for its hyphen continuation to leave the shorter one free.
    unlisted = {"id": "4", "state": ">", "owner": ME, "text": "writer CL-W-CI-PY-2", "first": at(1)}
    facts = cap(tmp, items=(LEASED_B, unlisted), text=PREFIX_SURVEY)
    check("an unlisted longer id does not staff the shorter", "CL-W-CI" in free_ids(facts), True)
    # ac243a48.3: one item naming both staffs the shorter one it names.
    both = {
        "id": "3",
        "state": ">",
        "owner": ME,
        "text": "writer CL-W-CI-PY-1 and CL-W-CI",
        "first": at(1),
    }
    facts = cap(tmp, items=(LEASED_B, both), text=PREFIX_SURVEY)
    check("an item naming both ids staffs the shorter", "CL-W-CI" in free_ids(facts), False)
    check("and the longer", "CL-W-CI-PY-1" in free_ids(facts), False)
    spaced = {"id": "2", "state": ">", "owner": ME, "text": "writer CL W CI PY 1", "first": at(1)}
    facts = cap(tmp, items=(LEASED_B, spaced), text=PREFIX_SURVEY)
    check("a spaced longer survey id leaves the shorter free", "CL-W-CI" in free_ids(facts), True)
    check("a spaced longer survey id staffs itself", "CL-W-CI-PY-1" in free_ids(facts), False)


def shared_sig_cases(tmp):
    """A box text shared by two plans (the LP-bench receipts) shares one sig: ticked in one plan and open in the other, it is not done (2026-11-27: two such sigs made every survey read as "ticked since")."""
    import wl_planqueue as PQ

    root = pathlib.Path(tmp)
    box = "- [{}] LP-bench [live] Fresh bench receipt.\n  Accept: live-proof bench account-smoke\n"
    (root / "a.md").write_text("# a\n\n" + box.format("x"), encoding="utf-8")
    (root / "b.md").write_text("# b\n\n" + box.format(" "), encoding="utf-8")
    (root / "c.md").write_text(
        "# c\n\n" + box.format("x").replace("Fresh", "Only"), encoding="utf-8"
    )
    queue = root / PQ.QUEUE_REL
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("queue\n", encoding="utf-8")
    real = PQ.promoted_numbered
    PQ.promoted_numbered = lambda _text: [("1", "a.md"), ("2", "b.md"), ("3", "c.md")]
    try:
        done = W.promoted_done_sigs(root)
    finally:
        PQ.promoted_numbered = real
    import wl_planrec as PR

    only_c = {b[3] for b in PR.done_boxes((root / "c.md").read_text(encoding="utf-8"))}
    shared = {b[3] for b in PR.done_boxes((root / "a.md").read_text(encoding="utf-8"))}
    # review c4e31ac4.1: pin WHICH sig survives, not only how many
    check("only the sig ticked everywhere is done", done, only_c)
    check("the shared sig is not done", bool(done & shared), False)


def main():
    parse_cases()
    for group in (
        shared_sig_cases,
        refill_cases,
        refresh_cases,
        clock_cases,
        segment_cases,
        review_cases,
        prefix_cases,
    ):
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

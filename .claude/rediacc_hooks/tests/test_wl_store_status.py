"""wl_storestatus: the snapshot, the change rows, the freshness classes and the two renderers (agent/plans/PLAN-stop-hook-store-status.md S1, Design D1 and D2).

Every fold here is built by the store's own fold (`wl_store._fold_events`) from planted events, so a case tests the module against the record shape the hook really reads. Every firing case carries a control off the same fold that differs in one fact.
"""

from __future__ import annotations

import calendar
import datetime

import pytest

from rediacc_hooks.tests import wlfix

S = wlfix.import_wl("wl_store")
L = wlfix.import_wl("wl_liveness")
SS = wlfix.import_wl("wl_storestatus")

SID = "abcd1234-0000-4000-8000-000000000000"
ME = "abcd1234"
PEER = "ffff9999"
NOW = calendar.timegm((2026, 11, 18, 12, 0, 0))


def at(minutes_ago: float) -> str:
    moment = datetime.datetime.fromtimestamp(NOW - minutes_ago * 60, datetime.UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def add(
    rid: str, minutes_ago: float, text: str = "item", owner: str = ME, state: str = " "
) -> dict:
    return {
        "ev": "add",
        "id": rid,
        "at": at(minutes_ago),
        "by": owner,
        "o": owner,
        "s": state,
        "t": "%s (%s)" % (text, owner),
    }


def ev(kind: str, rid: str, minutes_ago: float, **kw) -> dict:
    return {"ev": kind, "id": rid, "at": at(minutes_ago), "by": ME, **kw}


def fold(events: list[dict]):
    """The fold `wl_store.load` builds, minus the disk: the same `_fold_events` pass and the same item list."""
    ordered = sorted(events, key=S.event_order)
    records, md_keys, cli_ids, md_hash, lineage = S._fold_events(ordered)
    items = []
    for k in list(md_keys) + [i for i in cli_ids if i not in md_keys]:
        rec = records.get(k)
        if rec is None or rec.get("state") == "~":
            continue
        rec = dict(rec)
        rec["line"] = S._render_line(rec)
        items.append(rec)
    items.sort(key=lambda r: (r.get("first", ""), r["id"]))
    return S.Fold(items, md_hash, lineage)


def snap(events: list[dict]):
    return SS.snapshot(fold(events), SID, NOW)


def kinds(prev, events: list[dict]) -> list[tuple[str, str]]:
    return [(r["id"], r["kind"]) for r in SS.changes(prev, fold(events), SID)]


def fresh(
    events: list[dict], prev="same", live=(), verdicts=None, roster_live=(), queued=(), covered=()
):
    f = fold(events)
    if prev == "same":
        prev = SS.snapshot(f, SID, NOW)
    rows = SS.freshness(
        f, SID, prev, set(live), dict(verdicts or {}), set(roster_live), set(queued), covered, NOW
    )
    return {r["id"]: r for r in rows}


# ---- snapshot ---------------------------------------------------------------


def test_snapshot_covers_owned_open_inflight_deferred_only():
    events = [
        add("a1", 30),
        add("a2", 30),
        ev("lease", "a2", 20, until=at(-60), worker="w1", note="started"),
        add("a3", 30),
        ev("state", "a3", 10, s="?", note="which one? DEFAULT: this one"),
        add("a4", 30),
        ev("state", "a4", 5, s="x", note="done"),
        add("p1", 30, owner=PEER),
    ]
    got = snap(events)
    assert set(got["items"]) == {"a1", "a2", "a3"}
    assert got["items"]["a2"] == [">", at(20), "w1", at(20), SS.note8("started")]
    assert got["stop_at"] == NOW
    assert got["at"] == [at(5), 0]


def test_snapshot_at_takes_the_event_high_water_mark_when_set():
    events = [add("a1", 30), ev("update", "a1", 3, note="n", ns=7)]
    f = fold(events)
    f.high_water = SS.high_water(events)
    assert SS.snapshot(f, SID, NOW)["at"] == [at(3), 7]


# ---- change kinds, each with a no-row control -------------------------------

BASE = [add("a1", 60, "first"), add("a2", 60, "second")]


def test_change_new():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, add("a9", 1, "fresh")]) == [("a9", "new")]


def test_change_ticked():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, ev("state", "a1", 1, s="x", note="shipped")]) == [("a1", "ticked")]


def test_change_deferred():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, ev("state", "a1", 1, s="?", note="q DEFAULT: x")]) == [
        ("a1", "deferred")
    ]


def test_change_reopened_from_deferred():
    deferred = [*BASE, ev("state", "a1", 30, s="?", note="q DEFAULT: x")]
    prev = snap(deferred)
    assert kinds(prev, deferred) == []
    assert kinds(prev, [*deferred, ev("state", "a1", 1, s=" ", note="answered")]) == [
        ("a1", "reopened")
    ]


def test_change_reopened_from_closed():
    closed = [*BASE, ev("state", "a1", 30, s="x", note="done")]
    prev = snap(closed)
    assert kinds(prev, closed) == []
    assert kinds(prev, [*closed, ev("state", "a1", 1, s=" ", note="judge reopened")]) == [
        ("a1", "reopened")
    ]


def test_change_leased():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, ev("lease", "a1", 1, until=at(-60), worker="w1")]) == [
        ("a1", "leased")
    ]


def test_change_unleased():
    leased = [*BASE, ev("lease", "a1", 30, until=at(-60), worker="w1")]
    prev = snap(leased)
    assert kinds(prev, leased) == []
    assert kinds(prev, [*leased, ev("unlease", "a1", 1, t="released")]) == [("a1", "unleased")]


def test_change_note():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, ev("update", "a1", 1, note="half done")]) == [("a1", "note")]


def test_change_retired():
    prev = snap(BASE)
    assert kinds(prev, BASE) == []
    assert kinds(prev, [*BASE, ev("tomb", "a1", 1, why="dup")]) == [("a1", "retired")]


def test_no_snapshot_gives_no_rows_and_says_so():
    assert SS.changes(None, fold(BASE), SID) == []
    assert SS.render_changes([], first=True) == SS.NO_SNAPSHOT
    assert SS.render_changes([]) == SS.CHANGES_NONE


# ---- compaction -------------------------------------------------------------


def test_compacted_fold_gives_no_change_rows():
    events = [
        add("a1", 300, "leased then updated"),
        ev("lease", "a1", 200, until=at(-60), worker="w1", note="HOLD_FOR:#a2"),
        ev("update", "a1", 100, note="later progress"),
        add("a2", 300, "deferred"),
        ev("state", "a2", 150, s="?", note="q DEFAULT: x"),
        add("a3", 300, "plain open"),
        add("a4", 300, "ticked"),
        ev("state", "a4", 50, s="x", note="done"),
    ]
    before = fold(events)
    prev = SS.snapshot(before, SID, NOW)
    rewritten = S.snapshot_events(before)
    after = fold(rewritten)
    # Non-vacuous: the compaction really does move the lease stamp, which a naive digest compare would call a change.
    assert after.by_id["a1"]["lease_at"] != before.by_id["a1"]["lease_at"]
    assert SS.changes(prev, after, SID) == []
    rows = SS.freshness(after, SID, prev, set(), {}, set(), set(), (), NOW)
    assert all(r["cls"] != "moved" for r in rows)
    # Control: a real update after the compaction is one row.
    assert kinds(prev, [*rewritten, ev("update", "a3", 1, note="moved on")]) == [("a3", "note")]


# ---- freshness classes ------------------------------------------------------


def test_class_moved():
    prev = snap(BASE)
    rows = fresh([*BASE, ev("update", "a1", 1, note="x")], prev=prev)
    assert rows["a1"]["cls"] == "moved"
    assert rows["a2"]["cls"] == "quiet"


def test_class_live_needs_verification():
    events = [add("a1", 300), ev("lease", "a1", 200, until=at(-60), worker="w1")]
    assert fresh(events, live={"w1"}, verdicts={"w1": "confirmed"})["a1"]["cls"] == "live"
    assert fresh(events, roster_live={"w1"})["a1"]["cls"] == "live"
    # Control: listed live but only suspect is not verified, and past the resolve rung it is stale.
    row = fresh(events, live={"w1"}, verdicts={"w1": "suspect"})["a1"]
    assert (row["cls"], row["wstate"], row["blocks"]) == ("stale", "suspect", True)


def test_class_waiting():
    blocked = [add("b0b0b0b0", 300, "blocker"), add("a1", 300, "waits BLOCKED_BY:#b0b0b0b0")]
    assert fresh(blocked)["a1"]["cls"] == "waiting"
    queue = [add("a1", 300), ev("lease", "a1", 200, until=at(-60), worker="queue")]
    assert fresh(queue)["a1"]["cls"] == "waiting"
    shell_wait = [add("a1", 300), ev("lease", "a1", 200, until=at(-60), worker="ag1")]
    assert fresh(shell_wait, verdicts={"ag1": "waiting"})["a1"]["cls"] == "waiting"
    # Control: the blocker closed, so nothing is waited on.
    done = [*blocked, ev("state", "b0b0b0b0", 250, s="x", note="done")]
    assert fresh(done)["a1"]["cls"] == "stale"


def test_class_queued():
    events = [add("a1", 300)]
    assert fresh(events, queued={"a1"})["a1"]["cls"] == "queued"
    assert fresh(events)["a1"]["cls"] == "stale"


def test_class_deferred():
    events = [add("a1", 300), ev("state", "a1", 200, s="?", note="q DEFAULT: x")]
    row = fresh(events)["a1"]
    assert (row["cls"], row["blocks"]) == ("deferred", False)


@pytest.mark.parametrize(("delta", "cls"), [(-1, "quiet"), (0, "stale")])
def test_class_quiet_and_stale_at_the_resolve_boundary(delta, cls):
    age = L.LADDER_RESOLVE_MIN + delta
    events = [add("a1", age)]
    row = fresh(events)["a1"]
    assert (row["age"], row["cls"], row["blocks"]) == (age, cls, cls == "stale")


@pytest.mark.parametrize(("delta", "cls"), [(-1, "quiet"), (0, "orphaned")])
def test_class_orphaned_at_the_investigate_boundary(delta, cls):
    age = L.LADDER_INVESTIGATE_MIN + delta
    events = [add("a1", 400), ev("lease", "a1", age, until=at(-60), worker="dead1")]
    row = fresh(events)["a1"]
    assert (row["age"], row["wstate"], row["cls"], row["blocks"]) == (
        age,
        "gone",
        cls,
        cls == "orphaned",
    )


def test_lead_lease_is_never_orphaned():
    age = L.LADDER_INVESTIGATE_MIN
    events = [add("a1", 400), ev("lease", "a1", age, until=at(-60), worker="lead")]
    row = fresh(events)["a1"]
    assert (row["wstate"], row["cls"]) == ("lead", "quiet")


def test_no_snapshot_judges_by_age_alone():
    rows = fresh([add("a1", L.LADDER_RESOLVE_MIN), add("a2", 1)], prev=None)
    assert (rows["a1"]["cls"], rows["a2"]["cls"]) == ("stale", "quiet")


def test_covered_item_is_listed_but_not_blocking():
    events = [add("a1", 300), add("a2", 300)]
    rows = SS.freshness(
        fold(events), SID, snap(events), set(), {}, set(), set(), {"a1": "roster-dead"}, NOW
    )
    by = {r["id"]: r for r in rows}
    assert (by["a1"]["cls"], by["a1"]["covered"], by["a1"]["blocks"]) == (
        "stale",
        "roster-dead",
        False,
    )
    assert SS.blocking(rows) == ["a2"]
    assert "stale[roster-dead]" in SS.render_table(rows)
    # Control: uncovered, both block.
    rows = SS.freshness(fold(events), SID, snap(events), set(), {}, set(), set(), set(), NOW)
    assert sorted(SS.blocking(rows)) == ["a1", "a2"]


def test_peer_items_are_not_judged():
    events = [add("p1", 300, owner=PEER), add("a1", 1)]
    assert set(fresh(events)) == {"a1"}


# ---- renderers --------------------------------------------------------------


def _rows(n: int) -> list[dict]:
    return [
        {
            "id": "%08x" % i,
            "state": " ",
            "worker": "",
            "wstate": "-",
            "age": i,
            "cls": "quiet",
            "why": "",
            "note": "n",
            "covered": "",
            "blocks": False,
        }
        for i in range(n)
    ]


def test_table_over_cap_ends_with_more_tail():
    text = SS.render_table(_rows(45), cap=40, me=ME)
    lines = text.splitlines()
    assert lines[0] == SS.TABLE_HEADER
    assert len(lines) == 42
    assert lines[-1] == "+5 more: worklist.py --status %s" % ME
    # Control: at the cap, no tail.
    assert "more:" not in SS.render_table(_rows(40), cap=40)


def test_table_default_cap_is_forty():
    assert SS.render_table(_rows(41)).splitlines()[-1] == "+1 more: worklist.py --status <me>"


def test_table_empty_is_silent():
    assert SS.render_table([]) == ""


def test_table_row_shape():
    events = [
        add("a1", 300),
        ev("lease", "a1", 12, until=at(-60), worker="w1", note="working on it"),
    ]
    rows = list(fresh(events, live={"w1"}, verdicts={"w1": "confirmed"}).values())
    line = SS.render_table(rows).splitlines()[1]
    assert line.startswith("#a1  [>]  w1 (live, verified)  12m  live")
    assert line.endswith("working on it")


def test_changes_over_cap_ends_with_more_tail():
    rows = [{"id": "%08x" % i, "kind": "note", "state": " ", "detail": "d"} for i in range(20)]
    lines = SS.render_changes(rows, cap=15, me=ME).splitlines()
    assert lines[0] == SS.CHANGES_HEADER
    assert len(lines) == 17
    assert lines[-1] == "+5 more: worklist.py --status %s --since-last-stop" % ME
    # Control: at the cap, no tail.
    assert "more:" not in SS.render_changes(rows[:15], cap=15)


def test_count_line():
    events = [add("a1", 300), add("a2", 1), ev("update", "a2", 0, note="x")]
    prev = snap([add("a1", 300), add("a2", 1)])
    rows = list(fresh(events, prev=prev).values())
    line = SS.count_line(rows, me=ME)
    assert line.startswith(
        "STORE STATUS: 2 open (1 moved, 0 live, 0 waiting, 0 queued, 0 quiet, 1 stale)"
    )
    assert line.endswith("worklist.py --status %s" % ME)


def test_the_module_loads_from_the_stop_hook_directory() -> None:
    """The suite resolves `.claude/hooks/stop/wl_storestatus.py` by name, so the module cannot be renamed or moved without this reading red."""
    assert SS.__file__.endswith(".claude/hooks/stop/wl_storestatus.py")

"""wl_storestatus: the snapshot, the change rows, the freshness classes and the two renderers (agent/plans/PLAN-stop-hook-store-status.md S1, Design D1 and D2).

Every fold here is built by the store's own fold (`wl_store._fold_events`) from planted events, so a case tests the module against the record shape the hook really reads. Every firing case carries a control off the same fold that differs in one fact.
"""

from __future__ import annotations

import calendar
import datetime
import json
import time

import pytest

from rediacc_hooks.tests import test_wl_roster as R
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


# ---- the review finding e8329fa3.1: same-second stamps ----------------------


def test_an_item_first_stamped_in_the_snapshots_own_second_reads_new():
    """The snapshot's high-water mark is second-resolution, so an item added after the snapshot inside that same second is `new`. Control: an item whose first stamp is older than the mark and that was not open at the snapshot reads `reopened`."""
    events = [add("a1", 10), ev("update", "a1", 5, note="moved")]
    prev = snap(events)
    assert prev["at"] == [at(5), 0]
    assert kinds(prev, [*events, add("a9", 5, "same second")]) == [("a9", "new")]
    closed = [*events, add("a8", 30), ev("state", "a8", 20, s="x", note="done")]
    prev = snap(closed)
    assert kinds(prev, [*closed, ev("state", "a8", 1, s=" ", note="back")]) == [("a8", "reopened")]


# ---- the stop wiring's pure halves (S3) -------------------------------------


def test_open_item_ids_names_what_open_items_names():
    events = [
        add("a1", 30),
        add("a2", 30, "waits"),
        add("a3", 30),
        add("a4", 30),
        ev("lease", "a4", 20, until=at(-60), worker="w1"),
        add("a5", 30),
        ev("lease", "a5", 20, until=at(-60), worker="w2"),
        add("p1", 30, owner=PEER),
    ]
    f = fold(events)
    # classify_items stamps the wait on the record; open_item_ids reads it after.
    next(r for r in f.items if r["id"] == "a2")["waiting_on"] = ["a1"]
    got = SS.open_item_ids(f, SID, in_flight_ids={"a4"}, queued_ids={"a3"})
    assert got == {"a1", "a5"}


def test_covering_reads_the_ladder_the_roster_and_open_items():
    events = [
        add("a1", 30),
        add("a2", 30),
        ev("lease", "a2", 20, until=at(-60), worker="w-silent"),
        add("a3", 30),
        add("a4", 30),
        add("a5", 30),
    ]
    cover = SS.covering(
        fold(events),
        SID,
        open_ids={"a1"},
        ladder={"ladder-resolve": ["#a3 - [>] text", "task #7 a harness task"], "ladder-gone": []},
        roster={"leased_dead": [("a4", "w4", "")], "silent": ["w-silent"], "status_due": []},
    )
    assert cover == {
        "a1": "open-items",
        "a2": "roster-silent",
        "a3": "ladder-resolve",
        "a4": "roster-dead",
    }
    # Control: no covering check names nothing.
    assert SS.covering(fold(events), SID) == {}


def test_render_stale_names_each_blocking_row_and_every_exit():
    events = [add("a1", 400), ev("lease", "a1", 300, until=at(-60), worker="b0dead")]
    rows = SS.freshness(fold(events), SID, snap(events), set(), {}, set(), set(), {}, NOW)
    text = SS.render_stale(rows, ME)
    assert text.startswith("WL-STALE: 1 open item(s)")
    assert "#a1  [>]  b0dead (gone)  orphaned: quiet 300m" in text
    for verb in ("--update %s" % ME, "BLOCKED_BY", "--defer", "--tick"):
        assert verb in text
    # Control: the same row covered by another check renders nothing.
    covered = SS.freshness(
        fold(events), SID, snap(events), set(), {}, set(), set(), {"a1": "roster-dead"}, NOW
    )
    assert SS.render_stale(covered, ME) == ""


def test_stop_texts_split_the_table_from_the_reason():
    events = [add("a1", 30, "one"), add("a2", 30, "two")]
    prev = snap(events)
    f = fold([*events, ev("update", "a2", 1, note="progress")])
    rows = SS.freshness(f, SID, prev, set(), {}, set(), set(), {}, NOW)
    system, reason = SS.stop_texts(rows, SS.changes(prev, f, SID), False, ME)
    assert system.startswith(SS.TABLE_HEADER)
    assert "#a2  note     progress" in system
    assert SS.TABLE_HEADER not in reason
    assert reason.splitlines()[0].startswith("STORE STATUS: 2 open (1 moved")
    assert "#a2  note     progress" in reason
    # Control: nothing owned and nothing changed is silent.
    assert SS.stop_texts([], [], False, ME) == ("", "")


def test_render_verb_since_last_stop_and_no_snapshot():
    events = [add("a1", 30, "one"), add("a2", 30, "two")]
    prev = snap(events)
    f = fold([*events, ev("update", "a2", 1, note="progress")])
    rows = SS.freshness(f, SID, prev, set(), {}, set(), set(), {}, NOW)
    only = SS.render_verb(rows, SS.changes(prev, f, SID), False, ME, since_last_stop=True)
    assert only.splitlines() == [SS.CHANGES_HEADER, "#a2  note     progress"]
    first_rows = SS.freshness(f, SID, None, set(), {}, set(), set(), {}, NOW)
    first = SS.render_verb(first_rows, [], True, ME, since_last_stop=True)
    assert SS.NO_SNAPSHOT in first
    assert "#a1  [ ]" in first
    assert "#a2  [ ]" in first
    assert SS.render_verb([], [], False, ME).startswith(SS.VERB_EMPTY % ME)


def test_an_unverified_worker_is_never_live_or_orphaned():
    events = [add("a1", 400), ev("lease", "a1", 300, until=at(-60), worker="b5hell")]
    rows = SS.freshness(
        fold(events), SID, snap(events), set(), {}, set(), set(), {}, NOW, unverified={"b5hell"}
    )
    assert (rows[0]["wstate"], rows[0]["cls"]) == (SS.W_UNVERIFIED, "stale")
    assert "b5hell (unverified (no stop event))" in SS.render_table(rows, me=ME)


# ---- the Stop hook, end to end through wlfix (S3) ---------------------------


def stamp(minutes_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def until(minutes_ahead: float = 60) -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + minutes_ahead * 60))


def plant(fix, *events: dict) -> None:
    """Raw events into the fixture's legacy log, stamps backdated: the store is append-only JSONL, so a backdated event is exactly what an old item looks like."""
    with fix.events.open("a", encoding="utf-8") as handle:
        for one in events:
            handle.write(json.dumps(one) + "\n")


def h_add(rid: str, age: float, text: str = "store status fixture") -> dict:
    return {
        "ev": "add",
        "id": rid,
        "at": stamp(age),
        "by": wlfix.ME,
        "s": " ",
        "o": wlfix.ME,
        "t": "(%s) %s %s" % (wlfix.ME, text, rid),
    }


def h_lease(rid: str, age: float, worker: str) -> dict:
    return {
        "ev": "lease",
        "id": rid,
        "at": stamp(age),
        "by": wlfix.ME,
        "until": until(),
        "worker": worker,
        "note": "",
        "worker_verified": False,
    }


def snap_doc(fix) -> dict:
    path = fix.stem(".state-%s.json" % wlfix.ME)
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("store_snap") or {}


def system_message(got) -> str:
    doc = json.loads(got.out) if got.out.strip() else {}
    return str(doc.get("systemMessage") or "")


STALE_ID = "5a1e0001"
BLOCKER_ID = "5a1e00b0"
QUIET_AGE = L.LADDER_RESOLVE_MIN + 10


def stale_world(fix, worker: str = "b0dead001", text: str = "store status fixture") -> None:
    fix.brief_now()
    fix.say("all done for now")
    plant(fix, h_add(STALE_ID, QUIET_AGE + 1, text), h_lease(STALE_ID, QUIET_AGE, worker))


def test_hook_blocks_a_stale_item_once_the_ladder_has_fired(wl):
    """A `[>]` item quiet past LADDER_RESOLVE_MIN with no live worker. The first stop's ladder rungs name it, so wl-stale stays out (no double block); the next stop, where those rungs already fired at that stamp, blocks with wl-stale naming it."""
    stale_world(wl)
    first = wl.run()
    assert first.decision == "block"
    assert "WL-STALE" not in first.out, "the ladder named it this stop: %s" % first.out[:600]
    second = wl.run()
    assert second.decision == "block"
    assert "WL-STALE" in second.out, second.out[:1200]
    assert "#%s  [>]  b0dead001 (gone)" % STALE_ID in second.out
    assert "#%s" % STALE_ID in system_message(second)


def test_hook_control_a_blocked_by_on_an_open_blocker_passes(wl):
    """Control: the same stale item carrying `BLOCKED_BY` on an open blocker is `waiting`, so no stop raises wl-stale for it."""
    stale_world(wl, text="store status fixture BLOCKED_BY:#%s" % BLOCKER_ID)
    plant(wl, h_add(BLOCKER_ID, 5, "the blocker"))
    wl.run()
    second = wl.run()
    assert "WL-STALE" not in second.out, second.out[:1200]
    assert "#%s  [>]" % STALE_ID in system_message(second)
    assert "waiting" in system_message(second)


def test_hook_control_a_live_verified_worker_passes(wl):
    """Control: the same stale item leased to a subagent the roster verifies live is `live`, so no stop raises wl-stale for it."""
    aid = "a5a1e00000000001"
    R.mk_sub(wl, aid, "general-purpose", 1)
    stale_world(wl, worker=aid)
    wl.run()
    second = wl.run()
    assert "WL-STALE" not in second.out, second.out[:1200]
    assert "%s (live, verified)" % aid in system_message(second)


def test_hook_no_double_block_with_roster_dead(wl):
    """An item `roster-dead` names this stop (a lease on a finished subagent) is listed with that key and never named again by wl-stale, on the ladder's first stop or after it."""
    aid = "a5a1e00000000002"
    R.mk_sub(wl, aid, "general-purpose", QUIET_AGE, last="end_turn", running=False)
    stale_world(wl, worker=aid)
    for _ in range(2):
        got = wl.run()
        assert "roster-dead" in got.out or "ROSTER" in got.out.upper(), got.out[:800]
        assert "WL-STALE" not in got.out, got.out[:1200]
    assert "[roster-dead]" in system_message(got)


def test_hook_pass_names_no_id_and_shows_the_table_and_changes(wl):
    """A stop whose message names no id, with every owned item moved, live-leased or waiting, is not blocked by wl-stale, and its systemMessage carries the table header and the change summary."""
    aid = "a5a1e00000000003"
    R.mk_sub(wl, aid, "general-purpose", 1)
    wl.brief_now()
    wl.say("all done for now")
    plant(
        wl,
        h_add("5a1e0010", QUIET_AGE + 1),
        h_lease("5a1e0010", QUIET_AGE, aid),
        h_add("5a1e0011", QUIET_AGE, "waits BLOCKED_BY:#5a1e0012"),
        h_add("5a1e0012", QUIET_AGE, "the blocker"),
    )
    wl.run()
    wl.cli("--update", wlfix.ME, "5a1e0012", "progress on the blocker")
    got = wl.run()
    assert "WL-STALE" not in got.out, got.out[:1200]
    sysmsg = system_message(got)
    assert SS.TABLE_HEADER in sysmsg
    assert SS.CHANGES_HEADER in sysmsg
    assert "#5a1e0012  note" in sysmsg


def test_hook_a_blocked_stop_advances_the_snapshot(wl):
    """A blocked stop writes `store_snap`, and the next stop's change summary lists only what moved in between."""
    wl.brief_now()
    wl.say("all done for now")
    plant(wl, h_add("5a1e0020", 30), h_add("5a1e0021", 30))
    first = wl.run()
    assert first.decision == "block"
    assert SS.NO_SNAPSHOT in first.out
    assert set(snap_doc(wl).get("items") or {}) == {"5a1e0020", "5a1e0021"}
    wl.cli("--update", wlfix.ME, "5a1e0021", "moved between the stops")
    second = wl.run()
    rows = [ln for ln in system_message(second).splitlines() if ln.startswith("#5a1e")]
    change_rows = [ln for ln in rows if "  note " in ln]
    assert change_rows == ["#5a1e0021  note     moved between the stops"], rows
    third = wl.run()
    assert SS.CHANGES_NONE in third.out


def test_hook_an_allow_with_nothing_owned_stays_silent(wl):
    """An allow with no owned open, in-flight or deferred item stays silent. Control: the same world with one owned item shows the table."""
    wl.brief_now()
    wl.say("done for now")
    wl.reg_repo()
    got = wl.run()
    assert got.decision == "allow"
    assert SS.TABLE_HEADER not in got.out
    plant(wl, h_add("5a1e0030", 1))
    assert SS.TABLE_HEADER in wl.run().out


# ---- `worklist.py --status <me> [--since-last-stop]` (S2, plan D4) ---------


def item_rows(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("#5a1e")]


def test_verb_bare_form_prints_one_row_per_owned_open_item(wl):
    plant(
        wl,
        h_add("5a1e0040", 30),
        h_add("5a1e0041", 30),
        {**h_add("5a1e0042", 30), "o": "ffff9999", "by": "ffff9999"},
    )
    got = wl.cli("--status", wlfix.ME)
    assert got.rc == 0, got.err
    assert got.out.startswith(SS.TABLE_HEADER)
    assert sorted(r.split()[0] for r in item_rows(got.out)) == ["#5a1e0040", "#5a1e0041"]
    # Control: a session owning nothing gets the one-line answer, not an empty table.
    empty = wl.cli_as("cafe1234", "--status", "cafe1234")
    assert empty.rc == 0, empty.err
    assert empty.out.startswith(SS.VERB_EMPTY % "cafe1234")


def test_verb_since_last_stop_is_read_only_and_lists_only_what_moved(wl):
    wl.brief_now()
    wl.say("all done for now")
    plant(wl, h_add("5a1e0050", 30), h_add("5a1e0051", 30))
    wl.run()
    state = wl.stem(".state-%s.json" % wlfix.ME)
    assert snap_doc(wl), "the stop planted no snapshot"
    wl.cli("--update", wlfix.ME, "5a1e0051", "moved inside the turn")
    before = state.read_bytes()
    one = wl.cli("--status", wlfix.ME, "--since-last-stop")
    two = wl.cli("--status", wlfix.ME, "--since-last-stop")
    assert one.rc == 0, one.err
    assert one.out == two.out
    assert state.read_bytes() == before, "the verb wrote the state file"
    assert item_rows(one.out) == ["#5a1e0051  note     moved inside the turn"]
    # Control: the bare form still lists both items.
    bare = item_rows(wl.cli("--status", wlfix.ME).out)
    assert sorted(r.split()[0] for r in bare if "  [ ]  " in r) == ["#5a1e0050", "#5a1e0051"]


def test_verb_with_no_snapshot_says_so_and_lists_every_item(wl):
    plant(wl, h_add("5a1e0060", 30), h_add("5a1e0061", 30))
    got = wl.cli("--status", wlfix.ME, "--since-last-stop")
    assert got.rc == 0, got.err
    assert SS.NO_SNAPSHOT in got.out
    assert sorted(r.split()[0] for r in item_rows(got.out)) == ["#5a1e0060", "#5a1e0061"]


def test_verb_a_shell_worker_reads_unverified(wl):
    plant(wl, h_add("5a1e0070", 31), h_lease("5a1e0070", 30, "b5he11001"))
    got = wl.cli("--status", wlfix.ME)
    assert got.rc == 0, got.err
    assert "b5he11001 (%s)" % SS.W_UNVERIFIED in got.out
    assert "(live, verified)" not in got.out


def test_verb_all_still_answers_the_roster_ping(wl):
    aid = "a5a1e00000000009"
    R.mk_sub(wl, aid, "general-purpose", 1)
    wl.run()
    got = wl.cli("--status", wlfix.ME, "all")
    assert "%s (general-purpose)" % aid in got.out + got.err
    assert SS.TABLE_HEADER not in got.out + got.err


def test_verb_a_wrong_prefix_is_refused(wl):
    got = wl.cli("--status", "ffff9999")
    assert got.rc != 0
    assert "identity mismatch" in got.err
    assert SS.TABLE_HEADER not in got.out
    # Control: the session's own prefix is answered.
    assert wl.cli("--status", wlfix.ME).rc == 0

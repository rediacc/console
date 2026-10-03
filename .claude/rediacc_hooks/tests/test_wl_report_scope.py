"""wl_report.unread on a SHARED branch: a stale report another session spawned is not this session's duty (2026-10-03).

After a merge left a checkout on `main`, 82 reports captured weeks earlier by seven other sessions blocked a stop as unread. The branch filter alone cannot tell a restarted session's own predecessor from a stranger, so the cut is age: a foreign report counts while it is younger than WORKLIST_DEAD_HOURS. Each case below carries a control that the same store without the trigger behaves as before.
"""

from __future__ import annotations

import datetime
import json

from rediacc_hooks.tests import wlfix

ME = "d778be9d"
PEER = "74de73ca"


def _stamp(hours_ago: float) -> str:
    t = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(tmp_path, rows):
    store = tmp_path / "store"
    store.mkdir()
    with (store / "index.jsonl").open("w", encoding="utf-8") as handle:
        for rid, session, hours in rows:
            handle.write(
                json.dumps(
                    {
                        "ev": "report",
                        "id": rid,
                        "at": _stamp(hours),
                        "branch": "main",
                        "agent": "Explore",
                        "session": session,
                        "body": "main/%s.md" % rid,
                        "bytes": 10,
                        "silent": False,
                    }
                )
                + "\n"
            )
    return store


def _ids(store, reader):
    report = wlfix.import_wl("wl_report")
    return [e["id"] for e in report.unread(store, "main", reader)]


def test_rs1_a_stale_foreign_report_is_not_this_sessions_duty(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKLIST_DEAD_HOURS", raising=False)
    store = _store(tmp_path, [("old-peer", PEER, 24 * 30)])
    assert _ids(store, ME) == [], "a month-old report from another session still surfaced"
    # CONTROL: the session that spawned it still sees it, so nothing was lost, only scoped.
    assert _ids(store, PEER) == ["old-peer"]


def test_rs2_own_recent_foreign_and_unowned_reports_still_count(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKLIST_DEAD_HOURS", raising=False)
    store = _store(
        tmp_path,
        [
            ("old-mine", ME, 24 * 30),
            ("recent-peer", PEER, 1),
            ("old-unowned", "", 24 * 30),
        ],
    )
    got = _ids(store, ME)
    assert "old-mine" in got, "this session's own old report was hidden"
    # A restarted session's predecessor is a different id, captured minutes or hours ago: it must stay visible.
    assert "recent-peer" in got, "a recent report from another session id was hidden"
    assert "old-unowned" in got, "a report with no session recorded was hidden"


def test_rs3_the_horizon_is_the_registered_dead_hours_knob(tmp_path, monkeypatch):
    store = _store(tmp_path, [("peer-3h", PEER, 3)])
    monkeypatch.setenv("WORKLIST_DEAD_HOURS", "2")
    assert _ids(store, ME) == [], "a 3h-old foreign report survived a 2h horizon"
    monkeypatch.setenv("WORKLIST_DEAD_HOURS", "24")
    assert _ids(store, ME) == ["peer-3h"], (
        "CONTROL: the same report inside a 24h horizon must count"
    )

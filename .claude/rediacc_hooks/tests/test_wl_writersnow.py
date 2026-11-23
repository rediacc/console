"""The /writers-now round record (agent/plans/PLAN-writers-now-cadence.md WN1).

The verb is driven through the real CLI against a `wlfix` sandbox and the ledger is read back from the sandbox's project root; the reader is driven directly. Every positive case has a control that differs by one planted fact.
"""

from __future__ import annotations

import datetime
import json

from rediacc_hooks.tests import wlfix

WN = wlfix.import_wl("wl_writersnow")

NOW = datetime.datetime(2026, 11, 23, 18, 0, 0, tzinfo=datetime.UTC)


def ledger_rows(wl):
    path = wl.proj / WN.LEDGER_REL
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_start_appends_a_row_and_a_second_start_within_the_hour_appends_its_own(wl):
    survey = str(wl.base / "1121-1-20261123T1800Z.md")
    first = wl.cli("--writers-now-start", wlfix.ME, survey)
    assert first.rc == 0, first.err
    second = wl.cli("--writers-now-start", wlfix.ME, survey)
    assert second.rc == 0, second.err
    rows = ledger_rows(wl)
    assert len(rows) == 2
    assert rows[0]["round"] != rows[1]["round"]
    for row, got in zip(rows, (first, second), strict=True):
        assert row["session"] == wlfix.ME
        assert row["survey"] == survey
        assert WN.C.parse_stamp(row["at"]) is not None
        assert "round %s started" % row["round"] in got.out


def test_start_refuses_a_missing_survey_and_writes_nothing(wl):
    got = wl.cli("--writers-now-start", wlfix.ME)
    assert got.rc == 2
    assert "usage: --writers-now-start" in got.err
    assert not (wl.proj / WN.LEDGER_REL).exists()


def test_start_refuses_a_foreign_identity_and_writes_nothing(wl):
    got = wl.cli("--writers-now-start", "cafe1234", str(wl.base / "s.md"))
    assert got.rc != 0
    assert "identity mismatch" in got.out + got.err
    assert not (wl.proj / WN.LEDGER_REL).exists()


def test_read_rounds_skips_a_torn_line_and_reads_an_absent_ledger_as_none(tmp_path):
    assert WN.read_rounds(tmp_path) == []
    WN.append_round(tmp_path, "aaaa1111", "/tmp/s1.md", NOW)
    with (tmp_path / WN.LEDGER_REL).open("a", encoding="utf-8") as fh:
        fh.write('{"round": "torn"\n')
    WN.append_round(tmp_path, "bbbb2222", "/tmp/s2.md", NOW + datetime.timedelta(minutes=5))
    rows = WN.read_rounds(tmp_path)
    assert [r["session"] for r in rows] == ["aaaa1111", "bbbb2222"]


def test_last_round_is_this_sessions_newest_and_ignores_a_peer(tmp_path):
    WN.append_round(tmp_path, "aaaa1111", "/tmp/old.md", NOW - datetime.timedelta(hours=2))
    WN.append_round(tmp_path, "aaaa1111", "/tmp/new.md", NOW - datetime.timedelta(minutes=10))
    WN.append_round(tmp_path, "bbbb2222", "/tmp/peer.md", NOW)
    rows = WN.read_rounds(tmp_path)
    assert WN.last_round(rows, "aaaa1111-full-session-id")["survey"] == "/tmp/new.md"
    assert WN.last_round(rows, "cccc3333") is None

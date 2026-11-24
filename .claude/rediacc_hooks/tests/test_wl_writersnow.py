"""The /writers-now round record (agent/plans/PLAN-writers-now-cadence.md WN1).

The verb is driven through the real CLI against a `wlfix` sandbox and the ledger is read back from the sandbox's project root; the reader is driven directly. Every positive case has a control that differs by one planted fact.
"""

from __future__ import annotations

import datetime
import json
import pathlib

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


def test_a_single_start_appends_exactly_one_row(wl):
    """Control of the test above: one start gives one row, so two rows there come from the second start."""
    survey = str(wl.base / "1121-1-20261123T1800Z.md")
    first = wl.cli("--writers-now-start", wlfix.ME, survey)
    assert first.rc == 0, first.err
    assert len(ledger_rows(wl)) == 1


def test_a_short_write_still_leaves_whole_terminated_lines(tmp_path, monkeypatch):
    """A write that stops after 7 bytes is continued, so the next append does not join onto a torn line (review 1f2320c0.1)."""
    real_write = WN.os.write

    def short(fd, data):
        return real_write(fd, bytes(data)[:7])

    monkeypatch.setattr(WN.os, "write", short)
    WN.append_round(tmp_path, "aaaa1111", "/tmp/s1.md", NOW)
    WN.append_round(tmp_path, "bbbb2222", "/tmp/s2.md", NOW + datetime.timedelta(minutes=5))
    text = (tmp_path / WN.LEDGER_REL).read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert [WN.json.loads(line)["session"] for line in text.splitlines()] == [
        "aaaa1111",
        "bbbb2222",
    ]


def test_a_full_write_is_one_call_per_row(tmp_path, monkeypatch):
    """Control: with no short write, each row is written by exactly one os.write."""
    calls = []
    real_write = WN.os.write

    def counting(fd, data):
        calls.append(len(data))
        return real_write(fd, data)

    monkeypatch.setattr(WN.os, "write", counting)
    WN.append_round(tmp_path, "aaaa1111", "/tmp/s1.md", NOW)
    assert len(calls) == 1


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


# ---- WN3: the self-review seeds ------------------------------------------------

RV = wlfix.import_wl("wl_review")
ME8 = "aaaa1111"
SINCE = NOW - datetime.timedelta(hours=1)
IN_WINDOW = "2026-11-23T17:30:00Z"
BEFORE = "2026-11-23T15:00:00Z"
REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "commands" / "writers-now.md"
OUTSIDE_OWNS = "- scripts/foo.ts needs the same guard; it is outside my Owns, so the lead edits it"


def item(iid, state, text, first=BEFORE, upd=BEFORE, owner=ME8):
    return {"id": iid, "state": state, "owner": owner, "text": text, "first": first, "upd": upd}


def review(at, resolution="open"):
    finding = RV.Finding(
        id="F1",
        severity="medium",
        file=".claude/hooks/stop/wl_x.py",
        line=12,
        anchor="x = 1",
        claim="the branch drops the error",
        resolution=resolution,
    )
    return (pathlib.Path("r.md"), RV.Review(sha="ab" * 20, reviewed_at=at, findings=[finding]))


def report(body, session=ME8, at=IN_WINDOW):
    entry = {"id": "c739e4aa739", "agent": "writer", "session": session, "at": at}
    return (entry, body)


def fixture_world():
    items = [
        item("b2b2b2b2", "x", "(aaaa1111) the blocker, now done"),
        item("a1a1a1a1", " ", "(aaaa1111) rerun the drill BLOCKED_BY:#b2b2b2b2"),
    ]
    reports = [report("## Report\nAll boxes done.\n" + OUTSIDE_OWNS + "\nclose: nothing\n")]
    return items, [review(IN_WINDOW)], reports


def test_the_fixture_session_produces_exactly_the_three_seeds() -> None:
    items, reviews, reports = fixture_world()
    seeds = WN.collect_seeds(items, reviews, reports, ME8, SINCE)
    assert [s["kind"] for s in seeds] == ["report", "unblocked", "review"], seeds
    assert "outside my Owns" in seeds[0]["text"]
    assert seeds[1]["ref"] == "#a1a1a1a1"
    assert "#b2b2b2b2 closed" in seeds[1]["text"]
    assert seeds[2]["ref"] == "abababab F1"


def test_controls_each_one_fact_changed_drops_its_seed() -> None:
    items, _reviews, _reports = fixture_world()
    # The blocker still open: the blocked item is waiting, not unblocked, and too old to be new.
    assert WN.item_seeds([dict(items[0], state=" "), items[1]], ME8, SINCE) == []
    # A peer's item with a closed blocker is the peer's to pick up.
    assert WN.item_seeds([items[0], dict(items[1], owner="bbbb2222")], ME8, SINCE) == []
    # A finding already resolved, and a review written before the window.
    assert WN.review_seeds([review(IN_WINDOW, "fixed | abc1234 | x")], SINCE) == []
    assert WN.review_seeds([review(BEFORE)], SINCE) == []
    # A peer's report, a report before the window, and a TICK line owing nothing.
    assert WN.report_seeds([report(OUTSIDE_OWNS, session="bbbb2222")], ME8, SINCE) == []
    assert WN.report_seeds([report(OUTSIDE_OWNS, at=BEFORE)], ME8, SINCE) == []
    tick = "TICK PLAN-x.md#0b762e5b done commits=abc landed=all owed=-"
    assert WN.report_seeds([report(tick)], ME8, SINCE) == []
    owing = "TICK PLAN-x.md#0b762e5b partial commits=abc landed=C1 owed=C2:live"
    assert len(WN.report_seeds([report(owing)], ME8, SINCE)) == 1


def test_an_open_item_added_in_the_window_is_a_seed_and_a_held_one_is_not() -> None:
    fresh = item("c3c3c3c3", " ", "(aaaa1111) follow-up defect", first=IN_WINDOW, upd=IN_WINDOW)
    held = dict(fresh, id="d4d4d4d4", state=">")
    got = WN.item_seeds([fresh, held], ME8, SINCE)
    assert [s["ref"] for s in got] == ["#c3c3c3c3"]


def test_one_source_past_the_cap_counts_the_rest_and_leaves_the_others_whole() -> None:
    items, reviews, _reports = fixture_world()
    lines = "\n".join("%d. edited f%d.py, outside my Owns" % (i, i) for i in range(WN.KIND_MAX + 5))
    chatty = [report(lines, at=IN_WINDOW) for _ in range(2)]
    for n, (entry, _body) in enumerate(chatty):
        entry["id"] = "rep%d" % n
    seeds = WN.collect_seeds(items, reviews, chatty, ME8, SINCE)
    kinds = [s["kind"] for s in seeds]
    # Two reports at REPORT_LINES_MAX lines each stay under the cap: no `more` seed.
    assert kinds.count("report") == 2 * WN.REPORT_LINES_MAX
    assert "more" not in kinds
    many = [report("outside my Owns", at=IN_WINDOW) for _ in range(WN.KIND_MAX + 3)]
    seeds = WN.collect_seeds(items, reviews, many, ME8, SINCE)
    kinds = [s["kind"] for s in seeds]
    assert kinds.count("report") == WN.KIND_MAX
    more = [s for s in seeds if s["kind"] == "more"]
    assert len(more) == 1
    assert more[0]["text"].startswith("3 more report seed(s)")
    assert kinds[-2:] == ["unblocked", "review"]


def test_an_unreadable_report_body_is_its_own_seed_not_an_empty_report() -> None:
    entry = dict(report("")[0], read_error="FileNotFoundError: gone")
    got = WN.report_seeds([(entry, None)], ME8, SINCE)
    assert len(got) == 1
    assert "body unreadable (FileNotFoundError: gone)" in got[0]["text"]


def test_start_round_writes_the_seeds_beside_the_survey_and_counts_them(tmp_path) -> None:
    items, reviews, reports = fixture_world()
    survey = tmp_path / "wn" / "1121-1-20261123T1800Z.md"
    seen = []

    def reports_since(since):
        seen.append(since)
        return reports

    row, text = WN.start_round(tmp_path, ME8, str(survey), NOW, items, reviews, reports_since)
    seeds_file = tmp_path / "wn" / "1121-1-20261123T1800Z-seeds.md"
    assert row["seeds"] == str(seeds_file)
    assert row["seed_count"] == 3
    assert seeds_file.read_text(encoding="utf-8") == text
    assert "round %s" % row["round"] in text
    assert text.count("\n- [S") == 3
    # No earlier round: the window reaches LOOKBACK_H hours back.
    assert seen == [NOW - datetime.timedelta(hours=WN.LOOKBACK_H)]
    # The second round's window starts at the first round.
    later = NOW + datetime.timedelta(minutes=20)
    WN.start_round(tmp_path, ME8, str(survey), later, items, reviews, reports_since)
    assert seen[-1] == NOW
    assert WN.read_rounds(tmp_path)[0]["round"] == row["round"]


def test_the_cli_prints_the_seeds_path(wl) -> None:
    survey = wl.base / "1121-1-20261123T1800Z.md"
    got = wl.cli("--writers-now-start", wlfix.ME, str(survey))
    assert got.rc == 0, got.err
    seeds_file = wl.base / "1121-1-20261123T1800Z-seeds.md"
    assert seeds_file.is_file()
    assert "seeds: 0 in %s" % seeds_file in got.out
    assert ledger_rows(wl)[0]["seeds"] == str(seeds_file)


def test_the_skill_hands_the_seeds_file_to_the_survey() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "--writers-now-start <me> <survey path>" in text
    assert "<branch>-<UTC stamp>-seeds.md" in text
    assert "classify EVERY seed" in text
    assert "`## Seeds`" in text


# ---- WN2: the cadence check ----------------------------------------------------

PS = wlfix.import_wl("wl_prscope")
E = wlfix.import_wl("wl_effort")
DEV = PS.LoopState(kind=PS.LIVE, role=PS.DEVELOPMENT)


def rounds_at(tmp_path, *minutes_ago, session=ME8):
    for m in minutes_ago:
        WN.append_round(tmp_path, session, "/tmp/s.md", NOW - datetime.timedelta(minutes=m))
    return WN.read_rounds(tmp_path)


def test_due_fires_with_no_round_and_with_a_61_minute_old_round(tmp_path) -> None:
    fires, facts = WN.due([], ME8, NOW, 4, DEV)
    assert fires
    assert facts["last"] is None
    fires, facts = WN.due(rounds_at(tmp_path, 61), ME8, NOW, 4, DEV)
    assert fires
    assert int(facts["age"]) == 61


def test_due_is_silent_inside_the_window_and_for_a_peer_round_it_still_fires(tmp_path) -> None:
    assert WN.due(rounds_at(tmp_path, 59), ME8, NOW, 4, DEV)[0] is False
    peer = tmp_path / "peer"
    assert WN.due(rounds_at(peer, 5, session="bbbb2222"), ME8, NOW, 4, DEV)[0] is True


def test_due_stands_down_in_the_landing_tree_its_babysit_phase_and_the_merge_phase() -> None:
    landing = PS.LoopState(kind=PS.LIVE, role=PS.LANDING)
    fires, facts = WN.due([], ME8, NOW, 4, landing)
    assert not fires
    assert facts["why"] == "the landing tree"
    # The babysit phase is the landing tree working its open PR (L-CI, L-FIX, L-REVIEW): the role decides.
    babysit = PS.LoopState(kind=PS.LIVE, role=PS.LANDING, pr=7, branch="1121-1")
    assert WN.due([], ME8, NOW, 4, babysit)[0] is False
    merged = PS.LoopState(kind=PS.MERGED, role=PS.DEVELOPMENT)
    fires, facts = WN.due([], ME8, NOW, 4, merged)
    assert not fires
    assert facts["why"] == "the merge phase"


def test_due_is_silent_with_an_empty_promoted_queue() -> None:
    assert WN.due([], ME8, NOW, 0, DEV)[0] is False
    # Control: one open box and the same world fires.
    assert WN.due([], ME8, NOW, 1, DEV)[0] is True


def test_the_restated_loop_names_match_wl_prscope() -> None:
    assert WN.LANDING_ROLE == PS.LANDING
    assert WN.MERGED_KIND == PS.MERGED


def test_the_effort_row_blocks_at_high_and_advises_at_smart() -> None:
    table, _problems = E.load()
    assert table["checks"]["writers-now-due"] == {"block": "high", "advise": "smart"}
    assert E.verdict("writers-now-due", "high") == E.BLOCK
    assert E.verdict("writers-now-due", "smart") == E.ADVISE
    assert E.verdict("writers-now-due", "low") == E.OFF


def plant_promoted(wl, boxes="- [ ] B1 [writer] one open box\n"):
    plan = wl.proj / "agent" / "plans" / "PLAN-wn-fixture.md"
    plan.write_text(
        "# PLAN: wn fixture\nStatus: approved\n\n## Boxes\n\n" + boxes, encoding="utf-8"
    )
    queue = wl.proj / "agent" / "plans" / "QUEUE.md"
    text = queue.read_text(encoding="utf-8")
    queue.write_text(
        text.replace("## Promoted\n", "## Promoted\n\n1. agent/plans/PLAN-wn-fixture.md\n", 1),
        encoding="utf-8",
    )


def test_promoted_open_counts_the_fixture_queue(wl) -> None:
    plant_promoted(wl, "- [ ] B1 open\n- [x] B2 done\n- [ ] B3 open\n")
    assert WN.promoted_open(wl.proj) == 2


def test_stop_hook_blocks_at_high_with_no_round(wl) -> None:
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    plant_promoted(wl)
    got = wl.run()
    assert got.decision == "block", got.out[:600]
    assert "WRITERS-NOW DUE" in got.out, got.out[:1200]
    assert "--writers-now-start %s" % wlfix.ME in got.out


def test_stop_hook_control_a_round_ten_minutes_ago_is_silent(wl) -> None:
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    plant_promoted(wl)
    WN.append_round(wl.proj, wlfix.ME, "/tmp/s.md", WN.C.utcnow() - datetime.timedelta(minutes=10))
    wl.check_quiet("WRITERS-NOW DUE", "a round inside the hour")


def test_stop_hook_control_no_promoted_box_is_silent(wl) -> None:
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    plant_promoted(wl, "- [x] B1 done\n")
    wl.check_quiet("WRITERS-NOW DUE", "every Promoted box ticked")

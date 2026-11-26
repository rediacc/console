"""The /writers-now round record (agent/plans/PLAN-writers-now-cadence.md WN1).

The verb is driven through the real CLI against a `wlfix` sandbox and the ledger is read back from the sandbox's project root; the reader is driven directly. Every positive case has a control that differs by one planted fact.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import re

import pytest

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
    """One round per age, each with its own survey written a minute after its start, so each round counts."""
    for m in minutes_ago:
        at = NOW - datetime.timedelta(minutes=m)
        survey = tmp_path / ("s-%s-%d.md" % (session, m))
        WN.append_round(tmp_path, session, str(survey), at)
        survey.write_text("survey %s %d\n" % (session, m), encoding="utf-8")
        stamp = (at + datetime.timedelta(minutes=1)).timestamp()
        WN.os.utime(survey, (stamp, stamp))
    return WN.read_rounds(tmp_path)


def test_due_fires_with_no_round_and_with_a_21_minute_old_round(tmp_path) -> None:
    fires, facts = WN.due([], ME8, NOW, 4, DEV)
    assert fires
    assert facts["last"] is None
    assert WN.WINDOW_MIN == 20
    fires, facts = WN.due(rounds_at(tmp_path, 21), ME8, NOW, 4, DEV)
    assert fires
    assert int(facts["age"]) == 21


def test_due_is_silent_inside_the_window_and_for_a_peer_round_it_still_fires(tmp_path) -> None:
    assert WN.due(rounds_at(tmp_path, 19), ME8, NOW, 4, DEV)[0] is False
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
    # A survey still being written (no file yet, 10 minutes in) counts as in progress.
    survey = wl.base / "wn" / "in-progress.md"
    WN.append_round(wl.proj, wlfix.ME, str(survey), WN.C.utcnow() - datetime.timedelta(minutes=10))
    wl.check_quiet("WRITERS-NOW DUE", "a round inside the window")


def test_stop_hook_control_no_promoted_box_is_silent(wl) -> None:
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    plant_promoted(wl, "- [x] B1 done\n")
    wl.check_quiet("WRITERS-NOW DUE", "every Promoted box ticked")


def test_overflow_is_counted_per_kind_when_a_group_mixes_unblocked_and_item_seeds(monkeypatch):
    mixed = [{"kind": "unblocked", "ref": "#u%d" % i, "text": "t"} for i in range(WN.KIND_MAX + 2)]
    mixed += [{"kind": "item", "ref": "#i%d" % i, "text": "t"} for i in range(3)]
    monkeypatch.setattr(WN, "item_seeds", lambda *_args: mixed)
    seeds = WN.collect_seeds([], [], [], ME8, SINCE)
    more = {s["ref"]: s["text"] for s in seeds if s["kind"] == "more"}
    assert more["unblocked"].startswith("2 more unblocked seed(s)")
    assert more["item"].startswith("3 more item seed(s)")
    # control: a group that fits under the cap says nothing
    monkeypatch.setattr(WN, "item_seeds", lambda *_args: mixed[:3])
    assert not [s for s in WN.collect_seeds([], [], [], ME8, SINCE) if s["kind"] == "more"]


def test_a_bare_owed_word_in_report_prose_is_not_a_seed() -> None:
    assert WN.report_seeds([report("Owed: none")], ME8, SINCE) == []
    assert len(WN.report_seeds([report("TICK x partial owed=C2:live")], ME8, SINCE)) == 1


def test_last_round_keeps_a_pre_compaction_row_of_the_same_session(monkeypatch, tmp_path) -> None:
    WN.append_round(tmp_path, "dddd4444", "/tmp/old.md", NOW)
    rows = WN.read_rounds(tmp_path)
    assert WN.last_round(rows, "eeee5555") is None
    monkeypatch.setattr(WN.C, "owned_by_me", lambda owner, _me: owner == "dddd4444")
    assert WN.last_round(rows, "eeee5555")["survey"] == "/tmp/old.md"


def test_an_unreadable_report_body_comes_back_as_none_with_the_error(monkeypatch, tmp_path) -> None:
    wl_report = wlfix.import_wl("wl_report")
    entry = {"session": ME8, "at": IN_WINDOW, "body": "gone.md", "id": "r1"}
    monkeypatch.setattr(wl_report, "store_root", lambda _start: tmp_path)
    monkeypatch.setattr(wl_report, "read_index", lambda _store: [entry])
    got = WN.gather_reports(tmp_path, ME8, SINCE)
    assert got[0][1] is None
    assert got[0][0]["read_error"].startswith("FileNotFoundError")
    (tmp_path / "gone.md").write_text("owed=C1:live\n", encoding="utf-8")  # control: readable
    assert WN.gather_reports(tmp_path, ME8, SINCE)[0][1] == "owed=C1:live\n"


# ---- a round counts only once its survey is real (operator report 2026-11-24, PR-TASK 79b7e92e) ----

SURVEY_TEXT = "# survey\n\n| box | group |\n|---|---|\n| B1 | CODE |\n"


def write_survey(path, text, at):
    """Write `text` to `path` with its mtime set to `at` (a datetime), the way a survey agent or a `cp` leaves it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = at.timestamp()
    WN.os.utime(path, (stamp, stamp))
    return path


# Round ages derived from the tuned timings: inside the survey grace, and past the grace but inside the window.
INSIDE_GRACE = WN.SURVEY_GRACE_MIN - 5
PAST_GRACE = WN.SURVEY_GRACE_MIN + 2
FIRST_ROUND_AGO = WN.WINDOW_MIN + 15
assert INSIDE_GRACE > 0
assert PAST_GRACE < WN.WINDOW_MIN


def two_rounds(tmp_path, second_text, second_written, second_ago=INSIDE_GRACE):
    """A real round outside the window, then a round `second_ago` minutes ago whose survey holds `second_text` written `second_written` minutes ago (None: never written)."""
    first = tmp_path / "wn" / "r1.md"
    t1 = NOW - datetime.timedelta(minutes=FIRST_ROUND_AGO)
    WN.append_round(tmp_path, ME8, str(first), t1)
    write_survey(first, SURVEY_TEXT, t1 + datetime.timedelta(minutes=5))
    second = tmp_path / "wn" / "r2.md"
    t2 = NOW - datetime.timedelta(minutes=second_ago)
    WN.append_round(tmp_path, ME8, str(second), t2)
    if second_written is not None:
        write_survey(second, second_text, NOW - datetime.timedelta(minutes=second_written))
    return WN.read_rounds(tmp_path)


def test_a_copied_survey_does_not_count_and_the_message_says_copied(tmp_path) -> None:
    # cp before --writers-now-start: the same bytes, older than the round.
    rows = two_rounds(tmp_path, SURVEY_TEXT, second_written=INSIDE_GRACE + 1)
    fires, facts = WN.due(rows, ME8, NOW, 4, DEV, root=tmp_path)
    assert fires
    assert "written before the round started" in WN.due_fields(facts, ME8)["last"]


def test_a_survey_copied_after_the_start_still_does_not_count(tmp_path) -> None:
    # The same bytes written after the start: the digest catches it.
    rows = two_rounds(tmp_path, SURVEY_TEXT, second_written=INSIDE_GRACE - 5)
    fires, facts = WN.due(rows, ME8, NOW, 4, DEV, root=tmp_path)
    assert fires
    assert "same content as the previous round" in WN.due_fields(facts, ME8)["last"]


def test_control_a_real_survey_written_after_the_start_counts(tmp_path) -> None:
    rows = two_rounds(tmp_path, SURVEY_TEXT + "| B2 | LIVE |\n", second_written=INSIDE_GRACE - 5)
    assert WN.due(rows, ME8, NOW, 4, DEV, root=tmp_path)[0] is False


def test_a_missing_survey_counts_for_the_grace_then_stops(tmp_path) -> None:
    rows = two_rounds(tmp_path, "", second_written=None, second_ago=INSIDE_GRACE)
    assert WN.due(rows, ME8, NOW, 4, DEV, root=tmp_path)[0] is False
    later = tmp_path / "later"
    rows = two_rounds(later, "", second_written=None, second_ago=PAST_GRACE)
    fires, facts = WN.due(rows, ME8, NOW, 4, DEV, root=later)
    assert fires
    assert "survey never written" in WN.due_fields(facts, ME8)["last"]


def test_the_message_names_an_old_round_as_older_than_the_window(tmp_path) -> None:
    first = tmp_path / "wn" / "r1.md"
    t1 = NOW - datetime.timedelta(minutes=FIRST_ROUND_AGO)
    WN.append_round(tmp_path, ME8, str(first), t1)
    write_survey(first, SURVEY_TEXT, t1 + datetime.timedelta(minutes=5))
    fires, facts = WN.due(WN.read_rounds(tmp_path), ME8, NOW, 4, DEV, root=tmp_path)
    assert fires
    assert "older than %d min" % WN.WINDOW_MIN in WN.due_fields(facts, ME8)["last"]


def test_start_refuses_an_existing_survey_identical_to_the_previous_rounds(wl) -> None:
    first = wl.base / "wn" / "1121-1-20261124T0825Z.md"
    got = wl.cli("--writers-now-start", wlfix.ME, str(first))
    assert got.rc == 0, got.err
    first.write_text(SURVEY_TEXT, encoding="utf-8")
    copied = wl.base / "wn" / "1121-1-20261124T0930Z.md"
    copied.write_text(SURVEY_TEXT, encoding="utf-8")
    got = wl.cli("--writers-now-start", wlfix.ME, str(copied))
    assert got.rc != 0
    assert "a copied survey is not a round" in got.err
    assert "writers-now-due" in got.err
    assert len(ledger_rows(wl)) == 1
    assert not (wl.base / "wn" / "1121-1-20261124T0930Z-seeds.md").exists()
    # Control: a fresh path starts the round and records the previous survey's digest.
    fresh = wl.base / "wn" / "1121-1-20261124T0931Z.md"
    got = wl.cli("--writers-now-start", wlfix.ME, str(fresh))
    assert got.rc == 0, got.err
    rows = ledger_rows(wl)
    assert len(rows) == 2
    assert rows[1]["prev_survey_digest"] == WN.survey_digest(first)


# ---- R20261125.3 (agent/plans/PLAN-stop-hook-retro-20261125.md friction 3): a live survey counts past the timer.
SURVEY_NAME = "1121-1-20261124T2349Z.md"


def missing_round(tmp_path, minutes_ago, round_id="315bd55a"):
    """One round of this session whose survey file was never written, started `minutes_ago` before NOW."""
    survey = tmp_path / "wn" / SURVEY_NAME
    WN.append_round(
        tmp_path, ME8, str(survey), NOW - datetime.timedelta(minutes=minutes_ago), round_id
    )
    return WN.read_rounds(tmp_path)[-1]


def bound_live(prompts, items=(), live_ids=()):
    """`due`'s live callable, bound to one fixture world the way the Stop hook binds it to the event."""
    return lambda row: WN.survey_live(row, prompts, list(items), set(live_ids))


def test_a_round_past_the_grace_with_a_live_survey_agent_counts(tmp_path) -> None:
    row = missing_round(tmp_path, PAST_GRACE)
    prompts = {"a7795c6b": "Survey the Promoted plans and write /tmp/writers-now/%s" % SURVEY_NAME}
    live = WN.survey_live(row, prompts, [], set())
    assert live is True
    assert WN.judge_round(tmp_path, row, None, NOW, live) == ""
    assert WN.due([row], ME8, NOW, 4, DEV, root=tmp_path, live=bound_live(prompts))[0] is False


def test_the_same_round_with_no_live_agent_is_never_written(tmp_path) -> None:
    row = missing_round(tmp_path, PAST_GRACE)
    prompts = {"x1": "an unrelated writer brief"}
    live = WN.survey_live(row, prompts, [], set())
    assert live is False
    assert WN.judge_round(tmp_path, row, None, NOW, live) == WN.WHY_NEVER_WRITTEN
    fires, facts = WN.due([row], ME8, NOW, 4, DEV, root=tmp_path, live=bound_live(prompts))
    assert fires
    assert facts["not_counted"] == WN.WHY_NEVER_WRITTEN


def test_a_round_inside_the_grace_with_no_agent_still_counts_on_the_timer(tmp_path) -> None:
    row = missing_round(tmp_path, INSIDE_GRACE)
    assert WN.judge_round(tmp_path, row, None, NOW, False) == ""
    assert WN.due([row], ME8, NOW, 4, DEV, root=tmp_path, live=bound_live({}))[0] is False


def test_a_live_leased_item_naming_the_round_is_a_witness_and_a_dead_lease_is_not(tmp_path) -> None:
    row = missing_round(tmp_path, PAST_GRACE)
    held = {"id": "c0ffee01", "state": ">", "worker": "w-live", "text": "survey", "lease_note": ""}
    held["lease_note"] = "writers-now round 315bd55a survey"
    assert WN.survey_live(row, {}, [held], {"w-live"}) is True
    assert WN.survey_live(row, {}, [held], {"w-other"}) is False
    assert WN.survey_live(row, {}, [dict(held, state=" ")], {"w-live"}) is False


def test_a_written_copied_survey_is_still_a_copy_while_live(tmp_path) -> None:
    """Liveness answers only a MISSING survey: a file written before the start stays a copy."""
    row = missing_round(tmp_path, 20)
    path = tmp_path / "wn" / SURVEY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old\n", encoding="utf-8")
    stamp = (NOW - datetime.timedelta(minutes=30)).timestamp()
    WN.os.utime(path, (stamp, stamp))
    assert WN.judge_round(tmp_path, row, None, NOW, True) == WN.WHY_COPIED_OLD


def _stale_round(wl):
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    plant_promoted(wl)
    survey = wl.base / "wn" / SURVEY_NAME
    WN.append_round(
        wl.proj, wlfix.ME, str(survey), WN.C.utcnow() - datetime.timedelta(minutes=PAST_GRACE)
    )


def test_stop_hook_a_live_task_naming_the_survey_keeps_a_round_past_the_grace_counting(wl) -> None:
    _stale_round(wl)
    wl.bg = json.dumps(
        [
            {
                "id": "sv1",
                "type": "shell",
                "status": "running",
                "description": "writers-now survey into %s" % SURVEY_NAME,
            }
        ]
    )
    wl.check_quiet("WRITERS-NOW DUE", "a live task is still writing the survey")


def test_stop_hook_control_an_unrelated_live_task_still_fires(wl) -> None:
    _stale_round(wl)
    wl.bg = json.dumps(
        [{"id": "sv1", "type": "shell", "status": "running", "description": "long CI watch"}]
    )
    got = wl.run()
    assert "WRITERS-NOW DUE" in got.out, got.out[:1200]
    assert WN.WHY_NEVER_WRITTEN in got.out, got.out[:1200]


def test_a_live_witness_stops_counting_after_the_liveness_cap(tmp_path) -> None:
    """Finding ec1021d6.2: a task naming the survey for the whole session must not silence the check without bound."""
    inside = missing_round(tmp_path, WN.SURVEY_LIVE_MAX_MIN - 5)
    assert WN.judge_round(tmp_path, inside, None, NOW, True) == ""
    past = missing_round(tmp_path, WN.SURVEY_LIVE_MAX_MIN + 5)
    assert WN.judge_round(tmp_path, past, None, NOW, True) == WN.WHY_NEVER_WRITTEN


def test_stop_hook_a_live_subagent_naming_the_survey_keeps_a_round_past_the_grace_counting(
    wl,
) -> None:
    """Finding ec1021d6.3: the agent-type branch (meta plus first prompt) through the Stop segment."""
    _stale_round(wl)
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "claude")
    root = wl.base / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(wl.proj))
    folder = root / wlfix.SID / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    tid = "a9999888877776666"
    (folder / ("agent-%s.meta.json" % tid)).write_text(
        json.dumps({"agentType": "Explore", "description": "survey", "spawnDepth": 1}),
        encoding="utf-8",
    )
    (folder / ("agent-%s.jsonl" % tid)).write_text(
        json.dumps(
            {"type": "user", "message": {"content": "Write the survey to /tmp/wn/%s" % SURVEY_NAME}}
        )
        + "\n",
        encoding="utf-8",
    )
    wl.bg = json.dumps(
        [{"id": tid, "type": "subagent", "status": "running", "description": "unrelated words"}]
    )
    wl.check_quiet("WRITERS-NOW DUE", "a live subagent is still writing the survey")


# ---- review findings of CL-W-HOOKS-STOP-4 -----------------------------------------------
# Each case names its finding. A positive case has a control that differs by one planted fact.

W = wlfix.import_wl("wl_worktrees")

# ---- wl_worktrees: hold owner tags (c9c88f05.1) -----------------------------------------


def test_a_short_lease_owner_agrees_with_its_own_full_tag_and_a_short_tag_agrees_with_no_one():
    assert W._tags_agree("abc", "abc12345")
    assert W._tags_agree("abc12345", "abc1")
    # Controls: the TAG stays at least TAG_MIN_CHARS long, an empty owner agrees with nothing, a stranger never agrees.
    assert not W._tags_agree("abc12345", "ab")
    assert not W._tags_agree("abc12345", "")
    assert not W._tags_agree("", "abc12345")
    assert not W._tags_agree("abc12345", "abd12345")
    # d798c543.1: a short owner (the lease record's own field) agrees only with tags it prefixes, never a stranger's.
    assert not W._tags_agree("abc", "abd12345")
    assert not W._tags_agree("a", "bcde1234")


def test_owner_problem_honours_a_short_owner_hold_and_still_refuses_a_peer():
    item = {"id": "ac6a4f6b", "owner": "abc12345"}
    assert W.owner_problem("abc12345", item, "abc") == ""
    assert "not the lease owner" in W.owner_problem("babe0000", item, "abc")


# ---- wl_writersnow: the survey witness (ec1021d6.4) -------------------------------------


def test_a_survey_witness_names_the_whole_file_not_the_tail_of_a_longer_one():
    row = {"survey": "/tmp/writers-now/1121-1-20261126T1723Z-r4.md", "round": "r"}
    mine = "write the survey to /tmp/writers-now/1121-1-20261126T1723Z-r4.md and return"
    longer = "write the survey to /tmp/writers-now/1121-1-20261126T1723Z-r4-b.md and return"
    tail = "write the survey to /tmp/writers-now/other-1121-1-20261126T1723Z-r4.md and return"
    assert WN.survey_live(row, {"t1": mine}, (), ())
    assert WN.survey_live(row, {"t1": "reads 1121-1-20261126T1723Z-r4.md."}, (), ())
    assert not WN.survey_live(row, {"t1": longer}, (), ())
    assert not WN.survey_live(row, {"t1": tail}, (), ())


# ---- wl_writersnow: the ticked count and an exhausted survey (7d036d68.1 and .2) ----------


def _cap(**over):
    cap = {
        "round": "r1",
        "read": True,
        "free": [],
        "live": 3,
        "floor": WN.CAPACITY_FLOOR,
        "ticked": 0,
        "age": WN.REFRESH_GAP_MIN + 1,
    }
    cap.update(over)
    return cap


OPEN = {"why": "", "open": 5}


def test_an_exhausted_survey_names_a_new_round_at_any_roster_size_once_it_is_old_enough():
    for live in (0, WN.CAPACITY_FLOOR, WN.CAPACITY_FLOOR + 8):
        kind, why = WN.assess(False, OPEN, _cap(live=live))
        assert kind == "due", live
        assert why == WN.WHY_EXHAUSTED % "r1"
    # Controls: a survey younger than the gap, and one that still holds a free cluster above the floor, stay silent.
    assert WN.assess(False, OPEN, _cap(live=20, age=WN.REFRESH_GAP_MIN - 1)) == ("", "")
    free = [{"id": "CL-A", "sigs": ["a" * 8], "head": "h"}]
    assert WN.assess(False, OPEN, _cap(live=20, free=free)) == ("", "")


def test_the_ticked_count_is_the_table_sigs_ticked_now_and_no_other_sig(tmp_path):
    survey = tmp_path / "s.md"
    survey.write_text(
        "| aaaaaaaa | A | CODE | none | n |\n| bbbbbbbb | B | CODE | none | n |\n"
        "## 4. CODE boxes clustered by shared files\n### Startable now\n"
        "- **CL-X (1)**: P A aaaaaaaa + B bbbbbbbb Files: f\n",
        encoding="utf-8",
    )
    rows = [
        {"round": "r1", "session": "deadbeef", "at": "2026-11-26T17:00:00Z", "survey": str(survey)}
    ]
    got = WN.capacity(rows, "deadbeef", tmp_path, [], 2, lambda: {"aaaaaaaa", "cccccccc"}, NOW)
    assert got["read"]
    assert got["ticked"] == 1
    got = WN.capacity(rows, "deadbeef", tmp_path, [], 2, lambda: {"cccccccc"}, NOW)
    assert got["ticked"] == 0


# ---- wl_writersnow: an unreadable Promoted plan (bd9a688e.1) ----------------------------


def test_promoted_open_raises_for_an_unreadable_plan_instead_of_adding_nothing(wl):
    plant_promoted(wl, "- [ ] B1 open\n")
    assert WN.promoted_open(wl.proj) == 1
    queue = wl.proj / "agent" / "plans" / "QUEUE.md"
    queue.write_text(
        queue.read_text(encoding="utf-8").replace(
            "## Promoted\n", "## Promoted\n\n2. agent/plans/PLAN-wn-gone.md\n", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"PLAN-wn-gone\.md"):
        WN.promoted_open(wl.proj)


# ---- worklist.py: the landing-record twin and the wl_cli bind (1cd88702.4, abf92494.1, 5a1c6e01.1) ----

WLK = wlfix.import_wl("worklist")
WCLI = wlfix.import_wl("wl_cli")
WGIT = wlfix.import_wl("wl_git")


class _Policy:
    def __init__(self):
        self.calls = []

    def read_landing_record(self, tree):
        self.calls.append(tree)
        return {"path": tree, "branch": "1121-1"}, ""


def _landing_world(monkeypatch, tmp_path, policy):
    common = tmp_path / "common"
    common.mkdir(exist_ok=True)
    (common / WLK.LANDING_RECORD_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(WLK, "_local_git_dirs", lambda _tree: (common / "wt", common))
    monkeypatch.setattr(WLK, "_local_commit_policy", policy)
    WLK._LANDING_READS.clear()
    for name in ("t1", "t2"):
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / ".git").write_text("gitdir: x\n", encoding="utf-8")
    return tmp_path / "t1", tmp_path / "t2"


def test_the_landing_read_is_cached_per_tree_and_record_version(monkeypatch, tmp_path):
    policy = _Policy()
    t1, t2 = _landing_world(monkeypatch, tmp_path, lambda: policy)
    assert WLK._local_read_landing_record(t1)[0]["branch"] == "1121-1"
    WLK._local_read_landing_record(t1)
    assert len(policy.calls) == 1, "the same tree and record are read once"
    WLK._local_read_landing_record(t2)
    assert len(policy.calls) == 2, "another tree over the same record is read again"
    WLK._LANDING_READS.clear()


def test_any_failure_loading_the_validator_is_a_problem_not_a_crash(monkeypatch, tmp_path):
    def broken():
        raise RuntimeError("boom")

    t1, _t2 = _landing_world(monkeypatch, tmp_path, broken)
    rec, why = WLK._local_read_landing_record(t1)
    assert rec is None
    assert "could not be loaded (RuntimeError: boom)" in why
    # Control: a loadable validator gives the record and no problem.
    _landing_world(monkeypatch, tmp_path, _Policy)
    rec, why = WLK._local_read_landing_record(t1)
    assert rec
    assert not why
    WLK._LANDING_READS.clear()


def _load_worklist_copy(monkeypatch, bind):
    monkeypatch.setattr(WCLI, "bind", bind)
    spec = importlib.util.spec_from_file_location("_wl_bind_copy", wlfix.HOOK)
    assert spec
    assert spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_bind_that_fails_makes_wl_cli_a_broken_sibling_shim(monkeypatch):
    def bad(_host):
        raise KeyError("MISSING_GLOBAL")

    mod = _load_worklist_copy(monkeypatch, bad)
    assert mod._BROKEN["wl_cli"].startswith("bind: KeyError")
    with pytest.raises(RuntimeError, match="sibling module wl_cli is unusable"):
        _ = mod.CLI.anything
    # Control: a bind that succeeds leaves wl_cli whole.
    good = _load_worklist_copy(monkeypatch, lambda _host: None)
    assert "wl_cli" not in good._BROKEN


# ---- wl_cli: the tick's submodule probe (26dc7587.2) -------------------------------------


def test_the_commit_ref_probe_skips_a_submodule_that_is_not_checked_out(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "private" / "out").mkdir(parents=True)
    (root / "private" / "in" / ".git").mkdir(parents=True)
    (root / ".gitmodules").write_text(
        '[submodule "private/out"]\n\tpath = private/out\n\turl = x\n'
        '[submodule "private/in"]\n\tpath = private/in\n\turl = x\n',
        encoding="utf-8",
    )
    cwds = []

    def probe(*_args, cwd, **_kw):
        cwds.append(str(cwd))
        return 1, "", ""

    monkeypatch.setattr(WGIT, "run_git", probe)
    got = WCLI.commit_ref_problem(str(root), "commit:0123456789abcdef", None)
    assert got == ("unresolved", "0123456789abcdef")
    assert str(root / "private" / "in") in cwds, "the checked-out submodule is probed"
    assert str(root / "private" / "out") not in cwds, "a submodule with no .git is not"
    assert str(root) in cwds

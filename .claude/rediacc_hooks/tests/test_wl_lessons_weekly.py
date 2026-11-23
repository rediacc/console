"""The weekly lessons plan (agent/plans/PLAN-weekly-lessons.md W3-W7): the curator's plan skeleton, the `lessons-weekly` Stop check, the retired `hint-proposals` advisory, resolution on a box tick and the queue entry.

Pure cases drive `wl_hints` directly against a temp tree; the Stop-hook cases drive the real hook through `wlfix`. Every FIRE has a control that differs by one planted fact.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import subprocess

from rediacc_hooks.tests import wlfix

TODAY = datetime.date(2026, 11, 23)
ME = wlfix.ME


def _h():
    return wlfix.import_wl("wl_hints")


def _rows(n=6, source="judge"):
    return [
        {
            "id": "p%07d" % i,
            "by": "x",
            "at": "2026-11-0%dT00:00:00Z" % (i % 9 + 1),
            "text": "lesson %d" % i,
            "source": source,
        }
        for i in range(n)
    ]


def _plant(root: pathlib.Path, rows) -> None:
    ledgers = root / "agent" / "ledgers"
    ledgers.mkdir(parents=True, exist_ok=True)
    (ledgers / "hint-proposals.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _plan(root: pathlib.Path, date8: str, rows, ticked=False) -> pathlib.Path:
    h = _h()
    text = h.weekly_plan_text(rows, date8, "deadbeef")
    if ticked:
        text = text.replace("- [ ] ", "- [x] ")
    path = root / "agent" / "plans" / h.lessons_plan_name(date8)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---- W3: the plan the curator emits ----------------------------------------------------------------


def test_plan_skeleton_names_every_pending_id_once_and_boxes_each_cluster():
    h = _h()
    wlfix.import_wl("wl_planrec")
    rows = [
        *_rows(4, "judge"),
        {"id": "w0000001", "text": "w1", "source": "wake-timer"},
        {"id": "w0000002", "text": "w2", "source": "wake-timer"},
        {"id": "s0000001", "text": "s1", "source": "lonely"},
    ]
    text = h.weekly_plan_text(rows, "2026-11-23", "deadbeef")
    table = h.parse_cluster_table(text)
    ids = [i for v in table.values() for i in v]
    assert sorted(ids) == sorted(r["id"] for r in rows), table
    assert len(ids) == len(set(ids)), "an id sits in two rows"
    assert list(table) == ["L1", "SINGLES"], table
    assert sorted(table["SINGLES"]) == ["s0000001", "w0000001", "w0000002"], table
    planrec = wlfix.import_wl("wl_planrec")
    boxes = planrec.open_boxes(text)
    assert [h.box_label(b[2]) for b in boxes] == ["L1"], boxes
    assert "Status: approved" in text
    assert "Owner: deadbeef" in text


def test_plan_skeleton_control_no_cluster_gives_no_box():
    h = _h()
    text = h.weekly_plan_text(_rows(2), "20261123", "deadbeef")
    assert wlfix.import_wl("wl_planrec").open_boxes(text) == []
    assert list(h.parse_cluster_table(text)) == ["SINGLES"]


def test_source_spellings_fold_into_one_box():
    h = _h()
    rows = [
        dict(row, id="q%d" % i, source=src)
        for i, (row, src) in enumerate(
            zip(_rows(3), ["judge", "stop-judge", "stop-gate-judge"], strict=True)
        )
    ]
    table = h.parse_cluster_table(h.weekly_plan_text(rows, "20261123", "deadbeef"))
    assert list(table) == ["L1"], table
    assert len(table["L1"]) == 3, table


def test_curator_brief_describes_the_weekly_run():
    root = pathlib.Path(__file__).resolve().parents[3]
    brief = (root / ".claude" / "agents" / "lesson-curator.md").read_text(encoding="utf-8")
    assert "weekly <me8> <epoch> <YYYYMMDD>" in brief
    assert "weekly_plan_text" in brief
    assert "PLAN-lessons-" in brief
    assert "Cluster table" in brief


# ---- W4: the lessons-weekly state and block ---------------------------------------------------------


def test_state_pending_proposals_and_no_plan_dispatch(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    assert h.weekly_state(str(tmp_path), TODAY) == ("dispatch", "")
    # control: nothing pending, no plan, nothing owed
    _plant(tmp_path, [])
    assert h.weekly_state(str(tmp_path), TODAY) == ("none", "")


def test_state_a_plan_newer_than_seven_days_stands_down(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    _plan(tmp_path, "20261117", _rows())
    assert h.weekly_state(str(tmp_path), TODAY)[0] == "none"  # 6 days
    _plan(tmp_path, "20261116", _rows())  # control: an older one never outranks the newest
    assert h.weekly_state(str(tmp_path), TODAY)[0] == "none"


def test_state_an_eight_day_plan_with_open_boxes_blocks_for_work(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    _plan(tmp_path, "20261115", _rows())
    assert h.weekly_state(str(tmp_path), TODAY) == ("work", "agent/plans/PLAN-lessons-20261115.md")


def test_state_an_eight_day_plan_with_every_box_ticked_asks_for_a_new_one(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    _plan(tmp_path, "20261115", _rows(), ticked=True)
    assert h.weekly_state(str(tmp_path), TODAY)[0] == "dispatch"
    # control: with nothing pending the finished week owes nothing
    _plant(tmp_path, [])
    assert h.weekly_state(str(tmp_path), TODAY)[0] == "none"


def test_state_an_unreadable_plan_is_an_error_not_an_empty_plan(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    path = _plan(tmp_path, "20261115", _rows())
    path.write_bytes(b"\xff\xfe")
    path.chmod(0)
    try:
        if path.read_bytes() is not None:  # running as root: chmod does not bite
            return
    except OSError:
        pass
    try:
        h.weekly_state(str(tmp_path), TODAY)
    except OSError:
        return
    finally:
        path.chmod(0o644)
    raise AssertionError("an unreadable plan read as an empty one")


def test_block_text_names_the_next_command_and_a_babysit_phase_parks_it(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    wl = str(tmp_path / "wl")
    sid = "deadbeef-1111-2222-3333-444444444444"
    text = h.weekly_block(str(tmp_path), wl, sid, TODAY)
    assert "LESSONS WEEKLY" in text, text
    assert "weekly deadbeef 0 20261123" in text, text
    assert "--promote deadbeef PLAN-lessons-20261123.md" in text, text
    # a babysit or merge phase (the landing tree) parks it; the claim is left untouched
    assert h.weekly_block(str(tmp_path), str(tmp_path / "wl2"), sid, TODAY, parked=True) == ""
    assert not list(tmp_path.glob("wl2.schedred-claim-*"))


def test_block_work_text_names_the_oldest_open_box(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    _plan(tmp_path, "20261115", _rows())
    text = h.weekly_block(str(tmp_path), str(tmp_path / "wl"), "deadbeef-1", TODAY)
    assert "open box, `L1`" in text, text
    assert "--plan-tick deadbeef agent/plans/PLAN-lessons-20261115.md " in text, text
    assert "8 days old" in text, text


def test_a_second_session_sees_no_block_while_the_first_holds_the_claim(tmp_path):
    h = _h()
    _plant(tmp_path, _rows())
    wl = str(tmp_path / "wl")
    first = h.weekly_block(str(tmp_path), wl, "aaaaaaaa-1", TODAY)
    second = h.weekly_block(str(tmp_path), wl, "bbbbbbbb-1", TODAY)
    again = h.weekly_block(str(tmp_path), wl, "aaaaaaaa-1", TODAY)
    assert "LESSONS WEEKLY" in first
    assert second == ""
    assert "LESSONS WEEKLY" in again


def test_stop_hook_blocks_on_pending_proposals_without_a_plan(wl):
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    _plant(wl.proj, _rows())
    got = wl.run()
    assert got.decision == "block", got.out[:600]
    assert "LESSONS WEEKLY" in got.out, got.out[:600]
    assert "hint proposal(s) are waiting" in got.out, "the pending count rides inside the block"


def test_stop_hook_control_no_pending_proposals_is_silent(wl):
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    wl.check_quiet("LESSONS WEEKLY", "no proposals, no block")


def test_stop_hook_control_a_fresh_plan_stands_down(wl):
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    _plant(wl.proj, _rows())
    today = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    _plan(wl.proj, today, _rows())
    wl.check_quiet("LESSONS WEEKLY", "a plan from today covers the week")


# ---- W5: one check owns the subject --------------------------------------------------------------------


def test_the_hint_proposals_advisory_and_its_effort_row_are_gone():
    root = pathlib.Path(__file__).resolve().parents[3]
    effort = json.loads((root / ".claude" / "config" / "effort.json").read_text(encoding="utf-8"))
    keys = set(effort["checks"])
    assert "hint-proposals" not in keys
    assert effort["checks"]["lessons-weekly"] == {"block": "smart", "advise": "low"}
    checks = (root / ".claude" / "hooks" / "stop" / "wl_checks.py").read_text(encoding="utf-8")
    assert '"hint-proposals"' not in checks


def test_the_advisory_no_longer_rides_a_clean_stop(wl):
    """With a plan covering the week the check stands down, and the old advisory text does not reappear."""
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    _plant(wl.proj, _rows())
    today = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    _plan(wl.proj, today, _rows())
    wl.check_quiet("hint proposal(s) are waiting", "folded into lessons-weekly")


# ---- W6: ticking a box resolves its proposals -------------------------------------------------------------


def _git_commit(wl) -> str:
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: seed")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(wl.proj), capture_output=True, text=True, check=True
    ).stdout.strip()


def _seed_box_ledger(wl) -> None:
    """The committed second reading of the boxes that `--plan-tick --write` updates beside the plan."""
    ledger = wl.proj / ".ci" / "config" / "plan-boxes.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"plans": {}}), encoding="utf-8")


def _investigate(wl, rel, sig):
    """The investigation row `--plan-tick` demands before it ticks (verdict `present`, pointers that resolve in the fixture repo)."""
    got = wl.cli(
        "--plan-investigate",
        ME,
        rel,
        sig,
        "present",
        "fileline:base.txt:1",
        "plan:%s" % rel,
        "--",
        "the fixture tree already holds the box, read at base.txt line 1 of the seed commit",
        "--write",
    )
    assert got.rc == 0, (got.out, got.err)


def test_tick_resolution_lists_the_box_ids_and_a_resolving_commit(wl):
    wl.reg_repo()
    rows = [*_rows(4), {"id": "s0000001", "text": "s", "source": "lonely"}]
    _plant(wl.proj, rows)
    plan = _plan(wl.proj, "20261120", rows)
    sha = _git_commit(wl)
    h = _h()
    text = plan.read_text(encoding="utf-8")
    ids, pointer, problem = h.tick_resolution(
        str(wl.proj), "agent/plans/PLAN-lessons-20261120.md", text, "L1", "commit:%s ran it" % sha
    )
    assert ids == ["p0000000", "p0000001", "p0000002", "p0000003"], ids
    assert pointer == "commit:%s" % sha
    assert problem == ""
    # CONTROL: a plan that is not a weekly lessons plan resolves nothing
    other = h.tick_resolution(
        str(wl.proj), "agent/plans/PLAN-other.md", text, "L1", "commit:%s" % sha
    )
    assert other == ([], "", "")
    # CONTROL: evidence with no resolving commit resolves nothing and says why
    ids2, pointer2, problem2 = h.tick_resolution(
        str(wl.proj), "agent/plans/PLAN-lessons-20261120.md", text, "L1", "exit 0 on the suite"
    )
    assert ids2, ids2
    assert pointer2 == "", pointer2
    assert problem2, problem2


def test_plan_tick_cli_resolves_the_cluster_and_leaves_the_rest_pending(wl):
    wl.reg_repo()
    rows = [*_rows(4), {"id": "s0000001", "text": "s", "source": "lonely"}]
    _plant(wl.proj, rows)
    _plan(wl.proj, "20261120", rows)
    sha = _git_commit(wl)
    sig = re.search(
        r"^\s+([0-9a-f]{8})\s+L1 ",
        wl.cli("--plan-tick", ME).out,
        re.MULTILINE,
    )
    assert sig, wl.cli("--plan-tick", ME).out[:500]
    _seed_box_ledger(wl)
    _investigate(wl, "agent/plans/PLAN-lessons-20261120.md", sig.group(1))
    got = wl.cli(
        "--plan-tick",
        ME,
        "agent/plans/PLAN-lessons-20261120.md",
        sig.group(1),
        "commit:%s fixed by the judge guard" % sha,
        "--write",
    )
    assert got.rc == 0, (got.out, got.err)
    assert "resolved 4 hint proposal(s) -> commit:%s" % sha in got.out, got.out
    pending = {r["id"] for r in _h().pending_proposals(str(wl.proj))}
    assert pending == {"s0000001"}, pending
    ledger = wl.proj / "agent" / "ledgers" / "hint-resolutions.jsonl"
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 4


def test_plan_tick_cli_control_a_plain_plan_writes_no_resolution(wl):
    wl.reg_repo()
    plans = wl.proj / "agent" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "PLAN-plain.md").write_text(
        "# PLAN\nStatus: approved\nOwner: deadbeef\nDepends-On: no-dep -- x\nPriority: P2 -- s\n"
        "Concurrency: parallel\nOwns: docs/x/**\n\n## Boxes\n- [ ] O1 an open box sits here\n",
        encoding="utf-8",
    )
    sha = _git_commit(wl)
    sig = re.search(r"^\s+([0-9a-f]{8})\s+O1 ", wl.cli("--plan-tick", ME).out, re.MULTILINE)
    assert sig
    _seed_box_ledger(wl)
    _investigate(wl, "agent/plans/PLAN-plain.md", sig.group(1))
    got = wl.cli(
        "--plan-tick",
        ME,
        "agent/plans/PLAN-plain.md",
        sig.group(1),
        "commit:%s done" % sha,
        "--write",
    )
    assert got.rc == 0, (got.out, got.err)
    assert "hint proposal" not in got.out
    assert not (wl.proj / "agent" / "ledgers" / "hint-resolutions.jsonl").exists()


# ---- W7: the saved plan joins Promoted through the existing tooling ---------------------------------------


def test_the_curators_plan_is_promoted_and_the_queue_passes_its_record_check(wl):
    wl.reg_repo()
    rows = _rows(4)
    _plant(wl.proj, rows)
    _plan(wl.proj, "20261120", rows)
    queue = wl.proj / wlfix.import_wl("wl_planqueue").QUEUE_REL
    queue.parent.mkdir(parents=True, exist_ok=True)
    # One entry already Promoted: promote into a section with none mangles the heading line (reported in the lease report, wl_planqueue.with_promoted_entry).
    queue.write_text(
        "# Plan queue\n\n## Promoted\n\n1. agent/plans/PLAN-head.md -- operator: first entry\n\n## Generated\n\n",
        encoding="utf-8",
    )
    (wl.proj / "agent" / "plans" / "PLAN-head.md").write_text(
        "# PLAN\nStatus: approved\nOwner: deadbeef\nDepends-On: no-dep -- x\nPriority: P2 -- s\n"
        "Concurrency: parallel\nOwns: docs/x/**\n\n## Boxes\n- [ ] O1 an open box sits here\n",
        encoding="utf-8",
    )
    _git_commit(wl)
    got = wl.cli("--promote", ME, "PLAN-lessons-20261120.md", "weekly lessons 2026-11-20")
    assert got.rc == 0, (got.out, got.err)
    assert "promoted agent/plans/PLAN-lessons-20261120.md as Promoted entry 2" in got.out, got.out
    pq = wlfix.import_wl("wl_planqueue")
    assert pq.entries(queue.read_text(encoding="utf-8"))[0] == [
        "agent/plans/PLAN-head.md",
        "agent/plans/PLAN-lessons-20261120.md",
    ]
    assert pq.problems(str(wl.proj)) == [], pq.problems(str(wl.proj))
    # CONTROL: the same plan is refused a second time and nothing moves
    before = queue.read_text(encoding="utf-8")
    again = wl.cli("--promote", ME, "PLAN-lessons-20261120.md", "again")
    assert again.rc == 1
    assert "already Promoted" in again.err
    assert queue.read_text(encoding="utf-8") == before


def test_the_dispatch_text_orders_the_promote_in_the_same_commit(tmp_path):
    _plant(tmp_path, _rows())
    text = _h().weekly_block(str(tmp_path), str(tmp_path / "wl"), "deadbeef-1", TODAY)
    assert "commit both together" in text, text

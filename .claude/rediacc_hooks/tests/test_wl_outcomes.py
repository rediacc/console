"""The outcome ledger (agent/plans/PLAN-stop-hook-effort-tuning.md T1).

One case per outcome (work, paperwork, overruled, expired), the operator-override cases (an effort change and an accepted demotion answer), the miss flag, the dedupe rules, the advisory `note`, and one run through the real Stop hook. `observe` is driven directly against a fixture fold and a scratch project; `wl_effort.activate` is reset after every case.
"""

from __future__ import annotations

import json
import subprocess
import time
import types

import pytest

from rediacc_hooks.tests import wlfix

OUT = wlfix.import_wl("wl_outcomes")
E = wlfix.import_wl("wl_effort")
ME = wlfix.ME
SID = wlfix.SID


@pytest.fixture(autouse=True)
def _no_active_level():
    yield
    E.activate(None)


def fold(*recs):
    items = list(recs)
    return types.SimpleNamespace(items=items, by_id={r["id"]: r for r in items})


def item(rid, state=" ", upd="2000-01-01T00:00:00Z", owner=ME, lease_at=""):
    return {"id": rid, "state": state, "owner": owner, "upd": upd, "lease_at": lease_at}


class World:
    def __init__(self, tmp_path):
        self.root = tmp_path / "proj"
        (self.root / "agent" / "ledgers").mkdir(parents=True)
        self.worklist = tmp_path / "wl.md"
        self.doc: dict = {}

    def stop(self, violations=(), f=None, msg="", level="smart"):
        return OUT.observe(
            self.root, self.worklist, SID, self.doc, level, list(violations), f or fold(), msg
        )

    def rows(self):
        return OUT.read_rows(OUT.ledger_path(self.root))

    def outcomes(self):
        return [(r["key"], r["outcome"]) for r in self.rows() if r.get("kind") == "outcome"]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


OPEN = ("open-items", False, "1 open item: #abcd1234 do the thing")


def test_work_a_tick_of_the_named_item_within_the_window(world):
    world.stop([OPEN], fold(item("abcd1234")))
    time.sleep(1.1)
    later = OUT.now_stamp()
    world.stop([], fold(item("abcd1234", "x", later)))
    assert world.outcomes() == [("open-items", "work")]
    row = world.rows()[0]
    assert row["why"] == "tick #abcd1234"
    assert (row["verdict"], row["level"], row["session"]) == ("block", "smart", ME)
    assert row["id"].startswith("eo-")


def test_work_a_lease_counts_and_another_items_tick_does_not(world):
    world.stop([OPEN], fold(item("abcd1234"), item("ffff0000")))
    time.sleep(1.1)
    later = OUT.now_stamp()
    world.stop([], fold(item("abcd1234"), item("ffff0000", "x", later)))
    assert world.outcomes() == [], "a tick of an item the check did not name is not its work"
    world.stop([], fold(item("abcd1234", ">", lease_at=later), item("ffff0000", "x", later)))
    assert world.outcomes() == [("open-items", "work")]
    assert world.rows()[0]["why"] == "lease #abcd1234"


def test_work_a_commit_naming_the_subject(world):
    git = ["git", "-C", str(world.root)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "config", "user.email", "t@t"], check=True)
    subprocess.run([*git, "config", "user.name", "t"], check=True)
    world.stop([("plan-drift", False, "agent/plans/PLAN-x.md box 3 drifted")])
    time.sleep(1.1)
    (world.root / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run([*git, "add", "f.txt"], check=True)
    subprocess.run([*git, "commit", "-qm", "fix: PLAN-x.md box 3"], check=True)
    world.stop([])
    assert world.outcomes() == [("plan-drift", "work")]
    assert world.rows()[0]["why"].startswith("commit ")


def test_paperwork_only_a_status_reply_followed(world):
    world.stop([OPEN], fold(item("abcd1234")))
    for _ in range(3):
        world.stop([], fold(item("abcd1234")), msg="status\n\n## Remaining\n- #abcd1234")
    assert world.outcomes() == [("open-items", "paperwork")]


def test_paperwork_a_state_md_rewrite(world):
    world.stop([OPEN], fold(item("abcd1234")))
    time.sleep(1.1)
    state = world.root / "agent" / ME / "STATE.md"
    state.parent.mkdir(parents=True)
    state.write_text("# state\n", encoding="utf-8")
    for _ in range(3):
        world.stop([], fold(item("abcd1234")))
    assert world.outcomes() == [("open-items", "paperwork")]


def test_expired_nothing_followed_in_three_stops(world):
    world.stop([OPEN], fold(item("abcd1234")))
    world.stop([], fold(item("abcd1234")))
    world.stop([], fold(item("abcd1234")))
    assert world.outcomes() == [], "the window is three stops, not two"
    world.stop([], fold(item("abcd1234")))
    assert world.outcomes() == [("open-items", "expired")]


def test_overruled_the_claim_is_refuted_by_a_closed_item(world):
    world.stop([OPEN], fold(item("abcd1234", "x", "2000-01-01T00:00:00Z")))
    assert world.outcomes() == [("open-items", "overruled")]
    assert world.rows()[0]["why"] == "refuted: #abcd1234 already closed"


def test_operator_override_lowering_the_effort_level(world):
    world.stop([("no-remaining", False, "no Remaining section")], level="high")
    world.stop([], level="low")
    rows = world.rows()
    op = [r for r in rows if r.get("kind") == "operator"]
    assert op
    assert (op[0]["signal"], op[0]["strong"]) == ("effort-change", True)
    assert (op[0]["from"], op[0]["to"]) == ("high", "low")
    out = [r for r in rows if r.get("kind") == "outcome"]
    assert [(r["key"], r["outcome"], r["strong"]) for r in out] == [
        ("no-remaining", "overruled", True)
    ]


def test_operator_override_an_accepted_demotion_answer(world):
    world.stop([("plan-drift", False, "drift")])
    time.sleep(1.1)
    OUT.append_rows(
        OUT.proposals_path(world.root),
        [{"kind": "answer", "key": "plan-drift", "decision": "accept", "at": OUT.now_stamp()}],
    )
    world.stop([])
    assert world.outcomes() == [("plan-drift", "overruled")]
    assert any(r.get("signal") == "ask-answer" for r in world.rows())


def test_control_raising_the_level_overrules_nothing(world):
    world.stop([OPEN], fold(item("abcd1234")), level="low")
    world.stop([], fold(item("abcd1234")), level="high")
    assert world.outcomes() == []


def test_a_ci_red_after_an_emission_marks_it_a_miss(world):
    world.stop([("plan-drift", False, "drift")], level="low")
    world.stop([("ci-red", True, "CI is red")], level="low")
    world.stop([], level="low")
    world.stop([], level="low")
    rows = {r["key"]: r for r in world.rows() if r.get("kind") == "outcome"}
    assert rows["plan-drift"]["verdict"] == "off"
    assert rows["plan-drift"]["miss"] is True
    [red] = world.doc[OUT.STATE_KEY]["pending"]  # still inside its own window
    assert (red["key"], red["miss"]) == ("ci-red", False), "a red is not its own miss"


def test_one_emission_per_key_while_pending_and_per_text_after(world):
    for _ in range(4):
        world.stop([OPEN], fold(item("abcd1234")))
    assert world.outcomes() == [("open-items", "expired")]
    world.stop([OPEN], fold(item("abcd1234")))
    assert len(world.doc[OUT.STATE_KEY]["pending"]) == 0, (
        "the same text again is not a new emission"
    )
    world.stop([("open-items", False, "2 open items: #abcd1234 #beef0000")], fold(item("abcd1234")))
    assert len(world.doc[OUT.STATE_KEY]["pending"]) == 1


def test_note_records_advisories_only_inside_a_stop(world):
    OUT.note(world.doc, "agent-hint", "a hint", True)
    assert OUT.STATE_KEY not in world.doc, "no stop in progress: nothing recorded"
    E.activate("smart")
    OUT.note(world.doc, "agent-hint", "a hint", True)
    OUT.note(world.doc, "hint-proposals", "2 pending", False)
    OUT.note(world.doc, "effort-tune", "the tuner's own request", True)
    pending = {e["key"]: e["verdict"] for e in world.doc[OUT.STATE_KEY]["pending"]}
    assert pending == {"agent-hint": "advise", "hint-proposals": "off"}


def test_subjects_reads_ids_plans_paths_and_the_key_suffix():
    got = OUT.subjects(
        "agent-pushback:gate-author",
        "see #abcd1234 and #0123456789ab in agent/plans/PLAN-x.md, .claude/hooks/stop/wl_x.py",
    )
    assert got["items"] == ["0123456789ab", "abcd1234"]
    assert got["plans"] == ["PLAN-x.md"]
    assert ".claude/hooks/stop/wl_x.py" in got["paths"]
    assert got["tokens"] == ["gate-author"]
    assert OUT.subjects("giveup-claim:abcd1234", "")["items"] == ["abcd1234"]


def test_observe_never_raises(world):
    assert OUT.observe(world.root, world.worklist, SID, world.doc, "smart", [None], None, "") == []


# ---- through the real Stop hook ------------------------------------------------------------------


@pytest.fixture
def wl(tmp_path):
    """One hook sandbox per test (wlfix.Fixture)."""
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def test_the_stop_hook_writes_rows_to_the_project_ledger(wl):
    assert wl.cli("--add", ME, "(%s) do the thing" % ME).rc == 0
    wl.settings(effort="low")
    for _ in range(4):
        wl.say("still going")
        assert wl.run().decision == "block"
    path = wl.proj / "agent" / "ledgers" / "effort-outcomes.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    keys = {(r["key"], r["verdict"], r["level"]) for r in rows}
    assert ("open-items", "block", "low") in keys, rows
    assert all(r["outcome"] in OUT.OUTCOMES for r in rows if r.get("kind") == "outcome")


def test_read_rows_skips_a_non_utf8_byte_instead_of_raising(tmp_path):
    """One stray byte in a ledger must cost its own line, not the classification of every later stop (04fd0798.4)."""
    path = tmp_path / "rows.jsonl"
    path.write_bytes(b'{"id": "a"}\n{"id": "b\xff"}\nnot json\n{"id": "c"}\n')
    ids = [r["id"] for r in OUT.read_rows(path)]
    assert "a" in ids
    assert "c" in ids

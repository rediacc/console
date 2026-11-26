"""Silent-failure sweep, part A: a read, parse or import failure in a Stop-hook module is NAMED (exception type and message) in text the caller already emits, instead of reading as "no data".

Every case injects the failure by monkeypatching the reader to raise, and is paired with a control that the normal path is unchanged (nothing named, same verdict).
"""

from __future__ import annotations

import io
import json
import types

import pytest
import wl_admit
import wl_backlog
import wl_benchblock
import wl_checklist
import wl_civerdict
import wl_handover
import wl_hints
import wl_planenforce
import wl_renettests
import wl_retro
import wl_worktrees

BOOM = "boom-sentinel-7"


def _raise(*_a, **_k):
    raise RuntimeError(BOOM)


# ---- wl_admit.defer_created -------------------------------------------------------------------


def _fold(rows):
    return types.SimpleNamespace(items=rows)


def test_defer_created_names_an_unreadable_store():
    doc = {"pendingask": {"defersig": "abc"}}
    got = wl_admit.defer_created(doc, _fold([{"id": "x"}]), "sess1234")
    assert got is False
    assert "KeyError" in doc["pendingask"]["defersig_error"]


def test_defer_created_control_readable_store_names_nothing():
    doc = {"pendingask": {"defersig": "abc"}}
    row = {"id": "x", "state": "?", "owner": "sess1234"}
    wl_admit.defer_created(doc, _fold([row]), "sess1234")
    assert "defersig_error" not in doc["pendingask"]
    assert doc["pendingask"]["defersig"] != "abc"


# ---- wl_backlog.next_plan ---------------------------------------------------------------------


def _queue_tree(tmp_path):
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    (plans / "PLAN-q.md").write_text(
        "# PLAN: q\n\nStatus: approved\nOwner: cafe1234\nDepends-On: no-dep -- fixture\n\n"
        "## Tasks\n\n- [ ] T1 build the fixture part\n",
        encoding="utf-8",
    )
    (plans / "QUEUE.md").write_text(
        "# Plan queue\n\n## Promoted\n\n1. agent/plans/PLAN-q.md\n\n## Generated\n\n"
        "<!-- queue:generated:begin -->\n<!-- queue:generated:end -->\n",
        encoding="utf-8",
    )
    return tmp_path


def test_next_plan_names_an_open_box_count_failure(tmp_path, monkeypatch):
    root = _queue_tree(tmp_path)
    monkeypatch.setattr(wl_backlog.R, "open_boxes", _raise)
    cand, reason, stats = wl_backlog.next_plan(root)
    assert reason == "nominated"
    assert BOOM in cand["count_problem"]
    assert BOOM in wl_backlog.render(cand, reason, stats)


def test_next_plan_control_counts_the_box_and_names_nothing(tmp_path):
    root = _queue_tree(tmp_path)
    cand, reason, stats = wl_backlog.next_plan(root)
    assert cand["open"] == 1
    assert not cand["count_problem"]
    assert "could not be counted" not in wl_backlog.render(cand, reason, stats)


# ---- wl_benchblock.main -----------------------------------------------------------------------

PAYLOAD = json.dumps(
    {
        "tool_name": "Bash",
        "tool_input": {"command": "./rdc.sh --config eu-bench machine list"},
        "tool_response": {"stdout": "HTTP 403", "stderr": ""},
    }
)


def test_benchblock_names_an_internal_failure(monkeypatch):
    monkeypatch.setattr(wl_benchblock, "notes", _raise)
    out = io.StringIO()
    rc = wl_benchblock.main(stdin=io.StringIO(PAYLOAD), stdout=out, src=object())
    assert rc == 0
    assert BOOM in out.getvalue()


def test_benchblock_control_unrelated_call_stays_silent(monkeypatch):
    monkeypatch.setattr(wl_benchblock, "notes", _raise)
    unrelated = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    out = io.StringIO()
    assert wl_benchblock.main(stdin=io.StringIO(unrelated), stdout=out) == 0
    assert out.getvalue() == ""


# ---- wl_checklist._adopt_hint -----------------------------------------------------------------


def test_adopt_hint_names_an_unreadable_owner_age(monkeypatch):
    monkeypatch.setattr(wl_checklist.S, "owner_age_hours", _raise)
    text = wl_checklist._adopt_hint("deadbeef", "/nowhere", "agent/x.md")
    assert BOOM in text


def test_adopt_hint_control_young_owner_says_nothing(monkeypatch):
    monkeypatch.setattr(wl_checklist.S, "owner_age_hours", lambda *_a: 1.0)
    assert wl_checklist._adopt_hint("deadbeef", "/nowhere", "agent/x.md") == ""


def test_adopt_hint_control_old_owner_offers_adoption(monkeypatch):
    monkeypatch.setattr(wl_checklist.S, "owner_age_hours", lambda *_a: 99.0)
    assert "adopt it" in wl_checklist._adopt_hint("deadbeef", "/nowhere", "agent/x.md")


# ---- wl_civerdict -----------------------------------------------------------------------------


def test_civerdict_note_names_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(wl_civerdict, "read_cache", _raise)
    assert BOOM in wl_civerdict.note(tmp_path, tmp_path / "wl", "sess", branch="b")


def test_civerdict_note_control_no_cache_is_empty(tmp_path):
    assert wl_civerdict.note(tmp_path, tmp_path / "wl", "sess", branch="b") == ""


def test_civerdict_session_line_names_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(wl_civerdict, "read_cache", _raise)
    assert BOOM in wl_civerdict.session_start_line(tmp_path / "wl", "b")


def test_civerdict_session_line_control_no_cache_is_empty(tmp_path):
    assert wl_civerdict.session_start_line(tmp_path / "wl", "b") == ""


# ---- wl_handover.lease_landed -----------------------------------------------------------------


def _land_record():
    return {
        "id": "h1",
        "at": "2026-11-23T00:00:00Z",
        "kind": "k",
        "check": "c",
        "answer": wl_handover.LEASE_PREFIX + "lease-1",
    }


def _unreadable_lease_findings(tmp_path, m):
    """The land findings with `read_world` raising, on a private UNREADABLE map (cbafdaaf.2: the module-level one outlived the test)."""
    m.setattr(wl_handover, "UNREADABLE", {})
    m.setattr(wl_worktrees, "read_world", _raise)
    return wl_handover.stop_findings(
        {"h1": _land_record()},
        wl_handover.ROLE_LANDING,
        landed=lambda lid: wl_handover.lease_landed(tmp_path, lid),
    )


def test_handover_names_an_unreadable_lease(tmp_path, monkeypatch):
    found = _unreadable_lease_findings(tmp_path, monkeypatch)
    assert len(found) == 1
    assert found[0][1] is True
    assert BOOM in found[0][2]


def test_handover_an_unreadable_lease_leaves_no_reason_behind(tmp_path, monkeypatch):
    """cbafdaaf.2: once the test's seams are undone, a later None state for the same lease is not handed a stale reason."""
    with monkeypatch.context() as m:
        assert BOOM in _unreadable_lease_findings(tmp_path, m)[0][2]
    assert "lease-1" not in wl_handover.UNREADABLE
    found = wl_handover.stop_findings(
        {"h1": _land_record()}, wl_handover.ROLE_LANDING, landed=lambda _lid: None
    )
    assert "could not be read" not in found[0][2]


def test_handover_control_a_landed_lease_is_not_a_finding():
    found = wl_handover.stop_findings(
        {"h1": _land_record()}, wl_handover.ROLE_LANDING, landed=lambda _lid: True
    )
    assert found == []


def test_handover_control_a_plain_unlanded_lease_names_no_failure():
    found = wl_handover.stop_findings(
        {"h1": _land_record()}, wl_handover.ROLE_LANDING, landed=lambda _lid: False
    )
    assert found[0][1] is True
    assert "could not be read" not in found[0][2]


# ---- wl_hints.pending_note --------------------------------------------------------------------


def test_pending_note_names_an_unreadable_epoch(monkeypatch):
    monkeypatch.setattr(wl_retro, "ctx", _raise)
    assert BOOM in wl_hints.pending_note("sess-1234abcd", [])


def test_pending_note_control_readable_epoch_names_nothing(monkeypatch):
    fake = types.SimpleNamespace(load_state=lambda _sid: {"epoch": 3})
    monkeypatch.setattr(wl_retro, "ctx", lambda: fake)
    note = wl_hints.pending_note("sess-1234abcd", [])
    assert "epoch could not be read" not in note


# ---- wl_renettests.advisory -------------------------------------------------------------------


def test_renettests_advisory_names_a_probe_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(wl_renettests, "pending", _raise)
    assert BOOM in wl_renettests.advisory(tmp_path)


def test_renettests_advisory_control_nothing_pending_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(wl_renettests, "pending", lambda *_a, **_k: None)
    assert wl_renettests.advisory(tmp_path) is None


# ---- wl_planenforce.evaluate ------------------------------------------------------------------

PLAN = "agent/plans/PLAN-x.md"
PLAN_TEXT = "# PLAN: x\n\nStatus: approved\n\n## Tasks\n\n- [ ] T1 build the fixture part\n"


def _read(_root, _rel):
    return PLAN_TEXT


def test_planenforce_names_an_unparseable_plan(monkeypatch):
    monkeypatch.setattr(wl_planenforce.R, "open_boxes", _raise)
    state, text, detail = wl_planenforce.evaluate("/nowhere", (PLAN,), "sess1234", read_text=_read)
    assert state == wl_planenforce.ADVISORY
    assert BOOM in text
    assert PLAN in text
    assert BOOM in detail["reason"]


def test_planenforce_first_box_collects_the_failure(monkeypatch):
    monkeypatch.setattr(wl_planenforce.R, "open_boxes", _raise)
    problems: list[str] = []
    assert wl_planenforce.first_box("/nowhere", PLAN, reader=_read, problems=problems) is None
    assert BOOM in problems[0]


def test_planenforce_control_a_readable_plan_still_blocks():
    state, text, detail = wl_planenforce.evaluate("/nowhere", (PLAN,), "sess1234", read_text=_read)
    assert state == wl_planenforce.BLOCK
    assert "could not be parsed" not in text
    assert detail["rows"] == [(PLAN, 1)]


@pytest.mark.parametrize("scope", [(), None])
def test_planenforce_control_empty_scope_is_silent(scope):
    assert wl_planenforce.evaluate("/nowhere", scope, "sess1234", read_text=_read)[0] == "silent"

"""Silent-failure sweep, part B: wl_ci, wl_lessons, wl_liveness and wl_roster name a failed read (exception type and message) where it used to read as "no data".

Each injected failure (a monkeypatched reader that raises) is paired with a control that the normal path is unchanged.
"""

from __future__ import annotations

import builtins
import sys
import time
import types
from typing import Any

import pytest
import wl_armed
import wl_ci
import wl_lessons
import wl_liveness
import wl_longred
import wl_reggate
import wl_report
import wl_roster

from rediacc_hooks.tests import test_wl_roster as roster_tests

BOOM = "boom-sentinel-9"


def _raise(*_a, **_k):
    raise RuntimeError(BOOM)


# ---- wl_ci: the diagnoser that does not load ---------------------------------------------------

GATE = {"run": 7}
INFO = {"owner": "o", "name": "n"}


def test_cancel_cause_names_a_diagnoser_that_does_not_load(monkeypatch):
    monkeypatch.setattr(wl_ci.importlib.util, "spec_from_file_location", _raise)
    cause = wl_ci.ci_cancel_cause("/nowhere", INFO, GATE)
    assert cause["kind"] == "unreadable"
    assert BOOM in cause["detail"]
    assert BOOM in wl_ci.ci_cancel_note({"info": {}, "cause": cause})


def test_cancel_cause_names_a_cause_read_that_raises(monkeypatch):
    fake = types.SimpleNamespace(
        GhFetcher=lambda *_a, **_k: object(),
        run_info=lambda *_a, **_k: ({"run_attempt": 1}, ""),
        run_jobs=lambda *_a, **_k: ([], ""),
        cancel_cause=_raise,
    )
    monkeypatch.setattr(wl_ci, "_load_diagnose", lambda: fake)
    cause = wl_ci.ci_cancel_cause("/nowhere", INFO, GATE)
    assert cause["kind"] == "unreadable"
    assert BOOM in cause["detail"]


def test_cancel_cause_control_no_run_is_the_plain_unknown(monkeypatch):
    monkeypatch.setattr(wl_ci, "_load_diagnose", object)
    cause = wl_ci.ci_cancel_cause("/nowhere", INFO, {})
    assert cause["kind"] == "unknown"
    assert wl_ci.ci_cancel_note({"info": {}, "cause": cause}) == ""


def test_carry_split_names_a_diagnoser_that_does_not_load(monkeypatch):
    monkeypatch.setattr(wl_ci.importlib.util, "spec_from_file_location", _raise)
    real, carried = wl_ci.ci_carry_split("/nowhere", INFO, "tip", [{"name": "x"}], {})
    assert carried == []
    assert BOOM in real[0]["carry"]["why"]


def test_sanctioned_match_collects_a_registry_failure(monkeypatch):
    monkeypatch.setattr(wl_ci.importlib.util, "spec_from_file_location", _raise)
    problems: list[str] = []
    assert wl_ci._sanctioned_match("gh run watch 1", problems) is False
    assert BOOM in problems[0]


def test_sanctioned_match_control_a_loading_registry_names_nothing():
    problems: list[str] = []
    wl_ci._sanctioned_match("echo hello", problems)
    assert problems == []


# ---- wl_ci.ci_longred --------------------------------------------------------------------------


def test_longred_names_a_ledger_that_cannot_be_read(monkeypatch):
    monkeypatch.setattr(wl_longred, "read_rows", _raise)
    info: dict[str, Any] = {"pr": 5, "contexts": []}
    assert wl_ci.ci_longred("/nowhere", info, "tip", []) is None
    assert BOOM in info["longred"]


def test_longred_control_no_pr_names_nothing():
    info: dict[str, Any] = {"contexts": []}
    assert wl_ci.ci_longred("/nowhere", info, "tip", []) is None
    assert "longred" not in info


# ---- wl_lessons.enforcer_state -----------------------------------------------------------------


class _Ctx:
    memory_dir = None

    def registry(self):
        raise RuntimeError(BOOM)


def test_enforcer_state_names_a_guard_test_probe_that_fails(monkeypatch):
    monkeypatch.setattr(wl_lessons, "pointer_problem", lambda *_a, **_k: "")
    live, tested, why = wl_lessons.enforcer_state("/nowhere", "guard:block_x", _Ctx())
    assert (live, tested) == (True, False)
    assert BOOM in why


def test_enforcer_state_names_a_gate_reachability_probe_that_fails(monkeypatch):
    monkeypatch.setattr(wl_lessons, "pointer_problem", lambda *_a, **_k: "")
    monkeypatch.setattr(wl_lessons.PR, "_package_scripts", lambda _root: {})
    monkeypatch.setattr(wl_reggate, "gate_reachable", _raise)
    live, tested, why = wl_lessons.enforcer_state("/nowhere", "gate:check-x", _Ctx())
    assert (live, tested) == (True, False)
    assert BOOM in why


def test_enforcer_state_control_an_unreachable_gate_is_plainly_so(monkeypatch):
    monkeypatch.setattr(wl_lessons, "pointer_problem", lambda *_a, **_k: "")
    monkeypatch.setattr(wl_lessons.PR, "_package_scripts", lambda _root: {})
    monkeypatch.setattr(wl_reggate, "gate_reachable", lambda *_a, **_k: False)
    _live, tested, why = wl_lessons.enforcer_state("/nowhere", "gate:check-x", _Ctx())
    assert tested is False
    assert why == "gate check-x is not reachable from npm run ci"


# ---- wl_liveness.live_worker_ids ---------------------------------------------------------------


def test_live_worker_ids_collects_a_shell_waiter_failure(monkeypatch):
    monkeypatch.setattr(wl_roster, "shell_waiters", _raise)
    event = {"background_tasks": [{"id": "b1", "status": "running"}]}
    problems: list[str] = []
    ids = wl_liveness.live_worker_ids(event, [{"id": "b0"}], "/nowhere", "s", problems=problems)
    assert ids == {"b0"}
    assert BOOM in problems[0]


def test_live_worker_ids_control_a_clean_read_names_nothing(monkeypatch):
    monkeypatch.setattr(wl_roster, "shell_waiters", lambda *_a: ["w1"])
    monkeypatch.setattr(wl_roster, "load_metas", lambda *_a: {})
    monkeypatch.setattr(wl_roster, "session_subagents_dir", lambda *_a: None)
    problems: list[str] = []
    ids = wl_liveness.live_worker_ids({}, [{"id": "b0"}], "/nowhere", "s", problems=problems)
    assert ids == {"b0", "w1"}
    assert problems == []


# ---- wl_roster ---------------------------------------------------------------------------------


def test_subagent_stop_at_collects_an_index_failure(monkeypatch):
    monkeypatch.setattr(wl_report, "read_index", _raise)
    problems: list[str] = []
    assert wl_roster.subagent_stop_at("/nowhere", "aid", problems=problems) is None
    assert BOOM in problems[0]


def test_completed_since_collects_a_transcript_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_report, "delivered_ids", _raise)
    problems: list[str] = []
    got = wl_roster._completed_since(tmp_path / "subagents", time.time(), problems=problems)
    assert got == {}
    assert BOOM in problems[0]


def test_completed_since_control_no_event_is_empty_and_names_nothing(tmp_path):
    problems: list[str] = []
    assert wl_roster._completed_since(tmp_path, None, problems=problems) == {}
    assert problems == []


# ---- wl_roster.roster end to end: the status source label names an unreadable SubagentStop store


def test_roster_status_source_names_an_unreadable_subagent_stop_store(wl):
    roster_tests.mk_sub(wl, roster_tests.W1, "general-purpose", 21, last="text")
    roster_tests.plant_lease(wl, "st1", roster_tests.W1, lease_age_min=21)
    broken = roster_tests.private_stop(
        wl,
        "wl_report.py",
        "    p = index_path(store)\n    out = []\n    try:\n        lines = (\n            _bounded_lines(",
        '    raise RuntimeError("boom-sentinel-9")\n    p = index_path(store)\n    out = []\n    try:\n        lines = (\n            _bounded_lines(',
    )
    v = roster_tests.verdict(wl, stop_dir=broken)
    assert "SubagentStop evidence unreadable" in v["rows"][roster_tests.W1]["status_src"]
    assert BOOM in v["rows"][roster_tests.W1]["status_src"]


def test_roster_status_source_control_a_readable_store_names_nothing(wl):
    roster_tests.mk_sub(wl, roster_tests.W1, "general-purpose", 21, last="text")
    roster_tests.plant_lease(wl, "st1", roster_tests.W1, lease_age_min=21)
    v = roster_tests.verdict(wl)
    assert "unreadable" not in v["rows"][roster_tests.W1]["status_src"]


def test_live_worker_ids_without_a_problems_list_says_so_on_stderr(monkeypatch, capsys):
    """Review 91ecf84b.1: the Stop hook's own call passes no `problems`; the failure must still be named, on stderr, not dropped."""
    monkeypatch.setattr(wl_roster, "shell_waiters", _raise)
    event = {"background_tasks": [{"id": "b1", "status": "running"}]}
    assert wl_liveness.live_worker_ids(event, [{"id": "b0"}], "/nowhere", "s") == {"b0"}
    err = capsys.readouterr().err
    assert "shell waiters" in err, err
    assert BOOM in err, err


def test_live_worker_ids_control_a_clean_read_without_problems_prints_nothing(monkeypatch, capsys):
    monkeypatch.setattr(wl_roster, "shell_waiters", lambda *_a: ["w1"])
    monkeypatch.setattr(wl_roster, "load_metas", lambda *_a: {})
    monkeypatch.setattr(wl_roster, "session_subagents_dir", lambda *_a: None)
    assert wl_liveness.live_worker_ids({}, [], "/nowhere", "s") == {"w1"}
    assert capsys.readouterr().err == ""


# ---- wl_liveness._arm_covers and the shell-work read -------------------------------------------

ARM_REC = {"arm": {"aid": "0123abcd"}}


def test_arm_covers_an_error_inside_covers_propagates(monkeypatch):
    """Review 775034ca.3: an exception from `covers()` is a defect to surface, not a reason to read the arm as not covering."""
    monkeypatch.setattr(wl_armed, "covers", _raise)
    with pytest.raises(RuntimeError, match=BOOM):
        wl_liveness._arm_covers(ARM_REC)


def test_arm_covers_control_a_covering_arm_answers_true(monkeypatch):
    monkeypatch.setattr(wl_armed, "covers", lambda *_a: True)
    assert wl_liveness._arm_covers(ARM_REC) is True
    assert wl_liveness._arm_covers({"arm": {}}) is False


def test_arm_covers_a_missing_wl_armed_covers_nothing_but_any_other_failure_propagates(
    monkeypatch,
):
    """Review 775034ca.4: the docstring's "cannot be imported" is exactly a wl_armed that is not installed; a SyntaxError in it is raised."""
    monkeypatch.setitem(sys.modules, "wl_armed", None)
    assert wl_liveness._arm_covers(ARM_REC) is False
    monkeypatch.delitem(sys.modules, "wl_armed")
    real = builtins.__import__

    def broken(name, *a, **k):
        if name == "wl_armed":
            raise SyntaxError("planted syntax error")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", broken)
    with pytest.raises(SyntaxError):
        wl_liveness._arm_covers(ARM_REC)


def _ladder_fold(wid):
    stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + 3600))
    rec = {
        "id": "it1",
        "state": ">",
        "owner": None,
        "line": "- [>] quiet item until:%s worker:%s" % (stamp, wid),
        "worker": wid,
        "worker_verified": True,
        "upd": "2020-01-01T00:00:00Z",
    }
    return types.SimpleNamespace(items=[rec])


def test_ladder_a_failed_shell_work_read_is_said_and_no_shell_counts_as_working(
    monkeypatch, capsys
):
    """Reviews 1a88774b.1 and b64fda50.1: when the shell-work probe raises, the age ladder runs as if no shell does real work AND stderr names the failure; the control (the probe names the shell as working) keeps it off the resolve rung."""
    monkeypatch.setattr(wl_roster, "known_subagent_ids", lambda *_a: set())
    monkeypatch.setattr(wl_liveness.C, "task_statuses", lambda *_a, **_k: {})
    event = {"background_tasks": [{"id": "sh1", "status": "running"}], "cwd": "/nowhere"}
    fold = _ladder_fold("sh1")
    got = wl_liveness.ladder(fold, "sess", event, {}, shell_work=_raise)
    err = capsys.readouterr().err
    assert "shell-work read failed" in err, err
    assert BOOM in err, err
    resolves = got[2]
    assert resolves, got
    got = wl_liveness.ladder(fold, "sess", event, {}, shell_work=set)
    assert capsys.readouterr().err == ""
    assert not got[2], got

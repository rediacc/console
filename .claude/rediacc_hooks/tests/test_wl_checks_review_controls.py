"""Controls for per-commit review findings on `wl_checks.py`: each test drives the call site a finding named as untested, with a silent control beside it.

The segments of `run_stop` take their locals as a dict (`ns`), so a test hands one a minimal dict and replaces its readers with recorders; the stop's own output is read for the sites a bare fixture world reaches.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import textwrap
import types

import pytest
import wl_bgsweep
import wl_checks
import wl_hints
import wl_liveness
import wl_prscope
import wl_roster
import wl_schedred
import wl_stack
import wl_storestatus
import wl_writersnow

from rediacc_hooks.tests import wlfix

SOURCE = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_failures():
    wl_checks.READ_FAILURES.clear()
    yield
    wl_checks.READ_FAILURES.clear()


@pytest.fixture
def queued(monkeypatch):
    """Record every `outq_add` and `outq_drop` key instead of touching a state file."""
    calls = types.SimpleNamespace(added=[], dropped=[])

    def add(_worklist, _sid, _doc, key, text, prio, **kw):
        calls.added.append((key, text, prio, kw))
        return True

    monkeypatch.setattr(wl_checks, "outq_add", add)
    monkeypatch.setattr(wl_checks, "outq_drop", lambda _doc, key: calls.dropped.append(key))
    return calls


def raising(*_a, **_k):
    raise RuntimeError("injected")


# ---- efa07054.1: the scheduled-freshness failure branch -------------------------


def sched_ns(tmp_path):
    return {
        "me8": "deadbeef",
        "root": tmp_path,
        "session_id": "deadbeef0000",
        "state_doc": {},
        "worklist": tmp_path / "wl",
    }


def test_a_failed_freshness_read_queues_the_hook_bug_advisory(monkeypatch, queued, tmp_path):
    monkeypatch.setattr(wl_schedred, "refresh_freshness", raising)
    wl_checks._stop_sched_fresh(sched_ns(tmp_path))
    [(key, text, prio, kw)] = queued.added
    assert key == "scheduled-stale-bug"
    assert "THIS IS A HOOK BUG" in text
    assert "RuntimeError: injected" in text
    assert (prio, kw["refresh_min"]) == (1, 60)


def test_a_failed_advisory_render_is_the_same_hook_bug(monkeypatch, queued, tmp_path):
    monkeypatch.setattr(wl_schedred, "refresh_freshness", lambda *_a, **_k: {})
    monkeypatch.setattr(wl_schedred, "freshness_advisory", raising)
    wl_checks._stop_sched_fresh(sched_ns(tmp_path))
    assert [c[0] for c in queued.added] == ["scheduled-stale-bug"]


def test_a_readable_freshness_queues_no_bug_advisory(monkeypatch, queued, tmp_path):
    """CONTROL: an empty advisory queues nothing; a stale workflow queues `scheduled-stale`, never the bug key."""
    monkeypatch.setattr(wl_schedred, "refresh_freshness", lambda *_a, **_k: {})
    monkeypatch.setattr(wl_schedred, "freshness_advisory", lambda *_a, **_k: "")
    wl_checks._stop_sched_fresh(sched_ns(tmp_path))
    assert queued.added == []
    monkeypatch.setattr(wl_schedred, "freshness_advisory", lambda *_a, **_k: "STALE WORKFLOW")
    wl_checks._stop_sched_fresh(sched_ns(tmp_path))
    assert [c[0] for c in queued.added] == ["scheduled-stale"]


# ---- d1a17fcf.1: the writers-now-due call site passes the project root ----------


def writers_now_ns(tmp_path):
    return {
        "_ss_rows": [],
        "me8": "deadbeef",
        "vadd": lambda *_a, **_k: None,
        "root": tmp_path,
        "worklist": tmp_path / "wl",
        "session_id": "deadbeef0000",
        "_loop": types.SimpleNamespace(role=""),
        "event": {},
        "live_bg": [],
        "fold": types.SimpleNamespace(items=[]),
        "_live_worker_ids": set(),
    }


def test_the_writers_now_check_reads_the_stop_segments_root(monkeypatch, tmp_path):
    seen = {}

    def due(*_a, **kw):
        seen.update(kw)
        return False, None

    monkeypatch.setattr(wl_storestatus, "blocking", lambda _rows: False)
    monkeypatch.setattr(wl_hints, "weekly_block", lambda *_a, **_k: "")
    monkeypatch.setattr(wl_writersnow, "read_rounds", lambda _root: [])
    monkeypatch.setattr(wl_writersnow, "promoted_open", lambda _root: 0)
    monkeypatch.setattr(wl_writersnow, "stand_down", lambda _loop: False)
    monkeypatch.setattr(wl_writersnow, "due", due)
    wl_checks._stop_store_freshness(writers_now_ns(tmp_path))
    assert seen["root"] == tmp_path


def test_a_failing_writers_now_read_is_named_and_does_not_fire(monkeypatch, tmp_path):
    """CONTROL: the failure path keeps its default (no fire) and names the site."""
    fired = []
    ns = writers_now_ns(tmp_path)
    ns["vadd"] = lambda key, *_a: fired.append(key)
    monkeypatch.setattr(wl_storestatus, "blocking", lambda _rows: False)
    monkeypatch.setattr(wl_hints, "weekly_block", lambda *_a, **_k: "")
    monkeypatch.setattr(wl_writersnow, "read_rounds", raising)
    wl_checks._stop_store_freshness(ns)
    assert fired == []
    assert "writers-now-due" in wl_checks.READ_FAILURES


# ---- ac89eb8d.1: the ladder call site passes the effort level's armed_blocks ----


def ladder_ns():
    return {
        "event": {},
        "fold": types.SimpleNamespace(items=[]),
        "me8": "deadbeef",
        "session_id": "deadbeef0000",
        "state_doc": {},
        "worklist": None,
    }


@pytest.mark.parametrize("flag", [True, False])
def test_the_ladder_reads_armed_blocks_now(monkeypatch, flag):
    seen = {}

    def ladder(*_a, **kw):
        seen.update(kw)
        return [], [], [], [], [], False

    monkeypatch.setattr(wl_liveness, "worker_facts", lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(wl_liveness, "ladder", ladder)
    monkeypatch.setattr(wl_checks, "armed_blocks_now", lambda: flag)
    wl_checks._stop_ladder_bookkeeping(ladder_ns())
    assert seen == {"armed_blocks": flag}


# ---- 1cd88702.5: an unread background sweep is named ----------------------------

BGSWEEP_WRAPPER = """
import os
import runpy
import sys

STOP = {stop!r}
sys.path.insert(0, STOP)
import wl_bgsweep

unread = os.environ["BG_UNREAD"]
wl_bgsweep.findings = lambda *a, **k: wl_bgsweep.Findings([], unread)
sys.argv = [STOP + "/worklist.py"]
runpy.run_path(STOP + "/worklist.py", run_name="__main__")
"""


@pytest.fixture
def bg_stop(tmp_path):
    fix = wlfix.Fixture(tmp_path / "world")
    fix.setup()
    wrapper = tmp_path / "wrap_bg.py"
    wrapper.write_text(BGSWEEP_WRAPPER.format(stop=str(wlfix.STOP_DIR)), encoding="utf-8")

    def run(unread: str) -> str:
        fix.hook = wrapper
        try:
            got = fix.run(extra_env={"BG_UNREAD": unread})
        finally:
            fix.hook = wlfix.HOOK
        assert got.rc == 0, got.err[-400:]
        assert got.decision != "block", got.out
        return str(json.loads(got.out).get("systemMessage") or "") if got.out.strip() else ""

    return run


def test_an_unread_sweep_result_is_named(bg_stop):
    msg = bg_stop("process table gone")
    assert "  bg-sweep: RuntimeError: process table gone" in msg, msg


def test_a_fully_read_sweep_names_nothing(bg_stop):
    """CONTROL: `unread` empty is a clean sweep, so no advisory names the site."""
    assert "bg-sweep" not in bg_stop("")


def test_the_findings_type_carries_unread():
    assert wl_bgsweep.Findings([], "x").unread == "x"
    assert wl_bgsweep.Findings([]).unread == ""


# ---- 2015f52a.3 and 2a6c600d.3: an unreadable release is named, never read as released


def stack_ns(released, tmp_path):
    return {
        "_loop": types.SimpleNamespace(landing_released=released),
        "event": {},
        "live_bg": [],
        "own": str(tmp_path),
        "root": tmp_path,
        "session_id": "deadbeef0000",
        "state_doc": {},
        "vadd": lambda *_a, **_k: None,
        "worklist": tmp_path / "wl",
    }


@pytest.fixture
def stack_world(monkeypatch):
    seen = types.SimpleNamespace(released=[])

    def verdict(_own, released, **_k):
        seen.released.append(released)
        return "", ""

    monkeypatch.setattr(wl_stack, "main_checkout_tasks", lambda *_a, **_k: [])
    monkeypatch.setattr(wl_stack, "stack_verdict", verdict)
    monkeypatch.setattr(wl_stack, "stack_report", lambda *_a, **_k: "")
    monkeypatch.setattr(wl_roster, "session_subagents_dir", lambda *_a, **_k: "none")
    monkeypatch.setattr(wl_roster, "load_metas", lambda *_a, **_k: {})
    return seen


def test_an_unreadable_release_queues_the_advisory_and_reads_as_not_released(
    queued, stack_world, tmp_path
):
    wl_checks._stop_landing_stack(stack_ns(wl_prscope.UNREADABLE_RELEASE, tmp_path))
    [(key, text, prio, kw)] = queued.added
    assert key == "landing-release-unreadable"
    assert "LANDING RELEASE UNREADABLE" in text
    assert (prio, kw["refresh_min"]) == (1, 0)
    assert stack_world.released == [False]
    assert "landing-release-unreadable" not in queued.dropped


@pytest.mark.parametrize(("value", "released"), [(0, False), (7, True)])
def test_a_readable_release_queues_no_advisory_and_drops_a_stale_one(
    queued, stack_world, tmp_path, value, released
):
    """CONTROL: 0 (pending) and a PR number (released) both retract the advisory and say nothing."""
    wl_checks._stop_landing_stack(stack_ns(value, tmp_path))
    assert queued.added == []
    assert "landing-release-unreadable" in queued.dropped
    assert stack_world.released == [released]


def dev_state(released):
    return wl_prscope.LoopState(
        kind=wl_prscope.OFF_LOOP, role=wl_prscope.DEVELOPMENT, landing_released=released
    )


def test_loop_next_text_does_not_promote_on_an_unreadable_release(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_checks.wl_stack, "notify_line", raising)
    got = wl_checks.loop_next_text(dev_state(wl_prscope.UNREADABLE_RELEASE), tmp_path, {}, False)
    assert got == ("", False)


def test_loop_next_text_promotes_on_a_released_pr(monkeypatch, tmp_path):
    """CONTROL: a positive release number takes the promote arm."""
    monkeypatch.setattr(wl_checks.wl_stack, "notify_line", lambda *_a, **_k: "CD DONE")
    monkeypatch.setattr(wl_checks, "branch_writer_boxes", lambda _root: [])
    assert wl_checks.loop_next_text(dev_state(7), tmp_path, {}, False) == ("CD DONE", True)


# ---- 12e42ca1.1: an unreadable branch log advises and never blocks --------------


def promote_world(monkeypatch, pending):
    monkeypatch.setattr(wl_checks.wl_stack, "notify_line", lambda *_a, **_k: "CD DONE")
    monkeypatch.setattr(wl_checks, "branch_writer_boxes", lambda _root: pending)


def test_an_unreadable_branch_log_advises_and_is_not_read_as_no_open_box(monkeypatch, tmp_path):
    promote_world(monkeypatch, None)
    text, blocking = wl_checks.loop_next_text(dev_state(7), tmp_path, {}, False)
    assert text == "CD DONE" + wl_checks.DEV_PROMOTE_UNREADABLE
    assert blocking is False


def test_open_boxes_wait_and_no_open_box_blocks(monkeypatch, tmp_path):
    """CONTROL: a list of open boxes advises with them named; an empty list is the one blocking arm."""
    promote_world(monkeypatch, ["PLAN-x.md:B1"])
    text, blocking = wl_checks.loop_next_text(dev_state(7), tmp_path, {}, False)
    assert "PLAN-x.md:B1" in text
    assert blocking is False
    promote_world(monkeypatch, [])
    assert wl_checks.loop_next_text(dev_state(7), tmp_path, {}, False) == ("CD DONE", True)


# ---- cc68eafa.1: a failure recorded after the first naming is named in the same stop


def test_the_advisory_is_refreshed_with_a_later_failure(tmp_path):
    state_doc: dict = {}
    wl = tmp_path / "wl"
    wl_checks.note_read_failure("early-site", RuntimeError("one"))
    wl_checks.name_read_failures(wl, "deadbeef0000", state_doc)
    wl_checks.note_read_failure("report-index", RuntimeError("two"))
    wl_checks.name_read_failures(wl, "deadbeef0000", state_doc)
    items = [e for e in state_doc["outq"]["items"] if e["key"] == "check-read-failed"]
    assert len(items) == 1
    assert "early-site" in items[0]["text"]
    assert "report-index: RuntimeError: two" in items[0]["text"]
    assert items[0]["text"].startswith("2 ")


def test_a_second_naming_with_no_new_failure_changes_nothing(tmp_path):
    """CONTROL: the same record queues one unchanged entry."""
    state_doc: dict = {}
    wl = tmp_path / "wl"
    wl_checks.note_read_failure("early-site", RuntimeError("one"))
    wl_checks.name_read_failures(wl, "deadbeef0000", state_doc)
    before = json.dumps(state_doc["outq"]["items"], sort_keys=True)
    wl_checks.name_read_failures(wl, "deadbeef0000", state_doc)
    assert json.dumps(state_doc["outq"]["items"], sort_keys=True) == before


def test_the_judge_segment_names_failures_after_the_judge_readers_ran():
    """The judge's readers (`report-index`, `judge-receipt-run`) run inside `_stop_judge`; the naming call sits after them and before the judge's verdict is acted on."""
    body = inspect.getsource(wl_checks._stop_judge)
    facts = body.index("facts=_judge_facts(")
    naming = body.index("name_read_failures(", facts)
    assert naming > facts
    assert body.index("if err is not None:", facts) > naming


def _judge_naming_siblings(source: str) -> list[str]:
    """Each statement list in `source` that holds an `if err is not None:`, rendered as the kinds of its statements: "naming" for an `if READ_FAILURES:` whose body is only the `name_read_failures(...)` call, "err" for the verdict branch, "-" otherwise."""
    tree = ast.parse(textwrap.dedent(source))
    out = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            kinds = []
            for stmt in stmts:
                text = ast.unparse(stmt) if isinstance(stmt, ast.If) else ""
                if text.startswith("if READ_FAILURES:") and len(stmt.body) == 1 and not stmt.orelse:
                    call = stmt.body[0]
                    is_call = isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)
                    name = ast.unparse(call.value.func) if is_call else ""
                    kinds.append("naming" if name == "name_read_failures" else "-")
                elif text.startswith("if err is not None:"):
                    kinds.append("err")
                else:
                    kinds.append("-")
            if "err" in kinds:
                out.append(" ".join(kinds))
    return out


def test_the_judge_naming_is_the_statement_right_before_the_verdict_branch():
    """d2f0573c.1: the naming call is its own `if READ_FAILURES:` statement, the sibling directly ahead of `if err is not None:` in the same block, so it runs on every judge answer; a call moved into an unrelated or unreached branch is no such sibling."""
    rows = _judge_naming_siblings(inspect.getsource(wl_checks._stop_judge))
    assert any("naming err" in row for row in rows), rows


def test_control_a_naming_call_nested_away_from_the_verdict_is_not_the_sibling():
    """d2f0573c.1 control: the same call buried in a branch that never runs is refused by the check above."""
    planted = (
        "def f():\n"
        "    if False:\n"
        "        if READ_FAILURES:\n"
        "            name_read_failures(a, b, c)\n"
        "    if err is not None:\n"
        "        pass\n"
    )
    rows = _judge_naming_siblings(planted)
    assert rows == ["- err"], rows
    assert not any("naming err" in row for row in rows)


# ---- e31b42fa.1: the ready-ticks comment says what the filter counts ------------


def test_the_ready_ticks_filter_counts_closed_rows_and_the_comment_says_so():
    assert re.search(r'readiness\(root, r\)\[0\] in \("ready", "closed"\)', SOURCE)
    comment = re.search(r"# TICKS A WRITER REPORTED[^\n]*", SOURCE)
    assert comment
    assert "`closed`" in comment.group(0)
    assert "--apply-ticks --write" in comment.group(0)

"""The "soaked pins available" advisory (agent/plans/PLAN-pins-command.md, T11).

The reader is driven against report.json files written into a scratch project. Every positive case has its control: the same report made stale, empty, malformed or absent says nothing. The effort row is checked against the real table, so an advisory the level never shows cannot pass.
"""

from __future__ import annotations

import ast
import datetime
import json

import pytest

from rediacc_hooks.tests import wlfix

SP = wlfix.import_wl("wl_soakedpins")
E = wlfix.import_wl("wl_effort")

NOW = datetime.datetime(2026, 10, 15, 6, 0, 0, tzinfo=datetime.UTC)
FRESH = "2026-10-15T00:31:12.482Z"
STALE = "2026-10-10T00:31:12.482Z"


def put(root, doc):
    path = SP.report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")


def pin(pid, frm, to):
    return {"id": pid, "from": frm, "to": to, "published": FRESH, "changes": []}


def test_a_fresh_report_with_soaked_pins_is_advised(tmp_path) -> None:
    put(
        tmp_path,
        {
            "now": FRESH,
            "pins": [pin("npm:zod", "4.6.7", "4.6.8"), pin("embed:tool", "1.0.0", "1.1.0")],
        },
    )
    assert SP.read(tmp_path, NOW) == [
        ("npm:zod", "4.6.7", "4.6.8"),
        ("embed:tool", "1.0.0", "1.1.0"),
    ]
    text = SP.advisory(tmp_path, NOW)
    assert text is not None
    assert "SOAKED PINS AVAILABLE (2" in text
    assert "npm:zod: 4.6.7 -> 4.6.8" in text
    assert "npm run pins -- apply-soaked" in text


@pytest.mark.parametrize(
    "doc",
    [
        {"now": FRESH, "pins": []},
        {"now": STALE, "pins": [pin("npm:zod", "1", "2")]},
        {"pins": [pin("npm:zod", "1", "2")]},
        {"now": "not a time", "pins": [pin("npm:zod", "1", "2")]},
        {"now": FRESH, "pins": "nope"},
        {"now": FRESH, "pins": [{"id": "", "to": "2"}, "junk"]},
        ["not", "a", "mapping"],
        "{ truncated",
        "",
    ],
)
def test_an_empty_stale_or_malformed_report_is_silence(tmp_path, doc) -> None:
    put(tmp_path, doc)
    assert SP.read(tmp_path, NOW) == []
    assert SP.advisory(tmp_path, NOW) is None


def test_no_report_is_silence(tmp_path) -> None:
    assert SP.advisory(tmp_path, NOW) is None


def test_a_long_list_is_capped_and_counted(tmp_path) -> None:
    put(
        tmp_path,
        {"now": FRESH, "pins": [pin("npm:p%d" % i, "1", "2") for i in range(SP.MAX_LISTED + 3)]},
    )
    text = SP.advisory(tmp_path, NOW)
    assert text is not None
    assert "(+3 more)" in text
    assert "npm:p%d:" % SP.MAX_LISTED not in text


def test_the_advisory_is_shown_from_smart_and_hidden_below() -> None:
    table, problem = E.load()
    assert not problem
    assert "soaked-pins" in table["checks"]
    assert E.advises("soaked-pins", "smart")
    assert E.advises("soaked-pins", "high")
    assert not E.advises("soaked-pins", "low")
    assert not E.advises("soaked-pins", "quiet")


def _wired(monkeypatch, advisory):
    """wl_checks._soaked_pins_report with the report reader replaced and outq_add recorded."""
    checks = wlfix.import_wl("wl_checks")
    calls: list[tuple] = []
    monkeypatch.setattr(SP, "advisory", advisory)
    monkeypatch.setattr(checks.C, "project_start", lambda: "/nowhere")
    monkeypatch.setattr(checks.C, "project_root", lambda _start: "/nowhere")
    monkeypatch.setattr(checks, "outq_add", lambda *a, **k: calls.append((a, k)))
    return checks, calls


def test_the_stop_hook_queues_the_advisory_under_its_effort_key(monkeypatch) -> None:
    checks, calls = _wired(monkeypatch, lambda _root: "2 soaked pins")
    checks._soaked_pins_report("wl", "sid", {})
    assert calls == [(("wl", "sid", {}, "soaked-pins", "2 soaked pins", 3), {})]


def test_the_stop_hook_queues_nothing_without_an_advisory_and_never_raises(monkeypatch) -> None:
    checks, calls = _wired(monkeypatch, lambda _root: None)
    checks._soaked_pins_report("wl", "sid", {})
    assert calls == []

    def boom(_root):
        raise RuntimeError("unreadable report")

    checks, calls = _wired(monkeypatch, boom)
    checks._soaked_pins_report("wl", "sid", {})
    assert calls == []


def _calls_in(source: str, function: str, callee: str) -> list[ast.Call]:
    tree = ast.parse(source)
    return [
        call
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef) and fn.name == function
        for call in ast.walk(fn)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == callee
    ]


def test_run_stop_calls_the_soaked_pins_report() -> None:
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    assert _calls_in(source, "run_stop", "_soaked_pins_report")


def test_the_call_finder_reads_the_enclosing_function_not_the_text() -> None:
    source = "def other():\n    _soaked_pins_report(a, b, c)\n\ndef run_stop():\n    return 1\n"
    assert _calls_in(source, "other", "_soaked_pins_report")
    assert not _calls_in(source, "run_stop", "_soaked_pins_report")

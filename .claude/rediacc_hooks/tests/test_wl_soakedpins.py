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


# A class body runs when the function around it runs, so it is walked; the defs and lambdas inside it are not.
NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _calls_in(
    source: str, function: str, callee: str, argument_names: tuple[str, ...]
) -> list[ast.Call]:
    """The calls to `callee(*argument_names)` that `function` itself runs: its own body, class bodies included (they run with it), but not a def or lambda nested in it (which never runs unless something calls it)."""
    tree = ast.parse(source)
    found: list[ast.Call] = []
    for fn in ast.walk(tree):
        if not (isinstance(fn, ast.FunctionDef) and fn.name == function):
            continue
        stack: list[ast.AST] = list(fn.body)
        while stack:
            node = stack.pop()
            if isinstance(node, NESTED_SCOPES):
                continue
            stack.extend(ast.iter_child_nodes(node))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == callee
                and not node.keywords
                and [a.id if isinstance(a, ast.Name) else None for a in node.args]
                == list(argument_names)
            ):
                found.append(node)
    return found


RUN_STOP_ARGS = ("worklist", "session_id", "state_doc")


def test_run_stop_calls_the_soaked_pins_report() -> None:
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    # run_stop's segments are `_stop_<key>(ns)` functions (PLAN-tooling-speed.md SP3), so the call may sit in run_stop or in one of them.
    holders = ["run_stop"] + [
        n.name
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name.startswith("_stop_")
    ]
    assert any(_calls_in(source, fn, "_soaked_pins_report", RUN_STOP_ARGS) for fn in holders)


def test_the_call_finder_reads_the_enclosing_function_not_the_text() -> None:
    source = "def other():\n    _soaked_pins_report(a, b, c)\n\ndef run_stop():\n    return 1\n"
    assert _calls_in(source, "other", "_soaked_pins_report", ("a", "b", "c"))
    assert not _calls_in(source, "run_stop", "_soaked_pins_report", ("a", "b", "c"))


def test_the_call_finder_needs_the_exact_arguments() -> None:
    head = "def run_stop(worklist, session_id, state_doc):\n"
    for call in (
        "_soaked_pins_report()",
        "_soaked_pins_report(worklist)",
        "_soaked_pins_report(session_id, worklist, state_doc)",
        "_soaked_pins_report(worklist, session_id, state_doc, extra)",
        "_soaked_pins_report(worklist, session_id, state_doc=state_doc)",
        "_soaked_pins_report(worklist, session_id, {})",
    ):
        assert not _calls_in(
            head + "    " + call + "\n", "run_stop", "_soaked_pins_report", RUN_STOP_ARGS
        ), call
    good = head + "    _soaked_pins_report(worklist, session_id, state_doc)\n"
    assert _calls_in(good, "run_stop", "_soaked_pins_report", RUN_STOP_ARGS)


def test_the_call_finder_ignores_a_call_inside_a_nested_def() -> None:
    nested = (
        "def run_stop(worklist, session_id, state_doc):\n"
        "    def never_called():\n"
        "        _soaked_pins_report(worklist, session_id, state_doc)\n"
        "    return never_called\n"
    )
    assert not _calls_in(nested, "run_stop", "_soaked_pins_report", RUN_STOP_ARGS)
    inline = (
        "def run_stop(worklist, session_id, state_doc):\n"
        "    if worklist:\n"
        "        _soaked_pins_report(worklist, session_id, state_doc)\n"
    )
    assert _calls_in(inline, "run_stop", "_soaked_pins_report", RUN_STOP_ARGS)


def test_the_call_finder_walks_a_class_body_but_not_its_methods():
    in_class = (
        "def run_stop(worklist, session_id, state_doc):\n"
        "    class Holder:\n"
        "        _soaked_pins_report(worklist, session_id, state_doc)\n"
    )
    assert _calls_in(in_class, "run_stop", "_soaked_pins_report", RUN_STOP_ARGS)
    in_method = (
        "def run_stop(worklist, session_id, state_doc):\n"
        "    class Holder:\n"
        "        def method(self):\n"
        "            _soaked_pins_report(worklist, session_id, state_doc)\n"
    )
    assert not _calls_in(in_method, "run_stop", "_soaked_pins_report", RUN_STOP_ARGS)


# THE DAILY LOCAL ROUTE (PLAN-ciquick-gate-contract K6): once per UTC day, development tree only, result recorded.
DAY1 = datetime.datetime(2026, 11, 28, 6, 0, 0, tzinfo=datetime.UTC)
DAY1_LATE = datetime.datetime(2026, 11, 28, 23, 59, 0, tzinfo=datetime.UTC)
DAY2 = datetime.datetime(2026, 11, 29, 0, 1, 0, tzinfo=datetime.UTC)


def _stamp(root, day, **extra):
    path = SP.stamp_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"day": day, **extra}), encoding="utf-8")


def test_a_stale_stamp_runs_the_fake_apply_and_claims_the_day(tmp_path) -> None:
    _stamp(tmp_path, "2026-11-27", state="done", rc=0)
    spawned: list[str] = []
    claim = SP.run_daily(tmp_path, "development", DAY1, spawn=spawned.append)
    assert claim is not None
    assert spawned == [str(tmp_path)]
    assert json.loads(SP.stamp_path(tmp_path).read_text())["day"] == "2026-11-28"


def test_no_stamp_runs_it_too(tmp_path) -> None:
    spawned: list[str] = []
    assert SP.run_daily(tmp_path, "", DAY1, spawn=spawned.append) is not None
    assert spawned == [str(tmp_path)]


def test_a_same_day_stamp_does_not_run_it_again(tmp_path) -> None:
    spawned: list[str] = []
    SP.run_daily(tmp_path, "development", DAY1, spawn=spawned.append)
    # Control: a second stop later the same UTC day, then the next day.
    assert SP.run_daily(tmp_path, "development", DAY1_LATE, spawn=spawned.append) is None
    assert len(spawned) == 1
    assert SP.run_daily(tmp_path, "development", DAY2, spawn=spawned.append) is not None
    assert len(spawned) == 2


def test_the_landing_tree_never_runs_it(tmp_path) -> None:
    spawned: list[str] = []
    assert SP.run_daily(tmp_path, "landing", DAY1, spawn=spawned.append) is None
    assert spawned == []
    assert not SP.stamp_path(tmp_path).exists()
    # Control: the same tree as a development tree does run it.
    assert SP.run_daily(tmp_path, "development", DAY1, spawn=spawned.append) is not None


def test_a_lease_tree_never_runs_it(tmp_path) -> None:
    lease = tmp_path / ".claude" / "worktrees" / "d778be9d-12"
    lease.mkdir(parents=True)
    spawned: list[str] = []
    assert SP.run_daily(lease, "development", DAY1, spawn=spawned.append) is None
    assert spawned == []


def test_a_failing_spawn_never_raises(tmp_path) -> None:
    def boom(_root):
        raise OSError("no npm")

    assert SP.run_daily(tmp_path, "development", DAY1, spawn=boom) is None


def test_a_failing_spawn_releases_the_day_for_a_retry(tmp_path) -> None:
    """Review 86953e7c.2: a spawn that raises does not consume the day; the next stop is due again and the failure is recorded."""

    def boom(_root):
        raise OSError("no npm")

    SP.run_daily(tmp_path, "development", DAY1, spawn=boom)
    on_disk = json.loads(SP.stamp_path(tmp_path).read_text())
    assert on_disk["state"] == "spawn-failed"
    assert on_disk["failed_day"] == "2026-11-28"
    assert "no npm" in on_disk["error"]
    assert SP.due(tmp_path, "development", DAY1) is True
    # And a later spawn that works claims the day as usual.
    assert SP.run_daily(tmp_path, "development", DAY1, spawn=lambda _r: None) is not None
    assert SP.due(tmp_path, "development", DAY1) is False


def test_the_runner_records_its_result_under_the_claimed_day(tmp_path) -> None:
    SP.run_daily(tmp_path, "development", DAY1, spawn=lambda _r: None)
    ticks = iter([10.0, 14.5])
    res = SP.run_verb(tmp_path, runner=lambda _r: (0, "applied 2 pins"), clock=lambda: next(ticks))
    assert res["rc"] == 0
    assert res["seconds"] == 4.5
    on_disk = json.loads(SP.stamp_path(tmp_path).read_text())
    assert on_disk["day"] == "2026-11-28"
    assert on_disk["state"] == "done"
    assert "applied 2 pins" in on_disk["tail"]
    # Control: a failing verb records its rc and does not reopen the day.
    res = SP.run_verb(tmp_path, runner=lambda _r: (3, "refused"))
    assert json.loads(SP.stamp_path(tmp_path).read_text())["rc"] == 3
    assert SP.run_daily(tmp_path, "development", DAY1_LATE, spawn=lambda _r: None) is None


def test_a_raising_runner_is_recorded_as_a_failure(tmp_path) -> None:
    def boom(_r):
        raise RuntimeError("network down")

    res = SP.run_verb(tmp_path, runner=boom)
    assert res["rc"] == 1
    assert "network down" in res["tail"]


def test_the_verb_is_the_apply_soaked_verb_writing_the_report_dir() -> None:
    assert SP.VERB[:5] == ["npm", "run", "pins", "--", "apply-soaked"]
    assert SP.VERB[-1] == ".ci/cache/pins-soaked"
    # The hook only claims and spawns; the verb's budget sits under the Stop hook's 900 s.
    assert SP.VERB_TIMEOUT_S < 900


def test_run_stop_calls_the_daily_route() -> None:
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    assert "_soaked_pins_daily(" in source
    assert "wl_soakedpins.run_daily(root, role)" in source

"""Named read failures in wl_review, wl_schedred, wl_histfirst and wl_resprofile (SF5 of agent/plans/PLAN-silent-failure-sweep.md).

THE CLASS: a broad handler that turned a failed read into the same value as "nothing there". Each changed site either names the failure in the text it already speaks (the review CLI's stderr, a SessionStart line, a red's cause, the history block), or keeps a conservative default that carries a `# swallowed-failure-ok:` reason saying why that default is the safe one.

Every red case has a silent twin, and a structural test holds the four files to the rule SF9's gate will hold them to.
"""

from __future__ import annotations

import ast
import types

import pytest
import wl_histfirst
import wl_planrec
import wl_review
import wl_schedred
import wl_store

from rediacc_hooks.tests import wlfix

FILES = ("wl_review.py", "wl_schedred.py", "wl_histfirst.py", "wl_resprofile.py")
WAIVER = "# swallowed-failure-ok:"


def raising(*_a, **_k):
    raise RuntimeError("sf5-injected")


# ---- the structural rule over the four files -----------------------------------


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, ast.Constant) and v.value in (None, "", 0, False):
        return True
    if isinstance(v, (ast.List, ast.Tuple, ast.Set)) and not v.elts:
        return True
    return isinstance(v, ast.Dict) and not v.keys


def silent_unwaived(source: str) -> list[int]:
    """Line numbers of broad handlers (Exception, BaseException, bare) that neither raise nor use their bound name and end in an empty return, pass, continue or empty assignment, with no waiver on the line above."""
    lines = source.splitlines()
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        names = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        if node.type is not None and not any(
            isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names
        ):
            continue
        if any(isinstance(x, ast.Raise) for x in ast.walk(node)):
            continue
        if node.name and any(
            isinstance(x, ast.Name) and x.id == node.name for b in node.body for x in ast.walk(b)
        ):
            continue
        last = node.body[-1]
        silent = (
            (isinstance(last, ast.Return) and _empty(last.value))
            or isinstance(last, (ast.Pass, ast.Continue))
            or (isinstance(last, ast.Assign) and _empty(last.value))
        )
        above = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
        if silent and not (above.startswith(WAIVER) and len(above[len(WAIVER) :].strip()) >= 30):
            out.append(node.lineno)
    return out


@pytest.mark.parametrize("name", FILES)
def test_every_broad_handler_names_its_failure_or_says_why_not(name):
    source = (wlfix.STOP_DIR / name).read_text(encoding="utf-8")
    assert silent_unwaived(source) == []


def test_the_rule_fires_on_a_planted_handler():
    """CONTROL in the other direction: the scan above is seen to fire."""
    planted = "def f():\n    try:\n        g()\n    except Exception:\n        return []\n"
    assert silent_unwaived(planted) == [4]
    short = "def f():\n    try:\n        g()\n    # swallowed-failure-ok: fine\n    except Exception:\n        pass\n"
    assert silent_unwaived(short) == [5]
    named = (
        "def f():\n    try:\n        g()\n    except Exception as exc:\n        return str(exc)\n"
    )
    assert silent_unwaived(named) == []


# ---- wl_review.landing_base ----------------------------------------------------


def test_an_unreadable_landing_record_is_named_on_stderr(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(wl_review, "_policy", lambda: types.SimpleNamespace(tree_binding=raising))
    assert wl_review.landing_base(tmp_path, "1121-2") == ""
    err = capsys.readouterr().err
    assert "the landing record could not be read (RuntimeError: sf5-injected)" in err


def test_no_landing_record_is_silent(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        wl_review, "_policy", lambda: types.SimpleNamespace(tree_binding=lambda _r: (None, ""))
    )
    assert wl_review.landing_base(tmp_path, "1121-2") == ""
    assert capsys.readouterr().err == ""


# ---- wl_schedred ----------------------------------------------------------------


def test_a_failed_diagnosis_names_the_cause_and_is_not_cached(monkeypatch, tmp_path):
    diag = types.SimpleNamespace(GhFetcher=raising, diagnose=raising)
    monkeypatch.setattr(wl_schedred.wl_ci, "_load_diagnose", lambda: diag)
    found, ok = wl_schedred._diagnosis(tmp_path, "o", "n", 1)
    assert ok is False
    assert found["cause"].startswith("the diagnosis could not be read (RuntimeError: sf5-injected)")


def test_a_read_diagnosis_is_cached_and_says_nothing_of_a_failure(monkeypatch, tmp_path):
    diag = types.SimpleNamespace(
        GhFetcher=lambda *_a, **_k: object(),
        diagnose=lambda _f, _r: {"verdict": "red", "first_failure": {"name": "lint"}, "cause": {}},
    )
    monkeypatch.setattr(wl_schedred.wl_ci, "_load_diagnose", lambda: diag)
    found, ok = wl_schedred._diagnosis(tmp_path, "o", "n", 1)
    assert ok is True
    assert found["root"] == "lint"
    assert "could not be read" not in found["cause"]


def test_an_unreadable_freshness_cache_is_named_at_session_start(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_schedred, "_red_session_start_line", lambda _w: "")
    monkeypatch.setattr(wl_schedred, "read_freshness", raising)
    line = wl_schedred.session_start_line(tmp_path / "wl.md")
    assert "[the freshness cache could not be read (RuntimeError: sf5-injected)]" in line


def test_a_clean_session_start_says_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_schedred, "read_freshness", lambda _w: None)
    monkeypatch.setattr(wl_schedred, "read_cache", lambda _w: None)
    assert wl_schedred.session_start_line(tmp_path / "wl.md") == ""


def test_an_unreadable_red_cache_is_named_at_session_start(monkeypatch, tmp_path):
    monkeypatch.setattr(wl_schedred, "read_cache", raising)
    line = wl_schedred._red_session_start_line(tmp_path / "wl.md")
    assert "the scheduled-red cache could not be read (RuntimeError: sf5-injected)" in line


def test_a_failure_after_the_cache_read_is_not_blamed_on_the_cache(monkeypatch, tmp_path):
    doc = {"workflows": [{"red": True, "run_id": 1}], "at": 0}
    monkeypatch.setattr(wl_schedred, "read_cache", lambda _w: doc)
    monkeypatch.setattr(wl_schedred, "fields", raising)
    line = wl_schedred._red_session_start_line(tmp_path / "wl.md")
    assert "the scheduled-red line could not be built from the cache (RuntimeError" in line
    assert "cache could not be read" not in line


def test_an_unreadable_worklist_makes_tracked_unknown_not_untracked(monkeypatch, tmp_path):

    red = {"red": True, "run_id": 42, "stem": "ci-drift", "name": "CI - Drift", "url": "u"}
    monkeypatch.setattr(wl_schedred, "read_cache", lambda _w: {"workflows": [red], "at": 0})
    monkeypatch.setattr(wl_store, "load", raising)
    line = wl_schedred._red_session_start_line(tmp_path / "wl.md")
    assert (
        "the worklist could not be read (RuntimeError: sf5-injected), so tracked is unknown" in line
    )
    # b9c7fd2d.2: the unread worklist never renders the false "untracked" verdict.
    assert "untracked" not in line, line


def test_a_readable_worklist_does_not_mention_it(monkeypatch, tmp_path):

    red = {"red": True, "run_id": 42, "stem": "ci-drift", "name": "CI - Drift", "url": "u"}
    monkeypatch.setattr(wl_schedred, "read_cache", lambda _w: {"workflows": [red], "at": 0})
    monkeypatch.setattr(wl_store, "load", lambda *_a, **_k: types.SimpleNamespace(items=[]))
    line = wl_schedred._red_session_start_line(tmp_path / "wl.md")
    assert line
    assert "could not be read" not in line
    # Control for the "untracked" assertion above: a readable worklist with no item tracking the red says so.
    assert "untracked" in line, line


# ---- wl_histfirst ---------------------------------------------------------------


def _history_world(monkeypatch):
    monkeypatch.setattr(wl_histfirst, "_git", lambda _root, *_a: "abc1234 one commit\n")
    monkeypatch.setattr(
        wl_histfirst,
        "suspects",
        lambda *_a: [("abc1234ab", "touch lint", [".ci/lint.py"])],
    )
    return [{"name": "lint", "step": "lint"}]


def test_an_unreadable_plan_record_is_named_in_the_history_block(monkeypatch, tmp_path):

    rows = _history_world(monkeypatch)
    monkeypatch.setattr(wl_planrec, "why_for_paths", raising)
    text = wl_histfirst.render(tmp_path, rows, "deadbeef")
    assert "Start here:" in text
    assert "(the plan-record layer could not be read: RuntimeError: sf5-injected)" in text


def test_a_readable_plan_record_layer_says_nothing_of_a_failure(monkeypatch, tmp_path):

    rows = _history_world(monkeypatch)
    monkeypatch.setattr(wl_planrec, "why_for_paths", lambda *_a: "")
    text = wl_histfirst.render(tmp_path, rows, "deadbeef")
    assert "Start here:" in text
    assert "could not be read" not in text

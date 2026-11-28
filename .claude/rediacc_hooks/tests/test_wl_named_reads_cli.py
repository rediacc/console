"""Named failures in `worklist.py` and `wl_cli.py` (SF6 of agent/plans/PLAN-silent-failure-sweep.md).

THE CLASS: a broad `except Exception` that hands back an empty default (`None`, `{}`, `return`, `pass`) without saying why, so a failed import or read looks like "nothing there". Each site below keeps its default, because the hook is never taken down by an advisory, and now writes one stderr line naming the failure.

Every red case has a silent twin: the same call with nothing broken writes no such line, so the naming cannot turn into noise.
"""

from __future__ import annotations

import ast
import io
import shutil
import sys

import pytest

from rediacc_hooks.tests import wlfix

worklist = wlfix.import_wl("worklist")
wl_cli = wlfix.import_wl("wl_cli")


def _copy_hook(wl, mutate: dict[str, tuple[str, str]]):
    """A copy of the hook directory with each `{file: (old, new)}` text swap applied (and asserted to match once)."""
    hooks = wl.base / "hooks" / "stop"
    shutil.copytree(wlfix.STOP_DIR, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    for name, (old, new) in mutate.items():
        text = (hooks / name).read_text(encoding="utf-8")
        assert text.count(old) == 1, (name, old)
        (hooks / name).write_text(text.replace(old, new), encoding="utf-8")
    wl.hook = hooks / "worklist.py"


# ---- worklist.py: the last-known-good import ----------------------------------


def test_a_broken_lkg_import_is_named(wl):
    _copy_hook(
        wl,
        {
            "wl_lkg.py": (
                "\nimport contextlib\n",
                '\nraise ImportError("sf6-injected")\nimport contextlib\n',
            )
        },
    )
    got = wl.cli("--list", "--open", wlfix.ME)
    assert "wl_lkg did not import (ImportError: sf6-injected)" in got.err, got.err[:400]


def test_a_working_lkg_import_says_nothing(wl):
    got = wl.cli("--list", "--open", wlfix.ME)
    assert "wl_lkg did not import" not in got.err


# ---- worklist.py: the stand-down's wl_git import ------------------------------


def test_a_broken_wl_git_import_is_named_by_the_standdown(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "wl_git", None)
    assert worklist._operation_standdown({"cwd": "/nonexistent"}) is None
    assert "wl_git did not import" in capsys.readouterr().err


def test_a_working_wl_git_import_says_nothing(monkeypatch, capsys, tmp_path):
    monkeypatch.undo()
    worklist._operation_standdown({"cwd": str(tmp_path)})
    assert "wl_git did not import" not in capsys.readouterr().err


# ---- worklist.py: a stdin that cannot be read ---------------------------------


class _UnreadableStdin:
    def fileno(self):
        raise OSError("no fd")

    def read(self):
        raise RuntimeError("sf6-injected")


def test_an_unreadable_stdin_is_named(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _UnreadableStdin())
    assert worklist._read_event() == ({}, False)
    assert "stdin could not be read (RuntimeError: sf6-injected)" in capsys.readouterr().err


def test_a_readable_stdin_says_nothing(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"session_id": "abc"}'))
    event, _ = worklist._read_event()
    assert event.get("session_id") == "abc"
    assert "stdin could not be read" not in capsys.readouterr().err


# ---- wl_cli.py: the running-task output ages ----------------------------------


def test_unavailable_output_ages_are_named(monkeypatch, capsys):
    def boom():
        raise OSError("sf6-injected")

    monkeypatch.setattr(wl_cli.os, "getcwd", boom)
    assert wl_cli._annotated_running(["a1", "b2"], "abcd1234") == "a1, b2"
    assert "output ages unavailable (OSError: sf6-injected)" in capsys.readouterr().err


def test_readable_output_ages_say_nothing(capsys):
    assert wl_cli._annotated_running(["a1"], "abcd1234") == "a1"
    assert "output ages unavailable" not in capsys.readouterr().err


# ---- wl_cli.py: the --state signature refresh ---------------------------------


def test_a_failed_state_sig_refresh_is_named(wl):
    _copy_hook(
        wl,
        {
            "wl_cli.py": (
                'doc["state_sig"] = S.state_items_sig(',
                'doc["state_sig"] = (_ for _ in ()).throw(RuntimeError("sf6-injected")) or S.state_items_sig(',
            )
        },
    )
    got = wl.cli("--state", wlfix.ME, stdin=wlfix.STATE_BODY)
    assert got.rc == 0, got.err[:400]
    assert "state_sig could not be refreshed (RuntimeError: sf6-injected)" in got.err, got.err[:400]
    assert "STATE.md section written" in got.out


def test_a_clean_state_write_says_nothing(wl):
    got = wl.cli("--state", wlfix.ME, stdin=wlfix.STATE_BODY)
    assert got.rc == 0, got.err[:400]
    assert "could not be refreshed" not in got.err


def _silent_handlers(source: str, name: str) -> list[str]:
    """`<name>:<line>` for each `except Exception` (or bare, or BaseException) in `source` that ends in an empty value without using or re-raising the exception, unless the line above carries `swallowed-failure-ok`."""

    def empty(v):
        return v is None or (isinstance(v, ast.Constant) and v.value in (None, "", 0, False))

    bad = []
    lines = source.split("\n")
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        names = (
            []
            if node.type is None
            else [node.type]
            if not isinstance(node.type, ast.Tuple)
            else list(node.type.elts)
        )
        if node.type is not None and not any(
            isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names
        ):
            continue
        body = list(node.body)
        walked = [n for st in body for n in ast.walk(st)]
        if any(isinstance(n, ast.Raise) for n in walked):
            continue
        if node.name and any(isinstance(n, ast.Name) and n.id == node.name for n in walked):
            continue
        last = body[-1]
        silent = (
            (isinstance(last, ast.Return) and empty(last.value))
            or isinstance(last, (ast.Pass, ast.Continue))
            or (isinstance(last, ast.Assign) and empty(last.value))
        )
        waived = node.lineno >= 2 and "swallowed-failure-ok" in lines[node.lineno - 2]
        if silent and not waived:
            bad.append("%s:%d" % (name, node.lineno))
    return bad


def test_the_cli_and_hook_hold_no_unnamed_broad_handler():
    """The Context 6 rule over these two files: no `except Exception` that ends in an empty value without using or re-raising the exception."""
    bad = []
    for path in (wlfix.STOP_DIR / "worklist.py", wlfix.STOP_DIR / "wl_cli.py"):
        bad += _silent_handlers(path.read_text(encoding="utf-8"), path.name)
    assert bad == []


@pytest.mark.parametrize(
    ("source", "want"),
    [
        ("try:\n    x()\nexcept Exception:\n    pass\n", ["p.py:3"]),
        ("try:\n    x()\nexcept (OSError, Exception):\n    y = None\n", ["p.py:3"]),
        (
            "def f():\n    try:\n        x()\n    except BaseException:\n        return ''\n",
            ["p.py:4"],
        ),
        ("try:\n    x()\nexcept Exception as exc:\n    log(exc)\n", []),
        ("try:\n    x()\nexcept Exception:\n    raise\n", []),
        ("try:\n    x()\nexcept OSError:\n    pass\n", []),
        ("try:\n    x()\n# swallowed-failure-ok: a probe\nexcept Exception:\n    pass\n", []),
    ],
)
def test_control_the_scan_sees_a_planted_silent_handler(source, want):
    """daf9c7a5.1: the SAME scan the test above runs, over planted sources: a silent broad handler is flagged, a named, re-raised, narrow or waived one is not."""
    assert _silent_handlers(source, "p.py") == want


@pytest.fixture(autouse=True)
def _keep_stdin():
    saved = sys.stdin
    yield
    sys.stdin = saved

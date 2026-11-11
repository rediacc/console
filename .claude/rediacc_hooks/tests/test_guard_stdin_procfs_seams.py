"""The procfs spelling of stdin in two guards is named from the environment (hook_cross_os scopes `review-stdin-anchor` and `worktree-stdin-anchor`).

Each guard reads its root once, at import, so each case loads a fresh copy of the module under the environment it names. The default case pins `/proc`; the override case pins that the configured root's spelling is recognised and the default one no longer is (review 7ba9677a.1, which found the override path untested).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
REVIEW = HOOKS / "guards" / "block_review_file_shell_write.py"
WORKTREE = HOOKS / "guards" / "block_worktree_add.py"


def _load(path: pathlib.Path, alias: str):
    if str(HOOKS) not in sys.path:
        sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_review_guard_default_root_is_proc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIACC_REVIEW_STDIN_PROCFS", raising=False)
    g = _load(REVIEW, "review_stdin_default")
    assert "/proc/self/fd/0" in g._STDIN_DEVICES
    assert g._may_be_stdin("/proc/self/fd/0")


def test_review_guard_override_moves_the_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIACC_REVIEW_STDIN_PROCFS", "/altproc/")
    g = _load(REVIEW, "review_stdin_override")
    assert "/altproc/self/fd/0" in g._STDIN_DEVICES
    assert "/proc/self/fd/0" not in g._STDIN_DEVICES
    assert g._may_be_stdin("/altproc/self/fd/0")


def test_worktree_guard_default_root_is_proc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIACC_WORKTREE_STDIN_PROCFS", raising=False)
    g = _load(WORKTREE, "worktree_stdin_default")
    assert g.PROC_STDIN == "/proc/self/fd/0"
    assert "/proc/self/fd/0" in g.STDIN_PATHS


def test_worktree_guard_override_moves_the_spelling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIACC_WORKTREE_STDIN_PROCFS", "/altproc")
    g = _load(WORKTREE, "worktree_stdin_override")
    assert g.PROC_STDIN == "/altproc/self/fd/0"
    assert "/proc/self/fd/0" not in g.STDIN_PATHS

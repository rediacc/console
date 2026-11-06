"""PLAN-backup-program J9: the renet_changed decision, driven against real throwaway git repositories."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import renet_changed

if TYPE_CHECKING:
    import pathlib

ZERO = "0" * 40


def _run(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: pathlib.Path, name: str, content: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _run(repo, "git", "add", "-A")
    _run(repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)
    return _run(repo, "git", "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    _run(tmp_path, "git", "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_push_detects_a_renet_path_change(repo: pathlib.Path) -> None:
    base = _commit(repo, "a.txt", "1")
    _commit(repo, "private/renet/x", "2")
    assert renet_changed.decide("push", base, "") is True


def test_push_without_a_renet_change_is_false(repo: pathlib.Path) -> None:
    base = _commit(repo, "private/renet/x", "1")
    _commit(repo, "b.txt", "2")
    assert renet_changed.decide("push", base, "") is False


def test_branch_creating_push_fails_open(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    assert renet_changed.decide("push", ZERO, "") is True


def test_pull_request_uses_the_merge_base(repo: pathlib.Path) -> None:
    root = _commit(repo, "a.txt", "1")
    _run(repo, "git", "checkout", "-q", "-b", "pr")
    _commit(repo, "private/renet/x", "pr")
    pr_head = _run(repo, "git", "rev-parse", "HEAD")
    _run(repo, "git", "checkout", "-q", "main")
    # main moves on without touching renet, then the PR head is checked out
    main_tip = _commit(repo, "c.txt", "main")
    _run(repo, "git", "checkout", "-q", pr_head)
    assert renet_changed.decide("pull_request", main_tip, main_tip) is True
    assert root


def test_pull_request_untouched_renet_is_false_even_when_base_moved_renet(
    repo: pathlib.Path,
) -> None:
    _commit(repo, "a.txt", "1")
    _run(repo, "git", "checkout", "-q", "-b", "pr")
    _commit(repo, "b.txt", "pr")
    pr_head = _run(repo, "git", "rev-parse", "HEAD")
    _run(repo, "git", "checkout", "-q", "main")
    main_tip = _commit(repo, "private/renet/x", "main moved renet")
    _run(repo, "git", "checkout", "-q", pr_head)
    assert renet_changed.decide("pull_request", main_tip, main_tip) is False


def test_missing_base_fails_open(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    assert renet_changed.decide("pull_request", "", "") is True
    assert renet_changed.decide("pull_request", "", "1" * 40) is True


def test_other_events_are_false(repo: pathlib.Path) -> None:
    _commit(repo, "private/renet/x", "1")
    assert renet_changed.decide("schedule", "", "") is False

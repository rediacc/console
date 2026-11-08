"""PLAN-backup-program J6: the backup_changed decision, driven against real throwaway git repositories."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import backup_changed, renet_changed

if TYPE_CHECKING:
    import pathlib

ZERO = "0" * 40
BACKUP_GO = "private/renet/pkg/chunkstore/store.go"
BACKUP_SUITE = "packages/e2e-tests/tests/26-backup-storage-cli.test.ts"
OTHER_RENET_GO = "private/renet/pkg/unrelated/x.go"


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
    # The fixture commits plain files under private/renet/, which a real tree holds as a gitlink. With the submodule
    # list emptied those files are read as paths, so the area globs answer; the gitlink fail-open has its own test.
    monkeypatch.setattr(backup_changed.surfaces, "SUBMODULES", ())
    return tmp_path


def test_the_path_set_comes_from_the_proof_map() -> None:
    assert BACKUP_SUITE in backup_changed._suites()


def test_push_detects_a_renet_backup_path(repo: pathlib.Path) -> None:
    base = _commit(repo, "a.txt", "1")
    _commit(repo, BACKUP_GO, "2")
    assert backup_changed.decide("push", base, "") is True


def test_push_detects_a_backup_suite_file(repo: pathlib.Path) -> None:
    base = _commit(repo, "a.txt", "1")
    _commit(repo, BACKUP_SUITE, "2")
    assert backup_changed.decide("push", base, "") is True


def test_push_without_a_backup_path_is_false(repo: pathlib.Path) -> None:
    base = _commit(repo, BACKUP_GO, "1")
    _commit(repo, "b.txt", "2")
    _commit(repo, OTHER_RENET_GO, "3")
    assert backup_changed.decide("push", base, "") is False


def test_branch_creating_push_fails_open(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    assert backup_changed.decide("push", ZERO, "") is True


def test_pull_request_uses_the_merge_base(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    _run(repo, "git", "checkout", "-q", "-b", "pr")
    _commit(repo, BACKUP_GO, "pr")
    pr_head = _run(repo, "git", "rev-parse", "HEAD")
    _run(repo, "git", "checkout", "-q", "main")
    main_tip = _commit(repo, "c.txt", "main")
    _run(repo, "git", "checkout", "-q", pr_head)
    assert backup_changed.decide("pull_request", main_tip, main_tip) is True


def test_pull_request_untouched_backup_is_false_even_when_base_moved_it(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    _run(repo, "git", "checkout", "-q", "-b", "pr")
    _commit(repo, "b.txt", "pr")
    pr_head = _run(repo, "git", "rev-parse", "HEAD")
    _run(repo, "git", "checkout", "-q", "main")
    main_tip = _commit(repo, BACKUP_GO, "main moved backup")
    _run(repo, "git", "checkout", "-q", pr_head)
    assert backup_changed.decide("pull_request", main_tip, main_tip) is False


def test_missing_base_fails_open(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    assert backup_changed.decide("pull_request", "", "") is True
    assert backup_changed.decide("pull_request", "", "1" * 40) is True


def test_other_events_are_false(repo: pathlib.Path) -> None:
    _commit(repo, BACKUP_GO, "1")
    assert backup_changed.decide("schedule", "", "") is False
    assert backup_changed.decide("workflow_dispatch", "", "") is False


def test_a_base_with_no_merge_base_fails_open(repo: pathlib.Path) -> None:
    _commit(repo, "a.txt", "1")
    _run(repo, "git", "checkout", "-q", "--orphan", "unrelated")
    unrelated = _commit(repo, "u.txt", "orphan")
    _run(repo, "git", "checkout", "-q", "main")
    assert backup_changed.decide("pull_request", unrelated, unrelated) is True


@pytest.mark.usefixtures("repo")
def test_a_missing_git_binary_answers_true_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_git(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(renet_changed.subprocess, "run", no_git)
    assert backup_changed.decide("push", "1" * 40, "") is True
    assert backup_changed.decide("pull_request", "", "1" * 40) is True


def test_a_failed_submodule_range_fails_open(
    repo: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _commit(repo, "a.txt", "1")
    _commit(repo, "b.txt", "2")
    unknown = backup_changed.surfaces.Changed(hits=(), unknown=("private/renet x: not checked out",))
    monkeypatch.setattr(backup_changed.surfaces, "changed_paths", lambda *_a, **_k: unknown)
    assert backup_changed.decide("push", base, "") is True


def test_main_writes_the_output_file(
    repo: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    base = _commit(repo, "a.txt", "1")
    _commit(repo, BACKUP_GO, "2")
    out = tmp_path_factory.mktemp("out") / "gh_output"
    monkeypatch.setenv("EVENT_NAME", "push")
    monkeypatch.setenv("BEFORE_SHA", base)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert backup_changed.main() == 0
    assert out.read_text() == "changed=true\n"

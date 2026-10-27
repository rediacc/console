"""rediacc_ci.release.tag against a throwaway bare remote. Nothing here touches a real remote."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.release import tag

if TYPE_CHECKING:
    from pathlib import Path


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path):
    bare = tmp_path / "remote.git"
    bare.mkdir()
    _run(bare, "init", "--bare", "-q")
    work = tmp_path / "work"
    work.mkdir()
    _run(work, "init", "-q")
    _run(work, "config", "user.name", "t")
    _run(work, "config", "user.email", "t@example.invalid")
    _run(work, "config", "commit.gpgsign", "false")
    _run(work, "remote", "add", "origin", str(bare))
    (work / "a").write_text("1")
    _run(work, "add", "a")
    _run(work, "commit", "-q", "-m", "one")
    first = _run(work, "rev-parse", "HEAD")
    (work / "a").write_text("2")
    _run(work, "commit", "-q", "-am", "two")
    second = _run(work, "rev-parse", "HEAD")
    return work, bare, first, second


def test_create_then_idempotent(repo):
    work, bare, first, _ = repo
    out = tag.ensure_tag("1.2.3", first, cwd=str(work))
    assert out.startswith("Created tag v1.2.3")
    assert _run(bare, "rev-parse", "v1.2.3^{commit}") == first
    assert _run(bare, "cat-file", "-t", "v1.2.3") == "tag"
    again = tag.ensure_tag("1.2.3", first, cwd=str(work))
    assert "already exists" in again


def test_lightweight(repo):
    work, bare, first, _ = repo
    tag.ensure_tag("1.0.0", first, cwd=str(work), lightweight=True)
    assert _run(bare, "cat-file", "-t", "v1.0.0") == "commit"


def test_conflicting_commit_refused(repo):
    work, bare, first, second = repo
    tag.ensure_tag("1.2.3", first, cwd=str(work))
    with pytest.raises(tag.TagError, match="two commits"):
        tag.ensure_tag("1.2.3", second, cwd=str(work))
    assert _run(bare, "rev-parse", "v1.2.3^{commit}") == first
    assert "already exists" in tag.ensure_tag("1.2.3", second, cwd=str(work), retry=True)


def test_retry_without_remote_tag_refused(repo):
    work, _, first, _ = repo
    with pytest.raises(tag.TagError, match="no such tag"):
        tag.ensure_tag("9.9.9", first, cwd=str(work), retry=True)


def test_ls_remote_failure_is_unknown(repo, tmp_path):
    work, _, first, _ = repo
    with pytest.raises(tag.TagError, match="UNKNOWN"):
        tag.ensure_tag("1.2.3", first, cwd=str(work), remote=str(tmp_path / "missing.git"))
    assert _run(work, "tag", "--list") == ""


def test_dry_run_writes_nothing(repo):
    work, bare, first, _ = repo
    out = tag.ensure_tag("2.0.0", first, cwd=str(work), dry_run=True)
    assert out.startswith("DRY RUN")
    assert _run(work, "tag", "--list") == ""
    assert _run(bare, "tag", "--list") == ""


def test_main_exit_codes(repo, monkeypatch, capsys):
    work, _, first, second = repo
    monkeypatch.chdir(work)
    assert tag.main(["--version", "3.0.0", "--sha", first, "--dry-run"]) == 0
    assert tag.main(["--version", "3.0.0", "--sha", first]) == 0
    assert tag.main(["--version", "3.0.0", "--sha", second]) == 1
    assert "two commits" in capsys.readouterr().err

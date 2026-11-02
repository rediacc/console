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


def test_dry_run_refuses_a_local_tag_on_another_commit_like_the_real_run(repo):
    """A local v<V> elsewhere, absent on the remote: the real run refuses, so --dry-run must not say 'would create'."""
    work, bare, first, second = repo
    _run(work, "tag", "v2.1.0", second)
    for dry in (True, False):
        with pytest.raises(tag.TagError, match=r"Local tag v2\.1\.0 points at"):
            tag.ensure_tag("2.1.0", first, cwd=str(work), dry_run=dry)
    assert _run(bare, "tag", "--list") == ""
    assert tag.ensure_tag("2.1.0", second, cwd=str(work), dry_run=True).startswith("DRY RUN")


def test_main_exit_codes(repo, monkeypatch, capsys):
    work, _, first, second = repo
    monkeypatch.chdir(work)
    assert tag.main(["--version", "3.0.0", "--sha", first, "--dry-run"]) == 0
    assert tag.main(["--version", "3.0.0", "--sha", first]) == 0
    assert tag.main(["--version", "3.0.0", "--sha", second]) == 1
    assert "two commits" in capsys.readouterr().err


def test_create_tag_returns_the_tag_object_oid_and_pushes_nothing(repo):
    work, bare, first, _ = repo
    oid = tag.create_tag("4.0.0", first, cwd=str(work), bot_name="b", bot_email="b@x.invalid")
    assert oid == _run(work, "rev-parse", "refs/tags/v4.0.0")
    assert oid != first, "an annotated tag's object id is not the commit"
    assert _run(work, "cat-file", "-t", oid) == "tag"
    assert _run(bare, "tag", "--list") == ""
    # Idempotent before the push: the same local tag answers the same oid.
    assert tag.create_tag("4.0.0", first, cwd=str(work)) == oid


def test_create_tag_lightweight_oid_is_the_commit(repo):
    work, _, first, _ = repo
    assert tag.create_tag("4.0.1", first, cwd=str(work), lightweight=True) == first


def test_push_tag_pushes_exactly_the_created_object(repo):
    work, bare, first, _ = repo
    oid = tag.create_tag("4.1.0", first, cwd=str(work))
    out = tag.push_tag("4.1.0", oid, cwd=str(work))
    assert out.startswith("Created tag v4.1.0")
    assert _run(bare, "rev-parse", "refs/tags/v4.1.0") == oid
    assert "nothing to push" in tag.push_tag("4.1.0", oid, cwd=str(work))
    # After the push, create_tag reports the remote's object, which a retry pushes as a no-op.
    assert tag.create_tag("4.1.0", first, cwd=str(work)) == oid


def test_push_tag_refuses_an_oid_the_local_tag_is_not(repo):
    work, bare, first, second = repo
    tag.create_tag("4.2.0", first, cwd=str(work))
    with pytest.raises(tag.TagError, match="another object"):
        tag.push_tag("4.2.0", second, cwd=str(work))
    with pytest.raises(tag.TagError, match="another object"):
        tag.push_tag("4.9.9", first, cwd=str(work))
    assert _run(bare, "tag", "--list") == ""


def test_push_tag_refuses_to_move_a_remote_tag(repo):
    work, _, first, second = repo
    tag.ensure_tag("4.3.0", first, cwd=str(work))
    with pytest.raises(tag.TagError, match="move a released tag"):
        tag.push_tag("4.3.0", second, cwd=str(work))


def test_create_tag_refuses_a_remote_tag_on_another_commit(repo):
    work, _, first, second = repo
    tag.ensure_tag("4.4.0", first, cwd=str(work))
    with pytest.raises(tag.TagError, match="two commits"):
        tag.create_tag("4.4.0", second, cwd=str(work))


def test_create_only_prints_the_oid_and_push_oid_pushes_it(repo, monkeypatch, capsys):
    work, bare, first, _ = repo
    monkeypatch.chdir(work)
    assert tag.main(["--version", "5.0.0", "--sha", first, "--create-only"]) == 0
    oid = capsys.readouterr().out.strip()
    assert oid == _run(work, "rev-parse", "refs/tags/v5.0.0")
    assert _run(bare, "tag", "--list") == ""
    assert tag.main(["--version", "5.0.0", "--push-oid", first]) == 1
    assert "another object" in capsys.readouterr().err
    assert tag.main(["--version", "5.0.0", "--push-oid", oid]) == 0
    assert _run(bare, "rev-parse", "refs/tags/v5.0.0") == oid

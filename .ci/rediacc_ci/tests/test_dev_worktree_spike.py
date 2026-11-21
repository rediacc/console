"""`worktree_spike.git()` fills a missing or empty commit identity and keeps a non-empty one (d1a28260.1, d1a28260.2)."""

from __future__ import annotations

import pytest

from rediacc_ci.dev import worktree_spike as spike

IDENT = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")
FILLED = "spike <spike@example.invalid>"


def _isolate(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in IDENT:
        monkeypatch.delenv(key, raising=False)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    spike.must(tmp_path, "init", "-q", str(repo))
    return repo


def _commit_ident(repo):
    spike.must(repo, "commit", "-q", "--allow-empty", "-m", "x")
    return spike.must(repo, "log", "-1", "--format=%an <%ae> / %cn <%ce>")


def test_empty_identity_values_are_filled(monkeypatch, tmp_path):
    """d1a28260.1: a runner exporting an empty name or email no longer reaches git as an empty ident."""
    _isolate(monkeypatch, tmp_path)
    for key in IDENT:
        monkeypatch.setenv(key, "")
    assert _commit_ident(_repo(tmp_path)) == f"{FILLED} / {FILLED}"


def test_non_empty_preset_identity_survives(monkeypatch, tmp_path):
    """d1a28260.2: an identity the environment sets is kept."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Ada")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "ada@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Bob")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bob@example.test")
    assert _commit_ident(_repo(tmp_path)) == "Ada <ada@example.test> / Bob <bob@example.test>"


@pytest.mark.parametrize("empty", ["name", "email"])
def test_partial_preset_fills_only_the_empty_half(monkeypatch, tmp_path, empty):
    """CONTROL for d1a28260.1: the non-empty half of an author survives while its empty sibling is filled."""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "" if empty == "name" else "Ada")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "" if empty == "email" else "ada@example.test")
    author = _commit_ident(_repo(tmp_path)).split(" / ")[0]
    assert author == (
        "spike <ada@example.test>" if empty == "name" else "Ada <spike@example.invalid>"
    )


def test_fixture_commits_with_no_global_git_config(monkeypatch, tmp_path):
    """d1a28260.2: a runner without ~/.gitconfig builds the fixture."""
    _isolate(monkeypatch, tmp_path)
    root = spike.build_fixture(tmp_path, plant=False).root
    assert spike.must(root, "rev-parse", "HEAD")

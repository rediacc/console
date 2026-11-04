"""`pick_resolve.py` on real cherry-pick conflicts in throwaway repositories, with controls where it must stop."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.dev import pick_resolve

SCRIPT = paths.CI_DIR / "rediacc_ci" / "dev" / "pick_resolve.py"
TABLE = "pkg/i18n/locales/hashes.json"
ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _doc(hashes):
    return {"$meta": {"keyCount": len(hashes), "sourceLanguage": "en"}, "hashes": hashes}


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _table(repo, hashes):
    _write(repo, TABLE, json.dumps(_doc(hashes), indent=2, sort_keys=True) + "\n")


def git(repo, *args):
    env = {**os.environ, **ENV}
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False
    )


def commit(repo, message):
    assert git(repo, "add", "-A").returncode == 0
    assert git(repo, "commit", "-q", "-m", message).returncode == 0
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def resolve(repo, *extra):
    env = {**os.environ, **ENV}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def read(repo):
    return json.loads((repo / TABLE).read_text(encoding="utf-8"))


def pick_pending(repo):
    return git(repo, "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD").returncode == 0


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    assert git(root, "init", "-q", "-b", "main").returncode == 0
    _table(root, {"k.a": "1", "k.b": "2", "k.c": "3", "k.d": "4"})
    _write(root, "other.txt", "base\n")
    commit(root, "base")
    return root


def _diverge(root, side_edit, main_edit, side_other=None, main_other=None):
    """A `side` branch commit and a `main` commit, both touching neighbouring table lines. Returns the side sha."""
    assert git(root, "checkout", "-q", "-b", "side").returncode == 0
    _table(root, side_edit)
    if side_other:
        _write(root, "other.txt", side_other)
    sha = commit(root, "side")
    assert git(root, "checkout", "-q", "main").returncode == 0
    _table(root, main_edit)
    if main_other:
        _write(root, "other.txt", main_other)
    commit(root, "main")
    return sha


def test_merges_adjacent_edits_and_finishes(repo):
    side = _diverge(
        repo,
        {"k.a": "1", "k.b": "2", "k.b1": "21", "k.c": "3", "k.d": "4"},
        {"k.a": "1", "k.b": "2", "k.b2": "22", "k.c": "3", "k.d": "4"},
    )
    assert git(repo, "cherry-pick", "-x", side).returncode != 0
    done = resolve(repo)
    assert done.returncode == 0, done.stderr
    assert not pick_pending(repo)
    table = read(repo)
    assert table["hashes"] == {
        "k.a": "1",
        "k.b": "2",
        "k.b1": "21",
        "k.b2": "22",
        "k.c": "3",
        "k.d": "4",
    }
    assert table["$meta"]["keyCount"] == 6
    assert "(cherry picked from commit %s)" % side in git(repo, "log", "-1", "--format=%B").stdout


def test_merges_changed_and_removed_keys(repo):
    side = _diverge(
        repo,
        {"k.a": "1", "k.b": "9", "k.c": "3", "k.d": "4"},
        {"k.a": "1", "k.b": "2", "k.c": "3"},
    )
    assert git(repo, "cherry-pick", side).returncode != 0
    assert resolve(repo).returncode == 0
    assert read(repo)["hashes"] == {"k.a": "1", "k.b": "9", "k.c": "3"}


def test_continues_a_two_commit_sequence(repo):
    assert git(repo, "checkout", "-q", "-b", "side").returncode == 0
    _table(repo, {"k.a": "1", "k.b": "2", "k.b1": "21", "k.c": "3", "k.d": "4"})
    first = commit(repo, "side one")
    _table(repo, {"k.a": "1", "k.b": "2", "k.b1": "21", "k.b3": "23", "k.c": "3", "k.d": "4"})
    second = commit(repo, "side two")
    assert git(repo, "checkout", "-q", "main").returncode == 0
    _table(repo, {"k.a": "1", "k.b": "2", "k.b2": "22", "k.c": "3", "k.d": "4"})
    commit(repo, "main")
    assert git(repo, "cherry-pick", first, second).returncode != 0
    done = resolve(repo)
    assert done.returncode == 0, done.stderr
    assert set(read(repo)["hashes"]) == {"k.a", "k.b", "k.b1", "k.b2", "k.b3", "k.c", "k.d"}
    assert git(repo, "log", "--format=%s", "-3").stdout.split("\n")[:2] == ["side two", "side one"]


def test_stops_when_another_file_conflicts(repo):
    side = _diverge(
        repo,
        {"k.a": "1", "k.b": "2", "k.b1": "21", "k.c": "3", "k.d": "4"},
        {"k.a": "1", "k.b": "2", "k.b2": "22", "k.c": "3", "k.d": "4"},
        side_other="side\n",
        main_other="main\n",
    )
    assert git(repo, "cherry-pick", side).returncode != 0
    done = resolve(repo)
    assert done.returncode == 1
    assert "other.txt" in done.stderr
    assert pick_pending(repo)
    assert "<<<<<<<" in (repo / "other.txt").read_text(encoding="utf-8")


def test_stops_when_one_key_changed_differently(repo):
    side = _diverge(
        repo,
        {"k.a": "1", "k.b": "side", "k.c": "3", "k.d": "4"},
        {"k.a": "1", "k.b": "main", "k.c": "3", "k.d": "4"},
    )
    assert git(repo, "cherry-pick", side).returncode != 0
    done = resolve(repo)
    assert done.returncode == 1
    assert "/hashes/k.b" in done.stderr
    assert pick_pending(repo)


def test_refuses_to_start_a_pick(repo):
    before = git(repo, "rev-parse", "HEAD").stdout
    done = resolve(repo)
    assert done.returncode == 2
    assert git(repo, "rev-parse", "HEAD").stdout == before


def test_merge_table_leaf_conflict_names_the_path():
    with pytest.raises(pick_resolve.StopError, match="/hashes/x"):
        pick_resolve.merge_table(_doc({"x": "0"}), _doc({"x": "1"}), _doc({"x": "2"}))

"""The landing-tree binding in `commit_policy` (agent/plans/PLAN-two-track-merge-dev.md, box LT1).

REAL REPOSITORIES. Each case builds a repository whose main tree (the development tree) is on `1120-1` and whose linked tree `landing` is on `1120-2`, the open PR's branch. The control is the same pair with no record: both trees then see both branches, exactly the reading before the binding existed. A record splits the set so each tree sees its own branch, and the mutant case (the record ignored) proves the split comes from the record.
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import subprocess

import pytest

CP = importlib.import_module("rediacc_hooks.commit_policy")

DEV, PR, THIRD = "1120-1", "1120-2", "1120-3"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(directory, *args) -> str:
    env = {k: v for k, v in os.environ.items() if k not in CP.REPO_ENV}
    env.update(GIT_ENV)
    proc = subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, env=env
    )
    return proc.stdout.decode().strip()


def _today(repo) -> list[str]:
    """The live set as `live_branches(gh=False)` read it before the binding: every non-`main` branch whose upstream is not gone."""
    return [
        b
        for b in CP.local_branches(str(repo))
        if b != "main" and not CP._gone_upstream(str(repo), b)
    ]


@pytest.fixture
def world(tmp_path):
    """`(dev, landing)`: the main tree on DEV and a linked tree on PR, no record yet."""
    dev = tmp_path / "console"
    dev.mkdir()
    _git(dev, "init", "-q", "-b", "main")
    (dev / "f").write_text("x\n", encoding="utf-8")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "branch", DEV)
    _git(dev, "branch", PR)
    _git(dev, "symbolic-ref", "HEAD", "refs/heads/" + DEV)
    landing = tmp_path / "console-landing"
    _git(dev, "worktree", "add", "-q", str(landing), PR)
    return os.path.realpath(dev), os.path.realpath(landing)


def _bind(dev, landing, branch=PR) -> str:
    return CP.write_landing_record(dev, landing, branch)


def _record_file(dev) -> str:
    return os.path.join(CP.common_dir(dev), CP.LANDING_RECORD_NAME)


def test_record_lives_in_the_common_git_dir(world):
    dev, landing = world
    where = _bind(dev, landing)
    assert where == _record_file(dev)
    assert os.path.dirname(where) == os.path.realpath(os.path.join(dev, ".git"))
    assert json.loads(pathlib.Path(where).read_text(encoding="utf-8")) == {
        "path": landing,
        "branch": PR,
    }
    assert CP.landing_record_path(landing) == where


def test_no_record_keeps_todays_reading_exactly(world):
    dev, landing = world
    assert not os.path.exists(_record_file(dev))
    for tree in (dev, landing):
        assert CP.live_branches(tree, gh=False) == _today(tree) == [DEV, PR]
        assert CP.tree_role(tree) == CP.ROLE_DEVELOPMENT
        assert CP.misplaced_branch(tree) == ""
        assert CP.landing_record(tree) is None
        assert CP.landing_record_problem(tree) == ""


def test_each_tree_sees_only_its_own_branch(world):
    dev, landing = world
    _bind(dev, landing)
    assert CP.tree_role(dev) == CP.ROLE_DEVELOPMENT
    assert CP.tree_role(landing) == CP.ROLE_LANDING
    assert CP.live_branches(dev, gh=False) == [DEV]
    assert CP.live_branches(landing, gh=False) == [PR]
    assert CP.misplaced_branch(dev) == ""
    assert CP.misplaced_branch(landing) == ""


def test_a_subdirectory_reads_its_trees_role(world):
    dev, landing = world
    _bind(dev, landing)
    sub = os.path.join(landing, "sub")
    os.mkdir(sub)
    assert CP.tree_role(sub) == CP.ROLE_LANDING
    assert CP.live_branches(sub, gh=False) == [PR]


def test_mutant_ignoring_the_record_turns_the_two_tree_case_red(world, monkeypatch):
    dev, landing = world
    _bind(dev, landing)
    monkeypatch.setattr(CP, "landing_record", lambda _repo: None)
    assert CP.live_branches(dev, gh=False) != [DEV]
    assert CP.live_branches(landing, gh=False) != [PR]


def test_a_third_branch_is_still_counted_in_the_development_tree(world):
    dev, landing = world
    _bind(dev, landing)
    _git(dev, "branch", THIRD)
    assert CP.live_branches(dev, gh=False) == [DEV, THIRD]
    assert CP.live_branches(landing, gh=False) == [PR]


def test_a_gone_record_branch_is_not_live_in_the_landing_tree(world):
    dev, landing = world
    _bind(dev, landing)
    _git(dev, "config", "branch.%s.remote" % PR, ".")
    _git(dev, "config", "branch.%s.merge" % PR, "refs/heads/vanished")
    assert CP._gone_upstream(dev, PR)
    assert CP.live_branches(landing, gh=False) == []
    assert CP.live_branches(dev, gh=False) == [DEV]


def test_pr_branch_in_the_development_tree_is_misplaced(world):
    dev, landing = world
    _bind(dev, landing)
    _git(dev, "symbolic-ref", "HEAD", "refs/heads/" + PR)
    assert CP.misplaced_branch(dev) == PR
    assert CP.misplaced_branch(landing) == ""


def test_other_branch_in_the_landing_tree_is_misplaced(world):
    dev, landing = world
    _bind(dev, landing)
    _git(landing, "symbolic-ref", "HEAD", "refs/heads/" + THIRD)
    assert CP.misplaced_branch(landing) == THIRD
    _git(landing, "update-ref", "--no-deref", "HEAD", _git(landing, "rev-parse", "main"))
    assert CP.misplaced_branch(landing) == ""


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("not json", "{not json"),
        ("a list", "[]"),
        ("a missing key", json.dumps({"path": "/x"})),
        ("an extra key", json.dumps({"path": "/x", "branch": PR, "extra": 1})),
        ("a non-string branch", json.dumps({"path": "/x", "branch": 7})),
        ("a relative path", json.dumps({"path": "console-landing", "branch": PR})),
        ("a branch off the shape", json.dumps({"path": "@LANDING@", "branch": "feature"})),
        ("a missing path", json.dumps({"path": "@LANDING@-gone", "branch": PR})),
        ("an unrelated directory", json.dumps({"path": "@OTHER@", "branch": PR})),
        ("not UTF-8", b"\xff\xfe".decode("latin-1")),
    ],
)
def test_a_defective_record_is_absent_and_reported(world, tmp_path, label, text):
    dev, landing = world
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    body = text.replace("@LANDING@", landing).replace("@OTHER@", os.path.realpath(other))
    encoding = "latin-1" if label == "not UTF-8" else "utf-8"
    with open(_record_file(dev), "w", encoding=encoding) as handle:
        handle.write(body)
    for tree in (dev, landing):
        assert CP.landing_record(tree) is None, label
        assert CP.landing_record_problem(tree), label
        assert CP.live_branches(tree, gh=False) == _today(tree) == [DEV, PR], label
        assert CP.tree_role(tree) == CP.ROLE_DEVELOPMENT, label
        assert CP.misplaced_branch(tree) == "", label


def test_a_removed_landing_tree_unbinds(world):
    dev, landing = world
    _bind(dev, landing)
    _git(dev, "worktree", "remove", "--force", landing)
    assert CP.landing_record(dev) is None
    assert "does not exist" in CP.landing_record_problem(dev)
    assert CP.live_branches(dev, gh=False) == [DEV, PR]


def test_write_refuses_a_bad_branch_or_a_foreign_tree(world, tmp_path):
    dev, landing = world
    with pytest.raises(ValueError, match="MMDD-N"):
        CP.write_landing_record(dev, landing, "feature")
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    with pytest.raises(ValueError, match="not a tree"):
        CP.write_landing_record(dev, str(other), PR)
    assert not os.path.exists(_record_file(dev))


def test_write_stores_the_realpath(world, tmp_path):
    dev, landing = world
    alias = tmp_path / "alias"
    alias.symlink_to(landing)
    _bind(dev, str(alias))
    assert CP.landing_record(dev) == {"path": landing, "branch": PR}
    assert CP.tree_role(str(alias)) == CP.ROLE_LANDING


def test_gh_reading_splits_the_same_way_and_skips_the_other_trees_branch(world, monkeypatch):
    dev, landing = world
    asked: list[str] = []

    def fake_gh(_repo, args):
        asked.append(args[3])
        return []

    monkeypatch.setattr(CP, "_gh_lines", fake_gh)
    assert CP.live_branches(dev, gh=True) == [DEV, PR]
    assert asked == [DEV, PR]
    _bind(dev, landing)
    asked.clear()
    assert CP.live_branches(dev, gh=True) == [DEV]
    assert asked == [DEV]
    asked.clear()
    assert CP.live_branches(landing, gh=True) == [PR]
    assert asked == [PR]


def test_gh_merged_record_branch_leaves_the_landing_tree_empty(world, monkeypatch):
    dev, landing = world
    _bind(dev, landing)
    monkeypatch.setattr(CP, "_gh_lines", lambda _repo, _args: ["MERGED"])
    assert CP.live_branches(landing, gh=True) == []
    assert CP.live_branches(dev, gh=True) == []

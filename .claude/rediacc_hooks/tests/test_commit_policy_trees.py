"""A command typed in either bound tree is placed in its own tree (agent/plans/PLAN-two-track-merge-dev.md, box LT11).

REAL REPOSITORIES. The main checkout `console` (the development tree, on DEV) and its linked tree `console-landing` (on PR), a sibling outside it, with a bare `origin` beside both. With the landing record each tree reads the other as this project's own: a commit, a branch and a push typed in the sibling resolve to the sibling's toplevel from either root, and `foreign_only` never stands a guard down for them. The control is the same pair with no record, where the sibling reads as foreign exactly as before the binding, and the mutant (`is_ours` replaced by `is_inside(path, root)`) proves the placement comes from the bound trees.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess

import pytest

CP = importlib.import_module("rediacc_hooks.commit_policy")
SS = importlib.import_module("rediacc_hooks.shellscan")
HOOKIO = importlib.import_module("rediacc_hooks.hookio")

DEV, PR = "1120-1", "1120-2"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(directory, *args) -> str:
    env = {k: v for k, v in os.environ.items() if k not in CP.REPO_ENV}
    env.update(GIT_ENV)
    proc = subprocess.run(
        ["git", "-C", str(directory), *args], check=True, capture_output=True, env=env
    )
    return proc.stdout.decode().strip()


@pytest.fixture
def world(tmp_path):
    """`(dev, landing)`, realpaths, bound by the record; a test unbinds by deleting it."""
    base = os.path.realpath(tmp_path)
    origin = os.path.join(base, "origin.git")
    subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
    dev = os.path.join(base, "console")
    os.mkdir(dev)
    _git(dev, "init", "-q", "-b", "main")
    with open(os.path.join(dev, "f"), "w", encoding="utf-8") as handle:
        handle.write("x\n")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "remote", "add", "origin", origin)
    _git(dev, "branch", PR)
    _git(dev, "switch", "-q", "-c", DEV)
    landing = os.path.join(base, "console-landing")
    _git(dev, "worktree", "add", "-q", landing, PR)
    CP.write_landing_record(dev, landing, PR)
    return dev, landing


def _unbind(dev):
    os.unlink(CP.landing_record_path(dev))


def _event(cmd, cwd, root):
    payload = json.dumps({"cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd}})
    return HOOKIO.Event(payload, env={"CLAUDE_PROJECT_DIR": root})


def _foreign(cmd, cwd, root):
    return CP.foreign_only(_event(cmd, cwd, root), cmd)


def _placed(cmd, cwd, root, aware=True):
    """`scoped_repo` of the command's one git run: as `foreign_only` places it (`aware`, the bound trees passed), or as a caller still testing `is_inside(answer, root)` does."""
    (run,) = CP.git_runs(cmd)
    trees = CP.bound_trees(root) if aware else None
    return CP.scoped_repo(run, cwd, root, CP.created_dirs(cmd, cwd), cmd, trees=trees)


GH_ORIGIN = "https://github.com/example-owner/example-repo.git"


def _github_origin(dev):
    """Point `origin` at a network repository: a push there is one this checkout's policy reads (`push_elsewhere` is False), so the push arm of `scoped_repo` decides."""
    _git(dev, "remote", "set-url", "origin", GH_ORIGIN)


def test_a_push_to_our_remote_typed_in_the_sibling_resolves_to_it(world):
    dev, landing = world
    _github_origin(dev)
    assert _placed(PUSH, landing, dev) == landing
    assert _placed(PUSH, dev, landing) == dev
    assert not _foreign(PUSH, landing, dev)
    assert not _foreign(PUSH, dev, landing)


def test_an_unaware_caller_keeps_judging_the_push_as_this_checkout(world):
    dev, landing = world
    _github_origin(dev)
    assert _placed(PUSH, landing, dev, aware=False) == ""
    assert _placed(PUSH, dev, landing, aware=False) == ""


def test_control_no_record_a_push_to_our_remote_is_judged_here(world):
    dev, landing = world
    _github_origin(dev)
    _unbind(dev)
    assert _placed(PUSH, landing, dev) == ""
    assert not _foreign(PUSH, landing, dev)


COMMIT = "git commit -q -m x"
BRANCH = "git branch 1120-9"
PUSH = "git push origin HEAD"


# --- bound_trees, is_ours, command_tree ---


def test_bound_trees_from_either_side(world):
    dev, landing = world
    assert CP.bound_trees(dev) == [dev, landing]
    assert CP.bound_trees(landing) == [landing, dev]
    assert CP.is_ours(os.path.join(landing, "x"), dev)
    assert CP.is_ours(os.path.join(dev, "x"), landing)


def test_bound_trees_with_no_record_is_the_root_alone(world):
    dev, landing = world
    _unbind(dev)
    assert CP.bound_trees(dev) == [dev]
    assert CP.bound_trees(landing) == [landing]
    assert not CP.is_ours(landing, dev)
    assert not CP.is_ours(dev, landing)


def test_a_third_tree_binds_nothing(world, tmp_path):
    dev, _landing = world
    third = os.path.join(os.path.realpath(tmp_path), "third")
    _git(dev, "worktree", "add", "-q", "--detach", third)
    assert CP.bound_trees(third) == [third]
    assert not CP.is_ours(dev, third)


def test_command_tree_reads_the_cwds_bound_tree(world):
    dev, landing = world
    sub = os.path.join(landing, "deep")
    os.mkdir(sub)
    assert CP.command_tree(dev, landing) == landing
    assert CP.command_tree(dev, sub) == landing
    assert CP.command_tree(landing, dev) == dev
    assert CP.command_tree(dev, dev) == dev
    assert CP.command_tree(dev, "/") == dev
    _unbind(dev)
    assert CP.command_tree(dev, landing) == dev


def test_owning_tree_is_registration(world, tmp_path):
    dev, landing = world
    trees = CP.bound_trees(dev)
    assert CP.owning_tree(landing, trees) == landing
    assert CP.owning_tree(dev, trees) == dev
    assert CP.owning_tree(str(tmp_path), trees) is None


# --- placement: a commit, a branch and a push typed in the sibling tree ---


@pytest.mark.parametrize("cmd", [COMMIT, BRANCH, PUSH])
def test_typed_in_the_landing_tree_from_the_main_checkout(world, cmd):
    dev, landing = world
    assert _placed(cmd, landing, dev) == landing
    assert not _foreign(cmd, landing, dev)


@pytest.mark.parametrize("cmd", [COMMIT, BRANCH, PUSH])
def test_typed_in_the_main_checkout_from_the_landing_tree(world, cmd):
    dev, landing = world
    assert _placed(cmd, dev, landing) == dev
    assert not _foreign(cmd, dev, landing)


@pytest.mark.parametrize("cmd", [COMMIT, BRANCH, PUSH])
def test_dash_c_into_the_sibling(world, cmd):
    dev, landing = world
    spelled = cmd.replace("git ", "git -C %s " % landing, 1)
    assert not _foreign(spelled, dev, dev)
    spelled = cmd.replace("git ", "git -C %s " % dev, 1)
    assert not _foreign(spelled, landing, landing)


def test_branch_creation_lands_in_the_sibling(world):
    dev, landing = world
    (made,) = CP.branch_creations(BRANCH, dev, landing)
    assert (made.repo_root, made.name) == (landing, "1120-9")


@pytest.mark.parametrize("cmd", [COMMIT, BRANCH, PUSH])
def test_control_no_record_reads_the_sibling_as_foreign(world, cmd):
    dev, landing = world
    _unbind(dev)
    assert _foreign(cmd, landing, dev)
    assert _foreign(cmd, dev, landing)


def test_control_a_scratch_repository_stays_foreign(world, tmp_path):
    dev, landing = world
    scratch = os.path.join(os.path.realpath(tmp_path), "scratch")
    os.mkdir(scratch)
    _git(scratch, "init", "-q", "-b", "main")
    assert _foreign(COMMIT, scratch, dev)
    assert _foreign(COMMIT, scratch, landing)


def test_mutant_using_is_inside_turns_the_two_tree_case_red(world, monkeypatch):
    dev, landing = world
    monkeypatch.setattr(CP, "is_ours", lambda path, root, _trees=None: CP.is_inside(path, root))
    assert _foreign(COMMIT, landing, dev)
    assert _foreign(PUSH, dev, landing)
    _github_origin(dev)
    assert _placed(PUSH, landing, dev) == ""


# --- shellscan.target_root ---


def test_target_root_names_the_sibling_from_either_root(world):
    dev, landing = world
    assert SS.target_root("cd %s && %s" % (landing, COMMIT), dev, verb="commit") == landing
    assert SS.target_root("cd %s && %s" % (dev, COMMIT), landing, verb="commit") == dev
    assert SS.target_root(COMMIT, dev, verb="commit") == ""


def test_target_root_a_directory_made_in_the_sibling_is_the_sibling(world):
    dev, landing = world
    made = os.path.join(landing, "newdir")
    cmd = "mkdir %s && cd %s && %s" % (made, made, COMMIT)
    assert SS.target_root(cmd, dev, verb="commit") == landing
    missing = os.path.join(landing, "missing")
    assert SS.target_root("cd %s; %s" % (missing, COMMIT), dev, verb="commit") == ""


def test_target_root_control_no_record_reads_a_made_directory_as_foreign(world):
    dev, landing = world
    _unbind(dev)
    made = os.path.join(landing, "newdir")
    cmd = "mkdir %s && cd %s && %s" % (made, made, COMMIT)
    assert SS.target_root(cmd, dev, verb="commit") == made


# --- the record itself (review findings fab1b63d.1 and fab1b63d.2) ---


def test_a_record_naming_the_main_checkout_binds_nothing(world):
    dev, _landing = world
    with open(CP.landing_record_path(dev), "w", encoding="utf-8") as handle:
        json.dump({"path": dev, "branch": PR}, handle)
    assert CP.landing_record(dev) is None
    assert "linked tree" in CP.landing_record_problem(dev)
    assert CP.tree_role(dev) == CP.ROLE_DEVELOPMENT
    assert DEV in CP.live_branches(dev, gh=False)
    with pytest.raises(ValueError, match="linked tree"):
        CP.write_landing_record(dev, dev, PR)


def test_a_record_naming_a_subdirectory_binds_nothing(world):
    dev, landing = world
    sub = os.path.join(landing, "deep")
    os.mkdir(sub)
    with pytest.raises(ValueError, match="linked tree"):
        CP.write_landing_record(dev, sub, PR)


def test_a_failed_write_leaves_no_temporary_file(world, monkeypatch):
    dev, landing = world

    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(CP.json, "dump", broken)
    with pytest.raises(OSError, match="disk full"):
        CP.write_landing_record(dev, landing, PR)
    common = CP.common_dir(dev)
    assert [n for n in os.listdir(common) if n.endswith(".tmp")] == []

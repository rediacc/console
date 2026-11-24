"""A push typed in a repository that sits inside the landing tree is that repository's push, never this checkout's (box LT11).

`scoped_repo` answers the sibling bound tree's repository only for a caller that passes `trees=bound_trees(root)`; without it the push resolves to this checkout and is judged against this checkout's receipt and branch. Each caller below is driven on a real nested repository inside a real landing tree, with the bound trees planted back to the session root as the red-once mutant and a push in the root itself as the silent control.
"""

from __future__ import annotations

import ast
import importlib
import os
import pathlib
import subprocess

import pytest

CP = importlib.import_module("rediacc_hooks.commit_policy")
VM = importlib.import_module("rediacc_hooks.guards.block_vm_unverified_push")
RENET = importlib.import_module("rediacc_hooks.guards.block_renet_untested_push")
BACKUP = importlib.import_module("rediacc_hooks.guards.block_backup_unverified_push")

GUARDS = pathlib.Path(__file__).resolve().parents[1] / "guards"
DEV, PR = "1121-1", "1121-2"
ORIGIN = "https://github.com/rediacc/console.git"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(directory, *args):
    env = {k: v for k, v in os.environ.items() if k not in CP.REPO_ENV}
    env.update(GIT_ENV)
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def world(tmp_path):
    """(dev root, landing tree, nested repository in the landing tree), the landing record written."""
    dev = tmp_path / "console"
    dev.mkdir()
    _git(dev, "init", "-q", "-b", "main")
    (dev / "f").write_text("x\n", encoding="utf-8")
    _git(dev, "add", "f")
    _git(dev, "commit", "-q", "-m", "init")
    _git(dev, "remote", "add", "origin", ORIGIN)
    _git(dev, "branch", DEV)
    _git(dev, "branch", PR)
    _git(dev, "symbolic-ref", "HEAD", "refs/heads/" + DEV)
    landing = tmp_path / "console-landing"
    _git(dev, "worktree", "add", "-q", str(landing), PR)
    dev_real, landing_real = os.path.realpath(dev), os.path.realpath(landing)
    CP.write_landing_record(dev_real, landing_real, PR)
    nested = pathlib.Path(landing_real) / "private" / "sm"
    nested.mkdir(parents=True)
    _git(nested, "init", "-q", "-b", "main")
    # The same GitHub origin as this checkout's: a push to it is one this checkout's policy reads, so the scope answer is what separates the trees.
    _git(nested, "remote", "add", "origin", ORIGIN)
    return dev_real, landing_real, str(nested)


def _first_run(cmd):
    return CP.git_runs(cmd, "push")[0]


def _vm_tree(root, cmd):
    return VM._push_tree(_first_run(cmd), root, root, CP.created_dirs(cmd, root), cmd)


def _creation(root, cmd):
    return CP._creation_repo(_first_run(cmd), root, root, frozenset(), cmd)


def _plant_session_root_only(monkeypatch):
    monkeypatch.setattr(CP, "bound_trees", lambda root: [root] if root else [])


def test_vm_judges_a_landing_submodule_push_by_neither_tree(world):
    root, _landing, nested = world
    assert _vm_tree(root, "git -C %s push origin main" % nested) == ""


def test_vm_planted_session_root_only_judges_it_as_this_checkout(world, monkeypatch):
    root, _landing, nested = world
    _plant_session_root_only(monkeypatch)
    assert _vm_tree(root, "git -C %s push origin main" % nested) == root


def test_vm_control_a_push_in_the_root_is_judged_there(world):
    root, _landing, _nested = world
    assert _vm_tree(root, "git push origin x") == root


def _judged(guard, cmd, root):
    out = guard._pushes(cmd, root, root)
    return out if isinstance(out, list) else [row for rows in out.values() for row in rows]


@pytest.mark.parametrize("guard", [BACKUP, RENET], ids=["backup", "renet"])
def test_receipt_guards_skip_a_landing_submodule_push(world, guard, monkeypatch):
    root, _landing, nested = world
    cmd = "git -C %s push origin x" % nested
    assert _judged(guard, cmd, root) == []
    _plant_session_root_only(monkeypatch)
    assert _judged(guard, cmd, root) != []


@pytest.mark.parametrize("guard", [BACKUP, RENET], ids=["backup", "renet"])
def test_receipt_guards_control_a_root_push_is_judged(world, guard):
    root, _landing, _nested = world
    assert _judged(guard, "git push origin x", root) != []


def test_creation_repo_answers_the_landing_submodule_itself(world, monkeypatch):
    root, _landing, nested = world
    cmd = "git -C %s push origin %s" % (nested, DEV)
    assert os.path.realpath(_creation(root, cmd)) == os.path.realpath(nested)
    _plant_session_root_only(monkeypatch)
    assert os.path.realpath(_creation(root, cmd)) == os.path.realpath(root)


@pytest.mark.parametrize(
    "name",
    ["block_vm_unverified_push", "block_renet_untested_push", "block_backup_unverified_push"],
)
def test_every_scoped_repo_call_passes_the_bound_trees(name):
    tree = ast.parse((GUARDS / (name + ".py")).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "scoped_repo"
    ]
    assert calls
    assert all(any(k.arg == "trees" for k in c.keywords) for c in calls)

"""The git-level one-branch rule with two trees (box LT3 of agent/plans/PLAN-two-track-merge-dev.md): `githooks.reference_transaction`.

A fixture main checkout holds its landing tree, a real linked tree at the fixed sibling `<main>-landing`, and the landing record binds that tree to the PR branch (`commit_policy.write_landing_record`, the writer the landing verb calls). Branches are cut through real git with `core.hooksPath` on this checkout's hooks, so the refusal is the one git itself runs.

THE CONTROLS. The same two trees with no record answer as the rule did before the binding: the development cut is refused beside the PR branch. The record's own branch cut in the development tree is refused by the new arm, and with that arm planted out (in process, the module's source with its test replaced) the same creation is admitted.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
STRIP = ("COMMIT_POLICY_OK", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
PR, DEV, THIRD = "0101-1", "0101-2", "0101-3"
ARM = 'if bound is not None and name == bound["branch"]:'


def _load(name: str, path: pathlib.Path, plant: tuple[str, str] | None = None):
    source = path.read_text(encoding="utf-8")
    if plant is not None:
        assert plant[0] in source, "the plant no longer applies"
        source = source.replace(*plant)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


GH = _load("githooks_landing_under_test", HOOKS / "githooks.py")


def _git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key in STRIP:
        monkeypatch.delenv(key, raising=False)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def _trees(tmp_path, record=True, detached=False, dev=False):
    """(main checkout, landing tree): the PR branch in the landing tree, or the landing tree detached with the PR branch nowhere (`detached`)."""
    main = (tmp_path / "console").resolve()
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    _git(main, "commit", "-q", "--no-gpg-sign", "--allow-empty", "-m", "seed")
    landing = pathlib.Path(str(main) + "-landing")
    if detached:
        _git(main, "worktree", "add", "-q", "--detach", str(landing))
    else:
        _git(main, "branch", PR)
        _git(main, "worktree", "add", "-q", str(landing), PR)
    if record:
        GH.cp.write_landing_record(str(main), str(landing), PR)
    if dev:
        _git(main, "switch", "-q", "-c", DEV)
    _git(main, "config", "core.hooksPath", str(HOOKS))
    return main, landing


def _cut(repo, *args):
    """(refused by the commit-policy hook, stderr) for a branch cut in `repo`."""
    proc = _git(repo, *args, check=False)
    return proc.returncode != 0 and "commit-policy:" in proc.stderr, proc.stderr


def test_development_branch_cut_beside_the_landing_tree(tmp_path):
    main, _ = _trees(tmp_path)
    refused, err = _cut(main, "switch", "-q", "-c", DEV)
    assert not refused, err


def test_control_no_record_refuses_the_development_cut(tmp_path):
    main, _ = _trees(tmp_path, record=False)
    refused, err = _cut(main, "switch", "-q", "-c", DEV)
    assert refused, err
    assert "`%s` is live" % PR in err, err


def test_third_branch_beside_the_development_branch(tmp_path):
    main, _ = _trees(tmp_path, dev=True)
    _git(main, "switch", "-q", "main")
    refused, err = _cut(main, "branch", THIRD)
    assert refused, err
    assert "`%s` is live" % DEV in err, err


def test_third_branch_in_the_landing_tree(tmp_path):
    _, landing = _trees(tmp_path)
    refused, err = _cut(landing, "branch", DEV)
    assert refused, err
    assert "`%s` is live" % PR in err, err


def test_landing_branch_cut_in_the_development_tree(tmp_path):
    main, _ = _trees(tmp_path, detached=True)
    refused, err = _cut(main, "branch", PR)
    assert refused, err
    assert "landing record binds it" in err, err


def test_control_landing_branch_cut_with_no_record(tmp_path):
    main, _ = _trees(tmp_path, record=False, detached=True)
    refused, err = _cut(main, "branch", PR)
    assert not refused, err


def _created(repo, name):
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return "%s %s refs/heads/%s\n" % (GH.cp.ZERO_OID, sha, name)


@pytest.mark.parametrize(("plant", "want"), [(None, 1), ((ARM, "if False:"), 0)])
def test_the_arm_is_what_refuses(tmp_path, monkeypatch, plant, want):
    main, _ = _trees(tmp_path, detached=True)
    module = _load("githooks_landing_plant_%s" % (plant is not None), HOOKS / "githooks.py", plant)
    monkeypatch.chdir(main)
    assert module.reference_transaction(["prepared"], _created(main, PR)) == want


def test_no_record_reads_as_before(tmp_path, monkeypatch):
    main, _ = _trees(tmp_path, record=False)
    monkeypatch.chdir(main)
    assert GH.cp.landing_record(str(main)) is None
    assert GH.reference_transaction(["prepared"], _created(main, DEV)) == 1

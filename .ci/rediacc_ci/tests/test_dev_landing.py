"""`./run.sh worktree landing` in throwaway repositories (PLAN-two-track-merge-dev LT2).

Each test builds a console with a bare origin and one submodule with its own bare origin, under a temporary directory, so the sibling landing path lands inside it. `gh` and the dependency seed are injected; nothing touches a real checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci.dev import landing, worktree
from rediacc_ci.dev import worktree_spike as spike

SUB = "private/sub"
PR = "0101-1"


def git(cwd, *args):
    return spike.must(cwd, "-c", "protocol.file.allow=always", *args)


def gh_for(*branches):
    rows = json.dumps([{"headRefName": b} for b in branches])
    return lambda _args, _cwd: (0, rows)


class Seeded:
    def __init__(self):
        self.calls = []

    def __call__(self, path, root, tip):
        self.calls.append((pathlib.Path(path), pathlib.Path(root), tip))


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    sub_origin = tmp_path / "sub-origin.git"
    for bare in (origin, sub_origin):
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed-sub"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "f.txt").write_text("sub\n", encoding="utf-8")
    git(seed, "add", "f.txt")
    git(seed, "commit", "-q", "-m", "sub")
    git(seed, "push", "-q", str(sub_origin), "main")

    root = tmp_path / "work" / "console"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", str(origin))
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "console")
    git(root, "submodule", "add", "-q", str(sub_origin), SUB)
    git(root, "commit", "-q", "-m", "add submodule")
    git(root, "push", "-q", "origin", "main")
    git(root, "switch", "-q", "-c", PR)
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    git(root, "add", "b.txt")
    git(root, "commit", "-q", "-m", "on the PR branch")
    git(root, "push", "-q", "origin", PR)
    git(root, "switch", "-q", "main")
    return root


def test_create_makes_tree_on_the_pr_branch(repo):
    seed = Seeded()
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=seed))
    assert path == repo.parent / "console-landing"
    assert spike.out(path, "symbolic-ref", "--short", "HEAD") == PR
    assert (path / "b.txt").is_file()
    assert len(seed.calls) == 1
    assert seed.calls[0][0] == path


def test_submodule_tree_is_on_the_branch_name(repo):
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    sub = path / SUB
    assert spike.out(sub, "symbolic-ref", "--short", "HEAD") == PR
    gitlink = spike.out(repo, "rev-parse", "%s:%s" % (PR, SUB))
    assert spike.out(sub, "rev-parse", "HEAD") == gitlink


def test_record_written(repo):
    path = landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    record = json.loads((repo / ".git" / "rediacc-landing.json").read_text(encoding="utf-8"))
    assert record == {"path": os.path.realpath(path), "branch": PR}


def test_reuse_fast_forwards(repo):
    first = landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    seed = Seeded()
    peer = repo.parent / "peer"
    git(repo.parent, "clone", "-q", "-b", PR, str(repo.parent.parent / "origin.git"), str(peer))
    (peer / "c.txt").write_text("c\n", encoding="utf-8")
    git(peer, "add", "c.txt")
    git(peer, "commit", "-q", "-m", "peer")
    git(peer, "push", "-q", "origin", PR)
    second = landing.make_landing(repo, gh=gh_for(PR), seed=seed)
    assert second == first
    assert (pathlib.Path(first) / "c.txt").is_file()
    assert seed.calls == []


def test_refuses_main(repo):
    with pytest.raises(landing.LandingRefusedError, match="never holds main"):
        landing.make_landing(repo, gh=gh_for("main"), seed=Seeded())
    assert not (repo.parent / "console-landing").exists()


def test_refuses_the_development_branch(repo):
    git(repo, "switch", "-q", "-c", "0202-1")
    with pytest.raises(landing.LandingRefusedError, match="development branch 0202-1"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    assert not (repo.parent / "console-landing").exists()


def test_refuses_the_branch_the_main_checkout_holds(repo):
    git(repo, "switch", "-q", PR)
    with pytest.raises(landing.LandingRefusedError, match="switch the main checkout"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())


def test_refuses_a_second_path(repo):
    other = repo.parent / "elsewhere"
    landing.write_record(repo, other, PR)
    with pytest.raises(landing.LandingRefusedError, match="second path"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())


def test_refuses_a_foreign_directory(repo):
    (repo.parent / "console-landing").mkdir()
    with pytest.raises(landing.LandingRefusedError, match="not a worktree"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())


def test_refuses_a_dirty_tree_on_reuse(repo):
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    (path / "b.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(landing.LandingRefusedError, match="dirty"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())


def test_failed_seed_leaves_nothing(repo):
    def broken(_path, _root, _tip):
        message = "seed broke"
        raise RuntimeError(message)

    with pytest.raises(landing.LandingRefusedError, match="seed broke"):
        landing.make_landing(repo, gh=gh_for(PR), seed=broken)
    assert not (repo.parent / "console-landing").exists()
    assert not (repo / ".git" / "rediacc-landing.json").exists()


def test_help_lists_the_verb(capsys):
    assert worktree.main(["--help"]) == 0
    assert "landing" in capsys.readouterr().out
    assert worktree.main(["landing", "--help"]) == 0
    assert sys.stdout is not None

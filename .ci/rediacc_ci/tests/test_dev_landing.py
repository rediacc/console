"""`./run.sh worktree landing` in throwaway repositories (PLAN-two-track-merge-dev LT2).

Each test builds a console with a bare origin and one submodule with its own bare origin, under a temporary directory, so the sibling landing path lands inside it. `gh` and the dependency seed are injected; nothing touches a real checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

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
    git(repo, "submodule", "update", "-q", "--init")
    git(repo / SUB, "branch", PR)
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    sub = path / SUB
    assert spike.out(sub, "symbolic-ref", "--short", "HEAD") == PR
    gitlink = spike.out(repo, "rev-parse", "%s:%s" % (PR, SUB))
    assert spike.out(sub, "rev-parse", "HEAD") == gitlink


def test_a_submodule_without_the_branch_sits_detached_at_its_gitlink(repo):
    # Creating the PR's branch in a submodule the PR does not touch made a live branch nothing pushes, and the git-level hook refused it (2026-11-21, private/homebrew-tap).
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    sub = path / SUB
    assert spike.out(sub, "symbolic-ref", "-q", "--short", "HEAD") == ""
    gitlink = spike.out(repo, "rev-parse", "%s:%s" % (PR, SUB))
    assert spike.out(sub, "rev-parse", "HEAD") == gitlink
    assert spike.out(repo / ".git" / "modules" / SUB, "branch", "--list", PR) == ""


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


def test_a_development_branch_here_is_the_two_tree_shape(repo):
    # The main checkout on another MMDD-N branch is the shape the switch-over leaves, so a refresh from it must work (it was refused before 2026-11-21).
    git(repo, "switch", "-q", "-c", "0202-1")
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    assert spike.out(path, "symbolic-ref", "--short", "HEAD") == PR
    assert spike.out(repo, "symbolic-ref", "--short", "HEAD") == "0202-1"


def test_first_switch_over_cuts_the_development_branch_stacked(repo):
    git(repo, "switch", "-q", PR)
    sub = repo / SUB
    git(repo, "submodule", "update", "-q", "--init")
    git(sub, "switch", "-q", "-c", PR)
    tip = spike.out(repo, "rev-parse", PR)
    path = pathlib.Path(
        landing.make_landing(
            repo, gh=gh_for(PR), seed=Seeded(), next_name=lambda _r, _t: "0202-1", today="0202"
        )
    )
    assert spike.out(path, "symbolic-ref", "--short", "HEAD") == PR
    assert spike.out(path / SUB, "symbolic-ref", "--short", "HEAD") == PR
    assert spike.out(repo, "symbolic-ref", "--short", "HEAD") == "0202-1"
    assert spike.out(repo, "rev-parse", "HEAD") == tip
    assert spike.out(sub, "symbolic-ref", "--short", "HEAD") == "0202-1"
    record = json.loads((repo / ".git" / "rediacc-landing.json").read_text(encoding="utf-8"))
    assert record["branch"] == PR


def test_failed_switch_over_gives_the_branch_back(repo):
    git(repo, "switch", "-q", PR)

    def broken(_path, _root, _tip):
        message = "seed broke"
        raise RuntimeError(message)

    with pytest.raises(landing.LandingRefusedError, match="seed broke"):
        landing.make_landing(
            repo, gh=gh_for(PR), seed=broken, next_name=lambda _r, _t: "0202-1", today="0202"
        )
    assert spike.out(repo, "symbolic-ref", "--short", "HEAD") == PR
    assert not (repo.parent / "console-landing").exists()


def _failing_switch(monkeypatch, *needles):
    """Make `spike.git` fail a `switch` whose argv holds every needle, and leave other calls alone."""
    real = spike.git

    def fake(cwd, *args):
        if "switch" in args and all(n in args for n in needles):
            return subprocess.CompletedProcess(args, 1, "", "forced failure")
        return real(cwd, *args)

    monkeypatch.setattr(spike, "git", fake)


def test_failed_console_cut_removes_the_landing_tree_and_gives_the_branch_back(repo, monkeypatch):
    git(repo, "switch", "-q", PR)
    _failing_switch(monkeypatch, "-c", "0202-1")
    with pytest.raises(landing.LandingRefusedError, match="could not be cut here"):
        landing.make_landing(
            repo, gh=gh_for(PR), seed=Seeded(), next_name=lambda _r, _t: "0202-1", today="0202"
        )
    monkeypatch.undo()
    assert spike.out(repo, "symbolic-ref", "--short", "HEAD") == PR
    assert not (repo.parent / "console-landing").exists()
    assert not (repo / ".git" / "rediacc-landing.json").exists()


def test_failed_submodule_cut_names_the_recovery_command(repo, monkeypatch):
    git(repo, "switch", "-q", PR)
    git(repo, "submodule", "update", "-q", "--init")
    git(repo / SUB, "switch", "-q", "-c", PR)
    real = spike.git

    def fake(cwd, *args):
        if "switch" in args and "-c" in args and pathlib.Path(cwd) == repo / SUB:
            return subprocess.CompletedProcess(args, 1, "", "forced failure")
        return real(cwd, *args)

    monkeypatch.setattr(spike, "git", fake)
    with pytest.raises(landing.LandingRefusedError, match="switch --no-track -c 0202-1"):
        landing.make_landing(
            repo, gh=gh_for(PR), seed=Seeded(), next_name=lambda _r, _t: "0202-1", today="0202"
        )


def test_failed_detach_gives_back_the_trees_already_detached(repo, monkeypatch):
    git(repo, "switch", "-q", PR)
    git(repo, "submodule", "update", "-q", "--init")
    git(repo / SUB, "switch", "-q", "-c", PR)
    real = spike.must

    def fake(cwd, *args):
        if "--detach" in args and pathlib.Path(cwd) == repo:
            message = "forced failure"
            raise RuntimeError(message)
        return real(cwd, *args)

    monkeypatch.setattr(spike, "must", fake)
    with pytest.raises(landing.LandingRefusedError, match="could not be detached"):
        landing.make_landing(
            repo, gh=gh_for(PR), seed=Seeded(), next_name=lambda _r, _t: "0202-1", today="0202"
        )
    monkeypatch.undo()
    assert spike.out(repo / SUB, "symbolic-ref", "--short", "HEAD") == PR


def test_failed_detach_names_a_tree_that_stayed_detached(repo, monkeypatch):
    """Review f029cf99.1: when the give-back of an already detached submodule tree fails, the refusal names it instead of claiming nothing moved."""
    git(repo, "switch", "-q", PR)
    git(repo, "submodule", "update", "-q", "--init")
    git(repo / SUB, "switch", "-q", "-c", PR)
    real_must, real_git = spike.must, spike.git

    def fake_must(cwd, *args):
        if "--detach" in args and pathlib.Path(cwd) == repo:
            message = "forced failure"
            raise RuntimeError(message)
        return real_must(cwd, *args)

    def fake_git(cwd, *args):
        if (
            "--detach" not in args
            and args[:2] == ("switch", "--quiet")
            and pathlib.Path(cwd) == repo / SUB
        ):
            return subprocess.CompletedProcess(args, 1, "", "cannot switch back")
        return real_git(cwd, *args)

    monkeypatch.setattr(spike, "must", fake_must)
    monkeypatch.setattr(spike, "git", fake_git)
    with pytest.raises(landing.LandingRefusedError, match="stays detached") as caught:
        landing.make_landing(
            repo, gh=gh_for(PR), seed=Seeded(), next_name=lambda _r, _t: "0202-1", today="0202"
        )
    assert str(repo / SUB) in str(caught.value)


@pytest.mark.parametrize("where", ["main", "--detach"])
def test_reuse_on_main_after_the_merge_names_promote(repo, where):
    # The landing tree may sit on main for a hotfix after the merge (PLAN-simple-two-tree-loop ruling 10); with no open PR the refusal names promote, not the missing PR.
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    git(repo, "switch", "-q", "-c", "0202-1")
    git(path, "switch", "-q", *(["--detach", "origin/main"] if where == "--detach" else ["main"]))
    for gh in (gh_for(), gh_for(PR)):
        with pytest.raises(landing.LandingRefusedError, match="worktree landing --promote"):
            landing.make_landing(repo, gh=gh, seed=Seeded())


def test_reuse_control_off_the_pr_branch_names_the_switch(repo):
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    git(path, "switch", "-q", "-c", "0303-1")
    with pytest.raises(landing.LandingRefusedError, match="switch %s" % PR) as raised:
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    assert "--promote" not in str(raised.value)


def test_refuses_a_second_path(repo):
    other = repo.parent / "elsewhere"
    git(repo, "worktree", "add", "-q", "--detach", str(other))
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
    assert capsys.readouterr().out.startswith("Usage: ./run.sh worktree landing")


def test_a_failing_gh_is_named(repo):
    with pytest.raises(landing.LandingRefusedError, match="gh pr list failed"):
        landing.make_landing(repo, gh=lambda _a, _c: (1, ""), seed=Seeded())
    with pytest.raises(landing.LandingRefusedError, match="no JSON"):
        landing.make_landing(repo, gh=lambda _a, _c: (0, "not json"), seed=Seeded())
    assert not (repo.parent / "console-landing").exists()


def test_no_pr_and_the_main_checkout_on_its_branch_names_the_cut(repo):
    git(repo, "switch", "-q", PR)
    with pytest.raises(landing.LandingRefusedError, match="cut or switch to another MMDD-N"):
        landing.make_landing(repo, gh=gh_for(), seed=Seeded())


def test_a_failed_fetch_refuses_a_stale_remote_ref(repo):
    git(repo, "branch", "-D", PR)
    assert spike.out(repo, "rev-parse", "--verify", "-q", "refs/remotes/origin/" + PR)
    git(repo, "remote", "set-url", "origin", str(repo.parent / "no-such-origin.git"))
    with pytest.raises(landing.LandingRefusedError, match="git fetch origin %s failed" % PR):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    assert not (repo.parent / "console-landing").exists()


def test_reuse_refuses_a_missing_submodule_tree(repo):
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    shutil.rmtree(path / SUB)
    # A removed directory reads dirty; an emptied one does not, and the old skip then ran rev-parse and a merge in the superproject's tree.
    (path / SUB).mkdir()
    assert not spike.out(path, "status", "--porcelain", "--ignore-submodules=none")
    with pytest.raises(landing.LandingRefusedError, match="lacks its submodule tree"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())


def test_refuses_a_defective_record(repo):
    (repo / ".git" / "rediacc-landing.json").write_text('{"path": "relative"}\n', encoding="utf-8")
    with pytest.raises(landing.LandingRefusedError, match="binds nothing"):
        landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    assert not (repo.parent / "console-landing").exists()


def test_record_is_the_commit_policy_record(repo):
    path = landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    policy = spike.load_commit_policy()
    assert policy.landing_record(str(repo)) == {"path": os.path.realpath(path), "branch": PR}
    assert policy.tree_role(path) == policy.ROLE_LANDING
    assert policy.tree_role(str(repo)) == policy.ROLE_DEVELOPMENT


DEV = "0101-2"


def _two_tree_submodules(repo):
    """The landing tree made for a submodule that carries the PR's branch, then the development branch cut in the main checkout and its submodule: one module store holding both names."""
    git(repo, "submodule", "update", "-q", "--init")
    git(repo / SUB, "branch", PR)
    path = pathlib.Path(landing.make_landing(repo, gh=gh_for(PR), seed=Seeded()))
    git(repo, "switch", "-q", "-c", DEV)
    git(repo / SUB, "switch", "-q", "-c", DEV)
    heads = spike.out(repo / SUB, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    assert sorted(heads.split()) == sorted(["main", PR, DEV])
    return path


def test_each_submodule_tree_reads_one_live_branch(repo):
    path = _two_tree_submodules(repo)
    policy = spike.load_commit_policy()
    assert policy.live_branches(str(path / SUB), gh=False) == [PR]
    assert policy.live_branches(str(repo / SUB), gh=False) == [DEV]
    assert policy.tree_role(str(path / SUB)) == policy.ROLE_LANDING
    assert policy.misplaced_branch(str(path / SUB)) == ""


def test_submodule_split_mutant_without_the_superproject_turns_red(repo, monkeypatch):
    path = _two_tree_submodules(repo)
    policy = spike.load_commit_policy()

    def own_only(repo_root):
        record = policy.landing_record(repo_root)
        return record, policy._role(repo_root, record)

    monkeypatch.setattr(policy, "tree_binding", own_only)
    assert policy.live_branches(str(path / SUB), gh=False) != [PR]
    assert policy.live_branches(str(repo / SUB), gh=False) != [DEV]


def test_submodule_with_no_record_reads_every_branch(repo):
    path = _two_tree_submodules(repo)
    (repo / ".git" / "rediacc-landing.json").unlink()
    policy = spike.load_commit_policy()
    assert sorted(policy.live_branches(str(path / SUB), gh=False)) == sorted([PR, DEV])
    assert sorted(policy.live_branches(str(repo / SUB), gh=False)) == sorted([PR, DEV])


def test_promote_is_dispatched_and_listed(monkeypatch, capsys):
    seen: list[list[str]] = []

    def promote(args):
        seen.append(args)
        return 7

    monkeypatch.setattr(landing.landing_promote, "cmd_promote", promote)
    assert landing.cmd_landing(["--promote", "x"]) == 7
    assert seen == [["x"]]
    assert worktree.main(["landing", "--help"]) == 0
    out = capsys.readouterr().out
    assert "[--promote]" in out
    assert "worktree landing --promote" in out


def test_status_names_the_landing_tree_and_its_branch(repo, capsys):
    path = landing.make_landing(repo, gh=gh_for(PR), seed=Seeded())
    assert landing.cmd_status(repo) == 0
    assert capsys.readouterr().out == "%s on %s\n" % (os.path.realpath(path), PR)


def test_status_without_a_record(repo, capsys):
    assert landing.cmd_status(repo) == 0
    assert capsys.readouterr().out == "(no landing record)\n"


def test_status_names_a_defective_record(repo, capsys):
    (repo / ".git" / "rediacc-landing.json").write_text("{not json", encoding="utf-8")
    assert landing.cmd_status(repo) == 0
    out = capsys.readouterr().out
    assert out.startswith("(landing record unreadable: ")


def test_status_is_dispatched_by_the_verb(repo, monkeypatch, capsys):
    monkeypatch.setattr(landing.paths, "repo_root", lambda: str(repo))
    assert landing.cmd_landing(["--status"]) == 0
    assert capsys.readouterr().out == "(no landing record)\n"

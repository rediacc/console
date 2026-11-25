"""`./run.sh worktree land <id> --run` in throwaway repositories (PLAN-drain-throughput DT12).

Nothing here touches a real checkout: every repository is built under a tmp directory.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.dev import worktree_land_run as run
from rediacc_ci.dev import worktree_lease as lease

REGION = "<!-- >>> gen-docs: x -->\n%s\n<!-- <<< gen-docs -->\n"
REGEN = "regenerated"
GEN_CMD = (
    sys.executable,
    "-c",
    "import pathlib,re;p=pathlib.Path('doc.md');"
    "p.write_text(re.sub(r'(?s)(gen-docs: x -->\\n).*?(\\n<!-- <<<)', r'\\g<1>%s\\g<2>', p.read_text()))"
    % REGEN,
)


def sh(cwd, *args):
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "main"
    root.mkdir()
    sh(root, "init", "-q", "-b", "live")
    sh(root, "config", "user.email", "t@example.invalid")
    sh(root, "config", "user.name", "t")
    (root / "doc.md").write_text("intro\n" + REGION % "old")
    (root / "code.txt").write_text("a\n")
    sh(root, "add", "--", "doc.md", "code.txt")
    sh(root, "commit", "-q", "-m", "base", "--", "doc.md", "code.txt")
    return root


def lease_commit(root, files, message):
    """One commit on a side branch off live, left there; returns its sha. HEAD returns to live."""
    sh(root, "switch", "-q", "-c", "lease-%d" % len(sh(root, "branch").splitlines()), "live")
    for name, text in files.items():
        (root / name).write_text(text)
    sh(root, "commit", "-q", "-m", message, "--", *files)
    sha = sh(root, "rev-parse", "HEAD")
    sh(root, "switch", "-q", "live")
    return sha


def live_commit(root, files, message):
    for name, text in files.items():
        (root / name).write_text(text)
    sh(root, "commit", "-q", "-m", message, "--", *files)


def plan_for(root, shas, messages=None):
    return run.LandPlan(root, "lease1", [], shas, messages or {})


def test_clean_pick_lands_with_x_line(repo):
    sha = lease_commit(repo, {"code.txt": "b\n"}, "feat: b\n\nPR-TASK: 1")
    lines = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append) == 0
    assert lines == ["step pick %s rc=0" % sha[:12]]
    assert (repo / "code.txt").read_text() == "b\n"
    assert "cherry picked from commit %s" % sha in sh(repo, "log", "-1", "--format=%B")


def test_generated_region_conflict_is_regenerated(repo):
    sha = lease_commit(repo, {"doc.md": "intro\n" + REGION % "from-lease"}, "feat: doc")
    live_commit(repo, {"doc.md": "intro\n" + REGION % "from-head"}, "chore: doc head")
    lines = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 0
    assert (repo / "doc.md").read_text() == "intro\n" + REGION % REGEN
    names = [line.split(" rc=")[0] for line in lines]
    assert "step take-head doc.md" in names
    assert "step gen-docs" in names
    assert not (repo / ".git" / "CHERRY_PICK_HEAD").exists()


def test_real_conflict_stops_and_leaves_pick_in_progress(repo):
    sha = lease_commit(repo, {"doc.md": "lease-intro\n" + REGION % "old"}, "feat: intro")
    live_commit(repo, {"doc.md": "head-intro\n" + REGION % "old"}, "chore: intro head")
    lines = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 1
    assert (repo / ".git" / "CHERRY_PICK_HEAD").exists()
    assert any(line.startswith("stop: conflict in doc.md") for line in lines)
    assert "step pick %s rc=1" % sha[:12] in lines


def test_staged_change_is_refused(repo):
    sha = lease_commit(repo, {"code.txt": "b\n"}, "feat: b")
    (repo / "code.txt").write_text("dirty\n")
    sh(repo, "add", "--", "code.txt")
    lines = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append) == 1
    assert lines[0].startswith("refused: staged changes")


def test_generated_conflict_predicate():
    inner = "x\n" + "<" * 7 + " a\n1\n=======\n2\n" + ">" * 7 + " b\n"
    assert run.confined_to_generated(REGION % inner.rstrip("\n"))
    assert not run.confined_to_generated("<" * 7 + " a\n1\n=======\n2\n" + ">" * 7 + " b\n")
    assert not run.confined_to_generated(REGION % "no hunk")


def test_refused_inside_a_lease(tmp_path, monkeypatch, capsys):
    tree = tmp_path / "lease"
    tree.mkdir()
    (tree / ".git").write_text("gitdir: /nowhere\n")
    monkeypatch.setattr(paths, "repo_root", lambda: tree)
    assert lease.cmd_land(["abc", "--run"]) == 1
    assert capsys.readouterr().out == ""


def test_run_is_named_in_the_usage():
    assert "--run" in lease.LAND_HELP.splitlines()[0]
    assert isinstance(pathlib.Path(run.__file__), pathlib.Path)

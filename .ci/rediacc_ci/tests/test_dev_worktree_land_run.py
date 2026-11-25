"""`./run.sh worktree land <id> --run` in throwaway repositories (PLAN-drain-throughput DT12).

Nothing here touches a real checkout: every repository is built under a tmp directory.
"""

from __future__ import annotations

import os
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
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append) == 0
    assert lines == ["step pick %s rc=0" % sha[:12]]
    assert (repo / "code.txt").read_text() == "b\n"
    assert "cherry picked from commit %s" % sha in sh(repo, "log", "-1", "--format=%B")


def test_generated_region_conflict_is_regenerated(repo):
    sha = lease_commit(repo, {"doc.md": "intro\n" + REGION % "from-lease"}, "feat: doc")
    live_commit(repo, {"doc.md": "intro\n" + REGION % "from-head"}, "chore: doc head")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 0
    assert (repo / "doc.md").read_text() == "intro\n" + REGION % REGEN
    names = [line.split(" rc=")[0] for line in lines]
    assert "step take-head doc.md" in names
    assert "step gen-docs" in names
    assert not (repo / ".git" / "CHERRY_PICK_HEAD").exists()


def test_generated_conflict_keeps_clean_merged_edits_outside_the_region(repo):
    """Review 6f2bf605.1: the lease commit's clean-merged edit outside the region survives the resolve."""
    body = "intro\nmiddle\nmore\n"
    live_commit(repo, {"doc.md": body + REGION % "old"}, "chore: widen")
    sha = lease_commit(
        repo, {"doc.md": body.replace("intro", "INTRO") + REGION % "from-lease"}, "feat: doc"
    )
    live_commit(repo, {"doc.md": body + REGION % "from-head"}, "chore: doc head")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 0
    assert (repo / "doc.md").read_text() == body.replace("intro", "INTRO") + REGION % REGEN
    assert not (repo / ".git" / "CHERRY_PICK_HEAD").exists()


def test_keep_head_hunks_resolves_each_hunk_and_keeps_clean_lines():
    text = "a\n<<<<<<< HEAD\nours\n||||||| base\nold\n=======\ntheirs\n>>>>>>> x\nb\n"
    assert run.keep_head_hunks(text) == "a\nours\nb\n"
    with pytest.raises(ValueError, match="unterminated conflict hunk"):
        run.keep_head_hunks("a\n<<<<<<< HEAD\nours\n")


def test_real_conflict_stops_and_leaves_pick_in_progress(repo):
    sha = lease_commit(repo, {"doc.md": "lease-intro\n" + REGION % "old"}, "feat: intro")
    live_commit(repo, {"doc.md": "head-intro\n" + REGION % "old"}, "chore: intro head")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 1
    assert (repo / ".git" / "CHERRY_PICK_HEAD").exists()
    assert any(line.startswith("stop: conflict in doc.md") for line in lines)
    assert "step pick %s rc=1" % sha[:12] in lines


def test_staged_change_is_refused(repo):
    sha = lease_commit(repo, {"code.txt": "b\n"}, "feat: b")
    (repo / "code.txt").write_text("dirty\n")
    sh(repo, "add", "--", "code.txt")
    lines: list[str] = []
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


# ---- review findings of landed commits (6f2bf605.2 .3 .4, fe5a894d.1) and the two --run gaps ----

FAIL_CMD = (sys.executable, "-c", "import sys; sys.exit(3)")
NOOP_CMD = (sys.executable, "-c", "pass")
LANE = "test-e2e-workers"
REBALANCE_LINE = (
    '"e2e#smoke" runs in no CI job: the lane\'s enumerator lists it and no leg names it. '
    "Place it on the lightest leg: npx tsx scripts/gates/check-lane-budget.ts "
    "--rebalance %s --write" % LANE
)


def test_a_failed_regenerate_names_the_paths_and_leaves_the_pick(repo):
    """6f2bf605.2: after the take-head rewrite, a gen-docs failure is a stop that lists the paths."""
    sha = lease_commit(repo, {"doc.md": "intro\n" + REGION % "from-lease"}, "feat: doc")
    live_commit(repo, {"doc.md": "intro\n" + REGION % "from-head"}, "chore: doc head")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=FAIL_CMD) == 1
    assert "stop: gen-docs failed for doc.md; the cherry-pick is left in progress" in lines
    assert (repo / ".git" / "CHERRY_PICK_HEAD").exists()


def test_control_a_working_regenerate_emits_no_stop(repo):
    sha = lease_commit(repo, {"doc.md": "intro\n" + REGION % "from-lease"}, "feat: doc")
    live_commit(repo, {"doc.md": "intro\n" + REGION % "from-head"}, "chore: doc head")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 0
    assert not [line for line in lines if line.startswith("stop:")]


def test_a_binary_conflict_stops_instead_of_raising(repo):
    """6f2bf605.4: a conflicted file that is not UTF-8 text used to raise out of execute."""
    (repo / "blob.bin").write_bytes(b"\xff\x00base\n")
    sh(repo, "add", "--", "blob.bin")
    sh(repo, "commit", "-q", "-m", "chore: blob", "--", "blob.bin")
    sh(repo, "switch", "-q", "-c", "lease-bin", "live")
    (repo / "blob.bin").write_bytes(b"\xff\x00lease\n")
    sh(repo, "commit", "-q", "-m", "feat: blob", "--", "blob.bin")
    sha = sh(repo, "rev-parse", "HEAD")
    sh(repo, "switch", "-q", "live")
    (repo / "blob.bin").write_bytes(b"\xff\x00head\n")
    sh(repo, "commit", "-q", "-m", "chore: blob head", "--", "blob.bin")
    lines: list[str] = []
    assert run.execute(plan_for(repo, [sha]), emit=lines.append, gen_cmd=GEN_CMD) == 1
    assert any(line.startswith("stop: conflict in blob.bin") for line in lines), lines
    assert (repo / ".git" / "CHERRY_PICK_HEAD").exists()


def test_crlf_line_endings_survive_the_generated_resolve(repo):
    """fe5a894d.1: a CRLF file keeps its endings, outside the region and inside."""
    region = REGION.replace("\n", "\r\n")
    body = "intro\r\nmiddle\r\n"
    live_commit(repo, {"doc.md": body + region % "old"}, "chore: crlf")
    sha = lease_commit(
        repo, {"doc.md": body.replace("intro", "INTRO") + region % "from-lease"}, "feat: doc"
    )
    live_commit(repo, {"doc.md": body + region % "from-head"}, "chore: doc head")
    assert run.execute(plan_for(repo, [sha]), emit=lambda _l: None, gen_cmd=NOOP_CMD) == 0
    assert (repo / "doc.md").read_bytes() == (
        body.replace("intro", "INTRO") + region % "from-head"
    ).encode()


def test_control_lf_files_resolve_unchanged(repo):
    sha = lease_commit(repo, {"doc.md": "INTRO\n" + REGION % "from-lease"}, "feat: doc")
    live_commit(repo, {"doc.md": "intro\n" + REGION % "from-head"}, "chore: doc head")
    assert run.execute(plan_for(repo, [sha]), emit=lambda _l: None, gen_cmd=NOOP_CMD) == 0
    assert (repo / "doc.md").read_bytes() == ("INTRO\n" + REGION % "from-head").encode()


# ---- --run marks the review findings a landed commit fixes ----


def fake_worklist(root):
    """A worklist.py that records its argv, so the call is read without the real store."""
    script = root / ".claude" / "hooks" / "stop" / "worklist.py"
    script.parent.mkdir(parents=True)
    log = root / "marks.log"
    script.write_text(
        "import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n" % str(log),
        encoding="utf-8",
    )
    return log


def test_run_marks_each_fixes_review_trailer_with_the_landed_sha(repo):
    log = fake_worklist(repo)
    sha = lease_commit(
        repo,
        {"code.txt": "b\n"},
        "fix: b\n\nFixes-Review: abc12345.1\nFixes-Review: abc12345.2\nPR-TASK: 1",
    )
    lines: list[str] = []
    plan = plan_for(repo, [sha], {sha: sh(repo, "log", "-1", "--format=%B", sha)})
    assert run.execute(plan, emit=lines.append, me="d778") == 0
    landed = sh(repo, "rev-parse", "HEAD")
    assert landed != sha
    assert log.read_text().splitlines() == [
        "--review-mark d778 abc12345.1 fixed %s" % landed,
        "--review-mark d778 abc12345.2 fixed %s" % landed,
    ]
    assert "step review-mark abc12345.1 %s rc=0" % landed[:12] in lines
    assert "step review-mark abc12345.2 %s rc=0" % landed[:12] in lines


def test_control_run_marks_nothing_without_me_or_without_a_trailer(repo):
    log = fake_worklist(repo)
    first = lease_commit(repo, {"code.txt": "b\n"}, "fix: b\n\nFixes-Review: abc12345.1")
    plan = plan_for(repo, [first], {first: sh(repo, "log", "-1", "--format=%B", first)})
    assert run.execute(plan, emit=lambda _l: None) == 0
    second = lease_commit(repo, {"code.txt": "c\n"}, "fix: c")
    plan = plan_for(repo, [second], {second: "fix: c"})
    lines: list[str] = []
    assert run.execute(plan, emit=lines.append, me="d778") == 0
    assert not log.exists()
    assert not [line for line in lines if "review-mark" in line]


def test_a_failed_review_mark_is_a_failed_step(repo):
    script = repo / ".claude" / "hooks" / "stop" / "worklist.py"
    script.parent.mkdir(parents=True)
    script.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    sha = lease_commit(repo, {"code.txt": "b\n"}, "fix: b\n\nFixes-Review: abc12345.1")
    lines: list[str] = []
    plan = plan_for(repo, [sha], {sha: sh(repo, "log", "-1", "--format=%B", sha)})
    assert run.execute(plan, emit=lines.append, me="d778") == 1
    assert any(line.startswith("step review-mark abc12345.1") and "rc=2" in line for line in lines)


# ---- after_picks: a lane `--run` cannot place, and a gate that stays red ----


def gate_script(tmp_path, text, *, red_runs):
    """A coverage gate that prints `text` and exits 1 for its first `red_runs` runs, then 0."""
    counter = tmp_path / "gate-runs"
    script = tmp_path / "gate.py"
    script.write_text(
        "import pathlib, sys\n"
        "c = pathlib.Path(%r)\n"
        "n = int(c.read_text()) if c.exists() else 0\n"
        "c.write_text(str(n + 1))\n"
        "if n < %d:\n"
        "    print(%r)\n"
        "    sys.exit(1)\n" % (str(counter), red_runs, text),
        encoding="utf-8",
    )
    return (sys.executable, str(script))


@pytest.fixture
def fake_npm(tmp_path, monkeypatch):
    """`npm run shard:place` succeeds without placing anything."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    npm.chmod(0o755)
    monkeypatch.setenv("PATH", "%s:%s" % (bin_dir, os.environ["PATH"]))


def test_a_bucketed_lane_is_a_named_stop_for_the_lead(tmp_path):
    lines: list[str] = []
    gate = gate_script(tmp_path, REBALANCE_LINE, red_runs=9)
    assert run.after_picks(tmp_path, "", emit=lines.append, shard_check=gate) == 1
    assert "step shard-coverage rc=1 lane %s is not placed by --run" % LANE in lines
    assert "stop: coverage gate line for the lead: %s" % REBALANCE_LINE in lines
    assert not [line for line in lines if "names no lane" in line]


@pytest.mark.usefixtures("fake_npm")
def test_control_a_placeable_lane_is_placed_and_the_gate_rechecked(tmp_path):
    hint = "x runs in no CI job. Place it on the lightest leg: npm run shard:place -- unit-lane"
    lines: list[str] = []
    gate = gate_script(tmp_path, hint, red_runs=1)
    assert run.after_picks(tmp_path, "", emit=lines.append, shard_check=gate) == 0
    assert "step shard:place unit-lane rc=0" in lines
    assert "step shard-coverage recheck rc=0" in lines
    assert not [line for line in lines if line.startswith("stop:")]


@pytest.mark.usefixtures("fake_npm")
def test_a_gate_still_red_after_placing_is_reported_red(tmp_path):
    """6f2bf605.3: shard:place succeeding does not clear a gate that fails on the next run."""
    hint = "x runs in no CI job. Place it on the lightest leg: npm run shard:place -- unit-lane"
    lines: list[str] = []
    gate = gate_script(tmp_path, hint, red_runs=9)
    assert run.after_picks(tmp_path, "", emit=lines.append, shard_check=gate) == 1
    assert any(
        line.startswith("step shard-coverage recheck rc=1") and "still red" in line
        for line in lines
    )

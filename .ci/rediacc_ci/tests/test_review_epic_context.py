"""Differential: `rediacc_ci.review.epic_context` against its twin
`.ci/scripts/review/epic-context.sh`.

A disposable local git repo (never GitHub -- `git log`/`git show` need no remote), on the `test_version_resolve_version.py` strategy: real commits, a real `origin/main` ref built as a plain local branch (nothing here needs an actual remote, only something `git rev-parse --verify` resolves), and a worklist snapshot file the twin reads by convention
(`agent/pr/<branch-with-slashes-as-dashes>.md`).

THE DUPLICATE-HEADING CASE (`test_two_items_under_one_heading_duplicates_it`) is the one worth explaining before it looks like a bug in the port: a heading
with two worklist items that both carry the epic's trailer prints TWICE in the
twin, once staged immediately before each trailer line. Confirmed against real `awk` while writing the port (see that module's docstring); the differential exists to keep it that way on purpose, not to quietly "fix" it into printing once.

K=5 LEDGER: `.ci/shadow/w7p6-epic-context.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.review import epic_context

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "review" / "epic-context.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "epic_context.py"


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "agent" / "pr").mkdir(parents=True)
    (repo / "agent" / "PLAN-example.md").write_text(
        "# PLAN: example\n\nline 2\nline 3\n", encoding="utf-8"
    )
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    # A local "origin/main" the twin's `git rev-parse --verify` can resolve without a real remote: a plain branch ref of that exact name works because `git rev-parse` does not care whether it looks like a remote.
    _git(repo, "branch", "origin/main")
    return repo


def _snapshot(repo: pathlib.Path, branch: str, text: str) -> None:
    slug = branch.replace("/", "-")
    (repo / "agent" / "pr" / f"{slug}.md").write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "snapshot")


def _run(subject: pathlib.Path, repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    return subprocess.run(
        [*runner, str(subject), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def run_both(repo: pathlib.Path, *args: str):
    old = _run(TWIN, repo, *args)
    new = _run(PORT, repo, *args)
    return old, new


def test_no_snapshot_is_a_named_error(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "0906-1")
    old, new = run_both(repo, "e1", "0906-1")
    assert old.returncode == 1
    assert "no snapshot at agent/pr/0906-1.md" in old.stderr
    assert new.returncode == old.returncode
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


def test_no_arguments_is_usage(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new = run_both(repo)
    assert old.returncode == 2
    assert new.returncode == 2
    assert new.stderr == old.stderr


def test_simple_epic_with_plan_reference_and_commit(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/x")
    snap = (
        "# Work in feature/x\n\n"
        "### Epic Alpha\n"
        "- item1 evidence\n"
        "  PR-TASK: e1\n"
        "  body line, see agent/PLAN-example.md\n"
    )
    _snapshot(repo, "feature/x", snap)
    (repo / "g.txt").write_text("change\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: something\n\nPR-TASK: e1")

    old, new = run_both(repo, "e1", "feature/x")
    assert old.returncode == 0
    assert "EPIC e1   (branch feature/x)" in old.stdout
    assert "### Epic Alpha" in old.stdout
    assert "agent/PLAN-example.md (first 40 lines)" in old.stdout
    assert "files touched:" in old.stdout
    assert "g.txt" in old.stdout
    assert new.returncode == old.returncode
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


def test_referenced_plan_missing_from_checkout(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/y")
    snap = "### Epic Beta\n  PR-TASK: e2\n  see agent/PLAN-ghost.md\n"
    _snapshot(repo, "feature/y", snap)
    old, new = run_both(repo, "e2", "feature/y")
    assert "referenced but NOT in this checkout" in old.stdout
    assert new.stdout == old.stdout


def test_no_matching_commits_is_named(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/z")
    snap = "### Epic Gamma\n- nothing yet\n  PR-TASK: e3\n"
    _snapshot(repo, "feature/z", snap)
    old, new = run_both(repo, "e3", "feature/z")
    assert "NO COMMITS carry this trailer" in old.stdout
    assert new.stdout == old.stdout


def test_two_items_under_one_heading_duplicates_it(tmp_path: pathlib.Path) -> None:
    """THE QUIRK, driven for real: two trailer-matching lines under one heading
    print that heading twice. If the port ever "cleaned this up" to print once,
    this is the case that catches it."""
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/dup")
    snap = (
        "### Epic Alpha\n"
        "- item1 evidence\n"
        "  PR-TASK: e1\n"
        "  body line 1a\n"
        "- item2 evidence\n"
        "  PR-TASK: e1\n"
        "  body line 2a\n"
        "### Epic Beta\n"
        "- item3\n"
        "  PR-TASK: e2\n"
    )
    _snapshot(repo, "feature/dup", snap)
    old, new = run_both(repo, "e1", "feature/dup")
    assert old.stdout.count("### Epic Alpha") == 2, "the twin's own quirk did not fire: %r" % (
        old.stdout,
    )
    assert new.stdout == old.stdout


def test_base_ref_unresolvable_is_named(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "branch", "-D", "origin/main")
    _git(repo, "checkout", "-q", "-b", "feature/w")
    snap = "### Epic Delta\n  PR-TASK: e4\n"
    _snapshot(repo, "feature/w", snap)
    old, new = run_both(repo, "e4", "feature/w")
    assert "is not resolvable in this checkout; commit list skipped" in old.stdout
    assert new.stdout == old.stdout


def test_current_branch_is_used_when_omitted(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/omitted")
    snap = "### Epic E\n  PR-TASK: e5\n"
    _snapshot(repo, "feature/omitted", snap)
    old, new = run_both(repo, "e5")
    assert "branch feature/omitted" in old.stdout
    assert new.stdout == old.stdout


def test_pure_helpers_match_the_real_awk_directly() -> None:
    """Exercise the exported helpers without shelling out, on the fixture that
    forced the analysis in the first place."""
    lines = [
        "### Epic Alpha",
        "- item1 evidence",
        "  PR-TASK: e1",
        "  body line 1a",
        "- item2 evidence",
        "  PR-TASK: e1",
        "  body line 2a",
        "### Epic Beta",
        "- item3",
        "  PR-TASK: e2",
    ]
    section = epic_context._epic_section(lines, "e1")
    assert section.count("### Epic Alpha") == 2
    simple = epic_context._epic_lines(lines, "e1")
    assert simple[0] == "  PR-TASK: e1"
    assert "### Epic Alpha" not in simple

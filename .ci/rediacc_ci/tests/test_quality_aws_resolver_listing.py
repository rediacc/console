"""The aws resolver gate lists a work tree from the git index, not from an rglob."""

from __future__ import annotations

import pathlib
import subprocess

from rediacc_ci.quality import aws_resolver as gate


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _tree(tmp_path: pathlib.Path, git: bool) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (".ci/scripts/tracked.sh", ".ci/scratch/ignored.sh", ".ci/notes.txt"):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n", encoding="utf-8")
    (root / ".gitignore").write_text(".ci/scratch/\n", encoding="utf-8")
    if git:
        _git(root, "init", "-q")
        _git(root, "add", ".gitignore", ".ci/scripts", ".ci/notes.txt")
    return root


def _listed(root: pathlib.Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in gate._files(root, root / ".ci", "*.sh")]


def test_work_tree_lists_tracked_files_only(tmp_path: pathlib.Path) -> None:
    assert _listed(_tree(tmp_path, git=True)) == [".ci/scripts/tracked.sh"], "ignored file is an input"


def test_non_work_tree_still_walks(tmp_path: pathlib.Path) -> None:
    assert _listed(_tree(tmp_path, git=False)) == [
        ".ci/scratch/ignored.sh",
        ".ci/scripts/tracked.sh",
    ]

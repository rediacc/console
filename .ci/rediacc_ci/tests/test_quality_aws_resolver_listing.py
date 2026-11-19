"""The aws resolver gate lists a work tree from the git index, not from an rglob."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from rediacc_ci.quality import aws_resolver as gate

if TYPE_CHECKING:
    import pathlib


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
    assert _listed(_tree(tmp_path, git=True)) == [".ci/scripts/tracked.sh"], (
        "ignored file is an input"
    )


def test_non_work_tree_still_walks(tmp_path: pathlib.Path) -> None:
    assert _listed(_tree(tmp_path, git=False)) == [
        ".ci/scratch/ignored.sh",
        ".ci/scripts/tracked.sh",
    ]


def test_an_untracked_file_is_not_listed_until_it_is_added(tmp_path: pathlib.Path) -> None:
    """Finding 84023613.4: CI lints a fresh checkout, so a new untracked file is not an input until it is added to the index."""
    root = _tree(tmp_path, git=True)
    (root / ".ci/scripts/new.sh").write_text("x\n", encoding="utf-8")
    assert _listed(root) == [".ci/scripts/tracked.sh"]
    _git(root, "add", ".ci/scripts/new.sh")
    assert _listed(root) == [".ci/scripts/new.sh", ".ci/scripts/tracked.sh"]

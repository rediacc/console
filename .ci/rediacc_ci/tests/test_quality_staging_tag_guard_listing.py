"""The staging tag guard lists a work tree from the git index, not from a walk.

A gitignored directory under `.ci` (the cache is the real one) must not be an input: the walk with a hand-restated prune was the only thing standing between the gate and downloaded toolchains.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from rediacc_ci.quality import staging_tag_guard as gate

if TYPE_CHECKING:
    import pathlib

CALL = '#!/bin/bash\n"$D/cleanup-staging.sh" --tag "$CHANNEL"\n'


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _tree(tmp_path: pathlib.Path, git: bool) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (".ci/scripts/release/tracked.sh", ".ci/scratch/ignored.sh"):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(CALL, encoding="utf-8")
    (root / ".gitignore").write_text(".ci/scratch/\n", encoding="utf-8")
    if git:
        _git(root, "init", "-q")
        _git(root, "add", ".gitignore", ".ci/scripts")
    return root


def test_work_tree_lists_tracked_files_only(tmp_path: pathlib.Path) -> None:
    root = _tree(tmp_path, git=True)
    hits, files_read = gate.grep_hits(root)
    files = {h.split(":", 1)[0] for h in hits}
    assert files == {str(root / ".ci/scripts/release/tracked.sh")}, "the ignored file is an input"
    assert files_read == 1


def test_non_work_tree_still_walks(tmp_path: pathlib.Path) -> None:
    """The other direction: with no index the walk reads both, so the listing is what excluded the ignored file above."""
    root = _tree(tmp_path, git=False)
    hits, files_read = gate.grep_hits(root)
    assert files_read == 2
    assert len({h.split(":", 1)[0] for h in hits}) == 2

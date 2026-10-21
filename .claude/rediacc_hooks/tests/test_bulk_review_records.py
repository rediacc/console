"""block_unproven_bulk_transform: which `agent/reviews/` files count toward bulk scale.

wl_review.py writes the records of a submodule's commits into the console's `agent/reviews/<branch>/`, so a record names a commit of the console OR of a submodule. Only a record whose sha is a real commit of one of them is exempt; a fabricated sha, and every ordinary file, still counts.
"""

import os
import subprocess

from rediacc_hooks.guards import block_unproven_bulk_transform as guard


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout.strip()


def _repo(path):
    os.makedirs(path)
    _git(path, "init", "-q", "-b", "main")
    # The content names the repository, so two fixtures made in the same second never share a commit sha.
    with open(os.path.join(path, "a.txt"), "w") as fh:
        fh.write("%s\n" % path)
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD")


def test_a_submodule_commit_record_is_exempt_and_a_fabricated_one_counts(tmp_path):
    console = str(tmp_path / "console")
    console_sha = _repo(console)
    sub_sha = _repo(os.path.join(console, "private", "sub"))
    with open(os.path.join(console, ".gitmodules"), "w") as fh:
        fh.write('[submodule "private/sub"]\n\tpath = private/sub\n\turl = ../sub\n')
    fake = "f" * 40
    files = [
        "agent/reviews/0101-1/%s.md" % console_sha,
        "agent/reviews/0101-1/%s.md" % sub_sha,
        "agent/reviews/0101-1/%s.md" % fake,
        "agent/reviews/0101-1/clean.jsonl",
        "src/real.py",
    ]
    counted = guard._counted(files, console)
    assert counted == ["agent/reviews/0101-1/%s.md" % fake, "src/real.py"], counted


def test_without_gitmodules_a_submodule_sha_still_counts(tmp_path):
    console = str(tmp_path / "console")
    _repo(console)
    sub_sha = _repo(str(tmp_path / "elsewhere"))
    record = "agent/reviews/0101-1/%s.md" % sub_sha
    assert guard._counted([record], console) == [record]


def test_a_gitmodules_path_outside_the_repository_vouches_for_nothing(tmp_path):
    console = str(tmp_path / "console")
    _repo(console)
    outside_sha = _repo(str(tmp_path / "outside"))
    with open(os.path.join(console, ".gitmodules"), "w") as fh:
        fh.write('[submodule "x"]\n\tpath = ../outside\n\turl = ../outside\n')
    record = "agent/reviews/0101-1/%s.md" % outside_sha
    assert guard._counted([record], console) == [record]

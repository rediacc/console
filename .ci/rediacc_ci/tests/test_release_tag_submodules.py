"""Differential: `rediacc_ci.release.tag_submodules` against its twin `.ci/scripts/release/tag-submodules.sh`.

THE SUBJECT PUSHES TAGS, so the first design decision is where. Never at the real `private/renet` remote: every case here builds a throwaway parent directory holding its own `private/renet` git repository whose `origin` is a BARE repository in the same tmpdir, and the remote is added as the RELATIVE path `../renet-remote.git`. Relative on purpose -- `git push` prints `To <remote>`
to stderr, and an absolute path would differ between the two independent fixtures and defeat byte-for-byte comparison for a reason that has nothing to do with the port.

TWO FIXTURES PER CASE, ONE PER SIDE, because this subject MUTATES: the first run creates the tag, so a second run against the same tree would take the reuse arm and the two sides would be compared on different behaviour. The fixtures are built with fixed content and fixed author/committer identity and dates, which makes the commit SHA identical in both -- so even the `(<sha>)`
inside the reuse notice compares byte for byte.

ALL THREE ARMS ARE DRIVEN, not just the happy path, because the arm the twin's own header singles out is the failure one: "Drift is a hard failure, not a silent retag." `test_drift_is_a_hard_failure` asserts the refusal AND that the remote was left untouched, and `test_planted_defect_is_caught` removes that arm
from the port to prove the case can fire.

ONE DOCUMENTED DIVERGENCE: a missing/empty `VERSION` is `${VERSION:?...}` in
the twin, whose bash diagnostic carries a line number. Those two cases assert agreement on exit code, stream and substance; everything else here is byte-for-byte.

K=5 LEDGER: `.ci/shadow/w7p6-tag-submodules.observations.jsonl` -- five
distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded in a disposable scratch repo outside this checkout (dirty tree; `--record` refuses one) through a `drive-tag.sh` fixture builder that makes the same throwaway parent/submodule/bare-remote this file makes, one mode per tree: fresh tag, reuse at HEAD, drift, unborn HEAD, and a missing origin.
No real remote is ever contacted.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import tag_submodules

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "tag-submodules.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "tag_submodules.py"
BASH = shutil.which("bash") or "/bin/bash"

VERSION = "1.2.3"

# Fixed so both fixtures produce the SAME commit SHA. Without this the reuse notice's `(<sha>)` differs between the sides and the comparison has to be weakened to a regex, which would also stop it noticing a port that printed the wrong sha.
FIXED_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
}

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def _git(cwd: pathlib.Path, *args: str, check: bool = True):
    env = dict(os.environ)
    env.update(FIXED_GIT_ENV)
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=check, env=env
    )


def _parent(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    parent = tmp_path / name
    (parent / "private").mkdir(parents=True)
    return parent


def _submodule(parent: pathlib.Path, *, commits: int = 1) -> pathlib.Path:
    """A real git repo at `private/renet` with a bare `../renet-remote.git`."""
    sub = parent / "private" / "renet"
    sub.mkdir()
    _git(parent / "private", "init", "--bare", "-q", "renet-remote.git")
    _git(sub, "init", "-q")
    _git(sub, "config", "user.name", "Fixture")
    _git(sub, "config", "user.email", "fixture@example.com")
    # RELATIVE remote: see this module's docstring on why `To <remote>` must not carry a tmpdir path.
    _git(sub, "remote", "add", "origin", "../renet-remote.git")
    for i in range(commits):
        (sub / "f.txt").write_text("content %d\n" % i, encoding="utf-8")
        _git(sub, "add", "f.txt")
        _git(sub, "commit", "-q", "-m", "commit %d" % i)
    return sub


def _run(subject: pathlib.Path, parent: pathlib.Path, **overrides: str):
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    env = dict(BASE_ENV)
    env.update(overrides)
    return subprocess.run(
        [*runner, str(subject)],
        cwd=parent,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )


def _assert_agree(old, new, label: str) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def _remote_tags(parent: pathlib.Path) -> str:
    return _git(parent / "private" / "renet-remote.git", "tag", "-l").stdout


def test_uninitialized_submodule_is_skipped(tmp_path: pathlib.Path) -> None:
    """No `private/renet/.git` at all: a notice, exit 0, nothing pushed."""
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    old = _run(TWIN, old_parent, VERSION=VERSION)
    new = _run(PORT, new_parent, VERSION=VERSION)
    assert old.returncode == 0
    assert old.stdout == "::notice::Skipping private/renet (not initialized)\n"
    _assert_agree(old, new, "uninitialized")


def test_directory_without_dot_git_is_skipped(tmp_path: pathlib.Path) -> None:
    """The directory exists but is not a checkout -- the case an unrun `git submodule update --init` leaves behind."""
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    for parent in (old_parent, new_parent):
        (parent / "private" / "renet").mkdir()
    old = _run(TWIN, old_parent, VERSION=VERSION)
    new = _run(PORT, new_parent, VERSION=VERSION)
    assert old.returncode == 0
    assert "Skipping private/renet (not initialized)" in old.stdout
    _assert_agree(old, new, "empty-dir")


def test_dot_git_as_a_file_is_initialized(tmp_path: pathlib.Path) -> None:
    """A real submodule checkout has `.git` as a FILE holding a gitdir pointer. A port that tested only `is_dir()` would skip every real submodule and exit 0, which is the silent pass this case exists for."""
    results = []
    for name in ("old", "new"):
        parent = _parent(tmp_path, name)
        sub = _submodule(parent)
        # Convert the checkout to the pointer-file shape git itself uses.
        gitdir = parent / "private" / "renet-gitdir"
        shutil.move(str(sub / ".git"), str(gitdir))
        (sub / ".git").write_text("gitdir: ../renet-gitdir\n", encoding="utf-8")
        _git(sub, "config", "core.worktree", "../renet")
        subject = TWIN if name == "old" else PORT
        results.append((parent, _run(subject, parent, VERSION=VERSION)))
    (old_parent, old), (new_parent, new) = results
    assert old.returncode == 0, f"twin failed on a pointer-file submodule: {old.stderr!r}"
    assert "Skipping" not in old.stdout
    _assert_agree(old, new, "dot-git-file")
    assert _remote_tags(old_parent) == "v1.2.3\n"
    assert _remote_tags(new_parent) == _remote_tags(old_parent)


def test_fresh_tag_is_created_and_pushed(tmp_path: pathlib.Path) -> None:
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    _submodule(old_parent)
    _submodule(new_parent)
    old = _run(TWIN, old_parent, VERSION=VERSION)
    new = _run(PORT, new_parent, VERSION=VERSION)
    assert old.returncode == 0
    assert old.stdout == ""
    assert "[new tag]" in old.stderr, "the twin did not actually push; the case is vacuous"
    _assert_agree(old, new, "fresh-tag")
    assert _remote_tags(old_parent) == "v1.2.3\n"
    assert _remote_tags(new_parent) == _remote_tags(old_parent)


def test_tag_already_at_head_is_reused_and_the_push_is_idempotent(
    tmp_path: pathlib.Path,
) -> None:
    parents = []
    for name in ("old", "new"):
        parent = _parent(tmp_path, name)
        sub = _submodule(parent)
        _git(sub, "tag", "-a", "v" + VERSION, "-m", "v" + VERSION)
        _git(sub, "push", "-q", "origin", "v" + VERSION)
        parents.append(parent)
    old = _run(TWIN, parents[0], VERSION=VERSION)
    new = _run(PORT, parents[1], VERSION=VERSION)
    assert old.returncode == 0
    assert old.stdout.startswith("::notice::Submodule private/renet tag v1.2.3 already at HEAD (")
    assert old.stdout.rstrip("\n").endswith("); reusing")
    assert "Everything up-to-date" in old.stderr
    _assert_agree(old, new, "reuse-at-head")


def test_drift_is_a_hard_failure(tmp_path: pathlib.Path) -> None:
    """THE ARM THE TWIN'S HEADER IS ABOUT. The tag exists but points at an older commit: refusing is the only correct answer, because a release that retagged here would claim one version maps to two commits."""
    parents = []
    for name in ("old", "new"):
        parent = _parent(tmp_path, name)
        sub = _submodule(parent, commits=2)
        first = _git(sub, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        _git(sub, "tag", "-a", "v" + VERSION, first, "-m", "v" + VERSION)
        _git(sub, "push", "-q", "origin", "v" + VERSION)
        parents.append(parent)
    old = _run(TWIN, parents[0], VERSION=VERSION)
    new = _run(PORT, parents[1], VERSION=VERSION)
    assert old.returncode == 1
    assert "::error::Submodule private/renet tag v1.2.3 already points to " in old.stdout
    assert "Drift must be resolved manually before this release can proceed." in old.stdout
    _assert_agree(old, new, "drift")
    # The refusal must also mean NOTHING WAS PUSHED past the existing tag.
    old_remote = _git(parents[0] / "private" / "renet-remote.git", "rev-list", "-n1", "v1.2.3")
    sub_first = _git(
        parents[0] / "private" / "renet", "rev-list", "--max-parents=0", "HEAD"
    ).stdout.strip()
    assert old_remote.stdout.strip() == sub_first, "the twin retagged despite the drift"


def test_missing_version_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    """DOCUMENTED DIVERGENCE (`${VERSION:?...}` carries a bash line number)."""
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    _submodule(old_parent)
    _submodule(new_parent)
    old = _run(TWIN, old_parent)
    new = _run(PORT, new_parent)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stdout == new.stdout == ""
    assert "VERSION must be set" in old.stderr
    assert "VERSION must be set" in new.stderr
    assert _remote_tags(old_parent) == ""
    assert _remote_tags(new_parent) == ""


def test_empty_version_refuses_too(tmp_path: pathlib.Path) -> None:
    """`:?` fires on set-but-empty, not only on unset. A port using `"VERSION" in os.environ` would sail past this and try to push `v`."""
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    _submodule(old_parent)
    _submodule(new_parent)
    old = _run(TWIN, old_parent, VERSION="")
    new = _run(PORT, new_parent, VERSION="")
    assert old.returncode == 1
    assert new.returncode == 1
    assert "VERSION must be set" in old.stderr
    assert "VERSION must be set" in new.stderr
    assert _remote_tags(old_parent) == ""
    assert _remote_tags(new_parent) == ""


def test_unborn_head_dies_with_gits_own_exit_code(tmp_path: pathlib.Path) -> None:
    """A `.git` with no commits: `git rev-parse HEAD` fails, and under `set -e` the failed command substitution takes the script down with git's status. git's fatal message is on the INHERITED stderr, so it is byte-identical."""
    parents = []
    for name in ("old", "new"):
        parent = _parent(tmp_path, name)
        _submodule(parent, commits=0)
        parents.append(parent)
    old = _run(TWIN, parents[0], VERSION=VERSION)
    new = _run(PORT, parents[1], VERSION=VERSION)
    assert old.returncode == 128
    assert "fatal:" in old.stderr, "git said nothing; this case is not exercising the path"
    _assert_agree(old, new, "unborn-head")


def test_push_failure_propagates(tmp_path: pathlib.Path) -> None:
    """No `origin` at all. The tag is still created locally, and the push failure is the script's exit code -- not swallowed into a 0."""
    parents = []
    for name in ("old", "new"):
        parent = _parent(tmp_path, name)
        sub = _submodule(parent)
        _git(sub, "remote", "remove", "origin")
        parents.append(parent)
    old = _run(TWIN, parents[0], VERSION=VERSION)
    new = _run(PORT, parents[1], VERSION=VERSION)
    assert old.returncode != 0
    assert "origin" in old.stderr
    _assert_agree(old, new, "push-failure")


def test_missing_git_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`require_cmd git` is the first statement on both sides."""
    stub = tmp_path / "no-git-bin"
    stub.mkdir()
    for name in ("dirname", "uname"):
        real = shutil.which(name)
        assert real is not None, f"{name} is missing from this machine"
        (stub / name).symlink_to(real)
    assert shutil.which("git", path=str(stub)) is None, "git leaked into the stub PATH"
    old_parent = _parent(tmp_path, "old")
    new_parent = _parent(tmp_path, "new")
    old = _run(TWIN, old_parent, PATH=str(stub), VERSION=VERSION)
    new = _run(PORT, new_parent, PATH=str(stub), VERSION=VERSION)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'git' is not available\n"
    _assert_agree(old, new, "missing-git")


def test_is_initialized_helper(tmp_path: pathlib.Path) -> None:
    """The pure helper, BOTH DIRECTIONS: a `.git` directory and a `.git` file both count as initialized, a bare directory and a missing one do not."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert tag_submodules.is_initialized("nothing/here") is False
        (tmp_path / "bare").mkdir()
        assert tag_submodules.is_initialized("bare") is False
        (tmp_path / "dirshape" / ".git").mkdir(parents=True)
        assert tag_submodules.is_initialized("dirshape") is True
        (tmp_path / "fileshape").mkdir()
        (tmp_path / "fileshape" / ".git").write_text("gitdir: ../x\n", encoding="utf-8")
        assert tag_submodules.is_initialized("fileshape") is True
    finally:
        os.chdir(cwd)
    assert tag_submodules.SUBMODULES == ("private/renet",)


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY on the arm the twin's header exists for. Delete the drift refusal so the port silently reuses whatever tag it finds -- exactly the "silent retag" the twin forbids. Driven red against the drift fixture, then the source is restored byte-identical and re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace("        if existing_sha != head_sha:\n", "        if False:\n")
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    parents = []
    for name in ("old", "bad", "good"):
        parent = _parent(tmp_path, name)
        sub = _submodule(parent, commits=2)
        first = _git(sub, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        _git(sub, "tag", "-a", "v" + VERSION, first, "-m", "v" + VERSION)
        _git(sub, "push", "-q", "origin", "v" + VERSION)
        parents.append(parent)

    old = _run(TWIN, parents[0], VERSION=VERSION)
    bad = _run(mutant, parents[1], VERSION=VERSION)
    assert old.returncode == 1, "the TWIN did not refuse the drift; the plant is untested"
    assert bad.returncode == 0, "the mutant still refused; the plant did not fire"
    assert "::error::" not in bad.stdout

    good = _run(PORT, parents[2], VERSION=VERSION)
    assert good.returncode == old.returncode
    assert good.stdout == old.stdout, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )

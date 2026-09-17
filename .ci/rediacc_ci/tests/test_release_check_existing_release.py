"""`rediacc_ci.release.check_existing_release` against its bash twin.

TWO EXTERNAL CALLS, TWO DIFFERENT FIXTURE STRATEGIES. `git fetch`/`git tag -l`
run against a REAL git remote -- a disposable local bare repo this test
creates and points `origin` at, never GitHub -- so both sides exercise the
real git binary end to end. `gh release view` is faked on PATH (PREPENDED,
same reasoning as the `curl` fakes in the manifest siblings: `git` must keep
resolving normally).
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys

from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/release/check-existing-release.sh"
MODULE = "check_existing_release"

# Both invocations run with cwd set to a SCRATCH repo (so `git fetch`/`git tag` act on its `origin`, not this checkout), so the twin path and PYTHONPATH must be ABSOLUTE -- relative to this checkout, not to the scratch cwd.
_TWIN_ABS = str(pathlib.Path(diff.repo()) / TWIN)
_CI_ABS = str(pathlib.Path(diff.repo()) / ".ci")

FAKE_GH_TEMPLATE = """#!{python}
import sys
sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
sys.exit({rc})
"""


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_repo_with_origin(tmp_path: pathlib.Path, *, tags: list[str]) -> pathlib.Path:
    """A repo with a real `origin` remote (a local bare clone) carrying `tags`."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare")

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q")
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    (work / "f.txt").write_text("x")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "remote", "add", "origin", str(origin))
    for t in tags:
        _git(work, "tag", t)
    _git(work, "push", "-q", "origin", "HEAD", "--tags")

    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _make_fake_gh(
    tmp_path: pathlib.Path, *, rc: int, stdout: str = "", stderr: str = ""
) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(
        FAKE_GH_TEMPLATE.format(python=sys.executable, stdout=stdout, stderr=stderr, rc=rc)
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_both(
    repo: pathlib.Path, bindir: pathlib.Path, version: str
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(
        VERSION=version, GITHUB_REPOSITORY="rediacc/console", PATH=path_with_fake
    )
    new_env = diff.env_for(
        VERSION=version,
        GITHUB_REPOSITORY="rediacc/console",
        PATH=path_with_fake,
        PYTHONPATH=_CI_ABS,
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % _TWIN_ABS, env=old_env, cwd=str(repo), timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(repo), timeout=30
    )
    return old, new


def test_an_existing_tag_is_refused_on_both_sides(tmp_path: pathlib.Path) -> None:
    repo = _make_repo_with_origin(tmp_path, tags=["v1.2.3"])
    bindir = _make_fake_gh(tmp_path, rc=1, stderr="release not found\n")
    old, new = run_both(repo, bindir, "1.2.3")
    assert old == (
        1,
        "::error::Git tag v1.2.3 already exists. Aborting to prevent duplicate publish.\n",
        "",
    )
    assert new == old


def test_an_existing_github_release_is_refused_on_both_sides(tmp_path: pathlib.Path) -> None:
    repo = _make_repo_with_origin(tmp_path, tags=[])
    bindir = _make_fake_gh(tmp_path, rc=0, stdout="v1.2.3\tTitle\tpublished\t...\n")
    old, new = run_both(repo, bindir, "1.2.3")
    assert old == (
        1,
        "::error::Release v1.2.3 already exists. Aborting to prevent duplicate publish.\n",
        "",
    )
    assert new == old


def test_a_genuinely_new_version_is_available_on_both_sides(tmp_path: pathlib.Path) -> None:
    repo = _make_repo_with_origin(tmp_path, tags=["v0.9.0"])
    bindir = _make_fake_gh(tmp_path, rc=1, stderr="release not found\n")
    old, new = run_both(repo, bindir, "1.2.3")
    assert old == (0, "Version v1.2.3 is available for publishing.\n", "")
    assert new == old


def test_missing_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    repo = _make_repo_with_origin(tmp_path, tags=[])
    bindir = _make_fake_gh(tmp_path, rc=1, stderr="release not found\n")
    path_with_fake = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
    old_env = diff.env_for(GITHUB_REPOSITORY="rediacc/console", PATH=path_with_fake)
    new_env = diff.env_for(
        GITHUB_REPOSITORY="rediacc/console",
        PATH=path_with_fake,
        PYTHONPATH=_CI_ABS,
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % _TWIN_ABS, env=old_env, cwd=str(repo), timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(repo), timeout=30
    )
    assert old[0] == 1
    assert new[0] == 1
    assert "VERSION" in old[2]
    assert "VERSION" in new[2]

"""`rediacc_ci.version.resolve_version` against its bash twin.

Sibling of `test_release_check_existing_release.py` for the git-fixture strategy: real git tags in a disposable local repo, never GitHub. `git tag` needs no remote at all, so this fixture is simpler than that sibling's -- one `git init` plus a run of `git tag -a` calls.

Both invocations run with `cwd` set to the SCRATCH repo (so `git tag -l` acts on IT, not this checkout), so the twin path and PYTHONPATH must be ABSOLUTE -- relative to this checkout, not to the scratch cwd, exactly as in `test_release_check_existing_release.py`.

THE ONE BASH-SEMANTICS CASE WORTH A DEDICATED TEST: a tag with more than three dotted components (`v1.2.3.4`) folds the fourth into PATCH re-joined with '.' via bash's `read` with too few variable names, rather than being dropped. If the port ever "simplified" this to a 3-way split, `test_extra_dotted_component` is the one that would catch it, and it is exercised for both
directions (a component present, and PATCH bumped on top of it).

K=5 LEDGER: `.ci/shadow/w7p6-resolve-version.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's
own working tree is not clean; `shadow-gate.ts --record` refuses a dirty
tree). See that file's own header for the exact recording commands.
"""

from __future__ import annotations

import pathlib
import subprocess

from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/version/resolve-version.sh"
MODULE = "resolve_version"

_TWIN_ABS = str(pathlib.Path(diff.repo()) / TWIN)
_CI_ABS = str(pathlib.Path(diff.repo()) / ".ci")


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_repo(tmp_path: pathlib.Path, *, tags: list[str]) -> pathlib.Path:
    """A local repo with one commit and the given (possibly zero) tags."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    for t in tags:
        _git(repo, "tag", "-a", t, "-m", t)
    return repo


def run_both(repo: pathlib.Path, *args: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for()
    new_env = diff.env_for(PYTHONPATH=_CI_ABS, PYTHONDONTWRITEBYTECODE="1")
    arg_str = " ".join(args)
    old = diff.bash_streams(f"bash {_TWIN_ABS} {arg_str}", env=old_env, cwd=str(repo), timeout=30)
    new = diff.bash_streams(
        f"python3 -m rediacc_ci.version.{MODULE} {arg_str}",
        env=new_env,
        cwd=str(repo),
        timeout=30,
    )
    return old, new


def test_current_reads_the_latest_tag(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.2.3"])
    old, new = run_both(repo, "--current")
    assert old == (0, "1.2.3\n", "")
    assert new == old


def test_bump_patch(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.2.3"])
    old, new = run_both(repo, "--bump-type", "patch")
    assert old == (0, "1.2.4\n", "")
    assert new == old


def test_bump_minor_resets_patch(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.2.3"])
    old, new = run_both(repo, "--bump-type", "minor")
    assert old == (0, "1.3.0\n", "")
    assert new == old


def test_bump_major_resets_minor_and_patch(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.2.3"])
    old, new = run_both(repo, "--bump-type", "major")
    assert old == (0, "2.0.0\n", "")
    assert new == old


def test_prerelease_suffix_is_stripped_before_current_and_bump(
    tmp_path: pathlib.Path,
) -> None:
    repo = _make_repo(tmp_path, tags=["v2.5.0-beta.1"])
    old_current, new_current = run_both(repo, "--current")
    assert old_current == (0, "2.5.0\n", "")
    assert new_current == old_current
    old_bump, new_bump = run_both(repo, "--bump-type", "patch")
    assert old_bump == (0, "2.5.1\n", "")
    assert new_bump == old_bump


def test_newest_tag_by_version_sort_wins_not_creation_order(tmp_path: pathlib.Path) -> None:
    # v2.0.0 is tagged AFTER v10.0.0 so creation order and version order
    # disagree; both sides must pick the higher version, not the newer tag.
    repo = _make_repo(tmp_path, tags=["v10.0.0", "v2.0.0"])
    old, new = run_both(repo, "--current")
    assert old == (0, "10.0.0\n", "")
    assert new == old


def test_missing_patch_component_defaults_to_zero(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v9.9"])
    old, new = run_both(repo, "--bump-type", "patch")
    assert old == (0, "9.9.1\n", "")
    assert new == old


def test_extra_dotted_component_folds_into_patch(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.2.3.4"])
    old_current, new_current = run_both(repo, "--current")
    assert old_current == (0, "1.2.3.4\n", "")
    assert new_current == old_current


def test_no_tags_is_a_loud_error_not_a_silent_default(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=[])
    old, new = run_both(repo, "--current")
    assert old[0] == 1
    assert old[1] == ""
    assert "no version tags found" in old[2]
    assert new == old


def test_no_arguments_is_an_error(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.0.0"])
    old, new = run_both(repo)
    assert old == (1, "", "Error: --bump-type or --current required\n")
    assert new == old


def test_bump_type_with_no_value_is_an_error(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.0.0"])
    old, new = run_both(repo, "--bump-type")
    assert old == (1, "", "Error: --bump-type requires a value\n")
    assert new == old


def test_invalid_bump_type_names_the_bad_value(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.0.0"])
    old, new = run_both(repo, "--bump-type", "bogus")
    assert old == (
        1,
        "",
        "Error: invalid bump type 'bogus' (expected patch, minor, or major)\n",
    )
    assert new == old


def test_unknown_flag_prints_usage(tmp_path: pathlib.Path) -> None:
    repo = _make_repo(tmp_path, tags=["v1.0.0"])
    old, new = run_both(repo, "--nonsense")
    assert old == (
        1,
        "",
        "Usage: resolve-version.sh [--current | --bump-type patch|minor|major]\n",
    )
    assert new == old

"""`rediacc_ci.release.resolve_backfill_commit` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT`. The K=5 ledger is
`.ci/shadow/w7p5a-resolve-backfill-commit.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-resolve-backfill-commit --assert --k 5` -> "equivalence holds over 5 distinct trees").

EVERY CASE HERE RUNS AGAINST A THROWAWAY GIT REPOSITORY BUILT IN `tmp_path`, not against this checkout's own history. The twin never `cd`s -- it runs `git rev-list` / `git cat-file` / `git merge-base` against whatever repo the caller's cwd belongs to -- so a fixture repo with a controlled tag, a controlled `origin/main` (a plain ref, no real remote needed: `git update-ref
refs/remotes/origin/main <sha>` is enough for `merge-base --is-ancestor` to read it), and a controlled off-main commit is what lets this test assert the "reachable" and "not reachable from origin/main" arms deterministically, without depending on this repository's history staying shaped the way it happens to be shaped today.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN_REL = ".ci/scripts/release/resolve-backfill-commit.sh"
MODULE = "resolve_backfill_commit"


def _git(repo: pathlib.Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=diff.env_for(),
    )
    return r.stdout.strip()


def _build_repo(repo: pathlib.Path) -> dict[str, str]:
    """A tiny repo: two commits on `main` (tagged v1.0.0 at the tip, tracked as `origin/main`), and one commit on a feature branch never merged into it.

    Returns the shas/tags a test needs, so a case reads as "which of these" rather than re-deriving offsets into the fixture's own history.
    """
    repo.mkdir(parents=True, exist_ok=True)
    env = diff.env_for(
        GIT_AUTHOR_NAME="w7p5a",
        GIT_AUTHOR_EMAIL="w7p5a@example.invalid",
        GIT_COMMITTER_NAME="w7p5a",
        GIT_COMMITTER_EMAIL="w7p5a@example.invalid",
    )
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", *args], cwd=str(repo), env=env, capture_output=True, text=True, check=True
    )
    run("init", "-q", "-b", "main")
    (repo / "f.txt").write_text("one\n", encoding="utf-8")
    run("add", "f.txt")
    run("commit", "-q", "-m", "first")
    (repo / "f.txt").write_text("two\n", encoding="utf-8")
    run("commit", "-aq", "-m", "second")
    main_tip = _git(repo, "rev-parse", "HEAD")
    run("tag", "v1.0.0", main_tip)
    # A plain ref is enough for `merge-base --is-ancestor <sha> origin/main` to read; no real remote or network is involved.
    run("update-ref", "refs/remotes/origin/main", main_tip)
    run("checkout", "-qb", "feature")
    (repo / "f.txt").write_text("off-main\n", encoding="utf-8")
    run("commit", "-aq", "-m", "unmerged")
    off_main_sha = _git(repo, "rev-parse", "HEAD")
    run("checkout", "-q", "main")
    return {"main_tip": main_tip, "off_main_sha": off_main_sha}


def run_both(
    repo: pathlib.Path, twin_root: str, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = repo / "old-output.txt"
    out_new = repo / "new-output.txt"
    old_env = diff.env_for(**env_extra, GITHUB_OUTPUT=str(out_old))
    new_env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out_new),
        PYTHONPATH=os.path.join(twin_root, ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams(
        "bash %s" % os.path.join(twin_root, TWIN_REL), env=old_env, cwd=str(repo), timeout=30
    )
    new = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, cwd=str(repo), timeout=30
    )
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_tag_resolves_and_is_reachable(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    env = {"VERSION": "v1.0.0"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        repo, diff.repo(), env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert (
        old_out == f"→ resolved v1.0.0 → {facts['main_tip']}\n✓ commit reachable from origin/main\n"
    )
    assert new_out == old_out
    assert old_output == f"commit_sha={facts['main_tip']}\n"
    assert new_output == old_output


def test_missing_tag_names_the_tag_byte_for_byte(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    _build_repo(repo)
    env = {"VERSION": "v9.9.9-does-not-exist"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), _, _ = run_both(
        repo, diff.repo(), env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert (
        old_out
        == "::error::tag v9.9.9-does-not-exist not found in this checkout; pass commit_sha explicitly\n"
    )
    assert new_out == old_out
    assert old_err == new_err == ""


def test_operator_supplied_sha_that_does_not_exist_byte_for_byte(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    _build_repo(repo)
    bogus = "deadbeef" * 5
    env = {"VERSION": "v1.0.0", "INPUT_SHA": bogus}
    (old_exit, old_out, _old_err), (new_exit, new_out, _new_err), _, _ = run_both(
        repo, diff.repo(), env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert old_out == new_out
    assert f"commit {bogus} does not name a commit" in old_out
    assert "2026-08-23 git history rewrite" in old_out


def test_operator_supplied_sha_not_reachable_from_origin_main(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    facts = _build_repo(repo)
    env = {"VERSION": "v1.0.0", "INPUT_SHA": facts["off_main_sha"]}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), _, _ = run_both(
        repo, diff.repo(), env
    )
    assert old_exit == 1
    assert new_exit == 1
    assert old_out == (
        f"→ using operator-supplied commit_sha: {facts['off_main_sha']}\n"
        f"::error::commit {facts['off_main_sha']} is not reachable from origin/main\n"
        "::error::refusing to backfill a sentinel for a detached tag\n"
    )
    assert new_out == old_out
    assert old_err == new_err == ""


def test_missing_version_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    _build_repo(repo)
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(repo, diff.repo(), {})
    assert old_exit == 1
    assert new_exit == 1
    assert "VERSION" in old_err
    assert "must be set" in old_err
    assert "VERSION" in new_err
    assert "must be set" in new_err

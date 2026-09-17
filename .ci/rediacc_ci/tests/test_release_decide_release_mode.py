"""`rediacc_ci.release.decide_release_mode` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT` and why the missing-env-var
path is checked for exit code and substance, not bytes. The K=5 ledger is
`.ci/shadow/w7p5a-decide-release-mode.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-decide-release-mode --assert
--k 5` -> "equivalence holds over 5 distinct trees").

Unlike the deploy sibling, this script ALSO prints `::notice::` lines to
stdout, so those cases assert full stdout equality too (not just the file).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/release/decide-release-mode.sh"
MODULE = "decide_release_mode"


def run_both(
    tmp_path: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-output.txt"
    out_new = tmp_path / "new-output.txt"
    old_env = diff.env_for(**env_extra, GITHUB_OUTPUT=str(out_old))
    new_env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out_new),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_workers_only_short_circuits_before_release_mode(tmp_path: pathlib.Path) -> None:
    env = {"DEPLOY_WORKERS_ONLY": "true", "RELEASE_MODE": "patch"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert (
        old_out == "::notice::Workers-only mode -- deploy Workers without version bump or publish\n"
    )
    assert new_out == old_out
    assert old_output == "retry_mode=false\nworkers_only=true\n"
    assert new_output == old_output


def test_retry_mode(tmp_path: pathlib.Path) -> None:
    env = {"DEPLOY_WORKERS_ONLY": "false", "RELEASE_MODE": "retry"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "::notice::Retry mode -- will re-deploy current version without bumping\n"
    assert new_out == old_out
    assert old_output == "workers_only=false\nretry_mode=true\n"
    assert new_output == old_output


def test_patch_mode(tmp_path: pathlib.Path) -> None:
    env = {"DEPLOY_WORKERS_ONLY": "false", "RELEASE_MODE": "patch"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "::notice::Release mode: patch bump -- will create new release\n"
    assert new_out == old_out
    assert old_output == "workers_only=false\nretry_mode=false\n"
    assert new_output == old_output


def test_missing_deploy_workers_only_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    env = {"RELEASE_MODE": "patch"}
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, env)
    assert old_exit == 1
    assert new_exit == 1
    assert "DEPLOY_WORKERS_ONLY" in old_err
    assert "must be set" in old_err
    assert "DEPLOY_WORKERS_ONLY" in new_err
    assert "must be set" in new_err

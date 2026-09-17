"""`rediacc_ci.release.deployment_summary` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_STEP_SUMMARY`. The K=5 ledger is
`.ci/shadow/w7p5a-deployment-summary.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-deployment-summary --assert --k 5` -> "equivalence holds over 5 distinct trees").

The valid path is byte-identical on purpose: this script has no branch at all, only string interpolation into a fixed template, so "both sides wrote the exact same bytes" is the whole claim being tested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/release/deployment-summary.sh"
MODULE = "deployment_summary"


def run_both(
    tmp_path: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-summary.md"
    out_new = tmp_path / "new-summary.md"
    old_env = diff.env_for(**env_extra, GITHUB_STEP_SUMMARY=str(out_old))
    new_env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=str(out_new),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_full_summary_is_byte_identical(tmp_path: pathlib.Path) -> None:
    env = {"VERSION": "1.2.3", "CI_RUN_ID": "42", "CI_SHA": "abc123"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_output == (
        "\n---\n\n## Deployment Complete\n\n"
        "**Version:** v1.2.3\n"
        "**CI Run:** 42 (sha: abc123)\n"
        "**Pages URL:** https://www.rediacc.com\n\n"
        "**Docker images:**\n"
        "- ghcr.io/rediacc/renet:1.2.3 + :latest\n"
        "- ghcr.io/rediacc/rdc:1.2.3 + :latest\n"
        "- ghcr.io/rediacc/server:1.2.3 + :latest (on-prem)\n"
    )
    assert new_output == old_output


def test_appends_rather_than_overwrites(tmp_path: pathlib.Path) -> None:
    """`$GITHUB_STEP_SUMMARY` already carries other jobs' output by the time this step runs; both sides must `>>`, never truncate."""
    out_old = tmp_path / "old-summary.md"
    out_new = tmp_path / "new-summary.md"
    out_old.write_text("# earlier job output\n", encoding="utf-8")
    out_new.write_text("# earlier job output\n", encoding="utf-8")
    env = {"VERSION": "0.0.1", "CI_RUN_ID": "1", "CI_SHA": "deadbeef"}
    old_env = diff.env_for(**env, GITHUB_STEP_SUMMARY=str(out_old))
    new_env = diff.env_for(
        **env, GITHUB_STEP_SUMMARY=str(out_new), PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    assert old[0] == 0
    assert new == old
    old_output = out_old.read_text(encoding="utf-8")
    new_output = out_new.read_text(encoding="utf-8")
    assert old_output.startswith("# earlier job output\n")
    assert new_output == old_output


def test_missing_ci_sha_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    env = {"VERSION": "1.2.3", "CI_RUN_ID": "42"}
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, env)
    assert old_exit == 1
    assert new_exit == 1
    assert "CI_SHA" in old_err
    assert "must be set" in old_err
    assert "CI_SHA" in new_err
    assert "must be set" in new_err

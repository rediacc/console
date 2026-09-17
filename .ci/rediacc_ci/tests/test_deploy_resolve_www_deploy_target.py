"""`rediacc_ci.deploy.resolve_www_deploy_target` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for why `/dev/stdout` is not used as `$GITHUB_OUTPUT` and why the missing-env-var
path is checked for exit code and substance, not bytes. The K=5 ledger is
`.ci/shadow/w7p5a-resolve-www-deploy-target.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-resolve-www-deploy-target --assert --k 5` -> "equivalence holds over 5 distinct trees").

BOTH VALID PATHS ARE BYTE-IDENTICAL, deliberately, same reasoning as the
`resolve_account_deploy_config` sibling: pure computation, four `key=value`
lines to `$GITHUB_OUTPUT`, nothing on stdout or stderr.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/deploy/resolve-www-deploy-target.sh"
MODULE = "resolve_www_deploy_target"


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
    new = diff.bash_streams("python3 -m rediacc_ci.deploy.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_stable_target_selects_the_stable_worker(tmp_path: pathlib.Path) -> None:
    env = {"TARGET": "stable"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_output == (
        "script=deploy-www.sh\nworker=rediacc-www\ndomain=www.rediacc.com\nsandbox=\n"
    )
    assert new_output == old_output


def test_edge_target_selects_the_edge_worker_and_sandbox(tmp_path: pathlib.Path) -> None:
    env = {"TARGET": "edge"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_output == (
        "script=deploy-edge.sh\nworker=edge-rediacc-www\ndomain=edge.rediacc.com\n"
        "sandbox=--sandbox\n"
    )
    assert new_output == old_output


def test_missing_target_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """Exit codes and the identified variable agree; wording does not, and is not supposed to -- see the port's module docstring."""
    env: dict[str, str] = {}
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, env)
    assert old_exit == 1
    assert new_exit == 1
    assert "TARGET" in old_err
    assert "must be set" in old_err
    assert "TARGET" in new_err
    assert "must be set" in new_err

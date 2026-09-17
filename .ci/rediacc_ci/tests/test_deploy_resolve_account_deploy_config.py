"""`rediacc_ci.deploy.resolve_account_deploy_config` against its bash twin.

W7P5-a (`agent/PLAN-tooling-transformation.md` line 607): `deploy/` and
`release/` carried zero Python and zero ledgers before this box. The K=5
shadow-gate ledger proving equivalence across five distinct committed specimens lives at `.ci/shadow/w7p5a-resolve-account-deploy-config.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-resolve-account-deploy-config
--assert --k 5` -> "equivalence holds over 5 distinct trees"); this file is
the fast, permanent regression twin of that one-time proof, run against the REAL twin and REAL port in this tree rather than a throwaway fixture, since the script has no git-scanning surface for a fixture to vary.

BOTH VALID PATHS ARE BYTE-IDENTICAL, deliberately, because the script is pure
computation (no logging helper, no colour, no timestamp): four `key=value`
lines to `$GITHUB_OUTPUT`, nothing to stdout or stderr. The missing-env-var path is NOT byte-identical on purpose -- see the port's module docstring -- so that case only asserts the exit code and that both messages name the missing variable, which is what the shadow-gate ledger's `--finding-re` actually compares.

`/dev/stdout` IS NOT USED as `$GITHUB_OUTPUT` here. Both `bash >>` and Python's `open(...,"a")` fail with ENXIO ("No such device or address") when `$GITHUB_OUTPUT` names `/dev/stdout` and the process's fd 1 is an anonymous
pipe rather than a tty -- which is exactly what `subprocess.run(capture_output=True)`
and Node's `spawnSync` both give a child. Reproduced directly with `bash -c 'echo x >>/dev/stdout'` under a piped fd 1. A real temp file sidesteps it and is what the twin's own "Run locally" usage comment should arguably say instead of `/dev/stdout`, though that is the bash file's docstring to fix, not this port's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/deploy/resolve-account-deploy-config.sh"
MODULE = "resolve_account_deploy_config"


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


def test_edge_target_selects_edge_worker_and_sandbox(tmp_path: pathlib.Path) -> None:
    env = {
        "TARGET": "edge",
        "MATRIX_ID": "eu",
        "MATRIX_SECRET_SUFFIX": "EU",
        "MATRIX_WORKER_NAME": "w",
        "MATRIX_DOMAIN": "d",
        "MATRIX_EDGE_WORKER_NAME": "ew",
        "MATRIX_EDGE_DOMAIN": "ed",
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_output == "region=eu\nworker=ew\ndomain=ed\nsandbox=--sandbox\n"
    assert new_output == old_output


def test_stable_target_selects_stable_worker_and_no_sandbox(tmp_path: pathlib.Path) -> None:
    env = {
        "TARGET": "stable",
        "MATRIX_ID": "us",
        "MATRIX_SECRET_SUFFIX": "US",
        "MATRIX_WORKER_NAME": "w2",
        "MATRIX_DOMAIN": "d2",
        "MATRIX_EDGE_WORKER_NAME": "ew2",
        "MATRIX_EDGE_DOMAIN": "ed2",
    }
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (0, "", "")
    assert (new_exit, new_out, new_err) == (0, "", "")
    assert old_output == "region=us\nworker=w2\ndomain=d2\nsandbox=\n"
    assert new_output == old_output


def test_missing_target_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """Exit codes and the identified variable agree; wording does not, and is
    not supposed to -- see the port's module docstring."""
    env = {"MATRIX_ID": "eu", "MATRIX_SECRET_SUFFIX": "EU"}
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, env)
    assert old_exit == 1
    assert new_exit == 1
    assert "TARGET" in old_err
    assert "must be set" in old_err
    assert "TARGET" in new_err
    assert "must be set" in new_err

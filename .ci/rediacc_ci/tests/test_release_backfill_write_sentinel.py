"""`rediacc_ci.release.backfill_write_sentinel` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT`. The K=5 ledger is
`.ci/shadow/w7p5a-backfill-write-sentinel.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-backfill-write-sentinel
--assert --k 5` -> "equivalence holds over 5 distinct trees").

`DRY_RUN=false` STAYS ON THE LOCAL-ARGUMENT-VALIDATION PATH, same design as
`test_deploy_upload_media_to_r2.py`'s forwarding-shim cases: `aws` is absent
on this host (`shutil.which("aws") is None`, asserted below so this test
fails loud rather than silently passing on a host where it is not), so both
sides' forward into `.ci/scripts/deploy/write-release-sentinel.sh` dies at
its own `require_cmd aws` -- before any network access, before any R2
credential is read. That failure message is exactly what these cases assert,
which is the real, unmocked forward this port makes, stopped by the same
missing binary the bash twin would stop on.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/release/backfill-write-sentinel.sh"
MODULE = "backfill_write_sentinel"


def test_aws_is_absent_on_this_host() -> None:
    """The premise every DRY_RUN=false case below depends on."""
    assert shutil.which("aws") is None, (
        "aws is installed on this host; the DRY_RUN=false cases below assume it is "
        "absent so the forward stops before any R2 access. Re-derive them against "
        "a host without aws, or they are exercising a different path than documented."
    )


def run_both(env_extra: dict[str, str]) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for(**env_extra)
    new_env = diff.env_for(**env_extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    return old, new


def test_dry_run_true_prints_the_invocation_byte_for_byte() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "true"}
    old, new = run_both(env)
    expected_stdout = (
        "→ DRY RUN -- would invoke:\n"
        "   .ci/scripts/deploy/write-release-sentinel.sh --version 1.1.2 "
        "--channel edge --commit-sha deadbeef1234\n"
        "→ no R2 mutation performed\n"
    )
    assert old == (0, expected_stdout, "")
    assert new == old


def test_dry_run_true_strips_the_leading_v(tmp_path: pathlib.Path) -> None:
    del tmp_path
    env = {
        "VERSION": "v9.9.9",
        "CHANNEL": "stable",
        "COMMIT_SHA": "cafef00d",
        "DRY_RUN": "true",
    }
    old, new = run_both(env)
    assert old[0] == 0
    assert "--version 9.9.9 " in old[1]
    assert new == old


def test_dry_run_false_forwards_and_dies_on_missing_aws_byte_for_byte() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "false"}
    old, new = run_both(env)
    assert old == (
        1,
        "→ writing sentinel(s) for v1.1.2 on channel edge (commit deadbeef1234)\n",
        "✗ Required command 'aws' is not available\n",
    )
    assert new == old


def test_missing_channel_fails_the_same_way_reworded() -> None:
    """Exit codes and the identified variable agree; wording does not, and is
    not supposed to -- see the port's module docstring."""
    env = {"VERSION": "v1.1.2", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "true"}
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(env)
    assert old_exit == 1
    assert new_exit == 1
    assert "CHANNEL" in old_err
    assert "must be set" in old_err
    assert "CHANNEL" in new_err
    assert "must be set" in new_err


def test_missing_dry_run_fails_the_same_way_reworded() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234"}
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(env)
    assert old_exit == 1
    assert new_exit == 1
    assert "DRY_RUN" in old_err
    assert "must be set" in old_err
    assert "DRY_RUN" in new_err
    assert "must be set" in new_err

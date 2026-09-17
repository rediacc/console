"""`rediacc_ci.release.backfill_write_sentinel` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT`. The K=5 ledger is
`.ci/shadow/w7p5a-backfill-write-sentinel.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-backfill-write-sentinel --assert --k 5` -> "equivalence holds over 5 distinct trees").

`DRY_RUN=false` STAYS ON THE LOCAL-ARGUMENT-VALIDATION PATH, same design as
`test_deploy_upload_media_to_r2.py`'s forwarding-shim cases: `aws` is absent on this host (`shutil.which("aws") is None`, asserted below so this test fails loud rather than silently passing on a host where it is not), so both sides' forward into `.ci/scripts/deploy/write-release-sentinel.sh` dies at its own `require_cmd aws` -- before any network access, before any R2 credential is
read. That failure message is exactly what these cases assert, which is the real, unmocked forward this port makes, stopped by the same missing binary the bash twin would stop on.
"""

from __future__ import annotations

import functools
import pathlib
import tempfile

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import pathmask

TWIN = ".ci/scripts/release/backfill-write-sentinel.sh"
MODULE = "backfill_write_sentinel"


@functools.lru_cache(maxsize=1)
def masked_path() -> str:
    """The differential's PATH with `aws` MADE unreachable, once per session.

    The DRY_RUN=false cases below need the forward to stop at `require_cmd aws`
    before it can reach R2. This used to be left to the host, and the host obliged on every developer machine and refused on a GitHub runner, which ships the CLI at /usr/local/bin/aws. See pathmask.py for why the mask
    mirrors a directory rather than guessing at `PATH=/usr/bin:/bin`.
    """
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="backfill-pathmask-"))
    path = pathmask.path_without("aws", scratch, base=diff.BASE_ENV["PATH"])
    pathmask.assert_absent("aws", path)
    return path


def test_the_subjects_cannot_reach_aws() -> None:
    """The premise every DRY_RUN=false case below depends on -- MADE, not assumed.

    This was `assert shutil.which("aws") is None`, a claim about the machine that happened to be running the suite. It passed here and failed in CI run 34970782616 with `/usr/local/bin/aws`, and the failure was the honest one: on a host WITH aws those cases were never exercising the refusal they document. Now the PATH handed to both subjects is masked, and this asserts the mask
    rather than the host.
    """
    pathmask.assert_absent("aws", masked_path())


def run_both(env_extra: dict[str, str]) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for(**env_extra, PATH=masked_path())
    new_env = diff.env_for(
        **env_extra, PATH=masked_path(), PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
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
    """Exit codes and the identified variable agree; wording does not, and is not supposed to -- see the port's module docstring."""
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

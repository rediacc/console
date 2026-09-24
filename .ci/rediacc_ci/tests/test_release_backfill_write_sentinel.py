"""`rediacc_ci.release.backfill_write_sentinel`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/release/backfill-write-sentinel.sh` over the same environment and compared its exit code, stdout and stderr against the port's.
The K=5 ledger `.ci/shadow/w7p5a-backfill-write-sentinel.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-backfill-write-sentinel --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

`DRY_RUN=false` STAYS ON THE LOCAL-ARGUMENT-VALIDATION PATH, same design as `test_deploy_upload_media_to_r2.py`'s forwarding-shim cases: `aws` is MADE unreachable below, so the forward into `.ci/scripts/deploy/write-release-sentinel.sh` dies at its own `require_cmd aws` -- before any network access, before any R2 credential is read. That failure message is exactly what the case
asserts, which is the real, unmocked forward this port makes, stopped by the same missing binary the bash twin stopped on.
"""

from __future__ import annotations

import functools
import pathlib

from rediacc_ci import runtmp
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import pathmask

MODULE = "backfill_write_sentinel"


@functools.lru_cache(maxsize=1)
def masked_path() -> str:
    """The differential's PATH with `aws` MADE unreachable, once per session.

    The DRY_RUN=false case below needs the forward to stop at `require_cmd aws`
    before it can reach R2. This used to be left to the host, and the host obliged on every developer machine and refused on a GitHub runner, which ships the CLI at /usr/local/bin/aws. See pathmask.py for why the mask
    mirrors a directory rather than guessing at `PATH=/usr/bin:/bin`.
    """
    # Session-cached, so no single test owns it and pytest's tmp_path cannot hold it. A pid-stamped run dir: removed at exit, and swept by the next run when this one was killed before exit, or every killed run leaves one symlink farm in /tmp.
    scratch = pathlib.Path(runtmp.run_dir("backfill-pathmask-"))
    path = pathmask.path_without("aws", scratch, base=diff.BASE_ENV["PATH"])
    pathmask.assert_absent("aws", path)
    return path


def test_the_subject_cannot_reach_aws() -> None:
    """The premise every DRY_RUN=false case below depends on -- MADE, not assumed.

    This was `assert shutil.which("aws") is None`, a claim about the machine that happened to be running the suite. It passed here and failed in CI run 34970782616 with `/usr/local/bin/aws`, and the failure was the honest one: on a host WITH aws those cases were never exercising the refusal they document. Now the PATH handed to the subject is masked, and this asserts the mask
    rather than the host.
    """
    pathmask.assert_absent("aws", masked_path())


def run_port(env_extra: dict[str, str]) -> tuple[int, str, str]:
    env = diff.env_for(
        **env_extra, PATH=masked_path(), PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    return diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30)


def test_dry_run_true_prints_the_invocation_byte_for_byte() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "true"}
    expected_stdout = (
        "→ DRY RUN -- would invoke:\n"
        "   .ci/scripts/deploy/write-release-sentinel.sh --version 1.1.2 "
        "--channel edge --commit-sha deadbeef1234\n"
        "→ no R2 mutation performed\n"
    )
    assert run_port(env) == (0, expected_stdout, "")


def test_dry_run_true_strips_the_leading_v() -> None:
    env = {"VERSION": "v9.9.9", "CHANNEL": "stable", "COMMIT_SHA": "cafef00d", "DRY_RUN": "true"}
    exit_code, out, _ = run_port(env)
    assert exit_code == 0
    assert "--version 9.9.9 " in out
    assert "--channel stable " in out


def test_dry_run_false_forwards_and_dies_on_missing_aws_byte_for_byte() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "false"}
    assert run_port(env) == (
        1,
        "→ writing sentinel(s) for v1.1.2 on channel edge (commit deadbeef1234)\n",
        "✗ Required command 'aws' is not available\n",
    )


def test_the_dry_run_flag_separates_the_two_paths() -> None:
    """ANTI-VACUITY. The two cases above are only evidence while the flag is what decides between them."""
    base = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234"}
    dry = run_port({**base, "DRY_RUN": "true"})
    wet = run_port({**base, "DRY_RUN": "false"})
    assert dry[0] != wet[0]
    assert dry[1] != wet[1]


def test_missing_channel_is_refused_and_names_the_variable() -> None:
    env = {"VERSION": "v1.1.2", "COMMIT_SHA": "deadbeef1234", "DRY_RUN": "true"}
    exit_code, _, err = run_port(env)
    assert exit_code == 1
    assert "CHANNEL" in err
    assert "must be set" in err


def test_missing_dry_run_is_refused_and_names_the_variable() -> None:
    env = {"VERSION": "v1.1.2", "CHANNEL": "edge", "COMMIT_SHA": "deadbeef1234"}
    exit_code, _, err = run_port(env)
    assert exit_code == 1
    assert "DRY_RUN" in err
    assert "must be set" in err

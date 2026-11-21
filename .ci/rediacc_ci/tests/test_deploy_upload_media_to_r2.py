"""`rediacc_ci.deploy.upload_media_to_r2` against its bash twin.

Both are pure forwarding shims (`exec` / `os.execv`) onto the real primitive, `.ci/media/tools/upload-r2.sh`, so what is under test is the FORWARD: argv, exit status, and whatever the target prints before it would need network access. Every case here stays on the target's local argument-validation path (`--kind`, then `require_var`, then `require_file`), which all run before
`require_cmd aws` -- so these are real invocations of both shims, with no credentials, no network, and no fixture, exactly like `.ci/rediacc_ci/tests/gates/test_gate_media_shims.py`'s own "aws, npx and the network absent" design for the twin.

The K=5 shadow-gate ledger is
`.ci/shadow/w7p5a-upload-media-to-r2.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-upload-media-to-r2 --assert --k 5` -> "equivalence holds over 5 distinct trees"), varying argv rather than env vars across the five specimens -- this script has no environment-driven branch at all.
"""

from __future__ import annotations

import os
import subprocess

from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import MEDIA_BUCKET

TWIN = ".ci/scripts/deploy/upload-media-to-r2.sh"
MODULE = "upload_media_to_r2"


def run_both(argv: str) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s %s" % (TWIN, argv), env=env, timeout=30)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.deploy.%s %s" % (MODULE, argv), env=env, timeout=30
    )
    return old, new


def test_no_args_rejects_kind_byte_for_byte() -> None:
    old, new = run_both("")
    assert old == (1, "", "✗ --kind must be 'tutorials' or 'solutions', got ''\n")
    assert new == old


def test_bogus_kind_names_the_bad_value_byte_for_byte() -> None:
    old, new = run_both("--kind bogus")
    assert old == (1, "", "✗ --kind must be 'tutorials' or 'solutions', got 'bogus'\n")
    assert new == old


def test_unknown_flag_byte_for_byte() -> None:
    old, new = run_both("--wat nope")
    assert old == (1, "", "✗ Unknown argument: --wat\n")
    assert new == old


def test_missing_required_var_after_valid_kind_byte_for_byte() -> None:
    old, new = run_both("--kind tutorials")
    assert old[0] == 1
    assert new == old
    assert "is not set" in old[1] + old[2]


def test_missing_file_byte_for_byte(tmp_path) -> None:
    missing = tmp_path / "does-not-exist.mp4"
    argv = "--kind solutions --key k --lang en --field mp4 --file %s" % missing
    old, new = run_both(argv)
    assert old[0] == 1
    assert new == old


def test_upload_target_is_the_media_bucket(tmp_path) -> None:
    """The primitive publishes to the registry's `media` bucket, in both the `s3 cp` and the HEAD readback."""

    calls = tmp_path / "aws-calls.txt"
    fake_aws = tmp_path / "fake-aws"
    fake_aws.write_text('#!/bin/sh\necho "$@" >> "%s"\n' % calls)
    fake_aws.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_npx = fake_bin / "npx"
    fake_npx.write_text("#!/bin/sh\nexit 0\n")
    fake_npx.chmod(0o755)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    env = dict(os.environ)
    env.update(
        AWS_BIN=str(fake_aws),
        PATH="%s:%s" % (fake_bin, os.environ["PATH"]),
        CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID="k",
        CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY="s",
        CLOUDFLARE_R2_MEDIA_ENDPOINT="http://127.0.0.1:1",
    )
    argv = ["bash", ".ci/media/tools/upload-r2.sh", "--kind", "solutions", "--key", "k"]
    argv += ["--lang", "en", "--field", "mp4", "--file", str(video)]
    argv += ["--defer-manifest", str(tmp_path / "deferred.tsv")]
    proc = subprocess.run(
        argv, env=env, cwd=diff.repo(), capture_output=True, text=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
    lines = calls.read_text().splitlines()
    key = "videos/solutions/en/clip.mp4"
    assert lines[0].startswith("s3 cp %s s3://%s/%s " % (video, MEDIA_BUCKET, key))
    assert "s3api head-object --bucket %s --key %s " % (MEDIA_BUCKET, key) in lines[1]

#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/write-release-sentinel.sh`.

Writes the `.released` commit sentinel, which is the ATOMIC COMMIT POINT of the
release pipeline: after this, `write_once_guard` in `upload-to-r2.sh` refuses to
overwrite the bytes and the drift gate requires a matching git tag. The twin's
header carries the contract; this docstring records only what the PORT decided.

THE VALIDATOR LIBRARY IS NOT RE-PORTED HERE. `rediacc_ci.core.
release_state_validator` is already the Python side of
`.ci/scripts/lib/release-state-validator.sh`, so `binary_count` and
`get_sentinel_payload` come from there rather than being spelled a second time.
One consequence is visible in the differential and named rather than hidden:
that module's `_log_error` deliberately omits `common.sh`'s `✗ ` glyph (its own
docstring says so), while the twin's `log_error` emits it. The two stderr
streams therefore differ by exactly that prefix on the `rsv_binary_count`
failure path, and `test_deploy_write_release_sentinel` normalises that one
prefix and nothing else.

`aws` AND `jq` ARE SHELLED OUT TO. `aws` because it is a credentialed tool with
a real remote side, which is precisely the kind the campaign fakes on `PATH`
rather than reimplements; `jq` because the payload IS jq's bytes. `jq -nc`
with five `--arg`s produces a specific key order and a specific escaping, and a
`json.dumps` here would be a second answer to a question the twin has already
answered. The payload is uploaded verbatim and read back for comparison, so any
byte difference is a real difference.

THE ONE THING NEITHER SIDE CAN MAKE IDENTICAL is `released_at`. The twin stamps
`date -u +'%Y-%m-%dT%H:%M:%SZ'` and this stamps
`datetime.now(UTC).strftime(...)`; two processes started a second apart produce
two different payloads. Nothing in either program's OUTPUT quotes the
timestamp, so stdout and stderr still compare byte for byte; the differential
compares the uploaded payload with that one field normalised, and asserts
separately that both sides emit the same FORMAT.

TWO TWIN DEFECTS ARE CARRIED, NOT FIXED (they belong to a later cutover box):

  FINDING 5: `--version` WITH NO VALUE EXITS 1 SILENTLY. The parser does
  `VERSION="${2:-}"; shift 2`, and `shift 2` with one argument left returns
  non-zero, which `set -e` turns into a bare exit 1. Not the documented exit 2,
  and no message at all. Driven:
  `bash -c 'set -e; while [[ $# -gt 0 ]]; do case "$1" in --version) V="${2:-}";
  shift 2;; esac; done' _ --version` exits 1 with empty stdout and stderr.

  FINDING 6: A FAILED `rsv_binary_count` PROBE ALSO EXITS 1, and 1 is the same
  code the sealed-but-empty REFUSAL uses. The library goes to real trouble to
  distinguish "the prefix is empty" from "the question could not be answered"
  (see its own comment at :161-166), and this caller collapses both back into
  one exit code, differing only in the stderr text.

Exit: 0 sentinel written and read back, 1 any failure, 2 a usage error.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.core import release_state_validator as rsv

PRODUCT = "cli"
CHANNELS = ("edge", "stable")


class UsageError(Exception):
    """`log_error ...; exit 2`, the twin's usage-error shape."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SentinelFailedError(Exception):
    """A `log_error ...; return 1` out of `write_sentinel`, which `set -e` fatals."""

    def __init__(self, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines = list(lines)


def parse_flags(argv: list[str]) -> tuple[str, str, str]:
    """The twin's `while [[ $# -gt 0 ]]; do case "$1" in ...` loop.

    Returns `(version, channel, commit_sha)`, any of which may be empty; the
    required-flag checks are the caller's, exactly as in the twin.

    THE MISSING-VALUE CASE IS FINDING 5 and is reproduced, not corrected:
    `--version` as the last argument makes `shift 2` fail, and under `set -e`
    that is exit 1 with NO output. `_ShiftFailedError` below carries that.
    """
    version = channel = commit_sha = ""
    known = {"--version": "version", "--channel": "channel", "--commit-sha": "commit_sha"}
    rest = list(argv)
    while rest:
        flag = rest[0]
        if flag not in known:
            raise UsageError("unknown flag: %s" % flag)
        value = rest[1] if len(rest) > 1 else ""
        if len(rest) < 2:  # `shift 2` needs two positionals
            raise _ShiftFailedError
        if known[flag] == "version":
            version = value
        elif known[flag] == "channel":
            channel = value
        else:
            commit_sha = value
        rest = rest[2:]
    return version, channel, commit_sha


class _ShiftFailedError(Exception):
    """`shift 2` with one argument left: exit 1, no message. See FINDING 5."""


def build_payload(
    version_tag: str, channel: str, commit_sha: str, product: str, released_at: str
) -> str:
    """`build_payload` (write-release-sentinel.sh:92-108), via real `jq -nc`.

    The key order in the object literal is the twin's and is preserved by jq,
    so the uploaded bytes are the twin's bytes. `--arg` is used for all five,
    which means every value is a JSON STRING even when it looks numeric.
    """
    proc = subprocess.run(
        [
            "jq",
            "-nc",
            "--arg",
            "version",
            version_tag,
            "--arg",
            "channel",
            channel,
            "--arg",
            "commit",
            commit_sha,
            "--arg",
            "product",
            product,
            "--arg",
            "released_at",
            released_at,
            """{
            version: $version,
            channel: $channel,
            commit_sha: $commit,
            product: $product,
            released_at: $released_at,
            artifacts_produced: ["cli"]
        }""",
        ],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SentinelFailedError("build_payload: jq exited %d" % proc.returncode)
    return proc.stdout.rstrip("\n")


def released_at_now() -> str:
    """`date -u +'%Y-%m-%dT%H:%M:%SZ'`. Second precision, no fraction, Z suffix."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jq_field(payload: str, field: str) -> str:
    """`jq -r '.<field>' <<<"$payload"`."""
    proc = subprocess.run(
        ["jq", "-r", ".%s" % field],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        check=False,
    )
    return proc.stdout.rstrip("\n")


def write_sentinel(product: str, version_tag: str, channel: str, commit_sha: str) -> None:
    """`write_sentinel` (write-release-sentinel.sh:110-155). Raises on any refusal."""
    bucket = rsv.bucket()
    key = "%s/%s/%s" % (product, version_tag, rsv.SENTINEL_KEY)

    # Defense in depth: never seal a prefix that has no binaries. Writing `.released` over an empty prefix manufactures the corrupt "sealed-but-empty" state (sentinel blocks re-upload, every versioned install 404s).
    bin_count = rsv.binary_count("%s/%s/" % (product, version_tag))
    if bin_count is None:
        # `bin_count="$(rsv_binary_count ...)"` failing under `set -e`. The
        # library has already logged WHY. See FINDING 6.
        raise _ProbeFailedError
    if bin_count <= 0:
        raise SentinelFailedError(
            "refusing to seal %s/%s/: prefix has no binaries (count=%d)."
            % (product, version_tag, bin_count),
            "  Sealing an empty prefix would create the sealed-but-empty corrupt state.",
        )

    payload = build_payload(version_tag, channel, commit_sha, product, released_at_now())

    log.step("writing sentinel: s3://%s/%s" % (bucket, key))
    # `printf '%s' "$payload" | aws s3 cp - s3://...` under `set -euo pipefail`: this script, unlike its two verify- siblings, keeps pipefail ON, so a failing aws aborts the run.
    proc = subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            "-",
            "s3://%s/%s" % (bucket, key),
            "--endpoint-url",
            os.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
            "--cache-control",
            "no-cache",
            "--content-type",
            "application/json",
        ],
        input=payload,
        stdout=None,
        stderr=None,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise _UploadFailedError(proc.returncode)

    # Readback verification: do not trust a silent upload.
    readback = rsv.get_sentinel_payload(product, version_tag)
    if not readback:
        raise SentinelFailedError(
            "sentinel readback failed: s3://%s/%s is missing immediately after write"
            % (bucket, key)
        )
    # Compare the version field; the timestamp may differ by seconds on R2.
    wanted_v = _jq_field(payload, "version")
    got_v = _jq_field(readback, "version")
    if wanted_v != got_v:
        raise SentinelFailedError(
            "sentinel readback content mismatch at s3://%s/%s" % (bucket, key),
            "  wrote version=%s, read back version=%s" % (wanted_v, got_v),
        )
    log.info("  sealed %s/%s/%s" % (product, version_tag, rsv.SENTINEL_KEY))


class _ProbeFailedError(Exception):
    """`rsv_binary_count` could not answer. Exit 1, message already logged."""


class _UploadFailedError(Exception):
    """`aws s3 cp` failed under pipefail. Carries aws's own exit status."""

    def __init__(self, code: int) -> None:
        super().__init__("aws s3 cp exited %d" % code)
        self.code = code


def main(argv: list[str]) -> int:
    try:
        version, channel, commit_sha = parse_flags(argv)
    except UsageError as usage:
        log.error(usage.message)
        return 2
    except _ShiftFailedError:
        return 1

    if not version:
        log.error("--version required")
        return 2
    if not channel:
        log.error("--channel required")
        return 2
    if not commit_sha:
        log.error("--commit-sha required")
        return 2
    if channel not in CHANNELS:
        log.error(
            "sentinel write is only valid on release channels (edge|stable); got: %s" % channel
        )
        return 2

    try:
        common.require_cmd("aws")
        common.require_cmd("jq")
        access_key = common.require_var("CLOUDFLARE_R2_ACCESS_KEY_ID")
        secret_key = common.require_var("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        common.require_var("CLOUDFLARE_R2_ENDPOINT")
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code

    os.environ["AWS_ACCESS_KEY_ID"] = access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    version_tag = "v%s" % version

    try:
        write_sentinel(PRODUCT, version_tag, channel, commit_sha)
    except SentinelFailedError as failure:
        for line in failure.lines:
            log.error(line)
        return 1
    except _ProbeFailedError:
        return 1
    except _UploadFailedError as upload:
        return upload.code

    log.info("release %s on %s is sealed" % (version_tag, channel))

    # Ratchet advance is intentionally NOT done here; cd-v2.yml's tag-and-release
    # job owns `.ci/config/release-contract-floor.txt` and already holds the app-token that can commit it.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/delete-r2-channel.sh`.

Deletes one PR channel's R2 artifacts, plus the `-promoted` copy the promotion-simulation test leaves behind. Runs on PR close: every prefix is attempted whatever an earlier one did, and a channel that was never created is not an error.

Twelve `aws s3 rm --recursive` calls, two per package format:

    s3://$RELEASES_BUCKET/<format>/$CHANNEL/
    s3://$RELEASES_BUCKET/<format>/$CHANNEL-promoted/

for `cli npm apt rpm apk archlinux`, in that order.

NOTHING HERE REACHES R2 IN A TEST. `aws` is the only external tool involved and it carries the credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_delete_r2_channel.py`) puts a RECORDING FAKE `aws` on a scratch PATH that logs its exact argv. The call log is the main evidence for this script: two implementations can print identical output while deleting different
prefixes, and the OBSERVABLE EFFECT of this program is entirely the set of `rm` calls it makes.

`aws` IS SHELLED OUT TO, NOT REPLACED BY `boto3`, and the reason is the same one that keeps `jq` in the Cloudflare siblings: the twin's contract with the tool includes the tool's own stdout (`delete: s3://...` lines a workflow log shows), its exit status, and the `2>/dev/null` that hides its stderr. A boto3 port would have to re-emit all three.

A REFUSED DELETE IS REPORTED AS ONE (Rule T delta, PLAN-retire-bash-oracles B4). The twin ended every call in `2>/dev/null || true` and printed its closing line unconditionally, so an expired key or an `AccessDenied` produced exactly the output of a clean-up that worked: exit 0, twelve silent failures, and a bucket still holding the channel. `|| true` was written for "a channel that was never created is
not an error", and that case never needed it: `aws s3 rm --recursive` over an absent prefix exits 0. This port still attempts all twelve prefixes, then names every refused one with aws's own message, drops the false success line and exits 1. The cases that moved are recorded as intentional deltas in `goldens/twins/deploy.delete-r2-channel.jsonl`, and `test_delta_*` in
`.ci/rediacc_ci/tests/test_deploy_delete_r2_channel.py` fail on the twin's behaviour.

ONE DIVERGENCE, in refusal text nobody parses. The five `: "${VAR:?msg}"` guards
are bash's own diagnostic, `<path>: line 25: CHANNEL: CHANNEL is required (e.g. pr-123)`, carrying the bash file name and a bash line number. This port prints the `VAR: msg` half without the prefix, on the same stream, with the same exit status 1. Identical ruling to `deploy/wait_for_preview_worker.py`. The ORDER of the guards is observable and is kept: `require_cmd aws` runs
FIRST, so a run missing both the binary and every variable names the binary.

`:?` IS AN UNSET-OR-EMPTY TEST, not an unset test: `CHANNEL=` refuses exactly as
an absent CHANNEL does. Reproduced, and driven in the differential, because a port testing `"CHANNEL" in os.environ` would sail past an empty one and then delete `s3://bucket/cli//`, which is every channel's parent prefix.

K=5 LEDGER: `.ci/shadow/w7p6-delete-r2-channel.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import awscli, common

# `for dir in cli npm apt rpm apk archlinux` (:37). ORDER MATTERS to the call log, which is how this port is proved equivalent.
FORMATS = ("cli", "npm", "apt", "rpm", "apk", "archlinux")

# The `-promoted` suffix the promotion-simulation test creates (:41).
PROMOTED_SUFFIX = "-promoted"

# The five `${VAR:?msg}` guards (:25-33), in order, as (name, message). The
# messages are the twin's verbatim, including the two that name the R2_* -> AWS_* bridge -- the header says promote-stable.yml stayed red for seven runs because a missing bridge surfaced as "NoCredentials" instead.
REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("CHANNEL", "CHANNEL is required (e.g. pr-123)"),
    ("RELEASES_BUCKET", "RELEASES_BUCKET is required"),
    ("CLOUDFLARE_R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT is required"),
    (
        "AWS_ACCESS_KEY_ID",
        "AWS_ACCESS_KEY_ID is required (map it from CLOUDFLARE_R2_ACCESS_KEY_ID)",
    ),
    (
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY is required (map it from CLOUDFLARE_R2_SECRET_ACCESS_KEY)",
    ),
)


class MissingEnvError(Exception):
    """One `${VAR:?msg}` firing. Exit 1, message on stderr, nothing else runs."""

    def __init__(self, name: str, message: str) -> None:
        super().__init__("%s: %s" % (name, message))
        self.name = name
        self.message = message


def require_env(env: dict[str, str]) -> dict[str, str]:
    """The five guards, in the twin's order. Returns the five values.

    Raises on the FIRST missing or empty one, because `: "${VAR:?}"` ends the
    shell there and the later guards never run.
    """
    values: dict[str, str] = {}
    for name, message in REQUIRED_ENV:
        value = env.get(name, "")
        if not value:
            raise MissingEnvError(name, message)
        values[name] = value
    return values


def prefixes(bucket: str, channel: str) -> list[str]:
    """The twelve `s3://` prefixes, in the order the twin visits them (:38-42).

    Exposed as a pure helper so the differential can assert the SET as well as compare it against the twin: the observable effect of this program is which prefixes it removes, and a port that reordered them would still print the same two log lines.
    """
    out: list[str] = []
    for fmt in FORMATS:
        out.append("s3://%s/%s/%s/" % (bucket, fmt, channel))
        out.append("s3://%s/%s/%s%s/" % (bucket, fmt, channel, PROMOTED_SUFFIX))
    return out


def aws_argv(prefix: str, endpoint: str) -> list[str]:
    """One `aws s3 rm ... --recursive --endpoint-url ...` (:38-39)."""
    return [awscli.AWS, "s3", "rm", prefix, "--recursive", "--endpoint-url", endpoint]


def _rm(argv: list[str]) -> tuple[int, str]:
    """One `aws s3 rm`, returning its status and its stderr.

    STDOUT IS INHERITED, exactly as the twin leaves it: the `delete: s3://...` lines reach the workflow log. Stderr is captured instead of discarded, because it is the only explanation a refused delete has; a call that succeeded has its stderr dropped, as the twin dropped all of it.
    """
    proc = awscli.run(argv, stderr=subprocess.PIPE)
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    try:
        awscli.require()
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        values = require_env(dict(os.environ))
    except MissingEnvError as exc:
        # THE DIVERGENCE: bash prefixes this with `<path>: line N: `.
        print("%s: %s" % (exc.name, exc.message), file=sys.stderr)
        return 1

    channel = values["CHANNEL"]
    bucket = values["RELEASES_BUCKET"]
    endpoint = values["CLOUDFLARE_R2_ENDPOINT"]

    log.info("Cleaning up R2 channel: %s..." % channel)

    failed: list[str] = []
    for prefix in prefixes(bucket, channel):
        status, stderr = _rm(aws_argv(prefix, endpoint))
        if status:
            failed.append(prefix)
            sys.stderr.write(stderr)
            print(
                "::warning::delete-r2-channel: aws s3 rm %s failed with status %d"
                % (prefix, status),
                file=sys.stderr,
            )

    if failed:
        print(
            "::error::delete-r2-channel: channel '%s' was NOT fully deleted from R2: "
            "%d of %d prefixes failed" % (channel, len(failed), len(FORMATS) * 2),
            file=sys.stderr,
        )
        return 1

    log.info("Channel '%s' (+ promoted) deleted from R2" % channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

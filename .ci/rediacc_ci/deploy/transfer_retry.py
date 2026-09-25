"""A bounded, announced retry for an idempotent R2 transfer (Rule T, worklist #4175e786).

The bash twins run each `aws s3 cp/sync` once under `set -e`, so ONE broken read ends a production promote half-way. Measured twice on 2026-09-24 (M-live item 9, runs 2 and 3): `IncompleteRead` on a large apt pool .deb, a different file each time. A recursive download into a fresh directory, a sync, and a single-object copy are all safe to repeat, and every retry is said out loud on stderr so a flaky path stays visible.

A REFUSAL IS NOT RETRIED (#b22efec4). On 2026-09-24 (M-live item 10) the minted R2 token expired mid-run and the retry spent its remaining attempts, and their delays, on `AccessDenied`. A wrong or expired credential, or a missing bucket, gives the same answer on every try, so `retried` stops on the first one and names it. Transient failures (a broken read, a timeout, a 5xx) keep the retry.

A RETRIED DOWNLOAD MUST RESUME, NOT RESTART (#a8d1d6d0). The promotes used to stage `<dir>/edge/` with `aws s3 cp --recursive`, which fetches every object on every attempt, so on a flaky link each retry drew a fresh broken read on a different file and never got further. Measured 2026-09-25 (M-live item 10 re-run): `rpm/edge` failed 3/3 with `IncompleteRead`, a different `.rpm` each time. They now stage
with `aws s3 sync` into a directory `fresh_stage` emptied once per run, so a retry fetches only what is still missing. Two properties of aws-cli make that safe, both driven against a local fake endpoint with aws-cli 2.36.40 (and read in the awscli 1.46.1 source, `s3transfer/download.py` and `customizations/s3/utils.py`):

  * A BROKEN READ LEAVES NOTHING THAT LOOKS COMPLETE. The body is written to `<name>.<8 random chars>` and renamed only when complete; a failed transfer removes the temporary file. After an `IncompleteRead` the file is simply absent, so the next `sync` fetches it.
  * A COMPLETED FILE IS SKIPPED. aws stamps it with the object's LastModified TRUNCATED TO WHOLE SECONDS, and a download-direction sync skips a same-size local file that is not newer than the object. `--exact-timestamps` would defeat that on a backend whose LastModified carries milliseconds (R2 does): truncated != exact, so every file is fetched again. It is deliberately not used.

The same skip rule is why the stage is emptied BEFORE the first attempt: a same-size, older leftover from an earlier run (the fixed `/tmp/promote-<dir>` outlives a failed run) would be skipped and promoted in place of the current object. Emptying it once per run, and never between attempts, is what keeps the resume and drops the leftover.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ATTEMPTS = 3

# The S3 error codes that no retry can change. Matched in aws's own `An error occurred (<Code>)` form, so a key that merely contains the word does not count.
FATAL_CODES = ("AccessDenied", "InvalidAccessKeyId", "NoSuchBucket", "ExpiredToken")


def fresh_stage(path: str) -> None:
    """Empty `path` and recreate it, once per run before the first download attempt. See the module docstring: a resumable `sync` must not start from an earlier run's leftovers."""
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def fatal_code(stderr: str) -> str:
    """The first non-transient error code named in `stderr`, or "" when there is none."""
    for code in FATAL_CODES:
        if "(%s)" % code in stderr:
            return code
    return ""


def run_captured(argv: list[str]) -> tuple[int, str]:
    """Run `argv` with stdout inherited, and stderr captured AND forwarded unchanged, so the retry can read what failed."""
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run(argv, check=False, stderr=subprocess.PIPE)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.flush()
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def retried(run: Callable[[], tuple[int, str]], what: str, self_name: str, delay_s: float) -> int:
    """Call `run` up to ATTEMPTS times while it fails transiently. Returns the last status.

    `run` returns `(status, stderr)`. A failure whose stderr names a `FATAL_CODES` entry ends the loop at once.
    """
    status, stderr = run()
    for attempt in range(2, ATTEMPTS + 1):
        if status == 0:
            return 0
        code = fatal_code(stderr)
        if code:
            break
        print(
            "%s: %s failed (exit %d), retrying (%d/%d)"
            % (self_name, what, status, attempt, ATTEMPTS),
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay_s)
        status, stderr = run()
    code = fatal_code(stderr) if status else ""
    if code:
        print(
            "%s: %s failed with %s, which a retry cannot change (the R2 credential is wrong or "
            "expired, or the bucket is missing); not retrying" % (self_name, what, code),
            file=sys.stderr,
            flush=True,
        )
    return status

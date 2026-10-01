"""A bounded, announced retry for an idempotent R2 transfer (Rule T, worklist #4175e786).

The bash twins run each `aws s3 cp/sync` once under `set -e`, so ONE broken read ends a production promote half-way. Measured twice on 2026-09-24 (M-live item 9, runs 2 and 3): `IncompleteRead` on a large apt pool .deb, a different file each time. A recursive download into a fresh directory, a sync, and a single-object copy are all safe to repeat, and every retry is said out loud on stderr so a flaky path stays visible.

A REFUSAL IS NOT RETRIED (#b22efec4). On 2026-09-24 (M-live item 10) the minted R2 token expired mid-run and the retry spent its remaining attempts, and their delays, on `AccessDenied`. A wrong or expired credential, or a missing bucket, gives the same answer on every try, so `retried` stops on the first one and names it. Transient failures (a broken read, a timeout, a 5xx) keep the retry.

WHAT IS RETRIED NOW. Since the server-side promote (operator ruling 2026-09-26, `r2_promote.py`) the promotes no longer stage `<dir>/edge/` on the runner, so the resume-versus-restart question the staging download raised (#a8d1d6d0) is gone with it. What remains is per call and idempotent: a listing, one server-side `copy-object`, and a single-file fetch or put of a channel pointer.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ATTEMPTS = 3

# The S3 error codes that no retry can change. Matched in aws's own `An error occurred (<Code>)` form, so a key that merely contains the word does not count.
FATAL_CODES = ("AccessDenied", "InvalidAccessKeyId", "NoSuchBucket", "ExpiredToken")


# What a retry CAN change, as aws prints it. Deliberately a short list: an upload that fails for a reason not named here is reported once and left alone.
TRANSIENT_MARKERS = (
    "IncompleteRead",
    "Connection broken",
    "Connection reset",
    "Read timeout",
    "Connect timeout",
    "Could not connect to the endpoint URL",
    "(InternalError)",
    "(SlowDown)",
    "(ServiceUnavailable)",
    "(RequestTimeout)",
    "(503)",
    "(500)",
    "reached max retries",
)


def is_transient(stderr: str) -> bool:
    """True when `stderr` names a failure class a retry can change, and no refusal (see FATAL_CODES) is named beside it."""
    if fatal_code(stderr):
        return False
    return any(marker in stderr for marker in TRANSIENT_MARKERS)


def fatal_code(stderr: str) -> str:
    """The first non-transient error code named in `stderr`, or "" when there is none."""
    for code in FATAL_CODES:
        if "(%s)" % code in stderr:
            return code
    return ""


def retried(
    run: Callable[[], tuple[int, str]],
    what: str,
    self_name: str,
    delay_s: float,
    *,
    only_transient: bool = False,
) -> int:
    """Call `run` up to ATTEMPTS times while it fails transiently. Returns the last status.

    `run` returns `(status, stderr)`. A failure whose stderr names a `FATAL_CODES` entry ends the loop at once. With `only_transient`, so does any failure that `is_transient` does not recognise: the caller does not know its tool's refusals, so it retries only what it can name.
    """
    status, stderr = run()
    for attempt in range(2, ATTEMPTS + 1):
        if status == 0:
            return 0
        code = fatal_code(stderr)
        if code or (only_transient and not is_transient(stderr)):
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

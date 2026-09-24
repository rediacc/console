"""A bounded, announced retry for an idempotent R2 transfer (Rule T, worklist #4175e786).

The bash twins run each `aws s3 cp/sync` once under `set -e`, so ONE broken read ends a production promote half-way. Measured twice on 2026-09-24 (M-live item 9, runs 2 and 3): `IncompleteRead` on a large apt pool .deb, a different file each time. A recursive download into a fresh directory, a sync, and a single-object copy are all safe to repeat, and every retry is said out loud on stderr so a flaky path stays visible.
"""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ATTEMPTS = 3


def retried(run: Callable[[], int], what: str, self_name: str, delay_s: float) -> int:
    """Call `run` up to ATTEMPTS times while it returns non-zero. Returns the last status."""
    status = run()
    for attempt in range(2, ATTEMPTS + 1):
        if status == 0:
            return 0
        print(
            "%s: %s failed (exit %d), retrying (%d/%d)"
            % (self_name, what, status, attempt, ATTEMPTS),
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay_s)
        status = run()
    return status

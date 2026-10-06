"""Retry a GitHub read through `gh` on a TRANSIENT failure only.

WHY NOT `ghx.gh(attempts=3)`: that retries on ANY non-zero exit (so a 404 or an auth failure costs the full backoff) and its 2 s / 4 s schedule spans six seconds, shorter than a typical GitHub 5xx blip. On 2026-10-06 `check:ci-budget-freshness` failed CI job 112158906504 (run 37429940875) on `gh: Server Error (HTTP 502)` for `.../actions/runs/37247747390/jobs`, after the three immediate attempts all landed inside one outage.

THE POLICY: a failure is retried when its output names a server-side or connection fault (`is_transient`); a 4xx, an auth failure, a rate limit, a timeout and any other failure raise at once. Three attempts, 5 s then 15 s between them. A call that never succeeds returns its LAST `GhResult`, so the caller's `.stdout`/`.json()` raises the typed error naming the final failure.

THE SEAM: `runner` is the one-attempt `gh` call (default `ghx.gh`, looked up at call time) and `sleep` is injectable; tests pass fakes and never touch the network.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from rediacc_ci import proc
from rediacc_ci.core import ghx

if TYPE_CHECKING:
    from collections.abc import Callable

ATTEMPTS = 3
DELAY_S = 5.0
FACTOR = 3.0

# `gh: Server Error (HTTP 502)` is gh's own rendering of any 5xx; the rest are the connection-level faults gh prints verbatim. `stream error` is the 2026-09-27 HTTP/2 CANCEL a budget refresh died on once.
_TRANSIENT_RE = re.compile(
    r"http 5\d\d|server error|bad gateway|service unavailable|gateway time-?out"
    r"|connection reset|stream error|unexpected eof|connection refused|tls handshake timeout",
    re.IGNORECASE,
)


def is_transient(stderr: str) -> bool:
    """True when `stderr` names a 5xx or a connection-level fault. 4xx text never matches."""
    return _TRANSIENT_RE.search(stderr or "") is not None


def retry_transient[T](
    call: Callable[[], T],
    failure_text: Callable[[T], str | None],
    *,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Run `call()` until `failure_text(result)` is None (success) or names a non-transient failure, backing off between transient ones. Returns the last result."""

    nap = sleep or time.sleep
    schedule = proc.backoff_delays(attempts, DELAY_S, FACTOR)
    result = call()
    for pause in schedule:
        text = failure_text(result)
        if text is None or not is_transient(text):
            break
        nap(pause)
        result = call()
    return result


def gh(
    args: list[str],
    *,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    runner: Callable[..., ghx.GhResult] | None = None,
) -> ghx.GhResult:
    """`gh <args>` with transient retry. Never raises for a non-zero exit; read `.stdout`/`.json()`."""
    run = runner or ghx.gh
    return retry_transient(
        lambda: run(args, attempts=1),
        lambda r: None if r.ok else (r.stderr or "failed"),
        attempts=attempts,
        sleep=sleep,
    )


def api_json(
    path: str,
    *,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    runner: Callable[..., ghx.GhResult] | None = None,
) -> Any:
    """`gh api <path>`, retried on transient failure, then parsed. Raises the typed `ghx` error on failure."""
    return gh(["api", path], attempts=attempts, sleep=sleep, runner=runner).json()

"""Port of `.ci/scripts/deploy/wait-for-preview-worker.sh`.

Blocks until a per-PR preview Worker answers both `/health` and `.well-known/server-info` for `REQUIRED_STREAK` consecutive probes. The twin's own header explains why this is testable at all without touching a real Worker: it was written with `PREVIEW_URL_OVERRIDE` / `REQUIRED_STREAK` / `MAX_ATTEMPTS` / `PROBE_INTERVAL_SECONDS` test-only knobs specifically so
`.ci/rediacc_ci/tests/gates/test_gate_preview_readiness.py` can drive it against a local Node HTTP stub. This port reuses exactly that stub technique in `test_deploy_wait_for_preview_worker.py`: no real Cloudflare Worker, no credentials, nothing that leaves this host.

REAL HTTP, NOT A STUBBED BINARY. The external tool the twin shells out to is `curl`, a generic HTTP client with no state and no credential of its own -- unlike `wrangler`/`aws`/`gh`, faking the BINARY would just reimplement `urllib.request` under a different name. So this port makes the HTTP calls directly with `urllib.request`, matching `curl -fsSL`'s semantics (raise on a non-2xx
status, follow redirects, no output), and the differential proves parity by pointing both sides' target URL at the SAME local stub server via `PREVIEW_URL_OVERRIDE`, exactly as the existing bash gate test already does.

REWORDED, NOT BYTE-IDENTICAL, on the missing-PR_NUMBER path only: the twin's
`${VAR:?msg}` diagnostic carries a bash line number that is not worth
reproducing (same reasoning as every other port's module docstring). Every other path -- the per-attempt log lines, the final success/failure line -- is byte-identical, because those are this port's own literal strings, not bash's.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

SELF = "wait-for-preview-worker.py"


def _log(icon: str, message: str) -> None:
    print(f"{icon} {message}", file=sys.stderr)


def _get_ok(url: str, *, timeout: float = 10.0) -> str | None:
    """`curl -fsSL <url>`, quietly: the body on 2xx, None on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            if 200 <= resp.status < 300:
                return resp.read().decode("utf-8", "replace")
            return None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _ready(preview_url: str) -> bool:
    if _get_ok(f"{preview_url}/account/api/v1/health") is None:
        return False
    body = _get_ok(f"{preview_url}/account/api/v1/.well-known/server-info")
    if body is None:
        return False
    return '"publicKeySpki"' in body


def main(argv: list[str]) -> int:
    del argv

    override = os.environ.get("PREVIEW_URL_OVERRIDE", "")
    if override:
        preview_url = override
    else:
        pr_number = os.environ.get("PR_NUMBER", "")
        if not pr_number:
            print(f"{SELF}: PR_NUMBER is required", file=sys.stderr)
            return 1
        preview_url = f"https://pr-{pr_number}.rediacc.workers.dev"

    required_streak = int(os.environ.get("REQUIRED_STREAK", "3"))
    max_attempts = int(os.environ.get("MAX_ATTEMPTS", "60"))
    probe_interval_seconds = float(os.environ.get("PROBE_INTERVAL_SECONDS", "2"))

    streak = 0
    for i in range(1, max_attempts + 1):
        if _ready(preview_url):
            streak += 1
            if streak >= required_streak:
                _log(
                    "✓",
                    f"Preview worker is ready (health + server-info both serving, "
                    f"{required_streak} consecutive probes)",
                )
                return 0
            _log(
                "✓",
                f"Preview worker answered ({streak}/{required_streak} consecutive)... (attempt {i}/{max_attempts})",
            )
        else:
            if streak > 0:
                _log(
                    "⚠",
                    f"Preview worker flapped after {streak} consecutive success(es); "
                    f"streak reset (attempt {i}/{max_attempts})",
                )
            else:
                _log("✓", f"Waiting for preview worker... (attempt {i}/{max_attempts})")
            streak = 0
        time.sleep(probe_interval_seconds)

    _log(
        "✗",
        f"Preview worker did not become ready (never held for {required_streak} consecutive probes)",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

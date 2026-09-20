"""Port of `.ci/scripts/test/assert-r2-sentinel.sh` (77 lines).

The post-upload assertion that a versioned R2 prefix is in a healthy sealed state. It replaced a dead key-based guard that looked at `cli/v${V}/manifest.json`, a file nothing ever wrote, so the sentinel was always empty and retries were free to overwrite published binaries. The twin's header owns that history and it is not restated.

THE PORT LIVES IN `release/`, NOT `test/`, because the twin's directory names its CALLER (`cd-stage.yml`'s test lane) rather than its subject. Its nearest sibling is `reprobe_r2_sentinel`, which probes the same bucket through the same library, and the two belong next to each other.

Ledger: `.ci/shadow/w7p4b-assert-r2-sentinel.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p4b-assert-r2-sentinel --assert --k 5`).

-----------------------------------------------------------------------------
THE THIRD OUTCOME THE TWIN HAS AND NEVER PRINTS
-----------------------------------------------------------------------------
`bin_count="$(rsv_binary_count "$prefix")"` runs under `set -e`, and `rsv_binary_count` returns 1 with EMPTY stdout when the probe could not be answered -- an expired credential, a 5xx, an unparseable count. The assignment therefore fails, `set -e` fires, and the script ends at that line: exit 1, with the library's own probe failure on stderr and none of this file's messages.

In particular the `Versioned release prefix is not in a healthy sealed state.` line, the one a reader greps for, never appears, which is what `quality/silent_failure_patterns.py:15` records as "would have aborted before flagging missing bytes".

That is reproduced rather than improved on. `binary_count` answering `None` is this module's spelling of the same refusal, and the early `return 1` emits nothing of its own.

-----------------------------------------------------------------------------
THE SENTINEL PROBE'S THREE STATES COLLAPSE TO TWO, AND SAFELY
-----------------------------------------------------------------------------
`sentinel_exists` answers YES / NO / UNKNOWN. The twin's `elif rsv_sentinel_exists ...; then` is a two-way branch, so "genuinely absent" (1) and "could not tell" (2) both fall to the `else` arm and both report the empty-prefix failure. The fold is lossy and the loss errs toward failing the job, which is the direction a post-upload assertion must err in; the library still logs its
own reason on the UNKNOWN path, so the distinction survives where a reader can see it.

-----------------------------------------------------------------------------
`BUCKET` IS READ ONCE AND USED ONLY IN PROSE
-----------------------------------------------------------------------------
The twin's `BUCKET` (`:27`) is interpolated into three messages and never reaches an `aws` call; the requests go through the library's own `RSV_BUCKET`, set from the same `RELEASES_BUCKET` default at source time. Two reads of one variable, and `rsv.bucket()` is the spelling that keeps them from drifting.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.core import release_state_validator as rsv

# `:33`. The only two channels that write `cli/v<version>/` at all; anything else is skipped rather than failed.
RELEASE_CHANNELS = ("stable", "edge")

# `:39`. The twin's one non-1 failure code, kept distinct: a missing VERSION is a caller bug, not a bad release.
EXIT_USAGE = 2

EMPTY_CHANNEL = "Channel is empty; skipping sentinel assertion"
NOT_RELEASE_CHANNEL = "Channel '%s' is not a release channel; skipping sentinel assertion"
VERSION_REQUIRED = "VERSION is required for sentinel assertion"
HEALTHY = "s3://%s/%s contains %d binary object(s)"
SEALED_BUT_EMPTY = (
    "SEALED-BUT-EMPTY: s3://%s/%s has a .released sentinel but NO binaries.",
    "  A prior orphan-scrub deleted the bytes; every versioned install of this product will 404.",
    "  Remediation: scrub the sentinel then re-run CI: scripts/ops/scrub-sentinel.sh v%s --execute",
)
NOTHING_UPLOADED = (
    "R2 versioned prefix s3://%s/%s is empty after upload (no binaries, no sentinel).",
    "  The CLI upload loop did not populate the versioned path.",
)
UNHEALTHY = "Versioned release prefix is not in a healthy sealed state."

# `:43-45`, in the twin's order. A refusal names the first missing one only.
REQUIRED_VARS = (
    "CLOUDFLARE_R2_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
    "CLOUDFLARE_R2_ENDPOINT",
)


def _require(fn, *args) -> str | None:
    """`require_cmd` / `require_var`: log the refusal to stderr, exit 1.

    Both helpers in `common.sh` end in `log_error ...; exit 1`, and the message text is the library's, not this file's.
    """
    try:
        return fn(*args)
    except common.RefusalError as exc:
        log.error(str(exc))
        return None


def main(argv: list[str]) -> int:
    channel = argv[0] if len(argv) > 0 else ""
    version = argv[1] if len(argv) > 1 else ""

    # `:29-36`. Both skips are successes: a non-release channel writes no versioned prefix, so there is nothing to assert about it.
    if not channel:
        log.info(EMPTY_CHANNEL)
        return 0
    if channel not in RELEASE_CHANNELS:
        log.info(NOT_RELEASE_CHANNEL % channel)
        return 0
    if not version:
        log.error(VERSION_REQUIRED)
        return EXIT_USAGE

    if _require(common.require_cmd, "aws") is None:
        return 1
    for name in REQUIRED_VARS:
        if _require(common.require_var, name) is None:
            return 1

    # `:47-49`. The library's `aws` children read the process environment two layers down, so the exports have to land in `os.environ` itself.
    os.environ["AWS_ACCESS_KEY_ID"] = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    bucket = rsv.bucket()
    prefix = "cli/v%s/" % version
    # `product="${prefix%%/*}"` (`:59`): everything before the first slash.
    product = prefix.split("/", 1)[0]

    # `:60`. See the module docstring: None is the twin's `set -e` abort, and it prints nothing here because the twin printed nothing there either.
    count = rsv.binary_count(prefix)
    if count is None:
        return 1

    if count > 0:
        log.info(HEALTHY % (bucket, prefix, count))
        return 0

    if rsv.sentinel_exists(product, "v%s" % version) is rsv.Probe.YES:
        log.error(SEALED_BUT_EMPTY[0] % (bucket, prefix))
        log.error(SEALED_BUT_EMPTY[1])
        log.error(SEALED_BUT_EMPTY[2] % version)
    else:
        log.error(NOTHING_UPLOADED[0] % (bucket, prefix))
        log.error(NOTHING_UPLOADED[1])

    log.error(UNHEALTHY)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

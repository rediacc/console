"""Port of `.ci/scripts/release/reprobe-r2-sentinel.sh`.

Re-reads R2 after a sentinel write and asserts the sentinel is really there. The writer short-circuits when a sentinel already exists and swallows several "nothing to do" cases, so trusting its exit code alone would let a backfill report success while the drift the operator ran it for is still present. This probes the live bucket instead.

THE PROBE LIBRARY IS SHARED, NOT RE-DERIVED. The twin sources
`.ci/scripts/lib/release-state-validator.sh` and calls `rsv_sentinel_exists`;
this calls `rediacc_ci.core.release_state_validator.sentinel_exists`, which is that function's already-verified port, down to grepping the captured stderr for `404|Not Found|NoSuchKey` because the aws CLI returns 254 for both a 404 and an auth failure and the exit code genuinely cannot tell them apart.

AND THE THIRD STATE IS DELIBERATELY FOLDED HERE, which is worth saying out loud because the library went to some trouble to keep it separate. `sentinel_exists`
answers YES / NO / UNKNOWN; the twin's `if rsv_sentinel_exists ...; then` is a
two-way branch, so rc=1 (genuinely absent) and rc=2 (could not tell) both land
in the `else` and both print `::error::... NOT present after write`. That is lossy, and the loss is SAFE IN THIS ONE CALLER: an unanswered probe here fails the job, which is the direction a post-write assertion must err in. The port reproduces the fold rather than improving on it, and the library still logs its own "this is NOT evidence that it is missing" line to stderr on the
UNKNOWN path, so the distinction survives where a reader can see it.

ENV IS EXPORTED BY MUTATING `os.environ`, not by building a dict to hand to `subprocess`, because the `aws` calls happen two layers down inside the shared library, which reads `os.environ` itself. The twin's three `export` lines have exactly that reach: they set the process environment every later `aws` child inherits.

ONE PRECONDITION HAS NO PORT: the twin's library refuses to load on bash older than 4.0 (associative arrays), printing four lines and returning 1 at source time -- BEFORE `require_cmd aws`. Python has no equivalent precondition, so on a bash 3.2 host the two sides diverge at the first line. Named rather than simulated: inventing a version refusal the port does not actually have
would be a fiction, and the CI runners are all bash 5.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.core import release_state_validator as rsv

SELF = "reprobe-r2-sentinel.py"

# BLOCKER: the single-element tuple is deliberate and carried over verbatim from the twin (`for product in cli`), which took it verbatim from backfill-release-sentinel.yml -- cli is the only product with `.released` sentinels today, and keeping the loop shape means adding the next one is a one-word edit rather than a restructure.
PRODUCTS = ("cli",)

PRESENT = "✓ %s/%s/%s present in R2"
ABSENT = "::error::%s/%s/%s NOT present after write"


def _require_cmd(name: str) -> int | None:
    """`require_cmd` (common.sh:141-147): log and exit 1, message byte-identical."""
    try:
        common.require_cmd(name)
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1
    return None


def _require_var(name: str) -> str:
    """`${NAME:?message}`: unset AND empty both refuse, with exit 1."""
    value = os.environ.get(name)
    if not value:
        print("%s: %s must be set" % (SELF, name), file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    refusal = _require_cmd("aws")
    if refusal is not None:
        return refusal
    version = _require_var("VERSION")
    access_key = _require_var("CLOUDFLARE_R2_ACCESS_KEY_ID")
    secret_key = _require_var("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    _require_var("CLOUDFLARE_R2_ENDPOINT")

    os.environ["AWS_ACCESS_KEY_ID"] = access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    missing = 0
    for product in PRODUCTS:
        if rsv.sentinel_exists(product, version) is rsv.Probe.YES:
            print(PRESENT % (product, version, rsv.SENTINEL_KEY))
        else:
            print(ABSENT % (product, version, rsv.SENTINEL_KEY))
            missing = 1
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

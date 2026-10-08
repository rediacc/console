"""The sentinel-aware write guard for a versioned release prefix (`cli/v<V>/`).

A versioned prefix is COMMITTED iff a `.released` sentinel exists under it. The sentinel is written by `write_release_sentinel` in the finalize-release-sentinel CI job, only after every CI gate passes (the invariant is `core.release_state_validator`'s).

This guard NEVER deletes from R2. A prior implementation scrubbed "orphan" prefixes (bytes present, no sentinel) at release time via `aws s3 rm --exclude '*.released'`. On a retried or duplicate stage-artifacts run that scrub raced the finalize sentinel write and deleted a SEALED release's binaries while keeping `.released`, the "sealed-but-empty" state that burned v1.1.16 and v1.1.17. Orphan cleanup now lives only in the nightly housekeeping job (`rediacc_ci.housekeeping.cleanup_versions` Phase 8d), off the release critical path.

Answers (the caller branches on them):

  0   PROCEED: no sentinel. A clean prefix, or a byte-only orphan from a cancelled run. Uploading overwrites the deterministic per-version filenames in place; no scrub is needed.
  10  SKIP: the version is already sealed AND its binaries are present. An idempotent rerun of a published version; the caller must not re-upload the immutable versioned path (the immutable-URL promise), but channel pointers still refresh.
  `SealedButEmptyError`  FAIL: sealed but the binaries are missing (the corrupt sealed-but-empty state), which must never be silently overwritten. It is the old guard's `exit 1`: the caller ends the run.

HISTORY. This was the one function the bash-to-Python port deliberately left as bash (the v1.1.16/17 incident), sourced out of `upload-to-r2.sh` and driven by `write_once_guard_check`. Operator ruling D5 (2026-10-08) ported it BEHIND GOLDENS FROZEN FROM THE BASH FIRST: `tests/goldens/twins/deploy.upload-to-r2.jsonl` holds the bash guard's answer (exit code, both streams, the `aws` call sequence) on every branch, and `tests/test_deploy_write_once_guard.py` holds this module to them.

TWO BEHAVIOURS OF THE BASH ARE CARRIED, NOT REPAIRED, and the goldens pin both:
  * A sentinel probe that cannot answer (expired credentials, a 5xx) PROCEEDS. `sentinel_exists` logs why and answers UNKNOWN, which the old `if rsv_sentinel_exists` read as false. Fail-open toward the upload is the safe direction here, since the versioned upload overwrites per-version filenames in place.
  * A sealed version whose binary count CANNOT BE OBTAINED is reported as sealed-but-empty. The old `bin_count="$(rsv_binary_count ...)"` ran under `|| rc=$?`, which suppresses errexit, so the empty string compared as 0. It is fail-closed, so the direction is safe, but the remediation text then names a scrub of a possibly healthy release; the probe's own error line above it is what tells the operator the count never arrived.
"""

from __future__ import annotations

from rediacc_ci import log
from rediacc_ci.core import release_state_validator as rsv

PROCEED = 0
SKIP = 10

# The messages are the bash guard's, byte for byte (the goldens pin them). The dash in the second refusal line is U+2014, built with `chr` so the character is not in this source.
EM_DASH = chr(0x2014)
IDEMPOTENT = (
    "Idempotent: %s is already sealed with %d binary object(s).",
    "  Skipping immutable upload of %s (re-publishing a sealed version is a no-op).",
)
CORRUPT = (
    "Corrupt release state: s3://%s/%s is SEALED (.released present) but has NO binaries.",
    "  This is the 'sealed-but-empty' failure "
    + EM_DASH
    + " a prior run's orphan-scrub deleted the bytes.",
    "  The version cannot be silently re-uploaded (that breaks the immutable-URL promise).",
    "  Remediation: scrub the sentinel, then re-run CI to repopulate the prefix:",
    "    PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel %s --execute",
)


class SealedButEmptyError(Exception):
    """The sealed-but-empty refusal. The old guard called `exit 1` here, ending the whole run."""


def split_prefix(prefix: str) -> tuple[str, str]:
    """`product="${prefix%%/*}"` and `version="${prefix#*/}"; version="${version%/}"`.

    `cli/v1.0.5/` -> (`cli`, `v1.0.5`). A prefix with no slash leaves both expansions at the whole string, because `${x#*/}` removes nothing when the pattern does not match.
    """
    product = prefix.split("/", 1)[0]
    version = prefix.split("/", 1)[1] if "/" in prefix else prefix
    version = version.removesuffix("/")
    return product, version


def write_once_guard(
    prefix: str, context: str, *, endpoint: str, dry_run: bool, bucket: str | None = None
) -> int:
    """Answer 0 (proceed) or 10 (skip), or raise `SealedButEmptyError`.

    `prefix` is e.g. `cli/v1.0.5/` and `context` a human label such as `cli v1.0.5`. `bucket` defaults to the validator's (`RELEASES_BUCKET` or the registry default).
    """
    name = bucket or rsv.bucket()
    if dry_run:
        log.info(
            "[DRY-RUN] sentinel-aware guard would check s3://%s/%s (%s)" % (name, prefix, context)
        )
        return PROCEED

    product, version = split_prefix(prefix)

    if rsv.sentinel_exists(product, version, endpoint) is rsv.Probe.YES:
        count = rsv.binary_count(prefix, endpoint)
        if count is not None and count > 0:
            log.info(IDEMPOTENT[0] % (context, count))
            log.info(IDEMPOTENT[1] % prefix)
            return SKIP
        log.error(CORRUPT[0] % (name, prefix))
        log.error(CORRUPT[1])
        log.error(CORRUPT[2])
        log.error(CORRUPT[3])
        log.error(CORRUPT[4] % version)
        raise SealedButEmptyError(prefix)

    # No sentinel: a clean prefix or a byte-only orphan from a cancelled run. Do NOT scrub; the versioned upload overwrites per-version filenames in place, and nightly housekeeping reaps genuine orphans safely off the release path. This is what eliminates the sealed-but-empty race.
    return PROCEED

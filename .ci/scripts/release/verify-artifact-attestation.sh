#!/bin/bash
# Verify build provenance (SLSA attestation) of the downloaded release artifacts.
#
# WHY: the CLI binaries and packages published by a release are attested at
# build time in CI. Re-verifying them here proves the bytes CD is about to
# publish are the bytes CI produced, not something swapped in between.
#
# HARDENED 2026-08-07. Every `gh attestation verify` failure used to become a
# `::warning::` and the script had no failing exit path at all -- it could not
# fail, for any input, ever. The header called that a "transition period",
# nothing recorded when the period ended, and so it never would. That is the
# same decay that left assert-artifact-version.sh warning-and-passing for its
# entire life while a release published 1.2.16 binaries labelled 1.2.17.
#
# There is no unattestable case left to tolerate: cd-stage.yml attests
# `dist/cli/**/*` and `dist/packages/**/*` -- the exact two trees this script
# walks -- on every push run, which is the only kind of run a release promotes
# from. A missing or invalid attestation therefore means the bytes are not the
# bytes CI produced, and that is a failure, not a note.
#
# Finding nothing to verify is also a failure. `find` over two absent
# directories prints nothing, the loop body never runs, and the old script
# exited 0 having verified precisely zero artifacts -- indistinguishable from
# a clean pass.
#
# Usage:
#   .ci/scripts/release/verify-artifact-attestation.sh
#
# Expects the release artifacts already downloaded into dist/cli and
# dist/packages relative to the repo root.
#
# Required env:
#   GITHUB_REPOSITORY  owner/repo that owns the attestations
#   GH_TOKEN           token for `gh attestation verify`
#
# Run locally, after downloading a run's release-artifacts into dist/:
#   GITHUB_REPOSITORY=rediacc/console \
#     .ci/scripts/release/verify-artifact-attestation.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; every variable is env-wired and there are no pipelines, so
# neither can change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
: "${GITHUB_REPOSITORY:?verify-artifact-attestation.sh: GITHUB_REPOSITORY must be set}"

cd "$(get_repo_root)"

echo "Verifying artifact provenance..."
CHECKED=0
FAILED_COUNT=0
FAILED_LIST=""
# BLOCKER: dist/ paths are build-generated and contain no whitespace, and a find -exec rewrite would lose the per-file pass/fail accounting this step reports on and the CHECKED count that makes "verified nothing" a failure
# shellcheck disable=SC2044
for f in $(find dist/cli dist/packages -type f 2>/dev/null); do
    CHECKED=$((CHECKED + 1))
    if verify_output="$(gh attestation verify "$f" --repo "${GITHUB_REPOSITORY}" 2>&1)"; then
        continue
    fi
    echo "::error::Build attestation verification FAILED for $f"
    echo "$verify_output" >&2
    FAILED_COUNT=$((FAILED_COUNT + 1))
    FAILED_LIST="${FAILED_LIST}  - ${f}"$'\n'
done

if [[ "$CHECKED" -eq 0 ]]; then
    echo "::error::No files found under dist/cli or dist/packages, so NOTHING was verified."
    echo "::error::The release artifacts were expected to be downloaded before this step. Verifying zero artifacts is not a pass."
    exit 1
fi

if [[ "$FAILED_COUNT" -gt 0 ]]; then
    echo "::error::${FAILED_COUNT} of ${CHECKED} release artifacts have no valid build attestation:"
    printf '%s' "$FAILED_LIST" >&2
    echo "::error::These bytes cannot be shown to be the bytes CI produced. Refusing to publish."
    exit 1
fi

echo "::notice::Build provenance verified for all ${CHECKED} release artifacts."

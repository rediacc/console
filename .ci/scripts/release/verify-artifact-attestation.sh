#!/bin/bash
# Verify build provenance (SLSA attestation) of the downloaded release artifacts.
#
# WHY: the CLI binaries and packages published by a release are attested at
# build time in CI. Re-verifying them here proves the bytes CD is about to
# publish are the bytes CI produced, not something swapped in between.
#
# Deliberately NON-blocking: artifacts built before attestation was enabled have
# none, so a missing attestation is a ::warning::, never a failure. This is a
# transition-period stance -- once every artifact in the pipeline carries one,
# turn the warning into a hard failure.
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
FAILED=false
# BLOCKER: loop shape moved verbatim out of cd-v2.yml so release behaviour is bit-identical; dist/ paths are build-generated and contain no whitespace, and a find -exec rewrite would lose the per-file FAILED accounting this step reports on
# shellcheck disable=SC2044
for f in $(find dist/cli dist/packages -type f 2>/dev/null); do
    gh attestation verify "$f" --repo "${GITHUB_REPOSITORY}" 2>/dev/null || {
        echo "::warning::No attestation for $f (expected for first run after attestation is enabled)"
        FAILED=true
    }
done
if [[ "$FAILED" == "true" ]]; then
    echo "::warning::Some artifacts lack attestation — this is expected during the transition period"
fi

#!/bin/bash
# Invoke the release-sentinel writer for an admin backfill, with a dry-run mode.
#
# WHY: this is the only R2-mutating step of the backfill workflow, so it is the
# one that must be trivially previewable. dry_run prints the exact writer
# invocation and exits 0 without touching R2; only an explicit dry_run=false
# (already gated on a typed confirmation input upstream) reaches the writer.
# The writer itself is idempotent, so a repeat run is safe.
#
# Usage:
#   .ci/scripts/release/backfill-write-sentinel.sh
#
# Required env:
#   VERSION       version tag with leading v, e.g. v1.1.2 (stripped for the writer)
#   CHANNEL       release channel: edge | stable
#   COMMIT_SHA    commit to record in the sentinel payload
#   DRY_RUN       "true" prints the invocation and exits 0; anything else writes
#
# Required env when DRY_RUN is not "true" (consumed by the writer):
#   R2_ACCESS_KEY_ID   R2_SECRET_ACCESS_KEY   R2_ENDPOINT
#
# Run locally (safe preview, touches nothing):
#   VERSION=v1.1.2 CHANNEL=edge COMMIT_SHA=deadbeef DRY_RUN=true \
#     .ci/scripts/release/backfill-write-sentinel.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${VERSION:?backfill-write-sentinel.sh: VERSION must be set}"
: "${CHANNEL:?backfill-write-sentinel.sh: CHANNEL must be set}"
: "${COMMIT_SHA:?backfill-write-sentinel.sh: COMMIT_SHA must be set}"
: "${DRY_RUN:?backfill-write-sentinel.sh: DRY_RUN must be set}"

# The writer path is repo-relative, exactly as it was in the workflow step.
cd "$(get_repo_root)"

# Strip leading v for the writer (it expects 1.1.2, not v1.1.2).
NUMERIC_VERSION="${VERSION#v}"
ARGS=(
    --version "$NUMERIC_VERSION"
    --channel "$CHANNEL"
    --commit-sha "$COMMIT_SHA"
)
if [[ "$DRY_RUN" == "true" ]]; then
    echo "→ DRY RUN — would invoke:"
    printf '   .ci/scripts/deploy/write-release-sentinel.sh'
    printf ' %q' "${ARGS[@]}"
    printf '\n'
    echo "→ no R2 mutation performed"
    exit 0
fi
echo "→ writing sentinel(s) for $VERSION on channel $CHANNEL (commit $COMMIT_SHA)"
.ci/scripts/deploy/write-release-sentinel.sh "${ARGS[@]}"

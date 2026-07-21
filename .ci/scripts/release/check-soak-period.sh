#!/bin/bash
# Decide whether the edge release has soaked long enough to become stable.
#
# WHY: stable is edge that nobody complained about. The soak window is the only
# thing separating the two channels, so it is computed from the manifest's own
# releaseDate rather than from anything a dispatcher could get wrong. The
# `force` input exists for the deliberate hotfix case and says so in the log.
#
# The date parse tries GNU `date -d` first and falls back to BSD `date -j -f`,
# so this behaves the same on a Linux runner and on macOS.
#
# Usage:
#   .ci/scripts/release/check-soak-period.sh
#
# Required env:
#   EDGE_DATE       releaseDate from the edge manifest (ISO-8601)
#   SOAK_DAYS       soak window in days (workflow-level env in promote-stable.yml)
#   GITHUB_OUTPUT   step-output file to append ready to
#
# Optional env:
#   FORCE           "true" bypasses the soak window
#
# Run locally:
#   EDGE_DATE=2026-07-01T00:00:00 SOAK_DAYS=7 GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/check-soak-period.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; every variable is env-wired and there are no pipelines, so
# neither can change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${GITHUB_OUTPUT:?check-soak-period.sh: GITHUB_OUTPUT must be set}"
EDGE_DATE="${EDGE_DATE:?check-soak-period.sh: EDGE_DATE must be set}"
SOAK_DAYS="${SOAK_DAYS:?check-soak-period.sh: SOAK_DAYS must be set}"
FORCE="${FORCE:-}"

EDGE_EPOCH=$(date -d "$EDGE_DATE" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$EDGE_DATE" +%s 2>/dev/null)
NOW_EPOCH=$(date +%s)
AGE_DAYS=$(((NOW_EPOCH - EDGE_EPOCH) / 86400))

echo "Edge release age: ${AGE_DAYS} days (soak: ${SOAK_DAYS} days)"

if [[ "$FORCE" == "true" ]]; then
    echo "Force promotion requested, skipping soak check"
    echo "ready=true" >>"$GITHUB_OUTPUT"
elif [[ $AGE_DAYS -lt $SOAK_DAYS ]]; then
    echo "Edge needs $((SOAK_DAYS - AGE_DAYS)) more day(s) of soak"
    echo "ready=false" >>"$GITHUB_OUTPUT"
else
    echo "Soak period complete"
    echo "ready=true" >>"$GITHUB_OUTPUT"
fi

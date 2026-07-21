#!/bin/bash
# Read the live edge CLI manifest and emit the version + release date that the
# stable-promotion decision hangs off.
#
# WHY: the manifest published at releases.rediacc.com is the authoritative
# statement of what edge currently is. Reading it (rather than a git tag or a
# workflow input) means promotion can only ever move bytes that are actually
# serving. A missing manifest is not an error -- a brand-new bucket simply has
# nothing to promote -- so it emits skip=true and exits 0.
#
# Usage:
#   .ci/scripts/release/check-edge-manifest.sh
#
# Required env:
#   GITHUB_OUTPUT   step-output file to append version / date / skip to
#
# Run locally (read-only):
#   GITHUB_OUTPUT=/dev/stdout .ci/scripts/release/check-edge-manifest.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; both `jq` pipelines are assignments whose left side is a
# never-failing `echo`, so pipefail cannot change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl
require_cmd jq
: "${GITHUB_OUTPUT:?check-edge-manifest.sh: GITHUB_OUTPUT must be set}"

EDGE_MANIFEST=$(curl -sf "https://releases.rediacc.com/cli/edge/manifest.json" || echo "")
if [[ -z "$EDGE_MANIFEST" ]]; then
    echo "No edge manifest found, skipping"
    echo "skip=true" >>"$GITHUB_OUTPUT"
    exit 0
fi

EDGE_VERSION=$(echo "$EDGE_MANIFEST" | jq -r '.version')
EDGE_DATE=$(echo "$EDGE_MANIFEST" | jq -r '.releaseDate')
echo "version=$EDGE_VERSION" >>"$GITHUB_OUTPUT"
echo "date=$EDGE_DATE" >>"$GITHUB_OUTPUT"
echo "skip=false" >>"$GITHUB_OUTPUT"

echo "Edge version: $EDGE_VERSION (released: $EDGE_DATE)"

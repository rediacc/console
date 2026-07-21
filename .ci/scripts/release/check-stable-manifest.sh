#!/bin/bash
# Read the live stable CLI manifest and decide whether it already matches edge.
#
# WHY: promotion must be idempotent. The daily schedule fires whether or not
# anything new shipped, so the first question is always "is stable already the
# version edge is on?". If it is, every later step short-circuits and the run
# reports promoted=false rather than re-uploading identical bytes.
#
# A missing stable manifest is not an error -- the very first promotion has
# nothing to compare against -- so STABLE_VERSION stays empty and same=false.
#
# Usage:
#   .ci/scripts/release/check-stable-manifest.sh
#
# Required env:
#   EDGE_VERSION    version currently on edge, from check-edge-manifest.sh
#   GITHUB_OUTPUT   step-output file to append version / same to
#
# Run locally (read-only):
#   EDGE_VERSION=1.2.3 GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/check-stable-manifest.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; the one `jq` pipeline is an assignment whose left side is a
# never-failing `echo`, so pipefail cannot change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl
require_cmd jq
: "${GITHUB_OUTPUT:?check-stable-manifest.sh: GITHUB_OUTPUT must be set}"
EDGE_VERSION="${EDGE_VERSION:?check-stable-manifest.sh: EDGE_VERSION must be set}"

STABLE_MANIFEST=$(curl -sf "https://releases.rediacc.com/cli/stable/manifest.json" || echo "")
STABLE_VERSION=""
if [[ -n "$STABLE_MANIFEST" ]]; then
    STABLE_VERSION=$(echo "$STABLE_MANIFEST" | jq -r '.version')
fi
echo "version=$STABLE_VERSION" >>"$GITHUB_OUTPUT"

if [[ "$STABLE_VERSION" == "$EDGE_VERSION" ]]; then
    echo "Edge and stable are the same version ($STABLE_VERSION), skipping"
    echo "same=true" >>"$GITHUB_OUTPUT"
else
    echo "same=false" >>"$GITHUB_OUTPUT"
fi

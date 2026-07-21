#!/bin/bash
# Pick the deploy script / Worker name / domain / sandbox flag for the www
# Worker, and emit them as step outputs.
#
# WHY: stable serves www.rediacc.com from the rediacc-www Worker and edge serves
# edge.rediacc.com from edge-rediacc-www, via two different wrangler wrappers.
# Resolving the pair once, into named outputs, keeps the deploy / secret /
# webhook steps that follow from each re-deriving it and drifting apart.
#
# Usage:
#   .ci/scripts/deploy/resolve-www-deploy-target.sh
#
# Required env:
#   TARGET          deploy channel: stable | edge
#   GITHUB_OUTPUT   step-output file to append the resolved values to
#
# Outputs: script, worker, domain, sandbox
#
# Run locally (read-only):
#   TARGET=edge GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/deploy/resolve-www-deploy-target.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. Neither can change the outcome: every variable read is
# guarded above, and the script contains no pipeline.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${TARGET:?resolve-www-deploy-target.sh: TARGET must be set}"
: "${GITHUB_OUTPUT:?resolve-www-deploy-target.sh: GITHUB_OUTPUT must be set}"

if [[ "$TARGET" == "stable" ]]; then
    echo "script=deploy-www.sh" >>"$GITHUB_OUTPUT"
    echo "worker=rediacc-www" >>"$GITHUB_OUTPUT"
    echo "domain=www.rediacc.com" >>"$GITHUB_OUTPUT"
    echo "sandbox=" >>"$GITHUB_OUTPUT"
else
    echo "script=deploy-edge.sh" >>"$GITHUB_OUTPUT"
    echo "worker=edge-rediacc-www" >>"$GITHUB_OUTPUT"
    echo "domain=edge.rediacc.com" >>"$GITHUB_OUTPUT"
    echo "sandbox=--sandbox" >>"$GITHUB_OUTPUT"
fi

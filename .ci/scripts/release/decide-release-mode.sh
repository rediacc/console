#!/bin/bash
# Decide which release mode cd-v2.yml runs in, and emit the step outputs the
# rest of the workflow gates on.
#
# WHY: three mutually exclusive paths share one workflow.
#   workers_only : emergency Worker redeploy -- no version bump, no publish.
#   retry        : re-deploy the current tag without bumping.
#   patch        : recompute next_version from PR labels + git tags, publish.
# Encoding that choice once, here, keeps every downstream `if:` reading three
# booleans instead of re-deriving the same precedence rules.
#
# Usage:
#   .ci/scripts/release/decide-release-mode.sh
#
# Required env:
#   DEPLOY_WORKERS_ONLY  "true" selects the workers-only path
#   RELEASE_MODE         "retry" or "patch" (ignored when workers-only)
#   GITHUB_OUTPUT        step-output file to append to
#
# Run locally:
#   DEPLOY_WORKERS_ONLY=false RELEASE_MODE=patch GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/decide-release-mode.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; every variable is env-wired and there are no pipelines, so
# neither can change the outcome.

# NOTE: this script no longer emits `skip_release`. It wrote `false` on all
# three paths, so the ~9 conditions in cd-v2.yml that gated on it were
# permanently true -- and one of that workflow's comments credited it with a
# skip that `workers_only` was actually performing. The real bump-none
# decision lives in .ci/scripts/ci/initialize.sh (step 6b) and gates whether
# cd-v2 is DISPATCHED AT ALL, so by the time this script runs the release has
# already been decided on.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${GITHUB_OUTPUT:?decide-release-mode.sh: GITHUB_OUTPUT must be set}"
DEPLOY_WORKERS_ONLY="${DEPLOY_WORKERS_ONLY:?decide-release-mode.sh: DEPLOY_WORKERS_ONLY must be set}"
RELEASE_MODE="${RELEASE_MODE:-}"

if [[ "$DEPLOY_WORKERS_ONLY" == "true" ]]; then
    echo "retry_mode=false" >>"$GITHUB_OUTPUT"
    echo "workers_only=true" >>"$GITHUB_OUTPUT"
    echo "::notice::Workers-only mode -- deploy Workers without version bump or publish"
    exit 0
fi
echo "workers_only=false" >>"$GITHUB_OUTPUT"

if [[ "$RELEASE_MODE" == "retry" ]]; then
    echo "retry_mode=true" >>"$GITHUB_OUTPUT"
    echo "::notice::Retry mode -- will re-deploy current version without bumping"
else
    echo "retry_mode=false" >>"$GITHUB_OUTPUT"
    echo "::notice::Release mode: ${RELEASE_MODE} bump -- will create new release"
fi

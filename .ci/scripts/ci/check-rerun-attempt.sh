#!/bin/bash
# Defense-in-depth cap on automatic rerun attempts.
#
# The watchdog already stops retrying after attempt 2, but it is AI-driven and a
# misclassification could loop. This is the dumb, deterministic backstop: read
# the run's current attempt and refuse to rerun at or past the cap.
#
# Writes WATCHDOG_SKIP_RERUN=true|false to $GITHUB_ENV for the following step to gate
# on. The name is the CONSUMER's, spelled once: watchdog-monitor.cjs reads it under
# exactly that name, and a shorter one here would mean two spellings for one value.
#
# Usage:
#   RUN_ID=123456 GH_REPO=rediacc/console GH_TOKEN=... \
#     .ci/scripts/ci/check-rerun-attempt.sh
#
# Required env:
#   RUN_ID     the workflow run to inspect
#   GH_REPO    owner/repo
#   GH_TOKEN   token for `gh api` (secret — env, never argv)
# Optional env:
#   MAX_ATTEMPTS   default 2
#   GITHUB_ENV     when set, WATCHDOG_SKIP_RERUN is exported to later steps

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
: "${RUN_ID:?RUN_ID is required}"
: "${GH_REPO:?GH_REPO is required}"

MAX_ATTEMPTS="${MAX_ATTEMPTS:-2}"

echo "::group::Fetching run details"
log_info "Run ID: ${RUN_ID}"
ATTEMPT="$(gh api "repos/${GH_REPO}/actions/runs/${RUN_ID}" --jq '.run_attempt')"
log_info "Current run attempt: ${ATTEMPT}"
echo "::endgroup::"

if [[ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]]; then
    log_warn "Run attempt ${ATTEMPT} >= max ${MAX_ATTEMPTS} - skipping rerun (defense-in-depth)"
    SKIP="true"
else
    log_info "Run attempt ${ATTEMPT} < max ${MAX_ATTEMPTS} - rerun is allowed"
    SKIP="false"
fi

[[ -n "${GITHUB_ENV:-}" ]] && echo "WATCHDOG_SKIP_RERUN=${SKIP}" >>"$GITHUB_ENV"

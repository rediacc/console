#!/bin/bash
# The body of the `CI Complete` gate: fail unless every CI job reached an
# acceptable conclusion.
#
# Two tiers, and the distinction is load-bearing:
#   HARD-REQUIRED  must be exactly "success". These never legitimately skip, so
#                  a skip means the DAG broke and must not read as green.
#   SOFT-REQUIRED  "success" or "skipped" both pass; only "failure" blocks.
#                  These are event-gated (pull_request-only jobs skip on
#                  push-to-main, full_suite jobs skip on merge, and so on).
#
# Every conclusion arrives as an env var so the script is runnable and testable
# outside Actions. An unset variable is treated as a failure rather than
# silently passing -- a renamed job must break loudly here.
#
# Usage (as CI does it, one env var per job):
#   RESULT_INITIALIZE=success RESULT_BUILD_DOCKER=success ... \
#     .ci/scripts/ci/assert-ci-complete.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

HARD_REQUIRED=(INITIALIZE BUILD_DOCKER BUILD_DOCKER_FAST BUILD_CLI)
# MIGRATION_TEST is deliberately absent: it moved from a top-level ci.yml job
# into ct-tests.yml, so its result now rolls up through TESTS. A failing
# migration fails the `tests` reusable workflow, which fails RESULT_TESTS here.
# BREAKPOINT_LIFECYCLE is SOFT, not HARD: it is gated on full_suite
# (github.event_name != 'push'), so it legitimately skips on push-to-main.
# Soft still blocks on "failure" -- which is what matters, because a failing
# lifecycle test means the debug box's teardown cannot be trusted.
# LABEL_GUIDE is SOFT: the job is gated on `github.event_name == 'pull_request'`
# (it comments on a PR, and a push-to-main has none), so it legitimately skips on
# every non-PR event. Soft still blocks on "failure", which is the half that
# matters here: a commenter that throws means .github/labels.yml stopped parsing,
# and that same file feeds the label-inventory gate.
SOFT_REQUIRED=(
    QUALITY REVIEW_GATE STRIPE_SANDBOX PACKAGE_TESTS STAGE_ARTIFACTS
    LABEL_GUIDE
    VALIDATE_INSTALL VALIDATE_PROMOTE TESTS ELITE_RUN_TEST OPS_TESTS
    UPDATE_FLOW_TEST DEPLOY_PREVIEW SMOKE_TEST_PREVIEW BREAKPOINT_LIFECYCLE
    CHECK_RELEASE_STATE
)

# Pointer-bump fast path (see .ci/scripts/ci/detect-pointer-bump.sh): the PR
# head is content-identical to a commit that already passed full CI, and the
# build jobs are DELIBERATELY skipped by ci.yml. Their skips must read as
# green here; a genuine failure of any of them still blocks (soft tier only
# forgives "skipped", never "failure").
if [[ "${POINTER_BUMP_ONLY:-}" == "true" ]]; then
    HARD_REQUIRED=(INITIALIZE)
    SOFT_REQUIRED+=(BUILD_DOCKER BUILD_DOCKER_FAST BUILD_CLI)
fi

failed=false

for job in "${HARD_REQUIRED[@]}"; do
    var="RESULT_${job}"
    value="${!var:-<unset>}"
    if [[ "$value" != "success" ]]; then
        log_error "${job}: ${value} (hard-required, must be 'success')"
        failed=true
    fi
done

for job in "${SOFT_REQUIRED[@]}"; do
    var="RESULT_${job}"
    value="${!var:-<unset>}"
    case "$value" in
        success | skipped) ;;
        *)
            log_error "${job}: ${value} (soft-required, must be 'success' or 'skipped')"
            failed=true
            ;;
    esac
done

if [[ "$failed" == "true" ]]; then
    log_error "One or more CI jobs did not reach an acceptable conclusion (see above)"
    exit 1
fi

log_info "All CI jobs passed successfully!"

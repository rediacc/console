#!/bin/bash
# Assert that an upstream job concluded as 'success'. Intended for
# downstream sentinel jobs that must detect the GHA transitive-skip
# propagation bug (finding J): when a job in the needs chain silently
# skips, downstream jobs without always() quietly skip too. A sentinel
# using this script will fail loudly instead.
#
# Usage: assert-job-succeeded.sh <job_label> <result>
#
# Example (from ci.yml):
#   run: .ci/scripts/ci/assert-job-succeeded.sh housekeeping "${{ needs.housekeeping.result }}"

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

JOB_LABEL="${1:-}"
RESULT="${2:-}"

if [[ -z "$JOB_LABEL" ]]; then
    log_error "Usage: $0 <job_label> <result>"
    exit 2
fi

log_info "${JOB_LABEL} result: ${RESULT}"

if [[ "$RESULT" == "success" ]]; then
    exit 0
fi

log_error "${JOB_LABEL} did not succeed (result=${RESULT})."
log_error "  This usually indicates GHA transitive-skip propagation."
log_error "  Check the if: on the ${JOB_LABEL} job has always() prefixed"
log_error "  so skips in its needs chain cannot silently disable it."
exit 1

#!/bin/bash
# Assert that an upstream job was not silently skipped by the GHA
# transitive-skip propagation bug (finding J): when a job in the needs
# chain skips, downstream jobs without always() quietly skip too. This
# sentinel catches that regression at runtime on push-to-main.
#
# Result handling:
#   success              : pass
#   skipped              : FAIL (the bug is back; fix the upstream if:)
#   cancelled / failure  : pass. cancelled is an externally-imposed signal
#                          (CI watchdog force-cancel, concurrent-push
#                          auto-cancel, manual cancel); failure is already
#                          surfaced by the upstream job itself. Neither is
#                          the class of bug this sentinel guards against.
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

case "$RESULT" in
    success)
        exit 0
        ;;
    skipped)
        log_error "${JOB_LABEL} was skipped. This is the GHA transitive-skip propagation bug (finding J)."
        log_error "  Some job in ${JOB_LABEL}'s needs chain skipped and GH Actions propagated"
        log_error "  the skip through to ${JOB_LABEL}. Prefix the if: on the ${JOB_LABEL} job"
        log_error "  with 'always() &&' so skips in its needs chain cannot silently disable it."
        log_error "  The static audit .ci/scripts/security/check-workflow-gates.sh should also"
        log_error "  have caught this; investigate why it did not."
        exit 1
        ;;
    cancelled | failure)
        log_warn "${JOB_LABEL} result=${RESULT}; treating as externally-imposed or already-surfaced."
        log_warn "  Sentinel only fails on 'skipped' (the transitive-skip propagation signature)."
        log_warn "  cancelled => CI watchdog, concurrent-push auto-cancel, or manual cancel."
        log_warn "  failure   => ${JOB_LABEL} already reported its own failure; no need to pile on."
        exit 0
        ;;
    *)
        log_error "${JOB_LABEL} has unexpected result='${RESULT}' (not success/skipped/cancelled/failure)."
        log_error "  Update assert-job-succeeded.sh to handle this state explicitly."
        exit 1
        ;;
esac

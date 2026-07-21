#!/bin/bash
# Block until the per-PR preview Worker answers its health endpoint.
#
# Cloudflare propagates a new Worker version asynchronously, so the deploy step
# returning is not the same as the Worker serving. 30 attempts, 2s apart.
#
# Usage:
#   PR_NUMBER=123 .ci/scripts/deploy/wait-for-preview-worker.sh
#
# Required env:
#   PR_NUMBER   preview worker is named pr-<PR_NUMBER>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl
: "${PR_NUMBER:?PR_NUMBER is required}"

PREVIEW_URL="https://pr-${PR_NUMBER}.rediacc.workers.dev"

for i in $(seq 1 30); do
    if curl -fsSL "${PREVIEW_URL}/account/api/v1/health" -o /dev/null 2>/dev/null; then
        log_info "Preview worker is ready"
        exit 0
    fi
    log_info "Waiting for preview worker... (attempt $i/30)"
    sleep 2
done

log_error "Preview worker did not become ready"
exit 1

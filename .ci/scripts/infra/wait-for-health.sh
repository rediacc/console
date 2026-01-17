#!/bin/bash
# Wait for a service health endpoint to become available
# Usage: wait-for-health.sh --url <health_url> [options]
#
# Polls an HTTP endpoint until it returns a successful response.
# Useful for waiting for services to start up.
#
# Options:
#   --url       Health endpoint URL (required)
#   --timeout   Maximum wait time in seconds (default: 120)
#   --interval  Polling interval in seconds (default: 2)
#   --message   Custom success message (default: "Service is ready")
#
# Example:
#   .ci/scripts/infra/wait-for-health.sh --url http://localhost/health --timeout 120
#   .ci/scripts/infra/wait-for-health.sh --url http://localhost:7322/api/health

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

URL="${ARG_URL:-}"
TIMEOUT="${ARG_TIMEOUT:-120}"
INTERVAL="${ARG_INTERVAL:-2}"
MESSAGE="${ARG_MESSAGE:-Service is ready}"

# Validate required arguments
if [[ -z "$URL" ]]; then
    log_error "Usage: wait-for-health.sh --url <health_url> [--timeout <seconds>] [--interval <seconds>]"
    exit 1
fi

require_cmd curl

log_step "Waiting for $URL (timeout: ${TIMEOUT}s)..."

ELAPSED=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    if curl -sf "$URL" > /dev/null 2>&1; then
        log_info "$MESSAGE"
        exit 0
    fi

    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
    log_debug "Waiting... (${ELAPSED}s / ${TIMEOUT}s)"
done

log_error "Timeout: $URL did not become available within ${TIMEOUT}s"
exit 1

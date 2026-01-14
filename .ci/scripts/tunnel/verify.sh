#!/bin/bash
# Verify tunnel connectivity via health endpoint
# Usage: verify.sh --url <tunnel_url> [--max-attempts <n>] [--interval <seconds>]
#
# Example:
#   .ci/scripts/tunnel/verify.sh --url https://my-tunnel.trycloudflare.com

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

TUNNEL_URL="${ARG_URL:-}"
MAX_ATTEMPTS="${ARG_MAX_ATTEMPTS:-10}"
INTERVAL="${ARG_INTERVAL:-5}"

# Validate required arguments
if [[ -z "$TUNNEL_URL" ]]; then
    log_error "Usage: verify.sh --url <tunnel_url> [--max-attempts <n>] [--interval <seconds>]"
    exit 1
fi

# Ensure URL doesn't have trailing slash for consistent /health check
TUNNEL_URL="${TUNNEL_URL%/}"
HEALTH_URL="${TUNNEL_URL}/health"

log_step "Verifying tunnel connectivity: $HEALTH_URL"

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    log_debug "Attempt $attempt/$MAX_ATTEMPTS..."

    # Use curl on Unix, handle both success and HTTP status
    if curl -sf --max-time 10 "$HEALTH_URL" > /dev/null 2>&1; then
        log_info "Tunnel connectivity verified"
        exit 0
    fi

    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
        log_warn "Attempt $attempt/$MAX_ATTEMPTS failed, retrying in ${INTERVAL}s..."
        sleep "$INTERVAL"
    fi
done

log_error "Could not connect to tunnel after $MAX_ATTEMPTS attempts"

# Add detailed error output for debugging
echo ""
echo "=== Verbose Connection Attempt ==="
echo "URL: $HEALTH_URL"
echo ""
curl -v --max-time 10 "$HEALTH_URL" 2>&1 | head -50 || true
echo ""
echo "==================================="

exit 1

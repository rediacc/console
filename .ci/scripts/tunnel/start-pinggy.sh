#!/bin/bash
# Start a Pinggy tunnel and output the public URL.
# Usage: start-pinggy.sh --port <local_port> [--timeout <seconds>]
#
# Starts SSH tunnel in background. Parses the HTTPS URL from output.
# Retries up to MAX_RETRIES times on failure (SSH exit, timeout).
# Exits 0 with URL on stdout, or 1 if all attempts fail.
#
# Example:
#   PINGGY_URL=$(start-pinggy.sh --port 80)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

PORT="${ARG_PORT:-80}"
TIMEOUT="${ARG_TIMEOUT:-60}"
LOG_FILE="$(get_temp_dir)/pinggy.log"
MAX_RETRIES=3
RETRY_DELAY=10

log_step "Starting Pinggy tunnel (port: $PORT, timeout: ${TIMEOUT}s, max retries: $MAX_RETRIES)..." >&2

for retry in $(seq 1 "$MAX_RETRIES"); do
    # Clear log file for this attempt
    : >"$LOG_FILE"

    # Start SSH tunnel in background, capture output
    ssh -p 443 \
        -R0:localhost:"${PORT}" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -o ConnectTimeout=15 \
        -o LogLevel=ERROR \
        -tt free.pinggy.io \
        : >"$LOG_FILE" 2>&1 &

    PINGGY_PID=$!
    echo "$PINGGY_PID" >"$(get_temp_dir)/pinggy.pid"

    # Wait for HTTPS URL to appear in output
    ELAPSED=0
    INTERVAL=2
    while [[ $ELAPSED -lt $TIMEOUT ]]; do
        URL=$(grep -oE 'https://[a-zA-Z0-9._-]+\.free\.pinggy\.(link|io)' "$LOG_FILE" 2>/dev/null | head -1 || true)
        if [[ -n "$URL" ]]; then
            log_info "Pinggy tunnel established: $URL (attempt $retry)" >&2
            echo "$URL"
            exit 0
        fi

        # Check if SSH process is still running
        if ! kill -0 "$PINGGY_PID" 2>/dev/null; then
            log_warn "Pinggy SSH process exited unexpectedly (attempt $retry/$MAX_RETRIES)" >&2
            cat "$LOG_FILE" >&2 || true
            break
        fi

        sleep "$INTERVAL"
        ELAPSED=$((ELAPSED + INTERVAL))
    done

    # Clean up this attempt
    kill "$PINGGY_PID" 2>/dev/null || true
    wait "$PINGGY_PID" 2>/dev/null || true

    if [[ $retry -lt $MAX_RETRIES ]]; then
        log_warn "Pinggy tunnel attempt $retry failed, retrying in ${RETRY_DELAY}s..." >&2
        sleep "$RETRY_DELAY"
    fi
done

log_error "Pinggy tunnel failed after $MAX_RETRIES attempts" >&2
cat "$LOG_FILE" >&2 || true
exit 1

#!/bin/bash
# Start a Pinggy tunnel and output the public URL.
# Usage: start-pinggy.sh --port <local_port> [--timeout <seconds>]
#
# Starts SSH tunnel in background. Parses the HTTPS URL from output.
# Exits 0 with URL on stdout, or 1 if URL not obtained within timeout.
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

log_step "Starting Pinggy tunnel (port: $PORT, timeout: ${TIMEOUT}s)..." >&2

# Start SSH tunnel in background, capture output
ssh -p 443 \
  -R0:localhost:"${PORT}" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o LogLevel=ERROR \
  -tt free.pinggy.io \
  > "$LOG_FILE" 2>&1 &

PINGGY_PID=$!
echo "$PINGGY_PID" > "$(get_temp_dir)/pinggy.pid"

# Wait for HTTPS URL to appear in output
ELAPSED=0
INTERVAL=2
while [[ $ELAPSED -lt $TIMEOUT ]]; do
  URL=$(grep -oE 'https://[a-zA-Z0-9._-]+\.free\.pinggy\.(link|io)' "$LOG_FILE" 2>/dev/null | head -1 || true)
  if [[ -n "$URL" ]]; then
    log_info "Pinggy tunnel established: $URL" >&2
    echo "$URL"
    exit 0
  fi

  # Check if SSH process is still running
  if ! kill -0 "$PINGGY_PID" 2>/dev/null; then
    log_error "Pinggy SSH process exited unexpectedly" >&2
    cat "$LOG_FILE" >&2 || true
    exit 1
  fi

  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

log_error "Pinggy tunnel URL not obtained within ${TIMEOUT}s" >&2
cat "$LOG_FILE" >&2 || true
kill "$PINGGY_PID" 2>/dev/null || true
exit 1

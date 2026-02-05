#!/bin/bash
# Start a Cloudflare Quick Tunnel and output the public URL.
# Usage: start-cloudflare.sh --url <local_url> [--timeout <seconds>]
#
# Installs cloudflared if not present, starts a quick tunnel in background.
# Parses the HTTPS URL from log output and verifies health.
# Exits 0 with URL on stdout, or 1 if URL not obtained within timeout.
#
# Example:
#   TUNNEL_URL=$(start-cloudflare.sh --url http://localhost --timeout 60)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

URL="${ARG_URL:-http://localhost}"
TIMEOUT="${ARG_TIMEOUT:-60}"
LOG_FILE="$(get_temp_dir)/cloudflared.log"

log_step "Starting Cloudflare tunnel (url: $URL, timeout: ${TIMEOUT}s)..." >&2

# Install cloudflared if not present
if ! command -v cloudflared &>/dev/null; then
    log_info "Installing cloudflared..." >&2
    local_deb="$(get_temp_dir)/cloudflared.deb"
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb" \
        -o "$local_deb"
    sudo dpkg -i "$local_deb" >/dev/null 2>&1
    rm -f "$local_deb"
    log_info "cloudflared installed: $(cloudflared --version)" >&2
fi

# Start cloudflared tunnel in background, capture output
cloudflared tunnel --url "$URL" >"$LOG_FILE" 2>&1 &

CF_PID=$!
echo "$CF_PID" >"$(get_temp_dir)/cloudflared.pid"

# Wait for HTTPS URL to appear in output
ELAPSED=0
INTERVAL=2
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1 || true)
    if [[ -n "$TUNNEL_URL" ]]; then
        # Verify tunnel health
        if curl -sf --max-time 10 "$TUNNEL_URL/health" >/dev/null 2>&1; then
            log_info "Cloudflare tunnel established and verified: $TUNNEL_URL" >&2
            echo "$TUNNEL_URL"
            exit 0
        fi
        log_info "Tunnel URL found but health check pending..." >&2
    fi

    # Check if cloudflared process is still running
    if ! kill -0 "$CF_PID" 2>/dev/null; then
        log_error "cloudflared process exited unexpectedly" >&2
        cat "$LOG_FILE" >&2 || true
        exit 1
    fi

    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

log_error "Cloudflare tunnel URL not obtained within ${TIMEOUT}s" >&2
cat "$LOG_FILE" >&2 || true
kill "$CF_PID" 2>/dev/null || true
exit 1

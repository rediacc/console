#!/bin/bash
# Select the first healthy tunnel from a list of URLs.
# Usage: select-tunnel.sh [--url <url>]... [--max-attempts <n>] [--interval <s>]
#
# Tests each URL's /health endpoint. Outputs the first responsive URL.
# Retries the full list up to max-attempts times (default: 10).
#
# Example:
#   TUNNEL_URL=$(select-tunnel.sh \
#     --url "https://abc.trycloudflare.com" \
#     --url "https://xyz.free.pinggy.link")

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse URLs (can't use parse_args for repeated --url flags)
URLS=()
MAX_ATTEMPTS=10
INTERVAL=5

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)
            if [[ -n "${2:-}" ]] && [[ "$2" != "--"* ]]; then
                URLS+=("$2")
                shift 2
            else
                shift
            fi
            ;;
        --max-attempts)
            MAX_ATTEMPTS="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Filter out empty URLs
VALID_URLS=()
for url in "${URLS[@]}"; do
    if [[ -n "$url" ]]; then
        VALID_URLS+=("$url")
    fi
done

if [[ ${#VALID_URLS[@]} -eq 0 ]]; then
    log_error "No tunnel URLs provided"
    exit 1
fi

log_step "Selecting tunnel from ${#VALID_URLS[@]} candidate(s)..." >&2

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    for url in "${VALID_URLS[@]}"; do
        HEALTH_URL="${url%/}/health"
        if curl -sf --max-time 10 "$HEALTH_URL" > /dev/null 2>&1; then
            log_info "Selected tunnel: $url (attempt $attempt)" >&2
            echo "$url"
            exit 0
        fi
        log_debug "  $url - not responding" >&2
    done

    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
        log_warn "No healthy tunnel found (attempt $attempt/$MAX_ATTEMPTS), retrying in ${INTERVAL}s..." >&2
        sleep "$INTERVAL"
    fi
done

log_error "No healthy tunnel found after $MAX_ATTEMPTS attempts" >&2
log_error "Tested URLs:" >&2
for url in "${VALID_URLS[@]}"; do
    log_error "  - $url" >&2
    echo "" >&2
    echo "=== Verbose connection attempt: ${url%/}/health ===" >&2
    curl -v --max-time 10 "${url%/}/health" 2>&1 | head -30 >&2 || true
    echo "==================================" >&2
done
exit 1

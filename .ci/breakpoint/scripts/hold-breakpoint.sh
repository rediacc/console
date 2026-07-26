#!/bin/bash
# Hold the session open for its duration, then return so teardown can run.
#
# WHY THIS IS A SCRIPT AND NOT AN INLINE `run:` BLOCK
# .ci/scripts/quality/check-workflows.sh enforces INLINE_MAX_LOGIC=8 logic lines
# per `run:` block, with "no baseline and no grandfathering" in its own words.
# The old standalone-run.yml's "Display Access Information and Keep Services
# Alive" block was roughly 90 logic lines and could not come back in that shape.
#
# TWO BEHAVIOURAL FIXES vs that block:
#
# 1. It health-checks the LOCAL ORIGIN, not the public URL. A Cloudflare edge
#    blip must not read as "the services are down", and in named mode the public
#    URL correctly answers 302 to an unauthenticated curl, which the old check
#    would have counted as failure forever.
#
# 2. It NEVER exits non-zero for a failed health check. A breakpoint session
#    whose app is unhealthy is precisely the session you want kept alive to look
#    at. It warns, dumps context, and keeps holding.
#
# Usage:
#   hold-breakpoint.sh --duration-min <n> [--origin http://localhost:8080]
#                      [--check-interval 60]
# Exit: 0 when the duration elapses.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

parse_args "$@"

DURATION_MIN="${ARG_DURATION_MIN:-30}"
ORIGIN="${ARG_ORIGIN:-http://localhost:8080}"
INTERVAL="${ARG_CHECK_INTERVAL:-60}"

if [[ ! "$DURATION_MIN" =~ ^[0-9]+$ ]] || [[ "$DURATION_MIN" -lt 1 ]]; then
    log_error "--duration-min must be a positive integer, got '$DURATION_MIN'"
    exit 4
fi

DURATION_SEC=$((DURATION_MIN * 60))
START_EPOCH="$(date +%s)"
END_EPOCH=$((START_EPOCH + DURATION_SEC))

# Publish the deadline so a human who ssh'd in can see when the box dies without
# having to work it out from the workflow start time.
bp_state_set BP_HOLD_DEADLINE "$END_EPOCH"
echo "$END_EPOCH" >"$(bp_state_dir)/hold-deadline"

log_info "holding for ${DURATION_MIN} minutes (until $(date -u -d "@${END_EPOCH}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "epoch ${END_EPOCH}"))"

unhealthy_streak=0

while true; do
    now="$(date +%s)"
    [[ $now -ge $END_EPOCH ]] && break

    remaining=$((END_EPOCH - now))
    sleep_for=$INTERVAL
    [[ $remaining -lt $sleep_for ]] && sleep_for=$remaining
    sleep "$sleep_for"

    # Same trap as start-tunnel.sh: curl -w '%{http_code}' prints 000 AND exits
    # non-zero on failure, so `|| echo 000` would yield "000000". Use || true.
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${ORIGIN}/health" 2>/dev/null || true)"
    [[ -n "$code" ]] || code="000"

    if [[ "$code" == "200" ]]; then
        unhealthy_streak=0
    else
        unhealthy_streak=$((unhealthy_streak + 1))
        log_warn "origin health check returned ${code} (streak ${unhealthy_streak}); the session stays up regardless"
        if [[ $unhealthy_streak -eq 1 ]]; then
            # Dump context ONCE per outage rather than every interval, so a
            # long unhealthy stretch does not bury the log.
            if command -v docker >/dev/null 2>&1; then
                docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null >&2 || true
            fi
        fi
    fi

    mins_left=$(((END_EPOCH - $(date +%s)) / 60))
    [[ $mins_left -ge 0 ]] && log_debug "${mins_left} minutes remaining"
done

log_info "duration elapsed; the session is finishing and teardown will run next"

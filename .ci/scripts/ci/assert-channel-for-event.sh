#!/bin/bash
# Assert that the resolved CHANNEL matches the GitHub event type.
#
# Guards against reintroducing the dryrun-<sha> fallthrough for schedule
# events (finding G). Any non-empty channel on those events would resume
# producing ~5 GB of orphan R2 bytes per trigger.
#
# Usage: assert-channel-for-event.sh <event_name> <channel>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

EVENT="${1:-}"
CHANNEL="${2-}"

if [[ -z "$EVENT" ]]; then
    log_error "Usage: $0 <event_name> <channel>"
    exit 2
fi

case "$EVENT" in
    schedule)
        if [[ -n "$CHANNEL" ]]; then
            log_error "Channel must be empty for $EVENT events (got: $CHANNEL)."
            log_error "  schedule must not produce R2 uploads."
            exit 1
        fi
        ;;
    push)
        if [[ "$CHANNEL" != "edge" ]]; then
            log_error "push events must resolve to edge channel (got: '$CHANNEL')."
            exit 1
        fi
        ;;
    pull_request)
        if [[ ! "$CHANNEL" =~ ^pr-[0-9]+$ ]]; then
            log_error "pull_request events must resolve to pr-N channel (got: '$CHANNEL')."
            exit 1
        fi
        ;;
    workflow_dispatch)
        # The nightly rehearsal (ci.yml, guarded to main). It must be
        # schedule-equivalent, and the half of that which matters here is
        # producing NO R2 bytes.
        #
        # This arm is not optional tidiness. The `*)` arm below warns and
        # ACCEPTS, so without an explicit arm the rehearsal would have landed
        # unasserted -- a new, human-triggerable, full-pipeline entry point
        # silently exempt from the one guard that exists to stop orphan R2
        # uploads. That guard was added because a previous design set
        # dryrun-<sha> here and produced ~5 GB of orphan bytes per trigger.
        if [[ -n "$CHANNEL" ]]; then
            log_error "Channel must be empty for $EVENT events (got: $CHANNEL)."
            log_error "  The nightly rehearsal must not produce R2 uploads."
            exit 1
        fi
        ;;
    *)
        log_warn "Unknown event: $EVENT (channel: '$CHANNEL'); accepting without assertion"
        ;;
esac

log_info "Channel '${CHANNEL:-<empty>}' matches event '${EVENT}'"

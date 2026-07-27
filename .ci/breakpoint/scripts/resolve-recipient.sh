#!/bin/bash
# Map a GitHub actor to an email address, from breakpoint.conf.
#
# The deleted .ci/scripts/infra/send-access-email.sh had this as a hardcoded
# six-name `case` in the script body. The mechanism was right -- it worked, and
# it is a real security control (see publish-endpoints.sh) -- but a hardcoded
# map cannot be vendored into a repo with different people, so the map moves to
# conf while the behaviour stays identical.
#
# Usage:  resolve-recipient.sh --actor <github-login>
# Stdout: the email address, or NOTHING when unmapped.
# Exit:   0 resolved, 1 unmapped (NOT an error: the caller falls back to the
#         logs channel), 4 bad arguments.
#
# An unmapped actor must never be fatal on its own. The old script got this
# right too: it warned and set EMAIL_SENT=false rather than failing the run.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

ACTOR="${ARG_ACTOR:-${GITHUB_ACTOR:-}}"

if [[ -z "$ACTOR" ]]; then
    log_error "missing required --actor (and GITHUB_ACTOR is unset)"
    exit 4
fi

MAP="${BREAKPOINT_ACTOR_EMAILS:-}"
if [[ -z "$MAP" ]]; then
    log_debug "BREAKPOINT_ACTOR_EMAILS is empty; no recipient mapping configured"
    exit 1
fi

# Comma-separated actor=email pairs. Whitespace around entries is tolerated
# because a long list in conf will be wrapped by somebody eventually.
IFS=',' read -ra PAIRS <<<"$MAP"
for pair in "${PAIRS[@]}"; do
    pair="${pair#"${pair%%[![:space:]]*}"}"
    pair="${pair%"${pair##*[![:space:]]}"}"
    [[ -n "$pair" ]] || continue

    key="${pair%%=*}"
    value="${pair#*=}"
    if [[ "$key" == "$ACTOR" ]] && [[ -n "$value" ]] && [[ "$value" != "$key" ]]; then
        echo "$value"
        exit 0
    fi
done

log_debug "actor '$ACTOR' is not present in BREAKPOINT_ACTOR_EMAILS"
exit 1

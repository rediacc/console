#!/bin/bash
# THE single teardown entry point. Mode-agnostic, idempotent, and strict.
#
# Usage:
#   stop-breakpoint.sh [--label <l>] [--run-id <id>] [--keep-services]
#
# Exit: 0 only when the verify pass confirms nothing is left. Non-zero when a
#       delete returned anything other than success/404, or when verify still
#       sees an object.
#
# WHY EXIT 0 IS EARNED, NOT ASSUMED
# The whole feature is a bet that teardown can be trusted. A red teardown step
# is noise you investigate once; a GREEN teardown that leaked is a lie that
# nobody investigates at all. So the last thing this script does is re-query
# Cloudflare and insist the objects are gone. There is no --lax.
#
# ORDERING: most security-relevant first.
#   1. interactive access (tmate)  -- before this line there is a HUMAN here
#   2. desktop
#   3. the connector               -- the public name stops resolving NOW
#   4. account-side objects        -- DNS, then Access, then tunnel
#   5. origin + services
#   6. verify
# Steps 4+ are hygiene; the exposure ends at step 3.
#
# MODE-AGNOSTIC: callers never branch on quick vs named. In quick mode every
# account-side lookup simply returns empty and the deletes no-op. That is the
# whole trick -- one code path, and the lookups find nothing.
#
# KILLS ONLY RECORDED PIDS. The deleted tmate action ran
# `pkill -f "tmate.*new-session"` and `rm -f /tmp/tmate-*.log`, both of which
# reach into a CONCURRENT job's processes and files. Never pattern-kill.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

KEEP_SERVICES="${ARG_KEEP_SERVICES:-false}"
STATE_DIR="$(bp_state_dir)"
FAILED=false

# Identity: prefer the descriptor, fall back to recomputation. The fallback is
# what makes this callable by the sweeper, which has no state file at all.
LABEL="${ARG_LABEL:-$(bp_state_get BP_LABEL)}"
RUN_ID="${ARG_RUN_ID:-$(bp_state_get BP_RUN_ID)}"
LABEL="${LABEL:-rdc-ci}"
RUN_ID="${RUN_ID:-${GITHUB_RUN_ID:-}}"

TUNNEL_NAME="$(bp_state_get BP_TUNNEL_NAME)"
HOSTNAME_FULL="$(bp_state_get BP_HOSTNAME)"
if [[ -z "$TUNNEL_NAME" ]] && [[ -n "$RUN_ID" ]]; then
    TUNNEL_NAME="$("$SCRIPT_DIR/derive-descriptor.sh" --field name --label "$LABEL" --run-id "$RUN_ID" 2>/dev/null || true)"
    HOSTNAME_FULL="$("$SCRIPT_DIR/derive-descriptor.sh" --field hostname --label "$LABEL" --run-id "$RUN_ID" 2>/dev/null || true)"
fi

# Nothing at all to do is a SUCCESS, not a failure. This runs from `always()`
# and again from the sweeper, so "already clean" is the normal second call.
if [[ ! -d "$STATE_DIR" ]] && [[ -z "$TUNNEL_NAME" ]]; then
    log_info "nothing to stop (no state dir, no derivable identity)"
    exit 0
fi

# =============================================================================
# 1. INTERACTIVE ACCESS
# =============================================================================
log_step "stopping interactive access..."
bp_kill_recorded tmate
# tmate's own socket, by the exact path start-shell.sh created. Not a glob:
# /tmp/tmate-*.sock would reach a concurrent job's session.
TMATE_SOCK="$(bp_state_get BP_TMATE_SOCKET)"
[[ -n "$TMATE_SOCK" ]] && rm -f "$TMATE_SOCK"

# =============================================================================
# 2. DESKTOP
# =============================================================================
if [[ -x "$SCRIPT_DIR/desktop-ctl.sh" ]]; then
    log_step "stopping desktop (no-op if it never started)..."
    "$SCRIPT_DIR/desktop-ctl.sh" stop >/dev/null 2>&1 || true
fi

# =============================================================================
# 3. THE CONNECTOR -- the exposure ends here
# =============================================================================
log_step "stopping tunnel connector..."
bp_kill_recorded cloudflared

# =============================================================================
# 4. ACCOUNT-SIDE OBJECTS
# =============================================================================
CF_API="https://api.cloudflare.com/client/v4"

cf_api() {
    local method="$1" path="$2"
    curl -sS -X "$method" "${CF_API}${path}" \
        -H "Authorization: Bearer ${BREAKPOINT_TUNNEL_TOKEN}" \
        -H "Content-Type: application/json" \
        --max-time 30
}

cf_ok() { echo "$1" | jq -e '.success == true' >/dev/null 2>&1; }

# A delete that 404s is SUCCESS: the object is gone, which is the goal. Only a
# real error counts against the exit code.
cf_deleted_ok() {
    local resp="$1"
    cf_ok "$resp" && return 0
    echo "$resp" | jq -e '[.errors[]?.code] | any(. == 1000 or . == 1146 or . == 10000 or . == 81044)' >/dev/null 2>&1 && return 0
    grep -qiE 'not found|does not exist' <<<"$resp" && return 0
    return 1
}

if [[ -n "${BREAKPOINT_TUNNEL_TOKEN:-}" ]] && [[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]] && command -v jq >/dev/null 2>&1; then
    ACCT="$CLOUDFLARE_ACCOUNT_ID"
    ZONE_ID="$(bp_state_get BP_ZONE_ID)"
    ZONE_NAME="${BREAKPOINT_TUNNEL_ZONE:-rediacc.io}"

    if [[ -z "$ZONE_ID" ]]; then
        ZONE_ID="$(cf_api GET "/zones?name=${ZONE_NAME}" | jq -r '.result[0].id // empty' 2>/dev/null || true)"
    fi

    # --- DNS FIRST ----------------------------------------------------------
    # Before Access, deliberately: deleting the Access app first would leave the
    # hostname live and UNAUTHENTICATED for the width of the next two calls.
    if [[ -n "$ZONE_ID" ]] && [[ -n "$HOSTNAME_FULL" ]]; then
        log_step "deleting DNS record ${HOSTNAME_FULL}..."
        DNS_ID="$(bp_state_get BP_DNS_RECORD_ID)"
        if [[ -z "$DNS_ID" ]]; then
            DNS_ID="$(cf_api GET "/zones/${ZONE_ID}/dns_records?name=${HOSTNAME_FULL}&type=CNAME" |
                jq -r '.result[] | select(.content | endswith(".cfargotunnel.com")) | .id' 2>/dev/null | head -1 || true)"
        fi
        if [[ -n "$DNS_ID" ]]; then
            resp="$(cf_api DELETE "/zones/${ZONE_ID}/dns_records/${DNS_ID}")"
            if cf_deleted_ok "$resp"; then
                log_info "DNS record deleted"
            else
                log_error "DNS record delete FAILED: $resp"
                FAILED=true
            fi
        fi
    fi

    # --- ACCESS -------------------------------------------------------------
    if [[ -n "$HOSTNAME_FULL" ]]; then
        APP_ID="$(bp_state_get BP_ACCESS_APP_ID)"
        if [[ -z "$APP_ID" ]]; then
            APP_ID="$(cf_api GET "/accounts/${ACCT}/access/apps" |
                jq -r --arg d "$HOSTNAME_FULL" '.result[]? | select(.domain == $d) | .id' 2>/dev/null | head -1 || true)"
        fi
        if [[ -n "$APP_ID" ]]; then
            log_step "deleting Access application..."
            resp="$(cf_api DELETE "/accounts/${ACCT}/access/apps/${APP_ID}")"
            if cf_deleted_ok "$resp"; then
                log_info "Access application deleted (policies cascade)"
            else
                log_error "Access app delete FAILED: $resp"
                FAILED=true
            fi
        fi
    fi

    # --- TUNNEL -------------------------------------------------------------
    if [[ -n "$TUNNEL_NAME" ]]; then
        TID="$(bp_state_get BP_TUNNEL_ID)"
        if [[ -z "$TID" ]]; then
            TID="$(cf_api GET "/accounts/${ACCT}/cfd_tunnel?name=${TUNNEL_NAME}&is_deleted=false" |
                jq -r '.result[0].id // empty' 2>/dev/null || true)"
        fi
        if [[ -n "$TID" ]]; then
            log_step "deleting tunnel ${TUNNEL_NAME}..."
            # cascade=true clears lingering connections; without it a tunnel
            # whose connector died uncleanly REFUSES deletion.
            resp="$(cf_api DELETE "/accounts/${ACCT}/cfd_tunnel/${TID}?cascade=true")"
            if cf_deleted_ok "$resp"; then
                log_info "tunnel deleted"
            else
                log_error "tunnel delete FAILED: $resp"
                FAILED=true
            fi
        fi
    fi
else
    log_debug "no Cloudflare credentials in env; skipping account-side cleanup (normal in quick mode)"
fi

rm -f ~/.cloudflared/*.json 2>/dev/null || true

# =============================================================================
# 5. ORIGIN AND SERVICES
# =============================================================================
log_step "stopping origin..."
bp_kill_recorded origin

# The Caddy gateway, when the session used --kind gateway. Removed BY NAME:
# the name embeds the run id, so this can never reach a concurrent session's
# container. Started with --rm, so `docker stop` also removes it; the explicit
# `docker rm -f` is the belt for a container that was created but never started.
GATEWAY="$(bp_state_get BP_GATEWAY_CONTAINER)"
if [[ -z "$GATEWAY" ]] && [[ -n "$RUN_ID" ]]; then
    GATEWAY="breakpoint-gateway-${RUN_ID}"
fi
if [[ -n "$GATEWAY" ]] && command -v docker >/dev/null 2>&1; then
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$GATEWAY"; then
        log_step "stopping gateway container ${GATEWAY}..."
        docker stop "$GATEWAY" >/dev/null 2>&1 || true
        docker rm -f "$GATEWAY" >/dev/null 2>&1 || true

        # POLL, do not check once. The container is started with --rm, so
        # `docker stop` hands removal to the daemon and returns before it has
        # finished; a single immediate check reports "survived removal" for a
        # container that is already on its way out. Observed live: teardown
        # printed the failure and the very next command showed it gone.
        #
        # A spurious RED here is not harmless. This whole feature rests on a
        # green teardown being trustworthy, and a step that cries wolf every
        # session is one people learn to ignore.
        gw_waited=0
        while [[ $gw_waited -lt 15 ]]; do
            docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$GATEWAY" || break
            sleep 1
            gw_waited=$((gw_waited + 1))
        done

        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$GATEWAY"; then
            log_error "gateway container ${GATEWAY} still present after ${gw_waited}s"
            FAILED=true
        else
            log_info "gateway container removed"
        fi
    fi
fi

if [[ "$KEEP_SERVICES" != "true" ]]; then
    SERVICES="$(bp_state_get BP_SERVICES)"
    if [[ -n "$SERVICES" ]] && [[ "$SERVICES" != "none" ]]; then
        REPO_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
        if [[ -x "$REPO_ROOT/.ci/scripts/infra/ci-stop-elite.sh" ]]; then
            log_step "stopping services ($SERVICES)..."
            "$REPO_ROOT/.ci/scripts/infra/ci-stop-elite.sh" >/dev/null 2>&1 || log_warn "ci-stop.sh reported an error"
        fi
    fi
fi

# =============================================================================
# 6. VERIFY -- exit 0 is earned here
# =============================================================================
if [[ -n "${BREAKPOINT_TUNNEL_TOKEN:-}" ]] && [[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]] && command -v jq >/dev/null 2>&1 && [[ -n "$TUNNEL_NAME" ]]; then
    log_step "verifying nothing is left..."
    LEFT="$(cf_api GET "/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel?name=${TUNNEL_NAME}&is_deleted=false" |
        jq -r '.result | length' 2>/dev/null || echo "0")"
    if [[ "$LEFT" != "0" ]]; then
        log_error "VERIFY FAILED: tunnel '$TUNNEL_NAME' still exists after delete"
        FAILED=true
    fi
    if [[ -n "$ZONE_ID" ]] && [[ -n "$HOSTNAME_FULL" ]]; then
        LEFT_DNS="$(cf_api GET "/zones/${ZONE_ID}/dns_records?name=${HOSTNAME_FULL}" |
            jq -r '.result | length' 2>/dev/null || echo "0")"
        if [[ "$LEFT_DNS" != "0" ]]; then
            log_error "VERIFY FAILED: DNS record '$HOSTNAME_FULL' still exists after delete"
            FAILED=true
        fi
    fi
    [[ "$FAILED" == "true" ]] || log_info "verified: no tunnel, no DNS record"
fi

rm -rf "$STATE_DIR"

if [[ "$FAILED" == "true" ]]; then
    log_error "teardown did NOT fully succeed; see above. The nightly sweeper is the backstop."
    exit 1
fi

log_info "teardown complete"

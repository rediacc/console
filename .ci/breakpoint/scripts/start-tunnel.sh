#!/bin/bash
# Bring up a Cloudflare tunnel in front of a local origin.
#
# Usage:
#   start-tunnel.sh --mode quick|named --origin <url> [--label <l>] [--run-id <id>]
#                   [--access-emails <csv>] [--connect-timeout <s>]
#
# Stdout: EXACTLY ONE LINE, the public URL. Every diagnostic goes to stderr.
#         Callers depend on this; test-breakpoint-lifecycle.sh asserts it.
# Exit:   0 up, 1 transport never came up, 2 named-mode provisioning failed,
#         3 missing credential/env, 4 bad arguments.
#
# TWO THINGS THE OLD .ci/scripts/tunnel/start-cloudflare.sh GOT WRONG
#
# 1. It gated tunnel liveness on APPLICATION health (`curl -sf $URL/health`) and
#    killed the tunnel and retried when that failed. A slow origin therefore
#    destroyed a perfectly working tunnel, three times, and then gave up. Here
#    liveness is TRANSPORT-ONLY: any HTTP status at all, including 502 and 530,
#    proves the edge terminated TLS and reached the connector. Whether the app
#    behind it is healthy is a separate question with a separate script
#    (tunnel-assert.sh) and a separate failure message.
#
# 2. In named mode the hostname is derived from a PUBLIC run id, so it is
#    guessable by anyone reading the Actions tab. Obscurity is not the control;
#    Cloudflare Access is. Access is therefore provisioned IN THIS SCRIPT, in
#    the same call sequence as the DNS record -- there is deliberately no
#    ordering in which the hostname resolves while unprotected. If an
#    unauthenticated probe comes back 200, Access did not attach and that is a
#    hard failure regardless of any fallback flag.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

MODE="${ARG_MODE:-}"
ORIGIN="${ARG_ORIGIN:-}"
LABEL="${ARG_LABEL:-rdc-ci}"
RUN_ID="${ARG_RUN_ID:-${GITHUB_RUN_ID:-}}"
ACCESS_EMAILS="${ARG_ACCESS_EMAILS:-}"
CONNECT_TIMEOUT="${ARG_CONNECT_TIMEOUT:-90}"

[[ -n "$MODE" ]] || {
    log_error "missing required --mode (quick|named)"
    exit 4
}
[[ -n "$ORIGIN" ]] || {
    log_error "missing required --origin (e.g. http://localhost:8080)"
    exit 4
}

# Validate the ONE free-text, operator-supplied value this feature accepts.
# Defence in depth: the workflow now passes it via `env:` so it can never be
# script text, and parse_args no longer evals -- this is the third layer, and
# the only one that constrains the CONTENT rather than the handling. A value
# reaching Cloudflare's Access policy API should look like an email list and
# nothing else.
if [[ -n "$ACCESS_EMAILS" ]]; then
    if [[ ! "$ACCESS_EMAILS" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}([[:space:]]*,[[:space:]]*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})*$ ]]; then
        log_error "--access-emails is not a comma-separated list of email addresses"
        log_error "got: ${ACCESS_EMAILS}"
        log_error "expected e.g.: alice@example.com,bob@example.com"
        exit 4
    fi

    # SHAPE IS NOT AUTHORISATION. The check above only proves the value LOOKS
    # like an email list; on its own it let any address through to Cloudflare's
    # Access policy. Dispatching this workflow needs push access, so the input
    # is not reachable by the public -- but it still turned "can push" into
    # "can hand an outsider a shell on a box holding the repo source", with no
    # record of it beyond a workflow input, and a single typo grants access to
    # whoever owns the mistyped address.
    #
    # So the input is a SELECTOR over people we already know, never a grant to
    # an arbitrary address. The roster is BREAKPOINT_ACTOR_EMAILS in
    # breakpoint.conf -- the same map that resolves the dispatching actor, so
    # there is no second list to keep in sync, and a vendored repo controls its
    # own roster by editing the one file it is expected to edit.
    #
    # FAIL CLOSED when the roster is empty: with no roster there is nothing to
    # authorise against, and "no roster means allow anything" would make this
    # check evaporate in exactly the repo that configured the least.
    roster="${BREAKPOINT_ACTOR_EMAILS:-}"
    if [[ -z "$roster" ]]; then
        log_error "--access-emails was given but BREAKPOINT_ACTOR_EMAILS is empty"
        log_error "there is no roster to authorise against, so this fails closed"
        log_error "Action: add the people to BREAKPOINT_ACTOR_EMAILS in breakpoint.conf"
        exit 4
    fi

    IFS=',' read -ra _requested <<<"$ACCESS_EMAILS"
    for _want in "${_requested[@]}"; do
        _want="${_want#"${_want%%[![:space:]]*}"}"
        _want="${_want%"${_want##*[![:space:]]}"}"
        [[ -z "$_want" ]] && continue
        # Match the VALUE half of each actor=email pair, anchored on both sides
        # so "bob@example.com" cannot be satisfied by "notbob@example.com.evil".
        if ! grep -qiE "(^|,)[[:space:]]*[^=,]+=[[:space:]]*$(bp_regex_escape "$_want")[[:space:]]*(,|$)" <<<"$roster"; then
            log_error "refusing to grant Access to '${_want}': not in BREAKPOINT_ACTOR_EMAILS"
            log_error "Rejected because: this input selects among people the repo already knows;"
            log_error "                  it is not a way to grant a box to an arbitrary address."
            log_error "Action: add them to BREAKPOINT_ACTOR_EMAILS in breakpoint.conf, in a"
            log_error "        commit somebody reviews, rather than in a dispatch input."
            exit 4
        fi
    done
    log_info "all requested Access emails are on the roster"
fi

STATE_DIR="$(bp_state_dir)"
LOG_FILE="$STATE_DIR/cloudflared.log"
mkdir -p "$STATE_DIR"

CF_BIN="$("$SCRIPT_DIR/install-cloudflared.sh")"

# -----------------------------------------------------------------------------
# Identity is recorded BEFORE anything is created.
# -----------------------------------------------------------------------------
TUNNEL_NAME="$("$SCRIPT_DIR/derive-descriptor.sh" --field name --label "$LABEL" --run-id "$RUN_ID")"
HOSTNAME_FULL="$("$SCRIPT_DIR/derive-descriptor.sh" --field hostname --label "$LABEL" --run-id "$RUN_ID")"

bp_state_set BP_SCHEMA "1"
bp_state_set BP_MODE "$MODE"
bp_state_set BP_LABEL "$LABEL"
bp_state_set BP_RUN_ID "$RUN_ID"
bp_state_set BP_REPO "${GITHUB_REPOSITORY:-}"
bp_state_set BP_TUNNEL_NAME "$TUNNEL_NAME"
bp_state_set BP_HOSTNAME "$HOSTNAME_FULL"
bp_state_set BP_ORIGIN "$ORIGIN"
bp_state_set BP_STARTED_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# -----------------------------------------------------------------------------
# Transport liveness. ANY status code counts.
# -----------------------------------------------------------------------------
# Returns the HTTP status on stdout, or 000 when the request did not complete.
#
# The `|| true` is load-bearing and the naive `|| echo "000"` is a TRAP:
# curl -w '%{http_code}' ALREADY prints 000 on a failed request AND exits
# non-zero, so `|| echo "000"` appends a SECOND 000 and yields "000000". That
# string is not equal to "000", so the caller's liveness check passed on a
# completely dead tunnel. Caught by running it: a tunnel whose hostname did not
# resolve reported "quick tunnel live: HTTP 000000 from the edge".
bp_probe_status() {
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null || true)"
    [[ -n "$code" ]] || code="000"
    echo "$code"
}

bp_wait_for_transport() {
    local url="$1" deadline="$2" elapsed=0 status=""
    while [[ $elapsed -lt $deadline ]]; do
        status="$(bp_probe_status "$url")"
        if [[ "$status" != "000" ]]; then
            echo "$status"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    return 1
}

# =============================================================================
# QUICK MODE
# =============================================================================
start_quick() {
    log_step "starting quick tunnel to $ORIGIN..."
    : >"$LOG_FILE"

    "$CF_BIN" tunnel --no-autoupdate --url "$ORIGIN" >"$LOG_FILE" 2>&1 &
    local pid=$!
    bp_record_pid cloudflared "$pid"
    bp_state_set BP_CLOUDFLARED_PID "$pid"

    local url
    if ! url="$(bp_wait_for_log_line "$LOG_FILE" 'https://[a-z0-9-]+\.trycloudflare\.com' "$CONNECT_TIMEOUT")"; then
        log_error "quick tunnel never published a URL"
        return 1
    fi

    local status
    if ! status="$(bp_wait_for_transport "$url" 60)"; then
        log_error "tunnel URL $url never answered (transport never came up)"
        return 1
    fi
    log_info "quick tunnel live: HTTP $status from the edge"

    bp_state_set BP_PUBLIC_URL "$url"
    echo "$url"
}

# =============================================================================
# NAMED MODE
# =============================================================================
CF_API="https://api.cloudflare.com/client/v4"

# cf_api <METHOD> <path> [json-body]
# Mirrors the cf_api helper in .ci/scripts/housekeeping/cleanup-versions.sh, but
# reads BREAKPOINT_TUNNEL_TOKEN -- deliberately NOT the account-wide
# CLOUDFLARE_API_TOKEN, which carries Workers/D1/R2/Pages rights that have no
# business being on a box that hands out an interactive shell.
cf_api() {
    local method="$1" path="$2" body="${3:-}"
    if [[ -n "$body" ]]; then
        curl -sS -X "$method" "${CF_API}${path}" \
            -H "Authorization: Bearer ${BREAKPOINT_TUNNEL_TOKEN}" \
            -H "Content-Type: application/json" \
            --max-time 30 --data "$body"
    else
        curl -sS -X "$method" "${CF_API}${path}" \
            -H "Authorization: Bearer ${BREAKPOINT_TUNNEL_TOKEN}" \
            -H "Content-Type: application/json" \
            --max-time 30
    fi
}

cf_ok() { echo "$1" | jq -e '.success == true' >/dev/null 2>&1; }
cf_errors() { echo "$1" | jq -r '.errors[]?.message' 2>/dev/null | head -3; }

start_named() {
    require_cmd jq
    require_var BREAKPOINT_TUNNEL_TOKEN
    require_var CLOUDFLARE_ACCOUNT_ID

    local zone_name="${BREAKPOINT_TUNNEL_ZONE:-rediacc.io}"
    local acct="$CLOUDFLARE_ACCOUNT_ID"
    local resp

    # --- resolve the zone id -------------------------------------------------
    resp="$(cf_api GET "/zones?name=${zone_name}")"
    if ! cf_ok "$resp"; then
        log_error "could not list zones: $(cf_errors "$resp")"
        return 2
    fi
    local zone_id
    zone_id="$(echo "$resp" | jq -r '.result[0].id // empty')"
    if [[ -z "$zone_id" ]]; then
        log_error "zone '$zone_name' not found, or the token cannot see it"
        return 2
    fi
    bp_state_set BP_ZONE_ID "$zone_id"

    # --- create the tunnel ---------------------------------------------------
    log_step "creating named tunnel $TUNNEL_NAME..."
    resp="$(cf_api POST "/accounts/${acct}/cfd_tunnel" \
        "$(jq -nc --arg n "$TUNNEL_NAME" '{name:$n, config_src:"local"}')")"
    if ! cf_ok "$resp"; then
        log_error "tunnel create failed: $(cf_errors "$resp")"
        return 2
    fi
    local tunnel_id tunnel_token
    tunnel_id="$(echo "$resp" | jq -r '.result.id')"
    tunnel_token="$(echo "$resp" | jq -r '.result.token')"
    # Record IMMEDIATELY: from this instant an object exists that teardown owns.
    bp_state_set BP_TUNNEL_ID "$tunnel_id"
    bp_gha_mask "$tunnel_token"

    # --- DNS CNAME -----------------------------------------------------------
    log_step "routing ${HOSTNAME_FULL} -> ${tunnel_id}.cfargotunnel.com..."
    resp="$(cf_api POST "/zones/${zone_id}/dns_records" \
        "$(jq -nc --arg n "$HOSTNAME_FULL" --arg c "${tunnel_id}.cfargotunnel.com" \
            '{type:"CNAME", name:$n, content:$c, proxied:true, ttl:1}')")"
    if ! cf_ok "$resp"; then
        log_error "DNS record create failed: $(cf_errors "$resp")"
        return 2
    fi
    bp_state_set BP_DNS_RECORD_ID "$(echo "$resp" | jq -r '.result.id')"

    # --- Cloudflare Access ---------------------------------------------------
    # Provisioned here, not in a later step, so the hostname is never live and
    # unprotected. See the header.
    local emails="$ACCESS_EMAILS"
    if [[ -z "$emails" ]]; then
        emails="$("$SCRIPT_DIR/resolve-recipient.sh" --actor "${GITHUB_ACTOR:-}" 2>/dev/null || true)"
    fi
    if [[ -z "$emails" ]]; then
        log_error "named mode requires at least one Access email, and none could be resolved."
        log_error "Pass --access-emails, or map ${GITHUB_ACTOR:-<actor>} in breakpoint.conf's BREAKPOINT_ACTOR_EMAILS."
        log_error "Refusing to publish ${HOSTNAME_FULL} with no access policy."
        return 2
    fi

    log_step "creating Access application for ${HOSTNAME_FULL}..."
    resp="$(cf_api POST "/accounts/${acct}/access/apps" \
        "$(jq -nc --arg d "$HOSTNAME_FULL" --arg n "breakpoint ${TUNNEL_NAME}" \
            '{name:$n, domain:$d, type:"self_hosted", session_duration:"8h"}')")"
    if ! cf_ok "$resp"; then
        log_error "Access app create failed: $(cf_errors "$resp")"
        return 2
    fi
    local app_id
    app_id="$(echo "$resp" | jq -r '.result.id')"
    bp_state_set BP_ACCESS_APP_ID "$app_id"

    local include_json
    include_json="$(echo "$emails" | tr ',' '\n' | jq -R 'select(length>0) | {email:{email:.}}' | jq -sc '.')"
    resp="$(cf_api POST "/accounts/${acct}/access/apps/${app_id}/policies" \
        "$(jq -nc --argjson inc "$include_json" '{name:"breakpoint-allow", decision:"allow", include:$inc}')")"
    if ! cf_ok "$resp"; then
        log_error "Access policy create failed: $(cf_errors "$resp")"
        return 2
    fi
    bp_state_set BP_ACCESS_POLICY_ID "$(echo "$resp" | jq -r '.result.id')"

    # --- run the connector ---------------------------------------------------
    log_step "starting connector..."
    : >"$LOG_FILE"
    "$CF_BIN" tunnel --no-autoupdate run --token "$tunnel_token" --url "$ORIGIN" >"$LOG_FILE" 2>&1 &
    local pid=$!
    bp_record_pid cloudflared "$pid"
    bp_state_set BP_CLOUDFLARED_PID "$pid"

    local url="https://${HOSTNAME_FULL}"
    local status
    if ! status="$(bp_wait_for_transport "$url" "$CONNECT_TIMEOUT")"; then
        log_error "$url never answered; the connector or DNS propagation did not come up"
        tail -30 "$LOG_FILE" >&2 || true
        return 1
    fi

    # An UNAUTHENTICATED probe must be bounced by Access. A 200 here means the
    # app is publishing straight through with no policy attached -- exactly the
    # silent-exposure case named mode exists to prevent. Hard failure.
    case "$status" in
        302 | 401 | 403)
            log_info "Access is armed (unauthenticated probe got HTTP $status)"
            ;;
        200)
            log_error "SECURITY: ${HOSTNAME_FULL} answered 200 to an UNAUTHENTICATED request."
            log_error "Cloudflare Access is not fronting this hostname. Refusing to hand out an"
            log_error "unauthenticated tunnel; tearing down."
            return 2
            ;;
        *)
            log_warn "unexpected status $status from $url; treating transport as up"
            ;;
    esac

    bp_state_set BP_PUBLIC_URL "$url"
    echo "$url"
}

# =============================================================================
case "$MODE" in
    quick) start_quick ;;
    named) start_named ;;
    *)
        log_error "unknown --mode '$MODE' (expected quick or named)"
        exit 4
        ;;
esac

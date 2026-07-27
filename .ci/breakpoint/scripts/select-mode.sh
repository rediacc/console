#!/bin/bash
# Decide which tunnel mode a session runs in. PURE: reads env and flags, writes
# one word to stdout, creates nothing.
#
# THE PROPERTY THIS SCRIPT EXISTS TO GUARANTEE: named mode never silently
# degrades to quick mode.
#
# quick and named are NOT two grades of the same thing. In quick mode the random
# *.trycloudflare.com URL is the ONLY thing protecting the box. In named mode
# the hostname is derived from a public run id and is therefore guessable by
# anyone reading the Actions tab, so Cloudflare Access -- not obscurity -- is
# the control. Falling back from named to quick on an API error would silently
# drop authentication at the exact moment nobody is looking. So a
# misconfiguration is a hard failure with EMPTY STDOUT, and the only way to get
# a fallback is to ask for one explicitly.
#
# Usage:
#   select-mode.sh [--mode quick|named|auto]
#
# Stdout: exactly one of `quick` or `named`, and NOTHING on failure.
# Exit:   0 ok, 3 named requested but not configured, 4 bad arguments.
#
# Env consulted for named mode:
#   BREAKPOINT_TUNNEL_TOKEN    Cloudflare API token (Tunnel+DNS+Access edit)
#   CLOUDFLARE_ACCOUNT_ID      account the tunnel is created in
#   BREAKPOINT_TUNNEL_ZONE     zone the hostname is created in (or conf)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

# Default is quick, NOT auto. The safe default is the one that needs no secrets
# and creates no account-side state; `auto` is a choice and must be made aloud.
MODE="${ARG_MODE:-quick}"

# parse_args turns a valueless flag into the literal string "true".

ZONE="${BREAKPOINT_TUNNEL_ZONE:-}"

named_is_configured() {
    [[ -n "${BREAKPOINT_TUNNEL_TOKEN:-}" ]] &&
        [[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]] &&
        [[ -n "$ZONE" ]]
}

# Name the FIRST missing piece, so a half-configured setup produces an
# actionable message instead of a generic one.
named_missing_what() {
    if [[ -z "${BREAKPOINT_TUNNEL_TOKEN:-}" ]]; then
        echo "BREAKPOINT_TUNNEL_TOKEN (secret)"
    elif [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        echo "CLOUDFLARE_ACCOUNT_ID (repo or org variable)"
    else
        echo "BREAKPOINT_TUNNEL_ZONE (breakpoint.conf)"
    fi
}

case "$MODE" in
    quick)
        # An explicit request always wins, in BOTH directions. Someone who asked
        # for quick while credentials happen to be present gets quick; silently
        # upgrading would create account-side objects they did not ask for and
        # do not know to clean up.
        if named_is_configured; then
            log_info "quick mode requested explicitly; named-mode credentials are present but unused"
        fi
        echo "quick"
        ;;

    named)
        if named_is_configured; then
            echo "named"
            exit 0
        fi

        missing="$(named_missing_what)"

        # THERE IS NO FALLBACK, DELIBERATELY. This used to accept
        # --allow-fallback and silently downgrade to quick, guarded by a refusal
        # when debug-shell or a desktop was on. The guard was the tell: it
        # existed because the maintainer already knew the downgrade was
        # dangerous, and it only narrowed the blast radius rather than removing
        # it. A flag whose entire purpose is "drop authentication and keep
        # going" cannot be made safe by listing the cases where dropping it is
        # worst -- someone asked for an authenticated tunnel, and quick mode is
        # not one. Failing to start is the correct outcome and is trivially
        # recoverable: fix the configuration, or dispatch with tunnel-mode:
        # quick and mean it.
        log_error "named mode requested but not configured (missing: $missing)"
        log_error "Rejected because: quick mode is UNAUTHENTICATED. Silently downgrading would"
        log_error "                  hand out a box that the operator believed was behind Access."
        log_error "Action, pick one:"
        log_error "  1. Configure the above, then re-dispatch."
        log_error "  2. Dispatch with tunnel-mode: quick, explicitly accepting no authentication."
        exit 3
        ;;

    auto)
        # `auto` is the ONLY mode permitted to choose, and it must announce the
        # choice: a run that silently landed in quick mode is indistinguishable
        # in the log from one that asked for it.
        if named_is_configured; then
            log_info "auto: named-mode credentials present, selecting named"
            echo "named"
        else
            bp_gha_warning "auto: named mode is not configured (missing: $(named_missing_what)); selecting QUICK mode, which is unauthenticated"
            echo "quick"
        fi
        ;;

    *)
        log_error "unknown --mode '$MODE' (expected one of: quick, named, auto)"
        exit 4
        ;;
esac

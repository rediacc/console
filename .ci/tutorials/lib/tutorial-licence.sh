#!/bin/bash
# Subscription token for the tutorial CLI.
#
# renet enforces licensing in every build, so each `rdc repo create` and
# `rdc repo fork` issues a repository licence from the account server, and the
# CLI needs a subscription token to ask for one. The tutorials delete and
# recreate the default config, so a stored `rdc subscription login` would not
# survive into the next script; the token rides REDIACC_TOKEN instead, which
# the CLI reads as its subscription token, with REDIACC_ACCOUNT_SERVER naming
# the server.
#
# Sources, first set wins: REDIACC_TOKEN itself, TUTORIAL_ACCOUNT_TOKEN, then
# E2E_ACCOUNT_API_TOKEN (the per-run token CI's
# `rediacc_ci.testrun.start_account` exports beside REDIACC_ACCOUNT_SERVER).
#
# Sourced by tutorial-helpers.sh and the stage-*.sh scripts. With
# TUTORIAL_LICENCE_QUIET=1 it skips the warning when no token is available (the
# stage scripts run against an operator config that may already be logged in).

if [[ -z "${REDIACC_TOKEN:-}" ]]; then
    _tutorial_token="${TUTORIAL_ACCOUNT_TOKEN:-${E2E_ACCOUNT_API_TOKEN:-}}"
    if [[ -n "$_tutorial_token" ]]; then
        export REDIACC_TOKEN="$_tutorial_token"
    fi
    unset _tutorial_token
fi

if [[ "${TUTORIAL_LICENCE_QUIET:-0}" != "1" ]] && [[ -z "${REDIACC_TOKEN:-}" || -z "${REDIACC_ACCOUNT_SERVER:-}" ]]; then
    echo "Warning: no subscription token for the tutorial CLI (REDIACC_TOKEN, TUTORIAL_ACCOUNT_TOKEN or E2E_ACCOUNT_API_TOKEN, plus REDIACC_ACCOUNT_SERVER)." >&2
    echo "         Every 'rdc repo create' and 'rdc repo fork' will refuse with LICENSE_REQUIRED." >&2
fi

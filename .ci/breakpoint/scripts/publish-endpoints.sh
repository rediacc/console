#!/bin/bash
# Decide HOW the operator learns the session's URL, and act on it.
#
# THIS IS A SECURITY CONTROL, NOT A CONVENIENCE.
#
# On a public repository the quick-mode tunnel URL is a BEARER CREDENTIAL:
# anyone watching the Actions tab can reach a runner holding the repo source,
# the app token, and -- with --debug-shell -- an interactive shell. Emailing the
# URL instead of printing it is what keeps it out of a world-readable log. That
# is why email is the DEFAULT and not an extra.
#
# THE BUG THIS FIXES
# The deleted standalone-run.yml masked the URL UNCONDITIONALLY at :349
# (`::add-mask::`) and printed `WEB ACCESS: [sent via email]`. It did read
# EMAIL_SENT at :429, but the failure branch said:
#     "Email not sent -- access details are only available via masked step outputs"
# which is unreadable BY CONSTRUCTION -- masking is exactly what makes step
# outputs unreadable. So whenever SES was absent, the operator got NOTHING and
# the box sat there for its full duration, unreachable and unusable.
# Meanwhile send-access-email.sh:169-179 already degraded correctly and its own
# comment said "sensitive access info will be shown in logs only". The intent
# was right; the log-printing half was simply never wired.
#
# THE RULE, and the whole fix: NEVER MASK WITHOUT A WORKING ALTERNATIVE CHANNEL.
# The channel is decided HERE, before anything is masked, and masking follows
# from the decision instead of preceding it.
#
#   SES configured AND actor resolves  -> email   -> mask the URL, do not print
#   otherwise (no SES / unmapped / --no-send-email)
#                                      -> logs    -> PRINT the URL, do not mask,
#                                                    and warn about the exposure
#   named mode                         -> never mask: the hostname derives from
#                                         a public run id, so masking is theatre.
#                                         Cloudflare Access is the control.
#
# Usage:
#   publish-endpoints.sh --url <public-url> [--send-email true|false]
#                        [--duration <min>] [--tmate-ssh <s>] [--tmate-web <s>]
#                        [--desktop-url <s>]
# Exit: 0 always unless arguments are bad. A delivery failure downgrades the
#       channel; it never fails the session, because a box you cannot reach is
#       still better than no box plus a red X.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

# READ FROM SESSION STATE, NOT FROM THE WORKFLOW`s `env:`. This is a security
# fix with a live receipt, not a refactor.
#
# GitHub prints every step`s `env:` block into the log BEFORE the step`s script
# runs. Passing the URL as `env: BP_URL: ${{ steps.tunnel.outputs.url }}` meant
# the runner published it ~4 seconds before this script could call
# `::add-mask::` on it -- and `::add-mask::` only redacts occurrences AFTER it
# registers. Observed in run 30254567365 on a PUBLIC repo: the email was sent
# correctly AND the URL sat in cleartext at log line 1700, defeating the entire
# reason the email channel is the default.
#
# The state file never touches the log, so reading from it closes the window
# completely rather than narrowing it. Args remain as a test override only.
URL="${ARG_URL:-$(bp_state_get BP_PUBLIC_URL)}"
SEND_EMAIL="${ARG_SEND_EMAIL:-true}"
DURATION="${ARG_DURATION:-}"
TMATE_SSH="${ARG_TMATE_SSH:-$(bp_state_get BP_TMATE_SSH)}"
TMATE_WEB="${ARG_TMATE_WEB:-$(bp_state_get BP_TMATE_WEB)}"
DESKTOP_URL="${ARG_DESKTOP_URL:-}"

[[ -n "$URL" ]] || {
    log_error "no access URL: neither --url nor BP_PUBLIC_URL in the session state"
    log_error "state file: $(bp_state_file)"
    exit 4
}

MODE="$(bp_state_get BP_MODE)"
MODE="${MODE:-quick}"
ACTOR="${GITHUB_ACTOR:-}"

# -----------------------------------------------------------------------------
# 1. Resolve the channel BEFORE masking anything.
# -----------------------------------------------------------------------------
CHANNEL="logs"
RECIPIENT=""
REASON=""

if [[ "$SEND_EMAIL" != "true" ]]; then
    REASON="--send-email=false was passed"
elif [[ -z "${AWS_ACCESS_KEY_ID:-}" ]] || [[ -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    # The AWS_SES_* org secrets are `visibility: selected`; as of 2026-07-26 the
    # selected list is console ONLY. Every other repo that vendors breakpoint
    # lands here, and that is a WORKING configuration, not a broken one.
    REASON="SES credentials are not present in this repo's environment"
elif ! command -v aws >/dev/null 2>&1; then
    REASON="the aws CLI is not installed on this runner"
else
    RECIPIENT="$("$SCRIPT_DIR/resolve-recipient.sh" --actor "$ACTOR" 2>/dev/null || true)"
    if [[ -n "$RECIPIENT" ]]; then
        CHANNEL="email"
    else
        REASON="actor '${ACTOR:-<unknown>}' has no mapping in BREAKPOINT_ACTOR_EMAILS"
    fi
fi

# -----------------------------------------------------------------------------
# 2. Mask ONLY if the URL is genuinely going somewhere else.
# -----------------------------------------------------------------------------
if [[ "$CHANNEL" == "email" ]] && [[ "$MODE" == "quick" ]]; then
    bp_gha_mask "$URL"
    [[ -n "$TMATE_SSH" ]] && bp_gha_mask "$TMATE_SSH"
    [[ -n "$TMATE_WEB" ]] && bp_gha_mask "$TMATE_WEB"
fi

# -----------------------------------------------------------------------------
# 3. Deliver.
# -----------------------------------------------------------------------------
send_email() {
    local body subject
    subject="breakpoint session ready (${GITHUB_REPOSITORY:-local}, run ${GITHUB_RUN_ID:-?})"
    body="A breakpoint debug session is live.

  URL:        ${URL}
  Mode:       ${MODE}
  Duration:   ${DURATION:-?} minutes
  Repository: ${GITHUB_REPOSITORY:-local}
  Run:        ${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}
"
    [[ -n "$DESKTOP_URL" ]] && body="${body}  Desktop:    ${DESKTOP_URL}
"
    [[ -n "$TMATE_SSH" ]] && body="${body}  SSH:        ${TMATE_SSH}
"
    [[ -n "$TMATE_WEB" ]] && body="${body}  Web shell:  ${TMATE_WEB}
"
    body="${body}
This session tears itself down when the duration elapses. If the run is
cancelled, the nightly sweeper is the backstop.
"

    aws ses send-email \
        --from "${AWS_SES_FROM:-}" \
        --destination "ToAddresses=${RECIPIENT}" \
        --message "Subject={Data=\"${subject}\"},Body={Text={Data=\"${body}\"}}" \
        >/dev/null 2>&1
}

if [[ "$CHANNEL" == "email" ]]; then
    log_step "sending access details to ${RECIPIENT}..."
    if send_email; then
        log_info "access details emailed to ${RECIPIENT}"
        {
            echo "### breakpoint session ready"
            echo ""
            echo "Access details were **emailed to ${RECIPIENT}** rather than printed,"
            echo "because this log is world-readable and the URL is a bearer credential."
            echo ""
            echo "- Mode: \`${MODE}\`"
            echo "- Duration: ${DURATION:-?} minutes"
        } >>"${GITHUB_STEP_SUMMARY:-/dev/null}"
        bp_state_set BP_DELIVERY "email"
        exit 0
    fi
    # Delivery failed AFTER we chose email. Fall through to logs rather than
    # leaving the operator with a masked URL and no way to read it -- that is
    # precisely the old bug.
    log_warn "email delivery failed; falling back to the logs channel"
    REASON="SES send failed"
    CHANNEL="logs"
fi

# -----------------------------------------------------------------------------
# LOGS CHANNEL
# -----------------------------------------------------------------------------
# Loud, and it narrows itself, but it does NOT refuse to run. A debug tool that
# will not start when you most need it is worse than one that is honest about
# its exposure.
bp_state_set BP_DELIVERY "logs"

if [[ "$MODE" == "quick" ]]; then
    bp_gha_warning "This session's URL is printed below IN A PUBLIC LOG because ${REASON}. Anyone who can read this run can reach this runner for the next ${DURATION:-?} minutes. For repositories without SES, named mode + Cloudflare Access is the durable answer."
else
    log_info "named mode: the hostname is derivable from the public run id, so Cloudflare Access is the control, not obscurity"
fi

echo ""
echo "======================================================================"
echo " BREAKPOINT SESSION READY"
echo "======================================================================"
echo "  URL:      ${URL}"
echo "  Mode:     ${MODE}"
echo "  Duration: ${DURATION:-?} minutes"
[[ -n "$DESKTOP_URL" ]] && echo "  Desktop:  ${DESKTOP_URL}"
[[ -n "$TMATE_SSH" ]] && echo "  SSH:      ${TMATE_SSH}"
[[ -n "$TMATE_WEB" ]] && echo "  Web:      ${TMATE_WEB}"
echo "----------------------------------------------------------------------"
echo "  Delivered via LOGS because: ${REASON}"
echo "======================================================================"
echo ""

{
    echo "### breakpoint session ready"
    echo ""
    echo "| | |"
    echo "|---|---|"
    echo "| URL | ${URL} |"
    echo "| Mode | \`${MODE}\` |"
    echo "| Duration | ${DURATION:-?} min |"
    echo ""
    echo "> Delivered in the log because ${REASON}."
    if [[ "$MODE" == "quick" ]]; then
        echo ">"
        echo "> Quick tunnels cap at 200 concurrent requests and do **not** support"
        echo "> Server-Sent Events. If something streaming looks broken, that is why."
    fi
} >>"${GITHUB_STEP_SUMMARY:-/dev/null}"

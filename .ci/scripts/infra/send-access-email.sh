#!/bin/bash
# Send access information email to the workflow triggering actor via AWS SES.
# Usage: send-access-email.sh --actor <github-actor> [options]
#
# Required environment variables:
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION - AWS SES credentials
#   SES_FROM - Sender email address (verified in SES)
#
# Options:
#   --actor <username>        GitHub actor username (required)
#   --tag <version>           Docker image version tag
#   --duration <minutes>      Run duration
#   --run-name <name>         Workflow run name
#   --run-url <url>           GitHub Actions run URL
#   --tunnel-url <url>        Cloudflare tunnel URL
#   --desktop-env <env>       Desktop environment (none = disabled)
#   --desktop-res <res>       Desktop resolution
#   --vm-os <os>              VM OS (none = disabled)
#   --vm-kvm <bool>           KVM available (true/false)
#   --vm-user <user>          VM machine username
#   --vm-pass <pass>          VM machine password
#   --bridge-ip <ip>          VM bridge IP
#   --worker-ips <ips>        Comma-separated worker IPs
#   --connection-string <str> Database connection string
#   --debug-ssh <cmd>         tmate SSH connection string
#   --debug-web <url>         tmate web URL
#
# Outputs EMAIL_SENT=true/false to $GITHUB_ENV if available.
#
# Example:
#   send-access-email.sh --actor mfbayraktar --tag 0.8.1 --duration 30

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# ACTOR → EMAIL MAPPING
# =============================================================================

resolve_email() {
    local actor="$1"
    case "$actor" in
        mfbayraktar) echo "muhammed@rediacc.com" ;;
        HamzaOzsarac) echo "hamza@rediacc.com" ;;
        04yuksel05) echo "yuksel@rediacc.com" ;;
        mehmethelveci) echo "mehmet@rediacc.com" ;;
        anilkartal) echo "anil@rediacc.com" ;;
        oiseguven) echo "omer@rediacc.com" ;;
        *) echo "" ;;
    esac
}

# =============================================================================
# PARSE ARGUMENTS
# =============================================================================

ACTOR=""
TAG=""
DURATION=""
RUN_NAME="Manual Service Run"
RUN_URL=""
TUNNEL_URL=""
DESKTOP_ENV="none"
DESKTOP_RES=""
VM_OS="none"
VM_KVM="false"
VM_USER=""
VM_PASS=""
BRIDGE_IP=""
WORKER_IPS=""
CONNECTION_STRING=""
DEBUG_SSH=""
DEBUG_WEB=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --actor)
            ACTOR="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --run-name)
            RUN_NAME="$2"
            shift 2
            ;;
        --run-url)
            RUN_URL="$2"
            shift 2
            ;;
        --tunnel-url)
            TUNNEL_URL="$2"
            shift 2
            ;;
        --desktop-env)
            DESKTOP_ENV="$2"
            shift 2
            ;;
        --desktop-res)
            DESKTOP_RES="$2"
            shift 2
            ;;
        --vm-os)
            VM_OS="$2"
            shift 2
            ;;
        --vm-kvm)
            VM_KVM="$2"
            shift 2
            ;;
        --vm-user)
            VM_USER="$2"
            shift 2
            ;;
        --vm-pass)
            VM_PASS="$2"
            shift 2
            ;;
        --bridge-ip)
            BRIDGE_IP="$2"
            shift 2
            ;;
        --worker-ips)
            WORKER_IPS="$2"
            shift 2
            ;;
        --connection-string)
            CONNECTION_STRING="$2"
            shift 2
            ;;
        --debug-ssh)
            DEBUG_SSH="$2"
            shift 2
            ;;
        --debug-web)
            DEBUG_WEB="$2"
            shift 2
            ;;
        *)
            log_warn "Unknown option: $1"
            shift
            ;;
    esac
done

# =============================================================================
# VALIDATION
# =============================================================================

set_email_sent() {
    if [[ -n "${GITHUB_ENV:-}" ]]; then
        echo "EMAIL_SENT=$1" >>"$GITHUB_ENV"
    fi
}

if [[ -z "$ACTOR" ]]; then
    log_error "Missing required --actor argument"
    set_email_sent "false"
    exit 1
fi

if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]] || [[ -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    log_warn "SES credentials not configured — skipping email notification"
    set_email_sent "false"
    exit 0
fi

RECIPIENT=$(resolve_email "$ACTOR")
if [[ -z "$RECIPIENT" ]]; then
    log_warn "No email mapping for actor '${ACTOR}' — sensitive access info will be shown in logs only"
    set_email_sent "false"
    exit 0
fi

log_step "Sending access information email to ${RECIPIENT}..."

# =============================================================================
# BUILD HTML EMAIL
# =============================================================================

# Email contains ONLY sensitive data — no URLs that could trigger spam filters
TD="style=\"padding: 6px 12px;\""
TH="style=\"padding: 6px 12px; font-weight: bold;\""
SENS_TABLE="style=\"border-collapse: collapse; width: 100%; background: #fef2f2; border: 1px solid #fecaca; border-radius: 4px;\""

HTML="<html><body style=\"font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 700px; margin: 0 auto; color: #1a1a1a;\">"
HTML+="<h2 style=\"border-bottom: 2px solid #556b2f; padding-bottom: 8px;\">Access Information — ${RUN_NAME}</h2>"
HTML+="<table style=\"border-collapse: collapse; width: 100%;\">"
HTML+="<tr><td ${TH}>Image Version</td><td ${TD}>${TAG}</td></tr>"
HTML+="<tr><td ${TH}>Duration</td><td ${TD}>${DURATION} minutes</td></tr>"

if [[ -n "$RUN_URL" ]]; then
    HTML+="<tr><td ${TH}>Workflow Run</td><td ${TD}><a href=\"${RUN_URL}\">View in GitHub</a></td></tr>"
fi

HTML+="</table>"
HTML+="<p style=\"color: #6b7280; font-size: 13px;\">Tunnel URLs and other non-sensitive details are available in the workflow logs.</p>"

# VM credentials + SSH access
if [[ "$VM_OS" != "none" ]] && [[ "$VM_KVM" == "true" ]]; then
    HTML+="<h3 style=\"color: #dc2626;\">VM Credentials</h3>"
    HTML+="<table ${SENS_TABLE}>"
    HTML+="<tr><td ${TH}>Username</td><td ${TD}><code>${VM_USER}</code></td></tr>"
    HTML+="<tr><td ${TH}>Password</td><td ${TD}><code>${VM_PASS}</code></td></tr>"
    HTML+="</table>"

    HTML+="<h3>SSH Access</h3><table style=\"border-collapse: collapse; width: 100%;\">"
    HTML+="<tr><td ${TH}>Bridge</td><td ${TD}><code>ssh ${VM_USER}@${BRIDGE_IP}</code></td></tr>"

    IFS=',' read -ra WORKER_ARRAY <<<"${WORKER_IPS}"
    for i in "${!WORKER_ARRAY[@]}"; do
        HTML+="<tr><td ${TH}>Worker $((i + 1))</td><td ${TD}><code>ssh ${VM_USER}@${WORKER_ARRAY[$i]}</code></td></tr>"
    done
    HTML+="</table>"
fi

# Database connection string
if [[ -n "$CONNECTION_STRING" ]]; then
    HTML+="<h3 style=\"color: #dc2626;\">Database</h3>"
    HTML+="<table ${SENS_TABLE}>"
    HTML+="<tr><td ${TH}>Connection String</td><td ${TD}><code style=\"word-break: break-all; font-size: 12px;\">PLACEHOLDER_CONNSTR</code></td></tr>"
    HTML+="</table>"
fi

# Footer
HTML+="<hr style=\"margin-top: 24px; border: none; border-top: 1px solid #e5e7eb;\">"
HTML+="<p style=\"color: #6b7280; font-size: 12px;\">Sent automatically by GitHub Actions. Do not reply.</p>"
HTML+="</body></html>"

# =============================================================================
# SEND VIA AWS SES
# =============================================================================

SUBJECT="[Rediacc] Access Info — ${RUN_NAME} (${TAG})"

# Use jq to safely construct JSON (handles special chars in connection string, passwords, etc.)
EMAIL_JSON=$(jq -n \
    --arg from "${SES_FROM}" \
    --arg to "${RECIPIENT}" \
    --arg subject "$SUBJECT" \
    --arg html "$HTML" \
    --arg connstr "$CONNECTION_STRING" \
    '{
    Content: {
      Simple: {
        Subject: { Data: $subject, Charset: "UTF-8" },
        Body: { Html: { Data: (if $connstr != "" then ($html | gsub("PLACEHOLDER_CONNSTR"; $connstr)) else $html end), Charset: "UTF-8" } }
      }
    },
    Destination: { ToAddresses: [$to] },
    FromEmailAddress: $from
  }')

if aws sesv2 send-email --cli-input-json "$EMAIL_JSON"; then
    log_info "Access information email sent to ${RECIPIENT}"
    set_email_sent "true"
else
    log_warn "Failed to send access information email to ${RECIPIENT}"
    set_email_sent "false"
fi

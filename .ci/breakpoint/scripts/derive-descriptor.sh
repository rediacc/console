#!/bin/bash
# Derive a breakpoint session's identity from the environment. PURE: reads env
# and flags, writes to stdout, creates nothing and deletes nothing.
#
# WHY THIS IS ITS OWN SCRIPT
# The name is the DURABLE channel. A session's descriptor file lives on a runner
# that may vanish without warning (force-cancel and infra loss both skip
# `if: always()` entirely), so cleanup cannot depend on it. What cleanup CAN
# depend on is that the tunnel's name is a pure function of $GITHUB_RUN_ID:
# reap-breakpoint-orphans.sh enumerates Cloudflare's own object list, parses the
# run id back out of each name, and asks GitHub whether that run is over. Zero
# cooperation required from the dead runner.
#
# That only works if start, stop and sweep agree on the grammar to the byte,
# which is why all three call this one script instead of formatting names
# inline.
#
# Usage:
#   derive-descriptor.sh --field <name|hostname|url|run-id|label> \
#                        [--label <l>] [--run-id <id>] [--zone <z>]
#
# Stdout: exactly one line, the requested field. Nothing else.
# Exit:   0 ok, 3 missing required env, 4 bad arguments.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

FIELD="${ARG_FIELD:-}"
LABEL="${ARG_LABEL:-${BREAKPOINT_DEFAULT_LABEL:-rdc-ci}}"
ZONE="${ARG_ZONE:-${BREAKPOINT_TUNNEL_ZONE:-rediacc.io}}"
RUN_ID="${ARG_RUN_ID:-${GITHUB_RUN_ID:-}}"

# DNS labels are capped at 63 octets by RFC 1035. Named mode turns the
# descriptor into a hostname label, so the cap is a hard constraint, not a
# nicety: an over-long label is rejected by the DNS API with a message that does
# not obviously point back here.
readonly DNS_LABEL_MAX=63

if [[ -z "$FIELD" ]]; then
    log_error "missing required --field (one of: name, hostname, url, run-id, label)"
    exit 4
fi

# Fail loudly rather than inventing a value. An empty run id would silently
# produce 'breakpoint-rdc-ci-' -- a name that matches no sweep regex, so the
# object it labels would be orphaned FOREVER. Refusing is the safe direction.
if [[ -z "$RUN_ID" ]]; then
    log_error "GITHUB_RUN_ID is not set and --run-id was not given"
    log_error "the run id is load-bearing: it is how the nightly sweeper attributes orphaned tunnels"
    exit 3
fi

if [[ ! "$RUN_ID" =~ ^[0-9]+$ ]]; then
    log_error "run id must be numeric, got: '$RUN_ID'"
    exit 4
fi

# Validate the label against the closed set from breakpoint.conf. Closed on
# purpose: the sweeper's regex is built from this list, so a label that is used
# but not listed is invisible to cleanup. Rejecting here is what keeps that
# promise true.
ALLOWED_LABELS="${BREAKPOINT_TUNNEL_LABELS:-rdc-ci rdc-dev rdc-demo}"
label_allowed=false
for allowed in $ALLOWED_LABELS; do
    if [[ "$LABEL" == "$allowed" ]]; then
        label_allowed=true
        break
    fi
done
if [[ "$label_allowed" != "true" ]]; then
    log_error "label '$LABEL' is not in BREAKPOINT_TUNNEL_LABELS ($ALLOWED_LABELS)"
    log_error "a label the sweeper's regex does not cover would leak its objects permanently"
    exit 4
fi

# Slugify: lowercase, non-alphanumeric to '-', collapse runs, trim, truncate.
bp_slugify() {
    local raw="$1" out
    out="$(echo "$raw" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/-/g; s/-\+/-/g; s/^-//; s/-$//')"
    if ((${#out} > DNS_LABEL_MAX)); then
        out="${out:0:$DNS_LABEL_MAX}"
        # Truncation can leave a trailing '-', which is invalid in a DNS label.
        out="${out%-}"
    fi
    echo "$out"
}

TUNNEL_NAME="$(bp_slugify "breakpoint-${LABEL}-${RUN_ID}")"
HOST_LABEL="$(bp_slugify "${LABEL}-${RUN_ID}")"
HOSTNAME_FULL="${HOST_LABEL}.${ZONE}"

case "$FIELD" in
    name) echo "$TUNNEL_NAME" ;;
    hostname) echo "$HOSTNAME_FULL" ;;
    url) echo "https://${HOSTNAME_FULL}" ;;
    run-id) echo "$RUN_ID" ;;
    label) echo "$LABEL" ;;
    *)
        log_error "unknown --field '$FIELD' (expected: name, hostname, url, run-id, label)"
        exit 4
        ;;
esac

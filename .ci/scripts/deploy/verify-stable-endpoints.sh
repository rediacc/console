#!/bin/bash
# Post-deploy verification for the stable environment.
#
# WHY: same reasoning as verify-edge-endpoints.sh, one channel over. A Worker
# deploy can report success while serving the wrong bundle or the wrong channel
# default, so each assertion is a fingerprint only the intended deployment can
# satisfy:
#   - install.sh / install.ps1 must be baked to channel=stable, on the worker
#     AND on the releases.rediacc.com R2 backstop (a separate serving path,
#     re-baked by promote-r2-to-stable.sh -- this proves that landed);
#   - /about=410, /en=200, mixed-case font=200 are behaviours only the
#     workers/www bundle has (redirect table, html_handling=drop-trailing-slash,
#     asset-path guard) -- a stale workers/marketing deploy fails all three.
# Per-region account health comes from regions.json so adding a region needs no
# edit here. Unlike the edge smoke test, region health here only WARNS: stable
# promotion has already happened by this point and a single slow region should
# not red the run.
#
# Usage:
#   .ci/scripts/deploy/verify-stable-endpoints.sh
#
# Must run from a checkout containing regions.json. Takes no env input.
#
# Run locally (read-only -- it only issues GETs against production):
#   .ci/scripts/deploy/verify-stable-endpoints.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u` is added
# here; `pipefail` is deliberately NOT, and common.sh's is turned back off
# below. `HDRS=$(curl -sI ... | tr -d '\r')` relies on the pipeline reporting
# tr's status: under pipefail a transient curl failure would abort the whole
# verification instead of falling through to the "headers not yet enabled"
# branch.

set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
# common.sh sets `-euo pipefail`; restore the workflow block's laxer pipeline
# semantics (see the header note above).
set +o pipefail

require_cmd curl
require_cmd jq

# regions.json is read by relative path, exactly as the workflow block did;
# anchoring to the repo root makes the script runnable from any cwd.
cd "$(get_repo_root)"

echo "Verifying stable deployment..."

INSTALL_SH=$(curl -fsSL https://www.rediacc.com/install.sh)
if ! echo "$INSTALL_SH" | grep -q 'REDIACC_CHANNEL:-stable'; then
    echo "::error::www.rediacc.com/install.sh is not baked to channel=stable"
    echo "$INSTALL_SH" | grep -E 'REDIACC_CHANNEL' || true
    exit 1
fi
echo "  marketing (install.sh): OK (channel=stable)"

INSTALL_PS1=$(curl -fsSL https://www.rediacc.com/install.ps1)
if ! echo "$INSTALL_PS1" | grep -qF '} else { "stable" }'; then
    echo "::error::www.rediacc.com/install.ps1 is not baked to channel=stable"
    echo "$INSTALL_PS1" | grep -F '$Channel' || true
    exit 1
fi
echo "  marketing (install.ps1): OK (channel=stable)"

# Worker-fingerprint checks. These assert that the NEW Worker bundle
# from workers/www/ is actually serving — not a stale deploy of the
# old workers/marketing/ code (which has no redirect table, no
# html_handling=drop-trailing-slash, and no asset-path guard).
# Cache-busting query strings ensure we hit the Worker, not a cached
# response.
RNDA=$RANDOM$RANDOM
RNDB=$RANDOM$RANDOM
RNDC=$RANDOM$RANDOM
S=$(curl -sI -o /dev/null -w '%{http_code}' "https://www.rediacc.com/about?cb=$RNDA")
[[ "$S" == "410" ]] || {
    echo "::error::www /about expected 410 (curated redirect table), got $S — old worker bundle likely live"
    exit 1
}
echo "  worker fingerprint (redirect table): OK (/about=410)"

S=$(curl -sI -o /dev/null -w '%{http_code}' "https://www.rediacc.com/en?cb=$RNDB")
[[ "$S" == "200" ]] || {
    echo "::error::www /en expected 200 (html_handling=drop-trailing-slash), got $S"
    exit 1
}
echo "  worker fingerprint (html_handling): OK (/en=200, no 307)"

S=$(curl -sI -o /dev/null -w '%{http_code}' "https://www.rediacc.com/fonts/inter/Inter-Regular.woff2?cb=$RNDC")
[[ "$S" == "200" ]] || {
    echo "::error::www mixed-case font expected 200 (asset-path guard), got $S"
    exit 1
}
echo "  worker fingerprint (asset-path guard): OK (Inter-Regular.woff2=200)"

# R2 backstop: per-channel copy at releases.rediacc.com/cli/stable/
# must also be channel-baked. The re-bake step in the promote job
# (above) rewrites REDIACC_CHANNEL:-edge → :-stable; this asserts it
# worked and the upload actually landed.
R2_SH=$(curl -fsSL https://releases.rediacc.com/cli/stable/install.sh)
if ! echo "$R2_SH" | grep -q 'REDIACC_CHANNEL:-stable'; then
    echo "::error::releases.rediacc.com/cli/stable/install.sh not baked to channel=stable"
    echo "$R2_SH" | grep -E 'REDIACC_CHANNEL' || true
    exit 1
fi
echo "  R2 cli/stable/install.sh: OK (channel=stable)"

R2_PS1=$(curl -fsSL https://releases.rediacc.com/cli/stable/install.ps1)
if ! echo "$R2_PS1" | grep -qF '} else { "stable" }'; then
    echo "::error::releases.rediacc.com/cli/stable/install.ps1 not baked to channel=stable"
    exit 1
fi
echo "  R2 cli/stable/install.ps1: OK (channel=stable)"

while read -r domain; do
    INFO_URL="https://${domain}/account/api/v1/.well-known/server-info"
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${INFO_URL}" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" != "200" ]]; then
        echo "::warning::${domain} health check returned HTTP ${HTTP_CODE}"
        continue
    fi
    HDRS=$(curl -sI "${INFO_URL}" | tr -d '\r')
    if echo "$HDRS" | grep -qi '^strict-transport-security:'; then
        if ! echo "$HDRS" | grep -qi '^x-content-type-options: *nosniff'; then
            echo "::warning::${domain} has HSTS but missing X-Content-Type-Options"
            continue
        fi
        echo "  ${domain} health: OK (security headers verified)"
    else
        echo "  ${domain} health: OK (security headers not yet enabled)"
    fi
done < <(jq -r '.regions[] | .domain' regions.json)

echo "Stable verification complete"

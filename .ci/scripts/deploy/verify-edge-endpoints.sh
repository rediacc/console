#!/bin/bash
# Post-deploy smoke test for the edge environment.
#
# WHY: a Worker deploy can report success while serving the wrong bundle, the
# wrong channel default, or a stale Astro build. Each assertion below is a
# fingerprint that only the intended, current deployment can satisfy:
#   - install.sh / install.ps1 must be baked to channel=edge (worker AND the
#     releases.rediacc.com R2 backstop, which is a separate serving path);
#   - /about=410, /en=200, mixed-case font=200 are behaviours only the
#     workers/www bundle has (redirect table, html_handling=drop-trailing-slash,
#     asset-path guard) -- a stale workers/marketing deploy fails all three;
#   - the rendered footer must carry the semver we just published, which proves
#     APP_VERSION propagated through cd-deploy-worker.yml -> astro.config.mjs.
# Per-region account health comes from regions.json so adding a region needs no
# edit here.
#
# Usage:
#   .ci/scripts/deploy/verify-edge-endpoints.sh
#
# Must run from a checkout containing regions.json.
#
# Required env:
#   VERSION        semver just published, no leading v (e.g. 1.2.3)
#
# Optional env:
#   WORKERS_ONLY   "true" skips every version-dependent assertion, because a
#                  workers-only deploy publishes no new version
#
# Run locally (read-only -- it only issues GETs against production edge):
#   VERSION=1.2.3 .ci/scripts/deploy/verify-edge-endpoints.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u` is added
# here; `pipefail` is deliberately NOT, and common.sh's is turned back off
# below. `HDRS=$(curl -sI ... | tr -d '\r')` relies on the pipeline reporting
# tr's status: under pipefail a transient curl failure would abort the whole
# smoke test instead of falling through to the "headers not yet enabled" branch.

set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
# common.sh sets `-euo pipefail`; restore the workflow block's laxer pipeline
# semantics (see the header note above).
set +o pipefail

require_cmd curl
require_cmd jq
VERSION="${VERSION:?verify-edge-endpoints.sh: VERSION must be set}"
WORKERS_ONLY="${WORKERS_ONLY:-}"

# regions.json is read by relative path, exactly as the workflow block did;
# anchoring to the repo root makes the script runnable from any cwd.
cd "$(get_repo_root)"

echo "Verifying edge deployment for v${VERSION}..."

# Marketing worker — also verify the channel default was rewritten.
INSTALL_SH=$(curl -fsSL https://edge.rediacc.com/install.sh)
if ! echo "$INSTALL_SH" | grep -q 'REDIACC_CHANNEL:-edge'; then
    echo "::error::edge.rediacc.com/install.sh is not baked to channel=edge"
    echo "$INSTALL_SH" | grep -E 'REDIACC_CHANNEL' || true
    exit 1
fi
echo "  marketing (install.sh): OK (channel=edge)"

INSTALL_PS1=$(curl -fsSL https://edge.rediacc.com/install.ps1)
if ! echo "$INSTALL_PS1" | grep -qF '} else { "edge" }'; then
    echo "::error::edge.rediacc.com/install.ps1 is not baked to channel=edge"
    echo "$INSTALL_PS1" | grep -F '$Channel' || true
    exit 1
fi
echo "  marketing (install.ps1): OK (channel=edge)"

# Worker-fingerprint checks. These assert that the NEW Worker bundle
# from workers/www/ is actually serving — not a stale deploy of the
# old workers/marketing/ code (which has no redirect table, no
# html_handling=drop-trailing-slash, and no asset-path guard).
# Cache-busting query strings ensure we hit the Worker, not a cached
# response.
RNDA=$RANDOM$RANDOM
RNDB=$RANDOM$RANDOM
RNDC=$RANDOM$RANDOM
S=$(curl -sI -o /dev/null -w '%{http_code}' "https://edge.rediacc.com/about?cb=$RNDA")
[[ "$S" == "410" ]] || {
    echo "::error::edge /about expected 410 (curated redirect table), got $S — old worker bundle likely live"
    exit 1
}
echo "  worker fingerprint (redirect table): OK (/about=410)"

S=$(curl -sI -o /dev/null -w '%{http_code}' "https://edge.rediacc.com/en?cb=$RNDB")
[[ "$S" == "200" ]] || {
    echo "::error::edge /en expected 200 (html_handling=drop-trailing-slash), got $S"
    exit 1
}
echo "  worker fingerprint (html_handling): OK (/en=200, no 307)"

S=$(curl -sI -o /dev/null -w '%{http_code}' "https://edge.rediacc.com/fonts/inter/Inter-Regular.woff2?cb=$RNDC")
[[ "$S" == "200" ]] || {
    echo "::error::edge mixed-case font expected 200 (asset-path guard), got $S"
    exit 1
}
echo "  worker fingerprint (asset-path guard): OK (Inter-Regular.woff2=200)"

# Footer version assertion: confirm the Astro build baked the
# expected semver into the rendered HTML. Catches regressions in
# APP_VERSION propagation (cd-deploy-worker.yml -> astro.config.mjs).
# Astro SSR inserts React text-boundary comment nodes, so the
# rendered HTML is `<p class="footer-version">v<!-- -->1.0.4</p>`
# -- the regex collapses any HTML comments between the "v" and
# the semver before matching.
if [[ "$WORKERS_ONLY" != "true" ]]; then
    FOOTER_HTML=$(curl -fsSL https://edge.rediacc.com/en/)
    FOOTER_NORMALIZED=$(echo "$FOOTER_HTML" | sed 's/<!--[^>]*-->//g')
    if ! echo "$FOOTER_NORMALIZED" | grep -qE "footer-version[^<]*>v${VERSION}<"; then
        echo "::error::edge.rediacc.com footer does not render v${VERSION}"
        echo "$FOOTER_HTML" | grep -oE 'footer-version[^<]*>[^<]*<[^>]*>[^<]*<' | head -3 || true
        exit 1
    fi
    echo "  marketing (footer version): OK (v${VERSION})"
fi

# R2 backstop: the per-channel copy at releases.rediacc.com/cli/edge/
# is the fallback serving path (not worker-rewritten). It must also
# be channel-baked (done at upload time in cd-stage.yml). This
# cross-check catches R2 upload regressions.
if [[ "$WORKERS_ONLY" != "true" ]]; then
    R2_SH=$(curl -fsSL https://releases.rediacc.com/cli/edge/install.sh)
    if ! echo "$R2_SH" | grep -q 'REDIACC_CHANNEL:-edge'; then
        echo "::error::releases.rediacc.com/cli/edge/install.sh not baked to channel=edge"
        echo "$R2_SH" | grep -E 'REDIACC_CHANNEL' || true
        exit 1
    fi
    echo "  R2 cli/edge/install.sh: OK (channel=edge)"

    R2_PS1=$(curl -fsSL https://releases.rediacc.com/cli/edge/install.ps1)
    if ! echo "$R2_PS1" | grep -qF '} else { "edge" }'; then
        echo "::error::releases.rediacc.com/cli/edge/install.ps1 not baked to channel=edge"
        exit 1
    fi
    echo "  R2 cli/edge/install.ps1: OK (channel=edge)"
else
    echo "  R2 backstop: skipped (workers-only deployment)"
fi

# R2 releases (skip in workers-only mode -- no new version was published)
if [[ "$WORKERS_ONLY" != "true" ]]; then
    EDGE_VERSION=$(curl -fsSL https://releases.rediacc.com/cli/edge/latest.json | jq -re '.version')
    echo "  edge latest.json: v${EDGE_VERSION}"

    if [[ "$EDGE_VERSION" == "$VERSION" ]]; then
        echo "  version match: OK"
    else
        echo "  version mismatch: edge has v${EDGE_VERSION}, expected v${VERSION} (acceptable in retry mode)"
    fi
else
    echo "  R2 version check: skipped (workers-only)"
fi

# Per-region account health checks (dynamic from regions.json).
# The header gate below activates the moment Phase 1 ships (worker
# sets Strict-Transport-Security): once HSTS is present, we require
# X-Content-Type-Options: nosniff alongside it. Until then the gate
# is a no-op — pre-Phase-1 deploys still pass.
FAILED=0
while read -r domain; do
    INFO_URL="https://${domain}/account/api/v1/.well-known/server-info"
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${INFO_URL}" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" != "200" ]]; then
        echo "::error::${domain} health check failed (HTTP ${HTTP_CODE})"
        FAILED=1
        continue
    fi
    HDRS=$(curl -sI "${INFO_URL}" | tr -d '\r')
    if echo "$HDRS" | grep -qi '^strict-transport-security:'; then
        if ! echo "$HDRS" | grep -qi '^x-content-type-options: *nosniff'; then
            echo "::error::${domain} has HSTS but missing X-Content-Type-Options: nosniff"
            FAILED=1
            continue
        fi
        echo "  ${domain} health: OK (security headers verified)"
    else
        echo "  ${domain} health: OK (security headers not yet enabled)"
    fi
done < <(jq -r '.regions[] | .edgeDomain' regions.json)

if [[ "$FAILED" -eq 1 ]]; then
    exit 1
fi
echo "Smoke test passed"

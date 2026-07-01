#!/bin/bash
# Purge the Cloudflare CDN cache for media.rediacc.com.
#
# Gotcha this script exists to prevent (hit twice during manual debugging):
# applying a new CORS policy or republishing a file does NOT retroactively
# fix already-cached responses. Any object fetched even once before a fix
# (e.g. a plain health-check curl with no Origin header) gets cached at the
# edge -- including the *absence* of a header -- for up to a year
# (Cache-Control: public, max-age=31536000). It'll keep serving the stale
# response until purged, even though the origin (R2) already has the fix.
# See .ci/docs/r2-media-setup.md #5b.
#
# Usage:
#   purge-media-cache.sh                # purge the whole media.rediacc.com hostname
#
# Environment (one of):
#   CLOUDFLARE_API_TOKEN              Pre-scoped bearer token
#   CF_GLOBAL_API_KEY + CF_EMAIL      Global API Key (full account access)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

ZONE_ID="9e802649c143c9cefd811d8fd671d31c" # rediacc.com
HOSTNAME="media.rediacc.com"

require_cmd curl
require_cmd jq

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    AUTH_HEADERS=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}")
elif [[ -n "${CF_GLOBAL_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
    AUTH_HEADERS=(-H "X-Auth-Key: ${CF_GLOBAL_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}")
else
    log_error "Set CLOUDFLARE_API_TOKEN, or CF_GLOBAL_API_KEY + CF_EMAIL"
    exit 1
fi

log_step "Purging Cloudflare cache for $HOSTNAME..."
RESPONSE="$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
    "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
    --data "{\"hosts\": [\"${HOSTNAME}\"]}")"

if [[ "$(echo "$RESPONSE" | jq -r '.success')" != "true" ]]; then
    log_error "Purge failed: $(echo "$RESPONSE" | jq -c '.errors')"
    exit 1
fi

log_info "Purge complete. Cache repopulates on next request (cf-cache-status: MISS then HIT)."

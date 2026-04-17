#!/bin/bash
# Purge a list of URLs from Cloudflare cache.
#
# Usage:
#   cf-purge-urls.sh --zone <ZONE_ID> url1 url2 ...
#   printf '%s\n' url1 url2 url3 | cf-purge-urls.sh --zone <ZONE_ID>
#
# Auth (in order tried):
#   1. $CLOUDFLARE_API_TOKEN  -> Authorization: Bearer
#   2. $CF_API_KEY + $CF_EMAIL -> X-Auth-Key + X-Auth-Email (global key)
#
# Why: releases.rediacc.com is an R2 bucket exposed via a CF custom domain.
# Even when uploads now set Cache-Control: no-cache, any pre-existing CF
# edge-cache entry from before the fix persists with its original (default)
# TTL, so apt-get update fetches the fresh InRelease but the old cached
# Packages.gz body, producing "File has unexpected size, Mirror sync in
# progress?" errors. Purging the just-uploaded URLs after each upload
# evicts those stale entries; the next request hits R2 origin (which now
# returns no-cache) and CF will not re-cache.
#
# Failure mode: purge is best-effort defence in depth -- the real fix
# against stale CF cache on releases.rediacc.com is the zone-level
# Cache Rule documented in .ci/docs/r2-setup.md. This script therefore
# always exits 0 even on credential/auth/API failures, and logs a
# ::warning:: so the CI run surfaces the issue without failing the job.
# If the Cache Rule is ever disabled, the purge returning API errors
# will still be visible as a warning and investigation can begin from
# there.

set -euo pipefail

ZONE_ID=""
URLS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --zone)
            ZONE_ID="$2"
            shift 2
            ;;
        --help | -h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            URLS+=("$1")
            shift
            ;;
    esac
done

if [[ -z "$ZONE_ID" ]]; then
    echo "::error::cf-purge-urls.sh: --zone <ZONE_ID> is required" >&2
    exit 1
fi

# Stdin URLs (one per line) on top of any positional ones.
if [[ ! -t 0 ]]; then
    while IFS= read -r line; do
        [[ -n "$line" ]] && URLS+=("$line")
    done
fi

TOTAL=${#URLS[@]}
if [[ $TOTAL -eq 0 ]]; then
    echo "cf-purge-urls.sh: no URLs to purge"
    exit 0
fi

# Pick auth method. CLOUDFLARE_API_TOKEN must have Zone.Cache Purge perm
# on the target zone; CF_API_KEY + CF_EMAIL is the global-key fallback.
AUTH_HEADERS=()
if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    AUTH_HEADERS=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN")
elif [[ -n "${CF_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
    AUTH_HEADERS=(-H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_API_KEY")
else
    echo "::warning::cf-purge-urls.sh: no Cloudflare credentials in env" \
        "(set CLOUDFLARE_API_TOKEN, or CF_API_KEY+CF_EMAIL); skipping purge" >&2
    exit 0
fi

echo "cf-purge-urls.sh: purging $TOTAL URL(s) from CF zone $ZONE_ID"

# CF API accepts up to 30 URLs per purge_cache request; chunk.
i=0
while [[ $i -lt $TOTAL ]]; do
    BATCH=("${URLS[@]:$i:30}")
    PAYLOAD=$(printf '%s\n' "${BATCH[@]}" | jq -R . | jq -sc '{files: .}')
    RESPONSE=$(curl -sS -X POST \
        "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
        "${AUTH_HEADERS[@]}" \
        -H "Content-Type: application/json" \
        --data "$PAYLOAD")
    SUCCESS=$(echo "$RESPONSE" | jq -r '.success // false')
    if [[ "$SUCCESS" != "true" ]]; then
        echo "::warning::CF purge failed for batch starting at index $i (best-effort; Cache Rule makes this non-critical):" >&2
        echo "$RESPONSE" | jq -c '.errors' >&2
        exit 0
    fi
    i=$((i + 30))
done

echo "cf-purge-urls.sh: purged $TOTAL URL(s) successfully"

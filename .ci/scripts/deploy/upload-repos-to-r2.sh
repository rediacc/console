#!/bin/bash
# Upload the built package repositories (apt/rpm/apk/archlinux) and the channel
# install scripts to R2, then purge the Cloudflare cache for every URL touched.
#
# WHY the Cache-Control policy below is "no-cache" and not "immutable":
# package-manager channel paths (apt/<channel>/, rpm/<channel>/, apk/<channel>/,
# archlinux/<channel>/) reuse filenames across releases -- the URL
# cli/edge/rdc-0.9.13.deb can serve DIFFERENT bytes from one CI run to the next
# because edge builds that happen to land on the same semver produce slightly
# different archives. Marking them "immutable" let CF cache a previous run's
# body under a URL the next run's APKINDEX points at with a different sha256 ->
# "BAD signature" cascades. no-cache means CF never caches (per
# developers.cloudflare.com/cache/concepts/default-cache-behavior), so there is
# no stale cached body to go stale. R2 origin is inside CF's network, so
# end-user install cost is not materially different. Truly-versioned paths
# (cli/v<semver>/, npm/<channel>/rediacc-cli-<semver>.tgz) keep their 1-year
# immutable cache; those are handled by upload-to-r2.sh.
#
# Usage:
#   .ci/scripts/deploy/upload-repos-to-r2.sh
#
# Required env:
#   CHANNEL                release channel to publish under, e.g. edge / pr-123
#   R2_ACCESS_KEY_ID       exported as AWS_ACCESS_KEY_ID for the aws CLI
#   R2_SECRET_ACCESS_KEY   exported as AWS_SECRET_ACCESS_KEY for the aws CLI
#   R2_ENDPOINT            S3 endpoint of the R2 bucket
#   CLOUDFLARE_API_TOKEN   read by cf-purge-urls.sh
#   CLOUDFLARE_ZONE_ID     zone whose cache is purged
#
# Reads dist/repos/{apt,rpm,apk,archlinux}/ and dist/pages/install.{sh,ps1}.
#
# Run locally (WRITES to R2 -- point R2_ENDPOINT at a scratch bucket first):
#   CHANNEL=pr-0 R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_ENDPOINT=... \
#     CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ZONE_ID=... \
#     .ci/scripts/deploy/upload-repos-to-r2.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. The only pipeline is `printf | cf-purge-urls.sh`, whose left
# side is a printf over a non-empty array, so pipefail cannot change the
# outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd aws
: "${CHANNEL:?upload-repos-to-r2.sh: CHANNEL must be set}"
: "${R2_ACCESS_KEY_ID:?upload-repos-to-r2.sh: R2_ACCESS_KEY_ID must be set}"
: "${R2_SECRET_ACCESS_KEY:?upload-repos-to-r2.sh: R2_SECRET_ACCESS_KEY must be set}"
: "${R2_ENDPOINT:?upload-repos-to-r2.sh: R2_ENDPOINT must be set}"
: "${CLOUDFLARE_ZONE_ID:?upload-repos-to-r2.sh: CLOUDFLARE_ZONE_ID must be set}"

# The dist/ paths and the cf-purge-urls.sh call below are repo-relative,
# exactly as they were in the workflow step.
cd "$(get_repo_root)"

export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

CC_MUTABLE="no-cache"

PURGE_URLS=()
for dir in apt rpm apk archlinux; do
    [[ -d "dist/repos/$dir" ]] || continue
    aws s3 sync "dist/repos/$dir" "s3://rediacc-releases/${dir}/${CHANNEL}/" \
        --cache-control "$CC_MUTABLE" \
        --endpoint-url "$R2_ENDPOINT" --quiet
    # Purge every uploaded URL to evict entries cached under the
    # old immutable policy. Once every CI cycle has re-uploaded
    # with no-cache, CF won't cache anything and subsequent purges
    # are cheap no-ops.
    while IFS= read -r f; do
        PURGE_URLS+=("https://releases.rediacc.com/${dir}/${CHANNEL}/${f#dist/repos/$dir/}")
    done < <(find "dist/repos/$dir" -type f)
done

# Upload install scripts (rewrite default channel so R2 copies
# under cli/${CHANNEL}/ install from ${CHANNEL} by default).
# Channel-pointer scripts are mutable.
for f in dist/pages/install.sh dist/pages/install.ps1; do
    [[ -f "$f" ]] || continue
    tmp="$(mktemp)"
    sed -e "s|REDIACC_CHANNEL:-stable|REDIACC_CHANNEL:-${CHANNEL}|g" \
        -e "s|} else { \"stable\" }|} else { \"${CHANNEL}\" }|g" \
        "$f" >"$tmp"
    aws s3 cp "$tmp" "s3://rediacc-releases/cli/${CHANNEL}/$(basename "$f")" \
        --cache-control "$CC_MUTABLE" \
        --endpoint-url "$R2_ENDPOINT" --quiet
    rm -f "$tmp"
    PURGE_URLS+=("https://releases.rediacc.com/cli/${CHANNEL}/$(basename "$f")")
done
echo "Repos uploaded to R2 channel: ${CHANNEL}"

# Purge CF cache for the mutable URLs we just (re)uploaded. Existing
# cached entries from before the no-cache fix would otherwise persist
# with their original (default) TTL, breaking apt-get update with
# "File has unexpected size".
if [[ ${#PURGE_URLS[@]} -gt 0 ]]; then
    printf '%s\n' "${PURGE_URLS[@]}" |
        .ci/scripts/deploy/cf-purge-urls.sh --zone "$CLOUDFLARE_ZONE_ID"
fi

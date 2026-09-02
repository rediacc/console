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
#   CLOUDFLARE_R2_ACCESS_KEY_ID       exported as AWS_ACCESS_KEY_ID for the aws CLI
#   CLOUDFLARE_R2_SECRET_ACCESS_KEY   exported as AWS_SECRET_ACCESS_KEY for the aws CLI
#   CLOUDFLARE_R2_ENDPOINT            S3 endpoint of the R2 bucket
#   CLOUDFLARE_API_TOKEN   read by cf-purge-urls.sh
#   CLOUDFLARE_ZONE_ID     zone whose cache is purged
#   SKIP_RELEASE           truthy (1/true/yes/y/on) when the merge carried
#                          'bump-none'. On a release channel NOTHING is written.
#
# Reads dist/repos/{apt,rpm,apk,archlinux}/ and dist/pages/install.{sh,ps1}.
#
# Run locally (WRITES to R2 -- point CLOUDFLARE_R2_ENDPOINT at a scratch bucket first):
#   CHANNEL=pr-0 CLOUDFLARE_R2_ACCESS_KEY_ID=... CLOUDFLARE_R2_SECRET_ACCESS_KEY=... CLOUDFLARE_R2_ENDPOINT=... \
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
: "${CLOUDFLARE_R2_ACCESS_KEY_ID:?upload-repos-to-r2.sh: CLOUDFLARE_R2_ACCESS_KEY_ID must be set}"
: "${CLOUDFLARE_R2_SECRET_ACCESS_KEY:?upload-repos-to-r2.sh: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set}"
: "${CLOUDFLARE_R2_ENDPOINT:?upload-repos-to-r2.sh: CLOUDFLARE_R2_ENDPOINT must be set}"
: "${CLOUDFLARE_ZONE_ID:?upload-repos-to-r2.sh: CLOUDFLARE_ZONE_ID must be set}"

# =============================================================================
# bump-none: the release was skipped, so NOTHING may be written
# =============================================================================
# This script is channel-pointer-only end to end: every path it writes is
# <repo>/${CHANNEL}/ or cli/${CHANNEL}/install.{sh,ps1}. On a bump-none merge
# there is no tag and no GitHub Release, so advancing those pointers publishes a
# version that does not exist. Same contract as upload-to-r2.sh's guard; this
# script takes no argv, so the signal arrives only as SKIP_RELEASE.
#
# Scoped to the release channels: a pr-N channel has no tag contract.
#
# SKIP_RELEASE_GUARD_BEGIN (anchor for the gate test's planted defects --
# .ci/scripts/test/gates/test-skip-release-channel-pointer.sh assembles its
# mutants by splitting this file on these two markers; do not remove them)
skip_release_requested() {
    case "${SKIP_RELEASE:-}" in
        true | TRUE | True | 1 | yes | YES | y | on | ON) return 0 ;;
        *) return 1 ;;
    esac
}

if skip_release_requested; then
    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        echo ""
        echo "================================================================"
        echo "  RELEASE SKIPPED (bump-none) -- NOTHING WAS WRITTEN TO R2"
        echo "================================================================"
        echo "  channel:  ${CHANNEL}"
        echo ""
        echo "  The merged PR carried the 'bump-none' label, so no tag and no"
        echo "  GitHub Release exist for this build. The package repositories"
        echo "  and install scripts are channel pointers, so publishing them"
        echo "  would advertise a version nobody can install."
        echo ""
        echo "  NOT written:"
        echo "    - apt/${CHANNEL}/  rpm/${CHANNEL}/  apk/${CHANNEL}/  archlinux/${CHANNEL}/"
        echo "    - cli/${CHANNEL}/install.sh  cli/${CHANNEL}/install.ps1"
        echo "    - no Cloudflare cache purge (nothing changed)"
        echo ""
        echo "  This is the intended outcome of a bump-none merge, not an error."
        echo "================================================================"
        echo ""
        exit 0
    fi
    echo "upload-repos-to-r2.sh: SKIP_RELEASE ignored on channel '${CHANNEL}': not a release channel, uploading as usual"
fi
# SKIP_RELEASE_GUARD_END

# The dist/ paths and the cf-purge-urls.sh call below are repo-relative,
# exactly as they were in the workflow step.
cd "$(get_repo_root)"

export AWS_ACCESS_KEY_ID="${CLOUDFLARE_R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${CLOUDFLARE_R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

CC_MUTABLE="no-cache"

PURGE_URLS=()
for dir in apt rpm apk archlinux; do
    [[ -d "dist/repos/$dir" ]] || continue
    aws s3 sync "dist/repos/$dir" "s3://rediacc-releases/${dir}/${CHANNEL}/" \
        --cache-control "$CC_MUTABLE" \
        --endpoint-url "$CLOUDFLARE_R2_ENDPOINT" --quiet
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
        --endpoint-url "$CLOUDFLARE_R2_ENDPOINT" --quiet
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

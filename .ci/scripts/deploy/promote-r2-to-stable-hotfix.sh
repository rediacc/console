#!/bin/bash
# Hotfix promotion: copy every R2 release channel from edge/ to stable/ inline
# with the release, skipping the normal 7-day soak.
#
# WHY: this is the emergency lane used by `Release` with publish_stable=true.
# The scheduled, soak-gated path is .ci/scripts/deploy/promote-r2-to-stable.sh
# (driven by promote-stable.yml), which does a two-phase metadata-last upload.
# This one is a straight recursive copy: a hotfix is by definition urgent and
# the version being promoted has just been published, so the window in which a
# client could see new metadata before new bytes is the same window the release
# itself already opened.
#
# Cache-Control policy: channel paths (apt/<channel>/, cli/<channel>/, ...)
# reuse filenames across releases, so none of them is safe to cache -- a
# previous run's cached body under the same URL breaks APKINDEX/Release
# signatures. Everything goes no-cache; CF never caches, so no stale body is
# possible. Truly-versioned paths (cli/v<semver>/, npm/<channel>/
# rediacc-cli-<semver>.tgz) keep their immutable cache via upload-to-r2.sh.
#
# Usage:
#   .ci/scripts/deploy/promote-r2-to-stable-hotfix.sh
#
# Required env:
#   R2_ACCESS_KEY_ID       R2 credentials, exported as AWS_* for the aws CLI
#   R2_SECRET_ACCESS_KEY
#   R2_ENDPOINT            R2 S3 endpoint
#
# Optional env:
#   CLOUDFLARE_ZONE_ID     zone to purge; the purge is best-effort and is the
#   CLOUDFLARE_API_TOKEN   last thing this script does, so a missing/void
#                          credential cannot leave the promotion half-done
#
# NOTE: this MUTATES the production stable channel. Do not run it locally
# against real credentials.
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here. Every variable is env-wired or locally assigned, and the only
# pipeline is the final purge (already the last command of an && chain, so its
# status reached the shell either way).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd aws
: "${R2_ACCESS_KEY_ID:?promote-r2-to-stable-hotfix.sh: R2_ACCESS_KEY_ID must be set}"
: "${R2_SECRET_ACCESS_KEY:?promote-r2-to-stable-hotfix.sh: R2_SECRET_ACCESS_KEY must be set}"
: "${R2_ENDPOINT:?promote-r2-to-stable-hotfix.sh: R2_ENDPOINT must be set}"

export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"
EP="--endpoint-url $R2_ENDPOINT"
BUCKET="rediacc-releases"

CC_MUTABLE="no-cache"

PURGE_URLS=()
for dir in cli apt rpm apk archlinux; do
    echo "Promoting ${dir}/edge/ -> ${dir}/stable/"
    TMP="/tmp/promote-${dir}"
    aws s3 cp "s3://${BUCKET}/${dir}/edge/" "$TMP/" $EP --recursive --quiet
    aws s3 cp "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --recursive --quiet \
        --cache-control "$CC_MUTABLE"
    # Purge every uploaded URL to flush any previously-cached body
    # under the same filename; channel paths reuse filenames across
    # releases.
    while IFS= read -r f; do
        PURGE_URLS+=("https://releases.rediacc.com/${dir}/stable/${f#"$TMP"/}")
    done < <(find "$TMP" -type f)
    rm -rf "$TMP"
done

# Fix channel references in config files (mutable channel pointers).
for file in rpm/stable/rediacc.repo archlinux/stable/rediacc.conf; do
    aws s3 cp "s3://${BUCKET}/${file}" /tmp/config $EP --quiet
    sed_in_place 's|/edge/|/stable/|g' /tmp/config
    aws s3 cp /tmp/config "s3://${BUCKET}/${file}" $EP --quiet \
        --cache-control "$CC_MUTABLE"
    PURGE_URLS+=("https://releases.rediacc.com/${file}")
done

# Re-bake install scripts: cd-stage.yml baked 'edge' into
# cli/edge/install.{sh,ps1}; the raw copy above carried that into
# cli/stable/. Rewrite back to stable. Channel-pointer scripts
# are mutable.
for file in cli/stable/install.sh cli/stable/install.ps1; do
    aws s3 cp "s3://${BUCKET}/${file}" /tmp/script $EP --quiet
    sed_in_place \
        -e 's|REDIACC_CHANNEL:-edge|REDIACC_CHANNEL:-stable|g' \
        -e 's|} else { "edge" }|} else { "stable" }|g' \
        /tmp/script
    aws s3 cp /tmp/script "s3://${BUCKET}/${file}" $EP --quiet \
        --cache-control "$CC_MUTABLE"
    PURGE_URLS+=("https://releases.rediacc.com/${file}")
done

echo "R2 promoted to stable"

# Purge CF cache for the mutable URLs we just (re)uploaded.
if [[ ${#PURGE_URLS[@]} -gt 0 ]]; then
    printf '%s\n' "${PURGE_URLS[@]}" |
        "$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"
fi

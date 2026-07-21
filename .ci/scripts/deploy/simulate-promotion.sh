#!/bin/bash
# Simulate an edge->stable promotion into a throwaway "<channel>-promoted" R2
# channel, so the package-manager install tests can be run against promoted
# bytes BEFORE a real promotion happens.
#
# WHY THIS EXISTS: promotion rewrites channel paths, and the install tests that
# follow (apt/dnf/apk/pacman) must exercise those rewritten paths. Doing it
# against a temporary channel means a broken promotion is caught in CI instead
# of after `promote-stable` has already moved production bytes.
#
# Usage:
#   CHANNEL=pr-123 \
#   AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... R2_ENDPOINT=... \
#   CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ZONE_ID=... \
#     .ci/scripts/deploy/simulate-promotion.sh
#
# Required env:
#   CHANNEL                 source channel (e.g. pr-123, edge)
#   AWS_ACCESS_KEY_ID       R2 access key      (secret — passed via env, never argv)
#   AWS_SECRET_ACCESS_KEY   R2 secret key      (secret)
#   R2_ENDPOINT             R2 S3 endpoint URL (secret)
#   CLOUDFLARE_API_TOKEN    for the cache purge (secret)
#   CLOUDFLARE_ZONE_ID      zone whose cache is purged
# Optional env:
#   GITHUB_ENV              when set, PROMOTED is exported back to later steps
#
# Deliberately NOT `set -x`: this repo's CI logs are public and this script
# handles R2 credentials plus a Cloudflare token. Masking covers today's values,
# but tracing every expanded command is one unmasked value away from a leak.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

require_cmd aws
require_cmd find

: "${CHANNEL:?CHANNEL is required (the source channel, e.g. pr-123)}"
[[ -n "${AWS_ACCESS_KEY_ID:-}" ]] || {
    log_error "R2_ACCESS_KEY_ID not set"
    exit 1
}
[[ -n "${R2_ENDPOINT:-}" ]] || {
    log_error "R2_ENDPOINT not set"
    exit 1
}

PROMOTED="${CHANNEL}-promoted"
BUCKET="rediacc-releases"
EP=(--endpoint-url "$R2_ENDPOINT")

# Hand PROMOTED back to subsequent workflow steps when running under Actions.
[[ -n "${GITHUB_ENV:-}" ]] && echo "PROMOTED=${PROMOTED}" >>"$GITHUB_ENV"

# R2's S3 API drops multi-MB streams under the CLI's default 10-way
# parallelism (IncompleteRead mid-transfer; 3 consecutive job failures on
# 2026-06-10 with zero Cloudflare incidents). Tame the transfer profile: few
# concurrent requests, big multipart threshold so ~8MB debs are single GETs,
# no read timeout.
aws configure set default.s3.max_concurrent_requests 3
aws configure set default.s3.multipart_threshold 64MB
aws configure set default.s3.multipart_chunksize 32MB

# Wrap transfers in a retry loop. AWS_MAX_ATTEMPTS=10 + AWS_RETRY_MODE=adaptive
# layer retries inside the SDK; the outer loop covers SDK budget exhaustion.
# Recursive transfers use `aws s3 sync`, so every outer retry RESUMES
# (already-complete files are skipped) instead of restarting the whole tree —
# with `cp --recursive`, one broken stream anywhere restarted hundreds of MB
# from scratch and the 5 attempts never converged.
aws_s3_cp_retry() {
    local attempt
    for attempt in 1 2 3 4 5; do
        if aws s3 cp --cli-read-timeout 0 "$@"; then
            return 0
        fi
        if [[ $attempt -eq 5 ]]; then
            log_error "aws s3 cp $* failed after 5 attempts"
            return 1
        fi
        log_warn "aws s3 cp attempt $attempt failed, retrying in $((attempt * 15))s..."
        sleep $((attempt * 15))
    done
}

aws_s3_sync_retry() {
    local attempt
    for attempt in 1 2 3 4 5; do
        if aws s3 sync --cli-read-timeout 0 "$@"; then
            return 0
        fi
        if [[ $attempt -eq 5 ]]; then
            log_error "aws s3 sync $* failed after 5 attempts"
            return 1
        fi
        log_warn "aws s3 sync attempt $attempt failed, retrying in $((attempt * 15))s... (resumes incomplete files)"
        sleep $((attempt * 15))
    done
}

# Cache-Control policy: channel paths reuse filenames per release, so nothing
# under <fmt>/<promoted>/ is safe to cache. Everything uploads no-cache; CF will
# not cache it, so the subsequent test_apt_install / test_apk_install cannot hit
# a stale POP.
CC_MUTABLE="no-cache"

PURGE_URLS=()

# Copy all repo formats from the source channel to the promoted channel.
# R2 doesn't support GetObjectTagging, so download+reupload via a local tmp.
for dir in apt rpm apk archlinux; do
    log_info "Copying ${dir}/${CHANNEL}/ -> ${dir}/${PROMOTED}/"
    TMP="/tmp/promote-${dir}"
    aws_s3_sync_retry "s3://${BUCKET}/${dir}/${CHANNEL}/" "$TMP/" "${EP[@]}"
    aws_s3_sync_retry "$TMP/" "s3://${BUCKET}/${dir}/${PROMOTED}/" "${EP[@]}" \
        --cache-control "$CC_MUTABLE"
    # Purge every uploaded URL to flush any previously-cached body under the
    # same filename.
    while IFS= read -r f; do
        PURGE_URLS+=("https://releases.rediacc.com/${dir}/${PROMOTED}/${f#"$TMP"/}")
    done < <(find "$TMP" -type f)
    rm -rf "$TMP"
done

# Sed-fix config files (replace channel in URLs). Mutable.
for file in "rpm/${PROMOTED}/rediacc.repo" "archlinux/${PROMOTED}/rediacc.conf"; do
    if aws s3 cp "s3://${BUCKET}/${file}" /tmp/config "${EP[@]}" 2>/dev/null; then
        sed_in_place "s|/${CHANNEL}/|/${PROMOTED}/|g" /tmp/config
        aws_s3_cp_retry /tmp/config "s3://${BUCKET}/${file}" "${EP[@]}" \
            --cache-control "$CC_MUTABLE"
        PURGE_URLS+=("https://releases.rediacc.com/${file}")
        log_info "Fixed channel in ${file}"
    fi
done

log_info "Promotion simulated: ${CHANNEL} -> ${PROMOTED}"

# Purge the CF cache for the mutable URLs just uploaded. Without this the
# test_apt_install step that runs next can hit a CF edge POP holding a stale
# Packages.gz from a previous CI run, even though we just uploaded fresh
# content with Cache-Control: no-cache.
if [[ ${#PURGE_URLS[@]} -gt 0 ]]; then
    printf '%s\n' "${PURGE_URLS[@]}" |
        .ci/scripts/deploy/cf-purge-urls.sh --zone "$CLOUDFLARE_ZONE_ID"
fi

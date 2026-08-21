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
#
# An aws_s3_sync_retry sat beside this, and its resume-vs-restart reasoning
# mattered while the whole channel was synced THROUGH the runner. The channel
# copy is server-side now (see below), so nothing recursive streams here any
# more and that helper had no caller left. It is DELETED rather than kept in
# case: check:ci-dead-bash caught it, and a helper nobody calls is a claim about
# the code that is no longer true.
#
# This one survives because the sed-fix step below still downloads and
# re-uploads two small config files, which is a genuine byte transfer.
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

# Cache-Control policy: channel paths reuse filenames per release, so nothing
# under <fmt>/<promoted>/ is safe to cache. Everything uploads no-cache; CF will
# not cache it, so the subsequent test_apt_install / test_apk_install cannot hit
# a stale POP.
CC_MUTABLE="no-cache"

PURGE_URLS=()

# Copy all repo formats from the source channel to the promoted channel,
# SERVER-SIDE: the bytes never leave R2.
#
# WHY THIS CHANGED. The old form synced the whole channel DOWN to /tmp and back
# UP again, so the job cost two full transfers of a channel that grows with
# every release. ci.yml's validate-promote comment tracked the trend and called
# this exact shot: 21m57s on 2026-07-27, 30m51s on 2026-08-07 (cancelled at the
# then-30-minute ceiling), 57m01s on 2026-08-18 with three minutes to spare,
# and 61m12s on 2026-08-20, which blew the raised 60-minute ceiling and took
# CI Complete and Pipeline Sentinel down with it. That comment says plainly that
# 60 buys headroom and does not fix the growth, and that the copy should become
# incremental rather than the number being raised again. The log of the failed
# job carries ZERO retry warnings and was killed mid-transfer, so this is size,
# not flakiness.
#
# "Incremental" cannot mean "skip what is already there": PROMOTED is created
# fresh and deleted at the end of every run, so its destination always starts
# empty. The actual lever is not transferring the bytes through the runner at
# all.
#
# WHY IT WAS NOT ALREADY SERVER-SIDE, and why `aws s3 sync` cannot do it.
# R2 does not implement the object-tagging surface, and `aws s3 sync`/`cp` reach
# for it on EVERY s3-to-s3 path, in both directions:
#
#   --copy-props default  -> client-side GetObjectTagging, which R2 lacks. This
#                            is the gap the original comment recorded.
#   --copy-props none     -> sends `x-amz-tagging-directive: REPLACE`, and R2
#                            answers CopyObject with
#                            "NotImplemented: Header 'x-amz-tagging-directive'
#                            with value 'REPLACE' not implemented"
#                            (measured on run 32465461193, every object).
#   --copy-props metadata-directive -> same REPLACE header, because "does not
#                            copy tags" is implemented by replacing them.
#
# So no flag combination makes the high-level command work here. `s3api
# copy-object` sends ONLY the parameters named, and `--tagging-directive` is
# omitted below, so neither the tag read nor the tag replace is ever attempted.
# `--metadata-directive REPLACE` is required because we set a new Cache-Control.
#
# Parallelism replaces what `sync` gave for free. The copies are independent and
# server-side, so they are dispatched through xargs -P; the transfer profile
# tuned above governs byte streams, which these no longer are.
SRC_PREFIX=""
DST_PREFIX=""
export BUCKET CC_MUTABLE R2_ENDPOINT SRC_PREFIX DST_PREFIX

copy_one_object() {
    local src_key="$1"
    # A key that does not start with SRC_PREFIX would make the strip below a
    # silent no-op and write to a DOUBLED destination
    # (apk/edge-promoted/apt/edge/...). Refuse instead: a wrong destination is
    # worse than a failed copy, because the install tests that follow would
    # then read a channel nobody wrote.
    if [[ "$src_key" != "$SRC_PREFIX"* ]]; then
        echo "key '$src_key' is not under expected prefix '$SRC_PREFIX'" >&2
        return 1
    fi
    local dst_key="${DST_PREFIX}${src_key#"$SRC_PREFIX"}"
    local attempt
    for attempt in 1 2 3; do
        if aws s3api copy-object \
            --bucket "$BUCKET" \
            --key "$dst_key" \
            --copy-source "${BUCKET}/${src_key}" \
            --metadata-directive REPLACE \
            --cache-control "$CC_MUTABLE" \
            --endpoint-url "$R2_ENDPOINT" >/dev/null; then
            return 0
        fi
        [[ $attempt -eq 3 ]] && {
            echo "copy-object failed after 3 attempts: $src_key" >&2
            return 1
        }
        sleep $((attempt * 5))
    done
}
export -f copy_one_object

for dir in apt rpm apk archlinux; do
    log_info "Copying ${dir}/${CHANNEL}/ -> ${dir}/${PROMOTED}/ (server-side)"
    SRC_PREFIX="${dir}/${CHANNEL}/"
    DST_PREFIX="${dir}/${PROMOTED}/"
    export SRC_PREFIX DST_PREFIX

    KEYS="$(mktemp)"
    aws s3 ls "s3://${BUCKET}/${SRC_PREFIX}" --recursive "${EP[@]}" |
        awk '{ for (i = 4; i <= NF; i++) printf "%s%s", $i, (i < NF ? OFS : ORS) }' >"$KEYS"

    # An empty listing is a FAILURE, not a fast success: the install tests that
    # follow would then run against an empty channel and pass while proving
    # nothing.
    if [[ ! -s "$KEYS" ]]; then
        rm -f "$KEYS"
        log_error "no objects found under ${SRC_PREFIX}; refusing to promote an empty channel"
        exit 1
    fi

    xargs -P 8 -I{} bash -c 'copy_one_object "$@"' _ {} <"$KEYS"

    while IFS= read -r key; do
        [[ -n "$key" ]] || continue
        PURGE_URLS+=("https://releases.rediacc.com/${DST_PREFIX}${key#"$SRC_PREFIX"}")
    done <"$KEYS"
    rm -f "$KEYS"
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

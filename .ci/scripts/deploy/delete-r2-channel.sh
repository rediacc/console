#!/bin/bash
# Delete a PR's R2 channel artifacts, plus the "-promoted" copy the
# promotion-simulation test creates.
#
# Every release uploads under <format>/<channel>/, so without this each closed
# PR leaves a channel behind forever.
#
# Deletes are best-effort (`|| true`): a channel that was never created is not
# an error, and this runs on PR close where failing helps nobody.
#
# Usage:
#   CHANNEL=pr-123 RELEASES_BUCKET=rediacc-releases R2_ENDPOINT=... \
#   AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... \
#     .ci/scripts/deploy/delete-r2-channel.sh
#
# Required env:
#   CHANNEL, RELEASES_BUCKET, R2_ENDPOINT
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   (secrets — env, never argv)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd aws
: "${CHANNEL:?CHANNEL is required (e.g. pr-123)}"
: "${RELEASES_BUCKET:?RELEASES_BUCKET is required}"
: "${R2_ENDPOINT:?R2_ENDPOINT is required}"

log_info "Cleaning up R2 channel: ${CHANNEL}..."

for dir in cli npm apt rpm apk archlinux; do
    aws s3 rm "s3://${RELEASES_BUCKET}/${dir}/${CHANNEL}/" \
        --recursive --endpoint-url "$R2_ENDPOINT" 2>/dev/null || true
    # Also clean up promotion-simulation artifacts.
    aws s3 rm "s3://${RELEASES_BUCKET}/${dir}/${CHANNEL}-promoted/" \
        --recursive --endpoint-url "$R2_ENDPOINT" 2>/dev/null || true
done

log_info "Channel '${CHANNEL}' (+ promoted) deleted from R2"

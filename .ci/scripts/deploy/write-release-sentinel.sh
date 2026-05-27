#!/bin/bash
# Write the `.released` commit sentinels for a release.
#
# This is the ATOMIC COMMIT POINT of the release pipeline. It runs from the
# finalize-release-sentinel CI job, AFTER every gate that must pass before a
# version is considered released (stage-artifacts, validate-install,
# validate-promote, all test suites). Writing the sentinel seals the version:
# from this point on, write_once_guard in upload-to-r2.sh refuses to overwrite
# the bytes, and the drift gate requires a matching git tag.
#
# See .ci/scripts/lib/release-state-validator.sh for the invariant.
#
# Usage:
#   write-release-sentinel.sh --version 1.0.5 --channel edge --commit-sha <sha> \
#     [--desktop]
#
# Flags:
#   --version      (required) Semver version WITHOUT the leading `v`.
#   --channel      (required) Release channel: edge | stable.
#   --commit-sha   (required) Git commit SHA that produced the artifacts.
#   --desktop      Emit desktop sentinel in addition to cli (platform-aware CI
#                  sets this only if desktop artifacts were produced).
#
# Env (required):
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT
#   RELEASES_BUCKET (optional, default rediacc-releases)
#
# Exit 0 on successful write + readback of every sentinel. Exit 1 on any
# failure — no partial commit. The finalize job must fail loud so the next
# CI run's pre-upload scrub can recover from the orphaned state.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/release-state-validator.sh
source "$SCRIPT_DIR/../lib/release-state-validator.sh"

VERSION=""
CHANNEL=""
COMMIT_SHA=""
INCLUDE_DESKTOP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="${2:-}"
            shift 2
            ;;
        --channel)
            CHANNEL="${2:-}"
            shift 2
            ;;
        --commit-sha)
            COMMIT_SHA="${2:-}"
            shift 2
            ;;
        --desktop)
            INCLUDE_DESKTOP=true
            shift
            ;;
        *)
            log_error "unknown flag: $1"
            exit 2
            ;;
    esac
done

[[ -z "$VERSION" ]] && {
    log_error "--version required"
    exit 2
}
[[ -z "$CHANNEL" ]] && {
    log_error "--channel required"
    exit 2
}
[[ -z "$COMMIT_SHA" ]] && {
    log_error "--commit-sha required"
    exit 2
}
if [[ "$CHANNEL" != "edge" && "$CHANNEL" != "stable" ]]; then
    log_error "sentinel write is only valid on release channels (edge|stable); got: $CHANNEL"
    exit 2
fi

require_cmd aws
require_cmd jq
require_var R2_ACCESS_KEY_ID
require_var R2_SECRET_ACCESS_KEY
require_var R2_ENDPOINT
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

VERSION_TAG="v${VERSION}"

# Payload intentionally includes what a post-hoc forensic sweep needs to
# reconstruct what CI intended: channel, commit, timestamp, and which product
# prefixes were populated this run.
build_payload() {
    local product="$1"
    jq -nc \
        --arg version "$VERSION_TAG" \
        --arg channel "$CHANNEL" \
        --arg commit "$COMMIT_SHA" \
        --arg product "$product" \
        --arg released_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --argjson include_desktop "$INCLUDE_DESKTOP" \
        '{
            version: $version,
            channel: $channel,
            commit_sha: $commit,
            product: $product,
            released_at: $released_at,
            artifacts_produced: (
                ["cli"] + (if $include_desktop then ["desktop"] else [] end)
            )
        }'
}

write_sentinel() {
    local product="$1"
    local key="${product}/${VERSION_TAG}/${RSV_SENTINEL_KEY}"

    # Defense in depth: never seal a prefix that has no binaries. Writing
    # `.released` over an empty/partial prefix manufactures the corrupt
    # "sealed-but-empty" state (sentinel blocks re-upload, every versioned
    # install 404s). Pairs with the no-scrub guard in upload-to-r2.sh.
    local bin_count
    bin_count="$(rsv_binary_count "${product}/${VERSION_TAG}/")"
    if [[ "$bin_count" -le 0 ]]; then
        log_error "refusing to seal ${product}/${VERSION_TAG}/: prefix has no binaries (count=${bin_count})."
        log_error "  Sealing an empty prefix would create the sealed-but-empty corrupt state."
        return 1
    fi

    local payload
    payload="$(build_payload "$product")"

    log_step "writing sentinel: s3://${RSV_BUCKET}/${key}"
    # printf '%s' over echo -n for portability: echo -n handling varies by
    # shell/platform, printf is POSIX-guaranteed.
    printf '%s' "$payload" |
        aws s3 cp - "s3://${RSV_BUCKET}/${key}" \
            --endpoint-url "$R2_ENDPOINT" \
            --cache-control "no-cache" \
            --content-type "application/json"

    # Readback verification — do not trust a silent upload.
    local readback
    readback="$(rsv_get_sentinel_payload "$product" "$VERSION_TAG")"
    if [[ -z "$readback" ]]; then
        log_error "sentinel readback failed: s3://${RSV_BUCKET}/${key} is missing immediately after write"
        return 1
    fi
    # Compare the version field; the timestamp may differ by seconds on R2.
    local wanted_v got_v
    wanted_v="$(jq -r '.version' <<<"$payload")"
    got_v="$(jq -r '.version' <<<"$readback")"
    if [[ "$wanted_v" != "$got_v" ]]; then
        log_error "sentinel readback content mismatch at s3://${RSV_BUCKET}/${key}"
        log_error "  wrote version=${wanted_v}, read back version=${got_v}"
        return 1
    fi
    log_info "  sealed ${product}/${VERSION_TAG}/${RSV_SENTINEL_KEY}"
}

# Order matters: cli FIRST, desktop SECOND. The bijection assertion permits
# cli-only (desktop absent) but forbids desktop-only (the library enforces
# `desktop sentinel ⇒ cli sentinel`). Writing cli first keeps the half-written
# state benign: a cancel between the two writes leaves cli committed and
# desktop orphaned, which the drift gate flags as drift (not as a silent pass).

write_sentinel cli

if [[ "$INCLUDE_DESKTOP" == "true" ]]; then
    write_sentinel desktop
else
    log_info "desktop sentinel skipped (--desktop not set)"
fi

log_info "release ${VERSION_TAG} on ${CHANNEL} is sealed"

# Ratchet advance is intentionally NOT done here. The release-contract-floor
# ratchet file (.ci/config/release-contract-floor.txt) is updated + committed
# by cd-v2.yml's tag-and-release job ("Advance release-contract-floor
# ratchet" step). That job already has the app-token + permissions to commit
# to main; doing the advance there keeps the writer authoritative and avoids
# split-brain between this script and cd-v2.

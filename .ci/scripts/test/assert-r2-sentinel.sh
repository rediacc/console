#!/bin/bash
# Assert that the R2 versioned sentinels are sealed post-upload.
#
# Replaces the dead key-based sentinel check in upload-to-r2.sh (finding A):
# the previous guard looked at cli/v${V}/manifest.json -- a file nothing
# ever wrote, so the sentinel was always empty and the guard silently let
# retries overwrite the binaries. The new prefix-based guard requires that
# ALL binaries for the version live under cli/v${V}/ and desktop/v${V}/;
# this script verifies the invariant after upload succeeds.
#
# Only meaningful on stable / edge channels (only those channels write to
# cli/v<version>/). Exits 0 on empty CHANNEL or non-release channel.
#
# Usage: assert-r2-sentinel.sh <channel> <version>
# Env required when channel in {stable,edge}:
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/release-state-validator.sh
source "$SCRIPT_DIR/../lib/release-state-validator.sh"

CHANNEL="${1:-}"
VERSION="${2:-}"
BUCKET="${RELEASES_BUCKET:-rediacc-releases}"

if [[ -z "$CHANNEL" ]]; then
    log_info "Channel is empty; skipping sentinel assertion"
    exit 0
fi
if [[ "$CHANNEL" != "stable" && "$CHANNEL" != "edge" ]]; then
    log_info "Channel '${CHANNEL}' is not a release channel; skipping sentinel assertion"
    exit 0
fi
if [[ -z "$VERSION" ]]; then
    log_error "VERSION is required for sentinel assertion"
    exit 2
fi

require_cmd aws
require_var R2_ACCESS_KEY_ID
require_var R2_SECRET_ACCESS_KEY
require_var R2_ENDPOINT

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

FAILED=false

# Count BINARIES (objects excluding the `.released` sentinel), not raw objects.
# A "sealed-but-empty" prefix (.released present, binaries scrubbed) has one
# object and would pass a naive count>0 check while every versioned install
# 404s. rsv_binary_count excludes the sentinel; combined with rsv_sentinel_exists
# it tells the healthy case (binaries present) apart from sealed-but-empty.
for prefix in "cli/v${VERSION}/" "desktop/v${VERSION}/"; do
    product="${prefix%%/*}"
    bin_count="$(rsv_binary_count "$prefix")"
    if [[ "$bin_count" -gt 0 ]]; then
        log_info "s3://${BUCKET}/${prefix} contains $bin_count binary object(s)"
    elif rsv_sentinel_exists "$product" "v${VERSION}"; then
        log_error "SEALED-BUT-EMPTY: s3://${BUCKET}/${prefix} has a .released sentinel but NO binaries."
        log_error "  A prior orphan-scrub deleted the bytes; every versioned install of this product will 404."
        log_error "  Remediation: scrub the sentinel then re-run CI: scripts/dev/scrub-sentinel.sh v${VERSION} --execute"
        FAILED=true
    else
        log_error "R2 versioned prefix s3://${BUCKET}/${prefix} is empty after upload (no binaries, no sentinel)."
        log_error "  The CLI/desktop upload loop did not populate the versioned path."
        FAILED=true
    fi
done

if [[ "$FAILED" == "true" ]]; then
    log_error "Versioned release prefix is not in a healthy sealed state."
    exit 1
fi

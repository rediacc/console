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

for prefix in "cli/v${VERSION}/" "desktop/v${VERSION}/"; do
    # Use the r2_count_objects helper instead of `aws s3 ls | wc -l`:
    # `aws s3 ls --recursive` returns exit 1 on empty prefixes, which under
    # `set -eo pipefail` would silently abort this script before the if-check
    # below ever ran. The helper normalises empty prefixes to "0".
    count="$(r2_count_objects "$BUCKET" "$prefix" "$R2_ENDPOINT")"
    if [[ "$count" -eq 0 ]]; then
        log_error "R2 versioned prefix s3://${BUCKET}/${prefix} is empty after upload."
        FAILED=true
    else
        log_info "s3://${BUCKET}/${prefix} contains $count entries"
    fi
done

if [[ "$FAILED" == "true" ]]; then
    log_error "Write-once guard would silently allow overwrites of a non-empty sentinel."
    log_error "Fix the CLI/desktop upload loop so it populates cli/v\${V}/ and desktop/v\${V}/."
    exit 1
fi

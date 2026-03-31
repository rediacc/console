#!/bin/bash
# Promote R2 staging artifacts to production channels (edge + stable).
#
# Copies CLI binaries, packages, desktop artifacts, and repo metadata
# (apt/, rpm/, apk/, archlinux/) from staging/{sha}/ to their final paths.
#
# Usage:
#   promote-r2-staging.sh --sha <commit-sha> --version <version>
#
# Required env vars:
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

SHA=""
VERSION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sha)
            SHA="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        *)
            log_error "Unknown: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$SHA" || -z "$VERSION" ]]; then
    log_error "Usage: promote-r2-staging.sh --sha <sha> --version <version>"
    exit 1
fi

require_cmd aws

export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID required}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY required}"
export AWS_DEFAULT_REGION="auto"

ENDPOINT="${R2_ENDPOINT:?R2_ENDPOINT required}"
BUCKET="${RELEASES_BUCKET}"
S3="aws s3 --endpoint-url $ENDPOINT"

STAGING_PREFIX="staging/${SHA}"

log_step "Promoting R2 staging to production channels"
log_info "  Source: s3://${BUCKET}/${STAGING_PREFIX}/"
log_info "  Version: v${VERSION}"

# Promote CLI binaries + manifests (versioned + edge + stable channels)
log_step "Promoting CLI artifacts..."
$S3 sync "s3://${BUCKET}/${STAGING_PREFIX}/cli/" "s3://${BUCKET}/cli/" --quiet
log_info "CLI promoted to cli/v${VERSION}/, cli/edge/, cli/stable/"

# Promote packages (versioned path)
if $S3 ls "s3://${BUCKET}/${STAGING_PREFIX}/packages/" >/dev/null 2>&1; then
    log_step "Promoting Linux packages..."
    $S3 sync "s3://${BUCKET}/${STAGING_PREFIX}/packages/" "s3://${BUCKET}/packages/" --quiet
    log_info "Packages promoted to packages/v${VERSION}/"
fi

# Promote desktop artifacts (versioned path)
if $S3 ls "s3://${BUCKET}/${STAGING_PREFIX}/desktop/" >/dev/null 2>&1; then
    log_step "Promoting Desktop artifacts..."
    $S3 sync "s3://${BUCKET}/${STAGING_PREFIX}/desktop/" "s3://${BUCKET}/desktop/" --quiet
    log_info "Desktop promoted to desktop/v${VERSION}/"
fi

# NOTE: repo metadata (apt/, rpm/, apk/, archlinux/) is NOT promoted from staging.
# Staging metadata contains staging-specific URLs (RPM baseurl, etc.).
# CD rebuilds metadata with production URLs and uploads directly to R2.

log_info "R2 promotion complete"

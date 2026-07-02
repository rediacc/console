#!/bin/bash
# Sync tutorial/solution video assets and the tutorial-narration audio cache
# to Cloudflare R2 (rediacc-www-media).
#
# Incremental by design: `aws s3 sync` only uploads files that are new or
# whose size/mtime differ from what's already in the bucket, so re-running
# this after re-recording a handful of tutorials only pushes what changed,
# not the whole 5GB+ tree. Safe to run as often as needed.
#
# The audio prefix (tutorials/audio/) is a build-time TTS cache, not a
# CDN-served asset -- see .ci/docs/r2-media-setup.md #3. It's synced with
# the same primitive purely for convenience (same bucket, same script).
#
# Usage:
#   sync-media-to-r2.sh                  # sync tutorials/video, videos/, and tutorials/audio
#   sync-media-to-r2.sh --tutorials-only
#   sync-media-to-r2.sh --solutions-only
#   sync-media-to-r2.sh --audio-only
#   sync-media-to-r2.sh --dry-run        # show what would change, upload nothing
#   sync-media-to-r2.sh --delete         # also remove remote objects with no local match
#
# Environment:
#   R2_MEDIA_ACCESS_KEY_ID      S3-compatible access key (required)
#   R2_MEDIA_SECRET_ACCESS_KEY  S3-compatible secret key (required)
#   R2_MEDIA_ENDPOINT           R2 endpoint URL (required)
#
# See .ci/docs/r2-media-setup.md for how these credentials are provisioned.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUCKET="rediacc-www-media"
CACHE_CONTROL="public, max-age=31536000"

SYNC_TUTORIALS=true
SYNC_SOLUTIONS=true
SYNC_AUDIO=true
DRY_RUN=false
DELETE_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tutorials-only)
            SYNC_TUTORIALS=true
            SYNC_SOLUTIONS=false
            SYNC_AUDIO=false
            shift
            ;;
        --solutions-only)
            SYNC_TUTORIALS=false
            SYNC_SOLUTIONS=true
            SYNC_AUDIO=false
            shift
            ;;
        --audio-only)
            SYNC_TUTORIALS=false
            SYNC_SOLUTIONS=false
            SYNC_AUDIO=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --delete)
            DELETE_FLAG="--delete"
            shift
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

require_var R2_MEDIA_ACCESS_KEY_ID R2_MEDIA_SECRET_ACCESS_KEY R2_MEDIA_ENDPOINT
require_cmd aws

export AWS_ACCESS_KEY_ID="$R2_MEDIA_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_MEDIA_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

SYNC_ARGS=(--endpoint-url "$R2_MEDIA_ENDPOINT" --cache-control "$CACHE_CONTROL" --no-progress)
if [[ "$DRY_RUN" == true ]]; then
    SYNC_ARGS+=(--dryrun)
    log_info "Dry run: no objects will be uploaded or deleted."
fi
if [[ -n "$DELETE_FLAG" ]]; then
    SYNC_ARGS+=("$DELETE_FLAG")
    log_warn "Delete mode: remote objects with no local counterpart will be removed."
fi

sync_dir() {
    local local_dir="$1"
    local remote_prefix="$2"
    if [[ ! -d "$local_dir" ]]; then
        log_warn "Skipping $local_dir (not present locally)"
        return 0
    fi
    log_step "Syncing $local_dir -> s3://$BUCKET/$remote_prefix"
    aws s3 sync "$local_dir" "s3://$BUCKET/$remote_prefix" "${SYNC_ARGS[@]}"
}

if [[ "$SYNC_TUTORIALS" == true ]]; then
    sync_dir "$REPO_ROOT/packages/www/public/assets/tutorials/video/" "tutorials/video/"
fi

if [[ "$SYNC_SOLUTIONS" == true ]]; then
    sync_dir "$REPO_ROOT/packages/www/public/assets/videos/" "videos/"
fi

if [[ "$SYNC_AUDIO" == true ]]; then
    sync_dir "$REPO_ROOT/packages/www/public/assets/tutorials/audio/" "tutorials/audio/"
fi

if [[ "$DRY_RUN" == false ]]; then
    log_info "Sync complete. Verify with:"
    log_info "  aws s3 sync --dryrun <local-dir> s3://$BUCKET/<prefix>/ --endpoint-url \$R2_MEDIA_ENDPOINT"
    log_info "  curl -sI https://media.rediacc.com/<path>"
fi

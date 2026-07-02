#!/bin/bash
# Restore tutorial/solution video assets and the tutorial-narration audio
# cache from Cloudflare R2 (rediacc-www-media) into a local checkout.
# Counterpart to sync-media-to-r2.sh (upload direction).
#
# Useful after a fresh `git clone`: once the media files are no longer
# committed to git (see the video-migration plan in CLAUDE.md's "Media
# Assets" section), this is how to populate a local working copy for
# pipeline development, ffmpeg/local-preview work, or offline use. Most
# `npm run dev` browsing does NOT need this — once the URL builders read
# from the manifest and point at media.rediacc.com, the site fetches videos
# straight from the CDN over the network, same as production. The audio
# cache (tutorials/audio/) is different: it's a build-time TTS cache read
# directly off local disk by the tutorial-video pipeline, so restoring it
# IS required before re-running `./run.sh www tutorials generate|video` on a
# fresh checkout — see .ci/docs/r2-media-setup.md #3.
#
# Incremental by design: `aws s3 sync` only downloads objects that are new
# or whose size/etag differ from the local copy — safe to re-run any time
# to pick up newly-published videos without re-downloading everything.
#
# Usage:
#   sync-media-from-r2.sh                  # restore tutorials/video, videos/, and tutorials/audio
#   sync-media-from-r2.sh --tutorials-only
#   sync-media-from-r2.sh --solutions-only
#   sync-media-from-r2.sh --audio-only
#   sync-media-from-r2.sh --dry-run        # show what would download, download nothing
#
# Environment:
#   R2_MEDIA_ACCESS_KEY_ID      S3-compatible access key (required)
#   R2_MEDIA_SECRET_ACCESS_KEY  S3-compatible secret key (required)
#   R2_MEDIA_ENDPOINT           R2 endpoint URL (required)
#
# See .ci/docs/r2-media-setup.md for how these credentials are provisioned.
# Note: media.rediacc.com is a public CDN domain — anyone can `curl`/browse
# individual files with no credentials at all. Credentials are only needed
# here because this script uses the S3 API to *list* and diff the whole
# bucket, which the public HTTPS domain doesn't expose. (The audio cache is
# not exposed on the public CDN at all -- it's only reachable via this S3
# API path.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUCKET="rediacc-www-media"

RESTORE_TUTORIALS=true
RESTORE_SOLUTIONS=true
RESTORE_AUDIO=true
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tutorials-only)
            RESTORE_TUTORIALS=true
            RESTORE_SOLUTIONS=false
            RESTORE_AUDIO=false
            shift
            ;;
        --solutions-only)
            RESTORE_TUTORIALS=false
            RESTORE_SOLUTIONS=true
            RESTORE_AUDIO=false
            shift
            ;;
        --audio-only)
            RESTORE_TUTORIALS=false
            RESTORE_SOLUTIONS=false
            RESTORE_AUDIO=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
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

SYNC_ARGS=(--endpoint-url "$R2_MEDIA_ENDPOINT" --no-progress)
if [[ "$DRY_RUN" == true ]]; then
    SYNC_ARGS+=(--dryrun)
    log_info "Dry run: nothing will be downloaded."
fi

restore_dir() {
    local remote_prefix="$1"
    local local_dir="$2"
    mkdir -p "$local_dir"
    log_step "Restoring s3://$BUCKET/$remote_prefix -> $local_dir"
    aws s3 sync "s3://$BUCKET/$remote_prefix" "$local_dir" "${SYNC_ARGS[@]}"
}

if [[ "$RESTORE_TUTORIALS" == true ]]; then
    restore_dir "tutorials/video/" "$REPO_ROOT/packages/www/public/assets/tutorials/video/"
fi

if [[ "$RESTORE_SOLUTIONS" == true ]]; then
    restore_dir "videos/" "$REPO_ROOT/packages/www/public/assets/videos/"
fi

if [[ "$RESTORE_AUDIO" == true ]]; then
    restore_dir "tutorials/audio/" "$REPO_ROOT/packages/www/public/assets/tutorials/audio/"
fi

if [[ "$DRY_RUN" == false ]]; then
    log_info "Restore complete."
fi

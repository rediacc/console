#!/bin/bash
# Upload a single tutorial/solution video asset to R2 and update the
# committed manifest (packages/www/src/data/video-manifest.json).
#
# This is the per-file publish primitive used by:
#   - packages/www/scripts/publish-tutorial-video-to-r2.ts (tutorial videos)
#   - private/growth/video_pipeline/publish.py (solution videos, cross-repo —
#     shells out to this script since it can't import a TS module directly)
#
# Not a generalization of upload-to-r2.sh: that script is coupled to the
# release-sentinel/write-once model (immutable versioned artifacts). Media
# assets are mutable-in-place (a re-record overwrites the same path), so
# this is a separate, much smaller script.
#
# Usage:
#   upload-media-to-r2.sh --kind tutorials --key <castKey> --lang <lang> \
#     --field mp4 --file <local-path>
#   upload-media-to-r2.sh --kind solutions --key <slug> --lang <lang> \
#     --field vertical --file <local-path>
#
# --field is one of: mp4, poster, vtt, chaptersVtt, wordsJson (tutorials) or
# mp4, vertical, poster (solutions) — must match a field name the manifest
# schema / URL builders expect (see update-video-manifest.ts's header comment).
#
# Environment:
#   R2_MEDIA_ACCESS_KEY_ID      S3-compatible access key (required)
#   R2_MEDIA_SECRET_ACCESS_KEY  S3-compatible secret key (required)
#   R2_MEDIA_ENDPOINT           R2 endpoint URL (required)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BUCKET="rediacc-www-media"
CACHE_CONTROL="public, max-age=31536000"
MANIFEST_HELPER="$REPO_ROOT/packages/www/scripts/lib/update-video-manifest.ts"

KIND=""
KEY=""
LANG=""
FIELD=""
FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --kind)
            KIND="$2"
            shift 2
            ;;
        --key)
            KEY="$2"
            shift 2
            ;;
        --lang)
            LANG="$2"
            shift 2
            ;;
        --field)
            FIELD="$2"
            shift 2
            ;;
        --file)
            FILE="$2"
            shift 2
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

if [[ "$KIND" != "tutorials" && "$KIND" != "solutions" ]]; then
    log_error "--kind must be 'tutorials' or 'solutions', got '$KIND'"
    exit 1
fi
require_var KEY LANG FIELD FILE
require_file "$FILE"
require_var R2_MEDIA_ACCESS_KEY_ID R2_MEDIA_SECRET_ACCESS_KEY R2_MEDIA_ENDPOINT
require_cmd aws
require_cmd npx
require_cmd sha256sum
require_cmd stat

export AWS_ACCESS_KEY_ID="$R2_MEDIA_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_MEDIA_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

# Bucket key layout mirrors the local public/assets/{tutorials/video,videos}
# tree minus BOTH the "public/" and "assets/" prefixes (see
# .ci/docs/r2-media-setup.md #1). tutorials -> tutorials/video/<lang>/<file>,
# solutions -> videos/solutions/<lang>/<file>.
FILENAME="$(basename "$FILE")"
if [[ "$KIND" == "tutorials" ]]; then
    REMOTE_KEY="tutorials/video/${LANG}/${FILENAME}"
else
    REMOTE_KEY="videos/solutions/${LANG}/${FILENAME}"
fi

log_step "Uploading $FILE -> s3://$BUCKET/$REMOTE_KEY"
aws s3 cp "$FILE" "s3://${BUCKET}/${REMOTE_KEY}" \
    --endpoint-url "$R2_MEDIA_ENDPOINT" \
    --cache-control "$CACHE_CONTROL" \
    --no-progress

log_step "Verifying upload (HEAD readback)"
aws s3api head-object --bucket "$BUCKET" --key "$REMOTE_KEY" --endpoint-url "$R2_MEDIA_ENDPOINT" >/dev/null

SIZE="$(stat -c%s "$FILE")"
SHA256="$(sha256sum "$FILE" | cut -d' ' -f1)"

log_step "Updating manifest: ${KIND}.${KEY}.${LANG}.${FIELD}"
npx tsx "$MANIFEST_HELPER" \
    --kind "$KIND" --key "$KEY" --lang "$LANG" --field "$FIELD" \
    --path "$REMOTE_KEY" --size "$SIZE" --sha256 "$SHA256"

log_info "Done: https://media.rediacc.com/${REMOTE_KEY}"

#!/bin/bash
# Upload a single tutorial/solution video asset to R2 and update the
# committed manifest (packages/www/src/data/video-manifest.json).
#
# This is the per-file publish primitive used by:
#   - packages/www/scripts/publish-tutorial-video-to-r2.ts (tutorial videos)
#   - private/growth/video_pipeline/publish.py (solution videos, cross-repo --
#     shells out to this script since it can't import a TS module directly)
#
# THIS FILE MOVED FROM .ci/scripts/deploy/upload-media-to-r2.sh (W10 phase 3). It is the
# only thing under .ci/scripts/deploy that belonged to the media pipeline: everything
# else there deploys the product, this uploads a rendered video. Its three siblings
# (sync-media-to-r2.sh, sync-media-from-r2.sh, purge-media-cache.sh) are bulk cache
# operations driven by .ci/media/r2.sh and by CI, and they stayed, because moving them
# would drag the deploy lane's shared helpers along with them.
#
# THE OLD PATH IS STILL A LIVE ENTRY POINT, and both remaining callers still spell it.
# The in-repo one could have been updated in this change; the cross-repo one could not,
# because private/growth is a gitignored repository this checkout cannot open. Updating
# only the one it can see would leave the two callers disagreeing about where the
# primitive lives, which is worse than either answer, so BOTH keep the old spelling and
# .ci/scripts/deploy/upload-media-to-r2.sh forwards here with exec.
#
# HOW THE CONTRACT IS CHECKED FROM THIS SIDE, since private/growth cannot be:
# .ci/rediacc_ci/tests/gates/test_gate_media_shims.py drives the OLD path with aws, npx and the
# network absent, and requires argv to arrive here byte-identical from an arbitrary cwd
# with the exit status forwarded. It also FREEZES the accepted flag set below against a
# recorded list, so dropping or renaming a flag a caller passes is red here rather than
# at the next publish. That frozen set is the actual cross-repo contract; the path is
# only how it is reached.
#
# Not a generalization of upload-to-r2.sh: that script is coupled to the
# release-sentinel/write-once model (immutable versioned artifacts). Media
# assets are mutable-in-place (a re-record overwrites the same path), so
# this is a separate, much smaller script.
#
# Usage:
#   upload-r2.sh --kind tutorials --key <castKey> --lang <lang> \
#     --field mp4 --file <local-path>
#   upload-r2.sh --kind solutions --key <slug> --lang <lang> \
#     --field vertical --file <local-path>
#
# --field is one of: mp4, poster, vtt, chaptersVtt, wordsJson (tutorials) or
# mp4, vertical, poster (solutions) -- must match a field name the manifest
# schema / URL builders expect (see update-video-manifest.ts's header comment).
#
# Environment:
#   CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID      S3-compatible access key (required)
#   CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY  S3-compatible secret key (required)
#   CLOUDFLARE_R2_MEDIA_ENDPOINT           R2 endpoint URL (required)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# .ci/media/tools -> .ci/media -> .ci -> repo root. The same three hops the old location
# needed (.ci/scripts/deploy -> .ci/scripts -> .ci -> root), which is why nothing about
# REPO_ROOT changed in the move.
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# The well-known WK_* facts (WK_MEDIA_ORIGIN below), spelled from the repo root rather than from here
# so a future relocation of this file is one line rather than a hunt for a `../..` that silently
# resolves to the wrong depth.
# shellcheck source=../../config/well-known.generated.sh
source "$REPO_ROOT/.ci/config/well-known.generated.sh"
# The log and require helpers this program uses, with the glyphs, the stderr-only rule and the
# colour rule (a terminal on fd 2 and no NO_COLOR) of the helper library it used to source.
if [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    _red='\033[0;31m' _green='\033[0;32m' _blue='\033[0;34m' _nc='\033[0m'
else
    _red='' _green='' _blue='' _nc=''
fi
log_info() { echo -e "${_green}✓${_nc} $*" >&2; }
log_error() { echo -e "${_red}✗${_nc} $*" >&2; }
log_step() { echo -e "${_blue}→${_nc} $*" >&2; }
require_var() {
    local var_name
    for var_name in "$@"; do
        if [[ -z "${!var_name:-}" ]]; then
            log_error "Required environment variable '$var_name' is not set"
            exit 1
        fi
    done
}
require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        log_error "Required command '$1' is not available"
        exit 1
    fi
}
require_file() {
    if [[ ! -f "$1" ]]; then
        log_error "Required file '$1' does not exist"
        exit 1
    fi
}
# The platform seams. This script is the one .ci/media program that runs standalone rather
# than through media-entry.sh, so it sources them itself: `sha256sum` and `stat -c%s` are
# both GNU spellings, and this is the file that publishes to a bucket, where a wrong hash
# or a wrong size is recorded in a committed manifest and read back as truth later.
# shellcheck source=../portable.sh
source "$REPO_ROOT/.ci/media/portable.sh"
BUCKET="rediacc-www-media"
CACHE_CONTROL="public, max-age=31536000"
MANIFEST_HELPER="$REPO_ROOT/packages/www/scripts/lib/update-video-manifest.ts"

KIND=""
KEY=""
LANG=""
FIELD=""
FILE=""
ENGINE=""
DEFER_MANIFEST=""

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
        # OPTIONAL. The TTS engine that narrated this asset, recorded into the
        # manifest so CI can tell a current narration from a stale one. Callers
        # that do not know it simply omit the flag.
        --engine)
            ENGINE="$2"
            shift 2
            ;;
        # Append the manifest tuple to this file instead of updating the manifest
        # now. A full tutorial sweep is 1170 files, and updating per file means
        # 1170 cold `npx tsx` starts each rewriting a 440 KB JSON -- hours of pure
        # overhead. The caller applies the whole file in one process afterwards.
        # Omitted by every other caller, which keeps the original behaviour.
        --defer-manifest)
            DEFER_MANIFEST="$2"
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
require_var CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY CLOUDFLARE_R2_MEDIA_ENDPOINT
# The aws CLI: AWS_BIN when set (CI exports the pinned install, .ci/bootstrap.sh
# which aws --pin), else the one on PATH -- the first two rungs of
# .ci/rediacc_ci/core/awscli.py.
AWS="${AWS_BIN:-aws}"
require_cmd "$AWS"
require_cmd npx
# sha256sum and stat are NOT required by name any more: media_file_size and
# "${MEDIA_SHA256[@]}" pick whichever spelling this host has and refuse, loudly and by
# name, when it has none. Requiring the GNU spelling here would have refused a host the
# seams can serve.

export AWS_ACCESS_KEY_ID="$CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"
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
"$AWS" s3 cp "$FILE" "s3://${BUCKET}/${REMOTE_KEY}" \
    --endpoint-url "$CLOUDFLARE_R2_MEDIA_ENDPOINT" \
    --cache-control "$CACHE_CONTROL" \
    --no-progress

log_step "Verifying upload (HEAD readback)"
"$AWS" s3api head-object --bucket "$BUCKET" --key "$REMOTE_KEY" --endpoint-url "$CLOUDFLARE_R2_MEDIA_ENDPOINT" >/dev/null

SIZE="$(media_file_size "$FILE")"
SHA256="$("${MEDIA_SHA256[@]}" "$FILE" | cut -d' ' -f1)"

log_step "Updating manifest: ${KIND}.${KEY}.${LANG}.${FIELD}"
# The helper parses argv strictly in flag/value pairs, so an empty --engine would
# shift everything and corrupt the call. Pass the flag only when we have a value.
ENGINE_ARGS=()
if [[ -n "$ENGINE" ]]; then
    ENGINE_ARGS=(--engine "$ENGINE")
fi

if [[ -n "$DEFER_MANIFEST" ]]; then
    # Tab-separated so the reader never has to guess at quoting. The upload and
    # its HEAD readback have already happened; only the bookkeeping is deferred.
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$KIND" "$KEY" "$LANG" "$FIELD" "$REMOTE_KEY" "$SIZE" "$SHA256" "$ENGINE" \
        >>"$DEFER_MANIFEST"
else
    npx tsx "$MANIFEST_HELPER" \
        --kind "$KIND" --key "$KEY" --lang "$LANG" --field "$FIELD" \
        --path "$REMOTE_KEY" --size "$SIZE" --sha256 "$SHA256" "${ENGINE_ARGS[@]}"
fi

log_info "Done: $WK_MEDIA_ORIGIN/${REMOTE_KEY}"

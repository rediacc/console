#!/bin/bash
# Soak-gated promotion: copy every R2 release channel from edge/ to stable/
# with a two-phase, metadata-last upload.
#
# WHY two phases: a package manager decides "there is a new version" from
# metadata (Packages.gz, APKINDEX, manifest.json, ...) and then fetches the
# bytes that metadata names. Uploading everything at once means a client can see
# the new-version signal minutes before the binaries it points at finish
# landing, which surfaces as 404s and "Mirror sync in progress?" errors.
#   Phase 1 uploads bytes (binaries, packages) -- slow, minutes. Client-visible
#     metadata at stable/ still points at the OLD version throughout.
#   Phase 2 uploads metadata -- seconds. Advancement becomes visible at this
#     boundary, not before.
# Within phase 2 the signed/hashing metadata is split from the metadata it
# hashes (Release after Packages, repomd.xml after primary/filelists) so a
# Release/InRelease hash can never disagree with the bytes on R2.
#
# Channel-specific rewrites (install.sh / .repo / .conf) happen on the local tmp
# copy BEFORE the phase 2 upload, which removes the second re-upload race the
# old sequential version had.
#
# Cache-Control policy: channel paths reuse filenames across releases, so
# nothing under <fmt>/<channel>/ is safe to cache. All channel uploads go
# no-cache; CF never caches, so no stale body is possible. Versioned paths
# (cli/v<semver>/) keep their immutable cache via upload-to-r2.sh.
#
# The hotfix lane that skips the soak is a different, single-phase script:
# .ci/scripts/deploy/promote-r2-to-stable-hotfix.sh (driven by cd-v2.yml).
#
# Usage:
#   .ci/scripts/deploy/promote-r2-to-stable.sh
#
# Required env:
#   AWS_ACCESS_KEY_ID      R2 credentials (the workflow maps R2_* onto these)
#   AWS_SECRET_ACCESS_KEY
#   AWS_DEFAULT_REGION     "auto" for R2
#   CLOUDFLARE_R2_ENDPOINT            R2 S3 endpoint
#   EDGE_VERSION           version being promoted; log line only
#
# Optional env:
#   CLOUDFLARE_ZONE_ID     zone to purge; the purge is best-effort and is the
#   CLOUDFLARE_API_TOKEN   last thing this script does, so a missing/void
#                          credential cannot leave the promotion half-done
#
# NOTE: this MUTATES the production stable channel. Do not run it locally
# against real credentials.
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here. Every variable is env-wired or locally assigned, and the only
# pipeline is the final purge (already the last command of an && chain, so its
# status reached the shell either way).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd aws
: "${AWS_ACCESS_KEY_ID:?promote-r2-to-stable.sh: AWS_ACCESS_KEY_ID must be set}"
: "${AWS_SECRET_ACCESS_KEY:?promote-r2-to-stable.sh: AWS_SECRET_ACCESS_KEY must be set}"
: "${CLOUDFLARE_R2_ENDPOINT:?promote-r2-to-stable.sh: CLOUDFLARE_R2_ENDPOINT must be set}"
EDGE_VERSION="${EDGE_VERSION:?promote-r2-to-stable.sh: EDGE_VERSION must be set}"

BUCKET="rediacc-releases"
EP="--endpoint-url $CLOUDFLARE_R2_ENDPOINT"

CC_MUTABLE="no-cache"

PURGE_URLS=()
for dir in cli apt rpm apk archlinux; do
    echo "Promoting ${dir}/edge/ -> ${dir}/stable/ (2-phase)"
    TMP="/tmp/promote-${dir}"
    aws s3 cp "s3://${BUCKET}/${dir}/edge/" "$TMP/" $EP --recursive --quiet

    # Per-dir channel rewrites -- apply to local copy, uploaded in phase 2.
    case "$dir" in
        cli)
            for f in "$TMP/install.sh" "$TMP/install.ps1"; do
                [[ -f "$f" ]] || continue
                sed_in_place \
                    -e 's|REDIACC_CHANNEL:-edge|REDIACC_CHANNEL:-stable|g' \
                    -e 's|} else { "edge" }|} else { "stable" }|g' \
                    "$f"
            done
            ;;
        rpm)
            [[ -f "$TMP/rediacc.repo" ]] && sed_in_place 's|/edge/|/stable/|g' "$TMP/rediacc.repo"
            ;;
        archlinux)
            [[ -f "$TMP/rediacc.conf" ]] && sed_in_place 's|/edge/|/stable/|g' "$TMP/rediacc.conf"
            ;;
    esac

    META_EXCLUDES=(
        --exclude 'Packages*' --exclude 'Release*' --exclude 'InRelease'
        --exclude 'repodata/*'
        --exclude 'APKINDEX.tar.gz'
        --exclude '*.db.tar.gz' --exclude '*.files.tar.gz'
        --exclude 'rediacc.db' --exclude 'rediacc.files'
        --exclude 'latest*.yml' --exclude 'latest.json' --exclude 'manifest.json'
        --exclude 'install.sh' --exclude 'install.ps1'
        --exclude '*.repo' --exclude '*.conf'
        --exclude 'rediacc-cli-latest.tgz'
        --exclude 'versions.json'
    )

    # ----- Phase 1: binaries / packages (slow, no metadata) -----
    aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
        --cache-control "$CC_MUTABLE" "${META_EXCLUDES[@]}"

    # ----- Phase 2: metadata (fast, flips client view to new version) -----
    case "$dir" in
        apt)
            # 2a: Packages / Packages.gz (hashes of .deb files in phase 1).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'Packages*'
            # 2b: Release / InRelease / Release.gpg (hash of phase 2a).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'Release*' --include 'InRelease'
            ;;
        rpm)
            # 2a: primary / filelists / other (hashed in 2b repomd).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'repodata/primary*' \
                --include 'repodata/filelists*' --include 'repodata/other*'
            # 2b: repomd.xml + signatures + rediacc.repo (config).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'repodata/repomd.xml*' \
                --include '*.repo'
            ;;
        apk)
            # APKINDEX references .apk files in same dir (phase 1).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'APKINDEX.tar.gz'
            ;;
        archlinux)
            # .db/.files reference .pkg.tar.zst in same dir (phase 1).
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include '*.db.tar.gz' --include '*.files.tar.gz' \
                --include 'rediacc.db' --include 'rediacc.files' \
                --include '*.conf'
            ;;
        cli)
            # manifest + latest.json + rebaked install scripts.
            aws s3 sync "$TMP/" "s3://${BUCKET}/${dir}/stable/" $EP --quiet \
                --cache-control "$CC_MUTABLE" \
                --exclude '*' --include 'manifest.json' --include 'latest.json' \
                --include 'install.sh' --include 'install.ps1' \
                --include 'versions.json'
            ;;
    esac

    # VACUITY FLOOR. `find "$TMP" -type f` after the sync above is how the purge list
    # is built, and an EMPTY $TMP means this dir promoted nothing -- the sync had no
    # source. That is indistinguishable from "promoted fine, nothing mutable to purge"
    # unless it is said out loud: the loop adds no URLs, the purge below is skipped
    # because the array is empty, and the run prints "R2 promotion complete".
    tmp_files=$(find "$TMP" -type f | wc -l || true)
    if [[ "$tmp_files" -eq 0 ]]; then
        echo "VACUOUS: ${dir} staged 0 file(s) for promotion; refusing to report a promotion that moved nothing" >&2
        exit 1
    fi

    while IFS= read -r f; do
        PURGE_URLS+=("https://releases.rediacc.com/${dir}/stable/${f#"$TMP"/}")
    done < <(find "$TMP" -type f)
    rm -rf "$TMP"
done

echo "R2 promotion complete: edge v${EDGE_VERSION} -> stable"

# Purge CF cache for the mutable URLs we just (re)uploaded.
if [[ ${#PURGE_URLS[@]} -gt 0 ]]; then
    printf '%s\n' "${PURGE_URLS[@]}" |
        "$SCRIPT_DIR/cf-purge-urls.sh" --zone "${CLOUDFLARE_ZONE_ID:-}"
fi

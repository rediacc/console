#!/bin/bash
# Upload release artifacts to Cloudflare R2
#
# Usage:
#   upload-to-r2.sh --version 0.5.0 --channel pr-123
#
# Options:
#   --version VERSION    Release version (required)
#   --channel CHANNEL    Release channel (e.g., "pr-123", "edge", "stable")
#   --cli-dir DIR        CLI binaries directory (default: dist/cli/)
#   --desktop-dir DIR    Desktop artifacts directory (default: dist/desktop/)
#   --packages-dir DIR   DEPRECATED (packages now in self-contained repos)
#   --dry-run            Print commands without executing
#
# Environment:
#   R2_ACCESS_KEY_ID      S3-compatible access key (required)
#   R2_SECRET_ACCESS_KEY  S3-compatible secret key (required)
#   R2_ENDPOINT           R2 endpoint URL (required)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

VERSION=""
CHANNEL=""
CLI_DIR=""
DESKTOP_DIR=""
PACKAGES_DIR=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --channel)
            CHANNEL="$2"
            shift 2
            ;;
        --cli-dir)
            CLI_DIR="$2"
            shift 2
            ;;
        --desktop-dir)
            DESKTOP_DIR="$2"
            shift 2
            ;;
        --packages-dir)
            PACKAGES_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --version VERSION --channel CHANNEL [--cli-dir DIR] [--desktop-dir DIR] [--packages-dir DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    log_error "--version is required"
    exit 1
fi

REPO_ROOT="$(get_repo_root)"
[[ -z "$CLI_DIR" ]] && CLI_DIR="$REPO_ROOT/dist/cli"
[[ -z "$DESKTOP_DIR" ]] && DESKTOP_DIR="$REPO_ROOT/dist/desktop"
[[ -z "$PACKAGES_DIR" ]] && PACKAGES_DIR="$REPO_ROOT/dist/packages"

if [[ -z "$CHANNEL" ]]; then
    log_error "--channel is required"
    exit 1
fi

log_step "Uploading v$VERSION to R2 channel: $CHANNEL"

# Validate R2 credentials
if [[ "$DRY_RUN" == "false" ]]; then
    for var in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Missing required environment variable: $var"
            exit 1
        fi
    done

    # Configure AWS CLI for R2
    export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
    export AWS_DEFAULT_REGION="auto"
fi

# Cache-Control policies for R2 objects served via the releases.rediacc.com
# Cloudflare custom domain. CF zone settings (aggressive cache + browser
# TTL 14400) used to override these origin headers on GET responses; a
# zone-level Cache Rule at `(http.host eq "releases.rediacc.com")` now
# bypasses cache entirely so origin headers pass through unmodified. See
# .ci/docs/r2-setup.md for how that rule is maintained.
#
# Even with CF bypassing cache, these headers are still correct to send:
# browsers + other intermediaries honor Cache-Control even when CF doesn't.
#
# - Mutable channel pointers (Packages.gz, install.sh, latest.json, etc.)
#   and any file under a package-manager channel path (apt/<channel>/,
#   apk/<channel>/, etc.) get "no-cache" because channel paths reuse
#   filenames across releases -- content at the same URL changes.
# - Truly immutable URL-versioned binaries (cli/v1.2.3/*, desktop/v1.2.3/*,
#   npm/<channel>/rediacc-cli-<semver>.tgz) get a 1-year cache because the
#   URL itself encodes the version and content never changes at that URL.
readonly CACHE_CONTROL_MUTABLE="no-cache"
readonly CACHE_CONTROL_IMMUTABLE="public, max-age=31536000, immutable"

# Helper: upload file to R2. Third arg is the Cache-Control value (defaults to
# the mutable policy because most callers upload channel-pointer files; binary
# uploads must pass $CACHE_CONTROL_IMMUTABLE explicitly).
r2_cp() {
    local src="$1"
    local dest="$2"
    local cache_control="${3:-$CACHE_CONTROL_MUTABLE}"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would upload: $src → $full_dest (Cache-Control: $cache_control)"
        return 0
    fi

    aws s3 cp "$src" "$full_dest" \
        --endpoint-url "$R2_ENDPOINT" \
        --cache-control "$cache_control" \
        --no-progress
}

# Helper: upload directory to R2. Third arg is the Cache-Control value applied
# to every object in the sync; defaults to the mutable policy. For mixed
# directories (binaries + metadata) call this twice with --include filters and
# different cache_control values, or use two separate r2_cp calls.
r2_sync() {
    local src="$1"
    local dest="$2"
    local cache_control="${3:-$CACHE_CONTROL_MUTABLE}"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would sync: $src → $full_dest (Cache-Control: $cache_control)"
        return 0
    fi

    aws s3 sync "$src" "$full_dest" \
        --endpoint-url "$R2_ENDPOINT" \
        --cache-control "$cache_control" \
        --no-progress
}

# Helper: write string to R2. Always uses the mutable Cache-Control policy
# because the only callers (latest.json, manifest.json, versions.json) are by
# nature mutable channel pointers.
r2_put() {
    local content="$1"
    local dest="$2"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"
    local content_type="${3:-application/json}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would write: $full_dest (Cache-Control: $CACHE_CONTROL_MUTABLE)"
        return 0
    fi

    echo "$content" | aws s3 cp - "$full_dest" \
        --endpoint-url "$R2_ENDPOINT" \
        --content-type "$content_type" \
        --cache-control "$CACHE_CONTROL_MUTABLE" \
        --no-progress
}

# Helper: delete R2 path recursively
r2_rm() {
    local path="$1"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would delete: s3://${RELEASES_BUCKET}/${path}"
        return 0
    fi
    aws s3 rm "s3://${RELEASES_BUCKET}/${path}" --recursive \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null || true
}

# Helper: read content from R2
r2_get() {
    local path="$1"
    aws s3 cp "s3://${RELEASES_BUCKET}/${path}" - \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null || echo ""
}

# Build R2 path: {type}/{channel}/{rest}
r2_path() {
    local type="$1"
    local rest="$2"
    echo "${type}/${CHANNEL}/${rest}"
}

# Build R2 versioned path (no channel): {path}
r2_versioned_path() {
    echo "$1"
}

# Update a versions.json tracker and output versions to prune
# Usage: update_versions_tracker <prefix> <version> <max_versions>
# Outputs pruned version strings (one per line) on stdout
update_versions_tracker() {
    local prefix="$1"
    local new_version="$2"
    local max_versions="$3"
    local tracker_path="${prefix}/versions.json"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update ${tracker_path}" >&2
        return 0
    fi

    local existing
    existing=$(r2_get "$tracker_path")
    [[ -z "$existing" ]] && existing="[]"

    if ! command -v jq &>/dev/null; then
        log_warn "jq not available, skipping version tracking for $prefix" >&2
        return 0
    fi

    local updated
    updated=$(echo "$existing" | jq --arg v "$new_version" \
        'if index($v) then . else [$v] + . end')

    # Output versions beyond retention window (to be pruned)
    echo "$updated" | jq -r ".[$max_versions:][]"

    # Write truncated tracker back (suppress r2_put stdout)
    local kept
    kept=$(echo "$updated" | jq ".[:$max_versions]")
    r2_put "$kept" "$tracker_path" >/dev/null
}

# Delete old versioned directories from R2
cleanup_old_versions() {
    local prefix="$1"
    local pruned_versions="$2"

    [[ -z "$pruned_versions" ]] && return 0

    log_step "Cleaning up old ${prefix} versions"
    while IFS= read -r ver; do
        [[ -z "$ver" ]] && continue
        log_info "  Deleting ${prefix}/v${ver}/"
        r2_rm "${prefix}/v${ver}/"
    done <<<"$pruned_versions"
}

UPLOADED=0

# =============================================================================
# CLI Binaries
# =============================================================================
if [[ -d "$CLI_DIR" ]]; then
    log_step "Uploading CLI binaries"

    # Upload to versioned path (permanent link). Versioned URLs are
    # immutable -- the same URL never serves different content -- so
    # CF can cache aggressively for end-user install perf. Only release
    # channels (stable/edge) may write here; PR/dryrun writes would
    # clobber cli/v${VERSION}/manifest.json with dev-named artifacts that
    # install.sh and Homebrew would fetch as "v${VERSION}".
    # Allowed channels are set in .github/workflows/ci.yml:115-122.
    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        for binary in "$CLI_DIR"/rdc-*; do
            [[ -f "$binary" ]] || continue
            local_name="$(basename "$binary")"
            r2_cp "$binary" "$(r2_versioned_path "cli/v${VERSION}/${local_name}")" "$CACHE_CONTROL_IMMUTABLE"
            ((UPLOADED++)) || true
        done
    fi

    # Upload to channel path
    for binary in "$CLI_DIR"/rdc-*; do
        [[ -f "$binary" ]] || continue
        local_name="$(basename "$binary")"
        r2_cp "$binary" "$(r2_path "cli" "${local_name}")"
    done
    if [[ -f "$CLI_DIR/manifest.json" ]]; then
        r2_cp "$CLI_DIR/manifest.json" "$(r2_path "cli" "manifest.json")"
    fi
    # Write latest.json LAST to avoid race conditions
    r2_put "{\"version\":\"${VERSION}\"}" "$(r2_path "cli" "latest.json")"

    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        log_info "CLI: uploaded to cli/v${VERSION}/ + cli/${CHANNEL}/"
    else
        log_info "CLI: uploaded to cli/${CHANNEL}/ (versioned path skipped; not a release channel)"
    fi

    # Track CLI versions for retention cleanup (production channels only)
    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        CLI_PRUNED=$(update_versions_tracker "cli" "$VERSION" "$R2_MAX_RELEASE_VERSIONS")
    fi
else
    log_warn "CLI directory not found: $CLI_DIR"
fi

# =============================================================================
# CLI npm Tarball
# =============================================================================
NPM_DIR="${NPM_DIR:-$REPO_ROOT/dist/npm}"
if [[ -d "$NPM_DIR" ]]; then
    log_step "Uploading CLI npm tarball"

    for tgz in "$NPM_DIR"/rediacc-cli-*.tgz; do
        [[ -f "$tgz" ]] || continue
        local_name="$(basename "$tgz")"
        [[ "$local_name" == "rediacc-cli-latest.tgz" ]] && continue
        # Versioned tarball filename (rediacc-cli-1.2.3.tgz) is immutable.
        r2_cp "$tgz" "$(r2_path "npm" "${local_name}")" "$CACHE_CONTROL_IMMUTABLE"
        ((UPLOADED++)) || true
    done

    if [[ -f "$NPM_DIR/rediacc-cli-latest.tgz" ]]; then
        r2_cp "$NPM_DIR/rediacc-cli-latest.tgz" "$(r2_path "npm" "rediacc-cli-latest.tgz")"
    fi

    log_info "npm: uploaded to npm/${CHANNEL}/"
else
    log_info "npm directory not found: $NPM_DIR (skipping)"
fi

# =============================================================================
# Desktop Artifacts
# =============================================================================
if [[ -d "$DESKTOP_DIR" ]]; then
    log_step "Uploading Desktop artifacts"

    for artifact in "$DESKTOP_DIR"/*; do
        [[ -f "$artifact" ]] || continue
        local_name="$(basename "$artifact")"
        [[ "$local_name" == "builder-debug.yml" ]] && continue

        # Versioned path is immutable; only release channels may write here.
        # Channel path is overwritten per release and must revalidate against
        # R2 every time. See CLI section above for the gating rationale.
        if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
            r2_cp "$artifact" "$(r2_versioned_path "desktop/v${VERSION}/${local_name}")" "$CACHE_CONTROL_IMMUTABLE"
            ((UPLOADED++)) || true
        fi
        r2_cp "$artifact" "$(r2_path "desktop" "${local_name}")"
    done

    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        log_info "Desktop: uploaded to desktop/v${VERSION}/ + desktop/${CHANNEL}/"
    else
        log_info "Desktop: uploaded to desktop/${CHANNEL}/ (versioned path skipped; not a release channel)"
    fi

    # Track Desktop versions for retention cleanup (production channels only)
    if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
        DESKTOP_PRUNED=$(update_versions_tracker "desktop" "$VERSION" "$R2_MAX_RELEASE_VERSIONS")
    fi
else
    log_info "Desktop directory not found: $DESKTOP_DIR (skipping)"
fi

# =============================================================================
# Cleanup Old Versions (production channels only)
# =============================================================================
if [[ "$CHANNEL" == "stable" || "$CHANNEL" == "edge" ]]; then
    cleanup_old_versions "cli" "${CLI_PRUNED:-}"
    cleanup_old_versions "desktop" "${DESKTOP_PRUNED:-}"
fi

# =============================================================================
# Summary
# =============================================================================
log_step "R2 upload complete"
log_info "  Artifacts uploaded: $UPLOADED"
log_info "  Version: v$VERSION"
log_info "  Channel: $CHANNEL"
log_info "  Bucket: $RELEASES_BUCKET"

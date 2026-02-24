#!/bin/bash
# Upload release artifacts to Cloudflare R2
#
# Usage:
#   upload-to-r2.sh --version 0.5.0 [--staging pr-123]
#
# Options:
#   --version VERSION    Release version (required)
#   --staging PREFIX     Upload to staging path (e.g., "pr-123" → staging/pr-123/)
#   --cli-dir DIR        CLI binaries directory (default: dist/cli/)
#   --desktop-dir DIR    Desktop artifacts directory (default: dist/desktop/)
#   --packages-dir DIR   Linux packages directory (default: dist/packages/)
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
STAGING=""
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
        --staging)
            STAGING="$2"
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
            echo "Usage: $0 --version VERSION [--staging PREFIX] [--cli-dir DIR] [--desktop-dir DIR] [--packages-dir DIR] [--dry-run]"
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

# Determine R2 path prefix
if [[ -n "$STAGING" ]]; then
    PREFIX="staging/${STAGING}"
    log_step "Uploading to R2 staging: $PREFIX"
else
    PREFIX=""
    log_step "Uploading release v$VERSION to R2"
fi

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

# Helper: upload file to R2
r2_cp() {
    local src="$1"
    local dest="$2"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would upload: $src → $full_dest"
        return 0
    fi

    aws s3 cp "$src" "$full_dest" --endpoint-url "$R2_ENDPOINT" --no-progress
}

# Helper: upload directory to R2
r2_sync() {
    local src="$1"
    local dest="$2"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would sync: $src → $full_dest"
        return 0
    fi

    aws s3 sync "$src" "$full_dest" --endpoint-url "$R2_ENDPOINT" --no-progress
}

# Helper: write string to R2
r2_put() {
    local content="$1"
    local dest="$2"
    local full_dest="s3://${RELEASES_BUCKET}/${dest}"
    local content_type="${3:-application/json}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would write: $full_dest"
        return 0
    fi

    echo "$content" | aws s3 cp - "$full_dest" \
        --endpoint-url "$R2_ENDPOINT" \
        --content-type "$content_type" \
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

# Build R2 path with optional staging prefix
r2_path() {
    local path="$1"
    if [[ -n "$PREFIX" ]]; then
        echo "${PREFIX}/${path}"
    else
        echo "$path"
    fi
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
    done <<< "$pruned_versions"
}

UPLOADED=0

# =============================================================================
# CLI Binaries
# =============================================================================
if [[ -d "$CLI_DIR" ]]; then
    log_step "Uploading CLI binaries"

    for binary in "$CLI_DIR"/rdc-*; do
        [[ -f "$binary" ]] || continue
        local_name="$(basename "$binary")"
        r2_cp "$binary" "$(r2_path "cli/v${VERSION}/${local_name}")"
        ((UPLOADED++)) || true
    done

    # Upload manifest.json if present
    if [[ -f "$CLI_DIR/manifest.json" ]]; then
        r2_cp "$CLI_DIR/manifest.json" "$(r2_path "cli/manifest.json")"
        ((UPLOADED++)) || true
    fi

    # Write latest.json for version discovery
    r2_put "{\"version\":\"${VERSION}\"}" "$(r2_path "cli/latest.json")"
    ((UPLOADED++)) || true

    # Copy binaries to cli/latest/ for stable download URLs
    for binary in "$CLI_DIR"/rdc-*; do
        [[ -f "$binary" ]] || continue
        local_name="$(basename "$binary")"
        r2_cp "$binary" "$(r2_path "cli/latest/${local_name}")"
    done

    log_info "CLI: uploaded to $(r2_path "cli/v${VERSION}/") + $(r2_path "cli/latest/")"

    # Track CLI versions for retention cleanup (production only)
    if [[ -z "$STAGING" ]]; then
        CLI_PRUNED=$(update_versions_tracker "cli" "$VERSION" "$R2_MAX_RELEASE_VERSIONS")
    fi
else
    log_warn "CLI directory not found: $CLI_DIR"
fi

# =============================================================================
# Desktop Artifacts
# =============================================================================
if [[ -d "$DESKTOP_DIR" ]] && [[ -z "$STAGING" ]]; then
    log_step "Uploading Desktop artifacts"

    # Upload all desktop files to versioned directory
    for artifact in "$DESKTOP_DIR"/*; do
        [[ -f "$artifact" ]] || continue
        local_name="$(basename "$artifact")"

        # Skip build debug files
        [[ "$local_name" == "builder-debug.yml" ]] && continue

        r2_cp "$artifact" "$(r2_path "desktop/v${VERSION}/${local_name}")"
        ((UPLOADED++)) || true

        # Copy electron-updater feed files to root
        case "$local_name" in
            latest*.yml | latest*.yaml)
                r2_cp "$artifact" "$(r2_path "desktop/${local_name}")"
                ;;
        esac
    done

    log_info "Desktop: uploaded to $(r2_path "desktop/v${VERSION}/")"

    # Track Desktop versions for retention cleanup
    DESKTOP_PRUNED=$(update_versions_tracker "desktop" "$VERSION" "$R2_MAX_RELEASE_VERSIONS")
else
    if [[ -n "$STAGING" ]]; then
        log_info "Desktop: skipped (staging mode — CLI only)"
    else
        log_warn "Desktop directory not found: $DESKTOP_DIR"
    fi
fi

# =============================================================================
# Linux Packages
# =============================================================================
if [[ -d "$PACKAGES_DIR" ]] && [[ -z "$STAGING" ]]; then
    log_step "Uploading Linux packages"

    for pkg in "$PACKAGES_DIR"/*; do
        [[ -f "$pkg" ]] || continue
        local_name="$(basename "$pkg")"
        r2_cp "$pkg" "$(r2_path "packages/v${VERSION}/${local_name}")"
        ((UPLOADED++)) || true
    done

    log_info "Packages: uploaded to $(r2_path "packages/v${VERSION}/")"

    # Track Package versions for retention cleanup
    PACKAGES_PRUNED=$(update_versions_tracker "packages" "$VERSION" "$R2_MAX_RELEASE_VERSIONS")
else
    if [[ -n "$STAGING" ]]; then
        log_info "Packages: skipped (staging mode — CLI only)"
    else
        log_warn "Packages directory not found: $PACKAGES_DIR"
    fi
fi

# =============================================================================
# Cleanup Old Versions
# =============================================================================
if [[ -z "$STAGING" ]]; then
    cleanup_old_versions "cli" "${CLI_PRUNED:-}"
    cleanup_old_versions "desktop" "${DESKTOP_PRUNED:-}"
    cleanup_old_versions "packages" "${PACKAGES_PRUNED:-}"
fi

# =============================================================================
# Summary
# =============================================================================
log_step "R2 upload complete"
log_info "  Artifacts uploaded: $UPLOADED"
log_info "  Version: v$VERSION"
if [[ -n "$STAGING" ]]; then
    log_info "  Staging prefix: $PREFIX"
else
    log_info "  Retention: last $R2_MAX_RELEASE_VERSIONS versions"
fi
log_info "  Bucket: $RELEASES_BUCKET"

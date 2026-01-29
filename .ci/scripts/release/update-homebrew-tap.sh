#!/bin/bash
# Update Homebrew tap formula with new version and SHA256 checksums.
#
# Usage:
#   update-homebrew-tap.sh --version X.Y.Z [--push | --stage-only] [--local-checksums <dir>] [--dry-run]
#
# Options:
#   --version              Required version to apply to formula
#   --push                 Commit and push changes to homebrew-tap repo, then
#                          update submodule pointer with a separate commit + normal push
#   --stage-only           Commit inside homebrew-tap, then stage the submodule
#                          pointer in the parent repo (for inclusion in the version commit)
#   --local-checksums DIR  Compute SHA256 from local binaries in DIR instead of
#                          downloading .sha256 files from the GitHub Release
#   --dry-run              Show actions without making changes
#
# Notes:
#   - Updates Formula/rediacc-cli.rb with new version and checksums
#   - Commits include [skip ci] to avoid triggering CI on homebrew-tap
#   - --stage-only is designed for use before the version commit (see commit.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

VERSION=""
PUSH=false
STAGE_ONLY=false
LOCAL_CHECKSUMS_DIR=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --stage-only)
            STAGE_ONLY=true
            shift
            ;;
        --local-checksums)
            LOCAL_CHECKSUMS_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --version X.Y.Z [--push | --stage-only] [--local-checksums <dir>] [--dry-run]"
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
TAP_DIR="$REPO_ROOT/private/homebrew-tap"
FORMULA_FILE="$TAP_DIR/$HOMEBREW_FORMULA_PATH"

# Ensure authenticated access for pushes in CI
if [[ -n "${GITHUB_PAT:-}" ]]; then
    git config --global url."https://${GITHUB_PAT}@github.com/".insteadOf "https://github.com/"
fi

sed_in_place() {
    local expr="$1"
    local file="$2"
    if [[ "$(detect_os)" == "macos" ]]; then
        sed -i '' -E "$expr" "$file"
    else
        sed -i -E "$expr" "$file"
    fi
}

sync_to_origin_main() {
    local dir="$1"
    git -C "$dir" fetch origin main >/dev/null 2>&1 || true
    local origin
    origin="$(git -C "$dir" rev-parse origin/main)"
    if [[ "$DRY_RUN" != "true" ]]; then
        git -C "$dir" checkout -B main "$origin" --force >/dev/null 2>&1
    fi
    log_info "Synced $dir to origin/main ($origin)"
}

download_checksums() {
    local tmpdir="$1"
    log_step "Downloading SHA256 checksums from release v$VERSION..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would download checksums for v$VERSION"
        return 0
    fi

    gh release download "v$VERSION" \
        --repo "$PKG_RELEASE_REPO" \
        --pattern "rdc-*.sha256" \
        --dir "$tmpdir" \
        --clobber

    # Verify we got all required checksums
    local required_files=("rdc-mac-arm64.sha256" "rdc-mac-x64.sha256" "rdc-linux-arm64.sha256" "rdc-linux-x64.sha256")
    for file in "${required_files[@]}"; do
        if [[ ! -f "$tmpdir/$file" ]]; then
            log_error "Missing checksum file: $file"
            exit 1
        fi
    done

    log_info "Downloaded all checksum files"
}

calculate_local_checksums() {
    local dir="$1"
    local outdir="$2"

    log_step "Computing SHA256 checksums from local binaries in $dir..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would compute checksums from $dir"
        return 0
    fi

    local names=("rdc-mac-arm64" "rdc-mac-x64" "rdc-linux-arm64" "rdc-linux-x64")

    for name in "${names[@]}"; do
        local found
        found=$(find "$dir" -name "${name}*" -type f | head -1)
        if [[ -z "$found" ]]; then
            log_error "Missing local binary matching ${name}* in $dir"
            exit 1
        fi
        sha256sum "$found" > "$outdir/${name}.sha256"
        log_info "  ${name}: $(awk '{print $1}' "$outdir/${name}.sha256")"
    done

    log_info "Computed all checksums from local binaries"
}

extract_checksum() {
    local file="$1"
    # Format is: <hash>  <filename>
    awk '{print $1}' "$file"
}

update_formula() {
    local tmpdir="$1"

    log_step "Updating formula with version $VERSION..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update formula to version $VERSION"
        return 0
    fi

    # Extract checksums
    local mac_arm64_sha
    local mac_x64_sha
    local linux_arm64_sha
    local linux_x64_sha

    mac_arm64_sha=$(extract_checksum "$tmpdir/rdc-mac-arm64.sha256")
    mac_x64_sha=$(extract_checksum "$tmpdir/rdc-mac-x64.sha256")
    linux_arm64_sha=$(extract_checksum "$tmpdir/rdc-linux-arm64.sha256")
    linux_x64_sha=$(extract_checksum "$tmpdir/rdc-linux-x64.sha256")

    log_info "Checksums extracted:"
    log_info "  mac-arm64:   $mac_arm64_sha"
    log_info "  mac-x64:     $mac_x64_sha"
    log_info "  linux-arm64: $linux_arm64_sha"
    log_info "  linux-x64:   $linux_x64_sha"

    # Update version
    sed_in_place "s/version \"[^\"]*\"/version \"$VERSION\"/" "$FORMULA_FILE"

    # Update SHA256 checksums
    # The formula has a specific structure where each platform block has its own sha256
    # We need to update them in order: mac-arm64, mac-x64, linux-arm64, linux-x64

    # Use a temporary file to handle multi-line replacements
    local tmpfile
    tmpfile=$(mktemp)

    awk -v mac_arm64="$mac_arm64_sha" \
        -v mac_x64="$mac_x64_sha" \
        -v linux_arm64="$linux_arm64_sha" \
        -v linux_x64="$linux_x64_sha" '
    BEGIN {
        in_macos = 0
        in_linux = 0
        in_arm = 0
        mac_arm_done = 0
        mac_x64_done = 0
        linux_arm_done = 0
        linux_x64_done = 0
    }
    /on_macos do/ { in_macos = 1; in_linux = 0 }
    /on_linux do/ { in_linux = 1; in_macos = 0 }
    /if Hardware::CPU.arm\?/ { in_arm = 1 }
    /^[[:space:]]*else/ { in_arm = 0 }
    /sha256/ {
        if (in_macos && in_arm && !mac_arm_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" mac_arm64 "\"")
            mac_arm_done = 1
        } else if (in_macos && !in_arm && !mac_x64_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" mac_x64 "\"")
            mac_x64_done = 1
        } else if (in_linux && in_arm && !linux_arm_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" linux_arm64 "\"")
            linux_arm_done = 1
        } else if (in_linux && !in_arm && !linux_x64_done) {
            gsub(/sha256 "[^"]*"/, "sha256 \"" linux_x64 "\"")
            linux_x64_done = 1
        }
    }
    { print }
    ' "$FORMULA_FILE" > "$tmpfile"

    mv "$tmpfile" "$FORMULA_FILE"

    log_info "Formula updated successfully"
}

commit_and_push() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would commit and push formula update"
        return 0
    fi

    if git -C "$TAP_DIR" diff --quiet "$HOMEBREW_FORMULA_PATH"; then
        log_info "Formula already at version $VERSION"
        return 0
    fi

    git -C "$TAP_DIR" add "$HOMEBREW_FORMULA_PATH"
    git -C "$TAP_DIR" -c user.name="$PUBLISH_BOT_NAME" -c user.email="$PUBLISH_BOT_EMAIL" \
        commit -m "chore(release): bump rediacc-cli to $VERSION [skip ci]"
    log_info "Committed formula update"

    git -C "$TAP_DIR" push origin HEAD:main
    log_info "Pushed to homebrew-tap"
}

stage_submodule_pointer() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would stage submodule pointer for private/homebrew-tap"
        return 0
    fi

    (
        cd "$REPO_ROOT"
        git add private/homebrew-tap
        log_info "Staged private/homebrew-tap submodule pointer in parent repo"
    )
}

update_submodule_pointer() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update submodule pointer"
        return 0
    fi

    (
        cd "$REPO_ROOT"
        git add private/homebrew-tap

        if git diff --cached --quiet; then
            log_info "No submodule pointer changes"
        else
            git -c user.name="$PUBLISH_BOT_NAME" -c user.email="$PUBLISH_BOT_EMAIL" \
                commit -m "chore(release): update homebrew-tap submodule pointer [skip ci]"
            git push origin HEAD:main
            log_info "Committed and pushed homebrew-tap submodule pointer update"
        fi
    )
}

# Main execution
log_step "Updating Homebrew tap for version $VERSION..."

require_file "$FORMULA_FILE"

# Create temp directory for checksums
CHECKSUM_DIR=$(mktemp -d)
trap 'rm -rf "$CHECKSUM_DIR"' EXIT

# Sync submodule to origin/main
sync_to_origin_main "$TAP_DIR"

# Obtain checksums — either from local binaries or GitHub Release
if [[ -n "$LOCAL_CHECKSUMS_DIR" ]]; then
    calculate_local_checksums "$LOCAL_CHECKSUMS_DIR" "$CHECKSUM_DIR"
else
    download_checksums "$CHECKSUM_DIR"
fi

# Update the formula
update_formula "$CHECKSUM_DIR"

# Commit and optionally push / stage
if [[ "$STAGE_ONLY" == "true" ]]; then
    commit_and_push          # commits inside the homebrew-tap submodule
    stage_submodule_pointer  # stages the pointer in the parent repo
elif [[ "$PUSH" == "true" ]]; then
    commit_and_push
    update_submodule_pointer
fi

log_info "Homebrew tap update complete"

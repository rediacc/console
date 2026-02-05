#!/bin/bash
# Version bump script for Console repository
# Updates version across all package files independently (bash + jq, no Python)
#
# Usage:
#   bump.sh --auto                    # Auto-increment patch version
#   bump.sh --patch                   # Auto-increment patch version
#   bump.sh --minor                   # Manually increment minor version
#   bump.sh --major                   # Manually increment major version
#   bump.sh --version 0.4.30          # Set explicit version
#   bump.sh --dry-run --auto          # Preview auto-increment changes
#   bump.sh --dry-run --minor         # Preview minor bump changes
#   bump.sh --dry-run --version 1.0.0 # Preview explicit version changes
#
# Environment variables:
#   DRY_RUN=true  - Preview changes without writing files
#
# Exit codes:
#   0 - Success
#   1 - Error (invalid arguments, validation failure, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

DRY_RUN="${DRY_RUN:-false}"
EXPLICIT_VERSION=""
OUTPUT_FILE=""
BUMP_TYPE=""

# Ensure only one bump flag is used
set_bump_type() {
    local type="$1"
    if [[ -n "$BUMP_TYPE" ]]; then
        log_error "Only one bump flag may be used (--auto/--patch/--minor/--major)"
        exit 1
    fi
    BUMP_TYPE="$type"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --auto)
            set_bump_type "patch"
            shift
            ;;
        --patch)
            set_bump_type "patch"
            shift
            ;;
        --minor)
            set_bump_type "minor"
            shift
            ;;
        --major)
            set_bump_type "major"
            shift
            ;;
        --version)
            EXPLICIT_VERSION="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -h | --help)
            echo "Usage: $0 [--auto | --patch | --minor | --major | --version X.Y.Z] [--dry-run] [--output file]"
            echo ""
            echo "Options:"
            echo "  --auto        Auto-increment patch version"
            echo "  --patch       Auto-increment patch version"
            echo "  --minor       Manually increment minor version (X.Y+1.0)"
            echo "  --major       Manually increment major version (X+1.0.0)"
            echo "  --version     Set explicit version (X.Y.Z format)"
            echo "  --dry-run     Preview changes without writing"
            echo "  --output      Write version to file (for CI)"
            echo "  -h, --help    Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate arguments
if [[ -z "$BUMP_TYPE" ]] && [[ -z "$EXPLICIT_VERSION" ]]; then
    log_error "Must specify --auto/--patch/--minor/--major or --version"
    echo "Usage: $0 [--auto | --patch | --minor | --major | --version X.Y.Z] [--dry-run]"
    exit 1
fi

if [[ -n "$BUMP_TYPE" ]] && [[ -n "$EXPLICIT_VERSION" ]]; then
    log_error "Cannot combine bump flags with --version"
    exit 1
fi

# Get current version from root package.json
get_current_version() {
    jq -r '.version' "$CONSOLE_ROOT_DIR/package.json"
}

# Validate semver format (X.Y.Z)
validate_semver() {
    local version="$1"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_error "Invalid version format: $version (expected X.Y.Z)"
        return 1
    fi
}

# Increment patch version: 0.4.29 -> 0.4.30
increment_patch() {
    local version="$1"
    local major minor patch
    IFS='.' read -r major minor patch <<<"$version"
    echo "${major}.${minor}.$((patch + 1))"
}

increment_minor() {
    local version="$1"
    local major minor _patch
    IFS='.' read -r major minor _patch <<<"$version"
    echo "${major}.$((minor + 1)).0"
}

increment_major() {
    local version="$1"
    local major _minor _patch
    IFS='.' read -r major _minor _patch <<<"$version"
    echo "$((major + 1)).0.0"
}

# Cross-platform sed -i
sed_in_place() {
    local expr="$1"
    local file="$2"
    if [[ "$(detect_os)" == "macos" ]]; then
        sed -i '' -E "$expr" "$file"
    else
        sed -i -E "$expr" "$file"
    fi
}

# Update package.json file
update_package_json() {
    local file="$1"
    local version="$2"

    if [[ ! -f "$file" ]]; then
        log_warn "File not found: $file"
        return 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $file to $version"
        return 0
    fi

    local tmp_file
    tmp_file=$(mktemp)
    jq --arg v "$version" '.version = $v' "$file" >"$tmp_file"
    mv "$tmp_file" "$file"
    log_info "Updated $file"
}

# Update TypeScript version constant
# Pattern: export const VERSION = 'X.Y.Z';
update_version_ts() {
    local file="$1"
    local version="$2"

    if [[ ! -f "$file" ]]; then
        log_warn "File not found: $file"
        return 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $file to $version"
        return 0
    fi

    # Handle both single and double quotes
    sed_in_place "s/export const VERSION = ['\"][^'\"]*['\"]/export const VERSION = '$version'/" "$file"
    log_info "Updated $file"
}

# Update Go version constant
# Pattern: const Version = "X.Y.Z"
update_version_go() {
    local file="$1"
    local version="$2"

    if [[ ! -f "$file" ]]; then
        log_warn "File not found: $file"
        return 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $file to $version"
        return 0
    fi

    sed_in_place "s/const Version = \"[^\"]*\"/const Version = \"$version\"/" "$file"
    log_info "Updated $file"
}

# Update C# project file version
# Pattern: <Version>X.Y.Z</Version>
update_csproj() {
    local file="$1"
    local version="$2"

    if [[ ! -f "$file" ]]; then
        log_warn "File not found: $file"
        return 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $file to $version"
        return 0
    fi

    sed_in_place "s/<Version>[^<]*<\/Version>/<Version>$version<\/Version>/" "$file"
    log_info "Updated $file"
}

# Main logic
main() {
    local current_version new_version

    require_cmd jq

    current_version=$(get_current_version)
    log_info "Current version: $current_version"

    # Determine new version
    if [[ -n "$EXPLICIT_VERSION" ]]; then
        new_version="$EXPLICIT_VERSION"
    else
        case "$BUMP_TYPE" in
            patch)
                new_version=$(increment_patch "$current_version")
                ;;
            minor)
                new_version=$(increment_minor "$current_version")
                ;;
            major)
                new_version=$(increment_major "$current_version")
                ;;
            *)
                log_error "Unknown bump type: $BUMP_TYPE"
                exit 1
                ;;
        esac
    fi

    # Validate
    if ! validate_semver "$new_version"; then
        exit 1
    fi

    log_step "Updating to version: $new_version"

    # Track update count
    local updated=0
    local failed=0

    # Update all package.json files
    for file in "${VERSION_FILES_JSON[@]}"; do
        local full_path="$CONSOLE_ROOT_DIR/$file"
        if update_package_json "$full_path" "$new_version"; then
            ((updated++)) || true
        else
            ((failed++)) || true
        fi
    done

    # Update TypeScript version constant
    local ts_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_TS"
    if [[ -f "$ts_file" ]]; then
        if update_version_ts "$ts_file" "$new_version"; then
            ((updated++)) || true
        else
            ((failed++)) || true
        fi
    else
        log_warn "TypeScript version file not found: $ts_file"
    fi

    # Update Go version constant
    local go_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_GO"
    if [[ -f "$go_file" ]]; then
        if update_version_go "$go_file" "$new_version"; then
            ((updated++)) || true
        else
            ((failed++)) || true
        fi
    else
        log_warn "Go version file not found: $go_file"
    fi

    # Update C# project version
    local csproj_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_CSPROJ"
    if [[ -f "$csproj_file" ]]; then
        if update_csproj "$csproj_file" "$new_version"; then
            ((updated++)) || true
        else
            ((failed++)) || true
        fi
    else
        log_warn "C# project file not found: $csproj_file"
    fi

    # Summary
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $updated files"
    else
        log_info "Updated $updated files"
    fi

    if [[ $failed -gt 0 ]]; then
        log_error "Failed to update $failed files"
        exit 1
    fi

    # Write version to output file if requested (for CI)
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "$new_version" >"$OUTPUT_FILE"
        log_info "Wrote version to $OUTPUT_FILE"
    fi

    # Output version to stdout (last line for easy capture)
    echo "$new_version"
}

main "$@"

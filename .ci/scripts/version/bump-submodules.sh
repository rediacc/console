#!/bin/bash
# Bump versions inside private submodules and update pointers in console repo.
#
# Usage:
#   bump-submodules.sh --version X.Y.Z [--tag | --no-tag] [--stage-only] [--dry-run]
#
# Options:
#   --version    Required version to apply to submodules
#   --tag        Create and push tag vX.Y.Z in submodule repos (default)
#   --no-tag     Skip tag creation
#   --stage-only Stage submodule pointers in main repo but skip commit/push
#   --dry-run    Show actions without committing/pushing
#
# Notes:
#   - Commits include [skip ci] to avoid submodule CI.
#   - Expects submodules to be checked out at origin/main.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

VERSION=""
TAG=true
STAGE_ONLY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --tag)
            TAG=true
            shift
            ;;
        --no-tag)
            TAG=false
            shift
            ;;
        --stage-only)
            STAGE_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --version X.Y.Z [--tag | --no-tag] [--stage-only] [--dry-run]"
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

# Ensure authenticated access for pushes in CI
if [[ -n "${GITHUB_PAT:-}" ]]; then
    git config --global url."https://x-access-token:${GITHUB_PAT}@github.com/".insteadOf "https://github.com/"
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

    local origin current
    origin="$(git -C "$dir" rev-parse origin/main)"
    current="$(git -C "$dir" rev-parse HEAD)"

    # Guard: refuse to regress — if current HEAD is NOT an ancestor of
    # origin/main, resetting would lose commits.
    if [[ "$current" != "$origin" ]]; then
        if ! git -C "$dir" merge-base --is-ancestor "$current" "$origin" 2>/dev/null; then
            log_error "REGRESSION GUARD: $dir HEAD ($current) is not ancestor of origin/main ($origin)"
            log_error "  Resetting would lose commits. Merge submodule PR first."
            log_error "  Run: .ci/scripts/release/merge-submodule-branches.sh"
            exit 1
        fi
    fi

    if [[ "$DRY_RUN" != "true" ]]; then
        git -C "$dir" checkout -B main "$origin" --force >/dev/null 2>&1
    fi
    log_info "Synced $dir to origin/main ($origin)"
}

commit_and_tag() {
    local dir="$1"
    local file="$2"
    local label="$3"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would update $label version to $VERSION"
        return 0
    fi

    if git -C "$dir" diff --quiet "$file"; then
        log_info "$label already at $VERSION"
    else
        git -C "$dir" add "$file"
        git -C "$dir" -c user.name="$PUBLISH_BOT_NAME" -c user.email="$PUBLISH_BOT_EMAIL" \
            commit -m "chore(release): bump version to $VERSION [skip ci]"
        log_info "Committed $label version bump"
    fi

    if [[ "$TAG" == "true" ]]; then
        if git -C "$dir" rev-parse "v$VERSION" >/dev/null 2>&1; then
            log_info "Tag v$VERSION already exists in $label"
        else
            git -C "$dir" -c user.name="$PUBLISH_BOT_NAME" -c user.email="$PUBLISH_BOT_EMAIL" \
                tag -a "v$VERSION" -m "v$VERSION"
            log_info "Tagged $label with v$VERSION"
        fi
    fi
}

push_changes() {
    local dir="$1"
    local label="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would push $label main and tags"
        return 0
    fi

    git -C "$dir" push origin HEAD:main
    if [[ "$TAG" == "true" ]]; then
        git -C "$dir" push origin "v$VERSION"
    fi
}

update_renet() {
    local dir="$REPO_ROOT/private/renet"
    local file="$dir/cmd/renet/version.go"
    require_file "$file"
    sync_to_origin_main "$dir"
    sed_in_place "s/const Version = \"[^\"]*\"/const Version = \"$VERSION\"/" "$file"
    commit_and_tag "$dir" "$file" "renet"
    push_changes "$dir" "renet"
}

update_middleware() {
    local dir="$REPO_ROOT/private/middleware"
    local file="$dir/middleware.csproj"
    require_file "$file"
    sync_to_origin_main "$dir"
    sed_in_place "s/<Version>[^<]*<\\/Version>/<Version>$VERSION<\\/Version>/" "$file"
    commit_and_tag "$dir" "$file" "middleware"
    push_changes "$dir" "middleware"
}

log_step "Bumping submodule versions to $VERSION..."
update_middleware
update_renet

log_step "Updating submodule pointers in console..."
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would update submodule pointers in console"
else
    cd "$REPO_ROOT"
    git add private/middleware private/renet
    if git diff --cached --quiet; then
        log_info "No submodule pointer changes to commit"
    elif [[ "$STAGE_ONLY" == "true" ]]; then
        log_info "Submodule pointers staged (--stage-only mode, skipping commit)"
    else
        git -c user.name="$PUBLISH_BOT_NAME" -c user.email="$PUBLISH_BOT_EMAIL" \
            commit -m "chore(release): bump submodule versions to $VERSION [skip ci]"
        git push origin HEAD
        log_info "Pushed submodule pointer update"
    fi
fi

log_info "Submodule version bump complete"

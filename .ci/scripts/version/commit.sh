#!/bin/bash
# Commit version changes with bot identity
# Designed for CI use after version bump
#
# Usage:
#   commit.sh                     # Commit staged version changes
#   commit.sh --version 0.4.30    # Include version in commit message
#   commit.sh --push              # Commit and push
#   commit.sh --no-skip-ci        # Commit without [skip ci]
#
# Environment variables:
#   GITHUB_HEAD_REF - PR branch name (for push target)
#   DRY_RUN=true    - Preview without committing
#
# Exit codes:
#   0 - Success (or no changes to commit)
#   1 - Error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

DRY_RUN="${DRY_RUN:-false}"
VERSION=""
PUSH=false
SKIP_CI=true

# Parse arguments
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
        --skip-ci)
            SKIP_CI=true
            shift
            ;;
        --no-skip-ci)
            SKIP_CI=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--version X.Y.Z] [--push] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --version     Include version in commit message"
            echo "  --push        Push after committing"
            echo "  --skip-ci     Include [skip ci] in commit message (default)"
            echo "  --no-skip-ci  Do not include [skip ci] in commit message"
            echo "  --dry-run     Preview without committing"
            echo "  -h, --help    Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check for recent version commits to prevent loops
check_recent_commits() {
    local recent_commit
    recent_commit=$(git log --oneline -5 --author="$PUBLISH_BOT_NAME" --grep="bump version" 2>/dev/null | head -1 || true)

    if [[ -n "$recent_commit" ]]; then
        log_error "Recent version commit detected, preventing loop: $recent_commit"
        log_error "If this is intentional, manually commit the changes"
        return 1
    fi
    return 0
}

# Stage version files
stage_files() {
    log_step "Staging version files..." >&2

    local staged=0

    # Stage package.json files
    for file in "${VERSION_FILES_JSON[@]}"; do
        local full_path="$CONSOLE_ROOT_DIR/$file"
        if [[ -f "$full_path" ]] && ! git diff --quiet "$full_path" 2>/dev/null; then
            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[DRY-RUN] Would stage $file" >&2
            else
                git add "$full_path"
            fi
            ((staged++)) || true
        fi
    done

    # Stage TypeScript version file
    local ts_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_TS"
    if [[ -f "$ts_file" ]] && ! git diff --quiet "$ts_file" 2>/dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would stage $VERSION_FILE_TS" >&2
        else
            git add "$ts_file"
        fi
        ((staged++)) || true
    fi

    # Stage Go version file
    local go_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_GO"
    if [[ -f "$go_file" ]] && ! git diff --quiet "$go_file" 2>/dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would stage $VERSION_FILE_GO" >&2
        else
            git add "$go_file"
        fi
        ((staged++)) || true
    fi

    # Stage C# project file
    local csproj_file="$CONSOLE_ROOT_DIR/$VERSION_FILE_CSPROJ"
    if [[ -f "$csproj_file" ]] && ! git diff --quiet "$csproj_file" 2>/dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would stage $VERSION_FILE_CSPROJ" >&2
        else
            git add "$csproj_file"
        fi
        ((staged++)) || true
    fi

    echo "$staged"
}

# Main logic
main() {
    cd "$CONSOLE_ROOT_DIR"

    # Check for recent commits to prevent loops
    if ! check_recent_commits; then
        exit 1
    fi

    # Stage files
    local staged_count
    staged_count=$(stage_files)

    if [[ "$staged_count" -eq 0 ]]; then
        log_info "No version files changed, nothing to commit"
        exit 0
    fi

    log_info "Staged $staged_count files"

    # Configure git identity
    if [[ "$DRY_RUN" != "true" ]]; then
        git config user.name "$PUBLISH_BOT_NAME"
        git config user.email "$PUBLISH_BOT_EMAIL"
    fi

    # Build commit message
    local commit_msg
    local skip_ci_suffix=""
    if [[ "$SKIP_CI" == "true" ]]; then
        skip_ci_suffix=" [skip ci]"
    fi

    if [[ -n "$VERSION" ]]; then
        commit_msg="chore(release): bump version to $VERSION${skip_ci_suffix}

Automatically incremented by CI."
    else
        commit_msg="chore(release): bump version${skip_ci_suffix}

Automatically incremented by CI."
    fi

    # Commit
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would commit with message:"
        echo "$commit_msg"
    else
        log_step "Committing version changes..."
        git commit -m "$commit_msg"
        log_info "Committed version changes"
    fi

    # Push if requested
    if [[ "$PUSH" == "true" ]]; then
        local push_target
        if [[ -n "${GITHUB_HEAD_REF:-}" ]]; then
            push_target="HEAD:${GITHUB_HEAD_REF}"
        elif [[ -n "${GITHUB_REF_NAME:-}" ]]; then
            push_target="HEAD:${GITHUB_REF_NAME}"
        elif [[ -n "${CI_COMMIT_REF_NAME:-}" ]]; then
            push_target="HEAD:${CI_COMMIT_REF_NAME}"
        else
            push_target="HEAD"
        fi

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would push to origin $push_target"
        else
            log_step "Pushing to origin..."
            git push origin "$push_target"
            log_info "Pushed version commit"
        fi
    fi

    log_info "Version commit complete"
}

main "$@"

#!/bin/bash
# CI Initialization Script
# Consolidates early CI checks: secrets validation, bot detection, submodule init, tag generation
#
# Usage: .ci/scripts/ci/initialize.sh [options]
#
# Options:
#   --check-only    Only run validation checks, skip tag generation
#   --output FILE   Write outputs to file (GitHub Actions format)
#
# Environment variables:
#   GITHUB_PAT          - Token for private repo access (required)
#   GITHUB_EVENT_NAME   - Event type (push, pull_request, etc.)
#   GITHUB_ACTOR        - GitHub username
#   COMMIT_AUTHOR       - Commit author name (for bot detection)
#
# Outputs (written to --output file or stdout):
#   is_bot=true|false
#   api_tag=<hash>
#   bridge_tag=<hash>
#   plugins_tag=<hash>
#   web_tag=<hash>
#   image_tag=<hash>
#   api_exists=true|false
#   bridge_exists=true|false
#   plugins_exists=true|false
#   web_exists=true|false

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

CHECK_ONLY="${ARG_CHECK_ONLY:-false}"
OUTPUT_FILE="${ARG_OUTPUT:-}"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Helper to write output
write_output() {
    local key="$1"
    local value="$2"
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "${key}=${value}" >> "$OUTPUT_FILE"
    fi
    echo "${key}=${value}"
}

# =============================================================================
# Step 1: Validate GH_PAT secret
# =============================================================================
log_step "Validating required secrets..."

if [[ -z "${GITHUB_PAT:-}" ]]; then
    log_error "ERROR: GITHUB_PAT is required but not set"
    log_error "This repository requires private submodule access."
    log_error "Configure the GH_PAT secret in: Settings > Secrets and variables > Actions"
    log_error "Required scopes: repo, write:packages"
    exit 1
fi
log_info "GH_PAT secret is configured"

# =============================================================================
# Step 2: Check if commit is from bot
# =============================================================================
log_step "Checking commit author..."

IS_BOT="false"
COMMIT_AUTHOR="${COMMIT_AUTHOR:-}"
EVENT_NAME="${GITHUB_EVENT_NAME:-}"

if [[ "$EVENT_NAME" == "push" ]] && [[ -n "$COMMIT_AUTHOR" ]]; then
    if [[ "$COMMIT_AUTHOR" == "github-actions[bot]" ]] || [[ "$COMMIT_AUTHOR" == "dependabot[bot]" ]]; then
        IS_BOT="true"
        log_info "Commit from bot: $COMMIT_AUTHOR - downstream jobs will be skipped"
    else
        log_info "Commit author: $COMMIT_AUTHOR"
    fi
else
    log_info "Non-push event or no author info, running CI normally"
fi

write_output "is_bot" "$IS_BOT"

# Exit early if bot commit or check-only mode
if [[ "$IS_BOT" == "true" ]]; then
    log_info "Bot commit detected, skipping remaining initialization"
    exit 0
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
    log_info "Check-only mode, skipping submodule and tag generation"
    exit 0
fi

# =============================================================================
# Step 3: Initialize submodules
# =============================================================================
log_step "Initializing private submodules..."

# Configure git to use token for GitHub
git config --global url."https://${GITHUB_PAT}@github.com/".insteadOf "https://github.com/"

# Check if submodules are already initialized
if [[ -f "private/middleware/.ci/ci.sh" ]] && [[ -f "private/renet/.ci/ci.sh" ]]; then
    log_info "Submodules already initialized"
else
    # Initialize submodules
    if ! git submodule update --init --recursive private/ 2>/dev/null; then
        log_error "Failed to initialize submodules"
        exit 1
    fi

    # Verify initialization
    if [[ ! -f "private/middleware/.ci/ci.sh" ]] || [[ ! -f "private/renet/.ci/ci.sh" ]]; then
        log_error "Submodule initialization incomplete"
        exit 1
    fi
    log_info "Submodules initialized successfully"
fi

# =============================================================================
# Step 4: Generate CI tags
# =============================================================================
log_step "Generating CI tags..."

API_TAG=$(.ci/scripts/ci/generate-tag.sh --submodule private/middleware)
BRIDGE_TAG=$(.ci/scripts/ci/generate-tag.sh --submodule private/renet)
PLUGINS_TAG=$(.ci/scripts/ci/generate-tag.sh --self)
WEB_TAG=$(.ci/scripts/ci/generate-tag.sh --self)

write_output "api_tag" "$API_TAG"
write_output "bridge_tag" "$BRIDGE_TAG"
write_output "plugins_tag" "$PLUGINS_TAG"
write_output "web_tag" "$WEB_TAG"
write_output "image_tag" "$BRIDGE_TAG"

log_info "API tag: $API_TAG (middleware commit)"
log_info "Bridge tag: $BRIDGE_TAG (renet commit)"
log_info "Plugins tag: $PLUGINS_TAG (console commit)"
log_info "Web tag: $WEB_TAG (console commit)"

# =============================================================================
# Step 5: Calculate next version
# =============================================================================
log_step "Calculating next version..."
NEXT_VERSION=$(.ci/scripts/version/bump.sh --auto --dry-run | tail -n 1)
write_output "next_version" "$NEXT_VERSION"
log_info "Next version: $NEXT_VERSION"

# =============================================================================
# Step 6: Check if images exist in registry (requires Docker)
# =============================================================================
log_step "Checking image cache in registry..."

check_image() {
    local name="$1"
    local tag="$2"
    if command -v docker &>/dev/null; then
        if docker manifest inspect "ghcr.io/rediacc/elite/${name}:${tag}" &>/dev/null 2>&1; then
            echo "true"
        else
            echo "false"
        fi
    else
        # Docker not available, assume images don't exist
        echo "false"
    fi
}

API_EXISTS=$(check_image "api" "$API_TAG")
BRIDGE_EXISTS=$(check_image "bridge" "$BRIDGE_TAG")
PLUGINS_EXISTS=$(check_image "plugin-terminal" "$PLUGINS_TAG")
WEB_EXISTS=$(check_image "web" "$WEB_TAG")

write_output "api_exists" "$API_EXISTS"
write_output "bridge_exists" "$BRIDGE_EXISTS"
write_output "plugins_exists" "$PLUGINS_EXISTS"
write_output "web_exists" "$WEB_EXISTS"

log_info "api:$API_TAG exists=$API_EXISTS"
log_info "bridge:$BRIDGE_TAG exists=$BRIDGE_EXISTS"
log_info "plugins:$PLUGINS_TAG exists=$PLUGINS_EXISTS"
log_info "web:$WEB_TAG exists=$WEB_EXISTS"

log_info "Initialization complete"

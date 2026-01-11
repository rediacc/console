#!/bin/bash
# Cleanup Elite environment - cancel workflow and clean up local files

# Don't use set -e to ensure cleanup completes even if some commands fail

# Load shared utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_shared.sh"

# Check dependencies (but don't exit on failure in cleanup)
if ! command -v gh &> /dev/null; then
    log_warn "gh CLI not found, cannot cancel workflow"
fi

# Get run ID
RUN_ID=$(get_run_id 2>/dev/null)
if [ -z "$RUN_ID" ]; then
    log_warn "No active Elite environment to cleanup"
    exit 0
fi

log_info "Cleaning up Elite environment (Run ID: $RUN_ID)..."
log_info "Workflow URL: https://github.com/$ELITE_REPO/actions/runs/$RUN_ID"

# Check if workflow is still running
STATUS=$(gh run view "$RUN_ID" --repo "$ELITE_REPO" --json status --jq '.status' 2>/dev/null || echo "unknown")
log_info "Current workflow status: $STATUS"

if [ "$STATUS" = "in_progress" ] || [ "$STATUS" = "queued" ] || [ "$STATUS" = "waiting" ]; then
    log_info "Workflow is $STATUS, cancelling..."

    if gh run cancel "$RUN_ID" --repo "$ELITE_REPO"; then
        log_success "Workflow cancelled successfully"
    else
        log_warn "Failed to cancel workflow (may have already completed or lack permissions)"
    fi
elif [ "$STATUS" = "unknown" ]; then
    log_warn "Could not determine workflow status, attempting to cancel anyway..."
    gh run cancel "$RUN_ID" --repo "$ELITE_REPO" 2>/dev/null || true
else
    log_info "Workflow already completed with status: $STATUS"
fi

# Archive deployment info if it exists (optional)
if [ -f "$DEPLOYMENT_INFO_FILE" ]; then
    ARCHIVE_DIR="$E2E_DIR/.elite-history"
    mkdir -p "$ARCHIVE_DIR"

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    ARCHIVE_FILE="$ARCHIVE_DIR/deployment-info-${RUN_ID}-${TIMESTAMP}.json"

    cp "$DEPLOYMENT_INFO_FILE" "$ARCHIVE_FILE"
    log_info "Archived deployment info to: $ARCHIVE_FILE"
fi

# Clean up local files
log_info "Cleaning up local files..."

if [ -f "$DEPLOYMENT_INFO_FILE" ]; then
    rm -f "$DEPLOYMENT_INFO_FILE"
    log_success "Removed deployment info file"
fi

if [ -f "$RUN_ID_FILE" ]; then
    rm -f "$RUN_ID_FILE"
    log_success "Removed run ID file"
fi

# Clean up backups older than 30 minutes
if [ -d "$E2E_DIR/.elite-history" ]; then
    find "$E2E_DIR/.elite-history" -name "deployment-info-*.json" -mmin +30 -delete 2>/dev/null || true
fi

print_separator
log_success "Cleanup complete!"
print_separator
echo ""
log_info "Elite environment has been cleaned up"
log_info "Run './go trigger' to start a new environment"

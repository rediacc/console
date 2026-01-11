#!/bin/bash
# Trigger Elite environment workflow and wait for deployment info

set -e

# Load shared utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_shared.sh"

# Check dependencies
check_dependencies

# Parse arguments
RUN_NAME="${1:-E2E Test Environment}"
DURATION="${2:-30}"
VERSION="${3:-latest}"
ENABLE_VMS="${4:-true}"
VM_PROVIDER="${5:-kvm}"
VM_CONFIG="${6:-Standard}"
ENABLE_DEBUG="${7:-false}"
VM_OS_IMAGE="${8:-rediacc-ubuntu-24.04}"
SKIP_MACHINE_REG="${9:-false}"
CI_MODE="${10:-true}"

log_info "Triggering Elite environment..."
log_info "  Run Name: ${RUN_NAME}"
log_info "  Duration: ${DURATION} minutes"
log_info "  Version: ${VERSION}"
log_info "  VMs: ${ENABLE_VMS} (${VM_PROVIDER}, ${VM_CONFIG}, ${VM_OS_IMAGE})"
log_info "  Debug: ${ENABLE_DEBUG}"
log_info "  Skip Registration: ${SKIP_MACHINE_REG}"
log_info "  CI Mode: ${CI_MODE}"

# Trigger the workflow
log_info "Starting workflow..."
gh workflow run "$WORKFLOW_NAME" \
    --repo "$ELITE_REPO" \
    -f run-name="$RUN_NAME" \
    -f duration="$DURATION" \
    -f version="$VERSION" \
    -f enable-vms="$ENABLE_VMS" \
    -f vm-provider="$VM_PROVIDER" \
    -f vm-configuration="$VM_CONFIG" \
    -f enable-debug="$ENABLE_DEBUG" \
    -f vm-os-image="$VM_OS_IMAGE" \
    -f skip-machine-registration="$SKIP_MACHINE_REG" \
    -f ci-mode="$CI_MODE"

if [ $? -ne 0 ]; then
    log_error "Failed to trigger workflow"
    exit 1
fi

log_success "Workflow triggered successfully"

# Wait for workflow to start
log_info "Waiting for workflow to start..."
sleep 5

# Get the most recent run ID
RUN_ID=$(gh run list --repo "$ELITE_REPO" \
    --workflow "$WORKFLOW_NAME" \
    --limit 1 \
    --json databaseId,status,createdAt \
    --jq '.[0].databaseId')

if [ -z "$RUN_ID" ]; then
    log_error "Failed to get run ID"
    exit 1
fi

log_success "Run ID: $RUN_ID"
log_info "Workflow URL: https://github.com/$ELITE_REPO/actions/runs/$RUN_ID"

# Save run ID
save_run_id "$RUN_ID"

# Wait for artifact to be available
log_info "Waiting for deployment information artifact..."
ARTIFACT_NAME="deployment-info-${RUN_ID}"
TIMEOUT=900  # 15 minutes timeout (VM provisioning can take time)
ELAPSED=0

while true; do
    # Check if artifact exists
    ARTIFACT_COUNT=$(gh api "repos/$ELITE_REPO/actions/runs/$RUN_ID/artifacts" \
        --jq ".artifacts[] | select(.name == \"$ARTIFACT_NAME\") | .id" | wc -l)

    if [ "$ARTIFACT_COUNT" -gt 0 ]; then
        log_success "Deployment information artifact found!"
        break
    fi

    # Check if workflow failed
    STATUS=$(gh run view "$RUN_ID" --repo "$ELITE_REPO" --json status --jq '.status')
    if [ "$STATUS" = "completed" ]; then
        CONCLUSION=$(gh run view "$RUN_ID" --repo "$ELITE_REPO" --json conclusion --jq '.conclusion')
        if [ "$CONCLUSION" != "success" ]; then
            log_error "Workflow completed with status: $CONCLUSION"
            log_error "Check logs: gh run view $RUN_ID --repo $ELITE_REPO --log"
            clear_run_id
            exit 1
        fi
    fi

    # Check timeout
    if [ $ELAPSED -ge $TIMEOUT ]; then
        log_error "Timeout waiting for deployment information"
        log_error "Workflow may still be running. Check: gh run view $RUN_ID --repo $ELITE_REPO"
        exit 1
    fi

    # Progress indicator
    echo -n "."
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done

echo ""  # New line after dots
log_success "Elite environment is ready!"
log_info "Run ID saved to: $RUN_ID_FILE"

# Return the run ID for chaining
echo "$RUN_ID"

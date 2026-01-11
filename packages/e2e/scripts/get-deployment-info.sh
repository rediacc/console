#!/bin/bash
# Download and parse deployment information from Elite workflow artifact

set -e

# Load shared utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_shared.sh"

# Check dependencies
check_dependencies

# Get run ID
RUN_ID=$(get_run_id)
if [ $? -ne 0 ]; then
    exit 1
fi

log_info "Downloading deployment information for run $RUN_ID..."

# Create temp directory for download
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Download artifact
ARTIFACT_NAME="deployment-info-${RUN_ID}"
log_info "Artifact name: $ARTIFACT_NAME"

if ! gh run download "$RUN_ID" \
    --repo "$ELITE_REPO" \
    --name "$ARTIFACT_NAME" \
    --dir "$TEMP_DIR" 2>/dev/null; then
    log_error "Failed to download artifact"
    log_error "Artifact may not be available yet"
    exit 1
fi

# Move to deployment info file
if [ ! -f "$TEMP_DIR/deployment-info.json" ]; then
    log_error "deployment-info.json not found in artifact"
    log_error "Contents: $(ls -la $TEMP_DIR)"
    exit 1
fi

mv "$TEMP_DIR/deployment-info.json" "$DEPLOYMENT_INFO_FILE"
log_success "Deployment information downloaded"

# Validate JSON
if ! jq empty "$DEPLOYMENT_INFO_FILE" 2>/dev/null; then
    log_error "Invalid JSON in deployment info"
    cat "$DEPLOYMENT_INFO_FILE"
    exit 1
fi

# Display summary
print_separator
echo "🌍 DEPLOYMENT INFORMATION"
print_separator
echo ""

DEPLOYMENT_INFO=$(cat "$DEPLOYMENT_INFO_FILE")

# Metadata
RUN_URL=$(jq_get "$DEPLOYMENT_INFO" '.metadata.workflow_url')
VERSION=$(jq_get "$DEPLOYMENT_INFO" '.metadata.version')
DURATION=$(jq_get "$DEPLOYMENT_INFO" '.metadata.duration_minutes')

echo "📋 Metadata:"
echo "   • Run ID: $RUN_ID"
echo "   • Version: $VERSION"
echo "   • Duration: $DURATION minutes"
echo "   • URL: $RUN_URL"
echo ""

# Access URLs
TUNNEL_URL=$(jq_get "$DEPLOYMENT_INFO" '.access.tunnel_url')
API_URL=$(jq_get "$DEPLOYMENT_INFO" '.access.api_url')

echo "🌐 Access URLs:"
echo "   • Cloudflare Tunnel: $TUNNEL_URL"
echo "   • API: $API_URL"
echo ""

# VM Information (if enabled)
VMS_ENABLED=$(jq_get "$DEPLOYMENT_INFO" '.vms.enabled')
if [ "$VMS_ENABLED" = "true" ]; then
    VM_PROVIDER=$(jq_get "$DEPLOYMENT_INFO" '.vms.provider')
    VM_CONFIG=$(jq_get "$DEPLOYMENT_INFO" '.vms.configuration')
    BRIDGE_IP=$(jq_get "$DEPLOYMENT_INFO" '.vms.bridge_ip')
    WORKER_IPS=$(jq_get "$DEPLOYMENT_INFO" '.vms.worker_ips | join(", ")')

    echo "🖥️  VM Infrastructure:"
    echo "   • Provider: $VM_PROVIDER"
    echo "   • Configuration: $VM_CONFIG"
    echo "   • Bridge IP: $BRIDGE_IP"
    echo "   • Worker IPs: $WORKER_IPS"
    echo ""

    # Machine Credentials
    MACHINE_USER=$(jq_get "$DEPLOYMENT_INFO" '.vms.machine_user')
    MACHINE_PASSWORD=$(jq_get "$DEPLOYMENT_INFO" '.vms.machine_password')
    if [ "$MACHINE_USER" != "null" ] && [ -n "$MACHINE_USER" ]; then
        echo "🔐 VM Credentials:"
        echo "   • Username: $MACHINE_USER"
        echo "   • Password: $MACHINE_PASSWORD"
        echo ""
    fi

    # SSH Access
    BRIDGE_SSH=$(jq_get "$DEPLOYMENT_INFO" '.vms.ssh_access.bridge')
    echo "🔑 SSH Access:"
    echo "   • Bridge: $BRIDGE_SSH"

    # Worker SSH commands
    WORKER_SSH=$(jq_get "$DEPLOYMENT_INFO" '.vms.ssh_access.workers | join("\n   • ")')
    if [ "$WORKER_SSH" != "null" ] && [ -n "$WORKER_SSH" ]; then
        echo "   • $WORKER_SSH"
    fi
    echo ""
fi

# Debug Information (if enabled)
DEBUG_ENABLED=$(jq_get "$DEPLOYMENT_INFO" '.debug.enabled')
if [ "$DEBUG_ENABLED" = "true" ]; then
    DEBUG_SSH=$(jq_get "$DEPLOYMENT_INFO" '.debug.ssh_connection')
    DEBUG_WEB=$(jq_get "$DEPLOYMENT_INFO" '.debug.web_url')

    echo "🔧 Debug Access:"
    echo "   • SSH: $DEBUG_SSH"
    echo "   • Web: $DEBUG_WEB"
    echo ""
fi

print_separator

log_success "Deployment information saved to: $DEPLOYMENT_INFO_FILE"

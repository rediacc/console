#!/bin/bash
# Update .env file with deployment information

set -e

# Load shared utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_shared.sh"

# Check dependencies
check_dependencies

# Get deployment info
DEPLOYMENT_INFO=$(get_deployment_info)
if [ $? -ne 0 ]; then
    exit 1
fi

ENV_FILE="$E2E_DIR/.env"
ENV_BACKUP="$E2E_DIR/.env.backup"

log_info "Updating .env file with deployment information..."

# Create backup if .env exists
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$ENV_BACKUP"
    log_info "Backup created: $ENV_BACKUP"
fi

# Extract values from deployment info
TUNNEL_URL=$(jq_get "$DEPLOYMENT_INFO" '.access.tunnel_url')
API_URL=$(jq_get "$DEPLOYMENT_INFO" '.access.api_url')

if [ -z "$TUNNEL_URL" ] || [ "$TUNNEL_URL" = "null" ]; then
    log_error "Tunnel URL not found in deployment info"
    exit 1
fi

# Function to update or add env variable
update_env_var() {
    local key="$1"
    local value="$2"
    local file="$3"

    if grep -q "^${key}=" "$file" 2>/dev/null; then
        # Update existing
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        # Add new
        echo "${key}=${value}" >> "$file"
    fi
}

# Create .env if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$E2E_DIR/.env.sample" ]; then
        cp "$E2E_DIR/.env.sample" "$ENV_FILE"
        log_info "Created .env from .env.sample"
    else
        touch "$ENV_FILE"
        log_info "Created new .env file"
    fi
fi

# Update BASE_URL with tunnel URL
update_env_var "BASE_URL" "$TUNNEL_URL" "$ENV_FILE"
log_success "Updated BASE_URL=$TUNNEL_URL"

# Optionally add API URL if needed
# update_env_var "API_URL" "$API_URL" "$ENV_FILE"

log_success ".env file updated successfully"
log_info "Environment file: $ENV_FILE"

# Display what was updated
echo ""
log_info "Updated variables:"
echo "   • BASE_URL: $TUNNEL_URL"

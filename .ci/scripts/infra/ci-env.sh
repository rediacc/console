#!/bin/bash
# CI Environment Setup Script
# Self-contained environment configuration for console CI
# Replaces dependency on elite/action/ci-env.sh
#
# Usage:
#   source .ci/scripts/infra/ci-env.sh
#
# This script:
# 1. Preserves workflow env vars (API_TAG, BRIDGE_TAG, WEB_TAG)
# 2. Generates SQL Server passwords with complexity requirements
# 3. Builds connection string
# 4. Exports all required environment variables
# 5. Masks sensitive values in GitHub Actions logs

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# =============================================================================
# PRESERVE WORKFLOW ENVIRONMENT VARIABLES
# =============================================================================
# These may be set by the CI workflow before sourcing this script
WORKFLOW_TAG="${TAG:-}"
WORKFLOW_CI_MODE="${CI_MODE:-}"
WORKFLOW_API_TAG="${API_TAG:-}"
WORKFLOW_BRIDGE_TAG="${BRIDGE_TAG:-}"
WORKFLOW_WEB_TAG="${WEB_TAG:-}"

# =============================================================================
# PASSWORD GENERATION
# =============================================================================
# Generate secure password meeting SQL Server complexity requirements:
# - At least 8 characters
# - Contains uppercase, lowercase, digit, and special character
generate_password() {
    # Generate 20-character base password from random bytes
    local password
    password=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-20)
    # Append complexity characters to ensure SQL Server requirements
    # This guarantees: uppercase (A), lowercase (a), digit (1), special (!)
    echo "${password}Aa1!"
}

# =============================================================================
# DOCKER REGISTRY CONFIGURATION
# =============================================================================
export DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/rediacc/elite}"

# For GitHub Container Registry, use GITHUB_TOKEN if available (GitHub Actions)
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    export DOCKER_REGISTRY_USERNAME="${GITHUB_ACTOR:-github-actions}"
    export DOCKER_REGISTRY_PASSWORD="${GITHUB_TOKEN}"
fi

# =============================================================================
# IMAGE TAGS
# =============================================================================
# Restore/set image tags (workflow values take precedence)
export TAG="${WORKFLOW_TAG:-latest}"
export API_TAG="${WORKFLOW_API_TAG:-$TAG}"
export BRIDGE_TAG="${WORKFLOW_BRIDGE_TAG:-$TAG}"
export WEB_TAG="${WORKFLOW_WEB_TAG:-$TAG}"

# Bridge image for middleware to spawn bridge containers
export DOCKER_BRIDGE_IMAGE="${DOCKER_REGISTRY}/bridge:${BRIDGE_TAG}"

# =============================================================================
# NETWORK CONFIGURATION
# =============================================================================
# Docker network name for bridge containers (standalone mode)
export DOCKER_INTERNET_NETWORK="rediacc_internet"

# Host networking for CI - allows bridge containers to access localhost for SSH
export DOCKER_BRIDGE_NETWORK_MODE="host"

# API URL for bridges using host networking (cannot resolve container names)
export DOCKER_BRIDGE_API_URL="http://localhost"

# =============================================================================
# SQL SERVER CONFIGURATION
# =============================================================================
# Generate database passwords
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-$(generate_password)}"
export MSSQL_RA_PASSWORD="${MSSQL_RA_PASSWORD:-$(generate_password)}"
export REDIACC_DATABASE_NAME="${REDIACC_DATABASE_NAME:-RediaccMiddleware}"
export REDIACC_SQL_USERNAME="${REDIACC_SQL_USERNAME:-rediacc}"

# Mask passwords in GitHub Actions logs
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "::add-mask::$MSSQL_SA_PASSWORD"
    echo "::add-mask::$MSSQL_RA_PASSWORD"
fi

# Build connection string (same format as middleware expects)
export CONNECTION_STRING="Server=sql,1433;Database=${REDIACC_DATABASE_NAME};User Id=${REDIACC_SQL_USERNAME};Password=\"${MSSQL_RA_PASSWORD}\";TrustServerCertificate=True;Application Name=${REDIACC_DATABASE_NAME};Max Pool Size=32;Min Pool Size=2;Connection Lifetime=120;Connection Timeout=15;Command Timeout=30;Pooling=true;MultipleActiveResultSets=false;Packet Size=32768"

# =============================================================================
# SYSTEM DEFAULTS
# =============================================================================
export SYSTEM_DOMAIN="${SYSTEM_DOMAIN:-localhost}"
export SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-admin@rediacc.io}"
export SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
export SYSTEM_ORGANIZATION_NAME="${SYSTEM_ORGANIZATION_NAME:-Default Organization}"
export SYSTEM_DEFAULT_BRIDGE_NAME="${SYSTEM_DEFAULT_BRIDGE_NAME:-Global Bridges}"
export SYSTEM_DEFAULT_REGION_NAME="${SYSTEM_DEFAULT_REGION_NAME:-Default Region}"
export SYSTEM_DEFAULT_TEAM_NAME="${SYSTEM_DEFAULT_TEAM_NAME:-Private Team}"

# CI mode configuration
export CI_MODE="${WORKFLOW_CI_MODE:-true}"

# =============================================================================
# GITHUB ENVIRONMENT EXPORT
# =============================================================================
# Export variables to GITHUB_ENV for subsequent workflow steps
if [[ -n "${GITHUB_ENV:-}" ]]; then
    {
        echo "DOCKER_REGISTRY=${DOCKER_REGISTRY}"
        echo "SYSTEM_DEFAULT_TEAM_NAME=${SYSTEM_DEFAULT_TEAM_NAME}"
        echo "SYSTEM_DEFAULT_REGION_NAME=${SYSTEM_DEFAULT_REGION_NAME}"
        echo "SYSTEM_DEFAULT_BRIDGE_NAME=${SYSTEM_DEFAULT_BRIDGE_NAME}"
        echo "DOCKER_BRIDGE_IMAGE=${DOCKER_BRIDGE_IMAGE}"
        echo "MSSQL_SA_PASSWORD=${MSSQL_SA_PASSWORD}"
        echo "MSSQL_RA_PASSWORD=${MSSQL_RA_PASSWORD}"
        echo "REDIACC_DATABASE_NAME=${REDIACC_DATABASE_NAME}"
        echo "REDIACC_SQL_USERNAME=${REDIACC_SQL_USERNAME}"
        echo "CONNECTION_STRING=${CONNECTION_STRING}"
    } >> "$GITHUB_ENV"
fi

# =============================================================================
# CI DOCKER PATHS
# =============================================================================
export CI_DOCKER_DIR="$CONSOLE_ROOT/.ci/docker/ci"
export CI_COMPOSE_FILE="$CI_DOCKER_DIR/docker-compose.yml"

echo "CI environment configured:"
echo "  Docker Registry: $DOCKER_REGISTRY"
echo "  API Tag: $API_TAG"
echo "  Bridge Tag: $BRIDGE_TAG"
echo "  Web Tag: $WEB_TAG"
echo "  Database: $REDIACC_DATABASE_NAME"

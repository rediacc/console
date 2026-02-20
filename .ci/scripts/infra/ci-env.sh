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
# ACCOUNT SERVER CONFIGURATION
# =============================================================================
# Generate Ed25519 key pair for subscription signing if not provided
if [[ -z "${ED25519_PRIVATE_KEY:-}" ]]; then
    KEYS=$(node -e "
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
        console.log(JSON.stringify({
            private: privateKey.export({type:'pkcs8',format:'der'}).toString('base64'),
            public: publicKey.export({type:'spki',format:'der'}).toString('base64')
        }));
    ")
    ED25519_PRIVATE_KEY=$(echo "$KEYS" | jq -r '.private')
    ED25519_PUBLIC_KEY=$(echo "$KEYS" | jq -r '.public')
fi
export ED25519_PRIVATE_KEY ED25519_PUBLIC_KEY

# Account server API key (generate if not provided)
export ACCOUNT_SERVER_API_KEY="${ACCOUNT_SERVER_API_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-64)}"
export ACCOUNT_SERVER_URL="${ACCOUNT_SERVER_URL:-http://account-server:3000}"

# Stripe webhook secret for account-server integration tests
export STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_test_$(openssl rand -hex 32)}"

# RustFS credentials for S3-compatible storage
export RUSTFS_ACCESS_KEY="${RUSTFS_ACCESS_KEY:-rustfsadmin}"
export RUSTFS_SECRET_KEY="${RUSTFS_SECRET_KEY:-rustfsadmin}"

# Mask sensitive values in GitHub Actions logs
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "::add-mask::$ED25519_PRIVATE_KEY"
    echo "::add-mask::$ACCOUNT_SERVER_API_KEY"
    echo "::add-mask::$STRIPE_WEBHOOK_SECRET"
    echo "::add-mask::$RUSTFS_SECRET_KEY"
fi

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
export SYSTEM_PLAN_CODE="${SYSTEM_PLAN_CODE:-COMMUNITY}"

# CI mode configuration
export CI_MODE="${WORKFLOW_CI_MODE:-true}"

# =============================================================================
# CI DOCKER PATHS
# =============================================================================
export CI_DOCKER_DIR="$CONSOLE_ROOT/.ci/docker/ci"
export CI_COMPOSE_FILE="$CI_DOCKER_DIR/docker-compose.yml"

# =============================================================================
# PERSIST ENVIRONMENT VARIABLES
# =============================================================================
# All docker-compose-referenced variables are defined once here and written to:
#   1. .env file  — read by docker compose from any workflow step / shell
#   2. GITHUB_ENV — available to subsequent GitHub Actions steps
#
# This single list prevents the class of bugs where a variable is added to
# docker-compose.yml but forgotten in one of the persistence targets.
# The quality check (check-compose-env.sh) validates this list stays complete.
PERSISTED_ENV=$(
    cat <<ENVBLOCK
DOCKER_REGISTRY=${DOCKER_REGISTRY}
TAG=${TAG}
API_TAG=${API_TAG}
WEB_TAG=${WEB_TAG}
BRIDGE_TAG=${BRIDGE_TAG}
DOCKER_BRIDGE_IMAGE=${DOCKER_BRIDGE_IMAGE}
DOCKER_BRIDGE_NETWORK_MODE=${DOCKER_BRIDGE_NETWORK_MODE}
DOCKER_BRIDGE_API_URL=${DOCKER_BRIDGE_API_URL}
SYSTEM_DOMAIN=${SYSTEM_DOMAIN}
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
CONNECTION_STRING=${CONNECTION_STRING}
MSSQL_SA_PASSWORD=${MSSQL_SA_PASSWORD}
MSSQL_RA_PASSWORD=${MSSQL_RA_PASSWORD}
REDIACC_DATABASE_NAME=${REDIACC_DATABASE_NAME}
REDIACC_SQL_USERNAME=${REDIACC_SQL_USERNAME}
SYSTEM_ADMIN_EMAIL=${SYSTEM_ADMIN_EMAIL}
SYSTEM_ADMIN_PASSWORD=${SYSTEM_ADMIN_PASSWORD}
SYSTEM_ORGANIZATION_NAME=${SYSTEM_ORGANIZATION_NAME}
SYSTEM_ORGANIZATION_VAULT_DEFAULTS=${SYSTEM_ORGANIZATION_VAULT_DEFAULTS:-}
SYSTEM_DEFAULT_BRIDGE_NAME=${SYSTEM_DEFAULT_BRIDGE_NAME}
SYSTEM_DEFAULT_REGION_NAME=${SYSTEM_DEFAULT_REGION_NAME}
SYSTEM_DEFAULT_TEAM_NAME=${SYSTEM_DEFAULT_TEAM_NAME}
CI_MODE=${CI_MODE}
ACCOUNT_SERVER_URL=${ACCOUNT_SERVER_URL}
ACCOUNT_SERVER_API_KEY=${ACCOUNT_SERVER_API_KEY}
ED25519_PRIVATE_KEY=${ED25519_PRIVATE_KEY}
ED25519_PUBLIC_KEY=${ED25519_PUBLIC_KEY}
RUSTFS_ACCESS_KEY=${RUSTFS_ACCESS_KEY}
RUSTFS_SECRET_KEY=${RUSTFS_SECRET_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
ENVBLOCK
)

# Write .env file for docker compose (gitignored)
{
    echo "# Auto-generated by ci-env.sh — do not edit"
    echo "$PERSISTED_ENV"
} >"$CI_DOCKER_DIR/.env"

# Export to GITHUB_ENV for subsequent workflow steps
if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "$PERSISTED_ENV" >>"$GITHUB_ENV"
fi

echo "CI environment configured:"
echo "  Docker Registry: $DOCKER_REGISTRY"
echo "  API Tag: $API_TAG"
echo "  Bridge Tag: $BRIDGE_TAG"
echo "  Web Tag: $WEB_TAG"
echo "  Database: $REDIACC_DATABASE_NAME"
echo "  Account Server: $ACCOUNT_SERVER_URL"

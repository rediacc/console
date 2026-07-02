#!/bin/bash
# CI Environment Setup Script
# Self-contained environment configuration for console CI
# Replaces dependency on elite/action/ci-env.sh
#
# Usage:
#   source .ci/scripts/infra/ci-env.sh
#
# This script:
# 1. Preserves workflow env vars (WEB_TAG)
# 2. Generates account-server keys/secrets when not provided
# 3. Exports all required environment variables
# 4. Masks sensitive values in GitHub Actions logs

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
WORKFLOW_WEB_TAG="${WEB_TAG:-}"

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
export WEB_TAG="${WORKFLOW_WEB_TAG:-$TAG}"

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

# Generate X25519 key pair for e2e encryption if not provided
# Production keys come from GitHub secrets (cd-v2.yml only).
# CI/test workflows generate throwaway keys here.
if [[ -z "${X25519_PRIVATE_KEY:-}" ]]; then
    X25519_KEYS=$(node -e "
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('x25519');
        console.log(JSON.stringify({
            private: privateKey.export({type:'pkcs8',format:'der'}).toString('base64'),
            public: publicKey.export({type:'spki',format:'der'}).toString('base64')
        }));
    ")
    X25519_PRIVATE_KEY=$(echo "$X25519_KEYS" | jq -r '.private')
    X25519_PUBLIC_KEY=$(echo "$X25519_KEYS" | jq -r '.public')
fi
export X25519_PRIVATE_KEY X25519_PUBLIC_KEY

# Account server API key (generate if not provided)
export ACCOUNT_SERVER_API_KEY="${ACCOUNT_SERVER_API_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-64)}"
export ACCOUNT_SERVER_URL="${ACCOUNT_SERVER_URL:-http://account-server:3000}"

# JWT secret for account-server session management
export JWT_SECRET="${JWT_SECRET:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-64)}"

# Stripe webhook secret for account-server integration tests
export STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-whsec_test_$(openssl rand -hex 32)}"

# Mask ALL generated secrets (GitHub only auto-masks ${{ secrets.* }} values)
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "::add-mask::$ED25519_PRIVATE_KEY"
    echo "::add-mask::$ED25519_PUBLIC_KEY"
    echo "::add-mask::$X25519_PRIVATE_KEY"
    echo "::add-mask::$X25519_PUBLIC_KEY"
    echo "::add-mask::$ACCOUNT_SERVER_API_KEY"
    echo "::add-mask::$JWT_SECRET"
    echo "::add-mask::$STRIPE_WEBHOOK_SECRET"
fi

# =============================================================================
# SYSTEM DEFAULTS
# =============================================================================
export SYSTEM_DOMAIN="${SYSTEM_DOMAIN:-localhost}"
export SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-admin@rediacc.io}"
export SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
[[ -n "${GITHUB_ACTIONS:-}" ]] && echo "::add-mask::$SYSTEM_ADMIN_PASSWORD"
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
WEB_TAG=${WEB_TAG}
SYSTEM_DOMAIN=${SYSTEM_DOMAIN}
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
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
X25519_PRIVATE_KEY=${X25519_PRIVATE_KEY}
X25519_PUBLIC_KEY=${X25519_PUBLIC_KEY}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
JWT_SECRET=${JWT_SECRET}
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
echo "  Web Tag: $WEB_TAG"
echo "  Account Server: $ACCOUNT_SERVER_URL"

#!/bin/bash
# Console development constants
# Single source of truth for all configuration
#
# ⚠️  IMPORTANT: When updating constants or configuration:
# ⚠️  1. Update this file (constants.sh)
# ⚠️  2. Update the main 'go' script if needed (console/go)
# ⚠️  3. Update documentation (console/docs/BACKEND.md)

# Prevent re-sourcing
[[ -n "${REDIACC_CONSTANTS_LOADED:-}" ]] && return 0
readonly REDIACC_CONSTANTS_LOADED=1

# =============================================================================
# VERSION REQUIREMENTS
# =============================================================================
readonly NODE_VERSION_REQUIRED="22"
readonly NODE_VERSION_MIN="22.0.0"
readonly NPM_VERSION_MIN="10.0.0"

# =============================================================================
# ELITE BACKEND CONFIGURATION
# =============================================================================
readonly ELITE_REPO_URL="https://github.com/rediacc/elite.git"
readonly ELITE_LOCAL_PATH="${ELITE_LOCAL_PATH:-$HOME/.rediacc/elite}"
readonly ELITE_DOCKER_REGISTRY="ghcr.io/rediacc/elite"
readonly ELITE_TAG="${ELITE_TAG:-latest}"

# Elite Docker Images
readonly ELITE_IMAGE_WEB="${ELITE_DOCKER_REGISTRY}/web:${ELITE_TAG}"
readonly ELITE_IMAGE_API="${ELITE_DOCKER_REGISTRY}/api:${ELITE_TAG}"
readonly ELITE_IMAGE_BRIDGE="${ELITE_DOCKER_REGISTRY}/bridge:${ELITE_TAG}"
readonly ELITE_IMAGE_SQL="mcr.microsoft.com/mssql/server:2022-CU21-ubuntu-22.04"

# Elite Container Names (matches CI standalone mode)
readonly ELITE_CONTAINER_WEB="rediacc-web"
readonly ELITE_CONTAINER_API="rediacc-api"
readonly ELITE_CONTAINER_SQL="rediacc-sql"

# Elite Docker Networks
readonly ELITE_NETWORK_INTERNET="rediacc_internet"
readonly ELITE_NETWORK_INTRANET="rediacc_intranet"

# =============================================================================
# API CONFIGURATION
# =============================================================================
readonly API_URL_LOCAL="http://localhost/api"
readonly API_URL_SANDBOX="https://sandbox.rediacc.com/api"
readonly API_HEALTH_ENDPOINT="/health"
readonly API_HEALTH_TIMEOUT=120  # seconds (matches CI)
readonly API_HEALTH_INTERVAL=2    # seconds between retries

# =============================================================================
# PORTS
# =============================================================================
readonly PORT_WEB=80              # Elite web proxy (nginx)
readonly PORT_WEB_HTTPS=443       # Elite web proxy (https)
readonly PORT_SQL=1433            # SQL Server
readonly PORT_CONSOLE_DEV=3000    # Console dev server default

# =============================================================================
# PATHS
# =============================================================================
readonly CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
readonly CI_DIR="$CONSOLE_ROOT_DIR/.ci"
readonly CI_SCRIPTS_DIR="$CI_DIR/scripts"
readonly CI_LIB_DIR="$CI_DIR/lib"
readonly CI_CONFIG_DIR="$CI_DIR/config"

# Backend management
readonly BACKEND_STATE_FILE="$CONSOLE_ROOT_DIR/.backend-state"
readonly BACKEND_ENV_FILE="$ELITE_LOCAL_PATH/.env"

# =============================================================================
# BUILD CONFIGURATION
# =============================================================================
readonly BUILD_TYPE_DEBUG="DEBUG"
readonly BUILD_TYPE_RELEASE="RELEASE"
readonly BUILD_TYPE_DEFAULT="$BUILD_TYPE_DEBUG"

# Docker build args
readonly DOCKER_BUILD_ARG_NODE_VERSION="NODE_VERSION=$NODE_VERSION_REQUIRED"

# =============================================================================
# BACKEND MODES
# =============================================================================
readonly BACKEND_MODE_GHCR="ghcr"        # Pull from ghcr.io (CI mode)
readonly BACKEND_MODE_LOCAL="local"      # Build from elite source
readonly BACKEND_MODE_DEFAULT="$BACKEND_MODE_GHCR"

# =============================================================================
# SQL CONFIGURATION
# =============================================================================
readonly SQL_SA_USER="sa"
readonly SQL_RA_USER_PREFIX="rediacc"
readonly SQL_DATABASE_PREFIX="RediaccMiddleware"
readonly SQL_INSTANCE_NAME="${SQL_INSTANCE_NAME:-local}"

# =============================================================================
# LOGGING
# =============================================================================
readonly LOG_LEVEL_DEBUG="debug"
readonly LOG_LEVEL_INFO="info"
readonly LOG_LEVEL_WARN="warn"
readonly LOG_LEVEL_ERROR="error"
readonly LOG_LEVEL_DEFAULT="$LOG_LEVEL_INFO"

# Color codes (if terminal supports)
readonly COLOR_RED='\033[0;31m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_CYAN='\033[0;36m'
readonly COLOR_NC='\033[0m' # No Color

# =============================================================================
# TIMEOUTS
# =============================================================================
readonly TIMEOUT_DOCKER_PULL=300      # 5 minutes
readonly TIMEOUT_DOCKER_START=60      # 1 minute
readonly TIMEOUT_DOCKER_STOP=30       # 30 seconds
readonly TIMEOUT_NPM_INSTALL=600      # 10 minutes

# =============================================================================
# VALIDATION
# =============================================================================
# Validate constants are set correctly
if [[ -z "$NODE_VERSION_REQUIRED" ]]; then
    echo "ERROR: NODE_VERSION_REQUIRED not set" >&2
    exit 1
fi

if [[ -z "$ELITE_REPO_URL" ]]; then
    echo "ERROR: ELITE_REPO_URL not set" >&2
    exit 1
fi

# Export for subprocess access
export NODE_VERSION_REQUIRED
export ELITE_LOCAL_PATH
export API_URL_LOCAL
export PORT_CONSOLE_DEV

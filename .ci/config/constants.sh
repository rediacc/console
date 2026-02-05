#!/bin/bash
# Console development constants
# Single source of truth for all configuration

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
# PATHS (must be defined early, used by other sections)
# =============================================================================
readonly CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
readonly CI_DIR="$CONSOLE_ROOT_DIR/.ci"
readonly CI_SCRIPTS_DIR="$CI_DIR/scripts"
readonly CI_LIB_DIR="$CI_DIR/lib"
readonly CI_CONFIG_DIR="$CI_DIR/config"

# =============================================================================
# DOCKER REGISTRY CONFIGURATION
# =============================================================================
# DOCKER_REGISTRY can be overridden by .env for local development
DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/rediacc/elite}"
DOCKER_TAG="${DOCKER_TAG:-latest}"

# Supported architectures for multi-arch builds
readonly SUPPORTED_ARCHS=("amd64" "arm64")

# Docker Images
readonly ELITE_IMAGE_WEB="${DOCKER_REGISTRY}/web:${DOCKER_TAG}"
readonly ELITE_IMAGE_API="${DOCKER_REGISTRY}/api:${DOCKER_TAG}"
readonly ELITE_IMAGE_BRIDGE="${DOCKER_REGISTRY}/bridge:${DOCKER_TAG}"
readonly ELITE_IMAGE_SQL="mcr.microsoft.com/mssql/server:2022-CU21-ubuntu-22.04"
readonly ELITE_IMAGE_SQL_ARM64="mcr.microsoft.com/azure-sql-edge:1.0.7"

# Docker Networks
readonly DOCKER_NETWORK_INTERNET="rediacc_internet"
readonly DOCKER_NETWORK_INTRANET="rediacc_intranet"

# =============================================================================
# BACKEND CONFIGURATION (self-contained docker-compose)
# =============================================================================
readonly CI_DOCKER_DIR="${CONSOLE_ROOT_DIR}/.ci/docker/ci"
readonly CI_COMPOSE_FILE="${CI_DOCKER_DIR}/docker-compose.yml"

# Container Names
readonly CI_CONTAINER_WEB="rediacc-web"
readonly CI_CONTAINER_API="rediacc-api"
readonly CI_CONTAINER_SQL="rediacc-sql"

# Backend state file
readonly BACKEND_STATE_FILE="$CONSOLE_ROOT_DIR/.backend-state"

# Default System Configuration (can be overridden by .env)
SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-admin@rediacc.io}"
SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
SYSTEM_ORGANIZATION_NAME="${SYSTEM_ORGANIZATION_NAME:-Default Organization}"
SYSTEM_DEFAULT_BRIDGE_NAME="${SYSTEM_DEFAULT_BRIDGE_NAME:-Global Bridges}"
SYSTEM_DEFAULT_REGION_NAME="${SYSTEM_DEFAULT_REGION_NAME:-Default Region}"
SYSTEM_DEFAULT_TEAM_NAME="${SYSTEM_DEFAULT_TEAM_NAME:-Private Team}"

# =============================================================================
# API CONFIGURATION
# =============================================================================
readonly API_URL_LOCAL="http://localhost/api"
readonly API_URL_SANDBOX="https://sandbox.rediacc.com/api"
readonly API_HEALTH_ENDPOINT="/health"
readonly API_HEALTH_TIMEOUT=120 # seconds
readonly API_HEALTH_INTERVAL=2  # seconds between retries

# =============================================================================
# BACKEND PRESETS (for --backend parameter)
# =============================================================================
readonly BACKEND_PRESET_LOCAL="http://localhost:7322"
readonly BACKEND_PRESET_SANDBOX="https://sandbox.rediacc.com"

# =============================================================================
# PORTS
# =============================================================================
readonly PORT_WEB=80
readonly PORT_WEB_HTTPS=443
readonly PORT_SQL=1433
readonly PORT_CONSOLE_DEV=3000

# =============================================================================
# BUILD CONFIGURATION
# =============================================================================
readonly BUILD_TYPE_DEBUG="DEBUG"
readonly BUILD_TYPE_RELEASE="RELEASE"
readonly BUILD_TYPE_DEFAULT="$BUILD_TYPE_DEBUG"

# Docker build args
readonly DOCKER_BUILD_ARG_NODE_VERSION="NODE_VERSION=$NODE_VERSION_REQUIRED"

# =============================================================================
# PUBLISHING CONFIGURATION
# =============================================================================
PUBLISH_DOCKER_REGISTRY="${PUBLISH_DOCKER_REGISTRY:-ghcr.io/rediacc/elite}"

# Bot identity for CI commits
readonly PUBLISH_BOT_NAME="github-actions[bot]"
readonly PUBLISH_BOT_EMAIL="github-actions[bot]@users.noreply.github.com"

# Docker images to publish
readonly PUBLISH_IMAGES=("api" "bridge" "plugin-terminal" "plugin-browser" "web" "cli")

# Dockerfiles (relative to CONSOLE_ROOT_DIR)
# Associative arrays require bash 4+; skip on older bash (e.g. macOS system bash 3.2).
# These are only used by Docker build scripts which run on Linux.
if ((BASH_VERSINFO[0] >= 4)); then
    declare -A DOCKERFILES=(
        ["api"]="private/middleware/Dockerfile"
        ["bridge"]="private/renet/Dockerfile"
        ["plugin-terminal"]="packages/plugins/terminal/Dockerfile"
        ["plugin-browser"]="packages/plugins/browser/Dockerfile"
        ["web"]="Dockerfile"
        ["cli"]="packages/cli/Dockerfile"
    )

    # Build contexts (relative to CONSOLE_ROOT_DIR)
    declare -A BUILD_CONTEXTS=(
        ["api"]="private/middleware"
        ["bridge"]="private/renet"
        ["plugin-terminal"]="packages/plugins/terminal"
        ["plugin-browser"]="packages/plugins/browser"
        ["web"]="."
        ["cli"]="."
    )
fi

# Version files to update (relative to CONSOLE_ROOT_DIR)
readonly VERSION_FILES_JSON=(
    "package.json"
    "packages/cli/package.json"
    "packages/shared/package.json"
    "packages/shared-desktop/package.json"
    "packages/web/package.json"
    "packages/desktop/package.json"
    "packages/e2e/package.json"
    "packages/bridge-tests/package.json"
    "packages/www/package.json"
    "packages/json/package.json"
)
readonly VERSION_FILE_TS="packages/cli/src/version.ts"
readonly VERSION_FILE_GO="private/renet/cmd/renet/version.go"
readonly VERSION_FILE_CSPROJ="private/middleware/middleware.csproj"

# =============================================================================
# PACKAGE REPOSITORY CONFIGURATION
# =============================================================================
readonly PKG_NAME="rediacc-cli"
readonly PKG_BINARY_NAME="rdc"
readonly PKG_INSTALL_PATH="/usr/local/bin/rdc"
readonly PKG_MAINTAINER="Rediacc <info@rediacc.com>"
readonly PKG_DESCRIPTION="Rediacc CLI - automation and scripting tool"
readonly PKG_HOMEPAGE="https://www.rediacc.com"
readonly PKG_SECTION="utils"
readonly PKG_PRIORITY="optional"
readonly PKG_MAX_VERSIONS=3
readonly PKG_RELEASE_REPO="rediacc/console"

# Homebrew tap configuration
readonly HOMEBREW_TAP_REPO="rediacc/homebrew-tap"
readonly HOMEBREW_FORMULA_PATH="Formula/rediacc-cli.rb"

# =============================================================================
# SQL CONFIGURATION
# =============================================================================
readonly SQL_SA_USER="sa"
readonly SQL_RA_USER_PREFIX="rediacc"
readonly SQL_DATABASE_PREFIX="RediaccMiddleware"

# =============================================================================
# LOGGING
# =============================================================================
readonly LOG_LEVEL_DEBUG="debug"
readonly LOG_LEVEL_INFO="info"
readonly LOG_LEVEL_WARN="warn"
readonly LOG_LEVEL_ERROR="error"
readonly LOG_LEVEL_DEFAULT="$LOG_LEVEL_INFO"

# Color codes
readonly COLOR_RED='\033[0;31m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_CYAN='\033[0;36m'
readonly COLOR_NC='\033[0m'

# =============================================================================
# DESKTOP ENVIRONMENT
# =============================================================================
readonly DESKTOP_DISPLAY_NUM="${DESKTOP_DISPLAY:-99}"
readonly DESKTOP_VNC_PORT="${DESKTOP_VNC_PORT:-5999}"
readonly DESKTOP_NOVNC_PORT="${DESKTOP_NOVNC_PORT:-6080}"
readonly DESKTOP_GATEWAY_PORT="${DESKTOP_GATEWAY_PORT:-8080}"
readonly DESKTOP_RESOLUTION="${DESKTOP_RESOLUTION:-1600x900}"

# =============================================================================
# TIMEOUTS
# =============================================================================
readonly TIMEOUT_DOCKER_PULL=300 # 5 minutes
readonly TIMEOUT_DOCKER_START=60 # 1 minute
readonly TIMEOUT_DOCKER_STOP=30  # 30 seconds
readonly TIMEOUT_NPM_INSTALL=600 # 10 minutes

# =============================================================================
# VALIDATION
# =============================================================================
if [[ -z "$NODE_VERSION_REQUIRED" ]]; then
    echo "ERROR: NODE_VERSION_REQUIRED not set" >&2
    exit 1
fi

# Export for subprocess access
export NODE_VERSION_REQUIRED
export API_URL_LOCAL
export PORT_CONSOLE_DEV

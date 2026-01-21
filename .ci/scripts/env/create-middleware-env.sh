#!/bin/bash
# Setup middleware test environment variables
#
# Usage: source .ci/scripts/env/create-middleware-env.sh
#
# This script is designed to be sourced, not executed.
# It exports environment variables with defaults that can be overridden
# by existing environment variables.
#
# Example:
#   source .ci/scripts/env/create-middleware-env.sh
#   echo $REDIACC_DATABASE_NAME  # RediaccMiddleware_test

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# SQL Server configuration
export SQL_SERVER="${SQL_SERVER:-localhost}"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-TestPassword123!}"
export MSSQL_RA_PASSWORD="${MSSQL_RA_PASSWORD:-TestPassword123!}"

# Database configuration
export REDIACC_DATABASE_NAME="${REDIACC_DATABASE_NAME:-RediaccMiddleware_test}"
export REDIACC_SQL_USERNAME="${REDIACC_SQL_USERNAME:-rediacc_test}"
export INSTANCE_NAME="${INSTANCE_NAME:-test}"
export SCRIPTS_DIR="${SCRIPTS_DIR:-scripts}"
export CONNECTION_STRING="${CONNECTION_STRING:-Server=localhost;Database=RediaccMiddleware_test;User Id=sa;Password=TestPassword123!;TrustServerCertificate=True}"

# System defaults
export SYSTEM_ORGANIZATION_NAME="${SYSTEM_ORGANIZATION_NAME:-Test Organization}"
export SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-admin@rediacc.io}"
export SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
export SYSTEM_DEFAULT_TEAM_NAME="${SYSTEM_DEFAULT_TEAM_NAME:-Private Team}"
export SYSTEM_DEFAULT_REGION_NAME="${SYSTEM_DEFAULT_REGION_NAME:-Default Region}"
export SYSTEM_DEFAULT_BRIDGE_NAME="${SYSTEM_DEFAULT_BRIDGE_NAME:-Global Bridges}"

log_info "Middleware test environment configured"

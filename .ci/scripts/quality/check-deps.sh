#!/bin/bash
# Check that all dependencies are up-to-date
#
# Usage:
#   .ci/scripts/quality/check-deps.sh
#
# Exit codes:
#   0 - All dependencies are up-to-date (or allowlisted)
#   1 - Outdated dependencies found

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

log_step "Checking dependency versions"
npx tsx "$REPO_ROOT/scripts/check-deps.ts"

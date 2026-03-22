#!/bin/bash
# Run tutorial player release-gate checks with agent-browser
# Usage:
#   .ci/scripts/test/run-www-player.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

require_cmd node
require_cmd npm
require_cmd agent-browser

log_step "Running tutorial player release gate..."
if npm run test:tutorial-player -w @rediacc/www; then
    log_info "Tutorial player release gate passed"
else
    log_error "Tutorial player release gate failed"
    exit 1
fi

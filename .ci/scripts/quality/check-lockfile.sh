#!/bin/bash
# Validate package-lock.json against supply-chain tampering.
# Usage: check-lockfile.sh
#
# Catches:
#   - resolved URLs pointing anywhere other than registry.npmjs.org (registry-confusion attack)
#   - non-HTTPS resolved URLs (downgrade)
#   - missing integrity hashes (poisoned entries)
#   - package-name mismatches between key and resolved tarball
#
# Run via: npm run check:ci-lockfile

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

log_step "Validating package-lock.json integrity..."

if [[ ! -f package-lock.json ]]; then
    log_error "package-lock.json is missing"
    exit 1
fi

npx --no-install lockfile-lint \
    --path package-lock.json \
    --type npm \
    --validate-https \
    --allowed-hosts npm \
    --validate-package-names \
    --validate-integrity

log_info "package-lock.json is clean"

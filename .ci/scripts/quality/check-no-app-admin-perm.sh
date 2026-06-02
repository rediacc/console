#!/bin/bash
# Assert that no workflow or composite action ever requests the
# `administration` permission on a `create-github-app-token` call.
#
# Per https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps
# `Administration: write` is the GitHub App permission that gates env CRUD
# (DELETE /repos/{owner}/{repo}/environments/{name}, deployment-branch-policies,
# deployment_protection_rules). The rediacc-ci-cd App is deliberately not
# granted this permission so a leaked App token cannot delete edge/stable.
#
# This gate fails loudly if any future workflow author tries to bypass that
# constraint by adding `permission-administration: write` (or read) to a
# create-github-app-token invocation. Adding the input would silently start
# requesting a permission the App may grant in the future, re-opening the
# blast-radius hole this audit closed.
#
# Usage: check-no-app-admin-perm.sh
#
# Exits 0 on clean, 1 on hit.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

log_step "Checking for permission-administration in workflows/actions..."

if grep -rn "permission-administration" .github/workflows/ .github/actions/ 2>/dev/null; then
    log_error "Found permission-administration request above."
    log_error "The rediacc-ci-cd App must not be granted administration:write."
    log_error "See CLAUDE.md \"App permission policy\" for rationale."
    exit 1
fi

log_info "OK: no permission-administration requests found."

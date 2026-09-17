#!/bin/bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-app-admin-perm is now registered to the Python port's entry point,
# .ci/scripts/quality/check_no_app_admin_perm.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs "...check_no_app_admin_perm.py" but its header derives "...check-no-app-admin-perm.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

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

# THIS GATE FAILED OPEN, and it did so while PRINTING the violation it missed.
#
# `grep` exits 2 when an operand does not exist, and it does that even when it
# found matches in the operands that DO exist. `if grep ...; then` reads any
# non-zero as "no match", so with `.github/actions/` absent the gate printed
#   .github/workflows/ci.yml:7:  permission-administration: write
# to stdout and then announced "OK: no permission-administration requests
# found" and exited 0. Reproduced 2026-09-06 under both ugrep and GNU grep, so
# it is not an implementation quirk. It was latent only because both directories
# happen to exist today: rename or delete either and this security gate is green
# forever, which is the exact shape it exists to prevent in others.
#
# Two changes. The scan directories are checked FIRST, because a missing operand
# means the gate cannot see its whole subject and must refuse rather than rule.
# And the grep exit is read as three outcomes, not two: 0 found, 1 clean,
# anything else an ERROR.
SCAN_DIRS=(.github/workflows .github/actions)
require_input -d 'cannot scan {}: it does not exist, so this gate would rule on part of its subject.' \
    'A partial scan that reports OK is worse than no scan. Refusing.' \
    "${SCAN_DIRS[@]}"

# `set -e` KILLS AN ASSIGNMENT whose command substitution exits non-zero, and
# grep exits 1 on the CLEAN case, so the guard below was never reached: the
# script died silently at this line on every green tree. Disarmed around the
# capture only, because the whole point here is to READ the exit code rather
# than let the shell act on it.
set +e
hits="$(grep -rn "permission-administration" "${SCAN_DIRS[@]}" 2>&1)"
rc=$?
set -e
if ((rc > 1)); then
    log_error "grep exited $rc while scanning ${SCAN_DIRS[*]}, so this gate read an incomplete corpus:"
    printf '%s\n' "$hits" >&2
    exit 1
fi
if ((rc == 0)); then
    printf '%s\n' "$hits"
    log_error "Found permission-administration request above."
    log_error "The rediacc-ci-cd App must not be granted administration:write."
    log_error "See CLAUDE.md \"App permission policy\" for rationale."
    exit 1
fi

log_info "OK: no permission-administration requests found."

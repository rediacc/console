#!/bin/bash
# Check that all renet functions have e2e-tests coverage
#
# Extracts all function names from RENET_FUNCTIONS in functions.generated.ts
# and verifies each one is exercised by the e2e-tests harness/suite under
# packages/e2e-tests.
#
# Coverage convention (a function `resource_verb` counts as covered when EITHER
# form appears anywhere in packages/e2e-tests .ts sources):
#   1. The raw queue-dispatch name as a string literal: 'resource_verb'
#      (this is how src/utils/bridge/methods/*.ts declare `function: 'name'`).
#   2. The CLI subcommand form with underscores as spaces: `resource verb`
#      (this is how the helpers shell out, e.g. `sudo renet repository fork ...`).
#
# This prevents adding new renet functions without corresponding e2e-tests.
#
# Usage:
#   .ci/scripts/quality/check-e2e-coverage.sh
#
# Exit codes:
#   0 - All (non-allowlisted) functions have e2e-tests coverage
#   1 - One or more functions are missing test coverage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

FUNCTIONS_FILE="$REPO_ROOT/packages/shared/src/renet-contract/data/functions.generated.ts"
E2E_TESTS_DIR="$REPO_ROOT/packages/e2e-tests"

# BLOCKER: legacy renet functions that predate the e2e-tests suite and
# are not yet exercised by it. The middleware-backed packages/cli/tests suite
# (which used to provide this coverage) was retired; migrating these into
# packages/e2e-tests is tracked follow-up work. NEW functions are still
# enforced — only names listed here are exempt, so the gate keeps catching
# untested additions. Remove a name here the moment its e2e-test lands.
ALLOWLIST=(
    backup_delete
    backup_list
    ceph_client_mount
    ceph_client_unmount
    ceph_clone_image
    container_remove
    repository_autostart_disable
    repository_autostart_disable_all
    repository_autostart_enable
    repository_autostart_enable_all
    repository_autostart_list
    repository_cat
    repository_commit_meta
    repository_diff
    repository_down_all
    repository_ownership
    repository_policy_get
    repository_policy_set
    repository_prune
    repository_template_apply
    repository_trim
    repository_up_all
)

# Validate required files exist
if [[ ! -f "$FUNCTIONS_FILE" ]]; then
    log_error "Functions file not found: $FUNCTIONS_FILE"
    exit 1
fi

if [[ ! -d "$E2E_TESTS_DIR" ]]; then
    log_error "e2e-tests directory not found: $E2E_TESTS_DIR"
    exit 1
fi

# Phase 1: Extract all renet function names from RENET_FUNCTIONS array
log_step "Extracting renet function names..."

# The RENET_FUNCTIONS array contains entries like:  'function_name',
# Extract names between single quotes
FUNCTIONS=()
IN_ARRAY=false
while IFS= read -r line; do
    # Detect start of RENET_FUNCTIONS array
    if [[ "$line" =~ RENET_FUNCTIONS[[:space:]]*=[[:space:]]*\[ ]]; then
        IN_ARRAY=true
        continue
    fi
    # Detect end of array
    if $IN_ARRAY && [[ "$line" =~ \][[:space:]]*as[[:space:]]+const ]]; then
        break
    fi
    # Extract function name from lines like:  'function_name',
    if $IN_ARRAY && [[ "$line" =~ \'([a-z_]+)\' ]]; then
        FUNCTIONS+=("${BASH_REMATCH[1]}")
    fi
done <"$FUNCTIONS_FILE"

TOTAL=${#FUNCTIONS[@]}
if [[ $TOTAL -eq 0 ]]; then
    log_error "No functions extracted from RENET_FUNCTIONS — parsing may be broken"
    exit 1
fi

log_info "Found $TOTAL renet functions in RENET_FUNCTIONS"

# Phase 2: Collect e2e-tests sources (harness + suite, excluding .d.ts)
log_step "Checking e2e-tests coverage..."

TEST_FILES=()
while IFS= read -r f; do
    [[ -f "$f" ]] && TEST_FILES+=("$f")
done < <(find "$E2E_TESTS_DIR/src" "$E2E_TESTS_DIR/tests" -name '*.ts' -not -name '*.d.ts' -type f 2>/dev/null)

if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
    log_error "No e2e-tests .ts files found under $E2E_TESTS_DIR"
    exit 1
fi

log_info "Scanning ${#TEST_FILES[@]} e2e-tests source files"

# Membership test for the allowlist
is_allowlisted() {
    local needle="$1"
    local item
    for item in "${ALLOWLIST[@]}"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

MISSING=()
for fn in "${FUNCTIONS[@]}"; do
    # Covered if the raw queue-dispatch name OR the CLI subcommand (space) form appears.
    if grep -Fql "$fn" "${TEST_FILES[@]}" 2>/dev/null; then
        continue
    fi
    if grep -Fql "${fn//_/ }" "${TEST_FILES[@]}" 2>/dev/null; then
        continue
    fi
    # Uncovered: only a failure if not on the legacy allowlist.
    is_allowlisted "$fn" && continue
    MISSING+=("$fn")
done

# Phase 3: THE REVERSE DIRECTION — does e2e dispatch a verb that no longer EXISTS?
#
# Phases 1-2 walk live -> e2e: "is every renet function exercised?" That is only half
# the contract, and the missing half is the one that bites. An e2e test calling a
# DELETED verb passed this gate in total silence — which is exactly how
# datastore_init/mount/unmount, datastore_ceph_{init,fork,unfork} and kube_csi_template
# outlived their own removal in P1 and only surfaced when the Tests + Infra tier finally
# ran (it is gated behind the upstream gates, so it had not executed once all campaign).
#
# The oracle is RENET_BRIDGE_FUNCTIONS: every name in the dispatcher's Registry —
# internal verbs included. RENET_FUNCTIONS above is the PUBLIC surface and omits them,
# and the bridge drives mostly internal verbs (datastore_*, machine_check_*, daemon_*),
# so it cannot answer this question. A schema-derived list cannot either: a verb may be
# registered WITHOUT a schema (ceph_clone_create is) and still dispatch fine.
log_step "Checking e2e-tests dispatch only verbs that still exist..."

BRIDGE_FUNCTIONS=()
IN_ARRAY=false
while IFS= read -r line; do
    if [[ "$line" =~ RENET_BRIDGE_FUNCTIONS[[:space:]]*=[[:space:]]*\[ ]]; then
        IN_ARRAY=true
        continue
    fi
    if $IN_ARRAY && [[ "$line" =~ \][[:space:]]*as[[:space:]]+const ]]; then
        break
    fi
    if $IN_ARRAY && [[ "$line" =~ \'([a-z0-9_]+)\' ]]; then
        BRIDGE_FUNCTIONS+=("${BASH_REMATCH[1]}")
    fi
done <"$FUNCTIONS_FILE"

if [[ ${#BRIDGE_FUNCTIONS[@]} -eq 0 ]]; then
    log_error "No functions extracted from RENET_BRIDGE_FUNCTIONS — parsing may be broken,"
    log_error "or the contract predates it. Regenerate:"
    log_error "  private/renet/bin/renet functions generate-types --output packages/shared/src/renet-contract/data --version dev"
    exit 1
fi
log_info "Found ${#BRIDGE_FUNCTIONS[@]} dispatchable verbs in RENET_BRIDGE_FUNCTIONS"

is_dispatchable() {
    local needle="$1"
    local item
    for item in "${BRIDGE_FUNCTIONS[@]}"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

# Every `function: 'name'` literal in the harness IS a dispatch — that is how
# src/utils/bridge/methods/*.ts name the verb they send to `functions once`.
DEAD=()
while IFS= read -r hit; do
    # grep -rn gives  <file>:<line>:<match>
    file="${hit%%:*}"
    rest="${hit#*:}"
    line="${rest%%:*}"
    verb="$(printf '%s' "$rest" | sed -E "s/.*function:[[:space:]]*'([a-z0-9_]+)'.*/\1/")"
    is_dispatchable "$verb" && continue
    DEAD+=("$verb  — ${file#"$REPO_ROOT"/}:$line")
done < <(grep -rn --include='*.ts' -E "function:[[:space:]]*'[a-z0-9_]+'" "$E2E_TESTS_DIR/src" "$E2E_TESTS_DIR/tests" 2>/dev/null || true)

if [[ ${#DEAD[@]} -gt 0 ]]; then
    log_error "e2e-tests dispatch ${#DEAD[@]} verb(s) that renet no longer registers:"
    log_error ""
    for d in "${DEAD[@]}"; do
        log_error "  - $d"
    done
    log_error ""
    log_error "These calls fail at RUNTIME with \"no command builder registered\". A renamed"
    log_error "verb means the test is stale by design: fix it FORWARD against the surviving"
    log_error "surface (see RENET_BRIDGE_FUNCTIONS), never restore the old name."
    exit 1
fi
log_info "All e2e-dispatched verbs exist in the renet registry"

# Phase 4: Report results
if [[ ${#MISSING[@]} -eq 0 ]]; then
    log_info "All enforced renet functions have e2e-tests coverage (${#ALLOWLIST[@]} legacy names allowlisted)"
    exit 0
fi

log_error "e2e-tests coverage gap: ${#MISSING[@]} function(s) missing coverage"
log_error ""
log_error "The following function(s) have no e2e-test under $E2E_TESTS_DIR:"
for fn in "${MISSING[@]}"; do
    log_error "  - $fn"
done
log_error ""
log_error "To fix: exercise the function in packages/e2e-tests. It counts as covered"
log_error "when the raw name appears as a string literal (e.g. a harness method's"
log_error "\`function: '${MISSING[0]}'\`) OR its CLI form '${MISSING[0]//_/ }' is invoked"
log_error "(e.g. \`sudo renet ${MISSING[0]//_/ } ...\`) in a harness/helper/test file."
exit 1

#!/bin/bash
# Check that all renet bridge functions have E2E test coverage
#
# Extracts all function names from BRIDGE_FUNCTIONS in functions.generated.ts
# and verifies each one appears in at least one E2E test file under 08-e2e/.
#
# This prevents adding new renet functions without corresponding E2E tests.
#
# Usage:
#   .ci/scripts/quality/check-e2e-coverage.sh
#
# Exit codes:
#   0 - All functions have E2E test coverage
#   1 - One or more functions are missing test coverage

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

FUNCTIONS_FILE="$REPO_ROOT/packages/shared/src/queue-vault/data/functions.generated.ts"
E2E_TEST_DIR="$REPO_ROOT/packages/cli/tests/tests/08-e2e"

# Validate required files exist
if [[ ! -f "$FUNCTIONS_FILE" ]]; then
    log_error "Functions file not found: $FUNCTIONS_FILE"
    exit 1
fi

if [[ ! -d "$E2E_TEST_DIR" ]]; then
    log_error "E2E test directory not found: $E2E_TEST_DIR"
    exit 1
fi

# Phase 1: Extract all bridge function names from BRIDGE_FUNCTIONS array
log_step "Extracting bridge function names..."

# The BRIDGE_FUNCTIONS array contains entries like:  'function_name',
# Extract names between single quotes
FUNCTIONS=()
IN_ARRAY=false
while IFS= read -r line; do
    # Detect start of BRIDGE_FUNCTIONS array
    if [[ "$line" =~ BRIDGE_FUNCTIONS[[:space:]]*=[[:space:]]*\[ ]]; then
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
    log_error "No functions extracted from BRIDGE_FUNCTIONS — parsing may be broken"
    exit 1
fi

log_info "Found $TOTAL bridge functions in BRIDGE_FUNCTIONS"

# Phase 2: Check each function appears in at least one E2E test file
log_step "Checking E2E test coverage..."

# Collect E2E test files (excluding 01-local-execution which tests CLI mechanics,
# not individual function coverage)
E2E_FILES=()
for f in "$E2E_TEST_DIR"/0[2-9]*.test.ts "$E2E_TEST_DIR"/[1-9]*.test.ts; do
    [[ -f "$f" ]] && E2E_FILES+=("$f")
done

if [[ ${#E2E_FILES[@]} -eq 0 ]]; then
    log_error "No E2E test files found matching 02-*.test.ts through 99-*.test.ts"
    exit 1
fi

log_info "Scanning ${#E2E_FILES[@]} E2E test files"

MISSING=()
for fn in "${FUNCTIONS[@]}"; do
    # Look for the function name as a string literal in test files
    # Matches: 'function_name' or "function_name" (in runLocalFunction calls, test descriptions, etc.)
    if ! grep -Eql "'${fn}'|\"${fn}\"" "${E2E_FILES[@]}" >/dev/null 2>&1; then
        MISSING+=("$fn")
    fi
done

# Phase 3: Report results
if [[ ${#MISSING[@]} -eq 0 ]]; then
    log_info "All $TOTAL bridge functions have E2E test coverage"
    exit 0
fi

COVERED=$((TOTAL - ${#MISSING[@]}))
log_error "E2E test coverage gap: $COVERED/$TOTAL functions covered"
log_error ""
log_error "The following ${#MISSING[@]} function(s) have no E2E test in $E2E_TEST_DIR:"
for fn in "${MISSING[@]}"; do
    log_error "  - $fn"
done
log_error ""
log_error "To fix: Add tests for the missing function(s) in packages/cli/tests/tests/08-e2e/"
log_error "Each function must appear as a string literal (e.g., in a runLocalFunction() call)"
log_error "in at least one test file numbered 02-*.test.ts or higher."
exit 1

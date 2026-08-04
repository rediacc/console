#!/bin/bash
# Check that renet's licence tier map still covers every registered function.
#
# Usage:
#   .ci/scripts/quality/check-renet-tier-map.sh
#
# Environment:
#   RENET_DIR - override the renet checkout under test (default: private/renet).
#               Used to point the gate at a scratch copy when proving it fires.
#
# Exit codes:
#   0 - the tier map covers the registry and drives dispatch
#   1 - a registered function has no tier, an entry names no function, the
#       dispatch path disagrees with the map, or the gate itself is unarmed
#
# WHY A LOCAL GATE
# ----------------
# These Go tests already run in CI (ct-tests.yml, job test-renet, step
# "Run renet tests"), but `npm run ci` had no leg for them, so a tier-map
# regression could only be found after a push. The CLI now DERIVES its
# licence-issuance class from this map through the generated contract
# (packages/shared/src/renet-contract/data/license-tiers.generated.ts, consumed
# by packages/cli/src/services/renet/renet-license-contract.ts), which makes the
# map's completeness a console-side correctness property, not only a renet one.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: shared log helpers and require_submodule used by every .ci/scripts gate
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
RENET_DIR="${RENET_DIR:-$REPO_ROOT/private/renet}"

cd "$REPO_ROOT"

# go.mod is the marker, not the directory: an uninitialised submodule leaves an
# EMPTY directory behind, and a gate that runs zero tests against it would
# report success while checking nothing.
require_submodule "$RENET_DIR/go.mod" "Renet submodule" || exit 0

# `auto` so private/renet/go.mod's toolchain directive stays the single source
# of truth, matching every sibling renet script.
export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"

# The tests this gate exists to run. Named individually rather than swept by a
# pattern so a RENAME is a loud failure here instead of a silent selection of
# zero tests: `go test -run` exits 0 with "no tests to run" when its regex
# matches nothing, which is the exact vacuity this repo keeps finding.
EXPECTED_TESTS=(
    TestTierMapCoversRegistry
    TestTierMapHasNoOrphans
    TestTierMapGateCanFail
    TestPendingBacklogIsReported
    TestTierMapDrivesDispatch
    TestOperateTierSurvivesExpiry
    TestTierProbeMatchesTheMap
)
RUN_REGEX='^(TestTierMap.*|TestTierProbeMatchesTheMap|TestOperateTierSurvivesExpiry|TestPendingBacklogIsReported)$'
TEST_PACKAGE="./pkg/functions/"

log_step "Checking the renet tier map covers the function registry..."

# Phase 1: instrument check. Confirm the regex selects exactly the expected set
# before trusting a green run of it.
LISTED="$(cd "$RENET_DIR" && go test -list "$RUN_REGEX" "$TEST_PACKAGE" | grep '^Test' | sort)"
WANTED="$(printf '%s\n' "${EXPECTED_TESTS[@]}" | sort)"
if [[ "$LISTED" != "$WANTED" ]]; then
    log_error "The tier-map test selection has drifted."
    log_error "  wanted:"
    printf '%s\n' "$WANTED" | sed 's/^/    /' >&2
    log_error "  selected by $RUN_REGEX:"
    printf '%s\n' "${LISTED:-<none>}" | sed 's/^/    /' >&2
    log_error "  Update EXPECTED_TESTS/RUN_REGEX in this gate, or restore the test names."
    exit 1
fi

# Phase 2: run them. -count=1 defeats the test cache, so a stale green from a
# previous tier map cannot be replayed.
log_step "Running ${#EXPECTED_TESTS[@]} tier-map tests in $TEST_PACKAGE..."
OUTPUT=""
RC=0
OUTPUT="$(cd "$RENET_DIR" && go test -count=1 -v -run "$RUN_REGEX" "$TEST_PACKAGE" 2>&1)" || RC=$?
if [[ "$RC" -ne 0 ]]; then
    printf '%s\n' "$OUTPUT" >&2
    log_error "Renet tier-map tests failed."
    log_error "  A registered function with no tier entry means renet cannot decide whether"
    log_error "  it needs a licence, and the CLI's generated contract inherits that gap."
    log_error "  Fix private/renet/pkg/license/tiermap.go, then: ./run.sh deploy prep"
    exit 1
fi

# Phase 3: a green exit is not enough. Assert each expected test actually
# reported PASS, so a build tag or a t.Skip cannot retire one silently.
MISSING=()
for test_name in "${EXPECTED_TESTS[@]}"; do
    printf '%s\n' "$OUTPUT" | grep -q -- "--- PASS: $test_name" || MISSING+=("$test_name")
done
if [[ "${#MISSING[@]}" -gt 0 ]]; then
    printf '%s\n' "$OUTPUT" >&2
    log_error "These tier-map tests never reported PASS: ${MISSING[*]}"
    log_error "  They were selected but did not run (skipped, or excluded by a build tag)."
    exit 1
fi

log_info "Renet tier map covers the registry (${#EXPECTED_TESTS[@]} tests passed)"

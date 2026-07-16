#!/bin/bash
# Run the root-tagged renet repository state tests.
#
# TestSaveState_SetsOwnership / _OwnershipMatchesMountDir / TestLoadState_
# PreservesData are `//go:build root` and t.Fatal (not skip) off-root, so under
# sudo they must run and PASS. Compiled by `go vet -tags root`, executed here.
#
# Requires: root (run under sudo), `go` on PATH. No env vars.
#
# Local run (from repo root):
#   sudo env "PATH=$PATH" .ci/scripts/private/renet-root-tests.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
cd "$(get_repo_root)/private/renet"

ROOT_TESTS='TestSaveState_SetsOwnership|TestSaveState_OwnershipMatchesMountDir|TestLoadState_PreservesData'

log_step "Running root-tagged repository tests..."
out="$(go test -tags root -run "$ROOT_TESTS" ./pkg/repository/ -v -count=1 -timeout 300s 2>&1)" || {
    echo "$out"
    exit 1
}
echo "$out"

# Loud guard: each named root test must actually PASS (t.Fatal off-root, so a
# non-root run would have already failed rather than silently skipped).
for t in TestSaveState_SetsOwnership TestSaveState_OwnershipMatchesMountDir TestLoadState_PreservesData; do
    if ! echo "$out" | grep -q -- "--- PASS: $t"; then
        echo "::error::$t did not PASS (root-tagged repository test)"
        exit 1
    fi
done
log_info "Root-tagged repository tests passed"

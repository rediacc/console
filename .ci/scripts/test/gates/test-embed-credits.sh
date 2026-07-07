#!/bin/bash
# Integration test for scripts/check-embed-credits.ts.
#
# Verifies the gate accepts the real in-tree inventories and rejects a
# version mismatch and a missing embedded-component entry, using the gate's
# EMBED_CREDITS_* path overrides to point at fixtures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR="$REPO_ROOT/scripts/check-embed-credits.ts"

FIXTURE_DIR=""
setup_fixtures() {
    FIXTURE_DIR="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture FIXTURE_DIR at trap-set time so EXIT removes this exact path
    trap "rm -rf '$FIXTURE_DIR'" EXIT

    # credits.go fixture with a deliberately wrong rclone version.
    cat >"$FIXTURE_DIR/bad-credits.go" <<'EOF'
package embed

var credits = []Credit{
	{Asset: AssetCRIU, Name: "CRIU", Version: "4.2"},
	{Asset: AssetRsync, Name: "rsync", Version: "3.4.1"},
	{Asset: AssetRclone, Name: "rclone", Version: "9.9.9"},
}
EOF

    # JSON fixture missing the rsync embedded component.
    cat >"$FIXTURE_DIR/missing.json" <<'EOF'
{
  "components": [
    { "asset": "criu", "name": "CRIU", "version": "4.2" },
    { "asset": "rclone", "name": "rclone", "version": "1.73.0" }
  ]
}
EOF
}

test_accepts_real_inventories() {
    cd "$REPO_ROOT"
    if ! npx tsx "$VALIDATOR" >/dev/null 2>&1; then
        log_fail "real in-tree inventories should pass the embed-credits gate"
    fi
    log_pass "real inventories pass validation"
}

test_rejects_version_mismatch() {
    local out rc=0
    out=$(cd "$REPO_ROOT" && EMBED_CREDITS_CREDITS_GO="$FIXTURE_DIR/bad-credits.go" \
        npx tsx "$VALIDATOR" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "a credits.go version mismatch should fail"
    assert_contains "$out" "rclone" "error names the mismatched component"
    log_pass "version mismatch is rejected"
}

test_rejects_missing_entry() {
    local out rc=0
    out=$(cd "$REPO_ROOT" && EMBED_CREDITS_JSON="$FIXTURE_DIR/missing.json" \
        npx tsx "$VALIDATOR" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "a JSON inventory missing an embedded component should fail"
    assert_contains "$out" "missing entry for embedded component 'rsync'" "error names the missing component"
    log_pass "missing embedded-component entry is rejected"
}

log_test "test-embed-credits"
setup_fixtures
test_accepts_real_inventories
test_rejects_version_mismatch
test_rejects_missing_entry
echo ""
log_pass "all tests passed"

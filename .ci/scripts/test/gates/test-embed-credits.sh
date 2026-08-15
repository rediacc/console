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

# Every assertion (including the fixture-override ones) reads the real
# Dockerfile + embed.go from the submodule; without it there is nothing to
# test. The gate itself runs in the Renet quality job, which has submodules.
if [[ ! -f "$REPO_ROOT/private/renet/Dockerfile" ]]; then
    echo "renet submodule not present -- skipping embed-credits gate test"
    exit 0
fi

FIXTURE_DIR=""
setup_fixtures() {
    FIXTURE_DIR="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture FIXTURE_DIR at trap-set time so EXIT removes this exact path
    trap "rm -rf '$FIXTURE_DIR'" EXIT

    # credits.go fixture with a deliberately wrong zot version.
    # (Was rclone until 2026-08-15, when rclone left the embed entirely. The
    # fixture was rewritten onto a SURVIVING asset rather than deleted: a
    # control that no longer names a real asset stops proving anything.)
    cat >"$FIXTURE_DIR/bad-credits.go" <<'EOF'
package embed

var credits = []Credit{
	{Asset: AssetCRIU, Name: "CRIU", Version: "4.2"},
	{Asset: AssetRsync, Name: "rsync", Version: "3.4.1"},
	{Asset: AssetZot, Name: "zot", Version: "9.9.9"},
}
EOF

    # JSON fixture missing the rsync embedded component.
    cat >"$FIXTURE_DIR/missing.json" <<'EOF'
{
  "components": [
    { "asset": "criu", "name": "CRIU", "version": "4.2" },
    { "asset": "zot", "name": "zot", "version": "2.1.2" }
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

test_rejects_dockerfile_pin_drift() {
    # The Dockerfile keeps its own ARG defaults so `docker build` works standalone.
    # This is the check that stops those defaults drifting from the lockfile.
    local TEMP out rc=0
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time so RETURN removes this exact dir
    trap "rm -rf '$TEMP'" RETURN
    sed 's/^ARG CRIU_VERSION=.*/ARG CRIU_VERSION=9.9.9/' \
        "$REPO_ROOT/private/renet/Dockerfile" >"$TEMP/Dockerfile"
    out=$(cd "$REPO_ROOT" && EMBED_CREDITS_DOCKERFILE="$TEMP/Dockerfile" \
        npx tsx scripts/check-embed-credits.ts 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "a Dockerfile pin drifting from the lockfile should fail"
    assert_contains "$out" "CRIU_VERSION" "error names the drifted ARG"
    log_pass "a Dockerfile pin that drifts from the lockfile is rejected"
}

test_rejects_stale_generated_artifact() {
    # The attribution artifacts are generated from the lockfile; a hand-edit or a
    # forgotten regenerate must be caught rather than silently shipped.
    local TEMP out rc=0
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time so RETURN removes this exact dir
    trap "rm -rf '$TEMP'" RETURN
    cp "$REPO_ROOT/private/renet/pkg/embed/credits_data.go" "$TEMP/credits_data.go"
    printf '\n// hand-edited\n' >>"$TEMP/credits_data.go"
    out=$(cd "$REPO_ROOT" && EMBED_CREDITS_GO_FILE="$TEMP/credits_data.go" \
        npx tsx scripts/check-embed-credits.ts 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "a stale generated artifact should fail"
    assert_contains "$out" "stale" "error says the artifact is stale"
    log_pass "a stale generated attribution artifact is rejected"
}

log_test "test-embed-credits"
setup_fixtures
test_accepts_real_inventories
test_rejects_dockerfile_pin_drift
test_rejects_stale_generated_artifact
echo ""
log_pass "all tests passed"

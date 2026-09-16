#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: node, submodules
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# Integration test for scripts/gates/check-embed-asset-freshness.ts.
#
# Drives the gate through EMBED_FRESHNESS_FIXTURE (a JSON map of base -> latest
# version/date used instead of the network), so it runs offline and
# deterministically. Proves: it passes when nothing is behind, FIRES on a stale
# pin, DEFERS a just-released version (the shared soak), and FAILS SOFT when a
# source can't be checked.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR="$REPO_ROOT/scripts/gates/check-embed-asset-freshness.ts"

# The gate reads the real Dockerfile pins from the renet submodule; without it
# there is nothing to compare against.
if [[ ! -f "$REPO_ROOT/private/renet/Dockerfile" ]]; then
    echo "renet submodule not present -- skipping embed-asset-freshness gate test"
    exit 0
fi

FIXTURE_DIR=""
setup_fixtures() {
    FIXTURE_DIR="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture FIXTURE_DIR at trap-set time so EXIT removes this exact path
    trap "rm -rf '$FIXTURE_DIR'" EXIT

    # Everything reported far OLDER than any real pin -> nothing is stale.
    cat >"$FIXTURE_DIR/all-current.json" <<'EOF'
{
  "criu": { "version": "0.0.1" }, "rsync": { "version": "0.0.1" },
  "zot": { "version": "0.0.1" },
  "k3s": { "version": "0.0.1" }, "csiprovisioner": { "version": "0.0.1" },
  "csisnapshotter": { "version": "0.0.1" }, "snapshotcontroller": { "version": "0.0.1" }
}
EOF

    # k3s reported far NEWER, published long ago -> confirmed stale (past soak).
    cat >"$FIXTURE_DIR/stale.json" <<'EOF'
{
  "criu": { "version": "0.0.1" }, "rsync": { "version": "0.0.1" },
  "zot": { "version": "0.0.1" },
  "k3s": { "version": "9999.0.0", "publishedAt": "2020-01-01T00:00:00Z" },
  "csiprovisioner": { "version": "0.0.1" }, "csisnapshotter": { "version": "0.0.1" },
  "snapshotcontroller": { "version": "0.0.1" }
}
EOF

    # k3s newer but published just now -> within the freshness window (deferred).
    local recent
    recent="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null ||
        date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)"
    cat >"$FIXTURE_DIR/fresh.json" <<EOF
{
  "criu": { "version": "0.0.1" }, "rsync": { "version": "0.0.1" },
  "zot": { "version": "0.0.1" },
  "k3s": { "version": "9999.0.0", "publishedAt": "$recent" },
  "csiprovisioner": { "version": "0.0.1" }, "csisnapshotter": { "version": "0.0.1" },
  "snapshotcontroller": { "version": "0.0.1" }
}
EOF

    # Empty fixture -> every source "not in fixture" -> could-not-check (fail soft).
    echo '{}' >"$FIXTURE_DIR/empty.json"

    # AN EMPTY BLOCKLIST for the upstream-map controls below, so they test the
    # GATE rather than whatever the repository's live policy happens to hold.
    # Without it `run_gate` read `.ci/policy/.embed-assets-upgrade-blocklist`,
    # and every one of those controls plants its staleness on k3s -- so the day
    # k3s was first held (2026-09-16, branch 0914-1) `test_fires_when_stale`
    # reported "a pin behind upstream should fail: expected 1, got 0". The
    # control had been passing only because production policy happened to be
    # empty, which is a control coupled to a decision it does not own.
    printf '# no holds; this fixture exists so the controls do not read live policy\n' \
        >"$FIXTURE_DIR/blocklist-empty"

    # A blocklist entry with NO BLOCKER reason -> verifyAllBlockers must reject it.
    printf 'criu\n' >"$FIXTURE_DIR/blocklist-bad"

    # A blocklist entry WITH a substantive BLOCKER reason -> accepted, no error.
    printf '# BLOCKER: upstream criu 4.3 regressed cgroup-v2 restore; holding at 4.2 until fixed\ncriu\n' \
        >"$FIXTURE_DIR/blocklist-good"
}

run_gate() { # <fixture-file> -> stdout+stderr, returns gate exit code
    # THE BLOCKLIST IS PINNED TO AN EMPTY FIXTURE, not inherited from the repo.
    # See blocklist-empty above: these controls plant their staleness on k3s, and
    # a real hold on k3s silently turned the staleness control into a no-op.
    (cd "$REPO_ROOT" &&
        EMBED_FRESHNESS_FIXTURE="$FIXTURE_DIR/$1" \
            EMBED_BLOCKLIST_FILE="$FIXTURE_DIR/blocklist-empty" \
            npx tsx "$VALIDATOR" 2>&1)
}

# Runs the gate with a fixture upstream map AND a fixture blocklist, so the
# blocklist's BLOCKER validation can be exercised in isolation from the network.
# $1 = freshness fixture file, $2 = blocklist fixture file
run_gate_blocklist() {
    (cd "$REPO_ROOT" &&
        EMBED_FRESHNESS_FIXTURE="$FIXTURE_DIR/$1" \
            EMBED_BLOCKLIST_FILE="$FIXTURE_DIR/$2" \
            npx tsx "$VALIDATOR" 2>&1)
}

test_passes_when_current() {
    local out rc=0
    out=$(run_gate all-current.json) || rc=$?
    assert_exit_code 0 "$rc" "nothing behind upstream should pass"
    log_pass "current pins pass"
}

test_fires_when_stale() {
    local out rc=0
    out=$(run_gate stale.json) || rc=$?
    assert_exit_code 1 "$rc" "a pin behind upstream should fail"
    assert_contains "$out" "k3s" "error names the stale component"
    assert_contains "$out" "--upgrade" "red output gives the --upgrade fix"
    log_pass "stale pin fires"
}

test_defers_fresh_release() {
    local out rc=0
    out=$(run_gate fresh.json) || rc=$?
    assert_exit_code 0 "$rc" "a just-released upstream version should be deferred, not failed"
    assert_contains "$out" "deferred" "fresh release is reported as deferred (soak)"
    log_pass "fresh release is deferred by the soak"
}

test_fails_soft_when_uncheckable() {
    local out rc=0
    out=$(run_gate empty.json) || rc=$?
    assert_exit_code 0 "$rc" "sources that cannot be checked must not fail the build"
    log_pass "uncheckable sources fail soft"
}

# The blocklist is a BLOCKER-gated suppression list; a bare entry with no
# substantive reason must fail the gate, not silently hold the pin.
test_blocklist_rejects_missing_reason() {
    local out rc=0
    out=$(run_gate_blocklist all-current.json blocklist-bad) || rc=$?
    assert_exit_code 1 "$rc" "a blocklist entry lacking a BLOCKER reason must fail the gate"
    assert_contains "$out" "invalid entries" "error names the malformed blocklist"
    log_pass "blocklist entry without a BLOCKER reason fires"
}

# A properly-reasoned blocklist entry is accepted (freshness itself passes here).
test_blocklist_accepts_valid_reason() {
    local out rc=0
    out=$(run_gate_blocklist all-current.json blocklist-good) || rc=$?
    assert_exit_code 0 "$rc" "a blocklist entry with a substantive BLOCKER reason must be accepted"
    log_pass "well-formed blocklist entry is accepted"
}

log_test "test-embed-asset-freshness"
setup_fixtures
test_passes_when_current
test_fires_when_stale
test_defers_fresh_release
test_fails_soft_when_uncheckable
test_blocklist_rejects_missing_reason
test_blocklist_accepts_valid_reason
echo ""
log_pass "all tests passed"

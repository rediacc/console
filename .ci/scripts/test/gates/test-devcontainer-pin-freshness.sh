#!/bin/bash
# Integration test for scripts/check-devcontainer-pin-freshness.ts.
#
# Drives the gate through DEVCONTAINER_FRESHNESS_FIXTURE (a JSON map of base ->
# latest version/date/digests used instead of the network), so it runs offline
# and deterministically. Proves: it passes when nothing is behind, FIRES on a
# stale pin, DEFERS a just-released version (the shared soak), FAILS SOFT when a
# source cannot be checked, and enforces the BLOCKER convention on its blocklist.
#
# Plus one assertion the embed gate's test has no reason to make: --upgrade must
# move the VERSION and its sha256 ARGs TOGETHER, and must refuse to move the
# version at all when a digest is missing. A tree carrying a new version beside a
# stale hash does not build, so an upgrade path that can produce one is worse
# than no upgrade path -- that is the whole reason this gate rewrites hashes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR="$REPO_ROOT/scripts/check-devcontainer-pin-freshness.ts"
DOCKERFILE="$REPO_ROOT/.devcontainer/Dockerfile"

# The real digests of bw-linux-2026.8.0.zip / bw-linux-arm64-2026.8.0.zip, used
# by the --upgrade cases so a passing test also re-proves the pins in the tree.
BW_SHA_AMD64="367f618e9fcccaac4980ec12c7bafd01df739b5f3cb1af31bc9045cf75eea1d6"
BW_SHA_ARM64="74d822a5dceda5896ed8fc07bc61925b29afd98d96a6a3e9e525ae556c3083a8"

FIXTURE_DIR=""
setup_fixtures() {
    FIXTURE_DIR="$(mktemp -d)"
    # THE REAL DOCKERFILE IS NEVER TOUCHED, and that is a correction rather than a
    # tidy-up. This block used to copy the tracked file aside, let --upgrade rewrite
    # it IN PLACE, and restore it from the EXIT trap. The restore was correct as far
    # as it went -- log_fail exits immediately, so a restore after the call is
    # skipped by exactly the runs that need it -- but the mutation itself is the
    # problem: it is visible to every other gate sharing the tree. On 2026-09-03 it
    # reddened check:ci-setup-idempotency in the pre-push lane, which reported
    # "setup --check changed the working tree" over `.devcontainer/Dockerfile`, a
    # file run.sh never writes. And this tree usually holds another session's
    # uncommitted work.
    #
    # So the gate now takes a Dockerfile PATH (DEVCONTAINER_DOCKERFILE, alongside
    # the fixture and blocklist seams it already had) and the test hands it a copy.
    cp "$DOCKERFILE" "$FIXTURE_DIR/Dockerfile"
    # WRITABLE regardless of the source's mode: cp gives a new file the source's
    # permissions, and --upgrade must be able to rewrite the copy. Without this the
    # test inherits whatever mode the tracked file happens to carry, which is a
    # dependency on the environment rather than on the code.
    chmod u+w "$FIXTURE_DIR/Dockerfile"
    DOCKERFILE="$FIXTURE_DIR/Dockerfile"
    export DEVCONTAINER_DOCKERFILE="$DOCKERFILE"
    # shellcheck disable=SC2064
    # BLOCKER: capture FIXTURE_DIR at trap-set time so EXIT removes this exact path
    trap "rm -rf '$FIXTURE_DIR'" EXIT

    # Reported far OLDER than the real pin -> nothing is stale.
    cat >"$FIXTURE_DIR/all-current.json" <<'EOF'
{ "bw": { "version": "0.0.1" } }
EOF

    # Reported far NEWER, published long ago -> confirmed stale (past the soak).
    cat >"$FIXTURE_DIR/stale.json" <<EOF
{
  "bw": {
    "version": "9999.1.0",
    "publishedAt": "2020-01-01T00:00:00Z",
    "digests": {
      "bw-linux-9999.1.0.zip": "$BW_SHA_AMD64",
      "bw-linux-arm64-9999.1.0.zip": "$BW_SHA_ARM64"
    }
  }
}
EOF

    # Stale, but the arm64 asset has no digest -> --upgrade must refuse the whole
    # source rather than write a version whose hash it could not resolve.
    cat >"$FIXTURE_DIR/stale-missing-digest.json" <<EOF
{
  "bw": {
    "version": "9999.1.0",
    "publishedAt": "2020-01-01T00:00:00Z",
    "digests": { "bw-linux-9999.1.0.zip": "$BW_SHA_AMD64" }
  }
}
EOF

    # Newer but published just now -> inside the freshness window (deferred).
    local recent
    recent="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null ||
        date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)"
    cat >"$FIXTURE_DIR/fresh.json" <<EOF
{ "bw": { "version": "9999.1.0", "publishedAt": "$recent" } }
EOF

    # Empty fixture -> every source "not in fixture" -> could-not-check (fail soft).
    echo '{}' >"$FIXTURE_DIR/empty.json"

    # A blocklist entry with NO BLOCKER reason -> verifyAllBlockers must reject it.
    printf 'bw\n' >"$FIXTURE_DIR/blocklist-bad"

    # A blocklist entry WITH a substantive BLOCKER reason -> accepted, no error.
    printf '# BLOCKER: the next Bitwarden CLI dropped the native linux build we depend on; holding until it returns\nbw\n' \
        >"$FIXTURE_DIR/blocklist-good"
}

run_gate() { # <fixture-file> [extra args...] -> stdout+stderr, returns exit code
    local fixture="$1"
    shift
    (cd "$REPO_ROOT" && DEVCONTAINER_FRESHNESS_FIXTURE="$FIXTURE_DIR/$fixture" \
        npx tsx "$VALIDATOR" "$@" 2>&1)
}

# Runs the gate with a fixture upstream map AND a fixture blocklist, so the
# blocklist's BLOCKER validation can be exercised in isolation from the network.
run_gate_blocklist() { # <freshness fixture> <blocklist fixture>
    (cd "$REPO_ROOT" &&
        DEVCONTAINER_FRESHNESS_FIXTURE="$FIXTURE_DIR/$1" \
            DEVCONTAINER_BLOCKLIST_FILE="$FIXTURE_DIR/$2" \
            npx tsx "$VALIDATOR" 2>&1)
}

test_passes_when_current() {
    local rc=0
    run_gate all-current.json >/dev/null || rc=$?
    assert_exit_code 0 "$rc" "nothing behind upstream should pass"
    log_pass "current pins pass"
}

test_fires_when_stale() {
    local out rc=0
    out=$(run_gate stale.json) || rc=$?
    assert_exit_code 1 "$rc" "a pin behind upstream should fail"
    assert_contains "$out" "Bitwarden CLI" "error names the stale component"
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
    local rc=0
    run_gate empty.json >/dev/null || rc=$?
    assert_exit_code 0 "$rc" "sources that cannot be checked must not fail the build"
    log_pass "uncheckable sources fail soft"
}

test_blocklist_rejects_missing_reason() {
    local out rc=0
    out=$(run_gate_blocklist all-current.json blocklist-bad) || rc=$?
    assert_exit_code 1 "$rc" "a blocklist entry lacking a BLOCKER reason must fail the gate"
    assert_contains "$out" "invalid entries" "error names the malformed blocklist"
    log_pass "blocklist entry without a BLOCKER reason fires"
}

test_blocklist_accepts_valid_reason() {
    local rc=0
    run_gate_blocklist all-current.json blocklist-good >/dev/null || rc=$?
    assert_exit_code 0 "$rc" "a blocklist entry with a substantive BLOCKER reason must be accepted"
    log_pass "well-formed blocklist entry is accepted"
}

# --upgrade WRITES to the real Dockerfile. The EXIT trap owns the restore (see
# setup_fixtures); this only puts the file back BETWEEN cases so the second one
# starts from the tracked pin rather than from the first one's 9999.1.0.
# Each --upgrade case needs a PRISTINE copy, because --upgrade rewrites in place
# and the next case must not see the previous one's edit. The source is the real
# tracked file; the destination is the fixture copy, so this reads FROM the tree
# and never writes TO it.
restore_dockerfile() { cp -f "$REPO_ROOT/.devcontainer/Dockerfile" "$DOCKERFILE" && chmod u+w "$DOCKERFILE"; }

test_upgrade_moves_version_and_hashes() {
    local out rc=0
    out=$(run_gate stale.json --upgrade) || rc=$?
    assert_exit_code 0 "$rc" "--upgrade with every digest resolvable should succeed"
    assert_contains "$out" "sha256 pin" "output says the hashes moved too, not just the version"

    local ver amd arm
    ver="$(grep -oP '^ARG BW_VERSION=\K\S+' "$DOCKERFILE")"
    amd="$(grep -oP '^ARG BW_SHA256_AMD64=\K\S+' "$DOCKERFILE")"
    arm="$(grep -oP '^ARG BW_SHA256_ARM64=\K\S+' "$DOCKERFILE")"
    assert_eq "$ver" "9999.1.0" "--upgrade rewrote BW_VERSION"
    assert_eq "$amd" "$BW_SHA_AMD64" "--upgrade rewrote BW_SHA256_AMD64 from the release digest"
    assert_eq "$arm" "$BW_SHA_ARM64" "--upgrade rewrote BW_SHA256_ARM64 from the release digest"
    restore_dockerfile
    log_pass "--upgrade moves the version and both sha256 pins together"
}

# THE ASSERTION THIS GATE EXISTS FOR. A half-applied upgrade -- new version, old
# hash -- is a tree that fails `docker build` at `sha256sum -c -`, and an operator
# who ran --upgrade and got that learns to distrust the gate rather than the
# release. So a missing digest must leave the Dockerfile completely untouched.
test_upgrade_refuses_when_a_digest_is_missing() {
    local out rc=0 before after
    before="$(sha256sum "$DOCKERFILE" | cut -d' ' -f1)"
    out=$(run_gate stale-missing-digest.json --upgrade) || rc=$?
    after="$(sha256sum "$DOCKERFILE" | cut -d' ' -f1)"

    assert_exit_code 1 "$rc" "--upgrade must fail when a required digest cannot be resolved"
    assert_contains "$out" "no digest" "the error names the missing digest"
    assert_eq "$after" "$before" "the Dockerfile must be left untouched, not half-written"
    restore_dockerfile
    log_pass "--upgrade refuses a partial rewrite when a digest is missing"
}

log_test "test-devcontainer-pin-freshness"
setup_fixtures
test_passes_when_current
test_fires_when_stale
test_defers_fresh_release
test_fails_soft_when_uncheckable
test_blocklist_rejects_missing_reason
test_blocklist_accepts_valid_reason
test_upgrade_moves_version_and_hashes
test_upgrade_refuses_when_a_digest_is_missing
echo ""
log_pass "all tests passed"

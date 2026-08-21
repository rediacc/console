#!/bin/bash
# Both-ways test for .ci/scripts/quality/check-go-module-sync.sh.
#
# WHY IT EXISTS DESPITE THE SIBLING PRECEDENT. check:ci-go-deps ships without a
# gate-test, so convention would have allowed this one to as well. The review of
# PR #570 flagged that CLAUDE.md's standard is the stronger claim: a gate never
# watched failing is indistinguishable from `true`. The defect this gate exists
# for surfaced ~25 minutes into CI and read as a slow proxy, so the one thing
# that must never rot is its ability to FAIL.
#
# The gate DISCOVERS modules by grepping for a `replace` onto the renet
# worktree, so the fixture is a throwaway tree containing such a module rather
# than the live one; that keeps the proofs independent of whatever
# license-mint happens to pin today.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-go-module-sync.sh"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# get_repo_root() resolves from the SCRIPT's own path (.ci/scripts/lib -> up 3),
# so the fixture mirrors the tree layout.
mkdir -p "$FIXTURE/repo/.ci/scripts/quality" "$FIXTURE/repo/.ci/scripts/lib"
cp "$GATE" "$FIXTURE/repo/.ci/scripts/quality/"
cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$FIXTURE/repo/.ci/scripts/lib/"
TARGET="$FIXTURE/repo/.ci/scripts/quality/check-go-module-sync.sh"

# A stub `go` whose `mod tidy -diff` verdict the test controls, so the cases
# below exercise the GATE's logic rather than a real module graph.
write_fake_go() {
    local verdict="$1"
    cat >"$FIXTURE/bin/go" <<STUB
#!/bin/bash
if [[ "\$1" == "mod" && "\$2" == "tidy" && "\$3" == "-diff" ]]; then
    if [[ "$verdict" == "tidy" ]]; then
        exit 0
    fi
    echo "diff current/go.mod tidy/go.mod"
    echo "-	github.com/sirupsen/logrus v1.10.0 // indirect"
    echo "+	github.com/sirupsen/logrus v1.10.1 // indirect"
    exit 1
fi
exit 0
STUB
    chmod +x "$FIXTURE/bin/go"
}

seed_module() {
    mkdir -p "$FIXTURE/repo/tool"
    cat >"$FIXTURE/repo/tool/go.mod" <<'MOD'
module example.com/tool

go 1.25.0

require github.com/rediacc/renet v0.0.0

replace github.com/rediacc/renet => ../../private/renet
MOD
}

run_gate() {
    local rc=0
    (cd "$FIXTURE/repo" && PATH="$FIXTURE/bin:$PATH" bash "$TARGET") \
        >"$FIXTURE/out.txt" 2>&1 || rc=$?
    [[ $rc -eq 0 ]] && echo "PASS" || echo "FAIL"
}
last_output() { cat "$FIXTURE/out.txt"; }

mkdir -p "$FIXTURE/bin"

test_a_tidy_module_passes() {
    # Baseline. If this failed, every other case would be meaningless.
    seed_module
    write_fake_go tidy
    assert_eq "$(run_gate)" "PASS" "a module already tidy against renet validates"
    log_pass "a tidy module passes"
}

test_an_out_of_sync_module_FAILS() {
    # THE CASE THE GATE EXISTS FOR: renet moved, the replacing module did not.
    seed_module
    write_fake_go stale
    assert_eq "$(run_gate)" "FAIL" "an out-of-sync module must fail"
    assert_contains "$(last_output)" "OUT OF SYNC" "the failure names the condition"
    assert_contains "$(last_output)" "go mod tidy" "the failure names the fix"
    log_pass "an out-of-sync module fails and names both the condition and the fix"
}

test_finding_NO_modules_is_a_failure_not_a_pass() {
    # A discovery gate that finds nothing has verified nothing. If the replace
    # coupling ever disappears, this must be a loud decision rather than a
    # silent green.
    rm -rf "$FIXTURE/repo/tool"
    write_fake_go tidy
    assert_eq "$(run_gate)" "FAIL" "zero discovered modules must not read as success"
    assert_contains "$(last_output)" "verified NOTHING" "the vacuity guard is what fires"
    log_pass "discovering zero modules fails rather than passing vacuously"
}

log_test "test-go-module-sync"
test_a_tidy_module_passes
test_an_out_of_sync_module_FAILS
test_finding_NO_modules_is_a_failure_not_a_pass
echo ""
log_pass "all tests passed"

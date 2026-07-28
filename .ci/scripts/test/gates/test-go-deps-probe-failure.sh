#!/bin/bash
# Unit test for the probe-failure guard in .ci/scripts/quality/check-go-deps.sh.
#
# WHAT BROKE. The gate gathered its data with
#
#     go list -u -m -json all 2>/dev/null | jq ... 2>/dev/null || true
#
# so ANY failure of either command produced an empty result set -- which is
# byte-identical to a clean tree. The gate then printed "All Go direct
# dependencies are up-to-date" and exited 0. It was not reporting that deps were
# fine; it was reporting nothing at all, in the voice of success.
#
# Observed 2026-07-27: a local `npm run ci` reported all-clean while CI failed on
# the SAME commit for an outdated csi-spec. The gate was not disagreeing with CI
# -- `go list` was exiting 1 locally (go.mod requires go >= 1.25, the toolchain
# on PATH was 1.24) and the failure was being swallowed.
#
# This is the repo's own doctrine applied to a gate that violated it: a validator
# that passes when given nothing is broken by definition.
#
# WHY A PATH SHIM. Reproducing the original required a specific broken toolchain
# on the machine. A fake `go` on PATH reproduces every failure mode
# deterministically and on any runner, including the ones a real toolchain cannot
# easily produce (valid-but-empty output).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# get_repo_root() resolves from the script's own path, so mirror the layout.
mkdir -p "$FIXTURE/.ci/scripts/quality" "$FIXTURE/.ci/scripts/lib" \
    "$FIXTURE/private/fakemod" "$FIXTURE/shim"
cp "$REPO_ROOT/.ci/scripts/quality/check-go-deps.sh" "$FIXTURE/.ci/scripts/quality/"
cp "$REPO_ROOT"/.ci/scripts/lib/*.sh "$FIXTURE/.ci/scripts/lib/"
printf 'module example.com/fakemod\n\ngo 1.25\n' >"$FIXTURE/private/fakemod/go.mod"
: >"$FIXTURE/.go-deps-upgrade-blocklist"
GATE="$FIXTURE/.ci/scripts/quality/check-go-deps.sh"

# install_fake_go <mode>
install_fake_go() {
    cat >"$FIXTURE/shim/go" <<EOF
#!/bin/bash
mode="$1"
case "\$mode" in
    fail)      echo "go: go.mod requires go >= 1.25.0 (running go 1.24.0)" >&2; exit 1 ;;
    empty)     exit 0 ;;
    garbage)   echo "this is not json"; exit 0 ;;
    clean)     printf '%s\n' '{"Path":"example.com/fakemod","Version":"v1.0.0","Main":true}' ;;
    outdated)  printf '%s\n' '{"Path":"github.com/some/dep","Version":"v1.0.0","Update":{"Version":"v1.1.0","Time":"2020-01-01T00:00:00Z"}}' ;;
esac
EOF
    chmod +x "$FIXTURE/shim/go"
}

# run_gate -> prints exit code; output captured to $FIXTURE/out.txt
run_gate() {
    local rc=0
    PATH="$FIXTURE/shim:$PATH" bash "$GATE" >"$FIXTURE/out.txt" 2>&1 || rc=$?
    echo "$rc"
}
out() { cat "$FIXTURE/out.txt"; }

# ---------------------------------------------------------------------------

test_healthy_clean_tree_passes() {
    # Baseline. Without this the failure cases could pass for the wrong reason
    # (e.g. the gate erroring on the fixture itself).
    install_fake_go clean
    assert_eq "$(run_gate)" "0" "a clean module list must pass"
    assert_contains "$(out)" "up-to-date" "and say so"
    log_pass "a healthy probe with no updates passes"
}

test_healthy_outdated_still_fails() {
    # The gate's original job must survive the fix.
    install_fake_go outdated
    assert_eq "$(run_gate)" "1" "a genuinely outdated direct dep must still fail"
    assert_contains "$(out)" "Outdated Go direct dependencies" "with the original diagnostic"
    log_pass "a real outdated dependency still fails the gate"
}

test_probe_failure_is_not_up_to_date() {
    # THE REGRESSION. This returned 0 and printed "up-to-date" before the fix.
    install_fake_go fail
    assert_eq "$(run_gate)" "1" "a failing go-list must fail the gate, not pass it"
    assert_contains "$(out)" "probe FAILED" "the failure is named as a probe failure"
    assert_not_contains "$(out)" "All Go direct dependencies are up-to-date" \
        "it must NOT claim everything is up-to-date"
    log_pass "a failing probe fails loudly instead of reporting all-clean"
}

test_probe_failure_surfaces_the_real_error() {
    # A diagnostic that does not name the underlying cause sends the reader
    # hunting through their own tree for a dependency problem that is really a
    # toolchain problem.
    install_fake_go fail
    run_gate >/dev/null
    assert_contains "$(out)" "go.mod requires go >= 1.25.0" "the actual go error is surfaced"
    assert_contains "$(out)" "exit=1" "the exit status is surfaced"
    log_pass "the probe failure carries go's own error text"
}

test_empty_output_is_a_failure_not_a_clean_tree() {
    # `go list -m` on a real module always emits at least the main module, so
    # zero modules means the probe returned nothing usable. This mode is the one
    # a real broken toolchain cannot easily produce, and it is the subtlest: exit
    # 0 with empty stdout looked exactly like success.
    install_fake_go empty
    assert_eq "$(run_gate)" "1" "an empty module list must fail"
    assert_contains "$(out)" "no modules at all" "and say why"
    log_pass "a successful-but-empty probe is treated as broken, not clean"
}

test_unparsable_output_is_a_failure() {
    install_fake_go garbage
    assert_eq "$(run_gate)" "1" "unparsable go-list output must fail"
    assert_contains "$(out)" "probe FAILED" "reported as a probe failure"
    log_pass "unparsable probe output fails instead of reading as clean"
}

test_real_gate_has_no_swallowing_redirects() {
    # Guards the specific shape that caused this: the fix is worthless if
    # somebody reinstates `2>/dev/null` or `|| true` on the probe.
    local real="$REPO_ROOT/.ci/scripts/quality/check-go-deps.sh"
    assert_not_contains "$(grep -A2 'go list -u -m -json all' "$real")" "2>/dev/null" \
        "the probe must not discard go's stderr"
    assert_not_contains "$(grep -A2 'go list -u -m -json all' "$real")" "|| true" \
        "the probe must not swallow a non-zero exit"
    log_pass "the real gate still captures the probe's stderr and exit status"
}

log_test "test-go-deps-probe-failure"
test_healthy_clean_tree_passes
test_healthy_outdated_still_fails
test_probe_failure_is_not_up_to_date
test_probe_failure_surfaces_the_real_error
test_empty_output_is_a_failure_not_a_clean_tree
test_unparsable_output_is_a_failure
test_real_gate_has_no_swallowing_redirects
echo ""
log_pass "all tests passed"

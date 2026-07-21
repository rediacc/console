#!/bin/bash
# Integration test for scripts/check-dead-bash.ts.
#
# Must be provable BOTH ways: passes on the real tree AND fires on planted dead
# code. The detector also has to NOT fire on the two discovery mechanisms that
# make a naive version useless (glob expansion, dynamic dispatch) -- a naive
# detector reports 54 orphan files here, ~85% of them false.
#
# Fixtures live under DEAD_BASH_ROOT so no tracked file is ever mutated; the
# working tree routinely holds other sessions' uncommitted work.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-dead-bash.ts"

# A fixture with one referenced script and one referencing caller, so the tree
# is healthy before each test bends exactly one thing.
make_fixture() {
    local t
    t="$(mktemp -d)"
    mkdir -p "$t/.ci/scripts/lib" "$t/scripts"
    cat >"$t/.ci/scripts/lib/helpers.sh" <<'EOF'
#!/bin/bash
live_helper() {
    echo "used"
}
EOF
    cat >"$t/run.sh" <<'EOF'
#!/bin/bash
source .ci/scripts/lib/helpers.sh
live_helper
bash .ci/scripts/lib/helpers.sh
EOF
    # run.sh needs an inbound reference of its own, or it is legitimately an
    # orphan and every test below inherits that finding. In the real repo the
    # docs name it; here a README plays that role.
    printf 'Run the entrypoint with `./run.sh`.\n' >"$t/README.md"
    echo "$t"
}

run_gate() {
    local root="$1"
    shift
    (cd "$REPO_ROOT" && DEAD_BASH_ROOT="$root" npx tsx "$GATE" "$@" 2>&1) || return $?
}

test_passes_on_real_repo() {
    local out rc=0
    out=$(cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "the live tree must have no dead shell symbols"
    assert_contains "$out" "scanned" "prints a scan summary"
    log_pass "passes clean on the real repository"
}

test_fires_on_unused_function() {
    local t out rc=0
    t="$(make_fixture)"
    printf 'orphan_fn() {\n    echo dead\n}\n' >>"$t/.ci/scripts/lib/helpers.sh"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "an uncalled function must fail the gate"
    assert_contains "$out" "orphan_fn" "names the dead function"
    assert_contains "$out" "helpers.sh:" "cites file:line"
    log_pass "fires on an unused shell function"
}

test_no_false_positive_on_cross_file_call() {
    local t out rc=0
    t="$(make_fixture)"
    # live_helper is defined in helpers.sh and called from run.sh.
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a function called from another file is not dead"
    assert_not_contains "$out" "live_helper" "cross-file call is recognised"
    log_pass "does not condemn a function called from another file"
}

test_fires_on_orphan_file() {
    local t out rc=0
    t="$(make_fixture)"
    printf '#!/bin/bash\necho nobody-calls-me\n' >"$t/scripts/orphan-script.sh"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "an unreferenced script must fail the gate"
    assert_contains "$out" "orphan-script.sh" "names the orphan file"
    log_pass "fires on an orphaned shell script"
}

test_glob_root_exempts_a_directory() {
    local t out rc=0
    t="$(make_fixture)"
    mkdir -p "$t/scripts/globbed"
    printf '#!/bin/bash\necho found-by-glob\n' >"$t/scripts/globbed/test-thing.sh"
    printf '# BLOCKER: expanded as a glob by a runner that never names these files individually\nglob:scripts/globbed/\n' >"$t/.dead-bash-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a glob-discovered file must not be reported"
    assert_not_contains "$out" "test-thing.sh" "glob root exempts the directory"
    log_pass "glob: root exempts glob-discovered scripts"
}

test_dispatch_prefix_exempts_functions() {
    local t out rc=0
    t="$(make_fixture)"
    printf 'phase_alpha() {\n    echo dispatched\n}\n' >>"$t/.ci/scripts/lib/helpers.sh"
    printf '# BLOCKER: assembled at runtime as "phase_$name" so no static call site can exist for these\ndispatch:phase_\n' >"$t/.dead-bash-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a dynamically dispatched function must not be reported"
    assert_not_contains "$out" "phase_alpha" "dispatch prefix exempts the function"
    log_pass "dispatch: prefix exempts dynamically dispatched functions"
}

test_manual_entry_exempts_a_file() {
    local t out rc=0
    t="$(make_fixture)"
    printf '#!/bin/bash\necho operator-runs-this\n' >"$t/scripts/manual-tool.sh"
    printf '# BLOCKER: run directly by the operator when a manual reconciliation is needed, never from CI\nmanual:scripts/manual-tool.sh\n' >"$t/.dead-bash-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "an allowlisted manual entrypoint must not be reported"
    assert_not_contains "$out" "manual-tool.sh:" "manual entry exempts the script"
    log_pass "manual: entry exempts an operator-invoked script"
}

test_rejects_low_effort_blocker() {
    local t out rc=0
    t="$(make_fixture)"
    printf '# BLOCKER: tbd\nglob:scripts/\n' >"$t/.dead-bash-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a low-effort BLOCKER must be rejected"
    assert_contains "$out" "BLOCKER validation failed" "shared validator rejects it"
    log_pass "low-effort BLOCKER on the allowlist is rejected"
}

test_rejects_unknown_entry_kind() {
    local t out rc=0
    t="$(make_fixture)"
    printf '# BLOCKER: an entry with no recognised prefix must be refused rather than silently ignored\nscripts/whatever.sh\n' >"$t/.dead-bash-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "an entry with no kind prefix must fail"
    assert_contains "$out" "must start with" "explains the required prefixes"
    log_pass "entry without glob:/dispatch:/manual: prefix is rejected"
}

test_empty_tree_is_vacuous() {
    local t out rc=0
    t="$(mktemp -d)"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a tree with no shell files must fail, not pass vacuously"
    assert_contains "$out" "ZERO shell files" "says the gate is blind"
    log_pass "empty tree fails as vacuous"
}

log_test "test-dead-bash"
test_passes_on_real_repo
test_fires_on_unused_function
test_no_false_positive_on_cross_file_call
test_fires_on_orphan_file
test_glob_root_exempts_a_directory
test_dispatch_prefix_exempts_functions
test_manual_entry_exempts_a_file
test_rejects_low_effort_blocker
test_rejects_unknown_entry_kind
test_empty_tree_is_vacuous
echo ""
log_pass "all tests passed"

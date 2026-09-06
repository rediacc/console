#!/bin/bash
# Integration test for scripts/check-dead-bash.ts.
#
# Must be provable BOTH ways: the detector fires on planted dead code AND the
# real tree is clean. The detector also has to NOT fire on the two discovery
# mechanisms that make a naive version useless (glob expansion, dynamic
# dispatch) -- a naive detector reports 54 orphan files here, ~85% of them false.
#
# THE REAL-TREE HALF LIVES IN check:ci-dead-bash, NOT HERE (changed 2026-09-06).
# This file used to open with test_passes_on_real_repo, which ran
# `npx tsx scripts/check-dead-bash.ts` over the whole repository -- byte for byte
# the same scan that `check:ci-dead-bash` (package.json) already runs as its own
# first-class manifest gate. Both are scheduled in the same full local run, so
# the real-tree scan executed TWICE per `npm run ci`.
#
# MEASURED, not read. Sampling the process table once a second through
#   npx tsx scripts/ci-runner/run.ts --only check:ci-hook-worklist-suite,\
#     gate-test:worklist-hooks,check:ci-dead-bash,gate-test:dead-bash --jobs 4
# showed TWO long-lived check-dead-bash.ts processes, 246s and 239s, alongside
# nine one-sample fixture scans. The nine are this file's planted-defect controls
# and are correct; the second long one was the duplicate.
#
# The both-ways property is UNCHANGED at the battery level, because
# check:ci-dead-bash is the real-tree direction and is asserted to still exist by
# test_real_tree_scan_is_delegated below. What is gone is the second execution of
# it, not the coverage. Deleting the assertion is how the coverage would actually
# be lost, so it fails this gate rather than being left to a comment.
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

# Seams so the delegation assertion can be driven against a doctored registry
# without touching the real files. Defaults are what CI reads.
DELEGATION_PACKAGE_JSON="${DELEGATION_PACKAGE_JSON:-$REPO_ROOT/package.json}"
DELEGATION_MANIFEST="${DELEGATION_MANIFEST:-$REPO_ROOT/scripts/ci-runner/manifest.ts}"

# delegation_verdict -- prints a reason and returns 1 when the real-tree scan is
# no longer registered anywhere. Split out of the test so the CONTROL below can
# drive the identical code path against a planted defect rather than a lookalike.
delegation_verdict() {
    local key='check:ci-dead-bash' leaf='scripts/check-dead-bash.ts' line entry

    # `|| true` on both extractions: under `set -euo pipefail` a non-matching
    # grep or awk would abort before the diagnostic could print, turning "the
    # delegate vanished" into a bare exit code -- the failure mode this whole
    # file exists to make legible.
    line="$(grep -F "\"$key\":" "$DELEGATION_PACKAGE_JSON" || true)"
    if [[ -z "$line" ]]; then
        echo "package.json has no \"$key\" script, so the real-tree scan runs NOWHERE"
        return 1
    fi
    if [[ "$line" != *"$leaf"* ]]; then
        echo "\"$key\" no longer runs $leaf; it runs:$line"
        return 1
    fi
    # A fixture-rooted invocation is not the real-tree scan. DEAD_BASH_ROOT is
    # exactly how this file points the gate at a mktemp tree, so a delegate that
    # sets it would be scanning a fixture while looking like full coverage.
    if [[ "$line" == *"DEAD_BASH_ROOT"* ]]; then
        echo "\"$key\" sets DEAD_BASH_ROOT, so it scans a fixture and not the real tree:$line"
        return 1
    fi

    # Bounded by the entry's own two-space closing brace rather than a fixed line
    # count: a `grep -A <n>` window either misses a reordered field or bleeds into
    # the NEXT entry and reads its `gate: true` as this one's.
    entry="$(awk -v k="id: '$key'," 'index($0, k) { f = 1 } f { print } f && /^  },$/ { exit }' \
        "$DELEGATION_MANIFEST" || true)"
    if [[ -z "$entry" ]]; then
        echo "scripts/ci-runner/manifest.ts has no entry with id '$key', so the npm key exists but nothing schedules it"
        return 1
    fi
    if [[ "$entry" != *"gate: true"* ]]; then
        echo "manifest entry '$key' is not gate: true, so a full run never selects it"
        return 1
    fi
    if [[ "$entry" != *"$leaf"* ]]; then
        echo "manifest entry '$key' no longer declares $leaf among its leaves"
        return 1
    fi
    return 0
}

test_real_tree_scan_is_delegated() {
    local out rc=0
    out="$(delegation_verdict)" || rc=$?
    if ((rc != 0)); then
        log_fail "the real-tree scan is no longer covered: $out"
    fi
    log_pass "the real-tree scan is delegated to a registered check:ci-dead-bash gate"
}

test_delegation_assertion_fires() {
    # CONTROL, in the file's own both-ways style. An assertion that cannot fail
    # is worth what no assertion is worth, and "the delegate quietly vanished"
    # looks exactly like "the delegate ran and passed". Four planted defects,
    # each of which must be caught, and each of which must be caught FOR ITS OWN
    # REASON -- a control that fires for the wrong reason is a control that will
    # keep firing after the defect it names is fixed.
    local t out rc
    t="$(mktemp -d)"

    grep -v -F '"check:ci-dead-bash":' "$REPO_ROOT/package.json" >"$t/pkg-missing.json"
    sed 's#"check:ci-dead-bash": "tsx scripts/check-dead-bash.ts"#"check:ci-dead-bash": "tsx scripts/check-something-else.ts"#' \
        "$REPO_ROOT/package.json" >"$t/pkg-repointed.json"
    sed "s/id: 'check:ci-dead-bash',/id: 'check:ci-dead-bash-renamed',/" \
        "$DELEGATION_MANIFEST" >"$t/manifest-noentry.ts"
    awk "/id: 'check:ci-dead-bash',/ { f = 1 }
         f && /gate: true,/ && !d { sub(/gate: true,/, \"gate: false,\"); d = 1 }
         /^  },\$/ { f = 0 }
         { print }" "$DELEGATION_MANIFEST" >"$t/manifest-gatefalse.ts"

    rc=0
    out=$(DELEGATION_PACKAGE_JSON="$t/pkg-missing.json" delegation_verdict) || rc=$?
    assert_exit_code 1 "$rc" "a package.json with the key REMOVED must fail the delegation check"
    assert_contains "$out" "runs NOWHERE" "names the missing key"

    rc=0
    out=$(DELEGATION_PACKAGE_JSON="$t/pkg-repointed.json" delegation_verdict) || rc=$?
    assert_exit_code 1 "$rc" "a key repointed at another script must fail"
    assert_contains "$out" "no longer runs" "names the repointing"

    rc=0
    out=$(DELEGATION_MANIFEST="$t/manifest-noentry.ts" delegation_verdict) || rc=$?
    assert_exit_code 1 "$rc" "an unregistered key must fail: an npm key nothing schedules is not coverage"
    assert_contains "$out" "no entry with id" "names the missing manifest entry"

    rc=0
    out=$(DELEGATION_MANIFEST="$t/manifest-gatefalse.ts" delegation_verdict) || rc=$?
    assert_exit_code 1 "$rc" "a gate: false entry must fail: a full run never selects it"
    assert_contains "$out" "not gate: true" "names the flipped flag"

    rm -rf "$t"
    log_pass "the delegation check fires on all four ways the real-tree scan can go uncovered"
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
test_real_tree_scan_is_delegated
test_delegation_assertion_fires
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

#!/bin/bash
# Both-ways test for the two version checks inside
# .ci/scripts/build/build-cli-executables.sh.
#
# WHAT THEY ARE FOR.
#   1. The release guard: on the publishable path (RELEASE_BUILD=true, set by
#      ci-build-cli.yml only on push-to-main) a placeholder, empty, or malformed
#      version must stop the build before a single byte is stamped.
#   2. The doctor smoke test: it runs the binary that was just produced and
#      reads its version back. This is the ONLY point in the entire pipeline
#      that reads a version out of freshly built bytes.
#
# WHAT WAS BROKEN. Check 2 asserted only `[[ -n "$CLI_VERSION" ]] && [[ ... !=
# "null" ]]` -- it never compared the reported version to the version the build
# was told to produce, and it parsed the reported value into the SAME variable
# name that carried the expected one, destroying the only copy. A SEA built as
# 0.0.0-dev passed with a cheerful "CLI version: 0.0.0-dev", and release
# 31154305287 published binaries built as 1.2.16 under the label 1.2.17 with
# this step green. Check 1 did not exist at all.
#
# HOW THE SMOKE TEST IS EXERCISED. Building a real SEA takes minutes, so the
# comparison block is EXTRACTED FROM THE REAL SCRIPT by its own anchors and run
# against planted doctor output. It is the script's own bytes, not a copy of
# its logic; if someone rewrites the block, the anchors stop matching and
# test_block_is_extractable fails rather than silently testing nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/build/build-cli-executables.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Part 1: the release guard, run against the REAL script.
# It sits immediately after the --dry-run exit and before `node bundle.mjs`,
# so a refused build costs a second and touches nothing.
# ---------------------------------------------------------------------------

# run_build <env-assignments...> -- returns exit code, output in $WORK/build.log
run_build() {
    local st=0
    env "$@" "$GATE" --platform linux --arch x64 --output "$WORK/out" \
        >"$WORK/build.log" 2>&1 || st=$?
    echo "$st"
}

test_release_build_refuses_the_placeholder() {
    log_test "RELEASE_BUILD=true refuses a 0.0.0-dev version"
    local st
    st="$(run_build RELEASE_BUILD=true CLI_VERSION=0.0.0-dev)"
    assert_eq "$st" "1" "a placeholder version must not build a publishable artifact"
    assert_contains "$(cat "$WORK/build.log")" "0.0.0-dev" "the refusal must name the version"
    log_pass "release build refuses 0.0.0-dev"
}

test_release_build_refuses_an_empty_version() {
    log_test "RELEASE_BUILD=true refuses an empty version"
    local st
    st="$(run_build RELEASE_BUILD=true CLI_VERSION=)"
    assert_eq "$st" "1" "an empty version must not build a publishable artifact"
    assert_contains "$(cat "$WORK/build.log")" "CLI_VERSION is empty" "the refusal must say the version was empty"
    log_pass "release build refuses an empty version"
}

test_release_build_refuses_a_malformed_version() {
    log_test "RELEASE_BUILD=true refuses a malformed version"
    local st
    st="$(run_build RELEASE_BUILD=true CLI_VERSION=1.2.x)"
    assert_eq "$st" "1" "a malformed version must not build a publishable artifact"
    assert_contains "$(cat "$WORK/build.log")" "not a publishable version" "the refusal must say why"
    log_pass "release build refuses 1.2.x"
}

# THE OTHER DIRECTION: without RELEASE_BUILD the same placeholder is fine, so
# PR CI and local `./rdc.sh --native` keep working. Proven by letting the build
# get PAST the guard and die at the bundler instead (a stub node makes that
# instant and writes nothing).
test_dev_build_still_accepts_the_placeholder() {
    log_test "a non-release build still accepts 0.0.0-dev"
    mkdir -p "$WORK/bin"
    cat >"$WORK/bin/node" <<'STUB'
#!/bin/bash
# Answers --version (the script logs it) and fails anything else, so the run
# stops at `node bundle.mjs` -- after the release guard, before any output.
[[ "${1:-}" == "--version" ]] && { echo "v22.0.0"; exit 0; }
echo "stub node: refusing to run $*" >&2
exit 1
STUB
    chmod +x "$WORK/bin/node"

    local st=0
    env PATH="$WORK/bin:$PATH" CLI_VERSION=0.0.0-dev "$GATE" \
        --platform linux --arch x64 --output "$WORK/out" \
        >"$WORK/dev.log" 2>&1 || st=$?
    local out
    out="$(cat "$WORK/dev.log")"
    assert_not_contains "$out" "refusing to build a publishable artifact" "no release guard without RELEASE_BUILD"
    assert_not_contains "$out" "not a publishable version" "no release guard without RELEASE_BUILD"
    assert_contains "$out" "stub node" "the run must have reached the bundler, i.e. passed the guard"
    assert_eq "$st" "1" "the stub bundler still fails the run"
    log_pass "the dev path is untouched by the release guard"
}

# ---------------------------------------------------------------------------
# Part 2: the doctor version comparison, extracted from the real script.
# ---------------------------------------------------------------------------

BLOCK_START='INSTALL_METHOD=$(echo "$DOCTOR_OUTPUT" | jq -r'
BLOCK_END='log_info "CLI version: $REPORTED_CLI_VERSION (matches build version)"'

extract_block() {
    awk -v s="$BLOCK_START" -v e="$BLOCK_END" '
        index($0, s) { p = 1 }
        p { print }
        p && index($0, e) { exit }
    ' "$GATE"
}

doctor_json() {
    local version="$1"
    printf '{"Environment":[{"name":"Install method","value":"SEA binary","status":"ok"},{"name":"CLI version","value":"%s","status":"ok"},{"name":"Node.js","value":"v22","status":"ok"}]}' "$version"
}

# runs the extracted block; args: <expected> <reported> [<sed-mutation>]
run_block() {
    local expected="$1" reported="$2" mutation="${3:-}"
    local script="$WORK/block.sh"
    {
        echo '#!/bin/bash'
        echo 'set -euo pipefail'
        echo 'log_info() { echo "INFO: $*"; }'
        echo 'log_error() { echo "ERROR: $*" >&2; }'
        echo "EXPECTED_CLI_VERSION='$expected'"
        echo "DOCTOR_OUTPUT='$(doctor_json "$reported")'"
        if [[ -n "$mutation" ]]; then
            extract_block | sed "$mutation"
        else
            extract_block
        fi
    } >"$script"
    local st=0
    bash "$script" >"$WORK/block.log" 2>&1 || st=$?
    echo "$st"
}

test_block_is_extractable() {
    log_test "the doctor comparison block is still where the anchors say"
    local block
    block="$(extract_block)"
    assert_contains "$block" 'REPORTED_CLI_VERSION' "extraction must capture the reported-version parse"
    assert_contains "$block" 'EXPECTED_CLI_VERSION' "extraction must capture the expected-version comparison"
    log_pass "block extracted from the real script"
}

test_matching_version_passes() {
    log_test "doctor version equal to the build version passes"
    assert_eq "$(run_block 1.2.17 1.2.17)" "0" "a matching version must pass"
    assert_contains "$(cat "$WORK/block.log")" "matches build version" "and must say so"
    log_pass "1.2.17 built, 1.2.17 reported"
}

# THE INCIDENT, replayed: release 31154305287 built 1.2.16 and labelled it 1.2.17.
test_mismatched_version_fails() {
    log_test "doctor version different from the build version fails"
    assert_eq "$(run_block 1.2.17 1.2.16)" "1" "a mismatched version must fail the build"
    assert_contains "$(cat "$WORK/block.log")" "CLI version mismatch" "the failure must name the mismatch"
    log_pass "1.2.16 reported for a 1.2.17 build is caught"
}

test_placeholder_in_the_binary_fails() {
    log_test "a binary reporting 0.0.0-dev fails a real-version build"
    assert_eq "$(run_block 1.2.17 0.0.0-dev)" "1" "0.0.0-dev in the bytes must fail"
    log_pass "0.0.0-dev in the binary no longer passes cheerfully"
}

test_empty_version_still_fails() {
    log_test "an unreadable doctor version still fails"
    assert_eq "$(run_block 1.2.17 '')" "1" "an empty reported version must fail"
    assert_contains "$(cat "$WORK/block.log")" "CLI version check failed" "the original non-empty check must survive"
    log_pass "empty reported version fails"
}

# THE CONTROL. Plant the pre-fix behaviour -- a comparison that compares
# nothing -- and watch the mismatch sail through. If this planted defect FAILED,
# test_mismatched_version_fails would prove nothing about the comparison.
test_planted_noncomparing_check_lets_the_mismatch_through() {
    log_test "control: with the comparison neutered, the mismatch passes"
    local st
    st="$(run_block 1.2.17 1.2.16 's|"$REPORTED_CLI_VERSION" != "$EXPECTED_CLI_VERSION"|1 -eq 0|')"
    assert_eq "$st" "0" "planted defect must pass (else the real assertion proves nothing)"
    assert_not_contains "$(cat "$WORK/block.log")" "mismatch" "planted defect must not report a mismatch"
    log_pass "the check demonstrably goes red only because it compares"
}

test_release_build_refuses_the_placeholder
test_release_build_refuses_an_empty_version
test_release_build_refuses_a_malformed_version
test_dev_build_still_accepts_the_placeholder
test_block_is_extractable
test_matching_version_passes
test_mismatched_version_fails
test_placeholder_in_the_binary_fails
test_empty_version_still_fails
test_planted_noncomparing_check_lets_the_mismatch_through

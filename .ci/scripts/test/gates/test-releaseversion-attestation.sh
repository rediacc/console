#!/bin/bash
# Both-ways test for .ci/scripts/release/verify-artifact-attestation.sh.
#
# WHAT IT IS FOR. cd-v2.yml runs it after downloading the release artifacts and
# before publishing them. It re-verifies the Sigstore build provenance that
# cd-stage.yml attached, proving the bytes CD is about to publish are the bytes
# CI produced.
#
# WHAT WAS BROKEN. Every `gh attestation verify` failure became a `::warning::`
# and the script had NO failing exit path at all -- it could not fail, for any
# input, ever. Its header called that a "transition period"; nothing recorded
# when the period ended, so it never would. Worse, `find` over two absent
# directories prints nothing, the loop body never runs, and it exited 0 having
# verified precisely zero artifacts, indistinguishable from a clean pass.
#
# The script resolves its repo root from its OWN path, so the test runs a copy
# inside a fixture tree. That keeps planted dist/ artifacts out of the real
# working tree, which other sessions are using.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/release/verify-artifact-attestation.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# build_fixture <name> [<artifact...>] -- a minimal repo root holding the script
# under test, its lib, and whatever artifacts the case needs.
build_fixture() {
    local name="$1"
    shift
    local root="$WORK/$name"
    mkdir -p "$root/.ci/scripts/release" "$root/.ci/scripts/lib"
    cp "$GATE" "$root/.ci/scripts/release/verify-artifact-attestation.sh"
    cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$root/.ci/scripts/lib/common.sh"
    local a
    for a in "$@"; do
        mkdir -p "$root/$(dirname "$a")"
        echo "bytes of $a" >"$root/$a"
    done
    echo "$root"
}

# fake_gh <dir> <unattested-basename-or-empty> -- a `gh` that verifies
# everything except the named file.
fake_gh() {
    local bin="$1/bin" bad="$2"
    mkdir -p "$bin"
    cat >"$bin/gh" <<FAKE
#!/bin/bash
# Emulates \`gh attestation verify <file> --repo <r>\`: \$1=attestation \$2=verify \$3=file.
target="\${3:-}"
if [[ -n "$bad" && "\$(basename "\$target")" == "$bad" ]]; then
    echo "no attestation found for \$target" >&2
    exit 1
fi
echo "Verification succeeded for \$target"
FAKE
    chmod +x "$bin/gh"
    echo "$bin"
}

# run_gate <root> <bin> -- exit code on stdout, combined output in $WORK/out.log
run_gate() {
    local st=0
    env PATH="$2:$PATH" GITHUB_REPOSITORY=rediacc/console GH_TOKEN=fake \
        "$1/.ci/scripts/release/verify-artifact-attestation.sh" \
        >"$WORK/out.log" 2>&1 || st=$?
    echo "$st"
}

test_all_attested_passes() {
    log_test "every artifact attested -> pass"
    local root bin
    root="$(build_fixture allgood dist/cli/rdc-linux-x64 dist/cli/rdc-linux-x64.sha256 dist/packages/rdc.deb)"
    bin="$(fake_gh "$root" "")"
    assert_eq "$(run_gate "$root" "$bin")" "0" "fully attested artifacts must pass"
    assert_contains "$(cat "$WORK/out.log")" "verified for all 3" "the pass must name how many it verified"
    log_pass "3 attested artifacts verified"
}

# THE DEFECT THIS SCRIPT EXISTS TO CATCH, planted: one artifact whose bytes are
# not the bytes CI attested. Before the fix this printed a warning and exited 0.
test_one_unattested_fails() {
    log_test "one unattested artifact -> fail"
    local root bin
    root="$(build_fixture oneBad dist/cli/rdc-linux-x64 dist/packages/rdc.deb)"
    bin="$(fake_gh "$root" "rdc.deb")"
    assert_eq "$(run_gate "$root" "$bin")" "1" "an unattested artifact must fail the release"
    local out
    out="$(cat "$WORK/out.log")"
    assert_contains "$out" "no valid build attestation" "the failure must say what is wrong"
    assert_contains "$out" "rdc.deb" "the failure must name the artifact"
    log_pass "an unattested artifact stops the release"
}

# THE OTHER WAY THIS SCRIPT COULD NOT FAIL: nothing to verify at all.
test_no_artifacts_fails() {
    log_test "nothing to verify -> fail"
    local root bin
    root="$(build_fixture empty)"
    bin="$(fake_gh "$root" "")"
    assert_eq "$(run_gate "$root" "$bin")" "1" "verifying zero artifacts is not a pass"
    assert_contains "$(cat "$WORK/out.log")" "NOTHING was verified" "the failure must say nothing was checked"
    log_pass "an empty dist/ stops the release"
}

# THE CONTROL. Neuter the failure accounting -- the pre-fix shape, where a
# failed verification only produced a warning -- and watch the same unattested
# artifact pass. If this planted defect FAILED, test_one_unattested_fails would
# not be evidence that the exit path is what makes the check red.
test_planted_warning_only_script_passes() {
    log_test "control: with failures downgraded to warnings, the bad artifact passes"
    local root bin
    root="$(build_fixture warnOnly dist/cli/rdc-linux-x64 dist/packages/rdc.deb)"
    bin="$(fake_gh "$root" "rdc.deb")"
    sed -i 's|FAILED_COUNT=$((FAILED_COUNT + 1))|FAILED_COUNT=$((FAILED_COUNT + 0))|' \
        "$root/.ci/scripts/release/verify-artifact-attestation.sh"
    assert_eq "$(run_gate "$root" "$bin")" "0" "planted warning-only script must pass (else the control proves nothing)"
    log_pass "the check goes red only because failures are counted and acted on"
}

test_all_attested_passes
test_one_unattested_fails
test_no_artifacts_fails
test_planted_warning_only_script_passes

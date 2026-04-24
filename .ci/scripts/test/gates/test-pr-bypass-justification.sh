#!/bin/bash
# Integration test for the bypass-label justification gate in
# .ci/scripts/quality/check-pr-description.sh.
#
# The gate is the function `check_bypass_label_justifications` which fetches
# PR labels + body via `gh pr view`. We shim `gh` on PATH so the function
# reads crafted JSON without touching the real GitHub API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET_SCRIPT="$REPO_ROOT/.ci/scripts/quality/check-pr-description.sh"

# Install a fake `gh` binary on PATH that returns the JSON at $GH_FAKE_OUTPUT.
# The fake ignores args; both `gh pr view ... --json labels,body` and later
# `gh pr view ... --json commits,body,title` in the main freshness flow get
# the same payload. We short-circuit the rest of the script by setting
# PR_NUMBER / GH_TOKEN to dummy values and running only the label function.
install_fake_gh() {
    local bin_dir="$1" json_file="$2"
    cat >"$bin_dir/gh" <<FAKE
#!/bin/bash
# All gh invocations return the crafted JSON; stderr silent.
cat "$json_file"
FAKE
    chmod +x "$bin_dir/gh"
}

# Run just the bypass-label check in isolation by sourcing the script up to
# and including the function definition, then invoking the function directly.
# This avoids running the whole freshness pipeline (which needs GraphQL).
run_bypass_check() {
    local json_file="$1"
    local bin_dir
    bin_dir="$(mktemp -d)"
    install_fake_gh "$bin_dir" "$json_file"
    local old_path="$PATH"
    export PATH="$bin_dir:$PATH"
    export PR_NUMBER=42
    export GH_TOKEN=fake
    export GITHUB_REPOSITORY="test/repo"
    # Extract the function + its prerequisite sourcing + BYPASS_LABELS into
    # a temp script; run that. Sourcing TARGET_SCRIPT directly would exit
    # because of the full pipeline at the bottom.
    local runner
    runner="$(mktemp)"
    cat >"$runner" <<'RUNNER'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "__TARGET__")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/../lib/blocker-validator.sh"
BYPASS_LABELS=(no-cancel-push no-cancel-failure no-auto-retry no-gemini-review no-external-quality)
RUNNER
    # Inject the function body by extracting it from the target script
    awk '
        /^check_bypass_label_justifications\(\)[[:space:]]*{[[:space:]]*$/ { in_fn=1 }
        in_fn { print }
        /^}[[:space:]]*$/ && in_fn { in_fn=0 }
    ' "$TARGET_SCRIPT" >>"$runner"
    echo "check_bypass_label_justifications" >>"$runner"
    # Replace the placeholder with an actual reference to the target script
    sed -i "s|__TARGET__|$TARGET_SCRIPT|" "$runner"
    local out rc=0
    out=$(bash "$runner" 2>&1) || rc=$?
    export PATH="$old_path"
    rm -rf "$bin_dir" "$runner"
    unset PR_NUMBER GH_TOKEN GITHUB_REPOSITORY
    echo "$out"
    return "$rc"
}

write_json() {
    local path="$1"
    shift
    cat >"$path" <<JSON
$*
JSON
}

test_no_bypass_label_is_skipped() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    write_json "$json" '{"labels":[{"name":"bug"},{"name":"needs-review"}],"body":"## Description\nnormal PR"}'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 0 "$rc" "PR without bypass labels must pass"
    assert_contains "$out" "No bypass labels applied" "skip reason explained"
    log_pass "PR without bypass labels is skipped"
}

test_bypass_label_with_valid_justification_passes() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    write_json "$json" '{
      "labels":[{"name":"no-external-quality"}],
      "body":"## Description\nfoo\n## Bypass justification\n- no-external-quality: investigating npm registry flake on dependabot bumps; need serial reruns to triage without masking\n## Additional Notes\nnone"
    }'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 0 "$rc" "valid justification must pass"
    assert_contains "$out" "passed the quality gate" "success message"
    log_pass "bypass label with valid justification passes"
}

test_bypass_label_missing_section_fails() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    write_json "$json" '{"labels":[{"name":"no-auto-retry"}],"body":"## Description\nfoo, no section here"}'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 1 "$rc" "missing section must fail"
    assert_contains "$out" "no '## Bypass justification' section" "error names the problem"
    log_pass "missing Bypass justification section is rejected"
}

test_low_effort_reason_fails() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    write_json "$json" '{
      "labels":[{"name":"no-cancel-push"}],
      "body":"## Bypass justification\n- no-cancel-push: tbd"
    }'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 1 "$rc" "banned-phrase reason must fail"
    assert_contains "$out" "low-effort placeholder" "reason rejected with name"
    log_pass "low-effort bypass reason is rejected"
}

test_short_reason_fails() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    write_json "$json" '{
      "labels":[{"name":"no-gemini-review"}],
      "body":"## Bypass justification\n- no-gemini-review: too short"
    }'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 1 "$rc" "short reason must fail"
    assert_contains "$out" "is too short" "error names the length problem"
    log_pass "short bypass reason is rejected"
}

test_multiple_labels_one_missing_fails() {
    local TEMP json
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    json="$TEMP/pr.json"
    # Two labels applied; only one justified. Second must cause failure.
    write_json "$json" '{
      "labels":[{"name":"no-cancel-push"},{"name":"no-auto-retry"}],
      "body":"## Bypass justification\n- no-cancel-push: genuinely investigating flaky network failure in Cloudflare R2 upload path, need isolation"
    }'
    local out rc=0
    out=$(run_bypass_check "$json") || rc=$?
    assert_exit_code 1 "$rc" "one missing justification must fail the whole gate"
    assert_contains "$out" "no-auto-retry" "names the missing label"
    log_pass "partial justification is rejected"
}

log_test "test-pr-bypass-justification"
test_no_bypass_label_is_skipped
test_bypass_label_with_valid_justification_passes
test_bypass_label_missing_section_fails
test_low_effort_reason_fails
test_short_reason_fails
test_multiple_labels_one_missing_fails
echo ""
log_pass "all tests passed"

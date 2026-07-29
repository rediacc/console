#!/bin/bash
# Unit test for .ci/scripts/quality/check-autopilot-no-bypass.sh.
#
# WHY THIS TEST EXISTS AT ALL, and it is not "because every gate should have one".
# The gate's most important assertion cannot be reached by driving the real API.
#
# Measured: console is public, so
#   curl https://api.github.com/repos/rediacc/console/rulesets/12344707
# answers 200 with NO `bypass_actors` key. A gate that fetched that would look in
# a list that does not exist, find no autopilot, and report PASS for ever. That is
# the single most dangerous shape this gate can have.
#
# But the failure is unreachable through `gh`: pointing GH_CONFIG_DIR at an empty
# directory makes `gh api` refuse the request outright, so the gate exits on "could
# not list rulesets" and the presence assertion never runs. Verified, not assumed --
# that exact control was run and it took the wrong branch.
#
# So the payload is planted through a `gh` shim on PATH. The gate under test is the
# REAL one, unmodified; only its view of the API is synthetic. No test hook, no
# override env var, nothing a security gate should not have in production.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-autopilot-no-bypass.sh"
[[ -x "$GATE" ]] || {
    echo "gate not found or not executable: $GATE" >&2
    exit 1
}

SHIMDIR="$(mktemp -d)"
trap 'rm -rf "$SHIMDIR"' EXIT

# plant <ruleset-json> -- install a `gh` shim that serves it for both the list and
# the detail call, then run the gate and echo "<exit>:<stderr>".
plant() {
    cat >"$SHIMDIR/gh" <<SHIM
#!/bin/bash
# args: api <path>
case "\$2" in
    */rulesets) echo '[{"id":99,"target":"branch","enforcement":"active"}]' ;;
    */rulesets/*) cat <<'BODY'
$1
BODY
        ;;
    *) exit 1 ;;
esac
SHIM
    chmod +x "$SHIMDIR/gh"
    local out rc=0
    out="$(PATH="$SHIMDIR:$PATH" AUTOPILOT_APP_ID=4409539 "$GATE" 2>&1)" || rc=$?
    echo "${rc}:${out}"
}

test_blind_read_fails_closed() {
    # THE WHOLE POINT. 200, plausible-looking, no bypass_actors key.
    local r
    r="$(plant '{"id":99,"name":"Branch Protection"}')"
    assert_eq "${r%%:*}" "1" "a payload with NO bypass_actors field must FAIL, not pass"
    assert_contains "$r" "BLIND read" "the failure must say it is blind, not merely 'not found'"
    log_pass "PLANTED missing bypass_actors => FAILURE (the public-repo 200 trap)"
}

test_bypass_entry_is_caught() {
    local r
    r="$(plant '{"id":99,"name":"Branch Protection","bypass_actors":[{"actor_id":4409539,"actor_type":"Integration","bypass_mode":"always"}]}')"
    assert_eq "${r%%:*}" "1" "an autopilot bypass entry must FAIL"
    assert_contains "$r" "HAS a bypass" "the failure must name the condition"
    log_pass "PLANTED autopilot bypass => FAILURE"
}

test_string_actor_id_still_matches() {
    # The API has returned actor_id as a number here; a future string form must not
    # silently stop matching. jq's tostring in the gate is what makes this hold.
    local r
    r="$(plant '{"id":99,"name":"Branch Protection","bypass_actors":[{"actor_id":"4409539","actor_type":"Integration","bypass_mode":"pull_request"}]}')"
    assert_eq "${r%%:*}" "1" "a STRING actor_id must match too, or the gate is type-fragile"
    log_pass "PLANTED string-typed actor_id => FAILURE (no type-coercion hole)"
}

test_other_actors_are_not_false_positives() {
    # Anti-vacuity in the other direction: the gate must not fail on every ruleset
    # that has any bypass at all, or its red would carry no information.
    local r
    r="$(plant '{"id":99,"name":"Branch Protection","bypass_actors":[{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"always"},{"actor_id":2772000,"actor_type":"Integration","bypass_mode":"always"}]}')"
    assert_eq "${r%%:*}" "0" "the real bypass actors (Admin + rediacc-ci-cd) must still PASS"
    assert_contains "$r" "autopilot absent" "a pass must state what it checked"
    log_pass "the two legitimate bypass actors do not trip it (red carries information)"
}

test_empty_bypass_list_passes() {
    local r
    r="$(plant '{"id":99,"name":"Branch Protection","bypass_actors":[]}')"
    assert_eq "${r%%:*}" "0" "an empty bypass list is the ideal state and must pass"
    log_pass "an explicitly empty bypass_actors list passes"
}

test_unset_app_id_fails_rather_than_defaulting() {
    local rc=0
    env -u AUTOPILOT_APP_ID "$GATE" >/dev/null 2>&1 || rc=$?
    assert_eq "$rc" "1" "an unset AUTOPILOT_APP_ID must fail, not silently check nothing"
    log_pass "missing config fails closed instead of passing against no id"
}

test_blind_read_fails_closed
test_bypass_entry_is_caught
test_string_actor_id_still_matches
test_other_actors_are_not_false_positives
test_empty_bypass_list_passes
test_unset_app_id_fails_rather_than_defaulting

log_pass "all tests passed"

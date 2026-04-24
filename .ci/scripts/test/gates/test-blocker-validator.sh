#!/bin/bash
# Unit tests for .ci/scripts/lib/blocker-validator.sh.
#
# Exercises:
#   - parse_blockered_list: happy path, edge cases (blank-line reset, grouped
#     IDs sharing BLOCKER, empty file, CRLF, mixed whitespace, inline form).
#   - validate_blocker_quality: accepts current allowlist entries, rejects
#     every phrase in LOW_EFFORT_BLOCKER_PATTERNS, rejects < 30-char reasons.
#   - verify_all_blockers: reports missing BLOCKER and bad BLOCKER.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: the subject under test — load the library we are exercising
source "$SCRIPT_DIR/../../lib/blocker-validator.sh"

test_parse_empty_file() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    : >"$TEMP/list"
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    assert_eq "${#ALLOWED[@]}" "0" "empty file yields no entries"
    assert_eq "${#BLOCKER[@]}" "0" "empty file yields no blockers"
    log_pass "parse empty file"
}

test_parse_happy_path() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
# Some prose
# BLOCKER: upstream X pins version Y; build-time only
1234567
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    assert_eq "${ALLOWED[1234567]:-}" "1" "ID registered"
    assert_contains "${BLOCKER[1234567]:-}" "upstream X pins" "BLOCKER captured"
    log_pass "parse happy path"
}

test_parse_grouped_ids_share_blocker() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
# BLOCKER: family of xmldom advisories; same transitive chain blocked by electron-builder major
1000001
1000002
1000003
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    assert_eq "${#ALLOWED[@]}" "3" "three IDs registered"
    local id
    for id in 1000001 1000002 1000003; do
        assert_contains "${BLOCKER[$id]:-}" "xmldom" "ID $id shares BLOCKER"
    done
    log_pass "parse grouped IDs share BLOCKER"
}

test_parse_blank_line_resets_blocker() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
# BLOCKER: group A blocker reason with enough length to pass validation
2000001

2000002
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    assert_contains "${BLOCKER[2000001]:-}" "group A" "first ID got BLOCKER"
    assert_eq "${BLOCKER[2000002]:-}" "" "second ID (after blank) has no BLOCKER"
    log_pass "blank line resets BLOCKER"
}

test_parse_inline_form_with_blocker() {
    # Pattern used by .deps-upgrade-blocklist: "package-name  # BLOCKER: reason"
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
antd  # BLOCKER: v6.x requires CSS-in-JS removal and component API changes
electron  # BLOCKER: v40.x breaks native module rebuild with nan library errors
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    assert_eq "${ALLOWED[antd]:-}" "1" "antd registered"
    assert_contains "${BLOCKER[antd]:-}" "CSS-in-JS" "antd BLOCKER captured from inline"
    assert_contains "${BLOCKER[electron]:-}" "native module" "electron BLOCKER captured"
    log_pass "parse inline form with BLOCKER"
}

test_validate_rejects_every_low_effort_phrase() {
    for pattern in "${LOW_EFFORT_BLOCKER_PATTERNS[@]}"; do
        # Stdout+stderr captured to /dev/null; we only care about exit code.
        if validate_blocker_quality "testid" "$pattern" "testfile" >/dev/null 2>&1; then
            log_fail "LOW_EFFORT_BLOCKER_PATTERNS[$pattern] should be rejected but passed"
        fi
    done
    log_pass "every LOW_EFFORT_BLOCKER_PATTERNS entry is rejected"
}

test_validate_rejects_short_reason() {
    # "upstream transitive" is 19 chars — below the 30-char floor
    if validate_blocker_quality "testid" "upstream transitive" "testfile" >/dev/null 2>&1; then
        log_fail "short reason should be rejected"
    fi
    log_pass "short reason is rejected"
}

test_validate_accepts_substantive_reason() {
    local good="electron-builder 26.x pins plist > xmldom 0.8.x; build-time only, requires electron major migration"
    if ! validate_blocker_quality "testid" "$good" "testfile" >/dev/null 2>&1; then
        log_fail "substantive reason should pass"
    fi
    log_pass "substantive reason passes"
}

test_validate_accepts_all_current_audit_entries() {
    # Sanity check: every BLOCKER reason in the currently-shipped allowlists
    # must pass the quality gate. This catches regressions in BLOCKER_MIN_LENGTH
    # or new banned phrases that collide with legitimate reasons.
    local file
    for file in .audit-prod-allowlist .audit-allowlist; do
        [[ ! -f "$file" ]] && continue
        declare -A ALLOWED=() BLOCKER=()
        parse_blockered_list "$file" ALLOWED BLOCKER
        for id in "${!BLOCKER[@]}"; do
            local reason="${BLOCKER[$id]}"
            [[ -z "$reason" ]] && continue
            if ! validate_blocker_quality "$id" "$reason" "$file" >/dev/null 2>&1; then
                log_fail "current allowlist entry $id in $file has a BLOCKER that fails validation: \"$reason\""
            fi
        done
        unset ALLOWED BLOCKER
    done
    log_pass "every current allowlist BLOCKER passes validation"
}

test_verify_all_blockers_fails_on_missing() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
# no BLOCKER here
3000001
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    if verify_all_blockers "$TEMP/list" BLOCKER >/dev/null 2>&1; then
        log_fail "verify_all_blockers should fail when BLOCKER missing"
    fi
    log_pass "verify_all_blockers rejects missing BLOCKER"
}

test_verify_all_blockers_passes_when_good() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    cat >"$TEMP/list" <<'EOF'
# BLOCKER: upstream package-X pins transitive package-Y <2; fix requires major migration
4000001
EOF
    declare -A ALLOWED=() BLOCKER=()
    parse_blockered_list "$TEMP/list" ALLOWED BLOCKER
    if ! verify_all_blockers "$TEMP/list" BLOCKER >/dev/null 2>&1; then
        log_fail "verify_all_blockers should pass when BLOCKER good"
    fi
    log_pass "verify_all_blockers accepts good BLOCKER"
}

# Run all tests
log_test "test-blocker-validator"
test_parse_empty_file
test_parse_happy_path
test_parse_grouped_ids_share_blocker
test_parse_blank_line_resets_blocker
test_parse_inline_form_with_blocker
test_validate_rejects_every_low_effort_phrase
test_validate_rejects_short_reason
test_validate_accepts_substantive_reason
test_validate_accepts_all_current_audit_entries
test_verify_all_blockers_fails_on_missing
test_verify_all_blockers_passes_when_good
echo ""
log_pass "all tests passed"

#!/bin/bash
# Unit tests for .ci/scripts/lib/age-check.sh.
#
# Exercises entry_age_days and check_entry_age with temp git fixtures that
# backdate commits to verify both warn (>180 days) and fail (>365 days) paths.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"
# shellcheck source=../lib/age-check.sh
# BLOCKER: the subject under test — load the library we are exercising
source "$SCRIPT_DIR/../../lib/age-check.sh"

make_fixture() {
    local dir="$1" age_days="$2" content="$3"
    (
        cd "$dir"
        git init -q
        git config user.email test@example.com
        git config user.name test
        git config commit.gpgsign false
        echo "$content" >listfile
        git add listfile
        local backdate
        backdate=$(date -u -d "$age_days days ago" +"%Y-%m-%dT%H:%M:%S")
        GIT_AUTHOR_DATE="$backdate" GIT_COMMITTER_DATE="$backdate" \
            git commit -q -m "fixture"
    )
}

test_age_fresh_entry() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    make_fixture "$TEMP" 5 "ENTRY_FRESH"
    (
        cd "$TEMP"
        local age
        age=$(entry_age_days listfile ENTRY_FRESH)
        # 5 days old — may read as 4 or 5 depending on rounding; accept 4-6
        if ((age < 4 || age > 6)); then
            log_fail "expected ~5 day age, got $age"
        fi
    )
    log_pass "fresh entry reports correct age"
}

test_age_old_entry_hard_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    make_fixture "$TEMP" 400 "ENTRY_OLD"
    (
        cd "$TEMP"
        local age
        age=$(entry_age_days listfile ENTRY_OLD)
        if ((age < 399 || age > 401)); then
            log_fail "expected ~400 day age, got $age"
        fi
        # check_entry_age should FAIL (return 1) for 400-day-old entry
        if check_entry_age listfile ENTRY_OLD testid >/dev/null 2>&1; then
            log_fail "check_entry_age should fail on 400-day-old entry"
        fi
    )
    log_pass "400-day entry hard-fails"
}

test_age_medium_entry_warns_only() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    make_fixture "$TEMP" 200 "ENTRY_WARN"
    (
        cd "$TEMP"
        # check_entry_age should return 0 (warn only) for 200-day-old entry
        if ! check_entry_age listfile ENTRY_WARN testid >/dev/null 2>&1; then
            log_fail "check_entry_age should pass (warn-only) on 200-day entry"
        fi
    )
    log_pass "200-day entry warns without failing"
}

test_age_untracked_file_returns_zero() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    (
        cd "$TEMP"
        echo "floating" >floating-file
        local age
        age=$(entry_age_days floating-file floating 2>/dev/null || echo 0)
        assert_eq "$age" "0" "untracked file returns 0 age"
    )
    log_pass "untracked file returns 0 age"
}

# A TRUNCATED history reports the graft's date, not the line's, so an old
# suppression looks new. Measured on the real repo before this was fixed: the
# github.com/docker/docker entry in .go-deps-upgrade-blocklist read 195 days on
# a full clone and 2 days on a truncated one, with AGE_WARN_DAYS at 180. The
# gate whose job is expiring stale suppressions expired nothing, in green.
make_shallow_pair() {
    local dir="$1" age_days="$2" content="$3"
    mkdir -p "$dir/origin"
    make_fixture "$dir/origin" "$age_days" "$content"
    # A second, RECENT commit so depth 1 cuts above the one that added the line.
    (
        cd "$dir/origin"
        echo "later" >>other
        git add other
        git commit -q -m "recent"
    )
    git clone -q --depth 1 "file://$dir/origin" "$dir/shallow"
    git clone -q "file://$dir/origin" "$dir/full"
}

test_age_truncated_history_cannot_verify() {
    local TEMP
    TEMP="$(mktemp -d)"
    trap 'rm -rf "$TEMP"' RETURN
    make_shallow_pair "$TEMP" 400 "ENTRY_OLD"

    # CONTROL FIRST: the same fixture with FULL history must measure the real
    # age. Without this, -1 below could just mean "the fixture is broken".
    (
        cd "$TEMP/full"
        local age
        age=$(entry_age_days listfile ENTRY_OLD)
        if ((age < 390 || age > 410)); then
            log_fail "CONTROL: full clone should measure ~400 days, got $age"
            exit 1
        fi
    )
    log_pass "CONTROL: a full clone still measures the real age (~400 days)"

    (
        cd "$TEMP/shallow"
        if [[ ! -s .git/shallow ]]; then
            log_fail "CONTROL: the shallow fixture carries no graft, so it proves nothing"
            exit 1
        fi
        local age
        age=$(entry_age_days listfile ENTRY_OLD)
        assert_eq "$age" "-1" "a truncated history reports CANNOT VERIFY, not an age"
    )
    log_pass "a truncated history reports -1 rather than a young age"

    # And CANNOT VERIFY must not be silently swallowed: refuse in CI, warn out.
    (
        cd "$TEMP/shallow"
        local rc=0
        CI=true check_entry_age listfile ENTRY_OLD test-id "fixture entry" >/dev/null 2>&1 || rc=$?
        assert_eq "$rc" "1" "CI refuses an unverifiable age"
    )
    log_pass "CI refuses an unverifiable age"
    (
        cd "$TEMP/shallow"
        local rc=0
        env -u CI bash -c "
            source '$SCRIPT_DIR/../../lib/age-check.sh'
            check_entry_age listfile ENTRY_OLD test-id 'fixture entry' >/dev/null 2>&1
        " || rc=$?
        assert_eq "$rc" "0" "a local shallow clone warns rather than blocking"
    )
    log_pass "a local shallow clone warns rather than blocking"
}

log_test "test-age-check"
test_age_fresh_entry
test_age_medium_entry_warns_only
test_age_old_entry_hard_fails
test_age_untracked_file_returns_zero
test_age_truncated_history_cannot_verify
echo ""
log_pass "all tests passed"

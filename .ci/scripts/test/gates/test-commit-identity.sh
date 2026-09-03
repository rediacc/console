#!/bin/bash
# Drives the REAL .ci/scripts/quality/check-commit-identity.sh against a fake `gh`.
#
# THAT GATE'S VERDICT IS AN API ANSWER, so the only way to test it without a live PR
# is to control what the API says. A fake `gh` on PATH serves fixture JSON and applies
# the caller's own --jq to it, which is the pattern test-review-status.sh already uses.
#
# WHAT IT GUARDS. 30 of 42 commits on branch 0903-1 carried an email GitHub does not
# link to the operator's account -- same display name as the good ones, so `git log`
# looked clean, while GitHub rendered them with no avatar and no contribution credit.
# Fixing it cost a history rewrite across four repositories.
#
# THE CASES THAT MATTER MOST are the ones where a wrong gate would be QUIET: an empty
# commit list, a failed `gh`, and a truncated page. Each of those is a way to inspect
# nothing and print a checkmark, which is the exact shape check-claude-attribution.sh
# was repaired for.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-commit-identity.sh"
[[ -x "$GATE" ]] || log_fail "gate not found at $GATE; this file would assert nothing"

# A fake `gh` that prints $FIXTURE for `api …/commits` and applies the caller's --jq.
# `exit_rc` lets a case simulate a rate limit or a network failure.
write_fake_gh() { # write_fake_gh <dir> <fixture-file> [exit_rc]
    local dir="$1" fixture="$2" rc="${3:-0}"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<FAKE
#!/bin/bash
set -uo pipefail
[ "$rc" -ne 0 ] && { echo "simulated gh failure" >&2; exit $rc; }
jqexpr=""
prev=""
for a in "\$@"; do
  [ "\$prev" = "--jq" ] && jqexpr="\$a"
  prev="\$a"
done
if [ -n "\$jqexpr" ]; then jq -r "\$jqexpr" <"$fixture"; else cat "$fixture"; fi
FAKE
    chmod +x "$dir/bin/gh"
}

# One commit object. `author`/`committer` are the GitHub ACCOUNTS, null when the email
# resolves to nobody -- which is the whole subject of the gate.
commit_json() { # commit_json <sha> <author-login|null> <committer-login|null> <email>
    local a="$1" login="$2" clogin="$3" email="$4"
    local au clu
    [ "$login" = "null" ] && au=null || au="{\"login\":\"$login\"}"
    [ "$clogin" = "null" ] && clu=null || clu="{\"login\":\"$clogin\"}"
    printf '{"sha":"%s","author":%s,"committer":%s,"commit":{"author":{"email":"%s","name":"N"}}}' \
        "$a" "$au" "$clu" "$email"
}

run_gate() { # run_gate <fixture-json> [gh_exit_rc] -> LAST_OUT, returns rc
    local body="$1" ghrc="${2:-0}" d rc=0
    d="$(mktemp -d)"
    printf '[%s]' "$body" >"$d/fixture.json"
    write_fake_gh "$d" "$d/fixture.json" "$ghrc"
    LAST_OUT="$(PATH="$d/bin:$PATH" GITHUB_TOKEN=x PR_NUMBER=1 \
        GITHUB_REPOSITORY=rediacc/console bash "$GATE" 2>&1)" || rc=$?
    rm -rf "$d"
    return "$rc"
}

# ── 1. THE PLANT: an unattributed author is named ─────────────────────────
test_null_author_fails() {
    local rc=0
    run_gate "$(commit_json 0d6611aaaa null mfbayraktar muhammed@rediacc.com)" || rc=$?
    assert_exit_code 1 "$rc" "a commit GitHub attributes to nobody must fail"
    assert_contains "$LAST_OUT" "0d6611a" "naming the sha"
    assert_contains "$LAST_OUT" "muhammed@rediacc.com" "and the email"
    log_pass "an unattributed author is reported by sha and address"
}

# ── 2. CONTROL: an attributed commit passes ───────────────────────────────
test_attributed_passes() {
    local rc=0
    run_gate "$(commit_json 1111111aaa mfbayraktar mfbayraktar mfbayraktar@live.com)" || rc=$?
    assert_exit_code 0 "$rc" "a fully attributed commit must pass, or every PR fails forever"
    assert_contains "$LAST_OUT" "all attributed" "and say what it cleared"
    log_pass "CONTROL: an attributed commit passes, so case 1 means something"
}

# ── 3. Bots attribute, and must not need a special case ───────────────────
# main carries github-actions[bot] commits. If they failed, the gate could never
# run on main and someone would add an exemption for a non-problem.
test_bot_passes() {
    local rc=0
    run_gate "$(commit_json 2222222aaa 'github-actions[bot]' 'github-actions[bot]' \
        'github-actions[bot]@users.noreply.github.com')" || rc=$?
    assert_exit_code 0 "$rc" "a bot commit resolves to an account and must pass"
    log_pass "bot commits pass without an exemption"
}

# ── 4. The COMMITTER half is judged too ───────────────────────────────────
# The 30 real commits had both fields wrong together, which is exactly how a
# committer-only defect would have been missed if only the author were checked.
test_null_committer_fails() {
    local rc=0
    run_gate "$(commit_json 3333333aaa mfbayraktar null mfbayraktar@live.com)" || rc=$?
    assert_exit_code 1 "$rc" "an unattributed COMMITTER must fail even when the author is fine"
    log_pass "the committer field is judged, not just the author"
}

# ── 5-7. The QUIET failures: ways to inspect nothing and print a checkmark ─
test_empty_list_refuses() {
    local rc=0
    run_gate "" || rc=$?
    assert_exit_code 1 "$rc" "an EMPTY commit list is a failed read, not a clean PR"
    assert_contains "$LAST_OUT" "empty" "and say so"
    log_pass "an empty commit list refuses instead of passing vacuously"
}

test_gh_failure_refuses() {
    local rc=0
    run_gate "$(commit_json 4444444aaa mfbayraktar mfbayraktar ok@example.com)" 1 || rc=$?
    assert_exit_code 1 "$rc" "a failed gh call must refuse, never report clean"
    assert_contains "$LAST_OUT" "Cannot certify" "with the fail-closed wording"
    log_pass "an unreadable API refuses rather than clearing the PR"
}

test_page_cap_refuses() {
    local body="" i rc=0
    for i in $(seq 1 250); do
        [[ -n "$body" ]] && body+=","
        body+="$(commit_json "$(printf 'c%09d' "$i")" mfbayraktar mfbayraktar ok@example.com)"
    done
    run_gate "$body" || rc=$?
    assert_exit_code 1 "$rc" "at the 250 page cap the set may be truncated and cannot be cleared"
    assert_contains "$LAST_OUT" "page cap" "naming the cap"
    log_pass "a possibly-truncated commit list is refused, not judged in part"
}

# ── 8. CONTROL over the whole file: the fake must be what decides ─────────
# Cases 1 and 2 differ ONLY in the fixture. If both gave the same verdict the fake
# would not be reaching the gate and every case above would be theatre.
test_control_fixture_decides() {
    local a=0 b=0
    run_gate "$(commit_json 5555555aaa null mfbayraktar bad@example.com)" || a=$?
    run_gate "$(commit_json 5555555aaa mfbayraktar mfbayraktar good@example.com)" || b=$?
    [ "$a" -eq 1 ] && [ "$b" -eq 0 ] ||
        log_fail "CONTROL: fixtures gave rc=$a and rc=$b; the fake gh is not deciding the verdict"
    log_pass "CONTROL: the fixture, and nothing else, flips the verdict"
}

log_test "test-commit-identity"
test_null_author_fails
test_attributed_passes
test_bot_passes
test_null_committer_fails
test_empty_list_refuses
test_gh_failure_refuses
test_page_cap_refuses
test_control_fixture_decides

echo ""
log_pass "all tests passed"

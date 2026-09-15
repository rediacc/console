#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: none
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
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

# A fake `gh` that ROUTES BY URL and applies the caller's --jq to the matching
# fixture. Two shapes now, because the gate reads the PR object for the compare
# range and its commit count, then the compare endpoint for the commits. A
# single-fixture fake would feed the commit list to the metadata read and the
# gate would refuse every case for the wrong reason.
# `exit_rc` lets a case simulate a rate limit or a network failure.
write_fake_gh() { # write_fake_gh <dir> <meta-file> <compare-file> [exit_rc]
    local dir="$1" meta="$2" compare="$3" rc="${4:-0}"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<FAKE
#!/bin/bash
set -uo pipefail
[ "$rc" -ne 0 ] && { echo "simulated gh failure" >&2; exit $rc; }
jqexpr=""
prev=""
url=""
for a in "\$@"; do
  [ "\$prev" = "--jq" ] && jqexpr="\$a"
  case "\$a" in repos/*) [ -z "\$url" ] && url="\$a" ;; esac
  prev="\$a"
done
case "\$url" in
  */compare/*) fixture="$compare" ;;
  *)           fixture="$meta" ;;
esac
# -c MATTERS: real \`gh --jq\` emits ONE COMPACT OBJECT PER LINE, and the gate's
# commit count is \`grep -c .\` over exactly that. A bare \`jq -r\` pretty-prints,
# which made this fake report 7 "commits" for a single commit -- invisible while
# the only consumer was a 250 cap, fatal to a count that must be exact.
if [ -n "\$jqexpr" ]; then jq -r -c "\$jqexpr" <"\$fixture"; else cat "\$fixture"; fi
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

# <declared-count> defaults to the number of commits in the body, so every case
# except the short-read one states a PR whose count MATCHES what it serves.
run_gate() { # run_gate <fixture-json> [gh_exit_rc] [declared-count] -> LAST_OUT, returns rc
    local body="$1" ghrc="${2:-0}" declared="${3:-}" d rc=0 n
    d="$(mktemp -d)"
    printf '{"commits":[%s]}' "$body" >"$d/compare.json"
    n="$(jq '.commits | length' <"$d/compare.json")"
    [[ -z "$declared" ]] && declared="$n"
    printf '{"base":{"sha":"base0000"},"head":{"sha":"head0000"},"commits":%s}' \
        "$declared" >"$d/meta.json"
    write_fake_gh "$d" "$d/meta.json" "$d/compare.json" "$ghrc"
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
    # `rc=1` ALONE IS NOT THIS CASE. The gate exits 1 for an unreadable API, a
    # missing token and a failed probe too, so without naming the finding this
    # case passed whenever anything at all went wrong.
    assert_contains "$LAST_OUT" "does not attribute to any account" \
        "and it must fail FOR the unattributed commit, not for some other reason"
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

# A SHORT READ is refused -- the shape that replaced the old 250 page cap. The
# cap could only notice truncation at one number; this notices it at any.
test_short_read_refuses() {
    local rc=0
    run_gate "$(commit_json 6666666aaa mfbayraktar mfbayraktar ok@example.com)" 0 3 || rc=$?
    assert_exit_code 1 "$rc" "reading 1 of a declared 3 commits cannot clear the PR"
    assert_contains "$LAST_OUT" "read 1 commit(s)" "naming what it actually read"
    assert_contains "$LAST_OUT" "the PR reports 3" "and what the PR says it should have"
    log_pass "an incomplete commit list is refused, not judged in part"
}

# MIRROR, and the regression this whole endpoint change exists to prevent: a PR
# LARGER than the old 250 cap must now be judged, not refused. Before the change
# this exact fixture produced "Cannot certify" on every run, which is how a
# 254-commit PR came to have two unattributed commits nobody could see.
test_over_the_old_cap_is_judged() {
    local body="" i rc=0
    for ((i = 1; i <= 254; i++)); do
        [[ -n "$body" ]] && body+=","
        body+="$(commit_json "$(printf 'c%09d' "$i")" mfbayraktar mfbayraktar ok@example.com)"
    done
    run_gate "$body" || rc=$?
    assert_exit_code 0 "$rc" "254 complete commits must be JUDGED; refusing on size is the bug"
    assert_contains "$LAST_OUT" "254 commit(s), all attributed" "and say how many it cleared"
    log_pass "a PR over the retired 250 cap is judged rather than refused"
}

# And the plant inside that same over-cap set: one bad commit among 254 must
# still be named. A completeness check that passed the set through without
# judging it would look identical to the case above.
test_over_the_old_cap_still_finds_the_offender() {
    local body="" i rc=0
    for ((i = 1; i <= 253; i++)); do
        body+="$(commit_json "$(printf 'c%09d' "$i")" mfbayraktar mfbayraktar ok@example.com),"
    done
    body+="$(commit_json 917d1902dd null null muhammed@rediacc.com)"
    run_gate "$body" || rc=$?
    assert_exit_code 1 "$rc" "one unattributed commit among 254 must still fail"
    assert_contains "$LAST_OUT" "917d190" "naming the sha"
    assert_contains "$LAST_OUT" "muhammed@rediacc.com" "and the address"
    log_pass "PLANT: an offender hidden in a 254-commit PR is found"
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
test_short_read_refuses
test_over_the_old_cap_is_judged
test_over_the_old_cap_still_finds_the_offender
test_control_fixture_decides

echo ""
log_pass "all tests passed"

#!/bin/bash
# Pin the security property of .ci/breakpoint/scripts/select-mode.sh:
# NAMED MODE NEVER SILENTLY DEGRADES TO QUICK MODE.
#
# quick and named are not two grades of the same thing. In quick mode the random
# *.trycloudflare.com URL is the ONLY thing protecting a runner that holds the
# repo source and, with debug-shell on, an interactive shell. In named mode the
# hostname is derived from a public run id, so it is guessable by anyone reading
# the Actions tab, and Cloudflare Access -- not obscurity -- is the control.
#
# So a named-mode request that cannot be honoured has exactly one correct
# outcome: fail, loudly, with EMPTY STDOUT. Falling back would drop
# authentication at the moment nobody is looking, and the caller downstream
# would happily start a tunnel on the word it read. Empty stdout is asserted
# directly for that reason: a caller doing MODE=$(select-mode.sh) with a
# half-failed script must get nothing rather than something.
#
# The reverse also matters and is asserted here: an explicit `--mode quick`
# stays quick even when named-mode credentials are sitting in the environment.
# A silent upgrade creates Cloudflare-side objects the operator did not ask for
# and does not know to clean up.
#
# The last-wins quirk of parse_args (`--mode named --mode quick` => quick) is
# pinned too, not because it is good, but because breakpoint-common.sh documents
# it as deliberate and something must fail if a future edit makes repeated flags
# accumulate instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SELECT="$REPO_ROOT/.ci/breakpoint/scripts/select-mode.sh"

[[ -x "$SELECT" ]] || log_fail "subject under test is missing or not executable: $SELECT"

# Credentials that make named mode configurable. The zone comes from
# breakpoint.conf, so only these two are environment-supplied.
readonly FAKE_TOKEN="BREAKPOINT_TUNNEL_TOKEN=not-a-real-token"
readonly FAKE_ACCOUNT="CLOUDFLARE_ACCOUNT_ID=0000000000000000000000000000dead"

# select_mode <tmp> [ENV=val ...] -- [--] [args...]
# Publishes SEL_RC / SEL_OUT (stdout only) / SEL_ERR (stderr, LOWERCASED).
#
# Globals rather than a return value on purpose: reading the result back through
# command substitution would run this in a subshell and throw the exit code
# away, which is how an exit-code assertion silently compares 0 against 0.
SEL_RC=0
SEL_OUT=""
SEL_ERR=""
select_mode() {
    local tmp="$1"
    shift
    local -a envs=()
    while (($# > 0)); do
        [[ "$1" == "--" ]] && {
            shift
            break
        }
        envs+=("$1")
        shift
    done
    local errfile="$tmp/stderr.$$"
    SEL_RC=0
    SEL_OUT="$(env -i PATH="$PATH" HOME="$tmp" RUNNER_TEMP="$tmp" "${envs[@]}" \
        bash "$SELECT" "$@" 2>"$errfile")" || SEL_RC=$?
    SEL_ERR="$(tr '[:upper:]' '[:lower:]' <"$errfile")"
    rm -f "$errfile"
}

# =============================================================================
# THE HEADLINE PROPERTY
# =============================================================================
test_named_without_credentials_fails_hard() {
    local tmp="$1"
    select_mode "$tmp" -- --mode named

    assert_exit_code 3 "$SEL_RC" "named mode with no credentials must fail"
    assert_eq "$SEL_OUT" "" "a failed selection must put NOTHING on stdout"
    # Lowercased in the helper so this catches the real message too, which
    # shouts "FALLING BACK TO QUICK MODE" in capitals -- a case-sensitive check
    # for the lowercase spelling would pass while the script fell back.
    assert_not_contains "$SEL_ERR" "falling back" "named mode must not fall back silently"
    # The message must EXPLAIN, not just exit non-zero. Asserting on
    # "unauthenticated" rather than the old "refusing to fall back" wording:
    # there is no fallback to refuse any more, so the reason is now the property
    # that makes downgrading wrong in the first place.
    assert_contains "$SEL_ERR" "unauthenticated" "the refusal must say WHY quick is not an acceptable substitute"
    log_pass "named without credentials: exit 3, empty stdout, no fallback"
}

test_named_half_configured_still_fails() {
    local tmp="$1"
    # Token present, account id missing. The dangerous shape: it LOOKS
    # configured to a reader, and a script that only checked the token would
    # proceed into a broken API call and then "recover" into quick mode.
    select_mode "$tmp" "$FAKE_TOKEN" -- --mode named
    assert_exit_code 3 "$SEL_RC" "named mode with only a token must fail"
    assert_eq "$SEL_OUT" "" "half-configured named mode must produce no stdout"
    assert_contains "$SEL_ERR" "cloudflare_account_id" "the error must name the missing piece"

    # And the mirror: account id present, token missing.
    select_mode "$tmp" "$FAKE_ACCOUNT" -- --mode named
    assert_exit_code 3 "$SEL_RC" "named mode with only an account id must fail"
    assert_contains "$SEL_ERR" "breakpoint_tunnel_token" "the error must name the missing piece"
    log_pass "half-configured named mode fails on either missing half"
}

test_named_fully_configured_succeeds() {
    local tmp="$1"
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" -- --mode named
    assert_exit_code 0 "$SEL_RC" "fully configured named mode must succeed: $SEL_ERR"
    assert_eq "$SEL_OUT" "named" "stdout must be exactly the word 'named'"
    log_pass "fully configured named mode prints exactly 'named'"
}

# =============================================================================
# EXPLICIT REQUESTS WIN IN BOTH DIRECTIONS
# =============================================================================
test_quick_without_credentials() {
    local tmp="$1"
    select_mode "$tmp" -- --mode quick
    assert_exit_code 0 "$SEL_RC" "quick mode needs no credentials"
    assert_eq "$SEL_OUT" "quick" "stdout must be exactly the word 'quick'"
    log_pass "quick without credentials prints exactly 'quick'"
}

test_quick_with_credentials_is_not_upgraded() {
    local tmp="$1"
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" -- --mode quick
    assert_exit_code 0 "$SEL_RC" "an explicit quick request must succeed"
    assert_eq "$SEL_OUT" "quick" "credentials being present must not silently upgrade to named"
    # It should still SAY the credentials went unused, or a run in the wrong
    # mode is indistinguishable in the log from one that asked for it.
    assert_contains "$SEL_ERR" "unused" "the log must note that named credentials were ignored"
    log_pass "quick WITH credentials stays quick (no silent upgrade)"
}

test_default_is_quick_not_auto() {
    local tmp="$1"
    # No --mode at all, with credentials present. If the default were `auto`
    # this would print `named`; the safe default is the one that needs no
    # secrets and creates no account-side state.
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" --
    assert_exit_code 0 "$SEL_RC" "the no-flag default must succeed"
    assert_eq "$SEL_OUT" "quick" "the default must be quick, NOT auto"
    log_pass "no --mode flag defaults to quick, not auto"
}

# =============================================================================
# AUTO IS THE ONLY MODE PERMITTED TO CHOOSE
# =============================================================================
test_auto_with_credentials_picks_named() {
    local tmp="$1"
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" -- --mode auto
    assert_exit_code 0 "$SEL_RC" "auto with credentials must succeed"
    assert_eq "$SEL_OUT" "named" "auto must prefer the authenticated mode when it can"
    log_pass "auto with credentials selects named"
}

test_auto_without_credentials_warns() {
    local tmp="$1"
    select_mode "$tmp" -- --mode auto
    assert_exit_code 0 "$SEL_RC" "auto without credentials must still succeed"
    assert_eq "$SEL_OUT" "quick" "auto must fall through to quick"
    # The warning is the whole difference between auto and a silent downgrade.
    assert_contains "$SEL_ERR" "unauthenticated" "auto must announce that the session is unauthenticated"
    assert_contains "$SEL_ERR" "not configured" "auto must say what was missing"
    log_pass "auto without credentials selects quick AND warns it is unauthenticated"
}

# =============================================================================
# ARGUMENT HANDLING
# =============================================================================
test_repeated_mode_flag_is_last_wins() {
    local tmp="$1"
    # parse_args eval-assigns the same variable name per flag, so repeats
    # overwrite rather than accumulate. Pinned so nobody later writes a script
    # that expects `--mode a --mode b` to mean "a and b" or to be an error.
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" -- --mode named --mode quick
    assert_exit_code 0 "$SEL_RC" "a repeated flag must not be an error"
    assert_eq "$SEL_OUT" "quick" "repeated flags are LAST-WINS, not accumulate"

    # ...and in the other order, so this is a real ordering pin and not a test
    # that would pass on any single-valued behaviour.
    select_mode "$tmp" "$FAKE_TOKEN" "$FAKE_ACCOUNT" -- --mode quick --mode named
    assert_eq "$SEL_OUT" "named" "last-wins holds in both orders"
    log_pass "repeated --mode is last-wins in both orders"
}

test_invalid_mode_rejected() {
    local tmp="$1"
    select_mode "$tmp" -- --mode sneaky
    assert_exit_code 4 "$SEL_RC" "an unknown mode must be rejected"
    assert_eq "$SEL_OUT" "" "a rejected mode must produce no stdout"
    # Listing the valid ones is what turns a typo into a ten-second fix.
    assert_contains "$SEL_ERR" "quick" "the error must list the valid modes"
    assert_contains "$SEL_ERR" "named" "the error must list the valid modes"
    assert_contains "$SEL_ERR" "auto" "the error must list the valid modes"
    log_pass "an invalid mode exits 4 and lists quick, named, auto"
}

# =============================================================================
# THERE IS NO ESCAPE HATCH -- NAMED NEVER DOWNGRADES
# =============================================================================
# This replaces a test for `--allow-fallback`, a flag that let named mode
# silently become quick mode. The flag was removed, and this proves the removal
# rather than merely deleting its test: a deleted test and a removed feature
# look identical in a diff, and only one of them is safe.
#
# The old flag carried its own refusal for debug-shell/desktop sessions, which
# was the tell -- the guard existed because the downgrade was already known to
# be dangerous, and it narrowed the blast radius instead of removing it.
test_named_never_falls_back_to_quick() {
    local tmp="$1"

    # The flag itself must be GONE, not merely defaulted off. A flag that still
    # parses can be passed by a vendored workflow that was not updated.
    if grep -q 'allow-fallback' "$SELECT" && ! grep -q '# .*allow-fallback' "$SELECT"; then
        log_fail "select-mode.sh still handles --allow-fallback; the downgrade path is reachable"
    fi

    # An unconfigured named request fails, and emits NOTHING on stdout. Empty
    # stdout is the load-bearing half: callers do `MODE=$(select-mode.sh ...)`,
    # so a stray "quick" on stdout would be consumed as a successful choice.
    select_mode "$tmp" -- --mode named
    assert_exit_code 3 "$SEL_RC" "an unconfigurable named request must fail, not downgrade"
    assert_eq "$SEL_OUT" "" "a refusal must produce EMPTY stdout, or the caller consumes it as a mode"
    assert_not_contains "$SEL_ERR" "falling back" "the word 'falling back' must not appear: there is no fallback"

    # ...and passing the removed flag must not resurrect the behaviour. Whether
    # it errors on the unknown flag or ignores it, what it must NEVER do is
    # print "quick" and exit 0.
    select_mode "$tmp" -- --mode named --allow-fallback
    assert_eq "$SEL_OUT" "" "the removed flag must not produce a mode on stdout"
    [[ "$SEL_RC" -ne 0 ]] || log_fail "passing the removed --allow-fallback still exits 0 -- the downgrade survived"

    # Same with an interactive session, which is the case that most needs auth.
    select_mode "$tmp" "BREAKPOINT_DEBUG_SHELL=true" -- --mode named
    assert_exit_code 3 "$SEL_RC" "named + debug-shell must fail rather than downgrade"
    assert_eq "$SEL_OUT" "" "no stdout on refusal"

    log_pass "named mode never downgrades to quick, with or without the removed flag"
}

with_temp_dir test_named_without_credentials_fails_hard
with_temp_dir test_named_half_configured_still_fails
with_temp_dir test_named_fully_configured_succeeds
with_temp_dir test_quick_without_credentials
with_temp_dir test_quick_with_credentials_is_not_upgraded
with_temp_dir test_default_is_quick_not_auto
with_temp_dir test_auto_with_credentials_picks_named
with_temp_dir test_auto_without_credentials_warns
with_temp_dir test_repeated_mode_flag_is_last_wins
with_temp_dir test_invalid_mode_rejected
# =============================================================================
# NAMED MODE REFUSES A DURATION TOO SHORT TO LOG IN
# =============================================================================
# Regression test for a real session. Named mode fronts the box with Cloudflare
# Access, whose one-time-PIN login is TWO email round trips. Teardown deletes
# the Access application the instant the timer expires, so run 30259141278
# (duration 5) died mid-login and Cloudflare answered:
#
#   That account does not have access.
#
# ...which blames the policy, the one component that was correct. The operator
# went looking for a permissions bug that did not exist. This guard turns a
# misleading runtime failure into an accurate refusal before anything is built.
test_named_refuses_too_short_a_duration() {
    local tmp="$1" rc
    local pre="$REPO_ROOT/.ci/breakpoint/scripts/preflight-breakpoint.sh"

    run_pre() {
        rc=0
        env RUNNER_TEMP="$tmp" GITHUB_RUN_ID=1 BP_ACTOR=mfbayraktar \
            BP_RUNNER=ubuntu-latest BP_LABEL=rdc-ci BP_MODE="$1" BP_DURATION="$2" \
            bash "$pre" >/dev/null 2>&1 || rc=$?
    }

    run_pre named 5
    [[ "$rc" -ne 0 ]] || log_fail "named mode accepted a 5-minute duration; the session would be torn down mid-login"

    run_pre named 15
    assert_exit_code 0 "$rc" "named mode must accept the documented 15-minute minimum"

    # Quick mode has NO login step, so a short session is legitimate there. If
    # this ever fails the guard has been applied too broadly.
    run_pre quick 5
    assert_exit_code 0 "$rc" "quick mode must still allow short sessions (it has no login step)"

    log_pass "named mode requires >= 15m; quick mode is unaffected"
}

with_temp_dir test_named_never_falls_back_to_quick
with_temp_dir test_named_refuses_too_short_a_duration

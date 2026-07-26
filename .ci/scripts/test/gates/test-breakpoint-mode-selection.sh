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
    assert_contains "$SEL_ERR" "refusing to fall back" "the refusal must say why"
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
# THE ESCAPE HATCH HAS ITS OWN LIMIT
# =============================================================================
test_allow_fallback_refused_for_interactive_sessions() {
    local tmp="$1"

    # Baseline: with no shell and no desktop, the explicit escape hatch works.
    # Without this control the two refusals below would pass even if
    # --allow-fallback were broken outright.
    select_mode "$tmp" -- --mode named --allow-fallback
    assert_exit_code 0 "$SEL_RC" "--allow-fallback must work for a plain web origin"
    assert_eq "$SEL_OUT" "quick" "--allow-fallback yields quick"
    assert_contains "$SEL_ERR" "no access authentication" "the fallback must be announced loudly"

    # An unauthenticated tunnel to a web app is a bad day. An unauthenticated
    # tunnel to an interactive shell on a runner holding the repo source is a
    # different category, so the hatch is closed there.
    select_mode "$tmp" "BREAKPOINT_DEBUG_SHELL=true" -- --mode named --allow-fallback
    assert_exit_code 3 "$SEL_RC" "--allow-fallback must be REFUSED with debug-shell on"
    assert_eq "$SEL_OUT" "" "a refused fallback must produce no stdout"
    assert_contains "$SEL_ERR" "refused" "the refusal must be explicit"

    select_mode "$tmp" "BREAKPOINT_DESKTOP=xfce" -- --mode named --allow-fallback
    assert_exit_code 3 "$SEL_RC" "--allow-fallback must be REFUSED with a desktop enabled"
    assert_eq "$SEL_OUT" "" "a refused fallback must produce no stdout"
    log_pass "--allow-fallback works for a web origin but is refused for shell/desktop"
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
with_temp_dir test_allow_fallback_refused_for_interactive_sessions

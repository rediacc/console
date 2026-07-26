#!/bin/bash
# Pin the tunnel-naming grammar produced by
# .ci/breakpoint/scripts/derive-descriptor.sh.
#
# WHY A GATE AND NOT A COMMENT
# The name is the only DURABLE channel breakpoint has. A session's state file
# lives on a runner that can vanish (force-cancel and infra loss both skip
# `if: always()` entirely), so cleanup cannot depend on it. What cleanup CAN
# depend on is that the tunnel name is a pure function of $GITHUB_RUN_ID:
# reap-breakpoint-orphans.sh lists Cloudflare's own objects, parses the run id
# back out of each name, and asks GitHub whether that run has finished.
#
# That machinery breaks SILENTLY if the grammar drifts by one byte -- the
# sweeper simply stops matching, no error anywhere, and the orphaned tunnels
# accumulate until somebody notices the bill. So the exact strings are asserted
# here, and so are the two refusals (empty run id, unlisted label) that exist
# specifically to stop an unsweepable name from ever being minted.
#
# Grammar under test:
#   tunnel name  breakpoint-<label>-<run-id>
#   hostname     <label>-<run-id>.<zone>
#   url          https://<hostname>
#   DNS label capped at 63 octets (RFC 1035)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

DERIVE="$REPO_ROOT/.ci/breakpoint/scripts/derive-descriptor.sh"

[[ -x "$DERIVE" ]] || log_fail "subject under test is missing or not executable: $DERIVE"

# The zone every expectation below is written against. Asserted rather than
# read, so a conf change that moves the zone shows up HERE (where the hostname
# expectations live) instead of as a mystery DNS failure at session start.
readonly EXPECTED_ZONE="rediacc.io"

# derive <tmp> <args...> -- run the subject with a scrubbed environment and a
# private state dir, and publish the three results as GLOBALS.
#
# Deliberately NOT a function whose result is read back through command
# substitution: that runs the function in a SUBSHELL, so an exit code assigned
# inside it never reaches the caller, and every assert_exit_code then compares
# the initial value against itself. The first draft of this file did exactly
# that and printed three green exit-code assertions that checked nothing.
DERIVE_RC=0
DERIVE_OUT=""
DERIVE_ERR=""
derive() {
    local tmp="$1"
    shift
    local errfile
    errfile="$tmp/stderr.$$"
    DERIVE_RC=0
    DERIVE_OUT="$(env -i PATH="$PATH" HOME="$tmp" RUNNER_TEMP="$tmp" \
        bash "$DERIVE" "$@" 2>"$errfile")" || DERIVE_RC=$?
    DERIVE_ERR="$(cat "$errfile")"
    rm -f "$errfile"
}

# =============================================================================
test_zone_is_what_the_expectations_assume() {
    local conf
    conf="$(cat "$REPO_ROOT/.ci/breakpoint/breakpoint.conf")"
    assert_contains "$conf" "BREAKPOINT_TUNNEL_ZONE=\"$EXPECTED_ZONE\"" \
        "the hostname expectations in this file are written against $EXPECTED_ZONE"
    log_pass "breakpoint.conf zone is $EXPECTED_ZONE (the hostname expectations hold)"
}

test_exact_tunnel_name() {
    local tmp="$1" out
    derive "$tmp" --field name --label rdc-ci --run-id 12345678901
    out="$DERIVE_OUT"
    assert_exit_code 0 "$DERIVE_RC" "deriving a name for a valid run id"
    assert_eq "$out" "breakpoint-rdc-ci-12345678901" "tunnel-name grammar"
    log_pass "tunnel name is exactly breakpoint-<label>-<run-id>"
}

test_exact_hostname_and_url() {
    local tmp="$1" host url
    derive "$tmp" --field hostname --label rdc-dev --run-id 42
    host="$DERIVE_OUT"
    assert_eq "$host" "rdc-dev-42.$EXPECTED_ZONE" "hostname grammar"

    derive "$tmp" --field url --label rdc-dev --run-id 42

    url="$DERIVE_OUT"
    assert_eq "$url" "https://rdc-dev-42.$EXPECTED_ZONE" "url grammar"

    # First-level label by necessity: Universal SSL covers the apex and ONE
    # level, so a middle label would silently need paid Advanced Certificate
    # Manager. Counting dots is how that stays true.
    assert_eq "$(echo "$host" | tr -cd '.' | wc -c | tr -d ' ')" "2" \
        "hostname must be first-level (<label>.<zone>), not <label>.<sub>.<zone>"
    log_pass "hostname and url are exactly <label>-<run-id>.$EXPECTED_ZONE, first-level"
}

test_missing_run_id_refuses_and_invents_nothing() {
    local tmp="$1" out
    # No GITHUB_RUN_ID in the env (env -i guarantees it) and no --run-id.
    derive "$tmp" --field name --label rdc-ci
    out="$DERIVE_OUT"
    if [[ "$DERIVE_RC" -eq 0 ]]; then
        log_fail "missing run id must be a hard failure, got exit 0 with stdout '$out'"
    fi
    assert_eq "$out" "" "a refusal must put NOTHING on stdout"
    # 'breakpoint-rdc-ci-' with an empty component is the specific shape that
    # would match no sweep regex and orphan its objects forever.
    assert_not_contains "$out" "--" "an empty component must never be emitted"
    assert_not_contains "$out" "breakpoint-" "no partial name may leak to stdout"
    assert_contains "$DERIVE_ERR" "GITHUB_RUN_ID" "the refusal must name the missing variable"
    log_pass "unset run id exits non-zero with empty stdout and invents no value"
}

test_non_numeric_run_id_rejected() {
    local tmp="$1" out
    derive "$tmp" --field name --label rdc-ci --run-id "12345; rm -rf /"
    out="$DERIVE_OUT"
    assert_exit_code 4 "$DERIVE_RC" "a non-numeric run id must be rejected"
    assert_eq "$out" "" "rejected input must produce no stdout"

    derive "$tmp" --field name --label rdc-ci --run-id "abc"

    out="$DERIVE_OUT"
    assert_exit_code 4 "$DERIVE_RC" "an alphabetic run id must be rejected"
    log_pass "non-numeric run ids are rejected with exit 4 and empty stdout"
}

test_unlisted_label_rejected() {
    local tmp="$1" out
    # The sweeper's regex is BUILT from BREAKPOINT_TUNNEL_LABELS, so a label
    # that is used but not listed is invisible to cleanup permanently. Refusing
    # here is the only thing keeping that promise true.
    derive "$tmp" --field name --label rdc-notalabel --run-id 99
    out="$DERIVE_OUT"
    assert_exit_code 4 "$DERIVE_RC" "a label outside BREAKPOINT_TUNNEL_LABELS must be rejected"
    assert_eq "$out" "" "a rejected label must produce no stdout"
    assert_contains "$DERIVE_ERR" "BREAKPOINT_TUNNEL_LABELS" "the refusal must point at the closed set"

    # Control: the listed labels are all accepted, so the check above is a real
    # filter and not a script that rejects everything.
    local label
    for label in rdc-ci rdc-dev rdc-demo; do
        derive "$tmp" --field name --label "$label" --run-id 99
        out="$DERIVE_OUT"
        assert_exit_code 0 "$DERIVE_RC" "listed label '$label' must be accepted"
        assert_eq "$out" "breakpoint-${label}-99" "listed label '$label' name"
    done
    log_pass "unlisted labels rejected, all three listed labels accepted"
}

test_deterministic() {
    local tmp="$1" a b
    derive "$tmp" --field name --label rdc-ci --run-id 777
    a="$DERIVE_OUT"
    derive "$tmp" --field name --label rdc-ci --run-id 777
    b="$DERIVE_OUT"
    assert_eq "$a" "$b" "the same inputs must produce byte-identical output"
    [[ -n "$a" ]] || log_fail "deterministic check compared two EMPTY strings, which proves nothing"
    log_pass "derivation is idempotent: same inputs, byte-identical name ($a)"
}

test_different_runs_get_different_names() {
    local tmp="$1" a b
    derive "$tmp" --field name --label rdc-ci --run-id 1000
    a="$DERIVE_OUT"
    derive "$tmp" --field name --label rdc-ci --run-id 1001
    b="$DERIVE_OUT"
    if [[ "$a" == "$b" ]]; then
        log_fail "two run ids collided on '$a'; concurrent sessions would fight over one tunnel"
    fi
    log_pass "different run ids yield different names ($a vs $b)"
}

test_dns_label_capped_at_63() {
    local tmp="$1" host label raw i
    # An 80-digit run id is not realistic; the CAP is, and it has to be
    # exercised by an input that actually exceeds it -- a 40-digit id produces a
    # 49-octet label, so the truncation branch never runs and the assertion is
    # decorative. Over-long labels are rejected by the DNS API with a message
    # that does not point back here, so truncation must happen before the call.
    raw=""
    for ((i = 0; i < 80; i++)); do
        raw="${raw}7"
    done
    derive "$tmp" --field hostname --label rdc-demo --run-id "$raw"
    host="$DERIVE_OUT"
    assert_exit_code 0 "$DERIVE_RC" "an over-long descriptor must be truncated, not refused"
    label="${host%%.*}"
    assert_eq "${#label}" "63" "an over-long DNS label must be truncated to exactly the RFC 1035 cap"
    assert_eq "${label: -1}" "7" "truncation must not leave a trailing '-' (invalid in a DNS label)"
    log_pass "an 89-octet descriptor is truncated to a valid 63-octet DNS label"
}

test_zone_is_what_the_expectations_assume
with_temp_dir test_exact_tunnel_name
with_temp_dir test_exact_hostname_and_url
with_temp_dir test_missing_run_id_refuses_and_invents_nothing
with_temp_dir test_non_numeric_run_id_rejected
with_temp_dir test_unlisted_label_rejected
with_temp_dir test_deterministic
with_temp_dir test_different_runs_get_different_names
with_temp_dir test_dns_label_capped_at_63

#!/bin/bash
# Tests for .ci/scripts/quality/announce-gate-skips.sh, the step that makes a
# label-held gate VISIBLE.
#
# The thing under test is an instrument, so every case here is really a
# question about the instrument rather than about the gates it announces: can
# it fire (skip), can it stay quiet when it should (hard), does it fail closed
# when the wiring breaks (unset), and does it refuse rather than guess when the
# wiring is wrong (unknown mode)? An announcer that silently announced nothing
# would restore exactly the invisible skip it exists to remove, so the
# quiet-direction cases are the load-bearing ones, not filler.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ANNOUNCER="$SCRIPT_DIR/../../quality/announce-gate-skips.sh"
[ -x "$ANNOUNCER" ] || {
    log_fail "announcer not found or not executable: $ANNOUNCER"
    exit 1
}

# run_announcer <mode-or-UNSET> <expected-exit> <label> [args...]
OUT=""
run_announcer() {
    local mode="$1" expected="$2" label="$3"
    shift 3
    local rc=0
    if [ "$mode" = "UNSET" ]; then
        OUT="$(env -u GATE_SKIP_MODE "$ANNOUNCER" "$@" 2>&1)" || rc=$?
    else
        OUT="$(GATE_SKIP_MODE="$mode" "$ANNOUNCER" "$@" 2>&1)" || rc=$?
    fi
    if [ "$rc" -ne "$expected" ]; then
        log_fail "$label: expected exit $expected, got $rc (output: $OUT)"
    fi
}

test_skip_announces_every_gate_by_name() {
    run_announcer skip 0 "skip announces" no-media-quality gate-alpha gate-beta
    case "$OUT" in
        *"::warning::"*) ;;
        *) log_fail "skip must emit a ::warning:: annotation, got: $OUT" ;;
    esac
    # Naming the gates is the whole point: "2 gates skipped" would not tell a
    # reader which coverage they lost.
    case "$OUT" in
        *gate-alpha*) ;;
        *) log_fail "skip must name gate-alpha: $OUT" ;;
    esac
    case "$OUT" in
        *gate-beta*) ;;
        *) log_fail "skip must name gate-beta: $OUT" ;;
    esac
    case "$OUT" in
        *no-media-quality*) ;;
        *) log_fail "skip must name the label responsible: $OUT" ;;
    esac
    log_pass "skip mode: exits 0, warns, names the label and every held gate"
}

test_hard_is_quiet_but_not_silent() {
    # CONTROL for the case above. If this warned, the announcement would be
    # noise on every green run and would stop meaning anything.
    run_announcer hard 0 "hard announces nothing held" no-media-quality gate-alpha gate-beta
    case "$OUT" in
        *"::warning::"*) log_fail "hard mode must not warn: $OUT" ;;
        *) ;;
    esac
    # But it must still say something: a completely silent announcer and a
    # missing announcer look identical in a log.
    case "$OUT" in
        *"2 gate(s) enforced"*) ;;
        *) log_fail "hard mode must report the enforced count: $OUT" ;;
    esac
    log_pass "hard mode: exits 0, no warning, still prints the enforced count"
}

test_unset_mode_fails_closed_to_hard() {
    # A wiring break (the env var never reaches the step) must read as "the
    # gates ran", never as "the gates were held".
    run_announcer UNSET 0 "unset is hard" no-media-quality gate-alpha
    case "$OUT" in
        *"::warning::"*) log_fail "unset must not announce a skip: $OUT" ;;
        *) ;;
    esac
    case "$OUT" in
        *"1 gate(s) enforced"*) ;;
        *) log_fail "unset must behave as hard: $OUT" ;;
    esac
    log_pass "unset GATE_SKIP_MODE fails closed to hard"
}

test_unknown_mode_refuses() {
    # The step `if:` treats any unrecognised value as "run", which is safe but
    # silent. This is the only place a typo'd mode is ever reported, so it must
    # refuse loudly rather than fall through to hard.
    run_announcer sideways 2 "unknown mode refuses" no-media-quality gate-alpha
    case "$OUT" in
        *"unknown GATE_SKIP_MODE"*) ;;
        *) log_fail "unknown mode must name itself in the refusal: $OUT" ;;
    esac
    case "$OUT" in
        *sideways*) ;;
        *) log_fail "refusal must echo the bad value: $OUT" ;;
    esac
    log_pass "unknown mode refuses (exit 2) and echoes the bad value"
}

test_zero_gates_refuses() {
    # An announcer with nothing to announce is miswired, not clean. Exiting 0
    # here would let a job drop its whole gate list and still look announced.
    run_announcer skip 2 "no gates refuses" no-media-quality
    case "$OUT" in
        *usage*) ;;
        *) log_fail "empty gate list must print usage: $OUT" ;;
    esac
    run_announcer skip 2 "no args at all refuses"
    log_pass "zero gate names refuses with usage in both modes of emptiness"
}

test_skip_writes_step_summary() {
    local tmp
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' RETURN
    local rc=0
    GATE_SKIP_MODE=skip GITHUB_STEP_SUMMARY="$tmp" \
        "$ANNOUNCER" no-media-quality gate-alpha >/dev/null 2>&1 || rc=$?
    [ "$rc" -eq 0 ] || log_fail "skip with summary should still exit 0, got $rc"
    grep -q "Gates skipped by" "$tmp" || log_fail "step summary not written: $(cat "$tmp")"
    grep -q "gate-alpha" "$tmp" || log_fail "step summary must name the gate: $(cat "$tmp")"

    # CONTROL: hard must not write a summary at all, or every green run would
    # carry a "gates skipped" heading.
    : >"$tmp"
    GATE_SKIP_MODE=hard GITHUB_STEP_SUMMARY="$tmp" \
        "$ANNOUNCER" no-media-quality gate-alpha >/dev/null 2>&1
    [ ! -s "$tmp" ] || log_fail "hard mode must write no step summary, got: $(cat "$tmp")"
    log_pass "skip writes the step summary, hard writes none"
}

# The announcer is wired into BOTH jobs that hold a media gate. A gate skipped
# in a job with no announcer would be invisible again, which is the defect this
# whole file is about, so the wiring itself is asserted rather than assumed.
test_workflow_wiring_covers_every_held_gate() {
    # Seam, so the wiring assertion below can itself be proven able to fire
    # against a mutated COPY. Mutating the real workflow to test the test is
    # how a shared tree loses somebody's uncommitted work.
    local wf
    wf="${GATE_SKIP_WORKFLOW:-$SCRIPT_DIR/../../../../.github/workflows/ci-quality.yml}"
    [ -f "$wf" ] || {
        log_fail "ci-quality.yml not found at $wf"
        return
    }
    local held announced
    held="$(grep -c "inputs.media_quality != 'skip'" "$wf" || true)"
    announced="$(grep -c "announce-gate-skips.sh no-media-quality" "$wf" || true)"
    [ "$held" -ge 3 ] || log_fail "expected at least 3 media-held steps, found $held"
    [ "$announced" -eq 2 ] || log_fail "expected 2 announcer invocations (content + i18n), found $announced"

    # Every gate named in an announcer invocation must be a gate that is
    # actually held somewhere, and vice versa. Otherwise the announcement
    # drifts into fiction the first time a gate is added or removed.
    local gate
    for gate in $(grep -oE "announce-gate-skips\.sh no-media-quality[a-zA-Z0-9:._ -]*" "$wf" |
        sed 's/announce-gate-skips\.sh no-media-quality //'); do
        grep -q "run: npm run $gate\$" "$wf" ||
            log_fail "announcer names '$gate' but no step in ci-quality.yml runs it"
    done
    log_pass "wiring: $held held steps, $announced announcers, every announced gate exists"
}

test_skip_announces_every_gate_by_name
test_hard_is_quiet_but_not_silent
test_unset_mode_fails_closed_to_hard
test_unknown_mode_refuses
test_zero_gates_refuses
test_skip_writes_step_summary
test_workflow_wiring_covers_every_held_gate

log_pass "all tests passed"

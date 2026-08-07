#!/bin/bash
# The Stop hook must survive a hostile stdin: never crash, never hang.
#
# WHY THIS EXISTS. On 2026-08-07 the harness reported:
#
#     Stop hook error: Failed with non-blocking status code:
#     EAGAIN: resource temporarily unavailable, read
#
# `_read_event` caught only JSONDecodeError and ValueError. EAGAIN arrives as
# BlockingIOError -- an OSError -- so it sailed past, the hook CRASHED, and
# every stop check silently did not run for that stop. The hook is the thing
# that enforces the other checks, so when it dies the whole guard layer goes
# quiet at once, and nothing in CI notices: the checks cannot validate the
# health of the process running them.
#
# THE OBVIOUS FIX WAS WORSE. `os.set_blocking(fd, True)` makes read() wait
# forever when the writer holds the pipe open and sends nothing; that version
# had to be SIGKILLed. A hook that HANGS is worse than one that crashes,
# because it stalls the session instead of failing it. So this file asserts
# BOTH properties, and a fix that trades one for the other fails here.
#
# WHAT IT DOES NOT DO, stated honestly. It does not exercise the checks' logic
# -- the rest of this directory is for that. And it does NOT reproduce the
# original EAGAIN crash against the real hook: mutating _read_event back to its
# pre-fix shape leaves this file GREEN, because CPython's buffered
# TextIOWrapper.read() returns "" rather than raising on a non-blocking empty
# pipe, so the old code fell through to a JSONDecodeError it already caught.
# The crash the harness reported came from a path these four shapes do not
# recreate. That is measured, not assumed, and it is recorded here so nobody
# reads a green run as proof the EAGAIN case is covered.
#
# WHAT IT DOES CATCH, mutation-proven: the HANG. Installing the
# `os.set_blocking(fd, True)` variant -- the obvious fix, nearly shipped in
# place of this one -- turns this file RED with
# `hung=1 crashed=0 elapsed=40.0`. That is the more dangerous regression of the
# two, because a hook that hangs stalls the session rather than failing it, and
# it is the one a future "simplification" is most likely to reintroduce.
#
# The crash arm is still worth keeping: its control (a deliberately broken
# stand-in) proves the harness CAN see a traceback, so if some future edit does
# make the hook raise, these four shapes will say so.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

HOOK="$SCRIPT_DIR/../../../../.claude/hooks/stop/worklist.py"
[ -f "$HOOK" ] || log_fail "stop hook not found: $HOOK"

# The driver lives in python because the hostile conditions (a non-blocking
# pipe, a writer that never writes) cannot be built in portable bash.
DRIVER="$(mktemp)"
trap 'rm -f "$DRIVER"' EXIT
cat >"$DRIVER" <<'PYEOF'
import json, os, subprocess, sys, time

hook, mode, budget = sys.argv[1], sys.argv[2], float(sys.argv[3])
payload = json.dumps({"session_id": "test-stop-hook-stdin", "cwd": os.getcwd()})

if mode == "closed":
    p = subprocess.Popen([sys.executable, hook], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    w = None
else:
    r, w = os.pipe()
    os.set_blocking(r, False)          # the exact state that killed the hook
    p = subprocess.Popen([sys.executable, hook], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    os.close(r)
    if mode in ("late", "garbage"):
        time.sleep(0.3)                # arrive AFTER the first read attempt
        body = payload if mode == "late" else "{not json at all"
        try:
            os.write(w, body.encode())
        except BrokenPipeError:
            pass
        os.close(w); w = None
    # mode == "never": hold the write end open and send nothing

t0 = time.monotonic()
hung = False
try:
    _, err = p.communicate(timeout=budget)
except subprocess.TimeoutExpired:
    p.kill(); _, err = p.communicate(); hung = True
elapsed = time.monotonic() - t0
if w is not None:
    os.close(w)

crashed = "Traceback" in err or "BlockingIOError" in err
print("hung=%s crashed=%s elapsed=%.1f" % (int(hung), int(crashed), elapsed))
PYEOF

run_mode() { # mode budget -> sets LAST
    LAST="$(python3 "$DRIVER" "$HOOK" "$1" "$2" 2>&1 | tail -1)"
}

test_never_written_payload_does_not_crash_or_hang() {
    # The founding case: a non-blocking pipe whose payload never arrives.
    # Crashing here is the 2026-08-07 bug; hanging here is the fix that was
    # nearly shipped in its place.
    run_mode never 40
    assert_contains "$LAST" "hung=0" "the hook must NOT hang when no payload ever arrives ($LAST)"
    assert_contains "$LAST" "crashed=0" "the hook must NOT crash on EAGAIN ($LAST)"
    log_pass "no payload: terminates, bounded, no traceback"
}

test_late_payload_is_still_read() {
    # Bounding the wait must not cost us the normal case: a payload written
    # after the first read attempt still has to be picked up.
    run_mode late 40
    assert_contains "$LAST" "hung=0" "a late payload must not hang the hook ($LAST)"
    assert_contains "$LAST" "crashed=0" "a late payload must not crash the hook ($LAST)"
    log_pass "late payload on a non-blocking pipe is read, not lost"
}

test_malformed_payload_does_not_crash() {
    run_mode garbage 40
    assert_contains "$LAST" "crashed=0" "malformed JSON must be handled, not raised ($LAST)"
    assert_contains "$LAST" "hung=0" "malformed JSON must not hang ($LAST)"
    log_pass "malformed payload is handled without a traceback"
}

test_closed_stdin_does_not_hang() {
    run_mode closed 40
    assert_contains "$LAST" "hung=0" "an immediately-closed stdin must not hang ($LAST)"
    assert_contains "$LAST" "crashed=0" "an immediately-closed stdin must not crash ($LAST)"
    log_pass "closed stdin terminates cleanly"
}

test_the_harness_can_actually_detect_a_crash() {
    # CONTROL. Without this, every assertion above could be passing because the
    # driver never reports a crash rather than because the hook never has one.
    # Point it at a stand-in that reproduces the ORIGINAL defect and require it
    # to be caught.
    local broken
    broken="$(mktemp --suffix=.py)"
    cat >"$broken" <<'PYEOF'
import json, sys
# The pre-fix shape: only JSONDecodeError/ValueError caught, so a
# BlockingIOError from a non-blocking read escapes as a traceback.
try:
    json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    pass
PYEOF
    local out
    out="$(python3 "$DRIVER" "$broken" never 20 2>&1 | tail -1)"
    rm -f "$broken"
    assert_contains "$out" "crashed=1" \
        "the harness MUST detect a crash in a deliberately broken stand-in, or the passes above prove nothing ($out)"
    log_pass "control fired: the harness detects a real crash"
}

log_test "test-stop-hook-stdin"
test_the_harness_can_actually_detect_a_crash
test_never_written_payload_does_not_crash_or_hang
test_late_payload_is_still_read
test_malformed_payload_does_not_crash
test_closed_stdin_does_not_hang
echo ""
log_pass "all tests passed"

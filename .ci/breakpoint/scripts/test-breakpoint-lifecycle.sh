#!/bin/bash
# The per-CI-round regression leg. Quick mode, ZERO credentials, ~2 minutes.
#
# WHAT THIS EXISTS TO CATCH, and why a nightly sweeper cannot catch it:
# the sweeper proves orphans get cleaned up EVENTUALLY. Nothing else proves
# that teardown works AT ALL. A6 below -- "the URL is gone after
# stop-breakpoint.sh" -- is the only automated proof in the whole feature that
# the thing which is supposed to tear down actually tears down.
#
# It runs in QUICK MODE ON PURPOSE, and that is a security property rather than
# a convenience: this is the only breakpoint code that runs inside a
# watchdog-monitored CI run, and the watchdog force-cancels, which bypasses
# `if: always()`. Quick mode creates ZERO account-side objects, so a
# force-cancel here leaks nothing by construction. A4 asserts exactly that, and
# it is what keeps the claim honest as the code changes.
#
# This lives INSIDE the folder (and is therefore hashed by MANIFEST.sha256)
# because every repo that vendors breakpoint wants it, unlike the gate tests in
# .ci/scripts/test/gates/ which depend on console's test harness.
#
# Usage: test-breakpoint-lifecycle.sh [--port 18099]
# Exit:  0 all assertions passed, 1 any assertion failed.

set -uo pipefail # NOT -e: an assertion must be able to fail and be reported
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

parse_args "$@"
PORT="${ARG_PORT:-18099}"

PASSED=0
FAILED=0

pass() {
    echo "PASS: $*"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "FAIL: $*" >&2
    FAILED=$((FAILED + 1))
}

cleanup() {
    "$SCRIPT_DIR/stop-breakpoint.sh" --run-id "${GITHUB_RUN_ID:-0}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== breakpoint lifecycle regression ==="

# --- A1: the origin serves BEFORE any tunnel exists -------------------------
# Without this, a tunnel failure and an origin failure look identical.
ORIGIN="$("$SCRIPT_DIR/start-origin.sh" --port "$PORT" --services none --desktop none)"
if [[ -n "$ORIGIN" ]] && [[ "$(curl -s --max-time 5 "${ORIGIN}/health" || true)" == "breakpoint-origin-ok" ]]; then
    pass "A1 origin serves locally before any tunnel exists"
else
    fail "A1 origin did not serve at ${ORIGIN:-<none>}"
    echo "aborting: every later assertion would be meaningless" >&2
    exit 1
fi

# --- A2: mode selection with no credentials resolves to quick ---------------
MODE="$("$SCRIPT_DIR/select-mode.sh" 2>/dev/null || true)"
if [[ "$MODE" == "quick" ]]; then
    pass "A2 select-mode defaults to quick with no credentials"
else
    fail "A2 select-mode returned '${MODE}', expected 'quick'"
fi

# --- A3: start-tunnel's stdout contract -------------------------------------
URL="$("$SCRIPT_DIR/start-tunnel.sh" --mode quick --origin "$ORIGIN" --run-id "${GITHUB_RUN_ID:-0}")"
RC=$?
if [[ $RC -eq 0 ]] && [[ "$URL" =~ ^https://[a-z0-9-]+\.trycloudflare\.com$ ]]; then
    pass "A3 start-tunnel emitted exactly one well-formed URL on stdout"
else
    fail "A3 start-tunnel rc=$RC stdout='${URL}' (expected one https://*.trycloudflare.com line)"
fi

# --- A4: quick mode created ZERO account-side objects -----------------------
STATE="$(bp_state_dir)/session.env"
if [[ -f "$STATE" ]] &&
    ! grep -q '^BP_TUNNEL_ID=' "$STATE" &&
    ! grep -q '^BP_DNS_RECORD_ID=' "$STATE" &&
    ! grep -q '^BP_ACCESS_APP_ID=' "$STATE"; then
    pass "A4 quick mode recorded no tunnel/DNS/Access object ids"
else
    fail "A4 quick mode recorded account-side object ids (or wrote no state at all)"
fi

# --- A5: the public URL serves the origin's content -------------------------
if [[ -n "$URL" ]]; then
    BODY=""
    elapsed=0
    while [[ $elapsed -lt 60 ]]; do
        BODY="$(curl -s --max-time 10 "${URL}/health" 2>/dev/null || true)"
        [[ "$BODY" == "breakpoint-origin-ok" ]] && break
        sleep 5
        elapsed=$((elapsed + 5))
    done
    if [[ "$BODY" == "breakpoint-origin-ok" ]]; then
        pass "A5 origin content served end-to-end through the Cloudflare edge"
    else
        fail "A5 public URL never served the origin body (got '${BODY}')"
    fi
fi

# --- A6: teardown, then GONE ------------------------------------------------
if "$SCRIPT_DIR/stop-breakpoint.sh" --run-id "${GITHUB_RUN_ID:-0}"; then
    pass "A6a stop-breakpoint exited 0"
else
    fail "A6a stop-breakpoint exited non-zero"
fi

if [[ -n "$URL" ]]; then
    sleep 5
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${URL}/health" 2>/dev/null || true)"
    [[ -n "$CODE" ]] || CODE="000"
    # Anything but a working 200 is correct here: 000 (DNS gone), 530/1033
    # (Cloudflare has no connector) all mean the tunnel is not serving.
    if [[ "$CODE" != "200" ]]; then
        pass "A6b the public URL no longer serves (HTTP ${CODE})"
    else
        fail "A6b the public URL STILL SERVES after teardown -- the tunnel leaked"
    fi
fi

# --- A7: no stragglers ------------------------------------------------------
if pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
    fail "A7 a cloudflared process survived teardown"
else
    pass "A7 no cloudflared process survived teardown"
fi

# --- A8: teardown is idempotent --------------------------------------------
# Both `always()` and the sweeper re-run it, so "already clean" is the normal
# second call and must not be an error.
if "$SCRIPT_DIR/stop-breakpoint.sh" --run-id "${GITHUB_RUN_ID:-0}" >/dev/null 2>&1; then
    pass "A8 a second teardown against clean state still exits 0"
else
    fail "A8 the second teardown exited non-zero"
fi

echo ""
echo "=== ${PASSED} passed, ${FAILED} failed ==="
[[ $FAILED -eq 0 ]] || exit 1
[[ $PASSED -gt 0 ]] || {
    echo "vacuous: no assertions ran" >&2
    exit 1
}

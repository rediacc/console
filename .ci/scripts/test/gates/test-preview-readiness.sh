#!/bin/bash
# Unit test for .ci/scripts/deploy/wait-for-preview-worker.sh.
#
# WHAT THIS GUARDS. The preview readiness probe gates smoke-test-preview.ts. If
# it reports "ready" while the worker is still flapping, the smoke test gets a
# cold worker and the PR goes red for a reason that has nothing to do with the
# PR. That happened in runs 30968082228 and 30995469629: the probe logged ready
# at 10:26:41.557 and the smoke test got HTTP 500 from the very same server-info
# URL 1.3 seconds later.
#
# WHY THE STREAK IS THE FIX AND NOT THE ENDPOINT. Two earlier commits already
# tried changing WHICH endpoint is probed -- 8b7840ed4 added the server-info
# probe, cefa43ca7 corrected the body it greps for -- and the failure returned
# both times, because a SINGLE success cannot distinguish "up" from "flapping".
# The deployment flaps by construction: deploy-www.sh deletes and recreates the
# per-PR D1 database on every push, and server-info touches D1 while /health
# does not.
#
# The load-bearing test here is test_streak_is_load_bearing: it re-runs the
# flapping case with REQUIRED_STREAK=1, the pre-fix behaviour, and demands that
# it PASSES. Without that, the flapping case failing would prove nothing about
# why -- it could be the stub, the URL, or the budget.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WAIT_SCRIPT="$REPO_ROOT/.ci/scripts/deploy/wait-for-preview-worker.sh"
WORK="$(mktemp -d)"
STUB_PID=""
cleanup() {
    [[ -n "$STUB_PID" ]] && kill "$STUB_PID" 2>/dev/null
    rm -rf "$WORK"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Stub preview worker. /health is always fine (it touches nothing in the real
# app either); server-info is the one that flaps.
# ---------------------------------------------------------------------------

cat >"$WORK/stub.cjs" <<'STUB'
const http = require('http');
const fs = require('fs');
const MODE = process.env.MODE || 'steady';
const GOOD = JSON.stringify({ e2e: { keys: [{ keyId: 'v1', publicKeySpki: 'AAAA' }] } });
let n = 0;

const server = http.createServer((req, res) => {
  if (req.url.endsWith('/health')) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end('{"status":"ok"}');
  }
  if (req.url.endsWith('/server-info')) {
    n++;
    // flap: good on 1 of every 3 probes, so the streak never reaches 2.
    // late: cold for the first 3 probes, then steady.
    const good = MODE === 'steady' ? true : MODE === 'flap' ? n % 3 === 1 : n > 3;
    if (good) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      return res.end(GOOD);
    }
    res.writeHead(500, { 'Content-Type': 'application/json' });
    return res.end('{"error":"cold"}');
  }
  res.writeHead(404);
  res.end();
});

server.listen(0, '127.0.0.1', () => {
  fs.writeFileSync(process.env.PORT_FILE, String(server.address().port));
});
STUB

start_stub() {
    local mode="$1"
    rm -f "$WORK/port"
    MODE="$mode" PORT_FILE="$WORK/port" node "$WORK/stub.cjs" &
    STUB_PID=$!
    for _ in $(seq 1 50); do
        [[ -s "$WORK/port" ]] && return 0
        sleep 0.1
    done
    log_fail "stub worker did not start (mode=$mode)"
}

stop_stub() {
    [[ -n "$STUB_PID" ]] && kill "$STUB_PID" 2>/dev/null
    wait "$STUB_PID" 2>/dev/null || true
    STUB_PID=""
}

# probe <mode> [extra env assignments...] -> exit code of the wait script
probe() {
    local mode="$1"
    shift
    start_stub "$mode"
    local port rc=0
    port="$(cat "$WORK/port")"
    env "$@" \
        PREVIEW_URL_OVERRIDE="http://127.0.0.1:${port}" \
        MAX_ATTEMPTS=9 \
        PROBE_INTERVAL_SECONDS=0.1 \
        bash "$WAIT_SCRIPT" >"$WORK/log.txt" 2>&1 || rc=$?
    stop_stub
    echo "$rc"
}

# ---------------------------------------------------------------------------

test_steady_worker_is_ready() {
    assert_eq "$(probe steady)" "0" "a steady worker is reported ready"
    assert_contains "$(cat "$WORK/log.txt")" "consecutive probes" \
        "success names the streak it required"
    log_pass "a steady worker passes"
}

test_flapping_worker_is_not_ready() {
    assert_eq "$(probe flap)" "1" "a flapping worker is NOT reported ready"
    assert_contains "$(cat "$WORK/log.txt")" "streak reset" \
        "the flap is reported as a reset, not as a plain wait"
    log_pass "a flapping worker is rejected"
}

test_streak_is_load_bearing() {
    # ANTI-VACUITY. Same stub, same URL, same budget -- only REQUIRED_STREAK
    # drops to 1, which is exactly what this script did before the fix. If this
    # does NOT pass, the flapping case above is failing for some other reason
    # and proves nothing about the streak.
    assert_eq "$(probe flap REQUIRED_STREAK=1)" "0" \
        "with REQUIRED_STREAK=1 the same flapping worker passes (the old bug)"
    log_pass "the streak is what rejects the flap, not the stub or the budget"
}

test_slow_worker_still_becomes_ready() {
    # The streak must not turn a merely COLD worker into a failure: this one is
    # down for 3 probes and then healthy, which must still end in success.
    assert_eq "$(probe late)" "0" "a cold-then-healthy worker still passes"
    log_pass "a slow start is not mistaken for a flap"
}

test_override_does_not_need_a_pr_number() {
    # PREVIEW_URL_OVERRIDE exists so this script is testable without being
    # copied through sed. It has to work with PR_NUMBER unset, or the tests
    # above are quietly exercising a different code path than CI does.
    start_stub steady
    local port rc=0
    port="$(cat "$WORK/port")"
    env -u PR_NUMBER \
        PREVIEW_URL_OVERRIDE="http://127.0.0.1:${port}" \
        MAX_ATTEMPTS=9 \
        PROBE_INTERVAL_SECONDS=0.1 \
        bash "$WAIT_SCRIPT" >"$WORK/log.txt" 2>&1 || rc=$?
    stop_stub
    assert_eq "$rc" "0" "the override works with PR_NUMBER unset"
    log_pass "the override needs no PR_NUMBER"
}

test_pr_number_still_required_without_override() {
    local rc=0
    env -u PR_NUMBER -u PREVIEW_URL_OVERRIDE \
        bash "$WAIT_SCRIPT" >"$WORK/log.txt" 2>&1 || rc=$?
    assert_eq "$rc" "1" "PR_NUMBER is still mandatory when no override is given"
    assert_contains "$(cat "$WORK/log.txt")" "PR_NUMBER" \
        "the failure names the missing variable"
    log_pass "the override did not make PR_NUMBER optional in CI"
}

test_ci_defaults_are_still_strict() {
    # The knobs are test-only. If someone weakens the DEFAULTS, CI silently goes
    # back to sampling one probe, and every test above would still pass because
    # they all set their own values.
    local src
    src="$(cat "$WAIT_SCRIPT")"
    assert_contains "$src" 'REQUIRED_STREAK="${REQUIRED_STREAK:-3}"' \
        "the default streak is still 3"
    assert_contains "$src" 'MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"' \
        "the default budget is still 60"
    assert_contains "$src" 'PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-2}"' \
        "the default spacing is still 2s"
    log_pass "CI defaults are unchanged"
}

log_test "test-preview-readiness"
test_steady_worker_is_ready
test_flapping_worker_is_not_ready
test_streak_is_load_bearing
test_slow_worker_still_becomes_ready
test_override_does_not_need_a_pr_number
test_pr_number_still_required_without_override
test_ci_defaults_are_still_strict
echo ""
log_pass "all tests passed"

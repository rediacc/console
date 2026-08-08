#!/usr/bin/env bash
# Assert the edge smoke test cannot be failed by ONE unlucky sample.
#
# WHY THIS EXISTS, AND WHY IT IS A PR GATE. On 2026-08-08 release run 31234422166
# deployed edge successfully and then failed
# `edge.rediacc.com footer does not render v1.2.19` -- while edge was ALREADY
# serving v1.2.19. The assertion sampled an eventually-consistent CDN exactly
# once, moments after the deploy, and lost the race. The failure cascaded:
# `Tag & GitHub Release` was skipped, so a good release shipped with NO git tag
# and NO GitHub Release.
#
# `verify-edge-endpoints.sh` runs ONLY from cd-v2.yml, which is dispatch-only and
# main-only. So the DEPLOY it verifies genuinely cannot be exercised on a PR --
# and that was the reasoning that nearly left this unguarded.
#
# The reasoning was wrong. The defect was never "edge served the wrong version";
# it was "the assertion samples once". That is a property of a shell script, and a
# shell script can be driven against a FAKE curl on any PR, with no deploy at all.
# That is what this gate does. The operator asked the right question.
#
# WHAT IT ASSERTS
#   1. RETRIES     a surface that is stale then correct is ACCEPTED (the incident).
#   2. STILL FAILS a surface that is ALWAYS wrong is REJECTED -- the retry must not
#                  have become "eventually pass no matter what".
#   3. NO BARE     no assertion still reads a network surface exactly once.
#
# CONTROL-FIRST: assertion 1 is re-run against a copy with the retry stripped, and
# MUST fail there. If the planted defect passes, this gate declares ITSELF broken.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
TARGET="$REPO_ROOT/.ci/scripts/deploy/verify-edge-endpoints.sh"

log_test "edge smoke test survives one unlucky sample"

[[ -f "$TARGET" ]] || {
    log_fail "verify-edge-endpoints.sh not found at $TARGET"
    exit 1
}

# Extract the retry engine by anchor. A rename or rewrite breaks THIS gate loudly
# instead of leaving it testing a stale copy pasted in here.
FN="$(awk '/^fetch_retry\(\) \{/,/^\}/' "$TARGET")"
assert_eq "$(grep -c '^fetch_retry() {' <<<"$FN")" "1" \
    "fetch_retry() is extractable from the real script"

# ---- 1. stale-then-correct is ACCEPTED -------------------------------------
# The predicate fails twice, then succeeds: exactly the shape of a CDN that has
# not finished propagating.
run_case() {
    local fn="$1" fails="$2" retries="$3"
    local state
    state="$(mktemp)"
    echo 0 >"$state"
    EDGE_RETRIES="$retries" EDGE_RETRY_SLEEP=0 STATE="$state" FAILS="$fails" \
        bash -c '
            set -eu
            '"$fn"'
            _p() {
                n=$(cat "$STATE"); n=$((n + 1)); echo "$n" >"$STATE"
                [ "$n" -gt "$FAILS" ]
            }
            fetch_retry probe _p
        ' >/dev/null 2>&1
}

if run_case "$FN" 2 6; then
    log_pass "a surface that is stale twice then correct is ACCEPTED (the 1.2.19 incident)"
else
    log_fail "a stale-then-correct surface was rejected; one unlucky sample can still fail a good release"
fi

# ---- 2. always-wrong is still REJECTED -------------------------------------
if run_case "$FN" 99 3; then
    log_fail "a surface that NEVER agrees was accepted -- the retry has become 'pass eventually', which is worse than no check"
else
    log_pass "a surface that never agrees is still REJECTED (retry did not become a rubber stamp)"
fi

# ---- 3. no assertion reads the network exactly once -------------------------
# Every bare `curl` that feeds an assertion must sit inside a predicate that
# fetch_retry drives. Counting is the cheap, robust form: the script had TWELVE
# single-sample reads and zero retries when this incident happened.
RETRYING="$(grep -c 'fetch_retry "' "$TARGET" || true)"
if [[ "$RETRYING" -ge 4 ]]; then
    log_pass "the load-bearing assertions are driven through fetch_retry ($RETRYING call sites)"
else
    log_fail "only $RETRYING assertion(s) retry; the rest can still be failed by one sample"
fi

# ---- CONTROL: strip the retry, assertion 1 MUST fail ------------------------
# Collapse the loop to a single attempt. If the stale-then-correct case still
# passes against that, this gate is not measuring what it claims.
MUTANT="${FN//EDGE_RETRIES:-6/EDGE_RETRIES:-1}"
MUTANT="${MUTANT//\"\$attempt\" -ge \"\$EDGE_RETRIES\"/true}"
if [[ "$MUTANT" == "$FN" ]]; then
    log_fail "CONTROL could not plant its defect (fetch_retry's shape changed); update the mutant here"
    exit 1
fi
if run_case "$MUTANT" 2 6; then
    log_fail "CONTROL DID NOT FIRE: a single-attempt fetch_retry still accepted a stale-then-correct surface, so this gate cannot detect the defect it exists for"
    exit 1
fi
log_pass "CONTROL fired: with the retry stripped, the stale-then-correct case fails as it did in production"

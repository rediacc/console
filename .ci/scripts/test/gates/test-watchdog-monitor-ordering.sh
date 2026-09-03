#!/bin/bash
# CHECK 6 of check-workflow-gates.sh had never been proven able to fail.
#
# WHY IT NEEDS A TEST. CHECK 6 is the rule that keeps the watchdog watching: no step
# ahead of "Monitor jobs and cancel on failure" may be able to stop the job. It was
# written after run 33704079162 reported "failure" having monitored NOTHING, and until
# now its only evidence of working was that it was green -- which is also exactly what
# it looks like when its anchor moves, its allowlist swallows the case, or its verdict
# is computed off the wrong list.
#
# It also just got LOOSER in one direction and STRICTER in another: a step carrying
# BOTH `continue-on-error: true` and a small `timeout-minutes` is now admitted
# regardless of its name, because those two properties are what the name was ever
# standing in for. A rule with a new door in it is precisely the rule that needs a
# test walking through the door and then trying the wall beside it.
#
# HOW. The checker is EXTRACTED FROM THE LIVE GATE rather than restated here. A
# restated copy keeps passing after the original changes, which is the failure this
# file exists to detect. Six plants, in both directions.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/security/check-workflow-gates.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/watchdog-monitor.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0

# --- Extract CHECK 6's checker, by content, from the live gate ---------------
awk '/^python3 - "\$ROOT_DIR" <<.PYEOF.$/ { buf = ""; grab = 1; next }
     grab && /^PYEOF$/ {
         if (buf ~ /Monitor jobs and cancel on failure/) printf "%s", buf
         grab = 0; next
     }
     grab { buf = buf $0 "\n" }' "$GATE" >"$TMP/check6.py"

if ! grep -q 'Monitor jobs and cancel on failure' "$TMP/check6.py"; then
    log_fail "could not extract CHECK 6 from check-workflow-gates.sh -- it was renamed"
    log_fail "or restructured. This test now tests NOTHING; fix the extraction, do not"
    log_fail "delete the test."
    exit 1
fi
log_pass "CHECK 6 extracted from the live gate ($(wc -l <"$TMP/check6.py") lines)"
PASS=$((PASS + 1))

run_check() { # run_check <workflow-file>; leaves output in $TMP/out
    local root="$TMP/root"
    rm -rf "$root"
    mkdir -p "$root/.github/workflows"
    cp "$1" "$root/.github/workflows/watchdog-monitor.yml"
    python3 "$TMP/check6.py" "$root" >"$TMP/out" 2>&1
}

expect() { # expect <want-rc> <label> <workflow-file>
    local want="$1" label="$2" file="$3" got=0
    run_check "$file" || got=$?
    if [[ "$got" == "$want" ]]; then
        log_pass "$label (rc=$got)"
        PASS=$((PASS + 1))
    else
        log_fail "$label: CHECK 6 exited $got, expected $want"
        sed 's/^/      /' "$TMP/out"
        exit 1
    fi
}

# plant <out> <extra-step-yaml-lines...>: the real workflow with one step inserted
# immediately ahead of the monitor. Text editing, because that is the kind of edit a
# human makes -- a round-trip through pyyaml would normalise away the shape.
plant() {
    local out="$1"
    shift
    python3 - "$WORKFLOW" "$out" "$@" <<'PY'
import sys
src = open(sys.argv[1]).read().split("\n")
extra = ["      - name: Planted step"] + ["        " + a for a in sys.argv[3:]]
i = next(k for k, l in enumerate(src)
         if l.startswith("      - name: Monitor jobs and cancel on failure"))
src[i:i] = extra + [""]
open(sys.argv[2], "w").write("\n".join(src))
PY
}

# --- 1. The real workflow passes --------------------------------------------
expect 0 "the real watchdog-monitor.yml passes" "$WORKFLOW"

# --- 2. A step that can FAIL, ahead of the monitor, is refused ---------------
plant "$TMP/can-fail.yml" "run: exit 1"
expect 1 "CONTROL: a can-fail step ahead of the monitor is refused" "$TMP/can-fail.yml"
grep -q "Planted step" "$TMP/out" || {
    log_fail "the refusal did not name the planted step, so it fired for another reason"
    exit 1
}
log_pass "the refusal names the planted step, not something else"
PASS=$((PASS + 1))

# --- 3. continue-on-error ALONE is not enough: it can still HANG -------------
plant "$TMP/coe-only.yml" "continue-on-error: true" "run: exec cat"
expect 1 "CONTROL: continue-on-error WITHOUT a timeout is still refused" "$TMP/coe-only.yml"

# --- 4. timeout ALONE is not enough: it can still FAIL -----------------------
plant "$TMP/timeout-only.yml" "timeout-minutes: 2" "run: exit 1"
expect 1 "CONTROL: timeout-minutes WITHOUT continue-on-error is still refused" \
    "$TMP/timeout-only.yml"

# --- 5. An EXPRESSION is not a literal and must not be trusted ---------------
plant "$TMP/expr.yml" 'continue-on-error: ${{ github.event_name == "push" }}' \
    "timeout-minutes: 2" "run: exit 1"
expect 1 "CONTROL: an expression continue-on-error is refused, not read as true" \
    "$TMP/expr.yml"

# --- 6. Both literals together are admitted ---------------------------------
plant "$TMP/both.yml" "continue-on-error: true" "timeout-minutes: 2" "run: exit 1"
expect 0 "a step carrying BOTH properties is admitted regardless of its name" \
    "$TMP/both.yml"

# --- 7. Anti-vacuity: a renamed monitor must refuse, never pass --------------
python3 - "$WORKFLOW" "$TMP/renamed.yml" <<'PY'
import sys
open(sys.argv[2], "w").write(
    open(sys.argv[1]).read().replace("Monitor jobs and cancel on failure", "Monitor jobs"))
PY
expect 1 "CONTROL: a renamed monitor step is refused, never passed vacuously" \
    "$TMP/renamed.yml"

log_pass "watchdog monitor ordering: $PASS assertion(s)"

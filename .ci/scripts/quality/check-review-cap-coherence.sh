#!/usr/bin/env bash
# Assert the two review scripts measure the SAME thing against the SAME cap.
#
# WHY THIS EXISTS. On 2026-08-07 PR #553 became green, ready, thread-clean and
# PERMANENTLY UNMERGEABLE. `review-status.sh` carries an explicit DEADLOCK GUARD
# for exactly that outcome -- when the cap is reached the marker can never advance,
# so it passes loudly instead of failing. The guard never fired, because the two
# scripts counted different numerators against the same cap:
#
#   claude-review-gate.sh   posted + spent attempts  -> 3/3, refuses to review
#   review-status.sh        posted reports only      -> 0/3, guard stays mute
#
# Each script's own logic was self-consistent and locally correct. The defect
# lived BETWEEN them, where no single-script check could see it -- which is why
# this gate compares the two rather than validating either.
#
# `lib/common.sh` was created to stop precisely this drift, and it half-worked:
# it shared the DENOMINATOR (review_cap_for) while the numerator stayed split
# across two files, one of which did not know spent attempts existed. Sharing a
# file is not the same as sharing the computation, so this gate checks the
# computation.
#
# WHAT IT ASSERTS
#   1. DRY-NUMERATOR   both scripts obtain the spend total from the shared
#                      review_spend_total(), and neither re-sums it locally.
#   2. DRY-DENOMINATOR both obtain the cap from the shared review_cap_for().
#   3. ONE-DEFINITION  the shared helpers exist in lib/common.sh and nowhere else,
#                      so a "helpful" local copy cannot silently shadow them.
#   4. GUARD-REACHABLE with numerator == cap, review-status's deadlock guard is
#                      the branch that runs. This is the behavioural half: 1-3
#                      could all hold while the guard was still dead code.
#
# CONTROL-FIRST. Plants the original defect (review-status counting posted reports
# alone) and requires the assertions to FAIL. If the planted defect passes, the
# gate declares ITSELF broken and exits non-zero, so a green here means the checks
# can fire rather than that nothing tripped them.

set -euo pipefail

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
GATE="$REPO_ROOT/.ci/scripts/review/claude-review-gate.sh"
STATUS="$REPO_ROOT/.ci/scripts/review/review-status.sh"
LIB="$REPO_ROOT/.ci/scripts/lib/common.sh"

fail() {
    echo "${RED}✗${NC} $*" >&2
    exit 1
}

for f in "$GATE" "$STATUS" "$LIB"; do
    [[ -f "$f" ]] || fail "check-review-cap-coherence: $f not found; refusing to pass while measuring nothing"
done

# evaluate <gate-src> <status-src> <lib-src> -- prints one line per failure, empty when coherent.
evaluate() {
    local g="$1" s="$2" l="$3"

    # 1 + 2. Both sides must reach for the shared helpers by name.
    grep -q 'review_spend_total' <<<"$g" || echo "DRY-NUMERATOR: claude-review-gate.sh does not call review_spend_total()"
    grep -q 'review_spend_total' <<<"$s" || echo "DRY-NUMERATOR: review-status.sh does not call review_spend_total()"
    grep -q 'review_cap_for' <<<"$g" || echo "DRY-DENOMINATOR: claude-review-gate.sh does not call review_cap_for()"
    grep -q 'review_cap_for' <<<"$s" || echo "DRY-DENOMINATOR: review-status.sh does not call review_cap_for()"

    # 1b. THE ACTUAL 2026-08-07 SHAPE: a caller deriving the numerator from
    # review_report_count directly. That is how review-status.sh read 0/3 while
    # the gate read 3/3, so it is named as its own failure rather than left to be
    # inferred from the absence of review_spend_total.
    if grep -qE 'review_count=.*review_report_count' <<<"$s"; then
        echo "DRY-NUMERATOR: review-status.sh derives its cap numerator from review_report_count (posted reports ONLY) -- spent attempts are invisible to it, which is the #553 deadlock"
    fi
    if grep -qE 'review_count=.*review_report_count' <<<"$g"; then
        echo "DRY-NUMERATOR: claude-review-gate.sh derives its cap numerator from review_report_count directly"
    fi

    # 3. The shared helpers must be defined once, in the lib.
    local n
    for fn in review_spend_total review_spent_attempt_count review_cap_for review_report_count; do
        grep -qE "^${fn}\(\) \{" <<<"$l" || echo "ONE-DEFINITION: ${fn}() is not defined in lib/common.sh"
        n=$(grep -cE "^${fn}\(\) \{" <<<"$g$s" || true)
        [[ "$n" -eq 0 ]] || echo "ONE-DEFINITION: ${fn}() is redefined in a review script; a local copy is what drifted last time"
    done

    # 4. Behavioural: with numerator == cap, the deadlock guard must be the branch
    # that runs. Extracted from the real file by anchor, never transcribed.
    local guard
    # Anchored at column 0 and stopped after the FIRST complete range: the same
    # condition appears again, indented, further down the file, and an unanchored
    # awk range restarts there and returns an unterminated block that cannot run.
    guard="$(awk '/^if \[\[ "\$currency_ok" == true \]\]/{f=1} f{print} f&&/^fi$/{exit}' <<<"$s")"
    if [[ -z "$guard" ]]; then
        echo "GUARD-REACHABLE: could not extract the currency/deadlock branch from review-status.sh (rewritten?)"
    else
        local out
        out="$(
            review_count=3 MAX_REVIEWS_PER_PR=3 currency_ok=false currency_detail=x head_sha=y last_sha=z \
                bash -c '
                    warnings=(); failures=()
                    log_info() { :; }; log_warn() { :; }; log_error() { :; }
                    '"$guard"'
                    if [[ ${#warnings[@]} -gt 0 ]]; then echo GUARD_FIRED; fi
                    if [[ ${#failures[@]} -gt 0 ]]; then echo GUARD_MISSED; fi
                ' 2>/dev/null
        )"
        if ! grep -q GUARD_FIRED <<<"$out"; then
            echo "GUARD-REACHABLE: at numerator == cap the deadlock guard did NOT fire (got: ${out:-nothing}). A capped PR would be reported as a required FAILURE and become unmergeable."
        fi
        if grep -q GUARD_MISSED <<<"$out"; then
            echo "GUARD-REACHABLE: at numerator == cap review-status still recorded a hard failure"
        fi
    fi
    # ALWAYS 0: findings travel on stdout. A non-zero return here would abort the
    # whole gate under `set -e` before it could print a single one.
    return 0
}

GATE_SRC="$(cat "$GATE")"
STATUS_SRC="$(cat "$STATUS")"
LIB_SRC="$(cat "$LIB")"

# ---- control: plant the original defect and require detection -----------------
MUTANT_STATUS="${STATUS_SRC//review_count=\"\$(review_spend_total \"\$pr\" \"\$ATTEMPT_PREFIX\")\"/review_count=\"\$(review_report_count \"\$pr\")\"}"
if [[ "$MUTANT_STATUS" == "$STATUS_SRC" ]]; then
    fail "check-review-cap-coherence: the control could not plant its defect (the review_spend_total call in review-status.sh is not where it was). Update the mutant here to match. Refusing to report a green that proves nothing."
fi
CONTROL_OUT="$(evaluate "$GATE_SRC" "$MUTANT_STATUS" "$LIB_SRC")"
if [[ -z "$CONTROL_OUT" ]]; then
    fail "check-review-cap-coherence: CONTROL DID NOT FIRE. The pre-fix split numerator passed every assertion, so this gate cannot detect the defect it exists for."
fi

# ---- the real run --------------------------------------------------------------
REAL_OUT="$(evaluate "$GATE_SRC" "$STATUS_SRC" "$LIB_SRC")"
if [[ -n "$REAL_OUT" ]]; then
    echo "${RED}✗${NC} the review cap is not measured coherently:" >&2
    printf '  %s\n' "$REAL_OUT" >&2
    echo >&2
    echo "  Both scripts must take the numerator from review_spend_total() and the" >&2
    echo "  denominator from review_cap_for(), both in .ci/scripts/lib/common.sh." >&2
    echo "  When they disagree, the gate stops reviewing while review-status keeps" >&2
    echo "  demanding a review, and the PR becomes permanently unmergeable." >&2
    exit 1
fi

echo "${GREEN}✓${NC} review cap coherent: one numerator, one denominator, deadlock guard reachable at the cap"
echo "  control fired on the pre-fix split numerator ($(wc -l <<<"$CONTROL_OUT") finding(s)), so this green means the checks can fail"

#!/bin/bash
# Every top-level job in ci.yml must reach the `ci-complete` verdict.
#
# WHY. `ci-complete` is the single required status check for branch protection.
# It is green when, and only when, the jobs it aggregates are green. A job that
# is not in its `needs:` list, or is in `needs:` but has no `RESULT_*` env var
# feeding assert-ci-complete.sh, is invisible to it: the job can go red and the
# required check still reports success.
#
# Nothing enforced the relationship, so it decayed. ci.yml declares 24 top-level
# jobs; `ci-complete` aggregated 18 of them. Adding a job is the natural motion,
# and wiring it into the aggregator twice (once in `needs:`, once in `env:`) is
# the step people skip. This makes forgetting it a build failure instead of an
# unguarded job.
#
# FOUR CHECKS, because there are four ways the wiring breaks:
#   1. A job is missing from `needs:`         -> its result is unreadable.
#   2. A job is in `needs:` but has no        -> assert-ci-complete.sh never
#      RESULT_<JOB> in the `env:` block          sees it, so it cannot judge it.
#   3. `needs:` names a job that does not     -> GitHub refuses the workflow at
#      exist                                     parse time.
#   4. A RESULT_<JOB> var is in neither       -> the var is passed and dropped;
#      HARD_REQUIRED nor SOFT_REQUIRED, or       or the tier reads an unset var
#      a tier names a var nobody passes          and every run is red.
#
# DIRECTION IS DELIBERATE for check 4 only. Checks 1 and 2 say jobs subset of
# aggregator. Check 4 is an equality, because a tier entry and an env var are
# two halves of one wire: either half alone is dead.
#
# THE EXEMPT SET IS A HOLE, so every entry carries a BLOCKER reason validated by
# the shared validator (see docs/agent-reference/suppressions.md). It lives inline rather
# than in a tracked dotfile: it describes the shape of THIS workflow's DAG, it is
# only meaningful next to the four checks above, and a repo-root suppression file
# would need a liveness probe whose oracle is exactly the parsing done here.
#
# TEST SEAM. CI_JOB_AGGREGATION_WORKFLOW and CI_JOB_AGGREGATION_ASSERT override
# the two inputs so the gate test can drive fixtures without touching a tracked
# file.
#
# Usage: check-ci-job-aggregation.sh
#
# Exits 0 when the wiring is complete, 1 on any gap.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_step / log_info / log_error and get_repo_root used throughout
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: the exempt set below is a suppression list and must be held to the same BLOCKER quality bar as every other allowlist in the repo
source "$SCRIPT_DIR/../lib/blocker-validator.sh"

REPO_ROOT="$(get_repo_root)"
CI_WORKFLOW="${CI_JOB_AGGREGATION_WORKFLOW:-$REPO_ROOT/.github/workflows/ci.yml}"
ASSERT_SCRIPT="${CI_JOB_AGGREGATION_ASSERT:-$REPO_ROOT/.ci/scripts/ci/assert-ci-complete.sh}"

# The aggregator job. Named once, here, so a rename fails loudly below rather
# than silently matching nothing.
AGGREGATOR="ci-complete"

# Anti-vacuity floor. ci.yml has carried 20+ top-level jobs for its whole life;
# a parse that returns fewer than this found a layout it does not understand,
# and reporting "all wired" off three jobs is the failure this gate exists to
# prevent.
MIN_JOBS=10

for f in "$CI_WORKFLOW" "$ASSERT_SCRIPT"; do
    if [[ ! -f "$f" ]]; then
        log_error "input not found: $f"
        log_error "This gate cannot assert anything without it. Fix the path, do not skip the check."
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# The exempt set. Entry = job name; reason = why ci-complete cannot or must not
# aggregate it. Parsed and quality-checked by the shared BLOCKER validator, so a
# "# tbd" exemption fails this gate the same way it fails every other list.
# ---------------------------------------------------------------------------
read -r -d '' EXEMPT_BLOCK <<'EXEMPT' || true
# BLOCKER: this IS the aggregator; a job listed in its own needs is a self-edge and GitHub rejects the workflow at parse time, so the exemption is structural rather than a judgment call
ci-complete

# BLOCKER: runs downstream of the aggregator (needs: [initialize, ci-complete]), so aggregating it would close a cycle; its conclusion is asserted instead by pipeline-sentinel via assert-job-succeeded.sh
finalize-release-sentinel

# BLOCKER: transitively downstream of the aggregator (needs finalize-release-sentinel, which needs ci-complete), so aggregating it would close a cycle; it is the terminal assertion of the release DAG and has nothing above it to report to
pipeline-sentinel

# BLOCKER: designed to be force-cancelled by a newer run (its if: is !cancelled(), and cancel-older-runs.sh cancels peers), so a cancelled conclusion is the routine outcome; the soft tier accepts only success or skipped, so aggregating it would turn every superseded push red
cancel-watchdog

# BLOCKER: its failure already reaches the aggregator, but only INDIRECTLY and by accident. build-docker, build-docker-fast and build-cli each gate on needs.build-renet.result == 'success', so a red build-renet skips all three, and all three are HARD_REQUIRED where a skip is red. ops-tests runs under always() and then dies fetching the missing renet artifact, which is a second, equally accidental path. The outcome is correct today and nothing pins it: dropping the build-renet clause from any of those four ifs, or moving one job to the soft tier, silently makes a red build-renet read as green. Aggregate it directly when the pointer-bump tier logic is next touched, and delete this entry.
build-renet
EXEMPT

EXEMPT_FILE="$(mktemp)"
trap 'rm -f "$EXEMPT_FILE"' EXIT
printf '%s\n' "$EXEMPT_BLOCK" >"$EXEMPT_FILE"

declare -A EXEMPT_ENTRIES=()
declare -A EXEMPT_REASONS=()
parse_blockered_list "$EXEMPT_FILE" EXEMPT_ENTRIES EXEMPT_REASONS
if ! verify_all_blockers "$EXEMPT_FILE" EXEMPT_REASONS; then
    # The validator names the temp file it was handed, which tells the reader
    # nothing about where to edit. Name the real one.
    log_error "The offending entry lives in the EXEMPT block of ${BASH_SOURCE[0]}"
    log_error "An exemption is a hole in the 'ci-complete is the required check' promise."
    log_error "It must say why the job genuinely cannot be aggregated."
    exit 1
fi

# ---------------------------------------------------------------------------
# Parsers. All three read the real files, not a copy.
# ---------------------------------------------------------------------------

# top_level_jobs <workflow> -> one job name per line
#
# Job keys are the only 2-space-indented bare keys after the `jobs:` line; job
# bodies sit at 4 spaces or deeper. Scoping to the jobs block keeps the `on:` /
# `permissions:` / `concurrency:` keys (also 2-space) out.
top_level_jobs() {
    awk '
        /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
        in_jobs && /^[^[:space:]#]/ { in_jobs = 0 }
        in_jobs && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
            key = $0
            sub(/^  /, "", key)
            sub(/:[[:space:]]*$/, "", key)
            print key
        }
    ' "$1"
}

# job_block <workflow> <job> -> the lines of that job, body only
job_block() {
    awk -v want="$2" '
        $0 ~ ("^  " want ":[[:space:]]*$") { in_job = 1; next }
        in_job && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { in_job = 0 }
        in_job { print }
    ' "$1"
}

# needs_names <block-file> -> one dependency job name per line
#
# `needs: [a, b, c]` is the form ci.yml uses. The brackets, commas and the key
# itself are stripped; a bare `needs: a` form also survives.
needs_names() {
    awk '
        /^[[:space:]]*needs:/ {
            line = $0
            sub(/^[[:space:]]*needs:[[:space:]]*/, "", line)
            gsub(/[][,]/, " ", line)
            n = split(line, parts, /[[:space:]]+/)
            for (i = 1; i <= n; i++) if (parts[i] != "") print parts[i]
        }
    ' "$1"
}

# result_vars <block-file> -> one RESULT_* env var name per line
result_vars() {
    awk '
        match($0, /RESULT_[A-Z0-9_]+:/) {
            print substr($0, RSTART, RLENGTH - 1)
        }
    ' "$1"
}

# tier_entries <assert-script> -> one tier member per line (HARD and SOFT)
#
# Reads the real HARD_REQUIRED / SOFT_REQUIRED arrays, including the `+=` form
# the pointer-bump fast path uses, so a member added there is seen here.
tier_entries() {
    awk '
        /^(HARD_REQUIRED|SOFT_REQUIRED)\+?=\(/ {
            collecting = 1
            sub(/^[^(]*\(/, "")
        }
        collecting {
            line = $0
            if (index(line, ")") > 0) {
                sub(/\).*$/, "", line)
                collecting = 0
            }
            sub(/#.*$/, "", line)
            n = split(line, parts, /[[:space:]]+/)
            for (i = 1; i <= n; i++) if (parts[i] != "") print parts[i]
        }
    ' "$1"
}

# result_var_for <job-name> -> RESULT_<JOB> with dashes folded to underscores
result_var_for() {
    local upper
    upper="$(printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_')"
    printf 'RESULT_%s' "$upper"
}

# ---------------------------------------------------------------------------
# Gather.
# ---------------------------------------------------------------------------

log_step "Checking that every ci.yml job reaches the $AGGREGATOR verdict..."

JOBS=()
while IFS= read -r j; do
    [[ -n "$j" ]] && JOBS+=("$j")
done < <(top_level_jobs "$CI_WORKFLOW")

if ((${#JOBS[@]} < MIN_JOBS)); then
    log_error "Parsed only ${#JOBS[@]} top-level job(s) from $CI_WORKFLOW (floor is $MIN_JOBS)."
    log_error "The workflow layout changed and this gate is blind. Fix the parser, do not lower the floor."
    exit 1
fi

BLOCK_FILE="$(mktemp)"
trap 'rm -f "$EXEMPT_FILE" "$BLOCK_FILE"' EXIT
job_block "$CI_WORKFLOW" "$AGGREGATOR" >"$BLOCK_FILE"

if [[ ! -s "$BLOCK_FILE" ]]; then
    log_error "No job named '$AGGREGATOR' in $CI_WORKFLOW."
    log_error "Either the required status check was renamed (update AGGREGATOR here) or it is gone."
    exit 1
fi

declare -A NEEDS=()
needs_count=0
while IFS= read -r n; do
    [[ -z "$n" ]] && continue
    NEEDS["$n"]=1
    needs_count=$((needs_count + 1))
done < <(needs_names "$BLOCK_FILE")

declare -A RESULTS=()
while IFS= read -r r; do
    [[ -n "$r" ]] && RESULTS["$r"]=1
done < <(result_vars "$BLOCK_FILE")

declare -A TIERS=()
while IFS= read -r t; do
    [[ -n "$t" ]] && TIERS["RESULT_$t"]=1
done < <(tier_entries "$ASSERT_SCRIPT")

# Anti-vacuity, one floor per input: an empty set here would make its checks
# pass by asserting over nothing.
if ((needs_count == 0)); then
    log_error "$AGGREGATOR has no 'needs:' list in $CI_WORKFLOW: it aggregates nothing."
    exit 1
fi
if ((${#RESULTS[@]} == 0)); then
    log_error "$AGGREGATOR passes no RESULT_* env vars in $CI_WORKFLOW: assert-ci-complete.sh judges nothing."
    exit 1
fi
if ((${#TIERS[@]} == 0)); then
    log_error "No HARD_REQUIRED / SOFT_REQUIRED members parsed from $ASSERT_SCRIPT: this gate is blind."
    exit 1
fi

declare -A IS_JOB=()
for j in "${JOBS[@]}"; do IS_JOB["$j"]=1; done

# ---------------------------------------------------------------------------
# Check.
# ---------------------------------------------------------------------------

missing_needs=()
missing_results=()
phantom_needs=()
untiered_results=()
orphan_tiers=()
dead_exemptions=()

# Liveness. A BLOCKER proves a reason existed once; it cannot prove the reason
# is still true. An exemption for a job that no longer exists is a hole held
# open by nothing, and it is invisible unless something asks. See the liveness
# section of docs/agent-reference/suppressions.md.
for e in "${!EXEMPT_ENTRIES[@]}"; do
    [[ -z "${IS_JOB[$e]:-}" ]] && dead_exemptions+=("$e")
done

for j in "${JOBS[@]}"; do
    [[ -n "${EXEMPT_ENTRIES[$j]:-}" ]] && continue
    var="$(result_var_for "$j")"
    [[ -z "${NEEDS[$j]:-}" ]] && missing_needs+=("$j")
    [[ -z "${RESULTS[$var]:-}" ]] && missing_results+=("$j -> $var")
done

for n in "${!NEEDS[@]}"; do
    [[ -z "${IS_JOB[$n]:-}" ]] && phantom_needs+=("$n")
done

for r in "${!RESULTS[@]}"; do
    [[ -z "${TIERS[$r]:-}" ]] && untiered_results+=("$r")
done

for t in "${!TIERS[@]}"; do
    [[ -z "${RESULTS[$t]:-}" ]] && orphan_tiers+=("$t")
done

echo ""
echo "CI Job Aggregation"
echo "============================================================"
echo "${#JOBS[@]} top-level job(s) in $(basename "$CI_WORKFLOW"); \
${#EXEMPT_ENTRIES[@]} exempt; $needs_count in ${AGGREGATOR}'s needs; \
${#RESULTS[@]} RESULT_* var(s); ${#TIERS[@]} tier member(s)."
echo ""

failed=false

if ((${#missing_needs[@]} > 0)); then
    log_error "${#missing_needs[@]} job(s) NOT in ${AGGREGATOR}'s needs: they can fail while the required check stays green:"
    for j in "${missing_needs[@]}"; do echo "  $j"; done
    echo "  Fix: add each to the 'needs:' list of $AGGREGATOR in $CI_WORKFLOW,"
    echo "  or add it to the exempt block in this script with a BLOCKER reason."
    failed=true
fi

if ((${#missing_results[@]} > 0)); then
    log_error "${#missing_results[@]} job(s) with no RESULT_* env var: assert-ci-complete.sh never sees them:"
    for j in "${missing_results[@]}"; do echo "  $j"; done
    echo "  Fix: add 'RESULT_<JOB>: \${{ needs.<job>.result }}' to the env: block of $AGGREGATOR."
    failed=true
fi

if ((${#phantom_needs[@]} > 0)); then
    log_error "${#phantom_needs[@]} needs entry/entries naming no such job: GitHub rejects this workflow:"
    for n in "${phantom_needs[@]}"; do echo "  $n"; done
    failed=true
fi

if ((${#untiered_results[@]} > 0)); then
    log_error "${#untiered_results[@]} RESULT_* var(s) in neither HARD_REQUIRED nor SOFT_REQUIRED: passed and dropped:"
    for r in "${untiered_results[@]}"; do echo "  $r"; done
    echo "  Fix: add the job to a tier in $ASSERT_SCRIPT."
    failed=true
fi

if ((${#orphan_tiers[@]} > 0)); then
    log_error "${#orphan_tiers[@]} tier member(s) that $AGGREGATOR never passes: the tier reads an unset var and every run is red:"
    for t in "${orphan_tiers[@]}"; do echo "  $t"; done
    failed=true
fi

if ((${#dead_exemptions[@]} > 0)); then
    log_error "${#dead_exemptions[@]} exempt entry/entries naming no such job: a hole held open for nothing:"
    for e in "${dead_exemptions[@]}"; do echo "  $e"; done
    echo "  Fix: delete the entry (and its BLOCKER) from the exempt block in this script."
    failed=true
fi

if [[ "$failed" == "true" ]]; then
    echo ""
    log_error "$AGGREGATOR is the required status check. A job it cannot see is a job that cannot block a merge."
    exit 1
fi

log_info "OK: every non-exempt ci.yml job is aggregated by $AGGREGATOR and tiered."

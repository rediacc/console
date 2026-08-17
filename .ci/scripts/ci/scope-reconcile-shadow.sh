#!/bin/bash
# Skip-plan reconciliation. POLARITY DEPENDS ON SCOPE_MODE, and that is the
# whole design of this file.
#
#   SCOPE_MODE=reduced  -- this run SKIPPED work because a plan said it could.
#                          Every way of failing to verify that plan is a HARD
#                          FAIL (exit 1): a missing plan artifact, an unreadable
#                          Jobs API, an absent node, a reconciler that times out
#                          or disagrees. A reduction nobody can verify is a skip
#                          nobody attested, which is precisely the failure this
#                          gate exists to catch. "Could not measure" must not be
#                          the cheapest way to skip a suite.
#
#   anything else        -- full, empty, or absent: the run executed everything,
#     (full/empty/unset)   so there is no reduction to attest and nothing here
#                          can be load-bearing. Behaviour is unchanged from the
#                          shadow era: loud notes, exit 0, gaps reported as gaps.
#
# It was SHADOW-ONLY until 2026-07-31, when D-1 flipped the scope engine live.
# Before that it ran the REAL reconciler against the REAL per-job outcomes and
# printed a verdict it never acted on, which is the evidence that had to exist
# before the reducing half could be trusted. The filename is unchanged because
# ci.yml wires this exact path.
#
# WHY IT CAN BE TRUSTED ON A RERUN, measured rather than assumed. The Jobs API
# call below uses the DEFAULT filter (`latest`), and the obvious worry is that
# on attempt 2 it would return only the re-run jobs, so every job that passed on
# attempt 1 would read as missing and a `rerun --failed` would red every planned
# key. It does not. Checked against two real console runs on 2026-07-31:
#   - run 30612674911 (attempt 4, `rerun --failed`): the default filter returns
#     all 34 jobs, every record tagged run_attempt=4, and comparing name-by-name
#     against attempt 1 only the three failures and one skip flipped to success.
#     The 15 jobs that succeeded on attempt 1 still report success.
#   - run 30606804258 (attempt 2): 95 jobs both attempts, and only the two
#     attempt-1 failures differ.
# GitHub materialises a COMPLETE job list per attempt, copying the conclusion of
# every job that was not re-run. So the hard gate is NOT scoped to
# GITHUB_RUN_ATTEMPT == 1; it applies to every attempt. (`filter=all` returns
# the union across attempts, 136 records for the first run, which is the wrong
# input here: it would show one job with several conclusions.)
#
# PRE-EXISTING SKIPS ARE ENCODED, not merely warned about. The plan carries the
# three conditions (`full_suite` false on push-to-main, `pointer_bump_only` true
# on a submodule-pointer PR, `is_bot` true on a bot push) and the reconciler
# exempts the keys each one skips, so a run of that shape reconciles clean
# instead of reporting up to seventeen false failures. See
# skip-plan-reconcile.cjs's PREEXISTING_CONDITIONS. A clean verdict whose every
# key was excused proves nothing, which is why the CLI prints the exempt keys
# alongside the verdict and why the counter that matters is verified keys.
#
# REQUIRED ENV
#   GH_TOKEN            needs `actions: read` to download the plan and read jobs
#   GITHUB_REPOSITORY   owner/name
#   GITHUB_RUN_ID       the run being reconciled
#   SCOPE_MODE          the scope step's `scope_mode` output. 'reduced' arms the
#                       hard gate; anything else (including unset) does not.
#   GITHUB_STEP_SUMMARY optional; falls back to stdout when running locally
#
# LOCAL RUN
#   GITHUB_REPOSITORY=rediacc/console GITHUB_RUN_ID=<id> \
#     .ci/scripts/ci/scope-reconcile-shadow.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECONCILER="$SCRIPT_DIR/skip-plan-reconcile.cjs"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
OUT_DIR="${SCOPE_SHADOW_OUT:-$SCRIPT_DIR/../../cache/scope-shadow}"
mkdir -p "$OUT_DIR"

# Emit to BOTH the step summary and stdout.
#
# The summary alone was a mistake: GitHub exposes no API for step summaries
# (the job object has no summary field), so everything this script reported was
# readable only by a human in the web UI. An automated caller - the thing most
# likely to be reading this verdict - saw an empty job log and could not tell
# "reported nothing" from "never ran". That is the same unreadable-instrument
# failure this whole mechanism exists to avoid.
#
# stdout lands in the job log, which IS in the API.
emit() {
    printf '%s\n' "$@" | tee -a "$SUMMARY"
}

# HARD TIME BOUND on every external call, and this is the important safety
# property of this script, not a nicety.
#
# This runs inside ci-complete, which is `runs-on: ubuntu-slim` with
# `timeout-minutes: 5`. Per docs/agent-reference/ci-gates.md, a slim job that runs out of
# time is marked CANCELLED with NO failed step, "which reads as neither pass nor
# fail and poisons CI Complete" -- the pipeline's single required check. So a
# hung `gh` retry or a slow artifact download here could cancel the required
# check for the whole PR.
#
# The total ceiling stays well under one minute against that 5-minute budget
# even with the retries below: two downloads plus two Jobs API calls plus one
# reconciler run, each bounded.
GH_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-45}"
bounded() { timeout "$GH_TIMEOUT" "$@"; }

# ARMED only for a run that actually reduced. Compared against the literal
# string: an unset or misspelled SCOPE_MODE leaves the gate disarmed, which is
# the safe direction here because a run that did not reduce has nothing to
# attest. The reducing half owns the opposite polarity (scope-shadow.sh emits
# no `run_*=false` line unless it wrote the plan this step downloads), so the
# two mistakes cannot combine into a skip nobody checked.
HARD_GATE=false
[[ "${SCOPE_MODE:-}" == "reduced" ]] && HARD_GATE=true

emit "### Skip-plan reconciliation (SCOPE_MODE=${SCOPE_MODE:-<unset>}, hard gate: ${HARD_GATE})" ""

# gap <lines...> -- report an outcome that could not be verified, and leave with
# the exit code this run's polarity demands. There is exactly one exit path for
# every "cannot measure" branch, so the polarity cannot be got right in one
# branch and wrong in the next.
gap() {
    emit "$@"
    if [[ "$HARD_GATE" == "true" ]]; then
        emit "" "**RECONCILIATION FAILED.** This run SKIPPED work on the strength of a plan" \
            "(scope_mode=reduced) and that plan could not be verified against what the run" \
            "actually did. An unverifiable reduction is a skip nobody attested, so this is" \
            "red rather than a note. Add the \`full-ci\` label and re-run for an" \
            "unconditional round." ""
        exit 1
    fi
    emit "_(scope_mode is not 'reduced', so nothing was skipped on this plan's word and" \
        "this is a gap in the evidence rather than a failure.)_" ""
    exit 0
}

# TOOL PROBE, and it is not defensive boilerplate. ci-complete runs on
# ubuntu-slim, where NO other job uses node and none sets it up
# (assert-ci-complete.sh is pure bash; only `gh` is evidenced there, by
# finalize-release-sentinel). If node is absent, running the reconciler would
# exit 127 and this script would dutifully print a verdict it never computed:
# the precise dead-instrument failure this whole programme exists to eliminate.
# An absent tool must read as "could not measure", never as a result -- and on a
# reduced run "could not measure" is now red, because otherwise dropping node
# from the runner would be a way to skip suites unaudited.
for tool in gh node; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        gap "_**cannot reconcile**: \`$tool\` is not available on this runner" \
            "(ci-complete runs on ubuntu-slim). Fix by adding setup-node to ci-complete," \
            "or by moving this step to a job on ubuntu-latest._" ""
    fi
done

# ONE RETRY on each external call, no more. When this step could only lose a
# measurement, a transient 502 cost nothing; now it can red the required check,
# so a single retry is the cheapest thing that separates "GitHub blinked" from
# "there is nothing to reconcile". Not a loop: if the second call fails too, the
# honest answer is that we cannot verify, and spending ci-complete's 5-minute
# budget asking again makes that answer later rather than better.
#
# Each attempt re-truncates its own output files. Retrying under ONE `>` would
# append the second response after the first's partial bytes and hand the
# reconciler concatenated garbage, which parses as a malformed payload and reads
# as a verdict.

# The plan was uploaded by initialize's scope step earlier in THIS run. The name
# is the bare `ci-skip-plan`, NOT run-id-suffixed: artifact names are already
# scoped per run, and scope-engine's createRepoIo looks up exactly this name
# when a LATER run goes hunting for a baseline. A suffixed name would be
# undiscoverable by the very consumer it exists for.
download_plan() {
    local attempt
    for attempt in 1 2; do
        rm -rf "$OUT_DIR/plan-dl"
        if bounded gh run download "${GITHUB_RUN_ID:-}" --repo "${GITHUB_REPOSITORY:-}" \
            -n "ci-skip-plan" -D "$OUT_DIR/plan-dl" >/dev/null 2>"$OUT_DIR/plan-dl.err"; then
            return 0
        fi
        [[ "$attempt" -eq 1 ]] && emit "_(the plan download failed; retrying once)_"
    done
    return 1
}

# Per-job outcomes, the thing the reconciler compares intent against.
# gh's stderr is KEPT, not discarded. Same defect class as a swallowed exception
# in the plan writer one file over: this branch already says "gap in the
# evidence", but without gh's own explanation a rate limit, an expired token and
# a 404 are one indistinguishable message, and the next session re-derives which
# one it was from nothing.
read_jobs() {
    local attempt
    for attempt in 1 2; do
        if bounded gh api "repos/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}/jobs?per_page=100" \
            --paginate >"$OUT_DIR/jobs.json" 2>"$OUT_DIR/jobs.err"; then
            return 0
        fi
        [[ "$attempt" -eq 1 ]] && emit "_(the jobs API call failed; retrying once)_"
    done
    return 1
}

if ! download_plan; then
    gap "_no attested plan for this run: nothing to reconcile (expected on push-to-main," \
        "where the scope step does not run)._" '```' \
        "$(head -c 500 "$OUT_DIR/plan-dl.err" 2>/dev/null)" '```' ""
fi

if ! read_jobs; then
    gap "_could not read the jobs API, so the run's actual per-job outcomes are" \
        "unavailable._" '```' \
        "$(head -c 500 "$OUT_DIR/jobs.err" 2>/dev/null)" '```' ""
fi

set +e
bounded node "$RECONCILER" --plan "$OUT_DIR/plan-dl/plan.json" \
    --jobs "$OUT_DIR/jobs.json" --run-id "${GITHUB_RUN_ID:-}" \
    >"$OUT_DIR/reconcile.out" 2>"$OUT_DIR/reconcile.err"
rc=$?
set -e

final=0
if [[ $rc -eq 124 ]]; then
    # 124 is `timeout` killing it, NOT the reconciler's verdict. Reporting this
    # as a reconcile failure would re-create, one line lower, exactly the
    # fabricated-verdict bug the tool probe above exists to prevent: the
    # reconciler never reached a conclusion, so there is nothing to report. On a
    # reduced run it is still red, because an unreached conclusion leaves the
    # skips unattested just as surely as a refused one.
    emit "_**cannot reconcile**: the reconciler exceeded ${GH_TIMEOUT}s and was killed." \
        "This is a GAP IN THE EVIDENCE, not a verdict._" ""
    [[ "$HARD_GATE" == "true" ]] && final=1
elif [[ $rc -eq 0 ]]; then
    emit "**reconciled** (exit 0). Check the \`pre-existing skips\` line below before" \
        "banking it: a pass whose every key was excused by \`full_suite\`," \
        "\`pointer_bump_only\` or \`is_bot\` is a VACUOUS pass, and the counter that has to" \
        "move is verified keys, not runs." ""
else
    emit "**reconcile FAILED** (exit ${rc}). Read the reason before blaming the plan." \
        "\`preexisting-claim-mismatch\` means the plan's annotation disagrees with what" \
        "its own recorded conditions imply, i.e. a tampered artifact or writer/reader" \
        "drift, NOT a scope error." ""
    [[ "$HARD_GATE" == "true" ]] && final=1
fi
emit '```'
head -c 3000 "$OUT_DIR/reconcile.err" 2>/dev/null | tee -a "$SUMMARY"
head -c 1500 "$OUT_DIR/reconcile.out" 2>/dev/null | tee -a "$SUMMARY"
emit '```'

if [[ $final -ne 0 ]]; then
    emit "" "**RECONCILIATION FAILED.** This run SKIPPED work on the strength of a plan" \
        "(scope_mode=reduced) that does not describe what the run actually did. Add the" \
        "\`full-ci\` label and re-run for an unconditional round." ""
fi

exit "$final"

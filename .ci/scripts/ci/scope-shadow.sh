#!/bin/bash
# Scope engine, SHADOW mode: publish what the engine WOULD decide, and decide
# nothing.
#
# Nothing in the pipeline reads this output, no job is gated on it, and this
# script always exits 0. It exists to gather evidence on real traffic BEFORE
# anything is allowed to skip work, which is the operator's stated D-1
# fallback ("if it slips, ship shadow").
#
# It answers two questions, deliberately kept separate:
#
#   --classify over the merge-base delta
#       What today's PR would scope to. Works immediately.
#
#   --resolve-baseline
#       Whether a REDUCED round is possible at all against the last green FULL
#       run. Today this reports `baseline:none-usable`, because a usable
#       baseline requires an attested plan whose outcome was RECONCILED and the
#       reconciler is not wired yet. That is the correct answer rather than a
#       bug, and seeing it in the log is the entire point: it is the counter
#       that has to move before any of this can be trusted.
#
# WHAT IT DELIBERATELY DOES NOT DO: it does not write a `reconciled` flag.
# Doing so would attest to an outcome nobody verified, and the engine would
# then chain reduced rounds off an unverified baseline. The plan stays unusable
# as a baseline until ci-complete reconciles it against actual per-job results.
#
# REQUIRED ENV
#   MERGE_SHA           github.sha (CI checks out the MERGE commit)
#   HEAD_SHA            github.event.pull_request.head.sha (fallback only)
#   GITHUB_REPOSITORY   owner/name, for `gh run list`
#   GH_TOKEN            needs `actions: read` for the run/artifact lookups
#   GITHUB_STEP_SUMMARY optional; falls back to stdout when running locally
#
# REQUIRES a non-shallow clone. With the default depth-1 checkout the engine
# answers `baseline:shallow-clone` on every run and reports full CI forever
# while looking healthy, which is D9's exact failure shape. The `fetch-depth: 0`
# on initialize's checkout and this script land together or not at all.
#
# LOCAL RUN
#   MERGE_SHA=$(git rev-parse HEAD) HEAD_SHA=$(git rev-parse HEAD) \
#   GITHUB_REPOSITORY=rediacc/console .ci/scripts/ci/scope-shadow.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$SCRIPT_DIR/scope-engine.cjs"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

# Outputs go under .ci/cache/ (gitignored, .gitignore:118) rather than the repo
# root. Running this locally used to drop changed.raw and three scope-*.json
# files as untracked litter in the working tree, which in a repo where sessions
# share a tree is one `git add -A` away from being committed by someone else.
OUT_DIR="${SCOPE_SHADOW_OUT:-$SCRIPT_DIR/../../cache/scope-shadow}"
mkdir -p "$OUT_DIR"

# Emit to BOTH the step summary and stdout.
#
# The summary alone was a mistake: GitHub exposes no API for step summaries
# (the job object has no summary field), so everything this script reported was
# readable only by a human in the web UI. An automated caller - the thing most
# likely to be reading a SHADOW observer's verdict - saw an empty job log and
# could not tell "reported nothing" from "never ran". That is the same
# unreadable-instrument failure this whole mechanism exists to avoid.
#
# stdout lands in the job log, which IS in the API.
emit() {
    printf '%s\n' "$@" | tee -a "$SUMMARY"
}

# Time bound, for the same reason as the reconcile shadow: this runs inside
# `initialize`, which every other job depends on, so a hang here stalls the
# ENTIRE pipeline rather than just losing a measurement. --resolve-baseline
# makes up to `limit` candidate lookups, each one a `gh run list` plus a
# `gh run download`, so the call count is bounded but the latency is not.
# A shadow observer must never be able to cost more than the data it gathers.
SCOPE_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-120}"
bounded() { timeout "$SCOPE_TIMEOUT" "$@"; }

# CI checks out the merge commit, whose ^1 is the base and ^2 the PR head.
# Both may be absent (a non-merge checkout, or a shallow clone that never
# fetched the parents), so neither is assumed.
# `--verify -q` is load-bearing. Plain `git rev-parse SHA^2` on a NON-merge
# commit prints the unresolved ref to stdout before failing, so a
# `|| echo "$HEAD_SHA"` fallback yields TWO lines and every downstream use gets
# garbage. Caught by running this: head became "<sha>^2\n<sha>", the diff came
# back empty, and the engine dutifully reported `empty-delta` -- which is
# indistinguishable in the log from a PR that genuinely changed nothing.
base="$(git rev-parse --verify -q "${MERGE_SHA}^1" 2>/dev/null || true)"
head="$(git rev-parse --verify -q "${MERGE_SHA}^2" 2>/dev/null || true)"
[[ -z "$head" ]] && head="${HEAD_SHA:-}"
shallow="$(git rev-parse --is-shallow-repository 2>/dev/null || echo unknown)"

emit "### Scope engine (shadow, decides nothing)" \
    "" \
    "shallow: \`${shallow}\` (must be false, or nothing below is meaningful)" \
    "base: \`${base:-unknown}\`  head: \`${head:-unknown}\`" \
    ""

if [[ -n "$base" && -n "$head" ]]; then
    git diff-tree -r --raw --no-commit-id "$base" "$head" >"$OUT_DIR/changed.raw" 2>/dev/null || true
    bounded node "$ENGINE" --classify --files "$OUT_DIR/changed.raw" >"$OUT_DIR/scope-classify.json" 2>/dev/null || true
    emit "**--classify over the merge-base delta**" "" '```json'
    head -c 4000 "$OUT_DIR/scope-classify.json" 2>/dev/null | tee -a "$SUMMARY" || emit "(no output)"
    emit '```' ""
else
    emit "_skipped --classify: no base/head pair resolved_" ""
fi

# Emit an ATTESTED-SHAPED plan: the classify verdict plus the run identity the
# reconciler checks (skip-plan-reconcile.cjs refuses a plan whose run_id is not
# this run's, as anti-tamper). Uploaded under the name --resolve-baseline looks
# for, deliberately:
#
#   - it proves the whole artifact path end to end (upload here, discover and
#     download on a LATER run), which is the half that cannot be unit-tested;
#   - and it still cannot be USED, because evaluateBaselineCandidate requires
#     `reconciled: true` and this plan has no such flag. A later run finds it
#     and answers `unreconciled-outcome` instead of `no-skip-plan`, which is a
#     strictly better signal: it says the plumbing works and the ATTESTATION is
#     what is missing.
#
# Writing `reconciled` here would be attesting to an outcome nobody verified.
#
# IT ALSO RECORDS THE PRE-EXISTING SKIP CONDITIONS, which is what makes the
# reconcile non-vacuous. The scope verdict alone is an incomplete prediction:
# ci.yml skips whole columns for reasons that predate the engine (`full_suite`
# is false on push-to-main, `pointer_bump_only` cuts the entire expensive
# pipeline, `is_bot` cuts the staging chain), so a plan saying "unit runs" is
# wrong on every pointer-bump PR and the gate would red seventeen keys on a run
# where nothing went wrong. annotatePlan() writes the observed values and the
# per-job condition; the reconciler re-derives from the same table and
# hard-fails on disagreement, so writer and reader cannot drift.
#
# TRI-STATE ON PURPOSE. Each value is passed through as the literal string and
# annotatePlan records it only when it is exactly "true" or "false". An unset
# variable is OMITTED rather than defaulted, because both defaults are wrong:
# defaulting full_suite to false would exempt sixteen keys on no evidence.
# Omitted means no exemption, which leaves the reconciler at its strict
# reading. Missing information must never widen an exemption.
if [[ -s "$OUT_DIR/scope-classify.json" ]]; then
    # No `2>/dev/null || true` here, and its removal is a fix rather than a
    # style change. Swallowing this writer's stderr made a crash indistinguish-
    # able from "no plan was due": the upload step carries
    # `if-no-files-found: ignore`, so a broken writer produced no artifact and
    # the reconcile shadow then reported the benign-sounding "no attested plan
    # for this run", one run after another, with the actual exception thrown
    # away. The script still cannot fail the job (it ends in exit 0); the
    # difference is that the failure is now READABLE.
    if ! bounded node -e '
const fs = require("fs");
const { annotatePlan } = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
plan.run_id = Number(process.env.GITHUB_RUN_ID || 0);
plan.base_sha = process.argv[3] || null;
plan.head_sha = process.argv[4] || null;
const tri = (v) => (v === "true" ? true : v === "false" ? false : undefined);
annotatePlan(plan, {
  full_suite: tri(process.env.FULL_SUITE),
  pointer_bump_only: tri(process.env.POINTER_BUMP_ONLY),
  is_bot: tri(process.env.IS_BOT),
});
fs.writeFileSync(process.argv[5], JSON.stringify(plan, null, 2));
' "$SCRIPT_DIR/skip-plan-reconcile.cjs" "$OUT_DIR/scope-classify.json" \
        "$base" "$head" "$OUT_DIR/plan.json" 2>"$OUT_DIR/plan-write.err"; then
        emit "_**the plan writer FAILED**: no attested plan will be uploaded for this" \
            "run, so ci-complete's reconcile will report 'no attested plan' and that" \
            "will be a GAP IN THE EVIDENCE, not a clean result._" '```'
        head -c 1000 "$OUT_DIR/plan-write.err" | tee -a "$SUMMARY"
        emit '```' ""
    else
        emit "**pre-existing skip conditions recorded in the plan**" "" '```json'
        bounded node -e '
const p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const exempt = Object.entries(p.jobs || {})
  .filter(([, v]) => v && v.preexisting_skip)
  .map(([k, v]) => `${k}:${v.preexisting_skip}`);
process.stdout.write(JSON.stringify({
  conditions: p.conditions,
  exempt_keys: exempt,
  planned_keys: Object.keys(p.jobs || {}).length,
}, null, 2) + "\n");
' "$OUT_DIR/plan.json" | tee -a "$SUMMARY"
        emit '```' ""
    fi
fi

if [[ -n "$head" ]]; then
    bounded node "$ENGINE" --resolve-baseline \
        --repo "${GITHUB_REPOSITORY}" --head "$head" --merge-sha "${MERGE_SHA}" \
        >"$OUT_DIR/scope-baseline.json" 2>"$OUT_DIR/scope-baseline.err" || true
    emit "**--resolve-baseline** (expect \`baseline:none-usable\` until the reconciler is wired)" "" '```json'
    head -c 4000 "$OUT_DIR/scope-baseline.json" 2>/dev/null | tee -a "$SUMMARY" || emit "(no output)"
    emit '```'
    if [[ -s "$OUT_DIR/scope-baseline.err" ]]; then
        emit "stderr:" '```'
        head -c 1000 "$OUT_DIR/scope-baseline.err" | tee -a "$SUMMARY"
        emit '```'
    fi
fi

# Always green. A shadow observer that can red a run is not a shadow observer.
exit 0

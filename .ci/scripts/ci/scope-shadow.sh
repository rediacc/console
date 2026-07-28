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

emit() { printf '%s\n' "$@" >>"$SUMMARY"; }

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
    git diff-tree -r --raw --no-commit-id "$base" "$head" >changed.raw 2>/dev/null || true
    node "$ENGINE" --classify --files changed.raw >scope-classify.json 2>/dev/null || true
    emit "**--classify over the merge-base delta**" "" '```json'
    head -c 4000 scope-classify.json 2>/dev/null >>"$SUMMARY" || emit "(no output)"
    emit '```' ""
else
    emit "_skipped --classify: no base/head pair resolved_" ""
fi

if [[ -n "$head" ]]; then
    node "$ENGINE" --resolve-baseline \
        --repo "${GITHUB_REPOSITORY}" --head "$head" --merge-sha "${MERGE_SHA}" \
        >scope-baseline.json 2>scope-baseline.err || true
    emit "**--resolve-baseline** (expect \`baseline:none-usable\` until the reconciler is wired)" "" '```json'
    head -c 4000 scope-baseline.json 2>/dev/null >>"$SUMMARY" || emit "(no output)"
    emit '```'
    if [[ -s scope-baseline.err ]]; then
        emit "stderr:" '```'
        head -c 1000 scope-baseline.err >>"$SUMMARY"
        emit '```'
    fi
fi

# Always green. A shadow observer that can red a run is not a shadow observer.
exit 0

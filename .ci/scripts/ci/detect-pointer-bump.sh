#!/bin/bash
# Detect a "pointer bump only" PR head: content provably identical to a commit
# that already passed full CI, differing only in submodule gitlinks that moved
# to tree-identical commits now on the submodules' main (the post-squash bump
# that /pr-merge pushes right before landing).
#
# When it fires, ci.yml skips the expensive jobs (builds, tests, the install
# matrix) and the run goes green in minutes -- honestly, because the proof is
# content identity, not trust. Any doubt on any test degrades to full CI.
#
# The proof, in order (every step fail-safe to pointer_bump_only=false):
#   1. Walk HEAD backwards (single-parent commits only, cap WALK_CAP): every
#      commit on the way must change ONLY gitlinks (mode 160000 -> 160000).
#      The first non-pointer commit is the BASELINE.
#   2. The baseline must carry a successful "CI Complete" check run.
#   3. For the NET gitlink diff baseline..HEAD, each move old->new must be
#      tree-identical (commit tree SHAs equal => byte-identical content; the
#      squash commit of an unchanged branch tip) AND new must be an ancestor
#      of the submodule's main (compare NEW...main => main is 'ahead' of or
#      'identical' to NEW; 'behind'/'diverged' mean unmerged or drifted).
#
# Called from initialize.sh AFTER submodule init (the token insteadOf rewrite
# is configured there, making `git fetch origin` authenticated).
#
# Usage: detect-pointer-bump.sh [--output FILE]
# Env:
#   GITHUB_EVENT_NAME   - only 'pull_request' can fast-path
#   GITHUB_REPOSITORY   - console repo slug (check-runs lookup)
#   CHECKS_TOKEN        - plain GITHUB_TOKEN; checks:read on console
#   GITHUB_PAT          - app token; contents:read on the submodule repos
#   GITHUB_STEP_SUMMARY - optional; receives the proof line
# Outputs: pointer_bump_only=true|false, baseline_sha=<sha or empty>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
OUTPUT_FILE="${ARG_OUTPUT:-}"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

WALK_CAP=5

write_output() {
    local key="$1"
    local value="$2"
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "${key}=${value}" >>"$OUTPUT_FILE"
    fi
    echo "${key}=${value}"
}

no_fast_path() {
    log_info "pointer_bump_only=false -- $1"
    write_output "pointer_bump_only" "false"
    write_output "baseline_sha" ""
    exit 0
}

[[ "${GITHUB_EVENT_NAME:-}" == "pull_request" ]] || no_fast_path "not a pull_request event"

# Shallow (depth-1) checkout: the walk needs parents and their trees. Local
# full clones (verification runs) skip the deepen -- it errors on non-shallow.
if [[ -f "$(git rev-parse --git-dir)/shallow" ]]; then
    git fetch --no-recurse-submodules --quiet --deepen=$((WALK_CAP + 1)) origin 2>/dev/null ||
        no_fast_path "could not deepen history"
fi

# --- Step 1: find the baseline ------------------------------------------------
current=$(git rev-parse HEAD)
baseline=""
for _ in $(seq 1 "$WALK_CAP"); do
    if git rev-parse --verify --quiet "${current}^2" >/dev/null; then
        no_fast_path "merge commit ${current:0:7} in the walk"
    fi
    parent=$(git rev-parse --verify --quiet "${current}^") ||
        no_fast_path "parent of ${current:0:7} unavailable"
    # -r is load-bearing: without it a nested gitlink change reports as its
    # parent TREE (":040000 040000 ... private") and never matches 160000.
    raw=$(git diff-tree -r --raw "$parent" "$current")
    [[ -n "$raw" ]] || no_fast_path "empty commit ${current:0:7}"
    if grep -vE '^:160000 160000 ' <<<"$raw" | grep -q .; then
        # First commit that touches anything beyond existing gitlinks.
        if [[ "$current" == "$(git rev-parse HEAD)" ]]; then
            no_fast_path "HEAD is not a pointer-only commit"
        fi
        break
    fi
    baseline="$parent"
    current="$parent"
done
[[ -n "$baseline" ]] || no_fast_path "no baseline within $WALK_CAP commits"

# --- Step 2: baseline must have passed full CI --------------------------------
green=$(GH_TOKEN="${CHECKS_TOKEN:-}" gh api -X GET \
    "repos/${GITHUB_REPOSITORY}/commits/${baseline}/check-runs" \
    -f check_name='CI Complete' \
    --jq '[.check_runs[] | select(.conclusion == "success")] | length' 2>/dev/null) ||
    no_fast_path "check-runs lookup failed for baseline ${baseline:0:7}"
[[ "${green:-0}" -ge 1 ]] || no_fast_path "baseline ${baseline:0:7} has no successful CI Complete"

# --- Step 3: every net gitlink move is tree-identical and merged ---------------
net=$(git diff-tree -r --raw "$baseline" HEAD)
if grep -vE '^:160000 160000 ' <<<"$net" | grep -q .; then
    no_fast_path "net diff vs baseline is not gitlink-only"
fi

proof=""
while IFS=$'\t' read -r meta sm_path; do
    [[ -n "$meta" ]] || continue
    old_sha=$(awk '{print $3}' <<<"$meta")
    new_sha=$(awk '{print $4}' <<<"$meta")
    # Two steps, not a pipe into xargs -r: with -r an empty lookup exits 0,
    # so the no-entry error could never fire (automated review finding; it
    # fell through to the generic parse error instead -- fail-safe but mute).
    sm_key=$(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' |
        awk -v p="$sm_path" '$2 == p {print $1}')
    [[ -n "$sm_key" ]] || no_fast_path "no .gitmodules entry for $sm_path"
    sm_url=$(git config -f .gitmodules --get "${sm_key%.path}.url") ||
        no_fast_path "no url for ${sm_key%.path} in .gitmodules"
    sm_repo=$(sed -E 's#\.git$##; s#.*[:/]([^/]+/[^/]+)$#\1#' <<<"$sm_url")
    [[ -n "$sm_repo" ]] || no_fast_path "cannot parse repo from $sm_url"

    tree_old=$(GH_TOKEN="${GITHUB_PAT:-}" gh api "repos/${sm_repo}/commits/${old_sha}" \
        --jq '.commit.tree.sha' 2>/dev/null) ||
        no_fast_path "cannot read $sm_repo@${old_sha:0:7}"
    tree_new=$(GH_TOKEN="${GITHUB_PAT:-}" gh api "repos/${sm_repo}/commits/${new_sha}" \
        --jq '.commit.tree.sha' 2>/dev/null) ||
        no_fast_path "cannot read $sm_repo@${new_sha:0:7}"
    [[ "$tree_old" == "$tree_new" ]] ||
        no_fast_path "$sm_path trees differ (${old_sha:0:7} vs ${new_sha:0:7} -- submodule main moved?)"

    # compare BASE...HEAD reports HEAD relative to BASE: main 'ahead' of (or
    # 'identical' to) NEW means NEW is an ancestor of main.
    status=$(GH_TOKEN="${GITHUB_PAT:-}" gh api "repos/${sm_repo}/compare/${new_sha}...main" \
        --jq '.status' 2>/dev/null) ||
        no_fast_path "compare failed for $sm_repo"
    case "$status" in
        identical | ahead) ;;
        *) no_fast_path "$sm_path new commit not on $sm_repo main (status: $status)" ;;
    esac
    proof+="$sm_path ${old_sha:0:7}->${new_sha:0:7} (tree-identical, on ${sm_repo} main); "
done <<<"$net"

log_info "pointer_bump_only=true -- baseline ${baseline:0:7} passed CI Complete; $proof"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
        echo "### Pointer-bump fast path"
        echo "Content-identical to \`${baseline}\` (successful CI Complete). Moves: ${proof}"
        echo "Expensive jobs are skipped; ci-complete accepts their skips via POINTER_BUMP_ONLY."
    } >>"$GITHUB_STEP_SUMMARY"
fi
write_output "pointer_bump_only" "true"
write_output "baseline_sha" "$baseline"

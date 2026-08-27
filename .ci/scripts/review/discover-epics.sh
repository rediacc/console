#!/usr/bin/env bash
# Emit the epic ids a branch declares, as a JSON array, for a workflow matrix.
#
# EXTRACTED FROM THE WORKFLOW, and not only because the inline block was 17
# logic lines against a limit of 8. The inline version re-implemented the
# snapshot parse that `review_epic_ids` in .ci/scripts/lib/common.sh already
# does, so there were two copies of one rule -- and two copies drift. The prose
# copy is the one that drifted last time, in branch-rebase.md.
#
# THE EMPTY CASE IS THE ONE TO GET RIGHT. A matrix over an empty array does not
# run the job AT ALL, so a PR with no epics would get NO review whatsoever --
# far worse than the crowding per-epic review exists to fix. This emits [""],
# producing exactly one pass with an empty epic, which is byte for byte the flat
# review that existed before epics.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq

branch="${PR_HEAD_REF:-}"
if [[ -z "$branch" ]]; then
    log_error "PR_HEAD_REF is unset; refusing to guess a branch and silently report no epics"
    exit 1
fi

ids=()
while IFS= read -r id; do
    [[ -n "$id" ]] && ids+=("$id")
done < <(review_epic_ids "$branch")

if [[ ${#ids[@]} -eq 0 ]]; then
    echo "no epics declared for ${branch}; one flat review pass will run"
    echo 'epics=[""]' >>"${GITHUB_OUTPUT:-/dev/stdout}"
    exit 0
fi

printf 'epics for %s: %s\n' "$branch" "${ids[*]}"
printf '%s\n' "${ids[@]}" | jq -R . | jq -sc . | {
    read -r json
    echo "epics=$json" >>"${GITHUB_OUTPUT:-/dev/stdout}"
}

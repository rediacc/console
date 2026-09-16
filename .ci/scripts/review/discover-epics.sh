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

# emit <line> -- append one `key=value` to $GITHUB_OUTPUT, or print it.
#
# NOT `>>"${GITHUB_OUTPUT:-/dev/stdout}"`, which is what both call sites below
# were until 2026-09-10. Opening /dev/stdout FAILS with ENXIO ("No such device
# or address") when stdout is a UNIX SOCKET, and a socket is exactly what
# Node's child_process.spawnSync hands a child -- including this repo's own
# scripts/lib/shadow-gate.ts harness. The script then printed its human line,
# LOST the epics= line entirely and exited 1: a failure report from a run that
# had already done its work, with the one output the workflow reads missing.
# Reproduced 2026-09-10 with a socketpair on fd 1: twin exit 1, stderr
# "discover-epics.sh: line 36: /dev/stdout: No such device or address".
# GITHUB_OUTPUT is always set in Actions, so the live matrix never hit this;
# every local run and every harness run did.
emit() {
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        printf '%s\n' "$1" >>"$GITHUB_OUTPUT"
    else
        printf '%s\n' "$1"
    fi
}

ids=()
while IFS= read -r id; do
    [[ -n "$id" ]] && ids+=("$id")
done < <(review_epic_ids "$branch")

if [[ ${#ids[@]} -eq 0 ]]; then
    echo "no epics declared for ${branch}; one flat review pass will run"
    emit 'epics=[""]'
    exit 0
fi

printf 'epics for %s: %s\n' "$branch" "${ids[*]}"
printf '%s\n' "${ids[@]}" | jq -R . | jq -sc . | {
    read -r json
    emit "epics=$json"
}

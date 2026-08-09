#!/bin/bash
# Find the open PRs whose autopilot CAMPAIGN is still open, so the 2-hourly
# sweeper can re-dispatch them.
#
# WHY THIS EXISTS. The sweeper used to list label-armed PRs only, and said so:
# "a PR armed only by an open CAMPAIGN carries no label, so this sweep does not
# reach it -- campaign rounds ride their own workflow_run events". That is true
# right up until an event is missed, which is the entire reason a sweeper
# exists. A campaign whose last workflow_run never arrived (a delivery gap, a
# run cancelled at the wrong moment, a rerun that produced no event) then sits
# open forever with nothing scheduled to notice. The label sweep was catching
# exactly the arming path that needs a sweeper least.
#
# PURE: PR list and comment dumps in, PR numbers out. No network, so the
# trust rule below is exercisable offline -- which matters, because it IS the
# trust rule: a campaign is only believed when state-comment.sh `select`
# accepts the comment, i.e. its author is the autopilot bot AND its body
# starts with the exact header. Console is public, so a lookalike comment
# claiming `campaign: open` is the obvious way to make the sweeper dispatch
# rounds against a PR nobody armed; the author check is what makes that fail,
# and the fields are re-normalized on read on top of it.
#
# Usage:
#   sweep-campaigns.sh --prs <file> --comments-dir <dir> --bot <login>
#
#   --prs           JSON: [{"number":N}, ...] (gh pr list --json number) or a
#                   bare [N, ...].
#   --comments-dir  one <number>.json per PR, each the issue-comments array
#                   shaped [{id, author, body}] that state-comment.sh reads.
#                   A PR with no dump is SKIPPED with a warning, never treated
#                   as campaign-less: "could not look" is not "not armed".
#
# Output: one PR number per line, ascending. Exit: 0 (an empty sweep is a
# normal, quiet result), 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
PRS="${ARG_PRS:-}"
COMMENTS_DIR="${ARG_COMMENTS_DIR:-}"
BOT="${ARG_BOT:-}"

[[ -n "$PRS" && -n "$COMMENTS_DIR" && -n "$BOT" ]] || {
    log_error "usage: sweep-campaigns.sh --prs <file> --comments-dir <dir> --bot <login>"
    exit 2
}
require_file "$PRS"
require_dir "$COMMENTS_DIR"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

numbers="$(jq -r '(if type == "array" then . else [] end)
    | map(if type == "object" then .number else . end)
    | map(select(type == "number"))
    | .[]' "$PRS" | LC_ALL=C sort -n)"

found=0
scanned=0
for n in $numbers; do
    dump="$COMMENTS_DIR/$n.json"
    if [[ ! -f "$dump" ]]; then
        log_warn "sweep-campaigns: no comment dump for PR #$n at $dump; skipping (an unreadable PR is not a closed campaign)"
        continue
    fi
    scanned=$((scanned + 1))
    sel="$("$SCRIPT_DIR/state-comment.sh" select --comments "$dump" --bot "$BOT")"
    [[ "$(jq -r '.found' <<<"$sel")" == "true" ]] || continue
    jq -r '.body // ""' <<<"$sel" >"$work/body.txt"
    campaign="$("$SCRIPT_DIR/state-comment.sh" fields --body "$work/body.txt" | jq -r '.campaign')"
    if [[ "$campaign" == "open" ]]; then
        printf '%s\n' "$n"
        found=$((found + 1))
    fi
done

log_info "sweep-campaigns: $found open campaign(s) across $scanned scanned PR(s)"

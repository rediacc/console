#!/bin/bash
# Collect every PR the sweeper should re-dispatch: label-armed UNION
# campaign-armed.
#
# THE UNION IS THE FIX. The sweep used to list label-armed PRs only, and its
# own comment admitted the gap: "a PR armed only by an open CAMPAIGN carries no
# label, so this sweep does not reach it -- campaign rounds ride their own
# workflow_run events". Those events are exactly what a sweeper exists to
# survive the loss of. A campaign whose last event never arrived had nothing
# scheduled to notice, so the sweep was reaching the arming path that needs it
# least and missing the one that needs it most.
#
# READ-ONLY, with github.token: listing PRs and reading comments needs no app
# token, and the dispatch that follows is a separate step with a separate
# credential. Trust in a campaign comes from state-comment.sh `select`
# (bot author + exact header), which sweep-campaigns.sh applies per PR --
# console is public, so a lookalike comment claiming `campaign: open` is the
# obvious way to make this sweep dispatch rounds nobody armed.
#
# Usage:
#   sweep-collect.sh --repo <owner/name> --label <name> --bot <login> \
#     --work <dir> --out <file>
#
# Env: GH_TOKEN. Exit: 0 collected (an empty result is normal), 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
REPO="${ARG_REPO:-}"
LABEL="${ARG_LABEL:-autopilot}"
BOT="${ARG_BOT:-}"
WORK="${ARG_WORK:-}"
OUT="${ARG_OUT:-}"

[[ -n "$REPO" && -n "$BOT" && -n "$WORK" && -n "$OUT" ]] || {
    log_error "usage: sweep-collect.sh --repo <owner/name> --label <name> --bot <login> --work <dir> --out <file>"
    exit 2
}
mkdir -p "$WORK/comments"

gh_json "sweeper open PR list" -- pr list --repo "$REPO" --state open --limit 50 --json number >"$WORK/prs.json"
gh_retry "sweeper label-armed list" -- pr list --repo "$REPO" --label "$LABEL" --state open \
    --json number --jq '.[].number' >"$WORK/label-armed.txt"

# --slurp, and it is load-bearing: `--paginate --jq` applies the filter PER
# PAGE and concatenates, so a PR past 30 comments produces two top-level JSON
# arrays in one file and every downstream reader sees the second one as a
# separate document. --slurp wraps the pages, `.[][]` flattens them back.
while IFS= read -r n; do
    [[ -n "$n" ]] || continue
    # jq as a separate pipe: the runner's gh refuses --slurp with --jq
    # ("not supported"), proven live on the first canary dispatch 2026-08-09.
    gh_retry "comments for PR #$n" -- api "repos/$REPO/issues/$n/comments" --paginate --slurp \
        >"$WORK/comments/$n.raw.json"
    jq '[.[][] | {id, author: .user.login, body}]' "$WORK/comments/$n.raw.json" >"$WORK/comments/$n.json"
done < <(jq -r '.[].number' "$WORK/prs.json")

"$SCRIPT_DIR/sweep-campaigns.sh" --prs "$WORK/prs.json" --comments-dir "$WORK/comments" --bot "$BOT" \
    >"$WORK/campaign-armed.txt"

LC_ALL=C sort -u "$WORK/label-armed.txt" "$WORK/campaign-armed.txt" | grep -E '^[0-9]+$' >"$OUT" || true
log_info "sweeper: $(grep -c . "$OUT" || true) armed PR(s) = $(grep -c . "$WORK/label-armed.txt" || true) label-armed U $(grep -c . "$WORK/campaign-armed.txt" || true) campaign-armed"

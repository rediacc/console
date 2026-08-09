#!/bin/bash
# Render the autopilot state comment and write it to the PR: the ONE place any
# job posts or patches it.
#
# THE LEDGER IS NEVER OPTIONAL (03-v2-autonomy.md section 0). Autopilot commits
# are attributed to the operator, and this comment is the audit trail recording
# every round's run, commit and reasoning. It is also the loop's memory: the
# round counter that bounds the whole design is COUNTED FROM THIS COMMENT, so a
# round that runs without recording itself is a round the termination proof
# cannot see.
#
# ONE WRITER, three callers (the model round, the finish job's rerun round, the
# finish job's campaign close). They differ only in arguments. Splitting them
# back into per-job shell is how the metadata line and the ruled-out section
# would drift apart, which is the same reasoning that made autopilot-gate.sh
# read the metadata line through state-comment.sh instead of re-parsing it.
#
# Usage:
#   update-state.sh --pr <n> --repo <owner/name> [--comment-id <id>] \
#     --body <previous-body-file> --state <s> --round <r> --rounds-max <n> \
#     --head <sha> --last-run "<id/attempt handled>" [--ledger <line>] \
#     [--verdict <file>] [--campaign <c>] [--model <id>] \
#     [--last-sig <hex8>] [--sig-count <n>] [--dry-run]
#
# --dry-run prints the rendered body and writes nothing, so the comment the
# operator actually reads is exercisable offline.
#
# --verdict is the VALIDATED verdict from autopilot-push.sh --verdict-out, not
# handoff.json: the handoff is untrusted model output, and the validator has
# already bounded these arrays. Its ruled_out[] and decisions[] become one
# capped bullet each -- the anti-thrash memory only works if it records more
# than the first entry of a round.
#
# Env: GH_TOKEN, and AUTOPILOT_ALLOW_STATE which must be exactly "true"
# (absent = off, fail closed) -- the same flag the calling step's `if:` checks,
# doubled here so a mis-wired step cannot write state the stage forbids.
#
# Exit: 0 written, 1 refused or the write failed, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
PR="${ARG_PR:-}"
REPO="${ARG_REPO:-}"
COMMENT_ID="${ARG_COMMENT_ID:-}"
BODY="${ARG_BODY:-}"
VERDICT="${ARG_VERDICT:-}"

[[ -n "$PR" && -n "$REPO" && -n "${ARG_STATE:-}" && -n "${ARG_ROUND:-}" && -n "${ARG_HEAD:-}" && -n "${ARG_LAST_RUN:-}" ]] || {
    log_error "usage: update-state.sh --pr <n> --repo <owner/name> [--comment-id <id>] --body <file> --state <s> --round <r> --rounds-max <n> --head <sha> --last-run <run> [--ledger <line>] [--verdict <file>] [--campaign <c>] [--model <id>] [--last-sig <s>] [--sig-count <n>]"
    exit 2
}
if [[ "${AUTOPILOT_ALLOW_STATE:-}" != "true" ]]; then
    log_error "stage-flag-disabled: AUTOPILOT_ALLOW_STATE is not 'true'; refusing the state write (fail closed)"
    exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
: >"$work/ruled-out.txt"
: >"$work/decisions.txt"

if [[ -n "$VERDICT" && -s "$VERDICT" ]]; then
    # Newlines collapse to spaces: the carry-over parser in state-comment.sh
    # keeps only lines that begin with "- ", so a multi-line entry would lose
    # its own continuation on the next round.
    jq -r '(.ruled_out // [])[] | gsub("[\r\n]+"; " ")' "$VERDICT" >"$work/ruled-out.txt"
    jq -r '(.decisions // [])[] | gsub("[\r\n]+"; " ")' "$VERDICT" >"$work/decisions.txt"
fi

args=(render
    --body "${BODY:-/dev/null}"
    --state "$ARG_STATE"
    --round "$ARG_ROUND/${ARG_ROUNDS_MAX:-0}"
    --head "$ARG_HEAD"
    --last-run "$ARG_LAST_RUN"
    --ruled-out-file "$work/ruled-out.txt"
    --decisions-file "$work/decisions.txt")
[[ -n "${ARG_LEDGER:-}" ]] && args+=(--ledger "$ARG_LEDGER")
[[ -n "${ARG_CAMPAIGN:-}" ]] && args+=(--campaign "$ARG_CAMPAIGN")
[[ -n "${ARG_MODEL:-}" ]] && args+=(--model "$ARG_MODEL")
[[ -n "${ARG_ROUNDS_MAX:-}" ]] && args+=(--rounds-max "$ARG_ROUNDS_MAX")
[[ -n "${ARG_LAST_SIG:-}" ]] && args+=(--last-sig "$ARG_LAST_SIG")
[[ -n "${ARG_SIG_COUNT:-}" ]] && args+=(--sig-count "$ARG_SIG_COUNT")

"$SCRIPT_DIR/state-comment.sh" "${args[@]}" >"$work/body.md"

if [[ "${ARG_DRY_RUN:-false}" == "true" ]]; then
    cat "$work/body.md"
    log_info "dry-run: would write the state comment for PR #$PR (comment id '${COMMENT_ID:-none}')"
    exit 0
fi

endpoint="repos/$REPO/issues/$PR/comments"
method="POST"
if [[ -n "$COMMENT_ID" ]]; then
    endpoint="repos/$REPO/issues/comments/$COMMENT_ID"
    method="PATCH"
fi
# -F body=@file: the rendered body carries model-authored text and never
# becomes shell or an argv value that a length limit could truncate.
gh_retry "state-comment $method" -- api --method "$method" "$endpoint" -F body=@"$work/body.md" >/dev/null
log_info "state comment $method to $endpoint (round $ARG_ROUND/${ARG_ROUNDS_MAX:-0}, state $ARG_STATE)"

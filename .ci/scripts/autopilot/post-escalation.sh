#!/bin/bash
# Post one escalation comment on the PR and latch the loop with
# `autopilot-blocked`.
#
# EVERY WAY A CAMPAIGN CAN STOP ENDS HERE, and that is the point. Before this
# script existed, an autopilot round that escalated painted the job red and
# applied a label with no words attached, so the operator's first signal was
# "nothing is happening any more" and the model's reason -- the entire payload
# of an escalation -- stayed in a run log nobody was told to open. Three
# callers now share one comment shape:
#   - the model round's `escalate` verdict (reason and proposed patch from the
#     validated verdict; a .github/** fix arrives as DATA, never as a push);
#   - the generic round failure (validator, tripwire, wall-4 assert), named by
#     step class rather than left as "something went wrong";
#   - the gate's terminal no-gos (stuck-signature, round-cap), which otherwise
#     end a campaign in complete silence.
#
# Usage:
#   post-escalation.sh --pr <n> --repo <owner/name> --title <text> \
#     [--verdict <file>] [--reason <text>] [--steps <k=v,k=v>] \
#     [--run-url <url>] [--round <r>] [--no-label] [--dry-run]
#
#   --verdict  autopilot-push.sh --verdict-out; .escalation.reason becomes the
#              body and .escalation.patch is attached as a fenced diff.
#   --reason   literal reason text, for callers with no verdict.
#   --steps    step conclusions as `key=conclusion` pairs; the FIRST key whose
#              conclusion is `failure` names the failed class in the comment.
#              Keys are the fixed map below, so adding a stage means adding a
#              key here rather than inventing prose at the call site.
#   --dry-run  print the comment body on stdout and write nothing. This is
#              what makes the body TESTABLE offline -- the words an operator
#              reads at the moment a campaign stops are the whole product of
#              this script, and a body only ever exercised against the live
#              API is a body nobody has read.
#
# MODEL TEXT NEVER BECOMES SHELL. The reason and patch are extracted with jq
# into a file and the comment is posted with `-F body=@file`; nothing
# model-authored is ever interpolated into a command.
#
# Env: GH_TOKEN, AUTOPILOT_ALLOW_STATE (must be exactly "true", absent = off).
# Exit: 0 posted, 1 refused or the write failed, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
PR="${ARG_PR:-}"
REPO="${ARG_REPO:-}"
TITLE="${ARG_TITLE:-}"
VERDICT="${ARG_VERDICT:-}"
REASON="${ARG_REASON:-}"
STEPS="${ARG_STEPS:-}"
RUN_URL="${ARG_RUN_URL:-}"
ROUND="${ARG_ROUND:-}"
NO_LABEL="${ARG_NO_LABEL:-false}"
DRY_RUN="${ARG_DRY_RUN:-false}"

[[ -n "$PR" && -n "$REPO" && -n "$TITLE" ]] || {
    log_error "usage: post-escalation.sh --pr <n> --repo <owner/name> --title <text> [--verdict <file>] [--reason <text>] [--steps <k=v,...>] [--run-url <url>] [--round <r>] [--no-label]"
    exit 2
}
if [[ "${AUTOPILOT_ALLOW_STATE:-}" != "true" ]]; then
    log_error "stage-flag-disabled: AUTOPILOT_ALLOW_STATE is not 'true'; refusing to comment or label (fail closed)"
    exit 1
fi

# The step-class map. A key with no entry here is reported by its raw key, so a
# new stage is never silently unnameable.
step_class() {
    case "$1" in
        restore) echo "the trusted-config assert (wall 4): the PR branch's agent config did not match the trusted snapshot" ;;
        model) echo "the model step itself (turn cap, timeout, or a hard error)" ;;
        boundary) echo "the harness boundary: the handoff validator or the exfiltration tripwire refused the round" ;;
        escalation) echo "posting the escalation comment" ;;
        reply) echo "answering and resolving the review threads" ;;
        state) echo "the state-comment write" ;;
        submodules) echo "the submodule push path" ;;
        *) echo "$1" ;;
    esac
}

failed_class="an unclassified step (no step reported a failure conclusion)"
if [[ -n "$STEPS" ]]; then
    IFS=',' read -ra __pairs <<<"$STEPS"
    for pair in "${__pairs[@]}"; do
        pair="${pair//[[:space:]]/}"
        [[ -n "$pair" ]] || continue
        if [[ "${pair#*=}" == "failure" ]]; then
            failed_class="$(step_class "${pair%%=*}")"
            break
        fi
    done
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

{
    printf '### Autopilot escalation: %s\n\n' "$TITLE"
    [[ -n "$ROUND" ]] && printf 'Round %s. ' "$ROUND"
    printf 'The loop is latched; clear the `autopilot-blocked` label to resume.\n\n'
    if [[ -n "$VERDICT" && -s "$VERDICT" ]]; then
        jq -r '.escalation.reason // "The round escalated without recording a reason."' "$VERDICT"
        [[ -n "$STEPS" ]] && printf '\nFailed step class: %s\n' "$failed_class"
    elif [[ -n "$REASON" ]]; then
        printf '%s\n' "$REASON"
        [[ -n "$STEPS" ]] && printf '\nFailed step class: %s\n' "$failed_class"
    else
        # With no verdict and no reason the step class IS the whole message,
        # so printing it twice would be noise at the one moment the operator
        # is scanning for what actually broke.
        printf 'The round failed in %s.\n' "$failed_class"
    fi
    if [[ -n "$VERDICT" && -s "$VERDICT" ]] && [[ "$(jq -r '(.escalation.patch // "") | length' "$VERDICT")" != "0" ]]; then
        # ATTACHED AS DATA, never applied. A .github/** fix reaches a human
        # this way precisely because the harness must never push one
        # (03-v2-autonomy.md wall 2).
        printf '\n<details><summary>Proposed patch (data, not applied)</summary>\n\n```diff\n'
        jq -r '.escalation.patch' "$VERDICT"
        printf '\n```\n\n</details>\n'
    fi
    [[ -n "$RUN_URL" ]] && printf '\nRun log: %s\n' "$RUN_URL"
} >"$work/body.md"

if [[ "$DRY_RUN" == "true" ]]; then
    cat "$work/body.md"
    log_info "dry-run: would comment on PR #$PR and $([[ "$NO_LABEL" == "true" ]] && echo "leave the labels alone" || echo "apply autopilot-blocked")"
    exit 0
fi

gh_retry "escalation comment" -- api --method POST "repos/$REPO/issues/$PR/comments" -F body=@"$work/body.md" >/dev/null
log_info "escalation comment posted on PR #$PR"

if [[ "$NO_LABEL" != "true" ]]; then
    gh_retry "escalation label" -- api --method POST "repos/$REPO/issues/$PR/labels" -f 'labels[]=autopilot-blocked' >/dev/null
    log_info "autopilot-blocked applied to PR #$PR; the loop is latched until a human clears it"
fi

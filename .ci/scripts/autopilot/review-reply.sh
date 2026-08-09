#!/bin/bash
# Reply to and resolve the review threads a review-response round disposed of.
#
# THE MODEL HOLDS NO WRITE TOKEN, so it cannot reply to a thread or resolve
# one; it records dispositions as `decisions` entries shaped
# `thread <id>: <disposition>` and exits. This script is the deterministic
# other half, and it is split in two on purpose:
#
#   plan  --verdict <file> --threads <file> [--max-body <n>] [--out <file>]
#         PURE. Turns the VALIDATED verdict's decisions[] into a reply plan.
#         Every thread id must (a) match a tight id shape and (b) be present
#         in the payload the model was actually shown. Anything else lands in
#         skipped[] with a reason and raises flagged -- never silently.
#   apply --plan <file> [--repo <owner/name>]
#         The writes: addPullRequestReviewThreadReply then resolveReviewThread
#         per entry, gated on AUTOPILOT_ALLOW_PUSH (absent = off).
#
# WHY THE ID MUST BE IN THE FIXTURE, not merely well-shaped. The reply body is
# model-authored text and the thread id chooses WHERE it is posted. A global
# GraphQL node id names a thread on ANY pull request in any repo the token can
# reach, so validating the id's characters alone would let a round that read a
# hostile finding post that finding's suggested text onto an unrelated PR. The
# payload is the round's whole world; a thread outside it is not addressable.
#
# The mutations are the ones check-resolved-threads.sh advertises to humans in
# its own remediation output, so the automated and manual paths cannot drift.
#
# Exit: 0 planned/applied, 1 write refused or a mutation failed, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

cmd="${1:-}"
shift || true
parse_args "$@"

# GraphQL node ids are base64url-ish; this is the character set GitHub uses
# plus a hard length bound, so nothing shell-shaped or path-shaped can ride
# through into a mutation variable.
ID_SHAPE='^[A-Za-z0-9_=-]{1,128}$'

REPLY_MUTATION='
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment { id }
  }
}'

RESOLVE_MUTATION='
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}'

case "$cmd" in
    plan)
        VERDICT="${ARG_VERDICT:-}"
        THREADS="${ARG_THREADS:-}"
        MAX_BODY="${ARG_MAX_BODY:-2000}"
        OUT="${ARG_OUT:-}"
        [[ -n "$VERDICT" && -n "$THREADS" ]] || {
            log_error "usage: review-reply.sh plan --verdict <file> --threads <file> [--max-body <n>] [--out <file>]"
            exit 2
        }
        require_file "$VERDICT"
        require_file "$THREADS"
        [[ "$MAX_BODY" =~ ^[0-9]{1,6}$ ]] || {
            log_error "--max-body must be a number, got '$MAX_BODY'"
            exit 2
        }

        # --threads accepts review-payload.sh's object or a bare array of
        # threads; both name the same set, and requiring one spelling would
        # break the moment the payload gains a field.
        # id -> repo, so a planned reply carries the repository its thread
        # lives in. The GraphQL mutations address a thread by its global node
        # id and need no repo argument, but the plan is also an audit record
        # and a log line, and "resolved a thread" is not a useful sentence
        # without naming where.
        known="$(jq -c '[ ((.threads // .) // [])[] | .id ] | map(select(type == "string"))' "$THREADS")"
        known_repos="$(jq -c '[ ((.threads // .) // [])[] | select(.id | type == "string") | {key: .id, value: (.repo // "console")} ] | from_entries' "$THREADS")"

        plan="$(jq -c \
            --argjson known "$known" \
            --argjson repos "$known_repos" \
            --arg shape "$ID_SHAPE" \
            --argjson max "$MAX_BODY" '
            ($known | map({(.): true}) | add // {}) as $ids
            | [ (.decisions // [])[]
                | select(type == "string")
                # Only entries in the documented disposition shape are thread
                # traffic; an ordinary decisions entry is not a reply and is
                # not an error either.
                | select(test("^thread [^:]+: "))
                | (capture("^thread (?<id>[^:]+): (?<body>.*)$"; "s")) ]
            | map(
                if (.id | test($shape) | not)
                then {kind: "skipped", entry: .id, reason: "malformed-id"}
                elif ($ids[.id] | not)
                then {kind: "skipped", entry: .id, reason: "unknown-thread"}
                else {kind: "reply", thread_id: .id, body: (.body[0:$max]),
                      repo: ($repos[.id] // "console")}
                end)
            | {replies: [ .[] | select(.kind == "reply") | {thread_id, body, repo} ],
               skipped: [ .[] | select(.kind == "skipped") | {entry, reason} ]}
            | . + {flagged: ((.skipped | length) > 0)}
        ' "$VERDICT")"

        if [[ -n "$OUT" ]]; then
            printf '%s\n' "$plan" >"$OUT"
        else
            printf '%s\n' "$plan"
        fi

        if [[ "$(jq -r '.flagged' <<<"$plan")" == "true" ]]; then
            # LOUD, because this is the model naming a thread nobody showed
            # it: either the payload filter and the prompt disagree about what
            # the round could see, or the round invented an id.
            log_warn "review-reply plan: $(jq -r '.skipped | length' <<<"$plan") disposition(s) name no thread in this round's payload and were skipped:"
            jq -r '.skipped[] | "    - \(.reason): \(.entry)"' <<<"$plan" >&2
        fi
        log_info "review-reply plan: $(jq -r '.replies | length' <<<"$plan") reply/resolve pair(s) planned"
        ;;
    apply)
        PLAN="${ARG_PLAN:-}"
        [[ -n "$PLAN" ]] || {
            log_error "usage: review-reply.sh apply --plan <file>"
            exit 2
        }
        require_file "$PLAN"
        if [[ "${AUTOPILOT_ALLOW_PUSH:-}" != "true" ]]; then
            log_error "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing to reply or resolve (fail closed)"
            exit 1
        fi

        n="$(jq -r '.replies | length' "$PLAN")"
        if [[ "$n" == "0" ]]; then
            log_info "review-reply apply: nothing planned; no thread touched"
            exit 0
        fi
        # Indexed, not piped: a `while read` in a pipeline runs in a subshell,
        # where a failed mutation cannot fail this script.
        for ((i = 0; i < n; i++)); do
            tid="$(jq -r ".replies[$i].thread_id" "$PLAN")"
            body="$(jq -r ".replies[$i].body" "$PLAN")"
            trepo="$(jq -r ".replies[$i].repo // \"console\"" "$PLAN")"
            # Re-checked at the write, not only at the plan: apply is a
            # separate invocation and its input is a file on disk.
            [[ "$tid" =~ $ID_SHAPE ]] || {
                log_error "review-reply apply: thread id '$tid' does not match the id shape; refusing"
                exit 1
            }
            # Model text travels as a -f VALUE, never as shell: `-f k=v` puts
            # the bytes in one argv slot with no re-parse.
            gh_json "review reply for thread $tid in $trepo" -- api graphql \
                -f query="$REPLY_MUTATION" -f threadId="$tid" -f body="$body" >/dev/null
            gh_json "resolve thread $tid" -- api graphql \
                -f query="$RESOLVE_MUTATION" -f threadId="$tid" >/dev/null
            log_info "replied and resolved thread $tid in $trepo"
        done
        log_info "review-reply apply: $n thread(s) answered and resolved"
        ;;
    *)
        log_error "unknown subcommand '${cmd}' (plan|apply)"
        exit 2
        ;;
esac

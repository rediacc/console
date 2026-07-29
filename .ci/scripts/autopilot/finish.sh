#!/bin/bash
# Deterministic finish-line steps: everything past "CI is green" that needs
# no model invocation (03-v2-autonomy.md sections 2 and 9 - ready-flip,
# review-gate rerun and done-detection are all zero-model-cost paths).
#
# Subcommands:
#   check-done --pr <fixture.json>
#       Pure. Fixture: {ci_green, draft, reviewed, unresolved_threads}.
#       Prints {"done":bool,"missing":[...]}; exit 0 done, 1 not done.
#       The missing list names every unmet condition so a stalled babysit is
#       diagnosable from the decision line alone.
#   ready-flip --pr <number> --repo <owner/name>
#       Flip the draft PR ready. Uses the post-model app token in the
#       environment; an app-token flip fires ready_for_review, which chains
#       the review pipeline (verified as the S3 canary's purpose).
#   rerun-review --pr <number> --repo <owner/name>
#       Re-request the review gate by rerunning its failed run for the PR
#       head. Bounded by the review cap, which the review pipeline itself
#       enforces; this script never loops.
# Writes are gated on AUTOPILOT_ALLOW_PUSH (absent = off, fail closed).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

cmd="${1:-}"
shift || true
parse_args "$@"

require_write_flag() {
    if [[ "${AUTOPILOT_ALLOW_PUSH:-}" != "true" ]]; then
        log_error "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing the write (fail closed)"
        exit 1
    fi
}

case "$cmd" in
    check-done)
        PR="${ARG_PR:-}"
        [[ -n "$PR" ]] || {
            log_error "usage: finish.sh check-done --pr <fixture.json>"
            exit 2
        }
        require_file "$PR"
        verdict="$(jq -c '
            {
                ci_green: (.ci_green // false),
                # NOT `.draft // true | not`: jq treats false as empty for
                # `//`, which would read a non-draft PR as a draft. A missing
                # draft field still fails closed (not done).
                not_draft: (has("draft") and (.draft == false)),
                reviewed: (.reviewed // false),
                threads_resolved: ((.unresolved_threads // 1) == 0)
            }
            | {
                done: (.ci_green and .not_draft and .reviewed and .threads_resolved),
                missing: [to_entries[] | select(.value | not) | .key]
            }
        ' "$PR")"
        printf '%s\n' "$verdict"
        [[ "$(jq -r '.done' <<<"$verdict")" == "true" ]] || exit 1
        ;;
    ready-flip)
        PR="${ARG_PR:-}"
        REPO="${ARG_REPO:-}"
        [[ -n "$PR" && -n "$REPO" ]] || {
            log_error "usage: finish.sh ready-flip --pr <number> --repo <owner/name>"
            exit 2
        }
        require_write_flag
        gh_retry "ready-flip" -- pr ready "$PR" --repo "$REPO"
        log_info "PR #$PR flipped ready for review"
        ;;
    rerun-review)
        PR="${ARG_PR:-}"
        REPO="${ARG_REPO:-}"
        [[ -n "$PR" && -n "$REPO" ]] || {
            log_error "usage: finish.sh rerun-review --pr <number> --repo <owner/name>"
            exit 2
        }
        require_write_flag
        head_sha="$(gh_json "rerun-review head" -- api "repos/$REPO/pulls/$PR" --jq '{sha: .head.sha}' | jq -r '.sha')"
        run_id="$(gh_json "rerun-review run" -- api \
            "repos/$REPO/actions/runs?head_sha=$head_sha&event=pull_request" \
            --jq '{id: ([.workflow_runs[] | select(.name | test("[Rr]eview"))] | first | .id)}' | jq -r '.id')"
        if [[ -z "$run_id" || "$run_id" == "null" ]]; then
            log_error "rerun-review: no review-pipeline run found for head $head_sha"
            exit 1
        fi
        gh_retry "rerun-review rerun" -- run rerun "$run_id" --repo "$REPO" --failed
        log_info "review run $run_id rerun requested for PR #$PR"
        ;;
    *)
        log_error "unknown subcommand '${cmd}' (check-done|ready-flip|rerun-review)"
        exit 2
        ;;
esac

#!/bin/bash
# Fetch every review thread on a PR, with its comments, as one JSON array.
#
# This is the NETWORK half of the review payload (03-v2-autonomy.md section 6,
# residual 1: "review-response rounds receive a gate-built payload filtered by
# comment author before the model sees any text"). It runs in the GATE job,
# with github.token and read-only permissions, so the fetch itself holds no
# write capability. The FILTERING is review-payload.sh, which is pure and
# therefore testable offline; keeping the two apart is what makes the security
# decision (whose text reaches the model) reviewable without a network.
#
# The pagination is check-resolved-threads.sh's, deliberately: that script
# already paid for the lesson that `reviewThreads(first: 100)` with no cursor
# silently truncates, so thread 101 being unresolved read as "all resolved".
# The query differs from it in ONE way -- comments(first: 20) instead of
# first: 1 -- because the model needs the finding text, not just its author.
#
# LINKED SUBMODULE PRs ARE FETCHED TOO. check-submodule-branches.sh reds the
# console PR while a linked submodule PR still carries unresolved threads, but
# the round only ever saw console's own threads -- so it could answer every
# console finding, resolve every console thread, and stay red on a complaint
# living in another repository. With --body, the console PR body is scanned by
# linked-sub-prs.sh (which recognises only the four known submodules) and each
# linked PR's threads are fetched as well. Every thread is tagged with the repo
# and PR it came from, so everything downstream can route its reply back.
#
# Usage:
#   fetch-review-threads.sh --pr <number> --repo <owner/name> --out <file> \
#     [--body <console-pr-body-file>]
#
# Env: GH_TOKEN. Exit: 0 written, 1 fetch failure (fail closed: an empty file
# is never written on failure, because "no threads" and "could not ask" must
# not share an output).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
PR="${ARG_PR:-}"
REPO="${ARG_REPO:-}"
OUT="${ARG_OUT:-}"
BODY="${ARG_BODY:-}"

[[ -n "$PR" && -n "$REPO" && -n "$OUT" ]] || {
    log_error "usage: fetch-review-threads.sh --pr <number> --repo <owner/name> --out <file>"
    exit 2
}
[[ "$PR" =~ ^[0-9]+$ ]] || {
    log_error "--pr must be a number, got '$PR'"
    exit 2
}

QUERY='
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 20) {
            nodes {
              databaseId
              body
              author { login }
            }
          }
        }
      }
    }
  }
}'

ALL_NODES='[]'

# fetch_target <owner/name> <pr> - append that PR's threads to ALL_NODES, each
# tagged with the repo and PR it came from.
fetch_target() {
    local target="$1" number="$2"
    local OWNER="${target%%/*}" NAME="${target##*/}"
    local AFTER='' PAGE=0 PAGE_JSON
    while :; do
        PAGE=$((PAGE + 1))
        # 50 pages is 5000 threads; a real PR never approaches it, so reaching it
        # means the cursor stopped advancing. Fail closed rather than spin.
        if ((PAGE > 50)); then
            log_error "review-thread pagination did not terminate after $PAGE pages; failing closed"
            return 1
        fi
        if [[ -z "$AFTER" ]]; then
            set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$NAME" -F pr="$number"
        else
            set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$NAME" -F pr="$number" -f after="$AFTER"
        fi
        if ! PAGE_JSON="$(gh_json "review threads for PR ${target}#${number} (page ${PAGE})" -- api graphql "$@")"; then
            log_error "cannot fetch review threads for PR ${target}#${number}; failing closed"
            return 1
        fi
        # A GraphQL error response is valid JSON and exits 0, so it is caught per
        # page rather than only on the last one.
        if jq -e '.errors' >/dev/null 2>&1 <<<"$PAGE_JSON"; then
            log_error "GraphQL query failed: $(jq -r '.errors[0].message // "unknown error"' <<<"$PAGE_JSON")"
            return 1
        fi
        ALL_NODES="$(jq -n --argjson acc "$ALL_NODES" --argjson page "$PAGE_JSON" \
            --arg repo "$target" --argjson pr "$number" \
            '$acc + (($page.data.repository.pullRequest.reviewThreads.nodes // [])
                     | map(. + {repo: $repo, pr: $pr}))')"
        [[ "$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage' <<<"$PAGE_JSON")" == "true" ]] || break
        AFTER="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor' <<<"$PAGE_JSON")"
        if [[ -z "$AFTER" || "$AFTER" == "null" ]]; then
            log_error "hasNextPage was true but the cursor was empty; failing closed"
            return 1
        fi
    done
}

# Console's own threads are REQUIRED: without them the payload describes
# nothing and a review round would answer findings it never read.
fetch_target "$REPO" "$PR" || {
    log_error "cannot fetch review threads for the console PR; failing closed"
    exit 1
}

# The linked submodule PRs, when the caller supplied the console body.
#
# THESE ARE BEST-EFFORT, AND THE REASON IS STRUCTURAL. This script runs in the
# GATE, which by invariant holds no app token (the payload must exist before
# the model starts, and the app token is minted only after the model exits).
# `github.token` is scoped to console, so a private submodule's PR is simply
# not readable from here today: the fetch fails with a permission error rather
# than returning an empty set. Killing the whole round over that would take
# fix rounds down with it, so each linked target degrades on its own and says
# so loudly. A round that cannot see a submodule thread cannot answer it, and
# the Submodule Branches gate will stay red until a human does -- which is why
# this warns rather than passing quietly.
if [[ -n "$BODY" && -s "$BODY" ]]; then
    while read -r target number; do
        [[ -n "$target" ]] || continue
        log_info "also fetching review threads for the linked ${target}#${number}"
        if ! fetch_target "$target" "$number"; then
            echo "::warning::autopilot gate: could not read review threads for ${target}#${number} (the gate holds no cross-repo token); this round cannot answer them"
        fi
    done < <("$SCRIPT_DIR/linked-sub-prs.sh" --body "$BODY")
fi

printf '%s\n' "$ALL_NODES" >"$OUT"
log_info "fetched $(jq 'length' <<<"$ALL_NODES") review thread(s) across $(jq -r '[.[].repo] | unique | length' <<<"$ALL_NODES") pull request(s) -> $OUT"

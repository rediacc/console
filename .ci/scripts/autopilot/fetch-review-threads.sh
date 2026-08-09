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
# Usage:
#   fetch-review-threads.sh --pr <number> --repo <owner/name> --out <file>
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

[[ -n "$PR" && -n "$REPO" && -n "$OUT" ]] || {
    log_error "usage: fetch-review-threads.sh --pr <number> --repo <owner/name> --out <file>"
    exit 2
}
[[ "$PR" =~ ^[0-9]+$ ]] || {
    log_error "--pr must be a number, got '$PR'"
    exit 2
}

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

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
AFTER=''
PAGE=0
while :; do
    PAGE=$((PAGE + 1))
    # 50 pages is 5000 threads; a real PR never approaches it, so reaching it
    # means the cursor stopped advancing. Fail closed rather than spin.
    if ((PAGE > 50)); then
        log_error "review-thread pagination did not terminate after $PAGE pages; failing closed"
        exit 1
    fi
    if [[ -z "$AFTER" ]]; then
        set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$NAME" -F pr="$PR"
    else
        set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$NAME" -F pr="$PR" -f after="$AFTER"
    fi
    if ! PAGE_JSON="$(gh_json "review threads for PR #${PR} (page ${PAGE})" -- api graphql "$@")"; then
        log_error "cannot fetch review threads for PR #${PR}; failing closed"
        exit 1
    fi
    # A GraphQL error response is valid JSON and exits 0, so it is caught per
    # page rather than only on the last one.
    if jq -e '.errors' >/dev/null 2>&1 <<<"$PAGE_JSON"; then
        log_error "GraphQL query failed: $(jq -r '.errors[0].message // "unknown error"' <<<"$PAGE_JSON")"
        exit 1
    fi
    ALL_NODES="$(jq -n --argjson acc "$ALL_NODES" --argjson page "$PAGE_JSON" \
        '$acc + ($page.data.repository.pullRequest.reviewThreads.nodes // [])')"
    [[ "$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage' <<<"$PAGE_JSON")" == "true" ]] || break
    AFTER="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor' <<<"$PAGE_JSON")"
    if [[ -z "$AFTER" || "$AFTER" == "null" ]]; then
        log_error "hasNextPage was true but the cursor was empty; failing closed"
        exit 1
    fi
done

printf '%s\n' "$ALL_NODES" >"$OUT"
log_info "fetched $(jq 'length' <<<"$ALL_NODES") review thread(s) for PR #${PR} across $PAGE page(s) -> $OUT"

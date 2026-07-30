#!/bin/bash
# Check that all review threads are resolved using GitHub GraphQL API
#
# This is separate from "unreplied comments" - a thread can have replies but
# still be unresolved. This script ensures all threads are properly resolved.
#
# Also checks if any reviewer has requested changes.
#
# Usage:
#   .ci/scripts/quality/check-resolved-threads.sh
#
# Environment variables:
#   GH_TOKEN           - GitHub token for API access (must have repo scope)
#   PR_NUMBER          - Pull request number
#   GITHUB_REPOSITORY  - Repository in owner/repo format

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Validate environment
require_var PR_NUMBER
require_var GH_TOKEN
require_var GITHUB_REPOSITORY

# Parse owner/repo
OWNER="${GITHUB_REPOSITORY%%/*}"
REPO="${GITHUB_REPOSITORY##*/}"

log_step "Checking review threads and review status..."

# GraphQL query to get all review threads
QUERY='
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 1) {
            nodes {
              body
              author {
                login
              }
            }
          }
        }
      }
    }
  }
}'

log_step "Fetching review threads via GraphQL..."

# Execute the GraphQL query. `gh api graphql` can exit 0 while returning a
# truncated or malformed body (an upstream hiccup), so a command-exit-code check
# alone misses it -- gh_json validates that the body is PARSEABLE JSON on each of
# its three attempts, which is what the hand-rolled loop that used to live here
# did. It moved to lib/common.sh because eight other call sites across the review
# and attribution gates needed exactly this and had none of it.
# PAGINATE. `reviewThreads(first: 100)` with no cursor silently truncates at 100,
# and because the gate only ever reports UNRESOLVED threads, thread 101 being
# unresolved read as "all threads resolved" -- a silent green on a merge-blocking
# check, which is the same failure class as the `|| echo "[]"` bug fixed below.
# $after is a nullable GraphQL variable, so omitting it on the first request is
# how you ask for page one; there is no valid empty-string cursor.
ALL_NODES='[]'
AFTER=''
PAGE=0
while :; do
    PAGE=$((PAGE + 1))
    # 50 pages is 5000 threads. A real PR never approaches it, so hitting this
    # means the cursor stopped advancing; fail closed rather than spin forever.
    if [[ "$PAGE" -gt 50 ]]; then
        log_error "Review-thread pagination did not terminate after $PAGE pages. Failing closed."
        exit 1
    fi
    if [[ -z "$AFTER" ]]; then
        set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER"
    else
        set -- -f query="$QUERY" -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER" -f after="$AFTER"
    fi
    if ! PAGE_JSON=$(gh_json "review threads for PR #${PR_NUMBER} (page ${PAGE})" -- api graphql "$@"); then
        log_error "Cannot determine whether review threads are resolved. Failing closed."
        exit 1
    fi
    # A GraphQL error response is valid JSON and exits 0, so catch it per page
    # rather than only on the last one.
    if echo "$PAGE_JSON" | jq -e '.errors' >/dev/null 2>&1; then
        ERROR_MSG=$(echo "$PAGE_JSON" | jq -r '.errors[0].message // "Unknown error"')
        log_error "GraphQL query failed: $ERROR_MSG"
        exit 1
    fi
    ALL_NODES=$(jq -n --argjson acc "$ALL_NODES" --argjson page "$PAGE_JSON" \
        '$acc + ($page.data.repository.pullRequest.reviewThreads.nodes // [])')
    if [[ "$(echo "$PAGE_JSON" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')" != "true" ]]; then
        break
    fi
    AFTER=$(echo "$PAGE_JSON" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
    if [[ -z "$AFTER" || "$AFTER" == "null" ]]; then
        log_error "hasNextPage was true but the cursor was empty. Failing closed."
        exit 1
    fi
done
[[ "$PAGE" -gt 1 ]] && log_step "Fetched $(echo "$ALL_NODES" | jq 'length') review threads across $PAGE pages"
# Re-wrap into the original single-response shape so every consumer below is
# unchanged.
RESULT=$(jq -n --argjson n "$ALL_NODES" \
    '{data: {repository: {pullRequest: {reviewThreads: {nodes: $n}}}}}')

# Extract unresolved threads (excluding outdated ones)
UNRESOLVED=$(echo "$RESULT" | jq '[
    .data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false and .isOutdated == false)
]')

UNRESOLVED_COUNT=$(echo "$UNRESOLVED" | jq 'length')

# Check for "Changes Requested" reviews
log_step "Checking review status..."

# FAIL CLOSED. `|| echo "[]"` here meant a gh failure produced an empty review
# list, so CHANGES_REQUESTED came out 0 and the gate reported that nobody had
# requested changes. That is a silent green on a merge-blocking check.
if ! REVIEWS=$(gh_json "review status for PR #${PR_NUMBER}" -- \
    api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews"); then
    log_error "Cannot determine whether a reviewer requested changes. Failing closed."
    exit 1
fi

# Get the latest review state per reviewer (reviewers can change their review)
CHANGES_REQUESTED=$(echo "$REVIEWS" | jq '[
    group_by(.user.login)
    | .[]
    | sort_by(.submitted_at)
    | last
    | select(.state == "CHANGES_REQUESTED")
] | length')

# Output results
HAS_ISSUES=false

if [[ "$CHANGES_REQUESTED" -gt 0 ]]; then
    HAS_ISSUES=true
    echo ""
    echo "============================================================"
    echo "  Changes Requested by Reviewer"
    echo "============================================================"
    echo ""
    echo "One or more reviewers have requested changes."
    echo ""
    echo "Reviewers who requested changes:"
    echo "$REVIEWS" | jq -r '
        group_by(.user.login)
        | .[]
        | sort_by(.submitted_at)
        | last
        | select(.state == "CHANGES_REQUESTED")
        | "  - @\(.user.login)"'
    echo ""
    echo "Please address the reviewer feedback and request a new review."
    echo "------------------------------------------------------------"
fi

if [[ "$UNRESOLVED_COUNT" -gt 0 ]]; then
    HAS_ISSUES=true
    echo ""
    echo "============================================================"
    echo "  Unresolved Review Threads"
    echo "============================================================"
    echo ""
    echo "Found $UNRESOLVED_COUNT unresolved review thread(s):"
    echo ""

    # List each unresolved thread
    echo "$UNRESOLVED" | jq -r '.[] |
        "  \(.path):\(.line // "N/A")"
        + "\n    Author: @\(.comments.nodes[0].author.login // "unknown")"
        + "\n    Comment: \(.comments.nodes[0].body | split("\n")[0] | .[0:80])..."
        + "\n"'

    echo "------------------------------------------------------------"
    echo "Please resolve all review threads before merging."
    echo ""
    echo "Option 1: Via GitHub UI"
    echo "  1. Go to the PR: https://github.com/${GITHUB_REPOSITORY}/pull/${PR_NUMBER}"
    echo "  2. Click 'Resolve conversation' on each thread"
    echo ""
    echo "Option 2: Via CLI (resolve all threads at once)"
    echo ""
    echo "  # Get unresolved thread IDs"
    echo "  cat > /tmp/query.graphql << 'GRAPHQL'"
    echo "  query(\$owner: String!, \$repo: String!, \$pr: Int!) {"
    echo "    repository(owner: \$owner, name: \$repo) {"
    echo "      pullRequest(number: \$pr) {"
    echo "        reviewThreads(first: 100) {"
    echo "          nodes { id isResolved }"
    echo "        }"
    echo "      }"
    echo "    }"
    echo "  }"
    echo "  GRAPHQL"
    echo ""
    echo "  cat > /tmp/resolve.graphql << 'GRAPHQL'"
    echo "  mutation(\$threadId: ID!) {"
    echo "    resolveReviewThread(input: {threadId: \$threadId}) {"
    echo "      thread { id isResolved }"
    echo "    }"
    echo "  }"
    echo "  GRAPHQL"
    echo ""
    echo "  # Resolve all unresolved threads"
    echo "  for id in \$(gh api graphql -F owner=\"${OWNER}\" -F repo=\"${REPO}\" -F pr=${PR_NUMBER} \\"
    echo "      -f query=\"\$(cat /tmp/query.graphql)\" \\"
    echo "      --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | .id'); do"
    echo "    gh api graphql -F threadId=\"\$id\" -f query=\"\$(cat /tmp/resolve.graphql)\" --silent"
    echo "  done"
    echo ""
    echo "------------------------------------------------------------"
fi

if [[ "$HAS_ISSUES" == "true" ]]; then
    exit 1
fi

# All good
TOTAL_THREADS=$(echo "$RESULT" | jq '.data.repository.pullRequest.reviewThreads.nodes | length')
RESOLVED_COUNT=$((TOTAL_THREADS - UNRESOLVED_COUNT))

echo ""
log_info "Review status: OK"
if [[ "$TOTAL_THREADS" -gt 0 ]]; then
    log_info "All $RESOLVED_COUNT review thread(s) are resolved"
else
    log_info "No review threads to resolve"
fi
log_info "No pending 'Changes Requested' reviews"
exit 0

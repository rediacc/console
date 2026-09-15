#!/bin/bash
# Check for Claude attribution in commits and PR description
#
# This script ensures commits don't contain Claude co-author attribution
# or AI-generated markers that should not be in production code.
#
# Usage:
#   GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-claude-attribution.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: gh_retry is needed so a failed API call cannot be mistaken for a PR that carries no attribution
source "$SCRIPT_DIR/../lib/common.sh"

# NEW SINCE THE 3N REWRITE: the commit loops now read fields out of the compare
# payload with jq instead of asking the API for each one, so jq is executed
# directly here and must be declared. Under `set -euo pipefail` a missing binary
# inside a command substitution exits 127 with no message at all.
require_cmd jq

# Validate required environment variables
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "GITHUB_TOKEN is required"
    exit 1
fi

if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping Claude attribution check (not a pull request)"
    exit 0
fi

REPO="${GITHUB_REPOSITORY:-rediacc/console}"
ISSUES=()

echo "Checking for Claude attribution in PR #${PR_NUMBER}..."

# Pattern to match Claude attribution (case-insensitive)
# Matches: Co-Authored-By: Claude, Generated with Claude, etc.
# Note: We specifically match attribution markers, not general mentions of Claude as a tool
CLAUDE_PATTERN="(Co-Authored-By[[:space:]]*:[[:space:]]*Claude|Generated with[[:space:]]+\[?Claude|🤖[[:space:]]*Generated|noreply@anthropic\.com)"

# FAIL CLOSED throughout. Every one of these five calls used to end in
# `|| echo ""`, so a rate limit or an expired token produced an empty PR body
# and an empty commit list: the `for SHA in $COMMITS` loops ran zero times,
# ISSUES stayed empty, and the gate printed "No Claude attribution found - OK"
# and exited 0 having inspected nothing. An unreadable PR is not a clean PR.
probe_failed() {
    echo "" >&2
    echo "Cannot certify that this PR is free of Claude attribution, because the" >&2
    echo "GitHub API could not be read. Failing closed rather than reporting clean." >&2
    exit 1
}

# Check PR description
echo "  Checking PR description..."
PR_BODY=$(gh_retry "PR body for #${PR_NUMBER}" -- \
    api "repos/${REPO}/pulls/${PR_NUMBER}" --jq '.body // ""') || probe_failed

if grep -qiE "$CLAUDE_PATTERN" <<<"$PR_BODY"; then
    MATCH=$(echo "$PR_BODY" | grep -iE "$CLAUDE_PATTERN" | head -1 || true)
    ISSUES+=("PR description contains: \"${MATCH}\"")
fi

# Check commit messages
echo "  Checking commit messages..."
# NOT `pulls/{n}/commits`: that endpoint caps at 250 EVEN WITH --paginate, and it
# caps SILENTLY -- no error, no marker, just a short list. Measured 2026-09-15 on
# rediacc/console#589, a 254-commit PR: this gate read 250 and reported
# "No Claude attribution found - OK" over the four NEWEST commits, which it had
# never seen. That is the exact shape this gate was repaired for in the first
# place (see the header): inspect nothing, print a checkmark.
#
# The compare endpoint paginates properly, and the PR's own `.commits` count is an
# INDEPENDENT number to check the read against -- so a short read now refuses
# instead of passing, at any size rather than at one magic threshold.
PR_META=$(gh_retry "PR metadata for #${PR_NUMBER}" -- \
    api "repos/${REPO}/pulls/${PR_NUMBER}" \
    --jq '"\(.base.sha) \(.head.sha) \(.commits)"') || probe_failed
read -r BASE_SHA HEAD_SHA TOTAL_COMMITS <<<"$PR_META"
if [[ -z "$BASE_SHA" || -z "$HEAD_SHA" || ! "$TOTAL_COMMITS" =~ ^[0-9]+$ ]]; then
    echo "  ERROR: could not read base/head/commit-count for PR #${PR_NUMBER}: '${PR_META}'." >&2
    probe_failed
fi

# ONE READ, NOT 3N. The compare payload already carries the message and the
# author name and address, so the `repos/{r}/commits/{sha}` calls this loop used
# to make were re-fetching data already in hand: THREE per commit, 762 of them on
# a 254-commit PR, ~3.5 minutes of a 12-minute job. Every one of them was also a
# chance for a rate limit to refuse a PR that is fine.
PAYLOAD=$(gh_retry "commit list for PR #${PR_NUMBER}" -- \
    api "repos/${REPO}/compare/${BASE_SHA}...${HEAD_SHA}?per_page=100" --paginate \
    --jq '.commits[] | {sha: .sha, message: .commit.message, name: .commit.author.name, email: .commit.author.email}') || probe_failed

# A PR always has at least one commit. An empty list here means the call
# succeeded but returned nothing usable, which is not a PR this gate can clear.
#
# `grep -q` AND NOT `[[ -z "${PAYLOAD//[[:space:]]/}" ]]`, WHICH IS QUADRATIC.
# The old test ran on a list of SHAs (~10 KB) and was instant; this payload
# carries every commit MESSAGE (~420 KB on #589) and bash's pattern substitution
# over it took 254 SECONDS, measured -- more than the entire gate had cost
# before. The whole point of this rewrite was to stop wasting the job's budget,
# and the first version of it spent four minutes deciding whether a string was
# blank.
if ! grep -q '[^[:space:]]' <<<"$PAYLOAD"; then
    echo "  ERROR: the commit list for PR #${PR_NUMBER} came back empty." >&2
    echo "  Every PR has at least one commit, so this is a failed read, not a clean PR." >&2
    probe_failed
fi

READ_COMMITS=$(grep -c . <<<"$PAYLOAD")
if [[ "$READ_COMMITS" -ne "$TOTAL_COMMITS" ]]; then
    echo "  ERROR: read ${READ_COMMITS} commit(s) for PR #${PR_NUMBER}, but the PR reports ${TOTAL_COMMITS}." >&2
    echo "  An incomplete set cannot be cleared; refusing rather than judging part of it." >&2
    probe_failed
fi

# TWO PASSES, NOT ONE, and the order is load-bearing: every message finding is
# reported before every author finding, which is the order the old two-loop shape
# produced and which the expected-output fixtures encode.
while IFS= read -r ROW; do
    [[ -z "$ROW" ]] && continue
    # A MALFORMED ROW IS DROPPED, NOT FATAL. Under `set -e` a bare
    # `SHA=$(jq ...)` would kill the whole gate on one bad line, turning a
    # corrupt byte into "the gate is flaky"; the port drops the line for the
    # same reason, so both under-report identically instead of one crashing.
    SHA=$(jq -r '.sha // empty' <<<"$ROW" 2>/dev/null) || continue
    [[ -z "$SHA" ]] && continue
    # `jq -r .message` and not @tsv: a commit message is MULTI-LINE, and @tsv
    # would fold it to a literal `\n`, which changes both whether grep matches
    # and which line `head -1` prints.
    COMMIT_MSG=$(jq -r '.message // ""' <<<"$ROW")

    if grep -qiE "$CLAUDE_PATTERN" <<<"$COMMIT_MSG"; then
        SHORT_SHA="${SHA:0:7}"
        MATCH=$(echo "$COMMIT_MSG" | grep -iE "$CLAUDE_PATTERN" | head -1 || true)
        ISSUES+=("Commit ${SHORT_SHA} contains: \"${MATCH}\"")
    fi
done <<<"$PAYLOAD"

# Check commit authors
echo "  Checking commit authors..."
while IFS= read -r ROW; do
    [[ -z "$ROW" ]] && continue
    SHA=$(jq -r '.sha // empty' <<<"$ROW" 2>/dev/null) || continue
    [[ -z "$SHA" ]] && continue
    AUTHOR_NAME=$(jq -r '.name // ""' <<<"$ROW")
    AUTHOR_EMAIL=$(jq -r '.email // ""' <<<"$ROW")

    if grep -qiE "(claude|anthropic)" <<<"$AUTHOR_NAME $AUTHOR_EMAIL"; then
        SHORT_SHA="${SHA:0:7}"
        ISSUES+=("Commit ${SHORT_SHA} authored by: ${AUTHOR_NAME} <${AUTHOR_EMAIL}>")
    fi
done <<<"$PAYLOAD"

if [[ ${#ISSUES[@]} -eq 0 ]]; then
    echo "No Claude attribution found - OK"
    exit 0
fi

# Found issues
echo ""
echo "============================================================"
echo "  Claude Attribution Detected"
echo "============================================================"
echo ""
echo "Found ${#ISSUES[@]} instance(s) of Claude attribution:"
echo ""
for issue in "${ISSUES[@]}"; do
    echo "  - ${issue}"
done
echo ""
echo "------------------------------------------------------------"
echo "Please remove Claude attribution before merging."
echo ""
echo "To fix commit messages, use interactive rebase:"
echo ""
echo "  git rebase -i HEAD~N  # where N is number of commits"
echo "  # Change 'pick' to 'reword' for commits to edit"
echo "  # Remove Co-Authored-By lines and save"
echo "  git push --force"
echo ""
echo "To fix PR description:"
echo ""
echo "  gh pr edit ${PR_NUMBER} --body \"\$(gh pr view ${PR_NUMBER} --json body -q .body | sed '/Claude/d')\""
echo ""
echo "Or edit directly on GitHub:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}"
echo "------------------------------------------------------------"
exit 1

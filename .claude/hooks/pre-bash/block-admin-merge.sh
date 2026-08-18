#!/usr/bin/env bash
# Merge discipline for `gh pr merge`:
#   1. --admin is banned OUTRIGHT (no green-escape, operator ruling 2026-07-22).
#      The old flow admin-merged over a still-pending pointer-bump CI run and
#      left every merged PR permanently red; the pointer-bump fast path makes
#      the wait minutes, so --admin has no remaining legitimate use here.
#   2. --auto defers only the CI-green requirement (GitHub enforces that at
#      merge time). Review hygiene is NOT a required check, so --auto still
#      proves it NOW like an immediate merge does.
#   3. Review hygiene = zero unresolved review threads AND a substantive
#      reply to the newest finished review REPORT (issue-comment channel,
#      check-review-report-replies.sh). Required checks are per-commit: a
#      report posted after CI went green can never turn the check red, so
#      merge time is the only enforcement point, and ci.yml's review-gate only
#      re-evaluates on the next push.
#   4. An immediate merge (no --auto) must additionally prove CI green NOW.
#      Console gets all checks; other rediacc repos get the hygiene checks
#      (their thread state feeds console's Submodule Branches gate).
#      Network paths are NOT covered by test-hooks.sh; verification
#      failures fail CLOSED.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
# Bypass-resistant command scanning (unwraps sh -c/eval payloads, strips
# heredocs+prose, matches --flag=value forms). A commit message MENTIONING
# "gh pr merge --admin" must not trip the ban, but `sh -c 'gh pr merge
# --admin'` and `--admin=true` MUST. See lib/command-scan.sh.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
hook_gh_pr_at_command_pos "$SCAN" merge || exit 0

# SCAN is the only parsed view: it already carries the prose-stripped command
# plus any unwrapped shell-wrapper payload. A second, separately-built stripped
# view used to exist for field parsing; keeping two views in sync is the drift
# hazard lib/command-scan.sh already records, so fields are read from SCAN.

# --admin ban: match the flag in ANY form on the raw command (=value,
# assignment, inside a wrapper payload). Over-blocking is the safe direction.
if hook_flag_present "$CMD" admin; then
    echo "❌ BLOCKED: 'gh pr merge --admin' is banned. It bypasses the required CI Complete check and is how merged PRs ended up permanently red (pointer-bump commits merged mid-run). The sanctioned path: wait for the fast-path CI run to go green (minutes for pointer-only pushes), then 'gh pr ready' and 'gh pr merge --squash --auto'. If GitHub refuses a plain merge, the PR is not actually green -- fix that instead." >&2
    exit 2
fi

# CLAUDE_PROJECT_DIR is unset outside hook invocation (e.g. the harness);
# fall back to the git toplevel so the script path stays absolute.
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

# Every field (repo, selector, --auto) is read from the SEGMENT that carries
# this `gh pr merge`, and EACH merge on the line is checked on its own. Parsing
# line-wide cross-attributed fields between sibling invocations -- observed
# live: `gh pr view 94 --repo rediacc/renet; gh pr merge 66 --repo
# rediacc/account` resolved as rediacc/renet#66, an unrelated long-merged PR,
# and blocked the merge on THAT PR's threads. It also examined only one of
# several merges on a line. See hook_gh_pr_segment.
while IFS= read -r SEG; do
    [[ -z "$SEG" ]] && continue
    REPO=$(hook_target_repo "$SEG" "$SCAN" "$CWD")
    case "$REPO" in rediacc/*) ;; *) continue ;; esac

    AUTO=0
    hook_flag_present "$SEG" auto && AUTO=1

    SEL=$(hook_pr_selector "$SEG" merge)
    PRDATA=$(timeout 20 gh pr view ${SEL:+"$SEL"} --repo "$REPO" --json number,statusCheckRollup 2>/dev/null)
    NUM=$(printf '%s' "$PRDATA" | jq -r '.number // empty' 2>/dev/null)
    if [[ -z "$NUM" ]]; then
        echo "❌ BLOCKED: could not resolve the PR for 'gh pr merge' (repo $REPO, selector '${SEL:-<current branch>}'). Cannot verify green + resolved threads, so the merge is not allowed. Name the PR explicitly or re-run after checking 'gh pr view'." >&2
        exit 2
    fi

    if [[ "$AUTO" == "0" && "$REPO" == "rediacc/console" ]]; then
        CONCLUSION=$(printf '%s' "$PRDATA" | jq -r '[.statusCheckRollup[] | select(.name == "CI Complete")] | first | .conclusion // "ABSENT"' 2>/dev/null)
        if [[ "$CONCLUSION" != "SUCCESS" ]]; then
            echo "❌ BLOCKED: immediate merge of console PR #$NUM requires CI Complete = SUCCESS on the current head (got: ${CONCLUSION:-verification failed}). Use 'gh pr merge --squash --auto' to let GitHub merge at green, or wait for the run." >&2
            exit 2
        fi
    fi

    # Report-reply hygiene (both --auto and immediate): the newest finished
    # review report must have a substantive id-referencing reply. Reuses the CI
    # gate script verbatim; fails CLOSED on script/network failure.
    if ! OUT=$(timeout 30 env GH_TOKEN="$(gh auth token)" \
        PR_NUMBER="$NUM" GITHUB_REPOSITORY="$REPO" \
        bash "$ROOT/.ci/scripts/quality/check-review-report-replies.sh" 2>&1); then
        echo "❌ BLOCKED: $REPO#$NUM has an unaddressed review REPORT (or the check could not run). Required checks are per-commit, so a report posted after CI went green can only be enforced here. Details:" >&2
        printf '%s\n' "$OUT" | tail -15 >&2
        exit 2
    fi

    OWNER=${REPO%%/*}
    NAME=${REPO##*/}
    UNRESOLVED=$(timeout 20 gh api graphql \
        -f query='query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { pullRequest(number: $n) { reviewThreads(first: 100) { nodes { isResolved } } } } }' \
        -f o="$OWNER" -f r="$NAME" -F n="$NUM" \
        --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)] | length' 2>/dev/null)
    if [[ -z "$UNRESOLVED" || "$UNRESOLVED" != "0" ]]; then
        echo "❌ BLOCKED: $REPO#$NUM has ${UNRESOLVED:-unverifiable} unresolved review thread(s). Reply substantively and resolve them (GraphQL resolveReviewThread) before merging -- review threads are the blocking channel of the Claude review flow." >&2
        exit 2
    fi
done <<<"$(hook_gh_pr_segment "$SCAN" merge)"
exit 0

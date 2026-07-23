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
#      merge time is the only enforcement point — ci.yml's review-gate only
#      re-evaluates on the next push.
#   4. An immediate merge (no --auto) must additionally prove CI green NOW.
#      Console gets all checks; other rediacc repos get the hygiene checks
#      (their thread state feeds console's Submodule Branches gate).
#      Network paths are NOT covered by test-hooks.sh; verification
#      failures fail CLOSED.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
# Quote-strip + command-position anchor; rationale in block-premature-ready.sh.
# Especially load-bearing here: a commit message MENTIONING "gh pr merge
# --admin" must not trip the unconditional --admin ban.
STRIPPED=$(printf '%s' "$CMD" | tr '\n' '\001' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr '\001' '\n')
echo "$STRIPPED" | grep -qE '(^|[;&|]|\$\()[[:space:]]*gh pr merge' || exit 0

if echo "$STRIPPED" | grep -qE -- '--admin([[:space:]]|$)'; then
    echo "❌ BLOCKED: 'gh pr merge --admin' is banned. It bypasses the required CI Complete check and is how merged PRs ended up permanently red (pointer-bump commits merged mid-run). The sanctioned path: wait for the fast-path CI run to go green (minutes for pointer-only pushes), then 'gh pr ready' and 'gh pr merge --squash --auto'. If GitHub refuses a plain merge, the PR is not actually green -- fix that instead." >&2
    exit 2
fi

AUTO=0
echo "$STRIPPED" | grep -qE -- '--auto([[:space:]]|$)' && AUTO=1

REPO=$(printf '%s\n' "$STRIPPED" | grep -oE -- '(--repo[= ]|-R )[A-Za-z0-9_./-]+' | head -1 | sed -E 's/^(--repo[= ]|-R )//')
[[ -z "$REPO" ]] && REPO="rediacc/console"
case "$REPO" in rediacc/*) ;; *) exit 0 ;; esac

SEL=$(printf '%s\n' "$STRIPPED" | sed -n 's/.*gh pr merge[[:space:]]*//p' | awk '{for (i=1; i<=NF; i++) if ($i !~ /^-/) { print $i; exit }}')
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
# CLAUDE_PROJECT_DIR is unset outside hook invocation (e.g. the harness);
# fall back to the git toplevel so the script path stays absolute.
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
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
exit 0

#!/usr/bin/env bash
# PostToolUse advisory: after a git push, force-cancel older in-progress CI runs on this branch.
# Always exits 0 (advisory only). Uses $CLAUDE_PROJECT_DIR so it reads the CURRENT worktree's
# branch (the previous hardcoded path pointed at the main worktree and misread the branch).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if ! echo "$CMD" | grep -qE 'git push'; then exit 0; fi
# BRANCHES TO CONSIDER = the checked-out branch PLUS every branch this push
# actually targeted. Using only the checked-out branch made this hook a NO-OP for
# any wave that pushes with an explicit refspec.
#
# Observed 2026-07-29: the working branch was 0728-3 while PR #543's CI runs on
# 0728-2, because each push was `git push origin 0728-3` followed by
# `git push origin HEAD:0728-2`. The hook queried 0728-3, which has ZERO runs,
# found nothing to cancel, and exited 0 looking healthy. Meanwhile round 13 kept
# running and round 14 queued behind it -- a duplicate full round of machine time
# on every push of the wave.
#
# So parse the refspec out of the command: `HEAD:0728-2` and `0728-3` both name a
# destination branch, and a bare `git push` targets the current one.
BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)
if [[ -z "$BRANCH" || "$BRANCH" == "main" ]]; then exit 0; fi

BRANCHES="$BRANCH"
# Everything after `git push [flags] [remote]`; take the DESTINATION side of any
# `src:dst` refspec, and any bare ref that is not a flag or the remote name.
for tok in $(echo "$CMD" | sed -n 's/.*git push//p' | tr ' ' '\n'); do
    case "$tok" in
        -* | origin | gitlab | "") continue ;;
        *:*) BRANCHES="$BRANCHES ${tok##*:}" ;;
        *) BRANCHES="$BRANCHES $tok" ;;
    esac
done
BRANCHES=$(echo "$BRANCHES" | tr ' ' '\n' | grep -v '^$' | grep -v '^main$' | sort -u | tr '\n' ' ')
# Cancel only runs that are GENUINELY superseded, i.e. built from a sha that is no
# longer the tip of origin/$BRANCH.
#
# This hook fires on ANY command containing `git push`, including a push to a SUBMODULE
# (private/renet, private/account). Those pushes do not advance the console branch, so the
# in-flight console run is still the one we want, yet the old logic cancelled it anyway,
# because it matched every queued/in_progress run regardless of sha. The documented workflow
# is "submodules first, then console", so this hook was force-cancelling a live console run
# on essentially every cycle: rounds 10 and 12 of the P4 wave died exactly this way, each
# showing the misleading "cancelled + zero failed jobs" signature.
#
# Comparing against the freshly-fetched tip makes the rule honest: a run whose headSha IS the
# tip is current (do not touch it); a run whose headSha is not is superseded (cancel it).
COUNT=0
for BRANCH in $BRANCHES; do
    git -C "${CLAUDE_PROJECT_DIR:-.}" fetch origin "$BRANCH" --quiet 2>/dev/null || true
    TIP=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse "origin/$BRANCH" 2>/dev/null)
    if [[ -z "$TIP" ]]; then continue; fi
    # NOTE: `gh ... --jq` does NOT accept jq's `--arg`, so the tip is interpolated into the
    # filter. $TIP is a hex sha from rev-parse, so there is nothing to quote-escape.
    RUNS=$(gh run list --repo rediacc/console --branch "$BRANCH" --json databaseId,status,headSha \
        --jq ".[] | select(.status == \"in_progress\" or .status == \"queued\") | select(.headSha != \"$TIP\") | .databaseId" 2>/dev/null)
    if [[ -z "$RUNS" ]]; then continue; fi
    for rid in $RUNS; do
        gh api repos/rediacc/console/actions/runs/$rid/force-cancel -X POST 2>/dev/null && COUNT=$((COUNT + 1))
    done
done
if [[ $COUNT -gt 0 ]]; then
    echo "⚡ Auto-cancelled $COUNT old CI run(s) across: $BRANCHES. The new push triggers a fresh CI run. Watch it with: gh run watch <new-run-id> --repo rediacc/console --exit-status --interval 100 (run_in_background: true). Remember: watch the Console CI run, not the Watchdog Monitor chain runs; auto-retries land as attempt 2 of the same Console CI run."
fi
echo "📝 If a PR is open for any of: $BRANCHES, refresh its description NOW (gh pr edit <N> --body-file ...). The PR-Description gate fails when the body is older than the newest commit. Stale-only failure? Refresh + 'gh run rerun <id> --failed' (no commit needed)."
exit 0

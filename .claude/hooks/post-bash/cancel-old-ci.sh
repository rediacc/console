#!/usr/bin/env bash
# PostToolUse advisory: after a git push, force-cancel older in-progress CI runs on this branch.
# Always exits 0 (advisory only). Uses $CLAUDE_PROJECT_DIR so it reads the CURRENT worktree's
# branch (the previous hardcoded path pointed at the main worktree and misread the branch).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if ! echo "$CMD" | grep -qE 'git push'; then exit 0; fi
BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)
if [[ -z "$BRANCH" || "$BRANCH" == "main" ]]; then exit 0; fi
RUNS=$(gh run list --repo rediacc/console --branch "$BRANCH" --json databaseId,status --jq '.[] | select(.status == "in_progress" or .status == "queued") | .databaseId' 2>/dev/null)
if [[ -z "$RUNS" ]]; then exit 0; fi
COUNT=0
for rid in $RUNS; do
  gh api repos/rediacc/console/actions/runs/$rid/force-cancel -X POST 2>/dev/null && COUNT=$((COUNT+1))
done
if [[ $COUNT -gt 0 ]]; then
  echo "⚡ Auto-cancelled $COUNT old CI run(s) on $BRANCH. The new push triggers a fresh CI run. Watch it with: gh run watch <new-run-id> --repo rediacc/console --exit-status --interval 100 (run_in_background: true). Remember: watch the Console CI run, not Rerun Failed Jobs auto-retries."
fi
echo "📝 If a PR is open for $BRANCH: refresh its description NOW (gh pr edit <N> --body-file ...) — the PR-Description gate fails when the body is older than the newest commit. Stale-only failure? Refresh + 'gh run rerun <id> --failed' (no commit needed)."
exit 0

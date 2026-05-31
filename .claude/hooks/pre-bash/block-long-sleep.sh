#!/usr/bin/env bash
# Block sleep > 20s (catches the sleep+gh-run-view polling pattern).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
SLEEP_VAL=$(echo "$CMD" | grep -oE 'sleep +[0-9]+' | grep -oE '[0-9]+' | head -1)
if [[ -n "$SLEEP_VAL" && "$SLEEP_VAL" -gt 20 ]]; then
  echo "❌ BLOCKED: Do not use sleep > 20s. (Lowered from 30 to catch the sleep+gh-run-view polling pattern that was slipping through at 30 exactly.) Use: gh run watch RUN_ID --repo rediacc/console --exit-status --interval 100 with run_in_background:true. You will be notified automatically when it completes. NOTE: The CI has a watchdog that auto-retries transient failures and force-cancels code-change failures. When gh run watch reports failure, check if the run is a Rerun Failed Jobs auto-retry -- always watch the Console CI run, not the retry. Also: a PostToolUse hook auto-cancels old CI runs on every git push, so you never need to cancel manually." >&2
  exit 2
fi
exit 0

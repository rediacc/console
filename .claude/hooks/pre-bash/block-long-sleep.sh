#!/usr/bin/env bash
# Block sleep > 20s (catches the sleep+gh-run-view polling pattern).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
SLEEP_VAL=$(echo "$CMD" | grep -oE 'sleep +[0-9]+' | grep -oE '[0-9]+' | head -1)
if [[ -n "$SLEEP_VAL" && "$SLEEP_VAL" -gt 20 ]]; then
    echo '❌ BLOCKED: Do not use sleep > 20s. (Lowered from 30 to catch the sleep+gh-run-view polling pattern that was slipping through at 30 exactly.) To wait on CI, arm a terminal-state watch in the background (run_in_background:true): R=RUN_ID; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs. Do NOT rely on gh run watch -- it has dropped silently on terminal runs (observed 4/4); a process exit on terminal state is the reliable notification. NOTE: The CI has a watchdog that auto-retries transient failures and force-cancels code-change failures. When the watch reports failure, check whether the watchdog holds a pending auto-retry (attempt 2 lands on the SAME Console CI run) -- always watch the Console CI run, not the Watchdog Monitor chain runs. Also: a PostToolUse hook auto-cancels old CI runs on every git push, so you never need to cancel manually.' >&2
    exit 2
fi
exit 0

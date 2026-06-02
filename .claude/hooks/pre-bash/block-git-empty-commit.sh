#!/usr/bin/env bash
# Block empty commits used to re-trigger CI.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git commit[^|;&]*--allow-empty'; then
  echo "❌ BLOCKED: Do not use empty commits to re-trigger CI. Empty commits kick off a fresh CI run (attempt 1 of 2) that redoes ALL jobs and wastes runner minutes. Instead, rerun only the failed jobs: gh run rerun RUN_ID --repo rediacc/console --failed. If the run was force-cancelled (attempt 2 of 2 exhausted) and the AI classified a transient failure as code-change, first update .ci/prompts/ci-failure-classifier.md so that pattern is recognized as transient, then rerun." >&2
  exit 2
fi
exit 0

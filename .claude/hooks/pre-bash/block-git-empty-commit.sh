#!/usr/bin/env bash
# Block empty commits used to re-trigger CI.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git commit[^|;&]*--allow-empty'; then
  echo "❌ BLOCKED: Do not use empty commits to re-trigger CI. Empty commits kick off a fresh CI run (attempt 1 of 2) that redoes ALL jobs and wastes runner minutes. Instead, rerun the run: for failures in tunnel-CONSUMER jobs (Tests+Infra E2E / CLI / E2E Electron, or any job that waited on 'tunnel URL'), use a FULL 'gh run rerun RUN_ID --repo rediacc/console' — the tunnel-url artifact is named per run_attempt and the already-green publisher job (infra-backend) does not rerun on --failed, so a --failed rerun leaves consumers waiting 300s for an artifact that never appears. For all other failures, 'gh run rerun RUN_ID --repo rediacc/console --failed' is cheaper and sufficient. If the run was force-cancelled and the AI classified a transient failure as code-change, first update .ci/prompts/ci-failure-classifier.md so that pattern is recognized as transient, then rerun." >&2
  exit 2
fi
exit 0

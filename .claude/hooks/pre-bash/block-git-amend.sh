#!/usr/bin/env bash
# Block `git commit --amend` for PR babysitting.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git commit[^|;&]*--amend|git commit[^|;&]*[[:space:]]-[a-zA-Z]*amend'; then
  echo "❌ BLOCKED: Do not use 'git commit --amend' for PR babysitting. Amending rewrites the existing PR commit in place, which collapses every CI fix into one commit and destroys the per-change history (this PR's single commit was already amended 16 times and the individual changes became impossible to trace). Make EACH fix a NEW commit: git commit -m 'fix(scope): ...' then a plain 'git push'. The reviewer needs a readable per-commit trail. If commits genuinely need squashing, that is the user's call at merge time, not yours." >&2
  exit 2
fi
exit 0

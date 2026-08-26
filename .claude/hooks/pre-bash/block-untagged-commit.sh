#!/usr/bin/env bash
# Require a PR-TASK trailer on commits, so a per-epic review can find its work.
#
# WHY. The review now runs once per epic, and it selects an epic's commits with
# `git log --grep='^PR-TASK: <id>'`. A commit with no trailer belongs to no epic,
# so it is reviewed by nobody, silently. That is the same shape as the flat
# review's licence to leave areas unreviewed, moved one level down to where
# nothing reports it at all.
#
# ANCHORED TO LINE START, deliberately. The sibling guard block-commit-meta.sh
# states the rule this follows in its own header: a guard whose only failure mode
# is refusing CORRECT input teaches people to reword honest messages until it
# stops complaining. A commit whose prose merely mentions PR-TASK is not tagged;
# only a real trailer line is.
#
# NO COLLISION with the two existing message guards. Neither of their patterns
# matches PR-TASK, and there is no allowlist to update.
#
# KNOWN BLIND SPOT, stated rather than hidden: this sees only the raw Bash
# string, so `git commit -F file` and a command-substituted message are opaque to
# it. CI is the real enforcement; this hook exists to catch the common case at
# the moment it is cheapest to fix. It therefore ALLOWS what it cannot read
# rather than refusing a commit it cannot judge.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# Only a real `git commit` at command position. Anything else is out of scope.
printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+commit([[:space:]]|$)' || exit 0

# A message read from a file, or no inline message at all, is unreadable here.
printf '%s' "$CMD" | grep -qE '(-F|--file)([[:space:]]|=)' && exit 0
printf '%s' "$CMD" | grep -qE '\-m([[:space:]]|=)' || exit 0

# The trailer must START a line. Both a real newline and an escaped one are
# accepted, because $'...' and heredocs deliver the first while a -m string
# written with \n delivers the second.
if printf '%s' "$CMD" | grep -qP '(^|\\n|\n)[[:space:]]*PR-TASK:[[:space:]]*[0-9a-f]{6,32}'; then
    exit 0
fi

cat >&2 <<'MSG'
BLOCKED: this commit carries no PR-TASK trailer.

The review runs once per epic and selects an epic's commits with
`git log --grep='^PR-TASK: <id>'`. An untagged commit belongs to no epic, so it
is reviewed by nobody and nothing reports the gap.

Add a trailer line naming the epic this change belongs to:

  git commit -m "feat(x): what changed

  PR-TASK: <epic-id>"

List the epics, or make one:

  .claude/hooks/stop/worklist.py --epic <me> list
  .claude/hooks/stop/worklist.py --epic <me> new "<title>"
MSG
exit 2

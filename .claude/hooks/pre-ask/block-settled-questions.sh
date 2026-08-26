#!/usr/bin/env bash
# Refuse an AskUserQuestion whose answer CLAUDE.md already gives.
#
# THE PROBLEM, in the operator's words: "I don't know why you ask this question
# on each new session. It seems that my CLAUDE.md doesn't override you on each
# new session. See the big-bang statements there. Find a way to go for big-bang
# on each session."
#
# They are right that the document is not enough. Anthropic's own guidance says
# so: "CLAUDE.md content is delivered as a user message after the system prompt,
# not as part of the system prompt itself... there's no guarantee of strict
# compliance", and "If the instruction is something that must run at a specific
# point... write it as a hook instead. Hooks execute as shell commands at fixed
# lifecycle events and apply regardless of what Claude decides to do."
# So this is a hook.
#
# WHAT IT REFUSES, and nothing more: a PERMISSION-SEEKING question about
# committing, branching, pushing, opening a PR or merging. CLAUDE.md settles
# those twice over -- "the default deliverable is an uncommitted working tree"
# and "ask for the big-bang, not for permission to patch one thing" -- so asking
# costs the operator a round trip to repeat a rule they already wrote down.
#
# THE MATCH IS NARROW ON PURPOSE, and the narrowness is the whole design. A hook
# that swallows legitimate questions is worse than the nagging it replaces,
# because the operator never learns what was suppressed. Two independent
# conditions must BOTH hold:
#
#   1. a permission-seeking shape  (should I / shall I / do you want / may I /
#      would you like / is it ok / can I / want me to)
#   2. a git-workflow object       (commit / branch / push / PR / merge)
#
# So "Should I commit this?" is refused, while "Which branch strategy fits this
# repo?" and "Did the rebase drop a commit?" pass untouched: they are questions
# about DESIGN and FACT, not requests for permission this repo already granted.
#
# This is the same over-matching lesson wl_agents.py paid for four separate
# times in one session, where ordinary English words like `while`, `see`, `step`
# and `stop` were scoring as domain terms. Anchor on intent, not vocabulary.
INPUT=$(cat)

# jq is guaranteed here: require-jq.sh runs first in this same chain and fails
# closed without it.
QUESTION=$(printf '%s' "$INPUT" | jq -r '
  [ .tool_input.question?,
    (.tool_input.questions[]?.question),
    (.tool_input.questions[]?.header)
  ] | map(select(. != null)) | join(" ")
' 2>/dev/null | tr '[:upper:]' '[:lower:]')

[ -z "$QUESTION" ] && exit 0

PERMISSION='(should|shall|may|can) (i|we)|do you want|would you like|want me to|is it (ok|okay|fine)|are you happy for|should it be'
OBJECT='commit|branch|push|pull request|open a pr|[^a-z]pr[^a-z]|merge'

if ! printf '%s' "$QUESTION" | grep -qE "$PERMISSION"; then
    exit 0
fi
if ! printf '%s' "$QUESTION" | grep -qE "$OBJECT"; then
    exit 0
fi

cat >&2 <<'MSG'
BLOCKED: CLAUDE.md already answers this, so asking spends a round trip repeating
a rule the operator has written down twice.

  Session default 1: "The default deliverable is an uncommitted working tree.
  Do not git commit, create a branch, push, or open a PR unless the operator
  asks for it in that task."

  Findings rule: "Ask for the big-bang, not for permission to patch one thing...
  put the whole cluster into a single plan and ask to run it."

Proceed with the documented default: leave the work uncommitted, and if a
decision genuinely needs the operator, park it as a worklist [?] carrying its
own DEFAULT rather than blocking the turn on a question.

If you are NOT asking for permission -- a design question that happens to
mention branching, or a factual question about a merge -- rephrase it as the
question it actually is, and this hook will pass it.
MSG
exit 2

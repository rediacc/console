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
#
# WHAT A REFUSAL LEAVES BEHIND. Every refusal below appends one line to a
# ledger beside the worklist state (see LEDGER). Before that it left NO TRACE
# ANYWHERE, and `.claude/hooks/test-hooks.sh` says exactly why that matters:
# "a false positive is invisible by construction: the operator never learns
# what was not asked". A narrow matcher is only trustworthy if its misses are
# countable, so the denominator has to exist on disk.
INPUT=$(cat)

# jq IS NOT GUARANTEED HERE, and this comment used to claim it was: "jq is
# guaranteed here: require-jq.sh runs first in this same chain and fails closed
# without it." That is false. The AskUserQuestion matcher in
# .claude/settings.json contains exactly ONE hook -- this one -- so nothing runs
# ahead of it. Without jq the command substitution below produced an empty
# QUESTION and the `[ -z ... ]` guard passed the question through SILENTLY: a
# gate that cannot fire, wearing a comment that promised it could.
#
# The handling is now explicit and it FAILS OPEN ON PURPOSE, which is the
# opposite of the rule for the Stop gates next door. A missing jq is this
# hook's problem, not the session's, and blocking a legitimate question over a
# missing binary is the precise failure the "narrow on purpose" note above
# exists to prevent. So: pass the question, and SAY that it went unexamined
# rather than pretending it was examined and cleared.
if ! command -v jq >/dev/null 2>&1; then
    echo "block-settled-questions: jq not found; this question passed UNEXAMINED (the hook did not run its match)." >&2
    exit 0
fi

QUESTION=$(printf '%s' "$INPUT" | jq -r '
  [ .tool_input.question?,
    (.tool_input.questions[]?.question),
    (.tool_input.questions[]?.header)
  ] | map(select(. != null)) | join(" ")
' 2>/dev/null | tr '[:upper:]' '[:lower:]')

[ -z "$QUESTION" ] && exit 0

PERMISSION='(should|shall|may|can) (i|we)|do you want|would you like|want me to|is it (ok|okay|fine)|are you happy for|should it be'
OBJECT='commit|branch|push|pull request|open a pr|[^a-z]pr[^a-z]|merge'

PERM_HIT=$(printf '%s' "$QUESTION" | grep -oE "$PERMISSION" | head -n1)
[ -z "$PERM_HIT" ] && exit 0
OBJ_HIT=$(printf '%s' "$QUESTION" | grep -oE "$OBJECT" | head -n1)
[ -z "$OBJ_HIT" ] && exit 0

# ---- THE REFUSAL LEDGER -----------------------------------------------------
# One line per refusal, appended BEFORE the message is printed, so a refusal is
# recorded even if everything after this point fails. It carries the timestamp,
# the session, the question text this hook actually matched against (lowercased
# and joined, i.e. what the regexes saw rather than a reconstruction), and the
# two spans that matched -- so "which condition matched" is answerable from the
# file instead of by re-deriving it.
#
# It lives beside the worklist state (TMPDIR/claude-worklist/<slug>.md), NOT in
# the repo: it is per-machine session debris, and a ledger that dirtied the
# working tree would be deleted by the first person tidying a diff.
#
# BEST EFFORT, ALWAYS. `worklist.py --path` is self-contained (it works with
# every sibling module broken -- see suite case 118), but if python3 is missing
# or the write fails, the refusal still happens. A ledger that could veto the
# gate would be a worse bug than no ledger.
LEDGER=""
WLPATH=$(python3 "$(dirname "$0")/../stop/worklist.py" --path 2>/dev/null)
[ -n "$WLPATH" ] && LEDGER="${WLPATH}.ask-refusals.jsonl"
if [ -n "$LEDGER" ]; then
    SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
    jq -n -c \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg session "${SESSION:-unknown}" \
        --arg question "$(printf '%s' "$QUESTION" | head -c 500)" \
        --arg permission "$PERM_HIT" \
        --arg object "$OBJ_HIT" \
        '{ts:$ts, session:$session, question:$question, permission:$permission, object:$object}' \
        >>"$LEDGER" 2>/dev/null || true
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

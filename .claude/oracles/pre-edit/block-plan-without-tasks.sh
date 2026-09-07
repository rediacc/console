#!/usr/bin/env bash
# Refuse a plan file that carries no task list the Stop hook can parse.
#
# WHY THIS EXISTS, from this session rather than from theory. The plan-fidelity
# check (.claude/hooks/stop/wl_planfid.py) blocks a stop while "a plan task
# nothing tracks" exists, and it finds those tasks with a MARKDOWN parser. A
# plan written in prose is not seen as having zero tasks -- it is seen as
# having the WRONG ones. Measured on agent/PLAN-secret-namespace-migration.md
# before this guard existed: plan_tasks() returned 21 "tasks", of which 8 were
# the operator's locked DECISIONS and 5 were open QUESTIONS, while every real
# unit of work (the two rotation defects, the atomic rename, the four cleanup
# items) was invisible. The session was then told to decompose a list that did
# not describe its work, twice, and could not tell why.
#
# So the failure is not "the plan is badly written". It is that the author and
# the enforcement layer are reading two different documents, and nothing says
# so until a stop is refused for a reason the author cannot act on.
#
# THE RULE, and it is one line: a plan file must contain at least one CHECKBOX
# task, `- [ ]` or `- [x]`. That is the only construct wl_planfid.plan_tasks
# treats as a task WHEREVER it appears; everything else it counts is a plain
# bullet that happens to sit under a heading whose first three words name work,
# which is precisely the accident that turns a Decisions section into a task
# list.
#
# WHY NOT "zero parsed tasks". That weaker rule is the obvious one and it would
# have MISSED the incident above completely -- 21 > 0. A rule that cannot fire
# on the case that motivated it is the vacuous-gate shape TRAPS.md is about.
#
# WHY IT IS NOT OVER-BLOCKING, which is the failure mode check-hook-integrity.sh
# names as the reason guards get deleted. MEASURED, not assumed: 59 of the 62
# plans in agent/ today carry ZERO checkboxes, so a guard that refused every
# edit to a checkbox-less plan would fire on almost every plan in the tree, for
# work that has nothing to do with the convention. That guard would be deleted
# within a week. The scope is therefore drawn where authorship actually happens:
#
#   * a WRITE is authoring: the whole document is in hand, so it must conform,
#     whether the file is new or a wholesale rewrite of an old one
#   * an EDIT/MultiEdit is amending. It is judged against the union of the file
#     ON DISK and the incoming fragments, and it is enforced ONLY when the plan
#     already has a task list (so an edit can never strip one out) or the file
#     does not exist yet. A legacy prose plan is GRANDFATHERED against piecemeal
#     edits and says so on stderr rather than blocking
#   * scope is agent/PLAN-*.md and <anything>/.claude/plans/*.md, nothing else
#   * a plan under 400 chars is a stub and is exempt, matching wl_planfid's own
#     MIN_PLAN_CHARS floor for "worth judging"
#   * the remedy is one character per line, and the message writes it out
#
# THE PARSER IS IMPORTED, NEVER RE-DERIVED. This calls wl_planfid.plan_tasks and
# wl_planfid.CHECKBOX_RE directly, so the guard and the Stop hook cannot drift
# into disagreeing about what a task is -- the same discipline
# test-plan-status-parse.py uses on plan_records.
#
# FAILS OPEN on a missing python3, a missing module, or unreadable input. A
# guard about DOCUMENT SHAPE has no business walling a session in because an
# interpreter is absent; the Stop hook still enforces the real rule.
#
# RESIDUAL, stated rather than pretended away: an Edit that DELETES the last
# checkbox from a plan that has one is still allowed, because the union sees the
# on-disk list and cannot know the line is on its way out. Whole-file Writes --
# the shape that actually produced the incident -- are checked exactly.

INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$FILE" ] || exit 0
case "$FILE" in
    */agent/PLAN-*.md | agent/PLAN-*.md | */.claude/plans/*.md) ;;
    *) exit 0 ;;
esac

FRAGMENTS=$(printf '%s' "$INPUT" | jq -r '[.tool_input.content, .tool_input.new_string, .tool_input.new_source, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' 2>/dev/null)
[ -n "$FRAGMENTS" ] || exit 0

# A Write replaces the file outright; an Edit only amends it, so the resulting
# document is at least the union of what is there and what is arriving.
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
SUBJECT="$FRAGMENTS"
if [ "$TOOL" != "Write" ] && [ -f "$FILE" ]; then
    SUBJECT="$(cat "$FILE" 2>/dev/null)
$FRAGMENTS"
    # The grandfather clause. An amendment to a plan that never had a task list
    # is not the moment to demand one -- see the measured note above.
    if ! grep -qE '^[[:space:]]*[-*+] \[[ xX]\] ' "$FILE" 2>/dev/null; then
        echo "note: $FILE predates the plan-task convention (no '- [ ]' task list). Not blocking an amendment, but a plan without checkbox tasks is invisible to the Stop hook's plan-fidelity check -- add a '## Tasks' section next time you rewrite it." >&2
        exit 0
    fi
fi

STOPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../stop" 2>/dev/null && pwd)"
[ -n "$STOPDIR" ] && [ -f "$STOPDIR/wl_planfid.py" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# "<checkbox-count> <parsed-task-count>", or empty when anything at all went
# wrong -- see FAILS OPEN above.
COUNTS=$(printf '%s' "$SUBJECT" | STOPDIR="$STOPDIR" python3 -c '
import os, sys
sys.path.insert(0, os.environ["STOPDIR"])
try:
    import wl_planfid as P
except Exception:
    sys.exit(0)
text = sys.stdin.read()
if len(text) < P.MIN_PLAN_CHARS:
    sys.exit(0)
boxes = sum(1 for line in text.splitlines() if P.CHECKBOX_RE.match(line))
print(boxes, len(P.plan_tasks(text)))
' 2>/dev/null)
[ -n "$COUNTS" ] || exit 0

BOXES=${COUNTS%% *}
PARSED=${COUNTS##* }
[ "${BOXES:-1}" -eq 0 ] 2>/dev/null || exit 0

if [ "${PARSED:-0}" -gt 0 ]; then
    WHY="it has NO checkbox task, yet $PARSED of its plain bullets parse as tasks anyway -- they sit under a heading whose first three words name work, so the Stop hook will quote THOSE back at you as 'plan task(s) nothing tracks', decisions and open questions included. That is the exact confusion this guard exists to stop."
else
    WHY="it has no task list at all: wl_planfid.plan_tasks() finds 0 tasks in it, so the plan-fidelity check reads it as a document with nothing to decompose."
fi

cat >&2 <<MSG
❌ BLOCKED: $FILE is a plan with no parseable task list -- $WHY

ADD a section like this (anywhere in the file; '## Tasks' near the top is the convention):

## Tasks

- [ ] Fix <the concrete thing>, with a file:line or an id where you have one
- [ ] <the next real unit of work, one line each>
- [x] <a task already done>

The parser is .claude/hooks/stop/wl_planfid.py plan_tasks(). What it actually accepts:
  * '- [ ] text' and '- [x] text' count as a task ANYWHERE in the file. This is the only
    construct that is unambiguous, which is why this guard requires at least one.
  * '- [?]' and '- [>]' do NOT parse. They are worklist states, not plan tasks -- park
    them under a '## Remaining (operator)' heading instead.
  * a PLAIN bullet counts only under a heading whose FIRST THREE WORDS name work
    (wave/phase/step/stage/task/plan/implement/work/change/round/part/build/todo/action).
    That is why 'Part 0 - DECIDED by the operator' turns eight locked decisions into
    eight 'tasks': rename such a heading (e.g. 'Decisions locked by the operator
    (Part 0)') so its bullets read as the prose they are.
  * bullets indented 4 or more spaces are detail about their parent, never tasks.
  * fenced code blocks are skipped, and a task must normalise to 8+ characters.

Then track one worklist item per checkbox: worklist.py --add <you> <task text>
MSG
exit 2

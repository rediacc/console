---
description: Surface every decision currently waiting on the operator and put them as structured multiple-choice questions, so the operator never has to write a long prompt to be asked. Collects the three places a pending decision hides - `[?]` worklist deferrals with their DEFAULT/WHY/HOW, DECISIONS logged in the active round log for post-hoc veto, and gate/finding choices this session parked - then asks in batches with a recommended option first. Free text after the command narrows the scope to matching items.
argument-hint: "[filter: a substring, an item id, or a topic; omit to ask about everything pending]"
disable-model-invocation: true
allowed-tools: Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(git branch:*), Bash(ls:*), Bash(grep:*), Bash(date:*)
---

## Pending decisions, gathered

- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Open worklist items (`[?]` = already parked for you, `[ ]` = open work): !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | head -40 || echo '(worklist unavailable)'`
- Round log with DECISIONS awaiting veto: !`ls -t ~/.claude/projects/-home-muhammed-console/reports/pr-babysit-*.md 2>/dev/null | head -1 || echo '(no active round log)'`
- DECISIONS recorded in it: !`f=$(ls -t ~/.claude/projects/-home-muhammed-console/reports/pr-babysit-*.md 2>/dev/null | head -1); [ -n "$f" ] && grep -c '^- \*\*' "$f" 2>/dev/null || echo 0`

## What to do

**Ask. Do not implement, do not re-litigate, do not report status.** This command
exists because the operator should not have to compose a prompt to be consulted.
Its entire output is questions, then whatever the answers set in motion.

### 1. Collect, from all three places a decision hides

1. **`[?]` worklist deferrals.** Already parked for the operator, each carrying
   `DEFAULT:`/`WHY:`/`HOW:`. Their DEFAULT executes on a timer, so an unanswered
   one is a decision made by the clock. Those are the highest-value asks.
2. **DECISIONS in the active round log.** Choices made autonomously under the
   in-context tier-3 rule, recorded for **post-hoc veto**. The operator has never
   seen them; that is the point of asking.
3. **Choices this session made silently.** A default taken, a scope narrowed, an
   alternative rejected. If answering differently would change what ships, it
   belongs here even when nothing tracked it.

If `$ARGUMENTS` is non-empty, keep only items matching it (substring, item id, or
topic) and say how many were filtered out.

### 2. Filter to what is genuinely the operator's

Ask ONLY where the answer changes what happens next AND the call is not yours:
product intent, risk acceptance, packaging, anything outward-facing or
irreversible, and any veto of an autonomous gate/suppression decision.

**Do not ask** what the code, the request, or a sensible default already settles.
A question you could answer by running something is not a decision. It is a task,
so go run it. Over-asking is the failure mode this repo already has thirty deferrals
of; this command must not manufacture more.

If nothing survives the filter, say so in one line and stop. That is a valid,
common outcome and it is much better than inventing a question.

### 3. Ask with AskUserQuestion

- Batch up to 4 per call; if more remain, ask the next batch after these are
  answered rather than dumping everything.
- **Recommended option FIRST, labelled `(Recommended)`.** Silence should land on
  the sane choice.
- Each option's description carries the CONSEQUENCE, not a restatement of the
  label: what ships, what breaks, what it costs, what it forecloses.
- Include the real alternative you rejected as an option, described fairly. A
  veto is only meaningful when the thing being vetoed is on the ballot.
- For a `[?]`, the DEFAULT must appear as an option, marked as the default.
- Where a concrete artifact would decide it (a diff, two competing snippets, a
  layout), use `preview` so the operator compares rather than imagines.

### 4. Act on the answers

- Apply each answer immediately where it is cheap and unambiguous.
- **Record it where it survives compaction**: `--tick` the `[?]` with the
  operator's words as evidence, or append the ruling to the round log's DECISIONS
  section. An answer that lives only in chat is an answer that gets asked again.
- If an answer overturns something already committed, say plainly what is being
  reverted and do it; do not defend the original.
- If an answer opens new work, put it on the worklist rather than starting a
  second thread of it mid-command.

### 5. Report in one screen

Answers received, what each changed, what is now unblocked. No essay: the
operator just answered questions and does not need them narrated back.

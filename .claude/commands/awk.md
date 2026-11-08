---
description: Away from keyboard. Marks the operator away until their next message, so no question is put to them and the session keeps draining work alone. AskUserQuestion is refused by the pre-ask guard while the mode stands; a decision that is genuinely the operator's is parked as a `[?]` with a DEFAULT, which executes when its window closes unanswered. Reusable; the mode ends by itself at the operator's next message. Free text after the command is kept as the away note.
argument-hint: "[note: why or until when, e.g. 'until morning']"
allowed-tools: Bash(python3 .claude/hooks/stop/wl_away.py:*), Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(git branch:*), Bash(date:*)
---

## Away mode, set

- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Branch: !`git branch --show-current`
- Flag: !`python3 .claude/hooks/stop/wl_away.py set`
- Note: $ARGUMENTS
- Open worklist slice: !`.claude/hooks/stop/worklist.py --list --open 2>&1 | head -30`

## How to work while the operator is away

The operator is away from the keyboard. Nobody reads a question until they return, so a question costs the whole wait. The mode ends by itself at their next message (a typed turn, an interrupt, or a message sent mid-turn); `python3 .claude/hooks/stop/wl_away.py clear` ends it by hand.

1. **No questions.** `AskUserQuestion` is refused by `block_away_questions` (chain `pre-ask`). No question goes into prose at the end of a turn either: a report ends with what was done and what runs, never with a request for permission.
2. **Decide what is the session's to decide.** Anything the code, the request, a ruling, `feedback` memory or a sensible default settles is decided now, and the choice is recorded where the operator will read it: the round log's DECISIONS section for a veto in the morning, or the commit message.
3. **Park only what is genuinely the operator's**: product intent, risk acceptance, spend, anything outward-facing or irreversible that no ruling covers. Park it as a deferral whose DEFAULT is the recommended choice, and keep working on everything that does not wait on it:
   `.claude/hooks/stop/worklist.py --defer <me> <id> '<question> DEFAULT: <action> WHY: <reason> HOW: <exact command>'`
   A DEFAULT that must not run before a set instant carries `NOT-BEFORE:<ISO8601Z>`. A question parked here is asked properly, through `/ask`, once the operator is back.
4. **Keep draining.** The Stop hook's queue is the work order: plan boxes, live queues (bench and hostinger start at once), landings, reviews, gate runs once per batch. A stop that waits on background work arms the wake timer as its own background call (`python3 .claude/hooks/stop/wl_wake.py <me>`, `timeout: 2400000`). Standing rules are unchanged: operator-only actions (secrets the session cannot mint, purchases, a stable release without `RELEASE_ASKED`) stay parked, and production data is never deleted.
5. **Leave a morning digest.** Before each long wait, `STATE.md` (through `worklist.py --state <me>`) carries an `## Overnight` section: what landed (commit shas), what was ticked, what was decided under rule 2 and where it is recorded, and each parked `[?]` with its DEFAULT and when that DEFAULT fires.

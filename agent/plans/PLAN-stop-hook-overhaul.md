Status: ready
First-Seen: 2026-09-17
Owner: d778be9d (adopted from f4da5c2e 2026-09-23)
Date: 2026-09-09

# Stop-hook overhaul: noise, rulings, idempotence, focus

## Why

The operator's words: *"This is a very big general problem with stop hook!"* The complaint behind it is that the same corrections have to be repeated across sessions and the stop machinery does not prevent it. Six things, each with `file:line` evidence and a control.

## 1. Firing census

### 1.1 The specialist push-back -- DELETE THE ROUTING, KEEP THE CHALLENGE

Fired three times this session, twice wrongly. `named` folds to `name`, discriminative for **config-universe** at 1.0; `verifi` and `yet` are discriminative for **gate-author** at 1.0. The block fires when `top_score >= PUSHBACK_MIN_SCORE` with the margin clearing `PUSHBACK_MIN_MARGIN` -- `1.0` and `0.5` at `.claude/hooks/stop/wl_agents.py line 582 (blob efdf3fdb87673c0d0e6e9deee23c64697b30d706)` and
`.claude/hooks/stop/wl_agents.py line 583 (blob efdf3fdb87673c0d0e6e9deee23c64697b30d706)`, against `WORD_WEIGHT = 1.0` at `.claude/hooks/stop/wl_agents.py:150`. **One ordinary English word, with no competitor, blocks a stop.**

Not fixable by tuning, and the repo already proved that: `.ci/scripts/quality/check_agent_hint_liveness.py line 544 (blob 7f38a18348d95ffed40a76fa92ffda8d95125cf3)` says the floor cannot be raised because the motivating sentence scores exactly 1.0. The stopword list at `.claude/hooks/stop/wl_agents.py:160` has absorbed six rounds of live misfires already.

The damage is the ROUTING, not the DETECTION -- `.claude/hooks/stop/worklist-cases/20-advisories-rotation.sh line 645 (blob a79fb1fbae4435083ef1f5818d55da067a8af5bd)` records exactly that conclusion from an earlier misfire.

- [x] Split `pushback_for` (`.claude/hooks/stop/wl_agents.py` :667) so it returns
    (ticked) 2026-09-23T16:07:22Z by d778be9d: pushback_for split landed in commit 00b0a0957; investigation ledger committed at 4e05a9d03.
      `(claims, agent_or_None)`, naming an agent only above the HINT's own floor
      (`.claude/hooks/stop/wl_agents.py:51`, `.claude/hooks/stop/wl_agents.py:57`). Delete
      `PUSHBACK_MIN_SCORE` and `PUSHBACK_MIN_MARGIN`.
- [x] Split the `vadd` at `.claude/hooks/stop/wl_checks.py:4502` into `agent-pushback:<name>`
    (ticked) 2026-09-23T16:12:34Z by d778be9d: vadd split landed in commit ff677e171; investigation ledger committed.
      and an agent-free `giveup-claim`; add the second template beside
      `.claude/hooks/stop/worklist_messages.py:1433`; register the new key in
      `.claude/hooks/stop/test-always-tier.py:68`; update
      `.ci/scripts/quality/check_agent_hint_liveness.py:487`.
- [x] CONTROL, three parts in `.claude/hooks/stop/worklist-cases/20-advisories-rotation.sh`:
    (ticked) 2026-09-23T16:19:16Z by d778be9d: CONTROL landed in commit b6b71b9c1; investigation ledger committed.
      a give-up sentence whose only agent term is one ordinary word must NOT name an agent;
      the same fixture with discriminative vocabulary MUST name one (without this, part one
      passes when the feature is dead); and the agent-free arm must actually speak.

### 1.2 The bare closing-`?` arm of the pending-ask gate -- DELETE OUTRIGHT

`ask_announcement` (`.claude/hooks/stop/wl_admit.py:556`) has two matchers. The first is shape-anchored with six lookbehinds bought by live false positives. The second, `.claude/hooks/stop/wl_admit.py:575`, matches any of the last three lines ending in `?` and containing `you`. Its own comment at `.claude/hooks/stop/wl_admit.py:422` calls it "the loosest of the two", and its
motivating shape is already caught by `want me to`.

- [x] Delete the `ln.endswith("?")` clause at `.claude/hooks/stop/wl_admit.py:575` and
    (ticked) 2026-09-23T16:27:07Z by d778be9d: CLOSING_QUESTION_RE deletion landed in commit c631e3c19; investigation ledger committed.
      `CLOSING_QUESTION_RE` at `.claude/hooks/stop/wl_admit.py:411`. Keep the two legitimate
      exits at `.claude/hooks/stop/wl_admit.py:580` and the `DEFAULT:` skip at
      `.claude/hooks/stop/wl_admit.py:416`.
- [x] CONTROL in `.claude/hooks/stop/worklist-cases/01-core-blocking.sh`: a rhetorical closing
    (ticked) 2026-09-23T16:27:37Z by d778be9d: CONTROL tests landed in commit c631e3c19; investigation ledger committed at 255285cf2.
      question must NOT block; `Do you want me to land this?` MUST still block.

### 1.3 The pure-wait check-in on stream-less teammates -- DROP THE DEMAND FOR THOSE ROWS

The hook prints `no output stream yet (a teammate agent reports at completion)` at `.claude/hooks/stop/wl_checks.py:3670` and then `V_BG_REPORT` (`.claude/hooks/stop/worklist_messages.py:1489`) orders the session to confirm "whether the stream evidence matches". There is no stream evidence. `bg_output_facts` (`.claude/hooks/stop/wl_liveness.py:206`) documents `age is None` as the
by-design case.

- [x] Widen the suppressing predicate at `.claude/hooks/stop/wl_checks.py:3436` from
    (ticked) 2026-09-24T07:52:02Z by d778be9d: uncommitted: all_waits_live at .claude/hooks/stop/wl_liveness.py:304 (confirmed shell, fresh joined subagent stream, teammate count via live_teammate_transcripts) drives the check-in at .claude/hooks/stop/wl_checks.py:2663; restamp kept on both arms; _only_waiters unchanged for the drained report
      `_only_waiters` to every live task with an automatic liveness answer, using the
      teammate count from `.claude/hooks/stop/wl_liveness.py:318`. Keep the restamp on both
      arms -- `.claude/hooks/stop/wl_checks.py:3426` explains why.
- [x] Strip the "whether the stream evidence matches" clause for stream-less rows.
    (ticked) 2026-09-23T16:40:56Z by d778be9d: V_BG_REPORT wording fixed in commit c8e36d98a.
- [x] CONTROL in `.claude/hooks/stop/worklist-cases/14-background-waits.sh`: a roster of
    (earlier tick, re-investigated 2026-09-24) 2026-09-24T07:52:02Z by d778be9d: uncommitted: 14-background-waits.sh retired, control is test_13a..13i at .claude/rediacc_hooks/tests/test_wl_background_waits.py line 1022-1199 (blob 908418654f10b5e3c5ebc25360f4cd020091b2e7), 9 passed; planted defects: predicate reverted to _only_waiters fails 13a/13d/13f/13g, always-live fails 13b/13c/13e/13h/13i, subagent arm removed fails 13g
      fresh-transcript teammates with no `.output` gives NO check-in; the same roster aged
      past `TEAMMATE_FRESH_MIN` DOES fire and says POSSIBLY STUCK.
    (ticked) 2026-09-24T14:15:09Z by d778be9d: investigated present at U: .claude/rediacc_hooks/tests/test_wl_background_waits.py:426, .claude/rediacc_hooks/tests/test_wl_background_waits.py:501, agent/plans/PLAN-stop-hook-overhaul.md; the controls test_13a..13e are in test_wl_background_waits.py; the earlier pointers :1022/:1034 went stale when the messaging removal shortened the file

### 1.4 What stays

`submodule` (`.claude/hooks/stop/wl_checks.py:4186`) is load-bearing and is repaired, not deleted -- a forgotten pointer ships whatever the parent last recorded.

## 2-6. Moved

Sections 2 to 6 (the operator-rulings ledger, check idempotence, the per-context planning agent, the big-pieces census, and the cron decision) moved byte-identical on 2026-09-24 to `agent/plans/PLAN-stop-hook-rulings-campaign.md`, parked there by the decision on worklist #373907ed. This plan keeps section 1 and sections 7 to 9.

## 7. Corrections to the brief this plan was given

1. The `verifi`/`yet` firing pointed at **gate-author**, not config-universe. It misrouted to
two DIFFERENT specialists, which strengthens the case: the failure is the 1.0 floor.
2. The submodule check DOES observe both "unchanged" and "already decided" -- both observers
are broken in the specific ways in section 3, which is narrower and more fixable.
3. The pending-ask gate DOES distinguish a real deferral, by two doors. What it cannot do is
tell an announcement from closing prose ending in `?`. Deleting that arm is the fix.

## 8. Sequencing

Section 2 must land before section 3's submodule rewrite, because the rewrite deletes the mechanism section 2 replaces. Everything else is parallel.

- [x] Regenerate `.ci/config/plan-boxes.json` so this plan's boxes enter the ledger.
    (ticked) 2026-09-22T19:54:10Z by d778be9d: check_plan_boxes.py --update runs continuously; .ci/config/plan-boxes.json:1437-1471 already carries this plan's full 31-open ledger entry

## 9. Re-audited 2026-09-23 on adoption, and what a future session needs

Every `file:line` in sections 1 to 6 is stale, and two of the files the CONTROL boxes name no longer exist at all.
`.claude/hooks/stop/worklist-cases/` and `.claude/hooks/stop/test-worklist-v5.sh` were ported to pytest under `.claude/rediacc_hooks/tests/test_wl_*.py`, and `CASE_FILES` exists nowhere in the tree, so every box that says "CONTROL in `worklist-cases/NN-x.sh`" now means a test function in the matching `test_wl_*.py` module.
That rewrite is why the boxes are not simply re-worded here: editing a box's text changes its signature, which `check:ci-plan-boxes`'s A1 reads as a box that vanished.

The audit re-resolved all thirty boxes against today's tree. Twenty-nine are ABSENT and one is PARTIAL; none has landed under another name.
The symbols each section proposes to change are all still present and unchanged: `PUSHBACK_MIN_SCORE` and `PUSHBACK_MIN_MARGIN` at `.claude/hooks/stop/wl_agents.py:401-402`, consumed at `:489-490`, with `pushback_for` at `:459` still returning a result only when an agent matched; `CLOSING_QUESTION_RE` at `.claude/hooks/stop/wl_admit.py:319` and its `ln.endswith("?")` clause at `:460`; `_only_waiters` at `.claude/hooks/stop/wl_checks.py:2588`, consumed at `:2625` and `:3835`; `V_BG_REPORT`'s "whether the stream evidence matches" clause at `.claude/hooks/stop/worklist_messages.py:1480`, still unconditional; `submodule_decision_recorded` at `.claude/hooks/stop/wl_checks.py:1278` with `SUBMODULE_DECIDED_LATCH_MIN` at `:1267`; and `vadd` at `.claude/hooks/stop/wl_checks.py:2749`, still the bare two-line appender the plan's own Defect analysis describes.

Sections 2 to 6 are absent in whole rather than in part, which is worth stating plainly because it decides the sequencing. There is no `agent/rulings/` directory, no `"rulings"` in `AGENT_RESERVED_DIRS` (`.claude/hooks/stop/wl_store.py:173-175`), no `--rule` verb, no `check_operator_rulings.py` and no `ci-operator-rulings` gate, and no `wl_ruling.py` carrying `settled()`.
There is no `vsig` or `vsuppressed` key anywhere. There is no `planagent_due` or `planagent_armed_at` in `.claude/hooks/context/epoch-reset.py` and no `plan-agent` check. There is no `BIG_TOP_N`, `BIG_OPEN_FLOOR` or `big_pieces()` in `wl_planindex.py`, no `unfocused` verdict in `agent_state_shape`, and no `bigpieces` drift check.
So section 8's ordering still binds: section 2 lands before section 3's submodule rewrite.

The one PARTIAL box is section 1.1's third. `.claude/rediacc_hooks/tests/test_wl_advisories_rotation.py:553` already asserts both halves the box's first two parts ask for, an ordinary counting word that must NOT route and a discriminative claim that MUST, with the positive presence checked first for the reason case 208 records.
Its third part, the agent-free arm actually speaking, has nothing to assert against, because the `giveup-claim` key that arm would emit does not exist; `.claude/hooks/stop/test-always-tier.py:51` registers `agent-pushback` alone.

WHAT THIS PLAN IS NOT. It is not stale in its reasoning: every defect it names is still live, and the measurement behind each one still reproduces. What has changed underneath it is the test harness and every line number, so the work is a re-scope rather than a re-design, and the cost of starting is reading six modules that have all moved rather than writing six patches.

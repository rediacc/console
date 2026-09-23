Status: ready
First-Seen: 2026-09-17
Owner: f4da5c2e
Date: 2026-09-09

# Stop-hook overhaul: noise, rulings, idempotence, focus

## Why

The operator's words: *"This is a very big general problem with stop hook!"* The complaint behind it is that the same corrections have to be repeated across sessions and the stop machinery does not prevent it. Six things, each with `file:line` evidence and a control.

## 1. Firing census

### 1.1 The specialist push-back -- DELETE THE ROUTING, KEEP THE CHALLENGE

Fired three times this session, twice wrongly. `named` folds to `name`, discriminative for **config-universe** at 1.0; `verifi` and `yet` are discriminative for **gate-author** at 1.0. The block fires when `top_score >= PUSHBACK_MIN_SCORE` with the margin clearing `PUSHBACK_MIN_MARGIN` -- `1.0` and `0.5` at `.claude/hooks/stop/wl_agents.py:582` and
`.claude/hooks/stop/wl_agents.py:583`, against `WORD_WEIGHT = 1.0` at `.claude/hooks/stop/wl_agents.py:150`. **One ordinary English word, with no competitor, blocks a stop.**

Not fixable by tuning, and the repo already proved that: `.ci/scripts/quality/check_agent_hint_liveness.py:544` says the floor cannot be raised because the motivating sentence scores exactly 1.0. The stopword list at `.claude/hooks/stop/wl_agents.py:160` has absorbed six rounds of live misfires already.

The damage is the ROUTING, not the DETECTION -- `.claude/hooks/stop/worklist-cases/20-advisories-rotation.sh:645` records exactly that conclusion from an earlier misfire.

- [ ] Split `pushback_for` (`.claude/hooks/stop/wl_agents.py:667`) so it returns
      `(claims, agent_or_None)`, naming an agent only above the HINT's own floor
      (`.claude/hooks/stop/wl_agents.py:51`, `.claude/hooks/stop/wl_agents.py:57`). Delete
      `PUSHBACK_MIN_SCORE` and `PUSHBACK_MIN_MARGIN`.
- [ ] Split the `vadd` at `.claude/hooks/stop/wl_checks.py:4502` into `agent-pushback:<name>`
      and an agent-free `giveup-claim`; add the second template beside
      `.claude/hooks/stop/worklist_messages.py:1433`; register the new key in
      `.claude/hooks/stop/test-always-tier.py:68`; update
      `.ci/scripts/quality/check_agent_hint_liveness.py:487`.
- [ ] CONTROL, three parts in `.claude/hooks/stop/worklist-cases/20-advisories-rotation.sh`:
      a give-up sentence whose only agent term is one ordinary word must NOT name an agent;
      the same fixture with discriminative vocabulary MUST name one (without this, part one
      passes when the feature is dead); and the agent-free arm must actually speak.

### 1.2 The bare closing-`?` arm of the pending-ask gate -- DELETE OUTRIGHT

`ask_announcement` (`.claude/hooks/stop/wl_admit.py:556`) has two matchers. The first is shape-anchored with six lookbehinds bought by live false positives. The second, `.claude/hooks/stop/wl_admit.py:575`, matches any of the last three lines ending in `?` and containing `you`. Its own comment at `.claude/hooks/stop/wl_admit.py:422` calls it "the loosest of the two", and its
motivating shape is already caught by `want me to`.

- [ ] Delete the `ln.endswith("?")` clause at `.claude/hooks/stop/wl_admit.py:575` and
      `CLOSING_QUESTION_RE` at `.claude/hooks/stop/wl_admit.py:411`. Keep the two legitimate
      exits at `.claude/hooks/stop/wl_admit.py:580` and the `DEFAULT:` skip at
      `.claude/hooks/stop/wl_admit.py:416`.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/01-core-blocking.sh`: a rhetorical closing
      question must NOT block; `Do you want me to land this?` MUST still block.

### 1.3 The pure-wait check-in on stream-less teammates -- DROP THE DEMAND FOR THOSE ROWS

The hook prints `no output stream yet (a teammate agent reports at completion)` at `.claude/hooks/stop/wl_checks.py:3670` and then `V_BG_REPORT` (`.claude/hooks/stop/worklist_messages.py:1489`) orders the session to confirm "whether the stream evidence matches". There is no stream evidence. `bg_output_facts` (`.claude/hooks/stop/wl_liveness.py:206`) documents `age is None` as the
by-design case.

- [ ] Widen the suppressing predicate at `.claude/hooks/stop/wl_checks.py:3436` from
      `_only_waiters` to every live task with an automatic liveness answer, using the
      teammate count from `.claude/hooks/stop/wl_liveness.py:318`. Keep the restamp on both
      arms -- `.claude/hooks/stop/wl_checks.py:3426` explains why.
- [ ] Strip the "whether the stream evidence matches" clause for stream-less rows.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/14-background-waits.sh`: a roster of
      fresh-transcript teammates with no `.output` gives NO check-in; the same roster aged
      past `TEAMMATE_FRESH_MIN` DOES fire and says POSSIBLY STUCK.

### 1.4 What stays

`submodule` (`.claude/hooks/stop/wl_checks.py:4186`) is load-bearing and is repaired, not deleted -- a forgotten pointer ships whatever the parent last recorded.

## 2. A durable OPERATOR RULING record

`agent/RULES.md` is read at exactly ONE place in the whole hook tree, `.claude/hooks/stop/wl_checks.py:2303`, where its text is pasted into a briefing. **No check consults it before firing.** Every ruling that binds machinery today is a hand-written constant -- `.claude/hooks/stop/wl_reggate.py:56` is the clearest case.

The freshness asymmetry is half the answer (`.claude/hooks/stop/wl_store.py:116`: "STATE.md is rewritten and freshness-gated; RULES.md is sharpened and never age-gated") -- it gives a ruling a durable HOME. It does not give a check a way to READ it.

- [ ] Add `agent/rulings/<session8>.jsonl`, append-only, one file per writing session -- the
      merge-conflict argument at `.claude/hooks/stop/wl_reggate.py:114`. Row shape:
      `{ev, id, at, by, check, subject, sig, verdict, text}`; a reversal is a second `revoke`
      row. **There is no delete path**, which is what makes a silent drop impossible.
- [ ] Add `"rulings"` to `AGENT_RESERVED_DIRS` at `.claude/hooks/stop/wl_store.py:289`.
- [ ] Add a `worklist.py --rule <prefix> <check-key> <subject> '<text>' [--until <ISO>]` verb
      using the flock/tempfile/`os.replace` discipline at `.claude/hooks/stop/worklist.py:1469`.
      It appends the row AND rewrites a generated `## Rulings (machine-checked)` section in
      `agent/RULES.md`.
- [ ] Add `.ci/scripts/quality/check_operator_rulings.py` asserting byte-equality between the
      rendered section and the ledger -- the anti-lying-cache discipline
      `.claude/hooks/stop/wl_planindex.py:25` already states. Wire a new gate registered as `ci-operator-rulings`.
- [ ] Add `.claude/hooks/stop/wl_ruling.py` exposing `settled(root, check_key, subject_sig)`,
      globbing ALL sessions' ledgers. Any error returns `None`, restoring today's behaviour.
- [ ] CONTROL, new `.claude/hooks/stop/worklist-cases/27-rulings.sh` added to `CASE_FILES` in
      `.claude/hooks/stop/test-worklist-v5.sh`: moved pointer blocks; a ruling silences the
      next stop; a DIFFERENT sha blocks again (keyed on subject, not a global mute); a
      wholesale `--state` rewrite leaves it silent; a FRESH session id leaves it silent
      (the cross-session property today's mechanism lacks); `--revoke` blocks again.

## 3. Idempotence: how a check knows nothing has changed

`outq_add` (`.claude/hooks/stop/wl_checks.py:1861`) dedupes advisories on `sha1(text)`. The VIOLATION path has nothing equivalent: `vadd` (`.claude/hooks/stop/wl_checks.py:3634`) is three lines that append to a list.

**Defect A -- the latch is session-local.** `_sub` reads `state_doc["subptr"]` (`.claude/hooks/stop/wl_checks.py:4174`), so a new session fires on its first stop. The cross-session door, `submodule_decision_recorded` (`.claude/hooks/stop/wl_checks.py:1737`), is a SUBSTRING scan requiring both the path and `sha[:9]` in one event's values -- a correct decision recorded in prose gets
no credit. That is the likely "I decided it and it fired again".

**Defect B -- the latch is spent only if the text wins rotation.** `submodule` is `always=False` (`.claude/hooks/stop/wl_checks.py:4186`); its latch is spent by `spend_display_latches` (`.claude/hooks/stop/wl_checks.py:3655`) with the keys actually rendered (`.claude/hooks/stop/wl_checks.py:5579`). **But the violation was already appended** and a non-empty list blocks regardless.
That is the three-identical-stops mechanism exactly.

- [ ] Extend `vadd` with `subject=` and `latch_min=`: compute `sig`, consult
      `wl_ruling.settled`, then `state_doc["vsig"][key]`, and **suppress before appending** so
      a ruled-on or unchanged subject never reaches `violations`. Register the stamp in the
      existing `display_latch` dict at `.claude/hooks/stop/wl_checks.py:3653`.
- [ ] Rewrite the submodule site at `.claude/hooks/stop/wl_checks.py:4155-4200` onto it.
- [ ] Delete `submodule_decision_recorded` (`.claude/hooks/stop/wl_checks.py:1737-1802`) and
      `SUBMODULE_DECIDED_LATCH_MIN` (`.claude/hooks/stop/wl_checks.py:1724`).
      `SUBMODULE_LATCH_MIN` (`.claude/hooks/stop/wl_checks.py:1717`) survives as `latch_min`.
- [ ] Report `state_doc["vsuppressed"]` in `worklist.py --doctor`, one line per key. Silence
      needs a denominator or a ruling can quietly mute a real signal.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/03-drift-loops-freshness.sh`: three stops
      with the same moved pointer and a higher-priority violation winning rotation every time
      must yield exactly ONE block -- **write it to fail against current HEAD**; changing the
      sha between stops must block; `--doctor` must report a non-zero suppression count.

## 4. The planning agent per context: a Stop check

**Verdict: a Stop check, armed by the existing PostCompact epoch. Not PostCompact alone. Not
a cron.** PostCompact cannot refuse anything -- `.claude/hooks/context/epoch-reset.py:14`: "PostCompact has no decision control ... Exit 0, always." A printed requirement is a document, and `.claude/hooks/stop/wl_checks.py:4488` already says a document an agent can skip is not a control. A cron cannot express "per context" at all.

- [ ] Arm: add `planagent_due` and `planagent_armed_at` to the existing `save_state` at
      `.claude/hooks/context/epoch-reset.py:26`.
- [ ] Enforce: a new `plan-agent` Stop check, `always=True`.
- [ ] Disarm on UNFAKEABLE evidence: an index row written by
      `wl_report.handle_subagent_stop` (`.claude/hooks/stop/wl_report.py:646`, type recorded
      at `.claude/hooks/stop/wl_report.py:585`, index at `.claude/hooks/stop/wl_report.py:154`)
      with `session == me8`, `at >= planagent_armed_at`, and a planning `type`. The session
      does not write that row; the harness does.
- [ ] Two anti-nag rules, both required: never fire on the FIRST stop of an epoch, and never
      fire when the session has done no write work in the epoch.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/25-first-touch.sh`: armed + write work +
      two stops blocks; a planning index row after the arm silences it; the SAME row stamped
      BEFORE the arm still blocks; armed with no write work is silent.

## 5. Big pieces: derive the mark, gate the section

`agent/INDEX.md` already carries a `## Plan census` (`.claude/hooks/stop/wl_planindex.py:98`) with per-plan open-box counts (`.claude/hooks/stop/wl_planindex.py:164`), held byte-equal by G-R8 -- which is why `.claude/hooks/stop/wl_planindex.py:25` calls it authoritative rather than a cache.

**A big piece is a census row that is not finished and whose open count is in the top N (default 5) or `>= 10`.** No new field, nothing to hand-maintain, nothing to go stale. It encodes the ruling already at `agent/RULES.md`: finish the big pieces first.

- [ ] Add `BIG_TOP_N`, `BIG_OPEN_FLOOR` and `big_pieces(root)` to
      `.claude/hooks/stop/wl_planindex.py`; sort and mark them in `plans_block`
      (`.claude/hooks/stop/wl_checks.py:1377`) so the session copies from what the hook just
      handed it.
- [ ] Add an `unfocused` verdict to `agent_state_shape` (`.claude/hooks/stop/wl_store.py:2420`)
      -- the one choke point BOTH write paths share -- requiring a `## Big pieces` section
      exactly as `## Next action` is required.
- [ ] Add a rotating `bigpieces` drift check comparing the section against the census. This is
      what survives a wholesale rewrite: the rewrite is FORCED to re-derive, and a drift check
      on a derived field cannot be satisfied by remembering.
- [ ] CONTROL across `.claude/hooks/stop/worklist-cases/02-state-document.sh` and
      `.claude/hooks/stop/worklist-cases/16-triage-and-plans.sh`: a body without the section is
      refused by BOTH write paths; with it, accepted; a section naming a finished plan fires
      the drift check; a section agreeing with the census is silent.

## 6. Cron: NO

Three reasons. **(1)** The cron shape is already fixed and enforced: a second work schedule is blocked at `.claude/hooks/stop/wl_checks.py:5000` and a second poll cron at `.claude/hooks/stop/wl_checks.py:5011`. **(2)** A cron wakes a session to check a fact that only changes when a file changes, and this repo has paid that bill -- `.claude/hooks/stop/wl_store.py:121` records a
pure-age rule "outpaced by the 5-minute poll cron". **(3)** A clock cannot express "once per context".

- [ ] Instead, fold ONE conditional line into the existing `worklist.py --poll`, emitted only
      when the STATE.md `## Big pieces` section disagrees with the census. A poll printing
      nothing ends the turn silently (`.claude/hooks/stop/worklist_messages.py:378`), so this
      costs no new schedule and no turn on an empty result.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/08-poll-and-waiting.sh`: an agreeing
      section prints NOTHING (assert empty stdout); a disagreeing one prints exactly the line.

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

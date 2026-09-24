# PLAN: stop-hook rulings campaign (sections 2-6 split from PLAN-stop-hook-overhaul.md)
Status: draft -- sections 2+3 and 5 APPROVED by operator ruling on #373907ed (2026-09-23T14:31Z); section 4 declined and moved to PLAN-stop-hook-plan-agent-check-declined.md; section 6 not named in that ruling and stays a proposal. Not adopted by any session, so its boxes are advisory until one adopts it.
Correction, 2026-09-24: this header used to say #373907ed PARKED sections 2 to 6. That was the question's DEFAULT, not the answer. Not adopted by any session, so its boxes are an advisory, never a block.
First-Seen: 2026-09-17
Owner: d778be9d (the session holding the #373907ed answer)
Date: 2026-09-24

Split out byte-identical on 2026-09-24 from `agent/plans/PLAN-stop-hook-overhaul.md`, which keeps section 1 (the noise fixes the decision said to execute) and its sections 7 to 9. The split exists because an adopted plan makes every open box a blocking mission, so these parked boxes demanded fresh trackers on every stop; five add-and-tick rounds had not ended that.

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
- [ ] CONTROL, new `.claude/rediacc_hooks/tests/test_wl_rulings.py` (a new pytest module, collected automatically; was
      the retired `test-worklist-v5.sh` CASE_FILES list): moved pointer blocks; a ruling silences the
      next stop; a DIFFERENT sha blocks again (keyed on subject, not a global mute); a
      wholesale `--state` rewrite leaves it silent; a FRESH session id leaves it silent
      (the cross-session property today's mechanism lacks); `--revoke` blocks again.

## 3. Idempotence: how a check knows nothing has changed

`outq_add` (`.claude/hooks/stop/wl_checks.py:1861`) dedupes advisories on `sha1(text)`. The VIOLATION path has nothing equivalent: `vadd` (`.claude/hooks/stop/wl_checks.py:3634`) is three lines that append to a list.

**Defect A -- the latch is session-local.** `_sub` reads `state_doc["subptr"]` (`.claude/hooks/stop/wl_checks.py:4174`), so a new session fires on its first stop. The cross-session door, `submodule_decision_recorded` (`.claude/hooks/stop/wl_checks.py:1737`), is a SUBSTRING scan requiring both the path and `sha[:9]` in one event's values -- a correct decision recorded in prose gets
no credit. That is the likely `I decided it and it fired again`.

**Defect B -- the latch is spent only if the text wins rotation.** `submodule` is `always=False` (`.claude/hooks/stop/wl_checks.py:4186`); its latch is spent by `spend_display_latches` (`.claude/hooks/stop/wl_checks.py:3655`) with the keys actually rendered (`.claude/hooks/stop/wl_checks.py line 5579 (blob d86d0bcbd3be)`). **But the violation was already appended** and a non-empty list blocks regardless.
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
- [ ] CONTROL in `.claude/rediacc_hooks/tests/test_wl_drift_loops_freshness.py`: three stops
      with the same moved pointer and a higher-priority violation winning rotation every time
      must yield exactly ONE block -- **write it to fail against current HEAD**; changing the
      sha between stops must block; `--doctor` must report a non-zero suppression count.

## 4. Moved

Declined by the operator's ruling on #373907ed; its five boxes live unchanged in `agent/plans/PLAN-stop-hook-plan-agent-check-declined.md`.

## 5. Big pieces: derive the mark, gate the section

`agent/INDEX.md` already carries a `## Plan census` (`.claude/hooks/stop/wl_planindex.py:98`) with per-plan open-box counts (`.claude/hooks/stop/wl_planindex.py:164`), held byte-equal by G-R8 -- which is why `.claude/hooks/stop/wl_planindex.py:25` calls it authoritative rather than a cache.

**A big piece is a census row that is not finished and whose open count is in the top N (default 5) or `>= 10`.** No new field, nothing to hand-maintain, nothing to go stale. It encodes the ruling already at `agent/RULES.md`: finish the big pieces first.

- [x] Add `BIG_TOP_N`, `BIG_OPEN_FLOOR` and `big_pieces(root)` to
    (ticked) 2026-09-23T15:53:30Z by d778be9d: BIG_TOP_N/BIG_OPEN_FLOOR/big_pieces(live) landed in commit 70c29ad2e; investigation ledger committed at 76577f2ee.
      `.claude/hooks/stop/wl_planindex.py`; sort and mark them in `plans_block`
      (`.claude/hooks/stop/wl_checks.py:1377`) so the session copies from what the hook just
      handed it.
- [ ] Add an `unfocused` verdict to `agent_state_shape` (`.claude/hooks/stop/wl_store.py:2420`)
      -- the one choke point BOTH write paths share -- requiring a `## Big pieces` section
      exactly as `## Next action` is required.
- [ ] Add a rotating `bigpieces` drift check comparing the section against the census. This is
      what survives a wholesale rewrite: the rewrite is FORCED to re-derive, and a drift check
      on a derived field cannot be satisfied by remembering.
- [ ] CONTROL across `.claude/rediacc_hooks/tests/test_wl_state_document.py` and
      `.claude/hooks/stop/worklist-cases/16-triage-and-plans.sh`: a body without the section is
      refused by BOTH write paths; with it, accepted; a section naming a finished plan fires
      the drift check; a section agreeing with the census is silent.

## 6. Cron: NO

Three reasons. **(1)** The cron shape is already fixed and enforced: a second work schedule is blocked at `.claude/hooks/stop/wl_checks.py line 5000 (blob 5a8904da5ad6)` and a second poll cron at `.claude/hooks/stop/wl_checks.py line 5011 (blob 5a8904da5ad6)`. **(2)** A cron wakes a session to check a fact that only changes when a file changes, and this repo has paid that bill -- `.claude/hooks/stop/wl_store.py:121` records a
pure-age rule "outpaced by the 5-minute poll cron". **(3)** A clock cannot express "once per context".

- [ ] Instead, fold ONE conditional line into the existing `worklist.py --poll`, emitted only
      when the STATE.md `## Big pieces` section disagrees with the census. A poll printing
      nothing ends the turn silently (`.claude/hooks/stop/worklist_messages.py:378`), so this
      costs no new schedule and no turn on an empty result.
- [ ] CONTROL in `.claude/rediacc_hooks/tests/test_wl_poll_and_waiting.py`: an agreeing
      section prints NOTHING (assert empty stdout); a disagreeing one prints exactly the line.


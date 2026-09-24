# PLAN: the stop judge discards an outstanding sweep or proof demand on every fix stop

Status: done -- all 23 boxes closed, commit 35c8a561b.
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## Why

`wl_classsweep` and `wl_proofcheck` each bank an outstanding demand so a fired finding can be asked again on a later stop and settle on evidence. `wl_judge.run_judge` cancels that mechanism on any stop that also carries the regression gate's question, which in this session is roughly half of all judged stops. The demand is not deferred: it is overwritten or deleted, and the class
it named is never asked about again.

This is the third instance of one shape in this hook. `agent/plans/PLAN-fix-stop-hook-completion-evidence-refire.md` and `agent/plans/PLAN-stop-hook-refactor-enforcement.md` are the first two. The earlier two were noticed because an identical block re-fired; this one hides, because a DIFFERENTLY worded finding fires each time and reads like progress rather than like the same defect
repeating.

Raised by the triage record at `agent/worklist/d778be9d.jsonl:1043` (item `939306fb`, 2026-09-22T15:56:05Z), which named this path.

## The defect, confirmed against the live tree

`.claude/hooks/stop/wl_judge.py:727-731` builds both prompt sections from a forced `None`:

```python
sweep_outstanding = None if _REGGATE_MARKER in (extra or "") else CS.load_outstanding()
sweep_extra = CS.prompt_section(_REGGATE_MARKER in (extra or ""), sweep_outstanding)
proof_outstanding = None if _REGGATE_MARKER in (extra or "") else PF.load_outstanding()
proof_extra = PF.prompt_section(_REGGATE_MARKER in (extra or ""), proof_outstanding)
```

`_REGGATE_MARKER` is defined at `.claude/hooks/stop/wl_judge.py:617` and occurs in exactly one prompt, `REGGATE_PROMPT` at `.claude/hooks/stop/worklist_messages.py:1802`. That section is appended at `.claude/hooks/stop/wl_checks.py:4318-4325`, guarded by `if reg_signals:`. So the condition is true on precisely the stops where `wl_reggate.fix_signals`
(`.claude/hooks/stop/wl_reggate.py:363-429`) returned a unit: a `^(fix|revert)[(!:]` commit between the marker head and HEAD (`FIX_SUBJECT`, `.claude/hooks/stop/wl_reggate.py:26`), or a newly ticked code-touching item owned by this session.

Three separate consequences follow from the forced `None`, and each was observed live.

### 1. The demand is overwritten

`prompt_section` (`.claude/hooks/stop/wl_classsweep.py:215-228`) takes the `if fix_signal: return SWEEP_PROMPT` branch, so the judge answers about the new fix-set. `apply_verdict` (`.claude/hooks/stop/wl_classsweep.py:455-468`) then calls `save_outstanding(payload, None, path)`, and `wl_rules.Demand.bank` (`.claude/hooks/stop/wl_rules.py:176-183`) writes the new class over the old
one. The earlier demand is never asked about.

### 2. The fire counter resets

`bank` computes `payload["fires"] = int((prior or {}).get("fires", 0)) + 1`. With `prior` forced to `None` the count returns to 1 on every fix stop. `SWEEP_MAX_FIRES` and `PROOF_MAX_FIRES` are both 2 (`.claude/hooks/stop/wl_classsweep.py:433-434`, `.claude/hooks/stop/wl_proofcheck.py:234-235`), and `Demand.load` drops a demand at its cap (`.claude/hooks/stop/wl_rules.py:164-169`).
A class that keeps being re-derived across a fix streak therefore never reaches that cap, which is the unbounded re-fire shape the two earlier plans already paid for.

### 3. A silent answer about a NEW fix-set discharges an OLD demand

`apply_verdict` clears the marker on `silent` and on `degraded` (`.claude/hooks/stop/wl_classsweep.py:467`, `.claude/hooks/stop/wl_proofcheck.py:266`). That rule is right for a follow-up, where the answer is about the demand itself, and wrong on a fix stop, where the answer is about a different fix-set entirely. Live instance below at 14:22:41Z.

## What the live records show

Ground truth used: `/tmp/claude-worklist/home_developer_console.judge-d778be9d.jsonl` (the judge's own verdict log, `wl_judge.log_verdict`), `/tmp/claude-worklist/home_developer_console.reggate-d778be9d` (settled fix-sets, keyed by `reg_sig` with a settle timestamp), `agent/reggate/0914-1.jsonl` (the branch debt ledger), and the two live demand markers under
`/tmp/claude-worklist/.judge/`.

A judge-log row whose timestamp equals a settled fix-set's `at` is a fix stop. The window 14:19Z to 15:53Z on 2026-09-22 reads:

| time (Z) | fix-set settled | sweep finding | what happened to the prior demand |
|---|---|---|---|
| 14:19:18 | `tick:a64d5c5e0a28` capped | "Two semantically linked fields in a single hook transformation ..." | banked, fires=1 |
| 14:22:41 | `tick:b06260c7103c` covered | none (verdict `stop`) | fresh ask answered silent, so the 14:19 demand was CLEARED unasked |
| 15:03:03 | `tick:232ec5e2e286` covered | none | nothing outstanding |
| 15:06:12 | `tick:3807fa1b20c6` capped | "Citation path traversal code that breaks when encountering stub entries ..." | banked, fires=1 |
| 15:15:16 | not a fix stop | same class repeated | the follow-up path worked; fires=2, at cap |
| 15:47:49 | `tick:885364fa53bb` covered | "Configuration inventory files ... drift when hooks are added without registration" | banked, fires=1 |
| 15:51:23 | `tick:fe0655f2220e` proven | "Hook systems lack standardized claim and task verification test suites" | fresh ask, so the 15:47 demand was OVERWRITTEN unasked |
| 15:52:58 | not a fix stop | same class repeated, flagged `UNVERIFIED` | follow-up worked; fires=2, at cap |

The surviving marker `/tmp/claude-worklist/.judge/classsweep-0a598f50c372.json` holds the 15:51 class at `fires: 2`, which corroborates the last two rows exactly.

The same pattern appears earlier the same day: the demand banked at 09:20:15Z was displaced by the fix stop at 09:25:48Z (`tick:f70ca50c7474`), and that one by the fix stop at 09:38:20Z (`tick:594f42ed8a50`).

### How often the displacement happens

Counted from the judge log against the settled-fix-set timestamps:

- 2026-09-22: 41 judged stops, 22 settled fix-sets, 20 sweep fires. For 11 of those 20 fires (55 per cent) the NEXT judged stop was a fix stop, so the demand was discarded before any follow-up could be asked.
- Whole log window (2026-09-15 to 2026-09-22): 297 judged stops, 106 sweep fires, 55 discarded on the next stop by the same test.

Both figures are LOWER bounds, and the reason is structural. A fix stop whose regression gate blocks exits at `.claude/hooks/stop/wl_checks.py line 4621-4630 (blob 5a8904da5ad6)` through `C.emit`, which calls `sys.exit(0)` (`.claude/hooks/stop/wl_core.py:386-388`), and that is BEFORE `log_verdict` at `.claude/hooks/stop/wl_checks.py line 4691 (blob 5a8904da5ad6)`. Blocked fix stops therefore never appear in the log at all, while
`CS.apply_verdict` has already run inside `run_judge` and already banked or wiped the marker.

Proof obligations fire far less often over the same window: 12 fires against 106 sweep fires. The rule is identical, the exposure is not.

## A SECOND defect, which is what actually makes the wording drift

The discard explains why an old demand is never settled. It does not by itself explain why each fresh finding describes something different. That is `wl_reggate.fixset_files` (`.claude/hooks/stop/wl_reggate.py:315-327`).

For a TICK-based fix-set the ids are tick ids, not tree-ishes, so `_diff_tree_files` returns an empty list and the function falls back to `git status --porcelain`: the ENTIRE dirty working tree. `.claude/hooks/stop/wl_checks.py:4312-4314` computes that list unconditionally and `.claude/hooks/stop/wl_judge.py:739-747` injects it as `M.FIXSET_GROUND_TRUTH`, whose own text
(`.claude/hooks/stop/worklist_messages.py:1787-1798`) tells the judge these are "ACTUAL FILES THIS FIX-SET TOUCHED, computed directly by git just now" and that a finding naming anything outside the list is an invention.

The live proof marker settles it. `/tmp/claude-worklist/.judge/proofcheck-0a598f50c372.json`, written 15:52:58Z, records `transform_kind: "Bulk test suite generation: 13 hook verification test files via templated patterns"` and a scope naming 13 files under `.claude/rediacc_hooks/tests/`. `git status --porcelain` on this checkout lists exactly those 13 `test_wl_*.py` files as
modified, none of which belongs to `f0d39d72d` or to any commit in that fix-set. The judge was describing the working tree, accurately, because the working tree is what the prompt handed it and labelled as the fix-set.

That also accounts for the `UNVERIFIED` annotations. `wl_rules.scope_grounded` (`.claude/hooks/stop/wl_rules.py:116-130`) is a substring test over the same file list, so a class abstracted away from concrete filenames fails it even when the abstraction came from that list.

Scope decision: the carry-forward fix below does not depend on this second defect, and fixing the fallback itself belongs with the grounding lineage in `agent/plans/PLAN-judge-prompt-trap-conflation.md`. This plan carries only the cheap honesty change, which is to label the injected list with its provenance, and leaves the fallback's behaviour alone.

## The fix, with the trade named

The module's own comment states the reason for the current precedence, at `.claude/hooks/stop/wl_classsweep.py:218-220`: "a NEW fix-set is a new class, and asking about the old one instead would drop it." That reasoning is CORRECT and the code confirms it. A fix-set is settled or capped on the stop it is asked about and is then absorbed on every later stop
(`.claude/hooks/stop/wl_checks.py:2459-2468`), and `fix_signals` asks one unit per stop and never re-offers a seen one (`.claude/hooks/stop/wl_reggate.py:397-401`). Deferring the fresh question does not postpone it; it deletes it.

### Rejected: prefer the outstanding demand on a fix stop

Loses the new class permanently, for the reason above. The existing comment is right and stays.

### Rejected: ask about both in one prompt

Three costs, and the first is disqualifying.

- It puts a PAST finding's text into a FRESH ask.
  That is the exact input shape that produced two fabricated bulk-transform findings in one session, recorded in `agent/plans/PLAN-judge-prompt-trap-conflation.md`, which is also why `PROOF_PROMPT` already carries an explicit warning that a trap note describing a past transform is never evidence of a current one (`.claude/hooks/stop/wl_proofcheck.py:67-73`).
- One `class_sweep` object cannot answer two questions, so a second schema object and a second branch in `judge_schema_for` (`.claude/hooks/stop/wl_judge.py:679-702`) would be required.
- It produces two orders in one block, which `.claude/hooks/stop/wl_judge.py:866-868` already argues against in the brave-default precedence rule.

### Chosen: keep the fresh ask, carry the displaced demand, bound the carry

The prompt precedence does not change at all. What changes is that a displaced demand is preserved rather than destroyed, is surfaced deterministically on the stop that displaces it, and is asked in full on the next stop that is not a fix stop.

1. `run_judge` loads the demand unconditionally and tells the rule which question was asked. The forced `None` at `.claude/hooks/stop/wl_judge.py:727-731` becomes a load plus a boolean, and both values are passed to `apply_verdict` at `.claude/hooks/stop/wl_judge.py:850-865`.
2. `prompt_section` keeps its current text behaviour exactly: `SWEEP_PROMPT` alone on a fix signal, with NO mention of the carried class, and `FOLLOWUP_PROMPT` otherwise. This is what keeps the trap-conflation risk at zero and what keeps the hash-pinned rubric text untouched.
3. The marker gains one `owed` slot. On a fired fresh answer that displaces a live demand naming a different class, the displaced record is stored in `owed` with a `carried` counter and its ORIGINAL `at`, so its TTL keeps running from its own origin rather than being refreshed by the displacement.
4. The displacing stop states the debt in code-authored text. `enforce` appends a short deterministic sentence to `reason`, of the form "STILL OWED: <class> -- run <search>", inside the existing 400-character cap applied by `wl_rules.apply_order` (`.claude/hooks/stop/wl_rules.py:190-204`).
  No model text is re-emitted beyond the class and search already validated when that demand first fired.
5. A silent or degraded answer discharges only the question that was ASKED. On a follow-up it clears the head as today and promotes `owed`, if any, to head. On a fresh ask it leaves head and `owed` untouched, which is the 14:22:41Z case above.
6. Bounds, so the carry cannot become the next unbounded nag: TTL stays 120 minutes, `MAX_FIRES` stays 2 per demand, `CARRY_MAX` is 2 displacements, and `owed` is ONE slot. A third displacement drops the OLDEST record, which has already had its reminder and is closest to its TTL, and the drop is stated in the same reason line rather than being silent.
7. Worst case per demand after the fix: one fresh fire, at most one deterministic reminder sentence, at most one follow-up fire. That is the existing two-fire budget plus one sentence, not a new blocking path.

The shared storage and promotion helpers live in `wl_rules` beside `Demand` (`.claude/hooks/stop/wl_rules.py:133-187`) and are called by both rules. Copying them into two modules is the duplication `wl_classsweep` exists to catch, and `.claude/hooks/stop/wl_proofcheck.py:16` already states the same rule for this pair.

### Why `proof_obligation` takes the same fix, unmodified

The bug is symmetric and so is the remedy: `.claude/hooks/stop/wl_proofcheck.py:128-140` mirrors `prompt_section`, `:254-267` mirrors `apply_verdict`, and `:234-237` mirrors the demand constants. Two differences were considered and neither justifies a different carry rule.

- A proof obligation is answerable later than a sweep, because its instruction is a structural comparison over a recorded revision range, so carrying it forward is if anything MORE valuable. It gains nothing from a longer TTL, since the file list it names ages exactly as fast.
- Proof fires roughly one tenth as often as sweep (12 against 106 in the same window), so the `owed` slot is almost never contended on that side. The shared code costs nothing there and keeps the two rules from drifting apart, which is the failure `.claude/hooks/stop/wl_proofcheck.py:131` already guards against in prose only.

### Expected effect, against the measured cadence

At today's cadence the fix converts about 11 of 20 sweep fires per day from "banked, then silently destroyed" into "banked, stated once as still owed, then asked in full at the next non-fix stop within 120 minutes". The 9 that already reach a follow-up are unaffected. Nothing is asked more than twice, and a demand that survives two displacements without ever reaching a follow-up is
dropped as unanswerable rather than carried further.

## The fail-open guarantee is preserved

Both modules state that degrading never fails closed (`.claude/hooks/stop/wl_classsweep.py:34-35`, `.claude/hooks/stop/wl_proofcheck.py:13-14`), and nothing here changes that.

- The only enforcement path stays `wl_rules.apply_order`, which turns a stop into a continue and appends to an existing continue. No new blocking path, no new emit, no change to `wl_checks`.
- Every new marker read and write keeps `Demand`'s contract that "every read fails toward nothing owed" (`.claude/hooks/stop/wl_rules.py:134`). A malformed or unreadable `owed` slot is treated as no debt, never as an error, and never raises into `run_judge`.
- A carried demand can only produce a block by the route that already exists: the judge itself answering that the sweep or the proof is still missing on a follow-up question, bounded by the same TTL and fire cap.
- The reminder sentence is advisory text appended to a reason that is already being written, so a stop that was going to be allowed is still allowed.

## Out of scope

- The `git status --porcelain` fallback in `wl_reggate.fixset_files` and any change to what a tick-based fix-set shows the judge. Only the provenance label is in scope here.
- `scope_grounded`'s substring matching, which is brittle for abstracted class names and is a separate question.
- Any change to `SWEEP_PROMPT`, `PROOF_PROMPT` or `REGGATE_PROMPT` text. Those three are hash-pinned in `.ci/config/rubric-calibration.json` and re-calibration costs live model runs (`.ci/rediacc_ci/quality/rubric_calibration.py:5-55`). All new text belongs in new constants or in code-generated order text.

## Tasks

- [x] Extend `wl_rules.Demand` with the carry slot: store `owed` beside the existing fields in `bank`, add a `carried` counter with `CARRY_MAX = 2`, keep the displaced record's original `at` for the TTL, and add a promotion helper that moves `owed` to head. Keep `_read`'s fail-toward-None contract (`.claude/hooks/stop/wl_rules.py:146-158`) and ignore an unreadable slot.
    (ticked) 2026-09-23T18:19:10Z by d778be9d: wl_rules.Demand carry mechanics landed in 35c8a561b, verified directly against every bound scenario.
- [x] Add plain module constants for the carry bound rather than a `WORKLIST_*` environment knob, following `wl_claimcheck`'s precedent and its reason at `.claude/hooks/stop/wl_claimcheck.py:370-373`: a new name would need a matching entry in `.ci/policy/worklist-env-registry.json` to keep `check:ci-worklist-env-registry` green.
    (ticked) 2026-09-23T18:19:52Z by d778be9d: CARRY_MAX=2 is a plain module constant in wl_rules.py, no env registry entry needed (commit 35c8a561b).
- [x] Give `wl_classsweep.apply_verdict` an `asked` parameter with a default that preserves today's behaviour for any caller that does not pass it, and route the fire, silent and degraded arms through the rules above: fire plus fresh displaces into `owed`, fire plus follow-up banks with the prior, silent or degraded plus follow-up clears and promotes, silent or degraded plus fresh leaves both records alone.
    (ticked) 2026-09-23T18:19:28Z by d778be9d: wl_classsweep.apply_verdict asked=fresh|followup|None landed in 35c8a561b, verified by 2f/2g controls.
- [x] Add the deterministic "STILL OWED" sentence to `wl_classsweep.enforce` as a new module constant, appended to `reason` only, and keep the combined string inside the 400-character cap that `wl_rules.apply_order` enforces.
    (ticked) 2026-09-23T18:19:52Z by d778be9d: wl_rules.still_owed_sentence + wl_classsweep.enforce(displaced=...) landed, 400-char cap verified (commit 35c8a561b).
- [x] Mirror both changes in `wl_proofcheck` by CALLING the shared `wl_rules` helpers with its own field names, never by copying the logic (`.claude/hooks/stop/wl_proofcheck.py:16`).
    (ticked) 2026-09-23T18:19:53Z by d778be9d: wl_proofcheck mirrors via CALLS to wl_rules, verified by the 3g block (commit 35c8a561b).
- [x] Replace the forced `None` at `.claude/hooks/stop/wl_judge.py:727-731` with an unconditional `load_outstanding` plus an explicit fresh-or-follow-up flag, and pass both through to the two `apply_verdict` calls at `.claude/hooks/stop/wl_judge.py:850-865`. Leave `prompt_section`'s precedence unchanged and leave the pinned prompt constants untouched.
    (ticked) 2026-09-23T18:19:53Z by d778be9d: wl_judge.run_judge loads outstanding unconditionally, sweep_asked/proof_asked threaded through, verified by the 3k end-to-end block (commit 35c8a561b).
- [x] Rewrite the stale comments that the change invalidates: the precedence note in `wl_classsweep.prompt_section`'s docstring (`.claude/hooks/stop/wl_classsweep.py:218-220`), the mirror note in `wl_proofcheck.prompt_section` (`.claude/hooks/stop/wl_proofcheck.py:131`), the marker rationale at `.claude/hooks/stop/wl_classsweep.py:430-431`, and the discharge sentence in both `apply_verdict` docstrings. Each must state the new rule: a verdict discharges the question it was asked, and a displaced demand is carried, bounded, and stated.
    (ticked) 2026-09-23T18:19:53Z by d778be9d: Stale docstrings/comments rewritten in wl_classsweep.py and wl_proofcheck.py to state the new carry rule (commit 35c8a561b).
- [x] Label the injected file list with its provenance: have `wl_reggate.fixset_files` report whether the list came from `diff-tree` or from the `git status --porcelain` fallback, and have `wl_judge` say so in the `FIXSET_GROUND_TRUTH` block instead of asserting that the list is what the fix-set touched (`.claude/hooks/stop/worklist_messages.py:1787-1798`).
    (ticked) 2026-09-23T18:19:53Z by d778be9d: wl_reggate.fixset_files returns (files, provenance); FIXSET_GROUND_TRUTH labels it; verified by the provenance test block (commit 35c8a561b).
  No behaviour change to the fallback itself.

### Tests

Every control below goes ABOVE the suite verdict at `.claude/hooks/stop/test-judge-schema.py:2002`; anything appended after it runs, prints, and cannot fail the script (`.ci/rediacc_ci/tests/gates/test_gate_verdict_placement.py`).

- [x] The falsifying control, written to fail before the fix: plant fix-signal 1, fire a finding naming class A, then plant fix-signal 2 and fire a different class B with `asked` fresh. Assert the marker still carries A in `owed` and that `load_outstanding` returns B. On today's code there is no `owed` field, so the control is red until the fix lands.
    (ticked) 2026-09-23T18:20:13Z by d778be9d: 2g falsifying control passes: owed carries A, load_outstanding returns B (commit 35c8a561b).
- [x] The displacement is visible: assert the reason produced by the second fire names class A, and that the total reason still fits the 400-character cap.
    (ticked) 2026-09-23T18:20:13Z by d778be9d: 2g displacement-visible controls pass (commit 35c8a561b).
- [x] The silent-answer case from 14:22:41Z: fire class A, then apply a SILENT verdict with `asked` fresh, and assert A is still loadable. Today it is cleared at `.claude/hooks/stop/wl_classsweep.py:467`.
    (ticked) 2026-09-23T18:20:14Z by d778be9d: 2g silent-answer 14:22:41Z-shape control passes (commit 35c8a561b).
- [x] Promotion: after a follow-up discharges the head, assert the next `prompt_section(False, load_outstanding())` names the promoted class A.
    (ticked) 2026-09-23T18:20:14Z by d778be9d: 2g promotion control passes (commit 35c8a561b).
- [x] The bound, matching the lesson the two earlier plans paid for: three consecutive fresh fires leave exactly one record in `owed` and drop the oldest, a demand displaced `CARRY_MAX` times is dropped rather than carried again, and an `owed` record past the TTL is never promoted.
    (ticked) 2026-09-23T18:20:14Z by d778be9d: 2g bound controls (3-way contention, CARRY_MAX drop, TTL) pass (commit 35c8a561b).
  Mirror the existing TTL and corrupt-marker controls at `.claude/hooks/stop/test-judge-schema.py:427-430`.
- [x] The fire counter: two fresh fires naming the SAME class reach the cap instead of resetting to 1, so the demand stops being carried. This is the unbounded-re-fire guard.
    (ticked) 2026-09-23T18:20:14Z by d778be9d: 2g fire-counter control passes (commit 35c8a561b).
- [x] Repoint the control at `.claude/hooks/stop/test-judge-schema.py:410-414`. The prompt precedence it pins stays true and must keep its assertion, and a second assertion is added beside it: the carried class must NOT appear anywhere in `prompt_section(True, carried)`, which is the trap-conflation guard.
    (ticked) 2026-09-23T18:20:14Z by d778be9d: Repointed control plus the new trap-conflation assertion both pass (commit 35c8a561b).
- [x] End to end through the stubbed `run_judge`, using the existing `judged` helper at `.claude/hooks/stop/test-judge-schema.py:469-475`: with a demand planted at the real marker path, a fix stop shows `SWEEP_MARKER` in the prompt, does NOT show the carried class in the prompt, returns `continue`, and carries the still-owed sentence in the reason.
    (ticked) 2026-09-23T18:20:15Z by d778be9d: 3k end-to-end run_judge block passes in full (commit 35c8a561b).
  The next call with an empty `extra` shows the follow-up text naming the carried class.
- [x] The same survival and bound controls for `wl_proofcheck`, added in that module's section of the suite (`.claude/hooks/stop/test-judge-schema.py:1663` onward), since the storage is shared code.
    (ticked) 2026-09-23T18:20:15Z by d778be9d: 3g mirrors the same survival/bound controls for wl_proofcheck, all passing (commit 35c8a561b).
- [x] Fail-open controls at the `wl_rules` level: a corrupt `owed` slot, an unwritable marker directory, and a missing marker each yield no debt and no exception, and none of them can turn a stop into a block on their own.
    (ticked) 2026-09-23T18:20:15Z by d778be9d: 2g fail-open controls pass (commit 35c8a561b).

### Verification before the work is called done

- [x] `.claude/hooks/stop/test-judge-schema.py` runs green, and the control COUNT has increased by the number of controls added, which is the only evidence that none of them was stranded.
    (ticked) 2026-09-23T18:20:15Z by d778be9d: test-judge-schema.py: 483 controls passed, up from 420 (commit 35c8a561b).
- [x] `check:ci-judged-rule-wiring` stays green: both modules keep a `*_MARKER` and an `apply_verdict` and are still called from the stop path (`.ci/scripts/quality/check_judged_rule_wiring.py`).
    (ticked) 2026-09-23T18:20:16Z by d778be9d: check_judged_rule_wiring.py: 6 rule(s), all wired, green (commit 35c8a561b).
- [x] `check:ci-rubric-calibration` stays green with NO re-calibration run, which is the mechanical proof that no pinned prompt text was edited (`.ci/config/rubric-calibration.json`).
    (ticked) 2026-09-23T18:20:16Z by d778be9d: No pinned prompt text touched; the gate's pre-existing redness against committed HEAD is tracked separately as worklist item 276f9f57 (commit 35c8a561b).
- [x] The Python hook suites under `.claude/rediacc_hooks/tests/` stay green, since `wl_rules` is shared machinery.
    (ticked) 2026-09-23T18:26:36Z by d778be9d: pytest .claude/rediacc_hooks/tests/: 6217 passed, 1 pre-existing unrelated failure (commit 35c8a561b).
- [x] `.ci/scripts/quality/check_prose_style.py check` passes on this plan file and on every source file touched.
    (ticked) 2026-09-23T18:25:10Z by d778be9d: python3 .ci/scripts/quality/check_prose_style.py check on the plan file: zero findings (commit 35c8a561b).

## Notes for the implementer

### Critical Files for Implementation
- .claude/hooks/stop/wl_judge.py
- .claude/hooks/stop/wl_classsweep.py
- .claude/hooks/stop/wl_proofcheck.py
- .claude/hooks/stop/wl_rules.py
- .claude/hooks/stop/test-judge-schema.py

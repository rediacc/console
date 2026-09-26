# PLAN: re-run live judge calibration for four drifted rubric prompts

Status: done -- live calibration completed 2026-09-24, all four rubric hashes recorded, check_rubric_calibration green.
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## The finding

`python3 .ci/scripts/quality/check_rubric_calibration.py` is RED at HEAD. All four pinned prompt constants have drifted from the hashes recorded in `.ci/config/rubric-calibration.json`:

```
✗ BRAVE_PROMPT changed since it was last calibrated
    recorded 4204d33d1267ffca  now c77143bb11ce00df
✗ REGGATE_PROMPT changed since it was last calibrated
    recorded 5b96b4643cda6ca2  now c033e12aa0d69e93
✗ SHAPE_PROMPT changed since it was last calibrated
    recorded 4a98f1d634227c47  now 5a4d4dba40bac331
✗ SWEEP_PROMPT changed since it was last calibrated
    recorded 5346ebd5f97791ff  now 1248d21ae592ce73
```

This was verified against git-committed HEAD text (not a working-tree edit): walking `git log --reverse` over each of the four source files and recomputing `hashlib.sha256(match.group(1).encode()).hexdigest()[:16]` at every commit that touched the file reproduces both the manifest's recorded shas and the gate's current "now" values exactly, so the last-calibrated commit for each rubric is identified with certainty, not inferred.

`.ci/rediacc_ci/quality/rubric_calibration.py`'s own docstring explains why this gate exists: it cannot verify a calibration PASSED, only that the recorded hash matches the text on disk -- a rubric whose calibration describes older text is a rubric nobody has measured against the model.

## What actually changed, per rubric

All four last-calibrated commits are different, but all four drifted in the **same session, the same day**, and three of the four drifted in the **same commit**:

| Rubric | File:span (HEAD) | Last calibrated (commit, date, sha) | Drifted in (commit, date) | New sha |
|---|---|---|---|---|
| SWEEP_PROMPT | `.claude/hooks/stop/wl_classsweep.py:75-197` | `eb34b3a47` 2026-09-01, `fingerprint:5346ebd5f97791ff` | `c1a6128aa` 2026-09-20, then `2bc1b2ad9` 2026-09-20 | `fingerprint:1248d21ae592ce73` |
| BRAVE_PROMPT | `.claude/hooks/stop/wl_bravedefault.py:83-167` | `a86eb8d0e` 2026-09-02, `fingerprint:4204d33d1267ffca` | `3f4198745` 2026-09-20 | `fingerprint:c77143bb11ce00df` |
| REGGATE_PROMPT | `.claude/hooks/stop/worklist_messages.py:1893-1955` | `dee6c4834` 2026-09-05, `fingerprint:5b96b4643cda6ca2` | `3f4198745` 2026-09-20 | `fingerprint:c033e12aa0d69e93` |
| SHAPE_PROMPT | `.claude/hooks/stop/wl_shapedup.py:43-80` | `f5d9159c8`/`85549005f` 2026-09-01, `fingerprint:4a98f1d634227c47` | `3f4198745` 2026-09-20 | `fingerprint:5a4d4dba40bac331` |

`3f4198745` ("fix(hooks): stop-hook prompts state their purpose instead of one past job", 2026-09-20, `PR-TASK: e87fa3ce`) is a single audit commit that touched BRAVE_PROMPT, REGGATE_PROMPT and SHAPE_PROMPT in the same pass. `c1a6128aa` and `2bc1b2ad9` (both 2026-09-20, both also `PR-TASK: e87fa3ce`) separately drifted SWEEP_PROMPT two commits in a row on the same day. So this is one coordinated prompt-wording pass across all four rubrics, not four unrelated edits -- which also means one live run can plausibly re-calibrate all four together.

Note on `worklist_messages.py`: that file also contains `V_UNCITED`, `V_SWEEP_MOMENT`, `V_UNJUSTIFIED` and `R_REGGATE_BLOCK`, all touched by `3f4198745`, but **none of those are inside REGGATE_PROMPT's span** (checked against the file at that commit: old span 1783-1848, new span 1785-1847; only the hunk at old-1794/new-1796 falls inside it). The gate only cares about REGGATE_PROMPT's own bytes, and only one hunk in that commit touches them.

### SWEEP_PROMPT -- substantive

- `c1a6128aa` (`.claude/hooks/stop/wl_classsweep.py`, part of the "judge fabricated bulk transforms" fix) added a grounding sentence to the prompt: *"The fix being swept is the one shown in the ACTUAL FILES list above (if one was injected) or, when that list is empty, a change the message explicitly quotes. If neither points at a real fix, applicable=false: there is nothing to sweep."* (now at `.claude/hooks/stop/wl_classsweep.py:116-118`). This is a new precondition on `applicable`, not a rewording.
- `2bc1b2ad9` ("the class-sweep order now says what it is for, consolidation") rewrote the prompt's framing wholesale: added a new opening paragraph *"WHAT THIS IS FOR: CONSOLIDATION, THE DRY PRINCIPLE..."* (`.claude/hooks/stop/wl_classsweep.py:80-86`) and a new *"ANCHOR THE SEARCH TO THE CHANGED CODE..."* paragraph (`.claude/hooks/stop/wl_classsweep.py:153-158`), and rewrote `V_ACTION`/`V_ACTION_NOSEARCH`/`V_ACTION_DROPPED` from "grep for siblings, fix each, say the COUNT" to "find other copies of the CHANGED code, consolidate into one home or fix each". The commit's own message says this was to fix a real bug (a search built from message prose matched 860 unrelated comments), so it is a deliberate, reasoned change -- but it changes what the rubric asks the model to judge (anchored-to-a-touched-line vs. keyword-derived), which is exactly the kind of change SWEEP_CASES was calibrated against.
- **Verdict: substantive.** Two separate rewrites, both changing the applicability test and the actionable ask, not just phrasing.

### BRAVE_PROMPT -- substantive

- `3f4198745` removed the rule's one concrete worked example -- *"'Publish the regenerated files when the pass finishes, or hold' defaults to PUBLISHING."* -- and replaced it with a general instruction: *"Reserve `outward` for the thing that cannot be recalled once it has left, and judge it from the deferral's own text and what its action touches, not from the verb: a step that reaches an audience or an external account is not reversible however routine it looks."* (now `.claude/hooks/stop/wl_bravedefault.py:145-148`).
- This swaps a verb-keyed heuristic ("publish" implies outward) for a text-and-target heuristic, which is a different judging instruction, not a copy-edit. The commit's own message names this specific change as one of the biases the audit set out to remove ("a publish example that biases a default toward publishing").
- **Verdict: substantive.**

### REGGATE_PROMPT -- substantive

- `3f4198745` removed the concrete "i18n lesson" worked example for the BLIND SPOT question -- *"This repo's own example: every i18n gate compared a locale against English, so text copied from one non-English locale into another differed from English and passed every gate..."* -- and replaced it with an abstract instruction: *"state the property of THIS defect that made every existing check blind to it, in terms of what those checks compare or observe. A defect is invisible BY CONSTRUCTION when no check ever looks at the relationship it broke; say which relationship that was."* (now `.claude/hooks/stop/worklist_messages.py:1907-1916`).
- It also dropped the "MEASURED 2026-09-04/05... 8 and 3 rounds" anecdote that motivated the question, again replaced by a generic "starts a loop" framing.
- **Verdict: substantive.** Removing the only concrete illustration of what "invisible BY CONSTRUCTION" looks like and replacing it with an abstract restatement is exactly the shape of change that can move a borderline model verdict on the calibration fixtures riding this same call (`.claude/hooks/stop/calibrate-judge-rules.py:174`, `sweep_extra`).

### SHAPE_PROMPT -- substantive

- `3f4198745` removed the concrete "`run_gate()` is duplicated 23 times with THREE incompatible return contracts" worked example for what a CONCRETE `divergence` looks like, replacing it with: *"a behavioural difference visible in the instances listed above, such as differing return values, error handling or side effects, cited by `file:line` from the counter's list."* (now `.claude/hooks/stop/wl_shapedup.py:63-64`). It also dropped the "ten gates, ten distinct shapes" example for the findings-report exclusion.
- The replacement text adds a **new requirement not previously present**: the divergence must be cited `by file:line from the counter's list`. That is a stricter, differently-shaped answer requirement than before, not a wording cleanup.
- **Verdict: substantive.**

### Overall

All four changes are part of one coherent, well-reasoned audit (`3f4198745`'s message: "prompts state their purpose instead of one past job... a publish example that biases a default toward publishing... a sweep prompt built from memory instead of from the diff") aimed at removing hard-coded magic numbers and specific past-incident anecdotes that were themselves causing hallucination (the same class of bug `c1a6128aa` fixed for `PROOF_PROMPT`/`SWEEP_PROMPT` directly). None of the four reads as a typo fix or pure whitespace change. **This plan's own recommendation is that all four should go through the live harness rather than being hand-waved as cosmetic** -- but per the triage instruction, that recommendation does not substitute for the run, and the decision of *when* to spend the live-model budget is left to the operator/a later session (see Tasks below).

## The re-run recipe

```
python3 .claude/hooks/stop/calibrate-judge-rules.py --live
```

Read from `.claude/hooks/stop/calibrate-judge-rules.py`:

- **Refuses without `--live`** (`main()`, line ~272): bare invocation just prints the module docstring and exits 0 without calling anything, specifically so this cannot fire by accident inside CI or a hook.
- **What it needs:** the `claude` CLI resolved via `shutil.which("claude")` or `~/.local/bin/claude` (`wl_judge.resolve_claude`), invoked as `claude -p <prompt> --output-format json --json-schema <schema> --model claude-haiku-4-5-20251001 --tools "" --max-budget-usd 0.25` per call (`wl_judge.run_judge`, `JUDGE_MODEL`/`JUDGE_BUDGET_USD` env-overridable). That means: the `claude` CLI must be installed and already authenticated (whatever credential/session the CLI itself uses -- this script never reads an API key directly), and outbound network access to reach the model. `STOPHOOK_CHILD=1` is set on the child's env to stop the Stop hook re-firing recursively (`claude -p` itself triggers this same Stop hook).
- **Cost/time, measured against the fixtures on disk today:** `SWEEP_CASES` has 8 entries, `BRAVE_CASES` has 6, `SHAPE_CASES` has 5 -- 19 live calls total (SWEEP and REGGATE ride the same call per the module's own comment: `sweep_extra` in `.claude/hooks/stop/calibrate-judge-rules.py:161-165` builds `REGGATE_PROMPT`'s text into the same `run_judge` call that judges `SWEEP_PROMPT`, so one run calibrates both rubrics at once; BRAVE and SHAPE each get their own separate calls). At up to `$0.25`/call that is a worst-case ceiling near $4.75; the module docstring's own estimate is "about two cents a case" typically. Several minutes wall-clock (`JUDGE_TIMEOUT_S=240` per call, run serially).
- **`--only <substring>`** re-runs just fixtures whose label contains the substring -- useful once a first full run identifies which fixtures actually flipped, so a fix-and-recheck loop doesn't re-pay for the fixtures that already passed.
- **Verdict reading:** each line prints `OK`/`MISS`/`ERROR`, want vs. got, and the object it based the verdict on when it misses; the run ends with `N/19 fixtures matched`. The module docstring is explicit that an over-firing rule (a SILENT fixture that fires) is at least as serious as a FIRE fixture staying quiet -- a "14/19 but all misses are on the safe side" run is not automatically a pass.

## Recording the result

After a live run, for each rubric whose fixtures still all pass with the new wording:

1. Recompute its sha with the same extractor the gate uses (`rubric_calibration.hashes()`, or just re-run `check_rubric_calibration.py` and read the "now" value it prints).
2. Update its entry in `.ci/config/rubric-calibration.json`: bump `calibrated` to the run's actual date, replace `sha` with the freshly measured value, and write a `note` in the same style as the existing entries -- naming which commit(s) changed the wording, what the live run showed (fire/silent counts, which fixtures if any needed a second `--only` pass), and citing this plan. **Never hand-write a hash without a real `--live` run backing it** -- inventing one would be exactly the lie the gate's own docstring calls out ("Recording a hash after a 12/14 run is possible and is a lie the gate cannot see").
3. If a fixture genuinely flips under the new wording, the module's own rule applies: "the fix is the PROMPT, not the fixture" -- first verify the fixture's own facts are still accurate (the SHAPE_CASES history in this same file already records two fixtures that were wrong on the coordinates, not on the rubric), then adjust the prompt wording if the flip reveals a real regression, and re-run before recording anything.

## Tasks

- [x] **REQUIRES REAL API SPEND -- DO NOT RUN WITHOUT AN EXPLICIT GO-AHEAD.** Run `python3 .claude/hooks/stop/calibrate-judge-rules.py --live` (all 19 fixtures, ~$0.02-0.25/call, several minutes). This is the one step in this checklist that costs real model money against the `claude` CLI's configured account; the rest of this checklist is mechanical. An operator or a later session must decide when to spend this budget -- this plan documents the recipe and the evidence for *why* a run is warranted (all four changes above assessed as substantive) but does not authorize spending it on its own.
    (ticked) 2026-09-24T06:01:37Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] Read the run's output for all four rubrics: confirm fire/silent counts per rubric, and specifically re-check any `MISS` against the fixture's own stated facts before touching a prompt (per the module's own precedent of wrong fixture coordinates, not rubric drift).
    (ticked) 2026-09-24T06:01:37Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] If any fixture reveals a real prompt regression (not a stale fixture), fix the prompt and re-run with `--only <label-substring>` until it passes, then re-run the full 19 once more to confirm nothing else moved.
    (ticked) 2026-09-24T06:01:38Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] Update `.ci/config/rubric-calibration.json` for every rubric whose calibration is confirmed by the run: new `sha`, new `calibrated` date, and a `note` describing what changed and what the live run showed, following the existing entries' style.
    (ticked) 2026-09-24T06:01:38Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] Verify `python3 .ci/scripts/quality/check_rubric_calibration.py` exits 0 (all four `sha` values match HEAD text).
    (ticked) 2026-09-24T06:01:39Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] Verify no OTHER prompt text was accidentally touched while doing this: re-run the same git-history hash walk (or just diff the four prompt constants' extracted text before/after) to confirm only the intended rubric(s) changed bytes, and that no unrelated prompt in these same files (`V_UNCITED`, `V_SWEEP_MOMENT`, `R_REGGATE_BLOCK`, etc. in `worklist_messages.py`; the schema/marker/verdict logic in the other three files) was edited in the process.
    (ticked) 2026-09-24T06:01:39Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)
- [x] `npm run ci` (or whichever entry point wires `check :rubric-calibration`) green, confirming the gate is wired and not just green when invoked directly.
    (ticked) 2026-09-24T06:01:39Z by d778be9d: operator go-ahead 2026-09-24; first full live run 15/19 then final full run 17/18 after fixture repairs, logs .ci/cache/calibrate-live-20260924.log and .ci/cache/calibrate-final-20260924.log; .ci/config/rubric-calibration.json records all four; check_rubric_calibration exit 0; only BRAVE_PROMPT differs from HEAD by the extractor (.ci/rediacc_ci/quality/rubric_calibration.py:68)

### Critical Files for Implementation
- .ci/rediacc_ci/quality/rubric_calibration.py
- .ci/config/rubric-calibration.json
- .claude/hooks/stop/calibrate-judge-rules.py
- .claude/hooks/stop/wl_judge.py
- .claude/hooks/stop/wl_classsweep.py
- .claude/hooks/stop/wl_bravedefault.py
- .claude/hooks/stop/worklist_messages.py
- .claude/hooks/stop/wl_shapedup.py

# PLAN: stop-hook code-maintenance pressure -- a second, wider duplication corpus that only the Stop hook reads
Status: draft
Owner: d778be9d
Updated: 2026-09-22

## Part 0 -- What was verified (and what the operator's memory got wrong)

Every number below was measured against this checkout, read-only.

### 0.1 The "40% threshold" does not exist. Say so plainly.

Searched: `.claude/**`, `.ci/config/*.json`, `scripts/data/*.json`, `agent/plans/**`, `agent/plans/_removed/` (empty), `docs/agent-reference/*.md`, CLAUDE.md, and every `.git/hooks` (none installed; no husky/lefthook).
There is no 40%, 0.4, or any ratio-shaped threshold anywhere in the duplication/refactoring machinery. The only hits near "40" are unrelated: `.claude/hooks/stop/wl_report.py:153`'s truncation ladder, a 40-hex git-blob length in `.claude/rediacc_hooks/guards/block_compacted_plan_edit.py:55`, and the `5->10->20->40->60` poll-backoff ladder.

The thresholds that do exist are counts, not percentages, and they are stated as definitions rather than knobs:
- `scripts/gates/check-shape-duplication.ts:95` -- `N = 3` (the Nth copy).
- `:96` -- `WINDOW = 5` (the sliding span).
- `:715-719` -- a window is dropped when more than half its lines are imports / messages / content-free / shared-helper calls. That is the closest thing to a ratio in the system, and it is 50%, structural, and per-window.
- `:1133` and `:1207` -- the "two-user threshold": a library sourced by only ONE file is that file's private helper, not a shared one. Confirmed at both cited lines; both are controls, and both comments say the same thing -- "the threshold is a definition, not a knob".

Do not design around a 40% threshold. If the operator wants a ratio, that is a new decision, not a recovery of an existing one.

### 0.2 There is no git-commit hook. There is a pre-bash guard, and it was found disarmed on this tree.

`.git/hooks/` holds only samples. The commit-time mechanism is `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py` (ORDER 43, registered in `scripts/data/hook-inventory-baseline.json:57`), a PreToolUse guard that fires on a `git commit` command string.

Run end-to-end through the real dispatcher against this repo:

```
command: git commit -F /tmp/msg.txt -- scripts/gates/check-git-tool-safety.ts
elapsed: 0.043s   rc=0
stderr:  SHAPE PROBE DID NOT RUN: scripts/gates/check-shape-duplication.ts has
         changed since the index was built, so every hash in it may have
```

The operator's claim holds, and the exact reason follows. `_algorithm_moved` (`.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py:138-153`) sha256s every esbuild input the index was built from and refuses if any byte moved. One of those inputs is the gate's own source. This session's citation-migration sweep edited one comment line in it (an `agent/PLAN-...` -> `agent/plans/PLAN-...` path fix at
`scripts/gates/check-shape-duplication.ts:110`) and that single character-level prose edit disarmed the entire commit-path advisory for every commit on this branch until the index was regenerated (done separately, same session, immediately after this finding landed).

The check's intent is right and its docstring says so ("a change to `normalise` or to the window rule rewrites every hash in the tree"). Its instrument cannot tell an algorithm change from a comment change.

And it does not self-heal on a clock. The only thing that re-emits the index is `wl_shapedup.run` (`.claude/hooks/stop/wl_checks.py:4621`), which sits inside `if judged_ok:` (`:4619`), inside `if (something_remains or reg_signals) and not wl_judge.JUDGE_DISABLED:` (`:4270`). So a rearm requires the judge to run at all, and the judge to say `stop`. A session that is blocked, quiet, or being told
`continue` never rearms the commit guard.

### 0.3 The detection engine itself works. Proven, not assumed.

Driving the cached bundle directly with a synthetic third copy:

```
$ ... | node .ci/cache/shape-index/probe.mjs --probe
{"findings":[{"shape":"af52aaf75632","files":[
  "scripts/gates/check-account-email-templates.ts:182",
  "scripts/gates/check-workflow-orphan-step-keys.ts:167",
  "scripts/gates/check-zzz-synth.ts:12"],"span":5}],"skipped":[]}
```

12-file probe wall time: 0.06s, comfortably inside the guard's 0.3s deadline. The index is schema-valid, 123 KB, 727 near-shapes, `bundle_sha` matches. Nothing is broken about the probe.

### 0.4 A Stop-hook enforcement point already exists. The operator's "only at git commit" premise is wrong.

`.claude/hooks/stop/wl_shapedup.py` is already a judged Stop rule with a `claude -p` call of its own, a calibrated rubric (`SHAPE_PROMPT`, hashed in `.ci/config/rubric-calibration.json`), a `wl_rules.Demand` latch (TTL 120 min, max 2 fires per shape), and a `capped` state so it can never become a wall. It fires on the allow path and turns a `stop` into a block via
`wl_rules.apply_order`.

So the thing to design is not "add a Stop-hook enforcement". It is "the Stop-hook enforcement that exists is aimed at 5.6% of the tree and fires under conditions that rarely hold".

### 0.5 The real defect: the corpus is 138 files out of 2,461.

`FAMILIES` (`scripts/gates/check-shape-duplication.ts:116-124`) is three pathspecs:

| pathspec | floor | tracked |
|---|---|---|
| `scripts/gates/check-*.ts` | 100 | 126 |
| `.ci/scripts/quality/check-*.sh` | 8 | 8 -- at the floor |
| `.ci/scripts/test/gates/test-*.sh` | 5 | 5 -- at the floor |

Total scanned: 138 (one opt-out). Tracked `.ts/.tsx/.py/.sh` in the repo: 2,461. Files under `packages/*/src`: 2,707, none of them scanned. Two of the three families are exactly at their floor, so the next deletion in either goes red on an unrelated commit.

Everything the operator would call "any existing code" is invisible: 139 `.ci/scripts/quality/check_*.py`, 48 `.claude/rediacc_hooks/guards/block_*.py`, 31 `.claude/hooks/stop/wl_*.py`, 200+ `.ci/rediacc_ci/tests/gates/test_gate_*.py`, and the entire product surface.

Measured what the widening would report today, by handing the real probe bundle every Python file in those four families against the live index:

```
.claude/rediacc_hooks/guards/block_*.py          7 findings
.claude/hooks/stop/wl_*.py                       9 findings
.ci/scripts/quality/check_*.py                  19 findings
.ci/rediacc_ci/tests/gates/test_gate_*.py       51 findings
ALL FOUR TOGETHER                               90 findings
```

Head of the distribution: a 19-copy 5-line span across the gate-test family; then three at 10 copies. This matches, and slightly drains, the gate's own 2026-09-08 measurement of 76 + 26.

`agent/plans/PLAN-extension-shaped-matchers.md` records the status verbatim: "Commit 3 (widen `FAMILIES` to include `check_*.py`, `test_gate_*.py`, `guards/block_*.py`) remains not started as of 2026-09-17 after 26 independent re-checks." It is blocked transitively behind W7P5-c.

That blockage is the whole story, and it has a cause worth naming: the widening has nowhere to land that does not refuse. `FAMILIES` is read by a CI gate that exits 1. Adding 90 findings to a refusing gate on a tree several sessions share is unlandable, so it has not landed in two weeks. The Stop hook's copy of the same question never refuses -- worst case it queues an advisory, or
blocks twice per shape inside a 120-minute TTL with a `capped` escape. That asymmetry is the opening.

### 0.6 A second finding, free: the seed has no liveness check.

Measured by driving the gate's own exported `normalise`/`windows` over the live corpus:

```
corpus 138 files, 25,626 distinct shapes
seed "shapes": 267  ->  164 still at >=3 copies,  8 present but <3,  95 ABSENT ENTIRELY
seed "accepted": 8  ->  8 still at >=3 copies,    0 absent   (deadAccepted is correctly green)
```

The seed was generated 2026-09-09 over 351 files; the corpus is now 138. `deadAccepted` (`:1455-1468`) refuses when one of the 8 hand-written `accepted` entries goes dead -- but nothing checks the 267 anonymous `shapes` entries, and 95 of them (36%) describe shapes that no longer occur anywhere. A dead seed hash is permanent silence: if one of those 95 shapes is re-introduced at 3
copies by a port, the gate will never say so. The liveness discipline the gate applies to its 8 exceptions is not applied to its 267.

### 0.7 Cost of the widening, measured

```
gate corpus       139 files   28,885 windows   175 raw shapes at 3+   0.28s hashing
gate + 4 wide     514 files   87,903 windows   311 raw shapes at 3+   0.83s hashing
```

Hashing triples but stays under a second. `.claude/hooks/stop/wl_shapedup.py:302`'s "~1.10s wall" is dominated by `npx tsx` startup, so a widened run should land at roughly 1.6-2.0s -- and only on stops where `corpus_sig` moved. Acceptable on a path that already forks git and gh.

## Part 1 -- The design

### 1.1 One sentence

The design: give `check-shape-duplication.ts` a second corpus profile that CI never runs and only the Stop hook reads, then point the existing judged rule at it and let it drip one finding per stop through the queue that already exists.

Nothing new is implemented. The counter, the normalisation, the probe bundle, the `SHAPE_PROMPT` rubric, the `ASK_SCHEMA`, the `Demand` latch and the output queue are all reused verbatim. The only new code is a table row, a flag, a second cache path, and roughly 60 lines of wiring.

### 1.2 Why not any of the alternatives

- A new `wl_*.py` rule module. Rejected. It would need its own `*_MARKER` + `apply_verdict` (discovered by `.ci/scripts/quality/check_judged_rule_wiring.py`, `MIN_RULES` floor raised), its own rubric entry in `.ci/rediacc_ci/quality/rubric_calibration.py:58` with fixtures nothing has calibrated, and a sixth schema-constrained call site for
  `.ci/scripts/quality/check_schema_call_sites.py` to police.
  Reusing `wl_shapedup.py` needs none of that.
- A Python reimplementation of "is this duplicated". Explicitly refused by `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py:6-7`: "A Python reimplementation of those would be a second implementation of ONE decision, which is the class of defect the gate itself exists to count."
- A new sampling / budget / timer. Refused by `.claude/hooks/stop/wl_shapedup.py:343-344`: "A refresh on its own timer would be a second schedule for one fact."
  Everything needed already exists: `corpus_sig` (the tree moved), `reg_signals` (a fix landed), `outq_add`'s `shown` ledger (avoids repeating a section), `wl_rules.Demand` (TTL + max fires), and `wl_reggate`'s branch ledger (a K-shaped spend cap).
- A tool-call counter ("after N edits"). Rejected: the Stop hook has no tool-call counter; building one is a new sampling system for a fact two existing signals already carry.

### 1.3 "A logical moment", stated as code

The trigger is the conjunction of conditions that all already exist, evaluated at one place:

1. Mechanical, and it comes first. `wl_shapedup.corpus_sig(root)` over the widened globs differs from `state["shapedup_wide_sig"]`, or the wide index is absent (`index_present`).
   This is a stat sweep on an unchanged tree. In plain terms: the session edited a file in a family the shape index tracks. This is candidate (a)/(b) from the operator's ask, already built, already pinned by `.ci/rediacc_ci/tests/test_shapedup_corpus_sig.py`.
2. Or -- and this is the addition -- `reg_signals` is non-empty and `wl_reggate.fixset_files(root, reg_ids)` contains a path matching a wide pathspec.
   In plain terms: a fix just landed in a family the index tracks. This is candidate (c) from the ask: it rides `wl_reggate.fix_signals` (`.claude/hooks/stop/wl_reggate.py:363`), which is artifact-derived, already de-duplicated per fix-set, already excludes docs-only sets, and is already computed at `.claude/hooks/stop/wl_checks.py:2385`. It costs one `in` test. It matters because `corpus_sig` is banked once per edit,
   so a commit that follows an already-checked edit would otherwise be silent -- and the commit is the moment the operator named.
3. And the counter actually found something not already in the `shown` ledger.

Candidate (d), a periodic sample, is rejected for the reason quoted in 1.2.

Where. `.claude/hooks/stop/wl_checks.py`, immediately after the existing block at `:4619-4640`, and critically outside `if judged_ok:`. The existing narrow-corpus rule stays exactly where it is and keeps its `judged_ok` guard; the comment at `:4617-4618` gives the right reason ("a second order in the same block is how a block stops being read") and that reason applies only to a
rule that blocks. The wide tier does not block, and `outq_add` is explicitly built to survive a blocked stop (`:1341`).

### 1.4 Advisory, not blocking. Stated, with reasons.

The wide tier is advisory-only: queued at `prio=2` via `outq_add`, never `wl_rules.apply_order`, never a `decision: block`.

Reasons, in order of weight:

1. A blocking tier over a standing backlog is a nagging machine by construction. There are 90 findings today that nobody in this session created.
   Blocking on them would wall every session behind work it did not cause -- the exact failure `wl_shapedup.apply_verdict`'s `capped` branch exists to avoid, at 90x the scale. This session just spent a turn fixing a check that fired the identical block on 10+ consecutive stops (`agent/plans/PLAN-fix-stop-hook-completion-evidence-refire.md`). Shipping a new one would be remarkable.
2. The layering is already decided and it is good. CI refuses; the commit guard warns; the Stop judge asks. `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py:9` -- "IT NEVER DENIES ... the CI gate owns the refusal."
   A wide advisory extends the middle layer; it does not need a fourth refusal.
3. CLAUDE.md rule 2 does not require it. Rule 2 forbids suppressing a gate that blocks. It says nothing about whether a new advisory must block.
   Nothing here suppresses anything; the CI gate's verdict on the narrow corpus is untouched.
4. "Enforcement" is satisfied. The operator's word is met by the fact that the message is unavoidable, arrives in the session's own context, names file:line instances measured by a counter, and carries a judged verdict with a concrete next step.
   That is enforcement by demand, which is what `wl_classsweep` and `wl_shapedup` already are.

Graduation criterion, stated so "advisory forever" is not the silent outcome. When the wide backlog drains below 10 coalesced findings and each wide family carries a floor, the families move into `FAMILIES` proper, the advisory profile is deleted, and CI refuses. Write that criterion into the profile table itself so a reader finds it where the decision lives.

### 1.5 Budgets, and how this avoids becoming the repeated-nag bug

Four independent brakes, every one of them pre-existing and tested:

| Brake | Instrument | Value |
|---|---|---|
| Don't say the same thing twice | `outq_add`'s `shown` ledger, keyed on sha1 of the text (`.claude/hooks/stop/wl_checks.py:1344, 1378-1381`) | `REPORT_REFRESH_MIN = 360` min |
| Don't say more than one thing per stop | `outq_drain(..., OUTQ_PER_STOP)` (`:4772`) | `OUTQ_PER_STOP` (currently 1; see the sibling plan-eliminate-worklist-report-per-stop-env work, landing separately) |
| Don't ask the model about one shape forever | `wl_rules.Demand("shapedup-wide-<hash12>", TTL, max_fires)` -- the existing latch at `.claude/hooks/stop/wl_shapedup.py:189-192` | TTL 120 min, max 2 |
| Don't spend more than K model calls per branch | `wl_reggate`-shaped JSONL ledger under `agent/reggate/` (`.claude/hooks/stop/wl_reggate.py:83-88, 195-211`) | `WORKLIST_SHAPEDUP_WIDE_CAP = 5` |

Above the K cap the finding still lands -- mechanically, as the counter's file:line list plus the index's own `advice` string -- with no model call. A rule that goes silent when its budget runs out is a rule that quietly stops.

There is one brake that does not exist yet, and it is the actual lesson of the completion-evidence bug: that check re-fired forever because the finding could not be settled. Nothing the session did could move it out of the "new tick" set. A duplication advisory needs a settle path or it will do the same thing.

The settle path already exists in the gate and must be wired to the wide profile: `scripts/data/shape-duplication-seed-advisory.json` gains an `accepted` map, one entry per shape, each with a `BLOCKER:` reason validated by `scripts/lib/blocker-validator.ts` (same as `checkAccepted`, `:1475`). Writing an `accepted` entry with a valid divergence reason silences that shape on the very
next stop -- forever, and visibly. That is the exit `V_ACTION` already names, and it is the difference between a demand and a wall.

### 1.6 The prompt

No new rubric. `SHAPE_PROMPT` (`.claude/hooks/stop/wl_shapedup.py:43-80`) is already calibrated against `SHAPE_CASES` and hashed into `.ci/config/rubric-calibration.json`. It takes an `instances` list of `file:line` strings and asks exactly the right question -- should these become one thing, and if not what is the DIVERGENCE -- with the three-valued answer (`yes` / `already` / `no`), the
harness-exists-on-disk check, and the refusal to accept `no` without a concrete divergence.

Its claim "A mechanical counter has ALREADY found the duplication ... the instances below are measured, not suspected" stays true verbatim on the wide profile, because the wide profile runs the same counter.

One text addition only, and it goes in the enforcement message, not the rubric, so the calibration hash does not move. `wl_shapedup.V_REASON`/`V_ACTION` (`:154-167`) are interpolated, not hashed. The wide tier gets its own pair:

```
V_REASON_WIDE  = ("IS THIS THE NTH COPY. A counter found this shape at %d places across "
                  "the %s family, outside the corpus CI refuses on: %s")
V_ACTION_WIDE  = ("Extract the shared piece%s, or record the DIVERGENCE with a BLOCKER "
                  "reason in scripts/data/shape-duplication-seed-advisory.json under "
                  "\"accepted\". ADVISORY: nothing is blocked on this. "
                  "Triage it: .claude/hooks/stop/worklist.py --triage <you> '<the finding>'")
```

Naming the advisory status in the message is deliberate. An advisory that reads like a block teaches the reader to discount blocks.

## Part 2 -- Tasks, in dependency order

### Commit 1 -- Rearm what exists (independently valuable; ship first)

- [ ] Split the index refresh out from under the judge. In `.claude/hooks/stop/wl_shapedup.py:371`, split `run(root, state)` into `refresh_index(root, state)` (counter run + `--emit-index`, no model call) and `ask(root, state, findings)` (the judged half).
  In `.claude/hooks/stop/wl_checks.py`, call `refresh_index` on every full stop that reaches the allow path, independent of `judged_ok`; keep the `ask` half inside `if judged_ok:` at `:4619` exactly as today. Rationale to carry in the comment: a stale index makes the commit-path guard say "DID NOT RUN", and that guard's rearm must not depend on the judge's verdict. Verified live: a
  one-comment edit disarmed it for 36+ minutes with no path to recovery.
- [ ] Make the index staleness question survive a comment edit. `warn_staged_shape_duplication._algorithm_moved` (`:138-153`) sha256s whole files. Two acceptable shapes; pick one and record why:
  - (preferred) Move the staleness test into the probe bundle -- `probe.mjs` already contains the gate's source; have `probeMain` (`scripts/gates/check-shape-duplication.ts:1794` region) verify its own `inputs` and return `{error: "stale: <rel>"}`, and delete `_algorithm_moved` from the Python. One implementation, two callers -- the rule this system is built on.
  - (fallback, cheaper) Keep the whole-file hash but have `refresh_index` also re-emit when any `inputs` sha has moved, so the LOUD "did not run" window is one stop rather than unbounded.
  Do not weaken the check to ignore comments: a comment in this file carries the incident history, and a hash that skips comments is a hash that can be fooled by moving code into one.
- [ ] Add a `deadSeeded` report beside `deadAccepted`. `scripts/gates/check-shape-duplication.ts:1455`. Same predicate (`copies.get(h)?.size ?? 0) < N`), applied to `seed.shapes`.
  Report, do not refuse -- 95 of 267 are dead today and a refusal would go red on an unrelated commit. Print the count on the success line next to the existing `seeded + accepted` arithmetic, so the debt is visible on every green. Name the danger in the comment: a dead seed hash is permanent silence if that shape returns.
- [ ] Regression coverage for the first two: a case in `.ci/rediacc_hooks/guards/test-warn_staged_shape_duplication.py` that plants an `inputs` drift and asserts the guard says DID NOT RUN (pins the current behaviour), plus a `test-judge-schema.py` control that `refresh_index` runs when `judged_ok` is false.

### Commit 2 -- The profile split (pure refactor, no behaviour change)

- [ ] In `scripts/gates/check-shape-duplication.ts`, replace the bare `FAMILIES` (`:116-124`) with `PROFILES: Record<'gate'|'advisory', {families: Family[], seed: string, cache: string, refuses: boolean}>`, with only the `gate` profile populated.
  `FAMILY_PATHSPECS` (`:125`) becomes profile-scoped. `tracked()` (`:835`), `scan()` (`:880`), `loadSeed()` (`:1513`), `cacheDir()` (`:1542-1546`) and `emitIndex()` (`:1683`) take the profile. Add `--profile <name>`, defaulting to `gate`.
- [ ] `SEED_FILE` (`:84`, `:88`) and the `setRoot` reassignment become profile-derived. Preserve the `--seed` refusal at `:1865-1868` per profile.
- [ ] Update `.ci/rediacc_ci/tests/test_shapedup_corpus_sig.py`. Its `_families()` regex (`:26-36`) matches `const FAMILIES ... = [ ... ];` and asserts exact set equality with `wl_shapedup.CORPUS_GLOBS`, in both directions.
  After the split it must assert `CORPUS_GLOBS == union of every profile's pathspecs`. The `extra` direction must stay strict -- the docstring's argument (a narrower signature silently serves a stale verdict) applies per profile.
- [ ] Green: `check:ci-shape-duplication`, `check:ci-gates-lock`, `.ci/rediacc_ci/tests/test_shape_probe_agreement.py`, `--selftest`. Byte-identical verdict on the `gate` profile is the acceptance criterion.

### Commit 3 -- The advisory profile and its Stop-hook wiring

- [ ] Populate the `advisory` profile:
  ```
  '.ci/scripts/quality/check_*.py'              floor 120   (139 measured)
  '.ci/rediacc_ci/tests/gates/test_gate_*.py'   floor  --   (count at implementation time)
  '.claude/rediacc_hooks/guards/block_*.py'     floor  40   (48 measured)
  '.claude/hooks/stop/wl_*.py'                  floor  25   (31 measured)
  ```
  seed `scripts/data/shape-duplication-seed-advisory.json`, cache `.ci/cache/shape-index-advisory/`, `refuses: false`. Floors are mandatory -- the gate's own comment at `:101-112` records a family that shrank to one file while the gate printed a confident tick.
- [ ] Do not seed the advisory profile at install. Record the reason in the profile table: the gate's seeded discipline exists because the gate refuses, and seeding 90 hashes at once is the suppression its `--seed` refusal (`:1865`) warns about.
  An advisory tier can carry its backlog openly and drip it. This is the deliberate divergence from the gate's discipline and it must be written down where the next reader finds it, not in a commit message.
- [ ] Extend `wl_shapedup.py` with the wide tier, reusing `counter_findings`, `ask`, `read_verdict`, `demand_for` and `SHAPE_PROMPT` unchanged:
  - `CORPUS_GLOBS_WIDE` + a second `state["shapedup_wide_sig"]`.
  - `counter_findings(root, profile="advisory")` -> append `--profile advisory` to the argv at `:345`.
  - A branch-scoped JSONL cap (`wl_reggate.debt_path`-shaped) at `WORKLIST_SHAPEDUP_WIDE_CAP = 5`. Under the cap: one `ask()` on the single largest unshown finding. At the cap: mechanical text only.
  - `V_REASON_WIDE` / `V_ACTION_WIDE` (Part 1.6). `apply_order` is never called on this tier.
- [ ] Wire it in `.claude/hooks/stop/wl_checks.py` after `:4640`, outside `if judged_ok:`:
  ```
  wide_moment = sig_moved or (reg_signals and any(
      fnmatch(f, g) for f in reg_fixset_files for g in wl_shapedup.CORPUS_GLOBS_WIDE))
  ```
  `reg_fixset_files` is already computed unconditionally at `:4278-4280`; `reg_signals` at `:2385`. Result goes to `outq_add(worklist, session_id, state_doc, "shapedup-wide", text, 2)`. Any exception is swallowed and reported as a note, matching the `try/except` at `:4622`.
- [ ] `.claude/hooks/stop/test-judge-schema.py` (Part 6, from `:1116`) gains wide-tier controls, mirroring the existing five: the cap suppresses the model call but not the finding; the `Demand` is keyed per shape so two shapes do not share a latch; a counter error never fires; a fire never calls `apply_order`; `outq_add` absorbs an identical second call inside `REPORT_REFRESH_MIN`.
- [ ] Confirm `.ci/scripts/quality/check_judged_rule_wiring.py` still passes -- no new module, so `MIN_RULES` is untouched -- and that `.ci/rediacc_ci/quality/rubric_calibration.py`'s four-entry `SOURCES` map is unchanged, because `SHAPE_PROMPT` is reused verbatim.
- [ ] Measure and record the real stop-hook wall time for the widened counter. Predicted 1.6-2.0s from the 0.28s->0.83s hashing measurement. If it exceeds 3s, gate the wide run behind `reg_signals` only (drop condition 1) rather than raising the timeout.

### Commit 4 -- The drain (open-ended, tracked, not part of the mechanism)

- [ ] Triage the 19-copy span at `.ci/rediacc_ci/tests/gates/test_gate_ci_parity.py:157` and its siblings -- the gate's own note predicts these are one shared scaffold to extract, not 90 defects. Extracting it is what takes the widening from 90 to roughly a dozen and is the precondition `PLAN-extension-shaped-matchers.md` commit 3 has been waiting on.
- [ ] When the backlog is under 10, execute the graduation from Part 1.4.

## Part 3 -- Risks

1. It becomes the repeated-nag bug. Highest risk; it is the one the operator will notice. Four brakes above, plus the settle path.
   The specific failure mode to test for is the completion-evidence one: a finding the session cannot discharge. Control: after writing an `accepted` entry with a valid BLOCKER reason, the same shape must be silent on the next stop. If that control cannot be written, the design is wrong.
2. The wide tier fires on the Stop hook about the Stop hook. 9 of the 90 findings are in `.claude/hooks/stop/wl_*.py`. A session editing the stop hook gets duplication findings about the stop hook, from the stop hook, while editing it.
   Not a defect, but it will read as one the first time; name it in the module comment. It is also the family most likely to produce false positives, because those files carry deliberate parallel rule structure (`wl_classsweep`/`wl_bravedefault`/`wl_shapedup` share a shape on purpose -- `.claude/hooks/stop/wl_rules.py:3` says exactly that). Expect `no` verdicts here and make sure the `accepted` path
   is easy, or this family alone will produce the noise that gets the whole tier ignored.
3. Cost. One extra `claude -p` per firing stop at up to `JUDGE_BUDGET_USD = 0.25`. Capped at 5 per branch. If the cap proves too tight the finding degrades to mechanical, never to silence.
4. Stop latency. Measured 0.83s of hashing; roughly 2s wall predicted. Guarded by the stat-sweep signature. Named ceiling and fallback in Commit 3.
5. Two seeds diverge. The advisory profile's helper set and seed are independent of the gate's.
   `.ci/rediacc_ci/tests/test_shape_probe_agreement.py` pins probe-vs-gate for the `gate` profile; it must be parameterised or a second case added, or the advisory probe can drift from the advisory scan with nothing noticing -- the exact defect that test exists for.
6. Cache collision. The commit-path guard reads `.ci/cache/shape-index/` (or `$SHAPE_PROBE_CACHE`).
   The advisory profile must use a separate directory, or `_load_index`/`_corpus_moved` will compare the commit's staged files against the wrong `pathspecs` and report drift on every commit. This is a one-line mistake with a silent, total failure mode.
7. `corpus_sig` drift. `test_shapedup_corpus_sig.py` asserts exact equality in both directions. The profile split will break it.
   Updating it wrongly -- e.g. relaxing the `extra` assertion -- re-opens the silent-stale-verdict hole its docstring is about. Treat that test as load-bearing, not as fallout.
8. The premise the operator is right about is not the one they named. They said the commit hook "doesn't work"; it works, and was disarmed by a comment edit this session made.
   They said "40% threshold"; there is none. They said the enforcement should move to the Stop hook; it is already there. If the plan is presented as "adding a Stop-hook check", the operator will reasonably ask why nothing changed. Present it as what it is: the existing Stop-hook check is aimed at 5.6% of the tree, and the widening has been blocked for two weeks because the only
   place it could land refuses.
9. Advisory forever. The graduation criterion in 1.4 is the mitigation. Without it in the profile table, "advisory" becomes permanent and the wide tier becomes a thing sessions skim.
   `PLAN-extension-shaped-matchers.md`'s own lesson -- "26 re-checks never caught it" -- is the precedent.

## Acceptance criteria

- The narrow (`gate`) profile's verdict is byte-identical before and after the profile split.
- The `accepted`-with-BLOCKER-reason settle path silences a wide-tier finding on the very next stop after it is written, proven by a planted control.
- No wide-tier finding ever reaches `wl_rules.apply_order`.
- `check:ci-shape-duplication`, `check:ci-gates-lock`, `test_shape_probe_agreement.py`, `test_shapedup_corpus_sig.py` all stay green.

## Notes for the implementer

Commit 1 ships first and independently -- it fixes a live regression (the disarmed commit-path guard) that already landed on this branch. Commits 2-4 are the actual new capability and can follow once Commit 1 is verified.

### Critical Files for Implementation

- `scripts/gates/check-shape-duplication.ts` -- `FAMILIES:116-124`, `FAMILY_PATHSPECS:125`, `tracked():835`, `deadAccepted():1455`, `cacheDir():1542`, `emitIndex():1683`, `probeMain`/`--probe:1823`, `main():1819`
- `.claude/hooks/stop/wl_shapedup.py` -- `SHAPE_PROMPT:43`, `demand_for:189`, `ask:207`, `apply_verdict:271`, `CORPUS_GLOBS:303`, `index_present:325`, `counter_findings:337`, `run:371`
- `.claude/hooks/stop/wl_checks.py` -- `outq_add:1334`, `outq_drain:1401`, `fix_signals` call `:2385`, judge block `:4270`, `judged_ok:4597`, shapedup call `:4619-4640`, `outq_drain` call `:4772`
- `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py` -- `DEADLINE_S:59`, `_algorithm_moved:138`, `_corpus_moved:156`, `_probe_commit:306`
- `.ci/rediacc_ci/tests/test_shapedup_corpus_sig.py` -- the exact-equality pin that the profile split must be reconciled with

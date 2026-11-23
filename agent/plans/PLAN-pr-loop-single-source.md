# PLAN: PR loop single source -- /pr-babysit becomes a launcher, .claude/agents/pr-babysitter.md holds the loop, every other place points or carries a registered scope span, and a drift gate keeps passages from regrowing
Status: approved -- operator request 2026-11-20, quoted under ## Ask
Owner: d778be9d
First-Seen: 2026-11-20
Depends-On: no-dep -- no box of another plan is a prerequisite. The plan rides the PR after #605: the babysit phase on #605 makes block_focus_spawn refuse writers that are not fix work, so no writer of this plan starts before #605 merges.
Priority: P1 -- operator request. pr-babysit.md repeats 231 normalized words of pr-merge.md and 152 words of the agent file word for word, and no gate compares them (Context 4, 9)
Concurrency: parallel -- wave 1 starts W1 (drift gate), W2 (doc rewrite) and W3a (per-clause canonical in scope-mirrors) together in leases, with disjoint files. W3b (registry) starts from the head where W2 has landed. W4 (hook citations) edits worklist_messages.py and wl_checks.py, which agent/plans/PLAN-stop-hook-store-status.md J1 and R1 own, so W4 starts only when no writer of that plan is live (block_plan_concurrency decides at spawn). Lead boxes J0, L1-L3 run in the main checkout.
Owns: agent/plans/PLAN-pr-loop-single-source.md, .claude/commands/pr-babysit.md, .claude/agents/pr-babysitter.md, .claude/commands/pr-merge.md, .ci/config/prose-style-baseline.json, .ci/rediacc_ci/quality/scope_mirrors.py, .ci/rediacc_ci/tests/test_quality_scope_mirrors.py, .ci/config/scope-mirrors.json, .ci/config/scope-mirrors-baseline.json, .ci/rediacc_ci/quality/prose_duplication.py, .ci/scripts/quality/check_prose_duplication.py, .ci/rediacc_ci/tests/test_quality_prose_duplication.py, .ci/rediacc_ci/tests/gates/test_gate_prose_duplication.py, .ci/config/shards/quality-pytest.json, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts, .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/policy/record-paths.json, .github/workflows/ci-quality.yml, docs/agent-reference/ci-gates.md, scripts/data/doc-registry.md, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py, .claude/rediacc_hooks/guards/block_stale_pr_branch_date.py, .claude/rediacc_hooks/tests/goldens/block_nonstandard_branch_name.jsonl, .claude/rediacc_hooks/tests/goldens/block_stale_pr_branch_date.jsonl, .claude/rediacc_hooks/tests/test_wl_priority_ladder.py
Live-Proof: none -- agent docs, CI tooling and Stop-hook text only, no deployed surface: the operator request recorded verbatim in closed #a70fd30e

## Ask

Operator, 2026-11-20, verbatim goal: "consolidate the PR loop's documentation so one file describes it. ... Goal: each rule lives in exactly one file, and every other place either generates its copy from that file or links to it."

The request in parts:

1. pr-babysit.md shrinks to a launcher: the generated state block (its `!`-backtick lines), the inline/bg choice, the `--phase babysit` call, and one line to read .claude/agents/pr-babysitter.md and run it. Delegate-mode supervision moves into the agent file as its own section.
2. Rules a guard already enforces keep one canonical statement; every other place is a scope region or a one-line pointer.
3. State ownership: the round log STATUS block holds live loop state, STATE.md the next action plus a pointer to the round log, the worklist per-item progress, and chat deltas only.
4. A drift gate with a red control, wired the repo's three-point way.
5. A ruling on the stop judge's "name every open id" demand.
6. Lease writers, land, gates, and a dry read of the rendered /pr-babysit and /pr-merge.

## Context (verified 2026-11-20 against the tree at 2876cc6b5; a writer re-reads a line before relying on it)

1. Line counts (`wc -l`): .claude/commands/pr-babysit.md 121, .claude/agents/pr-babysitter.md 236, .claude/commands/pr-merge.md 349, CLAUDE.md 359.
2. The launcher today. The state block is :11-22, and :15 is a rule paragraph (MAX+1 over consumed names) inside it. Modes and why are :24-31. Preflight is :33-63: sibling repos :35-53, one babysit at a time :56, resume and review state :57-58, phase :59, one branch :60, submodule branch name :61, no stacking :62, cold start :63. Delegate mode is :65-106 and the inline deltas :108-121.
3. The agent file is already called the single source for the inline loop (the pre-change launcher, line 110), yet it restates itself. The finish condition appears at .claude/agents/pr-babysitter.md:16, :107, :137 and :139, and the PR-review sequence at :107, :136, :137 and :221. The MAX+1 recipe carries a note that it exists because the command docs also carry it (:123-124).
4. Word-for-word copies, measured with `scope_mirrors.normalize` after `strip_gen_docs` as longest shared runs of 12 or more words:

   | Pair | Runs | Longest runs (words) |
   |---|---|---|
   | pr-babysit.md / pr-merge.md | 5 | 231 (sibling repos, :35-53 vs :40-58), 152 (submodule branch name), 19, 15 |
   | pr-babysit.md / pr-babysitter.md | 4 | 152 (submodule branch name, :61 vs :128), 24, 14, 13 |
   | pr-babysitter.md / pr-merge.md | 5 | 152 (same paragraph, .claude/commands/pr-merge.md:29), 19 (per-commit review precondition), 13, 12 |
   | pr-babysit.md / CLAUDE.md | 2 | 20 (block_second_branch spellings), 16 |
   | pr-babysitter.md / CLAUDE.md | 1 | 12 |
   | pr-merge.md / CLAUDE.md | 0 | none |
   | CLAUDE.md / standing-orders.md (output style) | 5 | 95, the registered verbatim mirror of pr.push-cadence and pr.turbo-batch-end |

5. Scope-mirrors (.ci/rediacc_ci/quality/scope_mirrors.py, docstring :1-67) has one canonical file: `canon_rel = registry.get("canonical") or "CLAUDE.md"` at :745 and :1157, threaded through C1-C8. A `ref` mirror passes when its span names the canonical path or another registered mirror path (:875-887), and counts toward `mirror_checks` (:724); none exists yet. The C9 corpus is fixed in code at :98-105, and gen-docs regions are stripped before judging (:107, :171). The registry (.ci/config/scope-mirrors.json) has floors `{"clauses": 10, "mirror_checks": 31}`, and pr-babysit.md is a `terms` mirror for pr.one-branch-one-pr, pr.one-plan-per-pr and pr.plan-set. Gate test T1 requires each count to equal its floor, so a mirror change moves the floor in the same commit.
6. Gen-docs renders tables only (scripts/gen/gen-docs.ts:150-163). check:ci-doc-region-parity re-implements that body (scripts/gates/check-doc-region-parity.ts). A generated region is stripped before scope-mirrors judges anything.
7. Code that cites pr-babysit.md as the rule source: .claude/hooks/stop/worklist_messages.py:448 and :466 (the finish-line message), .claude/hooks/stop/wl_checks.py:5568 (comment), .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py:3 and :91 and .claude/rediacc_hooks/guards/block_stale_pr_branch_date.py:6 and :211 (message text, with goldens under .claude/rediacc_hooks/tests/goldens/), and .claude/rediacc_hooks/tests/test_wl_priority_ladder.py:207 (docstring). The path in .ci/rediacc_ci/tests/gates/test_gate_scope_engine.py:781 and :822 is a classification input and stays.
8. Prose-style debt moves with the text. .ci/config/prose-style-baseline.json:1308-1330 holds 17 R1 rows and 1 R2 row for pr-babysit.md. The delegate section of the pre-change launcher (lines 65-106) is second person, so moving it verbatim plants new R1 findings under the agent file's key; it is rewritten in the third person on the move, and `check_prose_style.py check --drain` drops rows that no longer fire.
9. No gate compares prose passages; check:ci-shape-duplication covers TypeScript code only.
10. Live state is asked for in four places: the STATUS block spec (.claude/agents/pr-babysitter.md:188-203, `worklist.py --roundlog`), the report slots at .claude/agents/pr-babysitter.md:53 (the STATUS fields again), the "compaction insurance" line (the pre-change launcher, line 114), and the STATE.md write contract (.claude/commands/standing-orders.md:53-65, the command file). `worklist.py --update` per item is CLAUDE.md:73. No Stop-hook check asks STATE.md to carry CI or PR state.
11. The judge's id demand is live at .claude/hooks/stop/worklist_messages.py:2232-2235, .claude/hooks/stop/wl_judge.py:1362-1370 (the `out-of-sync` basis), .claude/hooks/stop/wl_checks.py:6220-6224 (`V_OUT_OF_SYNC`) and the `missing_ids` fact (.claude/hooks/stop/wl_checks.py:3301-3358). agent/plans/PLAN-stop-hook-store-status.md already owns its removal: S1-S3 are ticked and wl_storestatus is wired in, J1 removes the fact, its checklist rule and the basis, R1 retires the producer and its effort row, and D1 rewrites CLAUDE.md:64-65 and docs/agent-reference/loop-prompt.md:30.
12. Registering a gate follows check:ci-scope-mirrors: package.json:140, scripts/ci-runner/manifest.ts:5692-5718 with a `ci` step in .github/workflows/ci-quality.yml job quality-content (the step at :1597-1599, kept in parity by scripts/gates/check-ci-parity.ts), the `---- gate ----` header gate-bind reads, scripts/ci-runner/gates.lock.json (`npm run gen:gates-lock`), trace-ledger.ts, .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/policy/record-paths.json, a gate test under .ci/rediacc_ci/tests/gates/ (plants into copies only), a shard entry in .ci/config/shards/quality-pytest.json, and the generated rows in scripts/data/doc-registry.md.

## Design

### D1. Canonical homes

The agent file describes the loop end to end; where a step is /pr-merge's own mechanics it names the step and points at pr-merge.md. Guard-enforced rules stay canonical in CLAUDE.md under their existing scope anchors. docs/agent-reference/ci-gates.md stays the guard and check reference, outside this rewrite and outside the drift gate.

| Rule | Canonical (file, section) | Every other place |
|---|---|---|
| One branch, one PR, no stacking (guard-enforced) | CLAUDE.md:25 `pr.one-branch-one-pr` | agent step 2 terms mirror (kept); launcher nothing; output style terms mirror (kept) |
| Merge condition | CLAUDE.md:26-27 `pr.merge-condition` | agent :107 and pr-merge :27 terms mirrors (kept); agent :16, :137, :139 collapse to "loop step 8" pointers |
| ff fallback | CLAUDE.md:28 `pr.ff-fallback` | pr-merge step 3 terms mirror (kept) |
| Submodule PR branch named like the console branch, and the rename trap | agent step 3, new `pr.submodule-branch-name` | pr-merge :29 becomes a `ref` line; launcher nothing |
| Sibling non-submodule repos under `private/` | agent Preflight, new `pr.sibling-repos` | pr-merge :40-58 becomes a `ref` line plus its own merge-order bullet (:59-60, kept) |
| Next `MMDD-N` is MAX+1 over consumed PR heads | agent step 2, new `pr.consumed-names` | pr-merge step 7 (:333-343) becomes a `ref` line; the launcher keeps only the `!` line that prints consumed names |
| Finish sequence (ready, per-commit reviews, PR review, threads, end phase) | agent step 8, new `pr.finish-sequence` | pr-merge section 0 precondition (:114) becomes a `ref` line |
| PR-review wait and answer (exit codes 0/3/4, answer before push, only the outage excused) | pr-merge section 3, new `pr.review-answer` | agent step 8(c) is the one `ref` line; agent step 7's PR-review tail and the gotcha at :221 are deleted |
| Per-commit review precondition | agent step 7 | pr-merge :114 points at step 7 |
| Modes, and why inline is the default | agent Modes (new, from launcher :24-31, :121) | the launcher keeps only the argument test |
| Delegate-mode supervision | agent "Delegate mode: the lead's side" (new, from launcher :65-106) | nothing else; no scope id, because no copy remains |
| Residue drain, commit by path | CLAUDE.md:22 Commit form | agent :86 keeps the loop-specific snapshot fallback; the inline delta (launcher :116) moves to agent Modes |
| Live loop state | agent Round log, new State ownership paragraph | D5 |

### D2. Mechanism: extend scope-mirrors with a per-clause canonical file; no gen-docs text provider

A clause in .ci/config/scope-mirrors.json may carry `"canonical": "<path>"`, a file in the C9 corpus; without it the clause keeps CLAUDE.md. New loop-only clauses are canonical in the agent file or pr-merge.md, and their other places are `ref` mirrors.

Why this and not generated copies:

- The ask is for pointers: a generated copy still shows the same passage to a reader who opens both files. Generation answers "the copies agree"; this plan needs "there are no copies".
- One mechanism: scope-mirrors already has anchors, pins, `ref`, C9 sentinels and controls. A gen-docs text kind would be built twice, in the renderer and in the parity gate's re-implementation.
- Generated regions are invisible to scope-mirrors, so a passage regrowing next to one would be checked by nothing.
- Command files carry front matter and `!` lines the loader runs; generated prose there is shown on every invocation.
- Keeping CLAUDE.md as the only canonical file would push loop-only paragraphs into a file every session loads and split the loop across two files. The per-clause key is small: `canon_rel` becomes per clause, C1 runs per canonical file, and `ref` names that clause's canonical path.

Accepted trade-offs: `ref` cannot see a pointer that names the right file and the wrong section (a declared blind spot, and the success line counts `ref` spans), and a clause's canonical file is one more place an id must open exactly once.

### D3. The launcher (target: at most 35 lines, from 121)

- Front matter: `description` says what the command starts, plus "Every rule of the loop is in .claude/agents/pr-babysitter.md". `argument-hint`, the YAML comment lines and `allowed-tools` stay.
- `## Current state`: the `!` lines of :13-22 with rule prose removed from their labels. :15 is deleted, and "at most ONE is allowed, `block_second_branch`" becomes the plain label "Live local branches besides `main`".
- `## Mode`: the first token exactly `bg` is delegate mode; anything else, no arguments included, is inline. The rest of `$ARGUMENTS` seeds the intent summary.
- `## Start`: `.claude/hooks/stop/worklist.py --phase <me> babysit [--pr <n>]`, then one line: read .claude/agents/pr-babysitter.md in full and run it, as the babysitter (section Modes, inline) or as the lead (section "Delegate mode: the lead's side", `bg`).
- No scope anchor, no rule sentence, no sentinel phrase.

### D4. Agent file layout (target: at most 285 lines, from 236)

Front matter, then the intro (modes, principal, authority order, a one-line pointer to loop step 8), then in order:

- Modes (new): inline is the default and why (launcher :29-31 condensed), the inline deltas (launcher :113-121 without restated mechanics), and when `bg` is still right.
- Preflight, both modes (new): one babysit at a time (stop and `--phase <me> build` when one is live), resume detection and review state, the cold-start rule, and sibling repos (canonical `pr.sibling-repos`).
- Rule 1, Rule 2, the sole CI reader and the wake-up rules: unchanged.
- Tree ownership and the per-PR loop.
- The loop, steps 0-9: step 2 holds canonical `pr.consumed-names`, step 3 `pr.submodule-branch-name`, step 8 `pr.finish-sequence` with 8(c) a `ref` to pr-merge section 3. The sentence at :123-124 is deleted.
- Tier system and Workers.
- Round log, with the new State ownership paragraph (D5).
- Delegate mode, the lead's side (new): launcher :65-106 in the third person ("the lead", "the babysitter"). Its six steps and the messaging protocol keep their content; lines that restate agent-side halves already in the file collapse to pointers (:67 to The loop opening, :76 to Tree ownership, :82 to the sole CI reader).
- Standing gotchas without :221, and Guardrails.

The drift gate is described here, not named: W1 registers it as a `check:ci-` script and records the registered name in its tick, after which the agent file can name it in one line near the top.

### D5. State ownership (spec edits in the agent file only)

- The round log STATUS block is the only place live loop state is written (run, heads, result, red, doing, blocked), refreshed with `worklist.py --roundlog`. Unchanged.
- STATE.md during a wave carries `## Next action` plus one line `Round log: <path>`; run ids, green counts and red names are not copied there.
- The worklist carries per-item progress through `--update`, with the PR token on fix items. Unchanged.
- Chat and SendMessage reports carry deltas only: the round, what changed since the last report, and a decision if one is needed. .claude/agents/pr-babysitter.md:53 is rewritten to say this in place of the six-slot list.
- launcher :114 (compaction insurance) moves into Modes as "warm-start reads the wave header and STATUS". .claude/commands/standing-orders.md:53-65 and .claude/commands/awk.md:25 make no loop-state demand and stay.

### D6. The drift gate: the prose-duplication gate (W1 registers it as a `check:ci-` script)

- Family, fixed in code so the registry cannot switch it off: CLAUDE.md, .claude/commands/pr-babysit.md, .claude/agents/pr-babysitter.md and .claude/commands/pr-merge.md, all six pairs. These are what an agent reads to drive the loop. The output style and the pr-epics skill hold registered verbatim mirrors, which scope-mirrors judges; ci-gates.md is the guard reference. Widening the family is a one-tuple change, and the success line prints it.
- Unit: runs of normalized words, reusing `scope_mirrors.normalize`, `strip_gen_docs`, `md_blocks`/`code_mask`, `canonical_spans`/`mirror_spans` and `load_registry`, so the repo has one normalization.
- Excluded text becomes a run break: gen-docs regions, fenced and indented code, and registered scope spans (canonical and mirror), which scope-mirrors judges. An anchor without a registry entry is already red there (C10). Front matter is included, because the skill loader shows the description.
- Threshold: 25 words. After the rewrite the longest legitimate shared run among the four is expected under 20 (Context 4: 19, 16 and 13; the 24- and 20-word runs leave with the launcher text).
- Finding: `<path_a>:<line> ~ <path_b>:<line> <n> words: "<first 12 words> ..."`, then the fix: keep the passage in its D1 home and point from the other file.
- No baseline: W2 removes every current hit and the gate lands in the same batch.
- Exit codes: 0 clean, 1 finding, 2 broken controls or usage error. A missing family file or zero extracted words is exit 2, never a pass.
- Controls (`controls_first`, planting with `plant`): the clean fixture green; a 30-word passage planted in launcher and agent red, naming both paths; a 24-word shared run green and a 25-word one red; the passage rewrapped with `**` and backticks still red; inside a fence in both files green; inside a gen-docs region green; inside a registered scope span in both files green; under an unregistered anchor red; a missing family file rc 2.
- Live-tree red control (gate test, in a copy under `--root`): append the agent file's `pr.sibling-repos` paragraph, anchor removed, to the launcher copy and require rc 1 naming both files; the untouched copy is rc 0.
- Blind spots printed on green: paraphrase (scope-mirrors C9 sentinels cover registered clauses), files outside the family, and passages under 25 words.

### D7. The stop judge's id demand

The judge should read the worklist store, not the message: the operator's 2026-11-18 ruling, carried by agent/plans/PLAN-stop-hook-store-status.md J1, R1 and D1, whose Owns and Accept lines cover all five Context 11 sites. A second box here would put one rule's work in two plans, the exact duplication this plan removes, so box J0 records the check and adds a line to that plan only if a site turns out uncovered (same owner).

### D8. Clean break

No compatibility pointers stay in the launcher for moved text. No baseline rows are kept for moved prose: the prose baseline is drained and the drift gate has none. The three pr-babysit.md mirror registrations are deleted, not converted to `ref`, and the floors become the exact new counts.

## Not verified (load-bearing; each owner re-checks)

- Whether the two guards' goldens record message text byte for byte. W4 runs the golden suites and regenerates only through the tool they name.
- Whether `check:ci-paths-origin` accepts `pathsOrigin: 'declared'` for a gate with a fixed file set or wants a trace entry. W1 follows what the check prints.
- The new clause sentinels must sit in their canonical span and not in the launcher's state labels; "already consumed" is in a launcher label, so it is ruled out for `pr.consumed-names`. W3b picks them and C3 checks them.

## Tasks

Order: W1, W2 and W3a start together in leases. W3b starts from the head with W2 landed. W4 starts when PLAN-stop-hook-store-status has no live writer. Then J0, then L1-L3.

- [x] W1 [writer] Drift gate `check:ci-prose-duplication` as in D6: the module, the entry script with its `---- gate ----` header, unit tests, a gate test with the live-tree planted control, and three-point wiring.
  (corrected ASKED:2026-11-20T19:04Z) The box line cites the drift gate by a script name that is not registered, and is kept as written only so the box signature holds. The registered name is chosen in W1 and recorded in its tick; the Wiring line below states this.
  Owns: .ci/rediacc_ci/quality/prose_duplication.py, .ci/scripts/quality/check_prose_duplication.py, .ci/rediacc_ci/tests/test_quality_prose_duplication.py, .ci/rediacc_ci/tests/gates/test_gate_prose_duplication.py, .ci/config/shards/quality-pytest.json, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts, .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/policy/record-paths.json, .github/workflows/ci-quality.yml, docs/agent-reference/ci-gates.md, scripts/data/doc-registry.md
  Depends on: none; the real-tree green needs W2 landed and is proved in L1.
  Wiring: package.json gains one `check:ci-` script that runs `.ci/scripts/quality/check_prose_duplication.py` (W1 picks its name and records it in the tick); a manifest entry next to check:ci-scope-mirrors with `ci: {kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-content', step: 'PR loop docs carry no duplicated passage'}` and paths covering the four family files, both quality modules, the entry script and package.json; the matching workflow step after .github/workflows/ci-quality.yml:1599; a ci-gates.md row beside :139 with the fix recipe (keep the passage in its D1 home, point from the other file, never raise the threshold); `npm run gen:gates-lock` and `npx tsx scripts/gen/gen-docs.ts --write`.
  Accept, in the lease: `.ci/scripts/quality/check_prose_duplication.py --selftest` rc 0 listing every D6 control; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_prose_duplication.py` rc 0; `npx tsx scripts/gates/check-ci-parity.ts` rc 0; `npm run -s check:ci-gates-lock` rc 0; `npm run -s check:ci-prose-style` rc 0.
    (ticked) 2026-11-21T11:55:51Z by d778be9d: commit:f9ae35ffa (+b7fb7ad0c) on 1121-1: check:ci-prose-duplication compares CLAUDE.md, pr-babysit.md, the agent file and pr-merge.md for shared runs of 25+ words, excluding fences, gen-docs regions and only pairs where both sides are registered spans of the same clause; selftest 32 controls, mutants red; gate rc 0 on the real tree; gate tests T1-T5 and unit tests pass on the landed tree
- [x] W2 [writer] Rewrite the three loop files to D1, D3, D4 and D5 in the third person with no new second-person lines, then drain the prose baseline.
  Owns: .claude/commands/pr-babysit.md, .claude/agents/pr-babysitter.md, .claude/commands/pr-merge.md, .ci/config/prose-style-baseline.json
  Depends on: none.
  The new canonical spans carry closed anchors: `pr.sibling-repos`, `pr.consumed-names`, `pr.submodule-branch-name` and `pr.finish-sequence` in the agent file, `pr.review-answer` in pr-merge.md section 3. Each `ref` line names the canonical file path. Existing anchors stay byte-identical where D1 says kept.
  Accept: `wc -l` gives the launcher at most 35, the agent file at most 285 and pr-merge.md at most 335; `grep -c 'scope:' .claude/commands/pr-babysit.md` prints 0; the launcher's `!` lines are byte-identical to :13-22 apart from the D3 label edits (compare the `!`-backtick spans before and after); `.ci/scripts/quality/check_prose_style.py check --drain` then `npm run -s check:ci-prose-style` rc 0; W1's entry script run against the lease tree prints no finding (or the lead runs it in L1 if W1 has not landed).
    (ticked) 2026-11-21T11:40:17Z by d778be9d: commit:6c4319601 on 1121-1: pr-babysit.md is a 30-line launcher (state block kept, no scope anchor, no phase call), the agent file holds the loop (Modes, Preflight, Delegate mode, State ownership), pr-merge.md points at the agent file and carries the canonical review-answer rule, current loop only (no turbo, phases or focus-spawn), front matter parses; check_prose_style on the three files rc 0, baseline drained 69 rows; the scope-mirror registry follows in W3b
- [x] W3a [writer] Per-clause canonical in scope-mirrors as in D2: a clause may carry `"canonical"`, which must be a corpus file; C1 runs per canonical file; C2, C3, C5, C6 and C8 judge against the clause's own canonical span; `ref` names the clause's canonical path or another mirror; repin reads the clause's canonical; the module docstring's contract and registry sections say so.
  Owns: .ci/rediacc_ci/quality/scope_mirrors.py, .ci/rediacc_ci/tests/test_quality_scope_mirrors.py
  Depends on: none.
  New controls: a clause canonical in a second fixture file passes; its anchor opened twice there is red on C1; a `canonical` outside the corpus is red on C0; a `ref` naming only CLAUDE.md for a clause canonical elsewhere is red on C6.
  Accept: `.ci/scripts/quality/check_scope_mirrors.py --selftest` rc 0 listing the four new controls; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_scope_mirrors.py .ci/rediacc_ci/tests/gates/test_gate_scope_mirrors.py` rc 0 on the unchanged registry.
    (ticked) 2026-11-21T11:31:51Z by d778be9d: commit:a8f47ee44 on 1121-1: a clause may carry "canonical" (a corpus file, else C0), C1 runs per canonical, canonical_spans takes mirror_ids so a canonical file can hold other clauses mirrors, C2/C3/C5/C6/C8 judge the clause own span, --repin pins it; selftest 81 controls (16 new CANON), 12 branch mutants red; tests 47 passed, check:ci-scope-mirrors rc 0 on the landed tree
- [x] W3b [writer] Registry for the new layout: delete the three pr-babysit.md mirror entries; add pr.sibling-repos, pr.consumed-names, pr.submodule-branch-name and pr.finish-sequence (canonical in the agent file, ref in pr-merge.md) and pr.review-answer (canonical in pr-merge.md, ref in the agent file), each with `canonical`, atoms, sentinels and one `ref` mirror; pin each with `--repin <id>`; set the floors to the printed counts (expected 15 clauses and 33 mirror checks); the baseline gains no rows.
  Owns: .ci/config/scope-mirrors.json, .ci/config/scope-mirrors-baseline.json
  Depends on: W2 and W3a landed.
  Accept: `npm run -s check:ci-scope-mirrors` rc 0 with count equal to floor for both; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_scope_mirrors.py` rc 0.
    (ticked) 2026-11-21T11:47:40Z by d778be9d: commit:00c75ecdb on 1121-1: the three pr-babysit.md mirrors deleted, five new clauses (sibling-repos, consumed-names, submodule-branch-name, finish-sequence canonical in the agent file; review-answer canonical in pr-merge.md) each with one ref mirror, pinned by --repin; floors 14 clauses / 27 mirror checks (the box estimate of 15/33 was wrong: 9+5 clauses); check:ci-scope-mirrors rc 0 on the landed tree, a planted pointer change red (C6)
- [x] W4 [writer] Point hook text that cites the launcher as the rule source at the agent file, loop step 8 (finish line) or step 2 (branch naming); citations only, no logic change.
  Owns: .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py, .claude/rediacc_hooks/guards/block_stale_pr_branch_date.py, .claude/rediacc_hooks/tests/goldens/block_nonstandard_branch_name.jsonl, .claude/rediacc_hooks/tests/goldens/block_stale_pr_branch_date.jsonl, .claude/rediacc_hooks/tests/test_wl_priority_ladder.py
  Depends on: W2 landed, and no live writer of PLAN-stop-hook-store-status.md (J1 and R1 own the first two files).
  Sites: .claude/hooks/stop/worklist_messages.py:448 and :466, .claude/hooks/stop/wl_checks.py:5568, .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py:3 and :91, .claude/rediacc_hooks/guards/block_stale_pr_branch_date.py:6 and :211, .claude/rediacc_hooks/tests/test_wl_priority_ladder.py:207.
  Accept: `grep -rn 'commands/pr-babysit\.md' .claude/hooks .claude/rediacc_hooks` prints only lines naming the launcher as a launcher; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_hooks_fixtures.py .claude/rediacc_hooks/tests/test_guards_differential.py .claude/rediacc_hooks/tests/test_wl_priority_ladder.py` rc 0.
    (ticked) 2026-11-21T13:20:46Z by d778be9d: landed 8728bdc92 (+ golden world fix 536754cc9); test_hooks_fixtures + test_guards_differential + test_wl_priority_ladder 9262 passed rc 0
- [x] J0 [lead] Record D7: the judge's open-id demand is covered by PLAN-stop-hook-store-status.md J1, R1 and D1, so this plan files no box for it.
  Accept: `grep -n 'MISSING IDS' agent/plans/PLAN-stop-hook-store-status.md` names J1; `grep -n 'out-of-sync'` on it names J1 and R1; `grep -n 'every open task by id'` on it names D1; each Context 11 site falls in those boxes' Owns, and an uncovered site gets one line added to that plan citing this box.
    (ticked) 2026-11-22T15:48:05Z by ace763dd: present: agent/plans/PLAN-stop-hook-store-status.md:155 J1, :166 R1, :174 D1 cover the Context 11 sites
- [x] L1 [lead] Land W2, W3a, W3b, W1 and W4 in that order with the `./run.sh worktree land <id>` lines, regenerate, and run the gates on the landed tree.
  Accept, each rc 0: `npx tsx scripts/gen/gen-docs.ts --write` then `npx tsx scripts/gen/gen-docs.ts`; `npm run -s check:ci-doc-region-parity`; the new prose-duplication gate through its npm script; `npm run -s check:ci-prose-style`; `npm run -s check:ci-scope-mirrors`; `npx tsx scripts/gates/check-ci-parity.ts`. Red control on the landed tree: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_prose_duplication.py` rc 0, its planted-duplicate case asserting rc 1.
    (ticked) 2026-11-22T15:47:22Z by ace763dd: present: b7fb7ad0c f9ae35ffa 8728bdc92; gen-docs, doc-region-parity, prose-duplication, prose-style, scope-mirrors, check-ci-parity rc 0
- [ ] L2 [lead] Dry read of the rendered /pr-babysit and /pr-merge.
  Accept: each command's front matter parses with a YAML safe_load; every `!` line of both state blocks, run by hand, exits 0 with non-empty output; one Sonnet Explore agent answers 16 questions twice, from the pre-change texts (`git show <base>:<path>` for the three files) and from the landed ones, and the answers agree on every question except Q14, whose new answer is D5. Questions: 1 the default mode; 2 what `bg` does; 3 the first command run; 4 the round-log path; 5 how the next `MMDD-N` is computed; 6 the submodule branch name and the rename trap; 7 sibling repos; 8 the finish condition; 9 who merges in each mode; 10 whether the lead reads CI in bg; 11 the liveness signal; 12 whether a delegated babysitter commits; 13 how a fix writer is admitted in the babysit phase; 14 where live state, STATE.md and chat each belong; 15 /pr-merge on sibling repos and merge order; 16 /pr-merge on the next branch name.
- [ ] L3 [lead] Acceptance record in this plan.
  Accept: a table gives `wc -l` before and after for the three files (121, 236 and 349 before, then the landed counts, the launcher at most 35), the rc of the four acceptance gates and of the red control, and the W1 gate's output for the launcher/agent pair: no finding, so no rule text is duplicated from the agent file.

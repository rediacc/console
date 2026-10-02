# PLAN-plan-preflight: revalidate a plan against the current tree before its first box is worked

Status: approved -- operator approved building it 2026-10-02 ("Is there any mechanism that when AI starts to implement, does it validate the plan since other plans may already be done or there could be a slightly different world than the plan description?"; answer: none exists, build it), worklist #db04dfdb
Depends-On: no-dep -- builds on PLAN-plan-per-pr-loop boxes L1 and L2 (loop definition, QUEUE.md, plan_gate), both already ticked; the shared files pr-babysitter.md and pr-merge.md are sequenced by the queue order, and no box here needs that plan's open boxes
Owner: d778be9d
Priority: P1 -- operator-requested 2026-10-02; queued in QUEUE.md Promoted right after PLAN-plan-per-pr-loop
Concurrency: parallel -- at most 4 writers, disjoint file ownership per box (see Tasks)
Owns: .claude/hooks/stop/wl_planpreflight.py, .claude/hooks/stop/wl_plandeps.py, .claude/hooks/stop/test-plandeps.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/test-planrec.py, .claude/hooks/stop/test-planenforce.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/tests/test_wl_plan_preflight.py, .claude/rediacc_hooks/tests/test_wl_identity.py, .ci/scripts/quality/check_plan_citations.py, .ci/rediacc_ci/tests/gates/test_gate_plan_citations.py, .ci/scripts/quality/check_plan_implementation.py, .ci/config/plan-implementation.json, .claude/agents/pr-babysitter.md, .claude/commands/pr-merge.md, .claude/commands/pr-babysit.md

## Current state (verified 2026-10-02 on 0930-1, merge base with origin/main = origin/main)

- Box-level investigation exists only at tick time. `--plan-tick` dispatches at `.claude/hooks/stop/worklist.py:2473` and `--plan-investigate` at `.claude/hooks/stop/worklist.py:2476` (`_plantick_cli` at `.claude/hooks/stop/worklist.py:737`, `_planinvestigate_cli` at `.claude/hooks/stop/worklist.py:810`). `wl_planrec.plan_tick` (`.claude/hooks/stop/wl_planrec.py:2373`) refuses a tick with no investigation row (`.claude/hooks/stop/wl_planrec.py:2422`), then runs clause 1 (ordering) and clause 2 (falsifiable absent) at `.claude/hooks/stop/wl_planrec.py:2437`. The latest row per (plan, sig) wins (`investigation_for`, `.claude/hooks/stop/wl_planrec.py:2098`). Rows record `head` = `git rev-parse HEAD` (`plan_investigate`, `.claude/hooks/stop/wl_planrec.py:2213`). Nothing surveys a whole plan, and nothing runs when a plan becomes a PR's plan.
- A box's signature is its box line only (`box_sig`, `.claude/hooks/stop/wl_planrec.py:674`). Rewording an open box counts as a deleted box: check:ci-plan-boxes G-A1 (`.ci/scripts/quality/check_plan_boxes.py:30`-`.ci/scripts/quality/check_plan_boxes.py:34`) treats "rewriting its text" as a vanished box. Indented continuation lines are not part of the signature (`_evidence_slot`, `.claude/hooks/stop/wl_planrec.py:1843`).
- Citations are checked only on lines a change adds (`.ci/scripts/quality/check_plan_citations.py:9`, `added_lines` at `.ci/scripts/quality/check_plan_citations.py:324`). For a fileline citation the only test is that "the file exists and has that many lines" (`.ci/scripts/quality/check_plan_citations.py:17`). A cited line whose content moved still passes. `problems_for` (`.ci/scripts/quality/check_plan_citations.py:655`) already takes arbitrary (rel, lineno, text) rows.
- Dependency completion is decided by `Status:` alone (`Graph.is_complete`, `.claude/hooks/stop/wl_plandeps.py:749`), and a task edge resolves at plan level. A dependency marked done but still carrying open boxes is never re-checked when a dependent plan starts.
- The PR-to-plan link is written once, at the first push (`.claude/hooks/post-bash/refresh_pr_body.py:155`, from `plan_gate.queue_head`, `.claude/rediacc_hooks/plan_gate.py:51`). The only plan gate before merge counts boxes (`plan_merge_refusal`, `.claude/rediacc_hooks/plan_gate.py:129`).
- The loop starts a plan without validating it: `.claude/agents/pr-babysitter.md:96` (one plan per PR), `.claude/agents/pr-babysitter.md:103` and `.claude/agents/pr-babysitter.md:125` (next plan from QUEUE.md), and `.claude/commands/pr-merge.md:326` ("Then start the next queued plan").
- CI re-derives closed boxes forward-only: P-A2..P-A4 in `tick_findings` (`.ci/scripts/quality/check_plan_implementation.py:344`) require an evidence line, an investigation row and ancestry. These are cut by `baseline_at` in `.ci/config/plan-implementation.json`.
- The header grammar can be extended by table: `FIELD_SPECS` (`.claude/hooks/stop/wl_plandeps.py:389`), with the X-field window at 12 lines (`.claude/hooks/stop/wl_plandeps.py:58`).
- A read-only Haiku fan-out needs no new agent definition. `Explore` is already a read-only type (`.claude/hooks/stop/wl_roster.py:48`), and the Haiku slice uses the per-call `model` override (`docs/agent-reference/model-routing.md:42`). A new `model: haiku` agent file would also need a reason entry for check:ci-agent-model-roster.

## Design

### Departures from the ask, each forced by the code

1. **A partial box's remainder is not written by editing the box text.** That edit changes the box signature and reds G-A1. The remainder goes on an indented continuation line under the box instead: `    (preflight) <date> partial: <remainder>`. It is generated from the `partial` investigation row's note, so the signature, the ledger and G-A1 are untouched. `.ci/config/plan-boxes.json` does not change for it.
2. **`Revalidated:` records the merge base with origin/main, not HEAD.** `gh pr merge --rebase` rewrites branch shas, while a main sha survives and keeps resolving for check:ci-plan-citations.
3. **Staleness only counts changes that landed on main.** It is measured over `<Revalidated sha>..<current merge base>`, so the branch's own implementation commits never make the plan stale. A rebase that pulls in other people's changes to the watched paths does.
4. **One enforcement point plus one CI backstop.** The refusal lives in `plan_tick`, which every box closure already passes through. It applies to every tick, not only the first, so a mid-PR rebase onto relevant changes also forces a re-run. The CI rule P-A9 catches ticks made with the Edit tool. Rejected alternatives:
   - First push: push guards also carry non-plan fixes, and the Plan link does not exist before the first push.
   - Writer spawn (`block_plan_concurrency`): inline work bypasses it, and the guard fails open.
   - Merge-time `plan_gate`: P-A9 already reaches the merge through the required CI Complete check.
5. **The citation check is reused through a subprocess.** check_plan_citations gains a whole-file `--plan <rel> --json` mode. The stop-hook module calls that mode rather than importing a `.ci/scripts` gate, which would invert the existing direction: the gate imports `wl_planrec`.
6. **Only part of the premise check can be done by machine.** Citation resolution, line drift, overlap commits and dependency state are computed and recorded. Whether a prose claim in "Current state" still holds is a judgment made by the Haiku surveyors, and the lead corrects the text. That half is procedure in the loop step, not a gate.

### The mechanism

**Header** (optional, inside the 12-line window, placed right after `Owns:`):

```
Revalidated: YYYY-MM-DD @ <merge-base sha, 12-40 hex> [-- <note>]
```

The field is parsed through a new `FIELD_SPECS` entry. A malformed value counts as absent.

**Watched paths** of a plan:
- every fileline path cited outside fenced blocks;
- every backticked token that is a tracked path;
- the `Owns:` globs, as `:(glob)` pathspecs;
- the plan file itself;
- the plan files of its `Depends-On:` targets.

**Freshness** (`wl_planpreflight.revalidation_state(root, rel, text=None)`):
- `missing`: no valid header.
- `orphan`: the sha is not an ancestor of the current merge base B, which is `git merge-base HEAD origin/main`, or `main` in a clone with no remote.
- `stale`: `git log --format=%H <sha>..B -- <watched>` is non-empty. The commits are listed in the refusal.
- `fresh`: none of the above.
- B unresolvable: the state is "unknown", and `plan_tick` refuses (fails closed).

**The preflight** (`worklist.py --plan-preflight <me> <plan> [--write]`). It is a dry run by default and prints a report with five parts:

1. **Survey.** For each open box, the latest investigation row and whether it is current, meaning `merge-base --is-ancestor B <row.head>`. For each box that is uncovered or not current, it prints a ready `--plan-investigate` skeleton. Present-verdict boxes that are still open are listed with a `--plan-tick` skeleton built from the row's pointers.
2. **Citations.** The JSON from `check_plan_citations.py --plan <rel> --json`, in three groups:
   - unresolved;
   - drifted: the cited line's text at the commit that last wrote the citing plan line (`git blame --porcelain`) differs from the line's text now;
   - relocatable: the old line text occurs exactly once in the current file.

   Only lines outside done boxes, `(ticked)` evidence lines and fences are blocking. Citations inside history lines are reported but not judged.
3. **Overlap.** Commits in `<since>..B` that touch the watched paths, each with its subject and the plan files that commit changed. `<since>` is the `Revalidated:` sha, or for a first run the last commit on B that touched the plan. The list is capped at 30 entries, with the total count printed.
4. **Dependencies.** Each `Depends-On:` edge is re-checked. A Status that is not finished blocks. A finished Status over open boxes with no `Ruling:` line is a warning, reported as a box count from `wl_planfile.plan_boxes`.
5. **Verdict.** `--write` is refused while any of these holds:
   - an open box has no current row;
   - a `present` row's box is still open;
   - a blocking citation is unresolved, or is drifted and not relocatable;
   - a dependency blocks.

When none of those holds, one atomic write (`wl_planrec.write_atomic`) does four things:
- sets `Revalidated: <today> @ <B[:12]>`;
- rewrites each relocatable fileline citation to its new line number;
- inserts or replaces the `(preflight)` continuation line for each current `partial` row;
- replaces a generated `<!-- preflight:begin -->` ... `<!-- preflight:end -->` section, placed after the header, that records the counts, the overlap list, the dependency verdicts and the relocations.

The verb then runs `wl_planrec.refresh_index`, as `--plan-tick` does, and never commits.

**Survey fan-out (loop procedure).** Open boxes are split into batches of at most 8. Each batch goes to `Agent(subagent_type=Explore, model=haiku)`. The prompt carries the boxes, their sigs, the overlap list and the plan's "Current state" section. Each surveyor returns one line per box, `<sig> <present|absent|partial> <kind>:<tok> <kind>:<tok> -- <note>`, plus a list of premise claims that the tree contradicts. The lead runs `--plan-investigate ... --write` for each line, using the existing path with its re-resolution. It ticks each `present` box through `--plan-tick`, corrects contradicted premises in the plan text, then runs `--plan-preflight --write`. Plan, ledger and investigation rows land in one commit: `chore(plan): preflight <slug> @ <B12>`.

**Enforcement.**
- `plan_tick` adds a third clause after clause 1 and clause 2: anything other than `fresh` is refused, and the message names the exact `--plan-preflight` command and the stale commits. The check is placed after the investigation clauses so the existing refusal messages keep their order.
- CI P-A9 in check:ci-plan-implementation: every box this branch moved from open to done, with its tick dated after the new `revalidation_at` cut, must sit in a plan whose head copy has a `Revalidated:` sha that is an ancestor of the CI merge base. Range freshness is then judged against that base using the same `revalidation_state`, imported (no second implementation).

## Tasks

Writers: PF1 and PF2 start in parallel. PF3 freezes the `wl_planpreflight` API (`revalidation_state`, `watched_paths`, `survey`, `overlap`, `dep_findings`, `citation_report`, `apply`) before PF4, PF5 and PF6 run in parallel. PF7 follows PF4. PF8 runs before PF5's commit. PF9 is last.

- [ ] PF1 `Revalidated:` header grammar: add a `FieldSpec("Revalidated", X_HEADER_LINES, parse_revalidated)` entry to `FIELD_SPECS` in `.claude/hooks/stop/wl_plandeps.py`. The value grammar is `YYYY-MM-DD @ <12-40 hex> [-- note]`, with the duplicate rule and the outside-window rule inherited, and no X-finding code (optional field). Red-first cases in `.claude/hooks/stop/test-plandeps.py`: valid, bad date, short sha, duplicate line, line 13 outside the window, absent field means no finding. Files: wl_plandeps.py, test-plandeps.py. Depends on: none. Acceptance: `python3 .claude/hooks/stop/test-plandeps.py` rc 0 with the six new cases listed in its output.
- [ ] PF2 Whole-plan citation mode: `.ci/scripts/quality/check_plan_citations.py --plan <rel> [--json]` judges every line of one plan through the existing `citations()` and `unresolved()`. It classifies lines as blocking (header, prose, open boxes and their continuations) or history (done boxes, `(ticked)` lines, fences). It adds drift detection: `git blame --porcelain` gives each citing line's commit, and the cited line's text at that commit (`git show <c>:<path>`) is compared with the line's text now. A uniquely relocatable line gets `"relocate_to": n`. The JSON contract is frozen here: `{"plan", "unresolved":[{line,kind,token,why,blocking}], "drifted":[{line,token,relocate_to|null,blocking}]}`. `selftest()` gains planted controls for one drifted line and one relocatable line, with the silent pair. Files: check_plan_citations.py, `.ci/rediacc_ci/tests/gates/test_gate_plan_citations.py`. Depends on: none. Acceptance: `python3 .ci/scripts/quality/check_plan_citations.py --selftest` rc 0; `python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_plan_citations.py -q` rc 0; `python3 .ci/scripts/quality/check_plan_citations.py --plan agent/plans/PLAN-plan-per-pr-loop.md --json` prints valid JSON.
- [ ] PF3 Core module `.claude/hooks/stop/wl_planpreflight.py` (stdlib plus lazy `wl_planrec`/`wl_plandeps`/`wl_planfile`; no environment reads) implementing the Design section: merge base resolution (origin/main, then main), watched paths, `revalidation_state` (missing/orphan/stale/fresh/unknown), survey currency, overlap, dependency findings, `citation_report` (subprocess to PF2's mode), `render_block` and `apply`. `apply` covers the header insert after `Owns:` (refused when that would leave the window), relocations, the `(preflight)` partial lines and the generated block. Red-first suite `.claude/rediacc_hooks/tests/test_wl_plan_preflight.py`, run against a fixture git repo with an `origin/main` ref, each case a planted defect paired with a silent control: a main commit touching a cited path after the sha makes the plan stale; a main commit touching an unrelated path keeps it fresh; a branch-only commit touching a cited path keeps it fresh; an `Owns:` glob match makes it stale; a dependency plan edited on main makes it stale; an orphan sha; a partial row produces a continuation line and leaves the box signature and `plan_boxes` output unchanged; a present-and-open box blocks `--write`; an unfinished dependency blocks; a done-with-open-boxes dependency warns; a relocation rewrites only the line number. Files: wl_planpreflight.py, test_wl_plan_preflight.py. Depends on: PF1, PF2 (JSON contract). Acceptance: `python3 -m pytest .claude/rediacc_hooks/tests/test_wl_plan_preflight.py -q` rc 0, at least 11 cases.
- [ ] PF4 Verb `worklist.py --plan-preflight <me> <plan> [--write]`: it takes identity through `_identity_or_die`, prints the report by default, and with `--write` writes the plan (`write_atomic`), refreshes INDEX/QUEUE (`refresh_index`) and prints the one-commit reminder. It never commits. Usage, dry-run and refusal strings go in `.claude/hooks/stop/worklist_messages.py`, and the dispatch sits beside the `--plan-investigate` dispatch. Add a CONTROL A row to `.claude/rediacc_hooks/tests/test_wl_identity.py`. Files: worklist.py, worklist_messages.py, test_wl_identity.py. Depends on: PF3. Acceptance: `python3 -m pytest .claude/rediacc_hooks/tests/test_wl_identity.py -q` rc 0; `python3 .claude/hooks/stop/worklist.py --plan-preflight <me> agent/plans/PLAN-plan-preflight.md` rc 0 printing all five report parts.
- [ ] PF5 Tick refusal: `wl_planrec.plan_tick` imports `wl_planpreflight` lazily and refuses any state other than `fresh` after clause 1 and clause 2. The message names `worklist.py --plan-preflight <me> <rel>` and up to 5 stale commits. Red-first: unrevalidated plan refused; fresh plan ticks; stale after a main commit touching a cited path refused; branch-own commit touching a cited path still ticks; B unresolvable refused. Existing success-path fixtures in `.claude/hooks/stop/test-planrec.py` and `.claude/hooks/stop/test-planenforce.py` gain a fresh `Revalidated:` header, and no existing refusal expectation changes. Files: wl_planrec.py, test-planrec.py, test-planenforce.py. Depends on: PF3; lands after PF8. Acceptance: `python3 .claude/hooks/stop/test-planrec.py && python3 .claude/hooks/stop/test-planenforce.py` rc 0 with the five new cases listed.
- [ ] PF6 CI backstop P-A9 in `.ci/scripts/quality/check_plan_implementation.py`: over the boxes `tick_findings` already judges, with the tick dated after the new `revalidation_at` key in `.ci/config/plan-implementation.json` (set to the landing date, so the landing commit is silent by construction), the plan's head copy must carry a `Revalidated:` whose sha is an ancestor of the merge base, and `revalidation_state` must not be `stale` against that base. Add `revalidation_state` to the `load_modules` contract. `controls_fired` gains three plants (missing header, stale range, tick before the cut, which stays silent), each with a healthy pair. Files: check_plan_implementation.py, plan-implementation.json. Depends on: PF3. Acceptance: `npm run check:ci-plan-implementation` rc 0 with the P-A9 controls printed as PASS.
- [ ] PF7 Loop wiring: `.claude/agents/pr-babysitter.md` gains a per-PR-loop bullet "Preflight the plan before the first writer" and a step 0 in "The loop" ahead of survey and resume detection, carrying the fan-out procedure (Explore with model haiku, batches of 8, the fixed output line, `--plan-investigate`/`--plan-tick` per box), premise correction, `--plan-preflight --write`, the single preflight commit, and a re-run after any rebase that `--plan-tick` reports as stale. `.claude/commands/pr-merge.md:326` ("Then start the next queued plan") runs the preflight on the new branch before any writer, and `.claude/commands/pr-babysit.md` says the same in its loop summary. Files: those three. Depends on: PF4. Acceptance: `grep -c "plan-preflight" .claude/agents/pr-babysitter.md .claude/commands/pr-merge.md .claude/commands/pr-babysit.md` reports at least 1 per file; `npm run check:ci-prose-style` rc 0.
- [ ] PF8 Dogfood before enforcement: run the full preflight (fan-out, investigations, `--write`) on this plan and on every plan with open boxes that a live PR carries (today `agent/plans/PLAN-plan-per-pr-loop.md`: R1, R3, M7), and commit each. These are the plans whose next tick PF5 would otherwise refuse. Files: the two plan files, `.ci/config/plan-boxes.json`, `agent/ledgers/plan-investigation.jsonl`, `agent/INDEX.md`, `agent/plans/QUEUE.md` (lead only, no writer). Depends on: PF4. Acceptance: `python3 .claude/hooks/stop/worklist.py --plan-preflight <me> agent/plans/PLAN-plan-preflight.md` reports state `fresh`; `npm run check:ci-plan-boxes && npm run check:ci-plan-record && npm run check:ci-plan-citations` rc 0.
- [ ] PF9 Real run: the first plan started by the loop after this PR merges goes through step 0 end to end. The PR body or report records the survey counts (present/absent/partial), ticks made by the survey, relocated and corrected citations, the overlap list length and the `Revalidated:` sha. One deliberate stale case is exercised: after a rebase onto a main commit that touches a cited path, `--plan-tick` refuses, the preflight is re-run and the tick passes. Files: none owned (evidence only). Depends on: PF5, PF6, PF7 and this PR's merge. Acceptance: the plan's header carries `Revalidated:` at the new branch's merge base, and the refused-then-accepted tick pair is quoted with both outputs in the round log.

## Interim procedure (until PF7 lands)

When the loop starts a plan from QUEUE.md before this plan ships, the lead runs the manual form of step 0: a read-only Explore (model haiku) survey of every open box, `--plan-investigate` per box with its verdict, `--plan-tick` for each `present` box, and a correction of any "Current state" claim the tree contradicts, all in one `chore(plan): preflight <slug>` commit before the first writer.

## Verification

- Unit level: PF1-PF6 acceptance commands, all rc 0, each new rule with a red-first case and its silent pair.
- Gate level: `npm run check:ci-plan-implementation`, `npm run check:ci-plan-citations`, `npm run check:ci-plan-boxes`, `npm run check:ci-plan-deps`, `npm run check:ci-plan-record`, `npm run check:ci-pytest`, all rc 0 on the PR head through `ci-trace.py`.
- Behaviour level:
  - On a scratch clone, cut a branch, add a main commit touching a path this plan cites, rebase: `--plan-tick` refuses and names that commit.
  - `--plan-preflight --write` then succeeds, and the tick passes.
  - A commit on the branch touching the same path does not make the plan stale.
- G-A1 safety: after a preflight that writes a `(preflight)` partial line, `python3 .ci/scripts/quality/check_plan_boxes.py` reports no vanished signature, and `.ci/config/plan-boxes.json` is unchanged for that plan.

## Risks

- **Every open plan carried by a live PR is refused at its next tick once PF5 lands.** PF8 revalidates those plans first, and the refusal names the exact command. Held plans are unaffected until they are started.
- **Noise from overlap on broad `Owns:` globs.** A plan owning `.claude/hooks/stop/*.py` goes stale on nearly every merge. This is accepted, because the cost is one re-run, and the refusal lists the commits so the re-run is targeted. If it proves too noisy, narrowing a plan's Owns is the remedy, not a bypass.
- **History lines drifting.** Citations inside done boxes and `(ticked)` lines are reported but never blocking. Without that split, old plans could never be revalidated.
- **Blame cost on large plans** (the largest is about 650 KB). The preflight runs one `git blame --porcelain` per plan, never one per line.
- **The premise check is judgment.** Surveyors can miss a contradicted claim. The machine half (citations, drift, overlap, dependencies) is enforced; the prose half is recorded in the preflight commit and reviewed by the per-commit reviewer.
- **Investigation rows go stale after a rebase.** A rebase also invalidates clause 1 for `absent` rows whose head is no longer an ancestor. This already happens today; the preflight re-survey writes fresh rows in the same pass.
- **File overlap with PLAN-plan-per-pr-loop** (`Owns:` lists pr-merge.md and pr-babysitter.md). `block_plan_concurrency` refuses a PF7 writer while that plan has live writers. PF7 is small and can be done inline by the lead.

# PLAN-plan-compaction-bindings: a plan is never compacted, moved or swept while anything still binds to it

Status: approved -- operator 2026-10-03: "The planning tools/system should not allow plan compaction if there is any binding to other plans until we complete all the pieces"
Depends-On: no-dep -- reuses wl_plandeps.Graph and the worklist store; no plan prerequisite
Owner: d778be9d
Priority: P1 -- seven plans already sit compacted in _done/ with open boxes, and their worklist items surfaced as unowned questions to the operator on 2026-10-03
Concurrency: parallel -- disjoint file ownership per box
Owns: .claude/hooks/stop/wl_planbind.py, .claude/hooks/stop/wl_planrec.py, .ci/scripts/quality/check_plan_folders.py, .ci/scripts/quality/check_plan_bindings.py, .claude/rediacc_hooks/tests/test_wl_planbind.py, .claude/hooks/stop/worklist_messages.py, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .github/workflows/ci-quality.yml, CLAUDE.md, docs/agent-reference/TRAPS.md

## Operator ruling (2026-10-03), condensed

A plan cannot be compacted (`--plan-compact`, with or without `--park`), moved to `_done/` or `_removed/` (`check_plan_folders --move`), or swept (`--sweep`) while anything binds to it. Bindings, all of them:

1. an open box of its own, unless the header carries a `Ruling:` that re-resolves AND every open box is re-homed (the box names where its work went: another plan's box, or a worklist item that is itself bound to a live plan);
2. an open worklist item, in any session's store, that cites the plan (`PLAN-x.md`) or one of its box signatures;
3. an unfinished plan that depends on it (`Depends-On:` or a task ref, through `wl_plandeps.Graph`);
4. an open box in another plan that cites one of its boxes.

## Current state (verified 2026-10-03 on 1003-1)

- `wl_planrec.compact` (`.claude/hooks/stop/wl_planrec.py:1550`) refuses a dirty path, an existing record, and open boxes unless `--park`; it reads nothing outside the file.
- `check_plan_folders.move` (`.ci/scripts/quality/check_plan_folders.py:459`) refuses a stub, a non-file and a terminal folder without a ledger row; `sweep` (`:399`) deletes past retention. Neither reads bindings.
- Seven `_done/` plans carry open boxes (`.ci/config/plan-boxes.json`): PLAN-ci-prebaked-vm-images (3 open), PLAN-ci-time-budget (2), PLAN-fix-console-ci-5day-failure (13, cited 58 times in agent/worklist/d778be9d.jsonl), PLAN-plan-file-lifecycle (1), PLAN-renet-ceph-gpu-non-apt (1), PLAN-renet-obs-mirror (3), PLAN-stop-hook-plan-agent-check-declined (5). On 2026-10-03 the worklist items bound to three of them reached the operator as "no live box: keep or drop?".

## Design

One function decides, every path asks it, and a gate re-checks the tree so a hand edit cannot slip past.

- `wl_planbind.bindings(root, rel) -> list[Binding(kind, where, detail)]`: the four kinds above. Items are read from every `agent/worklist/*.jsonl` through the store's fold (open, in-flight and deferred states count; done and dropped do not). Box citations match `PLAN-x.md [<sig>]` and the plan path. Dependents come from `wl_plandeps.Graph.load(root)`. Pure over its inputs, injected readers for the tests.
- Every compaction or move path calls it and refuses with the full list and the exact next commands (tick or re-home the item, `--epic <me> plan`, add the box to the plan that takes it over, or `--plan-revive`).
- The new plan-bindings gate (npm script `ci-plan-bindings` under the check prefix, added by CB4) judges the committed tree: any plan whose Status is compacted, parked, moved or finished, or that lives under `_done/`/`_removed/`, with a live binding, is a finding. There is no baseline: the migration box empties the set first (clean break).

## Tasks

- [ ] CB1 `.claude/hooks/stop/wl_planbind.py` with `bindings(root, rel)` per Design, and red-first tests in `.claude/rediacc_hooks/tests/test_wl_planbind.py`: an open item citing the plan binds; a ticked one does not (control); an item citing a box sig binds; a dependent unfinished plan binds, a finished dependent does not (control); an open box elsewhere citing a box binds; an own open box binds unless a `Ruling:` re-resolves and the box names its new home. Files: `.claude/hooks/stop/wl_planbind.py`, `.claude/rediacc_hooks/tests/test_wl_planbind.py`. Depends on: none. Acceptance: `.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_planbind.py` rc 0.
- [ ] CB2 `wl_planrec.compact` (both the compacted and the parked form) and `--plan-revive`'s inverse paths refuse while `bindings` is non-empty, printing every binding and the next commands; messages catalogued. Red-first: compacting the fixture plan with one open citing item is refused and names it; control: with the item ticked it compacts. Files: `.claude/hooks/stop/wl_planrec.py`, `.claude/hooks/stop/worklist_messages.py`, `.claude/rediacc_hooks/tests/test_wl_planbind.py`. Depends on: CB1. Acceptance: the new cases rc 0; `python3 .claude/hooks/stop/test-planfile.py` 0 failures.
- [ ] CB3 `check_plan_folders` `--move` and `--sweep` refuse a bound plan the same way (the .ci side imports wl_planbind by file, as other .ci quality scripts reach the stop modules). Red-first in the script's selftest. Files: `.ci/scripts/quality/check_plan_folders.py`. Depends on: CB1. Acceptance: `python3 .ci/scripts/quality/check_plan_folders.py --selftest` rc 0.
- [ ] CB4 The plan-bindings gate (`.ci/scripts/quality/check_plan_bindings.py`, npm script `ci-plan-bindings` under the check prefix), wired in package.json, the ci-runner manifest, gates.lock and the quality-static workflow step; controls first, a plant that proves it can fail, a vacuity refusal on zero plans read. Files: `.ci/scripts/quality/check_plan_bindings.py`, `package.json`, `scripts/ci-runner/manifest.ts`, `scripts/ci-runner/gates.lock.json`, `.github/workflows/ci-quality.yml`. Depends on: CB1. Acceptance: the new gate rc 0 after CB5; `npm run check:ci-parity && npm run check:ci-gate-bind && npm run check:ci-gates-lock` rc 0.
- [ ] CB5 Migration, lead-only: for each of the seven `_done/` plans with open boxes and every plan the gate flags, re-home each binding: revive the plan (`--plan-revive`) when its work is still wanted, or move its open boxes into the plan that took the work over (citing them), and tick or re-home each bound worklist item (`--epic <me> plan`, or close it with the box it now mirrors). Items the operator dropped on 2026-10-03 stay closed. Files: none owned (verbs and plan text only). Depends on: CB1-CB4. Acceptance: the plan-bindings gate rc 0 with zero findings; `npm run check:ci-plan-boxes && npm run check:ci-plan-record` rc 0.
- [ ] CB6 Docs: CLAUDE.md's plan lifecycle sentence (a plan with live bindings cannot be compacted, moved or swept), and a TRAPS.md entry for the 2026-10-03 orphans. Files: `CLAUDE.md`, `docs/agent-reference/TRAPS.md`. Depends on: CB2-CB4. Acceptance: `npm run check:ci-prose-style && npm run check:ci-trap-registry` rc 0.
- [ ] CB7 Real run: `worklist.py --plan-compact d778be9d <a live plan with an open citing item> --write` is refused naming the item, and `check_plan_folders --move` on the same plan is refused. Files: none owned (evidence only). Depends on: CB2, CB3. Acceptance: both refusals quoted in the round log.

## Verification

Each box's acceptance; then `npm run ci:quick`. The controls that the tick of a bound item releases the plan keep the guard from blocking finished work.

## Risks

- Reading every session's worklist on each compaction is slower than reading the file: bounded by the store size, and compaction is rare.
- A citation spelled differently from `PLAN-x.md` or a box sig is missed: the gate re-checks with the same matcher, and the migration box exercises it on 39 real items.

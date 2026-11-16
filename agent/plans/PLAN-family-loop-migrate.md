# PLAN: `rdc repo migrate` moves a repository together with its forks, and reflink sharing survives on the destination

Status: proposed -- converted from console#606 (operator picked this item 2026-11-16); awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: PLAN-datastore-migrate-correctness.md, PLAN-detached-jobs.md
Priority: P3 -- a family with forks cannot migrate at all today, but it refuses loudly with a teaching message and `repo push` per fork is a working manual path
Concurrency: parallel -- CLI migrate files plus one new e2e suite; renet backup_push.go is touched only if M1 refutes sharing, and that file waits on PLAN-datastore-migrate-correctness.md by Depends-On
Owns: agent/plans/PLAN-family-loop-migrate.md, packages/cli/src/commands/repo-migrate.ts, packages/cli/src/services/repo/repo-family-migrate.ts (new), packages/cli/src/services/repo/__tests__/repo-family-migrate.test.ts (new), packages/cli/src/services/jobs/steps.ts (migratePlacement step only), packages/cli/src/i18n/locales/*/cli.json, packages/e2e-tests/tests/23c-cli-migrate-family.test.ts (new), packages/e2e-tests/src/utils/cliMigrateHarness.ts, private/renet/cmd/renet/backup_push.go (seed path only, F6 only), docs/design/spec/13-wave2-ledger.md (status lines only)
Live-Proof: hostinger -- the migrate orchestration under packages/cli/src is the cli surface and the conditional seed fix in private/renet/cmd/renet is the renet surface; hostinger admits both.
Source: https://github.com/rediacc/console/issues/606

## Ask

`rdc repo migrate <name> --to <machine>` refuses any family that has forks, and a fork ref exits 2. The refusal was a fallback ruling (R2 of the wave-2 routing design) taken because nobody had measured whether the forks would still share extents with their grand once moved. Without sharing, a family of one 100 GB grand and five forks lands as 600 GB on the destination, which breaks the constant-cost fork promise.
This plan answers that question with a measurement, then makes migrate move the whole family in one command with sharing intact.

Search first: no plan in `agent/plans/` or `agent/plans/_done/` covers family migrate; `grep -rli family-loop agent/plans` finds nothing. The only records are the wave-2 ledger and the code comment cited below.

## Context (checked 2026-11-16 against the tree)

1. The refusal: `assertFamilyMigratable` (`packages/cli/src/commands/repo-migrate.ts:271`) throws `forkRefError` for a non-grand tag and `familyHasForks` for a grand with forks; it runs from `migrateRepo` at `repo-migrate.ts:473`. Its doc comment (`repo-migrate.ts:260-270`) gates the follow-up on "Open question #1: reflink preservation across backup_push with seeds, a VM check the fleet cannot give this week".
2. The ruling record: `docs/design/spec/13-wave2-ledger.md:36` (R2, "family-loop DEFERRED on the reflink-preservation VM question") and `:64-66` (item 11, deferred by standing rulings). The wave design doc the ledger cites is not in the tree, so the question survives only in those two places.
3. Migrate already sends seeds: `migrateParams` (`repo-migrate.ts:143-166`) builds `seed` from the repo's own GUID first, then `parentGuid`, then `grandGuid` (`:150-156`). For a fork whose grand already lives on the destination, the second or third seed hits.
4. The renet source job (`private/renet/cmd/renet/repository_migrate.go:188`) runs a hot bulk push with `seed` and `retain-base` (`:251`), stops the repo, then a cutover push with `delta-base` set to the retained base (`:257-267`), then unmounts and emits `cutover_complete`.
5. The seeded bulk push: `pushToMachine` reflinks the first seed that exists on the destination into the temp image (`private/renet/cmd/renet/backup_push.go:499-522`, `cp --archive --reflink=always`), or the destination's own copy on a re-push (`:524-538`), then runs rsync with `imageTransferRsyncFlags(!isDir && !seedUsed)` (`:598`), which for a seeded temp is `--partial --inplace --no-whole-file` without `--sparse` (`private/renet/cmd/renet/backup_pull.go:65-71`).
6. The cutover push: `attemptDeltaTransfer` (`private/renet/cmd/renet/backup_push_delta.go:27`) reflinks the remote base into the temp (`:98-107`), ships only the changed ranges that `delta.Compare` found (`:84`), and `delta.Apply` writes only those ranges with positioned writes (`private/renet/pkg/delta/apply.go:21-60`).
7. Placement is family-level: the `migratePlacement` step fires on each job's `marker:cutover_complete` and calls `setRepositoryPlacement(name, { machine: to })` with the family name (`packages/cli/src/services/jobs/steps.ts:124-136`). Run once per member, it would flip the whole family after the first member moved.
8. R3 deletes the source image after the target is up (`completeOnTarget`, `repo-migrate.ts:297`, `deleteSourceImage` at `:226`); `--keep-source` opts out (`:316`).
9. The phase-1 base survives its prune today (`13-wave2-ledger.md` item 12); PLAN-datastore-migrate-correctness.md A1/A2 fix it in `backup_push.go`. A family migrate retains one base per member, so without that fix every member leaks a full image on both machines.
10. PLAN-detached-jobs.md owns `repo-migrate.ts` with open boxes; its J4 successor-job model (`repo-migrate.ts:287-296`) is the shape a background family migrate has to fit.

**The VM question, answered from code as far as code goes.** Both write paths land on a reflink of a relative and then write only differing ranges: rsync `--inplace` skips writing a block that matches at the same offset (rsync's receiver seeks over it), and `delta.Apply` writes only changed ranges. LUKS ciphertext of a fork equals its grand's wherever the fork has not written, because a fork is a reflink of the same LUKS image with the same volume key.
So by construction the destination fork should share every unwritten extent with the destination grand. Two things code reading cannot settle: whether the bundled rsync (`getRsyncPath`) really skips same-offset matches rather than rewriting them, and whether btrfs keeps the sharing across the final `mv -f` and `chmod 400`. M1 measures both, with a control that proves the measurement can fail.

## Design

**M1 first, and it decides F6.** M1 is a measured VM experiment and a permanent e2e regression in the same suite. If it shows sharing survives, F6 closes as not needed with the measurement as evidence. If it refutes, F6 fixes the seed path before F1-F5 ship (the likely fix: a seeded push uses the delta path against the seed instead of rsync, since `delta.Compare` with the physical strategy already handles a reflinked pair).

M1 edits no file a prerequisite owns and only measures, so its tick carries `DEPS-WAIVED: measurement only, no prerequisite-owned file` and it can run before both Depends-On plans finish.

**M1 protocol.** Test 1 of `packages/e2e-tests/tests/23c-cli-migrate-family.test.ts`, on the `cliMigrateHarness` two-worker fleet (M1, M2): create a 2G grand, write 256 MiB into it, fork it, write 64 MiB into the fork, push the grand to M2, then push the fork to M2 with `--seed <grandGuid>`. On M2, `sudo btrfs filesystem du --raw -s` over both images gives each image's exclusive bytes.
The control, in the same test: push a second fork with no seed and `--force`; its exclusive bytes must exceed 200 MiB, which proves the measure can fail. The test also records the bundled rsync's `--version`.

**Family order.** Members migrate grand first, then forks in parent-depth order (a fork of a fork after its parent), so each member's closest relative is already on the destination when its seed list is read. The order comes from `parentGuid`/`grandGuid` in config, not from tag names.

**Two passes.** Pass 1 (hot, no downtime): pre-seed every member to the destination with the existing `backup_push` function, seeded by its relatives, so each member has an image under its own GUID there. Pass 2: one `repository_migrate` job per member in family order. Because migrate's seed list starts with the member's own GUID (Context 3), each pass-2 bulk push is a delta over the pass-1 copy, so a member's downtime is its cutover only.

**One placement flip, one start, one delete.** The family is single-valued, so the flip happens once, after the last member's cutover marker: the per-member jobs run without the `migratePlacement` step and the loop runs it once at the end. Members are started on the destination only after the flip, then DNS, then the source images are deleted (R3) only after every member is up.
A failure part-way leaves the family's placement on the source, the source images intact, and the moved members stopped; re-running the same command resumes, because pass 1 and pass 2 are idempotent per member (a member whose destination copy is current pushes nothing).

**Refusals that stay.** A fork ref (`name:tag`) still exits 2: migrate moves families, and a single fork elsewhere is `repo push`. `familyHasForks` is deleted with its 13 locale entries (clean break). `--background` on a family with forks refuses with a teaching error in this plan; chaining N jobs under the J4 successor model needs PLAN-detached-jobs.md finished first, and the refusal names it.

**Out of scope.** Cluster-placed families (`rdc cluster migrate` is its own path). The www docs line in `packages/www/src/content/docs/en/repositories.md` "Migrate Repository": a www edit makes the plan owe a bench www receipt, and the `www-smoke` check cannot verify until a bench www Worker exists (`.ci/config/proof-tiers.json` `tiers.live.checks.www-smoke`); the CLI help text carries the behaviour, and the docs line is an operator question.

## Boxes

- [ ] M1 [live] Run the M1 protocol (Design) as suite 23c test 1 on the two-worker fleet, with the unseeded control. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/23c-cli-migrate-family.test.ts` rc 0, the seeded fork's exclusive bytes under 96 MiB and the control's over 200 MiB, both numbers and the rsync version quoted in the tick
- [ ] F1 [writer] `repo-family-migrate.ts`: pure planner from config (`RepoFamily`, `parentGuid`, `grandGuid`) to the ordered member list and the two passes, with tests for a grand alone, grand plus two forks, a fork of a fork, and a cycle or missing parent that refuses. Accept: `cd packages/cli && npx vitest run src/services/repo/__tests__/repo-family-migrate.test.ts` rc 0
- [ ] F2 [writer] Wire the planner into `migrateRepo` per Design (pass 1 pre-seed via `backup_push`, pass 2 per-member jobs without the placement step, one flip, starts, DNS, source deletes last); delete the `familyHasForks` arm and key in all 13 locales; keep `forkRefError`; refuse `--background` for a family with forks with a new teaching key. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/repo-migrate-datastore.test.ts src/services/repo/__tests__/repo-family-migrate.test.ts` rc 0 and `npm run check:i18n` rc 0
- [ ] F3 [writer] `steps.ts`: the `migratePlacement` step runs only when the job's params carry the family's final-member flag, with a unit test that a non-final member's marker leaves placement unchanged. Accept: `cd packages/cli && npx vitest run src/services/jobs/__tests__/steps.test.ts` rc 0
- [ ] F4 [writer] e2e suite 23c tests 2-4: a grand with two forks migrates M1 to M2 (placement flipped once, all three up on M2, no member GUID left on M1, each fork's exclusive bytes under its written amount plus 32 MiB); a job killed after the grand's cutover leaves placement on M1 and a re-run completes; a fork ref still exits 2. Accept: `npx tsc --noEmit -p packages/e2e-tests` rc 0
- [ ] F5 [writer] `13-wave2-ledger.md`: R2's "DEFERRED" note and item 11's family-loop entry point at this plan and M1's measurement. Accept: `npm run check:ci-prose-style` rc 0
- [ ] F6 [writer] Only if M1 refutes sharing: make a seeded push keep extents shared (delta path against the seed, per Design), with a renet test that a seeded push of a fork writes only the fork's changed ranges. If M1 confirms sharing, tick with M1's numbers and no code. Accept: `cd private/renet && go test ./cmd/renet -run 'TestPushSeed' -count=1` rc 0, or M1's tick evidence quoted
- [ ] V1 [live] Run suite 23c on the KVM fleet after F2-F4 land; only the suite's own repos, no `ops down`, and wait until machines 11 and 12 are free (11 carries another agent's work at conversion time). Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test tests/23c-cli-migrate-family.test.ts` rc 0
- [ ] V2 [live] VM tier before the live receipt. Accept: `npm run vm:check -- --changed` rc 0 with a VERIFIED receipt
- [ ] LP-hostinger [live] Fresh hostinger receipt after V2 on the same tree.
  Accept: live-proof hostinger renet-live

## Risks

- Reconcile reports pass-1 copies as the R4 declared-plus-strays conflict until the flip (`packages/cli/src/services/config/config-reconcile.ts:141-148`), and its message advises `machine prune`. Reconcile never edits a declared placement, so nothing breaks, and a pruned pass-1 copy only costs a full push on resume; F4 asserts a reconcile during pass 1 changes no config.
- The grand is down from its cutover until the last fork's cutover finishes. Pass 1 keeps that window to the sum of the forks' cutover deltas; M1 and V1 record the measured window.
- A large family retains one delta base per member. Until PLAN-datastore-migrate-correctness.md A2 lands, each leaks; Depends-On holds this plan behind it.
- If M1 shows partial sharing (some extents rewritten by rsync's match-at-another-offset path), the thresholds decide; a result between them is reported to the operator, not rounded to a pass.

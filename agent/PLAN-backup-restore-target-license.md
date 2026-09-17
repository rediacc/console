# PLAN: Licence the restore target, so disaster recovery works on a bare machine
Status: compacted
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-backup-restore-target-license.md
Full-Text-Blob: 65118820f452478aba55580152843d0a14188c75
Record-Sig: e9455a6c

## Why
`renet backup restore` refused to run on a machine holding no repository licence, because the chunk-store session it needs is authenticated by a signed licence blob that doubles as the address book. That is precisely the disaster-recovery case, a bare replacement machine, so the verb failed exactly where it was needed, and it failed with a plain error string rather than the exit-10
LICENSE_REQUIRED signal, so none of the CLI's existing licence-recovery machinery could see it. renet could not fix it alone: it has no mint or install verb, only `license renew`, and the recovery framework's batch refresh works from a scan of INSTALLED repositories, which a bare machine has none of. The answer had to be a CLI-side pre-flight.

## Outcome
SHIPPED, measured 2026-09-06, with two named leftovers. THE HEADER SAYS `Status: draft` AND THE TREE DISAGREES; the console commit is 120cd9e73, "feat(backup): chunk-store cold path, rclone decommission, stop-hook cadence", an ancestor of origin/main.

- The predicate landed beside its sibling as specified: `isRestoreLicenseFunction` at
`packages/cli/src/services/renet/renet-license-contract.ts:178`.
- The pre-flight landed: `resolveRestoreLicenseContext` at
`packages/cli/src/services/executor/local-executor.ts:416` and `ensureRepoLicenseForRestore` at :1542, reached from the executor seam.
- The tier decision survived regeneration:
`packages/shared/src/renet-contract/data/license-tiers.generated.ts:25` reads `"backup_restore": { tier: "none", pending: false }`.
- RUN HERE: `npx vitest run --root packages/cli src/services/__tests__/local-executor-restore-license.test.ts`
exits 0 with 15 of 15 passing. It covers the plan's T1 to T5 and adds three guards against the "any licence on the box will do" trap: an unrelated licence still issues, the right guid in the WRONG datastore scope still issues, and a non-runtime-valid installed licence still issues.
- The size is derived from the manifest, though not where the plan put it:
`resolveRestoreSizeGb` at `packages/cli/src/services/executor/local-executor.ts:521` fetches the manifest and rounds up, rather than being threaded down from `backup.ts`.

TWO LEFTOVERS, both named by the plan itself. Checklist item 6 is not done: `private/renet/cmd/renet/backup_restore.go:359-360` still reads "that case needs a CLI-side issue-before-restore and is called out as a separate decision", describing as open a decision that has since been implemented, which is the exact stale-comment failure the plan's F4 warned about. Checklist item 9 is
not done: there is no restore scenario in `.ci/scripts/private/license-e2e.sh` and the backup drill's leg d is still host-only, so the one test the plan called "the only test in the repo that would have failed before this fix" was never written. The only proof today is the 15 unit tests.

## Lessons
- "Does the machine hold a licence" is the wrong question, and answering it the easy
way ships a worse bug than the one being fixed: `rdc backup restore --up` then runs `repository_up`, which resolves the licence guid-specifically with no fallback, so a carrier licence produces "the restore succeeded and the repo will not start". The licence must be for the SOURCE guid in the TARGET datastore's scope.
- A failure that does not use the product's own error signal is invisible to the
product's own recovery machinery. This one returned a plain string instead of exit-10 LICENSE_REQUIRED, so every existing licence-recovery path walked past it.
- A comment describing a decision as open outlives the decision. Item 6 is still in
the tree saying the fix is undecided, next to the fix.
- Unit tests over a mocked executor are the right level for this and still cannot see
the failure a bare machine would produce. The plan ranked the drill leg as the highest-value test and it is the piece that was dropped.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:10Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/cmd/renet/backup_restore.go, private/renet/pkg/license/store.go, packages/cli/src/services/executor/local-executor.ts, private/account/src/services/subscription.service.ts, private/account/src/services/backup-storage.service.ts, private/account/src/services/backup-chunk-store.ts, private/renet/pkg/chunkstore/session.go, private/account/src/routes/backups.ts, packages/cli/src/commands/backup.ts, private/renet/pkg/license/tiermap.go, private/renet/pkg/functions/executor_local.go, packages/cli/src/services/renet/renet-license-contract.ts, packages/cli/src/services/account/license.ts, private/account/src/routes/license.ts, private/renet/pkg/functions/commands/registry.go, packages/cli/src/services/config/config-resources.ts, packages/cli/src/commands/machine/register.ts, packages/cli/src/commands/__tests__/backup-restore-datastore.test.ts, packages/shared/src/subscription/constants.ts
Gates: none
Why-Source: auto
Read-History: `git show 65118820f452478aba55580152843d0a14188c75` recovers the text; `git log --find-object=65118820f452478aba55580152843d0a14188c75 --all` names the commit

## History
- 2026-09-06T17:06:10Z compacted by 8f55d4f0 from `draft` (record-sig e9455a6c)

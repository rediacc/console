# PLAN: the 14 packages/cli files over the 512-line budget are split by responsibility
Status: executing
Depends-On: no-dep -- pure refactors inside packages/cli
Owner: d778be9d
Updated: 2026-10-31
Epic: 9f92c43e (worklist #ff741c9a)
Priority: P1 -- check:ci-max-lines is red on 1023-1, which blocks ci:quick and the push
Concurrency: parallel -- four writers own disjoint file groups (S1-S4)
Live-Proof: bench -- the CLI is the surface; the split changes no behaviour, and the vm:check run before the push drives the CLI against real machines
Owns: agent/plans/PLAN-split-cli-files-over-512-line-budget.md, packages/cli/src/commands/backup-image*.ts, packages/cli/src/commands/backup-storage*.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-*.ts, packages/cli/src/commands/doctor*.ts, packages/cli/src/commands/repo-create-delete*.ts, packages/cli/src/commands/repo-fork*.ts, packages/cli/src/remote/sftp/**, packages/cli/src/services/backup-image/**, packages/cli/src/services/executor/**, packages/cli/src/services/jobs/**, packages/cli/src/**/__tests__/** (import paths only)

## Context
`npm run check:ci-max-lines` (scripts/gates/check-max-lines.ts) counts code lines, blank and comment lines excluded, against a 512 budget. On 2026-10-31 it lists 14 files: packages/cli/src/commands/backup-image.ts 615, backup-storage.ts 592, backup.ts 568, doctor.ts 532, repo-create-delete.ts 552, repo-fork.ts 577; packages/cli/src/remote/sftp/client.ts 559; packages/cli/src/services/backup-image/transfer.ts 736; packages/cli/src/services/executor/detached-execution.ts 580, job-client.ts 521, license-recovery.ts 554, local-executor.ts 554; packages/cli/src/services/jobs/plans.ts 765, steps.ts 924. None is exempt.

## Decision
Split each file by responsibility into sibling modules: no behaviour change, no new abstraction, no exemption. The original file keeps its public exports (re-exporting moved symbols) wherever callers import from it, so no caller outside the group needs an edit; tests that import a moved private symbol switch to the new path. Each new module stays under 512 code lines and carries the same comment density as the original.

## Boxes
- [ ] S1 commands: backup-image.ts, backup-storage.ts, backup.ts, doctor.ts, repo-create-delete.ts, repo-fork.ts each under 512. Accept: `npm run check:ci-max-lines` lists none of them; `cd packages/cli && npx vitest run src/commands && npx tsc --noEmit -p tsconfig.json`
- [ ] S2 remote and backup-image: remote/sftp/client.ts and services/backup-image/transfer.ts under 512. Accept: `npm run check:ci-max-lines` lists neither; `cd packages/cli && npx vitest run src/remote src/services/backup-image`
- [ ] S3 executor: detached-execution.ts, job-client.ts, license-recovery.ts, local-executor.ts under 512. Accept: `npm run check:ci-max-lines` lists none; `cd packages/cli && npx vitest run src/services/executor`
- [ ] S4 jobs: plans.ts and steps.ts under 512. Accept: `npm run check:ci-max-lines` lists neither; `cd packages/cli && npx vitest run src/services/jobs src/commands/__tests__/repo-set-rerender.test.ts src/commands/__tests__/job-plan-repo.test.ts`
- [ ] V1 The gate is green and the CLI suite passes. Accept: `npm run check:ci-max-lines` rc 0; `cd packages/cli && npx vitest run src` rc 0; `npx tsc --noEmit -p packages/cli/tsconfig.json` rc 0

# Handoff checklist: backup-storage
Status: executing
Owner: 97604f47

## Deliverables
- [x] d1 file:docs/backup-storage/README.md
- [x] d2 file:docs/backup-storage/01-verified-context.md
- [x] d3 file:docs/backup-storage/02-design.md
- [x] d4 file:docs/backup-storage/03-implementation-map.md
- [x] d5 file:docs/backup-storage/04-testing-and-local-loop.md
- [x] d6 file:docs/backup-storage/05-docs-and-decommission.md
- [x] d7 file:docs/backup-storage/06-execution-guide.md
- [x] d8 file:docs/backup-storage/PROMPT.md
- [x] d9 file:~/.claude/projects/-home-muhammed-monorepo-console/programs/backup-storage/MANIFEST.md

## Waves
- [x] w1 Wave 0: probes, instruments, and in-path defect fixes
- [x] w2 Wave 1: renet chunk engine + account control plane (parallel writers)
- [x] w3 Wave 2: CLI/schema surfaces + portal quota UI (parallel writers)
      UNTICKED 2026-08-15 (RE-APPLIED after a silent revert, see 07 §9.17):
      (a) `04-testing-and-local-loop.md:96` claimed the portal quota page smoke
      rides deploy-preview/smoke-test-preview; it did not, so BackupStorage.tsx
      (router.tsx:269) had NO coverage. **FIXED**: `stepQuotaPageShipped` in
      `.ci/scripts/test/smoke-test-preview.ts` now asserts the SERVED BUNDLE
      still carries the `backup-storage` route — a 200 on the route proves
      nothing, because the portal is a single-page app.
      (b) `backup strategy set` could not create the only destination kind the
      generator accepts. **FIXED** and verified. Re-tick once (a) has run green
      against a real preview deployment.
- [x] w4 Wave 3: test battery (vitest + drill, e2e byte-verify)
      UNTICKED 2026-08-15 (RE-APPLIED after a silent revert): the battery runs,
      but the control `06-execution-guide.md:49-51` calls non-negotiable was
      never built. No corruption-injection helper exists anywhere (no
      flipByte/corruptChunk/injectCorruption under packages, scripts or .ci), so
      nothing proves chunk verification can FAIL — 'a battery that cannot fail is
      not a battery', by this program's own words. Separately, e2e suite 26 is
      gated behind BACKUP_STORAGE_SUITE=1, which NO workflow sets.
- [x] w5 Wave 4: English docs and claims reconciliation, then Sonnet translations
      UNTICKED 2026-08-15 (RE-APPLIED after a silent revert): English is now
      corrected (backup-restore.md no longer denies a shipped chunk restore;
      limits.md no longer claims no retention is enforced and carries the plan
      quotas), but the 12 non-English locales are still stale against it —
      validate-translation-freshness exits 1. Re-tick when they land.
- [x] w6 Wave 5a: the credential-free half — cutover preflight (read-only, fails
      closed, proven both directions) + docs/backup-storage/08-cutover-runbook.md
- [x] w7 Wave 5b-i: the PROBE BUCKET leg. `rediacc-backups-probe` created in R2
      (HEAD 404 before, 200 after; the probe name, never the bare
      `rediacc-backups`), and `scripts/backup-cutover-preflight.sh` run against
      it: 6 checks, all passed — the first time that preflight has ever passed
      with a real store. The bucket immediately earned its keep: the tier-B
      delete probe found a latent data-loss defect in `deletePrefix` (string
      prefix matching destroying a sibling lineage), now fixed.
- [ ] w8 Wave 5b-ii: the REMAINING credentialed legs, still operator-only —
      set the four ACCOUNT_BACKUP_S3_* Worker secrets, add the bucket-scoped
      cf-r2-backup rotation slug, then migrate real machines and cut over.
- [x] w9 Decommission: CLI restore proven, so on the operator's instruction the
      rclone/OneDrive emission was DELETED (not deprecated). The preflight
      interlock was inverted to match: it now fails if the emission still
      returns. 2353 tests pass, lint:unused cleared of all 19 campaign findings.
      See 07-execution-record.md §9.

<!--
w6 was originally ONE row reading "integration, migration of real machines,
cutover, decommission". It was split rather than ticked, because ticking it
would have recorded migration, cutover and decommission as DONE when no machine
has been migrated, nothing has been cut over, and rclone is still the only way
to get data back. The credential-free half is genuinely complete; the rest is
not mine to do. A handoff checklist that overstates is worse than one that is
merely incomplete: the next session reads it as ground truth.
-->


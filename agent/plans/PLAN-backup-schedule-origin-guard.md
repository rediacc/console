# PLAN: a repo change never silently re-points a machine's backup units at another account server

Status: proposed -- found 2026-11-16 while running the console#522 spike on hostinger; awaiting operator approval
Owner: e0f36861
First-Seen: 2026-11-16
Depends-On: no-dep -- PLAN-hostinger-to-bench.md moves hostinger's units on purpose with --adopt-origin; this plan only stops an implicit move, and it is correct before, during and after that move
Priority: P1 -- a repo create, delete, fork, rename, promote or migrate through the wrong config rewrites production backup units so that renet refuses every scheduled run; today only an in-flight backup prevented it
Concurrency: parallel -- touches the schedule push path only
Owns: agent/plans/PLAN-backup-schedule-origin-guard.md, packages/cli/src/services/backup/backup-schedule.ts, packages/cli/src/services/backup/backup-schedule-reconcile.ts, packages/cli/src/services/backup/repo-change-hook.ts, packages/cli/src/services/backup/__tests__/backup-schedule-origin-guard.test.ts, packages/cli/src/i18n/locales/**
Live-Proof: hostinger -- the schedule push under packages/cli/src/services/backup is the cli surface, and hostinger is the machine whose units carry the production origin today

## Ask

On 2026-11-16 at 07:35Z `./rdc.sh --config eu-bench repo create vscode-spike -m hostinger --size 4G` finished with "Backup schedule on hostinger was not re-rendered after the repository change: Cannot deploy: backup(s) currently running: nightly-hot.repo.mail.latest". The repo command had started a full schedule push on its own, with the eu-bench config's account server, against a production machine whose six units carry `--expect-account-server https://eu.rediacc.cloud` and whose licences come from eu. Had the mail backup not been running, every unit would have been rewritten to expect bench, and renet would then refuse the eu licences at the next 03:00 run (private/renet/cmd/renet/backup_endpoints.go:155-176). The same path runs on every repo delete, so the spike repo cannot be torn down through eu-bench either. A schedule's account-server origin should only change when someone asks for it.

## Context (checked 2026-11-16 against the tree and on hostinger)

1. `reconcileSchedulesAfterRepoChange` runs `pushBackupSchedule` whenever the active config lists backup strategies for the machine (packages/cli/src/services/backup/backup-schedule.ts:270-292), and warns rather than throws on failure.
2. It is called through `reconcileBackupSchedules` (packages/cli/src/services/backup/repo-change-hook.ts:9-10) from repo create/delete (packages/cli/src/commands/repo-create-delete-teardown.ts:98), repo fork, repo promote, repo migrate, backup image deps and the jobs step runner (`grep -rln repo-change-hook packages/cli/src`).
3. The origin written into each unit is the active config's subscription server: `accountServerForRenet(sftp, remoteRenetPath, expectedAccountServerOrigin())` (packages/cli/src/services/backup/backup-schedule.ts:506), and `expectedAccountServerOrigin()` is `originOf(getSubscriptionServerUrl())` (packages/cli/src/services/backup/backup-store-universe.ts:54-55). The units on the machine are never read for their current origin.
4. Measured on hostinger 2026-11-16: `grep -ho "expect-account-server[= ][^ ]*" /etc/systemd/system/rediacc-backup-*.service | sort | uniq -c` gives `6 expect-account-server https://eu.rediacc.cloud`. The eu-bench config resolves to bench.
5. The only thing that stopped the rewrite was the in-flight gate (`applyInFlightGate(plan, options.force ?? false)`, packages/cli/src/services/backup/backup-schedule.ts:~511).
6. The deliberate move exists and is named: `rdc --config eu-bench subscription refresh -m hostinger --adopt-origin` re-licences, and PLAN-hostinger-to-bench.md Context 4 notes that an eu-bench push replaces the eu units in place, as intended once its re-licence step has run.
7. `eu-remote` cannot be used as the safe path today: `./rdc.sh --config eu-remote machine list` answers "The account server did not renew this device's config token (... accept them at https://eu.rediacc.cloud/account/terms, then run the command again.)".

## Design

1. Before any push, read the deployed units' `--expect-account-server` values over the same SFTP session. If any deployed origin differs from the config's origin, the push refuses with a message naming both origins and the machine, and changes nothing.
2. The implicit re-render after a repo change follows the same rule and stays best-effort: on an origin mismatch it skips with that message instead of pushing, so the repo verb still succeeds and a delete can no longer rewrite production units.
3. An explicit `rdc backup schedule -m <machine> --adopt-origin` is the one way to change the origin, mirroring `subscription refresh --adopt-origin`. Clean break: no environment switch and no silent fallback.
4. A machine with no deployed units, or units with no origin flag (older renet), has nothing to protect and pushes as today.

## Boxes

- [ ] G1 [writer] Unit test that fails today: a push whose config origin is bench against deployed units naming eu writes units (red), then refuses with both origins named (green); a repo-change re-render under the same mismatch skips without writing. Accept: `cd packages/cli && npx vitest run src/services/backup/__tests__/backup-schedule-origin-guard.test.ts` rc 0, and the same test against the unfixed tree fails
- [ ] G2 [writer] Implement Design 1-4 in backup-schedule.ts and backup-schedule-reconcile.ts, add `--adopt-origin` to `backup schedule`, i18n for the new messages across locales. Accept: `npm run ci -- --narrow` rc 0
- [ ] G3 [live] On hostinger through eu-bench: a repo create and delete of a scratch repo leave all six units on `https://eu.rediacc.cloud` and print the skip message. Accept: the grep from Context 4 still prints `6 expect-account-server https://eu.rediacc.cloud` after both verbs
- [ ] LP-hostinger [live] Fresh hostinger receipt after G2 lands.
  Accept: live-proof hostinger renet-live

## Risks

- PLAN-hostinger-to-bench's schedule step must pass `--adopt-origin` once this lands; its C-boxes should be checked for a plain `backup schedule` call when G2 merges.
- Reading units costs one extra remote command per push, negligible next to the push itself.

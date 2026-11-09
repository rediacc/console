# PLAN: the defects the 2026-11-07 hostinger restart cycle found are fixed at their roots

Status: approved -- operator standing order 2026-11-06 "continue for ALL the remaining jobs"; finding #5e864374, designed by a Plan agent on 2026-11-07
Depends-On: no-dep -- fixes of landed renet and CLI code found on the production machine; no other plan's output is needed
Owner: d778be9d
Priority: P1 -- each defect hit the production machine during the H4 cycle of PLAN-health-checks-local
Owns: agent/plans/PLAN-renet-restart-cycle-defects.md, private/renet/pkg/filesystem/permissions.go, private/renet/pkg/filesystem/permissions_test.go, private/renet/pkg/orchestration/lifecycle.go, private/renet/pkg/orchestration/lifecycle_test.go, private/renet/cmd/renet/repository_ownership.go, private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/hashes.json, private/renet/cmd/renet/daemons_upgrade.go, private/renet/cmd/renet/daemons_upgrade_test.go, private/renet/cmd/renet/job_commands.go, private/renet/cmd/renet/job_commands_sections_test.go, private/renet/cmd/renet/main.go, packages/cli/src/services/jobs/**, packages/cli/src/commands/job.ts, packages/cli/src/i18n/locales/*/cli.json, private/renet (gitlink bump only)
Concurrency: parallel -- defect 1 (filesystem, lifecycle, ownership command, renet i18n), defect 3 (daemons_upgrade) and defect 4 (CLI jobs plus the renet claim exit code) touch disjoint files; renet i18n belongs to the defect 1 writer only
Live-Proof: hostinger -- the remaining restarts of the H4 cycle (mautic first) run on the landed renet
Updated: 2026-11-07
First-Seen: 2026-11-07
Worklist: #5e864374, PR-TASK 09b8bdfa

## Finding

- Defect 1: `prepareLifecycleTree` (private/renet/pkg/orchestration/lifecycle.go:292-309) already re-owns root-owned files before an unprivileged up(), but `chownEntry` (private/renet/pkg/filesystem/permissions.go:286-288) skips any directory not owned by root, so root-owned files under a 7111-owned directory stay root (marketing n8n: 3047 files, EACCES crashloop; mautic apache/ports.conf).
- Defect 2: the list-all sections pattern rejected hyphens (private/renet/cmd/renet/job_commands.go:906), so `machine status --containers` failed.
- Defect 3: `recoverRepoContainers` (private/renet/cmd/renet/daemons_upgrade.go:557-607) starts the containers once against the ids of the first listing, folds "No such container" errors from recreated containers into the result, and waits against a fixed deadline with a 2-minute floor.
- Defect 4: a `starting` ticket was never checked when the defect was found, because `resolveStarting` was unwired in remote-deps.ts; it is checked now by `resolveStartingTicket` (packages/cli/src/services/jobs/finished-notice.ts:140-166) through `resolveStarting`, wired at packages/cli/src/services/jobs/remote-deps.ts:119 and :152, and, as found, a finished ticket whose step cannot run stayed pending with no age limit (D4 below added the 7-day expiry).
- Defect 5: `renet version` printed no trailing newline.

## Boxes

- [x] D2 list-all accepts hyphenated lowercase section names, with a table test of the CLI's sections string and injection-shaped values
    (ticked) 2026-11-07T06:46:51Z by d778be9d: commit:d82ce6f6a rc=0 landed and tested on the combined line (go test cmd/renet rc 0; vitest 395 passed; tsc rc 0)
- [x] D5 `renet version` ends in a newline (`versionLine`), with a test
    (ticked) 2026-11-07T06:46:52Z by d778be9d: commit:d82ce6f6a rc=0 landed and tested on the combined line (go test cmd/renet rc 0; vitest 395 passed; tsc rc 0)
- [x] D1 a one-time deep re-own (`ChownRootOwnedDeep`) descends directories owned by root or the target uid, skips other uids, writes an undo manifest, runs once behind `.rediacc/state/ownership-v2`; `renet repository ownership --root-owned [--dry-run|--undo]`; Go tests per the design
    (ticked) 2026-11-07T06:48:55Z by d778be9d: commit:2a8ebbe20 rc=0 renet c189652 997c2b6 6f5c397 via d82ce6f6a; go test rc 0; sudo pytest tests/integration/test_repository_ownership.py -k root_owned rc=0 (1 passed) on renet afc70f1
- [x] D3 `recoverRepoContainers` retries starts per current id, ignores "No such container", matches by compose labels then name, recomputes the deadline and extends it on progress, floor 5 minutes; Go tests per the design
    (ticked) 2026-11-07T06:46:53Z by d778be9d: commit:d82ce6f6a rc=0 landed and tested on the combined line (go test cmd/renet rc 0; vitest 395 passed; tsc rc 0)
  (corrected 2026-11-07, review 4504214e.1) D3's landed code commits are in the private/renet submodule: 73b41c1 (recover repo containers by progress, labels and last start error) and 69b9322 (the daemons-restart argv comment), both reaching the console through the pointer bump d82ce6f6a that the tick cites.
- [x] D4 tickets gain an `expired` event; starting tickets older than 10 minutes resolve through `renet job list --request-id`; finished tickets older than 7 days expire; `job claim` on a missing job exits 16; `rdc job dismiss <id...>|--stale`; vitest and Go tests per the design
    (ticked) 2026-11-07T06:46:54Z by d778be9d: commit:e573d1e0d rc=0 landed and tested on the combined line (go test cmd/renet rc 0; vitest 395 passed; tsc rc 0)
  (corrected 2026-11-07, review 4504214e.2) D4's `job claim` exit-16 half is in the private/renet submodule: 85aa590 (job claim on a missing job exits 16) and afc70f1 (the claim error carries the spool's own message), reaching the console through the pointer bump d82ce6f6a; e573d1e0d, cited in the tick, carries the ticket expiry and `rdc job dismiss` half.
- [ ] L1 hostinger: the remaining restart cycle runs on the landed renet and mautic's up() succeeds without a manual chown

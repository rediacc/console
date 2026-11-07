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
- Defect 4: a `starting` ticket is never checked (packages/cli/src/services/jobs/finished-notice.ts:90-96, `resolveStarting` unwired in remote-deps.ts:86), and a finished ticket whose step cannot run stays pending with no age limit.
- Defect 5: `renet version` printed no trailing newline.

## Boxes

- [ ] D2 list-all accepts hyphenated lowercase section names, with a table test of the CLI's sections string and injection-shaped values
- [ ] D5 `renet version` ends in a newline (`versionLine`), with a test
- [ ] D1 a one-time deep re-own (`ChownRootOwnedDeep`) descends directories owned by root or the target uid, skips other uids, writes an undo manifest, runs once behind `.rediacc/state/ownership-v2`; `renet repository ownership --root-owned [--dry-run|--undo]`; Go tests per the design
- [ ] D3 `recoverRepoContainers` retries starts per current id, ignores "No such container", matches by compose labels then name, recomputes the deadline and extends it on progress, floor 5 minutes; Go tests per the design
- [ ] D4 tickets gain an `expired` event; starting tickets older than 10 minutes resolve through `renet job list --request-id`; finished tickets older than 7 days expire; `job claim` on a missing job exits 16; `rdc job dismiss <id...>|--stale`; vitest and Go tests per the design
- [ ] L1 hostinger: the remaining restart cycle runs on the landed renet and mautic's up() succeeds without a manual chown

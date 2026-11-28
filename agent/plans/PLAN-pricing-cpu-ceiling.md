# PLAN: pricing CPU ceiling: every licence issuance and renewal reports the machine's logical CPUs, the server applies the tier ceiling with a 30-day grace, and paid tiers buy large-machine passes

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md -- PM1 adds `maxCpusPerMachine` and the pass constants, PM2 the resolver the passes register into
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the free offer protects revenue only once large machines are gated
Concurrency: parallel -- private/account/src/services/subscription.service.ts (issueRepoLicense, issueRepoLicenseBatch, renewRepoLicense, claimMachineSlotHard and touchActivationSoftClaim only) is shared with PLAN-pricing-seat-repo-caps.md and PLAN-pricing-billing-upgrade.md; packages/cli/src/services/account/license.ts may sit in PLAN-executor-account-routes.md's EA4 (the licence callers back on accountServerFetch); block_plan_concurrency serializes writers on both
Owns: agent/plans/PLAN-pricing-cpu-ceiling.md, private/renet (gitlink bump only), private/renet/pkg/list/system.go (the CPU count only), private/renet/pkg/license/renew.go (the request body only), private/renet/cmd/renet/repository_license_status.go (the scan output only), private/renet/pkg/subscription/types.go, private/account (gitlink bump only), private/account/src/services/subscription.service.ts (the five functions named under Concurrency), private/account/src/services/machine-cpu.service.ts (new), private/account/src/services/machine-pass.service.ts (new), private/account/src/routes/machine-passes.ts (new), private/account/src/routes/root-machine-passes.ts (new), private/account/drizzle/*_machine_cpu.sql (new), private/account/src/db/schema.ts (the two new tables only), private/account/web/src/pages/Machines.tsx, private/account/web/src/i18n/locales/*/machines.json, packages/cli/src/services/account/license.ts (the request body only), packages/cli/src/services/account/license-machine.ts (the scan field only), packages/cli/src/i18n/locales/*/cli.json (the CPU messages only), private/account/tests/integration/cpu-ceiling.test.ts (new)
Live-Proof: bench, hostinger -- bench runs the account worker's ceiling, grace and pass logic; hostinger is the renet target whose real CPU count is reported and judged

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Ceilings in logical CPUs (what the OS reports; hyperthreads and VM vCPUs count): FREE, COMMUNITY and free Professional 16, Professional 32, Business 64, Enterprise unlimited.
- R2. Over the free ceiling: a warning for 30 days, then new repositories, forks and licence issuance on THAT machine are refused. Running systems, start/stop, backups, restores and teardown are never blocked.
- R3. Large-machine pass for paid tiers: +8 CPUs on one named machine, $50/month or $200/year; at most 4 passes per machine; at most 3 machines with passes per subscription; beyond that, Enterprise.
- R4. CPU reporting goes through licence validation, NOT telemetry: the telemetry opt-out must neither stop it nor be broken by it (legal research 2026-11-27: GDPR Art 6(1)(b)/(f), ePrivacy "strictly necessary" exemption). Only the count and the existing machine identifier are sent.

## Finding (verified 2026-11-27)

- renet already reads the count: private/renet/pkg/list/system.go:53 (`runtime.NumCPU()`, which follows process affinity, so `taskset` lowers it) and /proc/cpuinfo at :175; it surfaces as `cpu_count` in machine status only. Nothing reports it to the account server.
- The floating-licence slot is claimed only on issuance (private/account/src/services/subscription.service.ts:1602, claimMachineSlotHard) and soft-touched on renewal (:1718, touchActivationSoftClaim, never refuses); renewal itself is :1166. Those are the only points where the server sees a machine, so the ceiling is judged per machine there, never per slot.
- renet's tier map already separates create from operate: `repository_create` and `repository_fork` are TierRepoLicenseCreate (private/renet/pkg/license/tiermap.go:74, :78), so refusing issuance blocks exactly R2's set and nothing it protects.
- The CLI issues through renet's `repository license-scan` (packages/cli/src/services/account/license-machine.ts) and `/licenses/activate-repo` (packages/cli/src/services/account/license.ts); renet renews by itself through its renewal URL (private/renet/pkg/license/renew.go).
- The machine fingerprint is private/renet/pkg/license/machineid.go:45; the ceiling keys on that machineId.

## Design

1. **Count.** renet reports online logical CPUs from `/sys/devices/system/cpu/online` (falling back to NumCPU), in the license-scan output and in the renewal body; the CLI forwards it in the activate-repo body. A missing count (an old renet) is treated as within the ceiling, with an event-log line, so an upgrade never strands a user.
2. **State.** `machine_cpu_state` (subscription_id, machine_id, cpu_count, first_over_at, last_seen_at): upserted on every issuance and renewal. `first_over_at` is set when the count first exceeds the effective ceiling and cleared when it drops back.
3. **Ceiling.** effective = tier ceiling (PM1) + 8 x passes on that machine. Issuance on a machine over the ceiling succeeds with a `cpuCeiling` warning block (count, ceiling, grace end) while `now < first_over_at + 30 days`, and is refused `CPU_CEILING_EXCEEDED` (403) after. Renewal is never refused (R2), it only updates the state.
4. **Passes.** `machine_passes` (id, subscription_id, machine_id, count 1-4, term monthly|annual, starts_at, ends_at, created_by). Limits enforced on write: at most 4 per machine, at most 3 machines per subscription, paid tiers only. Customer route to request passes (invoiced through PLAN-pricing-billing-upgrade.md's invoice path once it lands; until then created by root only), root route for the admin UI and root API tokens.
5. **Messages.** CLI and portal Machines page print the R2 copy: count, ceiling, days left, that running systems and backups are unaffected, and the upgrade and pass paths.
6. **Licence field.** The signed licence carries `maxCpusPerMachine` for the record; renet does not enforce it (the server does), so an offline renet is never stopped by it.

## Tasks

- [x] CC1 [writer] renet: Design 1 count in system.go, the license-scan field, the renewal body field, types.go `maxCpusPerMachine`; Go tests with a fake sysfs (controls first: affinity-limited process still reports the online count).
  Accept: `cd private/renet && go test ./pkg/list/... ./pkg/license/... ./pkg/subscription/...` rc 0 and `npm run check:ci-renet-types` rc 0
    (ticked) 2026-11-27T13:42:29Z by d778be9d: commit:5e311a7ab4; CC1 online cpu count (renet efb28a04, schema 25dabc9857); renet go test rc 0 landed, check:ci-renet-types rc 0
- [ ] CC2 [writer] account: migration and tables per Design 2 and 4, machine-cpu.service.ts and the issuance/renewal hooks per Design 3; integration tests, controls first (renewal over the ceiling succeeds; a running repo's renewal after grace succeeds; issuance after grace refused; a missing count passes).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/cpu-ceiling.test.ts` rc 0
- [ ] CC3 [writer] passes: machine-pass.service.ts and both routes per Design 4 with tests for the 4-per-machine and 3-machine limits and the paid-tier rule.
  Accept: `cd private/account && npx vitest run tests/integration/cpu-ceiling.test.ts` rc 0
- [ ] CC4 [writer] CLI and portal: the activate-repo body field, the Design 5 messages, English first and the other locales through the i18n pipeline.
  Accept: `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0, `cd private/account/web && npx tsc --noEmit` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after CC2 and CC3 land.
  Accept: live-proof bench account-smoke
- [ ] LP-hostinger [live] Install the branch's renet on hostinger and run the live renet check after CC1 lands.
  Accept: live-proof hostinger renet-live machine=hostinger
- [ ] CC-L1 [live] eu bench with hostinger: a test subscription with a ceiling temporarily set below hostinger's count issues with the warning, its `first_over_at` back-dated 31 days refuses a new create while `up` and a backup of an existing repo succeed, and one pass covering the gap restores issuance.
  Accept: the transcripts with their rc recorded under `## Outcome`

## Outcome

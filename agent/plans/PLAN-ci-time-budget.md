# PLAN: CI time budget. Every job finishes in 15 minutes or less, and the pipeline in 20 minutes or less (operator spec W)

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: the spec-X plan (Priority/Concurrency/Owns header grammar; the lead fills in the file name) -- the spec's suggested order is Y, X, W, Z, and P2 of this plan fans out 3-4 writers across `.github/workflows/**`, which needs X's Owns-overlap refusal to be safe.
Priority: P1 -- AI-proposed. It turns every later CI round into a 15-20 minute wait instead of 45-70 minutes, but it is not a correctness fix.
Concurrency: parallel
Owns: .ci/scripts/ci/watchdog-monitor.cjs, .github/workflows/watchdog-monitor.yml, .github/workflows/ct-tests.yml, .github/workflows/ci-ops-test.yml, .github/workflows/ci-quality.yml (quality-security, quality-complete and new lanes only), .github/workflows/ci.yml (needs:, timeout-minutes and validate-promote only), scripts/ci-runner/lanes.ts, scripts/ci-runner/run.ts, scripts/gate-bind.ts, scripts/gates/check-lane-budget.ts, scripts/gates/check-quality-complete.ts, scripts/ci/write-shard-receipt.cjs, .ci/rediacc_ci/ci/budget_report.py, .ci/rediacc_ci/private/run_renet.py, .ci/rediacc_ci/private/run_account.py, .ci/rediacc_ci/check_pytest.py, .ci/rediacc_ci/battery.py, .ci/rediacc_ci/deploy/simulate_promotion.py, .ci/scripts/test/run-e2e.sh, .ci/scripts/test/run-account-e2e.sh, .ci/tutorials/run-sequence.sh, .ci/config/lane-durations.json
Worklist: (to be assigned)

**Operator order, 2026-09-25 (spec W, verbatim):** "Target: every CI job finishes in 15 minutes or less, and the whole pipeline in 20 minutes or less." The spec also asks for:
1. a watchdog that works in phases;
2. measurement first;
3. a split of every job over 12 minutes, using `npm run ci`'s pool and the gates.lock lanes, including private/account and private/renet;
4. a lane-duration gate;
5. a before-and-after table.

**Overlap with spec Z.** Z removes the GitHub review job, and so the `Review Complete` required check. W must not touch that check or `CI Complete`. The two plans overlap on `.github/workflows/ci.yml`, so X's Owns rule serialises them.

**Line numbers** refer to console `20fc068c5` (2026-09-24), renet `c27d3ba` and account `a7d51cc`.

---

## 0. How this was measured (read-only)

- **Runs.** `gh run list --workflow ci.yml --branch main --status success -L 15` returns 15 green **push** runs from 2026-09-05 to 2026-09-07. It is 18 days since main was last green: every scheduled run since 2026-09-16 is `failure`, the latest being 36100355555. Push-to-main runs **no test suites**, because `full_suite` is `github.event_name != 'push'` (`.ci/scripts/ci/watchdog-monitor.cjs:70-72` comment). So main alone cannot measure the heavy jobs. Four samples are used:
  - **A.** The 15 green main push runs above (release chain).
  - **B.** 13 green PR runs plus 2 green schedule runs, 2026-08-31 to 2026-09-16 (full suite).
  - **B1.** The 7 of B that passed on attempt 1, used for critical-path offsets (35088917765, 35078358179, 33504819281, 33463226264, 33448444151, 33439968463, 33475880587).
  - **C.** Every `success` job in the 60 CI runs created since 2026-09-14, whatever the run's conclusion. It reflects the tree after the rediacc_ci port.
- **Wall time** = `completed_at - started_at` per job, successful jobs only. Queue time was measured separately: median 0.0-0.2 min.
- **Step and per-test breakdowns** come from `gh run view --log` on run 36040274865 (2026-09-24) and the step API on 33504819281 and 35128695736. Older job logs return HTTP 410.
- **Nothing was rerun, cancelled or dispatched.**

## 1. Measured before

### 1a. Jobs over 12 minutes, or whose max breaks 15 (median / max, minutes)

| Job (API display name) | B median | B max | C median | C max | Over 12? | Dominant cost (source) |
|---|---|---|---|---|---|---|
| Tests + Infra / E2E Workers (opensuse-16.0) | 42.2 | 43.9 | 43.4 | 53.8 | yes | VM prep 7.0, tests 27.9 (36040274865 log) |
| Tests + Infra / E2E Workers (ubuntu-24.04) | 36.7 | 50.5 | 41.6 | 50.6 | yes | setup 7.9 (Free Disk Space 4.5), VM prep 6.3, tests 27.4 |
| Tests + Infra / E2E Workers (fedora-43) | 38.7 | 47.1 | 39.4 | 64.9 | yes | as ubuntu |
| Tests + Infra / E2E Workers (oracle-10) | 35.1 | 48.1 | 38.1 | 46.7 | yes | as ubuntu |
| Tests + Infra / E2E Workers (debian-13) | 28.2 | 43.0 | 29.3 | 40.5 | yes | as ubuntu |
| Quality / Security | 10.2 | 36.2 | **35.9** | 36.2 | yes (recent) | Python package tests 20.9-22.5, Quality-gate unit tests 10.1-12.9 |
| Tests + Infra / E2E K8s Multinode | 28.9 | 69.5 | 29.2 | 52.2 | yes | cluster bring-up 17.5, one test 10.9 |
| OPS Tests / OPS Provision (linux-amd64) | 28.7 | 51.1 | 28.8 | 28.8 | yes | tutorial sequence 21.8-24.3 |
| Tests + Infra / E2E Ceph Workers | 20.7 | 35.4 | 24.8 | 35.8 | yes | Ceph bring-up 15.2, tests 1.3 |
| Tests + Infra / E2E K8s Ceph | 23.9 | 39.2 | 23.5 | 35.8 | yes | Ceph bring-up 16.7, tests 4.0 |
| Tests + Infra / Account E2E | 20.6 | 22.6 | 20.3 | 20.7 | yes | one step, 19.5-25.9 |
| Tests + Infra / E2E Ceph | 18.3 | 31.3 | 19.4 | 28.4 | yes | Ceph bring-up 11.8, tests 2.3 |
| Tests + Infra / Renet | 17.3 | 17.8 | 17.2 | 18.9 | yes | integration pytest 12.7-12.9, go unit 2.5-3.2 |
| Tests + Infra / E2E K8s | 16.4 | 40.5 | 16.7 | 29.1 | yes | globalSetup 4.4, one test 7.3, prelude 4.5 |
| Tests + Infra / E2E Migrate | 13.1 | 42.6 | 15.8 | 27.0 | yes | Free Disk Space 2.5, boot group B 3.9, test 5.8 |
| Quality / Packages | 12.0 | 13.7 | 12.3 | 14.3 | yes, pending | Stop-hook worklist suite 7.5, since ported to pytest; 4.6 in 36040274865 |
| Validate Promotion (main, sample A) | 15.1 | 22.4 | -- | -- | yes | Simulate promotion 10.6-17.4 |
| Tests + Infra / Concurrent Fork Isolation | 11.4 | 12.8 | 11.4 | 23.1 | max only | Free Disk Space 2.1, provision 3.6 |
| Quality / Code | 10.7 | 13.2 | 10.9 | 13.7 | now sharded x4, legs 8.9 / 9.3 | Lint unit |
| Stage Artifacts (main, sample A) | 9.5 | 12.6 | -- | -- | max only | staging-release upload 3.5, R2 uploads 2.2 |
| Tests + Infra / Drills | 3.7 | 4.2 | 3.9 | 14.2 | max only | -- |
| Build (CLI) / CLI (win-arm64) | 3.2 | 11.4 | 3.8 | 12.1 | max only | setup-workspace |
| Build (Renet) / Renet (Full) | 2.9 | 11.6 | 3.0 | 16.9 | max only | full embed build |

Every other job (about 60 more) has a median under 6.5 and a max under 11 in every sample.

### 1b. Pipeline wall time and critical path

- **PR, full suite (B1, attempt 1):** `CI Complete` ends at a median of **55.9 min**, max 68.2. The critical path, with median offsets from run creation:
  1. `Initialize` 0 -> 2.4
  2. `Build (Renet) / Renet (cached)` -> about 7
  3. `Build (Docker Fast) / Server Docker (onprem amd64)` 8.9 -> 12.7
  4. `Tests + Infra / E2E Workers (opensuse-16.0)` 13.3 -> 55.0
  5. `CI Complete` 55.6 -> 55.9
- **The same tree's second path** ends at about 46.1:
  1. `Initialize`
  2. Quality (Packages ends 14.2)
  3. Review Gate 16.2 -> 16.4
  4. `OPS Tests / OPS Provision (linux-amd64)` 17.2 -> 46.1
- **The same tree's release path** ends at 30.9: build-renet, then build-cli, then build-docker, then `Stage Artifacts` 20.2 -> 26.3, then `Validate Promotion` 26.0 -> 30.9.
- **Main push (A, 15 runs):** median **43.8 min**, max 52.7. The path:
  1. `Initialize` 0.6
  2. `Renet (cached)` 0.8 -> 6.4
  3. `CLI (win-arm64)` 6.2 -> 9.2
  4. `Devcontainer (amd64)` 9.4 -> 15.8
  5. `Devcontainer Manifest` 16.6
  6. `Stage Artifacts` 17.1 -> 26.9
  7. `Validate Promotion` 27.0 -> 42.8
  8. `CI Complete` 43.1, then `Finalize Release Sentinel` 43.5, then `Pipeline Sentinel` 43.8

### 1c. Capacity (this decides whether the 20-minute pipeline is reachable)

- **Plan.** The org is on the **free** plan (`gh api orgs/rediacc` -> `plan.name: free`). It has 0 self-hosted runners, and its only runner group has `allows_public_repositories: false`.
- **Concurrency.** Peak concurrent Linux jobs in a full run was **19** (33504819281) and **17** (36040274865). Queue time p90 was 1.4 min, max 3.0. GitHub documents 20 concurrent standard jobs for Free, and these numbers match that ceiling. That 20 is shared by the whole org.
- **Runner time.** One full PR run is **80 jobs and 586 runner-minutes** (33504819281): 47 ubuntu-latest, 14 ubuntu-slim, 6 arm, 4 macOS, 3 macOS-intel, 6 Windows.

## 2. What the numbers say (four findings that shape the design)

1. **The 20-minute pipeline is arithmetically out of reach on the Free plan, with or without sharding.**
   - 586 runner-minutes over 20 runners is a 29-minute lower bound today, before any dependency staging.
   - Sharding adds fixed cost per leg. The projected after-state is about 720 runner-minutes, a 36-minute lower bound.
   - The per-job 15-minute target is reachable on any plan. The pipeline target needs decision D-W1.
2. **For 9 of the 15 over-budget jobs, fixed cost dominates, not test payload.**
   - VM prep plus cluster bring-up: 6.3 (Workers), 11.8 (Ceph), 15.2 (Ceph Workers), 16.7 (K8s Ceph), 17.5 (K8s Multinode).
   - Every shard pays this again, so sharding the four Ceph/K8s jobs buys nothing.
   - The lever is fixed-cost reduction: Free Disk Space, duplicate package builds, and restoring snapshots of prepared VMs and clusters. P2 does this before any sharding.
3. **About 10.5 minutes of the PR critical path is a `needs:` edge, not work.**
   - `tests` needs `build-docker-fast` (`.github/workflows/ci.yml:999`).
   - Hypothesis, to verify in T2.1: no ct-tests.yml leg consumes a docker-fast image. There is no `ghcr.io/rediacc` reference and no `*_tag` input in ct-tests.yml, and each leg builds renet and the CLI itself.
   - Similarly, `ops-tests` waits for quality and review-gate (`ci.yml:1043`), and `stage-artifacts` waits for all of build-docker, including the Devcontainer legs (`ci.yml:962`).
4. **Some measured long poles are single indivisible units.**
   - `kube/17-multinode-cluster.test.ts` has one 10.9-minute test.
   - `13-postgres-fork-isolation.test.ts` runs 8.1 minutes (59 tests, 11 describes).
   - `kube/15-k8s-repo.test.ts` is one 7.3-minute test.
   - `.ci/tutorials/run-sequence.sh:12-15` makes cross-tutorial machine state deliberate.
   - These need an explicit split rule or an operator ruling, not a shard count.

## 3. Decisions for the operator (with recommendations)

- **D-W1. Concurrency ceiling** (decides the pipeline target).
  - (a) GitHub Team plan, 60 concurrent jobs. *Recommended*: the per-seat cost is small against about 35 minutes saved per full run.
  - (b) Self-hosted KVM runners. This needs a public-repo runner group and fork-PR hardening.
  - (c) Keep Free and narrow PR scope. PRs run the two full-integration E2E Workers distros (ubuntu, fedora); all five distros run nightly and pre-merge. That cuts about 115 runner-minutes.
  - (d) Keep Free and accept a pipeline target of about 35 minutes.
  - The P3 gate reads the ceiling from `.ci/config/lane-durations.json` (`concurrency`), so this ruling is one number.
- **D-W2. The hard lane ceiling versus the existing headroom gate.** `check_job_timeout_headroom.py:42` requires `timeout >= 1.5 x observed max`. With `timeout-minutes: 15`, that means observed max <= 10, which contradicts a 12-minute lane ceiling. *Recommend:* for budgeted jobs, the lane gate (p90 <= 12, timeout <= 15) supersedes the headroom rule. Fold `job-timeout-baseline.json` (refreshed 2026-08-21 from one run) into `lane-durations.json`, so there is one duration source.
- **D-W3. Indivisible long tests.**
  - For K8s Multinode and K8s repo, *recommend* splitting each long test at a checkpoint into two tests that restore a cluster snapshot. Test code stays in `packages/e2e-tests`.
  - The alternative is a declared, gate-visible budget exemption list, which the operator must approve item by item.
- **D-W4. Tutorial sequence.** *Recommend:* PRs run 4 contiguous segments via `TUTORIAL_ONLY` (`.ci/tutorials/run-sequence.sh:23,73`), each on fresh VMs. The nightly also runs the 4 segments, plus a rotating "boundary pair" (the last tutorial of segment k followed by the first of k+1) to keep some cross-boundary state coverage. The full unbroken sequence can no longer fit 15 minutes. This trade has to be explicit, because renet#60 is exactly what the unbroken sequence caught.
- **D-W5. Enforcing on main push.** Cancelling a main push means no release that time (`CI Complete` fails, so finalize does not dispatch cd-v2). *Recommend:* enforce on PRs first, and flip main only after 5 consecutive main pushes under 20 in report mode.
- **D-W6. Early start for VM jobs.** Drop `quality`/`review-gate` from `ops-tests` needs (`ci.yml:1043`), and `quality` from `stripe-sandbox`. Those gates exist to avoid burning runners when Quality is red. The watchdog already force-cancels the run on a Quality failure, after the no-retry drain, so the saving is small and costs about 10 minutes of critical path. *Recommend:* drop them, and keep review-gate on stage-artifacts (release).

## 4. Phases

### P1: measure, and the watchdog in report-only mode (no behaviour change)

- [ ] T1.1 [A] **`.ci/rediacc_ci/ci/budget_report.py`**, wired as `npm run ci:budget-report`. It is read-only against the Actions API.
  - Selection: the last N green runs per class (pr-full, main-push, schedule). Attempt-1 jobs only for offsets; all attempts for durations.
  - Output: per-job median, p90 and max; queue p90; runner-minutes; peak concurrency.
  - Critical path: walks the `needs:` graph of ci.yml plus each reusable callee, mapping display names `caller / callee` the same way `check_job_timeout_headroom.py` refresh does its aliasing.
  - Emits the markdown tables in section 1 and JSON. It regenerates this plan's before-table; acceptance is within ±10% of section 1.
- [ ] T1.2 [A] **Budget detection in `.ci/scripts/ci/watchdog-monitor.cjs`.**
  - A pure `evaluateBudget({jobs, run, nowMs, jobBudgetMin, runBudgetMin, excludePatterns})`, in the `evaluate*` style of `evaluateCancelExemption` (`:83`).
  - It is called every poll right after the job fetch (the loop at `:1054`, the fetch at about `:1068`).
  - Job clock: `now - started_at` for in-progress jobs, and `completed_at - started_at` for jobs that finished over budget between polls.
  - Run clock: `now - run.run_started_at` for the current attempt, so a rerun starts a fresh clock and queue time counts.
  - Excluded: `WATCHDOG_EXCLUDE_PATTERNS` (`watchdog-monitor.yml:148`: Watchdog, CI Complete, Review Complete).
- [ ] T1.3 [A] **Report-only output.**
  - For each violation: `core.warning("CI BUDGET VIOLATION (report-only): '<job>' at <m>m, budget 15m")`, one annotation per job per generation.
  - A `$GITHUB_STEP_SUMMARY` table, and `budget-violations.json` uploaded as `ci-budget-<run>-gen<g>` from the existing upload step (`watchdog-monitor.yml:225` pattern).
  - New env in the monitor step (`watchdog-monitor.yml:128-175`): `WATCHDOG_BUDGET_MODE: report`, `WATCHDOG_JOB_BUDGET_MIN: '15'`, `WATCHDOG_RUN_BUDGET_MIN: '20'`.
  - In `report` mode the function **never** reaches `forceCancel` (`:888`).
- [ ] T1.4 [A] **Tests** in `.ci/rediacc_ci/tests/gates/test_gate_watchdog_budget.py`, next to the existing `test_gate_watchdog_*` suites, with a mocked `github`:
  - a job at 14:59 does not fire, and at 15:01 does;
  - an excluded `CI Watchdog` never fires;
  - the run clock fires at 20:01;
  - in report mode `force-cancel` is never requested (**control:** the same fixture in enforce mode requests it exactly once);
  - a rerun attempt resets the run clock.
- [ ] T1.5 [A] `report-nightly-status.cjs` lists the night's budget violations under their own heading, so the schedule run (cancel-exempt, `:54`) still surfaces them.
- [ ] T1.6 [B] **Unit-duration artifacts from every lane that will be sharded.** No sharding yet.
  - Playwright `--reporter=json` beside the existing reporters in `run-e2e.sh` and `run-account-e2e.sh:220-224`.
  - `gotestsum --jsonfile` in renet.
  - `pytest --junitxml` durations in `check_pytest.py`.
  - The battery's own per-test timings.
  - `vitest --reporter=json` in `run_account.py`.
  - Each is uploaded as `unit-durations-<lane>-<leg>-<sha>`. `budget_report.py --refresh` (T3.2) consumes them.
- **Exit P1:** 7 days of report-only data, and T1.1 output matches section 1.

### P2: split every job over 12 minutes

Order matters. The cheap cuts come first, because each one lowers every later shard count.

**P2a. Critical path and fixed-cost cuts (no shards)**

- [ ] T2.1 [C] Verify finding 3, then drop `build-docker-fast` from `tests.needs` (`ci.yml:999`) and from the `if:` beside it.
  - Verification: grep every ct-tests leg for image pulls of `*_tag`, and run one trial dispatch.
  - Projected: PR tests start at about 2.5 instead of 13.0.
- [ ] T2.2 [C] Apply D-W6 (`ci.yml:1043` ops-tests needs; the stripe-sandbox needs at `:676`).
- [ ] T2.3 [C] **Free Disk Space.** ct-tests.yml has 9 copies (`:335`, `:386`, `:510`, ...), 1.1-5.8 minutes each. Replace them with one composite action that deletes only what the VM legs need, in the background (`rm -rf ... &`, joined before the KVM step), and drops the second prune in the Workers leg.
- [ ] T2.4 [C] Remove the duplicate `npm run build -w @rediacc/shared && npm run build -w @rediacc/provisioning` (about 2 min, visible in the E2E Ceph and K8s Multinode logs just before "Running E2E tests") where `setup-workspace build-packages: 'true'` already built them.
- [ ] T2.5 [D] **`simulate_promotion.py`.** It runs one `aws s3api copy-object` subprocess per key (`:210`) with `max_concurrent_requests 3` (`:120`). Move the copies onto the already-imported `concurrent.futures` pool (`:91`) with 16 workers and adaptive retry kept. Projected: Validate Promotion goes from 15.0 to about 5.
- [ ] T2.6 [C] **Release chain.**
  - Narrow `stage-artifacts` needs (`ci.yml:962`) to what it ships. Split `ci-build-docker.yml` so the Devcontainer legs (end 15.8-16.6) are not upstream of staging.
  - Split `Renet (cached)` "Extract Linux binaries + cross-compile Darwin/Windows" (4.2 min) into two legs.
  - Verify whether stage needs docker at all.

**P2b. One shard mechanism, reused from quality-code (T-SCHED B2)**

- [ ] T2.7 [B] **Lanes beyond ci-quality.yml.**
  - `laneCapabilities` today parses one workflow, and `LANE_ORDER` (`scripts/ci-runner/lanes.ts:25`) lists `quality-*` only. Key capabilities by `ci.workflow`, and add the test lanes: `test-e2e-workers`, `test-account-e2e`, `test-renet-go`, `test-renet-integration`, `quality-pytest`, `quality-gate-tests`, `ops-tutorials`.
  - Add one gates.lock entry per lane (`ci.kind: 'step'`, the workflow and job of that lane). The lane is then visible to `npm run ci`, `gate-bind` and the gates, as the spec asks.
- [ ] T2.8 [B] **Unit enumerators.** A test lane's units are not lock entries: adding hundreds of files to gates.lock would distort `npm run ci`. Each lane instead declares an enumerator (`unitsFrom`) that prints `{id, mutex?, needs?}` per unit:
  - Playwright: `--list --reporter=json`, file units, plus `file::describe` units where declared.
  - Go: `go list ./pkg/... ./cmd/...`, 83 packages.
  - pytest: `--collect-only -q` files, with `rediacc_ci.xdist_groups` groups as mutex units.
  - The battery's own test list, with its writer/scanner sets as mutex units.
  - vitest: its `include` globs.
  - Tutorials: slugs in sequence order, with `needs` chaining within a segment.
  - `shardPlan` (`lanes.ts:480`) takes these units unchanged. Its refusals (empty shard, a unit in two shards, lost units) stay the correctness backbone.
- [ ] T2.9 [B] **Balance by measured duration, not slots.** Today LPT sorts on `weight`, which is scheduler slots (`lanes.ts:651-662`). Add `estimateMs` from `.ci/config/lane-durations.json`; the p90 of unit durations falls back to `weight` when absent, as today. `quality-code`'s plan must come out byte-identical, and a selftest control asserts it.
- [ ] T2.10 [B] **Shard manifest plus local reproduction.**
  - `gate-bind --write` emits the `strategy.matrix.shard` region (the existing `# >>> shard-strategy` form, `ci-quality.yml:733-738`) for each test lane, plus `.ci/config/shards/<lane>.json`: leg to unit ids.
  - Each leg runs `<runner> --shard-manifest .ci/config/shards/<lane>.json --shard ${{ matrix.shard }}`.
  - `npm run ci -- --lane <lane> --shard i/N` (`scripts/ci-runner/run.ts`) replays one CI leg locally through the same pool.
- [ ] T2.11 [B] **Merge by receipt.** Generalise `scripts/ci/write-shard-receipt.cjs` (`RECEIPT_WRITER`, `scripts/gate-bind.ts:605`) and `check:ci-quality-complete` (`ci-quality.yml:2672-2706`) from lock ids to unit ids.
  - Each leg writes `{lane, index, of, units:[{id, outcome, ms}]}`, derived from the runner's own report (Playwright JSON, gotestsum JSON, junit), not from the plan.
  - One slim `<Lane> / Shard receipts` job per lane downloads `<lane>-shard-*`. It asserts every unit ran exactly once with a non-skipped outcome, then merges artifacts:
    - `npx playwright merge-reports` for blob reports;
    - concatenated JUnit;
    - Go coverprofiles concatenated with the repeated `mode:` lines dropped.
  - The same receipts feed T1.6 durations.

**P2c. Per-job shard designs**

| Lane (job) | Unit | Legs (projected) | How units are assigned | Leg name (API) | Merge |
|---|---|---|---|---|---|
| E2E Workers (`ct-tests.yml:231`, one per distro) | file (Playwright project per file, `packages/e2e-tests/playwright.config.ts:61-103`); `13-postgres-fork-isolation` as 3 describe units | 5 per distro after P2d; 11 per distro without P2d (fixed 9.7) | LPT by per-file p90 (36040274865: 13-postgres 8.1, 10-backup 2.5, 07 2.1, 17 2.1, rest under 2); leg runs `--project test-NN ...` and `--grep` for describe units; FULL_INTEGRATION legs get 12a/b/d+13b | `E2E Workers (ubuntu-24.04, 3/5)` | receipts, blob merge, `create_complete --name e2e-workers-<os>-s<i>` (`:421`) |
| Account E2E (`ct-tests.yml:1865`) | spec file (99 under `private/account/e2e/tests`) | 4 | LPT; `10-stripe/**` is ONE mutex unit, and only the leg holding it starts `stripe listen`: two listeners on one sandbox both receive every webhook | `Account E2E (2/4)` | receipts, blob merge |
| Account vitest integration (Quality / Go step, `ci-quality.yml:2597-2599`) | vitest file (102) | 1 today (Go job 4.5/8.2); the gate watches it | `run_account.py test --shard i/N` -> `vitest run --shard=i/N`; lane in SHARD_COUNTS only when the estimate crosses 12 | unchanged | vitest junit |
| Renet go (`ct-tests.yml:1659`, split) | package | 2 | LPT by gotestsum per-package time; `run-tests.sh:57-59` gains `RENET_TEST_PKGS` (renet PR, submodule-first); the subscription/root/btrfs phases (`:78-99`), eBPF, root-tagged and CSI steps pinned to leg 1 | `Renet (go, 1/2)` | coverprofile concat, junit |
| Renet integration (same job, split) | pytest file (14 in `private/renet/tests/integration`) | 3 | LPT; `ci-test.sh` accepts a file list via env; daemon setup per leg | `Renet (integration, 2/3)` | junit |
| Quality / Security (`ci-quality.yml:2083`), split into 3 jobs | -- | Security core 1 + pytest 3 + gate tests 2 | "Python package tests" (`:2359`, check:ci-pytest) -> `quality-pytest` lane, file units with xdist groups as mutex; "Quality-gate unit tests" (`:2377`, battery.py) -> `quality-gate-tests` lane, its W/S isolation as mutex; the 13 region steps stay in Security | `Pytest (1/3)`, `Gate tests (1/2)` | receipts; `check_pytest.py:94` kill timer scaled per leg |
| OPS Provision linux-amd64 (`ci-ops-test.yml:297-313`) | tutorial (18) | 4 contiguous segments (D-W4) | sequence order kept inside a segment (`needs` chain = co-location) | `OPS Provision (linux-amd64, 2/4)` | tutorial logs artifact per leg |
| E2E Ceph / Ceph Workers / K8s Ceph / K8s Multinode | none (fixed-cost bound) | 1 each (Multinode 2 via D-W3) | P2d snapshot restore | unchanged | -- |
| E2E K8s, E2E Migrate, Fork Isolation | none | 1 | P2a plus P2d | unchanged | -- |
| Validate Promotion | none | 1 | T2.5 | unchanged | -- |
| Quality / Packages | none | 1 | verify T1.1 shows at most 12 after the pytest port (4.6 in 36040274865) | unchanged | -- |

- [ ] T2.12 [C] E2E Workers shard wiring, as in the table. It is preceded by a **dependency probe**: run each file alone on fresh VMs (`--project test-NN`) and encode every file that fails without a predecessor as a `needs` edge. The config comment "Order maintained by workers:1 + fullyParallel:false" (`playwright.config.ts:53-55`) means some order dependence may be real.
- [ ] T2.13 [D] Account E2E and vitest `--shard` passthrough, as in the table. Test code stays in `private/account`. Cache the three `npm ci` trees and `~/.cache/ms-playwright` so the fixed cost per leg stays under 3 min.
- [ ] T2.14 [D] Renet split: the renet PR for the `RENET_TEST_PKGS` / file-list hooks first, then the console `run_renet.py` and ct-tests.yml changes. Record the honest note that go test (2.5-3.2) is not the long pole; integration (12.9) is.
- [ ] T2.15 [B] Quality / Security split into three jobs (`quality-pytest`, `quality-gate-tests`, Security core). Lower `timeout-minutes: 45` (`:2118`) after the split.
- [ ] T2.16 [C] OPS tutorial segments, per D-W4.

**P2d. Fixed-cost reduction by snapshot (renet feature, cross-repo)**

- [ ] T2.17 [D] `renet ops` snapshot/restore of prepared VM disks. Two snapshots:
  1. Workers: the state after Steps 1-8 of bridge globalSetup ("VM soft reset", renet setup on all VMs, RustFS, datastores, CRIU; 6.3-7.0 min).
  2. Ceph: the state after "Ceph cluster provisioning completed successfully" (11-15 min).
  - Cache key: renet version, ceph image pin, VM image month.
  - Target: restore in 3 min or less.
  - Hypothesis until measured. Without it, E2E Workers needs 11 legs per distro, and the four Ceph/K8s jobs stay at 19-29 min.
- [ ] T2.18 [C] Apply D-W3 to the K8s Multinode (10.9 min) and K8s repo (7.3 min) tests.

**Exit P2:** `budget_report` over 10 green full runs shows every job's p90 at 12 or under and its max at 15 or under. Pipeline p90 meets the D-W1 target.

### P3: the lane-duration gate

- [ ] T3.1 [B] **`scripts/gates/check-lane-budget.ts`** (`check:ci-lane-budget`, quality-code lane). In TypeScript because it re-runs `shardPlan`. For every lane (quality-* plus the test lanes) and every job in ci.yml and its callees:
  1. **Per-leg estimate:** the job's fixed cost p90 plus the sum of the leg's unit p90s, with the LPT plan recomputed from the committed manifest. Red if over **12 min**, naming lane, leg and top 3 units.
  2. **Unsharded job:** its job-level p90 at 12 or under.
  3. **Single unit:** a unit whose p90 plus the fixed cost exceeds 12 is red and marked "indivisible: split the unit, or record an approved exemption". The exemption list is empty, and each entry is operator-approved (D-W3).
  4. **Unknown units:** an enumerated unit with no estimate is red unless the lane declares `defaultUnitMs`. A new test file cannot enter unmeasured.
  5. **Freshness:** red if `lane-durations.json` `refreshed_at` is older than **14 days**. This mirrors `MAX_BASELINE_AGE_DAYS` (`check_job_timeout_headroom.py:45`), made stricter.
  6. **Pipeline:** critical-path estimate plus `max(0, runnerMinutes / concurrency - critical path)` at 20 or under. Advisory until D-W1 is decided, then red.
  7. **After P4:** every job declares `timeout-minutes` of 15 or less.
  - Selftest controls: 12.1 fails and 11.9 passes; stale fails and fresh passes; a planted unestimated file fails, and the same file with `defaultUnitMs` passes; quality-code's plan is unchanged. Offline and deterministic, like the headroom gate.
- [ ] T3.2 [A] **Where the estimates come from.** `budget_report.py --refresh` rewrites `.ci/config/lane-durations.json`:
  - per job: fixed cost p90, meaning setup steps up to the runner step, taken from the step API;
  - per unit: p90 from the T1.6 unit-duration artifacts of the last 10 green full runs;
  - plus the `concurrency` value.
- [ ] T3.3 [A] **How they stay fresh.** `housekeeping.yml` (the daily 03:00 cron) runs `budget_report.py --check`. When any leg's *measured* p90 exceeds 12, or a committed estimate drifts more than 25% from measured, the job fails and posts to the nightly-status issue thread. That catches real regressions the estimate misses. The 14-day staleness in T3.1 forces a refresh commit at least twice a month.
- [ ] T3.4 [B] Retire `job-timeout-baseline.json` into `lane-durations.json` per D-W2. `check:ci-timeout-headroom` keeps its non-budgeted jobs, or folds into T3.1.

### P4: enforce 15 and 20 minutes

Entry: P2 exit met, plus 5 consecutive full green runs with zero report-only violations.

- [ ] T4.1 [C] Set `timeout-minutes: 15` or less on every job, in ci.yml and in each callee (a `uses:` caller cannot carry one). Today it reaches 90 and 100 (`ct-tests.yml:241`, `:1091`, `:1667`). **This is the only per-job kill that exists**: the Actions API can cancel a whole run, not one job.
- [ ] T4.2 [A] Flip `WATCHDOG_BUDGET_MODE: enforce`.
  - A job crossing 15 or a run crossing 20 goes through `forceCancel` (`:888`, the single chokepoint), with `CI BUDGET VIOLATION: '<job>' ran <m>m (budget 15m)` in the roster annotation and `budget-violations.json`.
  - `CANCEL_EXEMPT_EVENTS` (`:54`, schedule and workflow_dispatch) stays report-only for the run-level cancel, so a nightly is never laundered to `cancelled`. `timeout-minutes` still kills its legs.
  - Main push follows D-W5.
- [ ] T4.3 [A] `STUCK_THRESHOLD_MIN` (`:1045`, default 60) becomes 15. A leg killed by its timeout is then classified as a budget violation and not auto-retried (today a 15-min timeout counts as a "normal cancellation", which is retryable).
- [ ] T4.4 [B] Turn on T3.1 check 7 (timeout of 15 or less on every job).
- **Rollback:** one env value back to `report`. Timeouts stay.

## 5. Required-check names and branch protection

- **Ruleset.** Ruleset 12344707 ("Branch Protection", the only ruleset) requires exactly **`CI Complete`** and **`Review Complete`** (integration 15368). The branch-protection endpoint returns 404: there is no classic protection. No shard rename in this plan changes what gates a merge, because `CI Complete` aggregates `needs.tests.result` and friends at the reusable-workflow level (`ci.yml:1740`). **W must not rename `CI Complete`.** `Review Complete` belongs to spec Z.
- **Consumers that DO key on display names**, all updated in the same commit as each rename:
  - `.ci/scripts/ci/skip-plan-reconcile.cjs:36` matches `name == base` or `startsWith(base + ' (')`. Every leg name therefore keeps the form `<Base> (<suffix>)`, for example `E2E Workers (ubuntu-24.04, 3/5)` and `Renet (go, 1/2)`. Renet's base stays `Renet`, and `Quality / Security` keeps its name, with the new jobs added to the reconcile table.
  - Watchdog patterns (`watchdog-monitor.yml:148-170`) are substring matches (`E2E`, `OPS`, `Quality`), so legs still match. The `test_gate_watchdog_*` fixtures get leg-shaped names.
  - `job-timeout-baseline.json` keys (T3.4).
  - Artifact names must be unique per leg: upload-artifact v7 refuses duplicates. Examples: `test-renet-coverage-${sha}` (`ct-tests.yml` near `:1733`) and `test-e2e-workers-<os>-<sha>` (`:426`).
  - `create_complete --name` values.
- **Side effect worth having:** rerun-failed-jobs reruns only the failed legs, so a flake costs one leg (about 11 min), not a 40-minute job.

## 6. Projected after (scenario B: every P2 lever including P2d; minutes)

| Job | Before median / max (B or A) | After legs | Projected per leg | Basis |
|---|---|---|---|---|
| E2E Workers (per distro) | 36.7-42.2 / 64.9 | 5 | about 11.5 | fixed 5.4 (setup 3.4 after T2.3, restore 2) + 27.4/5 + LPT slack |
| E2E Workers without P2d | same | 11 | about 12 | fixed 9.7 + 27.4/11 |
| E2E K8s Multinode | 28.9 / 69.5 | 2 (D-W3) | about 11.5 | prelude 2.5 + restore 3 + about 6 |
| E2E K8s Ceph | 23.9 / 39.2 | 1 | about 9.5 | 2.5 + 3 + 4.0 |
| E2E Ceph Workers | 20.7 / 35.8 | 1 | about 7 | 2.5 + 3 + 1.3 |
| E2E Ceph | 18.3 / 31.3 | 1 | about 8 | 2.5 + 3 + 2.3 |
| E2E K8s | 16.4 / 40.5 | 1 (D-W3 may give 2) | about 11.9 | 2.5 + 2 + 7.4 |
| E2E Migrate | 13.1 / 42.6 | 1 | about 10.5 | T2.3 + restore of group B |
| Account E2E | 20.6 / 22.6 | 4 | about 8 | about 3 setup + about 17/4 |
| Renet go | 17.3 / 18.9 (whole job) | 2 | about 6 | 3 setup + 1.6 + pinned phases |
| Renet integration | (inside the above) | 3 | about 7.5 | 3 + 12.9/3 |
| Quality / Security core | 35.9 / 36.2 (C) | 1 | about 4 | region steps only |
| Quality / Pytest | (inside Security) | 3 | about 9.5 | 2 + 22.5/3 |
| Quality / Gate tests | (inside Security) | 2 | about 8.5 | 2 + 12.9/2 |
| OPS Provision linux-amd64 | 28.7 / 51.1 | 4 | about 11 | provision about 5 + 24.3/4 |
| Concurrent Fork Isolation | 11.4 / 23.1 | 1 | about 8 | T2.3 |
| Validate Promotion (main) | 15.1 / 22.4 (A) | 1 | about 5 | T2.5 |
| Stage Artifacts (main) | 9.5 / 12.6 (A) | 1 | about 7-9.5 | parallel uploads (optional) |
| Quality / Packages | 12.3 / 14.3 (C) | 1 | about 5 | measured 4.6 after port |
| Quality / Code | 10.9 / 13.7 (C) | 4 (unchanged) | 8.9 / 9.3 | measured |

| Pipeline | Before | After, Team (60) | After, Free (20) |
|---|---|---|---|
| PR full: critical path | 55.9 median / 68.2 max | about 20-23 (release chain: init 2.4, renet 3, cli 3.4, stage 5.5, validate 5.4), about 18 if T2.6 shows stage needs no docker | same path, but at least 36 from capacity |
| PR full: runner-minutes | 586 | about 720 | about 720 |
| Main push | 43.8 / 52.7 | about 19.6-22.4 (init 0.6, renet 3, cli 3, stage 7-9.8, validate 5, finalize 1) | same (small run) |

Every "after" number is a projection built from the measured components named in the Basis column. P2's exit measures them for real, and T1.1 regenerates this table from live runs.

## 7. Risks and still-unverified points

- **Finding 3 is a hypothesis.** It could be that ct-tests needs nothing from build-docker-fast. If a leg does pull a docker-fast image, T2.1 narrows the edge to that one leg rather than dropping it.
- **E2E file independence** is unproven (T2.12's probe). `needs` edges co-locate units and may raise the leg count.
- **Snapshot restore times (P2d)** are targets. They need a renet feature, so a renet PR lands first.
- **Stripe:** concurrent Account E2E legs share one sandbox. Only the stripe-unit leg runs `stripe listen`, but the other legs' fixtures must not assume an exclusive sandbox. Audit `10-stripe` and `03-subscription`.
- **Free-plan capacity** is inferred from a documented limit plus a measured peak of 19. It is shared with the org's other 38 repos, so real queueing can be worse than section 1c.
- **Watchdog detection latency:** 30 s polls, plus a 20-60 s gap between generations (`WATCHDOG_DEADLINE_SECONDS: '480'`, `watchdog-monitor.yml:139`). `timeout-minutes` is the exact per-job cutoff; the watchdog is the named report and the run-level cutoff.
- **Main has not been green since 2026-09-07.** Sample A predates the rediacc_ci port. T1.1 must re-measure main once it is green again, before D-W5 flips.

### Critical Files for Implementation
- /home/developer/console/.ci/scripts/ci/watchdog-monitor.cjs
- /home/developer/console/scripts/ci-runner/lanes.ts
- /home/developer/console/.github/workflows/ct-tests.yml
- /home/developer/console/.github/workflows/ci.yml
- /home/developer/console/scripts/gate-bind.ts

## Operator rulings (2026-09-25, AskUserQuestion; re-asked and revised the same day)

- **D-W1: stay on GitHub Free; the pipeline target is ~35 minutes** (revised from "Team plan"). The per-job 15-minute budget is unchanged. `.ci/config/lane-durations.json` `concurrency` is 20, and the P3 pipeline check and the P4 run-level cancel use 35 minutes, not 20.
- **D-W4: make the OPS tutorials independent.** Each tutorial sets up its own prerequisites through fixtures so the tutorials shard like tests; T2.16 becomes "make every tutorial self-contained, then shard by tutorial", replacing the contiguous-segment design and the `needs` chaining. Profiling and trimming the sequence comes first. Cross-tutorial state is no longer exercised; say so in the tutorial docs.
- **D-W3: approved exemptions** (revised from the checkpoint split). `kube/17-multinode-cluster` (one 10.9-min test) and `kube/15-k8s-repo` (one 7.3-min test) stay whole; the lane gate carries them as a named, operator-approved exemption list, and T2.18 is dropped.
- **D-W5: enforce on PRs and main together** (revised from PRs-first). One switch; an over-budget main push cancels that release.
- D-W2 and D-W6 take the plan's recommendation: the lane gate supersedes the 1.5x headroom rule for budgeted jobs; drop quality/review-gate from ops-tests needs and keep review-gate on stage-artifacts.

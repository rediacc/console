# PLAN: First release checks: what bench cannot prove waits for the first real release

Status: approved -- operator answered "Reword and move" ASKED:2026-11-05T07:06Z.
Depends-On: no-dep -- waits on the operator lifting the edge and stable hold of ASKED:2026-11-04T16:33Z, not on another plan.
Priority: P2 -- these boxes close only on a real release, and the plans they came from can finish without them.
Concurrency: parallel -- its boxes run on separate targets; nothing here edits code until the hold lifts.
Owns: agent/plans/PLAN-first-release-checks.md, agent/plans/PLAN-*.md
Owner: d778be9d
First-Seen: 2026-11-05
Worklist: pending -- filed at promotion

## Why

Bench is one environment in one region. Boxes that prove the release pipeline, need elapsed time, or name a clause bench cannot reach stay open here until the first real release, which carries about 350 commits. The plans they came from cite each move.

One order carries over: multi-org ML5 reaches the three stable targets before durable-object L5 flips them, so no stable target takes both changes in one release.

## Tasks

- [ ] Multi-region placement: prove the us and asia executor placement on real edge-us and edge-asia, the clause split from six-targets L2, multi-org ML2, durable-object L2 and L3, and connect-timeout E10.
  Accept: E1 exits 0 on `durable` with two org ids against each origin, a console command before edge-us's enable step answers the coded 503 (six-targets L2), and org B's `executor_placement` counter on edge-us is recorded before and after 27-90 and 27-91 (connect-timeout E10).
- [ ] EU deploy order: deploy the account server on eu before the CLI release, the clause split from token-ip-rebind T9.
  Accept: the release records show the eu account deploy's version id and time ahead of the CLI publish.
- [ ] Hostinger scheduled timer: after the stable deploy, the next scheduled snapshot of one hostinger repo uploads and commits, the clause split from shared-bucket L2.
  Accept: `backup usage` shows the new snapshot, and `backup status` shows the timer took it.
- [ ] Production WAF and edge regions: apply the WAF rule to the production zones and deploy the account worker to every edge region, then stable, with `FREE_LICENSE_HMAC_KEY` set, the clauses split from free-license L1.
  Accept: `apply_cf_waf_rules` rc 0 per production zone, with a version id and rollback command recorded per region.

## Moved from PLAN-backup-program.md

- [ ] Q0: Before the cutover, set the four ACCOUNT_BACKUP_S3_* secrets on the eu stable Worker (names only, through the M1 path) and add the bucket-scoped cf-r2-backup rotation slug to the rotation profile in .ci/config/secret-supply.json; carried from CHECKLIST w8. Accept: the Worker settings list all four names; the rotation dry run lists the slug; the rollback version id is recorded. (corrected 2026-11-04: the slugs exist as cf-r2-backup-stable, -edge and -bench in private/account/rotation-manifest.json:136, and the rotation profile in .ci/config/secret-supply.json has no slug concept, so that clause needs no change there; what remains is the live push and dry run, which wait on the operator's hold on stable.)
- [ ] Q1: Merge the program's PR through the loop (CD deploys edge). Deploy stable EU locally per .claude/skills/deploy/SKILL.md: `./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- bash -c 'npm run build:packages && PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_account --region eu --target stable'` (with the portal build step the skill names), then the M1 secrets path for eu stable. Record the rollback version id and the D1 bookmark. Accept: https://eu.rediacc.com/account/api/v1/health answers 200 and the portal assets load.
- [ ] Q12: The next 02:00 timer run completes on its own and uploads only changed cells. Accept: backup status shows the timer run; usage grows by a small delta.
- [ ] Q13: After a few runs, `./rdc.sh backup retention preview mail --config eu-remote`. Accept: nothing beyond the policy is listed, and the floor is kept.
  (note) Runs through `eu-bench`, not `eu-remote`: PLAN-tested-on-bench ruling 1 as extended on 2026-11-04. The text above keeps the old name because a box's first 120 characters are its identity.

## Moved from PLAN-cloudflare-proxy.md

- [ ] C2 [P1] After Phase 2 is green and C1 lands: `EXECUTOR_MODE = "proxy"` and `EXECUTOR_URL = "https://proxy.eu.rediacc.com"` in `workers/account/wrangler.eu.toml` `[vars]`, an eu deploy, and one console command (`machine status hostinger`) run from the portal console end to end; us and asia stay `mock` -- acceptance: this plan records the deploy version, the console run's output matching the local run, and the audit event naming the user

## Moved from PLAN-telemetry-export.md

- [ ] T15 [ops] Live proxy acceptance, after `PLAN-cloudflare-proxy.md#P2a` and T13 and T14 deployed by that plan's Phase 2 redeploy: one `rdc --proxy https://proxy.eu.rediacc.com machine status hostinger` and one Worker probe -- Owns: agent/plans/PLAN-telemetry-export.md (a "Proxy results" section). Accept: Tempo lists `rediacc-proxy` and `rediacc-proxy-executor`, both spanmetrics series are above 0, and a `renet-execute` span from hostinger falls in the same minute; outputs recorded here.

## Moved from PLAN-stop-hook-one-plan-scope.md

- [ ] SC13b Real run after the merge: the first stop on the merged branch blocks with `loop-next` naming the next QUEUE.md plan and the step-7 commands; after the cut, the push and `gh pr create`, the new PR's body reads that plan's `Plan:` line and `loop-next` is silent. Files: none owned (evidence only). Depends on: SC13a and this PR's merge. Acceptance: both decision blocks quoted in the round log with the branch, PR number and head sha.

## Moved from PLAN-plan-preflight.md

- [ ] PF9 Real run: the first plan started by the loop after this PR merges goes through step 0 end to end. The PR body or report records the survey counts (present/absent/partial), ticks made by the survey, relocated and corrected citations, the overlap list length and the `Revalidated:` sha. One deliberate stale case is exercised: after a rebase onto a main commit that touches a cited path, `--plan-tick` refuses, the preflight is re-run and the tick passes. Files: none owned (evidence only). Depends on: PF5, PF6, PF7 and this PR's merge. Acceptance: the plan's header carries `Revalidated:` at the new branch's merge base, and the refused-then-accepted tick pair is quoted with both outputs in the round log.
    Under ruling 3b (2026-10-23, PF5 warn-first, `.claude/hooks/stop/wl_planrec.py:2009` `preflight_warning`) the stale case is a WARNING naming the stale commits and the `--plan-preflight` command, and the tick goes through; the evidence is the warned tick and the clean tick after the re-run.

## Moved from PLAN-local-release.md

- [ ] L1 [lead] One real edge release from the local machine, after the 1023-1 PR merges.
  - Record per-step timings in Results and compare them with the last CD pair: CI run 39898575743 plus CD run 39902042581, about 39 min to dispatch and about 60 min end to end.
  - Accept:
    - the release record in R2 shows every step ok;
    - `rdc --version` from the edge channel names V;
    - the R1 order entry reads satisfied;
    - the account Worker reaches eu edge after the CLI.
- [ ] L2 [lead] The first stable release through `release:local --channel stable` after the soak, together with the R3 live check (`subscription status` against `machine status hostinger --licenses`).
  - Accept: `verify_stable_endpoints` rc=0, and the stable deploy records are in R2.

## Moved from PLAN-proxy-cd-six-targets.md

- [ ] L5 [live, post-merge] stable-eu through promote-stable (soak or nightly waiver). Delete rediacc-proxy-eu's `EXECUTOR_TOKEN` secret and revoke its token. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: the stable-eu record matches L4's manifest sha256s for the same version, smoke rc is 0, E1 against `https://eu.rediacc.com` exits 0 with the audit event naming the user (this also closes PLAN-cloudflare-proxy C2), and no unrevoked 'cloudflare' token remains in the eu D1.
- [ ] L6 [live, post-merge] stable-us, as L5. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L5 for us.
- [ ] L7 [live, post-merge] stable-asia, as L5. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L5 for asia.
- [ ] L8 [ops, post-merge] Telemetry acceptance, which folds in PLAN-telemetry-export T15.
  - Verify U6 and extend the Alloy transform on hostinger to the regex in W1, with `deployment.environment` and `rediacc.region` resource attributes so the proxy Loki streams carry those labels.
  - Create one silent-sender rule per proxy target, `silent-proxy-<production|edge>-<r>` (six rules), keyed `service="rediacc-proxy"`, and unpause them. `silent-proxy-exec-prod-eu` stays paused (a DEFAULT).
  - T1's list holds all seven proxy hosts.
  
  -- Owns: the observability repo's Alloy config and alerting provisioning, .ci/rediacc_ci/ops/telemetry_delivery.py (the list). Accept: `python3 -m rediacc_ci.ops.telemetry_delivery` exits 0 with 14 hosts and 0 silent; Tempo lists `rediacc-proxy` and `rediacc-proxy-executor`; `count by (deployment_environment, rediacc_region) (traces_spanmetrics_calls_total{service="rediacc-proxy"})` returns 7 series; `GET /api/v1/provisioning/alert-rules` shows the six proxy rules with `isPaused: false`.

## Moved from PLAN-console-executor-multi-org.md

- [ ] ML4 [live, post-merge] The first CD edge run after merge. Its three job records, plus E1 per edge region. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: three deploy jobs succeed with smoke rc 0, and E1 exits 0 for each edge origin.
- [ ] ML5 [live, post-merge] stable-eu, stable-us and stable-asia through promote-stable. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: each stable row has smoke rc 0, and E1 against `https://eu.rediacc.com`, `https://us.rediacc.com` and `https://asia.rediacc.com` exits 0 with two org ids each.
- [ ] ML6 [ops, post-merge] Capacity watch. A Grafana query of the per-target count of `rediacc.proxy.outcome=capacity` over 14 days goes to the Live records, and the decision on raising max_instances goes to the operator with that number. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: the Live records carry the 14-day count for each of the six targets and the ASKED line or the "no capacity refusals" record.

## Moved from PLAN-executor-durable-object-policy.md

- [ ] L4 [live, post-merge] The first CD edge run after merge, with its three job records and E1 per edge region. -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: three deploy jobs succeed with smoke rc 0 and backend `durable`, and E1 exits 0 for each edge origin.
- [ ] L5 [live, post-merge] stable-eu, stable-us and stable-asia.
  - Phase 1 rides the merged release through promote-stable.
  - Phase 2 is the release that flips `BACKEND_BY_TARGET` for the three stable targets.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: each stable target has a forward-only Phase 1 row and a Phase 2 row with smoke rc 0, and E1 against `https://eu.rediacc.com`, `https://us.rediacc.com` and `https://asia.rediacc.com` exits 0 on `durable` with two org ids each.
- [ ] L7 [live, post-merge] Phase 3 per target, after C1.
  - Deploy the C1 release (forward-only) to bench, the three edge targets and the three stable targets.
  - Then run `npx wrangler containers delete <old application id>` per target, with the id read from `wrangler containers list` and recorded by its first 8 characters.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: seven forward-only rows with smoke rc 0, and `npx wrangler containers list` per account names no `ExecutorContainer` application.
- [ ] DL1 [deadline] All seven targets route `durable` and run without the `Container` class by 2026-12-15, two weeks before the 2026-12-31 freeze.
  - Checkpoints: S1 verdict by 2026-11-02; L0 to L3 by 2026-11-16; L5 by 2026-11-30; L7 by 2026-12-15.
  - Escalation: a missed checkpoint, a STOP verdict, or a policy still marked public beta on 2026-12-01 writes an ASKED line with two options:
    - (a) proceed on the beta;
    - (b) stay on the frozen class past 2026-12-31, which keeps running per Context item 1, with a re-check date.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: on or before 2026-12-15, L7 is ticked, or an ASKED line dated before 2026-12-31 records the operator's choice.

## Moved from PLAN-production-key-only.md

- [ ] L1 [live] Park the six entries, after K1-K3 are on the branch and right before the merge. The window is short because main's `account dev` still needs `_DEV` until the merge.
  1. `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env park ACCOUNT_ED25519_PRIVATE_KEY_DEV ACCOUNT_ED25519_PUBLIC_KEY_DEV ACCOUNT_JWT_SECRET_DEV ACCOUNT_SERVER_API_KEY_DEV ACCOUNT_X25519_PRIVATE_KEY_DEV ACCOUNT_X25519_PUBLIC_KEY_DEV`. It must print six MATCH lines with names only.
  2. Record the ids (unchanged, from .ci/config/bws-secret-map.json:61-93) and the verdicts. No value is ever printed.

- [ ] K6 [writer] After L1: map refresh and the no-DEV gate (G1). Changes:
  - Run `scripts/ops/bws-map-refresh.py` so bws-secret-map.json loses the six `_DEV` entries and gains no `__` entries.
  - Remove .ci/config/bws-unrequested.json:51-74 and .ci/config/env-manifest.json:107-117 rows. Regenerate doc-registry.md with `npx tsx scripts/gen/gen-docs.ts --write`.
  - Add the no-dev-keys gate (.ci/scripts/quality/check_no_dev_keys.py plus .ci/rediacc_ci/quality/no_dev_keys.py). It refuses:
    - (a) any store name ending `_DEV` in the map, bws-unrequested, env-manifest, or the store side of any secret-supply spec;
    - (b) the regex `(?<![A-Z0-9_])ACCOUNT_[A-Z0-9_]+_DEV(?![A-Z0-9_])` in tracked files under .ci/ (except .ci/shadow and .ci/cache), scripts/, .github/, private/renet/build.sh, private/account/{src,scripts,CLAUDE.md}, docs/;
    - (c) any `__`-prefixed store name bound by a profile;
    - (d) `RENET_KEYLESS` outside .github/workflows and tests;
    - (e) a `CACHE_STORE_NAMES` value that is not exactly its own name.
  - Register it in package.json, gate-costs.json and lane-durations.json.
  - Change .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py:1158 to assemble the literal at run time (under PLAN-executor-durable-object-policy's lease).

  Tests (gate test, controls):
  - Each rule goes red on its planted fixture in a temp tree: a `_DEV` map row, an `ACCOUNT_JWT_SECRET_DEV` line in a .py, a `__X` profile binding, `RENET_KEYLESS=1` in rdc.sh, and a `_DEV` cache alias.
  - `__ACCOUNT_X_DEV` text alone does not trip rule (b).
  - The real tree is green.

  Owns: .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, .ci/config/env-manifest.json, scripts/data/doc-registry.md, .ci/scripts/quality/check_no_dev_keys.py (new), .ci/rediacc_ci/quality/no_dev_keys.py (new), .ci/rediacc_ci/tests/gates/test_gate_no_dev_keys.py (new), package.json (one script line), .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py (line 1158 only). Accept: `npm run check:ci-bws-map`, `check:ci-bws-map-live` and `check:ci-secret-supply` rc 0, and the gate test rc 0.

## Moved from PLAN-backup-integrity.md

- [ ] H4: The next nightly: 10 repositories have `hasIndex` true and `indexStatus` sealed. demo-heartbeat is reported plainly: it has neither keyfile nor mount, so it gets no listing, and the warning is in its unit journal. Spot ran after the snapshot, and reports reached the account after the stable deploy.
  - Accept: `rdc --config eu-bench backup manifests <repo> -o json` rc 0 per repo, recorded here.

## Moved from PLAN-backup-critical-tier.md

- [ ] J5: A restore at a chosen minute from the last 24 hours, under a new name, compared by mail-store checksum on sampled messages; only the `-rt` copy is deleted, by GUID.
  - Accept: `rdc --config eu-bench backup restore mail --at <minute> --as mail-rt -m hostinger` rc 0, then `repo list -m hostinger` shows `mail` with its GUID unchanged and no copy after cleanup.
- [ ] J6: Seven days at 5 minutes: `waitingBytes` stabilizes near the formula, the first reap ran, and the churn cap state is known.
  - Accept: `rdc --config eu-bench backup usage -o json` rc 0 on day 8, with the series recorded here.

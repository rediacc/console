# PLAN: simulation before production: every edge release deploys the exact build per region to an ephemeral production-shaped preview with that region's production [vars] and a D1 copy, runs the account API smoke, deploys production only on green and tears the preview down in the same run; the release order becomes region-major with the real-edge smoke between regions; the PR merge needs a green preview smoke or a local receipt from the landing tree; and a missing Console CI workflow run on an open PR is red within 30 minutes

Status: approved -- operator ASKED:2026-11-28T10:44Z (ruling 4 and 5) and ASKED:2026-11-28T10:49Z (rulings 6 and 7), with the coordinator's order of the same morning to split this work out of PLAN-account-api-health.md; quoted under "Operator rulings"
Owner: d778be9d
Depends-On: PLAN-account-api-health.md#S1, PLAN-account-api-health.md#S2, PLAN-cloud-inventory.md#INV1 -- the preview stage and the real-edge row call S1's smoke and S2's region smoke; box P4 registers every ephemeral resource in the inventory registry INV1 adds
Priority: P0 -- the 2026-11-28 edge release reached eu, us and asia with every account API route answering 500; no stage between the build and production ran the production entry under production [vars]
Concurrency: parallel -- three writers with disjoint Owns (P: P1+P2+P3+P4, W: W1+W2, M: M1+M2), then lead live steps L1 and L2; Owns is disjoint from PLAN-account-api-health.md (which owns the smoke modules, the mail sender, the parity and coverage gates and ops-health) and from PLAN-ciquick-gate-contract.md, which owns .claude/config/effort.json: the two effort keys (`preview-smoke`, `ci-presence`) are reported by the M writer and applied by the lead once no gate-contract writer holds that file
Owns: agent/plans/PLAN-preprod-simulation.md, .ci/rediacc_ci/deploy/release_preview.py, .ci/rediacc_ci/deploy/preview_name.py, .ci/rediacc_ci/deploy/preview_signer.py, .ci/rediacc_ci/deploy/set_preview_worker_secrets.py, .ci/rediacc_ci/deploy/wait_for_preview_worker.py, .ci/rediacc_ci/release/local.py, .github/workflows/cd-deploy-account.yml, .github/workflows/cd-release-edge.yml, .ci/rediacc_ci/ops/preview_smoke_local.py, .ci/rediacc_ci/ops/ci_run_presence.py, .ci/rediacc_ci/ops/ops_health.py (ci-presence check only), .ci/rediacc_ci/tests/test_release_preview.py, .ci/rediacc_ci/tests/test_release_local_preview_stage.py, .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py, .ci/rediacc_ci/tests/test_preview_smoke_local.py, .ci/rediacc_ci/tests/test_ci_run_presence.py, .claude/rediacc_hooks/guards/block_admin_merge.py, .claude/rediacc_hooks/guards/test-block_admin_merge.py, .claude/hooks/stop/wl_previewsmoke.py, .claude/hooks/stop/test-wl_previewsmoke.py, .claude/hooks/stop/wl_checks.py (one block only), .claude/commands/landing.md (finish condition only), docs/agent-reference/release-process.md (preview stage section only)
Updated: 2026-11-28
First-Seen: 2026-11-28

## Context

The incident is recorded in agent/plans/PLAN-account-api-health.md *Incident (2026-11-28)*. The facts this plan acts on:

- release:local has no preview stage, and `plan()` expands per-region rows in table order (.ci/rediacc_ci/release/local.py:1231-1249), so all three account deploys (.ci/rediacc_ci/release/local.py:936-942) run before the single `verify-endpoints` smoke (.ci/rediacc_ci/release/local.py:1027-1031); no per-region stop exists today.
- CD deploys the regions as a parallel matrix with `fail-fast: false` (.github/workflows/cd-deploy-account.yml:254-256), with the Worker secrets set at .github/workflows/cd-deploy-account.yml:552, and verifies once afterwards in cd-release-edge.yml (:597-601).
- The PR preview is not production-shaped: ci.yml deploy-preview (.github/workflows/ci.yml:1507) deploys the www Worker, which wraps `createApp` directly (workers/www/src/index.ts:2) rather than the production entry (workers/account/src/index.ts:2), under generated [vars] (.ci/rediacc_ci/deploy/deploy_www.py:167-182) that lack the production keys. It stays the PR check; the release stage below is the production-shaped one.
- CI Complete needs smoke-test-preview (.github/workflows/ci.yml:2096, job at :1760), and a skipped smoke does not fail it, so a green CI Complete says nothing about the preview smoke.
- Console CI created no runs for PRs #602, #603 and #605 (a trigger outage from 2026-11-01 to 2026-11-28), and #607's runs were cancelled before the preview job. Nothing noticed a PR head with no run.
- The merge guard for `gh pr merge` is .claude/rediacc_hooks/guards/block_admin_merge.py (docstring lines 1-12); `gh pr ready` is gated separately by block_premature_ready.py.

## Operator rulings

ASKED:2026-11-28T10:44Z:

4. Simulation first: a mandatory production-shaped preview stage before every real edge deploy in release:local AND CD (same [vars] as each region's production toml, its own D1 copy, the release smoke against it; production only after green); a config-parity gate in ci:quick (bench and preview configs carry every [vars] key the production configs carry); a merge gate requiring a green preview smoke on the PR head.
5. Enforcement, not suggestions: hooks plus ci:quick and full CI gates, so other AI sessions cannot forget.

ASKED:2026-11-28T10:49Z:

6. PR preview enforcement, "Merge gate + local fallback": the merge refuses a head without a green preview smoke (read through ci-trace); when GitHub runs are missing, the same preview deploy and smoke runs LOCALLY from the landing tree and its receipt counts; plus a gate that reds when a PR head has no Console CI run 30 minutes after a push, so a trigger outage like 11-01..11-28 is seen in minutes.
7. Pre-production stage, "Ephemeral production-shaped preview": per release and region, deploy the exact build to a TEMPORARY preview with that region's production [vars] and a D1 copy, run the API smoke, deploy production only on green, then DELETE the preview Worker, D1 copy, preview signer and its secrets in the same run, recording each create and delete in the release record. Teardown runs also on failure, and a teardown failure is a red the run reports. Every created resource is registered in the inventory registry that PLAN-ciquick-gate-contract adds (box INV1 there).

Ruling 3 (no automatic rollback; mail emergency@ and stop before the next region) is quoted in PLAN-account-api-health.md and holds for every row this plan wires. The registry named in ruling 7 is cited here as the coordinator's later order names it, PLAN-cloud-inventory.md#INV1.

## Design

**D-preview (P1 to P4).** Per region and release, `.ci/rediacc_ci/deploy/release_preview.py` has four verbs: `create`, `smoke`, `teardown` and `stage` (all three in order, teardown in a `finally`). `create` makes a temporary Worker `rel-<sha8>-<region>` from the exact release build, its config rendered from workers/account/wrangler.<region>.toml: every [vars] key and value copied, plus `ENVIRONMENT = "preview"` and `SIGNERLESS_PREVIEW = "true"` (the flag deploy_www already sets, .ci/rediacc_ci/deploy/deploy_www.py:177-182), no route, and a D1 binding to a fresh copy `rel-<sha8>-<region>-db` of that region's database. It reuses the PR preview machinery: preview_name.py for the name rule, preview_signer.py for the preview's own signer, set_preview_worker_secrets.py for the secrets, wait_for_preview_worker.py for readiness. `smoke` is PLAN-account-api-health.md's S1 (`account_api_smoke.py`) against the preview origin. `teardown` deletes the Worker, the D1 copy, the preview signer and its secrets, each delete checked by a read-back. Every create and delete is one row of the release record (`record_document`, .ci/rediacc_ci/release/local.py:34); a teardown failure exits non-zero and is a red the run reports. The rendered config carries every production [vars] key by construction, which P1's test asserts key for key.

The D1 copy holds customer rows, so the preview has no route, never outlives the run, and is named in the release record. Unverified, and checked first in P1 (rule 3): whether `wrangler d1 export` holds writes on the production database while it runs. If it does, P1 measures the export on bench, bounds it, and records the figure here before the stage is wired.

**D-order (W1, W2).** Under the preview stage, `plan()` becomes region-major for the deploy and smoke sections: for eu, `release_preview stage`, then the signer, account deploy and secrets rows as today, then `edge_region_smoke --region eu` (PLAN-account-api-health.md S2); then the same for us, then asia. A preview red stops before that region's production deploy; a real-edge red stops before the next region, mails through S2 and prints the rollback commands. Nothing rolls back the account Worker or D1. The existing proxy `rollback` row (.ci/rediacc_ci/release/local.py:1009-1023) keeps its shape, as PLAN-account-api-health.md *D-edge* records. CD gets the same order: the deploy matrix serialized (`max-parallel: 1`, regions in regions.json order) with the stage steps before the deploy and the region smoke after "Set Worker secrets", teardown under `if: always()`.

**D-merge (M1).** The merge reads the `Smoke Test Preview` job conclusion on the head through `.ci/scripts/ci/ci-trace.py`; only `success` admits, never `skipped` or `cancelled`. When the head has no such run, `.ci/rediacc_ci/ops/preview_smoke_local.py` runs the same deploy_www preview and smoke-test-preview.ts from the landing tree and writes a receipt keyed on the head sha and the tree hash under `.ci/cache/preview-smoke/`; a matching receipt admits too. block_admin_merge.py refuses `gh pr merge` (`--auto` included) without either, `/landing`'s finish condition names the requirement, and the Stop-hook check `wl_previewsmoke.py` blocks the landing tree while the open PR's head has neither (effort key `preview-smoke`).

**D-presence (M2).** `.ci/rediacc_ci/ops/ci_run_presence.py` lists the open PRs and their heads with `gh`, and reds when a head pushed more than 30 minutes ago has no Console CI workflow run; an API failure is unknown, never green. A check inside CI cannot see a missing CI run, so it runs locally: ops_health refresh runs it as source `local-ci-presence` (PLAN-account-api-health.md A1 puts that source in the emergency class, so the Worker mails it within one cron run), and the Stop hook reports it (effort key `ci-presence`).

## Boxes

- [ ] P1 [writer] `release_preview.py create` per D-preview: render the region's production [vars] into the generated config, copy the region's D1, create the preview signer and secrets through the reused modules, wait for readiness, and append one release-record row per created resource. The D1 export behaviour is measured and recorded here first.
  - CONTROL: with the recording wrangler fake, the rendered config of each of eu, us and asia carries every [vars] key of its production toml (a key dropped from the renderer reds), carries no route, and binds only the copy.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_preview.py -q -k create` rc 0.
- [ ] P2 [writer] `release_preview.py smoke` and `stage`: S1 against the preview origin, and `stage` running create, smoke and teardown with teardown in a `finally`.
  - CONTROL: a planted 500 on the preview smoke exits 1 and still runs teardown; a green smoke exits 0 after teardown; a create that fails halfway tears down what it made.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_preview.py -q -k "smoke or stage"` rc 0.
- [ ] P3 [writer] `release_preview.py teardown`: delete the Worker, the D1 copy, the preview signer and its secrets, read each back as gone, and record each delete; any failed delete exits non-zero and names the resource.
  - CONTROL: a fake whose D1 delete fails makes `stage` exit non-zero after a green smoke, and the record names the surviving database.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_preview.py -q -k teardown` rc 0.
- [ ] P4 [writer] Every resource `create` makes is registered in the inventory registry on create and retired on delete, so a failed teardown leaves a visible orphan the registry check names.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_preview.py -q -k registry` rc 0, with a planted teardown failure leaving exactly one registered resource.
- [ ] W1 [writer] release:local per D-order: region-major `plan()` under the stage, the `release_preview stage` row before each region's deploy rows, the `edge_region_smoke` row after each account deploy, teardown recorded with `always`. A preview red runs no production row for that region or any later one; a real-edge red runs no row of the next region.
  - CONTROL: with the recording fake, a planted preview red for us runs eu's production rows and none of us or asia; a planted real-edge red for eu runs no us row, calls the mail sender once and prints the rollback commands; no account rollback command executes.
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_release_local_preview_stage.py -q` rc 0, and `npm run release:local -- --channel edge --workers-only --dry-run` prints stage, deploy and smoke rows region by region.
- [ ] W2 [writer] The release workflows per D-order: cd-deploy-account.yml serializes the matrix (`max-parallel: 1`), runs `release_preview stage` before the deploy and `edge_region_smoke` after "Set Worker secrets" (.github/workflows/cd-deploy-account.yml:552), with teardown under `if: always()`; cd-release-edge.yml keeps the post-release verify. No step rolls back.
  - Local-route: deploy-bench -- the workflow steps call the same release_preview.py and edge_region_smoke.py that L1 drives against bench from this machine
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py -q` rc 0 (asserting step order, `max-parallel: 1` and the always-teardown) and `npm run check:ci-workflows` rc 0.
- [ ] W3 [live] The first real edge release through the workflows after W2 lands shows, per region and in order, stage create, smoke rc 0, teardown rc 0, the production deploy and the region smoke rc 0 in its release record.
  GitHub-only: CD -- only the release pipeline runs the workflow matrix with its environments; L1 proves the same modules from this machine
  - Accept: the release record of that run, read from R2, lists those rows per region.
- [ ] M1 [writer] Merge gate with local fallback per D-merge: block_admin_merge.py refuses `gh pr merge` when the head commit of the open PR has neither a `success` Smoke Test Preview job (read through the trace script D-merge names) nor a matching receipt from preview_smoke_local.py; landing.md's finish condition names it; wl_previewsmoke.py blocks the landing tree's stop on the same reading.
  - CONTROL: guard tests with a stubbed trace: `skipped`, `cancelled`, no job with no receipt, and a receipt for another sha each refuse; `success` admits; a matching receipt admits.
  - Accept: `python3 .claude/rediacc_hooks/guards/test-block_admin_merge.py` rc 0, `python3 .claude/hooks/stop/test-wl_previewsmoke.py` rc 0, `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_preview_smoke_local.py -q` rc 0.
- [ ] M2 [writer] `ci_run_presence.py` per D-presence, run by ops_health refresh as source `local-ci-presence` and reported by the Stop hook.
  - CONTROL: fixtures for a 31-minute-old head with no workflow run (red), a 29-minute-old one (green), a head with a cancelled run (green: a run exists), and an API failure (unknown).
  - Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ci_run_presence.py -q` rc 0 and one live read `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ci_run_presence` with its rc and verdict recorded here.
- [ ] L1 [live] Bench drill: `release_preview stage --region bench-eu` with a half-config planted (one forensics secret set on the preview) refuses and tears down; the same stage without the plant is green and tears down; no `rel-` Worker, database or signer survives either run.
  - Local-route: deploy-bench -- release_preview.py runs from this machine against the bench account and signer Workers and the bench D1
  - Accept: both runs recorded here (rc 1, then rc 0), and `wrangler d1 list` plus `wrangler deployments list` show no `rel-` resource left.
- [ ] L2 [live] The landing-tree fallback: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.preview_smoke_local` against the open PR's head writes a receipt, and block_admin_merge admits a merge dry run on it while refusing the same head with the receipt removed.
  - Accept: the receipt path and both guard verdicts recorded here.

## Writer split and order

P (P1, P2, P3, then P4 once INV1 lands), W (W1, then W2, after PLAN-account-api-health.md S1 and S2 land; both stub `release_preview stage` until P2 lands) and M (M1, M2) start in leases. The lead then runs L1 and L2; W3 rides the next edge release.

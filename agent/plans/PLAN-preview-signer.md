# PLAN: Per-preview signer -- `rdc` works fully against a PR preview, signed by a short-lived delegated key that dies with the preview

Status: approved -- operator ruling ASKED:2026-11-22T04:23Z "Per-preview signer, as a plan" (worklist #51fb685e)
Depends-On: no-dep -- the one prerequisite is worklist #8e42e148 (the coded signer refusal), an item rather than a plan, carried here as box A0
Priority: P2 -- login, config storage and SSH-only listing already work against a preview; activation, repo create/fork/up and renewal do not, so a preview cannot prove a licensing change end to end
Concurrency: parallel -- writers own disjoint files; PLAN-enterprise-isolation.md (executing) also owns private/account/src/services/license-signer.service.ts and workers/signer/**, and PLAN-signer-bench-stop-binding-reattach.md owns deploy_signer.py, so block_plan_concurrency holds a writer until no live writer holds those files
Owns: agent/plans/PLAN-preview-signer.md, private/account/src/middleware/error-handler.ts, private/account/src/services/license-signer.service.ts, private/account/tests/integration/license-signer-scope.test.ts, private/account/tests/integration/signer-*.test.ts, workers/signer/**, workers/www/src/index.ts, .ci/rediacc_ci/deploy/deploy_www.py, .ci/rediacc_ci/deploy/deploy_signer.py, .ci/rediacc_ci/deploy/preview_signer.py, .ci/rediacc_ci/housekeeping/cf_leftovers.py, .ci/rediacc_ci/housekeeping/cleanup_cf_preview.py, .ci/rediacc_ci/testrun/seed_smoke.py, .ci/rediacc_ci/tests/test_deploy_*.py, .ci/rediacc_ci/tests/test_housekeeping_*.py, .ci/rediacc_ci/tests/test_testrun_seed_smoke.py, .ci/scripts/test/smoke-test-preview.ts, .github/workflows/ci.yml, .github/workflows/ops-cleanup-preview.yml
Live-Proof: bench -- the account, www and enterprise surfaces all admit bench: signer-bench-eu gains the preview caller tier and is redeployed to bench, and the account smoke runs on the deployed tree
Owner: d778be9d
First-Seen: 2026-11-22

## Ask

Operator, 2026-11-22T04:23Z, answering the question of how `rdc` should work against a PR preview address (`https://pr-<n>.rediacc.workers.dev`): "Per-preview signer, as a plan". <!-- style-ok -->

## Context (read on branch 1121-1, 2026-11-22; a writer re-reads each line before relying on it)

1. A preview is deployed by `.ci/rediacc_ci/deploy/deploy_www.py --name pr-<n>` from the `deploy-preview` job (`.github/workflows/ci.yml:1553`). It gets its own D1 `account-pr-<n>` (`db_name_for`, deploy_www.py:236), binds `ACCOUNT` to `account-bench` (:200-202) and binds `LICENSE_SIGNER` to `signer-bench-eu` with props `{tier: "shared", region: "eu"}` (:213-218).
2. The comment at `workers/www/src/index.ts:13-16` is stale: it says `ACCOUNT` is absent on previews and that the D1 is `account-db-pr-N` minted by `deploy-www.sh`. Both bindings and the name changed. Box D1 corrects it.
3. The bench signer's shared verdict reads subscriptions only from its `SHARED` database, which is `account-bench`'s (`private/account/src/services/license-signer.service.ts:343-344`, `SIGNER_FOREIGN_SUBSCRIPTION`). A free-tier claim skips the lookup (:342) but still meets the host check (:332). Renewal hosts default to `<region>.rediacc.cloud` (:292) and come from `SHARED_HOSTS` (`workers/signer/wrangler.template.toml`), so a preview renewal URL fails with `SIGNER_WRONG_HOST` (:347-348). Every preview activation therefore fails.
4. The refusal reaches the client as a generic 500: `SignerRefusedError` (`private/account/src/services/signer-client.ts:39`) is not an `AppError` and the error handler falls through (worklist #8e42e148).
5. Renet validates a repo licence by signature against the build-time `ProductionPublicKey` (`private/renet/pkg/license/preferred.go:20-25`), or by a delegation cert signed by that key (`validator.go:80-150`, `delegation.go:23-55`). It checks no renewal URL or host. A delegated licence must carry the cert's subscription id and plan, and stay under the cert's size limit and issuance count (`validator.go:126-148`). The cert window is enforced on growth and skipped on operate (`delegation.go` doc comment).
6. The production key is the bench key: "Bench binds the production key by standing ruling" and all regional signers hold one private key "because renet bakes one public key" (PLAN-enterprise-isolation.md, Design "Signers" and "Bench and local dev"). A licence the bench signer signs is valid on every released renet.
7. Renet's subscription-blob validator looks the signing key up by `publicKeyId` in its own key map (`private/renet/pkg/subscription/validator.go:56-68`) and has no delegation path in that function. Whether machine activation consumes a master-signed subscription blob that a delegated key cannot produce is not settled by reading; box A1 settles it before any writer starts.
8. The CLI takes any `--server` URL and seeds the E2E key from server-info (`packages/cli/src/commands/config.ts:116-146`). Activation and repo create/fork/up call `/account/api/v1/licenses/activate-repo` (`packages/cli/src/services/account/license.ts:159`).
9. The preview smoke test's step 4, "Repo license issuance" (`.ci/scripts/test/smoke-test-preview.ts:228-260`), drives that route through the tunnel and fails on every preview today. Worklist #51fb685e scopes it out of the smoke test with a reason citing this plan; box T1 brings it back.
10. `ops-cleanup-preview.yml` deletes the Worker `pr-<n>` and the D1 `account-pr-<n>` on PR close and runs only for same-repository PRs (:33). `deploy-preview` has no such condition (ci.yml:1556-1560); a fork run fails at the Bitwarden step because GitHub withholds secrets from fork `pull_request` runs, which is a failure and not a guard. `cf_leftovers.py:45` treats `^pr-[0-9]+$` as owned by the close cleanup.
11. Finding: the preview Worker runs PR-authored code and holds a `shared`-tier binding to a signer that signs with the production key. Within the bench shared scope that code can ask for any licence or delegation cert an `account-bench` subscription admits, valid on production renet. The same job also holds the Cloudflare API token, so a contributor with write access already controls more than this binding. Design D2 removes the binding; the token is the release-path plan's subject (PLAN-release-path-protection-2027.md).

## Design

### D1. Where the per-preview signer lives

- Option A (recommended): a second Worker `pr-<n>-signer`, built from `workers/signer` with a preview template, deployed by the `deploy-preview` job right before `pr-<n>`. No route, no workers.dev host, reached only by the preview's `LICENSE_SIGNER` binding. It binds the preview D1 `account-pr-<n>` as `SHARED`, and `SHARED_HOSTS` is the one preview host `pr-<n>.rediacc.workers.dev`. The key lives in a Worker that serves no internet request, apart from the routed code.
- Option B: a `LicenseSigner` entrypoint inside the `pr-<n>` Worker itself. One Worker less, but the delegated key then sits in the isolate that answers every public request.
- Option C: keep `signer-bench-eu`, add preview hosts to its `SHARED_HOSTS` and teach it to read preview databases. Rejected: the production key keeps signing for PR code, and one Worker would need a binding per open PR.

### D2. Which key it signs with

- Option A (recommended): a fresh Ed25519 key pair generated by the deploy job on every deploy, the private half pushed only as a `wrangler secret bulk` secret of `pr-<n>-signer`, and a delegation cert for the public half signed by the central signer. The cert is fixed by the central signer, not by the caller: subscription = one bench subscription reserved for previews (`PREVIEW_SUBSCRIPTION_ID`, a var rendered by `deploy_signer.py` from trusted config, box P1), plan = that subscription's plan, small fixed size and issuance limits, `validFrom` now, `validUntil` at most 7 days ahead. `signer-bench-eu` gets a new caller tier `{tier: "preview", pr, host, region}` that admits only `signDelegationCert` and refuses every licence, blob and cert outside those fixed fields. `pr-<n>-signer` binds `signer-bench-eu` with that tier, fetches its cert once and caches it in the preview D1. `pr-<n>` no longer binds `signer-bench-eu` at all.
- Option B: a non-production renet build that trusts a preview key. Rejected: a fleet VM would need a second renet, and the proof would not be of the released binary.
- Option C: the production key as a secret of a PR-deployed Worker. Refused outright.

What a malicious PR can do with Option A, and what limits it: it can read the delegated private key of its own preview. With it, it can sign licences only for the preview subscription and plan, under the cert's size and issuance limits, and only until `validUntil`; renet refuses anything else (Context 5). It cannot mint a cert for another subscription, because the preview tier ignores the caller's subscription field. Host binding limits renewal only: the preview signer refuses a renewal URL other than its own host, so a licence cannot be renewed through it once the preview is gone. The residual risk is the one in Context 11: a write-access author who rewrites the binding props to `tier: "shared"` reaches today's scope again; that is closed by scoping the Cloudflare token, not by this plan.

### D3. Subscription binding inside the preview

Renet requires a delegated licence to carry the cert's subscription id (Context 5). The preview seed (`.ci/rediacc_ci/testrun/seed_smoke.py`) gives the smoke organisation a subscription whose id and plan equal the preview subscription's. The preview signer refuses any claim for another subscription with `SIGNER_FOREIGN_SUBSCRIPTION`, which after A0 reaches the client as a coded 403, so an organisation signed up fresh on a preview gets a clear refusal rather than a 500. A renet change admitting several subscriptions per cert was considered and rejected: it widens the production trust path for a test convenience.

### D4. Lifecycle

Created by `deploy-preview` on each push to the PR: new key pair, new secret, cert fetched on first use, so a redeploy retires the previous key. Destroyed by `ops-cleanup-preview.yml` on PR close (Worker `pr-<n>-signer` deleted beside `pr-<n>` and the D1), and by the housekeeping sweep: `cf_leftovers.py` and `cleanup_cf_preview.py` learn `^pr-[0-9]+-signer$` and delete one whose PR is closed or whose `pr-<n>` is gone. There is no revocation list in renet; expiry is the revocation, and the 7-day ceiling bounds a leaked key even when a cleanup fails. A licence already on a test VM keeps operating (up) after expiry and cannot grow, by renet's operate carve-out.

### D5. Renewal

`renewalUrl` is the preview host. The preview signer admits a licence claim only when its renewal host is `pr-<n>.rediacc.workers.dev`. Once the preview dies, the host answers nothing and the cert has expired, so renewal is refused twice over.

### D6. Fork safety

A preview of a PR from a fork never gets a signer. `deploy-preview` gains `github.event.pull_request.head.repo.full_name == github.repository` in its `if:`, the same condition `ops-cleanup-preview.yml:33` carries, so a fork run skips rather than failing at the Bitwarden step. `preview_signer.py` refuses to run when `GITHUB_EVENT_PATH` names a fork head, as a second line that does not depend on the workflow text.

### D7. Prerequisite and proof

A0 (worklist #8e42e148) maps `SignerRefusedError` to coded responses: `SIGNER_UNAVAILABLE` and `SIGNER_SCOPE_UNAVAILABLE` to 503, `SIGNER_RESPONSE_INVALID` to 502, every other code to 403, body `{error: "License signing refused", code}`. The smoke test's "Repo license issuance" check returns as the automatic proof (T1, V1), and a real machine run through `rdc config init --server <preview>` closes the plan (V2).

## Tasks

- [ ] A0 [writer] Coded signer refusals in the account error handler (worklist #8e42e148): the mapping of D7, with an integration test whose stub binding refuses `SIGNER_FOREIGN_SUBSCRIPTION` and expects 403 with that code, and one per status class. Ticked with the landed sha of #8e42e148 when that item lands first.
  Owns: private/account/src/middleware/error-handler.ts, private/account/tests/integration/signer-client.test.ts.
  Depends on: none.
  Accept: `cd private/account && npx vitest run tests/integration/signer-client.test.ts` rc 0, the 403 case failing before the change.
- [ ] A1 [lead] Settle Context 7 before any writer starts: list every signed artifact the activation, repo create/fork/up and renewal paths hand to renet or the CLI (repo licence, subscription blob, any other), and for each whether a delegation-cert signature is accepted, using the on-premise entry (`private/account/src/entry/on-premise.ts`) as the precedent. Record the answer in this plan with file:line evidence. If an artifact admits only the master key, stop and raise the design choice before S1.
  Owns: agent/plans/PLAN-preview-signer.md.
  Depends on: none.
  Accept: a dated "A1 findings" section in this plan, every claim with a file:line, and the on-premise unit tests it cites run rc 0.
- [ ] S1 [writer] The `preview` caller tier in the signer service: `parseSignerCaller` admits `{tier: "preview", pr, host, region}`; for that tier only `signDelegationCert` is allowed, and the cert's subscription, plan, limits and validity ceiling come from the signer's own config (`PREVIEW_SUBSCRIPTION_ID`, 7 days), never from the request. Plus the delegated signing mode the preview signer runs in: shared verdict against its own `SHARED`, renewal host fixed to its one host, a claim for any other subscription refused `SIGNER_FOREIGN_SUBSCRIPTION`, and `signDelegationCert` refused (no sub-delegation).
  Owns: private/account/src/services/license-signer.service.ts, private/account/tests/integration/license-signer-scope.test.ts.
  Depends on: A1.
  Accept: `cd private/account && npx vitest run tests/integration/license-signer-scope.test.ts` rc 0, covering: a preview caller asking for a licence is refused; a preview cert request naming another subscription still yields the configured one or is refused; validity beyond 7 days is refused; the delegated mode refuses a foreign subscription and a foreign renewal host.
- [ ] S2 [writer] The signer Worker in delegated mode: with `DELEGATED_PRIVATE_KEY` set and no `ACCOUNT_ED25519_PRIVATE_KEY`, it fetches its cert from its `CENTRAL_SIGNER` binding on first use, caches it in `SHARED`, signs with the delegated key and embeds the cert in every repo licence. A preview template `workers/signer/wrangler.preview.template.toml` (no route, no workers.dev, no CONTROL unless S1 needs it, `SHARED` = the preview D1, `SHARED_HOSTS` = the preview host, `CENTRAL_SIGNER` = `signer-bench-eu` with preview props). A Worker holding both keys refuses to start.
  Owns: workers/signer/**, private/account/tests/integration/signer-entrypoint-probe.test.ts.
  Depends on: S1.
  Accept: `cd workers/signer && npx tsc --noEmit` rc 0 and `cd private/account && npx vitest run tests/integration/signer-entrypoint-probe.test.ts` rc 0, extended with a delegated-mode case whose licence verifies against a test master key through the cert.
- [ ] D1 [writer] `rediacc_ci.deploy.preview_signer`: generates the key pair, renders the preview template, deploys `pr-<n>-signer`, pushes the private half through `wrangler secret bulk` on stdin (never argv, never printed), verifies the secret list, and refuses a fork head (D6). `deploy_www.py` points `LICENSE_SIGNER` at `pr-<n>-signer` instead of `signer-bench-eu`. The stale comment at `workers/www/src/index.ts:13-16` is corrected. `deploy_signer.py` renders `PREVIEW_SUBSCRIPTION_ID` for the bench targets only.
  Owns: .ci/rediacc_ci/deploy/preview_signer.py, .ci/rediacc_ci/deploy/deploy_www.py, .ci/rediacc_ci/deploy/deploy_signer.py, workers/www/src/index.ts, .ci/rediacc_ci/tests/test_deploy_preview_signer.py, .ci/rediacc_ci/tests/test_deploy_deploy_www.py, .ci/rediacc_ci/tests/test_deploy_signer.py.
  Depends on: S2.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_preview_signer.py .ci/rediacc_ci/tests/test_deploy_deploy_www.py .ci/rediacc_ci/tests/test_deploy_signer.py` rc 0, with a test that the rendered preview config names no route and no production key name, and that a fork event refuses.
- [ ] D2 [writer] Workflow wiring: `deploy-preview` gains the same-repository condition (D6) and runs `preview_signer` before `deploy_www`; `ops-cleanup-preview.yml` deletes `pr-<n>-signer` beside `pr-<n>`.
  Owns: .github/workflows/ci.yml, .github/workflows/ops-cleanup-preview.yml.
  Depends on: D1.
  Accept: `npm run -s check:ci-workflows` rc 0 and `npm run ci -- --narrow` rc 0.
- [ ] C1 [writer] Housekeeping: `cf_leftovers.py` and `cleanup_cf_preview.py` recognise `^pr-[0-9]+-signer$`, sweep one whose PR is closed or whose `pr-<n>` is gone, and never touch `signer-<r>` or `signer-bench-<r>`.
  Owns: .ci/rediacc_ci/housekeeping/cf_leftovers.py, .ci/rediacc_ci/housekeeping/cleanup_cf_preview.py, .ci/rediacc_ci/tests/test_housekeeping_cf_leftovers.py, .ci/rediacc_ci/tests/test_housekeeping_cleanup_cf_preview.py.
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_housekeeping_cf_leftovers.py .ci/rediacc_ci/tests/test_housekeeping_cleanup_cf_preview.py` rc 0, including a case where `signer-bench-eu` survives the sweep.
- [ ] P1 [lead] Reserve the preview subscription on bench: one organisation and subscription in `account-bench` used only by previews, its plan one whose delegation-cert ceiling admits 7 days; record the id in the trusted config `deploy_signer.py` reads (D1) and the seed (T1).
  Owns: none -- a bench data step; the id lands through D1 and T1.
  Depends on: A1.
  Accept: a read of the `account-bench` D1 through wrangler shows the row active with the recorded plan, the command and its output quoted in the tick.
- [ ] T1 [writer] The preview seed gives the smoke organisation the preview subscription id and plan (D3), and the smoke test's "Repo license issuance" step returns unconditionally, removing the scope-out of #51fb685e, and also verifies the embedded cert chains to the production public key.
  Owns: .ci/rediacc_ci/testrun/seed_smoke.py, .ci/rediacc_ci/tests/test_testrun_seed_smoke.py, .ci/scripts/test/smoke-test-preview.ts.
  Depends on: P1, S2.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_testrun_seed_smoke.py` rc 0 and `npx tsc --noEmit -p .ci/scripts/tsconfig.json` rc 0.
- [ ] X1 [lead] Deploy the preview tier to bench: `signer-bench-eu` redeployed with `PREVIEW_SUBSCRIPTION_ID` from this tree, then the account Worker, with the rollback line recorded.
  (corrected 2026-11-22) Local-route: deploy-bench -- the branch tree is deployed to bench from this checkout through deploy_signer and deploy_bench
  Owns: none (runs only).
  Depends on: S1, D1, P1.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-signer -- python3 -m rediacc_ci.deploy.deploy_signer --target bench-eu --record .ci/cache/live-deploys/signer-bench-eu.json` rc 0 and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` rc 0, then `./run.sh enterprise proof signer --bench` rc 0 (existing tiers unharmed).
- [ ] LP-bench [live] A fresh bench receipt after X1, recorded and ticked through `worklist.py --live-proof`.
  Accept: live-proof bench account-smoke
- [ ] V1 [lead] The preview smoke test on a real preview of this branch's PR passes every step, "Repo license issuance" included, with the licence's `publicKeyId` the delegated key's fingerprint and not the master key id.
  (corrected 2026-11-22) GitHub-only: preview -- a per-PR preview exists only through the deploy-preview job on a pushed PR head; no local deploy reproduces its D1, host and binding set
  Owns: none.
  Depends on: D2, T1, X1.
  Accept: `python3 .claude/hooks/ci-trace.py --pr <n>` shows the deploy-preview job SUCCESS with the smoke step log line `Repo license issued (keyId: <delegated fingerprint>)`.
- [ ] V2 [lead] The real machine run: `rdc config init preview-<n> --server https://pr-<n>.rediacc.workers.dev`, login as the seeded smoke account, `rdc machine add` and setup of a fleet VM, then `rdc repo create` of a 1 GB repo, `rdc repo up`, `rdc repo fork`, and a forced renewal. Then close the PR (or delete the preview) and show renewal refused and growth refused after expiry or key loss, while `repo up` still operates. Finally show `pr-<n>-signer` gone after `ops-cleanup-preview`.
  (corrected 2026-11-22) GitHub-only: preview -- the address under test is the per-PR preview host, which only the deploy-preview job creates
  Owns: none (runs only, on an ops VM 192.168.111.*).
  Depends on: V1.
  Accept: each command's exit code recorded in the tick (create, up, fork, renew rc 0; renewal after teardown non-zero with a coded refusal), and `npx --no-install wrangler deployments list --name pr-<n>-signer` failing with not-found after close.

## Risks

- Context 7 may show machine activation needs a master-signed blob; A1 exists so that is found before code, not after.
- The cert ceiling of the reserved plan may be below 7 days; P1 picks the plan by measurement and the 7-day figure follows it downward, never upward.
- Two live plans share the signer files; block_plan_concurrency serialises their writers, and S1 and S2 rebase onto whatever PLAN-enterprise-isolation.md lands first.
- Context 11 stays open for a write-access author until the Cloudflare token is scoped (PLAN-release-path-protection-2027.md).

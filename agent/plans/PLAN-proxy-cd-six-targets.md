# PLAN: the console executor goes live per region: the mock retires to a test fixture, and CD deploys a proxy Worker plus executor container for each of the six targets

Status: approved -- operator order 2026-10-25T18:10Z (retire the console mock; CD deploys a proxy and executor per target; deploys to the six targets plus bench allowed without asking; deploy_proxy.py's MANUAL ONLY clause lifted) and the rulings ASKED:2026-10-25T18:18Z (us/asia "Closed until smoke passes", CEK sessions "Re-grant transparently") and ASKED:2026-10-25T19:08Z (token "A: binding mints", stable "Ride promote-stable", cost "1 per target, 7 total but 21 max. So, can have 3 when needed"), quoted under Operator rulings
Priority: P1 -- until the mock retirement landed (see Verified state), every deployed account Worker could serve the canned mock run, because EXECUTOR_MODE defaults to 'mock' (private/account/src/types/env.ts:263) and no wrangler config sets it; a deployed Worker now refuses it with 503 `CONSOLE_EXECUTION_UNAVAILABLE` (TEST_MODE is pinned false), so the paid console shows no machines at all until the executor is live; the proxy runs only in eu with a long-lived `cloudflare`-bound token that any Worker in any Cloudflare account could present
First-Seen: 2026-10-25
Owner: d778be9d
Depends-On: no-dep -- the code boxes stand alone; L1 and later need the end-to-end machine named in L0 (hostinger only inside the H1 window of PLAN-renet-runtime-converge, otherwise a publicly reachable VM); the relations to PLAN-cloudflare-proxy.md (box C2, the operator redeploy box) and PLAN-telemetry-export.md (boxes T14, T15, T16) are stated under Relation to other plans
Concurrency: parallel -- writers take the disjoint per-box Owns below, and the sequencing lines name the few shared files (M1 before I1 on private/account/src/types/env.ts; M1 before I4 on private/account/src/routes/console.ts; M3 before R1 on web/src/hooks/useCommand.ts; D1 before E1 on .ci/config/secret-supply.json). PLAN-cloudflare-proxy.md also owns workers/proxy/**, deploy_proxy.py and its test; its only open boxes are live or teardown, so no code writer collides. PLAN-telemetry-export.md owns telemetry_delivery.py, workers/proxy/wrangler.toml and observability-export-wiring.test.ts with T14 and T16 open, so T1, K1 and G2 run only while no writer for that plan holds those files.
Owns: private/account/src/routes/console.ts, private/account/src/routes/proxy.ts, private/account/src/routes/api-tokens.ts, private/account/src/routes/configs.ts, private/account/src/dto/proxy.dto.ts, private/account/src/errors.ts, private/account/src/container.ts, private/account/src/types/env.ts, private/account/src/types/api-token.ts, private/account/src/middleware/api-token.ts, private/account/src/services/api-token.service.ts, private/account/src/services/executor-issuer.service.ts, private/account/src/services/config.service.ts, private/account/src/db/schema.ts, private/account/drizzle/**, private/account/src/entry/cloudflare.ts, private/account/tests/integration/console-session.test.ts, private/account/tests/integration/executor-mode-wiring.test.ts, private/account/tests/integration/executor-issuer*.test.ts, private/account/tests/integration/api-token-service-binding.test.ts, private/account/tests/integration/api-token-purge.test.ts, private/account/tests/integration/executor-grant-principal.test.ts, private/account/tests/integration/proxy-introspect-self.test.ts, private/account/tests/integration/console-org-gate.test.ts, private/account/tests/integration/observability-export-wiring.test.ts, private/account/tests/integration/proxy-binding-wiring.test.ts, private/account/e2e/tests/27-console/**, private/account/e2e/tests/20-config-storage/20-09-password-journey.test.ts, private/account/web/src/api/console.ts, private/account/web/src/api/executor-session.ts, private/account/web/src/api/__tests__/**, private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/__tests__/**, private/account/web/src/providers/ConfigSessionProvider.tsx, private/account/web/src/components/console/ResultView.tsx, private/account/web/src/components/console/__tests__/**, private/account/web/src/i18n/locales/*/console.json, private/account/CLAUDE.md, workers/account/src/index.ts, workers/account/wrangler.*.toml, workers/proxy/**, packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/sessions.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/__tests__/**, regions.json, .ci/config/well-known.env, .ci/rediacc_ci/well_known.py, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/env-manifest.json, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/deploy/executor_artifacts.py, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/deploy/console_executor.py, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py, .ci/rediacc_ci/tests/test_deploy_proxy_configs.py, .ci/rediacc_ci/tests/test_deploy_executor_artifacts.py, .ci/rediacc_ci/tests/test_deploy_deploy_record.py, .ci/rediacc_ci/tests/test_deploy_console_executor.py, .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py, .ci/rediacc_ci/tests/goldens/twins/deploy.deploy-proxy.jsonl, .ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py, .ci/rediacc_ci/quality/proxy_image_smoke.py, .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py, .ci/scripts/quality/check_proxy_image_smoke.py, .ci/scripts/quality/check_proxy_cost_guard.py, .ci/scripts/quality/check_proxy_deploy_dry_run.py, .ci/rediacc_ci/tests/test_quality_proxy_cost_guard.py, .ci/rediacc_ci/ops/telemetry_delivery.py, .ci/rediacc_ci/tests/test_ops_telemetry_delivery.py, .github/workflows/cd-deploy-account.yml, .github/workflows/cd-v2.yml, .github/workflows/promote-stable.yml, .github/workflows/ci-quality.yml, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, package.json, package-lock.json, docs/observability/**, docs/environment-variables.md, .claude/skills/deploy/SKILL.md, agent/plans/PLAN-proxy-cd-six-targets.md, agent/plans/PLAN-cloudflare-proxy.md (relation lines only), agent/plans/PLAN-telemetry-export.md (relation lines and its "Proxy results" section only), .github/workflows/**, .ci/policy/**

## Operator rulings

- **Operator order 2026-10-25T18:10Z.**
  - (a) The console mock stream retires. Production and edge never answer /console/exec with a mock. A deployed Worker with no executor configured fails closed with a clear "console execution is not available in this region" refusal. The mock survives only as a test fixture (dev gateway, vitest, console e2e), behind the same switch as the /test/* routes.
  - (b) CD deploys a proxy Worker and an executor container for each target (edge and stable × eu, us, asia), inside the existing per-target release steps. Bench stays a separate manual target.
  - Deploys to all six targets plus bench are allowed without asking. deploy_proxy.py's MANUAL ONLY clause is lifted by this ruling, together with its twin golden header and the tests that cite it.
  - Every live deploy records the version id per target, the smoke rc, the rollback command, and the D1 bookmark wherever an account deploy touches D1.
  - One live end-to-end console command per region proves the executor path.
  - Secrets travel only through bws_env, and only their names appear anywhere.
- **ASKED:2026-10-25T18:18Z us/asia "Closed until smoke passes".** CD switches a region's console executor on only after that region's proxy smoke passes. Until then the region refuses.
- **ASKED:2026-10-25T18:18Z CEK sessions "Re-grant transparently".** When the executor answers unknown-session, the web client re-opens a session and re-seals the CEK. A test proves that a redeploy in the middle of a session re-grants without a new unlock.
- **ASKED:2026-10-25T19:08Z token "A: binding mints".**
  - No EXECUTOR_TOKEN is exported. A new account-Worker WorkerEntrypoint, ExecutorIssuer (RPC only, no fetch), issues a 30-60 minute `proxy:exec`+`audit:write` token for the region's configured executor org and owner, and re-checks owner or admin at each mint.
  - The proxy binds it as ISSUER, caches the token and renews it at about 80% of its life.
  - A new IP-binding mode, 'service-binding', is accepted only when viaServiceBinding and refused on the public path.
  - The container gets a placeholder REDIACC_TOKEN. forwardAccountEgress swaps in the real Bearer only on an allowlist of the paths the container calls.
  - The self-check that sends the token in a request body is handled.
  - The scheduled handler purges expired api_tokens rows nightly, and every mint writes an audit event.
  - EXECUTOR_TOKEN leaves the wrangler configs, the deploy_proxy closing lines and rotation.
- **ASKED:2026-10-25T19:08Z stable "Ride promote-stable".**
  - Stable proxies deploy inside promote-stable beside deploy-account-stable, inheriting the 7-day soak and the nightly waiver.
  - The CLI bundle and renet for a version are stored durably at edge time and fetched by version, so the stable executor is byte-identical to the edge one.
  - The currently red nightly CI on main is fixed on this branch.
- **ASKED:2026-10-25T19:08Z cost "1 per target, 7 total but 21 max. So, can have 3 when needed".** max_instances = 3 for each proxy config (6 CD configs + bench = 7, a ceiling of 21). check_proxy_cost_guard.py discovers every workers/proxy/wrangler*.toml. Superseded for max_instances by the operator ruling ASKED:2026-10-26T15:26Z "Per-org, raise the cap" (PLAN-console-executor-multi-org Decision 3): 25 per config, 175 in total, with a container spend alarm in cf_usage_report; the seven-config set and sleepAfter 2m stand.

## Context

### Verified state (2026-10-25, console tree and private/account 57f5b22 plus its working tree)

- **Mock retirement landed after this design was drafted.** private/account fd466482 (console pointer 7211c7aa) and 7135ad73 (pointer a2684e4d) carry `consoleUnavailable()` with code `CONSOLE_EXECUTION_UNAVAILABLE`, `mockAllowed()` = `testMode && executorMode !== 'proxy'`, the refusal at the three legs, tests/integration/executor-mode-wiring.test.ts (which also refuses `[env.*]` tables), the coded ConsoleStreamError, the localized ResultView state (13 locales) and the CLAUDE.md console section. M1, M2 and M3 are checked against that landed code: what they ask beyond it (relaying `EXECUTOR_SESSION_UNKNOWN`, the Cloudflare-entry-pinned runtime test, refusing any EXECUTOR_MODE var, the proxy-config half of M2) is the remaining work.
- **The deployed /test/* switch is TEST_MODE.** It is read at private/account/src/app.ts:241, pinned false at private/account/src/entry/cloudflare.ts:34-39, defaulted true on the dev gateway (private/account/src/entry/dev-gateway.ts:34-37) and in vitest (private/account/tests/integration/helpers/test-db.ts:62).
- **IP binding today.** private/account/src/middleware/api-token.ts:72-100 accepts 'cloudflare' over the binding at :74 and from any Cloudflare IP on the public path at :84-96. `ip_binding` is a plain text column with no CHECK constraint (private/account/drizzle/0052_api_token_ip_binding.sql, private/account/src/db/schema.ts:317), so a new mode value needs no migration. No table holds a foreign key to api_tokens.
- **Container egress.** forwardAccountEgress is at workers/proxy/src/index.ts:107-131, with the '/account/' prefix check at :109 (the findings cited :99-123). executorEnvVars (:91-97) hands the container the real EXECUTOR_TOKEN.
- **Paths the container calls** (all under `/account/api/v1/`):
  - POST `proxy/introspect` (packages/cli/src/services/serve/auth.ts:96, and :142 for the self-check, whose body carries the executor token at :148)
  - POST `licenses/audit-events` (packages/cli/src/services/serve/audit.ts:124)
  - POST `configs/executor-token` (packages/cli/src/services/serve/container-config.ts:141)
  - GET `configs/<id>` with `X-Config-Token` and no bearer (:162)
  - POST `configs/executor-grant` (:197)
  - GET `telemetry/config`, unauthenticated (packages/cli/src/services/telemetry/otlp-credentials.ts:83)
  - GET `.well-known/server-info` (packages/cli/src/services/account/account-client.ts:161)

### Corrections to the findings and new load-bearing facts

1. **The web client retries an unknown session only on the grant leg.** `openAndGrant` (private/account/web/src/api/executor-session.ts:115-123) re-opens once when the CEK leg answers 404. An exec that answers 404 is thrown as a ConsoleStreamError, and no caller calls `forget()` and retries: `forget()` is called only on lock and on team switch (private/account/web/src/providers/ConfigSessionProvider.tsx:199,:430). The re-grant ruling therefore needs new code (R1), not just a test.
   - Retrying the exec is safe because the executor validates the named session before the loader and dispatch run (packages/cli/src/services/serve/server.ts:188-194).
   - SessionError maps to 404 for every cause (packages/cli/src/services/serve/server.ts:70), including config-fetch failures (packages/cli/src/services/serve/container-config.ts:150,:166). That is why R2 adds a distinct code.
2. **Executor grants are keyed on the executor's token id.** The grant lookup matches `configExecutorGrants.executorTokenId` (private/account/src/services/config.service.ts:2164-2177; schema private/account/src/db/config-schema.ts:320-347). With an issued token renewed every ~36 minutes, every live session would stop finding its grant at each renewal. I2 keys grants on a stable executor principal instead.
3. **One executor serves one org.** Introspection answers `active:false` for a token from any org other than the executor token's (private/account/src/routes/proxy.ts, the `targetOrg.id !== callerOrg.id` check). A regional proxy therefore serves only members of the configured executor org. Any other org reaching the console would get a confusing relayed 401, so I4 refuses those callers with the same coded 503 (a DEFAULT, see Decisions). Serving every org is outside this plan.
4. **CD line numbers moved.**
   - .github/workflows/cd-deploy-account.yml: deploy job :147-, Resolve deploy config :287-297, Deploy account Worker :331-332, Set Worker secrets :337-400. The workflow has only `target` and `ref` inputs (:9-17), so D2 adds `version`.
   - .github/workflows/promote-stable.yml: deploy-account-stable :267-279, verify-stable needs at :295.
5. **Service bindings are open to any Worker in the same Cloudflare account.** Any Worker in the account that names an entrypoint in `[[services]]` reaches it. G2 adds a gate that only workers/proxy/wrangler.<target>.toml files name `ExecutorIssuer` or `CloudflareInternal`. UNVERIFIED: whether a PR-built preview Worker could carry such a block.
6. **The renet the image uses for bench is different.** Bench signs licences with the DEV key, so its executor cannot run the release renet. Bench keeps the local build path (deploy_proxy.py builds renet with the key bound by the `deploy-proxy-bench` profile).
7. **The red nightly** is Console CI scheduled run 40166548833, attempt 3, on 2026-10-25 at 08:16Z. Nine jobs failed:
   - Quality / Security, step Audit: body-parser high GHSA-27r3-jxmh-p828; fast-uri GHSA-w74x-v6f9-j3xg and GHSA-xhq7-xmqj-769h.
   - Quality / Code (3), Pin upstream freshness.
   - Quality / Code (4), Action freshness: docker/login-action.
   - Quality / Content, External dependency freshness.
   - Quality / i18n, Plan file housekeeping.
   - Quality / Go, Go dependency freshness.
   - Renet pkg matrix (opensuse-16.0), OBS upstream serves the pin: the ceph squid rebuild.
   - Quality / Shard receipts and CI Complete, which are aggregates of the above.
   - Housekeeping (CI time budget) and Pins Soaked are also red, but the soak waiver keys on Console CI, so they are named here and left out of N1.
8. **Telemetry plan status.** PLAN-telemetry-export T16's tool exists (telemetry_delivery.py, tests passing) but the box is unticked, and the workflow is not on main. T14's config half already sits in workers/proxy/wrangler.toml, and that box is unticked as well.

### Unverified claims (each is proved or refuted by the box named)

- U1 (L1): wrangler refuses to deploy a Worker whose `[[services]]` names a Worker that does not exist, but accepts a missing named entrypoint (runtime failure only). The second half is what the comment at workers/account/wrangler.eu.toml:69 implies. D2's bootstrap order works either way.
- U2 (L1): the CD Cloudflare token carries the Containers, registry-push, custom-domain DNS and Advanced Certificate permissions a first proxy deploy needs. A nested custom domain (`proxy.edge-us.rediacc.com`) gets its Advanced Certificate created by the deploy.
- U3 (A1): the CI renet artifact (`renet-binaries-<sha>`, retention 1 day, .github/workflows/ci-build-renet.yml:198-213, :360-) embeds the production licence public key, and edge and stable verify licences with the same key. A1 confirms both before choosing it as the source; if either fails, A1 builds renet in the CD edge job with the production key bound through bws.
- U4 (L0): a root user (ROOT_EMAIL) owns an org with an active subscription in each of the seven D1 databases.
- U5 (P1): `wrangler dev` with two configs (proxy plus a stub issuer Worker) resolves a named-entrypoint binding locally, as proxy_wrangler_dev_e2e needs.
- U6 (W1): the Alloy transform already maps `rediacc-proxy-eu` to `service.name = rediacc-proxy`, as docs/observability/signals/proxy.md claims.
- U7 (D1): the procedure that rewrites a frozen twin golden. D1 follows the goldens' own regeneration path and records the command it used.

## Design

1. **Mock retirement.**
   - The mock answers only when `testMode && executorMode !== 'proxy'`. Every other non-proxy case answers 503 `CONSOLE_EXECUTION_UNAVAILABLE` with the message "console execution is not available in this region".
   - TEST_MODE is pinned false on Workers, so production, edge, bench and preview can never stream the mock, even with EXECUTOR_MODE=mock delivered as a var or a secret.
   - relayedFailure relays the upstream `code` for one allowlisted value, `EXECUTOR_SESSION_UNKNOWN`. Today it drops codes (private/account/src/routes/console.ts:183-189).
2. **Switching the executor on per region.**
   - EXECUTOR_MODE leaves `[vars]` for good. The M2 gate refuses it in any workers/account config.
   - CD sets it as a Worker secret, `proxy`, with `wrangler secret put` (console_executor.py), and only after that target's proxy smoke passes. Rollback is `wrangler secret delete EXECUTOR_MODE`, which falls back to the default 'mock', which a deployed Worker refuses.
   - A secret survives later account deploys, so a region stays open across releases once proven. A failed proxy smoke in a later release closes it first (D2).
   - The EXECUTOR service binding gives the route, so EXECUTOR_URL stays unset on Workers.
3. **Issued executor tokens.**
   - `export class ExecutorIssuer extends WorkerEntrypoint` in workers/account/src/index.ts has one RPC method, `issue()`, takes no arguments and has no fetch. It returns `{ token, expiresAt }` for a 45-minute token with scopes exactly `proxy:exec` and `audit:write`, ipBinding `'service-binding'`, and a new nullable column `api_tokens.issuer_key = executor:<ENVIRONMENT>:<REGION>`.
   - The owner is the ROOT_EMAIL user, already a bws-supplied Worker secret, and the org is the one they own. `EXECUTOR_ISSUER_ORG_ID` in `[vars]` disambiguates when there is more than one (a DEFAULT).
   - Each mint re-checks that the owner still holds owner or admin and that the subscription is active. A failed check refuses with a reason code and writes an `executor_token.refused` audit event. A success writes `executor_token.issued` (token id, issuer_key, expiresAt, never the value).
   - The public POST /api-tokens route refuses `'service-binding'`, and from this plan on also refuses new `'cloudflare'` tokens.
   - The middleware accepts `'service-binding'` only when `viaServiceBinding`. On the public path it answers 403 whatever the source IP.
   - The scheduled handler deletes api_tokens rows whose `expires_at` is more than 7 days past, a grace window that keeps audit cross-references readable for a week.
4. **Executor principal for grants.** `executorPrincipalOf(token) = token.issuer_key ?? token.id`. config_executor_grants stores the principal in `executor_token_id`. Legacy rows hold token ids, which equal the principal of a token without an issuer_key, so no grant migration is needed. Only the api_tokens column migration runs, and it is the D1 change whose bookmark every account deploy records.
5. **The proxy Worker.**
   - `ISSUER: Service` replaces `EXECUTOR_TOKEN`. A module-scope cache renews the token at 80% of its life, with single-flight per isolate.
   - The container env carries `REDIACC_TOKEN = rediacc-executor-placeholder`.
   - forwardAccountEgress accepts only the method and path pairs listed under Context.
     - On the four executor-bearer paths (introspect, audit-events, executor-token, executor-grant) it requires `Authorization` to be exactly `Bearer <placeholder>` and swaps in the issued token.
     - On the other three it strips any Authorization.
     - Any other path, method, or Authorization value is refused with 403 and a logged reason code.
   - The container can reach only the ACCOUNT binding through this function. ISSUER is never reachable from container egress.
   - A new unauthenticated `/v1/ready` obtains the issued token and introspects it over ACCOUNT with `{ self: true }`. It answers 200 `{ ready: true, workerVersion }`, using a `[version_metadata]` binding, or 503 `{ ready: false, reason }`. The result is cached for 30 s, so the endpoint cannot be driven into mint storms.
6. **Self-introspection.** tokenIntrospectRequest gains optional `self: true`, which introspects the bearer itself, and the server prefers it when present. The CLI self-check sends `{ token, self: true }`. An older on-premise server strips the unknown key and reads `token` as before, so daemon mode is unchanged.
7. **Configs.**
   - workers/proxy/wrangler.toml becomes wrangler.eu.toml. Five new configs (wrangler.us.toml, wrangler.asia.toml, wrangler.edge-eu.toml, wrangler.edge-us.toml, wrangler.edge-asia.toml) are generated with them by `rediacc_ci.deploy.proxy_configs` from one template plus regions.json, which gains `proxyWorkerName` and `edgeProxyWorkerName`.
   - Names: `rediacc-proxy-<r>` and `edge-rediacc-proxy-<r>`. Routes: `proxy.<domain>` and `proxy.<edgeDomain>`, as custom domains, in .ci/config/well-known.env.
   - `ACCOUNT` (entrypoint CloudflareInternal) and `ISSUER` (entrypoint ExecutorIssuer) both point to the same target's account Worker.
   - `REGION`; `ENVIRONMENT` = production or edge; the otlp-<r> destination pair with `persist = false`; `max_instances = 3`; `sleepAfter` stays 2m.
   - Bench and dev stay hand-written but pass the same refusals (`config_refusals`, generalizing bench_refusals):
     - an exact name, route, ACCOUNT_URL, binding set and entrypoints;
     - REGION and ENVIRONMENT values;
     - destinations;
     - the top-level key allowlist;
     - no `[env.*]` table;
     - and a name, route or service token naming any other region or channel is refused by name (a us config can never carry an eu binding).
   - The account configs bind `EXECUTOR` to the same target's proxy. Bench gains one, to rediacc-proxy-bench.
8. **Durable executor artifacts.**
   - At edge time `rediacc_ci.deploy.executor_artifacts stage --version V` writes, once, `executor/v<V>/` in the releases R2 bucket:
     - cli-bundle.cjs and package.json, from cli-bundle-<sha>, .github/workflows/ci-build-docker.yml:93-103;
     - renet-linux-amd64, from renet-binaries-<sha>;
     - node-natives-linux-x64.tar, holding ssh2 and cpu-features built at the lockfile versions;
     - manifest.json, with each file's sha256, the version and the git sha.
   - `fetch --version V --dest workers/proxy/stage/` verifies every sha256 and refuses a mismatch. The Dockerfile copies stage/, re-runs `sha256sum -c`, and builds nothing from source. The base image is pinned by digest.
   - Retention: never trim the current or previous production version, plus the newest KEEP_RELEASES versions.
   - Rollback redeploys the previous version's config and fetched artifacts, because Cloudflare documents no container rollback.
9. **CD order inside the per-region deploy job (D2).**
   - Forward: record-before (the account and proxy version ids, and the D1 time-travel bookmark taken before migrations), then:
     1. a bootstrap proxy deploy, only when the proxy Worker does not exist yet (U1);
     2. Deploy account Worker;
     3. Set Worker secrets;
     4. Deploy proxy Worker (`deploy_proxy --target --region --version`);
     5. Proxy smoke (health 200, unauthenticated server-info 401, `/v1/ready` 200 with `workerVersion` equal to the deployed id, polled for up to 5 minutes);
     6. Enable console executor, only when the smoke step succeeded.
   - Failure path (`if: failure()`), in reverse: disable the console executor, redeploy the previous proxy version from record-before (nothing for a first deploy), then print the account rollback and D1 restore commands. Both are destructive enough to stay human-run.
   - The record (`deploy-record-<target>-<region>.json`: worker names, version ids before and after, the D1 bookmark, the smoke rc, the executor manifest sha256s, the rollback command) goes to the job summary and an artifact.
   - promote-stable and the cd-v2 hotfix call the same reusable workflow with `target: stable`. Edge passes `version: next_version`.
10. **Rollout risks from the Cloudflare documentation.**
    - A new image rolls out gradually, and old instances get SIGTERM with up to 15 minutes before SIGKILL. A redeploy therefore loses every executor session, which R1 covers.
    - "Deploy success means the rollout started", so the smoke polls `workerVersion`.
    - Each script has its own DO namespace. The existing `[[migrations]] tag = "v1"` applies to every new script.

## Tasks

### Account: console and refusal (private/account submodule PR first)

- [x] M1 [account-console] Finish and commit the mock-retirement draft. The three legs refuse with 503 `CONSOLE_EXECUTION_UNAVAILABLE` whenever `mockAllowed()` is false and the mode is not proxy. relayedFailure relays the upstream `code` only for `EXECUTOR_SESSION_UNKNOWN`. console-session.test.ts proves:
  - the mock under TEST_MODE;
  - the coded 503 with TEST_MODE false and EXECUTOR_MODE mock;
  - the coded 503 with EXECUTOR_MODE proxy and neither binding nor URL;
  - the coded 503 through an app built with the Cloudflare entry's env pinning while the raw env carries `TEST_MODE: true, EXECUTOR_MODE: 'mock'`, which is the runtime refusal on production and edge;
  - a relayed 404 that keeps `code`.
    (ticked) 2026-10-26T11:29:41Z by d778be9d: account fd46648 and 81fc892 (pointer 8d9ad4621): mockAllowed and the coded 503 in private/account/src/routes/console.ts:79; cd private/account && npx vitest run tests/integration/console-session.test.ts rc=0 (19 passed); cd private/account/e2e && npx playwright test --project=chromium tests/27-console/27-01-console.test.ts tests/20-config-storage/20-09-password-journey.test.ts rc=0 (16 passed, 2026-10-26, ./run.sh account dev with ROOT_EMAIL set; cd private/account && npm run typecheck rc=0 (2026-10-26))
  
  The e2e fixtures 27-01 and 20-09 name TEST_MODE as the reason the mock answers. -- Owns: private/account/src/routes/console.ts, private/account/src/errors.ts, private/account/src/container.ts, private/account/src/types/env.ts (the EXECUTOR_MODE comment only), private/account/tests/integration/console-session.test.ts, private/account/e2e/tests/27-console/27-01-console.test.ts, private/account/e2e/tests/20-config-storage/20-09-password-journey.test.ts, private/account/CLAUDE.md. Accept: `cd private/account && npx vitest run tests/integration/console-session.test.ts` exits 0, `npm run typecheck` exits 0, and `cd private/account/e2e && npx playwright test tests/27-console/27-01-console.test.ts tests/20-config-storage/20-09-password-journey.test.ts` exits 0 against the dev gateway.
- [x] M2 [account-gate] The deployed-config gate, modelled on tests/integration/cron-wiring.test.ts. Every workers/account/wrangler.*.toml `[vars]` sets neither EXECUTOR_MODE (any value, because CD owns it as a secret) nor TEST_MODE. Every workers/proxy/wrangler*.toml except wrangler.dev.toml sets neither. Controls show the parser sees a planted assignment. -- Owns: private/account/tests/integration/executor-mode-wiring.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-mode-wiring.test.ts` exits 0, and a scratch copy of workers/account/wrangler.us.toml with `EXECUTOR_MODE = "proxy"` added, pointed to by the test's directory override, makes it fail.
    (ticked) 2026-10-26T03:33:36Z by d778be9d: account c76a4e6e (pointer 0bd5f6b4a): executor-mode-wiring refuses any EXECUTOR_MODE and TEST_MODE in account [vars] and checks the seven proxy configs; vitest rc=0; a scratch wrangler.us.toml with EXECUTOR_MODE=proxy fails it (1 failed)
- [x] M3 [account-web] Localized refusal state. ConsoleStreamError carries status and code. A result whose `errorCode` is `CONSOLE_EXECUTION_UNAVAILABLE` renders a dedicated state from `console.json` key `executionUnavailable` (title and body) in all 13 locales instead of the raw message. -- Owns: private/account/web/src/api/console.ts, private/account/web/src/hooks/useCommand.ts, private/account/web/src/components/console/ResultView.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/components/console/__tests__/result-view-unavailable.test.tsx. Accept: `cd private/account/web && npx vitest run src/components/console/__tests__/result-view-unavailable.test.tsx` exits 0, and `npm run check:ci-i18n-completeness` and `npm run check:ci-i18n-placeholders` exit 0.
    (ticked) 2026-10-26T10:25:12Z by d778be9d: account fd46648 (pointer 7211c7aa1): ConsoleStreamError status and code in private/account/web/src/api/console.ts, the executionUnavailable state at private/account/web/src/components/console/ResultView.tsx:131; cd private/account/web && npx vitest run src/components/console/__tests__/result-view-unavailable.test.tsx rc=0 (2 passed); npm run check:ci-i18n-completeness rc=0; npm run check:ci-i18n-placeholders rc=0
- [x] R1 [account-web] Transparent re-grant, after M3 (useCommand.ts) and R2 (the code). When an exec fails with status 404 and code `EXECUTOR_SESSION_UNKNOWN`, useCommand calls the exec manager's `forget()` and retries the exec exactly once. The retry re-opens and re-seals through `getCek` with the CEK still held in memory, without a new unlock. Any other 404, or a second failure, surfaces unchanged. The redeploy test drives open, grant and exec against a fake executor, then wipes the fake's session store (a redeploy), then runs the next exec. It asserts one new open and grant, the exec succeeding, the unlock callback never called, and exactly one retry. -- Owns: private/account/web/src/hooks/useCommand.ts, private/account/web/src/api/executor-session.ts, private/account/web/src/providers/ConfigSessionProvider.tsx, private/account/web/src/hooks/__tests__/useCommand-regrant.test.ts, private/account/web/src/api/__tests__/executor-session.test.ts. Accept: `cd private/account/web && npx vitest run src/hooks/__tests__/useCommand-regrant.test.ts src/api/__tests__/executor-session.test.ts` exits 0.
    (ticked) 2026-10-26T03:33:51Z by d778be9d: account 102f353f (pointer 59df9e115): re-grant on EXECUTOR_SESSION_UNKNOWN; useCommand-regrant and executor-session vitest rc=0

### Account: issuer, token mode, grants

- [x] I1 [account-issuer] ExecutorIssuer, the 'service-binding' mode, audit and purge, after M1 (env.ts).
  - Build ExecutorIssuer and the IssuerService as in Design item 3. The `issuer_key` migration is the next drizzle number.
  - `EXECUTOR_ISSUER_ORG_ID` is an optional var.
  - `IP_BINDING_MODES` gains `'service-binding'`, allowed only with `proxy:exec`.
  - The middleware accepts it only over the binding. The public create route refuses it, and refuses new `'cloudflare'` tokens.
  - The scheduled handler gains `purgeExpiredApiTokens` (7-day grace).
  - Adversarial tests:
    - a service-binding token on the public path is refused with 403, including from an address inside the Cloudflare ranges;
    - it is accepted through `fetchViaServiceBinding`;
    - the public route refuses to create one;
    - an owner demoted to member gets a refused mint with an audit event;
    - a mint writes `executor_token.issued` with no token value in any column;
    - scopes are exactly the two;
    - TTL is between 30 and 60 minutes;
    - purge deletes only rows past the grace window;
    - `ExecutorIssuer.prototype.fetch` is undefined.
    (ticked) 2026-10-26T04:25:20Z by d778be9d: account 5c4daf48 and console 1d2cb1f3c: ExecutorIssuer, service-binding mode, migration 0065, purge; executor-issuer, api-token-service-binding, api-token-purge, cron-wiring vitest rc=0; typecheck rc=0
  
  -- Owns: workers/account/src/index.ts, private/account/src/entry/cloudflare.ts, private/account/src/services/executor-issuer.service.ts, private/account/src/services/api-token.service.ts, private/account/src/types/api-token.ts, private/account/src/types/env.ts, private/account/src/middleware/api-token.ts, private/account/src/routes/api-tokens.ts, private/account/src/db/schema.ts, private/account/drizzle/**, private/account/tests/integration/executor-issuer.test.ts, private/account/tests/integration/api-token-service-binding.test.ts, private/account/tests/integration/api-token-purge.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-issuer.test.ts tests/integration/api-token-service-binding.test.ts tests/integration/api-token-purge.test.ts tests/integration/cron-wiring.test.ts` exits 0 and `npm run typecheck` exits 0.
- [x] I2 [account-grants] Grants keyed on the executor principal (Design item 4), after I1. A grant recorded under issued token A is found by a config-token request under issued token B with the same issuer_key. A grant recorded by a token with a different issuer_key, or by an ordinary proxy:exec token, is not found. Legacy rows keep working. -- Owns: private/account/src/services/config.service.ts, private/account/src/routes/configs.ts, private/account/tests/integration/executor-grant-principal.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-grant-principal.test.ts tests/integration/proxy-*.test.ts` exits 0.
    (ticked) 2026-10-26T03:33:47Z by d778be9d: account e58ef9b2 (pointer 0bd5f6b4a): grants keyed on executorPrincipalOf; executor-grant-principal and proxy-* vitest rc=0
- [x] I3 [account-introspect] `self: true` introspection (Design item 6). The body `{ token: "<anything>", self: true }` introspects the bearer, and `{ token }` alone behaves as today. -- Owns: private/account/src/routes/proxy.ts, private/account/src/dto/proxy.dto.ts, private/account/tests/integration/proxy-introspect-self.test.ts. Accept: `cd private/account && npx vitest run tests/integration/proxy-introspect-self.test.ts tests/integration/proxy-cli-token.test.ts` exits 0.
    (ticked) 2026-10-26T03:33:40Z by d778be9d: account 66beddd (pointer 8d9ad4621): self: true introspection; proxy-introspect-self and proxy-cli-token tests rc=0
- [x] I4 [account-console] Console org gate (a DEFAULT, see Decisions), after M1 and I1. With the executor on, a caller whose resolved org is not the issuer's org gets the coded 503 instead of a relayed 401. -- Owns: private/account/src/routes/console.ts, private/account/tests/integration/console-org-gate.test.ts. Accept: `cd private/account && npx vitest run tests/integration/console-org-gate.test.ts tests/integration/console-session.test.ts` exits 0.
    (ticked) 2026-10-26T03:33:49Z by d778be9d: account c76a4e6e (pointer 0bd5f6b4a): console org gate; console-org-gate and console-session vitest rc=0

### CLI executor

- [x] R2 [cli] The unknown-session code. The three `Unknown or expired session` throws (packages/cli/src/services/serve/sessions.ts:131,:221,:242) carry `code: 'EXECUTOR_SESSION_UNKNOWN'`, and statusFor (packages/cli/src/services/serve/server.ts:67-78) puts it in the 404 body. Config-fetch SessionErrors stay uncoded. The test asserts the code on an exec naming a wiped session and no dispatch on that path. -- Owns: packages/cli/src/services/serve/sessions.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/__tests__/session-unknown-code.test.ts. Accept: `cd packages/cli && npx vitest run src/services/serve/__tests__/session-unknown-code.test.ts` exits 0 and `npx tsc --noEmit --project packages/cli/tsconfig.json` exits 0.
    (ticked) 2026-10-26T04:25:13Z by d778be9d: commit 3bd4b6e7f: EXECUTOR_SESSION_UNKNOWN on the three throws and in the 404 body; session-unknown-code test rc=0; tsc rc=0
- [x] P2 [cli] The self-check sends `{ token, self: true }` (packages/cli/src/services/serve/auth.ts:139-166). The test asserts the body shape, and that a server answering only the legacy shape still yields the audit capability. -- Owns: packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/__tests__/audit-capability-self.test.ts. Accept: `cd packages/cli && npx vitest run src/services/serve/__tests__/audit-capability-self.test.ts src/services/serve/__tests__/grand-repo-guard.test.ts` exits 0.
    (ticked) 2026-10-26T04:25:47Z by d778be9d: commit 3bd4b6e7f: the self-check sends { token, self: true }; audit-capability-self test rc=0 with grand-repo-guard

### Proxy Worker, configs, image, deploy

- [x] P1 [proxy] The Worker side of Design item 5.
  - Build the ISSUER token source, the placeholder REDIACC_TOKEN, the egress allowlist with the bearer swap, and `/v1/ready`.
  - Remove `EXECUTOR_TOKEN` from Env and from every comment.
  - proxy_wrangler_dev_e2e runs with a stub issuer Worker (U5).
  - Adversarial tests:
    - a container request on a non-allowlisted path gets 403;
    - an allowlisted path with a caller token in Authorization gets 403;
    - an allowlisted executor path with the placeholder reaches ACCOUNT with the issued Bearer and never the placeholder;
    - `telemetry/config` reaches ACCOUNT with no Authorization;
    - no egress path calls ISSUER, because the issuer fake counts zero calls from egress;
    - renewal happens once at 80% of life under 10 concurrent requests;
    - `/v1/ready` answers 503 `issuer-refused` when the issuer throws;
    - the container env never holds the issued token.
    (ticked) 2026-10-26T11:02:02Z by d778be9d: 777daf03f with 92200dfc: the container boots on EXECUTOR_TOKEN_PLACEHOLDER (workers/proxy/src/egress.ts:17, workers/proxy/src/index.ts:100), the ISSUER binding mints and the egress swaps the placeholder; cd workers/proxy && npm run test:unit rc=0 (80 passed); npm run check:ci-proxy-wrangler-dev-e2e rc=0 (45 controls; 401 for no bearer and an inactive token with no container started, 200 container mode for a proxy:exec bearer, teardown clean)
  
  -- Owns: workers/proxy/src/**, .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py. Accept: `cd workers/proxy && npm run test:unit` exits 0, and `npm run check:ci-proxy-wrangler-dev-e2e` exits 0 on a docker host.
- [x] K1 [proxy-config] Six configs plus refusals (Design item 7).
  - Add `.ci/rediacc_ci/deploy/proxy_configs.py` (`generate`, `--check`, `config_refusals`) and the template.
  - Rename wrangler.toml to wrangler.eu.toml and generate the other five. Bench gains ISSUER, `[version_metadata]` and max_instances 3, and loses the EXECUTOR_TOKEN comment. Dev drops EXECUTOR_TOKEN.
  - regions.json gains the proxy names. well-known.env and well_known.py gain WK_PROXY_US_HOST, WK_PROXY_ASIA_HOST, WK_PROXY_EDGE_EU_HOST, WK_PROXY_EDGE_US_HOST and WK_PROXY_EDGE_ASIA_HOST.
  - The account configs bind EXECUTOR to the same target's proxy.
  - MUST_NOT_MATCH in the preview-reaping test gains the five new names.
  - The tests plant, one at a time:
    - an eu ACCOUNT service in the us config;
    - an edge service in a stable config;
    - a `proxy.eu` route in asia;
    - ENVIRONMENT production in an edge config;
    - an otlp-eu destination in us;
    - `persist = true`;
    - `max_instances = 4`;
    - an `[env.x]` table;
    - an `account_id` key;
    - a stale generated file.
    (ticked) 2026-10-26T04:25:15Z by d778be9d: commit 0bd5f6b4a: six generated configs, config_refusals, well-known hosts, account EXECUTOR bindings; pytest test_deploy_proxy_configs and preview reaping rc=0; proxy_configs --check rc=0
    
    Each must be refused by name.
  
  -- Owns: workers/proxy/wrangler*.toml, workers/proxy/wrangler.template.toml, workers/account/wrangler.*.toml, regions.json, .ci/config/well-known.env, .ci/rediacc_ci/well_known.py, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/tests/test_deploy_proxy_configs.py, .ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_proxy_configs.py .ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py` exits 0 and `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs --check` exits 0.
- [x] A1 [artifacts] Durable versioned executor artifacts (Design item 8), after resolving U3. Add `executor_artifacts stage|fetch|stage-local`, where stage-local serves bench and local runs from a tree build. Tests use a fake R2 (`aws` on PATH) and assert:
  - write-once (a second stage with equal sha256s skips, unequal refuses);
  - a fetch with one flipped byte refuses;
  - the manifest carries version and git sha;
  - retention never selects the current or previous production version.
    (ticked) 2026-10-26T04:25:17Z by d778be9d: commit 5a34c566b: executor_artifacts stage/fetch/stage-local/retain; pytest test_deploy_executor_artifacts rc=0 (15)
  
  -- Owns: .ci/rediacc_ci/deploy/executor_artifacts.py, .ci/rediacc_ci/tests/test_deploy_executor_artifacts.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_executor_artifacts.py` exits 0.
- [x] A2 [proxy-image] The Dockerfile consumes workers/proxy/stage/: it copies the bundle, renet and natives, runs `sha256sum -c` against the manifest, has no `npm ci` or source build, pins the base image by digest, and keeps the `renet version` check. The image smoke stages through `executor_artifacts stage-local`. -- Owns: workers/proxy/Dockerfile, workers/proxy/stage/.gitkeep, .ci/rediacc_ci/quality/proxy_image_smoke.py, .ci/scripts/quality/check_proxy_image_smoke.py. Accept: `npm run check:ci-proxy-image-smoke` exits 0, and the built image's `node cli-bundle.cjs --version` equals the staged manifest version.
    (ticked) 2026-10-26T10:33:20Z by d778be9d: npm run check:ci-proxy-image-smoke rc=0 (2026-10-26, a 0.0.0-local stage, bundle and renet matching the manifest sha256s); the version-equality rule at .ci/rediacc_ci/quality/proxy_image_smoke.py:140 applies to a released stage and its selftest controls (a disagreeing bundle and a disagreeing renet are findings) pass; workers/proxy/Dockerfile:20 pins the base by digest and workers/proxy/Dockerfile:45 runs sha256sum -c with no npm ci; the built-image `node cli-bundle.cjs --version` equality was NOT run for A2 (a 0.0.0-local stage carries no released version), and that half of the Accept is carried by the L1 live box, whose first released-stage run checks it
- [x] D1 [proxy-deploy] Generalize deploy_proxy.py, after K1, A1 and A2.
  - `--target edge|stable|bench` and `--region eu|us|asia` (bench refuses any region other than eu). `--config wrangler.<...>.toml` is always passed. `config_refusals` runs before any profile, token or build.
  - Non-bench runs fetch artifacts with `--version`; bench runs stage-local with the DEV-key renet.
  - Capture the version id from the tee'd wrangler output (`Current Version ID:`), cross-checked against `wrangler deployments list --json`.
  - The smoke adds `/v1/ready` (200, with `workerVersion` equal to the captured id) after health 200 and server-info 401.
  - `--record <path>` writes the record. `--smoke-only` exists for CD. Dry runs work for every target.
  - The docstring's MANUAL ONLY paragraph is replaced by one citing operator order 2026-10-25T18:10Z (CD deploys it). The twin golden header follows (U7).
  - The closing lines print worker, version id and rollback command, with no EXECUTOR_TOKEN.
  - Remove EXECUTOR_TOKEN from env-manifest.json, secret-supply.json and docs/environment-variables.md.
  - Add a `deploy-proxy` profile (Workers token, account id, production licence public key, names only) and a `live-console` profile for E1 (executor-org member login, names only).
  - Tests pin the six configs' argv, a us config carrying an eu binding refused before the build, the version-id parse, the ready failure exiting 1, and no closing line naming EXECUTOR_TOKEN.
    (ticked) 2026-10-26T11:30:14Z by d778be9d: 0bd5f6b4a and 907cd289: .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py rc=0 (65 passed, 2026-10-26); npm run check:ci-proxy-deploy-dry-run rc=0 for all 7 targets; the Accept grep for EXECUTOR_TOKEN prints only legitimate references: EXECUTOR_TOKEN_PLACEHOLDER in workers/proxy/src/egress.ts, the refusal rule FORBIDDEN_TEXT at .ci/rediacc_ci/deploy/proxy_configs.py:58, and REDIACC_EXECUTOR_TOKEN in the env-manifest tombstone shard; no token value or secret binding remains
  
  -- Owns: .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py, .ci/rediacc_ci/tests/goldens/twins/deploy.deploy-proxy.jsonl, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/env-manifest.json, docs/environment-variables.md. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py` exits 0 and `grep -rn EXECUTOR_TOKEN workers/proxy .ci/rediacc_ci/deploy .ci/config` prints nothing.
- [x] D2 [cd] The CD steps (Design item 9), after D1. Add `deploy_record.py` (before and after records, `wrangler d1 time-travel info <db> --json` taken before migrations) and `console_executor.py` (`--enable|--disable`, `wrangler secret put|delete EXECUTOR_MODE`, value on stdin).
  - cd-deploy-account.yml gains the `version` input, `actions: read` where artifacts are downloaded, the edge-only stage job, and the step order of Design item 9.
  - The enable step reads `if: steps.proxy_smoke.outcome == 'success'`. The reverse-order rollback step reads `if: failure()`.
  - cd-v2.yml (edge and hotfix) and promote-stable.yml pass `version`. verify-stable keeps needing deploy-account-stable, which now contains the proxy steps.
  - A YAML structure test asserts:
    - the order;
    - the enable condition;
    - the rollback order;
    - that both callers pass `version`;
    - that no step echoes a secret value.
    (ticked) 2026-10-26T04:24:47Z by d778be9d: commit 907cd2892: per-region proxy deploy, smoke, executor enable on smoke success, reverse rollback; pytest test_deploy_deploy_record, test_deploy_console_executor, test_workflow_cd_deploy_account_proxy rc=0; actionlint rc=0; check:ci-parity rc=0
  
  -- Owns: .github/workflows/cd-deploy-account.yml, .github/workflows/cd-v2.yml, .github/workflows/promote-stable.yml, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/deploy/console_executor.py, .ci/rediacc_ci/tests/test_deploy_deploy_record.py, .ci/rediacc_ci/tests/test_deploy_console_executor.py, .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_deploy_record.py .ci/rediacc_ci/tests/test_deploy_console_executor.py .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py` exits 0, `actionlint .github/workflows/cd-deploy-account.yml .github/workflows/cd-v2.yml .github/workflows/promote-stable.yml` exits 0, and `npm run check:ci-parity` exits 0.

### Gates

- [x] G1 [gates] The cost guard over all configs. CONFIGS (.ci/scripts/quality/check_proxy_cost_guard.py:50) becomes a glob over workers/proxy/wrangler*.toml. Every config needs `max_instances` ≤ 3 and `sleepAfter` ≤ 120 s. The deployable set (every config except wrangler.dev.toml) has at most 7 members and a total of at most 21. MAX_INSTANCES_BUDGET becomes 3, citing the ruling. -- Owns: .ci/scripts/quality/check_proxy_cost_guard.py, .ci/rediacc_ci/tests/test_quality_proxy_cost_guard.py. Accept: `npm run check:ci-proxy-cost-guard` exits 0, and exits 1 on each of a planted `max_instances = 4`, a planted eighth deployable config, and a planted total of 22.
    (ticked) 2026-10-26T10:19:53Z by d778be9d: commit 8e0566b8e and 0bd5f6b4a; npm run check:ci-proxy-cost-guard rc=0 (8 containers, 8 configs, 7 deployable, 21 total; planted eighth config and total 22 fire); .ci/scripts/quality/check_proxy_cost_guard.py:44
- [x] G2 [gates] The T3 wiring test over all proxy configs, plus the binding wiring test. observability-export-wiring.test.ts discovers every deployable workers/proxy config and expects its region's pair with `persist = false`. The new proxy-binding-wiring test asserts:
  - each account config's EXECUTOR names its own target's proxy;
  - each proxy's ACCOUNT and ISSUER name its own target's account Worker, edge to edge and stable to stable;
  - no wrangler config outside workers/proxy (workers/www, workers/account and any generated preview config) names entrypoint `ExecutorIssuer` or `CloudflareInternal`.
    (ticked) 2026-10-26T04:24:49Z by d778be9d: account 5a34c5e7 (pointer 99551c0da): export wiring over every deployable proxy config and the binding wiring test; vitest rc=0 (99); a planted ISSUER in www fails it
  
  -- Owns: private/account/tests/integration/observability-export-wiring.test.ts, private/account/tests/integration/proxy-binding-wiring.test.ts. Accept: `cd private/account && npx vitest run tests/integration/observability-export-wiring.test.ts tests/integration/proxy-binding-wiring.test.ts` exits 0, and a planted ISSUER entry in workers/www/wrangler.toml makes it fail.
- [x] G3 [gates] A CI dry run for each target. `check:ci-proxy-deploy-dry-run` runs `deploy_proxy --dry-run` for the six CD targets and bench with fake credentials, and needs no image build. It is registered in package.json and scripts/ci-runner/manifest.ts with a `step` entry pointing to a new ci-quality.yml step, and gates.lock.json is regenerated. -- Owns: .ci/scripts/quality/check_proxy_deploy_dry_run.py, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .github/workflows/ci-quality.yml. Accept: `npm run check:ci-proxy-deploy-dry-run` exits 0 and `npm run check:ci-parity` exits 0.
    (ticked) 2026-10-26T03:33:44Z by d778be9d: commit 0bd5f6b4a: check:ci-proxy-deploy-dry-run runs deploy_proxy --dry-run for six CD targets and bench; rc=0; check:ci-parity rc=0

### Telemetry, nightly, docs, live tooling

- [x] T1 [telemetry] Proxy hosts in the delivery check. A `PROXY_HOSTS` list (well-known hosts of the deployed proxies, starting with bench and eu and grown by each live box) is probed at `/v1/health` with the probe header and judged as `rediacc-proxy`. Account hosts keep `/account/api/v1/health`. -- Owns: .ci/rediacc_ci/ops/telemetry_delivery.py, .ci/rediacc_ci/tests/test_ops_telemetry_delivery.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_ops_telemetry_delivery.py` exits 0, including a case where a proxy host probed at the account path would have 401ed.
    (ticked) 2026-10-26T04:25:22Z by d778be9d: commit 8e0566b8e: proxy hosts probed at /v1/health; test_ops_telemetry_delivery rc=0 including the account-path 401 case
- [ ] N1 [ci] Fix the red nightly Console CI (Context item 7). For each failing step, apply the remedy the gate names: upgrade body-parser and fast-uri in package-lock.json; upgrade docker/login-action, or record a BLOCKER with its reason; handle the pin, dependency and Go freshness items (golang.org/x/crypto stays put while v0.58.0 carries GO-2026-5932); update the OBS ceph pin; settle the overdue plan files. Re-read the causes with `.ci/scripts/ci/ci-trace.py --scheduled` at box time, since nightly causes change daily. -- Owns: the files each remedy names (package-lock.json, .github/workflows pins, .ci/policy/*, private/renet go.mod if demanded), recorded on the tick line. Accept: each failing step's script exits 0 on the branch (`.ci/scripts/ci/ci-trace.py --job <id> --steps` names it), and after merge `.ci/scripts/ci/ci-trace.py --scheduled` shows Console CI GREEN.
- [x] E1 [e2e] The live console probe spec, after D1 (profile). `27-90-live-executor.test.ts` is skipped unless `LIVE_CONSOLE_ORIGIN` is set. It logs in as the executor-org member from the `live-console` profile, unlocks the config, and runs `machine status <machine>` from the portal console. It asserts success, the absence of the mock warning text, and an `event_log` row of type `cli.command` naming the user (read through `wrangler d1 execute`). It prints the run's output and the event id. -- Owns: private/account/e2e/tests/27-console/27-90-live-executor.test.ts. Accept: the spec is listed by `npx playwright test --list` and is skipped without `LIVE_CONSOLE_ORIGIN`.
    (ticked) 2026-10-26T11:30:00Z by d778be9d: private/account/e2e/tests/27-console/27-90-live-executor.test.ts:5 gates the spec on LIVE_CONSOLE_ORIGIN; cd private/account/e2e && npx playwright test --list lists it (chromium, firefox, webkit); npx playwright test --project=chromium tests/27-console/27-90-live-executor.test.ts without LIVE_CONSOLE_ORIGIN rc=0 (1 skipped), 2026-10-26; the live run against a deployed origin is the L1-L3 boxes
- [x] W1 [docs] Documentation:
  - docs/observability/signals/proxy.md and architecture.md: seven proxy Workers, the per-region pair, the script-name mapping regex `^(edge-)?rediacc-proxy-(eu|us|asia|bench)$`, `/v1/ready`;
  - the private/account CLAUDE.md console section: issued tokens, the 'service-binding' mode, the executor principal, the org gate, enabling through CD;
  - the deploy skill: proxy steps, records, the rollback order, bench stays manual;
  - workers/proxy comments.
    (ticked) 2026-10-26T03:33:52Z by d778be9d: commit 59df9e115 and account e82a57a0: proxy docs, deploy skill 4a, account console section; check:ci-prose-style rc=0; ExecutorIssuer grep matches all three files
  
  -- Owns: docs/observability/**, private/account/CLAUDE.md, .claude/skills/deploy/SKILL.md. Accept: `npm run check:ci-prose-style` exits 0 and `grep -n 'ExecutorIssuer' private/account/CLAUDE.md .claude/skills/deploy/SKILL.md docs/observability/signals/proxy.md` matches all three.

### Live rollout (each box records worker and version ids before and after, smoke rc, rollback command, D1 bookmark, and one end-to-end console command)

- [ ] L0 [live] Bench and preconditions.
  - Run `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench`, then `deploy_proxy --target bench --record`, then `console_executor --target bench --enable`.
  - Delete the `EXECUTOR_TOKEN` secret from rediacc-proxy-bench and revoke token 5375a8fe.
  - Record U4 for all seven D1 databases (root user, org id, subscription; ids only).
  - Name the end-to-end machine (hostinger inside H1, otherwise the VM used).
  - Run E1 against bench.
  
  -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md (a "Live records" section). Accept: the bench record row has smoke rc 0, E1 against `https://bench.rediacc.com` exits 0, and `SELECT count(*) FROM api_tokens WHERE ip_binding='cloudflare' AND revoked_at IS NULL` on the bench D1 returns 0.
- [ ] L1 [live] edge-eu, before merge, through the local path of the deploy skill running the same modules CD runs. This box records U1 and U2 as observed. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: the edge-eu row records the account version before and after, the D1 bookmark, the proxy version, smoke rc 0, the enable step, the rollback command, and E1 against `https://edge-eu.rediacc.com` exiting 0.
- [ ] L2 [live] edge-us, as L1 (the first us proxy: closed until smoke passes). -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L1 for edge-us, plus a console command run before the enable step that answers the coded 503.
- [ ] L3 [live] edge-asia, as L2. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L2 for edge-asia.
- [ ] L4 [live, post-merge] The first CD edge run after merge, which proves CD itself. Its three per-region records come from the job summary. Each record carries the manifest sha256s stored at `executor/v<V>/`. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: the run's three deploy jobs succeed with smoke rc 0, and `executor_artifacts fetch --version <V>` verifies.
- [ ] L5 [live, post-merge] stable-eu through promote-stable (soak or nightly waiver). Delete rediacc-proxy-eu's `EXECUTOR_TOKEN` secret and revoke its token. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: the stable-eu record matches L4's manifest sha256s for the same version, smoke rc is 0, E1 against `https://eu.rediacc.com` exits 0 with the audit event naming the user (this also closes PLAN-cloudflare-proxy C2), and no unrevoked 'cloudflare' token remains in the eu D1.
- [ ] L6 [live, post-merge] stable-us, as L5. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L5 for us.
- [ ] L7 [live, post-merge] stable-asia, as L5. -- Owns: agent/plans/PLAN-proxy-cd-six-targets.md. Accept: as L5 for asia.
- [ ] L8 [ops, post-merge] Telemetry acceptance, which folds in PLAN-telemetry-export T15.
  - Verify U6 and extend the Alloy transform on hostinger to the regex in W1, with `deployment.environment` and `rediacc.region` resource attributes so the proxy Loki streams carry those labels.
  - Create one silent-sender rule per proxy target, `silent-proxy-<production|edge>-<r>` (six rules), keyed `service="rediacc-proxy"`, and unpause them. `silent-proxy-exec-prod-eu` stays paused (a DEFAULT).
  - T1's list holds all seven proxy hosts.
  
  -- Owns: the observability repo's Alloy config and alerting provisioning, .ci/rediacc_ci/ops/telemetry_delivery.py (the list). Accept: `python3 -m rediacc_ci.ops.telemetry_delivery` exits 0 with 14 hosts and 0 silent; Tempo lists `rediacc-proxy` and `rediacc-proxy-executor`; `count by (deployment_environment, rediacc_region) (traces_spanmetrics_calls_total{service="rediacc-proxy"})` returns 7 series; `GET /api/v1/provisioning/alert-rules` shows the six proxy rules with `isPaused: false`.
- [ ] L9 [account, post-merge] Retire the public 'cloudflare' path. Once all seven D1s report zero unrevoked 'cloudflare' tokens (L0, L5-L7), the public-path branch at private/account/src/middleware/api-token.ts:84-96 refuses every 'cloudflare' token, and the test asserts it. -- Owns: private/account/src/middleware/api-token.ts, private/account/tests/integration/api-token-service-binding.test.ts. Accept: `cd private/account && npx vitest run tests/integration/api-token-service-binding.test.ts` exits 0.
- [x] X1 [plans] Relation lines.
  - PLAN-cloudflare-proxy.md: C2 is closed by L5. The "Operator: redeploy ... EXECUTOR_TOKEN" box is superseded by ASKED:2026-10-25T19:08Z. Teardown stays that plan's fallback.
  - PLAN-telemetry-export.md: T15 is closed by L8, with outputs in its "Proxy results" section. T16's proxy-host clause is met by T1 and L8, while T16's own acceptance (a scheduled run on main) stays there. T14's config half is subsumed by K1 and G2, and its source half was already landed.
    (ticked) 2026-10-26T16:06:55Z by d778be9d: relation sections added at agent/plans/PLAN-cloudflare-proxy.md:397 (C2 closed by L5, the EXECUTOR_TOKEN box superseded by ASKED:2026-10-25T19:08Z, teardown the fallback) and agent/plans/PLAN-telemetry-export.md:184 (T15 closed by L8, T16 proxy-host clause met by T1 and L8, T14 config half subsumed by K1 and G2); grep -n PLAN-proxy-cd-six-targets on both files matches
  
  -- Owns: agent/plans/PLAN-cloudflare-proxy.md, agent/plans/PLAN-telemetry-export.md (those lines only). Accept: `grep -n 'PLAN-proxy-cd-six-targets' agent/plans/PLAN-cloudflare-proxy.md agent/plans/PLAN-telemetry-export.md` matches both files.

### Order and parallel writers

- Wave 1, all with disjoint Owns:
  - M1, then M2, M3 and R1;
  - R2 and P2;
  - I3;
  - P1;
  - K1;
  - A1;
  - G1;
  - T1;
  - N1.
- Wave 2: I1 after M1; A2 after A1; G2 after K1; D1 after K1, A1 and A2.
- Wave 3: I2 after I1; I4 after M1 and I1; D2, G3 and E1 after D1.
- Wave 4: W1. The live boxes run in the order L0 to L3 before merge, and L4 to L9 after merge. If the merge flow needs every box ticked, the lead decides whether the post-merge boxes move to a follow-up plan file; this plan does not assume either answer.

## Live records

| Target | Account version | D1 bookmark (before migrations) | Proxy version (previous) | Smoke rc | Rollback | End-to-end |
|---|---|---|---|---|---|---|
| bench (2026-10-26) | deploy_bench rc=0 (5 migrations incl. 0065) | 000000ca-00000000-00005110-c0e98905... (full value on worklist #03d54376) | ede18ed0-7f00-4f74-9ddc-862528f7ad31 (5ae345d3-fb6e-48fe-bcc3-446649fb5712) | 0 (health 200, server-info 401, ready 200) | `npx wrangler rollback 5ae345d3-fb6e-48fe-bcc3-446649fb5712 --config workers/proxy/wrangler.bench.toml` | E1 not run: the live-console member login secret is not in the store |
| bench proxy redeploy (2026-10-26) | unchanged | n/a (proxy only) | 64367c0d-0a0b-4351-a4fa-c97aa3c2d221 (94c4be16-4114-4ab2-adad-5e42603fac16) | 0 (health 200, server-info 401, ready 200) | `npx wrangler rollback 94c4be16-4114-4ab2-adad-5e42603fac16 --config workers/proxy/wrangler.bench.toml` | telemetry_delivery rc=0, 16/16 PASS incl. proxy.bench.rediacc.com logs |

Bench notes: the ROOT_EMAIL user, its org and a COMMUNITY subscription were registered through `POST /account/api/v1/auth/register` (ids 65b5d9d0, a49f455c, eba8a7c0) because deploy_bench and reset_bench seeded none (fixed in 27861278: deploy_bench now seeds the user and reset_bench still removes it, so every reset needs a following deploy_bench or `--seed-root`; `--seed-root` live rc=0), and the issuer refused ISSUER_OWNER_UNKNOWN until then; the first issued token was c032d177 (issuer key executor:bench:eu). `console_executor --enable --target bench --region eu` ran under the deploy-proxy-bench profile (rc=0). The old EXECUTOR_TOKEN secret was deleted from rediacc-proxy-bench and token 5375a8fe revoked. telemetry_delivery: 8 hosts, 16 signals, 0 silent. The image push first failed on a single 226 MB layer (registry commit timeout) and passed once the Dockerfile split bundle, natives and renet into separate layers (907cd2892). The bench proxy was deployed again between the first row and the redeploy row: wrangler reported 94c4be16 as the version live before the redeploy, not the ede18ed0 of the first row, and that intermediate deploy has no row of its own.

## Decisions taken as defaults (open to operator veto)

1. The executor owner is the ROOT_EMAIL user and its owned org, with `EXECUTOR_ISSUER_ORG_ID` as an override. Token TTL is 45 minutes, renewed at 80%.
2. I4 refuses non-executor-org callers with the same "not available in this region" 503, rather than letting a 401 relay. Serving every org would need a per-org issuer, which is outside this plan.
3. The purge grace is 7 days past `expires_at`.
4. The cost guard's total counts deployable configs only (seven). wrangler.dev.toml is checked at ≤3 but not counted.
5. EXECUTOR_MODE is a CD-managed Worker secret rather than a var, so it can be switched without a redeploy and survives account deploys.
6. The executor silent-sender rule stays paused, because no synthetic traffic exercises the container. The Worker rules are kept alive by the 6-hourly probe.
7. The public 'cloudflare' path is retired by L9 only after all seven D1s hold zero live tokens of that mode.

# PLAN: Cloudflare executor proxy (rediacc-proxy-eu): status, tests, live trial, cost, teardown

Status: approved -- operator rulings 2026-10-23 (AskUserQuestion): "Keep it and finish Phase 2", B5 "A mint command", console "Wire it after Phase 2"; quoted in "Operator rulings (2026-10-23)" below
Depends-On: no-dep -- cites no other plan; the account-side boxes ride the private/account submodule's own branch
Owner: d778be9d
Updated: 2026-10-23
Priority: P1 -- the operator kept the deployed proxy and ordered Phase 2 and the console wiring; a live Worker whose state no record describes is the open risk
Concurrency: parallel -- writers take disjoint per-box file sets (Worker and deploy, CLI executor, account route and console, e2e); Owns: decides overlaps
Owns: workers/proxy/src/**, workers/proxy/wrangler.toml, workers/proxy/Dockerfile, workers/proxy/tsconfig.json, workers/proxy/package.json, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py, .ci/scripts/quality/check_proxy_image_smoke.py, .ci/scripts/quality/check_proxy_cost_guard.py, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, package.json, .github/workflows/ci-quality.yml, .github/workflows/ci.yml, packages/cli/src/cli.ts, packages/cli/src/commands/serve.ts, packages/cli/src/commands/subscription*.ts, packages/cli/src/services/serve/**, packages/cli/src/services/executor/**, packages/cli/src/i18n/locales/**, packages/shared/src/cli-contract/**, packages/e2e-tests/**, private/account/src/routes/proxy.ts, private/account/src/routes/console.ts, private/account/src/types/env.ts, private/account/tests/integration/proxy-*.test.ts, private/account/tests/integration/console-session.test.ts, workers/account/wrangler.eu.toml, workers/account/src/index.ts, agent/plans/PLAN-cloudflare-proxy.md, .github/workflows/ci-build-renet.yml, .ci/rediacc_ci/quality/proxy_image_smoke.py

## Operator rulings (2026-10-23)

Asked with AskUserQuestion on 2026-10-23; each answer is quoted, then what it orders.

- **Proxy: "Keep it and finish Phase 2".** The plan is promoted. Phase 2 runs against hostinger (section 3), and the container's RSS and cold start are recorded here. Teardown (section 5) stays only as the fallback for a shelved proxy; it is not the end state.
- **B5: "A mint command".** An explicit `rdc` command mints a short-lived `proxy:exec` token from the logged-in session. The CLI login stays least-privilege: the device-code grant does not gain `proxy:exec`. It needs an account route, the CLI command, and missing test 8. Boxes B5a and B5b carry it; the older B5 box's acceptance ("the account integration test for the chosen fix passes") is met by B5a's test, so the two close together.
- **Console: "Wire it after Phase 2".** Once Phase 2 is green, eu gets `EXECUTOR_MODE=proxy` and `EXECUTOR_URL`, eu is deployed, and one console command is proven end to end. us and asia stay `mock` until the operator asks. Box C2 carries it, after box C1 (section 1.4).

## Tasks

- [x] A1 [P0] Cost settings: `max_instances = 2` in `workers/proxy/wrangler.toml` and `sleepAfter = '2m'` in `workers/proxy/src/index.ts` -- acceptance: `grep -n 'max_instances = 2' workers/proxy/wrangler.toml` and `grep -n "sleepAfter = '2m'" workers/proxy/src/index.ts` both match
    (ticked) 2026-10-23T08:27:53Z by d778be9d: commit:5f9a354ea max_instances = 2 at workers/proxy/wrangler.toml:40 (5f9a354ea) and sleepAfter = '2m' at workers/proxy/src/index.ts:63 (3b96d5133)
- [x] A2 [P0] B1: the Worker builds the container's `envVars` from its env (`REDIACC_TOKEN`, `REDIACC_ACCOUNT_SERVER`), drops the dead `REDIACC_EXECUTOR_MODE`, and gains its unit tests (missing test 1) -- acceptance: `cd workers/proxy && npm run test:unit` exits 0
    (ticked) 2026-10-23T08:28:27Z by d778be9d: commit:3b96d5133 executorEnvVars builds the container envVars from the Worker env (workers/proxy/src/index.ts:44, used at workers/proxy/src/index.ts:66); workers/proxy npm run test:unit 16 passed
- [x] A3 [P1] B2: the image ships a version-matched renet at `/usr/local/bin/renet`, the deploy builds it, and an image-smoke gate covers it (missing test 4) -- acceptance: `npm run check:ci-proxy-image-smoke` exits 0
    (ticked) 2026-10-23T08:27:55Z by d778be9d: commit:3b96d5133 the image copies a version-matched renet to /usr/local/bin/renet (Dockerfile:54-56,90-91); the smoke gate check:ci-proxy-image-smoke landed in 0868e3a53 and ran green 2026-09-24
- [x] A4 [P1] Post-deploy smoke in `deploy-proxy.sh` and `deploy_proxy.py` (`/v1/health` 200, unauthenticated `/v1/server-info` 401) with the differential test updated and the false dry-run header claim corrected (missing test 10) -- acceptance: `python3 -m pytest .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py -q` exits 0
    (ticked) 2026-10-23T08:27:57Z by d778be9d: commit:3b96d5133 deploy_proxy.smoke() checks /v1/health 200 and unauthenticated /v1/server-info 401; the bash twin is deleted (cb2908164); test_deploy_deploy_proxy.py 30 passed
- [x] A5 [P2] Cost-guard gate asserting `max_instances` and `sleepAfter` stay at or under the budgeted values (missing test 9) -- acceptance: the new gate exits 0 on the tree and 1 on a planted `max_instances = 20`
    (ticked) 2026-10-23T13:29:16Z by d778be9d: commit:2d4c5df52 .ci/scripts/quality/check_proxy_cost_guard.py rc=0 on the tree; .ci/rediacc_ci/tests/test_check_proxy_cost_guard.py plants max_instances = 20 and gets rc=1; wired as check:ci-proxy-cost-guard in quality-static
- [x] A6 [P2] Local Worker-to-container e2e under `wrangler dev` with containers, where `/v1/server-info` through the Worker answers `mode: "container"` (missing test 5) -- acceptance: that e2e run exits 0 on a docker host
    (ticked) 2026-10-24T04:37:23Z by d778be9d: commit:3c5f450ac .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py:1; npm run check:ci-proxy-wrangler-dev-e2e rc=0 (78 s, nothing left), pytest 26 passed, parity rc=0
- [x] B1 [P0] B3: request-scoped config for dispatch and re-attach, with execution asserted to reach `10.9.9.9` with the decrypted SSH key (missing test 2) -- acceptance: `container-config.test.ts` under `packages/cli/src/services/serve/__tests__/` passes with `configService` unmocked
    (ticked) 2026-10-23T08:28:29Z by d778be9d: commit:3b96d5133 request-scoped config lives in packages/cli/src/services/core/request-context.ts and is threaded into dispatch at packages/cli/src/services/serve/server.ts:204; container-config.test.ts passes
- [x] B2 [P0] S1: the executor computes `isGrandRepo` and refuses grand-repo mutations by default (missing test 7) -- acceptance: `packages/cli/src/services/serve/__tests__/grand-repo-guard.test.ts` passes
    (ticked) 2026-10-23T08:27:59Z by d778be9d: commit:3b96d5133 the executor computes isGrandRepo via resolveGrandRepoMutation and refuses grand-repo mutations by default; grand-repo-guard.test.ts passes
- [x] B3 [P1] B4: `ProxyClient.ensureSession()` opens a session and grants the sealed CEK once per process (missing test 3) -- acceptance: `packages/cli/src/services/executor/__tests__/proxy-client-session.test.ts` and the loopback variant in `container-config.test.ts` pass
    (ticked) 2026-10-23T08:28:01Z by d778be9d: commit:3b96d5133 ProxyClient.ensureSession opens a session and grants the sealed CEK once per session; proxy-client-session.test.ts passes
- [x] B4 [P2] e2e against a VM in `packages/e2e-tests` (nightly): `rdc --proxy <local serve> repo status <fork>`, then `repo up` and `repo down` on a fork (missing test 6) -- acceptance: the nightly e2e job passes the proxy spec
    (ticked) 2026-10-24T05:55:00Z by d778be9d: commit:7eb8b114f packages/e2e-tests/tests/29-proxy-local-executor.test.ts:1; live rc=0 twice (4/4); shard leg 4 of the E2E Workers matrix that runs on the nightly schedule
- [x] F1: proxied commands are audited; the executor checks its own `audit:write` before a change and refuses with 503 when it cannot audit -- acceptance: the `audit capability (F1)` block of `grand-repo-guard.test.ts` passes
    (ticked) 2026-10-23T08:28:31Z by d778be9d: commit:3b96d5133 the executor checks canWriteAudit before a changing command (packages/cli/src/services/serve/server.ts:408); the F1 block in grand-repo-guard.test.ts passes
- [x] Finding (a): `loadDaemonConfig` in `commands/serve.ts` returns a config that carries `policy`, so a daemon enforces the policy document -- acceptance: a serve test where a daemon refuses a command its policy denies
    (ticked) 2026-10-23T08:28:03Z by d778be9d: commit:3b96d5133 loadDaemonConfig returns a config carrying policy rather than getLocalConfig(); serve-daemon-config.test.ts passes
- [x] Finding (b): `outputJsonError` writes through `writeStdout`, so a dispatched command's JSON error reaches the client instead of "The command exited with code 1" -- acceptance: a dispatch test asserting the client sees the JSON error body
    (ticked) 2026-10-23T08:28:05Z by d778be9d: commit:3b96d5133 outputJsonError writes through writeStdout so a dispatched command's JSON reaches the caller; errors-proxied-json.test.ts passes
- [x] Finding (c): `utils/command-policy.ts` resolves a `name:base` ref to the grand's `latest` key, so the local agent guard no longer returns early -- acceptance: a command-policy test refusing a grand mutation named `name:base`
    (ticked) 2026-10-23T08:28:06Z by d778be9d: commit:3b96d5133 a name:base ref resolves to the grand's latest key; command-policy-grand-ref.test.ts passes
- [x] Smaller defect: `deploy_proxy.py` stops ignoring `--region` -- acceptance: `test_deploy_deploy_proxy.py` asserts a non-default region either changes the deploy or exits non-zero
    (ticked) 2026-10-23T13:29:39Z by d778be9d: commit:c6046b496 .ci/rediacc_ci/deploy/deploy_proxy.py refuses a non-eu region with rc=1 before any build; .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py 32 passed rc=0
- [x] Smaller defect: the `workers/proxy/tsconfig.json` comment about `src/__tests__` matches the tree -- acceptance: `workers/proxy/src/__tests__/index.test.ts` exists and the comment describes it
    (ticked) 2026-10-23T08:28:08Z by d778be9d: commit:3b96d5133 the tsconfig comment describes src/__tests__, which exists (src/__tests__/index.test.ts)
- [x] CI runs the Worker unit tests (`check:test-workers` covers `workers/proxy` as well as `workers/www`) -- acceptance: `npm run check:test-workers` exits 0 and `npm run check:ci-parity` exits 0
    (ticked) 2026-10-23T08:28:10Z by d778be9d: commit:0868e3a53 check:test-workers runs workers/proxy unit tests as well as workers/www (package.json:354, ci-quality.yml); check:test-workers and check:ci-parity rc=0
- [x] A CI job runs the proxy image smoke, replacing its `local-only` BLOCKER in `scripts/ci-runner/gates.lock.json` -- acceptance: `check:ci-proxy-image-smoke` carries a `step` entry and `npm run check:ci-parity` exits 0
    (ticked) 2026-10-24T04:12:37Z by d778be9d: commit:04da94740 .github/workflows/ci-build-renet.yml:522; job proxy-image-smoke runs the Proxy image smoke step, gates.lock.json carries its ci step entry, no local-only BLOCKER remains; npm run check:ci-parity rc=0 on 2026-10-24
- [x] B5 (account submodule, separate PR): CLI callers get `proxy:exec`, by a mint command or by the scope at login, with the account contract test pinning which token a CLI presents (missing test 8) -- acceptance: the account integration test for the chosen fix passes
    (ticked) 2026-10-24T04:12:40Z by d778be9d: commit:17c55af8b private/account/tests/integration/proxy-cli-token.test.ts:1; the B5a test meets this box per the plan's ruling; proxy-cli-token and console-session vitest 26 passed rc=0 on 2026-10-24; CLI half packages/cli/src/commands/subscription-proxy-token.ts
- [x] Operator Phase 0: `/v1/health` 200, unauthenticated `/v1/server-info` 401, and `wrangler containers list` with no running instance -- acceptance: the three section 3 Phase 0 outputs recorded in this plan
    (ticked) 2026-10-24T04:37:21Z by d778be9d: the three Phase 0 outputs recorded at agent/plans/PLAN-cloudflare-proxy.md:300 (health ok, 401, containers list 0 live instances), plus rollback handles; run 2026-10-24 on the tree at commit:3c5f450ac
- [x] Operator Phase 1: the daemon tier on the dev box against hostinger, including `repo up` and `repo down` on `demo-stackoverflow:proxytrial` -- acceptance: the Phase 1 results section records rc 0 for every step
    (ticked) 2026-10-23T08:28:11Z by d778be9d: commit:bcb0f2d7e the Phase 1 results section records rc 0 for status, repo status, fork up and fork down against hostinger
- [ ] Operator: redeploy after A2, A3, B1, B2 and B3 with `EXECUTOR_TOKEN` (scopes `proxy:exec` and `audit:write`) set, then Phase 2 steps 1-4 against hostinger -- acceptance: `rdc --proxy https://proxy.eu.rediacc.com machine status hostinger` exits 0 with output matching the local run
- [x] Phase 2 step 5: measure container RSS and cold start, decide whether `lite` is viable, and record the numbers in this plan -- acceptance: the measurements recorded in this plan
    (ticked) 2026-10-24T06:40:58Z by d778be9d: commit:f68c4aa8b measurements at agent/plans/PLAN-cloudflare-proxy.md:327 (basic, idle 237-242 MiB, cold 2.3-4.9 s, warm 487 ms; lite not viable, keep basic)
- [ ] Teardown per section 5 when the trial and improvement wave closes, or at once if the proxy is shelved -- acceptance: every section 5 step 7 check shows the proxy gone
- [x] B5a [P1] (account submodule) `POST /proxy/cli-token`, the CLI twin of `/proxy/session-token` (`private/account/src/routes/proxy.ts:127`): authenticated by the CLI's device-code login token instead of a session cookie, it re-resolves org, subscription and team membership, and mints a token whose scope is exactly the literal `proxy:exec`, attributed to the login token's user and team, short-lived like `PROXY_SESSION_TOKEN_TTL_MS` (`:175`); the device-code scope list (`private/account/src/services/device-code.service.ts:345-356`) stays without `proxy:exec` (missing test 8) -- acceptance: a new `private/account/tests/integration/proxy-cli-token.test.ts` passes, proving a login token mints, the minted token introspects `active` with exactly `["proxy:exec"]` and the login token's user, a revoked or other-org login token is refused, and a device-code login still carries no `proxy:exec`
    (ticked) 2026-10-23T13:29:40Z by d778be9d: commit:4b9da45fa moves private/account to efed758 (B5a in bfb48c9); private/account/tests/integration/proxy-cli-token.test.ts 13/13 rc=0; account typecheck rc=0
- [x] B5b [P1] An explicit `rdc` command (working name `rdc subscription proxy-token`) that calls B5a with the stored login token and writes only the minted token to stdout (`--json` adds `expiresAt`), registered in the CLI contract as not `proxyCapable`, with its strings in every CLI locale, so a caller runs `REDIACC_TOKEN=$(rdc subscription proxy-token) rdc --proxy <url> ...` -- acceptance: a CLI test drives the command against a fake account server and asserts stdout carries the token and nothing else, and `npx tsc --noEmit --project packages/cli/tsconfig.json` exits 0
    (ticked) 2026-10-23T13:29:42Z by d778be9d: commit:17c55af8b packages/cli/src/commands/subscription-proxy-token.ts and packages/cli/src/commands/__tests__/subscription-proxy-token.test.ts rc=0; npx tsc --noEmit --project packages/cli/tsconfig.json rc=0
- [x] C1 [P1] The account worker reaches the proxy through a service binding, not a public fetch: `console.ts` sends its three executor calls (`private/account/src/routes/console.ts:352`, `:407`, `:445`) through an `EXECUTOR` Fetcher when bound, and `workers/account/wrangler.eu.toml` binds `rediacc-proxy-eu`; `fetch(EXECUTOR_URL)` stays for a local executor in dev -- acceptance: a `console-session.test.ts` case where a bound Fetcher receives the command and the global `fetch` is never called, and `grep -n 'rediacc-proxy-eu' workers/account/wrangler.eu.toml` matches
    (ticked) 2026-10-24T04:12:42Z by d778be9d: commit:fa7742a0e workers/account/wrangler.eu.toml:70; console.ts picks the bound EXECUTOR Fetcher first (private/account/src/routes/console.ts:59), the eu worker binds rediacc-proxy-eu, console-session tests pass (26 with proxy-cli-token); not yet deployed, the binding ships with this branch
- [ ] C2 [P1] After Phase 2 is green and C1 lands: `EXECUTOR_MODE = "proxy"` and `EXECUTOR_URL = "https://proxy.eu.rediacc.com"` in `workers/account/wrangler.eu.toml` `[vars]`, an eu deploy, and one console command (`machine status hostinger`) run from the portal console end to end; us and asia stay `mock` -- acceptance: this plan records the deploy version, the console run's output matching the local run, and the audit event naming the user
- [x] P2a [P1] Phase 2 results recorded: the deploy version that carries the service binding, the `EXECUTOR_TOKEN` scopes (`proxy:exec`, `audit:write`) and its IP binding (`cloudflare`, `private/account/src/types/api-token.ts:18,22`), and the rc of every Phase 2 step 1-4 -- acceptance: a "Phase 2 results" section in this plan with those values
    (ticked) 2026-10-24T07:18:38Z by d778be9d: commit:74953c57d Phase 2 results at agent/plans/PLAN-cloudflare-proxy.md:303 (versions with the binding, token 5375a8fe proxy:exec+audit:write bound cloudflare, steps 1-3 rc=0, step 4 fails only at SSH after the fixes)

The existing boxes above are kept byte for byte, as the box ledger requires. Their state on 2026-10-23: A1-A4, B1-B3, F1, findings (a)-(c), the tsconfig comment, the Worker tests in CI and Operator Phase 1 are done on `origin/main` (commits 3b96d5133, 0868e3a53, 5f9a354ea, bcb0f2d7e), awaiting their ticks. Open: A5, A6, B4, `--region`, the image smoke in CI, B5 (with B5a and B5b), Phase 0, Phase 2 and its step 5, and teardown. Three readings of old boxes under the rulings:

- **A4** names `deploy-proxy.sh`. That bash twin was frozen to goldens and deleted in cb2908164 (2026-10-08); the smoke lives in `deploy_proxy.py` alone (`.ci/rediacc_ci/deploy/deploy_proxy.py:171`), and the test file named in the acceptance passes.
- **`--region`** (the "Smaller defect: `deploy_proxy.py` stops ignoring `--region`" box) takes the refusal form: the proxy's region lives in `workers/proxy/wrangler.toml`, so any `--region` other than `eu` exits non-zero before any build. The value is still read and only printed (`.ci/rediacc_ci/deploy/deploy_proxy.py:72`, `:236`, `:274`).
- **Teardown** runs only if the proxy is shelved. Under "Keep it and finish Phase 2" the trial wave closes with the proxy kept; that box then closes with the ruling as its evidence, and section 5 stays as the fallback.

The image-smoke CI box needs a renet build ahead of its lane: the gate stages `workers/proxy/renet/renet-linux-amd64` into the build context and builds the whole image, which is why it is `local-only` today (`scripts/ci-runner/gates.lock.json:5835-5850`). The job runs after `build-renet` (`.github/workflows/ci.yml:839`) and takes the renet artifact, rather than joining a quality lane that runs before any renet exists.

## 0. Verdict (2026-10-23)

The proxy is deployed and kept. The 2026-09-24 production deploy created the Worker `rediacc-proxy-eu`, the custom domain `proxy.eu.rediacc.com`, and the container application `rediacc-proxy-eu-executorcontainer`, by a manual run of `.ci/rediacc_ci/deploy/deploy_proxy.py`. It has never been torn down.

Every code blocker the first review found (B1-B4, S1, F1, findings (a)-(c)) is fixed on `origin/main` and tested (section 1.3). The daemon tier ran a real `repo up` and `repo down` against hostinger (Phase 1 results). The service binding to the account worker fixed the 401 every caller got on the first Phase 2 deploy (section 1.4).

What is not done: Phase 2 has no recorded run, so the container tier has never been shown to reach a machine; RSS and cold start are unmeasured; a CLI user has no way to get a `proxy:exec` token except a hand-made portal token (B5); production console runs are still mocked (C1, C2); and the cost guard, the image smoke in CI, the `wrangler dev` e2e and the VM e2e do not exist yet.

The cost is about $0 marginal while no caller wakes a container (section 4).

## 1. What the proxy is

### 1.1 Request flow (current)

1. **Client.** `rdc --proxy <url> <cmd>` or `REDIACC_PROXY_URL` (`packages/cli/src/cli.ts:183`, `:224`). The root preAction hook refuses a command that is not `proxyCapable`, then calls `runCommandThroughProxy` before the local action can run (`packages/cli/src/cli.ts:229-244`, `packages/cli/src/services/executor/proxy-command.ts:252`). The bearer is the stored subscription token, or `REDIACC_TOKEN` from the env (`packages/cli/src/services/account/subscription-auth.ts:8`, `:157`). 85 of the contract's commands are `proxyCapable` (`packages/shared/src/cli-contract/data/contract.json`). Before a command, `ProxyClient.ensureSession()` grants the sealed CEK to a `container` executor (`packages/cli/src/services/executor/proxy-client.ts:185`).
2. **Worker** (`workers/proxy/src/index.ts`).
   - `/v1/health` is answered by the Worker itself, without the container (`:129-131`).
   - Every other path introspects the caller's token with the account server, authenticating with `EXECUTOR_TOKEN`. The call goes through the `ACCOUNT` service binding (`:109`, `workers/proxy/wrangler.toml:19-21`). It requires `active`, an `orgId` and scope `proxy:exec`; each refusal is logged as a reason code, never a token, by `refuse()` (`:88-119`).
   - It routes to a Durable-Object-backed container keyed `orgId:teamId|default` and forwards the request untouched (`:122`, `:142-143`).
   - The container's env is built from the Worker's: `REDIACC_TOKEN` is `EXECUTOR_TOKEN` and `REDIACC_ACCOUNT_SERVER` is `ACCOUNT_URL` (`executorEnvVars`, `:44-49`, `:66`).
3. **Container.** `node cli-bundle.cjs serve --mode container --port 8080` (`workers/proxy/Dockerfile:99`), with a release renet at `/usr/local/bin/renet` whose version the bundle takes as its own (`workers/proxy/Dockerfile:54-56`, `:65`, `:90-91`). It serves the Hono app in `packages/cli/src/services/serve/server.ts`, with these routes (`packages/shared/src/cli-contract/wire.ts:207-217`):
   - `/v1/health` (`packages/cli/src/services/serve/server.ts:83`)
   - `/v1/server-info` (`:85`)
   - `POST /v1/session`, which mints an X25519 keypair (`:99`)
   - `POST /v1/session/:id/cek`, the sealed CEK grant (`:115`)
   - `POST /v1/command`, which streams NDJSON (`:140`)
   - `GET /v1/jobs/:id/events`, re-attach (`:306`)

   A command is authenticated with the account server, checked against the contract version and the `prepareCommand` hard gate, authorized against the policy inside the encrypted config (including the executor's own grand-repo refusal, `resolveGrandRepoMutation` in `packages/cli/src/services/serve/policy.ts`), refused with 503 if the executor cannot write its audit event (F1), dispatched in-process against the request-scoped config (B3), and audited.
4. **Container config loading** (`packages/cli/src/services/serve/container-config.ts`). It mints its own config token with `POST /account/api/v1/configs/executor-token` (`:139`; server side `private/account/src/routes/configs.ts:837`), pulls the ciphertext, decrypts it with the CEK granted for the session, and caches it per session. A command on a session with no grant is refused with "This session has no config key yet" (`:104`).
5. **Account side.**
   - `POST /proxy/introspect` (`private/account/src/routes/proxy.ts:46`) answers only for a token of the same org.
   - `POST /proxy/session-token` (`:127`) mints the web console's per-user `proxy:exec` token, five minutes long (`:175`).
   - A `proxy:exec` token may carry IP binding `unbound` or `cloudflare` instead of first-use (`private/account/src/types/api-token.ts:18`, `:22`; checked in `private/account/src/middleware/api-token.ts:70`), so `EXECUTOR_TOKEN` survives Cloudflare's rotating egress IPs.
   - The web console passthrough (`private/account/src/routes/console.ts:337`, `:390`, `:438`) answers with a mock stream unless `EXECUTOR_MODE` is `proxy`, and reaches `EXECUTOR_URL` with a public `fetch` (`:352`, `:407`, `:445`). Both values default to mock and unset (`private/account/src/types/env.ts:232-233`), and no regional `workers/account/wrangler.*.toml` sets them, so production console runs are mocked (boxes C1, C2).

### 1.2 Configuration needed before it can serve

| Item | Where | State (2026-10-23) |
|---|---|---|
| Custom domain `proxy.eu.rediacc.com` | `workers/proxy/wrangler.toml:9-11` | live since 2026-09-24 |
| `ACCOUNT_URL` var | `workers/proxy/wrangler.toml:14` | `https://eu.rediacc.com` |
| `ACCOUNT` service binding to `rediacc-account-eu` | `workers/proxy/wrangler.toml:19-21` | in the tree; the deploy that carries it is unrecorded (box P2a) |
| `EXECUTOR_TOKEN` secret: a portal API token with scopes `proxy:exec` and `audit:write`, IP binding `cloudflare`, in the org that owns hostinger's config | `workers/proxy/src/index.ts:98` | unrecorded (box P2a) |
| Container receives its token | `executorEnvVars`, `workers/proxy/src/index.ts:44-49`; read at `packages/cli/src/commands/serve.ts:61-67` | fixed (B1) |
| Org has a remote config store holding hostinger | `packages/cli/src/services/serve/container-config.ts`, `private/account/src/routes/configs.ts:837` | operator confirms with `rdc config remote status` |
| Caller token carries `proxy:exec` | `workers/proxy/src/index.ts:119` | CLI login token does not; boxes B5a and B5b |

The design is single-org: introspection answers `active:false` for a token of another org, so one `EXECUTOR_TOKEN` means one org.

### 1.3 History: the 2026-09-24 blockers and how each was fixed

This section records the first review's findings. None of them is open; the fixes are in 3b96d5133 (code and tests) and 0868e3a53 (gates and CI wiring).

- **B1, the container never got its token.** The Worker passed only a dead `REDIACC_EXECUTOR_MODE`, and `rdc serve` refuses to start without `REDIACC_TOKEN`. Fixed by `executorEnvVars` (`workers/proxy/src/index.ts:44-49`); regression in `workers/proxy/src/__tests__/index.test.ts`.
- **B2, the image had no renet.** Outside a SEA the CLI runs the renet on its path, so every machine command failed. Fixed: the image ships a release renet, version-matched to the bundle (`workers/proxy/Dockerfile:54-56`, `:90-91`), and a real deploy builds and stages it.
- **B3, the decrypted config reached policy only, not execution.** Fixed: `CommandRequestContext.config` carries a request-scoped config that `configService` and `configFileStorage` serve during a container dispatch and on re-attach (Writer B status below).
- **B4, the CLI never opened a session or granted the CEK.** Fixed by `ProxyClient.ensureSession()` (`packages/cli/src/services/executor/proxy-client.ts:185`).
- **B5, CLI login tokens lack `proxy:exec`.** Still true by design (`private/account/src/services/device-code.service.ts:345-356`); the 2026-10-23 ruling settles the fix as a mint command (boxes B5a, B5b). Until then the trial uses a portal token with `proxy:exec` in `REDIACC_TOKEN`.
- **S1, the grand-repo guard did not apply through the proxy.** The CLI guard runs inside the local action and only for agents, and `--proxy` exits before the action. Fixed: the executor computes grand-ness itself and refuses a grand-repo mutation unless the policy document sets `allowGrandRepos`.
- **Smaller defects.** The false "dry run does a docker build" claim is corrected. The `workers/proxy/tsconfig.json` comment now matches `src/__tests__` (`workers/proxy/tsconfig.json:8`). `--region` is still ignored (box above).

### 1.4 Design facts found after the first review

- **The service binding.** The proxy Worker and the account worker share the `rediacc.com` zone, and a Worker's `fetch()` to a same-zone hostname never reaches another Worker. On the first Phase 2 deploy (2026-09-24) every introspection failed, and every caller got 401. Introspection now goes through `[[services]] ACCOUNT -> rediacc-account-eu` (`workers/proxy/wrangler.toml:16-21`), the path `workers/www` already uses; `fetch(ACCOUNT_URL)` remains only for a deploy without the binding (`workers/proxy/src/index.ts:34-36`, `:109`).
- **The same trap waits for the console.** `console.ts` reaches `EXECUTOR_URL` with a public `fetch` (`private/account/src/routes/console.ts:352`, `:407`, `:445`), and `eu.rediacc.com` and `proxy.eu.rediacc.com` share that zone. Setting `EXECUTOR_URL` alone would reproduce the 401 in the other direction, so box C1 (an `EXECUTOR` binding on the account worker) comes before box C2.
- **Refusal logging.** `refuse()` logs why a caller was refused (`no-bearer`, `no-executor-token`, `introspect-http-<n>`, `inactive`, `no-org`, `no-proxy-exec-scope`) without logging the token (`workers/proxy/src/index.ts:84-119`), so a 401 in Phase 2 names its cause in the Worker logs.
- **IP-bound executor tokens.** A `proxy:exec` token can be bound to Cloudflare's published ranges (`private/account/src/types/api-token.ts:18`, `:22`), which is the binding `EXECUTOR_TOKEN` takes.

## 2. Test coverage (2026-10-23)

| Test | Proves | Does not prove |
|---|---|---|
| `workers/proxy/src/__tests__/index.test.ts` (16 tests, run by `check:test-workers` in CI: `package.json:354`, `.github/workflows/ci-quality.yml:2190`) | health without the container, the 401 cases, tenant keys, the executor-token guard, the B1 envVars regression | a real container |
| `packages/cli/src/services/serve/__tests__/loopback.test.ts` | the real `rdc --proxy` Commander path to a real serve app over HTTP, with real X25519 | Worker, container, machine |
| `.../container-config.test.ts` | container-mode decrypt, policy inside the ciphertext, execution and re-attach resolving the decrypted machine and SSH key (B3), the real CLI grant (B4 loopback) | a real machine |
| `.../grand-repo-guard.test.ts` | the executor's grand-repo refusal (S1) and the audit capability (F1, `:304`) | - |
| `.../command-dispatch.test.ts`, `sessions.test.ts`, `policy-stale-deny.test.ts`, `proxy-audit-attribution.test.ts` | argv translation and refusals, grant-principal binding, stale deny globs, audit attribution | execution |
| `packages/cli/src/services/executor/__tests__/proxy-command.test.ts`, `proxy-client-session.test.ts` | wire params, truncated streams, `ensureSession` | - |
| `packages/cli/src/commands/__tests__/serve-daemon-config.test.ts`, `packages/cli/src/utils/__tests__/errors-proxied-json.test.ts`, `packages/cli/src/utils/__tests__/command-policy-grand-ref.test.ts` | findings (a), (b) and (c) | - |
| `private/account/tests/integration/proxy-introspect.test.ts`, `proxy-session-token.test.ts`, `config-executor-token.test.ts`, `console-session.test.ts`, `exec-token-cache.test.ts` | introspection, console token minting, the executor config token, the console passthrough against a fake `EXECUTOR_URL`, token reuse | a CLI mint route (B5a); a bound executor (C1) |
| `.ci/rediacc_ci/tests/test_deploy_deploy_proxy.py` (30 tests) | the deploy's argv, refusals and post-deploy smoke, with fake tools | anything about Cloudflare |
| `check:ci-proxy-image-smoke` (`package.json:196`, `.ci/scripts/quality/check_proxy_image_smoke.py`) | the image builds, stays up, serves `mode: container` at the renet's version, runs `renet version`, and exits without `REDIACC_TOKEN` | runs only locally (`local-only`) |

No test sends a real request through the Worker to the container and back, and none reaches a machine through the container. (`private/renet/tests/integration/test_proxy_routes.py` and `.ci/rediacc_ci/tests/test_core_proxyx.py` are unrelated: Traefik routes, and CI "proxies".)

### Missing tests (numbering kept from 2026-09-24)

1. Worker unit tests: added (A2).
2. CLI B3 regression: added (B1).
3. CLI B4 `ensureSession`: added (B3).
4. Image smoke: added as a local gate (A3); the CI job is the image-smoke box.
5. Local Worker-to-container e2e under `wrangler dev` with containers, `/v1/server-info` answering `mode: "container"`: open (A6).
6. e2e against a VM in `packages/e2e-tests`, nightly: open (B4).
7. S1 grand-repo refusal: added (B2).
8. Account contract for the CLI's token: open, now B5a's test.
9. Cost guard over `max_instances` and `sleepAfter`: open (A5).
10. Post-deploy smoke: added (A4).

## 3. Live trial against hostinger

The CLI switch is `--proxy <url>` or `REDIACC_PROXY_URL` (`packages/cli/src/cli.ts:183`, `:224`). Phase 1 is done. Phase 2 is ordered by the 2026-10-23 ruling and no longer blocked by code.

Target rules:
- Never mutate a grand repo. `observability` is one, and so is any non-fork root, including `demo-stackoverflow`. The executor now refuses such a mutation itself (S1), and the trial keeps the rule anyway.
- The operator creates the fork **with the normal local CLI, not through the proxy**: `rdc repo fork demo-stackoverflow@hostinger --tag proxytrial` (O(1); `docs/agent-reference/local-env.md:101-117`).
- Every trial command names `demo-stackoverflow:proxytrial` or is read-only (`machine status`, `repo list`).

### Phase 0: what is live (no changes)

| Step | Proves | Verify | Rollback |
|---|---|---|---|
| `curl -s https://proxy.eu.rediacc.com/v1/health` | Worker and custom domain are live | `{"ok":true}` | none |
| `curl -s -o /dev/null -w '%{http_code}' https://proxy.eu.rediacc.com/v1/server-info` | Auth gate, no container started | `401` | none |
| `npx wrangler containers list` / `info <id>` (cwd `workers/proxy`) | App exists, 0 running instances | instance list empty | none |

### Phase 1: daemon tier on the dev box against hostinger (done 2026-09-24)

The steps are kept as run; results are in "Phase 1 results" below.

1. The operator creates a portal API token with scope `proxy:exec` in the org, used for both the executor and the caller.
2. Terminal A: `REDIACC_ACCOUNT_SERVER=https://eu.rediacc.com REDIACC_TOKEN=<tok> ./rdc.sh serve --mode daemon --host 127.0.0.1 --port 8080`. Pin the account server to the one that issued the token (Phase 1 results).
3. `REDIACC_TOKEN=<tok> ./rdc.sh --proxy http://127.0.0.1:8080 machine status hostinger`, matching `./rdc.sh machine status hostinger`.
4. `... --proxy http://127.0.0.1:8080 repo status demo-stackoverflow:proxytrial`.
5. `... --proxy ... repo up demo-stackoverflow:proxytrial`, then `repo down` the same ref. Rollback: `rdc repo delete demo-stackoverflow:proxytrial` (operator, locally).

### Phase 2: Cloudflare container tier (ordered 2026-10-23, M-live)

0. Redeploy with `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy`, so the live Worker carries the `ACCOUNT` service binding, `max_instances = 2`, `sleepAfter = '2m'` and the image with renet. Record the version (box P2a).
1. `npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml`, with a token carrying `proxy:exec` and `audit:write` and IP binding `cloudflare`. Verify: `/v1/server-info` with the caller token gives 200 and `mode: "container"` (the first container start). A 401 names its cause in the Worker logs (`refuse()`). Rollback: `npx wrangler secret delete EXECUTOR_TOKEN --config workers/proxy/wrangler.toml`, which returns to 401-only and zero container cost.
2. `wrangler containers info <id>` and Worker logs. Verify: the instance starts, then stops after `sleepAfter`.
3. `REDIACC_TOKEN=<caller tok> rdc --proxy https://proxy.eu.rediacc.com machine status hostinger`. Proves the full chain: CLI, Worker, container, config pull and decrypt, SSH to hostinger. Verify: output matches the local run, and the audit event names the user. Once B5b lands, the caller token comes from the mint command.
4. `repo status`, `repo up` and `repo down` on `demo-stackoverflow:proxytrial`, as in Phase 1. Proves egress, streaming, detach and re-attach through the Worker. Rollback: operator `repo delete` of the fork.
5. Measure container RSS and cold start (Worker logs, `containers info`), decide whether `lite` is viable, and record both numbers here.

After step 4 is green, box C2 wires the eu console.

## 4. Pricing and cost

Sources: developers.cloudflare.com/containers/pricing, /durable-objects/platform/pricing, /workers/platform/pricing, fetched 2026-09-24.

- **Workers Paid:** $5/month minimum. Containers require it. The account already pays it for rediacc-www and the account workers, so the proxy adds nothing to it.
  - 10M requests and 30M CPU-ms included.
  - Workers Logs: 20M events included.
- **Containers:**
  - Memory $0.0000025/GiB-s (25 GiB-h/month included), billed on provisioned memory.
  - vCPU $0.000020/vCPU-s (375 vCPU-min/month included), billed on **active use only**.
  - Disk $0.00000007/GB-s (200 GB-h/month included).
  - Egress in NA/EU $0.025/GB after 1 TB.
  - "Charges start when a request is sent to the container or when it is manually started. Charges stop after the container instance goes to sleep." Scale-to-zero is the default, and there is no minimum instance count.
  - Image storage limit is 50 GB per account. Storage is not listed as billed.
- **Durable Objects:** 1M requests and 400k GB-s included. SQLite: 5 GB, 25B row reads and 50M row writes included. Negligible here.
- **Library behaviour:** `sleepAfter` defaults to `'10m'` in `@cloudflare/containers`. An open HTTP stream counts as in flight, and the idle timer restarts only when the stream ends, so a long `repo up` stream keeps the container awake correctly.
- **Current settings:** `instance_type = "basic"` (1/4 vCPU, 1 GiB, 4 GB disk; `workers/proxy/wrangler.toml:35`), `max_instances = 2` (`:40`, since 5f9a354ea), `sleepAfter = '2m'` (`workers/proxy/src/index.ts:63`, since 3b96d5133).

Per running `basic` instance-hour:
- memory $0.0090
- disk $0.0010
- CPU up to $0.018 when fully busy, near $0 when idle

The allowances cover about 25 memory-hours and 50 disk-hours.

| Scenario | Container hours/month | Estimate |
|---|---|---|
| No `EXECUTOR_TOKEN`, or no caller (the Worker 401s before `getContainer`, `workers/proxy/src/index.ts:135-143`) | 0 | **$0 marginal** |
| Trial (30 sessions x 20 min + 2 min tail) | ~11 | **$0** (within allowances) |
| One team, 8 h per working day | ~176 | about $1.36 memory + $0.13 disk + $0 CPU, about **$1.5/month** |
| Runaway at the current cap: 2 instances pinned 24/7 | 1,460 | about $13 memory + $1.5 disk + CPU, about **$15/month** |
| Runaway at the old cap: 20 instances pinned 24/7 | 14,600 | about **$150/month** |

The remaining cost risk is a raised `max_instances` combined with something that keeps instances awake.

Recommendations, as of 2026-10-23:
1. `max_instances = 2` (done). Raise it deliberately when more teams use the proxy.
2. `sleepAfter = '2m'` (done). In-flight streams still keep the instance alive; the cost is a 1-3 s cold start more often, which Phase 2 step 5 measures.
3. Keep `instance_type = "basic"` until Phase 2 step 5 measures RSS. `lite` (1/16 vCPU, 256 MiB) would cut memory cost 4x but is probably too small for the Node runtime and too slow for ssh2 crypto.
4. Leave `EXECUTOR_TOKEN` unset whenever nothing uses the proxy. It is the kill switch.
5. Add the cost-guard gate (A5).

## 5. Teardown (fallback only)

Under the 2026-10-23 ruling the proxy is kept. Run this only if the operator shelves it. It is an M-live operator run: cwd `workers/proxy`, with a scoped `CLOUDFLARE_API_TOKEN`.

1. `npx wrangler containers list`: record the id of `rediacc-proxy-eu-executorcontainer`.
2. `npx wrangler containers images list`: record the `rediacc-proxy-eu-executorcontainer:<tag>` entries.
3. `npx wrangler delete --name rediacc-proxy-eu` (add `--force` if wrangler asks). This removes the script, its versions, its secrets (`EXECUTOR_TOKEN`), the `proxy.eu.rediacc.com` custom domain, and the DO namespace it owns.
4. `npx wrangler containers delete <id>` if step 1's app is still listed.
5. `npx wrangler containers images delete rediacc-proxy-eu-executorcontainer:<tag>` for every tag from step 2.
6. Revoke the `proxy:exec` portal token(s) created for `EXECUTOR_TOKEN` and for callers.
7. Verify:
   - `npx wrangler deployments list --name rediacc-proxy-eu` fails (not found)
   - `curl -sS https://proxy.eu.rediacc.com/v1/health` fails to resolve or connect
   - `containers list` and `containers images list` show nothing for the proxy
   - Dashboard > Workers & Pages shows no `rediacc-proxy-eu`
   - Dashboard > Billing > Billable usage shows Containers memory, vCPU and disk flat from the next day, and the next invoice has $0 in Containers lines
8. Do **not** downgrade Workers Paid. Other production Workers depend on it.
9. If C2 has landed, set eu's `EXECUTOR_MODE` back to `mock` and drop the C1 binding before step 3, or the account worker loses a bound service.
10. Repo follow-up (optional): keep the code. The gate fixture `.ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py:44` names the worker and can stay.

## 6. Remaining work by writer (disjoint files)

**Worker, deploy and gates.** Files: `workers/proxy/**`, `.ci/rediacc_ci/deploy/deploy_proxy.py`, `.ci/rediacc_ci/tests/test_deploy_deploy_proxy.py`, `.ci/scripts/quality/check_proxy_cost_guard.py`, `scripts/ci-runner/manifest.ts`, `package.json`, `.github/workflows/ci.yml`, `.github/workflows/ci-quality.yml`.
1. [P1] `--region` refusal.
2. [P1] The image smoke as a CI job after `build-renet`, replacing its `local-only` BLOCKER.
3. [P2] A5 cost guard (missing test 9).
4. [P2] A6 `wrangler dev` e2e (missing test 5).

**CLI.** Files: `packages/cli/src/commands/subscription*.ts`, `packages/cli/src/services/executor/**`, `packages/cli/src/i18n/locales/**`, `packages/shared/src/cli-contract/**`, `packages/e2e-tests/**`.
1. [P1] B5b, after B5a's route exists.
2. [P2] B4 VM e2e (missing test 6).

**Account (submodule branch).** Files: `private/account/src/routes/proxy.ts`, `private/account/src/routes/console.ts`, `private/account/src/types/env.ts`, `private/account/tests/integration/**`, plus `workers/account/wrangler.eu.toml` and `workers/account/src/index.ts` in the console repo.
1. [P1] B5a with missing test 8.
2. [P1] C1 executor service binding.

**Operator (M-live), in order.**
1. Phase 0, recorded.
2. Phase 2 steps 0-5, recorded in "Phase 2 results" (P2a and step 5).
3. C2 eu console wiring after Phase 2 is green.

## Phase 2 results (bench, 2026-10-24, sub-agent of lead session d778be9d)

Run on bench under the operator's bench-only bypass order (2026-10-24), not against hostinger: the eu proxy and hostinger stay untouched until the converge plan's H1 window (PLAN-renet-runtime-converge).

| | Before | After | Rollback |
|---|---|---|---|
| Account worker `rediacc-account-bench` (carries the CloudflareInternal entrypoint, account 9fb73f0) | 9acd4c8d | dfe865fb-974c-4c6d-bda1-031ee48aa40e, then secret change 10818332-b24c-44a8-9230-820f35c140c3 | `wrangler rollback 9acd4c8d`; D1 bookmark `000000bd-00000000-0000510e-7231ac96b7367046489c2029f87ccdfc` |
| Proxy worker `rediacc-proxy-bench` (ACCOUNT binding with `entrypoint = "CloudflareInternal"`) | 89b9e1f2 | 358bb286, then secret changes to eecfe3c1-f798-4a9d-989a-d3ecfb28bc5f | `wrangler rollback 89b9e1f2` |

`EXECUTOR_TOKEN` is token 5375a8fe: scopes `proxy:exec` and `audit:write`, IP binding `cloudflare` (`private/account/src/types/api-token.ts:18,22`), owned by a fresh bench org owner.

| Step | rc | Result |
|---|---|---|
| 1. `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` | 0 | account deployed |
| 2. `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench` | 0 | the DoH pin answered past a cached NXDOMAIN; `/v1/health` 200, unauthenticated `/v1/server-info` 401 |
| 3. `/v1/server-info` with a fresh owner's caller token | 0 | 200 `{"cliVersion":"2.4.0","contractVersion":"dev","mode":"container"}`, 3.07 s cold, 0.56 s warm; the account tail shows `entrypoint CloudflareInternal ... /proxy/introspect 200` |
| 4. `rdc --proxy https://proxy.bench.rediacc.com machine status vm12` | 1 | "The executor could not verify this token with the account server (403)": the container's own account calls went out its public egress and met the `cloudflare` binding |

Step 4 findings and their fixes:
- Container account egress refused with 403: fixed in f379e5b75 (the container addresses `http://account.internal`, intercepted by `ExecutorContainer.outboundByHost` and forwarded over the ACCOUNT binding). A bounded diagnostic with an `unbound` token (since revoked) showed every container call answering 200 once the binding question is out of the way, and the config decrypting.
- Executor audit events all rejected 400 (null type, data shape outside AuditEventSchema): fixed in 77c2518c2 and 069eeb770 (`cli.command` type, schema-valid payload, one event per command including a throwing dispatch).
- A Cloudflare container cannot reach the ops VMs (192.168.111.0/24 is private to the dev box), so `machine status`, fork, `repo up` and `repo down` end-to-end need a publicly reachable test machine. hostinger is excluded until H1.
- A new secret reaches a container only after its Durable Object idles out (`sleepAfter = 2m`): a container started a minute after `secret put` still ran the previous script version.

Re-run after the fixes (bench, 2026-10-24 07:05-07:13Z): proxy `rediacc-proxy-bench` 0432aa69-c448-4940-b38b-65eaad70d7bb (carries f379e5b75, 5a047c9c3, 3763bad34; rollback 4fb58b44), account `rediacc-account-bench` 83e0c016-40c6-4447-8ead-723e42f1fa6c (carries 77c2518c2; rollback 10818332, D1 bookmark `000000c5-00000000-0000510e-1d0a055499205be40954a9fca240beda`).

| Step | rc | Result |
|---|---|---|
| 4. `rdc --proxy https://proxy.bench.rediacc.com machine status vm12` (three runs, one from cold) | 1 | fails only at SSH, `Timed out while waiting for handshake` (vm12 is private to the dev box); the account tail shows the container's `.well-known/server-info`, `proxy/introspect`, `configs/executor-token`, the config pull and `licenses/audit-events` all 200 via the CloudflareInternal entrypoint |

event_log gained rows 9577d702-88d4-48e6-ad8d-4a5058a3c2ea and 75d402ca-c849-40f3-96ce-143277e1518c, both `type=cli.command`, attributed to the caller's proxy token through `onBehalfOfTokenId`. One earlier run right after a deploy ended with a client-side `fetch failed` that two cold runs did not reproduce; the proxy client calls `fetch` with no timeout and drops the error cause (worklist item).

## Phase 2 step 5 measurements (bench, 2026-10-24)

Instance type `basic` (0.25 vCPU, 1 GiB, 4 GB disk). The GraphQL `containersMetricsAdaptiveGroups` maximum memory was 237-242 MiB per minute while idle and serving server-info, disk 465 MiB, about 122 s up per wake (the 2 m sleep holds). `wrangler containers info` reports no RSS. Cold start, Worker wall time / container wall time on the first request after idle: 3000/2270, 2493/1967, 4909/4281 and 2348/1619 ms; warm 487 ms. Verdict: `lite` (256 MiB) is not viable, since idle use already sits at about 240 MiB before any `repo up`; keep `basic`.

## Phase 0 results (2026-10-24, lead session d778be9d)

| Check | rc | Output |
|---|---|---|
| `curl -sS https://proxy.eu.rediacc.com/v1/health` | 0 | `{"ok":true}` |
| `curl -sS -o /dev/null -w '%{http_code}' https://proxy.eu.rediacc.com/v1/server-info` | 0 | `401` |
| `npx wrangler containers list` in workers/proxy, through `bws_env exec --profile deploy-workers` | 0 | one app, `rediacc-proxy-eu-executorcontainer` (a030433c-f7b8-40aa-adea-d39ed0c87fb3), state `ready`, live instances 0, last modified 2026-09-24T14:26:21Z |

Rollback handles, read with `wrangler deployments list`: live version 9c90605d-b963-4ccf-b952-fda0bab48958, previous upload 17b3164d-f07b-4755-8926-edfdc682bceb (2026-09-24T14:41:57Z). `wrangler secret list` shows an EXECUTOR_TOKEN set by the 2026-09-24T16:13:52Z "Secret Change" deployment. Cloudflare cannot show its scopes, and it may be the Phase 1 token without `audit:write`.

Phase 2 is held on the token. `POST /account/api/v1/api-tokens` is the only route that mints `audit:write` with the `cloudflare` binding. It needs a portal session cookie of an org owner or admin (private/account/src/middleware/session.ts:10, private/account/src/routes/api-tokens.ts:59-72), so a password, a Turnstile captcha and possibly 2FA. The B5 mint grants only `proxy:exec` for 5 minutes. Phase 2 step 4 also cannot run as written while hostinger runs renet 7e6a8588: `repo up` and `repo down` go through `provision` access (packages/cli/src/services/executor/local-executor.ts:304-331), even through the proxy, and would install this branch's renet there (worklist #d0928775). Step 3 and the read-only half of step 4 (`machine status`, `repo status`, `repo list`) never upload renet.

## Phase 1 results (2026-09-24, lead session d778be9d)

History. Run on the dev box with an operator-created portal token (scope `proxy:exec`; kept in a mode-600 scratch file, never in the repo).

- **Daemon up.** `REDIACC_ACCOUNT_SERVER=https://eu.rediacc.com REDIACC_TOKEN=<token> ./rdc.sh serve --mode daemon --host 127.0.0.1 --port 18080` printed `Executor listening on http://127.0.0.1:18080 (mode: daemon)`, and `/v1/health` returned `{"ok":true}`.
- **`machine status hostinger` through the proxy: rc 0**, with live data (31.3G memory, datastore 85% used, scrub last run 2026-09-20). This covers the whole daemon path: CLI, daemon, token introspection, policy, dispatch, and a real SSH to hostinger.
- **`repo status demo-stackoverflow@hostinger` through the proxy: rc 0.** It returned the repo's real record (guid `db315abd-...`, created 2026-03-17T08:41:15Z). This was read-only on a grand repo, which S1 allows.
- **The first attempt failed with 401.** The active config's account pointer is `https://edge-eu.rediacc.com`. The edge account server has its own database, so a production token is unknown there (`Invalid or expired API token`, 401), while the same token introspects `active: true` on `eu.rediacc.com`. The daemon takes the introspection URL from the CLI config, so a trial must pin `REDIACC_ACCOUNT_SERVER` to the server that issued the token.
- **Found, F1: proxied commands are not audited.** The daemon logged `Ran "repo status" for muhammed@rediacc.com but could not record it: The account server rejected the audit event (403)`. The executor posts the audit event with a token that lacks `audit:write` (its scopes: license:activate, license:read, subscription:read, proxy:exec, backup:read, config:enroll, proxy:admin). The command still runs, so an audit gap is silent apart from a log line.
- **Not run: the fork steps (Phase 1 steps 4-5).** `rdc repo fork demo-stackoverflow@hostinger --tag proxytrial` failed before creating anything with `Token is bound to a different IP address`: the CLI's stored subscription token (used to license the fork) was minted from another IP. The CLI rolled its config back. The steps need an operator re-login of the CLI on this machine.
- **Fork steps PASSED after the operator's CLI re-login.** The re-login went against edge-eu.rediacc.com, the active config's account pointer. Its subscription token licenses the fork, while the proxy token came from eu.rediacc.com.
  - `rdc repo fork demo-stackoverflow@hostinger --tag proxytrial` created the fork, with a local CLI licence activation and repo key deploy.
  - Through `rdc --proxy http://127.0.0.1:18080`, each rc 0:
    - `repo status demo-stackoverflow:proxytrial@hostinger`
    - `repo up ...`: 56.5 s, 2 containers, exposed at `https://pgadmin-fork-proxytrial.demo-stackoverflow.hostinger.rediacc.io`, which answered 302 (pgAdmin's login redirect)
    - `repo down ...`: 0 containers afterwards
  - Cleanup: `rdc repo delete demo-stackoverflow:proxytrial@hostinger -y` (LUKS unmounted, repository deleted); `repo list` no longer shows the fork, and the daemon is stopped.
  - **Phase 1 is complete:** the executor protocol drives a real machine end to end, including a detached `repo up` stream. On 2026-09-24 Phase 2 still needed B1-B4; all four landed in 3b96d5133.

## Writer B status (2026-09-24, session d778be9d)

History; all of it is on `origin/main` in 3b96d5133.

- **S1 fixed.** The executor computes grand-ness itself (`resolveGrandRepoMutation`, `packages/cli/src/services/serve/policy.ts`) from the config the command runs against. The command set is the CLI guard's `grandGuard`; the repo test is the CLI guard's `grandGuid` check, but it fails closed on an unparseable or unknown ref. `repo promote` counts as a grand mutation by definition. With no policy document a grand-repo mutation is refused for every role; a document opts in with `allowGrandRepos`. Reads stay allowed. Test: `services/serve/__tests__/grand-repo-guard.test.ts` (missing test 7), container and daemon tiers.
- **F1 fixed.** Before running a command, the executor introspects its own token (`AuthVerifier.canWriteAudit`, cached for 60 s). If it cannot audit, a change is refused with 503 and a read runs with a WARNING in the result's stderr and the executor log. **EXECUTOR_TOKEN (the container's `REDIACC_TOKEN`) needs `audit:write` alongside `proxy:exec`.** Test: the `audit capability (F1)` block of the same file.
- **B3 fixed.** `CommandRequestContext.config` carries a request-scoped config. `configFileStorage` (load, save, update*, exists, list) and `configService` (getCurrent, getDecryptedConfig, getResourceState) serve it during a container dispatch and on the re-attach route. Writes stay in memory, and a spec write adds a WARNING to the result. Daemons keep their disk config. Test: `container-config.test.ts`, which no longer mocks `configService` at all. Execution resolves `10.9.9.9` and the decrypted SSH key (missing test 2), and re-attach resolves the machine the same way.
- **B4 fixed.** `ProxyClient.ensureSession()` asks for server-info and grants only to a `container`. It seals the CEK from `RemoteConfigAdapter.unwrapCek()` (new) with `cekHandoffEncrypt` and grants once per process per executor and token; a failed grant is retried. Tests: `services/executor/__tests__/proxy-client-session.test.ts` (unit, missing test 3), and the loopback variant in `container-config.test.ts`, where a real `rdc --proxy` completes the grant.
- Found, outside Writer B's files, and since fixed in 3b96d5133 with the tests named in section 2:
  - (a) `commands/serve.ts` `loadDaemonConfig` returned `getLocalConfig()`, which has no `policy`, so a daemon never enforced a policy document. It now returns the decrypted config (`packages/cli/src/commands/serve.ts:136`).
  - (b) `utils/errors.ts` `outputJsonError` wrote with `process.stdout.write` rather than `writeStdout`, so a dispatched command's JSON error went to the executor's stdout and the client saw only "The command exited with code 1".
  - (c) `utils/command-policy.ts` passed `name:base` refs through `getRepository`, which missed the grand's `latest` key, so the local agent guard returned early (fail-open). It now resolves a bare or `:base` ref to the family's grand (`packages/cli/src/utils/command-policy.ts:246`).

## Writer A status (2026-09-24, session d778be9d)

History; the code is on `origin/main` in 3b96d5133 and the gate wiring in 0868e3a53.

- **B1 fixed.** `ExecutorContainer.envVars` is built from the Worker env by `executorEnvVars(env)`: `REDIACC_TOKEN` = `EXECUTOR_TOKEN`, `REDIACC_ACCOUNT_SERVER` = `ACCOUNT_URL` (`workers/proxy/src/index.ts`). The dead `REDIACC_EXECUTOR_MODE` is gone. A Worker with no `EXECUTOR_TOKEN` answers 401 without introspecting. `sleepAfter` is `'2m'` (section 4, recommendation 2).
- **Missing test 1 added.** `workers/proxy/src/__tests__/index.test.ts` (plain vitest, `npm run test:unit`; the Container is a stub): health, the 401 cases, org:team and org:default, the executor-token guard, and the B1 envVars regression. 14 tests on 2026-09-24, 16 on 2026-10-23.
- **B2 fixed.** The Dockerfile copies `workers/proxy/renet/renet-linux-amd64` to `/usr/local/bin/renet`, and the bundle takes its `CLI_VERSION` from that renet's own `renet version`, so the two cannot disagree. The deploy builds it on a real deploy at the current version. A real deploy refuses before any build without `ACCOUNT_ED25519_PUBLIC_KEY`, because the executor uploads its renet to machines.
- **Missing test 10 added.** The deploy smoke-tests the host named by `wrangler.toml`'s route: `/v1/health` must answer 200 and an unauthenticated `/v1/server-info` must answer 401. The false "dry run does a docker build" header claim is corrected. The bash twin was deleted on 2026-10-08 (cb2908164); `test_deploy_deploy_proxy.py` now pins the Python deploy alone.
- **Missing test 4 added.** `check:ci-proxy-image-smoke` (slow, local-only) builds the image and runs it with a fake account server. It asserts the process stays up, `/v1/health`, `/v1/server-info` in `mode: container` with a `cliVersion` equal to the shipped renet, `/v1/session` introspected with the executor's own token, and `renet version`. As a control, the same image started without `REDIACC_TOKEN` must exit naming the variable. Green on the dev box on 2026-09-24.
- **CI wiring, since 0868e3a53.** CI runs the Worker tests: `check:test-workers` covers `workers/www` and `workers/proxy` (`package.json:354`), and its ci-quality step installs both (`.github/workflows/ci-quality.yml:2190`). The image smoke is still `local-only`; the image-smoke box wires it.

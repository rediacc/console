# PLAN: Cloudflare executor proxy (rediacc-proxy-eu): status, tests, live trial, cost, teardown

Status: proposed
Owner: d778be9d
Updated: 2026-09-24

## 0. Verdict

The first production deploy (2026-09-24) created the Worker, the custom domain `proxy.eu.rediacc.com`, and the container application `rediacc-proxy-eu-executorcontainer` (evidence: `.ci/cache/w7p5a-realrun/out/lead/1m-real-bash.stdout`, "Deployed rediacc-proxy-eu triggers ... proxy.eu.rediacc.com (custom domain)", Version 7c7a3192). The image was built from the `v1312` tree (`.ci/cache/w7p5a-realrun/LEAD-RUNBOOK.md:35`), not from HEAD.

**It cannot run a command against a machine today, and setting EXECUTOR_TOKEN alone will not fix that.** There are five blockers (B1-B5, section 1.3). Three of them (B1-B3) also block the web console tier. The unit tests do not catch them because each test mocks the exact seam that is broken (section 2).

The cost is about $0 marginal while it stays like this. Without EXECUTOR_TOKEN no caller can wake a container (section 4).

## 1. What the proxy is

### 1.1 Request flow (as designed)

1. **Client.** `rdc --proxy <url> <cmd>` or `REDIACC_PROXY_URL` (`packages/cli/src/cli.ts:180`, `:221`). The root preAction hook intercepts before the local action runs and calls `runCommandThroughProxy` (`packages/cli/src/cli.ts:222-243`, `packages/cli/src/services/executor/proxy-command.ts:215-259`). The bearer token is the stored subscription token, or `REDIACC_TOKEN` from the env (`packages/cli/src/cli.ts:232-240`, `packages/cli/src/services/account/subscription-auth.ts:8,121`). Refusals: 85 of 175 contract commands are `proxyCapable` (`packages/shared/src/cli-contract/data/contract.json`).
2. **Worker** (`workers/proxy/src/index.ts`).
   - `/v1/health` is answered by the Worker itself, without the container (`:99-101`).
   - Every other path introspects the caller's token with the account server, authenticating with `EXECUTOR_TOKEN` (`:68-93`). It requires `active`, an `orgId`, and scope `proxy:exec` (`:88-89`).
   - It routes to a Durable-Object-backed container keyed `orgId:teamId|default` (`:92`, `:112-113`) and forwards the request untouched.
3. **Container.** `node cli-bundle.cjs serve --mode container --port 8080` (`workers/proxy/Dockerfile:81`), the Hono app in `packages/cli/src/services/serve/server.ts`. It serves these routes (`packages/shared/src/cli-contract/wire.ts:192-205`):
   - `/v1/health`
   - `/v1/server-info`
   - `POST /v1/session`, which mints an X25519 keypair (`packages/cli/src/services/serve/server.ts:92-105`)
   - `POST /v1/session/:id/cek`, the sealed CEK grant (`:108-119`)
   - `POST /v1/command`, which streams NDJSON (`:133-257`)
   - `GET /v1/jobs/:id/events`, re-attach (`:274-351`)

   A command request goes through these stages:
   - authenticate with the account server (`packages/cli/src/services/serve/auth.ts:88,121`)
   - contract-version check (`packages/cli/src/services/serve/server.ts:145-156`)
   - `prepareCommand` hard gate (`:160-166`)
   - `loadConfig` and `authorize` against the policy inside the encrypted config (`:176-193`, `packages/cli/src/services/serve/policy.ts:97-110`)
   - in-process Commander dispatch (`:206`, `packages/cli/src/services/serve/command-dispatch.ts:316-360`)
   - an audit event (`packages/cli/src/services/serve/server.ts:221-240`)
4. **Container config loading** (`services/serve/container-config.ts`).
   - It mints its own config token with `POST /account/api/v1/configs/executor-token` (`:137-150`; server side `private/account/src/routes/configs.ts:534-566`).
   - It pulls the ciphertext (`:152-166`) and decrypts it with the CEK granted for the session (`:109`, `:127-130`).
   - The result is cached per session (`:80`, `:111-112`, `:133`).
5. **Account side.**
   - `POST /proxy/introspect` (`private/account/src/routes/proxy.ts:44-98`) is same-org only (`:66-67`).
   - `POST /proxy/session-token` (`:139-160`) is for the web console.
   - The web console passthrough is in `private/account/src/routes/console.ts:407,446`. It is gated by `EXECUTOR_MODE` (default `mock`) and `EXECUTOR_URL` (`private/account/src/types/env.ts:228-233`). Neither is set in `private/account/wrangler.toml`, so production console runs are still mocked.

### 1.2 Configuration needed before it can serve

| Item | Where | State |
|---|---|---|
| Custom domain `proxy.eu.rediacc.com` | `workers/proxy/wrangler.toml:9-11` | live |
| `ACCOUNT_URL` var | `workers/proxy/wrangler.toml:13-14` | live (`https://eu.rediacc.com`) |
| `EXECUTOR_TOKEN` secret: a portal API token, scope exactly `proxy:exec`, in the org that owns hostinger's config | `workers/proxy/wrangler.toml:16-17`, `workers/proxy/src/index.ts:32,76` | **missing** |
| Container receives its token | `packages/cli/src/commands/serve.ts:61-67` reads `REDIACC_TOKEN` | **never passed (B1)** |
| Org has a remote config store holding hostinger | `packages/cli/src/services/serve/container-config.ts:115-118`, `private/account/src/routes/configs.ts:552-561` | operator must confirm (`rdc config remote status`) |
| Caller token carries `proxy:exec` | `workers/proxy/src/index.ts:89`, `packages/cli/src/services/serve/auth.ts:121` | CLI login token does not (B5) |

The design is single-org. Introspection answers `active:false` for a token from another org (`private/account/src/routes/proxy.ts:66-67`), so one `EXECUTOR_TOKEN` means one org.

### 1.3 Finished vs broken

Finished and unit-tested:
- Worker routing and introspection
- serve HTTP surface, NDJSON framing, re-attach
- X25519 session and CEK grant with principal binding (`packages/cli/src/services/serve/sessions.ts:216-225`)
- policy (including the stale-deny refusal)
- audit attribution
- container config pull and decrypt
- the account endpoints
- deploy script and its Python twin

Blockers:

- **B1: the container never gets its token, so it exits at boot.**
  - The Worker passes only `envVars = { REDIACC_EXECUTOR_MODE: 'container' }` (`workers/proxy/src/index.ts:49-51`). Nothing in `packages/cli/src` reads `REDIACC_EXECUTOR_MODE`, so the variable is dead.
  - `rdc serve` throws when `REDIACC_TOKEN` is absent (`packages/cli/src/commands/serve.ts:61-67`).
  - `EXECUTOR_TOKEN` exists only in the Worker env. It is never handed to the DO or the container.
  - Fix: in `ExecutorContainer`, build `envVars` from `this.env`: `REDIACC_TOKEN: env.EXECUTOR_TOKEN`, `REDIACC_ACCOUNT_SERVER: env.ACCOUNT_URL` (`packages/cli/src/commands/serve.ts:69` resolves the URL through `packages/cli/src/services/account/subscription-auth.ts:33-41`). The library forwards `envVars` at start (`workers/proxy/node_modules/@cloudflare/containers/dist/lib/container.js`, lines 1327 and 1336).
- **B2: the image has no renet binary.**
  - It ships only `cli-bundle.cjs`, `ssh2` and `cpu-features` (`Dockerfile:71-73`). It is not a SEA.
  - Outside a SEA, `acquireRenet` resolves a local renet through the path or `which renet` (`packages/cli/src/services/renet/renet-execution.ts:189-191`, `:50-72`) and throws "Renet binary not found ... and not in PATH". Every machine command therefore fails.
  - Fix: copy a `renet-linux-amd64` whose version matches the bundle to `/usr/local/bin/renet`, or run the SEA in the image. The build context must then include the renet build output, which today `.ci/scripts/deploy/deploy-proxy.sh:31-34` does not build.
- **B3: the decrypted config is used for policy only, not for execution.**
  - `packages/cli/src/services/serve/server.ts:176` loads the session config and passes it only to `authorize` (`:177-193`).
  - `dispatchCommand` (`:206`) gets no config. The dispatched Commander tree reads `configService` and `configFileStorage` from disk (`packages/cli/src/services/serve/command-dispatch.ts:320-322`). `CommandRequestContext` has no config field (`packages/cli/src/services/core/request-context.ts`).
  - In the container that disk is empty, so machine and repo lookups fail. The re-attach route is affected the same way (`packages/cli/src/services/serve/server.ts:295`, then `connectForJobs(machine)`).
  - Fix: add `config` to `CommandRequestContext` and have `configService`/`configFileStorage` serve it while a dispatch is in progress.
- **B4: the CLI `--proxy` client never opens a session or grants the CEK.**
  - `proxy-client.ts` calls only `/v1/command`, `/v1/server-info` and `/v1/jobs` (`:163`, `:189`, `:292`). It never calls `/v1/session`.
  - The container therefore answers every command 404 "This session has no config key yet" (`packages/cli/src/services/serve/container-config.ts:100-106`).
  - Only the web console implements the grant (`private/account/src/routes/console.ts:407,446`), and that tier is `mock` in production.
  - Fix: a `ProxyClient.ensureSession()` that opens a session, unwraps the local CEK from the `config remote` enrollment, seals it with `cekHandoffEncrypt` to the executor's key, and posts it once per process. This needs a CLI whose config is remote-enabled.
- **B5: CLI login tokens lack `proxy:exec`.**
  - The device-code login mints `license:*`, `subscription:read`, `audit:write` and `backup:*` (`private/account/src/services/device-code.service.ts:145-157`).
  - The Worker returns 401 for such a token (`workers/proxy/src/index.ts:89`).
  - Workaround for the trial: create a portal API token with scope `proxy:exec` and pass it as `REDIACC_TOKEN`. Permanent fix: an explicit command that mints a proxy token, or add the scope at login (account submodule, separate PR).

Safety finding:

- **S1: the grand-repo guard does not apply through the proxy.**
  - `assertCommandPolicy` runs inside the local action, and only when `isAgentEnvironment()` is true (`packages/cli/src/utils/command-policy.ts:233`).
  - `--proxy` exits before the action (`packages/cli/src/cli.ts:221-243`). The executor process is not an agent.
  - `authorize` has an `isGrandRepo` field (`packages/cli/src/services/serve/policy.ts:85-86`) that `packages/cli/src/services/serve/server.ts:177-193` never sets.
  - So an agent using `--proxy` can mutate `observability` or any other grand repo, unless the org's policy document forbids it.
  - Until this is fixed, the trial below allows only read-only commands, plus commands aimed at a fork the operator created.

Smaller defects:
- `.ci/scripts/deploy/deploy-proxy.sh:9-10` claims the dry run does a docker build. It does not (`:38-42`), a gap `.ci/rediacc_ci/quality/container_build_context.py:3` already records.
- The `--region` value is ignored (`.ci/rediacc_ci/deploy/deploy_proxy.py:70`).
- `workers/proxy/tsconfig.json` comments about `src/__tests__` reaching `private/account` i18n, but the directory does not exist.

## 2. Test coverage

| Test | Count | Proves | Does not prove |
|---|---|---|---|
| `packages/cli/src/services/serve/__tests__/loopback.test.ts` | 28 | The real `rdc --proxy` Commander path to a real serve app over HTTP, with real X25519 | It uses a fake executor and a mocked `configService`; no Worker, no container, no machine |
| `.../container-config.test.ts` | 13 | Container-mode decrypt, policy inside the ciphertext, session scoping, per-session cache | **It masks B3.** `configService` is mocked (`:55-71`, machine `10.0.0.1`). The "runs against it" test (`:308-323`) asserts only that `authorize` saw the decrypted `10.9.9.9`, never that execution used it. The grant is done with raw `fetch`, not by the CLI client (masks B4) |
| `.../command-dispatch.test.ts` | 15 | argv translation and refusals | execution |
| `.../sessions.test.ts` | 8 | The grant is bound to its principal | - |
| `.../policy-stale-deny.test.ts` | 4 | A stale deny glob is refused | Grand-repo policy (S1) |
| `.../proxy-audit-attribution.test.ts` | 3 | The audit event names the person | - |
| `packages/cli/src/services/executor/__tests__/proxy-command.test.ts` | 15 | Wire params and truncated-stream handling | Session/CEK (B4) |
| `private/account/tests/integration/proxy-introspect.test.ts` | 9 | Introspect semantics, same-org | - |
| `.../proxy-session-token.test.ts` | 8 | Console token minting and attribution | - |
| `.../config-executor-token.test.ts` | 8 | Executor config-token grant | - |
| `.../console-session.test.ts` | 11 | Account-to-executor passthrough, against a fake `EXECUTOR_URL` | - |
| `.../exec-token-cache.test.ts` | 9 | Token reuse cache | - |
| `.ci/rediacc_ci/tests/test_deploy_deploy_proxy.py` | ~15 | bash/Python twin agreement on argv and messages with fake npx/npm | Anything about Cloudflare |
| `check:ci-container-build-context` (`package.json:182`) | gate | `image_build_context` is set | That the image builds or boots |
| typecheck-workers (`.ci/rediacc_ci/quality/typecheck_workers.py`) | gate | The Worker typechecks | behaviour |

- `workers/proxy` has **zero tests**.
- No e2e test in `packages/e2e-tests` uses `--proxy` or `serve`.
- **No test sends a real request through the Worker to the container and back, and none reaches a machine.**
- (`private/renet/tests/integration/test_proxy_routes.py` and `.ci/rediacc_ci/tests/test_core_proxyx.py` are unrelated: Traefik routes, and CI "proxies".)

### Missing tests

1. **workers/proxy unit tests** (vitest plus `@cloudflare/vitest-pool-workers`, new `workers/proxy/src/__tests__/index.test.ts`):
   - `/v1/health` does not touch the container
   - no, inactive, wrong-scope or no-org token gives 401
   - tenant key is `org:team` / `org:default`
   - missing `EXECUTOR_TOKEN` gives 401, not 500
   - B1 regression: `envVars` carries `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER`
2. **CLI, B3 regression** (`container-config.test.ts`): assert the executed call targeted `10.9.9.9` and used the decrypted SSH key. Stop mocking `getLocalMachine` for this test.
3. **CLI, B4**: a `proxy-client` test for `ensureSession`. A loopback variant where the real `rdc --proxy` completes the grant against a container-mode app.
4. **Image smoke in CI** (a `.ci` gate): `docker build -f workers/proxy/Dockerfile .`, run it with a fake account server, and assert:
   - the process stays up (B1)
   - `GET /v1/server-info` returns 200
   - `renet version` works in the image (B2)
5. **Local Worker-to-container e2e**: `wrangler dev` with containers (needs docker), with `/v1/server-info` through the Worker returning `mode: "container"`.
6. **e2e against a VM** (`packages/e2e-tests`, nightly): `rdc --proxy <local serve> repo status <fork>`, then `repo up`/`down` on a fork.
7. **S1**: through the proxy, a mutating command on a grand repo is refused. Cover it in `policy.ts`/`server.ts` tests once the fix computes `isGrandRepo`.
8. **Account contract, B5**: a test that pins which token a CLI must present, whichever fix is chosen.
9. **Cost guard**: a gate asserting `max_instances` ≤ the budgeted cap and `sleepAfter` ≤ the budgeted value in `wrangler.toml`/`index.ts`.
10. **Post-deploy smoke** (in `deploy-proxy.sh` and its twin, keeping the differential test in sync): `curl /v1/health` gives 200 and an unauthenticated `/v1/server-info` gives 401.

## 3. Live trial against hostinger

The CLI switch is `--proxy <url>` or `REDIACC_PROXY_URL` (`packages/cli/src/cli.ts:180,221`). The Cloudflare trial is **blocked on B1-B5**. Phase 1 shows the protocol working against hostinger today, without Cloudflare.

Target rules:
- Never a grand repo. `observability` is one, and so is any non-fork root, including `demo-stackoverflow`.
- The operator creates a fork **with the normal local CLI, not through the proxy**, so the local guard applies: `rdc repo fork demo-stackoverflow@hostinger --tag proxytrial` (O(1); `docs/agent-reference/local-env.md:101-117`).
- Every trial command names `demo-stackoverflow:proxytrial` or is read-only (`machine status`, `repo list`).
- Because of S1, an agent must never run a mutating `--proxy` command on any other ref.

### Phase 0: what is live today (no changes)

| Step | Proves | Verify | Rollback |
|---|---|---|---|
| `curl -s https://proxy.eu.rediacc.com/v1/health` | Worker and custom domain are live | `{"ok":true}` | none |
| `curl -s -o /dev/null -w '%{http_code}' https://proxy.eu.rediacc.com/v1/server-info` | Auth gate, no container started | `401` | none |
| `npx wrangler containers list` / `info <id>` (cwd `workers/proxy`) | App exists, 0 running instances | instance list empty | none |

### Phase 1: daemon tier on the dev box against hostinger (unblocked)

1. The operator creates a portal API token with scope `proxy:exec` in the org, used for both the executor and the caller. Proves B5's workaround. Rollback: revoke it in the portal.
2. Terminal A: `REDIACC_TOKEN=<tok> ./rdc.sh serve --mode daemon --host 127.0.0.1 --port 8080`. Proves the server boots and authenticates with the account server. Verify: the listening line (`packages/cli/src/commands/serve.ts:105-108`). Rollback: Ctrl-C (drain handler at `packages/cli/src/commands/serve.ts:111-116`).
3. `REDIACC_TOKEN=<tok> ./rdc.sh --proxy http://127.0.0.1:8080 machine status hostinger`. Proves a real SSH to hostinger through the proxy protocol, with policy and audit. Verify: the output matches `./rdc.sh machine status hostinger`, and an audit row names the operator. Rollback: none (read-only).
4. `... --proxy http://127.0.0.1:8080 repo status demo-stackoverflow:proxytrial`. Proves positional-ref commands and machine placement. Verify: same as local. Rollback: none.
5. `... --proxy ... repo up demo-stackoverflow:proxytrial`, then `repo down` the same ref. Proves detached jobs, the NDJSON stream and re-attach. Verify: the fork URL `https://pgadmin-fork-proxytrial.demo-stackoverflow.hostinger.rediacc.io` answers after up and stops after down. Rollback: `rdc repo delete demo-stackoverflow:proxytrial` (operator, locally).

### Phase 2: Cloudflare container tier (after B1-B5 land and an operator redeploy, which is M-live)

1. `npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml`. Proves Worker introspection works. Verify: `/v1/server-info` with the caller token gives 200 and `mode: "container"` (this is the first container start). Rollback: `npx wrangler secret delete EXECUTOR_TOKEN --config workers/proxy/wrangler.toml`, which returns to 401-only and zero container cost.
2. `wrangler containers info <id>` and Worker logs. Proves the instance started and slept after `sleepAfter`. Verify: the instance goes back to stopped. Rollback: none.
3. `REDIACC_TOKEN=<caller tok> rdc --proxy https://proxy.eu.rediacc.com machine status hostinger`. Proves the full chain: CLI, Worker, container, account config pull and decrypt, SSH to hostinger. Verify: output matches the local run, and the audit event names the user. Rollback: secret delete as in step 1.
4. `repo status`, `repo up` and `repo down` on `demo-stackoverflow:proxytrial`, as in Phase 1. Proves egress, streaming, detach and re-attach through the Worker. Rollback: operator `repo delete` of the fork.
5. Measure container RSS and cold start (Worker logs, `containers info`) to decide whether `lite` is viable. Record the results in this plan.

## 4. Pricing and cost

Sources: developers.cloudflare.com/containers/pricing, /durable-objects/platform/pricing, /workers/platform/pricing, fetched 2026-09-24.

- **Workers Paid:** $5/month minimum. Containers require it. The account already pays it, since the deploy succeeded and the account runs rediacc-www and the account workers, so the proxy adds nothing to it.
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
- **Library defaults:** `sleepAfter` defaults to `'10m'` (`@cloudflare/containers` 0.3.7, `workers/proxy/node_modules/@cloudflare/containers/dist/lib/container.js`, line 20). The proxy sets `'4m'` (`workers/proxy/src/index.ts:47`). An open HTTP stream counts as in flight, and the idle timer restarts only when the stream ends (`workers/proxy/node_modules/@cloudflare/containers/dist/lib/container.js`, lines 887-960), so long `repo up` streams keep the container awake correctly.
- **Current settings:** `instance_type = "basic"` (1/4 vCPU, 1 GiB, 4 GB disk; `workers/proxy/wrangler.toml:28`), `max_instances = 20` (`:29`), `sleepAfter = '4m'`.

Per running `basic` instance-hour:
- memory $0.0090
- disk $0.0010
- CPU up to $0.018 when fully busy, near $0 when idle

The allowances cover about 25 memory-hours and 50 disk-hours.

| Scenario | Container hours/month | Estimate |
|---|---|---|
| Today (no EXECUTOR_TOKEN; the Worker 401s before `getContainer`, `workers/proxy/src/index.ts:103-113`) | 0 | **$0 marginal** (Worker requests within included) |
| Trial (30 sessions × 20 min + 4 min tail) | ~12 | **$0** (within allowances) |
| One team, 8 h per working day | ~176 | about $1.36 memory + $0.13 disk + $0 CPU ≈ **$1.5/month** |
| Runaway: 20 instances pinned 24/7 | 14,600 | about $131 memory + $15 disk + CPU ≈ **$150/month** |

The only real cost risk is `max_instances = 20` combined with something that keeps instances awake.

Recommended changes:
1. `workers/proxy/wrangler.toml:29`: `max_instances = 20` → `2` while in trial. The design has one instance per team of one org.
2. `workers/proxy/src/index.ts:47`: `sleepAfter = '4m'` → `'2m'`. In-flight streams still keep the instance alive. The cost is a 1-3 s cold start more often.
3. Keep `instance_type = "basic"` (`workers/proxy/wrangler.toml:25-28`) until Phase 2 step 5 measures RSS. `lite` (1/16 vCPU, 256 MiB) would cut memory cost 4× but is probably too slow for ssh2 crypto.
4. Leave EXECUTOR_TOKEN unset whenever no trial is running. It is the kill switch.
5. Add the cost-guard gate (missing test 9).

## 5. Teardown

Do this when development, testing and improvement are finished, or right away if the trial is abandoned. It is an M-live operator run: cwd `workers/proxy`, with a scoped `CLOUDFLARE_API_TOKEN`.

1. `npx wrangler containers list`: record the id of `rediacc-proxy-eu-executorcontainer`.
2. `npx wrangler containers images list`: record the `rediacc-proxy-eu-executorcontainer:<tag>` entries.
3. `npx wrangler delete --name rediacc-proxy-eu` (the runbook's rollback form adds `--force`, `.ci/cache/w7p5a-realrun/LEAD-RUNBOOK.md:35`). This removes the script, its versions, its secrets (EXECUTOR_TOKEN), the `proxy.eu.rediacc.com` custom domain, and the DO namespace it owns.
4. `npx wrangler containers delete <id>` if step 1's app is still listed.
5. `npx wrangler containers images delete rediacc-proxy-eu-executorcontainer:<tag>` for every tag from step 2.
6. Revoke the `proxy:exec` portal token(s) created for EXECUTOR_TOKEN and for the caller.
7. Verify:
   - `npx wrangler deployments list --name rediacc-proxy-eu` fails (not found)
   - `curl -sS https://proxy.eu.rediacc.com/v1/health` fails to resolve or connect
   - `containers list` and `containers images list` show nothing for the proxy
   - Dashboard > Workers & Pages shows no `rediacc-proxy-eu`
   - Dashboard > Billing > Billable usage shows Containers memory, vCPU and disk flat from the next day, and the next invoice has $0 in Containers lines
8. Do **not** downgrade Workers Paid. Other production Workers depend on it.
9. Repo follow-up (optional): keep the code. The gate fixture `.ci/rediacc_ci/tests/gates/test_gate_preview_worker_reaping.py:44` names the worker and can stay.

## 6. Prioritized tasks (two writers, disjoint files)

**Writer A: Worker, image, deploy, cost.** Files: `workers/proxy/**` (including new `src/__tests__/`), `.ci/scripts/deploy/deploy-proxy.sh`, `.ci/rediacc_ci/deploy/deploy_proxy.py`, `.ci/rediacc_ci/tests/test_deploy_deploy_proxy.py`, a new `.ci/rediacc_ci/quality/` image-smoke and cost-guard gate plus its `package.json` script row.
1. [P0] Cost settings: `max_instances = 2`, `sleepAfter = '2m'`.
2. [P0] B1: pass `REDIACC_TOKEN`/`REDIACC_ACCOUNT_SERVER` into `envVars`; drop the dead `REDIACC_EXECUTOR_MODE`. Add Worker unit tests (missing test 1).
3. [P1] B2: ship renet in the image; the deploy script builds it. Add the image-smoke gate (missing test 4).
4. [P1] Post-deploy smoke in the deploy script and its twin, with the differential test updated (missing test 10). Fix the misleading dry-run header claim.
5. [P2] Cost-guard gate (missing test 9); `wrangler dev` e2e (missing test 5).

**Writer B: CLI executor.** Files: `packages/cli/src/services/core/request-context.ts`, `packages/cli/src/adapters/config-file-storage.ts`, `packages/cli/src/services/config/config-resources.ts`, `packages/cli/src/services/serve/{server,command-dispatch,policy}.ts`, `packages/cli/src/services/executor/{proxy-client,proxy-command}.ts`, `packages/cli/src/cli.ts`, and the tests under `services/serve/__tests__/` and `services/executor/__tests__/`.
1. [P0] B3: request-scoped config for dispatch and re-attach, plus missing test 2.
2. [P0] S1: compute `isGrandRepo` at the executor and refuse grand-repo mutations by default, plus missing test 7.
3. [P1] B4: `ProxyClient.ensureSession` with the CEK grant, plus missing test 3.
4. [P2] e2e VM test (missing test 6; `packages/e2e-tests`, which Writer B takes).

**Deferred (account submodule, separate PR):** B5, the proxy:exec scope or a mint command, plus missing test 8. The `REDIACC_TOKEN` portal-token workaround covers the trial.

**Operator (M-live):**
1. Phase 0 now.
2. Phase 1 as soon as convenient.
3. Redeploy after A2, A3, B1, B2 and B3, then Phase 2.
4. **Teardown item:** a worklist entry, "Tear down rediacc-proxy-eu per PLAN-cloudflare-proxy.md section 5", due when the trial and improvement wave closes. Run it immediately if the proxy is shelved.

## Phase 1 results (2026-09-24, lead session d778be9d)

Run on the dev box with an operator-created portal token (scope `proxy:exec`; kept in a mode-600 scratch file, never in the repo).

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
  - **Phase 1 is complete:** the executor protocol drives a real machine end to end, including a detached `repo up` stream. Phase 2, the Cloudflare container, still needs B1-B4.

## Writer B status (2026-09-24, session d778be9d)

- **S1 fixed.** The executor computes grand-ness itself (`resolveGrandRepoMutation`, `packages/cli/src/services/serve/policy.ts`) from the config the command runs against. The command set is the CLI guard's `grandGuard`; the repo test is the CLI guard's `grandGuid` check, but it fails closed on an unparseable or unknown ref. `repo promote` counts as a grand mutation by definition. With no policy document a grand-repo mutation is refused for every role; a document opts in with `allowGrandRepos`. Reads stay allowed. Test: `services/serve/__tests__/grand-repo-guard.test.ts` (missing test 7), container and daemon tiers.
- **F1 fixed.** Before running a command, the executor introspects its own token (`AuthVerifier.canWriteAudit`, cached for 60 s). If it cannot audit, a change is refused with 503 and a read runs with a WARNING in the result's stderr and the executor log. **EXECUTOR_TOKEN (the container's `REDIACC_TOKEN`) needs `audit:write` alongside `proxy:exec`.** Test: the `audit capability (F1)` block of the same file.
- **B3 fixed.** `CommandRequestContext.config` carries a request-scoped config. `configFileStorage` (load, save, update*, exists, list) and `configService` (getCurrent, getDecryptedConfig, getResourceState) serve it during a container dispatch and on the re-attach route. Writes stay in memory, and a spec write adds a WARNING to the result. Daemons keep their disk config. Test: `container-config.test.ts`, which no longer mocks `configService` at all. Execution resolves `10.9.9.9` and the decrypted SSH key (missing test 2), and re-attach resolves the machine the same way.
- **B4 fixed.** `ProxyClient.ensureSession()` asks for server-info and grants only to a `container`. It seals the CEK from `RemoteConfigAdapter.unwrapCek()` (new) with `cekHandoffEncrypt` and grants once per process per executor and token; a failed grant is retried. Tests: `services/executor/__tests__/proxy-client-session.test.ts` (unit, missing test 3), and the loopback variant in `container-config.test.ts`, where a real `rdc --proxy` completes the grant.
- Found, outside Writer B's files:
  - (a) `commands/serve.ts` `loadDaemonConfig` returns `getLocalConfig()`, which has no `policy`. A daemon therefore never enforces a policy document.
  - (b) `utils/errors.ts` `outputJsonError` writes with `process.stdout.write` rather than `writeStdout`. A dispatched command's JSON error goes to the executor's stdout, and the client sees only "The command exited with code 1".
  - (c) `utils/command-policy.ts` passes `name:base` refs through `getRepository`, which misses the grand's `latest` key, so the local agent guard returns early (fail-open) if a verb accepts `:base`.

## Writer A status (2026-09-24, session d778be9d)

- **B1 fixed.** `ExecutorContainer.envVars` is built from the Worker env by `executorEnvVars(env)`: `REDIACC_TOKEN` = `EXECUTOR_TOKEN`, `REDIACC_ACCOUNT_SERVER` = `ACCOUNT_URL` (`workers/proxy/src/index.ts`). The dead `REDIACC_EXECUTOR_MODE` is gone. A Worker with no `EXECUTOR_TOKEN` answers 401 without introspecting. `sleepAfter` is `'2m'` (section 4, recommendation 2).
- **Missing test 1 added.** `workers/proxy/src/__tests__/index.test.ts` (plain vitest, `npm run test:unit`; the Container is a stub), 14 tests: health, seven 401 cases, org:team and org:default, the executor-token guard, and the B1 envVars regression. Against the old `index.ts`, 3 of them fail.
- **B2 fixed.** The Dockerfile copies `workers/proxy/renet/renet-linux-amd64` to `/usr/local/bin/renet`, and the bundle takes its `CLI_VERSION` from that renet's own `renet version`, so the two cannot disagree. `deploy-proxy.sh` and `deploy_proxy.py` build it on a real deploy with `build-renet.sh --version $(resolve-version.sh --current)`. A real deploy refuses before any build without `ACCOUNT_ED25519_PUBLIC_KEY`, because the executor uploads its renet to machines.
- **Missing test 10 added.** Both deploy twins smoke-test the host named by `wrangler.toml`'s route: `/v1/health` must answer 200 and an unauthenticated `/v1/server-info` must answer 401. The false "dry run does a docker build" header claim is corrected. `test_deploy_deploy_proxy.py` has 29 tests; against the old twins, 11 fail.
- **Missing test 4 added.** `check:ci-proxy-image-smoke` (slow, local-only) builds the image and runs it with a fake account server. It asserts the process stays up, `/v1/health`, `/v1/server-info` in `mode: container` with a `cliVersion` equal to the shipped renet, `/v1/session` introspected with the executor's own token, and `renet version`. As a control, the same image started without `REDIACC_TOKEN` must exit naming the variable. Green on this box.
- **Open, outside the file set:** CI does not run the Worker tests yet (the `check:test-workers` script and its ci-quality.yml step cover only `workers/www`), and no CI job runs the image smoke.

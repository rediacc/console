# PLAN: the console executor leaves the frozen @cloudflare/containers `Container` class for the `durable_object` scheduling policy, with per-org instance sizing and the 25-per-target cap enforced in code, before 2026-12-31

Status: approved -- operator ruling ASKED:2026-10-26T15:26Z "Per-org, raise the cap (Recommended)": one executor container per org stays, the cap is raised (worklist #9638ab6b), and this migration plan follows (worklist #54cc96a6, lead session d778be9d, branch 1023-1). The Decisions section lists the defaults taken without asking; each is open to operator veto.
Priority: P1 -- Cloudflare stops updating the `Container` class after 2026-12-31 (Context item 1), and the proxy's per-org egress identity, sleep timer and start path all sit inside that class (workers/proxy/src/index.ts:117-164). Leaving it after the freeze means running an unpatched base class under a paid customer path.
First-Seen: 2026-10-26
Owner: d778be9d
Epic: executor-durable-object-policy
Depends-On: PLAN-console-executor-multi-org.md#W1, PLAN-console-executor-multi-org.md#W2, PLAN-console-executor-multi-org.md#ML5 -- W1 and W2 wrote the per-org pin, egress and token cache that this plan rebuilds on the new class (both ticked). ML5 puts multi-org on the three stable targets, so no stable target takes both changes in one release. S1 runs on a scratch Worker and needs none of them, so its tick line carries DEPS-WAIVED with that reason. The live boxes L1 and later wait for ML5.
Concurrency: exclusive -- the code boxes rewrite workers/proxy/src/index.ts and workers/proxy/src/egress.ts, which PLAN-console-executor-multi-org's W1 and W2 own. They also rewrite workers/proxy/wrangler*.toml, .ci/rediacc_ci/deploy/proxy_configs.py and .ci/scripts/quality/check_proxy_cost_guard.py, which worklist #9638ab6b holds uncommitted (Context item 9). No writer for this plan holds those files while a W box or #9638ab6b holds them.
Owns: agent/plans/PLAN-executor-durable-object-policy.md, workers/proxy/src/**, workers/proxy/package.json, workers/proxy/package-lock.json, workers/proxy/wrangler*.toml, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/tests/test_deploy_proxy_configs.py, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py, .ci/rediacc_ci/tests/goldens/twins/deploy.deploy-proxy.jsonl, .ci/scripts/quality/check_proxy_cost_guard.py, .ci/rediacc_ci/tests/test_check_proxy_cost_guard.py, .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py, .ci/rediacc_ci/spikes/do_policy_spike.py (new), .ci/rediacc_ci/tests/test_spikes_do_policy_spike.py (new), private/account/src/services/executor-issuer.service.ts (route only), workers/account/src/index.ts (the route signature only), private/account/tests/integration/executor-issuer-route.test.ts, private/account/tests/integration/proxy-binding-wiring.test.ts, docs/observability/signals/proxy.md, .claude/skills/deploy/SKILL.md (the executor paragraph only), agent/plans/PLAN-console-executor-multi-org.md (relation lines only)

## Operator rulings

- **ASKED:2026-10-26T15:26Z "Per-org, raise the cap (Recommended)".**
  - One executor container per org per target stays: Decision 1 of PLAN-console-executor-multi-org.
  - The cap becomes 25 per target (worklist #9638ab6b).
  - This plan migrates the executor to the `durable_object` scheduling policy before the `Container` class freezes.
- **Inherited, unchanged.**
  - Secrets travel only through bws_env, and only their names appear anywhere (order 2026-10-25T18:10Z).
  - Deploys to the six targets plus bench are allowed without asking (order 2026-10-25T18:10Z).
  - Every live deploy records the version id, the smoke rc and the rollback command, plus the D1 bookmark wherever a deploy touches D1.
  - There are no external users, so this is a clean break: no dual-format shims beyond the one rollback window in Design item 6.

## Context

### Verified state (2026-10-26, console 1023-1 at a5cd6256c plus its working tree)

1. **The freeze date.** https://blog.cloudflare.com/faster-agent-sandboxes/ (2026-09-30) says: "We'll maintain the `Container` class and legacy `Sandbox` class through December 31, 2026. Existing deployments keep running after that date, but the classes won't get updates". The same post reports that "median startup fell from just over four seconds to 648 milliseconds" under the new policy. It also says the Durable Object "can update the Container's Outbound Request Handler to inject newly granted credentials". The deadline is therefore about updates, not shutdown: a missed date leaves the executor running on an unpatched base class.
2. **What the policy is.** https://developers.cloudflare.com/containers/configuration/scheduling-policy/ says:
   - "The `durable_object` policy moves per-instance decisions into your Durable Object." <!-- style-ok -->
   - "Select an image and instance size when the Durable Object starts its Container".
   - "The `durable_object` policy does not support `max_instances`."
   - "The `durable_object` scheduling policy is in public beta."
   - "The runtime does not accept `basic` or the legacy `dev` and `standard` aliases."
   - "If you omit `instance`, the Container uses `lite`." <!-- style-ok -->
   - "Container instances that use the `durable_object` policy do not participate in application-wide image rollouts."
   - The named sizes are `lite`, `standard-1`, `standard-2`, `standard-3` and `standard-4`, or a custom object `{ vcpu, memoryMib, diskMb }`.
3. **The migration rules.** https://developers.cloudflare.com/containers/guides/migrate-to-durable-object-scheduling-policy/ says:
   - "The replacement application must use a new Durable Object class and namespace."
   - "The Container class does not support the durable_object policy."
   - "Rebuild any `Container` class helpers your application relies on" (the guide names port readiness checks, request proxying and sleep timeouts). <!-- style-ok -->
   - "Enforce any per-application cap in application code."
   - "Move other supported startup settings, such as `env` and `entrypoint`, into the same call."
   - "Set `enableInternet` to match the existing application."
   - "To roll back, route traffic to the old Durable Object binding again."
   - The cutover adds the new class, binding and container entry beside the old ones, and does not edit the existing entry's `scheduling_policy`.
4. **Outbound interception on the Durable Object Container API.** https://developers.cloudflare.com/containers/api/durable-object-container/ documents:
   - `interceptOutboundHttp(addr, binding)`, where binding is a "Worker entrypoint or service binding that handles matching requests";
   - per-instance props in the example `this.ctx.exports.MyWorker({ props: { message: "hello" } })`, plus "To change the props, register the rule again with new props.";
   - "An intercept lasts until the container stops, so register intercepts again for each new container.";
   - "You cannot remove an intercept while the container runs."; <!-- style-ok -->
   - "A `monitor()` promise does not carry over when the Durable Object restarts, for example after a deploy.";
   - `start()` "returns before the container is ready to accept requests".

   The page does not name a scheduling policy for `interceptOutboundHttp`. The library the proxy runs today is built on this same primitive: @cloudflare/containers 0.3.7 `applyOutboundInterception` calls `ctx.exports.ContainerProxy({ props })` with `containerId: this.ctx.id.toString()` and then `this.container.interceptOutboundHttp(host, fetcher)` (lines 1185 to 1212 of dist/lib/container.js in the installed @cloudflare/containers 0.3.7). Whether it works under the new policy is still DU1.
5. **The toolchain already speaks the policy.**
   - wrangler 4.152.0 is installed. Its config schema has `scheduling_policy` with the enum `default`, `durable_object`, `moon` and `regional`.
   - The same schema has `images` (each entry is `{ dockerfile, build_context, build_vars }` or `{ image }`, "Only supported when `scheduling_policy` is `\"durable_object\"`").
   - `@cloudflare/workers-types` declares `start(options?: ContainerStartupOptions)` with `image`, `instance`, `env` and `enableInternet`, plus `interceptOutboundHttp(addr: string, binding: Fetcher)` and `get images()` (lines 3985 to 4047 of the installed @cloudflare/workers-types index.d.ts).
6. **What the proxy takes from the frozen class today** (workers/proxy/src/index.ts):
   - the `ContainerProxy` re-export (:30) and the static `outboundHandlers` registry (:119-124);
   - `sleepAfter = '2m'` (:137) and its alarm loop (library dist/lib/container.js lines 742 to 790 and 1502 to 1587);
   - `envVars` and `startAndWaitForPorts` with `startOptions.envVars` (:156-162);
   - `setOutboundByHost('account.internal', 'accountEgress', { orgId })` (:159);
   - `getContainer` (:275) and `container.fetch` (:279);
   - the capacity verdict, guessed from start-error text by `CAPACITY_ERROR` (:114-115).

   `enableInternet` defaults to true in the library (dist/lib/container.js line 325). The executor needs it, because it opens SSH to customer machines.
7. **The light size cannot simply be `lite`.** agent/plans/PLAN-cloudflare-proxy.md:340 measured the executor on `basic`: "maximum memory was 237-242 MiB per minute while idle", with the verdict "`lite` (256 MiB) is not viable, since idle use already sits at about 240 MiB before any `repo up`". `basic` (1/4 vCPU, 1 GiB, 4 GB) is refused under the new policy (item 2).
8. **Prices and sizes.** https://developers.cloudflare.com/containers/platform-details/limits/ gives "lite | 1/16 | 256 MiB | 2 GB", "basic | 1/4 | 1 GiB | 4 GB" and "standard-1 | 1/2 | 4 GiB | 8 GB". https://developers.cloudflare.com/containers/pricing/ gives "+$0.0000025 per additional GiB-second" for memory and "+$0.00000007 per additional GB-second" for disk, and "CPU usage is based on active usage only." Memory plus disk, awake for 30 days:
   - lite costs about $1.98 a month;
   - a basic-equivalent costs about $7.21;
   - standard-1 costs about $27.37.
9. **The cap raise is in flight and uncommitted.** The working tree carries `max_instances = 25` in workers/proxy/wrangler.template.toml and the generated configs, and `MAX_INSTANCES = 25` in .ci/rediacc_ci/deploy/proxy_configs.py:51. .ci/scripts/quality/check_proxy_cost_guard.py:44-46 still says 3 and 21. This is worklist #9638ab6b, and this plan builds on its committed result.
10. **Rollback across a class change is refused.** https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/ blocks a rollback when "A Durable Object class lifecycle change has occurred between the version in the active deployment and the version selected to roll back to." deploy_proxy.py prints `npx wrangler rollback <previous>` unconditionally (.ci/rediacc_ci/deploy/deploy_proxy.py:209-213).
11. **The gates that read the container shape:**
    - `proxy_configs.config_refusals` requires exactly one `[[containers]]` entry, one `EXECUTOR` binding and the one v1 migration (.ci/rediacc_ci/deploy/proxy_configs.py:339-357);
    - its ALLOWED_KEYS has no `exports` key (:76-92), so the legacy `migrations` path stays;
    - check_proxy_cost_guard reads `max_instances` from TOML and `sleepAfter` from class bodies under workers/proxy/src (:108-195);
    - proxy_wrangler_dev_e2e builds its own dev config with `ExecutorContainer` (.ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py:677-679).

### Unverified claims (each is proved or refuted by the box named)

- DU1 (S1): under `scheduling_policy = "durable_object"`, `ctx.container.interceptOutboundHttp('account.internal', ctx.exports.AccountEgress({ props }))` routes the container's HTTP to that entrypoint with exactly that instance's props, and two instances never see each other's props.
- DU2 (S1): a running container's intercept survives a Worker deploy, or the Durable Object can re-register it from its constructor without dropping a connection.
- DU3 (S1): the runtime accepts the custom size `{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }`, a basic equivalent. S1 also records the executor's idle and `machine status` peak memory under `lite`.
- DU4 (S1): `images.executor = { dockerfile = "./Dockerfile", build_context = "../.." }` builds the existing image.
- DU5 (S1): `wrangler dev` runs a `durable_object`-policy container with its intercept locally, as check:ci-proxy-wrangler-dev-e2e needs. If it does not, that gate tests the new class through a fake `ctx.container` and records the gap.
- DU6 (S1): wrangler refuses, or silently ignores, `max_instances` on a `durable_object` entry. The cost guard refuses it either way.
- DU7 (S1): `enableInternet: true` lets the container open TCP 22 to a public host.

## Design

### 1. The spike decides the egress design before any code moves

S1 deploys a scratch Worker in the bench Cloudflare account under the `deploy-proxy-bench` profile. It runs on workers.dev only, with no route, no ACCOUNT and no ISSUER binding, and one `durable_object`-policy container entry. Two instances named `org-a` and `org-b` each:

- register `interceptOutboundHttp('account.internal', ctx.exports.SpikeEgress({ props: { orgId, containerId: ctx.id.toString() } }))` before `start()`;
- start a tiny image that calls `http://account.internal/echo` 20 times, interleaved across both instances.

SpikeEgress answers its props. S1 then re-registers with rotated props, deploys a new version while both run, starts three sizes, measures cold starts, probes TCP 22, runs `wrangler dev`, and deletes everything. The verdict picks one of four designs:

- **Design A (GO): per-instance props.** DU1 holds. The egress entrypoint takes `{ orgId, containerId }` from props that only Durable Object code sets, and cross-checks `containerId === env.ORG_EXECUTOR.idFromName(orgId).toString()`. This is today's check (workers/proxy/src/egress.ts:116-130) with a new source for the context.
- **Design B (FALLBACK-1): a per-container capability.** Interception works, but props are absent or shared.
  - At each start the Durable Object draws 32 random bytes and passes them as `REDIACC_TOKEN`, replacing the fixed placeholder.
  - It stores `sha256(cap) -> { orgId, containerId, expiresAt }` in the capacity coordinator (item 3) and deletes the row when the container stops.
  - The egress entrypoint, registered without props, looks up the hash with a constant-time compare and swaps the bearer for that org's issued token. Requests with no bearer go only to the three open routes (workers/proxy/src/egress.ts:30-36), which are public on the account server anyway.
  - A capability is useless outside its own container, and it rotates on every start.
- **Design C (FALLBACK-2): a public egress route.** No interception works under the policy. The container's `REDIACC_ACCOUNT_SERVER` becomes `https://proxy.<domain>/v1/egress`, and Design B's capability authenticates every bearer call. The Worker answers that path only for a capability the coordinator knows. The allowlist and the token swap are unchanged.
- **STOP.** Neither works: the container cannot reach the proxy Worker. The operator is asked (an ASKED line) whether to stay on the frozen `Container` class past 2026-12-31, which keeps running per Context item 1.

W3 implements only the design the verdict names. The rest of the plan is the same under A, B and C.

### 2. A new class and namespace beside the old ones

- **`OrgExecutor extends DurableObject<Env>`** in workers/proxy/src/org-executor.ts, bound as `ORG_EXECUTOR`. It uses `this.ctx.container` directly and imports nothing from @cloudflare/containers.
- **`ExecutorCapacity extends DurableObject<Env>`** in workers/proxy/src/capacity.ts, bound as `EXECUTOR_CAPACITY`.
- **Migration `v2`:** `new_sqlite_classes = ["OrgExecutor", "ExecutorCapacity"]`, appended after v1. The legacy `migrations` path stays, because moving to `exports` "cannot be undone" (Context item 3) and ALLOWED_KEYS has no `exports`.
- **A second `[[containers]]` entry:**

  ```toml
  [[containers]]
  class_name = "OrgExecutor"
  scheduling_policy = "durable_object"

  [containers.images.executor]
  dockerfile = "./Dockerfile"
  build_context = "../.."
  ```

  It carries no `max_instances` and no `instance_type`. The old `ExecutorContainer` entry, binding `EXECUTOR` and migration v1 stay until Phase 3 (item 6).
- **Two vars, `EXECUTOR_BACKEND` (`container` | `durable`) and `EXECUTOR_CAP` (a decimal string).**
  - Both are generated per target from tables in proxy_configs.py, `BACKEND_BY_TARGET` and `CAP_BY_TARGET`.
  - The Worker routes each request to `EXECUTOR` or `ORG_EXECUTOR` by the version's `EXECUTOR_BACKEND`, never by anything per request ("Choose the binding per logical Container, not per request", Context item 3).
  - During a gradual rollout, two versions can briefly route one org to both backends. The org's sessions then miss once, and the web client re-grants transparently (PLAN-proxy-cd-six-targets R1). This is accepted.

### 3. The cap of 25 per target, enforced in code

- **One `ExecutorCapacity` instance per target**, `idFromName('capacity:v1')`, holds a SQLite table `leases(org_id TEXT PRIMARY KEY, size TEXT NOT NULL, expires_at INTEGER NOT NULL)`.
- **RPCs:**
  - `acquire(orgId, size)` sweeps expired rows. It is idempotent per org: re-acquiring renews and never double-counts. It answers `{ ok: true }`, `{ ok: false, reason: 'full' }` or `{ ok: false, reason: 'heavy-full' }`.
  - `renew(orgId)` answers `held` or `not-held`.
  - `release(orgId)`.
  - `count()`, read only, for `/v1/ready` and tests.
- **The limits.**
  - `cap = min(parseInt(env.EXECUTOR_CAP), HARD_CAP)`, with `HARD_CAP = 25` a literal in capacity.ts.
  - `heavyCap = min(parseInt(env.EXECUTOR_HEAVY_CAP), HARD_HEAVY_CAP)`, with `HARD_HEAVY_CAP = 5` (Decisions 3).
  - A missing or unparsable var means `HARD_CAP`, never unlimited.
- **The lease.** A lease lives `LEASE_MS = 180_000`: `sleepAfter` of 120 s plus 60 s of grace.
  - OrgExecutor renews at each request start, throttled to once per 30 s, and from its idle alarm while a request is in flight, so long NDJSON streams hold their slot.
  - A crashed or redeployed OrgExecutor frees its slot within 180 s with no cleanup path. The coordinator's alarm sweeps expired rows.
- **Refusal.** `acquire` answering `full` or `heavy-full` makes the Worker answer the existing 503 `{ code: 'EXECUTOR_CAPACITY' }` with `Retry-After: 30` and the span attribute `rediacc.proxy.outcome = capacity` (workers/proxy/src/index.ts:216-226 shape, unchanged). console.ts already relays that code (PLAN-console-executor-multi-org A4). The `CAPACITY_ERROR` text guess is deleted: the verdict is now deterministic, and MU2 of that plan is moot for the new backend.
- **Fail closed.**
  - A coordinator that throws or times out yields 503 `EXECUTOR_START_FAILED`. A container is never started uncounted.
  - A `renew` answering `not-held` re-acquires. If that is refused, the container finishes its in-flight requests and is destroyed.
  - When the Durable Object constructor finds `ctx.container.running`, it re-acquires before serving. If that is refused, it drains and destroys the container.

### 4. Per-org instance sizing

**The rule.** The size is chosen at each container start, and a running container keeps its size until it stops.

- **HEAVY = `standard-1`** when either:
  - (a) `ExecutorIssuer.route(bearer)` answers `tier: 'high'`. The account Worker sets that iff the org's live primary subscription plan is BUSINESS or ENTERPRISE; or
  - (b) the org's OrgExecutor storage records an out-of-memory exit within the last 7 days: `monitor()` rejecting with exit code 137, or with an error naming OOM.
- **LIGHT** otherwise. LIGHT is decided once by S1 and written as a literal in workers/proxy/src/sizing.ts:
  - `lite`, only if S1 measures the executor's peak memory for a `machine status` run under `lite` below 200 MiB, which Context item 7 makes unlikely;
  - otherwise the custom size `{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }` (today's `basic`) if DU3 holds;
  - otherwise `standard-1` for every org, recorded with an ASKED line, because that costs about 3.8 times today's memory.
- **Heavy slots are capped at `heavyCap` of the 25.**
  - When they are full, an org that is HEAVY only by (a) starts LIGHT, which is today's size for it.
  - An org that is HEAVY by (b) gets 503 `EXECUTOR_CAPACITY`, because LIGHT is known to fail it.
- **Escalation.** An OOM exit under LIGHT flags the org, and its next start is HEAVY. An OOM under HEAVY sets `rediacc.proxy.outcome = oom-heavy` and escalates no further.
- **Telemetry.** The span carries `rediacc.proxy.size = light | heavy`, never an org id.
- **The account change (A1).** `route` answers `{ orgId, tier }`, with `tier` computed from `PLAN_METADATA` beside the entitlement check it already runs. The proxy treats a missing `tier` as `standard`. The account deploys before the proxy in CD order, so an older proxy simply ignores the field. There is no D1 migration.

### 5. Rebuilt helpers (W1)

- **start(orgId, size).**
  1. Acquire the lease (item 3).
  2. Register the egress intercept for the S1 design before `start()`. Context item 4 allows either order, and registering first leaves no window in which an egress call escapes to DNS.
  3. `ctx.container.start({ image: ctx.container.images.executor, instance, enableInternet: true, env: executorEnvVars(env, orgId[, cap]) })`.
  4. Store `{ orgId, size, image: ctx.container.images.executor, startedAt }` in Durable Object storage.
  5. Attach `monitor()`.
- **env.** Exactly the four names of workers/proxy/src/index.ts:97-104. Under Design B or C, REDIACC_TOKEN carries the capability instead of the placeholder. The test asserts that set, and that no issued token appears in it (Design item 3 of PLAN-console-executor-multi-org is unchanged).
- **readiness.** Poll `ctx.container.getTcpPort(8080).fetch('http://container/v1/health')` every 100 ms for up to 20 s. A `monitor()` rejection during the poll is a start failure (503 `EXECUTOR_START_FAILED`) and releases the lease. S1's cold-start median is recorded.
- **proxying.** `fetch(request)` counts in-flight requests, renews the lease, forwards to `getTcpPort(8080).fetch(request)` and streams the body back untouched. The count drops when the response body closes, not when the headers arrive.
- **sleepAfter.**
  - The class body sets `sleepAfter = '2m'` as a literal, so the existing cost-guard rule reads it unchanged.
  - Each request sets the alarm to `lastActivity + sleepAfter`.
  - When the alarm fires with zero in flight and the idle time reached, it calls `ctx.container.destroy('idle')` and `release(orgId)`.
  - With requests in flight it renews and re-arms. This is stricter than the library, which renews only at request start.
- **image drift.** Running instances do not take application rollouts (Context item 2). When a request finds the stored image differing from `ctx.container.images.executor` and nothing is in flight, the instance destroys and restarts on the new image before forwarding. Under load, the restart happens at the next idle moment, so an org never keeps an old image past its next idle gap.
- **restart after deploy.** `monitor()` does not survive a Durable Object restart (Context item 4). The constructor, inside `blockConcurrencyWhile`, finds a running container and then:
  - re-attaches `monitor()`;
  - re-acquires the lease;
  - re-registers the intercept with the stored props, if DU2 says that is needed. Re-registration replaces the handler without dropping open connections, per Context item 4.
- **pin semantics are kept.** `this.ctx.id.equals(env.ORG_EXECUTOR.idFromName(orgId))`, the stored org, and a second org refused (workers/proxy/src/index.ts:147-163).

### 6. Rollout phases and rollback

- **Phase 1, deploy only.** The release adds migration v2, the new entry and both bindings, with `EXECUTOR_BACKEND = container` on every target.
  - This is a class lifecycle change, so `wrangler rollback` to an older version is refused (Context item 10). The deploy is forward-only and its record says so.
  - It changes no behaviour: every org still runs on `ExecutorContainer`.
- **Phase 2, the flip.** `BACKEND_BY_TARGET` sends a target to `durable`: bench first, then the three edge targets, then the three stable targets in a later release through promote-stable.
  - Rollback is `npx wrangler rollback <Phase 1 or later version>`, which crosses no lifecycle change. Alternatively, flip the var back and redeploy.
  - Sessions live only in container RAM, so rolling back loses nothing a re-grant cannot rebuild (no reconciliation, unlike the guide's stateful case).
- **Phase 3, cleanup.** This runs after 14 days on all three stable targets, and by the deadline box.
  - Migration v3 `deleted_classes = ["ExecutorContainer"]`. The old class held only the in-memory org and the library's state tables, so no data is needed.
  - Delete the old `[[containers]]` entry, the `EXECUTOR` binding, `EXECUTOR_BACKEND`, `ContainerProxy`, the `@cloudflare/containers` dependency and the static `outboundHandlers`.
  - Run `npx wrangler containers delete <old application id>` per target, because "Removing the Wrangler entry does not delete the application" (Context item 3).
  - This phase is forward-only again.
- **deploy_proxy detects forward-only deploys.** A target's deploy is forward-only when the config's `[[migrations]]` list differs from the one in the previous release's config, read by `git show <previous release tag>:workers/proxy/<config>`. For such a deploy, `--record` writes `rollback: "forward-only: Durable Object class lifecycle change (v<n>); fix forward"` instead of a command wrangler would refuse.
- **No D1 migration anywhere.** The live records write `D1: none (no migration)` instead of a bookmark. The account deploy for A1 changes code only.

### 7. Cost guard (G1)

- **Per entry.**
  - A `[[containers]]` entry with no `scheduling_policy`, or `default`, keeps today's rule: `max_instances` at most `MAX_INSTANCES_BUDGET` (25 after #9638ab6b).
  - A `durable_object` entry must carry neither `max_instances` (it caps nothing, per Context item 2, and a reader would believe it did) nor `instance_type` (it applies only to the default policy).
- **The code cap.**
  - Every config carrying a `durable_object` entry must carry `[vars] EXECUTOR_CAP` and `EXECUTOR_HEAVY_CAP` as decimal strings at or under `MAX_INSTANCES_BUDGET` and `HEAVY_BUDGET` (5).
  - workers/proxy/src/capacity.ts must define `HARD_CAP` and `HARD_HEAVY_CAP` as integer literals at or under the same budgets.
  - A non-literal is a finding, as `sleepAfter` already is.
- **Sizes.** Every `instance:` value under workers/proxy/src (tests excluded) must be a literal in the allowed set: `'lite'`, `'standard-1'`, or the one custom object `{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }`. `standard-2` and above, a variable, or a second custom object is a finding.
- **The per-config count during dual run** is the cap of the routed backend: `max_instances` of the default entry when `EXECUTOR_BACKEND = container`, `EXECUTOR_CAP` when it is `durable`. The unrouted backend drains within `sleepAfter`.
- **Totals.** The deployable-set total keeps #9638ab6b's limit of 175. A worst-case dollar line is added: each config costs `(cap − heavyCap) × LIGHT_MONTHLY_USD + heavyCap × HEAVY_MONTHLY_USD`, with the prices from Context item 8 as constants citing the pricing page.
  - Each config must stay at or under `MAX_CONFIG_MONTHLY_USD = 300`, and the deployable set at or under `MAX_TOTAL_MONTHLY_USD = 2100` (Decisions 4).
  - With a basic-equivalent LIGHT that is 20 × $7.21 + 5 × $27.37 ≈ $281 per target, pinned awake.
- **sleepAfter.** The existing class-body rule applies to `OrgExecutor`, with the class list read from the TOML as now.
- **Anti-vacuity.** A config whose `durable_object` entry is planted with `max_instances = 25`, an `EXECUTOR_CAP = "26"`, a `HARD_CAP = 30`, an `instance: 'standard-2'` and a missing `sleepAfter` each makes the gate exit 1. Zero entries is still exit 2.

### 8. The binding fence (G2)

The egress entrypoint (`AccountEgress`, Design A or B) is an export of the main module, so another Worker in the account could bind it through `[[services]] entrypoint = "AccountEgress"`, with props in its binding config. proxy-binding-wiring.test.ts gains a direction: no wrangler config under workers/ binds entrypoint `AccountEgress` or `ContainerProxy`. Under Design A, the containerId cross-check also refuses props that do not name an `ORG_EXECUTOR` id.

## Tasks

### Spike (before anything else)

- [ ] S1 [spike] Prove per-instance outbound interception with per-instance params under the `durable_object` policy, on bench, and record the verdict (Design item 1).
  - Add `.ci/rediacc_ci/spikes/do_policy_spike.py` with three verbs, `deploy`, `run` and `teardown`. It writes the scratch Worker into `.ci/cache/do-policy-spike/` (never under workers/), deploys it as `rediacc-do-policy-spike` on workers.dev under the `deploy-proxy-bench` profile, and records JSON.
  - It proves DU1 to DU7:
    - interleaved echo calls from `org-a` and `org-b`, each returning exactly its own `{ orgId, containerId }`, with zero cross answers in 40 calls;
    - rotated props seen after re-registration;
    - the intercept answering after a new version is deployed mid-run, and whether the constructor had to re-register (DU2);
    - `start()` with `lite`, `standard-1` and `{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }`, accepted or refused, with the real executor image's idle and `machine status` peak memory under `lite` read from `containersMetricsAdaptiveGroups` (DU3);
    - the cold-start median of 10 starts for each accepted size;
    - the `images` build with `build_context = "../.."` (DU4);
    - `wrangler dev` with the intercept (DU5);
    - wrangler's answer to `max_instances` on the entry (DU6);
    - TCP 22 reachability (DU7).
  - Teardown runs `wrangler delete` and `wrangler containers delete` for the scratch app.
  - The tick line names the verdict, GO (Design A), FALLBACK-1 (B), FALLBACK-2 (C) or STOP, and the LIGHT size per Design item 4. STOP writes the ASKED line instead of ticking.

  -- Owns: .ci/rediacc_ci/spikes/do_policy_spike.py, .ci/rediacc_ci/tests/test_spikes_do_policy_spike.py, agent/plans/PLAN-executor-durable-object-policy.md (Spike record). Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_spikes_do_policy_spike.py` exits 0 (fake wrangler); `PYTHONPATH=.ci python3 -m rediacc_ci.spikes.do_policy_spike run --record .ci/cache/do-policy-spike/result.json` exits 0 with `"cross_answers": 0` and a `verdict` field; and after teardown `npx wrangler containers list` under the bench profile names no `rediacc-do-policy-spike` application.

### Account (private/account submodule PR first)

- [ ] A1 [account-issuer] `route` answers the tier, after S1.
  - `ExecutorIssuer.route(bearer)` answers `{ orgId, tier }`, where `tier` is `'high'` iff the primary live subscription plan is BUSINESS or ENTERPRISE, computed inside the existing entitlement read with no new query.
  - The refusal shape is unchanged.
  - Tests: a PROFESSIONAL org gets `standard`, a BUSINESS org and an ENTERPRISE org get `high`, a refused token still gets exactly `route-refused`, and no field beyond `orgId` and `tier` is answered.

  -- Owns: private/account/src/services/executor-issuer.service.ts (route only), workers/account/src/index.ts (the route signature only), private/account/tests/integration/executor-issuer-route.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-issuer-route.test.ts` exits 0 and `npm run typecheck` exits 0.

### Proxy Worker

- [ ] W1 [proxy] `OrgExecutor` with the rebuilt helpers (Design items 2 and 5), after S1.
  - Covers start, env, readiness, proxying with in-flight counting, the `sleepAfter = '2m'` alarm, image-drift restart, constructor recovery after a deploy, and the pin checks.
  - Tests against a fake `ctx.container` (start, running, monitor, destroy, getTcpPort, interceptOutboundHttp, images):
    - the env set is exactly the four names;
    - `start` is called with the image from `images.executor` and `enableInternet: true`;
    - the intercept is registered before `start`;
    - a `monitor()` rejection during readiness yields `EXECUTOR_START_FAILED` and a release;
    - the alarm does not destroy while a stream is open, and destroys and releases after 120 s idle;
    - an image change restarts only at zero in flight;
    - a constructor finding a running container re-acquires and re-attaches;
    - a second org's pin is refused;
    - an id mismatch is refused.

  -- Owns: workers/proxy/src/org-executor.ts, workers/proxy/src/__tests__/org-executor.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0 and `npx tsc --noEmit -p workers/proxy/tsconfig.json` exits 0.
- [ ] W2 [proxy] `ExecutorCapacity`, the coordinator (Design item 3), after S1.
  - Tests:
    - 25 distinct orgs acquire, and the 26th gets `full`;
    - a re-acquire by a held org does not count twice;
    - the 6th heavy acquire gets `heavy-full`, while a light one passes;
    - a lease not renewed for 180 s frees its slot at the next acquire and at the alarm;
    - `EXECUTOR_CAP = "2"` caps at 2;
    - `EXECUTOR_CAP = "40"` caps at 25;
    - a missing or garbage var caps at 25;
    - 50 concurrent acquires never admit more than the cap (input gate).

  -- Owns: workers/proxy/src/capacity.ts, workers/proxy/src/__tests__/capacity.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0.
- [ ] W3 [proxy] The egress for the S1 verdict, after S1 and W1.
  - **Design A:** `export class AccountEgress extends WorkerEntrypoint<Env, { orgId: string; containerId: string }>`, whose `fetch` calls today's `forwardAccountEgress` after the props and containerId checks (workers/proxy/src/egress.ts:116-130, moved from `ctx.params` to `this.ctx.props`).
  - **Design B or C:** the capability mint, the coordinator hash table, and the constant-time lookup. Under C, also the `/v1/egress/*` route.
  - Tests:
    - missing props or capability: 403 before any issuer call (the fake counts zero);
    - props naming another org's containerId: 403;
    - org A's capability presented for org B: 403;
    - a capability of a stopped container: 403;
    - the allowlist and the placeholder rule unchanged on the new path (the existing egress.test.ts cases reused).

  -- Owns: workers/proxy/src/egress.ts, workers/proxy/src/__tests__/egress.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0.
- [ ] W4 [proxy] Routing and sizing (Design items 2 and 4), after A1, W1, W2 and W3.
  - The Worker routes by `EXECUTOR_BACKEND`. `sizing.ts` holds the LIGHT literal from S1 and the rule. The capacity 503 comes from the coordinator answer, and `CAPACITY_ERROR` is deleted.
  - Tests:
    - `container` routes to `EXECUTOR` and `durable` routes to `ORG_EXECUTOR`, with never both in one version;
    - `tier: 'high'` gets `standard-1`;
    - a missing tier gets LIGHT;
    - an OOM flag within 7 days gets `standard-1`, and an 8-day-old flag gets LIGHT;
    - with heavy slots full, a high-tier org gets LIGHT and an OOM-flagged org gets 503 `EXECUTOR_CAPACITY` with `Retry-After: 30`;
    - the span carries `rediacc.proxy.size` and no org id.

  -- Owns: workers/proxy/src/index.ts, workers/proxy/src/sizing.ts, workers/proxy/src/__tests__/tenant-routing.test.ts, workers/proxy/src/__tests__/sizing.test.ts, workers/proxy/src/__tests__/index.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0, and `grep -n 'CAPACITY_ERROR' workers/proxy/src/index.ts` prints nothing.

### Configs, deploy, gates

- [ ] K1 [proxy-config] The template, the generator and the hand-written configs (Design item 2), after S1 and the commit of #9638ab6b.
  - The template gains the `OrgExecutor` entry with `images.executor`, the `ORG_EXECUTOR` and `EXECUTOR_CAPACITY` bindings, migration v2, and the three vars from `BACKEND_BY_TARGET`, `CAP_BY_TARGET` and `HEAVY_CAP_BY_TARGET`, all `container` and `"25"` and `"5"` at first. wrangler.bench.toml and wrangler.dev.toml are updated by hand.
  - `config_refusals` requires exactly the two entries (or exactly the one `OrgExecutor` entry once C1 lands), the two or three bindings, the migration list v1, v2 (and v3), `EXECUTOR_BACKEND` in {container, durable}, `EXECUTOR_CAP` at most 25, and no `max_instances` or `instance_type` on the durable entry.
  - proxy_wrangler_dev_e2e builds the matching dev config. If DU5 failed, it records the fake-container path.

  -- Owns: workers/proxy/wrangler*.toml, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/tests/test_deploy_proxy_configs.py, .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs --check` exits 0; `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_proxy_configs.py` exits 0, including planted refusals for `max_instances` on the durable entry, `EXECUTOR_CAP = "26"` and `EXECUTOR_BACKEND = "both"`; and `npm run check:ci-proxy-deploy-dry-run` exits 0.
- [ ] D1 [proxy-deploy] Forward-only detection and the record fields (Design item 6), after K1.
  - deploy_proxy compares the config's `[[migrations]]` with `git show <previous release tag>:<config>`. Bench uses its last recorded tag, kept in the record.
  - On a difference, the record says `forward-only` and the closing lines print no `wrangler rollback`.
  - The record gains `backend`, `migration_tag` and `cold_start_ms` (the first `/v1/ready` after the deploy).
  - The twin golden is re-recorded with `regolden --source port`.

  -- Owns: .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py, .ci/rediacc_ci/tests/goldens/twins/deploy.deploy-proxy.jsonl. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py` exits 0, including a v1-to-v2 case that writes `forward-only` and a v2-to-v2 case that writes the rollback command.
- [ ] G1 [gates] The cost guard for the policy (Design item 7), after K1 and W2.
  - Adds `HEAVY_BUDGET = 5`, `MAX_CONFIG_MONTHLY_USD = 300`, `MAX_TOTAL_MONTHLY_USD = 2100` and the price constants citing https://developers.cloudflare.com/containers/pricing/.
  - Adds the durable-entry rules, the cap-literal read of capacity.ts, the instance-literal allowlist, and the routed-backend count.
  - The selftest gains one control for each new rule, in both directions.

  -- Owns: .ci/scripts/quality/check_proxy_cost_guard.py, .ci/rediacc_ci/tests/test_check_proxy_cost_guard.py. Accept: `npm run check:ci-proxy-cost-guard` exits 0, and exits 1 on each of: a planted `max_instances` on the durable entry, `EXECUTOR_CAP = "26"`, `HARD_CAP = 30`, `instance: 'standard-2'`, a non-literal `instance`, an `OrgExecutor` with no `sleepAfter`, and a planted config total over $2,100.
- [ ] G2 [gates] The binding fence (Design item 8), after W3.
  - proxy-binding-wiring.test.ts refuses any wrangler config under workers/ that binds entrypoint `AccountEgress` or `ContainerProxy`, with a control that plants one.

  -- Owns: private/account/tests/integration/proxy-binding-wiring.test.ts. Accept: `cd private/account && npx vitest run tests/integration/proxy-binding-wiring.test.ts` exits 0, and fails on the planted binding.
- [ ] X1 [docs] docs/observability/signals/proxy.md, the deploy skill paragraph, and the relation line in PLAN-console-executor-multi-org.
  - proxy.md covers the two backends, `rediacc.proxy.size`, the `oom-heavy` outcome, the coordinator, and the forward-only phases.
  - The deploy skill paragraph covers the phase order and that Phase 1 and Phase 3 records are forward-only.
  - The PLAN-console-executor-multi-org relation line says that Design item 3's capacity, MU1 and MU2 are superseded for the durable backend.

  -- Owns: docs/observability/signals/proxy.md, .claude/skills/deploy/SKILL.md, agent/plans/PLAN-console-executor-multi-org.md (relation lines only). Accept: `npm run check:ci-prose-style` exits 0, and `grep -n 'PLAN-executor-durable-object-policy' agent/plans/PLAN-console-executor-multi-org.md docs/observability/signals/proxy.md` matches both.

### Cleanup (Phase 3)

- [ ] C1 [proxy] Retire the `Container` class, after L6.
  - Migration v3 `deleted_classes = ["ExecutorContainer"]`.
  - Remove the old entry, the `EXECUTOR` binding, `EXECUTOR_BACKEND` and its table, the `ContainerProxy` re-export, the static `outboundHandlers`, and `@cloudflare/containers` from package.json and the lockfile.
  - `config_refusals` and the cost guard require the one-entry shape.

  -- Owns: workers/proxy/src/index.ts, workers/proxy/package.json, workers/proxy/package-lock.json, workers/proxy/wrangler*.toml, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/tests/test_deploy_proxy_configs.py, .ci/scripts/quality/check_proxy_cost_guard.py, .ci/rediacc_ci/tests/test_check_proxy_cost_guard.py. Accept: `grep -rn '@cloudflare/containers\|ExecutorContainer\|ContainerProxy' workers/proxy/src workers/proxy/package.json workers/proxy/wrangler*.toml` prints nothing except the v1 and v3 migration lines; `cd workers/proxy && npm run test:unit` exits 0; `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs --check` and `npm run check:ci-proxy-cost-guard` exit 0.

### Live rollout

Each box records:

- the proxy version, before and after;
- the account version for A1's deploy;
- `D1: none (no migration)`;
- the smoke rc;
- the rollback command, or `forward-only`;
- the backend;
- the cold-start median;
- one org-A and one org-B `machine status` from the portal console (E1 of PLAN-console-executor-multi-org).

- [ ] L0 [live] Bench, Phase 1 then Phase 2, with drills.
  - Run deploy_bench (A1, no migration), then `deploy_proxy --target bench --record` with `container`, which is forward-only. Then flip bench to `durable` and deploy again.
  - Drills:
    - with `EXECUTOR_CAP = "2"` deployed for the drill, a third concurrent entitled org gets 503 `EXECUTOR_CAPACITY`, after which `"25"` is redeployed;
    - a BUSINESS-plan org starts `standard-1`, read from `rediacc.proxy.size` in `wrangler tail`;
    - org A idles 150 s and its slot frees (coordinator `count()` through `/v1/ready`);
    - a redeploy during an open stream keeps the stream and the egress working (DU2 live);
    - `wrangler rollback` to the Phase 1 version restores `container` routing, and a forward redeploy restores `durable`.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md (Live records). Accept: both bench rows have smoke rc 0; E1 against `https://bench.rediacc.com` exits 0 on `durable` with two org ids; and each drill's observed code is recorded.
- [ ] L1 [live] edge-eu, Phase 1 then Phase 2, before merge, through the deploy skill's local path. -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: both edge-eu rows have smoke rc 0, the Phase 1 row says forward-only, and E1 against `https://edge-eu.rediacc.com` exits 0 on `durable` with two org ids.
- [ ] L2 [live] edge-us, as L1. -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: as L1 for edge-us.
- [ ] L3 [live] edge-asia, as L1. -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: as L1 for edge-asia.
- [ ] L4 [live, post-merge] The first CD edge run after merge, with its three job records and E1 per edge region. -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: three deploy jobs succeed with smoke rc 0 and backend `durable`, and E1 exits 0 for each edge origin.
- [ ] L5 [live, post-merge] stable-eu, stable-us and stable-asia.
  - Phase 1 rides the merged release through promote-stable.
  - Phase 2 is the release that flips `BACKEND_BY_TARGET` for the three stable targets.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: each stable target has a forward-only Phase 1 row and a Phase 2 row with smoke rc 0, and E1 against `https://eu.rediacc.com`, `https://us.rediacc.com` and `https://asia.rediacc.com` exits 0 on `durable` with two org ids each.
- [ ] L6 [ops, post-merge] 14 days of observation on all six targets.
  - A Grafana query gives, per target, the counts of `rediacc.proxy.outcome` in {capacity, start-failed, oom-heavy}, the split of `rediacc.proxy.size`, and the cold-start median.
  - The container line of `cf_usage_report` gives the spend.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: the Live records carry the 14-day numbers for all six targets, and any non-zero capacity count carries an ASKED line on the cap.
- [ ] L7 [live, post-merge] Phase 3 per target, after C1.
  - Deploy the C1 release (forward-only) to bench, the three edge targets and the three stable targets.
  - Then run `npx wrangler containers delete <old application id>` per target, with the id read from `wrangler containers list` and recorded by its first 8 characters.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: seven forward-only rows with smoke rc 0, and `npx wrangler containers list` per account names no `ExecutorContainer` application.

### Deadline

- [ ] DL1 [deadline] All seven targets route `durable` and run without the `Container` class by 2026-12-15, two weeks before the 2026-12-31 freeze.
  - Checkpoints: S1 verdict by 2026-11-02; L0 to L3 by 2026-11-16; L5 by 2026-11-30; L7 by 2026-12-15.
  - Escalation: a missed checkpoint, a STOP verdict, or a policy still marked public beta on 2026-12-01 writes an ASKED line with two options:
    - (a) proceed on the beta;
    - (b) stay on the frozen class past 2026-12-31, which keeps running per Context item 1, with a re-check date.

  -- Owns: agent/plans/PLAN-executor-durable-object-policy.md. Accept: on or before 2026-12-15, L7 is ticked, or an ASKED line dated before 2026-12-31 records the operator's choice.

### Order and parallel writers

- Wave 0: S1. Nothing else starts before its verdict.
- Wave 1: A1; W1; W2; K1, once #9638ab6b is committed.
- Wave 2: W3 after W1; D1 after K1; G1 after K1 and W2.
- Wave 3: W4 after A1, W1, W2 and W3; G2 after W3; X1.
- Wave 4: L0 to L3 before merge; L4 to L6 after merge.
- Wave 5: C1 after L6; L7 after C1; DL1 closes.
- workers/proxy/src/index.ts is written by W4 and then C1. egress.ts is written by W3 alone. The configs, proxy_configs.py and the cost guard are written by K1, G1 and C1 in that order. None of these starts while a PLAN-console-executor-multi-org W box or #9638ab6b holds the file.

## Spike record

| Item | Observed | Verdict |
|---|---|---|

## Live records

| Target | Phase | Proxy version (previous, new) | Account version (A1) | D1 | Smoke rc | Rollback | Backend | Cold start median | Org A run | Org B run |
|---|---|---|---|---|---|---|---|---|---|---|

## Decisions taken as defaults (open to operator veto)

1. **A new class and binding beside the old, routed by a per-target var.** The guide demands a new class and namespace. A var lets each target flip on its own (bench, then edge, then stable) and keeps one `wrangler rollback` inside the window where no class lifecycle changes.
2. **The cap lives in one coordinator Durable Object per target, with expiring leases.** A lease that expires on its own needs no cleanup path after a crash or a deploy. One instance per target serves at most 25 holders, which is far below a Durable Object's throughput. A coordinator failure refuses rather than starting uncounted.
3. **A heavy sub-cap of 5 per target.** It bounds the worst case at about $281 per target pinned awake. A high-tier org that finds the heavy slots full runs LIGHT, its size today. An org that has run out of memory waits instead.
4. **A dollar ceiling in the cost guard** ($300 per config and $2,100 in total), because the cap now counts instances of two prices.
5. **LIGHT is a basic-equivalent custom size unless S1 shows `lite` suffices.** This departs from the brief's "lite for light orgs" on the strength of the 2026-10-24 measurement (Context item 7). An executor that runs out of memory on every first `repo up` would cost more in failed commands than the $5 a month per awake org saved.
6. **Heavy means BUSINESS or ENTERPRISE, or an OOM exit in the last 7 days.** The account Worker can read the plan, and only the proxy can see an OOM. No per-org manual override exists. One can be added through a root action if L6 shows the need.
7. **Phase 3 waits 14 days on stable and finishes by 2026-12-15.** This trades a longer rollback window against a two-week margin before the freeze.

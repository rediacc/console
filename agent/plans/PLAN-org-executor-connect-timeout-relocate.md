# PLAN: an executor connect that never completes gets a named, retryable error, and an org whose executor keeps hitting it moves to a new Durable Object id

Status: executing
Owner: d778be9d
Updated: 2026-10-28
Depends-On: PLAN-executor-durable-object-policy.md#L0, PLAN-executor-durable-object-policy.md#L2 -- relocation is built on the `durable` backend only. L0 puts bench on `durable`, which E9 (the Live-Proof run) needs. L2 puts edge-us on `durable`, which the E10 extra accept needs. The code boxes E1-E8 need only that plan's code boxes, and those are all ticked (S1, A1, W1-W4, K1, D1, G1, G2, X1)
Priority: P1 -- an org whose executor container lands where outbound TCP to its machine is dropped stays broken for good, and the user sees only a bare ssh2 timeout. Org B on edge-us has been in that state since 2026-10-28T06:24Z (worklist #a150016d)
Concurrency: exclusive -- E5-E7 rewrite workers/proxy/src/index.ts, org-executor.ts, capacity.ts and egress.ts. PLAN-executor-durable-object-policy is exclusive and owns workers/proxy/src/** until its C1 ticks, so a writer here runs only while no writer of that plan holds those files. E1-E3 (packages/cli) and E4 (private/account, workers/account) can run in parallel with each other and with E5. E6 follows E5, E7 follows E4 and E6, E8 follows E7, E9 follows E1-E8 and that plan's L0, and E10 follows E9 and that plan's L2
Owns: packages/cli/src/remote/sftp/connect-error.ts (new), packages/cli/src/remote/sftp/client.ts, packages/cli/src/remote/__tests__/ssh-connect-error.test.ts (new), packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/executor/__tests__/local-executor-connect-error.test.ts (new), packages/cli/src/utils/errors.ts, packages/cli/src/services/serve/egress-report.ts (new), packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/deps.ts, packages/cli/src/services/serve/__tests__/egress-report.test.ts (new), private/account (the gitlink bump only), private/account/drizzle/0068_executor_placement.sql (new), private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/src/services/executor-issuer.service.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/executor-issuer-route.test.ts, private/account/tests/integration/executor-issuer-relocate.test.ts (new), private/account/e2e/tests/27-console/27-92-live-egress-relocation.test.ts (new), workers/account/src/index.ts, workers/proxy/src/placement.ts (new), workers/proxy/src/span.ts (new), workers/proxy/src/index.ts, workers/proxy/src/org-executor.ts, workers/proxy/src/capacity.ts, workers/proxy/src/egress.ts, workers/proxy/src/issued-token.ts, workers/proxy/src/__tests__/placement.test.ts (new), workers/proxy/src/__tests__/org-executor.test.ts, workers/proxy/src/__tests__/capacity.test.ts, workers/proxy/src/__tests__/egress.test.ts, workers/proxy/src/__tests__/tenant-routing.test.ts, workers/proxy/src/__tests__/index.test.ts, docs/observability/signals/proxy.md, agent/plans/PLAN-org-executor-connect-timeout-relocate.md
Live-Proof: bench, hostinger -- the proxy surface's live target is bench (.ci/config/proof-tiers.json, surface `proxy`, live ["bench"]). E9 drives the named error and the relocation on bench through a machine entry whose SYNs go unanswered. The edge-us org B run (E10) is an extra accept only, because edge is not a live-proof target (operator ruling 2026-10-27). packages/cli/src/remote/sftp/connect-error.ts and client.ts are the cli-remote surface, whose only live target is hostinger, so renet-live on hostinger covers them.
First-Seen: 2026-10-28
Worklist: #a150016d (finding), PR-TASK 9f92c43e

## Problem

**The evidence.** On edge-us (proxy Worker `edge-rediacc-proxy-us`, workers/proxy), org B's executor container never sends a TCP SYN to its machine (hostinger 72.61.137.225:22).
- Six live console runs (private/account/e2e/tests/27-console/27-90-live-executor.test.ts and 27-91-live-two-orgs.test.ts) fail with `SSH connection error: Timed out while waiting for handshake` after 10 s.
- A hostinger tcpdump shows zero SYNs for those runs.
- Org A, and an org C provisioned fresh for the check, pass on the same edge-us proxy in the same minute (2026-10-28T06:24-06:26Z). Their SYNs arrive from Cloudflare 104.28.x. All three orgs share the machine config, the plan (PROFESSIONAL) and the size (light).
- Both orgs pass on edge-eu and edge-asia.
- These were ruled out: the address, the port, IPv4 against IPv6, the tier, the host firewall (ufw inactive, no fail2ban), test ordering, and a single bad container instance (five restarts).
- `wrangler tail` shows org B's container handling `/v1/command`, and its session, executor-grant, executor-token and config fetch all answer 200.

So the container's account egress works, and only its outbound TCP to the machine is dropped. The drop happens upstream of the host.

**Why it never recovers (verified in repo).**
- The Durable Object name is the org id alone on both backends: `getContainer(env.EXECUTOR, tenant.orgId)` (workers/proxy/src/index.ts:263) and `namespace.idFromName(tenant.orgId)` (workers/proxy/src/index.ts:317).
- Both pins refuse any other id (workers/proxy/src/index.ts:164, workers/proxy/src/org-executor.ts:267).
- Both egress identity checks require `containerId === idFromName(orgId)` (workers/proxy/src/egress.ts:137, workers/proxy/src/egress.ts:160).
- No code path ever gives an org a different object. Whatever placement the object (and so its container) has, the org keeps.

**The error is anonymous (verified in repo).**
- `SFTPClient.connect` sets `readyTimeout` to `DEFAULTS.SSH.READY_TIMEOUT`, which is 10000 (packages/cli/src/remote/sftp/client.ts:85, packages/shared/src/config/defaults.ts:42).
- It turns every ssh2 `error` into `SSH connection error: <message>` (packages/cli/src/remote/sftp/client.ts:116-122), whatever the cause.
- ssh2 1.17.0 tells the causes apart, and the CLI throws that information away:
  - A connect that never completes and a peer that never sends a banner both give `Timed out while waiting for handshake` with `level = 'client-timeout'` (ssh2 `lib/client.js`, lines 1112-1118 of the installed copy).
  - Only the first lacks the client `connect` event, which ssh2 emits once the TCP socket connects (ssh2 `lib/client.js`, line 767).
  - A refused connect is `level = 'client-socket'` with `code = 'ECONNREFUSED'` (ssh2 `lib/client.js`, lines 801-806).
  - An authentication failure is `client-authentication` (ssh2 `lib/client.js`, lines 404 and 469).
- `LocalExecutorService.execute` then flattens the throw to `{ success: false, exitCode: 1, error }` with no `errorCode` (packages/cli/src/services/executor/local-executor.ts:593-601).
- A raw throw falls to `normalizeError`'s GENERAL_ERROR fallback (packages/cli/src/utils/errors.ts:249-255). That is the GENERAL_ERROR the console shows.

**Which backend org B is on (verified in repo, check on edge first).** The brief places the id at workers/proxy/src/index.ts:317, the `durable` path. However, every generated config routes `container`:
- `BACKEND_BY_TARGET` is `container` for all eight targets (.ci/rediacc_ci/deploy/proxy_configs.py:69-71).
- workers/proxy/wrangler.edge-us.toml:18 says `EXECUTOR_BACKEND = "container"`.

Unless a hand deploy flipped edge-us, org B runs on the legacy `ExecutorContainer` (workers/proxy/src/index.ts:132-179, default scheduling, `max_instances = 25`), and its id comes from workers/proxy/src/index.ts:263. `npx wrangler versions view` on edge-us settles this before E10. The legacy class retires at PLAN-executor-durable-object-policy C1, and Cloudflare freezes it after 2026-12-31. This plan builds relocation on `durable` only and keeps the legacy backend as it is (Design 7).

**Claims and where they stand.**

Verified in repo, with the citations above:
- the id derivation and the identity checks;
- the 10 s readyTimeout;
- the ssh2 error levels and the `connect` event;
- the flattening to exit 1;
- the lease keyed by org id (workers/proxy/src/capacity.ts:74 and 99-104);
- the OOM flags as a per-org value the Worker reads (workers/proxy/src/org-executor.ts:40-42, 274-281; workers/proxy/src/index.ts:286 and 299-306);
- the route already reading the `organizations` row for each request (private/account/src/services/executor-issuer.service.ts:130-135).

Platform assumptions, to verify on bench or edge:
- **(P-a)** A Durable Object is placed near the first request that creates it and is never moved afterwards.
- **(P-b)** `locationHint` on `namespace.get(id, { locationHint })` is honoured only when that call creates the object. It is a hint, not a guarantee.
- **(P-c)** `jurisdiction` (`namespace.jurisdiction('eu' | 'fedramp')`) restricts where an object may live. It offers no US or Asia sub-placement, so it has no use here.
- **(P-d)** Under `durable_object` scheduling, a container runs with or near its object, and its outbound path (host and egress address) is fixed for the object's life. The five restarts that did not help are consistent with this, but they do not prove it.
- **(P-e)** A new object id, created by the same proxy Worker from the same caller, lands on a different container host or egress path often enough to escape a bad one. Org A and org C passing in the same minute from the same runner support this. Only E10 on org B can prove it, because bench cannot reproduce the bad placement.
- **(P-f)** An object's own container can reach that object by RPC through the outbound intercept (egress entrypoint, then `ORG_EXECUTOR.get(...)`) while a `fetch` on the object is still streaming. E9 exercises this.
- **(P-g)** On Cloudflare container egress, TCP to 192.0.2.10:22 (RFC 5737 TEST-NET-1) gets no answer at all, rather than an ICMP error or an RST. E9 checks this first and falls back to an iptables DROP.

## Design

1. **A named connect error in the CLI.**
   - New module packages/cli/src/remote/sftp/connect-error.ts.
   - `classifySshConnectFailure({ level, code, tcpConnected })` answers one of these kinds:
     - `unreachable`: `client-timeout` with no client `connect` event yet, or `client-socket` with `ETIMEDOUT`;
     - `handshake-timeout`: `client-timeout` after `connect`;
     - `refused`: `client-socket` with `ECONNREFUSED`;
     - `auth`: `client-authentication`;
     - `other`.
   - `SshConnectError extends Error` (`name = 'SshConnectError'`) carries `kind`, `host`, `port`, `timeoutMs`, `errorCode`, `exitCode` and `retryable`:
     - `unreachable` gives `EGRESS_UNREACHABLE`, exit `EXIT_CODES.NETWORK_ERROR` (6), retryable.
     - `refused` gives `SSH_REFUSED`, exit 6, retryable.
     - `handshake-timeout` gives `SSH_HANDSHAKE_TIMEOUT`, exit 6, retryable.
     - `auth` gives `SSH_AUTH_FAILED`, exit 1, not retryable.
     - `other` keeps today's message with exit 1 and no code.
   - The `unreachable` message names the cause: `<host>:<port> never answered the TCP connection attempt within 10 s; the address is valid but no reply came back. The machine may be down, a firewall may be dropping the traffic, or the executor's network path to it is blocked.`
   - `SFTPClient.connect` (packages/cli/src/remote/sftp/client.ts:73-130) records `tcpConnected` on the client `connect` event and rejects with `SshConnectError`. The host-key mismatch path (packages/cli/src/remote/sftp/client.ts:117-119) stays first and unchanged.
   - The constructor takes an optional client factory (default `new SSHClient()`), so a test can plant an ssh2 client.

2. **The error reaches the envelope and the console with its name.**
   - `LocalExecutorService.execute` catches `SshConnectError` (packages/cli/src/services/executor/local-executor.ts:593-601) and returns `{ success: false, exitCode, error: message, errorCode, errorGuidance, durationMs }`.
   - `ExecuteResult` already has `errorCode` and `errorGuidance` (packages/cli/src/services/executor/types.ts:161-172), and serve prefers a failed `lastResult` over a reconstructed one (packages/cli/src/services/serve/command-dispatch.ts:484). So the result line `rdc serve` writes (packages/cli/src/services/serve/server.ts:316-318) carries the code to the console unchanged.
   - `normalizeError` gets a name-keyed entry for `SshConnectError`, following the `REMOTE_CONFIG_ERRORS` precedent (packages/cli/src/utils/errors.ts:166-198). A laptop path that throws it raw then exits 6 with `NETWORK_ERROR` and `retryable: true`, not GENERAL_ERROR.

3. **The executor reports the failure through the one path that works.**
   - In container mode, when a result carries `errorCode === 'EGRESS_UNREACHABLE'`, server.ts awaits `deps.reportEgressUnreachable()` before writing the result line.
   - The report lives in packages/cli/src/services/serve/egress-report.ts. It is a bodiless `POST http://account.internal/executor/v1/egress-unreachable` with a 5 s deadline that never throws, and it answers `{ count, threshold, relocated } | undefined`.
   - `account.internal` is the egress the container already uses successfully on org B. The report sends no host, address or tenant data, because the identity comes from the intercept's props.
   - The guidance on the result line comes from the answer:
     - relocated: `This org's executor has moved to a new instance. Retry the command now.`
     - counted: `Attempt <count> of <threshold> before the executor moves to a new instance. Retry the command.`
     - no answer: `Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.`
   - `refused`, `auth`, `handshake-timeout` and `other` are never reported.

4. **The executor name carries a placement number stored in D1.**
   - Forward-only migration private/account/drizzle/0068_executor_placement.sql (0067 is the latest) adds two columns to `organizations` (private/account/src/db/schema.ts:394-410):
     - `executor_placement integer NOT NULL DEFAULT 0`;
     - `executor_relocated_at text`.
   - `ExecutorIssuerService.route` adds `executorPlacement` to the select it already runs (private/account/src/services/executor-issuer.service.ts:130-135) and answers `{ orgId, tier, placement }`. This costs no extra query and no extra hop on the hot path.
   - The new RPC `relocate(orgId, fromPlacement)` is exposed on the `ExecutorIssuer` entrypoint (workers/account/src/index.ts:86-99) through private/account/src/entry/cloudflare.ts. It runs one compare-and-set:
     `UPDATE organizations SET executor_placement = executor_placement + 1, executor_relocated_at = <now> WHERE id = ? AND executor_placement = ? AND (executor_relocated_at IS NULL OR executor_relocated_at <= <now - RELOCATE_MIN_INTERVAL>)`
   - It answers one of:
     - `{ ok: true, placement }`;
     - `{ ok: false, reason: 'stale', placement }` when another caller already moved the org;
     - `{ ok: false, reason: 'budget', placement }` within 30 minutes of the last move;
     - `{ ok: false, reason: 'unknown-org' }`.
   - D1 is chosen over the coordinator because D1 is the org's system of record, survives a coordinator table-shape bump (workers/proxy/src/capacity.ts:17-18), adds nothing to the request path, and can be read or reset by the operator with `wrangler d1 execute`.
   - workers/proxy/src/placement.ts owns:
     - `executorName(orgId, placement)`, which is `` `${orgId}:p${placement}` `` for every placement, 0 included. This is a clean break, and it discards nothing live because no target routes `durable` yet;
     - `placementOf(value)`: a non-negative safe integer, else undefined;
     - `UNREACHABLE_THRESHOLD = 3`;
     - `UNREACHABLE_WINDOW_MS = 600_000`;
     - `unreachableRecent(at, now)`.
   - `resolveTenant` (workers/proxy/src/index.ts:207-224) refuses with `refused:route-placement-missing` (503, unavailable) when the route gives no valid placement. It never guesses 0, because 0 is the possibly broken object.
   - The word is "placement", not "generation", because `OrgExecutor.generation` already names the per-start counter (workers/proxy/src/org-executor.ts:206).

5. **OrgExecutor counts reports, relocates and retires.**
   - `pin(orgId, placement, size)` checks `ctx.id.equals(idFromName(executorName(orgId, placement)))` in place of workers/proxy/src/org-executor.ts:267.
   - `ORG_KEY` stores `{ orgId, placement }`.
   - `ExecutorRecord` and `ExecutorEgressProps` gain `placement`. `recover` (workers/proxy/src/org-executor.ts:599-631) destroys a running container whose record lacks it, as `unrecorded`.
   - New RPC `recordEgressUnreachable(orgId, placement)`:
     - It refuses a mismatched org or placement.
     - It appends `Date.now()` to the `egressUnreachable` storage list, prunes entries older than `UNREACHABLE_WINDOW_MS`, and writes `egressUnreachableAt`.
     - Below `UNREACHABLE_THRESHOLD` it answers `{ count, threshold, relocated: false }`.
     - At the threshold it calls `env.ISSUER.relocate(orgId, placement)`, bounded like the coordinator calls (workers/proxy/src/org-executor.ts:132-142).
     - On `ok` or `stale` it writes `retired = { to }`, sets `draining`, and answers `relocated: true`.
     - On `budget` or a failure it logs and answers `relocated: false`, and the org stays put.
   - A retired object behaves as follows:
     - `pin` refuses with the new code `EXECUTOR_RELOCATED`, so `ExecutorRefusalCode` (workers/proxy/src/org-executor.ts:67) gains it.
     - `holdLease` never re-acquires, so a retired object cannot take a slot back.
     - When nothing is in flight, the existing drain (workers/proxy/src/org-executor.ts:380-390) stops the container and releases the lease. The request whose report caused the move ends with its named result line before the container goes.
   - The old object never touches the new id. Under (P-a), the first `get` of the new id must come from the Worker, so the new object is placed the way an object is placed for a fresh org.
   - `PinAnswer`'s ok branch gains `egressUnreachableRecent: boolean`, so the Worker needs no extra RPC for the outcome. The OOM flags stay their own reads (workers/proxy/src/org-executor.ts:274-281).
   - `OrgExecutorEnv` (workers/proxy/src/org-executor.ts:51-56) gains `ISSUER`. The Env comment at workers/proxy/src/index.ts:72-74 is updated, because the issuer is now also called by `relocate`.

6. **Leases are keyed by executor name, not by org.**
   - `ExecutorCapacity.acquire/renew/release` take the executor name (workers/proxy/src/capacity.ts:81-131).
   - The table becomes `leases (executor TEXT PRIMARY KEY, size, expires_at)` under `CAPACITY_NAME = 'capacity:v2'`. The suffix exists to version the shape (workers/proxy/src/capacity.ts:17-18).
   - A late `release` from the retired object then cannot delete the new object's slot, as it could with the org-keyed row (workers/proxy/src/capacity.ts:128-131). Two placements of one org briefly count as two, which errs on the safe side of the cap.
   - `HARD_CAP` and `HARD_HEAVY_CAP` stay the literals the cost guard reads (workers/proxy/src/capacity.ts:12-14).

7. **The Worker routes by placement and names the outcomes.**
   - `viaOrgExecutor` (workers/proxy/src/index.ts:309-332) derives the stub from `executorName(tenant.orgId, tenant.placement)` and pins with the placement.
   - On `EXECUTOR_RELOCATED` it calls `resolveTenant` once more, and retries once if the placement went up. Otherwise it answers 503 `EXECUTOR_START_FAILED`.
   - A forwarded request whose pin answer says `egressUnreachableRecent` gets the outcome `egress-unreachable` in place of `forwarded`, the way `oom-heavy` does (workers/proxy/src/index.ts:327-330).
   - `AccountEgress.fetch` (workers/proxy/src/egress.ts:151-165):
     - It checks `containerId === ORG_EXECUTOR.idFromName(executorName(orgId, placement)).toString()`.
     - It answers `POST /executor/v1/egress-unreachable` (empty query) itself, before `forwardAccountEgress`, by calling `recordEgressUnreachable` on its own object.
     - It never forwards to ACCOUNT and never calls the issuer.
     - Its span gets `rediacc.proxy.outcome` set to `egress-unreachable`, or to `relocated` when the report triggered the move, through `activeSpan`, which moves to the new src/span.ts.
   - The legacy `accountEgress` (workers/proxy/src/egress.ts:125-141) is unchanged. It refuses the report as `route-not-allowed`, the executor falls back to its no-answer guidance, and the named error still reaches the user.

8. **Signals.**
   - docs/observability/signals/proxy.md, outcome row (line 35) and the durable section (line 88):
     - `egress-unreachable`;
     - `relocated`;
     - `refused:route-placement-missing`.
   - Log lines carry the placement number and the count, never an org id. For example: `proxy: org executor egress unreachable 2/3 at p0`, `proxy: org executor relocated p0->p1`, `proxy: org executor relocate refused: budget`.

## Alternatives rejected

- **`locationHint` alone, or a hint per region beside the placement.** The hint applies only when the call creates the object (P-b), so it cannot move org B's existing object. Paired with a new id, it would pull the org away from the caller and add latency, and nothing in the evidence shows the whole region is bad: org A and org C pass from the same region. It is held back until E10 shows that a new id alone does not escape (P-e).
- **`jurisdiction`.** It only fences objects into `eu` or `fedramp` (P-c), so it has no effect inside us or asia.
- **The placement number in the coordinator.** The coordinator would join every request path as a per-target singleton. That changes the deliberate fail-open of a running container on coordinator trouble (workers/proxy/src/org-executor.ts:429-432). A future table-shape bump (`capacity:v2` here) would also reset every org to its first object.
- **A forward-pointer chain in retired objects, with a "home" object at the bare org id.** It works without the account change. However, each cold isolate pays an extra RPC per org on a miss, the home object needs a second role, and an operator has nothing to read or reset.
- **Scanning the NDJSON stream for the result line in the Durable Object.** It breaks the rule that routing never reads a command's output (workers/proxy/src/index.ts:13-16). It also misfires on any renet event text that contains the code.
- **A Worker-side TCP probe of the target (`cloudflare:sockets` `connect`) to prove the target valid before relocating.** Whether the intercept handler shares the container's egress path is unknown, so the probe may fail for the same reason the container does. It would also hand the container a TCP-connect primitive aimed wherever the container says. Under this plan a down machine costs at most one cold start per 30 minutes for its own org.
- **Relocating on every single failure, or raising readyTimeout.** One failure is not a pattern, and churning objects throws away the warm pool for nothing. A longer timeout only delays the same SYN that never leaves.
- **Relocation on the legacy `ExecutorContainer`.** That class is frozen after 2026-12-31 and retires at PLAN-executor-durable-object-policy C1. Building a second relocation path into it would be a compatibility shim.

## Tasks

- [x] E1 [writer] The connect classifier (Design 1). Add packages/cli/src/remote/sftp/connect-error.ts and wire `SFTPClient.connect` to record `tcpConnected` and reject with `SshConnectError`, adding the optional client factory. Tests:
  - The pure classifier covers each level and code pair, `client-timeout` both with and without `connect`.
  - A planted ssh2 client that emits `error` with `level: 'client-timeout'` and no `connect` gives `kind: 'unreachable'` and `errorCode: 'EGRESS_UNREACHABLE'`.
  - The same client with `connect` first gives `handshake-timeout`.
  - A real connect to a closed loopback port gives `refused`.
  - A real loopback listener that accepts and never sends a banner, with `timeout: 300`, gives `handshake-timeout`.
  - A mutant classifier that ignores `tcpConnected` turns the handshake case red.
    (ticked) 2026-10-28T07:32:15Z by d778be9d: 2026-10-28 by d778be9d: commit:f49b3faa3; E1 ssh-connect-error and host-key-mismatch vitest rc=0 (22), classifier mutant red. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Owns: packages/cli/src/remote/sftp/connect-error.ts, packages/cli/src/remote/sftp/client.ts, packages/cli/src/remote/__tests__/ssh-connect-error.test.ts. Accept: `cd packages/cli && npx vitest run src/remote/__tests__/ssh-connect-error.test.ts src/remote/__tests__/host-key-mismatch.test.ts` rc 0.
- [x] E2 [writer] The envelope (Design 2). Make the `local-executor.ts:593-601` catch return `exitCode`, `errorCode` and `errorGuidance` from `SshConnectError`, and add its name-keyed entry to `normalizeError`. Tests:
  - With `machineConnections.acquireFor` stubbed to reject with an `unreachable` `SshConnectError`, `execute` answers `exitCode: 6, errorCode: 'EGRESS_UNREACHABLE'`, with the message naming host and port.
  - A `refused` error answers `SSH_REFUSED`.
  - A plain `Error` still answers exit 1 with no code.
  - `normalizeError` maps the raw throw to `NETWORK_ERROR`, `retryable: true`.
    (ticked) 2026-10-28T07:15:13Z by d778be9d: 2026-10-28 by d778be9d: commit:f49b3faa3; cd packages/cli && npx vitest run src/services/executor/__tests__/local-executor-connect-error.test.ts rc=0

  Owns: packages/cli/src/services/executor/local-executor.ts, packages/cli/src/utils/errors.ts, packages/cli/src/services/executor/__tests__/local-executor-connect-error.test.ts. Accept: `cd packages/cli && npx vitest run src/services/executor/__tests__/local-executor-connect-error.test.ts` rc 0.
- [x] E3 [writer] The report (Design 3). Add egress-report.ts and the `reportEgressUnreachable` dep in deps.ts (container mode only), and have server.ts await it before the result line and set `errorGuidance` from its answer. Tests, with a fake fetch:
  - An `EGRESS_UNREACHABLE` result sends exactly one bodiless POST to `http://account.internal/executor/v1/egress-unreachable`, and the result line carries the relocated, counted or no-answer guidance for each of the three answers.
  - A result with `SSH_REFUSED`, `SSH_AUTH_FAILED` or no code sends nothing.
  - A report that hangs past 5 s still writes the result line.
  - A mutant that reports on any failed result turns the refused case red.
    (ticked) 2026-10-28T07:15:15Z by d778be9d: 2026-10-28 by d778be9d: commit:f49b3faa3; cd packages/cli && npx vitest run src/services/serve/__tests__/egress-report.test.ts src/services/serve/__tests__/container-config.test.ts rc=0 (29); report-filter mutant turned the three sends-nothing cases red

  Owns: packages/cli/src/services/serve/egress-report.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/deps.ts, packages/cli/src/services/serve/__tests__/egress-report.test.ts. Accept: `cd packages/cli && npx vitest run src/services/serve/__tests__/egress-report.test.ts src/services/serve/__tests__/container-config.test.ts` rc 0.
- [x] E4 [writer] The account side (Design 4). Make these changes:
  - migration 0068 and its `_journal.json` entry;
  - the schema columns;
  - `route` answering `placement`;
  - `relocate` with the compare-and-set and `RELOCATE_MIN_INTERVAL_MS = 1_800_000`;
  - `relocateExecutorPlacement` in entry/cloudflare.ts;
  - the `relocate` method and its doc sentence on the `ExecutorIssuer` entrypoint.
    (ticked) 2026-10-28T07:32:22Z by d778be9d: 2026-10-28 by d778be9d: commit:be5d60799; E4 account f195a55 and efb5eaf; executor-issuer-route, executor-issuer-relocate, executor-multi-org, executor-issuer vitest rc=0. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Commit in private/account and bump the pointer. Tests:
  - `route` answers `placement: 0` for a fresh org and 1 after one `relocate`.
  - `relocate(org, 0)` answers `{ ok: true, placement: 1 }`.
  - A second `relocate(org, 0)` answers `stale` with 1.
  - `relocate(org, 1)` within 30 minutes answers `budget`, and after a clock advance answers `ok` with 2.
  - An unknown org answers `unknown-org`.
  - A mutant without the `executor_placement = ?` guard turns the stale case red.

  Owns: private/account, private/account/drizzle/0068_executor_placement.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/src/services/executor-issuer.service.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/executor-issuer-route.test.ts, private/account/tests/integration/executor-issuer-relocate.test.ts, workers/account/src/index.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-issuer-route.test.ts tests/integration/executor-issuer-relocate.test.ts tests/integration/executor-multi-org.test.ts` rc 0.
- [x] E5 [writer] Placement helpers and lease keys (Design 4 proxy half, Design 6). Add src/placement.ts. Rekey `ExecutorCapacity` by executor name under `capacity:v2`, and keep the cap and sub-cap semantics. Tests:
  - placement.test.ts: `executorName('org-a', 0)` is `org-a:p0`; `placementOf` refuses -1, 1.5, `'1'` and undefined.
  - capacity.test.ts (existing cases rekeyed): `org-a:p0` and `org-a:p1` hold two slots; `release('org-a:p0')` leaves `org-a:p1` held.
  - A mutant that keys by the org prefix turns the second case red.
    (ticked) 2026-10-28T07:32:29Z by d778be9d: 2026-10-28 by d778be9d: commit:872e964a7; E5 placement and capacity vitest rc=0 (45), test:unit rc=0, prefix-key mutant red. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Owns: workers/proxy/src/placement.ts, workers/proxy/src/capacity.ts, workers/proxy/src/__tests__/placement.test.ts, workers/proxy/src/__tests__/capacity.test.ts. Accept: `cd workers/proxy && npm run typecheck && npx vitest run src/__tests__/placement.test.ts src/__tests__/capacity.test.ts` rc 0.
- [x] E6 [writer] OrgExecutor relocation (Design 5), after E5. Make these changes:
  - `pin(orgId, placement, size)` with the name check;
  - `placement` in the record, the props and `ORG_KEY`;
  - `recordEgressUnreachable`;
  - the `retired` state with the `EXECUTOR_RELOCATED` refusal, `holdLease` refusing to re-acquire, and the drain releasing `executorName(...)`;
  - `egressUnreachableRecent` on the pin answer;
  - `ISSUER` on the env.
    (ticked) 2026-10-28T07:32:33Z by d778be9d: 2026-10-28 by d778be9d: commit:76ab29b11; E6 org-executor vitest rc=0 (53), test:unit 244 rc=0, threshold-4 mutant red. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Tests in the existing harness (org-executor.test.ts), adding a `FakeIssuer` whose `relocate` answers are set per test:
  - Three reports within 10 minutes call `relocate('org-a', 0)` exactly once. The next `pin('org-a', 0, 'light')` answers `EXECUTOR_RELOCATED`. With a stream open, the container is destroyed only after it closes, and `release('org-a:p0')` is recorded.
  - Two reports, then a third 11 minutes later, never call `relocate`.
  - A `budget` answer leaves the object serving, and pin answers ok with `egressUnreachableRecent: true`.
  - A report naming another placement is refused.
  - A retired object whose renew answers `not-held` does not call `acquire`.
  - A mutant threshold of 4 turns the first case red.

  Owns: workers/proxy/src/org-executor.ts, workers/proxy/src/__tests__/org-executor.test.ts. Accept: `cd workers/proxy && npm run typecheck && npx vitest run src/__tests__/org-executor.test.ts` rc 0.
- [x] E7 [writer] Routing, egress route and outcomes (Design 7), after E4 and E6. Make these changes:
  - `relocate` on `ExecutorIssuerRpc` (workers/proxy/src/issued-token.ts:20);
  - src/span.ts;
  - `resolveTenant` reading `placement`;
  - `viaOrgExecutor` with the once-only re-route;
  - the `egress-unreachable` outcome on forward;
  - the `AccountEgress` placement check and local report route with its span outcome.
    (ticked) 2026-10-28T07:32:36Z by d778be9d: 2026-10-28 by d778be9d: commit:be5d60799; E7 npm run typecheck and test:unit rc=0 (261), executorName mutant fails the re-route case. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Tests:
  - tenant-routing.test.ts: a route answering `placement: 1` reaches the stub named `org-a:p1`.
  - index.test.ts: a stub answering `EXECUTOR_RELOCATED` makes the Worker call `route` again, and the next pin reaches `org-a:p2` (the "next request reaches a new id" case). A missing placement answers 503 with `refused:route-placement-missing`.
  - egress.test.ts:
    - The report route calls `recordEgressUnreachable` once, makes zero ACCOUNT and zero ISSUER calls, and records `egress-unreachable` (or `relocated`) on the span.
    - Props whose placement does not match `containerId` answer 403 `container-org-mismatch`.
    - The legacy `accountEgress` still answers the route 403 `route-not-allowed`.
  - A mutant `executorName` that drops the placement turns the re-route case red.

  Owns: workers/proxy/src/index.ts, workers/proxy/src/egress.ts, workers/proxy/src/issued-token.ts, workers/proxy/src/span.ts, workers/proxy/src/__tests__/tenant-routing.test.ts, workers/proxy/src/__tests__/index.test.ts, workers/proxy/src/__tests__/egress.test.ts. Accept: `cd workers/proxy && npm run typecheck && npm run test:unit` rc 0.
- [x] E8 [writer] Signals doc (Design 8), after E7. Update proxy.md:
  - the outcome row with `egress-unreachable`, `relocated` and `refused:route-placement-missing`;
  - a "Relocation" paragraph covering the threshold, the window, the 30-minute budget, D1 `executor_placement`, the retired object's drain, and the legacy backend's no-relocation behaviour;
  - the log lines.
    (ticked) 2026-10-28T07:32:41Z by d778be9d: 2026-10-28 by d778be9d: commit:be5d60799; E8 grep egress-unreachable and executor_placement in docs/observability/signals/proxy.md rc=0, prose check clean. DEPS-WAIVED: the plan header says code boxes E1-E8 need only PLAN-executor-durable-object-policy's code boxes, all ticked; the open prerequisites gate only E9 and E10

  Owns: docs/observability/signals/proxy.md. Accept: `grep -n "egress-unreachable" docs/observability/signals/proxy.md` rc 0 and `grep -n "executor_placement" docs/observability/signals/proxy.md` rc 0.
- [ ] E9 [live] Bench, the Live-Proof run, after E1-E8 and PLAN-executor-durable-object-policy L0. Steps:
  1. Deploy the bench account (migration 0068) before the proxy, then `deploy_proxy --target bench --record` on `durable`.
  2. Through the `machine add` verb (packages/cli/src/commands/machine/register.ts:122), add to bench org A's config:
     - `egress-blackhole` at 192.0.2.10:22;
     - `egress-refused` at the bench live-console machine's port 1.
  3. Check (P-g) first: one run against `egress-blackhole` must end in `EGRESS_UNREACHABLE`. If it ends otherwise, point `egress-blackhole` at the bench machine with `iptables -I INPUT -p tcp --dport 22 -j DROP` for the drill, and remove the rule afterwards.
  4. The new spec 27-92-live-egress-relocation.test.ts (skipped unless `LIVE_CONSOLE_ORIGIN` is set; machine names from `LIVE_CONSOLE_UNREACHABLE_MACHINE` and `LIVE_CONSOLE_REFUSED_MACHINE`) checks, in order:
     - three `machine status` runs on `egress-refused` each end with `SSH_REFUSED`, and org A's `executor_placement` is unchanged;
     - three runs on `egress-blackhole` each end with exit 6 and `EGRESS_UNREACHABLE`, the third with the relocated guidance;
     - `executor_placement` has gone up by exactly one, read with `wrangler d1 execute <LIVE_CONSOLE_D1_DATABASE> --remote --command "SELECT executor_placement FROM organizations WHERE id = '<org A>'"`;
     - `machine status` on the real machine passes;
     - `wrangler tail` shows `relocated p<n>->p<n+1>`.
  5. Record the version ids, the D1 bookmark and the rc in this plan.

  Owns: private/account/e2e/tests/27-console/27-92-live-egress-relocation.test.ts, agent/plans/PLAN-org-executor-connect-timeout-relocate.md. Accept: `cd private/account/e2e && LIVE_CONSOLE_ORIGIN=https://bench.rediacc.com npx playwright test 27-92` rc 0, plus `cd private/account/e2e && LIVE_CONSOLE_ORIGIN=https://bench.rediacc.com npx playwright test 27-90 27-91` rc 0.
  Live record, 2026-10-28, NOT PASSED (box stays open):
  - Deploy: `deploy_bench` rc 0 at head 941e1bff (D1 bookmark before migrations 00000146-000003c0-00005112-4c103c2493089c51f93f46d875188955, "No migrations to apply": 0068 was already on bench and `executor_placement` reads), account version 2e951cbe-8f22-42c7-92f2-5447037614ec; then `deploy_proxy --target bench --record /tmp/rec-e9.json` rc 0, proxy version 603278ce-a005-437f-8a87-198503867d83 (previous 2eff069a-37c6-4622-9a7b-85cfe3ad57a8), backend durable, cap 25. A later redeploy for the L0 drill 3 moved the proxy to 79ed4d90-6e20-4111-bd3d-b0a423867f0b.
  - Org A (08103c52) config attached through a new local config `e9-orga` (`config remote enable --master-password-stdin`, store 9faf0f01, config 3df57118). `machine add egress-blackhole --ip 192.0.2.10 --port 22` rc 0 and `machine add egress-refused --ip 72.61.137.225 --port 1` rc 0 (hostinger is the live-console machine).
  - `27-92` (with `-c playwright.live.config.ts`, LIVE_CONSOLE_PROXY_WORKER=rediacc-proxy-bench) rc 1 at its first refused run: the refused machine answered `exit 6 EGRESS_UNREACHABLE`, not `SSH_REFUSED`. Hostinger drops SYNs on every closed port (probed from the dev host: ports 1, 2, 9, 81, 2222, 8080 all time out), so port 1 never refuses. org A stayed at p0 and no relocation ran.
  - Substitute tried, then reverted: `egress-refused` at 127.0.0.1:1 (loopback inside the container should refuse). Two runs failed with `response.text: ... navigated away from` on the first refused run (the page lands on /account/dashboard); not diagnosed. `egress-refused` is back at 72.61.137.225:1.
  - (P-g) was not checked as its own run. Evidence so far: a closed port on hostinger gives `EGRESS_UNREACHABLE` from container egress, and the blackhole leg itself has not run. The iptables fallback was not used. Needs: a refusing endpoint reachable from Cloudflare container egress (a REJECT rule on a bench-machine port is the iptables-class change the task allows only after an explicit go), or a spec change.
  Live record, 2026-10-29 rerun, NOT PASSED (box stays open), under ASKED:2026-10-29T03:08Z "REJECT rule on hostinger (Recommended)":
  - Versions: proxy 2a24bdbc-e299-40c3-b450-fd63020987d7 (previous 79ed4d90-6e20-4111-bd3d-b0a423867f0b, from the L0 drill 3 redeploy), backend durable, cap 25, `/v1/ready` unchanged before and after. Account version unchanged from the 2026-10-28 record (2e951cbe). D1 bookmark taken before the run (`wrangler d1 time-travel info`): 00000149-00000230-00005113-98e2ae9048a10a79b597cebe7100e596.
  - Rule: `iptables -S INPUT | grep 'dport 1 '` was empty before; the `-I` rule went in rc 0 and showed in `-S INPUT`. After the run the first cleanup attempt FAILED: the wrapper's trap ran `./rdc.sh` from the e2e directory (`/bin/bash: ./rdc.sh: No such file or directory`), so the rule stayed in place for about 1 minute (04:49:32Z to roughly 04:50Z). The rule was then removed from the repo root: `-D` rc 0, and `iptables -S INPUT | grep 'dport 1 '` printed nothing (grep rc 1).
  - `executor_placement` for org A (08103c52-1471-47e4-a8f5-ea86b0aa0b27): 0 before, 0 after (relocated_at null). Org B (61fa8f2c): 1 before and after.
  - `27-92` (LIVE_CONSOLE_UNREACHABLE_MACHINE=egress-blackhole, LIVE_CONSOLE_REFUSED_MACHINE=egress-refused, LIVE_CONSOLE_PROXY_WORKER=rediacc-proxy-bench, LIVE_CONSOLE_WRANGLER_CONFIG=workers/account/wrangler.bench.toml): rc 1 at 04:49:32Z (run 04:48:48Z, 39.3 s) at its first refused run: `response.text: Protocol error (Network.getResponseBody): No data found for resource with given identifier ... navigated away from` (spec line 111, called from line 192), the same failure as the loopback substitute on 2026-10-28. The page snapshot shows the account dashboard, so the console page navigated away before the body was read, with the REJECT rule in place. The REJECT rule therefore did not get the refused leg to run, and the failure sits in the spec or the console page, not in the SSH_REFUSED path. No `wrangler tail` line was captured (the spec never reached it), so `relocated p0->p1` is NOT recorded. The fix needs a code change (read the body before navigation in the spec, or find why the page leaves /account/console/cmd/machine/status), so the run stopped here.
  - `27-90 27-91` rc 0 (2 passed, 1.8 m), run after the rule was gone.
  Live record, 2026-10-29 second rerun (account 4d722fe, spec reads the exec result through `route.fetch()`), NOT PASSED (box stays open), under ASKED:2026-10-29T03:08Z:
  - Versions: not redeployed; proxy and account as in the rerun above (proxy 2a24bdbc-e299-40c3-b450-fd63020987d7, account 2e951cbe), versions not re-read. D1 bookmark (`wrangler d1 time-travel info account-db-bench`, deploy-bench profile): 00000149-0000034f-00005113-e24850aee95076ed1fff01ea4f611dc7.
  - Rule: `-I` rc 0, `iptables -S INPUT` showed `-A INPUT -p tcp -m tcp --dport 1 -j REJECT --reject-with tcp-reset` (before the run and again after it); `-D` rc 0 from the repo root and `NO_RULE` printed.
  - Placement of org A (08103c52): 0 before, 0 after (expected +1). The first 27-92 attempt failed before any run on my own env error (LIVE_CONSOLE_WRANGLER_CONFIG given relative, ENOENT from the e2e cwd); rerun with the absolute path.
  - `27-92` rc 1 (29.9 s): navigation is fixed, the spec read `refused run 1: exit 6 code EGRESS_UNREACHABLE` and failed at spec line 213 (`Expected "SSH_REFUSED", Received "EGRESS_UNREACHABLE"`). Error context: /tmp/rediacc-live-console-results/27-console-27-92-live-egre-d6f8d--connects-move-the-executor-chromium/error-context.md. The `wrangler tail` (separate tail of rediacc-proxy-bench) shows `POST http://account.internal/executor/v1/egress-unreachable` and `proxy: org executor egress unreachable 1/3 at p0` for the refused machine, so a TCP RST from hostinger port 1 is still classified as unreachable on the Cloudflare container egress (the connect never reports a refusal) or the RST never reaches it. No `relocated p0->p1` line (0 matches).
  - `27-90 27-91` rc 0 (2 passed), run after the rule was removed.
- [ ] E10 [live, extra accept, not Live-Proof] edge-us with org B, after E9 and PLAN-executor-durable-object-policy L2. Steps:
  1. Confirm the deployed backend first with `npx wrangler versions view --config workers/proxy/wrangler.edge-us.toml`.
  2. Read org B's `executor_placement` before the run.
  3. Run 27-90 and 27-91 against edge-us.
  4. Record one of two outcomes:
     - Org B's executor fails at most three times with `EGRESS_UNREACHABLE`, its placement goes up by one, and every later run passes. This proves (P-e) on the real defect.
     - Org B passes from its first run on the fresh `durable` object (a new namespace is itself a new placement). Then the record says so, and (P-e) stays proven only by E9's mechanism plus that pass.

  A third outcome, where org B still fails after a relocation, refutes (P-e). It opens a finding for the `locationHint` follow-up named under Alternatives rejected.

  Owns: agent/plans/PLAN-org-executor-connect-timeout-relocate.md. Accept: `cd private/account/e2e && LIVE_CONSOLE_ORIGIN=https://edge-us.rediacc.com npx playwright test 27-90 27-91` rc 0, with org B's placement before and after recorded here.
- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt through --config eu-bench (PLAN-tested-on-bench ruling 3), after a VERIFIED npm run vm:check -- --changed on the same tree; ASK the operator first, because provisioning a branch renet restarts the router and daemons.
  - Accept: `live-proof hostinger renet-live`

## Risks

- **The backend premise.** By repo config, org B is on the legacy backend today (Problem, "Which backend org B is on"). Nothing here helps it before L2 flips edge-us to `durable`. That flip moves org B to a new namespace by itself, which can hide whether relocation was the fix (E10 records which outcome happened).
- **(P-e) may not hold.** If the bad path depends on the colo rather than on the host or object, a new id created from the same Worker may land on it again. E10 is the only real test. The fallback is a `locationHint` rotation over the region's hints on each relocation, as a separate plan.
- **A down machine also triggers relocation.** The executor cannot tell a dropped path from a machine that is powered off. The 30-minute budget limits the cost to one cold start per window for that org alone, and the guidance names both causes.
- **OOM history resets on relocation.** `oomAt` and `oomHeavyAt` live in the old object. The new object starts LIGHT for an OOM-flagged org until it runs out of memory once more. This is accepted to keep the old object from ever touching the new id (Design 5).
- **Deploy order.** The proxy refuses a route without `placement` (503). The account, with migration 0068, must deploy before the proxy on every target. CD already orders account before proxy. A local deploy must do the same, and E9 records it.
- **Cross-submodule ordering.** E4 lands in private/account and needs a pointer bump. E7's Accept runs only on the bumped pointer.
- **Re-entrancy (P-f).** The report reaches the object through its own container's intercept while a `fetch` on that object streams. If the platform deadlocks it, the 5 s report deadline keeps the command's result intact. E9 would then show no relocation, and the report has to move to an alarm-driven pull of a container route.
- **Coordinator v2.** `capacity:v2` starts empty. On `durable` targets, running containers re-acquire on their next renew ('not-held', then acquire at workers/proxy/src/org-executor.ts:433). Only bench runs `durable` before this lands.

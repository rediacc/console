# PLAN: one regional console executor serves many organizations, with each org held to its own container, its own issued token, its own grants and its own audit trail

Status: approved -- operator ruling 2026-10-26 ~05:30Z "Plan multi-org now, same branch" (worklist item #1741253b, lead session d778be9d, branch 1023-1). The Decisions section lists the defaults taken without asking; each is open to operator veto.
Priority: P1 -- today the console works only for the one org whose ROOT_EMAIL owner the region's issuer mints for (private/account/src/services/executor-issuer.service.ts:118-129). Every paying org in a region other than that one gets the coded 503 from the org gate (private/account/src/routes/console.ts:111-142), so the paid console is unusable for customers.
First-Seen: 2026-10-26
Owner: d778be9d
Epic: console-executor-multi-org
Depends-On: PLAN-proxy-cd-six-targets.md#P1, PLAN-proxy-cd-six-targets.md#M1, PLAN-proxy-cd-six-targets.md#D1, PLAN-proxy-cd-six-targets.md#D2 -- P1 (workers/proxy/src/**) and M1 (private/account/src/routes/console.ts) tick first, because this plan rewrites the same files; its live boxes L0-L3 can run before or after this plan's code lands, and its live boxes ML1 and later need the six-targets CD path (D1, D2) deployed; every other code box has no other dependency; six-targets E1 is named only under Concurrency, because it holds shared files and is not a dependency of any box here
Concurrency: parallel -- inside the waves under Order. The shared files are sequenced there: A1 before A2, A3 and A4 on private/account/src/services/executor-issuer.service.ts and private/account/src/types/env.ts; A2 before W2 on the ExecutorIssuer RPC shape; W1 before W2 on workers/proxy/src/index.ts. PLAN-proxy-cd-six-targets owns the same files until its P1, M1, D1 and E1 boxes tick, so no writer for this plan holds a file while that plan's open box holds it.
Owns: private/account/src/services/executor-issuer.service.ts, private/account/src/services/console-entitlement.service.ts (new), private/account/src/routes/console.ts, private/account/src/routes/configs.ts (the executor-grant and executor-token handlers only), private/account/src/routes/license.ts (the audit-events on-behalf-of block only), private/account/src/routes/proxy.ts (introspect only), private/account/src/routes/root.ts (the console-executor block and unblock actions only), private/account/src/middleware/rate-limit.ts, private/account/src/services/config.service.ts (executorPrincipalOf and mintExecutorSession only), private/account/src/services/api-token.service.ts, private/account/src/types/env.ts, private/account/src/entry/cloudflare.ts, private/account/src/errors.ts, private/account/src/db/schema.ts, private/account/drizzle/0066_*.sql, private/account/drizzle/meta/**, private/account/src/container.ts, private/account/tests/integration/executor-issuer*.test.ts, private/account/tests/integration/console-org-gate.test.ts (replaced by console-entitlement.test.ts), private/account/tests/integration/console-entitlement.test.ts, private/account/tests/integration/executor-multi-org.test.ts, private/account/tests/integration/executor-grant-principal.test.ts, private/account/tests/integration/config-executor-token.test.ts, private/account/tests/integration/audit-obo-issuer.test.ts, private/account/tests/integration/root-console-block.test.ts, private/account/web/src/components/console/ResultView.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/components/console/__tests__/result-view-entitlement.test.tsx, private/account/e2e/tests/27-console/27-91-live-two-orgs.test.ts, private/account/CLAUDE.md (console section), workers/account/src/index.ts, workers/proxy/src/**, packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/commands/serve.ts, packages/cli/src/services/serve/__tests__/**, .ci/config/secret-supply.json (the live-console profile only), .ci/rediacc_ci/ops/executor_orgs.py (new), .ci/rediacc_ci/tests/test_ops_executor_orgs.py (new), docs/observability/signals/proxy.md, .claude/skills/deploy/SKILL.md (the executor paragraph only), agent/plans/PLAN-console-executor-multi-org.md, agent/plans/PLAN-proxy-cd-six-targets.md (relation lines and Decision 2 only)

## Operator rulings

- **2026-10-26 ~05:30Z "Plan multi-org now, same branch".** Multi-org support is designed now and lands on branch 1023-1 next to PLAN-proxy-cd-six-targets.
- **Inherited from PLAN-proxy-cd-six-targets, unchanged:** 7 deployable configs (ASKED:2026-10-25T19:08Z); its max_instances = 3 and 21-in-total ceiling are superseded by ASKED:2026-10-26T15:26Z "Per-org, raise the cap": max_instances = 25 per proxy config, at most 175 in total, `sleepAfter` unchanged at 2 minutes. The binding mints, with no exported EXECUTOR_TOKEN (ASKED:2026-10-25T19:08Z). Each region stays closed until its smoke passes (ASKED:2026-10-25T18:18Z). The web client re-grants transparently (ASKED:2026-10-25T18:18Z). Secrets travel only through bws_env, and only their names appear anywhere (order 2026-10-25T18:10Z).
- **Standing posture:** there are no external users, so this is a clean break. No compatibility shims, no dual-format principals, and no fallback to ROOT_EMAIL ownership.

## Context

### Verified state (2026-10-26, console 1023-1, private/account 257625a)

1. **The issuer is single-org by construction.** `ExecutorIssuerService.issue(config)` resolves the owner from ROOT_EMAIL (private/account/src/services/executor-issuer.service.ts:118-122). It then picks the one org that owner owns, or the one EXECUTOR_ISSUER_ORG_ID names (:124-128), re-checks the owner's role (:134-141) and the subscription (:143-156), and mints with `createdByUserId = owner.id` and issuer_key `executor:<ENV>:<REGION>` (:158-168, :69-72). The RPC takes no arguments (workers/account/src/index.ts:86-89; private/account/src/entry/cloudflare.ts:121-140). EXECUTOR_ISSUER_ORG_ID is parsed at private/account/src/types/env.ts:267-270 and :367-381.
2. **The console org gate.** `issuerOrgId` (private/account/src/routes/console.ts:111-128) recomputes the issuer's org. `requireIssuerOrg` (:135-142) answers 503 `CONSOLE_EXECUTION_UNAVAILABLE` to any caller of another org, and all three legs call it (:444, :506, :544). The server checks no plan entitlement anywhere: `webConsole` appears only in packages/shared/src/subscription/constants.ts:529-553 (COMMUNITY false; PROFESSIONAL, BUSINESS and ENTERPRISE true) and in the web ConsoleGate. Bench's ROOT org holds a COMMUNITY subscription (PLAN-proxy-cd-six-targets, Live records, bench notes), and the issuer mints for it anyway.
3. **Introspection is same-org only.** private/account/src/routes/proxy.ts:81 resolves the caller's org from the executor token's subscription, and private/account/src/routes/proxy.ts:96 answers `active:false` for a target of any other org. This is the server-side rule that already makes an org-scoped executor token unable to act for a foreign org's user.
4. **Grant recording and config-token minting are org-bound server-side.**
   - `executorOrg` (private/account/src/routes/configs.ts:98-102) derives the org from the executor token's subscription and never reads a client value.
   - `/executor-grant` (private/account/src/routes/configs.ts:880-947) requires the presented user bearer to be of the same org (:912), not the executor's own principal (:914-915), live, carrying proxy:exec, and from a current member (:918).
   - `/executor-token` (private/account/src/routes/configs.ts:949-1022) requires the target user to be a member (:963-968). It requires the executor token's creator to equal the target or be an owner or admin (:975-986). It mints only through `mintExecutorSession`, which loads the store by the executor's org (config.service.ts, `configStores.orgId = executorOrgId`) and requires a live grant row matching session, principal and user (`configExecutorGrants.executorTokenId = executorPrincipal`). The grant also ends when the grantor's bearer is revoked or expired.
   - `executorPrincipalOf = issuerKey ?? id` (private/account/src/services/config.service.ts:358-360). The grant table's unique index is (store, executor_token_id, session) (private/account/src/db/config-schema.ts, `idx_config_executor_grants_session`).
5. **Audit attribution is org-checked.** `/licenses/audit-events` refuses a batch whose `onBehalfOfTokenId` resolves to another org, with 403 `ON_BEHALF_TOKEN_FORBIDDEN` (private/account/src/routes/license.ts:290-310). The actor is the on-behalf token's creator, else the authenticating token's creator (:326-328). The executor sends `onBehalfOfTokenId = principal.tokenId` (packages/cli/src/services/serve/audit.ts:56-59), and introspection supplies it (private/account/src/routes/proxy.ts:121-123).
6. **The proxy already places one container per tenant.** `resolveTenant` introspects the caller with the Worker's issued token and keys the Durable Object as `${orgId}:${teamId ?? 'default'}` (workers/proxy/src/index.ts:166-204). `getContainer(env.EXECUTOR, tenant)` follows at :243. But the issued token belongs to one org, so introspection of any other org's caller answers inactive (fact 3). The egress uses one module-scope token cache (workers/proxy/src/issued-token.ts:53-55, :97-119). That token reaches every container the same way (workers/proxy/src/egress.ts:78-91, :94-128), and the outbound handler ignores which container is calling (workers/proxy/src/index.ts:114-119).
7. **The containers library can tell instances apart.** @cloudflare/containers 0.3.7 hands each outbound handler `ctx: { containerId, className, params }` (the package's dist/lib/container.d.ts, lines 3 to 16). `setOutboundByHost(hostname, methodName, params)` installs a per-instance handler with params (:87-101). The container process cannot set these params: they are set by Durable Object code.
8. **What the executor holds per process.**
   - `SessionStore` is one per process. It holds sessions keyed by id and a user to session index (packages/cli/src/services/serve/sessions.ts:69-79, :143). Ownership is checked by userId only (:129, :220), and orgId is never compared.
   - The decrypted config cache is per session, in RAM (packages/cli/src/services/serve/container-config.ts:82, :113-136).
   - AuthVerifier caches principals per bearer for 60 s (packages/cli/src/services/serve/auth.ts:19, :90-116) and does not compare `body.orgId` with anything (:175-202).
   - Request config is scoped through runInRequestContext (packages/cli/src/services/serve/server.ts:471-486).
   - SSH keys come from the decrypted config (packages/cli/src/services/executor/local-executor.ts:431). Secrets reach renet on stdin, never argv (packages/cli/src/services/executor/renet-launch.ts:55-72).
   - Decryption binds storeId, configId and teamId through the envelope AAD (packages/cli/src/services/serve/container-config.ts:128-133).
9. **Rate limits.**
   - Introspect is limited per authenticated token id for binding calls (private/account/src/middleware/rate-limit.ts:102-139, the key `apiToken:${tokenId}` at :134).
   - All binding callers share one ceiling of limit × BINDING_CEILING_FACTOR (10, :82, :112).
   - With per-org tokens renewed every ~36 minutes, the per-token key splits one org across buckets, and the shared ceiling makes one busy org starve every other org in the region.
10. **The CD switch** is per account Worker (.ci/rediacc_ci/deploy/console_executor.py:1-14) and stays as it is. Multi-org needs no new secret: ROOT_EMAIL remains the system-root secret but the issuer stops reading it, and EXECUTOR_ISSUER_ORG_ID is set in no wrangler config or secret map (grep over workers/ and .ci/config returns nothing).

### Unverified claims (each is proved or refuted by the box named)

- MU1 (W1): `OutboundHandlerContext.containerId` equals `env.EXECUTOR.idFromName(tenant).toString()` for the instance `getContainer(env.EXECUTOR, tenant)` returns. If it does not, W1 binds through the params alone and records the observed shape.
- MU2 (W1, ML0): when max_instances running instances already exist, a start for a new Durable Object name fails with a catchable error, rather than queuing or evicting. ML0 records the observed error text on bench by starting a fourth org. Every one of the four must be entitled (the server checks no entitlement today, see Verified state item 2; with the planned check a COMMUNITY org, bench's ROOT org as it stands, is refused with 403 `CONSOLE_NOT_ENTITLED` before any container start), so the ROOT org takes a PROFESSIONAL subscription for that drill or a fourth provisioned org stands in for it.
- MU3 (W1): `startAndWaitForPorts({ startOptions: { envVars } })` (or the 0.3.7 equivalent) sets env per instance, overriding the class-level `envVars` field (workers/proxy/src/index.ts:134).
- MU4 (C2): `rdc serve --mode container` writes no key material to disk on the dispatch path, including known_hosts and ssh2 agent files. C2 proves it with an fs-write spy, or names the writes and moves them under a per-request 0700 directory that is removed in `finally`.
- MU5 (ML0): each of the seven D1s can hold two entitled orgs (PROFESSIONAL or higher, live subscription, config store with a server-recoverable org passphrase) created through existing root or test paths. ML0 records the path used and the ids only.

## Design

### 1. Identity: how the executor learns the org, and why org A can never run under org B

The org is never taken from the client. It is derived once from the caller's own token, server-side, and then pinned into every later hop, so each hop re-derives or verifies it independently.

1. **Front door.** The proxy Worker no longer introspects with an issued token. It calls a new RPC, `ExecutorIssuer.route(bearer)`, which:
   - performs the pure read that introspection performs (`apiTokenService.validate`, no IP bind, no lastUsedAt);
   - refuses `ip_binding = 'service-binding'` tokens, because an executor token is never a caller;
   - requires `proxy:exec`, refuses an archived team, and resolves the org through the token's subscription;
   - runs the entitlement check (item 4).

   It answers `{ orgId }` or a bare refusal code. The Durable Object key becomes `orgId` alone (it is `org:team` today, workers/proxy/src/index.ts:203). Teams share one CEK per org, so a per-team container isolates nothing cryptographically while multiplying instances against a cap of 3.
2. **Pinning the instance.** Before forwarding, the Worker calls the Durable Object's RPC `pin(orgId)`. The Durable Object:
   - checks `this.ctx.id.equals(env.EXECUTOR.idFromName(orgId))` and refuses otherwise, so a claimed org that is not the Durable Object's own name cannot be pinned;
   - stores the org, and refuses a later `pin` with a different value;
   - starts the container with per-instance env `REDIACC_EXECUTOR_ORG_ID=<orgId>` (MU3);
   - installs `setOutboundByHost('account.internal', 'accountEgress', { orgId })`.
3. **Egress.** `accountEgress(request, env, ctx)` requires `ctx.params.orgId`, and requires `ctx.containerId === env.EXECUTOR.idFromName(ctx.params.orgId).toString()` (MU1). It then swaps the placeholder for `issuedToken(env.ISSUER, orgId)`. The container never names an org: the org comes from Durable Object code and is cross-checked against the instance identity. The allowlist and the placeholder rule (workers/proxy/src/egress.ts:21-36, :78-91) are unchanged.
4. **Executor.** `rdc serve --mode container` refuses to start without `REDIACC_EXECUTOR_ORG_ID`. `AuthVerifier.toPrincipal` refuses `body.orgId !== pinnedOrg` with 401, in the same words as an inactive token. This is defence in depth: the org-A token already makes private/account/src/routes/proxy.ts:96 answer inactive for an org-B caller.
5. **Grant and config.** The org-A issued token can record grants only for org-A members (private/account/src/routes/configs.ts:912). It can mint config tokens only against org A's store (mintExecutorSession), and only for a grant row that names the principal `executor:<ENV>:<REGION>:<orgA>`. The pulled blob opens only under the CEK that the org-A user's browser sealed to that session's ephemeral key. The envelope AAD (packages/cli/src/services/serve/container-config.ts:128-133) refuses a blob served for another store, config or team. Org B's grant, config token, CEK and blob are therefore unreachable from org A's container at four independent server-side or cryptographic checks.
6. **Audit.** Every event carries `onBehalfOfTokenId`, and private/account/src/routes/license.ts:294-310 refuses a foreign one. Item 2 adds a rule: an issued executor token must name `onBehalfOfTokenId` on every event, because it has no creator to fall back to.

### 2. Token model: per-org issued tokens, minted on demand

- **`ExecutorIssuer.issue(orgId: string)`** replaces `issue()`. Each mint:
  - re-runs the entitlement check (item 4) for that org and refuses with a reason code otherwise (`ISSUER_ORG_NOT_FOUND`, `ISSUER_ORG_NOT_ENTITLED`, `ISSUER_ORG_BLOCKED`, `ISSUER_SUBSCRIPTION_INACTIVE`, `ISSUER_STORE_UNSUPPORTED`, `ISSUER_REGION_UNSET`);
  - mints a 45-minute token: scopes exactly `proxy:exec` and `audit:write`, ip binding `service-binding`, subscription = the org's primary live subscription, `createdByUserId = null`, and `issuer_key = executor:<ENVIRONMENT>:<REGION>:<orgId>`;
  - audits `executor_token.issued` or `executor_token.refused` with orgId, never the value.
- **What replaces ROOT_EMAIL ownership.** No user owns an executor token. The authority to act for a user is the live grant row that the user's own bearer recorded (private/account/src/routes/configs.ts:880-947), not an owner's role.
  - `/executor-token` (private/account/src/routes/configs.ts:975-986) treats a token with an `issuerKey` as authorized by the grant alone: it skips the creator check, while mintExecutorSession still demands a live grant for exactly this session, principal and user.
  - A token with no issuer key and no creator still acts for nobody else.
  - The issuer no longer reads ROOT_EMAIL. EXECUTOR_ISSUER_ORG_ID is deleted from env.ts and from the issuer env schema. The refusal codes `ISSUER_OWNER_UNSET`, `ISSUER_OWNER_UNKNOWN`, `ISSUER_ORG_AMBIGUOUS` and `ISSUER_ROLE_REVOKED` are deleted.
- **Principal.** `executorPrincipalOf` stays `issuerKey ?? id`. Because the key now includes the org, the principal is org-unique as well as store-scoped.
- **Proxy cache.** issued-token.ts becomes a per-org map with single-flight and failure backoff per org, an LRU bound of 64 orgs per isolate, and renewal at 80% as before. A refusal for org A never blocks org B.
- **Revocation.**
  - A root action, `POST /admin/orgs/:id/console-executor/block` (elevated session, root.ts), sets `organizations.console_executor_blocked_at`. It revokes every unrevoked api_tokens row of that org whose issuer_key starts with `executor:`, and deletes the org store's config_executor_grants rows.
  - The next egress call gets 401 from the account server. The proxy cache entry is dropped on any 401 from a bearer route, and the next mint is refused with `ISSUER_ORG_BLOCKED`.
  - A plan downgrade or a lapsed subscription stops new mints at once, and existing tokens within one TTL (45 minutes). The console gate refuses at the next leg.
- **Readiness.** `/v1/ready` (workers/proxy/src/ready.ts) can no longer introspect an org-less token. A third RPC, `ExecutorIssuer.probe()`, writes nothing: it checks the issuer env parses and D1 answers, and returns `{ ok: true, scopes, ttlMs }`. The ready endpoint checks that, plus `GET server-info` over ACCOUNT. The 30 s cache stays.

### 3. Isolation inside the executor

- **Process boundary = org boundary.** One container (a Durable Object instance, a separate Linux process tree) per org per target. Two orgs never share a SessionStore, a decrypted config, an SSH connection pool, a renet subprocess or a temp directory. A shared multi-tenant process was rejected (Decisions 1).
- **Inside one org's container**, the existing per-user rules hold:
  - session ownership by userId (packages/cli/src/services/serve/sessions.ts:129, :220);
  - a config cache per session, dropped with the session (packages/cli/src/services/serve/container-config.ts:84-93);
  - a 30-minute idle TTL for the CEK (packages/cli/src/services/serve/sessions.ts:32);
  - a request-scoped config context (packages/cli/src/services/serve/server.ts:471-486);
  - secrets on stdin (packages/cli/src/services/executor/renet-launch.ts:55-72).
  
  C2 adds the pinned-org assertion to `SessionStore.open`, so a session records `orgId` and `grantCek` and `sessionForExec` refuse a principal of another org with the indistinguishable unknown-session code. C2 also proves MU4.
- **Env.** The container env holds exactly REDIACC_TOKEN (placeholder), REDIACC_ACCOUNT_SERVER, REDIACC_REGION and REDIACC_EXECUTOR_ORG_ID. A test asserts that set, and asserts no issued token appears in it.
- **Capacity and concurrency.**
  - With max_instances 25 (Decision 3), at most 25 orgs per target run warm at once, and `sleepAfter = '2m'` frees a slot after idle.
  - A start that fails on capacity (MU2) answers 503 `{ code: 'EXECUTOR_CAPACITY' }` with `Retry-After: 30`. console.ts relays that one 503 code (RELAYED_STATUSES and RELAYED_CODES gain 503 and `EXECUTOR_CAPACITY`), and ResultView shows a localized "busy, retry shortly" state.
  - The proxy emits a `rediacc.proxy.outcome = capacity` span attribute, so the capacity question (Decisions 3) can be answered from Tempo rather than guessed.
- **Audit attribution.** This is unchanged (onBehalfOfTokenId, packages/cli/src/services/serve/audit.ts:56-59), plus the item 1.6 rule. The event_log row carries the org from the on-behalf token's org, so each org's console commands land in that org's audit trail.
- **Per-org rate limits.**
  - Binding-call buckets key on `issuerKey ?? tokenId` (private/account/src/middleware/rate-limit.ts:134), so renewal does not reset an org's bucket.
  - The shared binding ceiling (:112) becomes per-org for issuer-key tokens, and stays shared for the rest.
  - `/console/exec` gains `rateLimit` keyed on `console:<orgId>` (60 per minute), and `/console/session` gets 20 per minute per org.
  - The proxy front door makes no rate decision. The account Worker holds every limit.

### 4. Gate changes: the console org gate becomes an entitlement gate

- **`ConsoleEntitlementService.check(orgId)`** is one function used by the console legs, `ExecutorIssuer.route` and `ExecutorIssuer.issue`. It answers ok only when all of these hold:
  - the org exists and `console_executor_blocked_at` is null;
  - the primary subscription is live (the issuer's LIVE_STATUS_RANK rule, private/account/src/services/executor-issuer.service.ts:83-156, moved here);
  - `PLAN_METADATA[plan].webConsole` is true;
  - the org's config store exists with `serverRecoverableOrgPassphrase`, without which mintExecutorSession refuses anyway.
- **What each leg answers.**
  - `requireIssuerOrg` and `issuerOrgId` (private/account/src/routes/console.ts:102-142) are deleted.
  - Each leg answers the region-level 503 `CONSOLE_EXECUTION_UNAVAILABLE` exactly as today when the mode is not proxy or no executor is bound.
  - It answers 403 `CONSOLE_NOT_ENTITLED` with `details.reason` from `plan`, `subscription`, `store` or `blocked` when the org fails the check.
  - ResultView renders a localized state per reason in all 13 locales.
- **Fail-closed list.**
  - Any error inside the check refuses.
  - `route()` refuses unknown, revoked, expired, service-binding, scope-less and archived-team tokens with one code (`route-refused`), so it is no token oracle.
  - `issue()` refuses an org it cannot positively entitle.
  - The egress refuses a missing or mismatched org param before the issuer is asked.
  - The executor refuses to boot without a pinned org, and refuses a principal of another org.
  - A capacity failure is a 503, never a fallback to another org's instance.

### 5. Migration: a clean break

- **D1 migration `0066_console_executor_multi_org.sql`:**
  - `ALTER TABLE organizations ADD console_executor_blocked_at text`;
  - `UPDATE api_tokens SET revoked_at = <now> WHERE issuer_key LIKE 'executor:%' AND revoked_at IS NULL`, which retires the three-part single-org tokens;
  - `DELETE FROM config_executor_grants`. Live sessions re-grant through the R1 path of PLAN-proxy-cd-six-targets, which the redeploy already forces because the container sessions are wiped.
  
  No column or table is kept for the old model.
- **Code removals.** EXECUTOR_ISSUER_ORG_ID (private/account/src/types/env.ts:267-270, :373), the ROOT_EMAIL read in the issuer, `issuerOrgId` and `requireIssuerOrg`, the four owner refusal codes, the `org:team` Durable Object key, and the single module-scope token in issued-token.ts.
- **CD and secrets.**
  - No new Worker secret or var in any target, and the six-targets CD order already deploys the account Worker before the proxy (Design item 9). Between the account deploy and the proxy deploy, an old proxy calling `issue()` with no org is refused with `ISSUER_ORG_REQUIRED`, and the region answers 503 for those minutes. This is accepted because there are no external users.
  - The `live-console` bws profile gains names only: `LIVE_CONSOLE_ORG_A_EMAIL`, `LIVE_CONSOLE_ORG_A_PASSWORD`, `LIVE_CONSOLE_ORG_B_EMAIL`, `LIVE_CONSOLE_ORG_B_PASSWORD`, plus the TOTP seeds if the login demands them.
  - The cost guard is unchanged (3 per config, 21 in total).
- **Order.** Bench first (ML0), then edge-eu, edge-us and edge-asia before merge (ML1-ML3), then CD edge and promote-stable after merge (ML4-ML6).

### 6. Tests and live proof

- Account integration tests (A1-A5), proxy unit tests (W1-W2), CLI tests (C1-C2) and a web test (U1), each listed with its box.
- **Drills (ML0):**
  - cross-org session replay: org B's user sends org A's `X-Config-Session` value and gets 404 `EXECUTOR_SESSION_UNKNOWN`;
  - block and unblock: the blocked org's next command is refused within one request, and the other org is unaffected;
  - a capacity overflow, using a fourth org on bench;
  - a plan downgrade to COMMUNITY: 403 `CONSOLE_NOT_ENTITLED`, reason plan.
- **Live proof (ML0-ML6):**
  - per region, `machine status <machine>` from the portal console as an org-A member and as an org-B member;
  - each run succeeds without the mock text;
  - two `cli.command` event_log rows, each with its own org id and user;
  - two `executor_token.issued` rows with distinct issuer keys `executor:<env>:<region>:<org>`;
  - two distinct Durable Object names in the proxy's `rediacc.proxy.outcome=forwarded` spans (counted by `wrangler tail` lines, never printing an id beyond its first 8 characters).

## Tasks

### Account (private/account submodule PR first)

- [x] A1 [account-entitlement] ConsoleEntitlementService and migration 0066.
  - Add `private/account/src/services/console-entitlement.service.ts` with `check(orgId)` per Design item 4, moving LIVE_STATUS_RANK and TYPE_RANK out of executor-issuer.service.ts.
  - Write `drizzle/0066_console_executor_multi_org.sql` per Design item 5, add the schema column, and wire the service in container.ts.
  - Adversarial tests: a COMMUNITY org refused with reason plan; a suspended subscription refused; a store without a server-recoverable passphrase refused with reason store; a blocked org refused; a PROFESSIONAL org with a live subscription and store allowed; a thrown D1 error refuses; the migration revokes an `executor:edge:eu` token and empties config_executor_grants.
    (ticked) 2026-10-26T13:09:40Z by d778be9d: account 82a13c7c: private/account/src/services/console-entitlement.service.ts check(orgId) and private/account/drizzle/0066_console_executor_multi_org.sql; cd private/account && npx vitest run tests/integration/console-entitlement.test.ts rc=0 (13 passed); npm run typecheck rc=0; npm run check:ci-account-scope-audit rc=0
  
  -- Owns: private/account/src/services/console-entitlement.service.ts, private/account/src/db/schema.ts, private/account/drizzle/0066_*.sql, private/account/drizzle/meta/**, private/account/src/container.ts, private/account/tests/integration/console-entitlement.test.ts. Accept: `cd private/account && npx vitest run tests/integration/console-entitlement.test.ts` exits 0, `npm run typecheck` exits 0, and `npm run check:ci-account-scope-audit` exits 0.
- [x] A2 [account-issuer] The per-org ExecutorIssuer, after A1.
  - `route(bearer)`, `issue(orgId)` and `probe()` per Design items 1.1 and 2, with the RPC entrypoint in workers/account/src/index.ts and the handlers in entry/cloudflare.ts.
  - Delete EXECUTOR_ISSUER_ORG_ID, the ROOT_EMAIL read and the owner codes. issuer_key is `executor:<ENV>:<REGION>:<orgId>`, and createdByUserId is null.
  - Adversarial tests:
    - `issue` for a non-entitled org is refused and audited with orgId;
    - two orgs get tokens with distinct issuer keys, and neither token's introspection answers for the other org's user token;
    - `route` of a service-binding token, a revoked token, a token without proxy:exec and an archived-team token all answer the same `route-refused`;
    - `route` of an entitled member's proxy:exec token answers exactly `{ orgId }`;
    - `issue('')` and `issue` of an unknown id are refused;
    - `ExecutorIssuer.prototype.fetch` is undefined;
    - no column of the issued row or event row holds the token value;
    - `probe` writes no row.
    (ticked) 2026-10-26T15:03:58Z by d778be9d: account 272f7788 (console af0918ce): route, issue(orgId) behind the entitlement check, probe in private/account/src/services/executor-issuer.service.ts; cd private/account && npx vitest run tests/integration/executor-issuer.test.ts tests/integration/executor-issuer-route.test.ts tests/integration/api-token-service-binding.test.ts rc=0; npm run typecheck rc=0; the EXECUTOR_ISSUER_ORG_ID and ISSUER_OWNER_ grep prints nothing since A4 (account cf2c57df). DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: private/account/src/services/executor-issuer.service.ts, workers/account/src/index.ts, private/account/src/entry/cloudflare.ts, private/account/src/types/env.ts, private/account/src/services/api-token.service.ts, private/account/tests/integration/executor-issuer.test.ts, private/account/tests/integration/executor-issuer-route.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-issuer.test.ts tests/integration/executor-issuer-route.test.ts tests/integration/api-token-service-binding.test.ts` exits 0, `npm run typecheck` exits 0, and `grep -rn 'EXECUTOR_ISSUER_ORG_ID\|ISSUER_OWNER_' private/account/src workers/account/src` prints nothing.
- [x] A3 [account-grants] Grants, config tokens and audit for issuer tokens, after A2.
  - `/executor-token` authorizes an issuer-key token by the live grant alone (private/account/src/routes/configs.ts:975-986).
  - `/licenses/audit-events` refuses an event without `onBehalfOfTokenId` from an issuer-key token, with 403 `ON_BEHALF_REQUIRED`.
  - executor-grant-principal.test.ts is rewritten for the org-qualified key.
  - The cross-org matrix in executor-multi-org.test.ts, using org A and org B in one region:
    - org A's issued token cannot record a grant with an org-B bearer (403 `executor_grant_invalid`);
    - it cannot mint an executor-token for an org-B user (403);
    - with a grant recorded under org A's principal, org B's issued token cannot mint for that user and session;
    - an audit event from org A naming an org-B token as on-behalf is refused with `ON_BEHALF_TOKEN_FORBIDDEN`;
    - a grant survives renewal to a sibling token with the same org-qualified key;
    - a grant does not match a token of the same region and another org.
    (ticked) 2026-10-26T15:03:59Z by d778be9d: account 332b8b85 (pointer bd7ccbe6): cd private/account && npx vitest run tests/integration/executor-multi-org.test.ts tests/integration/executor-grant-principal.test.ts tests/integration/config-executor-token.test.ts tests/integration/audit-obo-issuer.test.ts tests/integration/proxy-introspect.test.ts rc=0. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: private/account/src/routes/configs.ts (the two executor handlers), private/account/src/services/config.service.ts (executorPrincipalOf comment and mintExecutorSession), private/account/src/routes/license.ts (on-behalf block), private/account/tests/integration/executor-multi-org.test.ts, private/account/tests/integration/executor-grant-principal.test.ts, private/account/tests/integration/config-executor-token.test.ts, private/account/tests/integration/audit-obo-issuer.test.ts. Accept: `cd private/account && npx vitest run tests/integration/executor-multi-org.test.ts tests/integration/executor-grant-principal.test.ts tests/integration/config-executor-token.test.ts tests/integration/audit-obo-issuer.test.ts tests/integration/proxy-*.test.ts` exits 0.
- [x] A4 [account-console] The entitlement gate on the console legs, after A1 and PLAN-proxy-cd-six-targets M1.
  - Delete `issuerOrgId` and `requireIssuerOrg`.
  - Every leg calls `ConsoleEntitlementService.check` and answers 403 `CONSOLE_NOT_ENTITLED` with `details.reason`.
  - `ErrorCode` gains `CONSOLE_NOT_ENTITLED`.
  - RELAYED_STATUSES gains 503, and RELAYED_CODES gains `EXECUTOR_CAPACITY`.
  - Per-org rate limits on /exec (60 per minute) and /session (20 per minute).
  - console-org-gate.test.ts is replaced: two entitled orgs both reach the fake executor; a COMMUNITY org gets 403 with reason plan; a blocked org gets 403 with reason blocked; the mode-off region still gets the 503; a relayed 503 keeps `EXECUTOR_CAPACITY`; the 61st exec in a minute for org A is 429 while org B's first passes (forceRateLimit).
    (ticked) 2026-10-26T15:04:00Z by d778be9d: account cf2c57df (pointer bd7ccbe6): cd private/account && npx vitest run tests/integration/console-entitlement.test.ts tests/integration/console-session.test.ts rc=0; tests/integration/console-org-gate.test.ts deleted; the route-level cases live in tests/integration/console-entitlement-gate.test.ts. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: private/account/src/routes/console.ts, private/account/src/errors.ts, private/account/tests/integration/console-org-gate.test.ts (deleted), private/account/tests/integration/console-session.test.ts. Accept: `cd private/account && npx vitest run tests/integration/console-entitlement.test.ts tests/integration/console-session.test.ts` exits 0 and `test ! -e private/account/tests/integration/console-org-gate.test.ts`.
- [x] A5 [account-root] Block, unblock and per-org rate buckets, after A1.
  - `POST /admin/orgs/:id/console-executor/block` and `/unblock` (root, elevated session) per Design item 2, Revocation, each audited as `console_executor.blocked` and `console_executor.unblocked`.
  - rate-limit.ts keys binding buckets on `issuerKey ?? tokenId` and gives issuer-key callers a per-org ceiling.
  - Tests: block revokes only that org's issuer tokens and grants, unblock lets the next `issue` pass, a non-root caller gets 403, and with forced limits org A exhausting its introspect bucket leaves org B's next call at 200.
    (ticked) 2026-10-26T13:27:17Z by d778be9d: account 7d3bec78 (pointer 4ec78ace): block and unblock in private/account/src/routes/root.ts, per-org buckets in private/account/src/middleware/rate-limit.ts; cd private/account && npx vitest run tests/integration/root-console-block.test.ts tests/integration/proxy-introspect.test.ts rc=0; npm run check:ci-account-layer-isolation rc=0. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88; the rest of that plan is live and post-merge
  
  -- Owns: private/account/src/routes/root.ts (the two actions), private/account/src/middleware/rate-limit.ts, private/account/tests/integration/root-console-block.test.ts, private/account/tests/integration/proxy-introspect.test.ts. Accept: `cd private/account && npx vitest run tests/integration/root-console-block.test.ts tests/integration/proxy-introspect.test.ts` exits 0 and `npm run check:ci-account-layer-isolation` exits 0.
- [x] U1 [account-web] Localized entitlement and capacity states, after A4.
  - ResultView renders `CONSOLE_NOT_ENTITLED` (reasons plan, subscription, store and blocked) and `EXECUTOR_CAPACITY` from new `console.json` keys in all 13 locales.
  - The capacity state offers a retry after `Retry-After`.
    (ticked) 2026-10-26T15:56:14Z by d778be9d: account 4cb229dd (pointer 1841a2ea): private/account/web/src/components/console/ResultView.tsx entitlement and capacity states; cd private/account/web && npx vitest run src/components/console/__tests__/result-view-entitlement.test.tsx rc=0; npm run check:ci-i18n-completeness rc=0; npm run check:ci-i18n-placeholders rc=0. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: private/account/web/src/components/console/ResultView.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/components/console/__tests__/result-view-entitlement.test.tsx. Accept: `cd private/account/web && npx vitest run src/components/console/__tests__/result-view-entitlement.test.tsx` exits 0, and `npm run check:ci-i18n-completeness` and `npm run check:ci-i18n-placeholders` exit 0.

### Proxy Worker

- [x] W1 [proxy] Per-org routing, pinning and egress, after PLAN-proxy-cd-six-targets P1.
  - `resolveTenant` calls `ISSUER.route(bearer)`, and the Durable Object key is `orgId`.
  - `ExecutorContainer.pin(orgId)` checks the id, stores the org, starts with the per-instance `REDIACC_EXECUTOR_ORG_ID` (MU3), and installs `setOutboundByHost` with `{ orgId }`.
  - The egress becomes the `accountEgress` named handler, which checks `ctx.params.orgId` and `ctx.containerId` (MU1).
  - A start failure on capacity maps to 503 `EXECUTOR_CAPACITY` with Retry-After (MU2), plus the capacity span attribute.
  - Adversarial tests:
    - two callers of two orgs reach two Durable Object names;
    - a route refusal is 401 and an issuer failure 503;
    - `pin` with an org whose `idFromName` differs from the instance id is refused;
    - a second `pin` with another org is refused;
    - an egress call with no params, or with params naming another org than the container id, is refused 403 before the issuer is called (the fake counts zero);
    - the container env set is exactly the four names;
    - a capacity error yields 503 with the code.
    (ticked) 2026-10-26T15:04:02Z by d778be9d: 67bc4187: cd workers/proxy && npm run test:unit rc=0 (105); npm run check:ci-proxy-wrangler-dev-e2e rc=0 with the stub issuer serving route, issue(orgId) and probe. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: workers/proxy/src/index.ts, workers/proxy/src/egress.ts, workers/proxy/src/__tests__/tenant-routing.test.ts, workers/proxy/src/__tests__/egress.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0, and `npm run check:ci-proxy-wrangler-dev-e2e` exits 0 on a docker host with the stub issuer serving two orgs.
- [x] W2 [proxy] Per-org token cache and readiness, after A2 (RPC shape) and W1.
  - `issuedToken(issuer, orgId)` keeps a per-org cache with single-flight, failure backoff and an LRU of 64 orgs.
  - A 401 on a bearer route drops that org's entry.
  - `/v1/ready` uses `probe()` plus server-info over ACCOUNT.
  - Tests:
    - 10 concurrent requests for org A and 10 for org B make exactly one mint each;
    - org A's token is never returned for org B;
    - org A's refusal backoff does not delay org B;
    - the 65th org evicts the least recently used;
    - the ready endpoint answers 503 `issuer-probe-failed` when probe throws, and writes no mint.
    (ticked) 2026-10-26T15:04:02Z by d778be9d: 67bc4187: cd workers/proxy && npm run test:unit rc=0; grep -n 'let cached' workers/proxy/src/issued-token.ts prints nothing. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: workers/proxy/src/issued-token.ts, workers/proxy/src/ready.ts, workers/proxy/src/__tests__/issued-token.test.ts, workers/proxy/src/__tests__/ready.test.ts. Accept: `cd workers/proxy && npm run test:unit` exits 0 and `grep -n 'let cached' workers/proxy/src/issued-token.ts` prints nothing.

### CLI executor

- [x] C1 [cli] The pinned org in `rdc serve --mode container`. serve.ts refuses to start in container mode without `REDIACC_EXECUTOR_ORG_ID`. AuthVerifier takes `pinnedOrgId` and refuses `body.orgId !== pinnedOrgId` with the inactive-token 401. The test proves the boot refusal, the foreign-org refusal, and that a foreign-org answer is not cached. -- Owns: packages/cli/src/commands/serve.ts, packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/__tests__/pinned-org.test.ts. Accept: `cd packages/cli && npx vitest run src/services/serve/__tests__/pinned-org.test.ts src/services/serve/__tests__/audit-capability-self.test.ts` exits 0 and `npx tsc --noEmit --project packages/cli/tsconfig.json` exits 0.
    (ticked) 2026-10-26T13:09:39Z by d778be9d: 3a2d76f1: packages/cli/src/services/serve/auth.ts resolvePinnedOrgId and the pinned-org refusal; cd packages/cli && npx vitest run src/services/serve/__tests__/pinned-org.test.ts src/services/serve/__tests__/audit-capability-self.test.ts rc=0 (9 passed); npx tsc --noEmit --project packages/cli/tsconfig.json rc=0
- [x] C2 [cli] Session org binding and key-material lifetime, after C1.
  - SessionStore records `orgId`. `grantCek` and `sessionForExec` refuse another org with `EXECUTOR_SESSION_UNKNOWN`.
  - The capability self-check (packages/cli/src/services/serve/auth.ts:139-168) tolerates an issued token with no creator.
  - MU4: a loopback test runs `machine status` against a fake machine under an fs-write spy and asserts no write of a private key, known_hosts or config bytes outside a per-request 0700 directory removed in `finally`.
  - Two sessions of two users in one process never share a config cache entry.
    (ticked) 2026-10-26T15:56:13Z by d778be9d: 1841a2ea: packages/cli/src/services/serve/sessions.ts ownedBy binds sessions to user and org; cd packages/cli && npx vitest run src/services/serve/__tests__/session-org-binding.test.ts src/services/serve/__tests__/key-material-lifetime.test.ts src/services/serve/__tests__/session-unknown-code.test.ts rc=0; MU4: no key, known_hosts or config bytes written under the fs-write spy. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: packages/cli/src/services/serve/sessions.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/__tests__/session-org-binding.test.ts, packages/cli/src/services/serve/__tests__/key-material-lifetime.test.ts. Accept: `cd packages/cli && npx vitest run src/services/serve/__tests__/session-org-binding.test.ts src/services/serve/__tests__/key-material-lifetime.test.ts src/services/serve/__tests__/session-unknown-code.test.ts` exits 0.

### Tooling, e2e, docs

- [x] T1 [ops] `rediacc_ci.ops.executor_orgs`, which reads a target's D1 through `wrangler d1 execute --json`.
  - `list` prints entitled orgs with id prefixes only.
  - `verify --org A --org B` checks both are entitled.
  - `block` and `unblock` call the root route through the deploy-proxy profile.
  - Tests use a fake wrangler.
    (ticked) 2026-10-26T13:27:15Z by d778be9d: 4ec78ace: .ci/rediacc_ci/ops/executor_orgs.py list, verify, block, unblock; .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_ops_executor_orgs.py rc=0 (20 passed). DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88; the rest of that plan is live and post-merge
  
  -- Owns: .ci/rediacc_ci/ops/executor_orgs.py, .ci/rediacc_ci/tests/test_ops_executor_orgs.py. Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_ops_executor_orgs.py` exits 0.
- [ ] E1 [e2e] `27-91-live-two-orgs.test.ts`, skipped unless `LIVE_CONSOLE_ORIGIN` is set.
  - It logs in as the org-A member and then the org-B member from the `live-console` profile, unlocks each org's config, and runs `machine status <machine>`.
  - It asserts success and no mock warning, and asserts two `cli.command` rows with distinct org ids naming each user.
  - It replays org A's X-Config-Session in org B's exec and asserts 404 `EXECUTOR_SESSION_UNKNOWN`.
  - The profile gains the four names only.
  
  -- Owns: private/account/e2e/tests/27-console/27-91-live-two-orgs.test.ts, .ci/config/secret-supply.json (live-console profile). Accept: `cd private/account/e2e && npx playwright test --list | grep 27-91` matches, the spec is skipped without `LIVE_CONSOLE_ORIGIN`, and `npm run check:ci-secret-supply` exits 0.
- [x] X1 [docs] Documentation and relations.
  - The private/account CLAUDE.md console section: per-org issuer, route, probe, the entitlement gate, block, and no ROOT_EMAIL ownership.
  - docs/observability/signals/proxy.md: the per-org Durable Object, the capacity outcome.
  - The deploy skill paragraph.
  - PLAN-proxy-cd-six-targets: Decision 2 and Context item 3 point here as superseded.
    (ticked) 2026-10-26T16:46:39Z by d778be9d: 24da2fcc and account e0fabe05: private/account/CLAUDE.md console section, docs/observability/signals/proxy.md per-org Durable Object and cap of 25, .claude/skills/deploy/SKILL.md executor paragraph, and superseded lines in agent/plans/PLAN-proxy-cd-six-targets.md Decisions 1-2 and Context item 3; npm run check:ci-prose-style rc=0; grep -n PLAN-console-executor-multi-org on agent/plans/PLAN-proxy-cd-six-targets.md and private/account/CLAUDE.md matches both. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: private/account/CLAUDE.md, docs/observability/signals/proxy.md, .claude/skills/deploy/SKILL.md, agent/plans/PLAN-proxy-cd-six-targets.md (relation lines only). Accept: `npm run check:ci-prose-style` exits 0, and `grep -n 'PLAN-console-executor-multi-org' agent/plans/PLAN-proxy-cd-six-targets.md private/account/CLAUDE.md` matches both.

### Live rollout (each box records account and proxy version ids before and after, the D1 bookmark taken before migration 0066, smoke rc, the rollback command, and the two-org end-to-end result)

- [x] ML0 [live] Bench.
  - Run deploy_bench (migration 0066), then `deploy_proxy --target bench --record`.
  - Provision orgs A and B (PROFESSIONAL, live subscription, config store) and record MU5.
  - Run E1 against bench.
  - Drills: org B is blocked and refused while org A runs, then unblocked; a downgrade to COMMUNITY gets 403 with reason plan; a fourth concurrent org (the bench ROOT org plus A, B and a third) gets 503 `EXECUTOR_CAPACITY`, recording MU2.
    (ticked) 2026-10-26T22:51:16Z by d778be9d: E1 against https://bench.rediacc.com exited 0 (1 passed, 1.7m; orgs 08103c52 and 61fa8f2c, cli.command aec41c73 and da74e5fd, replay 404 EXECUTOR_SESSION_UNKNOWN); executor_orgs verify rc0; two executor:bench:eu: issuer keys; drills recorded in the ML0 notes. DEPS-WAIVED: this plan depends only on PLAN-proxy-cd-six-targets boxes P1 and M1, both ticked in f2875e88
  
  -- Owns: agent/plans/PLAN-console-executor-multi-org.md (Live records). Accept: E1 against `https://bench.rediacc.com` exits 0; `executor_orgs verify` exits 0; `SELECT count(*) FROM api_tokens WHERE issuer_key LIKE 'executor:bench:eu:%' AND revoked_at IS NULL GROUP BY issuer_key` on the bench D1 shows two keys; and each drill's observed code is recorded.
- [ ] ML1 [live] edge-eu through the deploy skill's local path, which runs the CD modules. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: the edge-eu row has smoke rc 0 and E1 against `https://edge-eu.rediacc.com` exits 0 with two org ids.
- [ ] ML2 [live] edge-us, as ML1. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: as ML1 for edge-us.
- [ ] ML3 [live] edge-asia, as ML1. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: as ML1 for edge-asia.
- [ ] ML4 [live, post-merge] The first CD edge run after merge. Its three job records, plus E1 per edge region. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: three deploy jobs succeed with smoke rc 0, and E1 exits 0 for each edge origin.
- [ ] ML5 [live, post-merge] stable-eu, stable-us and stable-asia through promote-stable. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: each stable row has smoke rc 0, and E1 against `https://eu.rediacc.com`, `https://us.rediacc.com` and `https://asia.rediacc.com` exits 0 with two org ids each.
- [ ] ML6 [ops, post-merge] Capacity watch. A Grafana query of the per-target count of `rediacc.proxy.outcome=capacity` over 14 days goes to the Live records, and the decision on raising max_instances goes to the operator with that number. -- Owns: agent/plans/PLAN-console-executor-multi-org.md. Accept: the Live records carry the 14-day count for each of the six targets and the ASKED line or the "no capacity refusals" record.

### Order and parallel writers

- Wave 1: A1; C1; T1; W1 once P1 of the six-targets plan has ticked.
- Wave 2: A2 after A1; A5 after A1; C2 after C1; A4 after A1 and six-targets M1.
- Wave 3: A3 after A2; W2 after A2 and W1; U1 after A4; E1.
- Note on box ML6 (box text is a signature and is unchanged): its "decision on raising max_instances" is answered by Decision 3, the cap is already 25 per target, so ML6 records the 14-day capacity count and the container spend read from `cf_usage_report` against the budget.
- Wave 4: X1. The live boxes run ML0 to ML3 before merge and ML4 to ML6 after merge.

## Live records

| Target | Account version (before, after) | D1 bookmark (before 0066) | Proxy version (previous) | Smoke rc | Rollback | Org A run | Org B run |
|---|---|---|---|---|---|---|---|
| bench (ML0, 2026-10-26, in progress) | before 79503958 (inferred from `wrangler versions list`, not captured before the deploy), after d8a1ae5a (86b729f4 version_upload + Secret Change); migration 0066_console_executor_multi_org.sql applied, root seed a no-op | 000000d2-00000000-00005110-632bc78b3f4cad1aac09cd46b641039c; restore: `npx wrangler d1 time-travel restore account-db-bench --bookmark=000000d2-00000000-00005110-632bc78b3f4cad1aac09cd46b641039c --config wrangler.bench.toml` (from workers/account) | 64367c0d-0a0b-4351-a4fa-c97aa3c2d221 -> 45e83ade-fb8b-42a6-8b34-83db7468eee9 (image digest 494f7de2 -> b5d3105f) | proxy 0 (/v1/health 200, /v1/server-info 401 unauthenticated, /v1/ready 200); account deploy_bench rc 0 | proxy: `npx wrangler rollback 64367c0d-0a0b-4351-a4fa-c97aa3c2d221 --config workers/proxy/wrangler.bench.toml` | org 8d737fac (A): `executor_orgs verify` entitled; `/console/exec` as A reaches the executor in all three drill phases (404 "no config key yet", no key grant made); 1 `executor:bench:eu:8d73...` issuer key | org ae098e01 (B): verify entitled; blocked -> 403 CONSOLE_NOT_ENTITLED reason "blocked"; unblocked -> reaches executor again (see 401 note); issuer key `executor:bench:eu:ae09...` |

ML0 notes (2026-10-26, session d778be9d, in progress, not ticked):

- **MU5 (provisioned through real routes, `/test/*` is off on bench).** Path: `POST /auth/register` (Turnstile off on bench) for two users; root login (ROOT_EMAIL, BENCH_ROOT_PASSWORD from the deploy-bench profile) plus elevation through `/auth/reauth` with the link read from `captured_emails` via wrangler d1; `DELETE /admin/subscriptions/:id` on the auto COMMUNITY sub, then `POST /admin/subscriptions` PROFESSIONAL; per user: login, elevation, `/auth/2fa/setup` + `/auth/2fa/enable`, elevation, `POST /configs/setup` with a password slot, X25519 identity and random orgPassphrase built as `web/src/lib/config-setup-material.ts` does (script /tmp/ml0/ml0.mts, discarded; no secret persisted). Org A 8d737fac (store created by the first run, which then failed on a wrong table name in its own lookup query), org B ae098e01 (user e17474dc, store 1abe1b17). Bench now has 9 orgs, 2 entitled. `executor_orgs verify --target bench --org 8d737fac --org ae098e01` rc 0.
- **Token Accept query.** `api_tokens` rows with `issuer_key LIKE 'executor:bench:eu:%'` group into two keys (`...:8d73...` and `...:ae09...`).
- **Block/unblock drill** (`executor_orgs block|unblock --target bench --org ae098e01`, rc 0 each; `POST /console/exec` with `machine status`): B blocked -> 403 `CONSOLE_NOT_ENTITLED`, reason `blocked`, in the very next request; A in the same window -> reaches the executor (404 "This session has no config key yet"). A real command run needs a CEK grant, which was not made, so "A works" is proved to the executor boundary only.
- **Finding (not fixed).** After `unblock`, B's `/console/exec` answered 401 "The executor could not verify this token with the account server (401)" in 2 of 8 probes (one in two separate drill runs, roughly 20 s after unblock), the others reaching the executor. It self-clears within a minute. Likely a stale revoked token cached by the executor or another isolate after block revoked the org's issued tokens; needs a look at the executor's token cache invalidation.
- **Not drilled:** capacity overflow (cap 25 per target, needs many orgs; MU2 stays unproven); plan downgrade to COMMUNITY (403 reason plan); cross-org session replay (needs a real granted session).
- **Live-console member logins:** `.ci/config/secret-supply.json` profile `live-console` binds only `ROOT_EMAIL > LIVE_CONSOLE_EMAIL`; no login secret is stored, so no bws credential exists for a portal console member login. The throwaway ML0 users' passwords were discarded.
- **E1:** not runnable. `private/account/e2e/tests/27-console/27-91-live-two-orgs.test.ts` does not exist (only 27-90-live-executor.test.ts).
- **Round 2 (2026-10-26), proxy fix b2e7fe97.** Proxy redeployed to bench: 45e83ade -> 8a49f637, smoke rc 0, rollback `npx wrangler rollback 45e83ade-fb8b-42a6-8b34-83db7468eee9 --config workers/proxy/wrangler.bench.toml` (record /tmp/ml0-proxy2.json).
- **Block/unblock repeated on ae098e01 (B), 10 probes at 4 s spacing after unblock:** 0 of 10 were 401 (all reached the executor, 404 \"no config key yet\"); blocked probe 403 `CONSOLE_NOT_ENTITLED` reason `blocked`. The 401 finding is closed on bench.
- **Downgrade drill:** root `PUT /admin/subscriptions/d74566be` planCode COMMUNITY -> 200; B's next two `/console/exec` -> 403 `CONSOLE_NOT_ENTITLED` reason `plan`. PUT PROFESSIONAL -> 200; B reaches the executor again (404 \"no config key yet\", twice).
- **Two-org end-to-end, headless (the spec's flow without a browser).** Fresh orgs C 51fee6dd and D db8c574d (own users, PROFESSIONAL, password-slot stores sharing one store password, a pushed config with machine `ml0-host`): `POST /console/session` 200 and CEK grant 200 for each, two distinct session ids; `/console/exec` as each answers 200 from its own executor. Cross-org replay: D sending C's `X-Config-Session` -> 404 `EXECUTOR_SESSION_UNKNOWN` (drill met). D1 afterwards: live `executor:bench:eu:` issuer keys for 51fee, 8d737, ae098 (2 live) and db8c5; one `cli.command` row per org (51fee6dd, db8c574d), distinct org ids; `executor_token.issued` rows per org.
- **E1 verdict: not feasible on bench as the spec stands; three pieces fail.** (1) `machine status` returns success:false \"Fetching status from ml0-host failed\": the executor really SSHs, and bench has no SSH host reachable from a Cloudflare container with a key a bench store may hold (an ops VM is private; hostinger is a production host, and putting its key in a bench store was not authorized). (2) 27-91's `apiLogin` is a password-only login, but `POST /configs/bootstrap-session` (the unlock) requires `totpEnabled` (`requireTwoFactor`, private/account/src/routes/configs.ts:705), so every unlockable user answers a 2FA challenge on login and `apiLogin` gets no cookies; the spec needs a TOTP-aware login (secret from the store of seeds) or a cookie-injection path. (3) The replay step posts `{ pathKey, params:{name} }` with no `contractVersion` and no `positionals`, so the Worker answers 400 \"Malformed console exec request\" before the session check, never the expected 404 `EXECUTOR_SESSION_UNKNOWN`; the body must be `{ contractVersion, pathKey, params: {}, positionals: { name } }`. Not stored in bws: no member logins were persisted, because the spec cannot pass with them. Names the lead would add to the `live-console` profile once (1)-(3) are fixed: LIVE_CONSOLE_ORG_A_EMAIL, LIVE_CONSOLE_ORG_A_PASSWORD, LIVE_CONSOLE_ORG_B_EMAIL, LIVE_CONSOLE_ORG_B_PASSWORD, LIVE_CONSOLE_ORG_A_TOTP_SECRET, LIVE_CONSOLE_ORG_B_TOTP_SECRET, LIVE_CONSOLE_STORE_PASSWORD, LIVE_CONSOLE_MACHINE, LIVE_CONSOLE_D1_DATABASE (all `required`), with the entries created in ci-shared through bws-write.ts `op: create` (store-from-env refuses to create).
- **MU2 capacity drill (round 3).** Scratch config `/tmp/ml0cap/wrangler.bench.toml` (the committed file with max_instances = 3 and absolute main, image and build-context paths, since `deploy_proxy` takes no path and the staged image in workers/proxy/stage was reused), deployed with `wrangler deploy --config` under the deploy-proxy-bench profile, rc 0: version 8a49f637 -> cad2553f. Four concurrent `/console/exec` calls, one per entitled org A 8d737fac, B ae098e01, C 51fee6dd, D db8c574d, 4 rounds 5 s apart: orgs A, C and D got in every round (404 \"no config key yet\", i.e. they reached a running executor); org B got **503 `EXECUTOR_CAPACITY`** in all 4 rounds. The cap binds at 3 as the plan expects, and MU2's error is the proxy's own coded 503 (a catchable refusal, no queueing or eviction visible). The bench ROOT org was not used: it holds a COMMUNITY subscription, so the entitlement check would have refused it with 403 before any container start; four entitled orgs stood in for the fifth.
- **Finding (not fixed, no code changes allowed this round): the Retry-After is lost.** The 503 as seen by the browser-facing account Worker carried `Retry-After: null`. `workers/proxy/src/index.ts:224` sets `retry-after: 30`, but `relayedFailure` in `private/account/src/routes/console.ts:221-236` rebuilds the response from the body only and drops upstream headers, so the portal never sees the 30 s hint. The 30 itself was not observed on the wire (the proxy is not reachable without an executor token); it is read from the source.
- **Cap restored.** Committed `workers/proxy/wrangler.bench.toml` (max_instances = 25) redeployed with `wrangler deploy --config wrangler.bench.toml` (rc 0): version cad2553f -> 41ed108c; `deploy_proxy --target bench --smoke-only --record /tmp/ml0-proxy3.json` rc 0 (/v1/health 200, unauthenticated /v1/server-info 401, /v1/ready 200 on 41ed108c). Rollback: `npx wrangler rollback cad2553f-9725-4d43-b121-e4fa82f0da5c --config workers/proxy/wrangler.bench.toml` (that is the cap-3 version; the cap-25 version before the drill is `8a49f637-449c-4f2d-aa51-b628fd944c2b`). The cap-25 value was applied from the committed file and not read back (`wrangler containers list` does not show max_instances, and the application showed state `provisioning` right after the deploy).
- **Round 4 (2026-10-26), E1 against bench passes.** The #900fdadc default ran after its 120-minute window: a dedicated ed25519 probe key (comment rediacc-live-console-probe-2026-10-26, fingerprint SHA256:73fR5Z5qJD7qXaiHd5ACIv+zg0R+b14WCjs0KEyVm+U) authorized on hostinger with `from="104.28.0.0/16",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty,no-user-rc` (Cloudflare container egress, observed 104.28.154.80 and 104.28.163.155; a refusal from elsewhere was confirmed). Fresh orgs A 08103c52 and B 61fa8f2c (PROFESSIONAL, 2FA, one shared store password, a pushed config holding machine hostinger with that key). The logins live in bws ci-shared as the live-console profile names. E1 (`27-91-live-two-orgs.test.ts`, chromium, the out-of-tree settings later committed as `private/account/e2e/playwright.live.config.ts`) exited 0: 1 passed in 1.7m, cli.command rows aec41c73 (org 08103c52) and da74e5fd (org 61fa8f2c), and the replay answered 404 EXECUTOR_SESSION_UNKNOWN. Revoke: `REDIACC_ALLOW_GRAND_REPO='*' ./rdc.sh --config eu-remote term connect hostinger -c "sed -i '/ rediacc-live-console-probe-2026-10-26\$/d' ~/.ssh/authorized_keys"`, then delete bws LIVE_CONSOLE_PROBE_SSH_KEY.

## Decisions taken as defaults (open to operator veto)

1. **One container per org, not one shared multi-tenant process.** Several orgs' CEKs, decrypted configs, SSH pools and renet children would share one address space in a shared process, and any bug in dispatch, the request-context scoping or ssh2 would expose every tenant. The per-org container makes the org boundary a process boundary, and the Durable Object already gives per-tenant placement (workers/proxy/src/index.ts:203, :243). The cost is capacity (item 3).
2. **The Durable Object key is the org alone**, dropping the team. The org holds one CEK, so a per-team container isolates nothing cryptographically, and it would divide a 3-instance cap further.
3. **max_instances is 25 per target, a demand-sized cap with a cost alarm** (operator ruling ASKED:2026-10-26T15:26Z "Per-org, raise the cap (Recommended)", superseding the 3-per-target cost ruling ASKED:2026-10-25T19:08Z for max_instances). One container per org stays, idle orgs sleep after 2 minutes, and a 26th concurrent org on one target gets the coded, retryable 503. The cost bound moves from the instance cap to the alarm: `check_proxy_cost_guard.py` holds 25 per config and 175 in total, and the weekly `cf_usage_report` exits 1 naming the estimated cost when a target's container memory GiB-seconds or active vCPU-seconds pass the budget in `.ci/config/cf-spend-guard.json` (Cloudflare has no usage alert for Containers). ML6 now measures capacity refusals and container spend against that budget.
4. **The issuer takes `orgId` from the proxy Worker.** It trusts the Worker to name it only because the G2 gate of the six-targets plan lets only workers/proxy configs bind `ExecutorIssuer`, and because the org came from `route(bearer)` on the same binding. An org-bound routing ticket signed by the account Worker was considered and not taken: the egress renews tokens when no caller request is present, so a ticket would need its own renewal for no added boundary. The proxy Worker is already trusted with every caller's bearer.
5. **Issued tokens have no creator.** The authority to act for a user is the live grant that user's bearer recorded, so no owner's role, and no ROOT_EMAIL, can stall or widen the executor.
6. **Entitlement is the plan's `webConsole` flag** plus a live subscription and a store that can issue executor tokens. There is no per-org opt-in flag, only the root block switch.
7. **Per-org limits:** 60 execs and 20 session opens per minute per org at the account Worker, and binding buckets keyed on the issuer key with a per-org ceiling.
8. **The capacity and entitlement refusals are 503 `EXECUTOR_CAPACITY` and 403 `CONSOLE_NOT_ENTITLED`**, kept distinct from the region-level 503 `CONSOLE_EXECUTION_UNAVAILABLE`, so a user can tell "this region is off" from "not entitled" from "busy".

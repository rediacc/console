# remote-mcp: verified context

Read against the tree on 2026-11-20; each citation is a hypothesis a writer re-reads before relying on it. Paths are repo-relative. `CLI` = `packages/cli/src`, `ACC` = `private/account/src`, `SH` = `packages/shared/src`, `PX` = `workers/proxy/src`. Items the 2026-11-20 re-read could not confirm carry "unverified".

## 1. Executor and proxy request path

- **Two executor tiers, one artifact.** `rdc serve --mode container` runs in an org-keyed Cloudflare Container and starts with no key; `--mode daemon` runs on a customer host with its own enrollment (CLI/commands/serve.ts:1-20). The container image runs `node cli-bundle.cjs serve --mode container --port 8080` (workers/proxy/Dockerfile, final `CMD`).
- **Wire routes** are `/v1/command`, `/v1/health`, `/v1/server-info`, `/v1/session`, `/v1/session/:id/cek`, `/v1/jobs/:id/poll`, `/v1/jobs/:id/cancel` (SH/cli-contract/wire.ts:348). No MCP route exists anywhere in `CLI/services/serve/`, `PX/` or the Dockerfile.
- **The MCP server is deliberately not proxyable**: local-effect commands, "the MCP server" among them, are refused at dispatch (CLI/services/serve/command-dispatch.ts:157-180).
- **Worker routing.** `/v1/health` and `/v1/ready` answer without auth; everything else goes through `resolveTenant` (PX/index.ts:127), which calls the account `ExecutorIssuer.route()` (ACC/services/executor-issuer.service.ts:118) on every request with no cache.
- **One Durable Object per org and placement**, `executorName(orgId, placement)` (PX/placement.ts:13). The comment at CLI/services/serve/sessions.ts:68 still says "org:team": stale.
- **Container lifecycle.** `sleepAfter = '2m'` (PX/org-executor.ts:96), `enableInternet: true` (PX/org-executor.ts:511), code-level caps `HARD_CAP = 25`, `HARD_HEAVY_CAP = 5` (PX/capacity.ts:12, :14).
- **Issued executor tokens** live 45 minutes (ACC/services/executor-issuer.service.ts:27), renewed at 0.8 of life (PX/issued-token.ts:37), cached for at most 64 orgs per isolate (PX/issued-token.ts:73).
- **IP allowlist** is one deployment-wide `ALLOW_IPS` list checked against `cf-connecting-ip` (PX/ip-allowlist.ts:4, :50). Out of scope per D2.
- **`/v1/ready` discloses aggregate executor occupancy** without auth; the trade is documented as accepted (PX/ready.ts:8).
- **Daemon** listens on `0.0.0.0` by default (CLI/commands/serve.ts:55) and serves plain HTTP through `honoServe` (CLI/commands/serve.ts:112). The web console reaches executors only through one deployment-wide binding or `EXECUTOR_URL` (ACC/routes/console.ts:97-108).
- **Job attach window** is 20 s (CLI/services/jobs/attach.ts:23).

## 2. Key custody and executor sessions

- **Container mode needs a CEK grant per session.** The client opens `POST /v1/session`, the executor returns an ephemeral X25519 public key, and the client seals the CEK with `cekHandoffEncrypt` (SH/config-crypto/handoff.ts:43; HKDF info `rediacc-cek-handoff-v1` at :22). The browser path relays it through `POST /console/session` and `/console/session/:id/cek` (ACC/routes/console.ts, routes near the `EXECUTOR_SESSION_UNKNOWN` relay list at :55-61).
- **Session TTL** is 30 minutes idle (CLI/services/serve/sessions.ts:32); keys live in RAM only and die on the 2-minute sleep, a redeploy or an OOM exit.
- **One grant per (org, user)**: `grantsByUser` (CLI/services/serve/sessions.ts:74, set at :146). A second grant silently replaces the first.
- **The container config cache is keyed by session only** (CLI/services/serve/container-config.ts:113) and the config is picked from the first principal's team (:118). A team-B request of the same user can be served team A's config. The cache is never revalidated.
- **Executor grant TTL is fixed at 30 minutes** (ACC/services/config.service.ts:396) while sessions slide.
- **The browser re-grants on `EXECUTOR_SESSION_UNKNOWN`** (ACC/routes/console.ts:55-61); the CLI `--proxy` client caches its grant per process only (CLI/services/executor/proxy-client.ts:116, `ensureSession` at :168) and has no handler for that code (the only CLI reference is its definition, CLI/services/serve/sessions.ts:289), so every run repeats the key exchange.
- **The hosted tier requires a server-recoverable org passphrase** (`ISSUER_STORE_UNSUPPORTED`, ACC/services/executor-issuer.service.ts:45, :102; store check at ACC/services/config.service.ts:1341).
- **`cekWrap` binds no AAD** (SH/config-crypto/cek.ts:60), so any new slot type must bind its context in the HKDF info.

## 3. Config storage, encryption layers, push protocol

- **Three layers** (docs/DESIGN-CONFIG-STORAGE.md:224): SDK (time-windowed, server-derived), CEK (client-held, wrapped per slot), org passphrase (server-applied). The security claim is in the same file at :16.
- **Storage**: blob in R2 per region (`configs-{eu,us,asia}`), pointer, version and plaintext envelope in D1; each push writes a new key; 50 versions kept (docs/DESIGN-CONFIG-STORAGE.md, "Storage Architecture: D1 + R2").
- **Push** (docs/DESIGN-CONFIG-STORAGE.md:521): `POST /configs/session` returns `sdk_derived` and `serverSecret`; `PUT /configs/:id` carries version, blob, blinded commitments and tombstones; the server checks commitment continuity (ACC/services/config.service.ts:726, function at :3078) and compare-and-swaps the row (`pushConfig` at :595).
- **The push route checks only token and org membership**: `configTokenAuth()`, `configWriteCap`, `requireOrgMembership()` (ACC/routes/configs.ts:1514-1520).
- **Executor config tokens are read-only**: 403 `read_only_token` (ACC/routes/configs.ts:369-376).
- **Slots are unique per (store, user, method)** (ACC/db/config-schema.ts:123), so an agent slot cannot be a fourth method row for the same user without a schema change.
- **Stale comment**: "24h sliding expiration" (ACC/db/config-schema.ts:295) against 7 days in code and doc.
- **Passkey PRF**: the design doc calls PRF a hard requirement and notes Bitwarden and Windows Hello lack it (docs/DESIGN-CONFIG-STORAGE.md:644, :653); password and recovery slots exist in code, so that section is stale.

## 4. Config writes the hosted executor drops

- **Writes in a container dispatch stay in memory and are discarded** (CLI/services/core/request-context.ts:115). `isRemoteConfigFile` short-circuits to false under a request-scoped config (CLI/services/config/synced-write.ts:33). Version-bumping writes are only counted (CLI/adapters/config-file-storage.ts:69, read at CLI/services/serve/command-dispatch.ts:456).
- **The command still succeeds**; the only sign is a stderr warning (CLI/services/serve/server.ts:382). `requestScopedConfig` applies only in container mode (CLI/services/serve/server.ts:439).
- **`repo create` generates the LUKS credential into config** (CLI/commands/repo-create-delete.ts:239) inside `registerNewRepo` (:202), which runs before `runCreateJob` (:89, called at :311). Through the container tier the key is lost within about 2 minutes while the encrypted volume exists on the host. `rollbackCreateRepo` is at :44.
- **Siblings with the same loss**: `repo fork` (config entry), `repo delete` (removal), network-ID allocation, `machine provision` (VM not recorded). Proxy capability of each is `true` in SH/cli-contract/data/contract.json (checked 2026-11-20 for repo create, fork, up, delete, push, pull, machine provision, machine setup).

## 5. Policy storage and the member rewrite hole

- **Policy is `/policy` inside the encrypted config** (SH/config-schema/schemas.ts:596, schema import at :21), registered as one committed leaf (SH/config-schema/sensitivity.ts:91; `/access` at :94).
- **Schema**: `allowGrandRepos` and `allowClusterOps` are booleans (SH/policy/schema.ts:67, :69); grand-repo denial at SH/policy/evaluate.ts:147.
- **Editors**: the account web Permissions page (owner/admin gate in the UI only) previews with `evaluatePolicy` and saves through the config-session push (private/account/web/src/pages/console/Permissions.tsx:5-16). `ConfigEditor.tsx` in the same folder edits the whole document. No CLI command edits policy.
- **The hole**: any member with config write access can push a config with a rewritten `/policy`; the server enforces no role on that path (ACC/routes/configs.ts:1514-1520) and cannot see which committed value changed (blinded keys, fresh `fckSalt` per push, docs/DESIGN-CONFIG-STORAGE.md "Envelope v3").
- **Only the executor evaluates policy**: `evaluatePolicy` is called in CLI/services/serve/policy.ts and nowhere else in the CLI; `authorize` is at CLI/services/serve/policy.ts:108.
- **`teamSlug` is never passed**: the call at CLI/services/serve/server.ts:226-239 omits it, while CLI/services/serve/policy.ts:99, :116 accept it.

## 6. Local and remote guard mismatch

| Aspect | Local MCP (CLI/commands/mcp/tools.ts) | Executor (CLI/services/serve/policy.ts) |
|---|---|---|
| Permission source | `REDIACC_ALLOW_GRAND_REPO`, ancestry-checked | `allowGrandRepos` in `/policy` |
| Granularity | repo list or `*` | boolean |
| Org policy | not evaluated | evaluated |
| Repo not found or config error | proceeds (`return null`, tools.ts:77) | treated as grand, fails closed |
| No repo argument | no guard (`applyGrandRepoGuard`, tools.ts:132) | treated as grand |
| Always-grand commands | none | `MUTATES_GRAND_BY_DEFINITION` = `repo promote` (policy.ts:173) |
| Ops-VM fleet | exempt (`guardNamedRepo`, tools.ts:111) | not exempt |
| Enforcement point | MCP layer, then the CLI agent guard in the child | executor gate; CLI agent guards are inert there (CLI/utils/agent-guard.ts:78, :102) |

- **Annotation bug**: `readOnlyHint: !tool.isDestructive` (CLI/commands/mcp/tools.ts:177) marks non-destructive writes read-only.
- **No cluster-ops guard on the executor side** besides the policy flag (unverified that none exists elsewhere).

## 7. REDIACC_ALLOW_CONFIG_EDIT

- **What it unlocks**: `rdc config edit` / `--apply` for agents when the scope is `*` (CLI/commands/config/edit.ts:543; refusal at :65), and a bypass of the knowledge gate on sensitive pointers (CLI/services/core/mutation-gate.ts:104, :111). Scope read at CLI/utils/agent-guard.ts:124.
- **Dangers**: self-escalation (policy lives in the config), silent data loss (dropping a repo entry drops its LUKS key), drift between config and hosts, a local-only audit trail (`audit.log.jsonl`, single rotation at 10 MB, CLI/services/core/audit-log.ts:4-5), and an ancestry check that is weaker off Linux and meaningless remotely.
- **Footprint**: 76 occurrences in CLI and shared source including tests and locales (count from `git grep -c`, 2026-11-20 session).

## 8. Executor and auth gaps

- **Introspect** (ACC/routes/proxy.ts:62 onward) returns `active: true` when the creator has no org role (`orgRole ?? undefined`, :100-126), ignores the presented token's IP binding (`validate()` is a pure read, :50, :84) and returns no `expiresAt` (ACC/dto/proxy.dto.ts:23-42). The verifier caches 60 s past expiry (CLI/services/serve/auth.ts:20) in an unbounded `Map` (:90).
- **Rate limiter** is an in-memory map per isolate (ACC/middleware/rate-limit.ts:23); introspect limit 120/min (ACC/routes/proxy.ts:19).
- **Audit delivery failure is logged and the command still succeeds** (CLI/services/serve/audit.ts:36, :139).
- **Job terminal ledger is in memory**, capacity 10,000 per process (CLI/services/serve/job-poll.ts:213).
- **CLI login tokens carry no expiry** (ACC/services/device-code.service.ts:389, `undefined`); the plaintext token sits in `device_codes.token` until claimed (ACC/db/schema.ts:713).
- **Fable review gaps (2026-11-20)**: (1) cross-team config confusion, section 2; (2) stale per-session cache; (3) one grant per user; (4) slot table cannot hold agent slots and "any slot = active member" (ACC/services/config.service.ts:2314); (5) permissive introspect; (6) `teamSlug` never passed; (7) agent guards inert in the container, no executor cluster-ops guard; (8) fixed 30-minute grant TTL; (9) stale "24h" comment; (10) `repo create` order is correct, the credential is registered before the volume; (11) hosted tier needs the server-recoverable passphrase.

## 9. MCP tool surface

Derived 2026-11-20 by importing `COMMAND_METADATA` (CLI/config/command-metadata.ts) and joining `SH/cli-contract/data/contract.json`, skipping entries with `mcpExcludeReason` (98 such entries). 93 contract-derived tools; 49 proxy-capable, 44 not. The three hand-written tools in CLI/commands/mcp/custom-tools.ts (`machine_containers`, `machine_services`, `machine_repos`) are outside this count.

- **Proxy-capable (49)**: backup browse, cancel, list, restore, run, snapshot, status, verify; cluster snapshot list; datastore list, snapshot list, status; job cancel, dismiss, gc, list, logs, status; machine deprovision, gpu list, health, provision, restart-services, setup, status; repo admin fsck, cat, checkout, commit, create, delete, diff, down, exec, fork, gc, health, list, log, logs, merge, migrate, pull, push, replicate, replicate remove, status, trim, up.
- **Not proxy-capable (44)**: backup check (machine), immutability show (other), manifests (other), reconcile (other), repair (machine), retention (other), retention preview (other), strategy list (config), strategy show (config), toc-key sync (machine), undelete (other), usage (other); cluster kubeconfig (machine), cluster status (config); config access list, audit log, audit verify, current, list, prune, show (config), config reconcile (machine); credits, legal, version (other); feedback list, report, show (other); machine access show, add, infra cert status, infra show, list, provider add, provider list, provider remove, remove (config), machine converge, prune, scan-keys (machine); repo replicate status, secret get, secret list (config); server status (machine).
- **Docs drift**: `packages/www/src/content/docs/en/ai-agents-mcp.md` lists `machine_query`, `config_repositories`, `agent_capabilities`, `backup_push`, `backup_pull` and `term_exec`, none of which exist in the metadata.

## 10. In-memory-only records (D6)

| Where | Only copy in memory | Effect |
|---|---|---|
| CLI/services/core/request-context.ts:115 | container config writes | data loss, orphaned volumes and VMs |
| CLI/services/serve/audit.ts:139 | an undelivered audit event | a mutation with no audit record |
| CLI/services/serve/job-poll.ts:213 | terminal-event ledger | missing or duplicated final events after sleep |
| CLI/services/serve/sessions.ts:32 | granted CEK | CLI fails after sleep, no re-grant |
| CLI/services/serve/auth.ts:20 | token validity | revoked token works up to 60 s |
| ACC/middleware/rate-limit.ts:23 | rate counters | limits do not hold across isolates |
| CLI/services/core/audit-log.ts:4-5 | local config audit log | history lost at 10 MB rotation |

## 11. Production read, 2026-11-20

Read-only `SELECT`s through `rediacc_ci.core.bws_env exec --profile ops-health`; the scoped Cloudflare token minted for the run was destroyed.

| Region (D1) | Users | Non-Rediacc users | Orgs | Config stores |
|---|---|---|---|---|
| eu (`account-eu`) | not captured | 7 (1 in an org with a store) | 13 | 2: the operator's (1 config), `t11smoke...@maxxspace.com` (1 config, a Rediacc test account per D32) |
| us (`account-us`) | 6 | 2 (0 with a store) | 7 | 4: three `live-console-edge-us-*` test orgs (1 config each), the operator's (0) |
| asia (`account-asia`) | 4 | 1 (0 with a store) | 5 | 3: two `live-console-edge-asia-*` test orgs (1 each), the operator's (0) |

Every store has one member and one key slot; none sets `require_passkey`. Whether any config holds a `/policy` is not visible server-side.

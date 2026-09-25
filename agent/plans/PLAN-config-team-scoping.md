# PLAN: enforce config team scoping on the server, and decide on per-team cryptographic isolation

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-config-sync-hardening.md -- this plan is finding F19 of that plan, split out by operator ruling D8(a). Four links. (1) The new 403 on config-token routes must carry `newServerToken`, which that plan's T7 adds to every config-token error body. Without it, a refused request burns the caller's rotated token. (2) This plan's cross-team scenarios run in the harness that plan's T1 built (`private/account/tests/integration/config-sync/`). (3) Its T5 re-scopes `GET /:id/versions` to the store; this plan adds the team check to that same route. (4) Its T8 puts `teamId` into the v3 AAD, and section 4 here relies on that binding. Both plans edit `routes/configs.ts` and `config.service.ts`, so the commits here rebase onto writer A's T5 and T7.
Priority: P1 -- proposed by AI. Any config-store member who belongs to team X can today read, overwrite and delete team Y's config in the same org, and can decrypt what they read, because the CEK covers the whole store. The exposure is limited to people who are already org members and store members, and single-team orgs are unaffected. That makes it P1 rather than P0. It is still a broken access-control promise: `docs/DESIGN-CONFIG-STORAGE.md:200,212` states "Enforce team/org access control", and CLAUDE.md states "team scoping is server-side access control".
Concurrency: parallel. One writer (S) for the server and tests, plus the lead. S's Owns overlap writer A of PLAN-config-sync-hardening only in `routes/configs.ts`, `config.service.ts` and `config-token.ts`. S keeps its edits there to small hunks that call one new helper file, and rebases after A's T5 and T7 land. The CLI part (T7) is one error class plus i18n. It rides the console PR after the submodule PR.
Owns: private/account/src/utils/config-team-access.ts (new), private/account/src/routes/configs.ts (team-check hunks only), private/account/src/services/config.service.ts (listConfigs filter, token scope, executor grant filter hunks only), private/account/src/middleware/config-token.ts (scopeTeamId only), private/account/src/container.ts (configScopeTeamId variable only), private/account/src/db/config-schema.ts (config_tokens.scope_team_id only), private/account/drizzle/0056_config_token_team_scope.sql, private/account/drizzle/meta/** (0056 snapshot only), private/account/tests/integration/config-team-scope.test.ts (new), private/account/tests/integration/config-sync/team-scope.test.ts (new), private/account/tests/integration/config-sync/harness/teams.ts (new), private/account/tests/integration/config-sync/harness/device.ts (`teamId` enroll option only), packages/cli/src/adapters/remote-config-adapter.ts (403 mapping only), packages/cli/src/i18n/locales/*/cli.json (teamForbidden keys only), CLAUDE.md (config storage line only)
Worklist: (the lead adds this with worklist.py --add)

**Line numbers** are from console `64438d30b` and account `8fe80c2` (committed HEAD), read 2026-09-25. The account working tree has uncommitted edits from writer A, so some `config.service.ts` lines have since moved by about 6. Citations below use HEAD.

## Tasks

- [ ] T0 [lead] Get the operator's answers to E1-E5 (section 5). Freeze the authorization matrix in section 2.1 and the error contract (403 `{ error, code: 'team_forbidden', newServerToken }`).
- [ ] T1 [S] Harness support: `harness/teams.ts` provides `addTeam(fixture, name)`, `addOrgMember(fixture, { role, teams: [{ teamId, role }] })` and `removeFromTeam`. It inserts `teams`, `org_memberships` and `team_memberships` rows directly, and gives the member an identity plus a slot under the fixture CEK, so the member counts as a store member. `enrollDevice` gains a `teamId` option that lands in `remote.teamId`.
- [ ] T2 [S] Scenarios H19-H25 (section 3.2) in `config-sync/team-scope.test.ts`. Each one that reproduces today's gap starts as `it.fails` with `F19` in its title. The controls start as plain `it`. The route-level matrix goes in `tests/integration/config-team-scope.test.ts` (section 3.1), with the same `it.fails` rule.
- [ ] T3 [S] `src/utils/config-team-access.ts`: `authorizeConfigTeam(services, { orgId, userId, teamId, scopeTeamId, action })` returns the resolved `teamId | null` or throws `ConfigTeamForbiddenError`. It also provides `accessibleTeamIds(services, orgId, userId, scopeTeamId)`, which returns `'all' | Set<string>`, for listing. Both are built only on existing `orgService` methods (`getMemberRole` `org.service.ts:766`, `getTeamById` `:394`, `getTeamMembershipRole` `:574`) and follow the owner/admin bypass of `resolveUserTeam` (`:583-606`). Rules: section 2.1.
- [ ] T4 [S] Wire the check into every config-token route that names a config. Pull `GET /:id` (`configs.ts:998-1046`) and push `PUT /:id` (`:1048-1131`) call the helper before touching the service. `GET /` (`:1135-1151`) filters through `accessibleTeamIds`. `GET /:id/versions` (`:1153-1170`) resolves the entry's team after writer A's T5 and checks it. The 403 path returns `newServerToken`, reusing T7's helper from the parent plan. F19 H19-H22 flip to `it`.
- [ ] T5 [S] Session and api-token routes. `DELETE /:id` (`:1193-1204`) checks the team with `action: 'delete'` (E3). Password-enroll (`:850-950`) refuses a team-scoped api token whose user is not in that team, and a token whose team is in another org. It also stamps the token scope into the minted config token (T6). `mintExecutorSession` filters its `configs` list (`config.service.ts:1723-1730`) through `accessibleTeamIds`, and narrows further to the executor api token's team when it has one. `store-info` `configCount` (`configs.ts:447,454`) counts only the configs the caller can see.
- [ ] T6 [S] Token team scope (per E2). Migration `0056_config_token_team_scope.sql` adds nullable `config_tokens.scope_team_id` (FK `teams.id` ON DELETE CASCADE). `createToken` (`config.service.ts:863`) takes an optional `scopeTeamId`. `validateAndRotateToken` (`:916-1000`) copies it onto the rotated token and returns it. `mintDeviceToken` (`:899`) inherits the caller token's scope. `configTokenAuth` sets `configScopeTeamId` (`config-token.ts:61-65`, `container.ts:180-184`). The helper applies it as a narrowing on top of membership, never as a grant.
- [ ] T7 [S] Push and team integrity. The push `teamId` (`configs.ts:1083`) must name a non-archived team of the store's org. Today only the FK to `teams.id` constrains it (`config-schema.ts:202`), so a foreign-org team id is stored as is. H23 flips to `it`.
- [ ] T8 [S] CLI: `classifyFetchError` (`remote-config-adapter.ts`, the 401/409 mapper) maps 403 `team_forbidden` to a new `RemoteTeamForbiddenError`, with its message in 13 locales. On that error the read path neither serves nor keeps the offline cache for this config (E4). 403 already bypasses the cache fallback, because only `RemoteUnreachableError` is cache-served (`config-base.ts:178-218`). T8 adds the purge. H22's cache assertion flips.
- [ ] T9 [lead] Docs. The CLAUDE.md config storage line and `docs/DESIGN-CONFIG-STORAGE.md:200,212` (coordinate with the parent plan's T14, which owns that file) state the enforced matrix and the recorded crypto decision (E1).
- [ ] T10 [lead] Closure. H19-H25 and the route matrix are green with no `it.fails` left. The mutation controls table (section 3.3) has been run by hand, and each revert turned its named test red. The CI log of the account integration lane lists `config-team-scope.test.ts` and `config-sync/team-scope.test.ts` with non-zero test counts (testing skill). Live smoke on eu: an org with teams X and Y, where a plain member of X runs `rdc config remote enable` pinned to X, then tries `curl` pull, push and list against Y's config with their rotated token. Expected: 403, 403, and a list without Y.

## 1. The authorization gap, proven from code

**What authenticates a config-token request.** `configTokenAuth` (`middleware/config-token.ts:12-68`) resolves the token to `(storeId, orgId, userId, orgPassphrase)` and sets nothing else (`:61-65`). The `config_tokens` row has no team column (`db/config-schema.ts:266-293`). Tokens are minted per (store, user) by `createToken` (`config.service.ts:863-893`), which is called from `bootstrapSession` (`:1609`), `mintDeviceToken` (`:899`) and `mintExecutorSession` (`:1680`).

**What authorizes it.** Only `requireOrgMembership` (`middleware/require-org-membership.ts:18-32`), which checks `orgService.getMemberRole(orgId, userId)`: any org role passes. There is no team lookup on any config route. `grep teamMemberships src/routes/configs.ts` returns nothing.

**Read (pull).** `GET /:id` (`routes/configs.ts:998-1046`) takes `teamId` from the query string (`:1008`) and passes it to `pullConfig(storeId, configId, teamId)` (`:1011`). That function filters on `(configStoreId, configId, teamId-or-NULL)` only (`config.service.ts:715-730`). The handler then removes layer 3 (`:1014-1018`) and returns `server_secret` and `sdk_derived` (`:1020-1021`). A member of X who sends `?teamId=<Y>` receives Y's blob with every server-side layer stripped. The remaining layer is the CEK. It is one key per store (`config_key_slots` has no team column, `config-schema.ts:100-125`; CLAUDE.md: "One org-wide CEK encrypts every team's configs"). Every store member holds it, so the X member decrypts Y's config.

**Discovery.** `GET /` (`configs.ts:1135-1151`) returns `listConfigs(storeId)`, which filters on the store alone (`config.service.ts:761-775`). Every team's `configId` and `teamId` are listed. The portal editor (`web/src/pages/console/ConfigEditor.tsx:136`) and the handoff picker (`web/src/pages/ConfigRemote.tsx:306,512`) show them all. So the "caller must guess Y's ids" barrier does not exist.

**Write (push).** `PUT /:id` (`configs.ts:1048-1131`) passes `body.teamId` (`:1083`, DTO `dto/config.dto.ts:272`, a free string) to `pushConfig`. That function looks up the entry by the same caller-chosen triple (`config.service.ts:538-548`) and writes a new version. A member of X can overwrite Y's config. The only barrier is the version check. The overwrite is a normal new version in the history, attributed to the X member, which gives an audit trail but does not prevent it.

**Delete.** `DELETE /:id` (`configs.ts:1193-1204`) takes `teamId` from the query (`:1196`). It checks `requireStoreAccess(c, storeId)` with no role list (`:1200`), which means any org role (`:205-219`). It then hard-deletes every blob and row of Y's config (`config.service.ts:777-806`). Elevation is required. Team membership is not.

**Foreign team ids.** `config_entries.team_id` references `teams.id` only (`config-schema.ts:202`). Nothing checks `teams.org_id = config_stores.org_id`, so a push can file a config under another org's team id.

**Executor.** `mintExecutorSession` returns every config of the store (`config.service.ts:1723-1730`), whatever the target user's teams are.

**Password-enroll.** A team-scoped api token narrows only the choice of target config (`configs.ts:909-913`). The minted config token (`:935`, via `bootstrapSession`) is store-wide. Nothing checks that the token's user belongs to that team.

**Not a gap.** Store membership itself is owner-gated (`POST /members`, `configs.ts:1208-1256`, `requireStoreAccess(..., 'owner')`), and CEK rotation is owner/admin-gated (`:704-714`). So the exposure is limited to "org member who holds a store slot". Within that set, team boundaries are not enforced anywhere.

**Answer.** Yes. A store member of team X can list, read and decrypt, overwrite, and delete team Y's configs in the same org. Every step is proven above. H19-H22 and the route matrix reproduce it at runtime.

## 2. Server-side authorization fix

### 2.1 The rule

Given an org role, a team role and the config's `teamId`:

| Caller | `teamId = null` (org-level config) | `teamId = T` in the store's org | `T` archived | `T` in another org |
|---|---|---|---|---|
| org owner or admin | read, write, delete | read, write, delete | read only (E5) | 404 `team_not_found` |
| member with a `team_memberships` row in T | read, write; delete per E3 | read, write; delete if team_admin (E3) | 403 | 404 |
| member without a row in T | per E1b (default: read, write) | **403 `team_forbidden`** | 403 | 404 |
| token with `scope_team_id = S` | only if S's rule allows null (E2) | only if T = S, and the membership rule above also passes | as above | 404 |

Properties:
- **The check runs before any config lookup.** It depends only on `(orgId, userId, teamId, scope)`, never on whether the config exists. A 403 therefore reveals nothing the caller did not already send.
- **Membership is read on every request, never cached into the token.** Removing someone from team Y takes effect on their next request, with no token revocation. This matches how `requireOrgMembership` already handles org removal.
- **The owner/admin bypass copies `resolveUserTeam`** (`org.service.ts:583-606`), so config access matches the rest of the product. CEK rotation needs it: the rotating admin re-encrypts every team's config.
- **The team must belong to the store's org.** `requireTeamAccess` (`org.service.ts:608-616`) does not check this, so the helper does not use it.

### 2.2 Where each route is bound

| Route | Auth today | Bound to after the fix |
|---|---|---|
| `POST /session`, `POST /device-token` | config token plus org | Unchanged. They return store material, not config data. `device-token` copies the caller token's `scope_team_id` (T6). |
| `GET /:id` pull | config token plus org | Plus `authorizeConfigTeam(read)` on the query `teamId` |
| `PUT /:id` push | config token plus org | Plus `authorizeConfigTeam(write)` on `body.teamId`, and the team must be in the same org (T7) |
| `GET /` list | config token plus org | Filtered by `accessibleTeamIds` |
| `GET /:id/versions` | config token plus org | Store-scoped (parent T5), plus a read check on the entry's team |
| `DELETE /:id` | session, elevated, any org role | Plus `authorizeConfigTeam(delete)` |
| `POST /password-enroll` | api token (`config:enroll`) | The token's team must be the store org's, and the user must be in it. The config token is minted with `scope_team_id` = the api token's team. |
| `POST /executor-token` | api token (`proxy:exec`) | The grant's `configs` list is filtered to the target user's teams, narrowed further by the executor token's own team scope. The token it mints carries that scope. |
| `GET /store-info` | session | `configCount` counts only what the caller can see |
| rotation, members, slots, setup | session, owner/admin | Unchanged: store-wide by design |

### 2.3 Token binding (E2)

Config tokens stay bound to (user, store). Team access is evaluated live. An optional `scope_team_id` narrows a token that came from a team-scoped credential: the password-enroll api token, the executor api token, or a device token minted from a scoped token. A narrowing can never widen access. A scoped token is still refused when its user leaves the team. Tokens minted by the portal handoff (`bootstrapSession` through `/device-token`) are unscoped, because a human who is in several teams chooses among them in the picker.

### 2.4 The 403 contract

`403 { error, code: 'team_forbidden', newServerToken }` on config-token routes. `configTokenAuth` has already rotated and consumed the presented token by the time the team check runs, so the 403 must hand back the new token (the parent's T7). Otherwise the caller's chain dies with the refusal. Session routes return `403 { error, code: 'team_forbidden' }` through `AppError`, following the `codedConflict` pattern (`configs.ts:103-105`). An audit event `config.auth.team_forbidden` (data: `storeId`, `configId`, `teamId`) is logged through `eventLogService`, next to the existing `config.auth.*` events (`config-token.ts:33-45`).

## 3. Test strategy

### 3.1 Route matrix: `tests/integration/config-team-scope.test.ts`

This file is built like `config-org-scope.test.ts`: the real `createApp`, in-memory SQLite, `MemoryBlobStorageService`. Fixture: one org with teams X and Y, and four users:
- `owner`
- `admin` (org admin, no team rows)
- `mx` (member, team X only)
- `mxa` (team_admin of X)

Configs: `cX` (team X), `cY` (team Y) and `cOrg` (team null). Each config-token call uses a token from `service.mintDeviceToken`.

| Case | Expected | Starts as |
|---|---|---|
| mx pull cY | 403 `team_forbidden`, body has `newServerToken`, and the next call with it succeeds | `it.fails` (F19) |
| mx push cY v+1 | 403, cY version unchanged in D1 and R2 | `it.fails` |
| mx list | contains cX and cOrg, not cY | `it.fails` |
| mx DELETE cY (session, elevated) | 403, cY still present | `it.fails` |
| mx push with teamId = a team of another org | 404 `team_not_found`, no row | `it.fails` |
| mx `GET /:id/versions` for cY's entry | 403 (after parent T5) | `it.fails` |
| password-enroll with a Y-scoped api token for mx | 403 | `it.fails` |
| password-enroll with an X-scoped token for a user in X and Y, then pull cY with the minted token | 403 (scope narrows) | `it.fails` |
| executor grant for mx | `configs` lists cX and cOrg only | `it.fails` |
| **controls:** mx pull and push cX; owner and admin pull, push and list cY; mx pull cOrg (per E1b); mxa DELETE cX; pull of a missing config in team X is 404, not 403 | 200 / 404 | `it` |
| mx is removed from X mid-chain, then pulls cX with the rotated token | 403 | `it.fails` |

### 3.2 Harness scenarios: `tests/integration/config-sync/team-scope.test.ts`

These run the real CLI adapter, crypto, token storage and cache against the real server through `world.net`, as `adapter-roundtrip.test.ts` does. Setup comes from T1's `harness/teams.ts`.

- **H19 (F19, read).** Device A (owner, `teamId=Y`) pushes `seedConfig` to cY. Device B (mx, enrolled with `teamId=Y` in its pointer, same fixture CEK) calls `adapter.pull()`. Today B receives and **decrypts** A's config: the test asserts B's pull rejects with `RemoteTeamForbiddenError`, and starts as `it.fails`. A companion characterization `it` ("the CEK is store-wide: ciphertext obtained out of band decrypts") reads cY's blob straight from `world.blob`, has the server-side layers removed with the fixture keys, and decrypts it with B's unwrapped CEK. This test pins the documented property under E1(a). If E1 later picks per-team keys, it is flipped deliberately.
- **H20 (F19, write).** B pushes over cY. Expected: refused, and A's next pull still shows A's content at A's version. Starts as `it.fails`.
- **H21 (F19, discovery).** B's `GET /` through the adapter's list call does not contain cY. Starts as `it.fails`.
- **H22 (F19, revocation).** B, a member of X and Y, pulls cY successfully and the offline cache is written. B is then removed from Y (`removeFromTeam`). B's next pull gets `RemoteTeamForbiddenError`, B's token file holds the rotated token (the chain survives), and the cached copy of cY is gone (E4). Starts as `it.fails` until T4 and T8.
- **H23 (F19, foreign team).** B pushes a new config with a teamId from a second org created by `insertTestOrg`. Refused, and no `config_entries` row appears. Starts as `it.fails`.
- **H24 (control).** B, a member of X, round-trips cX: push, pull on a second device of B, and an edit visible to both. `it` from the start. This proves the fix does not break the normal flow.
- **H25 (control, admin).** An org admin with no team rows pulls and pushes cY. `it` from the start.

### 3.3 Mutation controls (run by hand in T10; each must turn its test red)

| Revert | Red test |
|---|---|
| Remove the `authorizeConfigTeam` call from `GET /:id` | H19, "mx pull cY" |
| Remove it from `PUT /:id` | H20, "mx push cY" |
| `GET /` returns `listConfigs` unfiltered | H21, "mx list" |
| Remove the `DELETE /:id` team check | "mx DELETE cY" |
| Drop the `team.orgId === store.orgId` comparison in the helper | H23 |
| Drop the owner/admin bypass | H25, "owner/admin pull cY" control |
| Cache the membership result at token mint instead of per request | H22, "removed mid-chain" |
| `validateAndRotateToken` does not copy `scope_team_id` onto the rotated token | "X-scoped token pulls cY" |
| The 403 body omits `newServerToken` | H22 (token file assertion), "mx pull cY" (next call) |
| Make the helper look the config up before checking the team (existence oracle) | "missing config in X is 404, not 403", plus a new "missing config in Y is 403, not 404" case |
| Skip the cache purge on `RemoteTeamForbiddenError` | H22 cache assertion |

## 4. Per-team cryptographic isolation: worth it?

**What server-side authorization does not cover.** With the fix, a member of X can no longer obtain Y's ciphertext from the API. They still hold a key that opens it. They can decrypt Y's data if Y's ciphertext reaches them some other way:
- a D1/R2 dump or leaked backup, plus their own slot;
- a future authorization bug;
- a malicious or compromised server.

A member removed from Y keeps both the key and any Y plaintext already in their offline cache.

**Options.**

- **(a) No cryptographic isolation. Enforce on the server and document it precisely. Recommended.**
  - Cost: T9 only.
  - What it does not stop: the three residual paths above.
  - Reasoning: the dominant residual path is a hostile server. Per-team keys do not stop that either, because the server serves the portal JS that unwraps keys (parent plan, section 0: "does not hold against an operator who serves malicious portal code"). That leaves storage compromise combined with a colluding member of another team, which is narrow.
- **(b) One config store per team.**
  - Reuse the existing store abstraction: a store keyed by (org, team), each with its own CEK, slots, rotation and member list.
  - Gains real isolation using only code that already exists and is tested.
  - Costs:
    - `getStoreForOrg` (`config.service.ts:1567`) and every `resolveConfigOrg` caller become (org, team)-aware;
    - `config_stores` gains `team_id` and a unique index;
    - owners enroll once per team;
    - the handoff picker selects a store before a config;
    - team membership changes go through the existing owner-gated member add, remove and rotate ceremonies per store.
  - This is the cheaper route if isolation is ever required.
- **(c) Per-team CEKs inside one store.**
  - Add `team_id` to `config_key_slots` and `config_cek_handoffs`. Unlock returns one wrapped key per team.
  - Rotation becomes per team.
  - Adding someone to a team needs an online key holder to seal the team key to their X25519 identity (`config_user_identities.x25519PublicKey`). Removing someone forces a re-key and re-encryption of that team's configs.
  - Owners and admins hold every team key.
  - The executor grant carries N keys.
  - This touches shared crypto, the CLI, the portal wizards, rotation and the cache format. It is largest in scope and gives the same protection as (b).
- **(d) Per-team DEKs wrapped under the org CEK. Rejected.** Everyone who holds the org CEK unwraps every team DEK, so it gives no isolation from members. It only adds rotation machinery.

**Recommendation.** Take (a) now as P1. Record (b) as the path to take if a customer needs isolation between teams (for example an MSP hosting several clients in one org), and give it its own plan then. Do not build (c) or (d).

## 5. Operator decisions (recommended option first)

- **E1, cryptographic isolation:**
  - (a) server-side enforcement only, documented as such (section 4), **recommended**;
  - (b) plan per-team stores now;
  - (c) plan per-team CEKs inside one store.
- **E1b, who may use the org-level config (`teamId = null`):**
  - (a) every store member may read and write it, as today, since it is the default target of `rdc config remote enable` in a single-team org and restricting it would break the common flow, **recommended**;
  - (b) all store members may read it, but only owners and admins may write it;
  - (c) treat null as the org's default team (`teams.is_default`) and require membership of it.
- **E2, token binding:**
  - (a) tokens stay (user, store) with a live membership check, plus an optional `scope_team_id` narrowing for team-scoped credentials, **recommended**;
  - (b) a live check only, with no scope column, so a team-scoped enroll token yields a store-wide config token (today's behavior for everything except the target choice);
  - (c) every config token is bound to exactly one team, so a multi-team human needs one enable per team.
- **E3, delete rights:**
  - (a) `DELETE /:id` needs team_admin of the config's team or org owner/admin, and for `teamId = null` owner/admin only, **recommended**;
  - (b) any member of the team may delete.
- **E4, after losing team access:**
  - (a) the CLI purges the offline cache of that config on `team_forbidden`, **recommended** (this is hygiene: it does not recall plaintext already copied, and says so);
  - (b) keep the cache and only refuse remote calls.
- **E5, archived teams:**
  - (a) owners and admins may read (for export) and nobody may write, **recommended**;
  - (b) no access at all until the team is unarchived.

## 6. Sequencing and risks

- **Phase 0.** T1 and T2 land first, with the failing cases marked `it.fails`. This proves the tests reproduce the gap.
- **Phase 1.** T3, T4 and T7 on the server. They rebase after the parent's T5 (versions scoping) and T7 (`newServerToken` in error bodies). If the parent's T7 is late, T4 includes the token in its own 403 body, and the parent's T7 later generalizes it.
- **Phase 2.** T5 and T6, which add migration 0056. The parent plan owns `0055_*`, so the number is confirmed at commit time against `drizzle/meta/_journal.json`.
- **Phase 3.** T8 (CLI), then T9 and T10.

**Risks.**
- **Existing multi-team users lose access they used silently.** A member whose pointer names a team they are not in gets 403 after deploy. Before deploy, a one-off D1 query lists `config.pull` and `config.push` events from the last 30 days where the user has no `team_memberships` row for the config's team, so affected users can be added to the team first.
- **Rotation must still see every config.** The rotation routes are owner/admin only and read the store directly (`beginCekRotation`), so they are unaffected. Assert this with a rotation test (`config-sync/rotation.test.ts`) run by a non-owner admin.
- **Extra D1 reads per config request.** The check adds 1-3 reads (`org_memberships`, `teams`, `team_memberships`), all on indexed keys (`idx_team_memberships_team_user`). This is acceptable on D1. Do not add a cache, because the per-request read is what makes revocation immediate.
- **The portal picker and editor change silently.** They now show fewer configs. `ConfigEditor`'s empty state (`ConfigEditor.tsx:224`) must not read as "no config exists" when the user simply has no visible team. Add a portal test case for it in `web/src/pages/console/__tests__/config-editor.test.tsx`, coordinated with that file's owner.

### Critical Files for Implementation
- /home/developer/console/private/account/src/routes/configs.ts
- /home/developer/console/private/account/src/services/config.service.ts
- /home/developer/console/private/account/src/services/org.service.ts (read-only reference: `resolveUserTeam`, `getTeamMembershipRole`, `getMemberRole`)
- /home/developer/console/private/account/src/middleware/config-token.ts (with `src/db/config-schema.ts` for `config_tokens`)
- /home/developer/console/private/account/tests/integration/config-sync/harness/device.ts (with `config-org-scope.test.ts` as the route-matrix template)

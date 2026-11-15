# PLAN: Root API token -- agents act as root on stable/edge through a root-scoped, IP-bound, expiring token with a TOTP session

Status: approved -- operator ruling ASKED:2026-11-15T17:07Z, verbatim intent: "agents act as root on stable/edge through a root-scoped, IP-bound, expiring API token kind that /admin routes accept (TOTP still required per call or per session), minted once from the portal and stored in bws as ROOT_API_TOKEN; no captcha bypass." Q1-Q4 below carry defaults logged for veto.
Depends-On: none
Priority: P1 -- no agent can open a production root session today: stable eu `POST /account/api/v1/auth/login` answers 400 {"error":"Captcha verification required"}, so every production root task waits on the operator's browser
Concurrency: parallel -- Wave 1 runs three file-disjoint writers (S1 server core, W1 portal page, C1 ops tool) against the wire contract fixed in Design 3. Wave 2 (S2, D1) starts after S1 lands. S2 edits the root route factory in 11 /admin route files, so it checks block_plan_concurrency for any live holder of private/account/src/routes/root*.ts, name-change.ts or partner-deals.ts first. C1 and L0 edit .ci/config/secret-supply.json and .ci/config/bws-secret-map.json, which PLAN-multi-region-bench.md also lists in its Owns; this plan changes only the `root-login` profile and adds one map key.
Owns: agent/plans/PLAN-root-api-token.md, private/account (gitlink bump only), private/account/src/db/schema.ts, private/account/drizzle/0088_root_api_tokens.sql, private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/0088_snapshot.json, private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/src/types/root-api-token.ts, private/account/src/services/root-api-token.service.ts, private/account/src/middleware/root-auth.ts, private/account/src/middleware/elevated.ts, private/account/src/routes/root-api-tokens.ts, private/account/src/routes/index.ts, private/account/src/routes/auth.ts, private/account/src/container.ts, private/account/src/app.ts, private/account/src/dto/root-api-token.dto.ts, private/account/src/dto/index.ts, private/account/src/errors.ts, private/account/src/constants.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/root-api-token*.test.ts, private/account/src/routes/root.ts, private/account/src/routes/root-contact.ts, private/account/src/routes/root-invoices.ts, private/account/src/routes/root-newsletter.ts, private/account/src/routes/root-partner.ts, private/account/src/routes/root-partner-certification.ts, private/account/src/routes/root-partner-offers.ts, private/account/src/routes/root-stripe.ts, private/account/src/routes/root-version-policy.ts, private/account/src/routes/name-change.ts, private/account/src/routes/partner-deals.ts, private/account/tests/integration/admin-root-token-coverage.test.ts, private/account/web/src/pages/admin/RootApiTokens.tsx, private/account/web/src/router.tsx, private/account/web/src/components/AppSidebar.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/pages/__tests__/admin-root-api-tokens.test.tsx, .ci/rediacc_ci/ops/root_login.py, .ci/rediacc_ci/tests/test_root_login.py, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/env-manifest.json, .ci/config/python-env-registry.json, .ci/config/bws-unrequested.json, private/account/CLAUDE.md, docs/agent-reference/bench-login.md, private/account/docs/secrets/rotation.md
Live-Proof: production -- stable eu, then edge eu (the same Worker set and D1, see Context 9); bench keeps the password path and is not touched
Owner: d778be9d
Updated: 2026-11-15
First-Seen: 2026-11-15

## Ask

Let an agent act as the system root on the production account Workers without the operator's browser and without bypassing Turnstile. The credential is a new token kind with these properties:
- root-scoped and minted by root alone, from the portal, once;
- bound to the agent's egress IP, with a refresh path, because that IP rotates nightly;
- expiring and rotatable;
- accepted on /admin routes only after a TOTP proof;
- stored in bws as ROOT_API_TOKEN.

`rediacc_ci.ops.root_login --target stable|edge` switches to it. Bench is unchanged.

## Context (read 2026-11-15 against the tree; a writer re-reads each citation before relying on it)

1. **The captcha wall.** `requireTurnstile('auth_login')` is built at private/account/src/routes/auth.ts:43 and sits on `POST /login` at private/account/src/routes/auth.ts:150-153. root_login posts there first (.ci/rediacc_ci/ops/root_login.py:209) and quotes the refusal (.ci/rediacc_ci/ops/root_login.py:210-221). Its docstring already rules out a bypass (.ci/rediacc_ci/ops/root_login.py:15). The middleware is exported at private/account/src/middleware/turnstile.ts:27.
2. **The api-token model.**
   - `createTokenSchema` is at private/account/src/types/api-token.ts:44-102. Its scope enum is per subscription (private/account/src/types/api-token.ts:48-89). `PRIVILEGED_TOKEN_SCOPES` (owner/admin to mint) is at private/account/src/types/api-token.ts:105-123. `TWO_FACTOR_TOKEN_SCOPES` (2FA to mint) is at private/account/src/middleware/require-2fa.ts:22-26.
   - IP modes are `first-use | unbound | cloudflare | service-binding` (private/account/src/types/api-token.ts:24). Non-default modes are allowed only with `proxy:exec` (private/account/src/types/api-token.ts:38-42). `service-binding` is minted only by the ExecutorIssuer and refused on the public path (private/account/src/types/api-token.ts:16-19; private/account/CLAUDE.md:282, :286; enforced at private/account/src/middleware/api-token.ts:72-82).
   - The `api_tokens` row carries a NOT NULL `subscription_id` (private/account/src/db/schema.ts:313-358). The table is registered ORG_SCOPED_INDIRECT (private/account/src/db/scope-registry.ts:65-74) and shard class `tenant` (private/account/src/db/shard-router.ts:83). Values look like `rdt_<64 hex>` (private/account/src/services/api-token.service.ts:365-369).
   - The system root "holds no license/seat" (private/account/CLAUDE.md:211). So a root token does not fit `api_tokens` without a fake subscription. That drives Design 1.
3. **How a first-use token is checked.**
   - The middleware binds on first use and refuses another IP with `TOKEN_IP_MISMATCH` and a `rebind: 'totp'|'relogin'` hint (private/account/src/middleware/api-token.ts:107-120).
   - The TOTP rebind route is the refresh model this plan copies. It resolves the token with no IP check (private/account/src/routes/api-token-ip.ts:57), refuses non-first-use tokens (:92-95), refuses an unknown IP (:98-104), and is idempotent at the same IP (:106-109). It requires the creator's TOTP (:111-126), runs a lock and disable ladder (:128-140), checks the code (:156-165), spends the step per user (:167-178), and moves the binding by compare-and-set (:181).
   - `resolveApiToken` has exactly two callers, and a test pins that count (private/account/src/middleware/api-token.ts:11-17; private/account/tests/integration/api-token-ip-rebind.test.ts:668). A root token must therefore not go through it.
4. **How /admin authenticates today.**
   - Mounts are at private/account/src/routes/index.ts:61-71. Every factory builds `const auth = sessionAuth(); const root = requireRole('root')` per route (for example private/account/src/routes/root.ts:53-54, private/account/src/routes/root-stripe.ts:29-30, private/account/src/routes/name-change.ts:59-61, private/account/src/routes/partner-deals.ts:124-126).
   - `sessionAuth` reads only the `access_token` cookie and sets `userId`, `userEmail`, `userRole` and `tokenPayload` (private/account/src/middleware/session.ts:8-34). `requireRole` compares `userRole` (private/account/src/middleware/session.ts:36-44).
   - Destructive routes add `requireElevated()` (private/account/src/middleware/elevated.ts:9-20), which asks `authService.isElevated(userId)`.
   - Elevation is ONE row per user (`onConflictDoUpdate` on `elevated_sessions.user_id`, private/account/src/services/auth.service.ts:654-671) with a 10-minute TTL (private/account/src/constants.ts:29). Reusing it for a token would also elevate the operator's browser, and the other way round.
   - Grep finds no `tokenPayload` read and no `getCookie` in any /admin handler, so a handler needs only `userId`, `userEmail` and `userRole`.
5. **Root identity.** Root is the user whose email equals `ROOT_EMAIL`. It is auto-promoted at sign-in (private/account/src/routes/auth.ts:62-77, event `auth.auto_promote_root`; private/account/CLAUDE.md:191).
6. **The TOTP paths.**
   - `/auth/2fa/verify` answers the login challenge (private/account/src/routes/auth.ts:546-594).
   - `/auth/reauth/totp` elevates a cookie session with a code (private/account/src/routes/auth.ts:435-445) through `verifyReauthTotp`, which refuses backup codes and spends the code (private/account/src/services/auth.service.ts:525-540).
   - Every TOTP use spends its 30 s step once per user: `spendTotpCode`/`claimTotpStep` is a compare-and-set on `users.totp_last_step` (private/account/src/services/auth.service.ts:548-556, :610-628).
   - **Consequence: a per-call TOTP header allows at most one /admin call per 30 s.** It would also collide with the operator's own sign-ins. Design 2 therefore uses a per-session proof.
   - The bench doc records the same collision (docs/agent-reference/bench-login.md:52).
7. **Audit.**
   - `eventLogService.log` takes `{type, source, userId, orgId?, actorTokenId?, data}` (private/account/src/services/event-log.service.ts:57-76, :131). The rebind route shows the token audit shape (private/account/src/routes/api-token-ip.ts:60-77).
   - The admin activity view humanizes types (private/account/src/routes/root.ts:870-930). It is listed by `GET /admin/activity` (private/account/src/routes/root.ts:116) across shards.
   - Expired api tokens are purged nightly (private/account/src/entry/cloudflare.ts:245) from `runRetentionSweeps` (private/account/src/entry/cloudflare.ts:334).
8. **The portal.**
   - Tokens are minted on the customer page private/account/web/src/pages/ApiTokens.tsx against `POST /api-tokens`, which is session-only (private/account/src/routes/api-tokens.ts:21-22, :25-138).
   - Admin pages are registered in private/account/web/src/router.tsx (for example :44 and :336 for version-policy) and the sidebar list at private/account/web/src/components/AppSidebar.tsx:118-140.
   - Step-up UI exists: private/account/web/src/components/ReauthStep.tsx.
9. **Stable and edge are one origin and one D1 per region.** "There is no stable Worker set" (docs/agent-reference/release-process.md:18-19). root_login resolves both targets to `https://<regions.json domain>` (.ci/rediacc_ci/ops/root_login.py:5, :89-97). Each region has its own D1 (regions.json:7 `account-eu`). So a token minted on eu is valid on eu only, for both targets.
10. **Ops tool and secrets.**
    - root_login has `TARGETS = ("stable", "edge")` (.ci/rediacc_ci/ops/root_login.py:35) and re-executes under the `root-login` profile (.ci/rediacc_ci/ops/root_login.py:34, :235-257). That profile requires ROOT_EMAIL, ROOT_PASSWORD and ROOT_TOTP_SEED (.ci/config/secret-supply.json:543-551), with map ids at .ci/config/bws-secret-map.json:439-447.
    - The bench path is a separate tool (`rediacc_ci.ops.login_bench`, `bench-login` profile), so leaving it alone needs no guard.
    - Commit 6ff21f1b29 shows the five registries a new vault name touches: secret-supply.json, bws-secret-map.json, env-manifest.json, python-env-registry.json and bws-unrequested.json.
11. **The account repo's gates.**
    - `check:ci-account-scope-audit`: every table must be registered, and USER_SCOPED tables must have a `userId` column (package.json:298; private/account/tests/integration/scope-audit.test.ts:35-40, :78).
    - `check:ci-account-layer-isolation`: routes import no DB layer (package.json:296).
    - `check:ci-account-no-admin-role`: the system role stays `root` (package.json:297).
    - `check:ci-account-config-auth` (private/account/CLAUDE.md:52-56).
    - Migrations live in private/account/drizzle (wrangler.toml:30). The newest is 0087 (88 journal entries). CD applies them with `wrangler d1 migrations apply` (.ci/rediacc_ci/deploy/deploy_account.py:303).

## Design

### 1. The token kind: a separate table, `root_api_tokens`

The token is a new kind, not a new scope in `createTokenSchema`. A separate table means:
- a root token can never satisfy `apiTokenAuth` on a customer route;
- a customer token can never satisfy /admin;
- `api_tokens` keeps its subscription invariant;
- the `resolveApiToken` count stays two.

- **Value:** `rdr_<64 hex>`. The prefix is how `rootAuth` tells it apart; customer values are `rdt_`. Only the sha256 is stored.
- **Scope:** the single scope `root:admin`, held in a `scope` text column so a later `root:read` needs no migration (Q4). The constant lives in private/account/src/types/root-api-token.ts. A test asserts `createTokenSchema` refuses `root:admin` (control for separation).
- **Table:** columns `id, user_id` (the root user; USER_SCOPED, shard class `global` like `elevatedSessions`), `name, token_hash` (unique), `scope, created_at, expires_at` (NOT NULL), `revoked_at, revoked_reason, last_used_at, last_used_ip`. Then:
  - `bound_v4` (one address) and `bound_v6` (one /64 prefix);
  - `bind_failed_attempts, bind_locked_until, bind_lock_count, binds_window_start, binds_in_window, last_totp_step`;
  - `session_expires_at, session_ip`;
  - `chain_id, chain_started_at, rotated_to_id`.
  The migration is 0088_root_api_tokens.sql. The writer confirms 0088 is still free when committing.
- **Minting is root only.** It needs a root cookie session, `requireRole('root')` and `requireElevated()` (a fresh step-up), and the root user must have TOTP enabled. Without TOTP the answer is 403 `TWO_FACTOR_REQUIRED`, because a token whose sessions need TOTP is useless without it.
- **Limits.** At most 2 live tokens per root (409 `ROOT_TOKEN_LIMIT`), which leaves room for a rotation overlap. `expiresInDays` is 1-90, default 90.
- **Never accepted elsewhere.** Mint, list and revoke-by-id are cookie-session routes, never accepted with a root token, so a token cannot mint tokens.
- **Checked at every use.** The row's `user_id` still has role `root` AND its email still equals `envConfig.rootEmail`. Otherwise the answer is 403 `ROOT_TOKEN_NOT_ROOT`. Changing ROOT_EMAIL kills every token.
- **IP binding.** It starts unbound and binds only through the TOTP-gated `bind` call (no silent first use). The bound set is one IPv4 address plus one IPv6 /64, canonicalized as bench_access does (docs/agent-reference/bench-login.md:22). A caller matches when its address equals `bound_v4` or falls inside `bound_v6` (`ipInAnyCidr`, private/account/src/utils/cidr.ts). Each family is bound separately because which family a client leaves over is not fixed (unverified, U2). An unknown client IP is refused (the api-token-ip.ts:98-104 rule).
- **Refresh path for the nightly IP change:** `POST /admin/root-token/bind` with the token and a fresh code.
  - The code is spent per user (Context 6).
  - Wrong and replayed codes feed a lock that doubles and then disables (the api-token-ip.ts:128-178 ladder and constants).
  - Binds are capped at 6 per 24 h per token.
  - Each bind replaces only the caller's family entry, closes any open session and is audited.
  - root_login runs it automatically when it gets `ROOT_TOKEN_IP_MISMATCH` (Design 6).
  - Honest limit: whoever holds both ROOT_API_TOKEN and ROOT_TOTP_SEED (the same bws project) can rebind. The binding protects against a token value leaking alone (logs, a paste), and each move is visible in the audit.
- **Expiry and rotation (Q2):**
  - `POST /admin/root-token/rotate` needs an open token session. It mints a successor with the same binding and lifetime, sets the old token's expiry to min(old, now + 1 h) and links the two through `rotated_to_id`.
  - It is refused once `chain_started_at` is more than 365 days old (MAX_TOKEN_TTL_MS, private/account/src/constants.ts:47). After that the operator mints again in the portal.
  - root_login rotates when fewer than 14 days remain and writes the new value to bws under the same entry (login_bench already writes BENCH_ROOT_TOTP_SEED back, per commit 6ff21f1b29).
  - This keeps the operator ruling's "minted once from the portal" true for a year.

### 2. How a call proves TOTP: a short token session, not a per-call code

A per-call code allows one call per 30 s and steals the operator's steps (Context 6). So:
- **Open:** `POST /admin/root-token/session` with `Authorization: Bearer rdr_...` and body `{code}`. The checks run in a fixed order, which is part of the contract:
  1. The token is valid (not revoked, not expired); otherwise 401.
  2. The creator is still root; otherwise 403 `ROOT_TOKEN_NOT_ROOT`.
  3. The caller's family is bound and matches; otherwise 403 `ROOT_TOKEN_IP_MISMATCH` with `rebind: 'totp'`.
  4. The token is not locked or disabled; otherwise 423 or 403.
  5. The code is a valid TOTP code (backup codes refused); otherwise 400 `TOTP_INVALID`.
  6. The step is spent (`claimTotpStep`); otherwise 409 `TOTP_REPLAYED`.
  7. Success: `session_expires_at = now + ELEVATED_SESSION_TTL_MS` (10 min) and `session_ip` = the caller's canonical address. The answer is `{sessionExpiresAt, tokenExpiresAt, bound:{v4,v6}}`.
- **The session lives on the token row,** not in `elevated_sessions`, so the operator's browser is neither elevated nor de-elevated by an agent. No second secret is issued: later calls carry the same bearer from the same IP.
- **Close:** `DELETE /admin/root-token/session` closes it.
- A token session counts as both `root` and `elevated`. It is the same fresh TOTP proof the cookie path's `/auth/reauth/totp` gives, with the same TTL.

### 3. Wire contract (fixed here so W1 and C1 can be written in parallel with S1)

All paths are under `/account/api/v1`. Errors use the existing `{error, code}` shape.

| Method and path | Auth | Body / answer |
|---|---|---|
| `POST /admin/root-tokens` | root cookie + elevated | `{name, expiresInDays?}`. 201 `{token, metadata}`; the value appears only here |
| `GET /admin/root-tokens` | root cookie | `{tokens:[{id,name,scope,createdAt,expiresAt,lastUsedAt,lastUsedIp,boundV4,boundV6,sessionExpiresAt,revokedAt,chainId,rotatedToId}]}`, no hash |
| `DELETE /admin/root-tokens/:id` | root cookie + elevated | revokes the id and every live successor in its chain, closes sessions. `{revoked:true}` |
| `POST /admin/root-token/bind` | bearer `rdr_` | `{code}`. 200 `{rebound:boolean, family:'v4'|'v6', bound:{v4,v6}}` |
| `POST /admin/root-token/session` | bearer `rdr_` | `{code}`. 200 `{sessionExpiresAt, tokenExpiresAt, bound}` |
| `DELETE /admin/root-token/session` | bearer `rdr_` | 200 `{closed:true}` |
| `POST /admin/root-token/rotate` | bearer `rdr_` + open session | 201 `{token, tokenExpiresAt}` |
| `DELETE /admin/root-token/self` | bearer `rdr_`, any IP, no session | 200 `{revoked:true}`. Revoking only removes power, so no proof is asked |

New error codes in private/account/src/errors.ts: `ROOT_TOKEN_IP_MISMATCH`, `ROOT_TOKEN_SESSION_REQUIRED`, `ROOT_TOKEN_NOT_ROOT`, `ROOT_TOKEN_LIMIT`, `ROOT_TOKEN_BIND_LIMIT`, `ROOT_TOKEN_CHAIN_EXPIRED`.

### 4. Which /admin routes accept it: `rootAuth()`

`private/account/src/middleware/root-auth.ts` exports `rootAuth()`:
- **No `Authorization: Bearer` header:** it runs `sessionAuth()` unchanged, so the operator's portal path is byte-identical.
- **`Bearer rdt_...` (a customer token):** 401 "customer API tokens are not accepted on /admin".
- **`Bearer rdr_...`:**
  1. Validate the token, apply the root check and the IP family match.
  2. Require `session_expires_at > now` and `session_ip` equal to the caller; otherwise 403 `ROOT_TOKEN_SESSION_REQUIRED`.
  3. Set `userId` (root user), `userEmail`, `userRole='root'` and `rootTokenId`.
  4. Run the route.
  5. Write `root_token.call` `{method, route: c.req.routePath, status}` with `actorTokenId`.

`requireElevated()` (S1, elevated.ts) passes when `rootTokenId` is set. Only `rootAuth` sets that, and only after the session check. Every other path is unchanged.

S2 swaps `sessionAuth()` for `rootAuth()` in the root factory of every file mounted at private/account/src/routes/index.ts:61-71. That is about 75 handlers: root.ts (23), root-contact.ts (4), root-invoices.ts (5), root-newsletter.ts (4), root-partner.ts (11), root-partner-certification.ts (5), root-partner-offers.ts (7), root-stripe.ts (10), root-version-policy.ts (2), and the root halves of name-change.ts (:59) and partner-deals.ts (:124).

Refused under a root token:
- the three portal token routes in Design 3, which stay `sessionAuth()`;
- every route outside /admin, where `rootAuth` is never mounted.

A coverage test enumerates the app's `/admin/*` routes and asserts each one either accepts a token session (status not 401) or is on an explicit session-only list of three entries. So a future /admin route on `sessionAuth` fails the build until someone makes an explicit choice. Whether Hono exposes the mounted sub-app routes for that enumeration is unverified (U8). The fallback is a list parsed from the mount table plus each factory.

### 5. Revocation and audit events

**Revocation:**
- portal revoke by id (it closes the session at once);
- self revoke;
- expiry;
- the old token's expiry is shortened at rotation;
- `POST /auth/2fa/disable` revokes every root token of that user with `revoked_reason='2fa_disabled'` (S1 owns auth.ts for this one hook at private/account/src/routes/auth.ts:527);
- a demotion or ROOT_EMAIL change refuses use (Design 1).

**Events,** `source: 'account-admin'`, with `userId` = root, `actorTokenId` and data that never includes the value:
- `root_token.created`, `root_token.revoked` `{reason}`, `root_token.rotated` `{from,to}`;
- `root_token.ip_bound` `{family, fromIp, toIp}`, `root_token.ip_bind_failed` `{reason, attemptedIp}`;
- `root_token.session_opened`, `root_token.session_refused` `{reason}`, `root_token.session_closed`;
- `root_token.call` `{method, route, status}`.

S2 adds their titles and descriptions to the admin activity humanizers (private/account/src/routes/root.ts:870-930).

**Notification (Q3):** the mint reuses `notificationService.sendApiTokenCreated(userId, {tokenName})`, whose `orgName` is optional (private/account/src/services/notification.service.ts:177-186). Binds are audited only.

**Retention:** rows revoked or expired more than 30 days ago are deleted by a bounded predicate sweep added beside the api-token purge (private/account/src/entry/cloudflare.ts:245). The table holds at most 2 live rows for one user.

### 6. Ops: `root_login --target stable|edge` switches to the token

- **Profile.** The `root-login` profile requires `ROOT_API_TOKEN` and `ROOT_TOTP_SEED`. ROOT_EMAIL and ROOT_PASSWORD move to `optional`, because nothing in token mode reads them. bench-login and login_bench are untouched.
- **Flow.** Read the values and refuse an unset value, the placeholder or a value not starting `rdr_` (rc 2, naming the entry). Then:
  1. `POST /admin/root-token/session` with a code.
  2. On 403 `ROOT_TOKEN_IP_MISMATCH`: `POST /admin/root-token/bind` with a code, wait for the next 30 s step, then `session` again. This is the refresh path.
  3. A refused code is retried once in the next window, as `_answer_challenge` does today (.ci/rediacc_ci/ops/root_login.py:160-196).
  4. On success it prints `root session opened (<target> <region>, token, session until HH:MMZ, token expires in N days)`. It also prints `ip rebound (<family>)` when a bind happened.
  5. With fewer than 14 days left, `--rotate` (or an automatic rotation when `ROOT_LOGIN_AUTOROTATE=1`) calls `rotate` and writes the new value back to bws, reusing login_bench's bws write helper (import it, do not copy it).
- **Region.** `--region eu` reads `ROOT_API_TOKEN`. `--region us|asia` refuses with "no root token for region <r>: mint one on <r>.rediacc.cloud and store it as ROOT_API_TOKEN_<SUFFIX>" (Q1).
- **New flags:**
  - `--check`: no request; validates the bws value and the seed.
  - `--probe stats|audit`: one read-only call. `stats` is `GET /admin/stats` and prints the status and the key count. `audit` is `GET /admin/activity?type=root_token.session_opened,root_token.call,root_token.ip_bound&pageSize=5` and prints types and times only.
  - `--control`: two live refusals. (a) `DELETE` the session, then `GET /admin/stats` must answer 403 `ROOT_TOKEN_SESSION_REQUIRED`. (b) `POST /auth/login` with no captcha token must still answer 400 "Captcha verification required".
- **Importable for other tools:** `open_token_session(target, region) -> AdminClient` with `get(path)`, GET-only by default.
- **Secrets:** no value or code reaches argv, logs or output.

### 7. Portal mint page

private/account/web/src/pages/admin/RootApiTokens.tsx at `/account/admin/root-tokens`, with a sidebar entry "Root API Tokens" next to "Version Policy".
- **Mint form:** name, and expiry days (default 90). A 403 `reauthRequired` answer shows `ReauthStep` and retries.
- **The value is shown once,** with copy and the instruction "store this in Bitwarden as ROOT_API_TOKEN (eu) and revoke the old token after the agent has used the new one".
- **The list** shows bound v4 and v6, last used (time and IP), whether a session is open, expiry, chain/rotated-to and a revoke button with a confirm.
- The page refuses to render a mint button when 2 tokens are live.

### 8. Bench

Unchanged. login_bench keeps the password and TOTP path, and root_login has no bench target (.ci/rediacc_ci/ops/root_login.py:35). The server code also deploys to bench, but nothing there mints a root token.

## Rulings needed (defaults run unless vetoed)

- **Q1. Per-region names.** Tokens are per regional D1 (Context 9), so one value cannot serve eu, us and asia. Default: `ROOT_API_TOKEN` as ruled is the eu token. `ROOT_API_TOKEN_US` and `ROOT_API_TOKEN_ASIA` follow the regions.json `secretSuffix` pattern when they are needed; this plan does not mint them. Alternative: rename to `ROOT_API_TOKEN_EU` now.
- **Q2. Self-rotation.** Default yes: the token rotates itself through `rotate`, capped at one year from the portal mint, so the operator mints once a year. Alternative: no rotate route, and the operator re-mints every 90 days.
- **Q3. Email on bind.** Default no: binds are audited only, and the mint sends the existing token-created mail. Alternative: a new "root token moved" email (adds email templates and i18n).
- **Q4. A read-only variant.** Default no: one scope `root:admin`, as ruled ("agents act as root"). The `scope` column leaves room for `root:read` (GET only) later.

## Not verified (load-bearing; each owner re-checks)

- U1. The 400 on stable eu login is the Turnstile middleware. Taken from the operator's report. The code at private/account/src/routes/auth.ts:43, :153 is consistent; the live answer was quoted by root_login on 2026-11-15 as `HTTP 400: Captcha verification required` (b2978e7c16).
- U2. The agent's egress rotates nightly (operator statement). Whether it is dual-stack and which family Python's `http.client` picks is unmeasured. The per-family bind covers both cases.
- U3. The production eu root user has TOTP enrolled with the seed in ROOT_TOTP_SEED. root_login was built on that premise, but no production session has ever opened.
- U4. `GET /admin/activity` (`listAdminActivityAcrossShards`) returns events that carry no `orgId`. If it does not, the `--probe audit` leg reads nothing, and LP2 opens a fix-forward box on root.ts.
- U5. `getClientIp` returns CF-Connecting-IP on Workers (private/account/src/utils/request.ts:110-130, partly read).
- U6. Migration number 0088 is free at commit time, and the drizzle snapshot naming matches drizzle/meta (only 0000 and 0007 snapshots exist today).
- U7. The exact `bws secret create` invocation and the ci-shared project id for L0.
- U8. Hono exposes the routes of mounted sub-apps for the S2 coverage test.
- U9. The vitest env can switch Turnstile on for the captcha control (`getTestEnv` keys not read).

## Tasks

### Wave 0

- [x] L0 [lead] Create the vault entry `ROOT_API_TOKEN` in the ci-shared project with the value `PLACEHOLDER-operator-fills` (U7), and add its id to the map.
  - Owns: .ci/config/bws-secret-map.json.
  - Accept: `grep -c '"ROOT_API_TOKEN"' .ci/config/bws-secret-map.json` prints 1, and `npm run -s check:ci-secret-supply` rc 0.
    (ticked) 2026-11-15T17:54:57Z by d778be9d: commit:600930fae3 store-from-env --create ROOT_API_TOKEN read back MATCH rc=0; bws-map-refresh rc=0 id 5e06ac8b

### Wave 1: three writers, file-disjoint, against the Design 3 contract

- [x] S1 [writer] Account server core: the table, migration 0088, registry entries (USER_SCOPED; SHARD_CLASS `global`), `RootApiTokenService`, `rootAuth()`, the `requireElevated` branch, the routes in Design 3 mounted at `/admin`, DTOs through `responds()`, error codes, the retention sweep, and the revoke-on-2FA-disable hook. The vitest integration suite has these refusals and controls:
  - Mint: a customer session gets 403. Root without step-up gets 403 `reauthRequired`. Root without TOTP gets 403 `TWO_FACTOR_REQUIRED`. A third live token gets 409. Control: the value is returned once and the list carries no hash. Control: `createTokenSchema` refuses `root:admin`.
  - Session: a wrong code gets 400. A replayed code gets 409, including a step already spent by `/auth/2fa/verify`. Unbound gets 403 `ROOT_TOKEN_IP_MISMATCH`. Another IP gets 403. Expired and revoked tokens get 401. A demoted creator and a changed ROOT_EMAIL each get 403 `ROOT_TOKEN_NOT_ROOT`. Control: 200.
  - Calls: a bearer without a session gets 403 `ROOT_TOKEN_SESSION_REQUIRED`. A session used from a second IP gets 403. A session after 10 min (fake clock) gets 403. An `rdt_` token on /admin gets 401. An `rdr_` token on `/portal/*` and on `/admin/root-tokens` gets 401. Control: `GET /admin/stats` 200 and a `requireElevated` route passes under a token session, each writing `root_token.call` with `actorTokenId`. Control: the cookie path with an elevated session still passes, and without elevation still answers `reauthRequired`.
  - Bind: the lock doubles, then disables. The 7th bind in 24 h gets 429 `ROOT_TOKEN_BIND_LIMIT`. The v4 and v6 entries are independent. Inside the /64 matches and outside refuses.
  - Rotate: no session gets 403. The successor works. The old token expires within 1 h. A chain older than 365 days gets 403 `ROOT_TOKEN_CHAIN_EXPIRED`.
  - Revoke: portal revoke kills an open session at once. Self revoke works from another IP. 2FA disable revokes all.
  - Captcha control: `POST /auth/login` carrying a valid `rdr_` bearer still answers 400 "Captcha verification required" when Turnstile is on (U9).
  - Sweep: deletes stale rows and keeps live ones.
  - Owns: private/account/src/db/schema.ts, private/account/drizzle/0088_root_api_tokens.sql (new), private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/0088_snapshot.json (new, if drizzle-kit writes one), private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/src/types/root-api-token.ts (new), private/account/src/services/root-api-token.service.ts (new), private/account/src/middleware/root-auth.ts (new), private/account/src/middleware/elevated.ts, private/account/src/routes/root-api-tokens.ts (new), private/account/src/routes/index.ts, private/account/src/routes/auth.ts, private/account/src/container.ts, private/account/src/app.ts, private/account/src/dto/root-api-token.dto.ts (new), private/account/src/dto/index.ts, private/account/src/errors.ts, private/account/src/constants.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/root-api-token*.test.ts (new).
  - Accept: `(cd private/account && npx vitest run tests/integration/root-api-token)` rc 0, `(cd private/account && npx vitest run tests/integration/api-token-ip-rebind.test.ts tests/integration/admin.test.ts tests/integration/root-console-block.test.ts)` rc 0, `npm run -s check:ci-account-scope-audit` rc 0, `npm run -s check:ci-account-layer-isolation` rc 0, `npm run -s check:ci-account-no-admin-role` rc 0, and `(cd private/account && npm run typecheck)` rc 0.
    (ticked) 2026-11-15T18:28:28Z by d778be9d: commit:494f280dc0 account 29fe9d9 via gitlink; 480 account tests rc=0, typecheck rc=0
    (evidence 2026-11-15T18:57Z, every Accept command on the landed tree 5b6f329157) vitest root-api-token 40 passed; vitest api-token-ip-rebind admin root-console-block 91 passed; check:ci-account-scope-audit, check:ci-account-layer-isolation, check:ci-account-no-admin-role rc 0; npm run typecheck rc 0.
- [x] W1 [writer] The portal page in Design 7, with the route, sidebar entry and endpoints (`adminRootTokens.list|create|revoke`). The test covers:
  - a mint behind `ReauthStep` on a 403 `reauthRequired`, then retried;
  - the value shown once with the ROOT_API_TOKEN instruction and absent after closing;
  - the list rendering bound v4/v6, session and expiry;
  - revoke confirm;
  - the mint button hidden at 2 live tokens.
  - Owns: private/account/web/src/pages/admin/RootApiTokens.tsx (new), private/account/web/src/router.tsx, private/account/web/src/components/AppSidebar.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/pages/__tests__/admin-root-api-tokens.test.tsx (new).
  - Accept: `(cd private/account/web && npx vitest run src/pages/__tests__/admin-root-api-tokens)` rc 0, and `(cd private/account && npm run typecheck:web)` rc 0.
    (ticked) 2026-11-15T18:28:33Z by d778be9d: commit:494f280dc0 account a92a3c3 via gitlink; web vitest 5 passed, web tsc rc=0
    (evidence 2026-11-15T18:57Z, the named Accept commands on the landed tree 5b6f329157) web vitest src/pages/__tests__/admin-root-api-tokens 5 passed; npm run typecheck:web rc 0.
- [x] C1 [writer] `root_login` token mode as in Design 6:
  - token session, automatic bind on `ROOT_TOKEN_IP_MISMATCH`, `--check`, `--probe stats|audit`, `--control`, `--rotate`, and the Q1 region refusal;
  - the `root-login` profile (required `ROOT_API_TOKEN`, `ROOT_TOTP_SEED`; optional `ROOT_EMAIL`, `ROOT_PASSWORD`);
  - registry entries for `ROOT_API_TOKEN` in env-manifest, python-env-registry and bws-unrequested (`no-github-twin`);
  - pytest with a recording transport covering: a placeholder or non-`rdr_` value gives rc 2 with no request; a mismatch triggers one bind and one session in consecutive steps; a code refused twice gives rc 1 and no third try; 429/5xx is a fault, not a refusal; the probe allowlist is GET only; `--control` fails when the session-less call answers 200 (control); a rotation writes the vault entry through the imported helper; no secret appears in captured stdout or stderr. The password path tests are kept and adapted.
  - Owns: .ci/rediacc_ci/ops/root_login.py, .ci/rediacc_ci/tests/test_root_login.py, .ci/config/secret-supply.json, .ci/config/env-manifest.json, .ci/config/python-env-registry.json, .ci/config/bws-unrequested.json.
  - Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_root_login.py .ci/rediacc_ci/tests/test_ops_totp.py .ci/rediacc_ci/tests/test_ops_login_bench.py` rc 0, `npm run -s check:ci-secret-supply` rc 0, `npm run -s check:ci-env-manifest` rc 0, `npm run -s check:ci-python-types` rc 0, and `npm run -s check:ci-python-lint` rc 0.
    (ticked) 2026-11-15T18:28:35Z by d778be9d: commit:91e012896c test_root_login.py 50 passed on the landed tree
    (evidence 2026-11-15T18:57Z, every Accept command on the landed tree 5b6f329157) pytest test_root_login.py test_ops_totp.py test_ops_login_bench.py 179 passed; check:ci-secret-supply, check:ci-env-manifest, check:ci-python-types, check:ci-python-lint rc 0.

### Wave 2: writers, after S1 lands

- [x] S2 [writer] Switch every /admin root factory from `sessionAuth()` to `rootAuth()` (Design 4) and add the `root_token.*` titles and descriptions to the admin activity humanizers. The coverage test enumerates every `/admin/*` method and path (U8) and requires each one to answer non-401 under a token session, except the three session-only token routes. A control mounts a dummy `/admin` route on `sessionAuth` and must fail the check.
  - Owns: private/account/src/routes/root.ts, private/account/src/routes/root-contact.ts, private/account/src/routes/root-invoices.ts, private/account/src/routes/root-newsletter.ts, private/account/src/routes/root-partner.ts, private/account/src/routes/root-partner-certification.ts, private/account/src/routes/root-partner-offers.ts, private/account/src/routes/root-stripe.ts, private/account/src/routes/root-version-policy.ts, private/account/src/routes/name-change.ts, private/account/src/routes/partner-deals.ts, private/account/tests/integration/admin-root-token-coverage.test.ts (new).
  - Accept: `(cd private/account && npx vitest run tests/integration/admin-root-token-coverage.test.ts tests/integration/admin.test.ts tests/integration/version-policy.test.ts tests/integration/partner-admin-detail.test.ts tests/integration/admin-sales-digest-run.test.ts tests/integration/root-console-block.test.ts)` rc 0, `(cd private/account && npm run typecheck)` rc 0, and `grep -c "sessionAuth()" private/account/src/routes/root*.ts` prints 0 for every file.
  (corrected 2026-11-15T18:57Z) The grep excludes routes/root-api-tokens.ts, whose three portal token routes keep sessionAuth() by Design 3-4: `grep -c "sessionAuth()" $(ls private/account/src/routes/root*.ts | grep -v root-api-tokens)` prints 0 for every file.
    (ticked) 2026-11-15T19:01:34Z by d778be9d: commit:5b6f329157 vitest admin-root-token-coverage admin version-policy partner-admin-detail admin-sales-digest-run root-console-block 127 passed; typecheck rc=0; corrected grep 0 for every switched factory
- [ ] D1 [writer] Docs:
  - private/account/CLAUDE.md: the root token under Roles Layer 1 and a short "Root API token" section covering the kind, session, bind, rotation, revocation and events.
  - docs/agent-reference/bench-login.md "Stable and edge root": token mode, the refresh path, the region rule and the one operator step.
  - private/account/docs/secrets/rotation.md: a ROOT_API_TOKEN row covering self-rotation, the yearly re-mint and the revoke steps.
  - Owns: private/account/CLAUDE.md, docs/agent-reference/bench-login.md, private/account/docs/secrets/rotation.md.
  - Accept: `grep -c "ROOT_API_TOKEN" docs/agent-reference/bench-login.md` prints at least 1, `grep -c "root_token.session_opened" private/account/CLAUDE.md` prints at least 1, and `npm run -s check:ci-prose-style` rc 0.

### Live queue: production eu, in order, after the PR merges and CD's edge deploy is green

- [ ] LP0 [live] The deploy reached production: the migration was applied by deploy_account and the route answers.
  - Accept: `curl -s -o /dev/null -w '%{http_code}' -X POST https://eu.rediacc.cloud/account/api/v1/admin/root-token/session` prints 401, and `curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer rdr_0' https://eu.rediacc.cloud/account/api/v1/admin/stats` prints 401.
- [ ] OP1 [live] THE ONE OPERATOR STEP. The operator signs in at https://eu.rediacc.cloud/account/admin/root-tokens, steps up with TOTP, mints one token (name `agent-root-eu`, 90 days) and pastes the value into the Bitwarden entry ROOT_API_TOKEN. No agent sees the value until it reads it from bws.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable --region eu --check` rc 0.
- [ ] LP1 [live] Stable eu: the first bind, a session and one read-only admin call.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable --region eu --probe stats` rc 0, printing `ip rebound`, `root session opened (stable eu, token, ...)` and `GET /admin/stats 200`.
- [ ] LP2 [live] The audit trail of LP1 is readable as root (U4).
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable --region eu --probe audit` rc 0, naming `root_token.ip_bound`, `root_token.session_opened` and `root_token.call`.
- [ ] LP3 [live] Live controls: a call with no session is refused, and login still demands the captcha.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable --region eu --control` rc 0.
- [ ] LP4 [live] Edge: the same origin and token reached through `--target edge`, which needs a fresh session and therefore the next TOTP step.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target edge --region eu --probe stats` rc 0.
- [ ] LP5 [live] The refresh path for real, on the first day after the agent's egress has changed. The run needs no operator.
  - Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable --region eu --probe stats` rc 0, printing `ip rebound (v4)` or `ip rebound (v6)`.
- [ ] F* [writer] Fix-forward boxes, opened under this plan for each claim a live box disproves, each owning only the file the claim names.
  - Accept: the failing live box's command rc 0.

### Critical files for implementation
- private/account/src/middleware/root-auth.ts (new; modelled on private/account/src/middleware/api-token.ts and private/account/src/middleware/session.ts)
- private/account/src/services/root-api-token.service.ts (new; the TOTP and lock ladder from private/account/src/routes/api-token-ip.ts and private/account/src/services/auth.service.ts)
- private/account/src/routes/root-api-tokens.ts (new) and private/account/src/routes/root.ts (the S2 switch pattern)
- private/account/src/db/schema.ts with private/account/src/db/scope-registry.ts
- .ci/rediacc_ci/ops/root_login.py

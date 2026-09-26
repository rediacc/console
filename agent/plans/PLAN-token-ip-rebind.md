# PLAN: a CLI login token can be moved to a new IP after a TOTP check (`Token is bound to a different IP address`)

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-config-handoff-relay-only.md -- shares config-remote*.ts, the cli.json locales and account-security.md; T5-T8 wait for the relay-only console commit, T1-T4 can start now
Priority: P1 -- This is an operator ruling. The operator is blocked on every account-server command after each ISP address change, and re-login is the only way out today.
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: private/account/src/middleware/api-token.ts, private/account/src/routes/api-token-ip.ts (new), private/account/src/routes/index.ts (one mount line), private/account/src/services/api-token.service.ts, private/account/src/utils/totp.ts (verifyCodeStep only), private/account/src/errors.ts (new codes only), private/account/src/constants.ts (API_TOKEN_REBIND_* only), private/account/src/db/schema.ts (api_tokens block only), private/account/drizzle/0054_api_token_ip_rebind.sql, private/account/drizzle/meta/_journal.json, private/account/src/dto/api-token.dto.ts, private/account/src/routes/portal.ts (activity title/description maps only), private/account/src/routes/root.ts (admin activity title/description maps only), private/account/tests/integration/api-token-ip-rebind.test.ts (new), packages/shared/src/subscription/types.ts (rebind wire types only), packages/cli/src/services/account/account-client.ts, packages/cli/src/services/account/token-ip-rebind.ts (new), packages/cli/src/utils/prompt.ts (askInput only), packages/cli/src/utils/spinner.ts (suspend helper only), packages/cli/src/services/core/audit.ts (one option), packages/cli/src/services/telemetry/otlp-credentials.ts (one option), packages/cli/src/commands/config-remote-password.ts (describeEnrollForbidden only), packages/cli/src/commands/__tests__/config-remote-password.test.ts, packages/cli/src/services/__tests__/account-client-ip-rebind.test.ts (new), packages/cli/src/i18n/locales/*/cli.json, packages/www/src/content/docs/*/account-security.md
Worklist: (the lead adds this with `worklist.py --add`)

**Operator ruling, 2026-09-25 (AskUserQuestion):** "Re-bind after a 2FA check." CLI login tokens keep first-use IP binding. When a request is refused with "Token is bound to a different IP address", the CLI asks for a TOTP code and the server moves the binding to the new IP. A stolen token on its own must still fail from another network.

**Trigger.** The operator's token `215a55b1` was bound to yesterday's public IPv4. The ISP changed the address overnight, and `rdc config remote enable` then failed with the raw server error.

**Line numbers** are from the working tree on 2026-09-25: console `3b8ecce25`, account `4ddf6dc`.

## Tasks

There are two writers, and their Owns do not overlap:
- **A** owns the server side: `private/account/**`.
- **B** owns the CLI, shared code, i18n and docs.

The submodule PR (A) merges first. The console PR (B, plus the pointer bump) follows it.

- [ ] T0 [lead] Freeze the wire contract (section 3.1). Put the error codes, the 403 body shape and the rebind request/response types in `packages/shared/src/subscription/types.ts`. A and B both import them.
- [ ] T1 [A] Migration `0054_api_token_ip_rebind.sql`, the schema columns, and `verifyCodeStep` in `utils/totp.ts` (sections 3.2 and 3.3).
- [ ] T2 [A] Split the middleware into `resolveApiToken` plus the IP check. The 403 carries `code: TOKEN_IP_MISMATCH` and the `rebind` hint (section 3.4).
- [ ] T3 [A] The rebind route, the service methods (atomic failure counter, compare-and-set bind), audit events and activity titles, and the DTO (sections 3.5-3.7).
- [ ] T4 [A] Integration tests and mutation controls (section 6.1).
- [ ] T5 [B] The central rebind in `accountServerFetch`: single-flight, retry once, the TTY and non-TTY paths, the `ipRebind: false` opt-out for background callers, and the spinner suspend (section 4).
- [ ] T6 [B] Remove the one-off match in `config-remote-password.ts`, and delete the `passwordIpBound` key from all 13 locales (section 4.5).
- [ ] T7 [B] CLI vitest and mutation controls (section 6.2).
- [ ] T8 [B] CLI i18n in 13 locales. Update the www `account-security.md` in 13 locales and regenerate the translation hashes and search indexes (section 7).
- [ ] T9 [lead] Closure:
  - The removal sweep in section 8 returns nothing.
  - Deploy the account server (eu) before the CLI release.
  - Live smoke of the operator's case: take a token bound to an address, change the egress IP (a VPN or phone hotspot is enough), run `rdc config remote enable`, get one prompt, enter the code, and the command succeeds.
  - Check that the portal Activity shows the "API token moved to a new IP" row.
  - Check that the same token with a wrong code from a third IP is refused.

## 0. What the code does now

- **Where the refusal comes from.** The middleware sends it as a bare `HTTPException` (`private/account/src/middleware/api-token.ts:56-59`), so the body is `{"error":"Token is bound to a different IP address"}` with no `code`. The error handler only adds `code` for `AppError` (`private/account/src/middleware/error-handler.ts:59-75`). That missing code is why the CLI matches on the text.
- **Which tokens can be refused.** Only first-use tokens: `IP_BINDING_MODES` is `first-use | unbound | cloudflare`, and the other two require `proxy:exec` (`private/account/src/types/api-token.ts:17-26`). The device-code login mints a first-use token with `createdByUserId = userId` (`private/account/src/services/device-code.service.ts:341-355`).
- **Revoked and expired tokens never get to the IP check.** `validate()` filters on `revokedAt IS NULL` and on expiry (`private/account/src/services/api-token.service.ts:77-90`), so they get 401 first.
- **Tokens from removed users are already gone.** When a user is removed from an org, their tokens are revoked (`private/account/src/services/org.service.ts:672-678`). That means "creator still a member" is already implied by "token not revoked".
- **The address the binding compares against.** `getClientIp` (`private/account/src/utils/request.ts:13-25`) reads `cf-connecting-ip`, then `x-forwarded-for`, then `x-real-ip`, and returns `'unknown'` when there is none. The tunnel removes all three headers from the inner request and writes only the outer caller's address (`private/account/src/app.ts:621-638`). So a rebind through the tunnel sees the same address the middleware later compares, and the envelope cannot spoof it.
- **The existing TOTP helpers.**
  - `totp.verifyCode` accepts ±1 time step (`private/account/src/utils/totp.ts:12`, `:109-120`) and returns only a boolean, so it cannot tell which step matched.
  - `AuthService.verifyReauthTotp` (`private/account/src/services/auth.service.ts:461-472`) is the 2026-09-24 step-up. It refuses backup codes on purpose and has **no replay guard**.
  - `POST /auth/reauth/totp` (`private/account/src/routes/auth.ts:446-455`) is session-authenticated and uses `authLimit`.
  - `requireTwoFactor` (`private/account/src/middleware/require-2fa.ts:14-32`) only checks `totpEnabled`.
- **Rate limiting is in memory and keyed by IP** (`private/account/src/middleware/rate-limit.ts:16-60`). It does nothing under `NODE_ENV=test` (`:17`) and under `securityConfig.testMode` (`:37`). A brute-force limit that tests can see, and that survives several Worker isolates, therefore has to live in the database.
- **Existing lockout shape to copy.** The login lockout (`private/account/src/services/user.service.ts:296-379`) uses `MAX_FAILED_ATTEMPTS=5`, `ATTEMPT_WINDOW_MS=15min`, and a lock that doubles from 5 minutes up to 1 hour (`private/account/src/constants.ts:9-12`).
- **`/api-tokens` cannot host the new route.** It applies `sessionAuth()` to its whole subtree (`private/account/src/routes/api-tokens.ts:20`), and the `/proxy` mount comment gives exactly that reason for using its own prefix (`private/account/src/routes/index.ts:109-113`). The operator's suggested path `POST /api-tokens/rebind-ip` would therefore run behind session auth. See D1.
- **The CLI.**
  - Every call to the account server goes through `accountServerFetch` (`packages/cli/src/services/account/account-client.ts:189-268`). It throws `{message, status, code}` built from the inner body (`:254-258`, `:279-284`).
  - The one special case for the IP refusal is `packages/cli/src/commands/config-remote-password.ts:45-47`. Its comment (`:26-36`) says outright that it matches on text only because there is no code. Its test case is `packages/cli/src/commands/__tests__/config-remote-password.test.ts:288-292`, and its string is `commands.config.remote.enable.passwordIpBound` (`packages/cli/src/i18n/locales/en/cli.json:316`, 13 locales).
  - `subscription status` shows the raw text (`packages/cli/src/commands/__tests__/subscription.test.ts:246-265`).
- **Proxy mode is not affected.** `/proxy/introspect` never applies `apiTokenAuth` to the presented token (`private/account/src/routes/proxy.ts:34-36`, `:64`). `rdc --proxy` users never hit the binding, and the executor's own `unbound`/`cloudflare` token takes the middleware branches this plan leaves alone.

## 1. Target flow

1. **The CLI call.** It goes through the tunnel. The middleware sees `boundIp !== clientIp` on a first-use token and answers 403 `{ error: "Token is bound to a different IP address", code: "TOKEN_IP_MISMATCH", rebind: "totp" | "relogin" }`. The message text stays exactly as it is, so older CLIs keep their current behaviour.
2. **`accountServerFetch` sees the code** and one of three things happens:
   - **TTY and `rebind: "totp"`.** It suspends the spinner and prompts `Your IP address changed. Enter the 6-digit code from your authenticator app to move this login here`. It then calls `POST /account/api/v1/api-token-ip/rebind {code}` with the same bearer token and retries the original request **once**.
   - **Non-TTY.** It throws a localized error that names both remedies. The error keeps `status: 403` and the code.
   - **`rebind: "relogin"`.** It never prompts. It says that 2FA is off, so the only remedy is `rdc subscription login`, and that enabling 2FA allows the move in future.
3. **The server checks** the token (without the IP check), its mode, its creator, the creator's TOTP, the lockout and replay. It then moves `bound_ip` in one conditional UPDATE and writes an audit row.

The retry is safe even for POSTs. The 403 comes from the auth middleware before any handler runs, and the mismatch branch writes nothing: no `bindIp` and no `updateLastUsed` (`private/account/src/middleware/api-token.ts:58-59`). A test in section 6.1 pins this down.

## 2. Threat model

- **What a move requires.** The token, plus a current TOTP code from the token creator's authenticator.
  - Re-login requires a portal session (password or magic link, plus TOTP when it is enabled). The token stands in for the first factor, so the bar is "a first-factor credential plus the second factor". That is the same bar as re-login with 2FA.
  - **A stolen token on its own still fails.** Without the code it gets 400 `TOTP_INVALID`, and the lockout caps guessing (below).
- **What changes compared with today.** Today a stolen token is useless off-network even to someone who has phished one TOTP code. After this change, an attacker who holds the token *and* a phished live code can move it. That is the accepted price of the ruling. Two things limit it:
  - every move is audited with both IPs;
  - the rightful user's next command gets `TOKEN_IP_MISMATCH` and prompts, so the theft shows up, and the user's own rebind takes the token back.

  The email alert is D4.
- **Brute force.** A 6-digit code checked at ±1 step has 3 winning values per guess, so p ≈ 3·10⁻⁶.
  - Per token: 5 failures in 15 minutes lock rebinding for 5 minutes, doubling up to 1 hour (the login-lockout shape).
  - After 4 locks with no success in between (20 failures), rebinding is **disabled** for that token until re-login. The attacker's lifetime chance is then about 20·3·10⁻⁶ = 6·10⁻⁵.
  - The per-IP `rateLimit({limit: 5, windowMs: 60_000})` stays on as the outer layer. The DB counter is the real limit, because the in-memory limiter is per isolate and switched off in tests.
- **Replay.** The server stores the matched time step (`rebind_last_totp_step`) and accepts a code only if its step is strictly greater (RFC 6238 §5.2). Enforcement is in the UPDATE's WHERE clause, so two concurrent requests carrying the same code cannot both win. A replayed code gets 409 `TOTP_REPLAYED`, counts as a failure, and is audited.
  - Scope is per token, as ruled. D5 covers per-user scope.
  - `/auth/reauth/totp` has the same missing replay guard. That is noted in section 9 and out of scope.
- **Backup codes are refused**, following `verifyReauthTotp`'s reasoning (`private/account/src/services/auth.service.ts:461-464`): recovery codes should not be spent on routine moves. See D2.
- **Modes left untouched:**
  - `unbound` and `cloudflare` never reach the mismatch branch.
  - The rebind route refuses them with 409 `IP_REBIND_UNAVAILABLE {reason: "not_first_use"}`, which stops it being used to pin an executor token to one IP.
  - Tests confirm that both modes behave exactly as before.
- **`'unknown'` address.** A rebind whose `getClientIp` is `UNKNOWN_CLIENT_IP` gets 400 `CLIENT_IP_UNKNOWN`. Otherwise one header-less call could move a token to `'unknown'`, which every other header-less caller would then match.
- **The server stays the only authority.** The `rebind` hint in the 403 reveals whether the creator has 2FA. The rebind route would reveal the same thing, so the hint adds nothing (D7). The 403 never includes the bound IP.

## 3. Server (Writer A)

### 3.1 Wire contract (T0, `packages/shared/src/subscription/types.ts`)

```ts
export const TOKEN_IP_MISMATCH = 'TOKEN_IP_MISMATCH';
export type TokenIpRebindHint = 'totp' | 'relogin';
export interface TokenIpMismatchBody { error: string; code: typeof TOKEN_IP_MISMATCH; rebind: TokenIpRebindHint }
export const API_TOKEN_IP_REBIND_PATH = '/account/api/v1/api-token-ip/rebind';
export interface ApiTokenIpRebindRequest { code: string }            // /^\d{6}$/
export interface ApiTokenIpRebindResponse { rebound: boolean; boundIp: string }
```

Refusal codes, added to `ErrorCode` in `private/account/src/errors.ts`:

| Code | Status | When |
|------|--------|------|
| `TOKEN_IP_MISMATCH` | 403 | The middleware refused a first-use token from another IP |
| `TOTP_INVALID` (exists) | 400 | Wrong code; details carry `attemptsRemaining` |
| `TOTP_REPLAYED` | 409 | The code's step is at or below the last one used |
| `IP_REBIND_LOCKED` | 429 | The token is inside its lock window; details carry `retryAfter` and a `Retry-After` header |
| `IP_REBIND_DISABLED` | 403 | The failure cap was reached; only re-login helps |
| `IP_REBIND_UNAVAILABLE` | 409 | details `reason: 'not_first_use' \| 'no_creator' \| 'no_totp'` |
| `CLIENT_IP_UNKNOWN` | 400 | The caller's address cannot be determined |

### 3.2 Migration `0054_api_token_ip_rebind.sql` (T1)

Four columns on `api_tokens`, following the `loginAttempts` shape (`private/account/src/db/schema.ts:76-82`):
- `rebind_failed_attempts integer NOT NULL DEFAULT 0`
- `rebind_last_failed_at text`
- `rebind_locked_until text`
- `rebind_lock_count integer NOT NULL DEFAULT 0`

A fifth column for replay:
- `rebind_last_totp_step integer`

Also:
- a journal entry with idx 54 (`drizzle/meta/_journal.json`; 0053 is the last one);
- no new table, so the scope-audit registry is untouched.

Constants in `private/account/src/constants.ts`:

```
API_TOKEN_REBIND_MAX_FAILED=5
API_TOKEN_REBIND_WINDOW_MS=15m
API_TOKEN_REBIND_BASE_LOCK_MS=5m
API_TOKEN_REBIND_MAX_LOCK_MS=1h
API_TOKEN_REBIND_DISABLE_AFTER_LOCKS=4
```

### 3.3 `verifyCodeStep` (T1, `private/account/src/utils/totp.ts`)

Add `verifyCodeStep(secret, code, now?) → Promise<number | null>`, which returns the counter that matched. Then `verifyCode` becomes `(await verifyCodeStep(...)) !== null`. Existing callers are unchanged.

### 3.4 Middleware (T2, `private/account/src/middleware/api-token.ts`)

- **Extract `resolveApiToken(c)`.** It covers the header, `validate`, and the archived-team check (`:10-29`), and returns the token. `apiTokenAuth` calls it and then does scopes and the IP check as before.
- **The mismatch branch** (`:58-59`) throws `AppError('Token is bound to a different IP address', 403, ErrorCode.TOKEN_IP_MISMATCH, { rebind })`.
  - `rebind` is `'totp'` when `createdByUserId` resolves to a user with `totpEnabled`, otherwise `'relogin'`.
  - The user lookup runs only on this failure branch.
  - The message text stays byte-identical, so older CLIs still match it.
- **The `cloudflare` 403 and the other branches are not changed.**

### 3.5 Route (T3, new `private/account/src/routes/api-token-ip.ts`)

Mounted at `app.route('/api-token-ip', apiTokenIpRoute())` in `private/account/src/routes/index.ts`, next to `/proxy`, with a comment explaining why it is not under `/api-tokens`. See D1.

`POST /rebind` is wrapped in `rateLimit({limit: 5, windowMs: 60_000})` and `responds(apiTokenIpRebindResponse)`. The handler's order matters:

1. `resolveApiToken(c)`: 401 for invalid, expired or revoked; 403 when the team is gone. **No scope is required and there is no IP check.** This is the only caller of `resolveApiToken` apart from `apiTokenAuth`; the gate is in section 8.
2. `ipBinding !== 'first-use'`: 409 `not_first_use`, audited.
3. `clientIp === UNKNOWN_CLIENT_IP`: 400 `CLIENT_IP_UNKNOWN`.
4. `boundIp === null || boundIp === clientIp`: 200 `{rebound: false, boundIp: clientIp}`. Nothing is written and no TOTP is used up. This keeps two parallel CLI processes idempotent.
5. Creator is null, or the user is missing: 409 `no_creator`, audited. The user has no TOTP: 409 `no_totp`, audited. The message says: "Two-factor authentication is not enabled for the user who created this token. Run `rdc subscription login` to create a new token".
6. `rebind_lock_count >= DISABLE_AFTER_LOCKS`: 403 `IP_REBIND_DISABLED`, audited.
7. `rebind_locked_until > now`: 429 `IP_REBIND_LOCKED` with `retryAfter`, audited. The counter does not increase.
8. Parse the body with `z.object({ code: z.string().regex(/^\d{6}$/) })`. A malformed body gets 400 from the ZodError path and does not count (it cannot be a real guess).
9. `step = verifyCodeStep(user.totpSecret, code)`. If it is null, call `apiTokenService.recordRebindFailure(id)`, which is one atomic UPDATE … RETURNING in the same shape as `private/account/src/services/user.service.ts:314-373`. The answer is 400 `TOTP_INVALID {attemptsRemaining}`, or 429 when this failure triggers the lock. Audited.
10. `apiTokenService.rebindIp(id, clientIp, step)`. It runs as one UPDATE:

    `SET bound_ip=?, rebind_last_totp_step=?, rebind_failed_attempts=0, rebind_lock_count=0, rebind_locked_until=NULL, last_used_at=now WHERE id=? AND revoked_at IS NULL AND ip_binding='first-use' AND (rebind_last_totp_step IS NULL OR rebind_last_totp_step < ?)`

    If no row changed, the result is 409 `TOTP_REPLAYED`, which also counts as a failure and is audited. The same WHERE clause closes the race with a concurrent revoke.
11. Audit the success, then return 200 `{rebound: true, boundIp: clientIp}`.

Routes may not import the database layer (`check:ci-account-layer-isolation`), so every query lives in `ApiTokenService`.

### 3.6 Audit (T3)

`eventLogService.log` writes these fields:
- `source: 'api'`
- `userId: createdByUserId`
- `actorTokenId: token.id`
- `subscriptionId` and `teamId`
- `orgId` from the subscription row

Two event types:
- `api_token.ip_rebound` with data `{ tokenId, name, fromIp, toIp }`;
- `api_token.ip_rebind_failed` with data `{ tokenId, name, reason: 'totp_invalid'|'totp_replayed'|'locked'|'disabled'|'no_totp'|'no_creator'|'not_first_use', boundIp, attemptedIp, attemptsRemaining? }`.

The `api_token.` prefix already files both under "security" (`private/account/src/routes/portal.ts:803`, `private/account/src/routes/root.ts:671`). Add titles and descriptions next to `api_token.revoked` in `private/account/src/routes/portal.ts:882-883/899-904` and `private/account/src/routes/root.ts:794-797/820-823`:
- "API token moved to a new IP"
- "API token IP move refused"

### 3.7 DTO (T3, `private/account/src/dto/api-token.dto.ts`)

Add `apiTokenIpRebindResponse = z.object({ rebound: z.boolean(), boundIp: z.string() })`, exported through `dto/index.ts`. Error bodies pass through `responds` unchanged (`private/account/src/middleware/responds.ts:22-23`).

## 4. CLI (Writer B)

### 4.1 `accountServerFetch` (T5, `packages/cli/src/services/account/account-client.ts`)

- **Split the function.** Move the current body into `accountServerFetchOnce(path, options, token)`, where the token is resolved once by the wrapper so that the retry and the rebind use the *same* token (whether stored, `REDIACC_TOKEN`, or `options.token`).
- **Keep the body.** `createAccountError` also keeps the parsed body as `details`, so `rebind`, `retryAfter` and `attemptsRemaining` reach the caller.
- **The wrapper:**
  ```
  try once
  catch e: if e.status===403 && e.code===TOKEN_IP_MISMATCH && !options.noAuth && options.ipRebind !== false
             → await ensureRebound({ token, serverUrl, hint: e.details.rebind })   // may throw
             → return accountServerFetchOnce(path, {...options}, token)            // exactly once, no second catch
  ```
- **A second mismatch** after a successful rebind throws `errors.subscription.ipRebind.stillMismatched`. That can happen, for example, when IPv4 and IPv6 egress alternate (section 9). The CLI does not prompt again.
- **New option.** `AccountFetchOptions.ipRebind?: boolean`, default true.

### 4.2 `ensureRebound` (T5, new `packages/cli/src/services/account/token-ip-rebind.ts`)

- **Single flight per token.** A module-level `Map<tokenHash, Promise<void>>`: parallel callers (license batch refresh, relay polling) share one prompt and one POST. A failed or declined outcome is cached for the rest of the process, so later 403s fail at once without prompting again.
- **`hint === 'relogin'`** throws `errors.subscription.ipRebind.reloginOnly`.
- **Non-interactive.** When `process.stdin.isTTY !== true` or `process.stderr.isTTY !== true`, throw `errors.subscription.ipRebind.nonInteractive`, which names both remedies:
  - run any `rdc` command, for example `rdc subscription status`, in an interactive terminal and enter the authenticator code;
  - or run `rdc subscription login`.

  The thrown error keeps `status: 403` and `code: TOKEN_IP_MISMATCH`, so call-site handling that checks status or code does not change.
- **Interactive.** Inside `suspendSpinner(...)`, ask for the code with `askInput(t('errors.subscription.ipRebind.prompt'), /^\d{6}$/)`, then `accountServerFetchOnce(API_TOKEN_IP_REBIND_PATH, { method: 'POST', body: { code }, ipRebind: false }, token)`.
  - `TOTP_INVALID` or `TOTP_REPLAYED`: print `wrongCode` or `replayed` (the replay message says to wait for the next code) and prompt again. At most 3 entries per process.
  - `IP_REBIND_LOCKED`: throw `locked {minutes}`.
  - `IP_REBIND_DISABLED`: throw `disabled`.
  - `IP_REBIND_UNAVAILABLE`: throw `reloginOnly` or `notFirstUse`.
  - On success, print `moved {ip}` to stderr.

### 4.3 Prompt and spinner helpers (T5)

- `packages/cli/src/utils/prompt.ts`: add `askInput(message, pattern)`, a visible `input` prompt with validation, built on the same lazy `getPrompt`. Pass `output: process.stderr` so `--output json` stdout stays clean. TOTP codes are short-lived and protected against replay, so hidden input is not needed.
- `packages/cli/src/utils/spinner.ts`: add `suspendSpinner(fn)`, which stops `currentSpinner`, runs `fn`, then restarts it with the same text.

### 4.4 Background callers opt out (T5)

These callers pass `ipRebind: false`, because a prompt during a timed-out background send or an exit flush would be wrong:
- the audit flush, `packages/cli/src/services/core/audit.ts:139`;
- the telemetry credentials fetch, `packages/cli/src/services/telemetry/otlp-credentials.ts:69`.

Both already treat a failure as non-fatal.

### 4.5 Remove the one-off match (T6)

- In `packages/cli/src/commands/config-remote-password.ts`, delete the `bound to a different IP` branch (`:45-47`).
- Add a first line to `describeEnrollForbidden`: `if (code === TOKEN_IP_MISMATCH) return message;`. The central path has already produced the localized text.
- Rewrite the comment at `:26-36`: the IP case now has a code and is handled in `accountServerFetch`, and the remaining text matches cover the other bare `HTTPException`s.
- Delete `commands.config.remote.enable.passwordIpBound` from all 13 `cli.json` files, then run `generate:cli-contract` so the `commands.*` bundle in `packages/shared/src/cli-contract/data/i18n/*.json` drops it. `check:ci-dead-translation-keys` would flag it otherwise.

## 5. What does not change

- The `unbound` and `cloudflare` middleware branches.
- `/proxy/introspect`.
- Config-token IP binding (`private/account/src/services/config.service.ts:916`, `ip_mismatch`). That is a separate credential with a short lifetime, rotated on every use, and the CLI re-mints it (section 9).
- The creation paths, and the portal token list DTO. `boundIp` already shows the new address after a move.

## 6. Tests

### 6.1 Account integration (new `private/account/tests/integration/api-token-ip-rebind.test.ts`)

**Setup.** Build it the same way as `private/account/tests/integration/api-token-ip-binding.test.ts:30-115`. Enable 2FA the way `private/account/tests/integration/auth.test.ts:1000` does, and mint codes with `generateCode`.
- The "next step" is `generateCode(secret, Date.now() + 30_000)`.
- `vi.setSystemTime` moves the clock.
- The token binds from `x-forwarded-for: IP_A`, and then the move uses `IP_B`.

**Cases:**
1. **Code on the refusal.** A request from `IP_B` gets 403 with `code === 'TOKEN_IP_MISMATCH'`, `rebind === 'totp'` and the message unchanged. `lastUsedAt` is unchanged, so the refusal writes nothing.
2. **Happy path.** A rebind from `IP_B` with a valid code returns 200 `{rebound: true, boundIp: IP_B}`, and the response passes the DTO airlock (`helpers/dto-assert.ts`). Afterwards `/proxy/introspect`, or any `apiTokenAuth` route, works from `IP_B` and gets 403 `TOKEN_IP_MISMATCH` from `IP_A`.
3. **Through the tunnel.** The rebind binds to the outer `x-forwarded-for`, and an inner spoofed `x-forwarded-for` is ignored (the precedent is `private/account/tests/integration/tunnel.test.ts:214-222`).
4. **A stolen token alone.** Wrong code → 400 `TOTP_INVALID` with `attemptsRemaining: 4`. `bound_ip` is still `IP_A`.
5. **Reused code.** The same code a second time after a success gets 409 `TOTP_REPLAYED`, and so does an older step. Two concurrent rebinds with one code (`Promise.all`) produce exactly one 200.
6. **Lockout.** Five wrong codes give 429 `IP_REBIND_LOCKED` with `Retry-After`. A *correct* code inside the lock window is still refused. After the lock expires, a correct code succeeds and the counters reset. Four locks in a row give 403 `IP_REBIND_DISABLED`.
7. **Revoked token.** The token is revoked through `DELETE /api-tokens/:id`, and the rebind gets 401.
8. **User without TOTP.** The mismatch 403 has `rebind: 'relogin'`, and the rebind gets 409 `IP_REBIND_UNAVAILABLE {reason: 'no_totp'}`. A token whose `createdByUserId` is null gets `no_creator`.
9. **Other modes untouched.** An `unbound` proxy:exec token is accepted from two IPs, the rebind gets 409 `not_first_use`, and `bound_ip` stays null. The same holds for `cloudflare`.
10. **No-op cases.** The rebind from the already-bound IP returns `{rebound: false}` and uses no TOTP (the same code then works from a new IP). A header-less rebind gets 400 `CLIENT_IP_UNKNOWN`.
11. **Audit rows.** The success writes one `api_token.ip_rebound` row with `fromIp`/`toIp` and `actorTokenId`. Every refusal in cases 4-9 writes `api_token.ip_rebind_failed` with the right `reason`. The portal activity feed shows the new titles.
12. **Outer limiter.** A test with `rateLimit({force: true})` shows the route's per-IP limiter answering 429.

**Mutation controls** (each must turn a named test red):
- remove the `rebind_last_totp_step <` condition → case 5;
- skip the lock check → case 6;
- mount the route behind `apiTokenAuth()` → cases 2 and 3;
- drop the `ipBinding` check → case 9;
- drop the failure audit → case 11;
- revert the middleware to `HTTPException` → case 1;
- accept backup codes → a case-4 variant that sends a backup code.

### 6.2 CLI vitest

**New `packages/cli/src/services/__tests__/account-client-ip-rebind.test.ts`.**
- Mock `@rediacc/shared/e2e` `sealRequest`/`openResponse` so they pass values through, stub `globalThis.fetch` with a scripted queue of inner responses, and mock `utils/prompt.js`.
- Set `isTTY` through `Object.defineProperty` (the precedent is `packages/cli/src/utils/__tests__/prompt.test.ts:18`).

Cases:
- **TTY:** 403 mismatch → one prompt → a POST to the rebind path carrying the same `Authorization` and `{code}` → the original request is replayed → the result is returned. There are exactly 3 fetches.
- **Retry once:** the rebind returns 200, but the retry is 403 again → `stillMismatched` is thrown, the prompt ran once, and there are 3 fetches.
- **Non-TTY:** no prompt, one fetch, and a message naming both remedies. `status` and `code` are kept.
- **`rebind: 'relogin'`** on a TTY: no prompt, and the message says re-login.
- **Wrong, then right:** two prompts and one success. After three wrong codes the CLI gives up.
- **Locked:** a 429 gives the `locked` message with minutes, and no further prompt.
- **Concurrency:** two parallel calls both hit the mismatch → one prompt and one rebind POST, and both are retried.
- **Opt-outs:** with `ipRebind: false` there is no prompt, and `noAuth` never triggers the path.
- **Explicit token:** `options.token` is the token used for the rebind.
- **Spinner:** `suspendSpinner` is called around the prompt.

**`config-remote-password.test.ts`.**
- Delete the IP entry from `forbiddenCases` (`:288-292`).
- Add a test: an enroll 403 with `code: 'TOKEN_IP_MISMATCH'` surfaces the central message unchanged.
- Add a source assertion: `config-remote-password.ts` does not contain `bound to a different IP`.

**Mutation controls:**
- turn the retry into a loop → "retry once" goes red (the scripted fetch queue runs dry);
- remove the single flight → the concurrency case goes red;
- remove the TTY check → the non-TTY case goes red (the prompt mock is called);
- stop resolving the token once → the explicit-token case goes red.

### 6.3 E2E

Not added. The account integration suite drives the real stack, including the tunnel. The T9 live smoke covers the CLI end to end.

## 7. i18n and docs (T8)

- **CLI, 13 `packages/cli/src/i18n/locales/*/cli.json`.** New keys under `errors.subscription.ipRebind`:
  - `prompt`, `moved`, `wrongCode`, `replayed`, `locked`, `disabled`, `reloginOnly`, `notFirstUse`, `nonInteractive`, `stillMismatched`.
  - These are under `errors.*`, not `commands.*`, so the contract bundle is unaffected apart from the removal in section 4.5.

  Gates:
  - `check:ci-i18n-cli-key-usage`;
  - `check:ci-i18n-cross-locale`;
  - `check:ci-em-dash-surfaces` (no em dashes in the new strings).
- **Docs, `packages/www/src/content/docs/*/account-security.md` (13).**
  - Replace the bullet at en:37 ("IP binding: first request locks the token to that IP address").
  - Add a short `When your IP address changes` subsection:
    - an interactive CLI asks for your authenticator code and moves the token;
    - automation must run one interactive command or `rdc subscription login`;
    - without 2FA, re-login is the only remedy;
    - wrong codes lock the move and too many disable it;
    - executor tokens (`unbound`/`cloudflare`) are unaffected.
  - Regenerate the translation hashes and the `packages/www/public/search-index*.json` files through their generators, not by hand.
  - `validate:translation-freshness` and `validate:content` must pass.

## 8. Removal sweep and single-caller gate (T9)

- `rg -n "bound to a different IP" packages/cli/src --glob '!**/__tests__/**'` returns nothing.
- `rg -n "passwordIpBound" packages/cli/src packages/shared/src` returns nothing.
- `rg -n "resolveApiToken\(" private/account/src` returns exactly two call sites: `middleware/api-token.ts` and `routes/api-token-ip.ts`. Add this as a case in the integration file that reads the source tree, the same way other account source assertions do, so that a new route skipping the IP check fails CI.

## 9. Operator decisions still open (recommended option first)

- **D1. Route path.**
  - Recommended: `POST /account/api/v1/api-token-ip/rebind`, its own prefix, following the `/proxy` precedent (`private/account/src/routes/index.ts:109-113`).
  - Alternative: `/api-tokens/rebind-ip`, which means moving `sessionAuth` from `use('*')` to each route in `api-tokens.ts`.
- **D2. Backup codes.**
  - Recommended: refuse them, as `verifyReauthTotp` does.
  - Alternative: accept one and spend it.
- **D3. Lockout numbers.**
  - Recommended: 5 failures per 15 minutes; a lock that doubles from 5 minutes to 1 hour; rebinding disabled after 4 locks (20 failures), until re-login.
  - Alternative: auto-revoke the token at the cap.
- **D4. User notification.**
  - Recommended: audit rows only in this plan, with an email on a successful move as a follow-up. A new email template means 13 localized templates and `check-account-email-templates`.
  - Alternative: send the email now.
- **D5. Replay scope.**
  - Recommended: per token, as ruled.
  - Alternative: per user (`users.totp_last_step`), which would also close the same gap in `/auth/reauth/totp` and 2FA login, but would refuse two token moves within one 30-second step.
- **D6. IPs in the audit data.**
  - Recommended: yes, `fromIp`/`toIp`. That is how the operator tells an ISP change from a theft.
  - Alternative: store a hash.
- **D7. The `rebind` hint in the 403.**
  - Recommended: include it. The rebind route reveals the same fact, and it saves a prompt that can never work.
  - Alternative: omit it, and let the CLI find out from `IP_REBIND_UNAVAILABLE` after prompting.
- **D8. Code name.**
  - Recommended: `TOKEN_IP_MISMATCH`, following the `ErrorCode` UPPER_SNAKE convention (`private/account/src/errors.ts:1-80`), plus a separate `rebind` field. The code names the refusal, and the hint names the remedy.
  - Alternative: `ip_rebind_available`, which would be wrong for users without TOTP.
- **D9. A dedicated command** (`rdc subscription rebind-ip [--code]`).
  - Recommended: not now. Any interactive command is the remedy, and a new command touches the contract, the docs and the tutorial gates.
  - Alternative: add it now for scripted TOTP entry.

**Out of scope, noted:**
- **Dual-stack churn.** When one machine's egress alternates between IPv4 and IPv6, it flips the binding and causes repeated prompts. A follow-up could bind IPv6 by /64.
- **Config tokens** keep their own binding (`private/account/src/services/config.service.ts:916`).

## 10. Risks and sequencing

- **Deploy order.** Deploy the server first. An old CLI with a new server keeps its current behaviour: the message is unchanged and the one-off match still works. A new CLI with an old server sees no `code`, so the raw message passes through as before. Neither order breaks anything.
- **D1/SQLite atomicity.** Both the failure counter and the move are single UPDATE statements with RETURNING or row-count checks. No step reads a value and then writes it back.
- **Merge conflicts** with the relay-only plan on `config-remote-password.ts`, `cli.json` and `account-security.md`. B starts T6 and T8 only after that plan's console commit (Depends-On).

### Critical Files for Implementation
- /home/developer/console/private/account/src/middleware/api-token.ts
- /home/developer/console/private/account/src/services/api-token.service.ts
- /home/developer/console/private/account/src/routes/index.ts (mount), plus the new private/account/src/routes/api-token-ip.ts
- /home/developer/console/packages/cli/src/services/account/account-client.ts
- /home/developer/console/packages/cli/src/commands/config-remote-password.ts

## Decisions taken (2026-09-25, lead, operator may override)

D1-D9 take the recommended option: `/api-token-ip/rebind` route; backup codes refused; lockout 5/15min doubling 5min-1h, disabled after 4 locks; audit rows only (email alert a follow-up); replay scope per token; fromIp/toIp in audit data; the `rebind` hint in the 403; code `TOKEN_IP_MISMATCH`; no dedicated command.

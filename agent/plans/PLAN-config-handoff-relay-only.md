# PLAN: the server relay is the only way config keys reach the CLI (`rdc config remote enable`, `rdc config rotate-cek`)

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-app-wide-org-selection.md -- its uncommitted working-tree edits touch the same files: `private/account/src/routes/device-codes.ts` (the approve route's org id), `private/account/web/src/auth/ProtectedRoute.tsx`, `private/account/e2e/src/utils/config-store-helpers.ts` and `private/account/e2e/tests/20-config-storage/20-11-prf-provider-matrix.test.ts` (`git -C private/account status`, 2026-09-25). Also PLAN-config-passkey-optional.md, which is `approved` with T1-T4 open, yet its code looks landed (`02cb4bf`, `a11c397`, `af08d91`). The lead should confirm and close it before T5 deletes `DeviceConfigSetup.tsx`, which that plan edits.
Priority: P1 -- proposed by AI. The operator is blocked: `rdc config remote enable` from WSL with a Windows browser ends in "Setup failed / Failed to fetch".
Concurrency: parallel
Owns: private/account/src/routes/device-codes.ts, private/account/src/services/device-code.service.ts, private/account/src/dto/device-code.dto.ts, private/account/src/db/schema.ts (device_codes block only), private/account/drizzle/0053_*.sql, private/account/drizzle/meta/**, private/account/src/constants.ts (DEVICE_CODE_* only), private/account/tests/integration/config-remote.test.ts, private/account/tests/integration/device-code-handoff.test.ts, private/account/web/src/pages/{ConfigRemote,ConfigSetup,DeviceConfigSetup}.tsx, private/account/web/src/lib/{config-handoff,cli-handoff-request}.ts, private/account/web/src/lib/__tests__/**, private/account/web/src/pages/__tests__/config-remote*.test.tsx, private/account/web/src/router.tsx (config routes only), private/account/web/src/auth/ProtectedRoute.tsx (the redirect line only), private/account/web/src/i18n/locales/*/configStorage.json, private/account/e2e/src/utils/config-store-helpers.ts, private/account/e2e/tests/20-config-storage/{20-03,20-11}-*.test.ts, packages/cli/src/commands/config-remote*.ts, packages/cli/src/commands/__tests__/config-remote-*.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/src/config/command-planes.ts (one comment), packages/shared/src/config-crypto/handoff.ts, packages/shared/src/config-crypto/__tests__/handoff-pairing.test.ts, packages/shared/src/cli-contract/data/**, packages/www/src/content/docs/*/{config-storage,account-security,cli-application}.md, docs/DESIGN-CONFIG-STORAGE.md, docs/design/spec/03-cli-contracts.md, .claude/skills/rdc/config-storage.md
Worklist: (lead adds this with `worklist.py --add`)

**Operator order, 2026-09-25 (verbatim):** `For cli './rdc.sh config remote enable', I got 'Enroll this device / Hand your encrypted config keys to the CLI waiting on your device. / Setup failed / Failed to fetch'. I found browser to cli a bit risky to communicate. As you can see we're in WSL but the browser on windows side. What about having a mechanism between cli<->server<->browser so no cli to browser. I suppose the current architecture was for safety. But I think cli can generate asymmetric key and share the public one to browser and server can use that key to eliminate man in the middle attacks. If that make sense employ a planning agent.`

**Line numbers** are from the working tree on `0923-1`, measured 2026-09-25. `private/account` has uncommitted org-selection edits, so each citation also names a function or string to re-anchor on.

## Tasks

At most three writers, and their Owns do not overlap:
- **A** owns the server: `private/account/src/**`, `tests/integration/**` and `drizzle/**`.
- **B** owns the portal and E2E: `private/account/web/src/**` and `e2e/**`.
- **C** owns the CLI, shared code, i18n and docs.

T1 freezes the contract. The submodule PR (A and B) lands first, then the console PR (C, plus the pointer bump).

- [ ] T1 [lead] Freeze the contract before anyone forks:
  - the endpoint shapes in section 3.2;
  - the fragment URL grammar in section 4.1;
  - the sealed-plaintext field `handoffNonce`;
  - `handoffKeyHash()` and `handoffPairingCode()` in `packages/shared/src/config-crypto/handoff.ts`, with the known-answer vector (section 5).

  Put these in the shared module first. B and C both import them.
- [ ] T2 [A] Migration `0053_device_code_handoff.sql` plus the schema change (section 3.1).
- [ ] T3 [A] The service and routes: create with purpose, `handoff-request`, the guarded `config-handoff`, atomic `claim`, `cancel`, the purpose fence on `approve` and GET poll, and the expired-row purge (sections 3.2 and 6). The DTOs change with them.
- [ ] T4 [A] Integration tests and mutation controls (section 7.2).
- [ ] T5 [B] Portal:
  - new `web/src/lib/cli-handoff-request.ts`;
  - a pairing-code step;
  - ConfigRemote and ConfigSetup post only to the relay;
  - delete `DeviceConfigSetup.tsx` and the `/account/device-config` route;
  - the router drops its `callback` branches;
  - ProtectedRoute keeps the URL hash (section 4.3).
- [ ] T6 [B] Portal locales: 13 `configStorage.json` files plus `.translation-hashes.json` (section 8.2). Add the portal unit tests (section 7.3).
- [ ] T7 [B] E2E: delete the helper `startCallbackServer`, add relay helpers, rewrite 20-11 (e) and (f), add (h) "tampered link", and repoint 20-03 (section 7.4).
- [ ] T8 [C] CLI:
  - new `packages/cli/src/commands/config-remote-relay.ts`;
  - delete `startCallbackServer`, `enableBrowser` and `--headless`;
  - `rotateCek` uses the relay;
  - login is required;
  - print the pairing code;
  - deadline-based polling with backoff, and cancel on Ctrl+C (sections 4.2 and 6).
- [ ] T9 [C] CLI tests and mutation controls (section 7.1). Add the shared known-answer test.
- [ ] T10 [C] CLI i18n in 13 locales, `generate:cli-contract`, the www docs in 13 locales, the design docs and the skill doc (section 8).
- [ ] T11 [lead] Closure: the removal sweep in section 9 returns nothing. Deploy the account server (eu) before the CLI release. Then do a live smoke of the operator's exact case: CLI in WSL, browser on Windows, `./rdc.sh config remote enable` for both a fresh store and an existing one, plus `config rotate-cek`.

## 0. What the code does now, and corrections to the brief

The brief's context holds, with these additions and corrections:

1. **There are three portal pages, not two.**
   - First-time setup exists twice: `ConfigSetup.tsx` (loopback only: `callbackUrl` at :151, the POST at :315) and `DeviceConfigSetup.tsx` (relay only: the POST at :215).
   - `ConfigRemote.tsx` sends a missing store to one or the other based on `callback` (:106-113), and posts to whichever transport the URL names (:182-199).
   - With one transport, `DeviceConfigSetup` is a duplicate. This plan deletes it and makes ConfigSetup relay-only.
2. **There are two loopback users in the CLI, both in `packages/cli/src/commands/config-remote.ts`:**
   - `enableBrowser` (:114-152);
   - `rotateCek` step 2 (:436-490).

   The other `createServer` hits are not handoffs: `services/executor/daemon/server.ts:92`, `services/repo/repo-ssh-tunnel.ts:40,74` and the templates in `embedded.generated.ts`. The E2E suite has its own copy: `private/account/e2e/src/utils/config-store-helpers.ts:764-820` (`startCallbackServer`), used by 20-11 (f) (:349-412).
3. **A likely extra cause of "Failed to fetch".** The loopback binds `127.0.0.1` (config-remote.ts:95) but advertises `http://localhost:<port>` (:126). If the browser resolves `localhost` to `::1`, nothing is listening there. From Windows to WSL2 it also depends on WSL's localhost forwarding. None of this matters once the loopback is gone.
4. **Anyone can seal a payload to the CLI.** The public key is in the URL, and ECIES has no sender authentication. Today any signed-in account that learns the device code and key can POST `config-handoff` (device-codes.ts:34-42; the only check is `sessionAuth`) with a handoff for **its own** store. On a fresh store, `applyHandoff` then **seeds that store with the victim's local config** (config-remote-enable.ts header :5-14: a 404 means "push the local config"). The attacker holds the CEK, so the victim's SSH keys and machine inventory are exfiltrated.

   The device code and key travel in the query string, so they show up in server logs, browser history and Referer. This is the weightiest risk. Sections 2 and 3 close it with user binding plus a secret nonce in the URL fragment, returned inside the sealed plaintext.
5. **Login and handoff device codes are not separated.**
   - `approve` (device-code.service.ts:113+) mints an API token on any pending code.
   - `storeConfigHandoff` (:88-111) accepts any pending code.
   - GET poll (:56-86) returns either one.
   - Both flows share `device_codes` (schema.ts:547-562).
6. **Consumption is one-shot but not atomic.**
   - `poll` runs select, then delete, then return (:65-83). Two concurrent polls can both read the blob.
   - `storeConfigHandoff` runs select, check, then update (:88-111).
7. **The CLI hides every polling error.** `pollOnce` (config-remote.ts:183-186) treats any non-ValidationError as "pending": network down, 404 on an unknown route, 429 or 5xx. The operator waits the full 10 minutes (`DEVICE_CODE_TTL_MS`, constants.ts:45) with no signal.
8. **The login redirect drops the URL hash.** `ProtectedRoute.tsx:27` stores `from: location.pathname + location.search`. The fragment design in section 4 needs `+ location.hash`.
9. **A factual error in PLAN-app-wide-org-selection.md:139.** It says the `config-handoff` fetches "have no auth by design (device-codes.ts:34)". Line 34 uses `auth` (`sessionAuth`), so they do require auth. That plan's `ORG_SCOPED_PREFIXES` will add `X-Org-Id` to the new `/device-codes/*` calls, which is harmless. Tell that plan's owner.
10. **The prerequisite check stays.** `checkEnablePrerequisites` (config-remote-enable.ts:57-96, route `/configs/enable-requirements` at configs.ts:405-421) is kept. Its no-token branch (:88-95) becomes a refusal (decision D1).

## 1. Target flow (one transport)

```
CLI (WSL)                          Account server                     Browser (anywhere)
1 keypair X25519 (ephemeral)
  nonce N (32B), pollSecret S (32B)
2 POST /device-codes  [Bearer login token]
  {purpose:'config-handoff', keyHash=H(spki), pollVerifier=H(S)}
                                   row: bound_user_id, key_hash, poll_verifier, TTL 15m
  <- {deviceCode D, interval, expiresIn}
3 print URL  <api>/account/config-remote#code=D&key=<spki>&nonce=N
  print pairing code P = code(H(spki)) and "approve as <email>"
4 POST /device-codes/D/claim {S}  (every 5s, backoff)      5 page reads the fragment (never sent to server)
                                   GET /device-codes/D/handoff-request [session]
                                   -> {status, keyHash, boundToYou, expiresAt}
                                                                   page: H(url key)==keyHash, boundToYou, pending
                                                                   user TYPES P from terminal; page compares to code(H(url key))
                                                                   unlock / create store, seal {..., handoffNonce:N} to url key
                                   POST /device-codes/D/config-handoff [session+2FA]
                                   {encryptedBlob, keyHash}: re-checks bound user, keyHash, pending, TTL (conditional UPDATE)
6 claim -> {status:'complete', configHandoff}  (DELETE ... RETURNING, one shot)
7 decrypt, require handoffNonce==N, apply, success
Ctrl+C: DELETE /device-codes/D {S}
```

## 2. Threat model

| Attacker | What they can do today | After this plan |
|---|---|---|
| A process on the CLI host, or the Windows/WSL network path | Sniff or race the loopback POST (plaintext HTTP, but sealed). Nothing to gain beyond DoS. | No loopback exists. |
| Link tamperer who swaps only `key` (clipboard, chat, terminal log, shoulder surf) | Page seals to the attacker's key and posts to the victim's code, and the attacker reads it if they can poll. | Server compares `keyHash` with the key it bound at creation: **fails closed**. The page also refuses before unlock. |
| Link tamperer who swaps the whole link (own device code, key and nonce) | Full CEK and slot-secret theft. | The attacker's device code is bound to the attacker's account, so the page shows `this request is not from your account` and refuses. If the attacker holds the victim's CLI login token and can mint a victim-bound code, the **typed pairing code** still fails: the victim types P from their own terminal, and it will not match the code derived from the attacker's key. |
| Third party who learns D and key (server logs, history, Referer) and forges a handoff for their own store (section 0 item 4) | Makes the victim's CLI seed its local config into the attacker's store. | The fragment keeps D, key and N out of server logs and Referer. The binding rejects POSTs from other users. The CLI rejects any plaintext whose `handoffNonce` is not N. |
| Someone who races the claim to consume the blob (DoS) | Unauthenticated GET poll deletes the blob. | Claim requires S, which never leaves the CLI. A wrong S returns the same 404 as an unknown code and consumes nothing. |
| Relay or DB insider (reads or writes `device_codes`) | Reads ciphertext only. Can write a forged blob sealed to the public key (the key reached it via the query string). | Reads ciphertext only. A forged blob fails the nonce check (N lives only in the fragment and the sealed plaintext). The key hash is stored, not the key. |
| **Malicious origin** (serves the page JavaScript) | Everything. | **Still everything.** The JavaScript it serves can read the fragment, skip the pairing check and exfiltrate the unlocked secret. Zero-knowledge here rests on trusting the served code, as it does for every other portal page that handles the CEK. The fingerprint defends against link tampering and relay-side swaps, **not** a compromised origin. The docs must say this plainly. |

**Pairing code strength.** P is the first 60 bits of SHA-256(SPKI), written as 12 characters over the 32-symbol alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (exactly 5 bits per symbol, so no modulo bias) and formatted `XXXX-XXXX-XXXX`.

40 bits (8 characters) is too few. A GPU attacker who has the link can derive public keys incrementally and hash them at better than 1e9 per second, which reaches 2^39 within the TTL. 60 bits is out of reach. Typing 12 characters matches the existing 10-character user code (device-code.service.ts:10-20).

Words are rejected: the wordlist would have to be stable across 13 locales, and comparing words invites partial matching.

## 3. Server (Writer A, `private/account`)

### 3.1 Schema and migration

`src/db/schema.ts:547-562`, in `device_codes`, add:
- `purpose text NOT NULL DEFAULT 'login'`, one of `'login'` or `'config-handoff'`;
- `bound_user_id text`;
- `handoff_key_hash text` (base64url SHA-256 of the SPKI bytes);
- `poll_verifier text` (base64url SHA-256 of S).

Add the migration `drizzle/0053_device_code_handoff.sql` (after `0052_api_token_ip_binding.sql`) and update the meta journal. Check `src/db/scope-registry.ts:114`, which lists `deviceCodes`, for any column rules.

Constants (`src/constants.ts:45`): `config-handoff` codes use the existing `DEVICE_CODE_TTL_MS` (10 minutes, operator ruling D3); add only `MAX_PENDING_HANDOFFS_PER_USER = 5`.

### 3.2 Routes (`src/routes/device-codes.ts`) and service (`src/services/device-code.service.ts`)

- **`POST /device-codes`** (currently :17-23):
  - An empty body keeps today's login behaviour.
  - A body with `{purpose:'config-handoff', keyHash, pollVerifier}` requires `apiTokenAuth('subscription:read')` and sets `bound_user_id = apiTokenCreatedByUserId`. It returns 403 when the token has no user, mirroring configs.ts:410-412.
  - Validate both hashes as 43-character base64url.
  - Refuse with 429 past `MAX_PENDING_HANDOFFS_PER_USER`.
  - Purge expired rows opportunistically: `DELETE WHERE expires_at < now`.
  - The response adds `expiresAt`.
- **`GET /device-codes/:deviceCode/handoff-request`** (new; sessionAuth; rate limit 30 per minute):
  - Returns 404 unless the purpose is `config-handoff`, the row is pending and not expired.
  - Otherwise returns `{status, keyHash, boundToYou: bound_user_id === userId, expiresAt}`. It never returns the bound user's email.
- **`POST /device-codes/:deviceCode/config-handoff`** (:33-42):
  - Middleware is `approveLimit, sessionAuth, requireTwoFactor()`.
  - Body `{encryptedBlob: string, keyHash: string}`.
  - The service does a single conditional `UPDATE ... SET status='complete', config_handoff_blob=? WHERE device_code=? AND purpose='config-handoff' AND status='pending' AND expires_at > now AND bound_user_id=? AND handoff_key_hash=?`, then checks the changed-row count.
  - On 0 rows, re-select only to choose the status: 404 for unknown or wrong purpose, 403 for a different user, 409 for a key mismatch or a code that is not pending, 410 for expired.
  - Cap `encryptedBlob` at 64 KiB.
- **`POST /device-codes/:deviceCode/claim`** (new; no session; rate limit 60 per minute):
  - Body `{pollSecret}`. Compare `H(pollSecret)` with `poll_verifier` using `crypto.subtle.timingSafeEqual` or a constant-time loop.
  - Mismatch, unknown code or wrong purpose: 404 `{status:'expired'}`, with nothing consumed.
  - Pending: `{status:'pending'}`.
  - Complete: `DELETE ... WHERE device_code=? AND status='complete' RETURNING config_handoff_blob` (Drizzle `.returning()`, SQLite 3.35+), so exactly one caller gets the blob. Return `{status:'complete', configHandoff}`.
- **`DELETE /device-codes/:deviceCode`** (new; body `{pollSecret}`): cancel. Deletes the row if the secret matches, and always returns 204.
- **`GET /device-codes/:deviceCode`** (:25-31) and **`approve`** (:44+): scope both to `purpose='login'`.
  - `poll` stops returning `configHandoff`. Remove the field from `deviceCodePollResponse` (`src/dto/device-code.dto.ts`).
  - `approve` treats a `config-handoff` code as 404.
  - Make the login `poll` atomic with `DELETE ... RETURNING` too (section 0 item 6).
- **DTOs:** add `deviceCodeHandoffRequestResponse` and `deviceCodeClaimResponse`, both run through `responds()`.

## 4. Clients

### 4.1 URL grammar

The URL is `<apiUrl>/account/config-remote#code=<D>&key=<encodeURIComponent(spki b64)>&nonce=<b64url N>`.

Everything sits in the **fragment**. Browsers never send it to the server or in Referer. There is no query string and no `callback`. The page parses it with `new URLSearchParams(location.hash.slice(1))`; the values are percent-encoded, so `+` survives.

### 4.2 CLI (Writer C)

**New module `packages/cli/src/commands/config-remote-relay.ts`.** It keeps config-remote.ts under the max-lines gate and gives rotate and enable a single implementation. It exports:
- `startRelayHandoff(apiUrl)`: keypair, N and S, create the device code with the stored login token, and return `{url, pairingCode, deviceCode, expiresAt, privateKey, nonce, pollSecret}`;
- `relayUrl()` (pure, testable);
- `waitForRelayHandoff(...)`: claim loop, then decrypt, then nonce check, returning a `HandoffPayload`;
- `cancelRelayHandoff(...)`.

**`config-remote.ts`:**
- Delete the `node:http` import (:1), `startCallbackServer` (:40-110), `enableBrowser` (:114-152), `headlessRemoteUrl` (:205-208) and `pollOnce`/`pollForDeviceCode` (:166-203). Keep `parseHandoff` (:158-164); relay.ts reuses it.
- `enableHeadless` (:210-256) becomes the only `enableRelay`.
- `rotateCek` step 2 (:436-490) calls the same relay helpers.
- Remove `--headless` (:504) and its dispatch (:526-530). This is decision D2.

**`config-remote-handoff.ts`:** `HandoffPayload` (:22-31) gains `handoffNonce: string`. `decryptHandoff` stays. The relay module checks the nonce with a constant-time compare. On a mismatch or a missing nonce it throws a new `handoffNotForThisRun` error and writes nothing. Rewrite the comment at :51, which names the callback. The mirror fixture rule at :7-9 still binds: update the portal fixture textually as well.

**`config-remote-enable.ts:88-95`:** with no login token for `apiUrl`, refuse with `loginRequired` ("run `rdc subscription login` first"). This is decision D1. Also fix the header comment at :2-3.

**What the CLI prints** (non-TTY prints the same lines without a spinner):
```
Checked the prerequisites for muhammed@rediacc.com: ...
Open this link in any browser signed in as muhammed@rediacc.com:
  https://eu.rediacc.com/account/config-remote#code=...&key=...&nonce=...
Pairing code (type it on the page when asked):  7KQ2-M9XD-P4RT
Waiting for the browser... expires 14:32. Press Ctrl+C to cancel.
```

**`tryOpenBrowser` (:30-38):** stays best-effort. Optional sub-step: under WSL (`WSL_DISTRO_NAME` set), try `wslview` when it is on PATH. Do not use `cmd.exe start`, which can mangle `&` and `#`. Verify during the T11 smoke that the fragment survives.

**`packages/cli/src/config/command-planes.ts:119`:** the comment becomes "blocks polling the server relay". Keep `interactive: true`.

**`packages/cli/src/commands/serve.ts:8`:** the comment that names `--headless` changes to the plain command.

### 4.3 Portal (Writer B)

**New `web/src/lib/cli-handoff-request.ts`:**
- `readHandoffRequest(hash)` returns `{deviceCode, key, nonce}` or null;
- `fetchHandoffRequest(deviceCode)`;
- `verifyHandoffRequest(req, serverView)`: pending, `boundToYou`, `handoffKeyHash(key) === keyHash`, each failure mapped to an i18n key;
- `pairingCodeMatches(typed, key)`: uppercase, strip whitespace and dashes, constant-length compare against `handoffPairingCode`;
- `deliverHandoff(deviceCode, blob, keyHash)`.

`buildCliHandoffPayload` (`lib/config-handoff.ts`) takes a required `handoffNonce`. Update the comment at :64 ("server relay / localhost callback").

**`pages/ConfigRemote.tsx`:**
- Replace the params at :89-93 with `readHandoffRequest(location.hash)`. A missing value shows the existing `remoteMissingKey` screen.
- Verify against the server **before** the requirements phase, and render specific error screens (another account's request, expired or cancelled, key mismatch).
- Add a `pairing` phase: a 12-character input that must match before the unlock button enables.
- The redirect for a missing store (:106-113) always goes to `/account/config-setup${location.hash}`.
- `finishHandoff` (:163-205) has a single relay branch.
- Drop the `callbackUrl`-dependent margin (:313).
- Rewrite the header doc at :1-25, including the honest threat statement.

**`pages/ConfigSetup.tsx`:** runs in two modes.
- With no fragment it is a portal-only setup.
- With a fragment it runs the same verify-then-pairing steps up front, then after `setupStore` seals and calls `deliverHandoff`. That replaces `callbackUrl` at :151, :265-277, :303-334, :482-487 and :592, and the step `callback` becomes `relay`.
- It absorbs the relay path from `DeviceConfigSetup.tsx:196-222`.

**Delete** `pages/DeviceConfigSetup.tsx` and its route (router.tsx:431).

**`router.tsx:135-185`:** `ConfigSetupRoute` and `ConfigRemoteRoute` lose the `searchParams.get('callback')` chrome branch and always render `<ProtectedRoute><Layout>`. Keep or trim the comment at :416 so it still points at `config-remote.ts`.

**`auth/ProtectedRoute.tsx:27`:** `from: location.pathname + location.search + location.hash`. Check that `Login.tsx:25-44` `navigate(nextPath)` keeps the hash (react-router parses a string path, so it should), and that the sessionStorage `postLoginPath` copy (:44) carries it.

## 5. Shared (`packages/shared/src/config-crypto/handoff.ts`)

- `handoffKeyHash(spki: Uint8Array): Promise<string>` returns base64url(SHA-256).
- `handoffPairingCode(spki: Uint8Array): Promise<string>` returns the first 60 bits of the same digest, 5 bits per symbol, formatted `XXXX-XXXX-XXXX`.

Export both from the package index. The CLI, the portal and the E2E helpers all call these, so no copy can drift. Add a known-answer vector: a fixed SPKI and the expected hash and code.

## 6. Device-code lifecycle

- **Expiry:** 10 minutes for both purposes (operator ruling D3). A first-time setup that runs past it expires, and the page says to rerun the command. The CLI loop runs until `expiresAt`, not for `maxAttempts`.
- **One-shot:** the blob is deleted atomically on the first successful claim, so it sits at rest for at most the TTL. Expired rows are purged when codes are created, and when polled.
- **Binding:** the same user id. A code minted by user U can only be completed by a portal session of U. The server already knows U from the token, so same-org is too weak: an org admin would receive another member's slot secret flow.
- **Rate limits:**
  - create: 10 per minute per IP (existing, :13);
  - claim: 60 per minute per IP;
  - handoff-request: 30 per minute;
  - config-handoff: 10 per minute (existing `approveLimit`);
  - pending codes per user: at most 5.

  The limiter is in-memory per isolate (`src/middleware/rate-limit.ts:12-14`), so the real controls are S (256 bits), the binding and N. The limits are hygiene.
- **Polling:** use the interval the server returns (5 s). On a 429, wait for `Retry-After`. On network errors or 5xx, back off exponentially up to 30 s and warn once after 3 consecutive failures (`serverUnreachableRetrying`). A 404 or `expired` raises `expired`. Any other 4xx raises at once with the status.
- **Cancellation:** on SIGINT during the wait, send a best-effort `DELETE /device-codes/D` with a 2 s timeout, then exit 130. The page then shows "request cancelled; run the command again". The same rule applies to `rotate-cek`.

## 7. Tests

### 7.1 CLI (vitest, `packages/cli/src/commands/__tests__/`)

**New `config-remote-relay.test.ts`:**
- the URL has a fragment only, and no `callback`, `?` or `localhost`;
- create sends a Bearer token, `purpose`, `keyHash === handoffKeyHash(spki)` and `pollVerifier === H(S)`;
- the printed pairing code equals `handoffPairingCode(spki)`;
- claim goes pending, then complete, and `applyHandoff` is called once;
- a 429 waits for `Retry-After` (fake timers);
- three network failures print one warning, then recover;
- `expired` raises a ValidationError;
- a nonce mismatch refuses, and neither `applyHandoff` nor secure storage is touched;
- a blob sealed to another key raises `handoffUndecryptable`;
- SIGINT sends a DELETE with S;
- `rotate-cek` goes through the relay helpers.

**Edits:**
- `config-remote-handoff.test.ts`: delete the callback-preflight block (:141-163) and the `headlessRemoteUrl` block (:130-139).
- `config-remote-prereq.test.ts`: drop the `--headless` loop (:107) and the `runEnable('--headless')` cases (:138-199); add "no token refuses with loginRequired".

**Mutation controls:** drop the nonce check, reorder claim before create, print a code derived from anything but the SPKI. Each one turns a named test red.

### 7.2 Account integration (`private/account/tests/integration/`)

Rewrite `config-remote.test.ts:379-432` ("Device code config-handoff relay") for the new flow. Add `device-code-handoff.test.ts`, covering:
- create with the handoff purpose and no token: 401; with a token: the row stores the bound user, hash and verifier;
- `handoff-request`: `boundToYou` true for the same user and false for another; 404 once cancelled or expired;
- `config-handoff`: 403 from another user; 409 on a keyHash mismatch; 409 when the code is not pending; 404 on a login-purpose code; 403 without 2FA; a blob over the size cap is refused;
- claim: a wrong secret gives 404 and a later right claim still gets the blob; the right secret gives the blob once, then `expired`; two concurrent claims via `Promise.all` give exactly one blob;
- `approve` on a handoff code gives 404; GET poll never includes `configHandoff`; expired rows are purged on create;
- one test uses `rateLimit({force:true})` on claim.

**Mutation controls** (each must turn a named test red):
- remove `handoff_key_hash` from the conditional UPDATE;
- remove `bound_user_id`;
- replace `DELETE ... RETURNING` with select-then-delete (the concurrent-claim test goes red);
- drop the purpose fence on `approve`.

### 7.3 Portal unit (`web/src/lib/__tests__`, `web/src/pages/__tests__`)

- `cli-handoff-request.test.ts`:
  - fragment parsing, with a legacy `?callback=` query giving null;
  - `verifyHandoffRequest` for each refusal;
  - pairing normalization (lowercase, spaces, dashes) and mismatch;
  - the known-answer vector from section 5, asserted again so the portal build matches the shared one.
- `config-remote.test.tsx`: the unlock button stays disabled until the typed code matches; `boundToYou=false` shows the error screen and makes no delivery fetch; a key-hash mismatch shows the error screen.
- ProtectedRoute: an unauthenticated visit to `/account/config-remote#code=...` stores `from` with the hash.
- `config-handoff.test.ts`: the mirror fixture gains `handoffNonce`, textually identical to the CLI fixture.

### 7.4 E2E (`private/account/e2e`)

**`src/utils/config-store-helpers.ts`:**
- Delete `CallbackServer`/`startCallbackServer` (:764-820) and `createDeviceCode` (:693-700) in its no-auth form.
- Add `startRelayRequest(baseUrl, apiToken, keys)` returning `{deviceCode, nonce, pollSecret, url, pairingCode}`, plus `claimHandoff(...)`.
- `pollDeviceHandoff` (:703-728) becomes the claim loop.
- `decryptHandoff` (:731-738) asserts the nonce.
- Add an API-token mint helper for the test user if none exists.

**`tests/20-config-storage/20-11-prf-provider-matrix.test.ts`:**
- (e), device setup (:314-347): the flow starts at `/account/config-remote#...`, is redirected to `/account/config-setup#...`, and the test types the pairing code.
- (f), CLI handoff (:349-412): rename to "CLI relay handoff", with a new store and then an existing store, both over the relay.
- New (h), tampered link:
  - swap `key` in the fragment: the page shows the key-mismatch error and no POST is recorded (`page.on('request')`);
  - a wrong pairing code keeps unlock disabled;
  - a second user's session on a code bound to the first user is refused.

**`20-03-passkey-setup.test.ts:174,197`:** repoint the `/account/device-config` visits to `/account/config-setup#code=TEST&key=...`. The missing-parameter screen now belongs to ConfigSetup.

**Control first:** before the fix, (h) must fail on today's code, because today's page posts with a swapped key.

## 8. i18n and docs

### 8.1 CLI: 13 locales, `packages/cli/src/i18n/locales/{ar,de,en,es,et,fr,it,ja,ko,pt,ru,tr,zh}/cli.json`

- **Add** under `commands.config.remote.enable`: `openRelay`, `pairingCode`, `approveAs`, `waitingUntil`, `cancelled`, `serverUnreachableRetrying`, `handoffNotForThisRun`, `loginRequired`.
- **Remove** `optionHeadless` (:288), `polling` (:293) and `waiting`/`received` (:291-292) if they are no longer referenced.
- **Rotate:** `rotateCek.waiting`/`received` (:469-470) reuse the relay wording.
- **Reword** `handoffUndecryptable` (:285) without "posted to the wrong session" wording tied to the callback.

Regenerate `packages/shared/src/cli-contract/data/{contract.json,contract.generated.ts,i18n/*.json}` with `npm run generate:cli-contract -w packages/cli`. `--headless` disappears at contract.json:3334. Gates: `check:ci-cli-contract`, `scripts/gates/check-cli-i18n-key-usage.ts` and `check-i18n-placeholders`.

### 8.2 Portal: 13 `web/src/i18n/locales/*/configStorage.json`

- **Add:** `remotePairingTitle`, `remotePairingPrompt`, `remotePairingMismatch`, `remoteRequestNotYours`, `remoteRequestExpired`, `remoteRequestKeyMismatch`, `remoteRequestCancelled`, `setupStepLabel_relay`, `setupErrorAt_relay`.
- **Remove:** `setupStepLabel_callback` (:63) and `setupErrorAt_callback` (:70).
- **Reword:** `remoteDeliveryFailed` (:157) so it says "server relay", not "CLI".
- ConfigSetup carries `/* eslint-disable custom/no-hardcoded-text */` (:1). New strings on the pairing step go through `t()` anyway, because the step is shared with ConfigRemote.
- Regenerate `.translation-hashes.json`.

### 8.3 Docs

- `packages/www/src/content/docs/*/config-storage.md` (13): a new `How the keys reach your CLI` section. It covers the relay, the pairing code, same-account approval, the TTL, Ctrl+C, and the honest "trusts the served page" limit. Include the WSL case.
- `*/account-security.md` (13): the "Device Code Flow" snippet at en:52-57 is already wrong (it claims `--headless` shows a user code). Rewrite it.
- `*/cli-application.md` (13): the generated `--headless` row (en:219) goes away via the docs generator (`scripts/gates/check-cli-docs.ts`).
- Design and agent docs:
  - `docs/DESIGN-CONFIG-STORAGE.md:228-284`: redraw the sequence diagram; remove "directly from browser to CLI via localhost" (:284);
  - `docs/DESIGN-CONFIG-STORAGE.md:863` and `docs/design/spec/03-cli-contracts.md:611`: drop `--headless`;
  - `.claude/skills/rdc/config-storage.md:11`: drop `--headless`;
  - `private/account/CLAUDE.md`: fix the relay mention if it names the callback.
- The www search indexes (`packages/www/public/search-index*.json`) are generated. Rebuild, do not hand-edit.

## 9. Removal sweep (T11 closure criterion)

This must return no matches outside `agent/`, `docs/archive` and generated search indexes:
```
rg -n "startCallbackServer|callback=|callbackUrl|Access-Control-Allow-Private-Network|device-config|DeviceConfigSetup|--headless|headlessRemoteUrl|optionHeadless|config_handoff_blob.*callback" \
   packages/cli/src packages/shared/src private/account/src private/account/web/src private/account/e2e packages/www/src/content docs .claude/skills
```
Also, `rg -n "node:http" packages/cli/src/commands/config-remote*.ts` must be empty.

## 10. Operator decisions (ruled 2026-09-25, AskUserQuestion)

- **D1. Require `rdc subscription login` first: YES.** The binding needs a user; with no login token for the server the CLI refuses with `loginRequired`.
- **D2. Remove `--headless`: YES.** Clean break, one transport.
- **D3. Handoff TTL: 10 minutes (operator overrode the 15-minute recommendation).** Use the existing `DEVICE_CODE_TTL_MS` for `config-handoff` codes; do NOT add `CONFIG_HANDOFF_TTL_MS`. Everywhere this plan says 15 minutes for the handoff TTL, read 10.
- **D4. Pairing code: TYPED.** The unlock button stays disabled until the typed 12-character code matches.

## 11. Risks and sequencing

- **Deploy order.** Deploy the account server (eu) first, then release the CLI. In between, an old CLI's `--headless` breaks because GET poll no longer returns `configHandoff`, and old callback links show the missing-request screen. There is one operator and no external consumers, so this break is accepted (clean break, no dual path).
- **Merge conflicts.** Conflicts with PLAN-app-wide-org-selection are likely in `device-codes.ts`, `ProtectedRoute.tsx` and the 20-11 E2E. Wait for it to land (Depends-On).
- **Fragments in terminals.** Some terminals stop linkifying at `#`. The T11 smoke checks Windows Terminal against WSL. The copy-paste path is unaffected.
- **Hash loss on the emailed-login path.** A magic link opened in a new tab loses sessionStorage, so the hash is lost too, as the query already is today. The page then shows the missing-request screen and tells the user to rerun the command. This is not a regression.

### Critical Files for Implementation
- /home/developer/console/packages/cli/src/commands/config-remote.ts
- /home/developer/console/private/account/src/services/device-code.service.ts
- /home/developer/console/private/account/src/routes/device-codes.ts
- /home/developer/console/private/account/web/src/pages/ConfigRemote.tsx
- /home/developer/console/private/account/web/src/pages/ConfigSetup.tsx

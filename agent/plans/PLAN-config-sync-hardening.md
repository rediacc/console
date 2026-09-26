# PLAN: make the config sync loop (pull, push, encrypt, decrypt) safe, and prove it with a real round-trip harness

Status: draft
Owner: d778be9d
First-Seen: 2026-09-25
Depends-On: PLAN-token-ip-rebind.md -- T11 (config token refresh) reuses the login token's TOTP rebind from that plan (`packages/cli/src/services/account/account-client.ts`, `token-ip-rebind.ts`). PLAN-config-handoff-relay-only.md -- both plans edit `packages/cli/src/commands/config-remote*.ts` and `packages/cli/src/i18n/locales/*/cli.json`, so T6, T11 and T12 wait for its console commit. T0-T5 and T7-T10 can start now.
Priority: P0 -- proposed by AI. The operator asked whether this loop is "safe enough". It is not. Three confirmed defects cause silent data loss: repo network IDs wiped on every remote write (F3), concurrent edits reverted (F6), and a lost update on the server (F7). One makes deleting a machine, repo or storage impossible (F2). The protocol accepts rollback and cross-config blob swaps (F1).
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: private/account/src/services/config.service.ts, private/account/src/routes/configs.ts, private/account/src/middleware/config-token.ts, private/account/src/middleware/error-handler.ts (config-token newServerToken passthrough only), private/account/src/dto/config.dto.ts, private/account/src/db/config-schema.ts, private/account/drizzle/0055_*.sql, private/account/drizzle/meta/**, private/account/web/src/api/config-session.ts, private/account/web/src/api/config.ts, private/account/web/src/pages/RotateCekWizard.tsx, private/account/tests/integration/config-sync/** (new), private/account/tests/integration/config-envelope-v2.test.ts, packages/cli/src/adapters/remote-config-adapter.ts, packages/cli/src/adapters/remote-token-storage.ts, packages/cli/src/services/config/config-server-client.ts, packages/cli/src/services/config/remote-cache.ts, packages/cli/src/services/config/config-base.ts, packages/cli/src/services/config/resource-state.ts (RemoteResourceState only), packages/cli/src/commands/config-remote-enable.ts, packages/cli/src/adapters/__tests__/remote-*.test.ts, packages/cli/src/services/__tests__/remote-cache.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/shared/src/config-crypto/{selective,layers,hmac,types,commitments,constants}.ts, packages/shared/src/config-crypto/__tests__/**, packages/shared/src/config-schema/{payload,sensitivity,walker}.ts, packages/shared/src/config-crypto/rotation.ts, packages/shared/src/config-schema/__tests__/**, docs/DESIGN-CONFIG-STORAGE.md, packages/www/src/content/docs/*/config-storage.md
Worklist: (the lead adds this with `worklist.py --add`)

**Operator question, 2026-09-25 (verbatim):** `do you think that pull, push, encrypt, decrypt loop/code is safe enough?`

**Short answer.** No. The encryption primitives are sound: AES-256-GCM with random IVs, HKDF with domain separation, and CEK wrapping that needs the slot secret. The loop around them is not:
- The ciphertext is not bound to the configuration it belongs to.
- The server's version check is not atomic.
- The CLI's cache and push paths use two different lists of host-local fields.
- The anti-downgrade rule makes deletion impossible.
- Config tokens die whenever a laptop changes network, and after 24 hours without use.

None of this was visible because every existing test mocks one side of the wire.

**Line numbers** are from console `bd0278084` and account `6046d44`, read 2026-09-25.

## Tasks

Writers:
- **A**: `private/account/src/**`, `drizzle/**`, `web/src/api/**`, `web/src/pages/RotateCekWizard.tsx`
- **B**: `packages/cli/**`, `packages/shared/**`, i18n and docs
- **C**: `private/account/tests/integration/config-sync/**`, plus one small test seam in `config-server-client.ts`. B reviews the seam; C writes it in T1, before any B work starts.

The submodule PR (A and C) merges first. The console PR (B, plus the pointer bump) follows it.

- [ ] T0 [lead] Get the operator's answers to D1-D9 (section 5). Freeze the wire contract for envelope v3, the tombstones, the token refresh route and the newServerToken-on-error rule (section 3). Put the shared types in `packages/shared/src/config-crypto/types.ts` first.
- [ ] T1 [C] Harness skeleton (section 4.1): in-process app, the network router with per-device IPs and fault hooks, a fake clock, device factories, and the `transport` seam in `configServerFetch`.
- [ ] T2 [C] Scenarios H1-H17 (section 4.2). The ones that reproduce today's defects start as `it.fails` with the defect ID in the test title. Each fix task flips its scenarios to `it`.
- [ ] T3 [B] Host-local registry and a single overlay: F3, F4, F18, and the renetPath class. Section 3.2.
- [ ] T4 [B] The push rebases on the server copy: F6. Section 3.3.
- [ ] T5 [A] Compare-and-swap push with version-unique blob keys, the same for rotation pass 2, and `/:id/versions` scoped to the store: F7, F16. Section 3.4.
- [ ] T6 [B] Token handling: thread the rotated token, one-request pull, a per-config lease, and persist the token on errors: F8, F9 (CLI half). Section 3.5.
- [ ] T7 [A] Put newServerToken in every config-token error body, and make the usage increment atomic: F8, F9 (server half). Section 3.5.
- [ ] T8 [B+A] Envelope v3: AES-GCM AAD binding, a client high-water mark, blinded pointer names, the HMAC retired, and migration per D2: F1, F13 (partly), F14, F15. Section 3.1.
- [ ] T9 [B+A] Deletion by tombstone: F2 (per D1), plus a distinct error for `precondition_failed`. Section 3.6.
- [ ] T10 [A+B] What happens after a CEK rotation: F11, F12. The server checks the generation on push; rotation revokes the other members' config tokens; the CLI raises a stale-generation error. Section 3.7.
- [ ] T11 [A+B] Config token lifetime and refresh: F10 (per D4). Section 3.8.
- [ ] T12 [B] account/defaults semantics per D3 (F5), enable cleanup (F17), and preserving unknown keys (F18). Section 3.9.
- [ ] T13 [A] Enforce the SDK epoch window per D5 (F13), and move the portal ConfigSession to the push response's fresh session material. Section 3.10.
- [ ] T14 [B] Docs: rewrite the zero-knowledge claim in `docs/DESIGN-CONFIG-STORAGE.md` and `config-storage.md` (13 locales) per D9, using the table in section 1.
- [ ] T16 [A+B] Version restore (D1 "plus versioning"): `GET /:id/versions/:v` returns an archived blob with its own `sdkEpoch` key; the CLI's `rdc config remote versions` lists and `rdc config remote restore <v>` decrypts the old version and pushes it as a NEW version through the T5 compare-and-swap, so the v3 high-water mark never moves backwards and a tombstone is emitted for anything the restored copy lacks; audit event `config.version.restore`. Harness scenario H18: A pushes v1..v3 (v3 deletes a machine), restores v1; B pulls and sees v1's content at v4, and a server `rollbackTo` of the same content is still refused.
- [ ] T17 [B] The sync model is ONE exclusion list (operator ruling 2026-09-25: "striping the networkid is a disaster ... it's key info per repo and we aim to have shared machines per team"; confirmed list after two rounds). Everything in a config syncs except `/remote`, `/encryption`, `/renetPath`, `/credentials/masterPasswordVerifier`, `/version`, `/schemaVersion`. The push sends the document minus those pointers (no per-section allow-list, no `stripStateForPush`), the pull overlay keeps exactly those pointers, and the T3 gate becomes "every key is synced unless listed". All of `state` syncs: `networkIds.next` and every repo's `networkId`, `registryPort`, `pushState`, `head`, `headCommit`, commit message/author/parent, `branches`, `reflog`; allocation of a new network ID is a synced write settled by the T5 compare-and-swap. One-time migration: a pulled copy with no `state` never erases local state, and the next push publishes it. Harness H19-state (a second device runs `term`/`repo up` on a repo the first created and gets the same networkId) starts as `it.fails`. PLAN-config-networkid-sync keeps only the renet guard and the machine lookup as a fallback for a missing ID.
- [ ] T18 [B] Every command that edits a remote config pushes through `updateSyncedSection` / `RemoteResourceState.updateDocument`, so no edit is reverted by the next pull: `commands/config/field.ts`, `commands/config/edit.ts`, `config-cluster-logic.ts`, `config-datastores.ts`, `config-resources.ts` (non-resource writes), `config-prune.ts`, `commands/update.ts` (`updateChannel`), `commands/subscription.ts` (`accountServer`), `services/account/account-client.ts` (`e2ePublicKey`); plus a gate or test that fails when a new writer of a synced section bypasses the push. Harness scenarios per command start as `it.fails`.
- [ ] T15 [lead] Closure:
  - H1-H17 are all green, with no `it.fails` left.
  - The mutation controls table (section 4.3) is run and recorded: each named revert turns its named test red.
  - The CI log of the account integration lane lists `config-sync/*.test.ts` with non-zero test counts (testing skill).
  - Live smoke against eu from two machines on two networks:
    - enable on both;
    - push from A, pull on B after more than 10 minutes (two epochs);
    - delete a machine;
    - move A to a phone hotspot and run a command (it must refresh per D4);
    - rotate the CEK from the portal, and check that B reports "stale key, re-enroll".

## 0. What each key protects

| Layer | Key | Where it lives | What it stops | What it does NOT stop |
|---|---|---|---|---|
| 1, SDK | `sdk_derived = HKDF(sdkMaster, epoch)` (`packages/shared/src/config-crypto/sdk.ts:36-39`) | `sdkMaster` is plain base64 in D1 (`config.service.ts:411`) | A holder of CEK plus ciphertext who has no valid config token | The server. Anyone with a token: pull hands out the pushed epoch's key forever (`configs.ts:1021`), and push accepts any client epoch (F13). The "time window" is not enforced. |
| 2, CEK | Random AES-256, wrapped with `HKDF(slotSecret‖serverSecret)` (`cek.ts:31-43`) | The slot secret stays on the device: the OS keyring for the CLI, RAM in the portal. `serverSecret` is plain base64 in D1 (`config.service.ts:1034-1036`, "For now it's stored as base64") | A D1/R2 dump, a passive or curious operator, and org members who are not in the store | An active server: it serves the portal JS that unwraps the CEK, it can roll back or swap blobs (F1), and it can read metadata (F14) |
| 3, Org | `orgPassphrase` used directly as an AES key (`layers.ts:65-81`) | Server-recoverable (`serverRecoverableOrgPassphrase`, `config.service.ts:406`), and decryptable from every presented token (`:945-952`) | An R2-only leak without D1 and the server key | The server, which can decrypt it at will |
| Tunnel | Per-request X25519/AES (`config-server-client.ts:70-97`) | - | Network MITM, spoofed client IPs (`app.ts:621-638`) | The server |

**The zero-knowledge claim, stated honestly:** confidentiality rests only on the CEK. It holds against storage compromise and a passive operator. It does not hold against an operator who serves malicious portal code. Integrity against the server is currently absent (F1). This rewrite is D9 and T14.

## 1. Findings

Each finding is marked **confirmed defect**, **plausible risk** or **verified safe**. "Confirmed by reading" means the code path is unambiguous; the harness scenario named in brackets reproduces it at runtime.

### Confirmed defects

**F1: A server can roll back a config or swap in another config's blob, and the CLI accepts it. [H14]**
- The only integrity check is an HMAC over `encryptedBlob` alone (`selective.ts:86-90`, verified at `:111-116`).
- The AES-GCM layers use no AAD (`layers.ts:24-34`, `aes.ts:130-134`).
- `id`, `version`, `teamId` and `sdkEpoch` are not in the plaintext: only `SENSITIVE_FIELDS` is encrypted (`selective.ts:78-86`).
- `selectiveDecrypt` returns `{...payload.envelope, ...sensitive}` (`:121-124`), so identity and version come from the unauthenticated envelope.
- The CLI builds that envelope from the pull response (`remote-config-adapter.ts:263-279`). The server builds it from the D1 row (`config.service.ts:744-757`) and keeps 50 archived blobs (`:337`, `:604-625`).
- The CLI never compares the pulled version with `remote.cachedVersion`.
- Consequences:
  - Pointing `current` at an old version is accepted, for example a revoked SSH key or an older `policy`. The next push from the CLI then makes the rollback permanent (`resource-state.ts:434`).
  - Configs in one store share one CEK, so serving config X's blob for config Y is accepted too.
- Envelope tampering, field by field:
  - `sdkEpoch`: detected, but only as a GCM failure, and misreported as a "session layer" error (`adapter.ts:433-435`).
  - `version`, `id`/`configId`, `teamId`, `lastModified`: not detected.
  - `commitments`: not verified on pull. The CLI invents empty ones when they are missing (`adapter.ts:271-275`).
  - `envelopeVersion`: checked (`selective.ts:105-109`).

**F2: Deleting a machine, repo, storage or credential from a remote config is impossible. [H13]**
- `pathsToCommit` commits one pointer for every non-public leaf, including `/resources/machines/<name>/ip` (`walker.ts:199-205`, `sensitivity.ts:102-106`).
- The server's anti-downgrade rule refuses any stored pointer that is missing from the new envelope (`config.service.ts:590-599`). The test that pins this is `config-envelope-v2.test.ts:142-164`.
- Removing a resource removes its pointers, so the push is refused with 409 `precondition_failed`.
- The CLI turns every 409 into `RemoteVersionConflictError` (`adapter.ts:477`). `RemoteResourceState` then re-pulls and re-pushes the same deletion three times (`resource-state.ts:409-421`) and reports "conflict retry exhausted".
- The same happens when clearing a committed scalar such as `defaults.universalUser` or `infra.certEmail`.

**F3: Every remote write wipes `state.repos`, including every repo's `networkId`. [H12]**
- `loadRemote` overlays only `remote`, `renetPath`, `account` and `defaults` (`config-base.ts:222`, `:402-409`), so the in-memory config has no `state`.
- `getResourceState` passes that config to `RemoteResourceState.load` (`config-base.ts:70-77`, `resource-state.ts:348-356`).
- `loadLocalState` flattens repositories without runtime state (`resource-state.ts:194-201`, `:82-100`).
- On every persist, `persistPatch` rewrites `state.repos` from that runtime-less view (`:228-231`). `nonEmpty({})` gives undefined.
- `pushOnce` then writes it back through `mergeRemoteIntoCache(merged, …)`, where `state: local.state` is the wiped `merged.state` (`resource-state.ts:431-438`, `remote-cache.ts:40`).
- Network IDs (`state-schema.ts:173-190`) are what `allocateNetworkIdInStore` scans (`config-network-id.ts:9-17`). Losing them lets a new repo be given an ID that is already in use on the machine.
- Root cause: two hand-kept lists of host-local fields (`remote-cache.ts:32-47` and `config-base.ts:402-409`). This is the same class as today's renetPath bug.

**F4: A remote config in master-password mode loses `credentials.masterPasswordVerifier` on the first pull.**
- The field is host-local by definition (`sensitivity.ts:86-100`, `commit:false`, "must never enter the remote config envelope").
- `mergeRemoteIntoCache` starts from `...pulled` and never restores it (`remote-cache.ts:32-47`). It keeps `encryption` (master-password mode, fields encrypted) but drops the verifier.
- `requireMasterPassword` then throws "No master password configured" (`master-password.ts:27-50`, via `config-base.ts:289-292`) unless `REDIACC_MASTER_PASSWORD` is set.
- The result: the offline cache and every write are locked out in a TTY. Same root cause as F3.

**F5: Remote changes to `account` and `defaults` never reach a device that already has them cached, and that device's next push reverts them. [H16]**
- The cache merge writes `account = {...pulled.account, ...local.account}` (`remote-cache.ts:46-47`). From then on the local copy holds every pulled key.
- The next pull layers those stale local values over the server's (`config-base.ts:405-408` in memory, `remote-cache.ts:46-47` on disk).
- `projectTopLevelSections` pushes them back to the server (`payload.ts:53-59`), silently reverting another device's change.

**F6: A retried push reverts concurrent edits to every family outside `LocalState`, including `policy`. [H15]**
- `pushOnce` builds the push from `configFileStorage.loadDecrypted` (the disk cache) plus `this.state` (`resource-state.ts:429-433`).
- After a 409, `rebaseOnFreshPull` refreshes only the five `LocalState` buckets and the version (`:451-460`). The disk cache is not updated.
- So `policy`, `infra`, `clusters`, `datastores`, `backupStrategies`, `cloudProviders`, `cfDnsApiToken`, `account` and `defaults` are pushed from the stale base.
- Commitments do not stop this, because the writer holds the CEK. The policy rollback is security-relevant: see the comment at `schemas.ts` `policy`.

**F7: The server loses updates when two pushes race. [H9]**
- The version check (`config.service.ts:551-555`) and the update (`:631-642`, `WHERE id = existing.id` only) are separate statements. Both writers pass the check and both get `success`.
- Worse, both write the same R2 key `current.enc` (`:601`, `:628`) before D1 changes. The blob that ends up stored can belong to the loser while D1 records the winner's hmac and version: the config is bricked for everyone (HMAC failure).
- Rotation has the same shape: check in pass 1 (`:1969`), then pass 2 writes `current.enc` and updates without a version predicate (`:1999-2021`).

**F8: Concurrent use of one config token fails with `token_exhausted`. [H7]**
- `pull()` and `push()` send the same token twice: `/session` and then the pull or PUT both use `token` (`adapter.ts:229-250`, `:305-319`). They persist two children, the second overwriting the first (`:454-457`).
- With `TOKEN_MAX_USAGE = 3` (`config.service.ts:312`), two processes sharing a token dir (an interactive `rdc` plus `rdc serve`, or a script) spend 4 uses of one token, and the fourth gets 401.
- `updateToken` reads outside the lock and then writes (`remote-token-storage.ts:98-104`). That is a lost-update race, and an older token can overwrite a newer one.
- On the server, the usage check (`:936`) and increment (`:975-981`) are not atomic.
- Pull does not need `/session` at all: the pull response already carries `server_secret` (`configs.ts:1033`).

**F9: The rotated token is thrown away on every error response.**
- `configServerFetch` throws on inner status ≥ 400 without returning `parsed.newServerToken` (`config-server-client.ts:107-110`), although the server puts it in 409 and 400 bodies (`configs.ts:1104-1125`).
- 404 and other `HTTPException` paths carry no token at all (`configs.ts:1040-1042`).
- Each such error spends one grace use of the stored token.
- The portal's `configFetch` has the same gap for everything except push (`web/src/api/config.ts`, `configPush` handles it by hand).

**F10: Config tokens break on network moves and after 24 hours idle, and then every command fails, reads included, until the user re-enables through the portal (TOTP plus elevated session).**
- Every rotated token is bound to the IP of the request that minted it (`config.service.ts:968`). The "binds on first use" comment in `mintDeviceToken` (`:891-898`) applies only to the first link in the chain.
- An address change fails with `ip_mismatch` (`:941-943`). The client IP comes from `config-token.ts:19-22`.
- Tokens expire 24 hours after the last use (`:311`, `:930-933`).
- `loadRemote` serves the offline cache only for `RemoteUnreachableError` (`config-base.ts:195`).
- The error messages name `rdc config remote enable` as the only remedy (en `cli.json`: `tokenExpired`, `tokenIpMismatch`, `tokenExhausted`).
- Cases that hit this: laptops moving between networks, ISP address changes, IPv6 privacy-address rotation, and dual-stack hosts where undici's `autoSelectFamily` connects over v4 on one run and v6 on another. The v4/v6 split is already named in the `mintDeviceToken` comment.

**F11: After a CEK rotation, the other devices get the wrong diagnosis.**
- Rotation deletes server-side slots and bumps `cekGeneration` (`config.service.ts:2031-2062`). It changes neither `serverSecret` nor the device's local `wrappedCek` (`remote-token-storage.ts:18-23`).
- So `deriveCek` still unwraps the OLD CEK successfully (`adapter.ts:386-405`). `RemoteStaleSlotError` is never raised.
- The HMAC then fails, and `classifyDecryptFailure` reports `undecryptableIdentity`, meaning "a different enrollment's config" (`adapter.ts:424-431`). That is the wrong cause and the wrong fix.
- The `rotateCek` doc comment, "the rotation deliberately revokes this device's wrapped CEK" (`commands/config-remote.ts`), is false for other devices.

**F13 (the claim part): The "time-windowed" SDK key is not time-windowed.**
- `pushConfig` validates neither `sdkEpoch` recency nor `envelope.sdkEpoch === body.sdkEpoch` (`config.service.ts:531` checks only id and version).
- Pull serves the pushed epoch's key indefinitely.
- The portal pushes with the epoch from session open for the whole session (`config-session.ts:61-66`, `:127-138`). It works only because of this gap, so it is a latent break if enforcement is ever added.

**F14: Metadata leaks to the server.**
- The commitment keys are plaintext JSON pointers (`commitments.ts:113-122`), stored in `envelopeJson` (`config.service.ts:602`, `:640`).
- So the server reads every machine, repo, storage, cluster and cloud-provider name, and which sensitive fields are set (`kind`).
- This contradicts "it never sees the encrypted blob's plaintext" (`selective.ts:8-12`).

**F16: `GET /configs/:id/versions` is not scoped to the store.**
- The route passes the URL id straight to `listVersions(configEntryId)`, which filters only on `configEntryId` (`configs.ts:1153-1168`, `config.service.ts:810-821`).
- Any config-token holder can read version metadata (`createdByUserId`, timestamps) of any entry UUID. Low severity: the UUIDs are unguessable.

**F18: Unknown top-level keys are dropped by the cache merge** (`remote-cache.ts:32-42` starts from `...pulled`). This contradicts the `.loose()` contract in `schemas.ts` ("a newer CLI's additions round-trip through an older CLI"). Low severity.

### Plausible risks

**F12: The server accepts a push sealed under a pre-rotation CEK.**
- `pushConfig` has no `cekGeneration` check (`config.service.ts:500-713`).
- Rotation revokes no config tokens (it only deletes slots and handoffs, `:2031-2069`), while member removal does (`:1246-1247`).
- So a member who is still enrolled but has not re-accepted, or a device being rotated away because it was compromised, can read the current version from `GET /configs` (`configs.ts:1135-1151`) and push v+1 sealed under the old CEK.
- Everyone on the new CEK is then locked out, and the old-key holder can read again.
- Honest CLIs are stopped only by the version check, and only by accident.

**F15: The raw CEK is used as both the AES-GCM key and the HMAC key** (`hmac.ts:17-26`). No known practical attack. The HMAC is redundant with the GCM tag, and its only job today is to label errors.

**F17: A failed enable deletes a secret that another local config may be using.** `cleanupHandoffCredentials` deletes `storageKeyId` unconditionally (`config-remote-enable.ts:156-163`). `storageKeyId` belongs to the (store, user) identity (`config.service.ts:424`, `:1602`), so a failed enable of a second local config for the same store deletes the first config's slot secret.

**F17b: Enable replaces local content without asking in some cases.** The overwrite prompt only compares `resources` (`config-remote-enable.ts:177-180`, `:260-267`). Local `credentials.ssh`, `policy` and `infra` are replaced by the store's without a prompt; the only copy left is the single-generation `.bak`.

**F19: Team scoping is not enforced.** A pull filters on store, config and the caller-chosen `teamId` query (`configs.ts:1007-1011`) behind org membership only. The CEK is store-wide, so team separation is not cryptographic either. This needs an operator decision (D8).

**F20: Runtime state that devices should share is kept per device.**
- `state.networkIds.next` and `state.repos[*].networkId` are host-local and never synced (`config-network-id.ts:25-43`, `payload.ts:47-51`).
- Two devices on one remote config allocate network IDs independently, starting from `MIN_NETWORK_ID`.
- Device B does not know the network IDs of repos that A created.
- Severity depends on whether renet can recover the ID from the machine (D8).

### Verified safe

- **S1: Epoch on every pull path.**
  - The CLI decrypts with the pull response's key (`adapter.ts:257-258`, after `bd0278084`).
  - The portal editor uses `res.sdk_derived` (`config-session.ts:110`).
  - The executor uses `pull.sdk_derived` (`services/serve/container-config.ts:129`).
  - The rotation wizard uses the pull key for decrypt and the session key for re-encrypt (`RotateCekWizard.tsx:169`, `:192`).
  - The offline cache involves no epoch.
- **S2: The window rolling between `/session` and PUT is harmless.** The client seals with, and sends, one epoch (`adapter.ts:310-326`). The server stores the body's epoch (`config.service.ts:638`, `:686`), and pull derives its key from it (`configs.ts:1021`).
- **S3: No IV reuse.** Every AES-GCM call draws a fresh random 96-bit IV (`aes.ts:130-134`). The long-lived keys (CEK, org key) are used far fewer than 2^32 times.
- **S4: The client IP cannot be spoofed through the tunnel.** Forwarding headers are removed from the inner request and rewritten from the outer one (`app.ts:621-638`).
- **S5: The CLI and the portal never race on a token.** The device token starts a separate chain (`configs.ts:980-996`, `config.service.ts:899-914`). Content races go through the version check, subject to F7.
- **S6: The portal's single-flight queue works.** Calls are chained (`config-session.ts:68-73`) and the token is threaded back on a push 409 (`config.ts` `configPush`). The remaining error-path gap is F9.
- **S7: The offline cache never hides auth failures, and writes fail closed.** `config-base.ts:194-220`, `resource-state.ts:462-474`.
- **S8: Member removal revokes that member's config tokens** (`config.service.ts:1246-1247`).
- **S9: A crash between the server rotating a token and the CLI saving it is survivable.** The old token keeps its unused grace uses. Today the margin is one use (F8); after T6 it is two.
- **S10: The relay handoff is sealed to the CLI's ephemeral X25519 key, with a nonce echo** (`config-remote-relay.ts:5-12`, `config-remote-handoff.ts:46-60`). It is safe against a passive server. An active server can serve portal JS: see the section 0 caveat.
- **S11: Rotation pass 1 rejects configs pushed during the rotation** (`config.service.ts:1969-1990`, idempotent through the fckSalt match at `:1951-1967`). The remaining gap is the pass-1-to-pass-2 time-of-check/time-of-use window (F7).

## 2. Root causes behind the sibling defects

1. **No binding between ciphertext and identity** (F1, F11, F12, F13, F14). The envelope is advisory data that the server writes. Fix it once, in envelope v3.
2. **Two hand-kept lists of host-local fields** (F3, F4, F18, and the renetPath bug fixed in `bd0278084`). Fix: one registry flag, used by the push projection, the cache merge and the in-memory overlay, with a gate test that every schema key is either projected or host-local.
3. **Read-then-write without compare-and-swap** (F7, the rotation pass 2 race, the `usageCount` race in F8, the token-file race in F8). Fix: CAS predicates and version-unique object keys.
4. **Error paths that lose protocol state** (F9, F2's 409 misread as a version conflict, F11's misdiagnosis). Fix: typed error codes carried end to end.

## 3. Fixes

### 3.1 Envelope v3 (T8; F1, F13, F14, F15)

- **AAD.** Add `aad` to `aesEncryptToString`/`aesDecryptFromString` (`aes.ts:159-173`). Use it on the CEK layer:
  `AAD = canonical({v:3, storeId, configId, teamId|null, version, sdkEpoch, cekGeneration, commitmentsDigest})`.
  `commitmentsDigest` is SHA-256 over the canonical commitments. The same AAD goes on the SDK layer, so epoch tampering reads as an integrity failure.
- **Retire the blob HMAC.** GCM plus AAD covers it. Keep the `hmac` column, written as `null` for v3.
- **Client checks on pull.** `selectiveDecrypt` takes an `expected: {storeId, configId, teamId}` argument, built from the local `remote` pointer and never from the response. After decrypting, the client:
  - refuses `version < highWater`, where `highWater = max(remote.cachedVersion, last pushed version)`, stored in the token file so a wiped cache does not reset it. This raises a new `RemoteRollbackError`.
  - recomputes the commitments from the decrypted document and requires them to equal the envelope's.
- **Blinded pointers.** Commitment keys become `base64(HMAC(FCK_ptr, pointer))`, with a separate HKDF info string `rediacc-config-ptr-v1` so the key is separate from the value HMAC. The server's anti-downgrade check is unchanged: it compares opaque keys.
- **Server.** Store `envelopeVersion` 3. Validate that `envelope.sdkEpoch === body.sdkEpoch` and `envelope.cekGeneration === store.cekGeneration` (this is also T10).
- **Migration.** Per D2.
- **Siblings.** The same AAD and pointer rules go through `buildConfigPushPayload`, `reencryptConfig`, the portal `ConfigSession` and the executor `container-config.ts`. They all share `payload.ts`, so one change covers all four callers.
- **Residual risk.** A device that has never seen the newer version, such as a freshly enrolled one, can still be handed an old version. Guaranteeing freshness against a malicious server needs an external witness. Named in D9.

### 3.2 Host-local registry and a single overlay (T3; F3, F4, F18)

- Add `hostLocal: true` to the sensitivity registry, or a sibling `HOST_LOCAL_ROOTS` in `config-schema`. It covers `/remote`, `/state`, `/encryption`, `/renetPath`, `/credentials/masterPasswordVerifier`, plus the device keys chosen in D3.
- One function, `overlayHostLocal(pulled, local)`, in `remote-cache.ts`. Both `mergeRemoteIntoCache` and `loadRemote` call it. `loadRemote` must return exactly what the cache holds, `state` included, so that `RemoteResourceState.load` sees runtime state. That fixes F3 at its root.
- Unknown top-level keys: keep local unknown keys unless the pulled document carries the same key (F18).
- **Gate test** in `config-schema/__tests__/`: every top-level key of `RdcConfigSchema.shape` is exactly one of {projected by `toFullConfig`, host-local}. It fails when a new key is added without a classification. This extends `commit-encrypt-parity.test.ts`.

### 3.3 The push rebases on the server copy (T4; F6)

- `rebaseOnFreshPull` writes the fresh pull through `writeRemoteCache` before the retry, so `pushOnce`'s `loadDecrypted` base is the server copy plus the host-local overlay.
- Alternative: hold the last pulled document in memory and build from it plus the host-local overlay. Either works; the first reuses existing code.
- The harness check is H15.

### 3.4 Compare-and-swap on the server (T5; F7, F16)

- The blob key becomes version-unique: `.../v/<version>.enc`. `current.enc` is no longer overwritten; the old `r2Key` becomes the archive entry and needs no copy.
- The update becomes `UPDATE … WHERE id=? AND version=?`. Check that exactly one row changed, otherwise throw `ConfigConflictError` and delete the orphaned blob on a best-effort basis.
- Rotation pass 2 gets the same predicate, `version = snap.version`.
- `listVersions(storeId, configEntryId)` joins through `config_entries` to filter on the store.
- Migration `0055`: none needed if `r2Key` already exists per row (it does, `:601`); the plan only changes the key format.

### 3.5 Token handling (T6 CLI, T7 server; F8, F9)

- **CLI.**
  - `fetch()` returns the rotated token, and the next call in the same operation uses it.
  - `pull()` becomes one request: it takes `server_secret` from the pull response. `push()` stays at two requests, with the token threaded between them.
  - A per-config lease: `RemoteTokenStorage.withLease(configName, fn)` holds the proper-lockfile lock on the token file for the whole adapter operation. It reads the token, runs the requests, and persists under the same lock. `updateToken` goes inside the lock.
  - `ConfigServerError` gains `newServerToken`, and `fetch()` persists it before classifying the error.
  - `precondition_failed` gets its own error class (T9).
- **Server.**
  - Every config-token route's error body carries `newServerToken` when `configNewToken` is set. This goes in the error handler, keyed on the context variable.
  - The usage increment becomes one atomic statement: `UPDATE config_tokens SET usage_count = usage_count + 1 WHERE id=? AND usage_count < 3 RETURNING`. Zero rows means `token_exhausted`.
  - **Keep** `TOKEN_MAX_USAGE = 3` as the crash margin.
- **Portal.** `configFetch` threads `newServerToken` from error bodies the same way `configPush` does.

### 3.6 Deletion by tombstone (T9; F2, per D1)

- The v3 envelope gains `commitments.removed: Record<blindedPointer, {hmac, kind}>`. The HMAC is computed with the **stored** `fckSalt`, which the client reads from the pulled envelope's commitments instead of inventing empty ones at `adapter.ts:271-275`.
- The server allows a stored pointer to disappear only when `removed[p]` matches the stored `{hmac, kind}`: to delete a value, the writer must know it. Otherwise it keeps today's anti-downgrade refusal.
- The CLI computes `removed` by diffing `pathsToCommit(pulledDoc)` against `pathsToCommit(newDoc)`.
- The CLI maps a 409 with `code === 'precondition_failed'` to a new `RemotePreconditionError`, naming the paths, with no replay loop.

### 3.7 After a CEK rotation (T10; F11, F12)

- **Server.**
  - `pushConfig` refuses a push whose `envelope.cekGeneration !== store.cekGeneration` (409 `stale_cek_generation`).
  - `completeCekRotation` deletes every config token in the store that belongs to anyone other than the initiator (`configTokens` where `userId != initiator`), inside the same pending-only block as `:2031-2069`.
- **CLI.**
  - Enable writes `cekGeneration` into the token file. It comes from the handoff payload, or from a new field in `/session`.
  - On an AAD or HMAC failure, or on `stale_cek_generation`, the CLI fetches the store generation (`/session` returns `cekGeneration`). If it is higher than the local one, it raises `RemoteStaleSlotError`; otherwise `RemoteConfigUndecryptableError`.
- **Siblings.** The portal `ConfigSession` push maps `stale_cek_generation` to its `envelope` conflict. The executor reports the same error.

### 3.8 Config token lifetime (T11; F10, per D4)

- **Recommended.** New route `POST /configs/device-token/refresh` with `apiTokenAuth('config:enroll')`. The token's creator must be a store identity with at least one slot at the current generation. It returns a fresh unbound device token.
- The login API token already carries TOTP-gated IP rebind (PLAN-token-ip-rebind), so a stolen config token alone still fails from another network.
- The CLI adapter calls the refresh once on `ip_mismatch`, `token_expired`, `token_exhausted` or `invalid_token`, under the lease, then retries. The refresh returns no key material: the CEK still needs the device's slot secret.
- If there is no login token for `apiUrl`, the CLI keeps today's messages but names both remedies.

### 3.9 account/defaults, enable cleanup, unknown keys (T12; F5, F17, F17b, F18)

- **account/defaults (per D3, recommended split).**
  - Device keys become host-local through the 3.2 registry: `account.accountServer`, `e2ePublicKey`, `updateChannel`, `releasesUrl`, `defaults.language`.
  - Synced keys (`userEmail`, `universalUser`, `datastoreSize`, `pruneGraceDays`) come from the server with no local override. Delete the spread overlays at `remote-cache.ts:46-47` and `config-base.ts:405-408`.
- **Enable cleanup.** Delete the secure-storage secret only if this enable wrote it (it was absent before) and no other local config's `remote.storageKeyId` names it.
- **Enable prompt.** `resourcesDiffer` becomes "synced projection differs", so it compares the `toFullConfig` projections and not only `resources`.

### 3.10 SDK epoch window (T13; F13, per D5)

- **Recommended.** The server requires `|body.sdkEpoch - currentEpoch| <= 1` on push.
- The portal `ConfigSession` adopts `sdk_derived`/`sdkEpoch` from each push response (`configs.ts:1092-1100` already returns them), and calls `/session` again when it has been idle for more than one window.
- The layer-1 documentation says what the layer actually protects (section 0).

## 4. The round-trip harness (T1, T2)

### 4.1 Design

- **Location.** `private/account/tests/integration/config-sync/` (D7). It is picked up by the existing `tests/integration/**/*.test.ts` include (`private/account/vitest.config.ts`) and runs in the account integration lane (`.github/workflows/ci-quality.yml:2604`, `rediacc_ci.private.run_account test`). That lane checks out the console tree with `build-packages: 'true'`, so relative imports of `packages/cli/src` resolve there, exactly as `@rediacc/shared` already does (`private/account/package.json:45`).
- **Server.** `createApp(() => getTestEnv(), () => db, () => blob)` with `createConfigTestDb()` and `MemoryBlobStorageService`, the same as `config-remote.test.ts:57-67`. The store, identity, slot, CEK and device tokens are set up through `ConfigService` (`setupStore`, `mintDeviceToken`), using `helpers/config-helpers.ts`.
- **Network (`harness/net.ts`).** A `fetch` implementation that routes `http://account.test/**` to `app.fetch` and sets `cf-connecting-ip` to the calling device's IP. The tunnel then moves it into `x-forwarded-for` (`app.ts:634-636`), so the IP path under test is the real one.
- **Fault hooks**, keyed by inner path, which the router can read by decrypting nothing (the outer path is always `/tunnel`, so the hook counts calls):
  - `dropResponseAfterServer(n)`
  - `advanceClockBetween('/session', 'PUT')`
  - `unreachable()` (throws `TypeError('fetch failed')` with `cause.code='ECONNREFUSED'`)
  - `http5xx()`
- **Hostile-server helpers.** These edit the D1 row and blob directly: `rollbackTo(version)` and `swapBlob(fromConfig, toConfig)`.
- **Seam, owned by C and reviewed by B.** `ConfigServerFetchOptions` gains optional `fetchImpl` and `serverKey`. `RemoteConfigAdapter` gains an optional 5th constructor argument, `transport`. Production passes nothing.
  - This is needed rather than stubbing the global fetch: two devices running at the same time need different IPs.
  - `serverKey` comes from the test env's X25519 public key (`helpers/test-keys.ts`).
- **Devices (`harness/device.ts`).** Each device has:
  - a temp `XDG_CONFIG_HOME` (read by `shared/src/paths/dirs.ts:78`);
  - its own `RemoteTokenStorage(tmpTokensDir)` (`remote-token-storage.ts:34`);
  - an in-memory `SecureStorage` (interface at `utils/secure-storage.ts:36-41`);
  - an IP.

  Adapter-level scenarios construct adapters directly. Service-level scenarios (`loadRemote`, `RemoteResourceState`, the cache) load a fresh module graph per device (`vi.resetModules()`, set `XDG_CONFIG_HOME`, then `await import(...)`), because `configFileStorage` and `TOKENS_DIR` are module singletons. "Two processes on one machine" means two module graphs pointed at the same temp dir, so proper-lockfile contention is real.
- **Clock.** `vi.useFakeTimers({ toFake: ['Date'] })` plus `vi.setSystemTime`. Only `Date` is faked, so the proper-lockfile timers and fetch still run. Helpers: `clock.epochs(n)` (n × 300 s) and `clock.hours(h)`. The server's `sdkGetEpoch` and token expiry both read `Date`, so one clock drives both sides.
- **Proof that it runs.** The file has a `describe` count assertion. T15 checks that the lane log lists the file.

### 4.2 Scenarios

Each scenario runs today's code before its fix. A scenario that reproduces a defect is `it.fails('F<n> …')` until its fix task lands.

| ID | Scenario | Asserts | Starts as |
|---|---|---|---|
| H1 | A pushes at epoch E; clock +2 epochs; A and B pull | Content equal on both; version equal | green (guards bd0278084) |
| H2 | Clock rolls between `/session` and PUT | Push accepted; later pull decrypts | green |
| H3 | Portal `ConfigSession` pushes 3 epochs after open (T13) | Accepted after the session-material refresh; refused without it | green today, spec after D5 |
| H4 | A on IP1 and B on IP2, both enabled; A's token replayed from IP2 | `RemoteTokenIpMismatchError`; after T11, auto-refresh succeeds | it.fails (F10) |
| H5 | A moves IP1 to IP3 mid-life | Per D4: one refresh, then success | it.fails (F10) |
| H6 | Clock +25 h idle; pull | Refresh or success per D4 (today: `token_expired`) | it.fails (F10) |
| H7 | Two module graphs on one token dir: `Promise.all` of 10 pull/push mixes | All succeed; every DB token `usageCount <= 1` except crash-margin cases | it.fails (F8) |
| H8 | Drop the response of `/session`, then of PUT, once each; retry | One new version; token within grace; no duplicate archive row | green/partial (F9) |
| H9 | A and B push from the same base at once | Exactly one success and one 409; the blob D1 points at decrypts to the winner | it.fails (F7) |
| H10 | Rotate the CEK (service-level, as in `config-cek-rotation.test.ts`); B pulls, then pushes with the old CEK | B gets `RemoteStaleSlotError`; the old-CEK push is refused `stale_cek_generation`; B's tokens revoked | it.fails (F11, F12) |
| H11 | Pull OK, then `unreachable()`; read and write; then a 401 | Cache served with a warning, and equal to the last pull; write fails closed with the file hash unchanged; the 401 throws and no cache is served | green |
| H12 | Field coverage: a fixture fills every `RdcConfigSchema` leaf, with a builder driven by the `check-schema-coverage` walker, plus host-local fields (`state.repos[*].networkId`, `state.networkIds`, `renetPath`, `encryption`, `masterPasswordVerifier`, `remote`, an unknown key). Seed on A, pull on B, `setMachines` on B, pull on A. Repeat in master-password mode | The synced projection is deep-equal on A and B; A's host-local fields are byte-identical before and after; the verifier survives | it.fails (F3, F4, F18) |
| H13 | A deletes a machine, a repo and the ssh credential | Push succeeds (T9); B no longer has them; a tombstone with a fake hmac is refused | it.fails (F2) |
| H14 | `rollbackTo(v-2)` and `swapBlob(X→Y)`, then pull | `RemoteRollbackError` and an integrity error; the cache file is unchanged | it.fails (F1) |
| H15 | B edits `policy`; A adds a machine from the older base (409, then rebase) | Both survive on the server | it.fails (F6) |
| H16 | B changes `defaults.universalUser`; A pulls, then pushes a machine | A sees B's value; the server keeps it | it.fails (F5) |
| H17 | Enable: seed push OK, pull-back faulted; a second local config enrolled to the same store | Local file untouched; the first config's slot secret still present | it.fails (F17) |

### 4.3 Mutation controls (run by hand in T15; each must turn its test red)

Run 2026-09-26 against 3c99a41d0 (account e1d426b), one revert at a time, each file restored byte-identical (`cmp`) and `packages/shared` rebuilt around the shared rows. Every row below went red.

| Revert | Red test | Run 2026-09-26 |
|---|---|---|
| `adapter.ts` pull decrypts with `session.sdkDerived` | H1 | H1, H2 red |
| Server stores the current epoch instead of `body.sdkEpoch` | H2 | H2 red |
| Remove the CAS predicate (T5) | H9 | F7 H9 red |
| Remove the lease lock or token threading (T6) | H7 | H7 red |
| Remove the device-local overlay (`remote-cache.ts` pointer loop) | H12 | H12 (both modes) red, plus H11, H13-H16 |
| Replace the `state` merge with the pulled `state` (T17) | S3, S5 (`state-sync.test.ts`) | S3, S5 red; H12 green, since `state` syncs now |
| Drop `policy` from the synced blob and its commitments (`payload.ts syncedDocument`; `SENSITIVE_FIELDS` is gone since T17) | H12, H15 | first run: H15 only, H12 compared A with B but not with the seed; H12 now also compares with the seed and goes red |
| Server ignores the tombstone hmac comparison (T9) | D1 forged-proof test (`envelope-v3.test.ts`) | D1 red; no H13 test sends a forged tombstone |
| Remove the AAD, or the high-water check (T8) | H14 | F1 H14 red (both halves) |
| `pushOnce` base from disk without the rebase cache write (T4) | H15 | H15 red |
| Remove the generation check on push (T10) | H10 (F12) | F12 red (the push fails as RemotePreconditionError instead) |
| `loadRemote` serves the cache on `RemoteAuthError` | H11 | H11 red |
| Restore the `...local.account` overlay | H16 synced account field | first run: green (H16 covered only `defaults`); the new H16 account-field test is red |

## 5. Operator decisions (recommended option first)

**Rulings, 2026-09-25 (operator, via AskUserQuestion):**
- D1: (a) tombstone with proof, **plus versioning**. First check whether a deletion or versioning plan already exists (planned or half-built); plan it here if none does.
- D2: (a) read v2 and write v3.
- D3: (b) **all synced**, with no local override. This drops the `...local.account` / `...local.defaults` layering; T12 becomes "remove the overlay" (F5, H16).
- D4: (a) auto-refresh, **with a 7-day config token lifetime instead of 24 h**.
- D5: (a) enforce a ±1 epoch window. D6: (a) blind pointer names in v3. D7: (a) the harness in `private/account/tests/integration/config-sync/` (default taken; T1 built it there). D8: (a) separate plans for F19 and F20. D9: (a) the precise claim.
- D1's versioning, investigated: no other plan covers deletion (only T9 here). Version HISTORY is built: every push archives the previous blob to `versions/{version}.enc` with a `config_versions` row (`config.service.ts:604-625`), pruned to `CONFIG_VERSION_HISTORY_LIMIT = 50` (`:337`), listed by `GET /:id/versions` (`routes/configs.ts:1154`). RESTORE is designed (`docs/DESIGN-CONFIG-STORAGE.md:731`, audit event `config.version.restore` at `:751`) and was never built: no route, no service method, no CLI command. It becomes T16.

- **D1, deletion:**
  - (a) tombstone-with-knowledge (section 3.6), **recommended**;
  - (b) allow any subtree to vanish when its whole resource root is gone, without proof;
  - (c) keep deletion blocked for remote configs and document it.
- **D2, migrating to envelope v3:**
  - (a) the CLI and portal read v2 for one release with a warning and auto-upgrade to v3 on the next push, while the server refuses new v2 pushes; **recommended**;
  - (b) hard cut: every store re-seeds;
  - (c) keep v2 and add only the client high-water check (partial).
- **D3, account/defaults:**
  - (a) split each key into synced or device-only through the registry, **recommended**;
  - (b) all synced, no local override;
  - (c) all host-local, and stop syncing them.
- **D4, config token lifetime and IP binding:**
  - (a) auto-refresh through the login API token (section 3.8), **recommended**;
  - (b) a sliding 30-day expiry, keeping IP binding;
  - (c) drop IP binding for config tokens, relying on rotation and expiry.
- **D5, the SDK layer:**
  - (a) enforce a ±1 epoch window and document its real guarantee, **recommended**;
  - (b) remove layer 1 entirely, since the server holds `sdkMaster`;
  - (c) keep it as it is and fix only the docs.
- **D6, metadata:**
  - (a) blind the pointer names in v3, **recommended**;
  - (b) accept the leak and document it.
- **D7, harness location:**
  - (a) `private/account/tests/integration/config-sync/`, **recommended**;
  - (b) a new console-level cross-package suite with its own lane.
- **D8, follow-ups:**
  - (a) open separate plans for team scoping (F19) and syncing network IDs across devices (F20), **recommended**;
  - (b) fold them into this plan.
- **D9, the public claim:**
  - (a) state it as "Confidential against storage compromise and a passive operator. Integrity bound per config and version. Not protected against an operator who serves malicious portal code or withholds the newest version from a device that never saw it." **Recommended**;
  - (b) keep "zero-knowledge" wording, adding a footnote.

## 6. Sequencing and risks

- **Phase 0 (T1-T2).** The harness with `it.fails` markers. This proves it has teeth before any fix lands.
- **Phase 1**: local fixes with no wire change: T3, T4, T5, T6, T7, T12. Stop the data loss first.
- **Phase 2**: the protocol: T8, T9, T10, T13. One envelope v3 migration covers all four.
- **Phase 3**: T11, after PLAN-token-ip-rebind lands.
- **Risks.**
  - The envelope v3 rollout must reach the CLI, the portal, the executor (`container-config.ts`) and the rotation wizard in one release train. The server must accept v3 before any client emits it.
  - Tombstones need the pulled commitments, which the CLI and portal now discard (`adapter.ts:271-275`, `config-session.ts:101`). Both must start carrying them.
  - Faking only `Date` in the harness keeps proper-lockfile's staleness check (mtime against `Date.now`) consistent, because no lock is held across a clock jump. Assert that in H7.

### Critical Files for Implementation
- /home/developer/console/packages/cli/src/adapters/remote-config-adapter.ts
- /home/developer/console/packages/shared/src/config-crypto/selective.ts
- /home/developer/console/private/account/src/services/config.service.ts
- /home/developer/console/packages/cli/src/services/config/remote-cache.ts (with config-base.ts and resource-state.ts)
- /home/developer/console/private/account/tests/integration/config-remote.test.ts (the template for the new harness)

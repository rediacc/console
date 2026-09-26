# PLAN: config storage without a PRF passkey, and a virtual-authenticator E2E matrix

Status: approved
Owner: d778be9d
First-Seen: 2026-09-24
Depends-On: no-dep -- touches only private/account server, portal and e2e plus run-account-e2e.sh; no open plan edits those files
Worklist: #4bbdca38, #fa5c407e
Priority: P1 -- seed: Status approved, 4 open box(es), a recent operator order
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: private/account, .ci/scripts/test/run-account-e2e.sh, private/account/src/routes/device-codes.ts

**Operator order, 2026-09-24 (/ask).** "Passkey optional": config storage must be usable when the passkey provider returns no WebAuthn PRF output. Bitwarden creates the passkey but returns no PRF result (bitwarden discussion #13838, still open July 2026). "Virtual authenticator E2E": Playwright against Chrome's CDP virtual authenticator, with `hasPrf` true and false, over setup, unlock, member accept, CEK rotation and device setup. A provider without PRF must never reach a dead end.

Lead-verified before writing (2026-09-24): `passkeyCredentialId` is nullable (private/account/src/db/config-schema.ts:69). `POST /members` inserts the invitee identity (private/account/src/routes/configs.ts:931-936). `/passkey/verify` inserts again, against the unique index at private/account/src/db/config-schema.ts:83. `getAndValidateChallenge` matches on userId alone (private/account/src/services/passkey.service.ts:225-241).

## 1. Root cause

1. **The portal hard-codes passkey as the first method.**
   - The first method is fixed at private/account/web/src/pages/ConfigSetup.tsx:85 and :522 (`setupPasskeyAlways`).
   - The PRF check is copied three times, and each copy throws into the error screen: private/account/web/src/pages/ConfigSetup.tsx:223-231, private/account/web/src/pages/ConfigRemote.tsx:331-333 and private/account/web/src/pages/ConfigMemberAccept.tsx:110-118.
   - E2E private/account/e2e/tests/20-config-storage/20-03-passkey-setup.test.ts:104-135 asserts that dead end as the expected result.
   - `webauthnConfigured` and `webauthnSupported` block setup even when no passkey will be used.
2. **Only passkey registration creates the member identity.**
   - `setupStore` inserts the store and its slots but no identity (private/account/src/services/config.service.ts:316-405). The owner's identity row appears only through `POST /passkey/verify` (private/account/src/routes/configs.ts:1036-1045).
   - So a password-first owner is missing from `listMembers` (private/account/src/services/config.service.ts:1101-1132) and gets a 403 from `/store-secret` (private/account/src/routes/configs.ts:414-417).
3. **Every admin ceremony is passkey-only.**
   - Member add: private/account/web/src/pages/ConfigMembers.tsx:146-185.
   - CEK rotation: private/account/web/src/pages/RotateCekWizard.tsx:106-139, with a hard-coded `method: 'passkey'`.
   - Existing-store CLI handoff: private/account/web/src/pages/ConfigRemote.tsx:192-193.
   - Member accept writes `method: 'passkey'` (private/account/src/services/config.service.ts:1013-1041).
4. **Latent bug: member accept inserts the identity twice.** Accept inserts the identity a second time: `POST /members` already inserted it, and private/account/web/src/pages/ConfigMemberAccept.tsx:194-198 then calls `/passkey/verify`. That violates the unique index. The integration test skips `/passkey/verify` (private/account/tests/integration/config-member-add.test.ts:500-537), and the E2E only loads the accept page.
5. **Latent bug: registration can pick up a stale challenge.** The unlock ceremonies store authentication challenges (private/account/src/services/passkey.service.ts:151-158) but never consume them, and the lookup does not match on the challenge value. A later registration can therefore read a stale challenge. The "add a passkey later" path hits this directly.

## 2. Design

**Identity binding. No schema change and no migration.**
- The identity is the membership record, not the passkey. `x25519PublicKey` and `storageKeyId` exist without a passkey, and the `passkey_*` columns stay nullable. (If a migration were needed its number would be 0053; none is.)
- `setupStore` creates the owner's identity. The route takes a required `x25519PublicKey` and, when there is a passkey slot, an inline `passkeyRegistration`. The server verifies the registration and applies the PRF gate before any row is written. The response carries `storageKeyId`.
- `/passkey/verify` becomes bind-only: an UPDATE of the caller's identity, never an INSERT (this fixes bug 4).
  - Body: `{ storeId, registrationResponse }`.
  - 403 when the caller is not a member; 409 when a credential is already bound.
  - `prfSupported: z.literal(true)` leaves the DTO.
- A passkey slot needs a bound credential. `putSlot`, `acceptCekHandoff` and `completeCekRotation` enforce it with 409 `passkey_not_bound`. `DELETE /slots/passkey` clears the identity's `passkey_*` fields.

**Setup rules.**
- Slots must be non-empty, with unique methods, and must include `passkey` or `password`. A recovery code alone is refused with 400.
- `requirePasskey` stays "passkey-only".
- A passkey slot comes with a registration, and a registration only with a passkey slot.
- PRF gate failure returns 400 `{ code: 'prf_unsupported' }`. WebAuthn not configured returns 503.

**What the PRF gate is.** It checks a client claim, so it is an integrity guard, not a security control: it keeps an honest client from binding a credential that can never open its slot. Keep it, with the machine-readable code, and document it that way in the code.

**Other server rules.**
- Member accept takes `{ storeId, slot }` for any method. A non-passkey slot under `requirePasskey` is refused with 403.
- `setRequirePasskey(true)` returns 409 when the calling owner holds no passkey slot (self-lockout guard).
- `completeCekRotation` rejects non-passkey slots under `requirePasskey`. Today it only checks that the slot list is non-empty (private/account/src/routes/configs.ts:481-491).
- The challenge lookup keys on `(userId, challenge)` from clientDataJSON (this fixes bug 5).

**Portal.**
- New shared modules replace the three copies:
  - `web/src/lib/passkey-ceremony.ts` (`registerConfigPasskey`, the one owner of the `prf.enabled` check);
  - `web/src/lib/config-setup-material.ts` (`buildSetupMaterial` for ConfigSetup and DeviceConfigSetup);
  - `web/src/components/config/PrfMissingNotice.tsx` (test ids `prf-missing`, `prf-missing-use-password`, `prf-missing-retry`, `prf-missing-policy`).
- Setup offers passkey or master password as the first method. On a PRF-less passkey it shows the notice and then the password form. The retry is safe because nothing exists on the server before setup.
- Member accept decrypts the handoff first, then lets the user choose passkey or password. Under `requirePasskey` it shows the policy variant.
- ConfigMembers and RotateCekWizard unlock through `ConfigUnlock` and `unlockCek()` with any held method. `UnlockedCek` gains `method`, `kdfParams` and `wrappingKey`.
- ConfigKeySlots gets "Add passkey" (`slot-add-passkey`).
- CLI handoff: `passkey_secret` carries the secret of whichever slot is handed off, passkey first. ConfigRemote gets a passkey/password picker. The CLI needs no change: packages/cli/src/commands/config-remote-enable.ts:38 and packages/cli/src/adapters/remote-config-adapter.ts:319-327 are method-agnostic.
- WebAuthn requirements become informational unless passkey is chosen. `x25519Supported` stays blocking.

**Rejected.**
- A synthetic "password credential" in `passkeyCredentialId`.
- Making `x25519PublicKey` nullable: rotation seals to every identity key (packages/shared/src/config-crypto/rotation.ts:130-152).
- Deriving X25519 from the password.
- Dropping the PRF gate.
- Keeping the two-step setup-then-verify, which risks a second store on retry.
- Renaming `passkey_secret`: it would force a lockstep CLI release for no functional gain.
- Evaluating PRF despite `enabled !== true`: no evidence any provider under-reports.

## 3. Tasks

- [ ] T1 [A] Server (owner: private/account `src/**`, `tests/integration/**`). Implement the rules in section 2:
  - `routes/configs.ts`: setup, store-info, slots, require-passkey, rotate-cek/complete, members/accept, passkey/verify.
  - `services/config.service.ts`, `services/passkey.service.ts`, `dto/config.dto.ts`.
  - `routes/test.ts` `/seed-config-store` passes the owner's X25519 key.
  - Update the config integration tests that assumed a separate identity insert.
  - Add `tests/integration/config-password-first.test.ts`. It covers password-only setup plus the owner in `listMembers`, 400 for a passkey slot without a registration, `prf_unsupported` with no store created, accept that no longer collides (it must fail on the pre-change code), 409 `passkey_not_bound`, password accept, 403 under the policy, the self-lockout 409, rotation under the policy, and registration with stale auth challenges present.
- [ ] T2 [B] Portal (owner: private/account `web/src/**`, including the 13 `configStorage.json` and `console.json` locale files):
  - The three new modules, and the pages ConfigSetup, DeviceConfigSetup, ConfigRemote, ConfigMemberAccept, ConfigMembers, ConfigKeySlots and RotateCekWizard.
  - `api/config.ts` and `hooks/useConfigSession.ts`.
  - Unit tests for `registerConfigPasskey` (PRF true and false), the password branch of `buildSetupMaterial` (its handoff secret unwraps `wrappedCek`), and the extended `UnlockedCek`.
  - i18n:
    - reword `setupChooseIntro` and `console.json:sessionErrorPrfUnsupported`;
    - delete `setupPasskeyAlways` and `rotatePrfUnavailable`;
    - add `setupPasskeyDesc`, `setupPrimaryRequired`, `setupProvidersHint`, `setupDoneSoleAdminWarning`, the `prfMissing*` family, `acceptChooseMethod`, `acceptWithPasskey`, `acceptWithPassword`, `keysAddPasskey`, `keysPasskeyAdded`, `rotateUnlockPrompt`, `rotateKeepPasskey`, `remoteChooseMethod`, `remotePasswordLabel`, `membersUnlockToAdd` and `requirePasskeySelfLockout`, in all 13 locales.
- [ ] T3 [C] E2E, CI and docs (owner: private/account `e2e/**`, `.ci/scripts/test/run-account-e2e.sh`, `packages/www/src/content/docs/*/config-storage.md`). Order: the control first (PRF-less setup on today's code must fail), then helpers, then the matrix, then edits to existing specs, then the CI assertion.
  - Helpers:
    - one `addVirtualAuthenticator(page, { prf })` in `webauthn-helpers.ts`;
    - `seedPasswordConfigStore` sends `x25519PublicKey`;
    - `addOrgMember`, `createDeviceCode`/`pollDeviceHandoff`/`decryptHandoff`, `startCallbackServer` and `expectNoPrfDeadEnd`.
  - New `e2e/tests/20-config-storage/20-11-prf-provider-matrix.test.ts` (`@config @webauthn`, chromium). Cases (a) to (g), each for `prf` true and false: setup, add a passkey later, member accept, CEK rotation, device setup, CLI callback handoff, and the `requirePasskey` policy. Every PRF-less case calls `expectNoPrfDeadEnd`.
  - Edit 20-03 (dead end becomes the password path), 20-08 (labels) and 20-10 (add a passkey before enabling the policy).
  - Add a `test:webauthn` script.
  - `run-account-e2e.sh` asserts from `reports/e2e/results.json` that at least N `@webauthn` chromium tests ran with status `expected` and none were skipped.
  - Docs: the Bitwarden row says to use a master password.
  - Check first whether `DeviceConfigSetup` sends `encryptedBlob` as an object while `private/account/src/routes/device-codes.ts:38-39` expects a string.
- [ ] T4 Lead: before deploy, run one production query: slot holders with no `config_user_identities` row. Then deploy eu and walk the operator's Bitwarden setup end to end.

## 4. CI wiring

The existing step "Run Account Portal E2E tests" (`.github/workflows/ct-tests.yml:1923-1924`, job `test-account-e2e`) runs every chromium spec with no grep (`.ci/scripts/test/run-account-e2e.sh:32`, `:233-240`), so the new spec rides along without a second step. The results.json assertion in T3 is what proves it ran. Server integration tests run under `.github/workflows/ci-quality.yml:2602` and portal unit tests under `check:ci-test-account-web`.

## 5. Risks

- The self-lockout guard changes the path 20-10 depends on; T3 handles it.
- A PRF-less passkey is left behind in the provider, and the notice says to delete it.
- Pre-existing and out of scope: the owner's identity X25519 private key is discarded at setup (private/account/web/src/pages/ConfigSetup.tsx:208-212), so a non-owner admin rotation would strand the owner.
- Production stores without an identity row (T4 query).
- E2E runtime: the job budget is 30 minutes (.github/workflows/ct-tests.yml:1873), so the matrix runs once per PRF value.

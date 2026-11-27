# PLAN-config-sealed-local: seal a remote-enabled config's secrets on disk under an OS-keyring key, with the master password optional on top

Status: approved -- operator decisions ASKED 2026-11-27: (1) remote configs sealed by default with an opt-out, (2) a random keyring key with the master password stacked on top as an option, (3) on key loss re-pull and re-seal with a one-line notice, and refuse on REDIACC_SECRET_STORE=file, (4) in the same change: seal on next write, master-password verbs, PBKDF2 600k, and sealing of the token files
Depends-On: no-dep -- builds only on landed code (secure-storage.ts native selection, remote-cache.ts overlay, config-field-crypto.ts stubs)
Priority: P1 -- a remote config's cache holds every synced secret in plaintext (mode 0600) by default, while docs/DESIGN-CONFIG-STORAGE.md:70 and the www page claim an "encrypted-at-rest read cache"
Concurrency: parallel -- 8 writer clusters on disjoint files in 4 waves (W1 crypto core, W6 i18n and W7 docs first; then W2 storage and W4 tokens; then W3 remote lifecycle and W5 commands; then W8 drill), then live boxes in order
Owns: agent/plans/PLAN-config-sealed-local.md, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/encryption/constants.ts, packages/cli/src/adapters/crypto.ts, packages/cli/src/adapters/config-field-crypto.ts, packages/cli/src/adapters/config-seal-key.ts, packages/cli/src/adapters/config-file-storage.ts, packages/cli/src/adapters/remote-token-storage.ts, packages/cli/src/adapters/remote-config-adapter.ts, packages/cli/src/services/core/master-password.ts, packages/cli/src/services/config/config-base.ts, packages/cli/src/services/config/remote-cache.ts, packages/cli/src/services/config/seal-recovery.ts, packages/cli/src/services/repo/prune.ts, packages/cli/src/services/account/subscription-auth.ts, packages/cli/src/commands/config.ts, packages/cli/src/commands/config-master-password.ts, packages/cli/src/commands/config-seal.ts, packages/cli/src/commands/config-remote.ts, packages/cli/src/commands/config-remote-unlink.ts, packages/cli/src/commands/config-remote-enable.ts, packages/cli/scripts/lib/option-classification.ts, packages/shared/src/cli-contract/data/contract.generated.ts, packages/cli/src/i18n/locales/*/cli.json, docs/DESIGN-CONFIG-STORAGE.md, docs/environment-variables.md, packages/www/src/content/docs/*/config-storage.md, .ci/rediacc_ci/drills/transfer.py, .ci/rediacc_ci/tests/test_drills_universe_transfer.py, packages/cli/src/**/__tests__/*seal*.test.ts, packages/cli/src/**/__tests__/*master-password*.test.ts
Live-Proof: bench -- `cli-bench` runs `./rdc.sh --config <cfg> subscription status`, which reads the sealed api-token file, and the shared schema change touches the account surface that bench serves
Owner: d778be9d
Updated: 2026-11-27

## Context (checked 2026-11-27 at bdbf06a464; each writer re-reads before relying on a line)

- `EncryptionSchema.mode` is `z.enum(['plaintext','master-password'])` (packages/shared/src/config-schema/schemas.ts:465). `createEmptyRdcConfig` writes `plaintext` (:690). `EncryptedBlobSchema` is `{data}` with no version (:52).
- The field transform runs only in `master-password` mode (packages/cli/src/adapters/config-field-crypto.ts:31-33, :104-121). Stubs `<encrypted:/ptr>` let public reads parse without a password (:17-22, :54-66). The verifier is the password encrypted under itself, unencrypted at rest (:12-15; packages/cli/src/commands/config.ts:63-70).
- Every `nodeCryptoProvider.encrypt` runs PBKDF2 at `ENCRYPTION_CONFIG.ITERATIONS` 100000 with a fresh salt per blob (packages/cli/src/adapters/crypto.ts:9-23, :59, :70; packages/shared/src/encryption/constants.ts:9). A blob does not record its iteration count. Raising the constant on its own would make every existing blob and verifier undecryptable, and 600k per field per save would multiply the cost by the field count.
- The password resolves from the process cache, then `REDIACC_MASTER_PASSWORD`, then a TTY prompt (packages/cli/src/services/core/master-password.ts:15-47; packages/cli/src/adapters/config-file-storage.ts:157-161). The only setter is `config init --master-password <password>` (packages/cli/src/commands/config.ts:293), a flag that the contract marks `sensitive` (packages/shared/src/cli-contract/data/contract.generated.ts:4818).
- The remote cache is the config file itself, written through `configFileStorage.updateCache` (packages/cli/src/services/config/remote-cache.ts:1-16, :159-175). `/encryption` and `/credentials/masterPasswordVerifier` are device-local and never synced (packages/shared/src/config-schema/sensitivity.ts:448-458). A pull rebuilds `encryption` as plaintext, and the overlay keeps the local value (packages/cli/src/services/config/remote-cache.ts:103-115).
- `saveUnlocked` copies the previous file to `<name>.json.bak` before every write (packages/cli/src/adapters/config-file-storage.ts:179-191, :356-372). The first sealed write would leave the pre-seal plaintext in `.bak`.
- secure-storage.ts: the native backend is the Secret Service, then keyctl @u (Linux), Keychain (macOS) or DPAPI (Windows, one PowerShell spawn per call, 20 s limit, :377-399). Selection proves a round trip once per process (:632-666). The key allowlist is `^[A-Za-z0-9:_-]{1,200}$` (:31-36). `REDIACC_SECRET_STORE=file` is the only opt-in (:531, :648-650). No backend falls back silently.
- The keyring holds only the slot secret, read on every `deriveCek` with no cache (packages/cli/src/adapters/remote-config-adapter.ts:645-654).
- `.tokens/<name>.json` holds `{token, wrappedCek, sync}` at 0600. `sync` holds the anti-rollback counters (`highWater`, `envelopeVersion`, `cekGeneration`, `policyHighWater`) next to confidential values (`fckSalt`, `configKey`, `policyContext`) (packages/cli/src/adapters/remote-token-storage.ts:22-71, :183-196). `set()` keeps an existing sync record across a re-enroll, by design (T8/T9).
- `api-token-<name>.json` is written synchronously at 0600 (packages/cli/src/services/account/subscription-auth.ts:117-131) and read synchronously (:66-75). `serverUrl`-only readers are at :89 and :101, and the token reader is at :167.
- Shared AES-GCM and HKDF helpers already exist (packages/shared/src/config-crypto/aes.ts, hkdf.ts).
- The transfer drill proves seed, offline read, fail-closed write and second device on keyctl @u (.ci/rediacc_ci/drills/transfer.py:5-11, :266-372). vm:check runs it as A2.2 (.ci/rediacc_ci/drills/vm_check.py:24, :3600).
- The docs overstate the protection: docs/DESIGN-CONFIG-STORAGE.md:70 ("encrypted-at-rest read cache"), :171 (Linux row lists keyctl only, with no Secret Service), :619 ("Save to the encrypted local cache"). www packages/www/src/content/docs/en/config-storage.md:117 says "encrypted at rest with the same mechanism as any local config". 13 locales carry the page, each with a `sourceHash`.

## Design

**D1 Modes.** `encryption.mode` gains `keyring` and `keyring+master-password`. New device-local fields under `/encryption`, already device-local as a whole, so sync is unaffected:
- `keyringId`: `rdc:seal:<uuid>`, a fresh uuid per seal and per re-seal, inside the secure-storage allowlist.
- `kdf`: `{alg:'pbkdf2-sha256', iterations:600000, salt}`, present whenever a password is part of the key.
- `sealOptOut`: boolean.

A shared helper `isSealed(config)` (mode is anything but `plaintext`) replaces the three `=== 'master-password'` tests (packages/cli/src/adapters/config-field-crypto.ts:32, packages/cli/src/adapters/config-file-storage.ts:108, packages/cli/src/services/repo/prune.ts:104). `config show`'s `encrypted` column (packages/cli/src/commands/config.ts:45) prints the mode.

**D2 Keys.**
- `K_ring`: 32 random bytes, base64, stored in secure storage under `keyringId`.
- `K_pw`: PBKDF2-SHA256(password, kdf.salt, 600000), derived once per process.
- Field key: `K_field = HKDF-SHA256(ikm = K_ring | K_pw | K_ring||K_pw, info = "rdc-config-seal-v2|" + config.id)`.
- Field blob v2: `{v:2, data}`, AES-256-GCM through shared/config-crypto/aes.ts, with AAD = `pointer + "|" + keyringId`, so a blob cannot be moved to another field or another key.
- A blob with no `v` is legacy: per-blob PBKDF2 at 100k under the password, read-only. The next write re-seals it as v2.
- `ENCRYPTION_CONFIG` keeps `ITERATIONS: 100000` renamed to `LEGACY_ITERATIONS`, and gains `ITERATIONS: 600000`. crypto.ts decrypt takes an iteration count, defaulting to legacy.

**D3 Per-process key cache.** New module adapters/config-seal-key.ts with these functions: `loadKey(keyringId)`, `mintKey()`, `dropKey(keyringId)`, `deriveFieldKey(config, password?)`.
- One Map holds `keyringId -> K_ring` and `(config.id, salt) -> K_pw`. One secure-storage `get` per key per process, so a DPAPI host spawns PowerShell once per key, not once per field or per read.
- Public reads never call `getSecureStorage()`. Selection itself costs a round trip, three PowerShell spawns on DPAPI.
- The slot-secret read in `deriveCek` goes through the same cache (D9).

**D4 Read path through placeholders.** `injectEncryptedStubs` runs for every sealed mode. `load()` returns stubs and never touches the keyring. Only `loadDecrypted` and `update`/`mutate` unseal. As a result `rdc.sh`, MCP tools and agents reading public fields (machine lists, repo names, `config show`) need no key, no prompt and no keyring round trip. A test spies on `getSecureStorage` and on `child_process` to prove zero calls for public reads.

**D5 Seal on next write (migration, no command).** In `saveUnlocked`, under the file lock, a config is upgraded when all of the following hold:
- `hasRemoteConfig(config)`,
- mode is `plaintext` or `master-password`,
- `!sealOptOut`.

The upgrade sets mode to `keyring` (or `keyring+master-password` when a verifier exists), mints `K_ring`, and runs `set` in secure storage BEFORE the temp-file rename.
- If the rename fails, the new key is deleted.
- After the rename, `.bak` is overwritten with the sealed bytes. Re-seals and opt-out removals do the same, so no plaintext or old-key copy stays behind.
- Cache writes (`updateCache`, no version bump) migrate too, because a refresh is the most common write.
- Local-only configs are never upgraded, and `seal on` refuses them (operator: no keyring option for local-only configs in this change).

**D6 File-store refusal.** When `REDIACC_SECRET_STORE=file`, D5 does not seal. The write goes ahead in its current mode, and one stderr line per config per process gives the reason (`commands.config.seal.fileStoreRefused`). An existing `master-password` mode is kept as is. `rdc config seal on` on a file store exits 2 with the same message. Stacking a keyring key over the file store is refused for the same reason.

**D7 Key loss.** Unsealing raises `SealKeyLostError` when either of these happens:
- secure storage returns null for `keyringId`,
- GCM authentication fails under a correct password (a legacy blob decrypt that fails is not counted as key loss).

`config-file-storage.ts` calls a registered handler (the same injection pattern as `RemoteStateWriter`, set from services/config/seal-recovery.ts) that:
1. Pulls from the store through the existing refresh path.
2. Writes the cache from an at-rest view with every sealed leaf dropped (`writeRemoteCache` gains a `discardSealed` option; it must not try to unseal the old file).
3. Mints a new `keyringId`, deletes the old entry, prints `commands.config.seal.keyLostResealed` once, and retries the read.

Further behavior:
- Offline, public reads still serve from stubs. A secret read fails with `keyLostOffline`, which names `rdc config remote refresh`.
- When the slot secret is gone too, which is typical after a keyctl reboot, the existing `RemotePasskeySecretMissingError` re-enroll message stands, and the re-enroll's cache write seals under a new key.
- Stacked mode keeps the same password and kdf salt. Only `K_ring` changes.
- Invariant enforced by a test in W1: no pointer that is in `DEVICE_LOCAL_POINTERS` is also `encryptAtRest`. A pull must be able to restore every sealed leaf, otherwise key loss would destroy data.

**D8 Master-password verbs.** `rdc config master-password set|change|remove [name] [--password-file <path|->]`.
- Input comes from a TTY prompt (entered twice, compared) or from the file or stdin. There is no value flag.
- `change` unlocks through the existing resolution, then asks for the new password.
- `set` on a local config gives `master-password` mode. On a remote sealed config it gives `keyring+master-password`.
- `remove` on a stacked config gives `keyring`. On a local config it gives `plaintext` and needs `--yes`.
- Every verb re-seals in a single locked write: new kdf salt, new verifier, new field blobs.
- Verifier v2 is `v2:` + AES-GCM(K_pw, "rdc-mp-verifier-v2"), at the same pointer.
- A legacy verifier that verifies is rewritten as v2 under the lock in the same process (the migration of the 100k verifier). `REDIACC_MASTER_PASSWORD` keeps working for unlock.
- `config init --master-password` stays for compatibility. It gains a `--master-password-file` sibling, and its help text points to the file form.

**D9 Token files.**
- `.tokens/<name>.json` gets a `sealed: {v:1, data}` field. It holds `token`, `fckSalt`, `configKey` and `policyContext`, under `HKDF(slotSecret, info="rdc-token-seal-v1|" + configName)`. The slot secret is already required for any pull, so sealing under it adds no new failure mode, and a lost config seal key leaves the token usable for the D7 re-pull. `wrappedCek` is already ciphertext under the slot secret and stays as it is.
- **Decision for the operator (default applies unless the operator rules otherwise):** the anti-rollback counters (`binding`, `highWater`, `envelopeVersion`, `cekGeneration`, `policyHighWater`) stay plaintext. They are not secret. If they were sealed, losing a key would silently reset them, which T8/T9 forbid, and `set()` carries them across a re-enroll.
- `api-token-<name>.json` of a sealed config stores `serverUrl` in plaintext and `token` as `sealed` under `HKDF(K_ring, info="rdc-api-token-v1|" + name)`, with `keyringId` recorded in the file. The `serverUrl` readers (:89, :101) need no key.
- The token reader (:167) unseals synchronously through a sync key-load path in config-seal-key.ts. The backends are `execFileSync` internally, so a sync path is possible.
- On key loss the api token is unreadable, and the notice adds `rdc subscription login`. `REDIACC_TOKEN` is unaffected. api-token files of local-only configs stay plaintext.
- Both files migrate on their next write.

**D10 Lifecycle.**
- `config remote disable` and `config remote unlink`: unseal to `plaintext` (or `master-password` if stacked), delete the keyring entry, print `unsealedOnDisable`.
- `config delete`: deletes the keyring entry.
- `config remote enable`: seals at the first cache write.
- `rdc config seal status|on|off [name]`: `off` sets `sealOptOut` and unseals. `on` clears it and seals now.

## i18n keys (W6 adds them first; the other clusters reference them by name)

`commands.config.seal.{descriptionShort,description,status.descriptionShort,on.descriptionShort,off.descriptionShort,statusLine,sealed,optedOut,keyLostResealed,keyLostOffline,keyLostApiToken,fileStoreRefused,localOnlyRefused,unsealedOnDisable}`, `commands.config.masterPassword.{descriptionShort,description,set.descriptionShort,change.descriptionShort,remove.descriptionShort,optionPasswordFile,promptNew,promptConfirm,mismatch,notSet,alreadySet,set,changed,removed,removeNeedsYes}`, `commands.config.init.optionMasterPasswordFile`, `errors.sealKeyLost`.

English source wording follows the prose style: no first or second person. Example: `Config {{name}}: its seal key was missing from the OS keyring; re-pulled from the store and sealed under a new key.`

## Boxes

### Wave 1
- [ ] W1 [writer] Crypto core, model opus. Covers D1 schema fields and `isSealed`, the D2 v2 blob, KDF and HKDF, the D3 key module with its cache and sync load, the D7 invariant test, and 600k with legacy decrypt.
  Owns: packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/encryption/constants.ts, packages/cli/src/adapters/crypto.ts, packages/cli/src/adapters/config-field-crypto.ts, packages/cli/src/adapters/config-seal-key.ts, packages/cli/src/adapters/__tests__/config-seal-key.test.ts, packages/cli/src/adapters/__tests__/config-field-crypto-seal.test.ts
  Accept: `cd packages/cli && npx vitest run src/adapters/__tests__/config-seal-key.test.ts src/adapters/__tests__/config-field-crypto-seal.test.ts` rc 0. The tests must include these controls:
  - a blob moved to another pointer fails (AAD);
  - a legacy 100k blob decrypts, and the same blob read as v2 fails;
  - with Windows mocked through the existing `vi.mock('node:child_process')` PowerShell fake from secure-storage.dpapi-timeout.test.ts, 50 field reads produce exactly 1 Unprotect spawn, and the control with the cache cleared produces 2;
  - the DEVICE_LOCAL-vs-encryptAtRest invariant fails when a fixture adds an offending pointer.
- [ ] W6 [writer] i18n, model sonnet. Every key listed above, in all 13 cli.json files, translated.
  Owns: packages/cli/src/i18n/locales/*/cli.json
  Accept: `npm run check:ci-i18n-completeness` and `npm run check:ci-i18n-cross-locale-core` rc 0
- [ ] W7 [writer] Docs, model sonnet.
  - DESIGN-CONFIG-STORAGE.md: :70, :171 (add the Secret Service row and the D5/D7 behavior), :619. Add a section "Sealed local cache" covering modes, key source, key loss, file-store refusal and token files.
  - docs/environment-variables.md: `REDIACC_SECRET_STORE` now also controls the sealing refusal.
  - www en/config-storage.md: :117 and the Security section, then the 12 locale copies re-translated with a fresh `sourceHash`.
  Owns: docs/DESIGN-CONFIG-STORAGE.md, docs/environment-variables.md, packages/www/src/content/docs/*/config-storage.md
  Accept: `npm run check:ci-i18n-www-content`, `npm run check:ci-docs-structure-parity` and `npm run check:ci-prose-style` rc 0, plus `grep -n "encrypted-at-rest read cache" docs/DESIGN-CONFIG-STORAGE.md` empty

### Wave 2
- [ ] W2 [writer] Storage and the password service, model opus.
  - D4 stubs for every sealed mode.
  - D5 seal on next write, including cache writes, the keyring-before-rename order with rollback, and the `.bak` overwrite.
  - D6 refusal.
  - The `SealKeyLostError` raise, plus a handler-registration hook.
  - master-password.ts: K_pw once per process, verifier v2 and legacy rewrite.
  - config-base.ts verifier accessors and the prune.ts `isSealed` change.
  Owns: packages/cli/src/adapters/config-file-storage.ts, packages/cli/src/services/core/master-password.ts, packages/cli/src/services/config/config-base.ts, packages/cli/src/services/repo/prune.ts, packages/cli/src/adapters/__tests__/config-file-storage-seal.test.ts, packages/cli/src/services/core/__tests__/master-password-v2.test.ts
  Accept: vitest on both files rc 0. Controls:
  - a remote fixture's raw file contains no secret value after one `updateCache`, while the local-only control keeps its plaintext;
  - `sealOptOut` stays plaintext;
  - `REDIACC_SECRET_STORE=file` stays plaintext and prints the line once;
  - `.bak` holds no plaintext;
  - a public `load()` makes 0 `getSecureStorage` calls, and the `loadDecrypted` control makes 1;
  - a 100k verifier is rewritten as `v2:`;
  - a stacked config fails with the right key and the wrong password, and with the right password and the wrong key.
  Also the existing persist-unification, storage and remote-cache tests pass.
  After: W1
- [x] W4 [writer] Token sealing, model opus. D9 for `.tokens` (only the confidential fields sealed, counters plaintext), the slot-secret cache in `deriveCek`, and the api-token seal with the sync unseal.
  Owns: packages/cli/src/adapters/remote-token-storage.ts, packages/cli/src/adapters/remote-config-adapter.ts, packages/cli/src/services/account/subscription-auth.ts, packages/cli/src/adapters/__tests__/remote-token-storage-seal.test.ts, packages/cli/src/services/account/__tests__/subscription-auth-seal.test.ts
  Accept: vitest rc 0. Controls:
  - the raw `.tokens` file contains no `token`, `fckSalt` or `policyContext` text, and `highWater` is readable;
  - a re-enroll `set()` keeps the counters;
  - a lost slot secret gives the re-enroll error, not a silent empty record;
  - api-token `serverUrl` reads make 0 keyring calls;
  - a local-only config's api-token stays plaintext.
  The existing remote-token-storage.test.ts and remote-config-adapter.real-crypto.test.ts pass.
  After: W1
    (ticked) 2026-11-27T13:42:08Z by d778be9d: commit:08f2a701b1; W4 token sealing; cli vitest src/adapters src/services/account rc 0 landed

### Wave 3
- [ ] W3 [writer] Remote lifecycle, model opus. D7 recovery handler (pull, `discardSealed` write, new key, old key deleted, one notice, offline message) and D10 disable, unlink, enable and delete.
  Owns: packages/cli/src/services/config/seal-recovery.ts, packages/cli/src/services/config/remote-cache.ts, packages/cli/src/commands/config-remote.ts, packages/cli/src/commands/config-remote-unlink.ts, packages/cli/src/commands/config-remote-enable.ts, packages/cli/src/services/config/__tests__/seal-recovery.test.ts
  Accept: vitest rc 0. Controls:
  - with the key deleted, online: one notice line, a new `keyringId`, the secret readable;
  - the same offline: public read rc 0 and secret read exits with `keyLostOffline`;
  - disable leaves plaintext and no keyring entry;
  - a stacked config after key loss keeps its kdf salt.
  The existing config-remote-disable*.test.ts pass.
  After: W2, W4
- [ ] W5 [writer] Commands, model sonnet. `config master-password set|change|remove` (prompt, `--password-file`, `-` for stdin), `config seal status|on|off`, `init --master-password-file`, the `encrypted` column, then contract regen.
  Owns: packages/cli/src/commands/config.ts, packages/cli/src/commands/config-master-password.ts, packages/cli/src/commands/config-seal.ts, packages/cli/scripts/lib/option-classification.ts, packages/shared/src/cli-contract/data/contract.generated.ts, packages/cli/src/commands/__tests__/config-master-password.test.ts, packages/cli/src/commands/__tests__/config-seal.test.ts
  Accept: vitest rc 0, plus `npm run generate:cli-contract -w packages/cli` with no diff afterwards, plus `npm run check:ci-cli-contract` and `npm run check:ci-i18n-cli-key-usage` rc 0. Controls:
  - no verb accepts a password value on argv;
  - `seal on` refuses a local-only config and a file store with exit 2;
  - `remove` on a local config without `--yes` refuses.
  After: W2, W3

### Wave 4
- [ ] W8 [writer] Transfer drill, model sonnet. New phase after phase 2:
  - the raw cache file lacks the `config ssh set` key material and has `encryption.mode == "keyring"`;
  - phase 2's offline read still passes;
  - a key-loss leg runs `keyctl unlink` on the `rdc:seal:` entry only, comes back online, reads, and asserts the stderr notice and a changed `keyringId`;
  - a `REDIACC_SECRET_STORE=file` leg asserts the refusal line and plaintext mode.
  Selftest cases cover each new assertion.
  Owns: .ci/rediacc_ci/drills/transfer.py, .ci/rediacc_ci/tests/test_drills_universe_transfer.py
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.drills.transfer --selftest` rc 0 and `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_drills_universe_transfer.py` rc 0
  After: W3
- [ ] V1 [live] vm:check with A2.2 green on the landed tree, with the receipt recorded.
  Accept: `npm run vm:check` VERIFIED with A2.2 `transfer` PASSED, including the W8 assertions
  After: W5, W8
- [ ] LP-bench [live] Fresh bench receipt after deploy, so the sealed api-token is read through `rdc.sh`.
  Accept: live-proof bench cli-bench
  Needs: bench-deploy
  After: V1

## Risks

- e2e tests that read a remote config's raw JSON for a credential will break once sealing is on. W2 greps `packages/cli/tests*` and `ct-tests` for raw reads and moves them to `loadDecrypted`.
- On a keyctl-only host a reboot loses `K_ring` and the slot secret together. Recovery is the existing re-enroll, followed by `rdc subscription login` for the api token. The docs state this.
- Two processes migrating the same config: D5 runs under the file lock and the at-rest read is redone inside it, so only one key is minted. A W2 test runs two concurrent `updateCache` calls and expects one `keyringId` and one keyring entry.

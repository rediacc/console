# Rediacc Config Storage Provider — Design Document

## Overview

A "rediacc" config storage provider lets teams sync CLI configuration files through the account server. Configs hold highly sensitive data (SSH keys, machine IPs, credentials), so they are encrypted on the client under a key the server never holds. [Security model](#security-model) states exactly what that protects and what it does not; it supersedes any broader "zero-knowledge" wording further down.

## Goals

1. **Client-held key**: the server stores blobs it cannot decrypt on its own (the precise claim is in [Security model](#security-model))
2. **Passkey first**: passkeys (biometric) are the preferred unlock; master password and recovery code slots exist for devices and providers without PRF
3. **Team sharing**: Multiple team members access the same configs
4. **Split-key security**: Neither client nor server alone can derive the encryption key (a master password slot is the exception, see the table below)
5. **Rotating tokens**: Stolen tokens self-invalidate on next legitimate use
6. **Cross-platform**: Works on Windows, macOS, Linux via browser-based passkey flow

## Security model

This section describes the system as built. Where an older section below says more, this one holds.

**The claim.** Stored configs are confidential against a compromise of the server's storage and against a passive operator. Every blob is bound to its store, config, team and version, so the server cannot swap one config's blob for another's or edit a blob undetected. The design does NOT protect against an operator who serves malicious portal code, or who withholds the newest version from a device that has never seen it.

Confidentiality rests on one key, the CEK. The server holds the other two layers' keys: the org passphrase (layer 3, stored server-recoverable) and `sdkMaster` (layer 1). Layer 2 is the CEK, wrapped per slot under `HKDF(slotSecret ‖ serverSecret)`; the slot secret stays on the device (the OS keyring for the CLI, RAM in the portal).

### What the server can and cannot learn or do

| Area | The server can | The server cannot |
|---|---|---|
| Content | Remove layer 3 (org passphrase) and layer 1 (`sdkMaster`) | Remove layer 2 without a slot secret |
| Metadata | Read the plaintext envelope: config id, team, version, SDK epoch, last-modified time, blob size, the number of committed fields and each one's value kind (string, object, missing, ...), plus request times and client IPs | Read machine, repository or storage names: envelope v3 blinds every commitment key, and a fresh `fckSalt` per push hides which values changed |
| Substitution | Refuse, delay or drop any request | Serve one config's blob as another config's, another team's, another version's or another epoch's, or next to edited commitments: the CEK layer's GCM tag fails |
| Rollback | Serve an old version to a device that never saw a newer one (a freshly enrolled device, or one whose token file was lost) | Serve the CLI a version older than the high-water mark it recorded: the pull is refused |
| Availability | Delete blobs, rows and history | - |
| Portal code | Serve modified JavaScript that reads the CEK or a slot secret out of the browser | - |
| Master password slot | Guess the password offline: it holds the slot's public KDF parameters (PBKDF2-SHA256, 600,000 iterations), the wrapped CEK and `serverSecret` | - |

A passkey slot (PRF output) and a recovery code (160 random bits) are not guessable this way; a master password slot is as strong as the password.

The anti-downgrade and tombstone rules are enforced BY the server, against writers. They stop a member or an agent that does not know a value from deleting or silently dropping it; they are not a protection against the server itself.

### Envelope v3: binding and deletion

Both client-side AES-GCM layers authenticate the same additional data:

```
'rediacc-config-aad-v3' NUL canonical({
  v: 3, storeId, configId, teamId | null, version, sdkEpoch,
  commitments: SHA-256(canonical({ alg, fckSalt, fields })),
})
```

A reader rebuilds it from its own pointer (the CLI's `remote` block, the portal's store and config choice), never from the pull response. The blob HMAC of envelope v2 is retired; the GCM tag covers the blob and its binding.

- **Blinded names.** A commitment key is `base64(HMAC(PBK, pointer))` with `PBK = HKDF(CEK, salt = configId, info = 'rediacc-config-ptr-v1')`. One pointer keeps one key across pushes of a config, so the server's anti-downgrade check still compares keys, and the same name in two configs gets unrelated keys.
- **Tombstones.** A push that drops a committed path carries `commitments.removed[key]`: the stored commitment, recomputed by the client from the value it saw under the stored `fckSalt`. The server lets a stored key vanish only against a matching tombstone, so deleting a machine, repository or storage works, and deleting a value requires knowing it.
- **High-water mark.** The CLI records the highest version it has pulled or pushed per config in its token file (not in the config cache, so clearing the cache does not reset it) and refuses a pull below it. Once it has seen v3 for a config it also refuses a v2 copy.
- **Migration.** Clients read v2 for one release, with a warning, and upgrade the config to v3 on their next push. The server refuses a v2 push.

**Residual risk.** A device that has never seen a newer version has nothing to hold the server against, so a server can still hand it an old one. Guaranteeing freshness against a malicious server needs an external witness, which this design does not have.

### Versions and restore

Every push archives the replaced version (the newest 50 are kept). `rdc config remote versions` lists them; `rdc config remote restore <version>` decrypts that version and publishes its content as a NEW version on top of the current one, through the ordinary compare-and-swap push. No version number moves backwards, so every device's high-water mark stays valid. Paths the restored copy lacks are deleted by tombstone, the network-ID allocator keeps the current counter when it is higher, and the server records `config.version.restore`.

### What syncs

Everything in a config syncs except these device-local pointers: `/schemaVersion`, `/version`, `/remote`, `/encryption`, `/renetPath`, `/credentials/masterPasswordVerifier`, and the login fields `/account/accountServer` and `/account/e2ePublicKey` (a login, and a logout, is per device). `state` syncs in full, including every repository's network ID, so a second device of a team opens a repository under the same network ID the first device allocated.

### Pushes, offline reads and tokens

- **Compare-and-swap.** A push names the version it replaces; the server moves the row only if it is still at that version and answers a conflict otherwise. Each version has its own blob key, so a losing push never overwrites a blob anything points at.
- **Offline.** A remote config keeps an encrypted-at-rest read cache. When the server is unreachable, reads are served from it with a staleness warning; writes fail closed, with no offline queue. A config with no `remote` block is local and works fully offline.
- **Config tokens.** Each request rotates the token (three uses of one token allowed, for retries), the first use binds it to the client's IP, and each token lives 7 days from the request that minted it. A token that expired, ran out of uses or is bound to an address the machine left is renewed by the CLI through the login token (`POST /configs/device-token/refresh`, scope `config:enroll`), whose own IP rebind takes a TOTP code. The renewal carries no key material.
- **SDK epoch.** The server refuses a push sealed more than one 5-minute window from its current epoch. Layer 1 stops a holder of the CEK and a blob who has no valid config token; it does not stop the server, which holds `sdkMaster`.
- **After a CEK rotation.** The other members' config tokens are revoked, and a device still holding the old key is told to re-enable (`rdc config remote enable`) rather than failing with a decryption error.
- **Member removal.** The member's slots, identity, pending handoffs and config tokens are deleted, so the next request is refused. What the member already pulled stays on their device; a copy of the CEK they kept is neutralized only by a CEK rotation.

## Architecture

### Key Hierarchy

```
Passkey (in YubiKey/iCloud Keychain/1Password)
  │
  │  PRF(passkey, "rediacc-secret-v1")
  ├────────────────────────────────────────► passkey_secret
  │                                          (deterministic, never transmitted to server)
  │  PRF(passkey, "rediacc-x25519-v1")
  ├────────────────────────────────────────► user_x25519_private → user_x25519_public
  │                                          (identity key pair for CEK distribution)
  │
  └─ passkey_secret + server_secret (from server DB, encrypted with org passphrase)
       │
       └─ HKDF(passkey_secret || server_secret) → User Wrapping Key (ephemeral, in memory only)
            │
            └─ Unwraps → CEK (Client Encryption Key — random, same for all team members)
                  │
                  └─ Encrypts/decrypts the SDK-encrypted config values (AES-256-GCM)

Server (master SDK never leaves server)
  │
  └─ sdk_derived = HKDF(sdkMaster, sdkEpoch)
       │            (sdkEpoch = floor(push_time / window_seconds))
       │
       └─ Time-windowed key — encrypts plaintext config values
          (different key every 5 minutes, server re-derives for pull using stored epoch)
```

Each user derives **two secrets** from their passkey via PRF with different salts:
- `passkey_secret` — combined with `server_secret` to create the wrapping key for CEK
- `user_x25519_private` — identity key pair for secure CEK distribution between team members

### Client-Side Secure Storage

The `passkey_secret` is stored in **platform-native secure storage**, not in the token file. The server provides a unique `storageKeyId` per user/org/team combination, which the CLI uses to index into the native storage:

| Platform | Mechanism | Headless? | Persists Reboot? | Protection |
|----------|-----------|-----------|-----------------|------------|
| Linux | Kernel keyring (`keyctl`) | Yes | No (memory) | Kernel-level isolation, per-user, supports timeouts |
| macOS | Keychain (`security`) | Yes | Yes (encrypted) | OS-level encryption, optional Touch ID |
| Windows | DPAPI (`ProtectedData`) | Yes | Yes (encrypted) | Tied to user's Windows login credentials |
| Fallback | Token file (0o600) | Yes | Yes | File permissions only (warning logged) |

```bash
# Linux — store in kernel keyring
keyctl add user "$storageKeyId" "$passkey_secret" @u
keyctl timeout <key-id> 86400   # 24h auto-expiry

# macOS — store in Keychain
security add-generic-password -a "$storageKeyId" -s rdc-config -w "$passkey_secret"

# Windows — encrypt with DPAPI, save to file
powershell -c "[Convert]::ToBase64String(
  [Security.Cryptography.ProtectedData]::Protect(...))"
# Saved to %LOCALAPPDATA%\rediacc\keys\<storageKeyId>.dpapi
```

The `storageKeyId` is generated by the server during setup (e.g., `rdc:org_abc:team_xyz:config_123`) and stored in the token file. The token file becomes a **pointer** to the secret, not the secret itself.

### What Lives Where

| Secret | Location | Protection |
|--------|----------|------------|
| Passkey private key | Passkey provider (YubiKey, iCloud Keychain, 1Password) | Biometric/PIN, synced across devices |
| `passkey_secret` | OS-native secure storage (indexed by `storageKeyId`) | Kernel keyring / Keychain / DPAPI |
| `storageKeyId` | Token file + server DB | Reference only — not a secret |
| `user_x25519_private` | Nowhere — derived on the fly from passkey PRF | Requires passkey + biometric |
| `user_x25519_public` | Server DB (plaintext) | Public key — safe to store |
| `server_secret` | Server DB | Encrypted with org passphrase |
| Org passphrase | Server DB | Encrypted with rotating token |
| CEK | Nowhere — unwrapped on the fly | Wrapped per-user in server DB |
| `wrappedCEK` (per user) | Server DB | `encrypt(HKDF(passkey_secret + server_secret), CEK)` |
| `sdkMaster` | Server DB (per org) | Never transmitted — used only for derivation on server |
| `sdk_derived` | Ephemeral — computed per request | `HKDF(sdkMaster, sdkEpoch)` — time-windowed, sent with every session, pull and version response |
| Config values | Server DB | Triple encrypted: `orgEnc(clientEnc_CEK(serverKeyEnc_SDK(values)))` |
| Rotating token | CLI token file (0o600) | Hashed in server DB, single-use, IP-bound |

### Encryption Layers

Config values have three independent encryption layers:

```
Layer 1 (Inner — SDK):       CLI encrypts plaintext with time-windowed sdk_derived
Layer 2 (Middle — CEK):      CLI encrypts SDK-encrypted values with client-controlled CEK
Layer 3 (Outer — Org Pass):  Server encrypts the already-encrypted blobs before storing

At rest in DB:  orgEnc(clientEnc_CEK(serverKeyEnc_SDK(ssh_keys)))
                orgEnc(clientEnc_CEK(serverKeyEnc_SDK(machines)))
                orgEnc(clientEnc_CEK(serverKeyEnc_SDK(repositories)))
```

The SDK layer uses **time-windowed derived keys**. The master SDK never leaves the server — the client only receives a derived key valid for a specific time window (default: 5 minutes). Each config entry stores the `sdkEpoch` it was encrypted with, so the server can re-derive the correct key on pull.

```
sdk_derived = HKDF(sdkMaster, sdkEpoch)
sdkEpoch = floor(push_timestamp / windowSeconds)

Example (window = 300s / 5 min):
  Push at 15:02 → epoch = floor(unix_ts / 300) = 5913166
  sdk_derived = HKDF(master, "5913166") → "x7y8z9..."

  Pull at 18:30 (different window, hours later):
  Server reads sdkEpoch = 5913166 from stored config
  Re-derives: HKDF(master, "5913166") → "x7y8z9..." (same key)
  Client decrypts successfully
```

**Security properties of each layer:**
- Compromised server code → sees `clientEnc_CEK(serverKeyEnc_SDK(values))` → has `sdkMaster` but CEK blocks access to the SDK layer
- Compromised DB → sees `orgEnc(clientEnc_CEK(serverKeyEnc_SDK(values)))` → three keys needed, has none
- Compromised CEK alone → can remove CEK layer → `serverKeyEnc_SDK(values)` → needs `sdk_derived` from server → server rejects revoked members
- Captured `sdk_derived` → only decrypts configs from that specific time window — future windows use different derived keys
- Compromised passkey alone → no `server_secret` → can't derive CEK
- Compromised token alone → no `passkey_secret` → can't derive CEK
- **Revoked member with CEK** → can't get `sdk_derived` (server rejects) → can't decrypt inner layer
- **Revoked member with CEK + old `sdk_derived`** → only decrypts configs from windows they participated in — not future configs

## Storage Architecture: D1 + R2

Metadata lives in D1 (lightweight, queryable for conflict detection and listing). Encrypted config blobs live in R2 (no size limits, up to 5 TB per object). This avoids D1's 100 KB SQL statement limit for large configs.

### R2 Bucket Structure

One bucket per deployment (`rediacc-configs`, `edge-rediacc-configs`), keyed by team and config:

```
  {teamId | _default}/{configId}/
    v/42-<uuid>.enc                ← current: orgEnc(clientEnc_CEK(sdk_derived(document)))
    v/41-<uuid>.enc                ← archived versions (newest 50 kept)
    v/40-<uuid>.enc
```

Every push writes a key of its own, so a push never overwrites a blob a row points at. The current row and each archive row name their blob key in D1.

### Plaintext envelope (D1 `envelope_json`)

```json
{
  "envelopeVersion": 3,
  "id": "config-id",
  "version": 42,
  "teamId": "team-uuid",
  "sdkEpoch": 5913166,
  "lastModified": "2026-03-19T20:00:00Z",
  "commitments": { "alg": "HMAC-SHA256", "fckSalt": "...", "fields": { "<blinded key>": { "hmac": "...", "kind": "string" } } }
}
```

There is no blob HMAC in v3; the `hmac` column is written as null.

### R2 blob (encrypted document)

```
orgEnc(clientEnc_CEK(serverKeyEnc_SDK({
  "machines": { ... },
  "repositories": { ... },
  "storages": { ... },
  "ssh": { ... }
})))
```

The whole synced document (every key except the device-local pointers, see [What syncs](#what-syncs)) is encrypted together as a single blob. The server decrypts the outer `orgEnc` layer on pull and returns the still-encrypted inner blob to the CLI.

### D1 Metadata (pointers + access control)

D1 stores only lightweight metadata — no encrypted blobs:

```json
{
  "configId": "uuid-v4",
  "version": 42,
  "teamId": "team-uuid",
  "sdkEpoch": 5913166,
  "r2Key": "team_xyz/550e8400-.../v/42-<uuid>.enc",
  "hmac": null,
  "signature": null,
  "lastModified": "2026-03-19T20:00:00Z"
}
```

**D1 handles** (without touching encrypted data):
- Version conflict detection (`version` field)
- Config identity verification (`configId`)
- Team/org access control (`teamId`, `orgId`)
- Listing configs with metadata
- R2 key lookup for blob retrieval

**R2 handles**:
- Encrypted blob storage (no size limits)
- Version history (one object per version)
- Efficient retrieval (single GET per pull)

**Server can** (without decrypting):
- Check version for conflict detection (`push v42` vs stored `v43` → reject)
- Verify config identity via `id`
- Enforce team/org access control
- List configs with metadata

**Server cannot see**:
- Machine IPs, ports, SSH known hosts
- SSH private keys
- Repository credentials
- Storage/S3 credentials
- Network topology

## Flows

### First-Time Setup (Once Per Org)

#### Desktop Mode (has browser)

```
CLI                           Browser                        Server
 │                              │                              │
 ├─ Start local server ────────►│                              │
 │  localhost:PORT              │                              │
 │                              │                              │
 ├─ Open browser ──────────────►│                              │
 │  /config-setup?              │                              │
 │  callback=localhost:PORT     │                              │
 │                              ├─ Passkey auth ──────────────►│
 │                              │  (passkey popup +            │
 │                              │   biometric)                 │
 │                              │                              │
 │                              │  PRF derives:                │
 │                              │  - passkey_secret            │
 │                              │  - user_x25519 key pair      │
 │                              │  (stay in browser,           │
 │                              │   never sent to server)      │
 │                              │                              │
 │                              ├─ user_x25519_public ────────►│
 │                              │  (server stores for          │
 │                              │   future CEK distribution)   │
 │                              │                              │
 │                              │◄──── server_secret ──────────┤
 │                              │      (via E2E tunnel)        │
 │                              │                              │
 │                              │  Browser computes:           │
 │                              │  wrapping_key = HKDF(        │
 │                              │    passkey_secret +           │
 │                              │    server_secret)            │
 │                              │                              │
 │                              │  CEK = random 256 bits       │
 │                              │                              │
 │                              │  wrappedCEK = encrypt(       │
 │                              │    wrapping_key, CEK)        │
 │                              │                              │
 │                              ├──── wrappedCEK ─────────────►│
 │                              │     (server stores it)       │
 │                              │                              │
 │◄─ POST localhost:PORT ───────┤                              │
 │   encrypt(nonce,             │                              │
 │     passkey_secret + token   │                              │
 │     + storageKeyId)          │                              │
 │                              │                              │
 ├─ Store passkey_secret in     │                              │
 │  native secure storage       │                              │
 │  (keyctl/Keychain/DPAPI)     │                              │
 │  indexed by storageKeyId     │                              │
 │                              │                              │
 ├─ Store storageKeyId +        │                              │
 │  serverToken + wrappedCEK    │                              │
 │  in token file (no secrets)  │                              │
 │                              │                              │
 ▼ Done. No password stored. No secrets on disk.               │
```

Server never sees `passkey_secret` — it goes directly from browser to CLI via localhost. The secret is stored in OS-native secure storage, not in the token file.

#### Headless Mode (no browser — e.g., Linode, EC2)

The server acts as a relay but never sees `passkey_secret` thanks to an ephemeral encryption handoff:

```
CLI                           Browser (phone/laptop)          Server
 │                              │                              │
 ├─ Generate ephemeral          │                              │
 │  X25519 key pair             │                              │
 │  (handoff_pub, handoff_priv) │                              │
 │                              │                              │
 ├─ Show URL to user: ─────────────────────────────────────────┤
 │  rediacc.com/device?         │                              │
 │  code=ABCD&key=handoff_pub   │                              │
 │                              │                              │
 │  (user opens URL on          │                              │
 │   phone or laptop)           │                              │
 │                              │                              │
 │                              │  Browser reads handoff_pub   │
 │                              │  from URL query param        │
 │                              │  (NOT from server API)       │
 │                              │                              │
 │                              ├─ Passkey auth ──────────────►│
 │                              │  (passkey on phone)          │
 │                              │                              │
 │                              │  PRF derives:                │
 │                              │  - passkey_secret            │
 │                              │  - user_x25519 key pair      │
 │                              │                              │
 │                              │  Encrypt with handoff_pub:   │
 │                              │  blob = X25519_encrypt(      │
 │                              │    handoff_pub,              │
 │                              │    passkey_secret + token)   │
 │                              │                              │
 │                              ├──── encrypted blob ─────────►│
 │                              │     (opaque to server)       │
 │                              │                              │
 │  CLI polls...                │                              │
 │◄───────────────── encrypted blob (relayed, can't read) ─────┤
 │                              │                              │
 ├─ Decrypt with handoff_priv   │                              │
 │  → passkey_secret + token    │                              │
 │    + storageKeyId            │                              │
 ├─ Discard handoff_priv        │                              │
 ├─ Store passkey_secret in     │                              │
 │  native secure storage       │                              │
 │  indexed by storageKeyId     │                              │
 ├─ Store storageKeyId +        │                              │
 │  serverToken + wrappedCEK    │                              │
 │  in token file (no secrets)  │                              │
 │                              │                              │
 ▼ Done. Server never saw passkey_secret. No secrets on disk.  │
```

In both flows the ephemeral X25519 key pair means the server only relays an encrypted blob it cannot decrypt, as long as the page code it serves is unmodified.

**Headless security note**: The browser JS reads `handoff_pub` from the **URL query parameter**, not from any server API. This prevents a rogue server from substituting its own public key. The config setup page must be served as a static page with Content Security Policy (CSP) and Subresource Integrity (SRI) to prevent script injection.

### Adding a Team Member

Adding a member is an elevated operation requiring 2FA. The CEK is distributed via X25519 key exchange between the admin's browser and the new member — the server never sees the CEK.

```
Admin Browser                  Server                    New Member Browser
 │                              │                              │
 │                              │  New member registers        │
 │                              │◄─ passkey + PRF ─────────────┤
 │                              │                              │
 │                              │  Server stores               │
 │                              │  new member's                │
 │                              │  user_x25519_public          │
 │                              │                              │
 │  Admin initiates             │                              │
 │  "add member" (elevated)     │                              │
 │                              │                              │
 ├─ Admin passkey auth ────────►│                              │
 │  PRF → passkey_secret        │                              │
 │                              │                              │
 │◄─ server_secret +            │                              │
 │   admin's wrappedCEK +       │                              │
 │   new member's               │                              │
 │   user_x25519_public ────────┤                              │
 │                              │                              │
 │  Admin browser:              │                              │
 │  1. Derive wrapping_key      │                              │
 │  2. Unwrap CEK               │                              │
 │  3. Encrypt CEK with         │                              │
 │     member's x25519_public   │                              │
 │                              │                              │
 ├─ encrypted CEK handoff ─────►│                              │
 │   (opaque to server)         │  Server stores pending       │
 │                              │  handoff blob                │
 │                              │                              │
 │                              │  New member accepts          │
 │                              │  invitation (elevated)       │
 │                              │                              │
 │                              │◄─ Passkey auth ──────────────┤
 │                              │                              │
 │                              ├─ Pending handoff blob ──────►│
 │                              │  + server_secret             │
 │                              │                              │
 │                              │  New member browser:         │
 │                              │  1. Derive x25519_private    │
 │                              │     from passkey PRF         │
 │                              │  2. Decrypt CEK from         │
 │                              │     handoff blob             │
 │                              │  3. Derive wrapping_key      │
 │                              │  4. Wrap CEK →               │
 │                              │     wrappedCEK_member        │
 │                              │                              │
 │                              │◄─ wrappedCEK_member ─────────┤
 │                              │   (server stores it)         │
 │                              │                              │
 │                              │  Delete pending handoff      │
 │                              │                              │
 ▼                              ▼  Done. Server never saw CEK. ▼
```

### Removing a Team Member

```
Admin triggers "remove member" (elevated + 2FA)
  → Server deletes member's wrappedCEK
  → Server revokes member's rotating tokens
  → Member can no longer get server_secret → can't derive wrapping key → can't unwrap CEK
```

Note: The removed member may have local copies of previously-pulled configs. This is inherent to any system that gives users access to data. Token revocation prevents future access.

### Push Config

A push is **2 requests** under one token lease: `/session` for the current epoch's key, then the PUT, which sends the token `/session` rotated to.

```
CLI                                          Server
 │                                             │
 ├─ POST /configs/session { serverToken } ────►│
 │                                             ├─ Validate token, check active membership
 │                                             ├─ Derive: sdk_derived = HKDF(sdkMaster,
 │                                             │    floor(now / windowSeconds))
 │◄──── { newServerToken, server_secret,       ┤
 │        sdk_derived, sdkEpoch }              │
 │                                             │
 ├─ Read slot secret from native storage       │
 ├─ Derive wrapping_key = HKDF(                │
 │    slot_secret + server_secret)             │
 ├─ Unwrap CEK from wrappedCEK                 │
 │                                             │
 ├─ Commit fields (blinded keys, fresh salt),  │
 │  tombstone every committed path dropped     │
 ├─ Encrypt: plaintext → sdk_derived → CEK,    │
 │  both layers under the envelope v3 AAD      │
 │                                             │
 ├─ PUT /configs/:id { newServerToken, ───────►│
 │    version, encryptedBlob, sdkEpoch,        │
 │    envelope }                               │
 │                                             ├─ Validate token, verify IP binding
 │                                             ├─ Refuse envelope != v3, envelope/body
 │                                             │    mismatch, epoch outside ±1 window
 │                                             ├─ Check version > stored
 │                                             ├─ Check every stored key is kept or
 │                                             │    tombstoned with the stored commitment
 │                                             ├─ Encrypt with org passphrase (Layer 3),
 │                                             │    write a new blob key
 │                                             ├─ Compare-and-swap the row on the
 │                                             │    version read; archive the old one
 │◄──── { newServerToken, version } ───────────┤
 │                                             │
 ├─ Record high-water mark in token file       │
 ▼ Done                                        │
```

### Pull Config

A pull is **1 request**: the response carries `server_secret` and the key of the epoch the config was pushed in.

```
CLI                                          Server
 │                                             │
 ├─ GET /configs/:id { serverToken } ─────────►│
 │                                             ├─ Validate token, verify IP binding
 │                                             ├─ Check active membership
 │                                             ├─ Decrypt org passphrase with token
 │                                             ├─ Decrypt Layer 3 (org passphrase)
 │                                             ├─ Derive: sdk_derived = HKDF(sdkMaster,
 │                                             │    sdkEpoch)  ← epoch from push time
 │                                             ├─ Generate new rotating token
 │◄──── { newServerToken, server_secret,       ┤
 │        sdk_derived, configData, envelope }  │
 │        (E2E tunnel)                         │
 │                                             │
 ├─ Derive wrapping_key, unwrap CEK            │
 ├─ Rebuild the AAD from the local `remote`    │
 │  pointer; decrypt CEK layer → SDK layer     │
 │  (a blob sealed for anything else fails)    │
 ├─ Refuse version < high-water mark           │
 ├─ Save to the encrypted local cache          │
 ├─ Update token file (token, high-water)      │
 ▼ Done                                        │
```

### Version Conflict Resolution

Server handles conflicts using plaintext envelope fields — no decryption needed:

```
CLI pushes version 42:
  Server stored version is 41 → 42 > 41 → Accept, store new version
  Server stored version is 43 → 42 < 43 → Reject: "Version conflict, pull first"
  Server stored id differs    → Reject: "Config identity mismatch"
```

The check and the write are one compare-and-swap (`UPDATE ... WHERE id = ? AND version = ?`), so two pushes racing from the same base cannot both land; the loser gets the conflict, and the CLI replays its edit on the fresh copy. `rdc config remote restore <version>` goes through the same path: it republishes an old version's content as a new version, never as a lower one.

## Token Rotation

Tokens are single-use. Each API call returns a new token:

```
Request 1: serverToken_1 → server validates → returns serverToken_2
Request 2: serverToken_2 → server validates → returns serverToken_3
...
```

Each token:
- Is a fresh random value
- Stored as a **hash** in the DB (not plaintext)
- Encrypts the org passphrase (so it can decrypt on next use)
- Has a grace window (3 uses) for concurrent/retry scenarios
- Expires 7 days after the request that minted it; the CLI then renews it through its login token (`POST /configs/device-token/refresh`), and the same renewal covers a token that ran out of uses or is bound to an address the machine left
- **Bound to the client IP on first use** — requests from a different IP are rejected and trigger an alert

**Stolen token analysis:**
- Before rotation: attacker must use from same IP as legitimate user (IP binding), gets at most one use
- After rotation: attacker's token is rejected, can't derive any keys
- Different IP: immediately rejected, user alerted

## Authentication Requirements

### Mandatory 2FA

Config storage requires 2FA to be enabled. No 2FA = no config sync.

**Operations requiring 2FA + elevated session:**
- First-time config store setup
- Adding/removing team members
- Key rotation (CEK re-generation)
- Config store deletion

**Operations requiring valid rotating token only:**
- Push/pull configs (frequent, must be frictionless)

### Passkey with PRF (Required)

Passkeys provide:
- Biometric authentication (no password to type)
- PRF-derived `passkey_secret` for split-key CEK
- PRF-derived `user_x25519_private` for secure CEK distribution between members
- Phishing resistance (domain-bound credentials)
- Cross-device sync via passkey providers (iCloud Keychain, 1Password, etc.)

Config storage requires a passkey provider that supports the PRF extension. No fallback — this is a hard requirement. Supported providers include FIDO2 security keys (e.g. YubiKey), iCloud Keychain, Google Password Manager, 1Password, and Dashlane. Note that Bitwarden and Windows Hello do NOT support PRF.

## Recovery

| Scenario | Recovery Path |
|----------|---------------|
| Lost device, passkey synced (iCloud Keychain/1Password) | New device → passkey provider syncs passkey → PRF derives same `passkey_secret` and `x25519` key pair → unwrap CEK → done |
| Team member loses passkey | Another admin re-does the "add member" flow: unwraps CEK in their browser, encrypts with new member's new X25519 public key, new member accepts and wraps CEK |
| Solo user loses passkey completely | Generate new passkey → new CEK → re-create configs from scratch (old configs unrecoverable by design) |
| Server DB lost | Restore from backup. Without backup, `server_secret` is gone → CEK unrecoverable |

**Recommendation**: Require at least 2 team admins for config storage. This provides built-in key recovery — if one admin loses their passkey, the other can re-distribute the CEK.

## Security Properties

| Property | How It's Achieved |
|----------|-------------------|
| Confidential against storage compromise and a passive operator | Client-side encryption with the CEK; the server never holds the CEK or a slot secret (full claim and limits: [Security model](#security-model)) |
| Not confidential against malicious portal code | The server serves the portal JavaScript that unwraps the CEK; a modified bundle can read it |
| Member addition and headless setup | CEK and slot secret handed off under X25519 between devices; the server relays opaque blobs |
| Data at rest encrypted | Triple encryption: `orgEnc(clientEnc_CEK(serverKeyEnc_SDK(values)))`; only the CEK layer is out of the server's reach |
| Revocation | Removing a member deletes their slots and config tokens, so the next request is refused; content already pulled stays on their device |
| Encryption key not stored anywhere | CEK unwrapped on the fly from `wrappedCEK` using split-key derived wrapping key |
| Stolen token → limited damage | Rotating tokens (3 uses), 7-day lifetime, IP-bound on first use |
| Stolen passkey alone → no access | Need `server_secret` too (split-key) |
| Stolen DB → no access | CEK wrapped per slot; a master password slot is open to offline guessing by whoever holds the DB |
| Binding and tamper detection | Envelope v3: both client layers authenticate (store, config, team, version, epoch, commitments digest) as AES-GCM AAD |
| Rollback | CLI refuses a version below its high-water mark; a device that never saw a newer version is not protected |
| Metadata | Commitment keys blinded per config; the server still sees ids, versions, epochs, sizes, field counts and value kinds |
| Deletion | A committed path is removed only against a tombstone equal to the stored commitment |
| Phishing resistance | Passkeys are domain-bound |
| Audit trail | Operations logged in event_log, including `config.version.read` and `config.version.restore` |
| IP binding | Rotating tokens bound to client IP on first use — different IP rejected |

## Hosting Compatibility

The account server runs on both Cloudflare Workers (D1 + R2) and Node.js standalone (BetterSQLite3 + local filesystem). Both use Hono as the HTTP framework and Web Crypto API for cryptography.

| Concern | Cloudflare Workers | Node.js Standalone |
|---------|-------------------|-------------------|
| Metadata DB | D1 (serverless SQLite) | BetterSQLite3 (local file) |
| Blob storage | R2 (S3-compatible, 5 TB per object) | RustFS (S3-compatible, self-hosted) |
| Transactions | `batch()` only (no BEGIN TRANSACTION) | Full transaction support |
| Crypto API | Web Crypto (native) — AES-GCM, HKDF, Ed25519, X25519 all supported | Web Crypto (via `crypto.subtle`) |
| Token rotation atomicity | Two-phase write: create new alongside old, then delete old | Single transaction |

**D1 limits verified against design:**
- Max SQL statement: 100 KB → no concern (encrypted blobs in R2, D1 only stores metadata)
- Max DB size: 10 GB → sufficient for metadata (version retention policy for old versions)
- Single-threaded queries → acceptable for config sync (infrequent operations)

**R2 limits:**
- Max object size: 5 TB → more than sufficient
- No per-bucket object count limit → version history is fine

For D1's `batch()` limitation on token rotation: write new token + new wrapped passphrase first, then delete old. If anything fails mid-way, old token still works. Stale tokens cleaned up periodically.

## Database Schema (Account Server)

New tables in `private/account/drizzle/`:

```sql
-- Per-org config encryption setup
CREATE TABLE config_stores (
  id TEXT PRIMARY KEY,
  orgId TEXT NOT NULL REFERENCES organizations(id),
  serverSecret TEXT NOT NULL,          -- encrypt(orgPassphrase, random_256_bit)
  sdkMaster TEXT NOT NULL,             -- Master SDK (never transmitted, used for HKDF derivation only)
  sdkWindowSeconds INTEGER NOT NULL DEFAULT 300, -- time window for key derivation (5 min default)
  createdAt INTEGER NOT NULL,
  updatedAt INTEGER NOT NULL
);

-- Per-user identity keys and storage references
CREATE TABLE config_user_identities (
  id TEXT PRIMARY KEY,
  configStoreId TEXT NOT NULL REFERENCES config_stores(id),
  userId TEXT NOT NULL REFERENCES users(id),
  x25519PublicKey TEXT NOT NULL,        -- derived from passkey PRF, stored plaintext (public key)
  storageKeyId TEXT NOT NULL,           -- unique ID for client-side native secure storage lookup
  createdAt INTEGER NOT NULL,
  UNIQUE(configStoreId, userId)
);

-- Per-user wrapped CEK (one row per user per config store)
CREATE TABLE config_user_keys (
  id TEXT PRIMARY KEY,
  configStoreId TEXT NOT NULL REFERENCES config_stores(id),
  userId TEXT NOT NULL REFERENCES users(id),
  wrappedCEK TEXT NOT NULL,            -- encrypt(HKDF(passkey_secret + server_secret), CEK)
  createdAt INTEGER NOT NULL,
  UNIQUE(configStoreId, userId)
);

-- Pending CEK handoffs for new members (admin encrypts CEK for new member's x25519 public key)
CREATE TABLE config_cek_handoffs (
  id TEXT PRIMARY KEY,
  configStoreId TEXT NOT NULL REFERENCES config_stores(id),
  targetUserId TEXT NOT NULL REFERENCES users(id),
  encryptedCEK TEXT NOT NULL,          -- X25519_encrypt(member_x25519_public, CEK) — opaque to server
  createdByUserId TEXT NOT NULL REFERENCES users(id),
  createdAt INTEGER NOT NULL,
  expiresAt INTEGER NOT NULL,          -- handoffs expire if not accepted
  UNIQUE(configStoreId, targetUserId)
);

-- Stored configs (D1 metadata only — encrypted blobs in R2)
CREATE TABLE config_entries (
  id TEXT PRIMARY KEY,
  configStoreId TEXT NOT NULL REFERENCES config_stores(id),
  teamId TEXT REFERENCES teams(id),    -- team-scoped config
  configId TEXT NOT NULL,              -- the config's own UUID (plaintext)
  version INTEGER NOT NULL,            -- plaintext for conflict detection
  lastModified INTEGER NOT NULL,

  r2Key TEXT NOT NULL,                 -- R2 object key: "{teamId}/{configId}/current.enc"
  sdkEpoch INTEGER NOT NULL,           -- floor(push_time / windowSeconds) — for SDK re-derivation on pull
  hmac TEXT,                           -- envelope v2 blob HMAC; null for every v3 write
  signature TEXT,                      -- unused, always null

  UNIQUE(configStoreId, teamId, configId)
);

-- Version history (D1 metadata — snapshots in R2 at versions/{version}.enc)
CREATE TABLE config_versions (
  id TEXT PRIMARY KEY,
  configEntryId TEXT NOT NULL REFERENCES config_entries(id),
  version INTEGER NOT NULL,
  r2Key TEXT NOT NULL,                  -- R2 object key: "{teamId}/{configId}/versions/{version}.enc"
  sdkEpoch INTEGER NOT NULL,            -- epoch at time of this version's push
  createdAt INTEGER NOT NULL,
  createdByUserId TEXT REFERENCES users(id)
);

-- Rotating tokens for config operations
CREATE TABLE config_tokens (
  id TEXT PRIMARY KEY,
  userId TEXT NOT NULL REFERENCES users(id),
  configStoreId TEXT NOT NULL REFERENCES config_stores(id),
  tokenHash TEXT NOT NULL UNIQUE,       -- SHA-256 hash (never store plaintext)
  encryptedOrgPassphrase TEXT NOT NULL, -- encrypt(token, orgPassphrase)
  boundIp TEXT,                         -- IP bound on first use, enforced on subsequent uses
  usageCount INTEGER DEFAULT 0,         -- max 3 uses for concurrency
  expiresAt INTEGER NOT NULL,           -- 7 days from the request that minted it
  createdAt INTEGER NOT NULL
);
```

## API Endpoints (Account Server)

New routes under `/account/api/v1/configs/`:

Responses only include what's needed for that operation. Crypto keys (`server_secret`, `sdk`) are only returned for encryption/decryption operations — not for listing or management calls.

```
SETUP
  POST   /configs/setup                  Setup config store for org (elevated + 2FA)

CRYPTO OPERATIONS (return server_secret + sdk_derived + newServerToken)
  POST   /configs/session                Session: derive sdk for current epoch (first request of a push)
  GET    /configs/:id                     Pull config: derive sdk for config's stored epoch (+ configData)
  PUT    /configs/:id                     Push config: v3 only, epoch within ±1 window, compare-and-swap on version
  GET    /configs/:id/versions/:v         Read one archived version (restore reads it, then pushes it as a new version)

NON-CRYPTO OPERATIONS (return newServerToken only)
  GET    /configs                         List config entries (metadata only)
  DELETE /configs/:id                     Delete config entry + R2 blobs (elevated)
  DELETE /configs/store                   Delete entire config store for org (org owner + elevated + 2FA)
  GET    /configs/:id/versions            List version history
  POST   /configs/device-token/refresh   Mint a fresh device config token (login api token, scope config:enroll)

MEMBER MANAGEMENT (return newServerToken only)
  POST   /configs/members                 Add member: X25519 identity + encrypted CEK handoff (elevated + 2FA)
  POST   /configs/members/accept          Accept invitation: decrypt CEK handoff, store wrappedCEK (elevated)
  DELETE /configs/members/:userId         Remove member: delete wrappedCEK + revoke tokens + stop serving SDK (elevated)
  GET    /configs/members                 List members with key status
```

## Audit Logging

All config operations are logged to the existing `event_log` table with a hash chain for tamper detection. Each log entry includes a hash of itself + the previous entry's hash — any deletion or modification breaks the chain.

### Logged Events

| Event | Logged Data | Severity |
|-------|-------------|----------|
| `config.push` | userId, configId, version, IP, timestamp, teamId | info |
| `config.pull` | userId, configId, version, IP, timestamp, teamId | info |
| `config.delete` | userId, configId, IP, timestamp, teamId | warning |
| `config.version.read` | userId, configId, version, teamId | info |
| `config.version.restore` | userId, configId, fromVersion, version, teamId | warning |
| `config.store.setup` | userId, orgId, timestamp | info |
| `config.store.delete` | userId, orgId, timestamp | critical |
| `config.member.added` | targetUserId, addedByUserId, teamId, timestamp | info |
| `config.member.accepted` | userId, teamId, timestamp | info |
| `config.member.removed` | targetUserId, removedByUserId, teamId, timestamp | warning |
| `config.auth.token_rotated` | userId, IP, timestamp | debug |
| `config.auth.revoked_access` | userId, IP, timestamp, reason | warning |
| `config.auth.ip_mismatch` | userId, expectedIP, actualIP, timestamp | critical |
| `config.auth.sdk_denied` | userId, IP, timestamp (revoked member tried to get sdk_derived) | critical |
| `config.hmac.failed` | userId, configId, timestamp (tamper detection triggered on pull) | critical |

### Critical Event Alerts

Events with `critical` severity trigger immediate notifications to org admins:

- **IP mismatch**: Someone used a token from an unexpected IP — possible token theft
- **SDK denied**: A revoked member attempted to access config decryption keys
- **HMAC failed**: Config integrity check failed — possible data corruption or tampering
- **Store deleted**: Entire config store was destroyed

These notifications are sent via the existing account server notification system (email).

## Config and Org Deletion

### Config Entry Deletion

Deleting a single config entry (elevated operation):

```
CLI                                          Server
 │                                             │
 ├─ DELETE /configs/:id { serverToken } ──────►│
 │                                             ├─ Validate token, verify elevated session
 │                                             ├─ Read r2Key from D1
 │                                             ├─ Delete R2: current.enc
 │                                             ├─ Delete R2: all versions/*.enc
 │                                             ├─ Delete R2: meta.json
 │                                             ├─ Delete D1: config_versions rows
 │                                             ├─ Delete D1: config_entries row
 │                                             ├─ Log: config.delete (warning)
 │◄──── { success, newServerToken } ───────────┤
```

All R2 objects under `{teamId}/{configId}/` are removed. D1 metadata is deleted. Hard delete — no soft-delete / trash bin (blobs are triple-encrypted, no recovery value without keys).

### Config Store Deletion (Org-Level)

Destroying the entire config store for an org (highly elevated — requires org owner + 2FA):

```
CLI                                          Server
 │                                             │
 ├─ DELETE /configs/store { serverToken } ────►│
 │                                             ├─ Validate token, verify org owner + elevated
 │                                             ├─ Delete ALL R2 objects in bucket
 │                                             ├─ Delete D1: all config_versions
 │                                             ├─ Delete D1: all config_entries
 │                                             ├─ Delete D1: all config_cek_handoffs
 │                                             ├─ Delete D1: all config_user_keys
 │                                             ├─ Delete D1: all config_user_identities
 │                                             ├─ Delete D1: all config_tokens
 │                                             ├─ Delete D1: config_stores row
 │                                             ├─ sdkMaster destroyed
 │                                             ├─ serverSecret destroyed
 │                                             ├─ Log: config.store.delete (critical)
 │                                             ├─ Notify all org admins
 │◄──── { success } ──────────────────────────┤
```

After store deletion:
- All encrypted blobs are gone (R2 objects deleted)
- All key material destroyed (sdkMaster, serverSecret, all wrappedCEKs)
- All team members' local token files become invalid (tokens revoked)
- Local config files on members' machines are unaffected (they still have plaintext copies)

### Member Removal Cleanup

When a member is removed, their key material is cleaned up:

```
Server performs:
  1. Delete config_user_keys row (wrappedCEK)
  2. Delete config_user_identities row (x25519 public key)
  3. Delete any pending config_cek_handoffs for this user
  4. Revoke all config_tokens for this user
  5. Log: config.member.removed (warning)
  6. Future sdk_derived requests from this user → rejected + logged as critical
```

The next request from the removed member is refused. What they already pulled stays on their device; a CEK they kept is neutralized for later blobs only by a CEK rotation.

## CLI Integration

New store adapter in `packages/cli/src/stores/`:

```
packages/cli/src/stores/rediacc-store-adapter.ts
```

Implements the same `StoreAdapter` interface as S3, Bitwarden, Git, etc. Registered as type `"rediacc"` in the store registry.

## Access Interfaces

### Web Portal (Setup + Management)
- `/account/config-setup` — Initial store setup (passkey + PRF ceremony)
- `/account/config-storage` — Dashboard (status, activity, passkey info)
- `/account/config-storage/members` — Member management (add via CLI, remove via portal)
- `/account/admin/config-storage` — Admin overview

### CLI (Daily Operations)
Shipped under `rdc config remote`:
- `rdc config remote enable`: link this config to the store (`--headless` for a device-code flow)
- `rdc config remote disable`: disconnect and write the config back to disk
- `rdc config remote refresh`: download and decrypt the latest config
- `rdc config remote status`: show store info
- `rdc config rotate-cek`: rotate the client-controlled encryption key

Uploads are implicit: once remote is enabled, config writes are encrypted and pushed to the store, so there is no separate push command.

These require passkey_secret in OS keyring (set during web portal setup).

### API (SDK/Token Auth)
Config CRUD operations use rotating X-Config-Token header. Portal operations use session cookies (+ 2FA/elevated for mutations).

### Token File

```json
{
  "token": "rdt_xxx",
  "serverUrl": "https://www.rediacc.com",
  "subscriptionId": "sub_xxx",
  "orgId": "org_xxx",
  "teamId": "team_xxx",
  "configStore": {
    "serverToken": "rdt_config_xxx",
    "storageKeyId": "rdc:org_abc:team_xyz:config_123",
    "wrappedCEK": "base64(...)"
  }
}
```

The token file contains only **references and wrapped keys** — no plaintext secrets. The `passkey_secret` lives in platform-native secure storage indexed by `storageKeyId`. If native secure storage is unavailable (rare), the CLI falls back to storing `passkey_secret` in the token file with a warning.

## Config Setup Portal Security

The browser page used for config setup (`/config-setup` and `/device` endpoints) must be a **minimal static page** with:

- **Content Security Policy (CSP)**: strict, no inline scripts, no eval
- **Subresource Integrity (SRI)**: all loaded scripts verified by hash
- **No server-side rendering**: pure static HTML/JS
- **Auditable source**: users can view-source to verify the page reads `handoff_pub` from URL params (not from server API)

This prevents a rogue server from substituting the handoff public key in headless mode.

## Threat Analysis

| Attack | Result |
|--------|--------|
| DB dump stolen | D1 holds `sdkMaster` and `serverSecret` in the clear and the org passphrase under a server key; the CEK layer still needs a slot secret. A master password slot can be guessed offline from that data |
| Server memory inspected during request | Sees `clientEnc_CEK(serverKeyEnc_SDK(values))` — has SDK but CEK blocks access |
| Removed member with CEK | Server access ends at removal (slots and config tokens deleted). A kept CEK plus a blob obtained elsewhere still needs that blob's `sdk_derived`; a CEK rotation closes the risk for later blobs |
| Removed member with CEK + captured `sdk_derived` | Only decrypts configs from that specific time window — future configs use different derived keys they never received |
| Token file stolen | Attacker gets `storageKeyId` (reference) + `serverToken` (one-use) + `wrappedCEK` — but no `passkey_secret` (in native secure storage, not in file). Can't derive CEK. |
| Token file + native storage compromised, same IP | Attacker has everything for one use (token rotates), then locked out |
| Token file + native storage compromised, different IP | Immediately rejected (IP binding), user alerted |
| Passkey compromised alone | No `server_secret` → can't derive wrapping key → can't unwrap CEK |
| Rogue server code deployed | Can strip layers 3 and 1 but not the CEK layer of CLI traffic. NOT protected: it can serve portal JavaScript that reads the CEK in the browser, withhold newer versions from a device that never saw them, and deny service |
| Server swaps or rolls back a blob | Envelope v3 AAD refuses a blob sealed for another store, config, team, version or epoch; the CLI refuses a version below its high-water mark |
| Rogue server substitutes handoff key | Browser reads key from URL param, not server API; a server that also serves modified page code can defeat this |
| E2E tunnel MITM | X25519 ECDH — requires server's private key to intercept |
| Former employee | Token revoked, wrappedCEK deleted → no `server_secret` access → can't derive CEK |
| Brute force attack | Passkey (PRF) and recovery code (160 bits) slots are not guessable; a master password slot is, offline, by anyone holding the server's data (PBKDF2-SHA256, 600,000 iterations) |
| Member addition eavesdropping | CEK encrypted with new member's X25519 public key — server relays opaque blob |

## Accepted Risks

| Risk | Rationale |
|------|-----------|
| `passkey_secret` is static | Stored in native secure storage (not token file). Mitigated by rotating `serverToken` (limits damage window) and IP binding. On systems without native storage (fallback to token file), file permissions (0o600) + warning logged. |
| All config versions decryptable with same CEK | CEK compromise = full exposure by design. Rotate CEK if compromise suspected (re-encrypt all configs, re-distribute to members). |
| `sdkMaster` rotation requires admin participation | Server can't rotate `sdkMaster` alone — the SDK layer is inside the CEK layer. An admin must pull configs (decrypt all 3 layers), server generates new `sdkMaster`, admin re-encrypts and pushes. Only needed if `sdkMaster` itself is compromised — for removed members, simply stop serving `sdk_derived` (no rotation needed). Time-windowed derivation limits captured key exposure to specific windows. |
| The server serves the portal code | A server that ships modified JavaScript can read the CEK in the browser. Out of scope of the claim; closing it needs code the server does not serve (a signed extension or a native client). |
| A device that never saw a newer version can be served an old one | The high-water mark only protects versions a device has seen. Freshness against a malicious server needs an external witness. |
| A master password slot is guessable offline | The server holds its KDF parameters, wrapped CEK and `serverSecret`. PBKDF2-SHA256 at 600,000 iterations slows guessing; passkey or recovery code slots, or the require-passkey policy, avoid it. |
| Metadata is visible | Config ids, teams, versions, epochs, blob sizes, field counts and value kinds stay in the plaintext envelope; names are blinded. |

## Implementation Order

1. **Account server**: D1 schema + R2 bucket setup + config CRUD endpoints + token rotation + IP binding
2. **Account server**: Passkey registration with PRF extension support + X25519 identity key storage + `storageKeyId` generation
3. **Account server**: CEK handoff endpoints (admin encrypts for member's X25519 key, member accepts)
4. **Account server**: Static config setup page with CSP + SRI
5. **CLI**: Platform-native secure storage abstraction (`keyctl` / Keychain / DPAPI / file fallback)
6. **CLI**: `rediacc-store-adapter.ts` implementing `StoreAdapter` interface
7. **CLI**: Browser-based setup flow (local loopback for passkey_secret handoff, store in native storage by `storageKeyId`)
8. **CLI**: Device code flow with ephemeral X25519 handoff (headless mode)
9. **CLI**: Selective encryption (encrypt values, keep version/id plaintext)
10. **E2E tests**: Full push/pull/sync cycle + token rotation + member add/remove + headless setup + native storage on all 3 platforms

## FAQ

### Why three encryption layers instead of two?

Two layers (client CEK + server org passphrase) protect against most threats, but leave a gap: a revoked member who already has the CEK can decrypt any previously-downloaded configs indefinitely. The third layer (SDK) adds a **live check** requirement: every pull and push fetches the epoch key from the server with a valid config token, and the server deletes a removed member's tokens. Layer 1 does not stop the server, which holds `sdkMaster`. Three layers, three independent revocation points:

- **Outer (org passphrase)**: Revoked by token rotation
- **Middle (CEK)**: Revoked by CEK rotation (requires admin, heavy operation)
- **Inner (SDK)**: Revoked instantly by server (stop serving SDK to the user)

### Why is the SDK inside the CEK layer (not outside)?

Layer order: `orgEnc(clientEnc_CEK(serverKeyEnc_SDK(plaintext)))`. The CEK layer wraps the SDK layer. This means the server — which holds the SDK — still can't decrypt configs because the CEK layer blocks access. If the SDK were outside the CEK layer, the server could strip the SDK layer and expose `clientEnc(plaintext)`, reducing the security model. With SDK inside CEK, the server
has the innermost key but can't reach it through the middle layer it doesn't control.

### How does SDK revocation work for removed members?

The server stops deriving `sdk_derived` for that user. No cryptographic rotation needed.

1. Admin removes the member → server deletes their slots and config tokens
2. The member's next request → refused; no `sdk_derived` is served
3. Member is stuck with `serverKeyEnc_SDK(values)` they can't decrypt

Even if the member saved a previously-received `sdk_derived`, it only decrypts configs from that specific time window (e.g., the 5-minute window it was derived for). Configs pushed after their removal use a new epoch → new derived key → inaccessible to the removed member.

This is much lighter than CEK or `sdkMaster` rotation (which require re-encrypting all configs).

### Can the server rotate the `sdkMaster` without admin help?

No. The SDK layer is inside the CEK layer: `clientEnc_CEK(serverKeyEnc_SDK(plaintext))`. To re-encrypt with a new `sdkMaster`, someone must first remove the CEK layer, which requires the CEK — which the server doesn't have. An admin must pull all configs (decrypt all 3 layers), the server generates a new `sdkMaster`, the admin re-encrypts and pushes. This is a heavy operation
reserved for `sdkMaster` compromise scenarios, not for routine member removal. With time-windowed derivation, even a compromised `sdk_derived` only exposes configs from one time window.

### Does the SDK add extra API calls?

Minimal impact. Only crypto operations (session, pull, push) return `{ newServerToken, server_secret, sdk_derived }` — non-crypto operations (list, delete, members) only return `{ newServerToken }` to avoid sending unnecessary key material. In the typical pull → edit → push workflow, the pull provides the `sdk_derived` and the push uses the cached copy. The only extra call is a
session bootstrap when the 30-second cache expires and the CLI needs to push without a prior pull. In practice, most operations are 1 API call.

### Why is the SDK time-windowed instead of a fixed key?

A fixed SDK, once captured, decrypts ALL configs forever. A time-windowed `sdk_derived` only decrypts configs from its specific time window (default: 5 minutes). The master SDK (`sdkMaster`) never leaves the server — the client only receives derived keys:

```
sdk_derived = HKDF(sdkMaster, floor(timestamp / 300))
```

Same master + same time window = same derived key (deterministic). Different window = completely different key. The server stores the `sdkEpoch` (an integer) with each config entry, so it can re-derive the correct key on pull — even hours or days later.

If a removed member saved an `sdk_derived`, they can only decrypt configs from that 5-minute window. All configs pushed after their removal use different derived keys they never received.

### Does time-windowed SDK affect concurrent team work?

No. Team members working within the same time window get the same `sdk_derived` — all operations within the same 5-minute window use the same derived key. The epoch is stored **per config entry** (when it was pushed), not per user or per pull. So:

- Alice pushes at 15:02, Bob pulls at 15:04 → same epoch → same `sdk_derived` → works
- Carol pushes at 15:08 → new epoch → new `sdk_derived` → stored with the config
- Alice pulls at 18:30 → server reads the stored epoch → re-derives the correct key → works

Version conflicts are handled separately by the plaintext `version` field — completely independent of the SDK mechanism.

### Why split storage between D1 and R2?

Cloudflare D1 has a 100 KB limit per SQL statement. Encrypted configs (especially teams with many machines and SSH known_hosts) can easily exceed this. R2 has no practical size limit (5 TB per object). So:

- **D1**: Lightweight metadata — version, sdkEpoch, R2 key pointer, hmac, signature, team/org references. Used for conflict detection, listing, and access control without touching encrypted data.
- **R2**: Encrypted blobs — the actual triple-encrypted config data. One object per config version.

For Node.js standalone deployments, encrypted blobs are stored in RustFS (S3-compatible, self-hosted). Both R2 and RustFS use the S3 API, so the same code path works for both — only the endpoint and credentials differ.

### Why not just encrypt the entire config file as one blob?

The config is stored as one encrypted blob in R2 (all sections together). But the **metadata envelope** (version, id, sdkEpoch, hmac) is stored separately in D1 as plaintext. This lets the server do operational tasks (conflict detection, listing, access control) on the plaintext envelope without decrypting anything. If everything were a single opaque blob including the version
number, every conflict check would require a full decryption round trip.

### Why do we need two encryption layers (client + server)?

Each layer protects against a different threat:
- **Client-side (CEK)**: Protects against a rogue server operator or compromised server code. Even during request processing, the server only sees `clientEnc(values)` — still encrypted.
- **Server-side (org passphrase)**: Protects against database theft. A DB dump yields `orgEnc(clientEnc(values))` — doubly useless without both keys.

If we only had server-side encryption, a rogue operator who modifies server code could log plaintext configs. If we only had client-side encryption, a DB breach would expose client-encrypted blobs that might be vulnerable to future attacks on the client-side key.

### Why split the CEK derivation between client and server?

Neither party alone can derive the encryption key:
- **Rediacc (server)** has `server_secret` but not `passkey_secret` → can't derive CEK
- **Stolen passkey** has `passkey_secret` but not `server_secret` → can't derive CEK
- **Stolen token file** has `storageKeyId` and `serverToken` but `passkey_secret` is in native secure storage → can't derive CEK

An attacker must compromise multiple independent systems simultaneously, and the rotating token limits the window to act.

### Why passkeys instead of passwords?

Passwords are reusable — the same password creates unlimited tokens and sessions. A stolen password gives permanent access until changed. Passkeys eliminate this:
- **Biometric-gated**: Requires fingerprint/face on each use
- **Phishing-resistant**: Bound to the domain — fake sites can't intercept
- **No secret to remember**: Nothing to write on a sticky note or reuse across services
- **PRF extension**: Derives a deterministic secret for encryption — passwords can't do this without additional key derivation complexity

### Why is there no password fallback?

A fallback weakens the entire system to the strength of the weakest option. If passwords are available, attackers will target them (phishing, brute force, credential stuffing). By making passkey+PRF the only path, there's no downgrade attack possible.

### Why rotating tokens instead of static API tokens?

Static API tokens are permanent — steal one, have access forever until manually revoked. Rotating tokens:
- Die after one use (next legitimate call rotates them)
- Are IP-bound on first use (different IP = rejected)
- Expire 7 days after the request that minted them, even if unused (the CLI renews through its login token)
- Encrypt the org passphrase (token IS the decryption key for the next operation)

A stolen rotating token has a window of seconds to hours. A stolen static token has a window of forever.

### How does config sync work on headless servers without a browser?

The device code flow (same pattern as GitHub CLI, `gcloud`, Stripe CLI):
1. CLI shows a URL + code: `rediacc.com/device?code=ABCD&key=<handoff_pub>`
2. User opens the URL on their phone or laptop (any device with a browser)
3. Browser handles passkey authentication + PRF derivation
4. `passkey_secret` is encrypted with the CLI's ephemeral public key (from the URL)
5. Server relays the encrypted blob — it can't read it
6. CLI decrypts and stores `passkey_secret` in the native secure storage

The server only relays an opaque encrypted blob, as long as the page code it serves is unmodified.

### Why does the browser read `handoff_pub` from the URL, not from the server API?

To prevent server-side key substitution. If the server provided the public key via its API, a rogue server could substitute its own key and intercept `passkey_secret`. By embedding the key in the URL (which the CLI controls), the browser reads it directly from the address bar. The config setup page is served as a static page with CSP + SRI to prevent script
injection. The page code still comes from the same server, so this blocks a substitution through the API but not a server that ships modified page code.

### How does team member addition work without the server seeing the CEK?

Each user derives an X25519 key pair from their passkey (using PRF with a different salt). The public key is stored on the server. When an admin adds a member:
1. Admin's browser unwraps the CEK (using their passkey)
2. Browser fetches the new member's X25519 public key from the server
3. Browser encrypts the CEK with the member's public key → sends to server
4. Server stores the encrypted blob (can't read it — no private key)
5. New member authenticates, derives their X25519 private key from passkey PRF
6. Decrypts CEK, wraps it with their own wrapping key, stores `wrappedCEK`

The server relays an opaque encrypted blob at every step. This is the same pattern used by Signal and MLS for group key distribution.

### What happens if a team member loses their passkey?

If their passkey is synced via iCloud Keychain/1Password — recover it on a new device. Same passkey = same PRF outputs = same keys. No action needed.

If the passkey is truly lost — another team admin re-does the "add member" flow with the recovering member's new passkey. The admin unwraps CEK in their browser and re-encrypts it for the new member's new X25519 public key. No data loss.

If it's a solo user with no other admins — old configs are unrecoverable by design. Generate a new passkey, new CEK, start fresh. This is why we recommend at least 2 team admins.

### What happens when a team member is removed?

Three revocation actions, in order of urgency:

1. **Immediate**: Admin removes member → server deletes their slots, identity and config tokens → the next request is refused, so no `server_secret` or `sdk_derived` is served again
2. **CEK rotation (optional)**: only a rotation keeps a CEK the member kept from opening blobs written later
3. **Infrastructure (separate)**: Rotate the team SSH key on all machines (`authorized_keys`) → their local copy of the old SSH key is rejected

The revoked member may have a **local snapshot** of the last config they pulled (plaintext `rediacc.json` on their disk). This is inherent to any system that gives users access to data. The SSH key rotation (step 3) ensures their snapshot's SSH keys are stale and useless.

CEK rotation is not needed to cut server access. It is needed when a removed member may have kept the CEK and may later obtain blobs another way.

### Why store `passkey_secret` in OS-native secure storage instead of the token file?

The token file sits on disk as a regular file (protected only by 0o600 permissions). If stolen (backup leak, malware, shared filesystem), all secrets in it are exposed. Native secure storage provides OS-level protection:
- **Linux kernel keyring**: Keys in kernel memory, not user-space. Not accessible via filesystem. Supports auto-expiry timeouts.
- **macOS Keychain**: Encrypted at rest by the OS. Can require Touch ID to access.
- **Windows DPAPI**: Encrypted with user's login credentials. Useless if copied to another machine.

The token file becomes a pointer (`storageKeyId`) to the secret, not the secret itself. Stealing the token file without the native storage gives the attacker a reference string and a one-use token — but no `passkey_secret` to derive the CEK.

### Why does the server generate the `storageKeyId` instead of the CLI?

The server controls the namespace to prevent collisions across orgs, teams, and config stores. Each `storageKeyId` is unique (e.g., `rdc:org_abc:team_xyz:config_123`). If the CLI generated it, two users in different orgs could collide. Server-generated IDs also enable revocation — the server can invalidate a `storageKeyId` and the CLI knows to re-authenticate.

### Can Rediacc operators read stored configs?

Not from what the server stores or relays, provided the operator stays passive and the portal code is the published code:

- **At rest**: the CEK layer needs a slot secret, which never reaches the server. The server can remove layer 3 (it can recover the org passphrase) and layer 1 (it holds `sdkMaster`), which leaves the CEK layer.
- **In transit**: CLI traffic carries only CEK-layer ciphertext; the slot secret stays in the OS keyring.
- **Not covered**: an operator who serves modified portal JavaScript can read the CEK in the browser, and an operator holding the database can guess a master password slot offline. An operator can also withhold the newest version from a device that never saw it.

The full list of what the server can and cannot learn or do is in [Security model](#security-model).

### Does this work on both Cloudflare Workers and self-hosted Node.js?

Yes. Both runtimes use Hono (HTTP framework) and Web Crypto API (cryptography). The only difference is database transactions:
- **Node.js/BetterSQLite3**: Full transaction support for atomic token rotation.
- **Cloudflare Workers/D1**: No `BEGIN TRANSACTION`. Uses two-phase writes (create new alongside old, then delete old). If anything fails, old token still works. Stale tokens cleaned up periodically.

### What's the riskiest part to implement?

The platform-native secure storage abstraction (implementation step 5). Three different OS APIs (`keyctl`, `security`, DPAPI) with different behaviors:
- Linux kernel keyring: keys in memory, lost on reboot, timeout-based expiry
- macOS Keychain: persistent, encrypted at rest, optional biometric
- Windows DPAPI: persistent, encrypted blob files, tied to user login

Each has different error modes, permission models, and availability guarantees. This should be built and tested as a standalone module before integrating with the rest of the system.

### Why is 2FA recommended but not mandatory (while passkey IS mandatory)?

A passkey is already multi-factor by nature — something you have (device) + something you are (biometric). Adding TOTP on top is redundant for authentication. However, TOTP adds value for **elevated operations** (adding members, deleting configs, key rotation) as an out-of-band confirmation — it proves access to a separate authenticator app, which may be on a different device than
the browser. Users who want maximum security enable TOTP. Users who find it unnecessary can rely on passkey re-authentication for elevated ops instead.

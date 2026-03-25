# Config Storage Security Architecture

> **Note**: Config storage setup and member management are web-portal-only operations.
> CLI push/pull commands are planned but not yet implemented.

## Executive Summary

The Rediacc config storage provider implements zero-knowledge encrypted config synchronization. CLI configurations — containing SSH keys, machine IPs, repository credentials, and network topology — are encrypted client-side before transmission. The server stores only opaque encrypted blobs it cannot decrypt, even during request processing.

**Key guarantee**: Neither Rediacc operators, hosting providers, nor database administrators can read stored configurations.

## Encryption Architecture

### Triple-Layer Encryption

Every config value passes through three independent encryption layers:

```
Layer 1 (Inner — SDK):       Time-windowed server-derived key
Layer 2 (Middle — CEK):      Client-controlled key (split-key derivation)
Layer 3 (Outer — Org Pass):  Server-side organization passphrase

At rest: orgEnc(clientEnc_CEK(serverKeyEnc_SDK(plaintext)))
```

Each layer protects against a different threat:
- **SDK (Layer 1)**: Enables instant access revocation — removed members can't get new SDK keys
- **CEK (Layer 2)**: Client-side zero-knowledge — server never has this key
- **Org Passphrase (Layer 3)**: Protects database at rest — DB dumps are useless

### Key Hierarchy

```
Passkey (YubiKey / iCloud Keychain / 1Password)
  │
  ├─ PRF("rediacc-secret-v1") → passkey_secret (never transmitted to server)
  ├─ PRF("rediacc-x25519-v1") → X25519 identity key pair (for member key distribution)
  │
  └─ passkey_secret + server_secret → wrapping_key → unwraps CEK
                                                        │
  sdkMaster (server DB) → HKDF(epoch) → sdk_derived    │
                                          │              │
                                          └──── encrypt ─┘── decrypt config values
```

### What Lives Where

| Secret | Location | Protection |
|--------|----------|------------|
| Passkey private key | Passkey provider | Biometric/PIN, synced across devices |
| passkey_secret | OS-native secure storage (keyctl/Keychain/DPAPI) | Platform-level isolation |
| server_secret | Server DB | Encrypted with org passphrase |
| Org passphrase | Server DB | Encrypted with rotating token |
| CEK | Nowhere — unwrapped on the fly | Split-key derivation required |
| sdk_derived | Ephemeral (30s cache) | Time-windowed HKDF from sdkMaster |
| sdkMaster | Server DB | Never transmitted |
| Config values | Server R2/RustFS | Triple-encrypted |

## Passkey + PRF Flow

### Registration (Once Per User)

1. User authenticates with passkey (biometric approval)
2. WebAuthn PRF extension derives `passkey_secret` — deterministic, never leaves the client
3. Same passkey derives X25519 identity key pair (different PRF salt)
4. Browser generates random CEK, wraps with `HKDF(passkey_secret + server_secret)`
5. Server stores wrapped CEK (can't unwrap — doesn't have passkey_secret)

### Daily Operations (No Password)

1. CLI reads `passkey_secret` from native secure storage
2. Server provides `server_secret` + `sdk_derived` via rotating token
3. CLI derives wrapping key → unwraps CEK → encrypts/decrypts config
4. CEK exists in memory only during the operation, then discarded

### Split-Key Security

Neither party alone can derive the encryption key:
- **Server** has `server_secret` but not `passkey_secret` → can't derive CEK
- **Stolen passkey** has `passkey_secret` but not `server_secret` → can't derive CEK
- **Stolen token file** has `storageKeyId` but `passkey_secret` is in native secure storage → can't derive CEK

## Token Security

### Rotating Tokens

Each API call returns a new token. The old token dies.

```
Request 1: token_1 → validated → returns token_2
Request 2: token_2 → validated → returns token_3
token_1 is now dead
```

Properties:
- **Single-use**: max 3 reuses (grace window for concurrent requests)
- **IP-bound**: first use binds to client IP; different IP → rejected + alert
- **24h expiry**: unused tokens expire automatically
- **Hashed storage**: server stores SHA-256 hash, never plaintext
- **Encrypts org passphrase**: each token encrypts the org passphrase for the next operation

### Stolen Token Analysis

| Scenario | Result |
|----------|--------|
| Token stolen before rotation | One-use window (same IP required), then dead |
| Token stolen after rotation | Rejected — hash doesn't match |
| Token + different IP | Immediately rejected, admin alerted |
| Token + no passkey_secret | Can authenticate once but can't derive CEK → can't decrypt |

## SDK Time-Windowed Derivation

The master SDK key (`sdkMaster`) never leaves the server. Clients receive derived keys valid for specific time windows:

```
sdk_derived = HKDF(sdkMaster, epoch)
epoch = floor(timestamp / 300)  // 5-minute windows
```

Properties:
- Same master + same window = same derived key (deterministic)
- Different window = completely different key (unpredictable without master)
- Server stores `sdkEpoch` with each config entry for re-derivation on pull
- Captured `sdk_derived` only decrypts configs from that specific 5-minute window

## Member Lifecycle

### Adding Members

CEK distribution uses X25519 key exchange between browsers — server only relays opaque blobs:

1. Admin authenticates → unwraps CEK in browser
2. Server provides new member's X25519 public key
3. Admin's browser encrypts CEK with member's public key
4. Server stores encrypted blob (can't read it)
5. New member authenticates → derives X25519 private key from passkey PRF
6. Decrypts CEK → wraps with own key → stores wrappedCEK

### Removing Members

1. Delete wrappedCEK → member can't unwrap CEK
2. Revoke tokens → member can't get server_secret
3. Stop serving sdk_derived → within 30 seconds, all access cut
4. No CEK rotation needed — just stop serving keys

### SDK Time-Window Protection

Even if a removed member saved an `sdk_derived`, they can only decrypt configs from that specific time window. All configs pushed after removal use new epoch keys they never received.

## Threat Model

| Attack | What Attacker Gets | What They Need | Result |
|--------|-------------------|----------------|--------|
| DB dump | orgEnc(clientEnc(sdkEnc(values))) | org passphrase + CEK + sdk_derived | Triple-encrypted, no single key sufficient |
| Server memory during request | clientEnc(sdkEnc(values)) | CEK + sdk_derived | Still double-encrypted |
| Token file stolen | storageKeyId + serverToken | passkey_secret (in secure storage) | Reference only, no secrets |
| Passkey compromised alone | passkey_secret | server_secret (requires valid token) | Can't derive CEK |
| Rogue server code | clientEnc(sdkEnc(values)) at most | CEK (never on server) | Still encrypted |
| Former employee with CEK | Can remove CEK layer | sdk_derived (server refuses) | Blocked within 30 seconds |

## Platform-Specific Security

### Client-Side Secure Storage

| Platform | Mechanism | Properties |
|----------|-----------|------------|
| Linux | Kernel keyring (`keyctl`) | Kernel memory, per-user isolation, auto-expiry |
| macOS | Keychain (`security`) | Encrypted at rest, optional Touch ID |
| Windows | DPAPI | Tied to user's Windows login, useless if copied |
| Fallback | File (0o600) | File permissions only (warning logged) |

### Headless Mode

For servers without browsers, zero-knowledge is preserved via ephemeral X25519 handoff:
1. CLI generates ephemeral key pair, embeds public key in URL
2. Browser reads key from URL (not from server API — prevents key substitution)
3. Browser encrypts passkey_secret with CLI's public key
4. Server relays opaque blob
5. CLI decrypts with ephemeral private key

### Hosting Compatibility

| Component | Cloudflare Workers | Node.js Standalone |
|-----------|-------------------|-------------------|
| Metadata DB | D1 (serverless SQLite) | BetterSQLite3 |
| Blob storage | R2 | RustFS (S3-compatible) |
| Crypto API | Web Crypto (native) | Web Crypto (crypto.subtle) |
| Token atomicity | Two-phase write (batch) | Transaction |

## 2FA Enforcement

| Operation | 2FA Required? | Why |
|-----------|---------------|-----|
| Store setup | Yes | Creates encryption infrastructure |
| Add member | Yes | Grants access to encrypted configs |
| Remove member | Yes | Revokes access |
| Delete store | Yes | Destroys all keys |
| Push/pull configs | No | Frequent, uses rotating tokens |
| Accept handoff | No | Member was already authorized |
| Read operations | No | No state changes |

## Audit Logging

All config operations are logged to `event_log` with hash chain integrity:

| Event | Severity | Trigger |
|-------|----------|---------|
| config.push | info | Config pushed |
| config.pull | info | Config pulled |
| config.member.added | info | Member invited |
| config.member.removed | warning | Member access revoked |
| config.store.delete | critical | Entire store destroyed |
| config.auth.ip_mismatch | critical | Token used from unexpected IP |
| config.auth.sdk_denied | critical | Removed member attempted access |
| config.hmac.failed | critical | Tamper detection triggered |

Critical events trigger immediate admin notifications.

## Selective Encryption

Config data is split into plaintext envelope and encrypted values:

```json
{
  "version": 42,          // plaintext — server reads for conflict detection
  "id": "uuid",           // plaintext — config identity
  "sdkEpoch": 5913166,    // plaintext — for SDK re-derivation
  "machines": "encrypted", // triple-encrypted
  "ssh": "encrypted",      // triple-encrypted
  "repositories": "encrypted"
}
```

The server can do version conflict detection, listing, and access control using only plaintext fields — no decryption needed for operational tasks.

## Version Conflict Resolution

```
Push v42 when server has v41 → Accept (42 > 41)
Push v42 when server has v43 → Reject: "Version conflict, pull first"
Push v42 when server has different id → Reject: "Config identity mismatch"
```

All conflict detection uses plaintext envelope fields. Zero cryptographic operations required.

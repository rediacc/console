---
title: Config Storage
description: Client-side encrypted config sync with passkey, master password, and recovery code unlock
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: en
---

# Config Storage

Config storage synchronizes a CLI configuration across devices. Configs are encrypted on the device with a content encryption key (CEK) that the server never holds. The [Security](#security) section states exactly what that protects against and what it does not.

## Unlock methods (key slots)

There is one CEK per store, wrapped independently for each unlock method, similar to LUKS key slots. Any single slot opens the same key, and slots can be added or removed without re-encrypting your data:

| Method | What it is | Notes |
|--------|-----------|-------|
| **Passkey** | WebAuthn passkey with the PRF extension | The strongest option; hardware-backed |
| **Master password** | A password you choose, stretched with PBKDF2-SHA256 (600,000 iterations) | Works without PRF-capable hardware; also enables headless CLI enrollment |
| **Recovery code** | A generated `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` code | Shown exactly once at creation; store it somewhere safe |

Every method feeds the same pipeline: the slot yields a secret that combines with a server-held secret to unwrap the CEK. Neither half alone is enough, and the slot secret never reaches the server. A master password slot is the weakest of the three: the server holds everything needed to test password guesses offline, so the password has to be strong. Passkey and recovery code slots have no such weakness.

Slots are managed in the portal on the Config Storage page. Organizations that want hardware-only unlock can enable the **require passkey** policy, which refuses and revokes non-passkey slots for the whole store.

Unlocking is per-device: you unlock once on a new device, and after that daily CLI operations (push/pull) work without touching a passkey or typing a password.

## Prerequisites

- **Two-factor authentication** enabled on your account
- For the **passkey** method: a passkey provider with PRF support, such as a FIDO2 security key (e.g. YubiKey), iCloud Keychain, Google Password Manager, 1Password, or Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+

The PRF requirement applies only to the passkey slot. The master password and recovery code methods work with any supported browser.

## Setup

1. Navigate to **Config Storage** in the sidebar, then click **Set Up Config Storage**
2. The requirements checklist verifies your browser, 2FA, and session status
3. Choose the first unlock method, then click **Create config store**:
   - **Passkey**, when the provider supports PRF: the security key is touched twice, once to register it and once to derive the encryption keys.
   - **Master password**, which works with any browser, including passkey providers without PRF such as Bitwarden.
   - Optionally a **recovery code**, shown once, to save before the store is created.
4. Setup complete. The CLI keeps the unlock secret in the OS keyring.

A passkey can be added later from the Config Storage page. Keep at least two unlock methods, so a lost or unsupported authenticator cannot lock the store.

## PRF Provider Compatibility

| Provider | PRF Support | Platforms |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 security keys | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Cross-platform |
| Bitwarden extension | ❌ | Use a master password instead |
| Windows Hello | ❌ | Not supported |

## Headless CLI enrollment

A machine with no browser (a server, a CI runner, an executor daemon) can enroll into an existing store with the master password method:

```bash
rdc config remote enable --password
```

Requirements:

- A **master password slot** already provisioned through the portal (the browser holds the key during provisioning, so this step cannot itself be headless)
- An **API token with the `config:enroll` scope** to authenticate the call

Enrollment is a read: the CLI fetches the slot's public KDF parameters and the wrapped key, derives the password secret locally, and unwraps the CEK on the device. It grants the device the ability to decrypt and sync the config; it does not modify the store.

## Enabling and offline reads

`rdc config remote enable` connects the active config to the store. When the store is empty, enabling **seeds it from your current local config**: the local resources are pushed as the store's first version, then pulled back to prove the round trip. When the store already has content, enable reconciles against it instead of overwriting (it aborts on a genuine divergence unless you pass `--force`).

Once enabled, the config keeps a full **read cache**, encrypted at rest with the same mechanism as any local config, so the store stays usable when the account server is unreachable:

- **Reads work offline.** The cached content is served with a staleness warning on stderr, tagged with the cached version and timestamp (`cachedVersion` / `cachedAt`).
- **Writes require the server and fail closed.** There is no offline write queue: a write that cannot reach the server errors out and names the server. If a write command succeeded, the change is on the server.
- **Concurrent edits from two machines** resolve by pull-replay-repush: the server accepts a push only on top of the version it replaces, and the losing push is replayed on the fresh copy, so a simultaneous edit elsewhere is not overwritten.
- **A local config** (one with no `remote` block) is not affected by any of this and works fully offline.

## What syncs

Everything in a config syncs, including every repository's network ID, except these device-local fields: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier`, and the login fields `account.accountServer` and `account.e2ePublicKey`. Logging in and out is per device.

## Versions and restore

The server keeps the last 50 versions of each config.

```bash
rdc config remote versions
rdc config remote restore <version>
```

A restore publishes the old content as a new version on top of the current one; it never moves the version number backwards. Every device gets the restored content on its next pull, and the restore is recorded in the audit log.

## Key rotation

Rotating the store's CEK re-wraps it under a new generation:

- **Recovery codes are always invalidated** by rotation, generate and save a new one afterwards
- A **master password slot** survives only if the password is re-entered during the rotation wizard
- A slot left behind at an older generation is reported as stale rather than failing with a cryptic decryption error
- The other members' config tokens are revoked, and a device still holding the old key is told to re-enable with `rdc config remote enable`

## Member Management

Config storage is scoped per organization. Members are managed via the web portal:

- **View members**: Config Storage → Members
- **Add member**: Currently via CLI only (web UI planned)
- **Remove member**: Click the remove button on the Members page (requires 2FA + re-authentication)

Safety guards prevent removing the last active member or removing yourself.

Configs in the store are further scoped per team, but that scoping is **server-side access control, not cryptographic isolation**: one org-wide CEK encrypts every team's configs, and the server enforces which teams a member may read.

## Security

**What is protected.** Stored configs are confidential against a compromise of the server's storage and against a passive operator. Every blob is bound to its store, config, team and version, so the server cannot swap one config's blob for another's or alter one undetected.

**What is not protected.** An operator who serves malicious portal code can read the key in the browser. An operator can also withhold the newest version from a device that has never seen it.

| The server can | The server cannot |
|---|---|
| See config ids, teams, version numbers, timestamps, blob sizes, how many fields a config commits and each field's type, and client IP addresses | See machine, repository or storage names (they are blinded) or any config value |
| Refuse, delay or delete configs and their history | Serve one config's content as another's, or edit it, without the device detecting it |
| Serve an old version to a device that never saw a newer one | Serve the CLI a version older than one it already saw: the CLI refuses it |
| Test master password guesses offline | Open a passkey or recovery code slot |

Other safeguards:

- **Split key**: decryption needs both the slot secret (on the device) and the server secret
- **Deletion needs knowledge**: removing a committed value from a config requires proving the value was known, so an agent with partial access cannot silently drop fields
- **Rotating tokens**: every request rotates the config token; a token is bound to the IP address of its first use and expires after 7 days
- **Revocation**: removing a member deletes their key slots and tokens at once; what they already pulled stays on their device, and a CEK rotation keeps a key they kept from opening later versions

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| PRF not supported | Authenticator lacks PRF extension | Use YubiKey, iCloud Keychain, 1Password, or Dashlane, or add a master password slot |
| X25519 not supported | Browser version too old | Update to Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+ |
| Already configured | Store exists for your organization | Visit /account/config-storage to manage |
| Config storage not configured | Server missing blob storage | Contact your admin to configure R2/RustFS |
| Token expired | No activity for 7 days, or the machine changed networks | Renewed automatically through the login; if no login is stored, run `rdc subscription login` or `rdc config remote enable` |
| Config came back at an older version | The server returned an older copy than this device already saw | Nothing changed locally; retry, and report it if it persists |
| Cannot remove last member | Would lock out the store permanently | Add another member first |
| Stale slot | Slot predates the last key rotation | Re-add the slot (recovery codes must be regenerated after every rotation) |

## Related

- [Web Console](/en/docs/web-console), unlocking the store in the browser to run commands
- [Proxy & Executor](/en/docs/proxy-and-executor), how the unlocked key is granted to an executor

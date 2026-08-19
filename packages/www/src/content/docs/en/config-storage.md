---
title: Config Storage
description: Zero-knowledge encrypted config sync with passkey, master password, and recovery code unlock
category: Guides
tags:
  - account
  - security
order: 8
language: en
---

# Config Storage

Config storage provides zero-knowledge encrypted synchronization of your CLI configuration across devices. Your configs are encrypted client-side with a content encryption key (CEK), the server never sees plaintext data.

## Unlock methods (key slots)

There is one CEK per store, wrapped independently for each unlock method, similar to LUKS key slots. Any single slot opens the same key, and slots can be added or removed without re-encrypting your data:

| Method | What it is | Notes |
|--------|-----------|-------|
| **Passkey** | WebAuthn passkey with the PRF extension | The strongest option; hardware-backed |
| **Master password** | A password you choose, stretched with PBKDF2-SHA256 (600,000 iterations) | Works without PRF-capable hardware; also enables headless CLI enrollment |
| **Recovery code** | A generated `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` code | Shown exactly once at creation; store it somewhere safe |

Every method feeds the same pipeline: the slot yields a secret that combines with a server-held secret to unwrap the CEK. Neither half alone is enough, so the zero-knowledge property holds for all three methods, the slot secret never reaches the server.

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
3. Click **Start Setup**. For a passkey slot you'll touch your security key twice:
   - First touch: registers the passkey
   - Second touch: derives encryption keys via PRF
4. Setup complete, your passkey secret is stored in your OS keyring

After setup, add a master password or recovery code slot from the Config Storage page so a lost or unsupported authenticator cannot lock you out.

## PRF Provider Compatibility

| Provider | PRF Support | Platforms |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 security keys | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Cross-platform |
| Bitwarden extension | ❌ | In development |
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
- **Concurrent edits from two machines** resolve by pull-replay-repush at the resource-bucket level, so a simultaneous edit elsewhere does not clobber yours.

## Key rotation

Rotating the store's CEK re-wraps it under a new generation:

- **Recovery codes are always invalidated** by rotation, generate and save a new one afterwards
- A **master password slot** survives only if the password is re-entered during the rotation wizard
- A slot left behind at an older generation is reported as stale rather than failing with a cryptic decryption error

## Member Management

Config storage is scoped per organization. Members are managed via the web portal:

- **View members**: Config Storage → Members
- **Add member**: Currently via CLI only (web UI planned)
- **Remove member**: Click the remove button on the Members page (requires 2FA + re-authentication)

Safety guards prevent removing the last active member or removing yourself.

Configs in the store are further scoped per team, but that scoping is **server-side access control, not cryptographic isolation**: one org-wide CEK encrypts every team's configs, and the server enforces which teams a member may read.

## Security

- **Zero-knowledge**: The server stores triple-encrypted data it cannot decrypt
- **Split-key**: Decryption requires both your slot secret (client) and server secret (server)
- **Rotating tokens**: Each API call uses a fresh token; old tokens self-destruct
- **IP binding**: Tokens are bound to your IP on first use
- **Instant revocation**: Removed members lose access within 30 seconds

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| PRF not supported | Authenticator lacks PRF extension | Use YubiKey, iCloud Keychain, 1Password, or Dashlane, or add a master password slot |
| X25519 not supported | Browser version too old | Update to Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+ |
| Already configured | Store exists for your organization | Visit /account/config-storage to manage |
| Config storage not configured | Server missing blob storage | Contact your admin to configure R2/RustFS |
| Token expired | No activity for 24 hours | Run any config storage command to refresh |
| Cannot remove last member | Would lock out the store permanently | Add another member first |
| Stale slot | Slot predates the last key rotation | Re-add the slot (recovery codes must be regenerated after every rotation) |

## Related

- [Web Console](/en/docs/web-console), unlocking the store in the browser to run commands
- [Proxy & Executor](/en/docs/proxy-and-executor), how the unlocked key is granted to an executor

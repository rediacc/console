---
title: Config Storage
description: Zero-knowledge encrypted config sync with passkey-based encryption
category: Guides
order: 8
language: en
sourceHash: "d20655e3e306b85b"
---

# Config Storage

Config storage provides zero-knowledge encrypted synchronization of your CLI configuration across devices. Your configs are encrypted with keys derived from your passkey — the server never sees plaintext data.

## Prerequisites

- **Two-factor authentication** enabled on your account
- **Passkey provider with PRF support**: FIDO2 security key (e.g. YubiKey), iCloud Keychain, Google Password Manager, 1Password, or Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+

## Setup

1. Navigate to **Config Storage** in the sidebar, then click **Set Up Config Storage**
2. The requirements checklist verifies your browser, 2FA, and session status
3. Click **Start Setup** — you'll need to touch your security key twice:
   - First touch: registers the passkey
   - Second touch: derives encryption keys via PRF
4. Setup complete — your passkey secret is stored in your OS keyring

After setup, daily CLI operations (push/pull) work without the passkey.

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

## Member Management

Config storage is scoped per organization. Members are managed via the web portal:

- **View members**: Config Storage → Members
- **Add member**: Currently via CLI only (web UI planned)
- **Remove member**: Click the remove button on the Members page (requires 2FA + re-authentication)

Safety guards prevent removing the last active member or removing yourself.

## Security

- **Zero-knowledge**: The server stores triple-encrypted data it cannot decrypt
- **Split-key**: Decryption requires both your passkey secret (client) and server secret (server)
- **Rotating tokens**: Each API call uses a fresh token; old tokens self-destruct
- **IP binding**: Tokens are bound to your IP on first use
- **Instant revocation**: Removed members lose access within 30 seconds

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| PRF not supported | Authenticator lacks PRF extension | Use YubiKey, iCloud Keychain, 1Password, or Dashlane |
| X25519 not supported | Browser version too old | Update to Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+ |
| Already configured | Store exists for your organization | Visit /account/config-storage to manage |
| Config storage not configured | Server missing blob storage | Contact your admin to configure R2/RustFS |
| Token expired | No activity for 24 hours | Run any config storage command to refresh |
| Cannot remove last member | Would lock out the store permanently | Add another member first |

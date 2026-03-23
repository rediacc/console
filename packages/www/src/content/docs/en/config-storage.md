---
title: "Config Storage (Rediacc Provider)"
description: "Securely sync CLI configuration across devices and teams with zero-knowledge encryption."
category: "Guides"
order: 9
language: en
---

# Config Storage

The Rediacc config storage provider syncs your CLI configuration across devices and teams with zero-knowledge encryption. Your SSH keys, machine IPs, and credentials are encrypted client-side before leaving your machine — even Rediacc operators cannot read your data.

## Prerequisites

- **Passkey provider with PRF support**: Bitwarden, iCloud Keychain, or Windows Hello
- **2FA enabled** for org owners/admins (required for store setup and member management)
- **Account subscription** with config storage enabled

## Quick Start

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Setup

### Desktop (Has Browser)

```bash
rdc store add my-config --type rediacc
```

1. A browser window opens to the Rediacc account portal
2. Register a passkey (Bitwarden/iCloud/Windows Hello popup)
3. The passkey's PRF extension derives your encryption keys
4. Keys are stored in your OS-native secure storage (Keychain/keyctl/DPAPI)
5. Done — no password to remember

### Headless Servers (No Browser)

```bash
rdc store add my-config --type rediacc --headless
```

1. CLI shows a URL with a device code
2. Open the URL on your phone or laptop
3. Complete passkey registration in the browser
4. The CLI automatically receives your encrypted keys via a secure relay
5. Zero-knowledge preserved — the server only relays an opaque encrypted blob

### Custom Server URL

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

After setup, push and pull work without any passwords or prompts:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Each operation uses a rotating token that self-destructs after one use. No static credentials.

## Team Management

Team members are managed through the web portal at `/account/config-storage/members`.

### Adding Members

1. Admin opens the config storage members page
2. Clicks "Add Member" (requires 2FA)
3. The admin's browser encrypts the team encryption key for the new member
4. New member logs in and accepts the invitation
5. Both can now push/pull the same configs

### Removing Members

1. Admin clicks "Remove" next to the member (requires 2FA)
2. Member's encryption keys are deleted immediately
3. Within 30 seconds, the member loses all access to encrypted configs

No key rotation needed — the server simply stops serving decryption keys to the removed member.

## Security Properties

| Property | How |
|----------|-----|
| **Zero-knowledge** | Client encrypts before sending; server sees only opaque blobs |
| **No master password** | Passkey biometric replaces passwords entirely |
| **Split-key derivation** | CEK requires both passkey_secret (client) + server_secret (server) |
| **Rotating tokens** | Each API call generates a new token; old ones die |
| **IP binding** | Tokens bound to client IP on first use |
| **Triple encryption** | SDK (time-windowed) + CEK (client) + org passphrase (server) |
| **Instant revocation** | Stop serving SDK to removed members; 30-second max delay |
| **Tamper detection** | HMAC over encrypted blobs; verified on every pull |

For the full security architecture, see [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## Troubleshooting

### "Passkey must support PRF extension"

Your passkey provider doesn't support the PRF extension. Use:
- Bitwarden (desktop app or browser extension)
- iCloud Keychain (Safari on macOS/iOS)
- Windows Hello

### "Two-factor authentication required"

Org owners and admins must enable 2FA before setting up config storage. Go to Account Settings → Security → Enable 2FA.

### "Version conflict"

Another team member pushed a newer version. Pull first:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Tokens expire after 24 hours of inactivity. Run any command to refresh:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

The encryption key was lost from your OS secure storage (reboot on Linux, keychain reset). Re-run setup:
```bash
rdc store add my-config --type rediacc
```

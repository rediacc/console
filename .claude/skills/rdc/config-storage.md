# Config Storage

Zero-knowledge encrypted config sync via the Rediacc account server.

## CLI commands

The CLI surface is `rdc config remote`:

| Command | Purpose |
|---------|---------|
| `rdc config remote enable` | Link this config to remote encrypted storage (add `--headless` for a device-code flow on a server with no browser) |
| `rdc config remote disable` | Disconnect from remote storage and save the config locally |
| `rdc config remote status` | Show remote connection status |
| `rdc config remote refresh` | Force a re-fetch of the config from remote storage |
| `rdc config rotate-cek` | Rotate the client-controlled encryption key |

Uploads are implicit: once remote is enabled, config writes go to the store. There is no
separate push command.

## Agent Limitations

- **Setup**: `config remote enable` needs a browser (passkey + PRF ceremony) or an approved
  device-code handoff, so it is not available to agents unattended
- **Member management**: Requires web portal (elevated + 2FA) — not available to agents
- Agents can read config storage status via the account web API but cannot modify

## Architecture

- One store per organization, configs scoped per team
- Triple-layer encryption: SDK (time-windowed) + CEK (client-controlled) + Org passphrase (server-side)
- Passkey provides PRF-derived secret — no password to remember
- Rotating tokens self-destruct after each use, IP-bound

## Setup Flow (Web Portal Only)

1. Navigate to /account/config-setup
2. Requirements checklist must all pass (2FA, elevated session, browser support)
3. Register passkey (touch security key)
4. Derive encryption keys via PRF (touch again)
5. Server creates store, client generates CEK
6. passkey_secret stored in OS keyring for future CLI use

## PRF Provider Compatibility

| Provider | PRF Support | Platforms |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 security keys | Yes | Win11, macOS, Linux |
| iCloud Keychain | Yes | macOS 15+, iOS 18+ |
| Google Password Manager | Yes | Android |
| 1Password | Yes | Android, iOS |
| Dashlane | Yes | Cross-platform |
| Bitwarden extension | No | — |
| Windows Hello | No | — |

## Security Properties

- Zero-knowledge: server never sees plaintext
- Split-key: neither client nor server alone can decrypt
- Instant revocation: removed members lose access within 30 seconds
- 2FA required for setup and member management

## Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Config storage not configured" | Server doesn't have blob storage | Admin must configure R2/RustFS |
| "passkey_secret not found" | OS secure storage cleared | Re-run setup via web portal |
| "PRF not supported" | Authenticator lacks PRF | Use YubiKey, iCloud Keychain, 1Password, or Dashlane |
| "X25519 not supported" | Browser too old | Update to Chrome 133+, Edge 133+, Firefox 130+, Safari 17+ |
| "Already configured" | Store exists for org | Visit /account/config-storage to manage |
| "Cannot remove last member" | Would lock out store | Add another member first |

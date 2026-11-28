# Config Storage

Zero-knowledge encrypted config sync via the Rediacc account server.

## CLI commands

The CLI surface is `rdc config remote`:

| Command | Purpose |
|---------|---------|
| `rdc config remote enable` | Link this config to remote encrypted storage (sign in first with `rdc subscription login`; the CLI prints a link and a pairing code to approve in any browser, through the account server relay) |
| `rdc config remote disable` | Disconnect from remote storage and save the config locally |
| `rdc config remote status` | Show remote connection status |
| `rdc config remote refresh` | Force a re-fetch of the config from remote storage |
| `rdc config rotate-cek` | Rotate the client-controlled encryption key |

Uploads are implicit: once remote is enabled, config writes go to the store. There is no separate push command.

## Agent Limitations

- **Setup**: `config remote enable` needs a browser (passkey + PRF ceremony) or an approved
device-code handoff, so it is not available to agents unattended
- **Member management**: Requires web portal (elevated + 2FA) — not available to agents
- Agents can read config storage status via the account web API but cannot modify
- **Config writes**: agents change one field at a time with `rdc config field set --current`; `rdc config edit` (interactive, `--apply`, `--reveal`) has no agent path and no override
- **Remote MCP**: an agent grant (minted in the portal, one config, 7 days by default, 30 at most) lets a remote agent run tools on the org executor; it is not a key holder and cannot edit the policy record

## Architecture

- One store per organization, configs scoped per team
- Triple-layer encryption: SDK (time-windowed) + CEK (client-controlled) + Org passphrase (server-side)
- Two unlock slots, passkey (PRF; on the device or a phone over QR) and the recovery kit; no password slot
- Every member holds a mandatory recovery kit, saved at enrollment with a save check
- Safety net: the server refuses a deletion that leaves fewer than two key holders and no recovery slot (`CONFIG_SAFETY_NET`); machine secrets and agent grants are not key holders
- Rotating tokens self-destruct after each use, IP-bound

## Setup Flow (Web Portal Only)

1. Navigate to /account/config-setup
2. Requirements checklist must all pass (2FA, elevated session, browser support)
3. Register passkey (touch security key)
4. Derive encryption keys via PRF (touch again)
5. Server creates store, client generates CEK
6. passkey_secret stored in OS keyring for future CLI use

## Headless enrollment

A machine with no browser enrolls with a machine secret (`RM1-`, minted in the portal, shown once): `REDIACC_MACHINE_SECRET=... rdc config remote enable --machine-secret <id>`, with an API token holding the `config:enroll` scope. `<id>` is the machine secret's id (`machineSecretId`), not the secret (`RM1-...`) itself. The secret comes from the environment, stdin or a hidden prompt, never argv.

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
| "PRF not supported" | Authenticator lacks PRF | Use YubiKey, iCloud Keychain, 1Password, Dashlane, or a phone over QR |
| "X25519 not supported" | Browser too old | Update to Chrome 133+, Edge 133+, Firefox 130+, Safari 17+ |
| "Already configured" | Store exists for org | Visit /account/config-storage to manage |
| "Cannot remove last member" | Would lock out store | Add another member first |

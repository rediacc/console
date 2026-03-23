# Config Storage

Secure config sync via the Rediacc provider with zero-knowledge triple-layer encryption.

## Agent Limitations

- `store add --type rediacc` requires browser interaction — **not available to agents**
- `store push/pull/sync` works normally after user completes setup
- Member management requires web portal (elevated + 2FA) — **not available to agents**
- Agents can read config storage status but cannot modify encryption settings

## Commands

### Push Config to Store
```bash
rdc store push --store <name>
```
Encrypts and uploads the current config. Uses rotating tokens — no password needed.

### Pull Config from Store
```bash
rdc store pull --store <name>
```
Downloads and decrypts the config. Verifies HMAC integrity before applying.

### Sync (Pull Then Push)
```bash
rdc store sync --store <name>
# Or sync all stores:
rdc store sync --all
```

### List Configured Stores
```bash
rdc store list
```
Shows all configured stores (S3, Bitwarden, Git, Vault, Rediacc).

## How It Works

1. User sets up config storage via browser (passkey + PRF)
2. Encryption keys derived from passkey — no password to remember
3. CLI encrypts config values locally (Layer 1: SDK, Layer 2: CEK)
4. Server adds Layer 3 encryption (org passphrase) before storing
5. On pull: server removes Layer 3, CLI removes Layers 2+1 → plaintext

## Security

- **Zero-knowledge**: Server never sees plaintext config data
- **Split-key**: Neither client nor server alone can derive the encryption key
- **Rotating tokens**: Each API call uses a fresh token; old tokens self-destruct
- **IP binding**: Tokens bound to client IP on first use
- **Instant revocation**: Removed members lose access within 30 seconds
- **2FA required**: Store setup and member management require two-factor authentication

## Version Conflicts

If another team member pushed a newer version:
```
Version conflict: remote is v43, push is v42. Pull first.
```

Resolution:
```bash
rdc store pull --store <name>
# Review changes, then push
rdc store push --store <name>
```

## Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Config storage not configured" | Server doesn't have blob storage | Admin must configure R2/RustFS |
| "passkey_secret not found" | OS secure storage cleared | Re-run `rdc store add --type rediacc` |
| "Token expired" | No activity for 24h | Run any store command to refresh |
| "IP mismatch" | Token used from different IP | Re-authenticate with new token |
| "2FA required" | Admin operation without 2FA | Enable 2FA in account settings |

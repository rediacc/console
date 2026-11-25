---
title: Config Storage
description: Client-side encrypted config sync with passkey and recovery kit unlock
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
| **Passkey** | WebAuthn passkey with the PRF extension, on this device or on a phone reached over a QR code | The strongest option; hardware-backed |
| **Recovery kit** | A generated `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` code, saved as a printed or downloaded kit | Mandatory for every member; the code is shown only while the kit is saved, so keep the kit somewhere safe |

A **machine secret** is not a slot: it enrolls a headless machine (see [Headless CLI enrollment](#headless-cli-enrollment)) and does not count as a way to unlock the store for a person.

Every method feeds the same pipeline: the slot yields a secret that combines with a server-held secret to unwrap the CEK. Neither half alone is enough, and the slot secret never reaches the server. Both secrets carry enough entropy that the server, which holds the wrapped key and its half of the wrapping key, has nothing to guess offline.

Slots are managed in the portal on the Config Storage page. Organizations that want hardware-only unlock can enable the **require passkey** policy, which refuses and revokes non-passkey slots for the whole store.

Unlocking is per-device: a new device unlocks once, and after that daily CLI operations (push/pull) work without touching a passkey or typing a recovery code.

## Prerequisites

- **Two-factor authentication** enabled on your account
- For the **passkey** method: a passkey provider with PRF support, such as a FIDO2 security key (e.g. YubiKey), iCloud Keychain, Google Password Manager, 1Password, or Dashlane, on the device or on a phone over QR
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+

The PRF requirement applies only to the passkey slot. The recovery kit works with any supported browser.

## Setup

1. Navigate to **Config Storage** in the sidebar, then click **Set Up Config Storage**
2. The requirements checklist verifies your browser, 2FA, and session status
3. Register a passkey, then click **Create config store**. The provider must support PRF: the security key is touched twice, once to register it and once to derive the encryption keys.
   - A **recovery code** is generated with the store and shown once, in a recovery kit. Save the kit before the store is created; setup does not complete without it.
4. Setup complete. The CLI keeps the unlock secret in the OS keyring.

A passkey can be added later from the Config Storage page.

### Phone over QR

A desktop without a local PRF authenticator can use a phone: the browser shows a QR code, the phone approves the passkey request over WebAuthn hybrid, and the PRF result unlocks the store as a local passkey would. The passkey slot remembers the credential and the transport it was enrolled with. If a PRF result does not unwrap the key, for example because a phone returned a different PRF output than the device that enrolled the passkey, the page asks to enroll the passkey again instead of reporting a decryption error. Hybrid PRF needs iOS 18.4+ or a current Android.

### Recovery kit

Every member receives a recovery kit at enrollment, and setup does not complete until it is saved. The kit holds the store name, the account email, the creation date, the code in groups, a QR of the code and recovery steps. A save check asks for the last 4 characters of the code, or a scan of its QR, before enrollment continues. There is no way to skip the kit, and keeping the printout safe is the member's responsibility.

- A **lost passkey** is recovered with the kit, then a new passkey is enrolled.
- A **lost kit** is regenerated from a working passkey; the old printout stops working.
- **Both lost**: an owner or admin re-adds the member through the member handoff.

### Safety net

The server refuses to delete a slot, remove a member or accept a member leaving when that would leave the store with fewer than two key holders and no recovery slot. A key holder is a distinct user with a passkey or recovery slot at the current key generation; machine secrets and agent grants do not count. A lost printout is invisible to the server, so the Config Storage page advises a second key holder while the store has only one. If the last key holder loses both the passkey and the kit, the store cannot be recovered.

## PRF Provider Compatibility

| Provider | PRF Support | Platforms |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 security keys | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Cross-platform |
| Bitwarden extension | ❌ | Use a hardware key or another passkey provider |
| Windows Hello | ❌ | Not supported |

## Headless CLI enrollment

A machine with no browser (a server, a CI runner, an executor daemon) can enroll into an existing store with a machine secret:

```bash
export REDIACC_MACHINE_SECRET=RM1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
rdc config remote enable --machine-secret <id>
```

Requirements:

- A **machine secret** minted through the portal (the browser holds the key while it wraps it under the secret, so this step cannot itself be headless). The portal shows the `RM1-` secret once, together with its id; the secret is scoped to the organization, a team or one config
- An **API token with the `config:enroll` scope** to authenticate the call

The secret comes from `REDIACC_MACHINE_SECRET`, else from standard input when it is piped, else from a hidden prompt; it is never a command-line argument. Enrollment is a read: the CLI fetches the secret's public KDF parameters and the wrapped key, derives the wrapping secret locally, and unwraps the CEK on the device. It grants the device the ability to decrypt and sync the config; it does not modify the store. Revoking the secret in the portal stops new enrollments with it.

## How the keys reach your CLI

`rdc config remote enable` (and `rdc config rotate-cek`) hand the unlock secret to the CLI through the account server. The CLI and the browser never talk to each other, so it works the same on a server with no browser, in WSL with the browser on Windows, or on a phone.

1. Sign in the CLI first with `rdc subscription login`. The server ties the request to that account.
2. The CLI creates a short-lived request and prints a link and a **pairing code** such as `7KQ2-M9XD-P4RT`. The link keeps everything it carries after the `#`, which browsers never send to a server.
3. Open the link in any browser signed in as the same account. A request from another account is refused.
4. Type the pairing code from the terminal when the page asks. The unlock button stays disabled until it matches.
5. Unlock with a passkey (on this device or a phone over QR) or the recovery kit. The browser seals the key to the CLI, and the server relays a blob it cannot read.
6. The CLI decrypts the blob, stores the secret in the OS keyring and reports success.

The request expires after 10 minutes. Press **Ctrl+C** in the CLI to cancel it: the CLI asks the server to drop the link, which then stops working at once, and the page says to run the command again. If that request does not get through, the link stays usable until the request expires. If the link is opened after it expired, or after a login redirect dropped the part after `#`, run the command again.

The pairing code is derived from the key inside the link. If someone swaps the link for their own, the code on the terminal will not match what the page expects, so nothing is released.

This protects against link tampering and against a relay that swaps or forges a blob. It does not protect against a server that ships modified page code: the page that opens is served by the account server, and the keys are as safe as that code is. The same trust applies to every portal page that handles the config key.

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

- **Recovery kits are always invalidated** by rotation, generate and save a new one afterwards
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

Other safeguards:

- **Split key**: decryption needs both the slot secret (on the device) and the server secret
- **Deletion needs knowledge**: removing a committed value from a config requires proving the value was known, so an agent with partial access cannot silently drop fields
- **Rotating tokens**: every request rotates the config token; a token is bound to the IP address of its first use and expires after 7 days
- **Revocation**: removing a member deletes their key slots and tokens at once; what they already pulled stays on their device, and a CEK rotation keeps a key they kept from opening later versions

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| PRF not supported | Authenticator lacks PRF extension | Use YubiKey, iCloud Keychain, 1Password, or Dashlane, or a phone over QR |
| X25519 not supported | Browser version too old | Update to Chrome 133+, Edge 133+, Firefox 130+, or Safari 17+ |
| Already configured | Store exists for your organization | Visit /account/config-storage to manage |
| Config storage not configured | Server missing blob storage | Contact your admin to configure R2/RustFS |
| Token expired | No activity for 7 days, or the machine changed networks | Renewed automatically through the login; if no login is stored, run `rdc subscription login` or `rdc config remote enable` |
| Config came back at an older version | The server returned an older copy than this device already saw | Nothing changed locally; retry, and report it if it persists |
| Cannot remove last member | Would lock out the store permanently | Add another member first |
| Stale slot | Slot predates the last key rotation | Re-add the slot (the recovery kit must be regenerated after every rotation) |

## Related

- [Web Console](/en/docs/web-console), unlocking the store in the browser to run commands
- [Proxy & Executor](/en/docs/proxy-and-executor), how the unlocked key is granted to an executor

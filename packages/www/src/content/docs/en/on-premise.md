---
title: "On-Premise Installation"
description: "Running the account server and CLI distribution on your own infrastructure."
category: "Guides"
order: 5
language: en
---

Rediacc can run entirely on your own infrastructure. The standalone Docker image includes the account server, web portal, marketing site, and CLI distribution endpoint. No external dependencies on Rediacc's hosted services are required.

## Docker Image

Pull the standalone image:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Run with default settings:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

The image serves:
- Account API at `/account/api/v1/`
- Web portal at `/account/`
- Marketing site at `/`
- CLI artifacts at `/releases/`
- Renet binaries at `/bin/`

## Installing the CLI from Your Server

Install the CLI directly from your on-premise server. The install script auto-detects the update channel and points the CLI at your server for updates.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

This single command:
1. Downloads the CLI binary from your server's `/releases/` endpoint
2. Queries `/account/api/v1/.well-known/server-info` to discover the update channel
3. Writes `server.json` with your server URL, update channel, and encryption keys
4. Configures `rdc update` to check your server for future updates

No `REDIACC_CHANNEL` variable is needed. The install script reads the channel from your server's configuration automatically.

## CLI Configuration with Named Configs

If you connect to multiple servers (on-premise, production, edge), named configs keep each environment isolated:

```bash
# Create a config for your on-premise server
rdc config init --name myserver --server https://account.example.com

# Log in using that config
rdc --config myserver subscription login

# All commands with --config use the on-premise server
rdc --config myserver machine query --name prod-1
```

Each named config stores its own account server URL and subscription token. Switching configs switches the entire server context.

## Air-Gapped Environments

For environments without internet access, set both the server URL and a custom releases URL:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

The CLI will check `account.example.com/releases/cli/stable/manifest.json` for updates instead of the public releases CDN.

If the server is completely offline, install the CLI via npm from the bundled tarball:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Environment Variables Reference

| Variable | Used by | Purpose |
|---|---|---|
| `REDIACC_SERVER_URL` | Install script | Account server URL. Auto-discovers channel and encryption keys. |
| `REDIACC_RELEASES_URL` | Install script, CLI updater | Custom releases endpoint for CLI binaries. Default: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Install script | Override the update channel. Auto-detected from server if not set. |
| `REDIACC_ACCOUNT_SERVER` | CLI runtime | Override account server URL for all CLI commands. |
| `RDC_UPDATE_CHANNEL` | CLI runtime | Override update channel for `rdc update`. |

## Server Configuration

The on-premise Docker image uses the same `ENVIRONMENT` variable as the hosted service. Set it in your Docker environment or orchestration config:

- `ENVIRONMENT=production` (default): standard resource limits; CLIs connecting to this server default to the **stable** update channel. The value name `production` is a legacy deploy identifier. Both `production` and `edge` modes are production-quality.
- `ENVIRONMENT=edge`: 2X Community limits; CLIs default to the **edge** update channel

See [Release Channels](/en/docs/release-channels) for details on what each environment provides.

## What the Server Tells the CLI

When the CLI connects to your server, it queries `/.well-known/server-info` to discover:

- **E2E encryption public key**: for zero-knowledge config storage
- **Minimum CLI version**: blocks outdated CLIs from connecting
- **Update channel**: tells the CLI which release channel to use for updates
- **Environment**: which deploy profile the server runs in (standard-limits vs. edge-with-2X-limits)

This auto-configuration means you only need the server URL. Everything else is discovered automatically.

## Licensing for Air-Gapped Deployments

Air-gapped and self-hosted on-premise servers issue licenses locally using a **delegation certificate** signed by the upstream master key. The certificate constrains the on-premise server to its plan limits and creates a tamper-evident chain. See [License Chain & Delegation](/en/docs/license-chain) for the cryptographic design (chain integrity, fork detection, audit proofs).

This section covers the operational setup: generating keys, requesting the cert, configuring auto-renew, and the offline (air-gapped) renewal flow.

### One subscription, one on-premise install

A subscription may have **at most one active delegation certificate at a time**. Each on-premise install enforces per-month and per-machine limits against its own local issuance ledger, so multiple active certs would multiply the effective quota with no possible reconciliation.

If you need separate environments (production, staging, DR, multi-region), buy one subscription per install. The single-active enforcement codifies this contract: an attempt to create a second active cert returns `409 DELEGATION_CERT_ALREADY_ACTIVE` with the existing cert id and instructions to renew (preferred, preserves the chain) or revoke-and-create (resets the chain).

### 1. Generate the on-premise Ed25519 key pair

The on-premise server uses a separate Ed25519 key pair to sign licenses. The upstream's delegation cert authorizes this specific public key.

```bash
# Generate a fresh keypair
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Convert to base64 (the format the on-premise expects in env vars)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Store the private key alongside your other secrets (for example, a Docker secret or Kubernetes Secret). It never leaves the on-premise box.

### 2. Request a delegation cert from the upstream

You can request the cert from the upstream account portal in three ways:

**Option A: Customer self-service (recommended).** Log into the upstream portal as an org owner or admin and go to **/account/delegation-certs**. Click **Create New**, paste the on-premise public key (base64 SPKI), pick a validity (or accept the per-plan default), and download the resulting `.json` file.

**Option B: Admin (cross-customer).** Rediacc support or the upstream system admin can call `POST /admin/delegation-certs` with the same parameters.

**Option C: `rdc` CLI (planned).** A future CLI command will wrap the portal flow.

The returned `.json` looks like:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

The cert's validity is governed by the validity policy (per-plan defaults and ceilings, per-subscription override, capped at subscription end + 3 day grace). The response also includes `effectiveDays` and `reason` so you can see why it picked that value. See [License Chain - Validity Policy](/en/docs/license-chain) for the full rules.

### 3. Install the cert on the on-premise server

Save the downloaded `.json` to a known path and point the on-premise to it:

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

Or, for ephemeral / Docker-secrets workflows, embed the cert as base64 in an env var:

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. Configure upstream verification + auto-renew (optional but recommended)

If your on-premise has outbound HTTPS access to the upstream, set up automatic renewal so the cert refreshes before expiry without manual intervention:

```bash
# Required for /onprem/cert-upload to verify uploaded certs against the upstream master key.
# Fails-fast at boot if UPSTREAM_API_KEY is set without this.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# Required for the auto-renew loop. Mint via the portal:
#   Org owner/admin → /account/delegation-certs → "Get auto-renew token"
# This is the ONLY way to obtain a delegation:renew-scoped api token.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Optional tuning (defaults shown).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

The on-premise auto-renew loop runs once at boot and then on the configured interval. It uses an **adaptive threshold** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) so a 15-day COMMUNITY cert renews at 5 days remaining instead of triggering renewal on day 1. A 90-day BUSINESS cert renews at 14 days remaining (the env-configured ceiling).

If renewal fails, the cert stays in use until natural expiry. The failure backs off for 1 hour and is recorded in `${DELEGATION_CERT_PATH}.status.json` plus exposed via `GET /onprem/cert-status`.

### 5. Air-gapped renewal (no outbound HTTPS)

If your on-premise cannot reach the upstream, use the manual transfer flow:

1. **Download a renewal request from the on-premise admin portal.** As the on-premise system root, hit `GET /onprem/renewal-request`. This returns a JSON manifest containing the local chain head, the delegated public key, and a tamper-evident Ed25519 signature from your on-premise private key.
2. **Transfer the manifest to the upstream** via USB, encrypted email, or any out-of-band channel. The manifest is small (a few KB) and contains no secrets.
3. **Process the manifest at the upstream.** Org owner/admin opens **/account/delegation-certs** → **Upload renewal request** → selects the manifest file. The upstream verifies the manifest signature against the active cert's `delegatedPublicKey` (proves it came from a holder of the on-premise private key), checks anti-replay (manifests older than 7 days are rejected), then issues a fresh cert.
4. **Download the new cert** from the upstream portal as a `.json` file.
5. **Transfer the cert back** to the on-premise.
6. **Upload to the on-premise** via the local admin portal (`POST /onprem/cert-upload`). The on-premise verifies the new cert against `UPSTREAM_PUBLIC_KEY` and validates that the cert's `genesisSequence` still links to a chain entry in the local issuance ledger (sequence advancement during transit is supported - the chain extends naturally).

This entire loop never requires network egress from the on-premise.

#### Manifest failure modes

| Code | Cause | Fix |
|---|---|---|
| `NO_ACTIVE_CERT` | Upstream has no active cert for this subscription | Issue a new cert via the create flow instead of renewing |
| `DELEGATED_KEY_MISMATCH` | Manifest's `delegatedPublicKey` differs from the active cert | The manifest may be a replay from a different on-prem install |
| `MANIFEST_SIGNATURE_INVALID` | Signature doesn't verify against the delegated public key | Manifest was tampered in transit, or you generated it on a different on-prem |
| `MANIFEST_EXPIRED` | Manifest is more than 7 days old | Generate a fresh renewal request from the on-premise |

#### Cert upload failure modes

| Code | Cause | Fix |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | New cert's `genesisSequence` is ahead of local chain head | Upstream is on a forked chain - investigate |
| `CHAIN_FORK_ON_UPLOAD` | Chain hash at the cert's `genesisSequence` doesn't match local ledger | Local chain has diverged from upstream - investigate |
| `Signature verification failed` | Cert isn't signed by the configured `UPSTREAM_PUBLIC_KEY` | Check that `UPSTREAM_PUBLIC_KEY` matches the upstream master public key |

### 6. Status and monitoring

Query the on-premise local cert state at any time:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

Returns the loaded cert's `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry`, plus the `autoRenew` block (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Wire this into your monitoring stack to alert on stale `lastSuccessAt` or non-null `lastError`.

For backup and audit, the on-premise admin can also download the currently loaded signed cert via `GET /onprem/cert-current` (requires elevated session).

### Delegation cert env var reference

| Variable | Required? | Purpose |
|---|---|---|
| `ON_PREMISE_MODE` | Yes | Set to `true` to enable the on-premise route subset |
| `ON_PREMISE_PRIVATE_KEY` | Yes | Base64 PKCS8 Ed25519 private key for delegated signing |
| `ON_PREMISE_PUBLIC_KEY` | Yes | Base64 SPKI Ed25519 public key (must match the cert's `delegatedPublicKey`) |
| `DELEGATION_CERT_PATH` | One of these | Filesystem path to the signed cert JSON |
| `DELEGATION_CERT_BASE64` | One of these | Base64-encoded cert JSON (alternative to file path) |
| `UPSTREAM_PUBLIC_KEY` | Required if `UPSTREAM_API_KEY` is set, or for `/onprem/cert-upload` to work | Base64 SPKI of the upstream master public key. Fail-fast at boot if missing. |
| `UPSTREAM_URL` | For auto-renew | Upstream account server base URL, e.g. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | For auto-renew | A `delegation:renew`-scoped api token. Mint via the portal - see Step 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Optional | Default 24. How often to check whether the cert needs renewal. |
| `RENEW_THRESHOLD_DAYS` | Optional | Default 14. Acts as a ceiling on the adaptive 1/3-of-validity threshold. |

### Threat model summary

The delegation cert model defends against:

- **Forged licenses**: the on-premise can only sign within its plan limits; renet rejects anything outside the cert's bounds.
- **Cert sharing across deployments**: chain divergence is detected at renewal (returns `CHAIN_FORK_DETECTED`).
- **Quota bypass via multi-install**: enforced at the upstream by single-active (one cert per subscription).
- **Chain rollback**: renet stores the highest-sequence-seen per subscription and rejects any blob with a lower sequence.
- **Compromised upstream credentials**: the bootstrap `delegation:renew` token is mintable only via the dedicated portal endpoint and is admin-gated. The token grants only renewal - it cannot read or modify any other resource.
- **Replay attacks on manifests**: manifests older than 7 days are rejected.

What it does **not** defend against:

- **Compromised on-premise private key**: a leaked private key lets an attacker sign licenses up to the cert's `validUntil`. Mitigation: rotate the keypair (revoke old cert + create new with new key) and treat all licenses signed by the old key as suspect.
- **Compromised upstream master key**: this is the trust root. Rotation procedures are out of scope here.

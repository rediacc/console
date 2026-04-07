---
title: "License Chain & Delegation"
description: "Tamper-evident license issuance, delegated signing for on-premise, and fork detection."
category: "Guides"
order: 8
language: en
---

# License Chain & Delegation

Rediacc uses a tamper-evident hash chain for license issuance and a delegation certificate model for on-premise deployments. This page explains how the system protects against tampering, replay attacks, and license sharing.

## Why a Chain?

Every license issued by an account server is recorded in an append-only ledger. Each entry is linked to the previous one via a SHA-256 hash, forming a chain. The chain has three properties that make tampering detectable:

1. **Sequence numbers** are global and monotonic per subscription. Skipping or reordering entries breaks the chain.
2. **Chain hashes** bind each entry to all previous entries. Modifying any past entry invalidates every entry that follows.
3. **Renet stores the highest sequence it has seen** per subscription. A server that rolls back its sequence is detected immediately.

## How a License is Issued

When the CLI requests a machine activation or repo license, the account server:

1. Reads the current chain head (last sequence + hash) for the subscription.
2. Builds the license payload with the next sequence number and the previous chain hash baked in.
3. Signs the payload with Ed25519.
4. Computes `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Appends the entry to the issuance ledger atomically. If two concurrent requests collide on the same sequence, the loser re-acquires the next sequence and re-signs.
6. Returns the signed blob with the chain hash to the CLI.

The `sequence` and `prevChainHash` are inside the signed payload (so they cannot be modified without invalidating the signature). The `chainHash` is on the envelope (computed after signing to avoid a circular dependency).

## How Renet Validates

Each machine running Renet stores its last-known chain state at `{licenseDir}/chain-state.json`. On every license validation, Renet checks:

| Check | Failure means |
|---|---|
| Ed25519 signature is valid | License was forged or tampered |
| `sequence > lastKnownSequence` | Server rolled back the chain (replay attack) |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | Chain entry was modified |
| `issuedAt >= lastKnownIssuedAt` | Clock manipulation (server clock set backwards) |

If any check fails, the license is rejected and the failure reason is reported.

## Delegation Certificates (On-Premise)

For air-gapped or self-hosted deployments, the upstream account server issues a **delegation certificate** authorizing an on-premise server to sign licenses with its own Ed25519 key. The certificate constrains what the on-premise server can do.

### Cert structure

A delegation cert contains:

- `subscriptionId` -- which subscription this cert applies to
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- plan limits baked in
- `maxTotalIssuances` -- upper bound on the chain sequence number
- `delegatedPublicKey` -- the on-premise server's Ed25519 public key (SPKI base64)
- `genesisHash` -- the chain starting point (continuation from previous cert, or "genesis")
- `genesisSequence` -- chain sequence at issuance time. Used by `/onprem/cert-upload` to validate that the new cert links to a known entry in the local issuance ledger when the chain has advanced during transit. Optional for backward compatibility (treated as 0 if missing).
- `validFrom`, `validUntil` -- validity window (governed by the validity policy below)
- Signed by the upstream master Ed25519 key

### How delegation works

1. Enterprise admin generates an Ed25519 key pair on the on-premise server.
2. Admin requests a delegation cert from the upstream:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. Upstream signs the cert with its master key and returns it.
4. On-premise server stores the cert and its private key, ready to sign licenses.
5. When a CLI requests a license from the on-premise server, the server signs with its delegated key and includes a reference to the cert.
6. Renet performs **two-level validation**:
   - Verify the cert's signature against the baked-in upstream master key.
   - Verify the blob's signature against the delegated key from the cert.
   - Check that `blob.sequence <= cert.maxTotalIssuances`.
   - Apply all the standard chain checks.

The on-premise server cannot:
- Forge a license outside the delegation cert's plan limits (renet rejects it).
- Issue more than `maxTotalIssuances` total operations (renet rejects sequence overflow).
- Modify the cert (the upstream signature breaks).

## Validity Policy

The validity window of a delegation cert is computed by a shared policy helper (`computeDelegationCertValidity()`) that runs on both the upstream backend and the customer portal frontend. The same inputs always produce the same `validUntil`, so customers can preview the effective validity in the create modal before submitting.

### Per-plan defaults and ceilings

| Plan | Default validity | Plan ceiling |
|---|---|---|
| COMMUNITY | 15 days | 30 days |
| PROFESSIONAL | 60 days | 120 days |
| BUSINESS | 90 days | 180 days |
| ENTERPRISE | 120 days | 365 days |

The default is what the create endpoint picks when the caller omits `validDays`. The ceiling is the upper bound the caller can request.

### Per-subscription override

Admins can set a custom `delegationCertDefaultDays` value on a specific subscription via the admin Subscription Detail page. **The override replaces both the default AND the ceiling for that subscription** - it's an escape hatch for special customers (e.g. an enterprise contract that needs a 200-day cert on a COMMUNITY plan). The Zod schema still enforces an absolute `1..365` range.

### Hard cap: subscription end + 3 day grace

Independent of the plan ceiling and override, every cert is hard-capped at `subscription.expiresAt + 3 days` (the existing `SUBSCRIPTION_CONFIG.gracePeriodDays`). This means:

- For perpetual subscriptions (`expiresAt = null`), no expiry cap applies - only the plan ceiling.
- For Stripe-billed monthly subscriptions, the cap is roughly the next billing date + 3 days. When Stripe rolls `expiresAt` forward each month, the cap moves with it.
- For trial subscriptions, the cap is the trial end + 3 days.

### Effective days + reason

Every create/renew response includes `effectiveDays` and `reason` so the caller can see exactly why the cert got the validity it did:

| Reason | Meaning |
|---|---|
| `plan_default` | No request, no override → used the per-plan default |
| `subscription_override` | No request → used the per-subscription override as the default |
| `requested` | Caller request honored within all caps |
| `plan_max_clamp` | Caller request exceeded the per-plan ceiling - clamped down |
| `override_max_clamp` | Caller request exceeded the per-subscription override - clamped down |
| `subscription_cap_clamp` | Otherwise-valid target would outlive the subscription's `expiresAt + 3 days` |

The customer portal create modal uses these reasons to render a live preview ("You will receive a 18-day cert. Clamped because the cert cannot outlive your subscription end date by more than 3 days.") so customers don't submit blind.

### Adaptive renewal threshold

The on-premise auto-renew loop uses an adaptive threshold modeled after Let's Encrypt:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

A 15-day COMMUNITY cert renews at 5 days remaining. A 90-day BUSINESS cert renews at 14 days remaining (the env-configured ceiling kicks in). A 120-day ENTERPRISE cert renews at 14 days remaining. This prevents short-lived certs from triggering renewal immediately while still giving long-lived certs a comfortable buffer.

## Single-Active Enforcement

A subscription may have **at most one active delegation certificate at a time** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### Why one?

Each on-premise install enforces `maxRepoLicenseIssuancesPerMonth`, `maxActivations`, and chain integrity against its own local issuance ledger. The on-premise does not sync usage counts to the upstream - that's the whole point of offline-capable delegation.

If a subscription had multiple active certs (one per install), each install would enforce the limit independently:

- A 500/month subscription with 3 active certs allows up to **1,500 issuances/month** in practice.
- Three parallel chains, each anchored to genesis, with no possible audit reconciliation.

The upstream cannot detect this bypass because the on-prems are designed to operate offline. **Single-active is the only enforceable model.** Multi-install customers (production + staging + DR) must purchase one subscription per install.

### Collision behavior

`POST /admin/delegation-certs` and `POST /portal/delegation-certs` reject a second create with:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

The customer portal surfaces this with a dedicated dialog explaining the consequences:

- **Renew (recommended)** - extends the existing chain. All previously issued repo licenses keep working.
- **Revoke and Create** - discards the existing chain and starts fresh from genesis. Previously issued repo licenses become unverifiable once the OLD cert's `validUntil` passes. Use only when you've migrated to a new on-prem with a different signing key, or recovering from a compromised key.

`renew()` is the atomic swap that preserves single-active and is **not** subject to the 409 collision check.

### Rate limit

Even with single-active, a malicious caller could loop `revoke → create → revoke → create` to burn upstream master-key signature cycles. Both create endpoints throttle at **10 attempts per rolling 24h** per subscription via the existing `rateLimits` table:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

The counter increments on every attempt regardless of outcome (collision-spam loops are also throttled).

## Fork Detection

If a customer shares their delegation cert with another party (or runs two on-premise servers from the same cert), the chains diverge. The upstream detects this at renewal time.

### Renewal flow

1. On-premise admin calls `POST /admin/delegation-certs/renew` with the current chain head:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. Upstream walks the chain entries against its own ledger record.
3. If `currentChainHash` does not match the upstream's recorded chain at `currentSequence`, fork detected:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. The new cert's `genesisHash` is set to the current chain hash, so machines with the old chain state can continue from where they left off.

If the cert is shared with a non-customer:
- They can use it during the cert's validity period.
- At first renewal, the upstream sees only one chain (the legitimate one).
- The new cert's `genesisHash` only matches the legitimate chain.
- Machines on the shared chain will reject new licenses immediately because their stored `chainHash` doesn't connect to the new cert's `genesisHash`.

## Air-Gapped Renewal

For on-premise installs without outbound HTTPS access to the upstream, the renewal flow is fully offline. There are three new endpoints that close the loop:

**On the on-premise (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - download the currently loaded signed cert (backup, audit, re-import)
- `GET /onprem/renewal-request` - generate a signed manifest containing the local chain head + delegated public key, signed by the on-premise private key

**On the upstream (admin or org-scoped portal):**
- `POST /admin/delegation-certs/process-renewal-request` (cross-customer system root)
- `POST /portal/delegation-certs/process-renewal-request` (org owner/admin)

### Renewal request manifest

The renewal request is a small JSON document:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

The signature is computed over the canonical encoding of the manifest (keys sorted alphabetically, then `JSON.stringify`) using the on-premise private key. This guarantees both sides compute identical bytes regardless of object construction order.

### Verification at upstream

`processRenewalManifest()` runs five checks:

1. **Active cert exists** for the manifest's subscription. Returns `404 NO_ACTIVE_CERT` otherwise - the customer should use the create flow, not renew.
2. **Delegated public key matches** the active cert. Returns `400 DELEGATED_KEY_MISMATCH` otherwise - guards against replay from a different on-prem.
3. **Manifest signature verifies** against the active cert's `delegatedPublicKey`. Returns `400 MANIFEST_SIGNATURE_INVALID` otherwise - proves the manifest came from a holder of the on-premise private key.
4. **Manifest age** is within 7 days (`RENEWAL_MANIFEST_MAX_AGE_MS`). Returns `400 MANIFEST_EXPIRED` otherwise - anti-replay anchor.
5. **Chain hash linkage** at the manifest's `currentSequence` matches the upstream's ledger. Returns `409 CHAIN_FORK_DETECTED` otherwise - guards against forked chains.

If all checks pass, `processRenewalManifest` calls the existing `renew()` flow, which atomically expires the old cert and inserts a new one. **It is not subject to the create-side single-active 409** because it's an atomic swap, not a 2-step revoke+create.

### Sequence advancement during transit

A renewal request manifest captures the chain head at the moment of generation. While the manifest is in transit (USB delivery, encrypted email), the on-premise may keep issuing repo licenses, advancing its local chain.

When the new cert is uploaded back to the on-premise, `/onprem/cert-upload` validates that the new cert's `genesisSequence` still links to a known entry in the local issuance ledger:

- If `cert.genesisSequence > localHead.sequence` → returns `409 CHAIN_HEAD_BEHIND` (upstream is on a forked chain).
- If `cert.genesisSequence > 0` and the local ledger entry at that sequence has a different `chainHash` than `cert.genesisHash` → returns `409 CHAIN_FORK_ON_UPLOAD` (local chain has diverged).
- Otherwise, the cert is accepted. Future issuances continue from `localHead.sequence + 1`.

This means **no write freeze is required during transit**. The chain extends naturally on both sides. Matches how X.509 cert renewal handles in-flight serial numbers.

## Periodic Audit

The upstream provides an audit endpoint to verify chain integrity without renewing the cert:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

The upstream walks the entries and returns either `{ valid: true }` or `{ valid: false, divergedAtSequence: N, expected, actual }`.

On-premise servers should call this endpoint periodically (default: weekly via `UPSTREAM_AUDIT_URL` env var) to detect forks early.

### Machine-side audit proofs

Renet can verify chain continuity locally using `VerifyAuditProof`. When a machine renews its license after a long gap, the server can return the intermediate chain entries as a proof. The machine walks the proof to verify each `chainHash` derives from the previous `prevHash + blobHash` via SHA-256, catching any tampering without contacting the upstream.

## Concurrency Safety

D1 (Cloudflare's database) does not support interactive transactions. Concurrent license issuance for the same subscription could collide on the sequence number. The account server handles this by:

1. Reading the next sequence + previous chain hash.
2. Building and signing the blob with that sequence baked in.
3. Inserting the ledger entry with `onConflictDoNothing`.
4. If the insert returns 0 rows changed, sequence was claimed by another request -- re-acquire the sequence, re-build, **re-sign**, and retry.
5. After 10 failed attempts, fail with an error.

The critical detail: the retry **re-signs** the blob. A naive retry that only updated the ledger entry would leave the signed blob with a stale sequence number, breaking the chain.

## Email Transport

The account server can send transactional emails (magic links, password resets, security notifications) via two pluggable transports:

| Transport | Configuration |
|---|---|
| `ses` (default) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Both transports work for cloud and on-premise deployments. Choose whichever fits your infrastructure: AWS SES with your own AWS account, or any SMTP server (Microsoft Exchange, Postfix, SendGrid, Mailgun, etc.).

The transport is selected at startup via the `EMAIL_TRANSPORT` environment variable. SMTP uses connection pooling and lazy loading, so the SMTP client library is only initialized if SMTP is selected.

All email templates and the public email API are identical across transports.

## Related Documentation

- [On-Premise Installation](/en/docs/on-premise) -- how to deploy the on-premise server
- [Subscription & Licensing](/en/docs/subscription-licensing) -- plan limits and machine slots
- [Release Channels](/en/docs/release-channels) -- edge vs stable channels
- [Data Regions](/en/docs/data-regions) -- regional data residency

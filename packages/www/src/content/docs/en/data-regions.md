---
title: "Data Regions"
description: "Where your data is stored and how regional data residency works."
category: "Concepts"
order: 3
language: en
---

When you sign up for Rediacc, you pick a data region. All your data stays there. That choice is permanent: you can't change it after sign-up. No migration path exists. Pick based on where your data needs to reside legally, not where your servers are today.

## Available Regions

| Region | Location | Domain |
|---|---|---|
| **Europe (EU)** | Frankfurt, Germany | `eu.rediacc.com` |
| **United States (US)** | Virginia, USA | `us.rediacc.com` |
| **Asia Pacific** | Tokyo, Japan | `asia.rediacc.com` |

Your region is auto-detected from your timezone at sign-up. You can override the suggestion in the region picker.

## What Stays in Your Region

These data types are stored and processed exclusively in your chosen region:

- **Account data**: email, name, organization, team memberships
- **Billing and subscription records**: plan, activations, license issuances
- **Encrypted configuration blobs**: zero-knowledge encrypted, client-side. The server cannot decrypt them.
- **Transactional emails**: password resets, magic links, notifications. Sent from a regional email endpoint.

## What Is Global

These are not region-specific:

- **CLI release artifacts**: public binaries hosted on a global CDN
- **Marketing website**: served globally from edge locations
- **Stripe payment processing**: handled by Stripe's own infrastructure under their data processing agreement

## Regional Infrastructure

| Component | EU | US | Asia |
|---|---|---|---|
| Database (D1) | Eastern Europe (EEUR) | Eastern North America (ENAM) | Asia Pacific (APAC) |
| Config storage (R2) | EU jurisdiction | US | Asia Pacific |
| Email (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Each region runs independent infrastructure. There are no cross-region queries or data flows between regions.

## EU Data Guarantees

Look: if you're subject to European data residency requirements, the EU region adds specific guarantees:

- **D1 database**: runs in Eastern Europe (EEUR location hint)
- **R2 config storage**: uses EU jurisdictional enforcement (contractual guarantee, not just a location hint)
- **Email**: sent from Frankfurt (eu-central-1)
- **EU-Japan mutual adequacy decision (2019)**: enables compliant data flows for the Asia region's infrastructure

For detailed GDPR mapping, see [GDPR Compliance](/en/docs/legal-gdpr).

## Zero-Knowledge Encryption

Configuration blobs stored in R2 are encrypted client-side before upload using X25519 key exchange and AES-256-GCM. The server holds only ciphertext. Neither Rediacc nor any infrastructure provider can read your configuration data.

Keys derive from a passkey with PRF extension. The server stores a secret that participates in key derivation, but neither the passkey alone nor the server secret alone can decrypt the data.

For details on the encryption architecture, see [Config Storage](/en/docs/config-storage).

## How to Choose

- **Pick the region closest to you** for the lowest latency.
- **Pick the region your organization requires** for compliance. If your company mandates EU data residency, choose EU.
- **The choice is permanent.** You cannot move your account to a different region after sign-up.

## For Compliance Officers

Technical properties of the regional architecture:

- **Separate databases per region**: each region has its own Cloudflare D1 database. No cross-region queries.
- **Separate storage per region**: each region has its own R2 bucket. EU uses jurisdictional enforcement.
- **Email delivery via AWS SES**: transactional emails are sent via AWS SES. EU and US use dedicated regional endpoints; Asia Pacific routes through the EU endpoint (eu-central-1).
- **One user, one region**: a user account exists in exactly one region. It cannot span multiple regions.
- **Webhook isolation**: Stripe webhook events are received by all regional workers but only processed by the region that owns the customer record.
- **Zero-knowledge config encryption**: the server cannot read configuration data. Encryption keys never leave the client device.

For a broader view of data sovereignty compliance, see [Data Sovereignty](/en/docs/legal-data-sovereignty).

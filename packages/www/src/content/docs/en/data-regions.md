---
title: "Data Regions"
description: "Where your data is stored and how regional data residency works."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: en
---

When you sign up for Rediacc, you pick a data region. All your data stays there. That choice is permanent: you can't change it after sign-up. No migration path exists. Pick based on where your data needs to reside legally, not where your servers are today.

## Available Regions

| Region | Location | Domain |
|---|---|---|
| **Europe (EU)** | European Union | `eu.rediacc.cloud` |
| **United States (US)** | Eastern North America | `us.rediacc.cloud` |
| **Asia Pacific** | Asia Pacific | `asia.rediacc.cloud` |

The location column names a Cloudflare region, not a data-centre city. Cloudflare does not promise a city.

The product runs on these `rediacc.cloud` domains. All documentation and the marketing site live on `www.rediacc.com`, which sends visitors to the right region from its region picker.

At sign-up, the picker suggests a region from the visitor's location, which can be confirmed or changed. At login, it forwards the visitor to the right region after a short countdown that can be cancelled or changed. If a company has its own deployment, the picker's "Enterprise customer?" option leads there from the visitor's work email. Only the domain is sent to find the region; the email only pre-fills the sign-in page.

## What Stays in Your Region

These data types are stored and processed in the chosen region, except that Asia Pacific transactional email is sent through the EU endpoint (see Regional Infrastructure below for what is guaranteed):

- **Account data**: email, name, organization, team memberships
- **Billing and subscription records**: plan, activations, license issuances
- **Encrypted configuration blobs**: zero-knowledge encrypted, client-side. The server cannot decrypt them.
- **Transactional emails**: password resets, magic links, notifications. Sent from a regional email endpoint.

## What Is Global

These are not region-specific:

- **CLI release artifacts**: public binaries hosted on a global CDN
- **Marketing website and documentation**: `www.rediacc.com`, served globally from edge locations
- **Stripe payment processing**: handled by Stripe's own infrastructure under their data processing agreement

## Regional Infrastructure

| Component | EU | US | Asia |
|---|---|---|---|
| Database (D1) | Eastern Europe hint (EEUR) | Eastern North America hint (ENAM) | Asia Pacific hint (APAC) |
| Config storage (R2) | EU jurisdiction (guaranteed) | No jurisdiction (best effort) | No jurisdiction (best effort) |
| Email (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Only the EU config storage is held to a guaranteed jurisdiction: Cloudflare restricts R2 objects under the EU jurisdiction to the EU. D1 database placement and the US and Asia Pacific storage use location hints, which are best effort. Cloudflare does not guarantee they run in the hinted region.

Each region runs independent infrastructure. There are no cross-region queries or data flows between regions.

## EU Data Guarantees

For European data residency requirements, the EU region adds one hard guarantee and some best-effort placement:

- **D1 database**: placed with the EEUR (Eastern Europe) location hint, which is best effort and not a guarantee
- **R2 config storage**: held to the EU jurisdiction, which Cloudflare guarantees (a hard restriction, not just a location hint)
- **Email**: sent from Frankfurt (eu-central-1)

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
- **Separate storage per region**: each region has its own R2 bucket. Only the EU bucket is held to a jurisdiction; US and Asia Pacific use best-effort placement.
- **Email delivery via AWS SES**: transactional emails are sent via AWS SES. EU and US use dedicated regional endpoints; Asia Pacific routes through the EU endpoint (eu-central-1).
- **One user, one region**: a user account exists in exactly one region. It cannot span multiple regions.
- **Webhook isolation**: Stripe webhook events are received by all regional workers but only processed by the region that owns the customer record.
- **Zero-knowledge config encryption**: the server cannot read configuration data. Encryption keys never leave the client device.

For a broader view of data sovereignty compliance, see [Data Sovereignty](/en/docs/legal-data-sovereignty).

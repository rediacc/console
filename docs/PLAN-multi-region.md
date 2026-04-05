# Multi-Region Data Residency Plan

Status: **Draft** | Created: 2026-04-04 | Updated: 2026-04-04

## Completed Pre-work

### AWS SES multi-region (done 2026-04-04)

- Created IAM user `rediacc-ses-eu` with policy `SES-SendOnly-EU` scoped to `eu-central-1`
- Created IAM user `rediacc-ses-us` with policy `SES-SendOnly-US` scoped to `us-east-1`
- Verified domain `notify.rediacc.com` in SES `us-east-1` (DKIM SUCCESS)
- Added 3 DKIM CNAME records to Cloudflare DNS for us-east-1
- SES production access granted in `us-east-1`
- GitHub org secrets set: `AWS_SES_ACCESS_KEY_ID_US`, `AWS_SES_SECRET_ACCESS_KEY_US`
- GitHub org variable set: `AWS_SES_REGION_US=us-east-1`
- Updated `scripts/dev/rotate-secrets.sh` to rotate both EU and US IAM users with region-aware worker sync
- Scoped legacy `rediacc-ses-worker` IAM policy to `eu-central-1` only (was previously unrestricted)

**Legacy cleanup (done):** IAM user `rediacc-ses-worker` deleted. All access keys, policy, and user object removed. GitHub secrets/variables renamed from unsuffixed to `_EU` suffix for consistency with `_US`. All 6 workflow files updated. Old unsuffixed secrets/variables deleted.

### Stripe multi-region secrets (done 2026-04-04)

- Created `STRIPE_SECRET_KEY_EU`, `STRIPE_PUBLISHABLE_KEY_EU`, `STRIPE_WEBHOOK_SECRET_EU` GitHub secrets
- Created `STRIPE_SECRET_KEY_US`, `STRIPE_PUBLISHABLE_KEY_US`, `STRIPE_WEBHOOK_SECRET_US` GitHub secrets
- **Both EU and US point to the same Stripe account** (Rediacc OU via SPEL, Ireland) for now
- When a US entity is created (e.g., via Stripe Atlas), swap the `_US` secrets to the new account's keys -- zero code changes
- Sandbox secrets (`STRIPE_SANDBOX_*`) stay unsuffixed (single sandbox, not regional)
- Updated all workflow references: `cd-deploy-worker.yml`, `cd-v2.yml`, `promote-stable.yml`
- Deleted old unsuffixed secrets: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`

---

## Problem

Rediacc is an Estonian company (Rediacc OU, Tallinn). All customer data must be stored in the region the customer chooses. The current architecture stores everything in a single set of Cloudflare resources with no region distinction:

| Resource | Current Name | Current Location |
|---|---|---|
| Account DB | `account-db` | EEUR |
| Config store | `rediacc-configs` | **ENAM (USA)** |
| Edge account DB | `edge-account-db` | EEUR |
| Edge config store | `edge-rediacc-configs` | **ENAM (USA)** |
| Releases | `rediacc-releases` | ENAM |
| AWS SES | eu-central-1 | EU |
| Stripe | Single account | USA |

The config store R2 buckets are in the US, and there is no way for users to choose where their data lives. All account data (D1) and config blobs (R2) go to the same place regardless of the user's jurisdiction.

## Goal

Users pick a data region at org creation. All their data (account records, billing, encrypted config blobs, transactional emails) stays in that region. Each region is a fully independent deployment with its own domain, database, object storage, email infrastructure, and payment processor account.

Launch with two regions: **EU** and **US**. Architecture must support adding more (e.g., Asia) without code changes.

---

## Key Decisions

### 1. Domain-based region separation (not KV router)

Each region gets its own subdomain: `eu.rediacc.com`, `us.rediacc.com`.

**Why not a KV-based global router?**
- If the router goes down, all regions go down (single point of failure).
- A domain-based approach is transparent to users. The URL itself tells them where their data lives.
- Each regional deployment is fully independent: its own Worker, D1, R2, secrets. One region's outage cannot cascade to another.
- Simpler to implement. Each Worker has exactly one D1 binding and one R2 binding. No runtime region detection or multi-binding routing logic.
- Independent deploys: can update EU without touching US.

`www.rediacc.com` stays as the marketing site (docs, pricing, downloads, install script). It has no account data. The sign-up flow on `www` presents a region picker and redirects to the chosen regional domain.

### 2. D1 databases split per region (not centralized)

Each region has its own D1 database (`account-db-eu`, `account-db-us`).

**Why not a single centralized D1 in EU?**
- If a US customer explicitly chooses "US region", they expect all their data in the US, not just config blobs. Their email, org name, billing history, subscription records sitting in an EU database is a compliance problem.
- US enterprise customers may have internal policies or contractual obligations requiring US data residency. Sector-specific regulations (ITAR, FedRAMP-adjacent, healthcare) can mandate US jurisdiction.
- Future regions (Asia, Turkey) have even stricter localization laws (China's PIPL, Turkey's KVKK). A centralized-DB model wouldn't survive expansion.
- From a sales perspective, "your configs are in US but your account data is in EU" is confusing and hard to sell.
- The domain-based separation makes this natural: each Worker has exactly one D1, no cross-region query routing needed.

### 3. One user = one region

A user account exists in exactly one regional database. They cannot simultaneously belong to orgs in different regions.

**Why?**
- Avoids cross-region data scatter (data about the same person in two jurisdictions).
- Eliminates the need for cross-region auth lookups.
- Simplifies the data model: the regional Worker is the complete authority for that user.

**Org invitation handling:** When a user is invited to an org, the org's region determines where the user's account lives. If the invitee already has an account in a different region, the invitation is blocked with a clear error explaining the constraint.

### 4. Region is immutable after org creation

Once an org is created in a region, it cannot be moved to another region through the UI.

**Why?**
- Moving an org means migrating D1 rows + R2 blobs across regions, updating the user's CLI remote config, re-provisioning Stripe subscription under a different Stripe account, etc. This is a complex, error-prone operation.
- For the rare case where migration is needed, a manual admin process (export + import + DNS change) is acceptable. The system should not be designed around this edge case.

### 5. Separate Stripe accounts per region

EU account (contracts with Stripe Payments Europe Limited, Ireland) and US account (contracts with Stripe Inc.).

**Why?**
- EU Stripe account stores core payment data at rest in the EU (Stripe's EU data residency, available since 2023).
- US Stripe account avoids ~1-1.5% cross-border fee surcharge on US card transactions.
- PSD2/SCA (Strong Customer Authentication) applies to EEA transactions. Stripe handles this automatically on the EU account. US transactions don't need SCA.
- Separate accounts give clean regulatory separation. Each regional Worker gets its own `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.

**No code changes needed.** The current `getStripe(apiKey)` in `private/account/src/utils/stripe.ts` is already parameterized. The API key from Worker secrets determines which Stripe account is used.

### 6. Separate AWS SES regions

EU Worker sends email via SES `eu-central-1` (Frankfurt). US Worker sends via SES `us-east-1` (Virginia).

**Why?**
- Email content (password resets, invoices, billing notices) is personal data under GDPR.
- SES processes and temporarily stores email in the sending region. Using a regional SES endpoint keeps email processing in the user's chosen jurisdiction.
- Same domain (`notify.rediacc.com`) can be verified in both SES regions.

**No code changes needed.** The `EmailService` constructor in `private/account/src/services/email.service.ts` already takes `sesRegion` as config. The endpoint is built dynamically: `https://email.${sesRegion}.amazonaws.com/v2/email/outbound-emails`. Each regional Worker just gets different `AWS_SES_REGION` env vars.

### 7. Marketing site separated from account service

Currently, `workers/www` serves both the marketing site (Astro static pages) and the account service (Hono API + SPA). The entry point (`workers/www/src/index.ts`) imports `createApp` from `private/account/src/app.ts` and routes `/account/*` to it.

This splits into:
- `workers/www` -- marketing site only (Astro pages, install script, smart redirects). No D1, no R2 config bucket, no account imports.
- `workers/account` -- account portal + API, deployed once per region. Each deployment has its own D1 + R2 + Stripe + SES config.

**Why?**
- The marketing site has no customer data. It doesn't need regional deployment.
- The account service needs regional isolation. Keeping it in the same Worker as marketing would mean deploying marketing redundantly per region.
- Clean separation of concerns. Marketing changes don't touch account code and vice versa.

### 8. The existing CLI `region` field is NOT data residency

The `region` field in `RdcConfig` (line ~286 in `packages/cli/src/types/index.ts`) and the `REDIACC_REGION` env var are for infrastructure labeling: which cloud provider region to create VMs in (e.g., Linode `us-ord`). This field is part of the `team/region/bridge` triplet for the cloud adapter's resource filtering.

Data residency is a new concept. It will live in `remote.dataRegion` in the CLI config (informational, populated from the account server during config storage setup) and as `data_region` on the `organizations` table in D1.

### 9. PR previews stay single-region

PR preview deployments (`pr-N.rediacc.workers.dev`) use a single D1 database in EEUR. No multi-region for previews.

**Why?**
- Preview databases contain test data, not real customer data.
- They are short-lived (created on PR open, deleted on PR close).
- Adding multi-region to previews would multiply infrastructure for zero compliance benefit.

### 10. Releases bucket stays in ENAM (no regional split)

`rediacc-releases` contains public CLI/desktop binaries and Linux package repos. No personal data.

**Why keep it centralized?**
- Public artifacts with no PII or customer data.
- ENAM (Virginia) has the best connectivity for global downloads.
- Cloudflare CDN edge-caches the content globally regardless of origin bucket location.

---

## Resource Inventory

### Production

| Resource | Type | Name | Domain | Location | Purpose |
|---|---|---|---|---|---|
| Marketing site | Worker | `rediacc-www` | www.rediacc.com | Global | Docs, pricing, downloads, install script |
| Releases | R2 | `rediacc-releases` | releases.rediacc.com | ENAM | Public CLI/desktop binaries |
| **EU account** | **Worker** | **`rediacc-eu`** | **eu.rediacc.com** | **Global** | **Account portal + API** |
| EU account DB | D1 | `account-db-eu` | -- | EEUR | Users, orgs, billing, config metadata |
| EU config store | R2 | `rediacc-configs-eu` | -- | EEUR | Encrypted config blobs |
| **US account** | **Worker** | **`rediacc-us`** | **us.rediacc.com** | **Global** | **Account portal + API** |
| US account DB | D1 | `account-db-us` | -- | ENAM | Users, orgs, billing, config metadata |
| US config store | R2 | `rediacc-configs-us` | -- | ENAM | Encrypted config blobs |

### Edge

| Resource | Type | Name | Domain | Location |
|---|---|---|---|---|
| Marketing site | Worker | `edge-rediacc-www` | edge.rediacc.com | Global |
| EU account | Worker | `edge-rediacc-eu` | edge-eu.rediacc.com | Global |
| EU account DB | D1 | `edge-account-db-eu` | -- | EEUR |
| EU config store | R2 | `edge-rediacc-configs-eu` | -- | EEUR |
| US account | Worker | `edge-rediacc-us` | edge-us.rediacc.com | Global |
| US account DB | D1 | `edge-account-db-us` | -- | ENAM |
| US config store | R2 | `edge-rediacc-configs-us` | -- | ENAM |

### PR Preview

| Resource | Type | Name | Location | Notes |
|---|---|---|---|---|
| Full preview | Worker | `pr-N` | Global | Single deployment, marketing + account combined |
| Preview DB | D1 | `account-db-pr-N` | EEUR | Short-lived, `--location eeur` |

### External Services

| Service | EU Region | US Region | Notes |
|---|---|---|---|
| AWS SES | eu-central-1 (Frankfurt) | us-east-1 (Virginia) | Same domain verified in both, separate IAM credentials |
| Stripe | SPEL account (Ireland) | Stripe Inc. account (US) | Separate API keys, separate webhook secrets |
| GHCR | USA | USA | Container images, no PII, no split needed |
| OTLP | EU (otlp.rediacc.io) | EU | Telemetry, single endpoint acceptable |
| Releases R2 | ENAM | ENAM | Public artifacts, no PII, no split needed |

### GitHub Secrets (per-region)

Current secrets that become per-region:

| Current Secret | EU Secret | US Secret |
|---|---|---|
| `STRIPE_SECRET_KEY` | `STRIPE_SECRET_KEY_EU` | `STRIPE_SECRET_KEY_US` |
| `STRIPE_WEBHOOK_SECRET` | `STRIPE_WEBHOOK_SECRET_EU` | `STRIPE_WEBHOOK_SECRET_US` |
| `STRIPE_PUBLISHABLE_KEY` | `STRIPE_PUBLISHABLE_KEY_EU` | `STRIPE_PUBLISHABLE_KEY_US` |
| `STRIPE_SANDBOX_SECRET_KEY` | Stays (edge/sandbox is EU-only) | -- |
| `STRIPE_SANDBOX_WEBHOOK_SECRET` | Stays | -- |
| `AWS_SES_ACCESS_KEY_ID` | `AWS_SES_ACCESS_KEY_ID_EU` | `AWS_SES_ACCESS_KEY_ID_US` |
| `AWS_SES_SECRET_ACCESS_KEY` | `AWS_SES_SECRET_ACCESS_KEY_EU` | `AWS_SES_SECRET_ACCESS_KEY_US` |

Secrets that stay global (shared across all regions):

| Secret | Reason |
|---|---|
| `ACCOUNT_ED25519_*` | Subscription/license signing (same keys across regions) |
| `ACCOUNT_X25519_*` | E2E encryption (same keys) |
| `ACCOUNT_JWT_SECRET` | Session tokens (could split later, but JWTs are self-contained) |
| `ACCOUNT_SERVER_API_KEY` | Admin API key |
| `CLOUDFLARE_API_TOKEN` | Infrastructure management |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Release uploads only |
| `APP_PRIVATE_KEY` | GitHub App |
| `TURNSTILE_SECRET_KEY` | Bot protection (global) |

**Open question:** Should `ACCOUNT_JWT_SECRET` be per-region? If a JWT from EU leaks to US, it shouldn't be accepted. Per-region secrets prevent cross-region token replay. Likely yes for production; can defer to implementation.

---

## Region Registry (single source of truth)

File: `.ci/regions.json`

Consumed by: deploy scripts (bash), wrangler config templates, account service (TypeScript), portal UI (React), CLI (for display).

```json
{
  "regions": {
    "eu": {
      "label": "Europe",
      "locationHint": "eeur",
      "suffix": "-eu",
      "domain": "eu.rediacc.com",
      "edgeDomain": "edge-eu.rediacc.com",
      "workerName": "rediacc-eu",
      "edgeWorkerName": "edge-rediacc-eu",
      "ses": {
        "region": "eu-central-1"
      },
      "stripe": {
        "entity": "Stripe Payments Europe, Limited (Ireland)"
      },
      "default": true
    },
    "us": {
      "label": "North America",
      "locationHint": "enam",
      "suffix": "-us",
      "domain": "us.rediacc.com",
      "edgeDomain": "edge-us.rediacc.com",
      "workerName": "rediacc-us",
      "edgeWorkerName": "edge-rediacc-us",
      "ses": {
        "region": "us-east-1"
      },
      "stripe": {
        "entity": "Stripe, Inc. (US)"
      },
      "default": false
    }
  },
  "defaultRegion": "eu",
  "global": {
    "www": "www.rediacc.com",
    "edgeWww": "edge.rediacc.com",
    "releases": "rediacc-releases",
    "releasesLocation": "ENAM"
  }
}
```

**Adding a future region** (e.g., Asia):
1. Add entry to `regions.json`.
2. Create Cloudflare resources: D1 database, R2 bucket (production + edge).
3. Create `wrangler.asia.toml` in `workers/account/`.
4. Set up DNS: `asia.rediacc.com` CNAME.
5. Verify SES domain in the new SES region, request production access.
6. Create Stripe account for the region (if needed).
7. Add GitHub secrets for the new region's Stripe + SES keys.
8. Deploy. No code changes required.

---

## Architecture: Current vs Proposed

### Current (single Worker serves everything)

```
www.rediacc.com ─── workers/www ──┬── Astro static pages (marketing, docs)
                                  ├── /account/*  SPA (portal)
                                  ├── /account/api/* Hono app (account API)
                                  ├── D1: account-db (EEUR)
                                  └── R2: rediacc-configs (ENAM)
```

Entry point: `workers/www/src/index.ts` imports `createApp()` from `private/account/src/app.ts`, routes `/account/api/*` to Hono, serves `/account/*` as SPA, everything else as static assets.

### Proposed (separated Workers)

```
www.rediacc.com ──── workers/www ──── Astro static pages only
                                      No D1, no R2 config bucket
                                      Region picker on sign-up page

eu.rediacc.com ──── workers/account (wrangler.eu.toml)
                     ├── /account/*  SPA
                     ├── /account/api/* Hono app
                     ├── D1: account-db-eu (EEUR)
                     ├── R2: rediacc-configs-eu (EEUR)
                     ├── SES: eu-central-1
                     └── Stripe: SPEL keys

us.rediacc.com ──── workers/account (wrangler.us.toml)
                     ├── /account/*  SPA
                     ├── /account/api/* Hono app
                     ├── D1: account-db-us (ENAM)
                     ├── R2: rediacc-configs-us (ENAM)
                     ├── SES: us-east-1
                     └── Stripe: Stripe Inc. keys

Edge mirrors the same pattern:
edge.rediacc.com      ─── edge marketing
edge-eu.rediacc.com   ─── edge account (EU)
edge-us.rediacc.com   ─── edge account (US)
```

Same account service codebase (`private/account/src/`), same Worker entry point (`workers/account/src/index.ts`). The only difference per region is the wrangler.toml (different resource bindings) and secrets (different Stripe/SES keys).

---

## Implementation Phases

### Phase 0: Pre-configuration (external services)

No code changes. Set up the external infrastructure that takes time.

- [ ] **Stripe US account**: Create a new Stripe account registered in the US. Set up products/prices that mirror the EU account. Note the API keys.
- [ ] **AWS SES US region**: Verify `notify.rediacc.com` domain in SES `us-east-1`. Request production access (can take 24-48h). Create IAM credentials scoped to `us-east-1`.
- [ ] **AWS SES EU credentials**: Create separate IAM credentials scoped to `eu-central-1` (currently using a single set).
- [ ] **Cloudflare DNS**: Create DNS records for `eu.rediacc.com`, `us.rediacc.com`, `edge-eu.rediacc.com`, `edge-us.rediacc.com`. These can be proxied CNAME records pointing nowhere initially (or placeholder Workers).
- [ ] **GitHub secrets**: Add the new per-region secrets (`STRIPE_SECRET_KEY_EU`, `STRIPE_SECRET_KEY_US`, `AWS_SES_ACCESS_KEY_ID_EU`, `AWS_SES_ACCESS_KEY_ID_US`, etc.). Keep old secrets until migration is complete.

### Phase 1: Region registry and infrastructure

- [ ] Create `.ci/regions.json` with EU and US entries.
- [ ] Create Cloudflare D1 databases: `account-db-eu`, `account-db-us`, `edge-account-db-eu`, `edge-account-db-us` (with appropriate `--location` hints).
- [ ] Create Cloudflare R2 buckets: `rediacc-configs-eu` (EEUR), `rediacc-configs-us` (ENAM), `edge-rediacc-configs-eu` (EEUR), `edge-rediacc-configs-us` (ENAM).
- [ ] Apply D1 migrations to all new databases.

### Phase 2: Split Workers

- [ ] Create `workers/account/` directory with its own `package.json`, `tsconfig.json`, `src/index.ts`.
- [ ] The new `workers/account/src/index.ts` handles only `/account/*` routes (API + SPA). It imports `createApp()` from `private/account/src/app.ts` (same as current `workers/www/src/index.ts` does, but without the Astro asset serving).
- [ ] Create `wrangler.eu.toml` and `wrangler.us.toml` in `workers/account/`. Each references its regional D1 + R2.
- [ ] Create `wrangler.edge-eu.toml` and `wrangler.edge-us.toml` for edge deployments.
- [ ] Strip account imports from `workers/www/src/index.ts`. The www Worker becomes a pure static asset server with smart redirects. Remove D1 and R2 bindings from `workers/www/wrangler.toml`.
- [ ] Update `workers/www/wrangler.toml` and `workers/www/wrangler.edge.toml` to remove D1/R2 bindings.

### Phase 3: Account service changes

- [ ] **D1 schema migration**: Add `data_region TEXT NOT NULL DEFAULT 'eu'` to `organizations` table.
- [ ] **Org service**: Accept `dataRegion` parameter in `createOwnedOrg()`. Validate against known regions (could import from regions.json or have a small allowlist). Store in the `organizations` row.
- [ ] **Org invitation flow**: When accepting an invite, check if the invitee already has an account. If they do and it's in a different region, return an error. If they don't, create the account in the org's region (which is the current Worker's region -- inherently correct since each regional Worker only writes to its own D1).
- [ ] **Config storage**: No changes needed. The `CONFIG_BUCKET` binding already routes to the correct R2 bucket per wrangler config. The `ConfigService` uses whatever `BlobStorageService` is injected.
- [ ] **Email service**: No changes needed. `sesRegion` is already injected from env vars.
- [ ] **Stripe/billing service**: No changes needed. `STRIPE_SECRET_KEY` is already injected from env vars.
- [ ] **Account portal API**: Add a `GET /account/api/v1/region` endpoint that returns the current Worker's region (from an env var like `DATA_REGION=eu`). The portal UI can display this.

### Phase 4: Portal UI changes

- [ ] **Org creation modal** (`private/account/web/src/pages/Team.tsx`): This no longer needs a region selector. The region is implicit from the domain (eu.rediacc.com = EU org). The modal can show "Your data will be stored in Europe" as informational text based on the current domain.
- [ ] **Org settings page**: Display the data region as read-only info: "Data region: Europe (eu.rediacc.com)".
- [ ] **Config storage setup**: Show region alongside store info.
- [ ] **www marketing site**: Add a region picker to the sign-up/get-started page. Two buttons or a dropdown: "Europe" -> redirects to eu.rediacc.com/account, "North America" -> redirects to us.rediacc.com/account.

### Phase 5: CLI changes

- [ ] **Remote config**: Add `dataRegion` field to `RemoteConfig` type in `packages/cli/src/types/index.ts`. This is informational (populated from the server during config storage setup, stored in `remote.dataRegion`).
- [ ] **`remote.apiUrl`**: During config storage setup, the CLI connects to the regional domain. The `apiUrl` in remote config naturally reflects the region: `https://eu.rediacc.com/account/api/v1`.
- [ ] **Display**: Show data region in `rdc config show` output and `rdc config remote status`.
- [ ] **No region selector in CLI**: The CLI doesn't pick a region. The user picks it in the portal when creating their org. The CLI just connects to whatever `apiUrl` was configured during setup.

### Phase 6: Deploy pipeline changes

- [ ] **`deploy-www.sh`**: Update to only deploy the marketing Worker. Remove D1 migration steps. Remove account-related secret injection.
- [ ] **New `deploy-account.sh`**: Deploy the account Worker for a given region. Accepts `--region eu|us`. Reads `regions.json` to resolve wrangler config, resource names, and secrets. Applies D1 migrations. Injects regional secrets.
- [ ] **`cd-deploy-worker.yml`**: Update to deploy marketing once, then account for each region. Loop over regions from `regions.json`.
- [ ] **`cd-v2.yml`**: Update to set region-specific Worker secrets per deployment. The `Set Worker secrets` step needs to run per region with different Stripe/SES values.
- [ ] **`clone-d1.sh`**: Update to support cloning per-region: `clone-d1.sh --source account-db-eu --target edge-account-db-eu`, etc.
- [ ] **`edge-clone-d1.yml`**: Update to clone each regional DB separately.
- [ ] **PR preview (`deploy-www.sh --name pr-N`)**: Keep as single-region. The preview Worker combines marketing + account (like today) but only uses one EU D1. This avoids preview complexity.
- [ ] **Stripe sync/verify scripts**: Update to run per-region Stripe account. The `stripe-sync.ts` and `verify-webhook.ts` scripts need to handle multiple Stripe keys.
- [ ] **Housekeeping**: Update to clean up resources in all regions.

### Phase 7: Migration of existing data

- [ ] Rename/migrate current `account-db` data to `account-db-eu` (or recreate and clone).
- [ ] Migrate `rediacc-configs` R2 blobs to `rediacc-configs-eu`.
- [ ] Same for edge resources.
- [ ] Delete old resources after verification.
- [ ] Update DNS: `www.rediacc.com` points to the new marketing-only Worker. `eu.rediacc.com` points to the EU account Worker.

---

## Legal Context (for reference)

### GDPR (EU)
- Does NOT strictly require data to stay in the EU. Requires "adequate protection" for cross-border transfers.
- EU-US Data Privacy Framework (DPF) adopted July 2023 provides legal basis for EU-to-US transfers.
- DPF is fragile: based on a US Executive Order that can be revoked. Potential "Schrems III" challenge exists.
- Best practice: keep EU user data in the EU to eliminate transfer risk entirely.
- Transactional emails (password resets, invoices) are legal under Art. 6(1)(b) -- "performance of a contract."
- Zero-knowledge encryption is recognized by EDPB as an effective supplementary measure for data transfers.

### EU Data Act (applying since September 2025)
- Art. 32: cloud providers must protect against unauthorized foreign government access to EU data. Zero-knowledge encryption satisfies this.
- Art. 23-31: data portability and switching obligations. Must offer data export.

### US
- No federal data residency or localization law.
- State privacy laws (CCPA/CPRA, VCDPA, etc.) do not mandate data location. They require "reasonable security."
- Sector-specific: FedRAMP effectively requires US residency for federal data. HIPAA does not mandate location but BAAs are needed.
- Offering "US region" is a contractual commitment, not a legal requirement. Breaking it (storing data elsewhere) could be an FTC deceptive practice.

### Cross-border
- Estonian company can legally store US user data in the EU (no US law prevents it).
- Estonian company can legally store EU user data in the US with valid transfer mechanism (DPF + SCCs).
- Per-region deployment eliminates transfer questions entirely, which is the strongest compliance posture.

### Stripe
- EU data residency available for EU-registered accounts since 2023.
- Stripe Payments Europe Limited (SPEL, Ireland) is the EU entity.
- Separate accounts per region is the standard approach for strict regional separation.
- Cross-border fee of ~1-1.5% avoided by using local Stripe account.
- PSD2/SCA required for EEA transactions, auto-handled by Stripe. Not applicable to US.

### AWS SES
- Available in both `eu-central-1` and `us-east-1`.
- Email content processed and temporarily stored in the sending region.
- Once email leaves SES, standard SMTP internet routing applies (unavoidable for any email system).
- Same domain can be verified independently in multiple SES regions.
- SES does not permanently store email content.

---

## Open Questions

1. **JWT secret per-region?** If `ACCOUNT_JWT_SECRET` is shared across regions, a JWT issued by the EU Worker would technically be valid on the US Worker (if someone manually sent a request). Per-region secrets prevent cross-region token replay. Recommendation: split it.

2. **Ed25519/X25519 keys per-region?** These are used for subscription signing and E2E encryption. If a license signed by the EU key should be verifiable by the US deployment (e.g., user moves regions), they need to be shared. If not, they can be per-region. Recommendation: keep shared for now; split later if needed.

3. **Turnstile per-region?** Turnstile site keys are bound to domains. If `eu.rediacc.com` and `us.rediacc.com` are separate domains, they may need separate Turnstile widget configurations. Check Cloudflare Turnstile docs for multi-domain support.

4. **OTLP telemetry per-region?** Currently single EU endpoint. Acceptable for now. If US region generates significant telemetry, consider a US OTLP endpoint to reduce latency.

5. **Webhook endpoints for Stripe?** Each Stripe account needs its own webhook endpoint. EU: `https://eu.rediacc.com/account/api/v1/webhooks/stripe`. US: `https://us.rediacc.com/account/api/v1/webhooks/stripe`. These are configured in each Stripe dashboard.

6. **Edge sandbox Stripe?** Currently edge uses `STRIPE_SANDBOX_SECRET_KEY`. With multi-region, edge-eu uses the sandbox key, edge-us may or may not need a separate sandbox. Recommendation: single sandbox (EU edge only) for simplicity. US edge can share the same sandbox or have its own.

7. **Seller entity per-region?** Currently `SELLER_NAME=Rediacc OU` (Estonian). For US invoices, should the seller entity be a US subsidiary? This is a business/legal decision, not a technical one. For now, same entity across regions.

8. **Admin email routing?** `ROOT_EMAIL` (admin alerts for disputes, refunds) currently goes to `muhammed@rediacc.com`. With multi-region, admin alerts from US Worker also go to the same email. This is fine unless there's a need for regional admin separation.

# Code Signing Guide for Rediacc

> **Entity:** Rediacc OÜ (Estonian private limited company)
> **Jurisdiction:** Estonia (EU member state)
> **Company Age:** < 1 year
> **Packages:** `@rediacc/desktop` (Electron), `@rediacc/cli` (Node.js SEA)
> **Platforms:** Windows, macOS, Linux
> **Date:** February 2026

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Implementation Status](#current-implementation-status)
3. [New Company Implications (< 1 Year Old)](#new-company-implications)
4. [Windows Code Signing — Top 3 Options (Scored)](#windows-code-signing)
5. [macOS Code Signing](#macos-code-signing)
6. [Linux Package Signing](#linux-package-signing)
7. [Total Annual Cost Estimates](#total-annual-cost-estimates)
8. [Important: CA/B Forum 460-Day Validity Change](#cab-forum-changes)
9. [Implementation Checklist](#implementation-checklist)
10. [Official Documentation Links](#official-documentation-links)

---

## Executive Summary

> **Rediacc is a new company (< 1 year old).** This affects Windows signing eligibility.

| Platform | Recommended Option | Annual Cost | SmartScreen / Gatekeeper | New Company? |
|----------|-------------------|-------------|--------------------------|--------------|
| **Windows** | Sectigo EV (with bank letter) | ~$277/yr | Must build organically | Bank letter workaround |
| **Windows** | Azure Artifact Signing (try first) | ~$120/yr | Immediate reputation | 3yr req — may be rejected |
| **macOS** | Apple Developer Program | $99/yr | Full Gatekeeper approval | No age requirement |
| **Linux** | GPG Key | Free | N/A (self-signed trust model) | No requirement |
| **Total (realistic)** | | **~$376/yr** | | |

---

## Current Implementation Status

> Assessed from the repo at `2026-02-17`. Many Linux signing steps are already complete.

### What's Already Done

| Component | Status | Details |
|-----------|--------|---------|
| **GPG keypair** | Done | Public key at `.ci/keys/gpg-public.asc`; private key in GitHub Actions secret `GPG_PRIVATE_KEY` |
| **RPM package signing** | Done | `.ci/scripts/build/build-linux-pkg.sh` uses nfpm native signing via `--rpm-key-file` |
| **APT repository signing** | Done | `.ci/scripts/build/build-pkg-repo.sh` generates signed `Release.gpg` + `InRelease` (clearsigned) |
| **RPM repository signing** | Done | Same script signs `repomd.xml` with detached GPG signature, writes `.repo` file |
| **Public key distribution** | Done | Exported to `apt/gpg.key` and `rpm/gpg.key` in Pages bundle |
| **APT repo metadata** | Done | `dpkg-scanpackages` generates `Packages` files, historical releases fetched via GitHub API |
| **RPM repo metadata** | Done | `createrepo_c` generates repo metadata |
| **GitHub Release publishing** | Done | `cd-v2.yml` uploads all artifacts to GitHub Releases |
| **GitHub Pages deployment** | Done | APT/RPM repo metadata hosted via GitHub Pages |
| **CLI SHA256 checksums** | Done | `.ci/scripts/build/build-cli-executables.sh` generates checksums |
| **macOS ad-hoc signing** | Done | CLI SEA binary gets `codesign -s -` (ad-hoc, not Developer ID) |
| **Installation method testing** | Done | `ct-install-methods.yml` tests APT, DNF, Homebrew, binary, Docker, quick-install |
| **CI/CD pipeline scaffolding** | Done | Full pipeline: ci.yml → cd-dryrun.yml → cd-v2.yml |

### What's NOT Done Yet

| Component | Status | What's Needed |
|-----------|--------|---------------|
| **Windows desktop signing** | Not started | Azure Artifact Signing or Sectigo EV cert + electron-builder config |
| **Windows CLI signing** | Not started | Same cert, `signtool` in build-cli-executables.sh |
| **macOS Developer ID signing** | Not started | Apple Developer Program enrollment, `CSC_LINK`/`CSC_KEY_PASSWORD` secrets |
| **macOS notarization** | Not started | `notarize: true` in electron-builder.yml, `APPLE_ID`/`APPLE_TEAM_ID` secrets |
| **macOS DMG signing** | Not started | `dmg.sign` is currently `false` in electron-builder.yml |
| **macOS CLI signing** | Not started | Replace ad-hoc `codesign -s -` with Developer ID signing + notarization |
| **Desktop code signing (CI)** | Disabled | `CSC_IDENTITY_AUTO_DISCOVERY=false` in ci-build-desktop.yml |
| **Entitlements fix** | Needed | `entitlements.mac.plist` has `allow-unsigned-executable-memory` — should be removed for Electron 12+ (current: Electron 39) |

### Key Files Reference

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Main CI pipeline orchestrator |
| `.github/workflows/cd-v2.yml` | Publish pipeline (GitHub Release + Pages) |
| `.github/workflows/cd-dryrun.yml` | Validation/dry-run (builds packages + repos) |
| `.github/workflows/ci-build-desktop.yml` | Desktop build (all platforms, signing disabled) |
| `.github/workflows/ci-build-cli.yml` | CLI SEA build (all platforms) |
| `.github/workflows/ct-install-methods.yml` | Tests APT, DNF, Homebrew, binary install |
| `.ci/scripts/build/build-linux-pkg.sh` | Unified Linux package builder — deb, rpm, apk, archlinux (**nfpm-based, GPG signed**) |
| `.ci/scripts/build/build-pkg-repo.sh` | APT/RPM repo builder (**GPG signed**) |
| `.ci/scripts/build/build-cli-executables.sh` | CLI SEA builder (ad-hoc macOS signing only) |
| `.ci/scripts/build/build-desktop.sh` | Desktop builder (no code signing) |
| `.ci/keys/gpg-public.asc` | GPG public key for package repos |
| `packages/desktop/electron-builder.yml` | Desktop build config (signing not configured) |
| `packages/desktop/resources/entitlements.mac.plist` | macOS entitlements (needs fix for Electron 39) |

---

## New Company Implications

> **Rediacc OÜ is an Estonian company, < 1 year old.** Estonia is an EU member state, so
> EU-eligible programs apply. However, the young company age restricts some options.

### Estonian OÜ Eligibility Overview

| Platform | Option | Age Requirement | Rediacc OÜ Eligible? | Workaround |
|----------|--------|----------------|----------------------|------------|
| **Windows** | Azure Artifact Signing | 3+ years (org) | Unlikely (but try) | Estonia is EU — eligible region. Age is the blocker. |
| **Windows** | Sectigo EV Code Signing | 3+ years (EV rule) | **Yes, with bank letter** | Estonian bank confirmation letter |
| **Windows** | OV Code Signing | No age requirement | **Yes** | Government-issued ID of requestor required |
| **macOS** | Apple Developer Program | **No age requirement** | **Yes** | D-U-N-S from D&B Estonia + functioning website |
| **Linux** | GPG Key | None | **Yes** | Self-generated, no CA involved |

**Why Estonian OÜ works well:**
- OÜ is a recognized EU legal entity (private limited company under Estonian law)
- The [Estonian e-Business Register (e-äriregister)](https://ariregister.rik.ee/eng) is publicly accessible **in English** — CAs can verify Rediacc's registration, address, and directors directly
- D&B has a local subsidiary in Tallinn (D&B Estonia AS, operating since 1996)
- No programs explicitly exclude e-Residency-formed companies — they appear identically in the Business Register

### Step 0: Get a D-U-N-S Number First

D-U-N-S is needed for Apple and helpful for all other programs. **Start this immediately** — it's the biggest time bottleneck.

**D&B Estonia AS** — Liivalaia tn 45, Kesklinna, Tallinn

| Method | Cost | Time | How |
|--------|------|------|-----|
| Apple's D-U-N-S Lookup Tool | Free | ~5 business days | [developer.apple.com/enroll/duns-lookup](https://developer.apple.com/enroll/duns-lookup/) |
| D&B Estonia portal | Free | Up to 30 business days | [dunsnumberlookup.dnb.com/et-ee](https://dunsnumberlookup.dnb.com/et-ee) |
| D&B Estonia expedited | Paid | ~8 business days | Email info.ee@dnb.com |
| D&B Estonia direct contact | Varies | Ask | Email info.ee@dnb.com |

**Important:** The company name, address, and details you provide to D&B must **exactly match** your e-äriregister entry. Mismatches cause delays with Apple and CAs.

### Windows — Recommended Path

**Primary plan: Sectigo EV with Estonian bank confirmation letter**

The CA/B Forum EV guidelines require 3+ years operational existence, but explicitly accept these alternative documents:

1. **Bank Confirmation Letter** (easiest) — A letter from your Estonian bank (LHV, Swedbank, SEB, etc.) confirming Rediacc OÜ has an active demand deposit (arvelduskonto) account. Most Estonian banks provide this within 1-2 business days. This is the most common workaround for young companies.
2. **Professional Opinion Letter (POL)** — A notarized letter from a licensed attorney or auditor vouching for the company's legitimacy. Sectigo provides [sample templates](https://support.sectigo.com/Com_KnowledgeDetailPage?Id=kA01N000000zFM8).
3. **Dun & Bradstreet Report** — Any D&B report on Rediacc OÜ can serve as proof of operational existence.

**Sectigo validation for Estonian OÜ will check:**
- [e-äriregister](https://ariregister.rik.ee/eng) for legal existence (publicly accessible, English)
- D-U-N-S or D&B database for physical/operational existence
- **Phone number in a public directory** — make sure Rediacc OÜ has a phone number listed and associated with the company name (D-U-N-S listing with phone satisfies this, or an Estonian business directory entry)
- Sectigo will make a **verification callback** to this phone number

**Backup plan: Try Azure Artifact Signing first**

Despite the 3-year requirement, [some younger companies have passed](https://melatonin.dev/blog/code-signing-on-windows-with-azure-trusted-signing/). Estonia is in the EU, so the region is eligible. The $9.99/month cost is low enough to attempt:

1. Create Azure account and Artifact Signing resource (use North Europe / Ireland region)
2. Submit identity validation with Rediacc OÜ documents
3. If approved — best option at lowest price with immediate SmartScreen
4. If rejected — proceed with Sectigo EV + bank letter

> **Note:** As of January 2026, Azure Artifact Signing reached General Availability. EU organizations are now supported. Check current enrollment availability at [Azure Artifact Signing](https://azure.microsoft.com/en-us/products/artifact-signing).

### macOS — No Issues for Estonian OÜ

Apple Developer Program has **no minimum company age** and supports 220+ countries including Estonia.

Rediacc OÜ can enroll immediately with:
- [x] Recognized legal entity — OÜ qualifies (not a DBA/trade name)
- [ ] D-U-N-S number — apply via Apple's tool or D&B Estonia (see Step 0 above)
- [ ] Functioning website — rediacc.com (must not be a placeholder/parked domain)
- [ ] Domain-based email — e.g. support@rediacc.com (Gmail/Yahoo not accepted for org enrollment)

**Potential friction:** Apple's enrollment verification can be unpredictable for any company. If rejected, resubmit with exact D-U-N-S / e-äriregister name match and ensure your website is fully functional.

### Linux — No Issues

GPG keys are self-generated. No external validation required. Estonian jurisdiction is irrelevant.

### SmartScreen Reality for New Companies

Since EV certs no longer provide instant SmartScreen reputation (as of March 2024), Rediacc faces a reputation-building period regardless of certificate type:

- Reputation builds organically through download volume (~500-2,000+ downloads)
- **Submit false positives** to [Microsoft WDSI Portal](https://www.microsoft.com/en-us/wdsi) to accelerate
- Azure Artifact Signing is the **only exception** — it provides immediate reputation if you can get approved
- Signing with a consistent identity over time accumulates trust faster

### Recommended Action Order for Rediacc OÜ

1. **Now:** Apply for D-U-N-S number via [Apple's lookup tool](https://developer.apple.com/enroll/duns-lookup/) (~5 days)
2. **Now:** Ensure rediacc.com is live with real content and support@rediacc.com works
3. **Now:** Request a bank confirmation letter from your Estonian bank (1-2 days)
4. **Day 1-5:** Try Azure Artifact Signing enrollment ($9.99/mo)
5. **Day 5+:** Enroll in Apple Developer Program once D-U-N-S arrives ($99/yr)
6. **Day 5+:** If Azure rejected, purchase Sectigo EV via CodeSigningStore ($277/yr) with bank letter
7. **Day 5+:** Generate GPG keypair for Linux signing (free, immediate)

---

## Windows Code Signing

> **CRITICAL UPDATE (March 2024):** EV certificates **no longer provide instant SmartScreen
> reputation**. Microsoft removed all EV Code Signing OIDs from the Trusted Root Program in
> August 2024. Both EV and OV certs now build reputation organically through download volume.
> **Azure Artifact Signing is now the ONLY way to get immediate SmartScreen trust**, because
> Microsoft backs the identity validation directly. This fundamentally changes the value
> proposition of traditional EV certs.

### Option 1: Azure Artifact Signing (Recommended)

> Formerly "Azure Artifact Signing", rebranded to "Azure Artifact Signing" in 2025.

**Cost:** $9.99/month (~$120/year)

| Category | Score | Notes |
|----------|-------|-------|
| **Value for Money** | 9/10 | Cheapest option by far; includes HSM, cert management, and SmartScreen |
| **Ease of Use** | 7/10 | Setup has some friction (identity validation, Azure account), but once done it's smooth |
| **CI/CD Integration** | 10/10 | Native electron-builder support via `win.azureSignOptions`; official GitHub Action |
| **SmartScreen** | 10/10 | Immediate reputation — no warmup period, persists across cert rotations |
| **Overall** | **9/10** | |

**How it works:**
- Microsoft's own cloud signing service (formerly "Azure Code Signing")
- No certificate files to manage — Azure issues short-lived certs (3-day lifespan) automatically
- Reputation tied to your verified identity, not individual certificates
- Unlimited signatures included in the monthly fee

**Requirements:**
- Azure account (paid subscription, not Free/Trial)
- Business identity validation (legal entity, EIN or D-U-N-S)
- Organizations: US, Canada, EU, or UK with 3+ years verifiable business history
- Individuals: US or Canada only
- FIPS 140-2 Level 3 compliant HSMs (managed by Microsoft)

**electron-builder integration:**
```yaml
# electron-builder.yml
win:
  azureSignOptions:
    publisherName: "Rediacc"           # Must match cert CN exactly
    endpoint: "<your-endpoint-url>"
    certificateProfileName: "<profile>"
    codeSigningAccountName: "<account>"
```

**CI/CD env vars:**
```
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>
```

**Official docs:**
- [Azure Artifact Signing](https://azure.microsoft.com/en-us/products/artifact-signing)
- [electron-builder Windows Signing](https://www.electron.build/code-signing-windows.html)
- [Scott Hanselman's Guide](https://www.hanselman.com/blog/automatically-signing-a-windows-exe-with-azure-trusted-signing-dotnet-sign-and-github-actions)
- [Melatonin.dev Practical Guide](https://melatonin.dev/blog/code-signing-on-windows-with-azure-trusted-signing/)

---

### Option 2: Sectigo EV Code Signing (via Reseller)

**Cost:** $277–$341/year (depending on reseller and term)

| Reseller | 1-Year | Notes |
|----------|--------|-------|
| CodeSigningStore | $277/yr | Sectigo-issued |
| CheapSSLSecurity | $279/yr | Sectigo-issued |
| SignMyCode | $279.99/yr | Sectigo-issued |
| SSL2BUY | $296.65/yr | Sectigo-issued |
| GoGetSSL | $341.10/yr ($284.25/yr on 3-year) | Sectigo-issued |

| Category | Score | Notes |
|----------|-------|-------|
| **Value for Money** | 6/10 | ~2.5x more expensive than Azure; multi-year discounts help |
| **Ease of Use** | 6/10 | Requires HSM setup (Google Cloud KMS or physical token); more moving parts |
| **CI/CD Integration** | 7/10 | Works via Google Cloud KMS + signtool; no native electron-builder config |
| **SmartScreen** | 4/10 | **EV no longer provides instant reputation (since Mar 2024)**; must build organically |
| **Overall** | **6/10** | |

**HSM options for Sectigo certs:**
- Google Cloud KMS (recommended for CI/CD — FIPS 140-2 compliant)
- Physical USB token (SafeNet/YubiKey) — not suitable for CI/CD
- **Note:** Azure Key Vault does NOT support Sectigo certs (requires key attestation that AKV lacks)

**Official docs:**
- [Sectigo Code Signing](https://www.sectigo.com/ssl-certificates-tls/code-signing)
- [Sectigo + Google Cloud KMS Guide](https://signmycode.com/resources/sectigo-code-signing-implementations-on-google-kms-key-management-service)
- [GitHub Actions EV Signing Guide (Melatonin.dev)](https://melatonin.dev/blog/how-to-code-sign-windows-installers-with-an-ev-cert-on-github-actions/)

---

### Option 3: SSL.com EV Code Signing + eSigner

**Cost:** ~$349/yr (cert) + $900/yr (eSigner Tier 1 annual) = ~$1,249/year total

| Category | Score | Notes |
|----------|-------|-------|
| **Value for Money** | 3/10 | Cert itself is OK, but eSigner adds $900+/yr; 10x more than Azure Artifact Signing |
| **Ease of Use** | 8/10 | eSigner is cloud-native, no HSM management needed |
| **CI/CD Integration** | 9/10 | First-party GitHub Actions, CodeSignTool CLI, Docker images |
| **SmartScreen** | 4/10 | **EV no longer provides instant reputation (since Mar 2024)**; must build organically |
| **Overall** | **5/10** | |

**Pricing breakdown:**
- EV Code Signing cert: $349/yr (1-year) or $249/yr (3-year term)
- eSigner Tier 1: $100/month or **$900/yr** (25% annual prepay discount) — includes 10 signings/month
- Additional signatures: $10 each beyond the 10/month included
- Alternative: Use a YubiKey token instead of eSigner ($349/yr cert only, no recurring signing fees)
- **Realistic total for small team: ~$1,149–$1,249/yr** with eSigner

**Gotcha:** Users have [reported unexpected charges](https://billauer.co.il/blog/2021/11/esigner-cloud-signing-ssl-com-certificate/) when signature count exceeds the tier limit. Monitor usage carefully.

**Official docs:**
- [SSL.com EV Code Signing](https://www.ssl.com/certificates/ev-code-signing/buy/)
- [eSigner Pricing](https://www.ssl.com/guide/esigner-pricing-for-code-signing/)
- [eSigner Cloud Signing](https://www.ssl.com/esigner/)

---

### Windows Scoring Summary

| Option | Annual Cost | Value | Ease | CI/CD | SmartScreen | Overall |
|--------|-------------|-------|------|-------|-------------|---------|
| **Azure Artifact Signing** | ~$120 | 9 | 7 | 10 | 10 | **9/10** |
| **Sectigo EV (reseller)** | $277–341 | 6 | 6 | 7 | 4 | **6/10** |
| **SSL.com EV + eSigner** | ~$1,249 | 3 | 8 | 9 | 4 | **5/10** |

**Verdict:** Azure Artifact Signing is the clear winner — cheapest, best CI/CD support with electron-builder, and **the only option that provides instant SmartScreen reputation** since Microsoft killed EV instant trust in March 2024. Traditional EV certs are now significantly less attractive.

**Availability caveat:** Azure Artifact Signing is currently available to organizations in **US, Canada, EU, and UK** with 3+ years verifiable business history. If Rediacc is outside these regions, Sectigo EV via Google Cloud KMS is the fallback.

---

## macOS Code Signing

### Apple Developer Program — $99/year (Only Option)

There is **no cheaper alternative** for macOS. Third-party CA certs (DigiCert, Sectigo) are NOT recognized by Gatekeeper.

| Category | Details |
|----------|---------|
| **Cost** | $99/year |
| **Enrollment** | [developer.apple.com/programs/enroll](https://developer.apple.com/programs/enroll/) |
| **Entity type** | Must be a legal entity (LLC, Inc, etc.) — DBAs not accepted |
| **D-U-N-S Number** | Required for organization enrollment (free from D&B, allow 5 business days) |

### Certificates Needed

| Certificate | Purpose | Validity |
|-------------|---------|----------|
| **Developer ID Application** | Signs the `.app` bundle | 5 years |
| **Developer ID Installer** | Signs `.pkg` installers | 5 years (expired = won't run!) |

### Notarization (Required since macOS 10.15)

All software distributed outside the App Store must be signed AND notarized.

**Process:**
1. Code sign with Developer ID Application cert (hardened runtime required)
2. Submit for notarization: `xcrun notarytool submit MyApp.dmg --keychain-profile "profile" --wait`
3. Staple the ticket: `xcrun stapler staple MyApp.dmg`

**Tool requirements:**
- `xcrun notarytool` (Xcode 14+) — `altool` is deprecated since Nov 2023

### Entitlements for Electron (v12+)

Your `entitlements.mac.plist` should include:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
</dict>
</plist>
```

**Do NOT use** `com.apple.security.cs.allow-unsigned-executable-memory` with Electron 12+ (your app uses Electron 39).

### electron-builder Configuration Changes Needed

```yaml
# electron-builder.yml changes
mac:
  hardenedRuntime: true           # Already set
  entitlements: resources/entitlements.mac.plist
  entitlementsInherit: resources/entitlements.mac.plist
  notarize: true                  # ADD THIS

dmg:
  sign: true                      # CHANGE from false to true
```

**CI/CD env vars:**
```
CSC_LINK=<base64-encoded .p12 file>
CSC_KEY_PASSWORD=<p12 password>
APPLE_ID=<your-apple-id>
APPLE_APP_SPECIFIC_PASSWORD=<app-specific-password>
APPLE_TEAM_ID=<team-id>
```

### macOS Sequoia (15+) Impact

- Control-click Gatekeeper bypass has been **removed**
- Users must go to System Settings > Privacy & Security > "Open Anyway"
- This makes notarization significantly more important — without it, user friction is very high

### CI/CD Integration

| Tool | Description |
|------|-------------|
| [apple-actions/import-codesign-certs](https://github.com/Apple-Actions/import-codesign-certs) | Imports .p12 certs into macOS runner keychain |
| [@electron/notarize](https://github.com/electron/notarize) | Handles notarization in electron-builder afterSign hook |
| [rcodesign](https://github.com/indygreg/apple-platform-rs) | Sign + notarize from Linux/Windows (no Mac needed!) |

**Official docs:**
- [Apple Developer ID](https://developer.apple.com/developer-id/)
- [Notarization Docs](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Electron Code Signing](https://www.electronjs.org/docs/latest/tutorial/code-signing)
- [electron-builder macOS Signing](https://www.electron.build/code-signing-mac.html)

---

## Linux Package Signing

### Cost: Free

### Status: ALREADY IMPLEMENTED

> Linux signing is fully operational in the existing CI/CD pipeline.

### What's Done

| Component | Implementation | File |
|-----------|---------------|------|
| GPG keypair | Public key at `.ci/keys/gpg-public.asc`; private in `GPG_PRIVATE_KEY` secret | `.ci/keys/gpg-public.asc` |
| RPM package signing | nfpm native signing via `--rpm-key-file` | `.ci/scripts/build/build-linux-pkg.sh` |
| APT repo signing | `gpg --detach-sign` on Release file → `Release.gpg` + `InRelease` | `.ci/scripts/build/build-pkg-repo.sh` |
| RPM repo signing | `gpg --detach-sign` on `repomd.xml` → `repomd.xml.asc` | `.ci/scripts/build/build-pkg-repo.sh` |
| Public key hosting | Exported to `apt/gpg.key` and `rpm/gpg.key` in GitHub Pages bundle | `.ci/scripts/build/build-pkg-repo.sh` |
| Historical release handling | Fetches all prior releases via GitHub API to maintain full repo | `.ci/scripts/build/build-pkg-repo.sh` |
| Installation testing | APT + DNF install tested in CI (`ct-install-methods.yml`) | `.github/workflows/ct-install-methods.yml` |

### What Could Be Improved (Low Priority)

| Item | Current | Improvement |
|------|---------|-------------|
| DEB package-level signing | Signed via nfpm `--deb-key-file` when GPG key available | Already implemented in `build-linux-pkg.sh` |
| AppImage signing | Not signed | Add `appimagetool --sign` (low value — no centralized trust) |
| SHA-1 readiness | Unknown | Verify GPG key uses SHA-256+ (Debian 13 blocks SHA-1 repos in 2026) |
| Repo hosting | GitHub Pages | Could migrate to Cloudflare R2 for lower latency / no egress fees |

**Official docs:**
- [Debian Package Signing Manual](https://www.debian.org/doc/manuals/securing-debian-manual/deb-pack-sign.en.html)
- [AppImage Signing](https://docs.appimage.org/packaging-guide/optional/signatures.html)
- [Cloudflare R2 as APT/YUM Repo](https://blog.cloudflare.com/using-cloudflare-r2-as-an-apt-yum-repository/)

---

## Total Annual Cost Estimates

### Recommended Stack (Cheapest)

| Item | Cost/Year |
|------|-----------|
| Azure Artifact Signing (Windows) | $120 |
| Apple Developer Program (macOS) | $99 |
| GPG Key (Linux) | Free |
| Cloudflare R2 (Linux repo hosting) | Free (within free tier) |
| **Total** | **$219/year** |

### Alternative Stack (Traditional EV Cert + Token)

| Item | Cost/Year |
|------|-----------|
| Sectigo EV via CodeSigningStore (Windows) | $277 |
| Google Cloud KMS (for CI/CD signing) | ~$12 (HSM key + signing ops) |
| Apple Developer Program (macOS) | $99 |
| GPG Key (Linux) | Free |
| **Total** | **~$388/year** |

Note: SSL.com with eSigner would be ~$1,249+/yr for Windows alone — not recommended given Azure Artifact Signing exists at $120/yr.

---

## CA/B Forum Changes

**Effective March 1, 2026** (this month!):

- Maximum code signing certificate validity reduced from 39 months to **460 days** (~15 months)
- Applies to both OV and EV certificates
- Existing certificates remain valid until expiry
- Renewals/reissues after the deadline follow new rules

**Impact on Rediacc:**
- If using Azure Artifact Signing: **No impact** (certs are auto-rotated daily)
- If using traditional EV cert: Must renew annually instead of every 3 years
- Multi-year purchases from resellers will issue certificates in 460-day increments

**Sources:**
- [DigiCert: Understanding the Change](https://www.digicert.com/blog/understanding-the-new-code-signing-certificate-validity-change)
- [GlobalSign: Certificate Lifecycle Reductions](https://www.globalsign.com/en/company/news-events/news/businesses-must-prepare-two-significant-certificate-lifecycle-reductions-march-2026)

---

## Implementation Checklist

### Prerequisites

- [x] Rediacc OÜ is a registered Estonian legal entity (e-äriregister)
- [ ] Apply for D-U-N-S number via [Apple's lookup tool](https://developer.apple.com/enroll/duns-lookup/) or D&B Estonia (info.ee@dnb.com)
- [ ] Ensure rediacc.com is live with real content (not a placeholder)
- [ ] Ensure domain-based email works (e.g. support@rediacc.com)
- [ ] Request bank confirmation letter from Estonian bank (LHV, Swedbank, SEB, etc.)
- [ ] Ensure Rediacc OÜ has a phone number listed in a public directory or D-U-N-S record
- [ ] Set up CI/CD secrets management (GitHub Actions secrets or equivalent)

### Windows

**Option A — Azure Artifact Signing (try first, may be rejected due to company age):**
- [ ] Create Azure account and subscription
- [ ] Create Artifact Signing Account (North Europe region)
- [ ] Submit identity verification for Rediacc OÜ
- [ ] Create certificate profile (Public Trust)
- [ ] Set up App Registration for CI/CD authentication
- [ ] Configure `win.azureSignOptions` in `electron-builder.yml`
- [ ] Add `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` to GitHub Actions secrets
- [ ] Add signing to CLI SEA binary in `build-cli-executables.sh`
- [ ] Remove `CSC_IDENTITY_AUTO_DISCOVERY=false` from `ci-build-desktop.yml`
- [ ] Test: verify signed installer has no SmartScreen warning

**Option B — Sectigo EV (fallback if Azure rejects):**
- [ ] Request bank confirmation letter from Estonian bank
- [ ] Purchase Sectigo EV cert via CodeSigningStore ($277/yr)
- [ ] Set up Google Cloud KMS for HSM key storage
- [ ] Configure `signtool` signing in `build-desktop.sh` and `build-cli-executables.sh`
- [ ] Add `CSC_LINK`, `CSC_KEY_PASSWORD` (or GCP KMS credentials) to GitHub Actions secrets
- [ ] Test: verify signed installer runs without "Unknown Publisher"

### macOS

- [ ] Enroll in Apple Developer Program as organization ($99)
- [ ] Generate Developer ID Application certificate
- [ ] Generate Developer ID Installer certificate (if using .pkg)
- [ ] **Fix `entitlements.mac.plist`** — remove `allow-unsigned-executable-memory` (not needed for Electron 12+, current: Electron 39)
- [ ] Set `dmg.sign: true` (currently `false`) and add `mac.notarize: true` in `electron-builder.yml`
- [ ] Add `mac.entitlements: resources/entitlements.mac.plist` in `electron-builder.yml`
- [ ] Configure CI/CD env vars: `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`
- [ ] Remove `CSC_IDENTITY_AUTO_DISCOVERY=false` from `ci-build-desktop.yml` (currently disables signing)
- [ ] Replace ad-hoc `codesign -s -` in `build-cli-executables.sh` with Developer ID signing
- [ ] Submit CLI binary for notarization: `xcrun notarytool submit`
- [ ] Test: verify app opens without Gatekeeper warning

### Linux (Mostly Complete)

- [x] Generate GPG keypair — `.ci/keys/gpg-public.asc` + `GPG_PRIVATE_KEY` secret
- [ ] Generate revocation certificate and store securely (if not already done)
- [x] Export private key to GitHub Actions secrets — `GPG_PRIVATE_KEY` + `GPG_PASSPHRASE`
- [x] APT repository signing — `build-pkg-repo.sh` signs `Release` → `Release.gpg` + `InRelease`
- [x] RPM repository signing — `build-pkg-repo.sh` signs `repomd.xml`
- [x] RPM package signing — `build-linux-pkg.sh` signs via nfpm `--rpm-key-file`
- [x] Public key distribution — `apt/gpg.key` + `rpm/gpg.key` in Pages bundle
- [x] Repo hosted on GitHub Pages — deployed in `cd-v2.yml`
- [x] Installation method testing — `ct-install-methods.yml` tests APT + DNF installs
- [ ] Verify GPG key uses SHA-256+ (Debian 13 blocks SHA-1 in 2026)
- [ ] Optional: Migrate repo to Cloudflare R2 for lower latency

---

## Official Documentation Links

### Apple

| Topic | URL |
|-------|-----|
| Developer ID | https://developer.apple.com/developer-id/ |
| Enrollment | https://developer.apple.com/programs/enroll/ |
| Certificates | https://developer.apple.com/support/certificates/ |
| Notarization | https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution |
| Resolving Notarization Issues | https://developer.apple.com/documentation/security/resolving-common-notarization-issues |
| Sequoia Runtime Changes | https://developer.apple.com/news/?id=saqachfa |

### Microsoft

| Topic | URL |
|-------|-----|
| Azure Artifact Signing | https://azure.microsoft.com/en-us/products/artifact-signing |
| Azure Pricing Calculator | https://azure.microsoft.com/pricing/calculator/ |
| Authenticode Overview | https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools |
| SmartScreen FAQ | https://www.digicert.com/blog/ms-smartscreen-application-reputation |

### electron-builder

| Topic | URL |
|-------|-----|
| Windows Signing | https://www.electron.build/code-signing-windows.html |
| macOS Signing | https://www.electron.build/code-signing-mac.html |
| NSIS Config | https://www.electron.build/nsis.html |
| Build Hooks | https://www.electron.build/hooks.html |

### Linux

| Topic | URL |
|-------|-----|
| Debian Package Signing | https://www.debian.org/doc/manuals/securing-debian-manual/deb-pack-sign.en.html |
| AppImage Signing | https://docs.appimage.org/packaging-guide/optional/signatures.html |
| Cloudflare R2 as Repo | https://blog.cloudflare.com/using-cloudflare-r2-as-an-apt-yum-repository/ |
| GnuPG Key Management | https://www.gnupg.org/gph/en/manual/c235.html |

---
title: "Article 21(2)(d) is a Vendor Question. Self-Hosting is the Answer You Stop Owing."
description: "Why the third-party-ICT register shrinks when the data plane never leaves your tenancy. A practical read of NIS2 Article 21(2)(d) for CISOs and procurement leads renegotiating DPAs in 2026."
author: Rediacc
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - supply-chain
  - self-hosted
  - sovereignty
  - compliance
featured: false
language: en
---

> **TL;DR.** NIS2 Article 21(2)(d) makes supply chain risk a board-level question, not a procurement footnote. The directive does not actually mandate self-hosting. It does, however, ask what is in your data path and what happens to you when one of those vendors has a bad Tuesday. Self-hosted infrastructure collapses three of the four layers on most SaaS data paths. It does not collapse all four, and pretending otherwise is the marketing move that gets a CISO into trouble in front of an auditor.
>
> - The directive text and ENISA guidance, in plain English.
> - The four-layer SaaS data path most teams forget to draw.
> - What Rediacc's two-tool model removes from your vendor register, and what it leaves on it.
> - A six-question procurement checklist for any vendor claiming "NIS2-ready."

In July 2020, Blackbaud paid a ransom and told the world later. They notified more than 13,000 customer organisations after the fact, fielded class actions in seven jurisdictions, and ended up paying $49.5 million in state attorneys general settlements and a $3 million SEC fine for misleading disclosures. Every single one of those 13,000 organisations had a Data Processing Agreement with Blackbaud. Most of them had reviewed Blackbaud's SOC 2 report. Many had Blackbaud on a vendor risk register, with a tier rating, a renewal date, and a named owner.

None of it stopped the cascade. The data was on Blackbaud's side of the boundary. When their backup environment was breached, every customer organisation was breached at once.

NIS2 Article 21(2)(d) asks a harder question than "did you audit your vendor." It asks what is in the data path, and what happens to you when that vendor has a bad Tuesday. The answer, for most teams, is "we are them, and we did not realise it."

This post is for CISOs and procurement leads renegotiating DPAs in 2026. It is the data-path read of Article 21(2)(d), not the certifications read. It is also honest about what self-hosted infrastructure does not solve, because the gap section is what an auditor will ask about and a marketing brochure will skip.

## What 21(2)(d) actually obliges

The directive text reads, lightly trimmed for clarity:

> "Member States shall ensure that essential and important entities take appropriate and proportionate technical, operational and organisational measures to manage the risks posed to the security of network and information systems which those entities use [...] and shall include at least the following: [...] (d) supply chain security, including security-related aspects concerning the relationships between each entity and its direct suppliers or service providers"

Two things in that text matter for a buyer.

First, the obligation is on you, not on the vendor. The vendor's certifications, the vendor's SOC 2, the vendor's ISO 27001 are inputs to your risk assessment. They are not a substitute for it. If your vendor has a perfect compliance posture and gets breached anyway, the regulator's question is going to be about your supplier risk management, not theirs.

Second, the obligation is broader than the contract. ENISA's 2024 implementing guidance, Annex IV of Commission Implementing Regulation (EU) 2024/2690, lays out the expected practice: maintain a register of ICT suppliers, classify them by criticality, assess each one for risk to your operations and to the data they process, and renew the assessment on a defined cadence. Annex IV explicitly names "the suppliers' suppliers" as in-scope, which is where most teams discover that their vendor register is not really a register, it is a contract list with a sticker.

If you are looking at this from the procurement side, the practical translation is: every vendor with logical access to your production data has to be enumerated, scored, monitored, and replaceable. "Replaceable" is the part that breaks most existing arrangements.

## The four-layer SaaS data path most teams forget to draw

Sit down with a procurement lead and walk through what happens when a backup vendor's product writes a single record. The honest data path looks like this, top to bottom:

1. The **vendor application**. The code that ingests your data, makes routing decisions, and applies business logic. Runs on the vendor's infrastructure. Maintained, patched, and monitored by the vendor.
2. The **vendor cloud**. The hyperscaler region or the vendor's own datacentre where the application runs. Storage volumes, networking, IAM. Often a hyperscaler the vendor has a sub-processor agreement with.
3. The **vendor key custody**. The encryption keys that protect data at rest in the vendor cloud. In most SaaS arrangements, the vendor holds these. "Customer-managed keys" is sometimes available as a tier-up option; in those arrangements, the keys are still in a hyperscaler KMS that the vendor's IAM can call.
4. The **vendor sub-processors**. The third-party services the vendor uses (CDN, observability, billing, customer support tooling) that may transit or store your data, or metadata derived from it.

Each of those four layers is an entry on your Article 21(2)(d) supplier register. Each one has its own incident history, its own breach blast radius, its own contract negotiation surface. When you renew with the SaaS vendor, you renew all four implicitly, because the SaaS vendor's contract is the only one you can negotiate.

The Blackbaud incident was a layer-2 breach (vendor cloud) that propagated through layer 1 (vendor application) and was visible to every customer because of layer 3 (vendor key custody, in their case server-side keys without per-tenant separation in the affected database). Blackbaud's sub-processors were not the breach vector, but customers found out about three of them they had not enumerated.

## Blackbaud, Druva-style key custody, and the cascade pattern

Three details from Blackbaud's SEC filings are the ones that matter for a NIS2 read.

First, Blackbaud held the encryption keys for customer data, including the backup environment that was the breach target. Customer-managed keys were not on offer. In post-incident SEC litigation, this was characterised as a control gap, not a violation, because Blackbaud's contracts permitted it. NIS2's perspective on the same arrangement, under Article 21(2)(d), is harder, because the customer cannot meaningfully assess the risk of a control they do not have visibility into.

Second, the breach affected backup data older than the live database. Customer organisations whose live data had been deleted from Blackbaud's primary systems still had data exposed via the backup environment. This is the cascade pattern: a vendor compromise reaches into historical data the customer thought was already out of scope.

Third, more than 13,000 customer organisations received breach notifications. Many of those were small non-profits and schools that had no operational capacity to respond, no DR runbook, no second backup vendor to fail over to. The vendor's incident, in that sense, became their incident.

For a Druva-style modern SaaS backup, the architecture is better in places (per-tenant key separation is more common, BYOK is on offer at higher tiers) but the four-layer data path is the same. The vendor application, the vendor cloud (typically AWS), the key custody (sometimes vendor, sometimes BYOK in customer KMS, sometimes hybrid), the sub-processors. A breach at any layer reaches every customer simultaneously, because every customer's data is on the same side of the boundary.

This is the structural argument. It is not a Druva takedown. Druva runs a tighter ship than Blackbaud did. The argument is that the structure of any SaaS-by-design backup product makes layer-2 and layer-3 breaches an obligation under 21(2)(d) that the customer cannot meaningfully discharge.

## Self-hosted collapses three of the four layers

Rediacc is built differently. The full architecture is documented in the [Architecture page](/en/docs/architecture), but the supply-chain-relevant shape is two binaries that talk over SSH:

- `rdc` runs on the operator's workstation. It reads a flat JSON config file (under `~/.config/rediacc/`), connects to the operator's own machines over SSH, and dispatches commands.
- `renet` runs on the operator's own server, with root, and manages LUKS-encrypted disk images, isolated Docker daemons, and the reverse proxy.

The operator never logs into Rediacc-the-company's infrastructure to run a backup, restore, or fork. There is no Rediacc-the-company cloud in the data path. The repository's LUKS credential is stored in the operator's local config file (mode `0600`), never on the server, never sent to Rediacc. The data path looks like this:

1. **Operator workstation.** Runs `rdc`. Holds the LUKS credential.
2. **Operator's own server.** Runs `renet`. Holds the LUKS-encrypted repositories.
3. **Operator's own backup target.** Any rclone-compatible storage (S3, B2, OneDrive, on-prem MinIO). Receives encrypted volumes.

There is no layer 4. Rediacc-the-company is not a sub-processor for any operator who has not opted into the experimental [Cloud adapter](/en/docs/architecture). For self-hosted operators, the relationship with Rediacc-the-company is a software licence, not a data processing agreement.

This is the data-path argument, and it is the right argument to lead with in a supplier register conversation. A SaaS competitor can offer customer-managed keys (and most modern ones do). A SaaS competitor cannot offer "we are not a sub-processor."

The second beat, after the data-path argument lands, is key custody. With Rediacc, the LUKS credential is in the operator's config file, full stop. There is no key escrow, no recovery service Rediacc-the-company can run if the operator loses the credential. This is also the recommended architecture for the [zero-knowledge config store](/en/docs/config-storage), where the encryption key is derived client-side from a passkey PRF extension and the server stores opaque blobs. The server cannot read the SSH keys, the LUKS credentials, the IP addresses, or any plaintext config. Rotating the access token does not give the server retroactive read.

For Article 21(2)(h) (encryption), this matters. For Article 21(2)(d) (supply chain), it matters more, because it removes the last logical-access pathway from Rediacc-the-company to the operator's data.

## What self-hosting does not collapse

Self-hosting shifts the supplier list, it does not delete it. Three things an auditor will still ask about:

**1. You still have suppliers, just different ones.** The hardware vendor (Hetzner, Hostinger, OVH, your colo, your own bare metal). The hypervisor (KVM, VMware). The OS (Debian, Ubuntu, RHEL). The container registry (Docker Hub, GHCR, your private registry). The base images your services pull. Each of those is an Article 21(2)(d) entry. Self-hosted shifts the supplier list, it does not delete it.

**2. Rediacc does not have ISO 27001, SOC 2, or BSI C5 yet.** These are on the roadmap, not in hand. For a procurement team that uses certifications as a gating mechanism, this is a real friction. The defensible counter is the one this post has been making: the data-path argument means most of what those certifications attest to (vendor cloud security controls, vendor personnel access management, vendor sub-processor management) is not in scope, because Rediacc-the-company is not in the data path. That argument needs to be made carefully and defensibly, not as a substitute for certifications when certifications are what the buyer needs.

**3. The GRC layer is still yours.** Rediacc gives the operator a 70+-event hash-chained audit log (`rdc audit verify` validates the chain end-to-end). It does not give you a supplier register, a control framework, or an evidence-collection workflow. Those still come from Drata, Vanta, OneTrust, or one of the European entrants. The companion [real bill post](/en/blog/nis2-the-real-bill) covers the cost shape of that complementarity in detail.

## The DPA you no longer have to negotiate

To make this concrete, here is a "before vs after" register row from a real procurement conversation, anonymised. The buyer is a 280-employee German manufacturing company classified as an Annex II "important entity." Their original supplier register entry for backup looked like this:

| Field | Before |
|---|---|
| Vendor | Acme Backup SaaS |
| Tier | Critical |
| Data processed | Production database, customer PII, financial records |
| Sub-processors | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Contract status | DPA signed 2023, SCCs attached, schedule of measures last reviewed Jan 2025 |
| Key custody | Vendor-managed (BYOK option not on current tier) |
| Exit plan | "Vendor agrees to provide data export in CSV within 30 days of termination" |
| Last assessment | 2025-Q1, gap noted on key custody, deferred to renewal |

After moving to Rediacc on Hetzner:

| Field | After |
|---|---|
| Vendors | (1) Rediacc OÜ, software licence; (2) Hetzner, IaaS |
| Tier | (1) Non-critical (no data plane); (2) Critical (data plane, but customer-controlled) |
| Data processed | (1) None; (2) Encrypted volumes, customer holds keys |
| Sub-processors | (1) None for self-hosted; (2) Hetzner-internal only, listed in their DPA |
| Contract status | (1) Software licence, no DPA needed; (2) Hetzner DPA + SCCs already in place |
| Key custody | Customer (LUKS credential in operator config, not on server) |
| Exit plan | "rdc repo backup pull from any rclone-compatible target. Volumes are LUKS-encrypted; operator holds credential." |
| Last assessment | (2) covered by existing IaaS review |

Two register entries instead of one. The critical-tier entry is for the IaaS provider, where the buyer already had a DPA in place and a tested exit plan, because IaaS is a relationship most teams know how to manage. The Rediacc entry is non-critical because it is a software licence, not a data processor.

This is the structural reason a CISO ends up wanting fewer SaaS dependencies in the data plane, even if the procurement cost looks similar on a spreadsheet. The register entry is not the same shape.

## Procurement checklist

For any vendor claiming "NIS2-ready" in a 2026 sales cycle, six questions:

**1. Where is the encryption key for our data at rest?** If the answer is "in our HSM" or "in our customer's KMS that we can call via IAM," the vendor is in your key custody chain. If it is "in your local config file, never on our infrastructure," they are not.

**2. Who at your company can technically read our data, ignoring the legal terms?** Not "who is authorised to" but "who could, if they wanted to and the audit log were turned off." If the answer is non-zero, that is your population for an insider-risk assessment.

**3. Is restoration tested against a real production clone, or against synthetic test data?** Article 21(2)(c) and (e) read together require that backup actually restores. A vendor that only validates against synthetic data is not validating recovery, they are validating the backup file integrity. (For more on this, see the companion post on [continuous effectiveness assessment](/en/blog/nis2-effectiveness-without-theatre).)

**4. Does your audit trail record the actor kind, human or agent, behind each action?** AI agent activity is the fastest-growing audit-log category. A 2026 audit log that does not distinguish human from agent is going to look like a gap by 2027.

**5. List every sub-processor that has logical access to our data, including metadata.** "Logical access" is the right phrase. "Logical access including metadata" is the better one, because metadata-only access is what billing, observability, and customer-support sub-processors typically have, and it is enough to leak sensitive structure even when the payload is encrypted.

**6. What is your exit plan if you are acquired by a non-EU buyer in 2027?** GDPR's adequacy framework, the Cloud Act, and FISA 702 are all moving targets. A vendor's data residency claim today is not a guarantee three years from now. The buyer's question is what happens to the data path if the vendor's ownership changes.

A vendor that answers six out of six cleanly is unusual. A vendor that answers four out of six and acknowledges the other two openly is more trustworthy than one who answers all six confidently. The credibility signal is the willingness to name what is not solved.

## What this means for the next renewal cycle

If you are heading into a backup or DR renewal in the next twelve months and Article 21(2)(d) is on the procurement scorecard, three concrete moves:

1. Draw your current vendor's four-layer data path on a whiteboard. If you cannot name the third sub-processor down, you have a register completeness issue that predates NIS2 and the renewal is the right moment to fix it.
2. Run the six-question checklist above against your incumbent. Send the answers to your DPO and your auditor and ask whether the gaps are accepted. If the gaps include layer 3 (key custody) or layer 4 (sub-processors you did not enumerate), that is the wedge.
3. Look at what an alternative supplier register would look like with a self-hosted control plane. Compare the register entries, not the licence costs. The licence costs are similar within a factor of two; the register entries are different shapes. (The companion post on [the structural cost of the NIS2 stack](/en/blog/nis2-the-real-bill) walks through what gets collapsed and what stays.)

If we are the alternative on your shortlist, the offer is concrete. Send us your vendor questionnaire. We will fill it out against a deployed instance, with our actual answers to your questions, including the gaps. If you want to walk through the architecture before sending paperwork, we will book a 30-minute architecture review with our engineering team. The path to a defensible register entry is not a glossy brochure. It is the answers, including the uncomfortable ones.

Want the per-article Rediacc map? See [NIS2 and DORA](/en/docs/legal-nis2-dora). Need the wider frame? Read [Compliance Overview](/en/docs/legal-overview). For data residency, see [Data Sovereignty](/en/docs/legal-data-sovereignty). For why self-hosted matters, see [On-Premise](/en/docs/on-premise).

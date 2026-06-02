---
title: "What Buyers Told Us in the First NIS2 Audit Cycle"
description: "The five-tool compliance stack mid-market essential entities are quietly assembling in 2026, what a self-hosted control plane collapses, and the line items that stay yours either way."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - buyer-guide
  - compliance
  - cost
  - mid-market
featured: false
language: en
---

> **TL;DR.** First-cycle NIS2 audits are now in the rear-view mirror for the German wave. The buyers we have spoken to since December all describe a version of the same stack: five tools, three contracts, two overlapping audit logs, and one gap they cannot close. This post is the structural version of that conversation. What a self-hosted control plane collapses, what stays on your budget either way, and why the right framing for a 2026 renewal cycle is not "cheaper than Veeam" but "fewer register entries, fewer overlaps, the same gaps named honestly."
>
> - Frontier Economics put EU-wide NIS2 compliance at EUR 31.2 billion a year. The per-organisation reality, in mid-market, is "we already had a security stack; NIS2 surfaced what was missing."
> - The five-tool stack: backup, DR, masking or test data, pen test contract, GRC. Each does part of the job. None covers the whole.
> - Rediacc collapses backup, DR, fork-as-test-data, and instant restore into one control plane with one audit log. It does not collapse GRC, certifications, training, broader MFA, pen testing, or SIEM and SOC.
> - The honest "still yours" table is the structural payoff of this post. A buyer who reads it and concludes Rediacc replaces Drata is going to disappoint their auditor.

In December 2025, BSI in Germany issued 47 formal notices to entities they considered to be in scope for NIS2 but not registered. ANSSI in France started a parallel exercise. ACN in Italy began chasing roughly 2,000 entities they thought were unregistered. The first wave of mid-market essential and important entities went into their first NIS2 audit cycle.

We have been on calls with about thirty of them since. Different sectors, different sizes, mostly Germany and Italy with a handful in the Netherlands and Estonia. The conversations rhyme. Every team has a backup vendor, a DR plan that may or may not have been tested, a story about staging that is half true, and a procurement budget that was approved before NIS2 was on anyone's slide deck.

This post is the structural version of those conversations. What a CFO or a buyer is actually being asked to sign in 2026, what a self-hosted control plane changes about the bill, and what the honest residual cost looks like. It is deliberately not a TCO calculator. The buyers we are talking to do not need another spreadsheet; they need a structural map of where the money is going and which line items overlap.

If you want the supply-chain risk argument behind the "self-hosted matters" claim, see the [companion post on Article 21(2)(d)](/en/blog/nis2-supply-chain-self-hosted). If you want the SRE-level argument about why annual pen tests are no longer enough, see the [companion post on continuous effectiveness](/en/blog/nis2-effectiveness-without-theatre). This post sits between them, at the budget conversation.

## The macro number, and what it does and does not mean

Frontier Economics' 2024 study for the European Commission put the direct annual cost of NIS2 compliance across the EU at EUR 31.2 billion. The figure is widely quoted; it is also widely misread.

The EUR 31.2 billion is across roughly 160,000 essential and important entities. Per organisation, the average lands in the EUR 150,000 to 250,000 range, with sector and size driving most of the variance. A 250-employee mid-market essential entity in manufacturing or healthcare is on the higher end of that range. A 60-employee important entity in a less data-heavy sector is on the lower end.

ENISA's own implementing-cost guidance (Annex IV of Implementing Regulation (EU) 2024/2690) is consistent with the Frontier number but breaks it down differently: roughly 35-45 percent on tooling, 30-40 percent on personnel and training, 15-20 percent on certification and audit, 5-10 percent on incident-response retainers and managed services.

What this means for a CFO signing a 2026 budget: the tooling layer is roughly EUR 50,000 to EUR 120,000 a year for mid-market, depending on what is already in place. That tooling layer is what we are going to walk through.

What it does not mean: that buying a NIS2-ready bundle solves the problem. The personnel-training and certification budgets are larger than the tooling budget for most teams, and no tooling vendor reduces those. A vendor pitch that claims a 50 percent NIS2 cost reduction is almost always doing the math against the tooling-only line, not against the full programme cost.

## The five-tool stack mid-market teams quietly assembled

Across the thirty buyer conversations, the stack looks the same in 90 percent of cases. Five categories, with one or two named vendors per category. The category labels are stable; the vendor choices vary.

**1. Backup vendor.** Veeam Data Platform Foundation or Premium is the modal answer. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect at the smaller end. Annual cost in the EUR 15,000 to EUR 60,000 range for mid-market. Usually the longest-standing line item; predates NIS2 by years.

**2. DR site or DR-as-a-service.** Either a secondary cloud region with a runbook, a Veeam Cloud Connect or Rubrik Cloud Vault tenancy, or a contract with a managed DR provider. Annual cost EUR 8,000 to EUR 35,000. Rarely tested in practice; the runbook is usually more aspirational than operational.

**3. Test-data or data-masking tool.** Delphix (now Perforce DevOps Data) is the enterprise default. Tonic.ai, Redgate Test Data Manager, occasionally a custom-built rsync-and-mask script. Annual cost EUR 25,000 to EUR 90,000 for the licensed options. Most teams in our calls do not have this line item; they have what they hope is good enough staging instead. The Article 21(2)(e) audit conversation is what brings it onto the budget.

**4. Pen test contract.** A retainer with a security testing firm or an autonomous platform like Pentera or Horizon3.ai. Annual cost EUR 15,000 to EUR 50,000 for the autonomous tools, EUR 20,000 to EUR 80,000 for human-led engagements. Most teams have this. Most teams do it once or twice a year.

**5. GRC platform.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. Sometimes a homegrown spreadsheet for the smallest teams. Annual cost EUR 12,000 to EUR 60,000. Used for the supplier register, control-framework attestation, evidence collection, and (increasingly) SOC 2 or ISO 27001 audit support.

Five line items, three to five named vendors, typically EUR 75,000 to EUR 295,000 a year before personnel and training. Variance is wide but the structure is consistent.

The five contracts often do not talk to each other. The audit logs are not unified. The exit plans are written separately. The vendor reviews are done separately, sometimes by different procurement leads. This is the structural shape that NIS2 makes uncomfortable.

## Where the overlaps are

Every category in the stack overlaps with at least one other.

**Backup overlaps with DR**. Modern backup vendors all claim to be DR-capable. Veeam Data Platform with Cloud Connect is a DR product. Rubrik with Cloud Vault is a DR product. The two line items often pay for adjacent capabilities at the same vendor. Buyers who have not consolidated the line items historically had operational reasons (separate teams, separate SLAs); under NIS2's "single source of truth for recovery" expectation, the rationale weakens.

**Backup overlaps with test data**. Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles all offer some form of mountable backup for testing. They are not full Delphix replacements (the masking layer is separate, the database integration is shallower) but for many test-data use cases the backup tool is half the answer. Most teams do not realise it.

**Pen test overlaps with autonomous testing**. The retainer-based human pen test and the Pentera-style continuous testing are sometimes pitched as alternatives, sometimes as complements. In practice, a buyer with both is paying twice for adjacent capability. A buyer with neither has an Article 21(2)(f) gap.

**GRC overlaps with everything**. Drata claims integration with backup, DR, identity, vulnerability management, training, and incident response. The integrations vary in depth. A GRC platform with shallow integration to a backup tool produces compliance evidence that is not the same as the backup tool's own evidence; auditors are starting to ask which one is canonical.

The overlaps are not waste. They are the consequence of a stack assembled over a decade, before NIS2 made the consolidation question structural.

## Where the gaps are

The gaps are more interesting than the overlaps, because the gaps are what NIS2 surfaces.

**Patch validation against real production data**. None of the five categories do this well. Backup tools mount the backup; the mounted environment is the recovered backup, not current production. Test-data tools mask production data; the masked environment is realistic in shape but loses the configuration deltas. Pen test contracts test what they are pointed at, which is staging in 90 percent of cases. The gap between "we have tools" and "we can test a CVE patch against a current production-equivalent environment in under an hour" is real and structural.

**Continuous effectiveness assessment**. Annual cadence is what most teams do. Article 21(2)(f) wants something more frequent. None of the five categories produce weekly or bi-weekly evidence by default. The buyer either runs custom drills (rare, expensive) or accepts the annual cadence and hopes the auditor accepts it (increasingly, they do not).

**Supply-chain register collapse**. Each of the five vendors is its own register entry. Each carries its own DPA, SCC, sub-processor list, and exit plan. The register has five tier-1 entries before personnel-training tools, identity tools, observability tools, and IaaS get added. The supply-chain conversation, in NIS2 terms, is a register-management conversation as much as a security conversation. (See the [supply-chain post](/en/blog/nis2-supply-chain-self-hosted) for the structural argument.)

**Article 23 reporting workflow**. The 24-hour early warning, 72-hour notification, and one-month report are not produced automatically by any of the five categories. They require a SIEM, a SOC (in-house or outsourced), and a person who knows how to file with the national CSIRT. Smaller teams often do not have this. The first incident is the painful learning experience.

## What Rediacc collapses

Rediacc is one control plane with a unified audit log, replacing four of the five categories' core capability for self-hosted infrastructure.

**Backup** runs in two modes. Hot is a crash-consistent BTRFS snapshot. No downtime. Cold does a stop, snapshot, start cycle. Both schedule on systemd timers. Both ship to many destinations via rclone. Volumes are LUKS-encrypted. The operator holds the key. Rediacc-the-company never sees plaintext. See [Backup & Restore](/en/docs/backup-restore) and [Cross Backup Strategy](/en/docs/cross-backup).

**DR**: same primitive as backup, plus `rdc repo migrate` for cross-machine data movement, plus the fork primitive for fast bring-up of recovered state on a parallel machine. The DR site can be another Hetzner machine, an OVH machine, an on-prem rack, anywhere SSH reaches. No DR-vendor cloud in the data path.

**Test data and full-stack cloning** runs on BTRFS reflink. The fork is constant-time, no matter the repo size. Full-stack means data, configs, containers, and services. We forked a 128 GB repo in 7.2 seconds in our [PocketOS test](/en/blog/i-tested-rediacc-against-the-pocketos-incident). The fork is current production, not a stripped-down staging copy. See [Risk-Free Upgrades](/en/docs/risk-free-upgrades).

**Instant restore**: `rdc repo backup pull` from any rclone target into a fresh fork, brought up under a fork-specific subdomain covered by the parent repository's wildcard certificate. No DNS scramble, no certificate dance.

**Unified audit log.** 70+ event types across the control plane. They cover sign-ins, API tokens, config writes, repo lifecycle, backup, sync, terminal sessions, and machine ops. The chain is hash-linked on the operator workstation. `rdc audit verify` checks it end to end.

For a 250-employee mid-market essential entity, the consolidation is from four named vendors (backup, DR, test-data, instant-restore) to one. One licence, one audit log, one set of upgrade decisions, one register entry.

The fifth category, GRC, is not collapsed. We come back to that.

## What stays on your budget either way

This is the section that determines whether the rest of the post is honest. The two-column table:

| Removed by Rediacc | Still yours, line item by line item |
|---|---|
| Backup vendor licence | GRC platform (Drata, Vanta, OneTrust, AuditBoard, DataGuard) for the supplier register, control-framework attestation, evidence collection, and SOC 2 or ISO 27001 audit support |
| DR-site contract or DR-as-a-service tenancy | Certification audit costs (ISO 27001, SOC 2, BSI C5 if you need them; Rediacc itself is not certified yet, so you carry that cost meanwhile) |
| Test-data or masking tool licence | Personnel training and security awareness budget (NIS2 Article 21(2)(g)) |
| Instant-recovery licence at the backup vendor | Broader corporate MFA solution; Rediacc has TOTP on the portal, not a corporate MFA platform |
| | Pen testing contract or autonomous testing platform; Rediacc gives the target environment, not the testing capability |
| | SIEM and SOC for Article 23 detection and reporting; Rediacc gives forensic-grade artefacts, not the operational reporting layer |
| | IaaS provider (Hetzner, OVH, your colo, your bare metal); Rediacc runs on, not instead of, infrastructure |
| | Personnel running the program. Rediacc is a tooling layer, not a security team |

The right side of the table is longer than the left side. That is the honest shape of what NIS2 costs. Removing the backup-and-DR-and-test-data overlap saves real money and real register entries; it does not turn a security program into a SaaS subscription.

A buyer who reads this and concludes "I can replace Drata with Rediacc" is going to disappoint their auditor. The right read is: the data-plane vendor consolidation that Rediacc enables is the thing that GRC tools cannot do, and the register-and-evidence work that GRC tools do is the thing Rediacc does not. The two are complementary.

Three more links if you want depth. The public mapping is at [NIS2 and DORA](/en/docs/legal-nis2-dora). The broader framing is at [Compliance Overview](/en/docs/legal-overview). The commercial side on Rediacc is at [Subscription & Licensing](/en/docs/subscription-licensing).

## A reference scenario, structural not numeric

Take a 250-employee German manufacturing company. Annex II "important entity" classification. Production data on 4 to 6 servers, mostly self-hosted with one or two SaaS tools (CRM, payroll). EUR 80M annual revenue. Existing security team of 3.

**Before**, their data-plane stack:

- Veeam Data Platform Foundation, EUR 24,000/year
- Veeam Cloud Connect for DR, EUR 12,000/year
- A homegrown rsync-plus-pg_dump scheme for test data, free in licence but costs an SRE half a day every two weeks
- Annual pen test, EUR 22,000
- Drata for GRC, EUR 18,000/year

Five contracts. Two of them (Veeam, Veeam Cloud Connect) are with the same vendor but different SKUs. The data-plane line items total EUR 36,000/year before counting the pen test or GRC. The team produces an annual recovery test, no continuous effectiveness evidence, and a supplier register with five entries on the data-plane side alone.

**After**, with Rediacc on Hetzner for the self-hosted workloads:

- Rediacc Business tier, EUR 8,400/year (covers their repo size)
- Hetzner IaaS for primary and secondary, EUR 9,600/year combined (already in the budget; no new line item)
- The pen test contract stays (EUR 22,000)
- Drata stays (EUR 18,000)
- The homegrown test-data scheme is retired; the SRE half-day every two weeks goes to running the weekly effectiveness routine instead

Data-plane consolidation: 5 line items down to 1 (Rediacc) plus the existing IaaS line. The supplier register's data-plane section drops from 5 entries to 2. The continuous-effectiveness story is now weekly drills with hash-chained audit log evidence; the recovery-test story is now backed by `rdc machine backup status` output and a per-week restore drill.

The numbers are illustrative, not promises. Your stack is different. The shape, four to five line items collapsing into one plus existing IaaS, is what a real buyer conversation looks like.

## A note on what this is not

This post is not a Veeam takedown or a TCO calculator. Veeam runs the largest VM-backup market share in Europe for good reasons; their product is mature, their partner network is broad, their NIS2 marketing is strong, and a buyer choosing Veeam in 2026 is not making a mistake. The numbers in the reference scenario are illustrative, drawn from actual buyer conversations, not benchmarks. Run the structural analysis against your own contracts.

What this is: a buyer-side framing for a CFO who is renegotiating a backup, DR, or compliance contract in the next twelve months and wants to know what a self-hosted control plane changes about the line items.

## What to do next

If you are heading into a renewal cycle and the budget is open, three concrete moves:

1. **Pull last year's three biggest security and infrastructure line items.** Send them to your DPO, your CISO, and your auditor. Ask which ones were already redundant before NIS2 made it visible. Most teams find at least one overlap they have been paying for.
2. **Map your current data-plane stack against the five-category list above.** Note which categories you have one vendor for, which you have two, and which you have none. The "none" cells are the gaps NIS2 will surface.
3. **Run the supplier-register exercise from the [supply-chain post](/en/blog/nis2-supply-chain-self-hosted)** for each data-plane vendor. Count the register entries. The number is usually higher than the team expected.

If we are on the shortlist, the offer is concrete. Send your three biggest line items from last year's security and infrastructure budget. We will tell you which ones can be collapsed and which cannot, in writing, in a week. The answer will include the gaps, because the gap-naming is what makes the rest of the answer trustworthy.

Three more docs if you want to go deeper. [zero-cost backup](/en/docs/zero-cost-backup) explains why we run lighter on storage than the incumbents. [Cross Backup Strategy](/en/docs/cross-backup) covers intercontinental DR. [Subscription & Licensing](/en/docs/subscription-licensing) is the commercial side.

---
title: "Data Sovereignty"
description: "How Rediacc's self-hosted architecture satisfies data residency and sovereignty requirements across global jurisdictions."
category: "Legal"
order: 7
language: en
---

Many countries require personal data of their citizens to be stored and processed within national borders. Rediacc's self-hosted architecture satisfies these requirements by design: data stays on your machine, in your data center, in your jurisdiction. No data leaves the machine during cloning, and no third-party SaaS processes your data.

## Why Self-Hosted Solves Data Sovereignty

Cross-border data transfer is the hardest compliance problem in cloud computing. Every jurisdiction has different rules, adequacy decisions, and transfer mechanisms. Self-hosted eliminates the entire category:

- **No cross-border transfer**: CoW cloning (`cp --reflink=always`) duplicates data on the same machine
- **No third-party processor**: Rediacc runs on your infrastructure, not on Rediacc's servers
- **No adequacy assessment needed**: data never leaves the jurisdiction, so transfer rules don't apply
- **No standard contractual clauses**: there is no international data flow to regulate

## Jurisdiction Coverage

### European Union

The [GDPR](https://gdpr-info.eu/) restricts transfers of personal data outside the EU/EEA unless the destination provides adequate protection. The landmark Schrems II ruling invalidated the EU-US Privacy Shield, and the [EUR 1.2 billion fine against Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) demonstrated the cost of getting cross-border transfers wrong.

Self-hosted Rediacc deployed in the EU keeps all data within the EU. No transfer mechanism is needed. See [GDPR Compliance](/en/docs/legal-gdpr) for article-level mapping.

### China

The [Personal Information Protection Law (PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) requires personal data of Chinese citizens to be stored in China. Cross-border transfers require security assessments by the Cyberspace Administration of China (CAC). Self-hosted Rediacc on Chinese infrastructure avoids CAC security assessments entirely.

### Brazil

The [Lei Geral de Protecao de Dados (LGPD)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) requires adequate security measures and restricts international transfers. Self-hosted in Brazil eliminates transfer concerns and satisfies Art. 46's technical measures requirement through LUKS2 encryption and network isolation.

### India

The [Digital Personal Data Protection Act (DPDP Act, 2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) restricts transfers to countries not on a government-approved list. Self-hosted on Indian infrastructure means no transfer regardless of which countries get blacklisted. India's government and defense sectors strongly prefer on-premises solutions.

### Turkiye

The [KVKK (Law No. 6698)](https://kvkk.gov.tr/en/) restricts international transfers with complex adequacy requirements. Turkiye is not on the EU adequacy list, so cross-border transfers require explicit approval. Self-hosted in Turkiye eliminates this entirely.

### South Korea

The [Personal Information Protection Act (PIPA)](https://www.pipc.go.kr/eng/index.do) is one of the strictest globally and explicitly mandates encryption of personal data during storage and transmission. LUKS2 AES-256 directly satisfies this requirement. Fines of up to 3% of revenue.

### Japan

The [Act on Protection of Personal Information (APPI)](https://www.ppc.go.jp/en/legal/) restricts cross-border transfers unless the recipient country provides adequate protection. Self-hosted in Japan avoids transfer restrictions and aligns with the market's cultural preference for on-premises solutions.

### Australia

The [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) holds the disclosing entity liable for an overseas recipient's data handling (APP 8). Self-hosted eliminates this liability entirely. LUKS2 encryption and network isolation provide concrete "reasonable steps" under APP 11.

### United Arab Emirates

[Federal Decree-Law No. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) requires adequate security measures and restricts cross-border transfers. UAE's government and financial sectors strongly prefer on-premises deployments.

### Saudi Arabia

The [Personal Data Protection Law (PDPL)](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) requires personal data of Saudi residents to be stored and processed within Saudi Arabia. Self-hosted directly satisfies this strict localization requirement.

### Singapore

The [Personal Data Protection Act (PDPA)](https://sso.agc.gov.sg/Act/PDPA2012) requires reasonable security and restricts cross-border transfers. Self-hosted in Singapore, a major APAC data hub, satisfies regional compliance for ASEAN operations.

### Russia

[Federal Law 242-FZ](https://pd.rkn.gov.ru/) requires personal data of Russian citizens to be stored on servers in Russia. Violations can result in website blocking. Self-hosted on Russian soil provides compliance by architecture.

## The Pattern

Across all jurisdictions, the compliance equation is the same:

| Property | Cloud/SaaS | Self-Hosted Rediacc |
|----------|-----------|-------------------|
| Data location | Provider's data centers (may span borders) | Your machine, your jurisdiction |
| Transfer mechanism needed | Yes (SCCs, adequacy, consent) | No (no transfer occurs) |
| Third-party processor liability | Yes | No |
| Encryption control | Provider-managed keys | Your LUKS credentials, locally stored |
| Cloning/staging data | May cross borders or leave your control | CoW on same machine, same jurisdiction |

## Hosted Service: Regional Data Residency

For users of the hosted Rediacc service (not self-hosted), data residency is enforced through regional infrastructure. Three regions are available: EU (Frankfurt), US (Virginia), and Asia Pacific (Tokyo). Each region runs independent databases, storage, and email endpoints with no cross-region data flows. The EU region uses jurisdictional enforcement on R2 storage. See [Data Regions](/en/docs/data-regions) for the full technical breakdown.

---
title: "What Compliance Actually Requires"
description: "Rediacc runs on your infrastructure. You control your data. Here's how that aligns with major compliance frameworks."
category: "Legal"
order: 0
language: en
---

Rediacc runs entirely on your infrastructure. During cloning, backups, and deployments, your data stays on your machines. You're both the controller and processor. No third-party SaaS, no external access.

We map Rediacc's technical capabilities to major compliance requirements. Each page breaks down a specific regulation with references to the official legal text.

## Compliance Matrix

| Framework | Scope | Key Rediacc Capabilities |
|-----------|-------|--------------------------|
| [GDPR](/en/docs/legal-gdpr) | EU data protection and privacy | CoW cloning on same machine, LUKS2 encryption, zero-knowledge config store, audit logging, right to erasure via `rdc repo delete` |
| [SOC 2](/en/docs/legal-soc2) | Trust service criteria for service organizations | Encryption at rest, zero-knowledge config sync, network isolation, audit trail, backup and recovery |
| [HIPAA](/en/docs/legal-hipaa) | US health information protection | LUKS2 encryption, zero-knowledge config store, SSH-only access, isolated Docker daemons, transmission security |
| [CCPA](/en/docs/legal-ccpa) | California consumer privacy rights | Self-hosted (no data sale/sharing), zero-knowledge encryption, encrypted deletion, data inventory per repository |
| [ISO 27001](/en/docs/legal-iso27001) | Information security management controls | Asset management, cryptographic controls, zero-knowledge config store, access control, operations security |
| [PCI DSS](/en/docs/legal-pci-dss) | Payment card data protection | Network segmentation by architecture, mandatory encryption, audit logging, scope reduction via self-hosted |
| [NIS2 and DORA](/en/docs/legal-nis2-dora) | EU cybersecurity and financial resilience | Supply chain risk elimination, resilience testing via CoW cloning, encryption, incident detection |
| [Data Sovereignty](/en/docs/legal-data-sovereignty) | Global data residency laws (PIPL, LGPD, KVKK, PIPA, and more) | Self-hosted = data never leaves your jurisdiction. No cross-border transfers, no adequacy assessments |

## Architectural Foundations

Here's what connects them all: every compliance framework in this section maps back to the same technical foundation.

- **Encryption at rest**: Every repository is LUKS2 AES-256 encrypted. Credentials are stored only in the operator's local config, never on the server.
- **Network isolation**: Each repository gets its own Docker daemon, loopback IP subnet (/26), and iptables rules. Containers from different repositories cannot communicate.
- **Copy-on-write cloning**: `rdc repo fork` uses filesystem reflinks (`cp --reflink=always`). Data is duplicated on the same machine without any network transfer.
- **Audit logging**: 70+ event types covering authentication (login, 2FA, password changes, session revocation), API token lifecycle, config store operations, subscription/licensing activity, and CLI machine operations (repo lifecycle, backup, sync, terminal sessions). Accessible via admin dashboard and the portal activity page (with org-scoped filtering and JSON export). Machine operations are also recorded in your system logs for defense in depth.
- **Encrypted backup**: `rdc repo push/pull` transfers data over SSH. The backup destination receives LUKS-encrypted volumes.
- **Zero-knowledge config store**: Optional encrypted config sync across devices. Configs are encrypted client-side with AES-256-GCM before upload. The server stores only opaque blobs. The server cannot read SSH keys, credentials, IP addresses, or any plaintext config data. Key derivation uses passkey PRF extension + HKDF with domain separation. Member access is managed via X25519 key exchange, and revocation is immediate.

For details on these capabilities, see [Architecture](/en/docs/architecture), [Repositories](/en/docs/repositories), [Config Storage](/en/docs/config-storage), and [Account Security](/en/docs/account-security).

## Why It Matters

Compliance failures are expensive. Really expensive. The cases below show problems Rediacc's architecture structurally prevents:

| Incident | Fine | What went wrong |
|----------|------|----------------|
| [Meta: EU-US data transfers](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | EUR 1.2B | Personal data transferred across borders without adequate safeguards. Self-hosted means no transfer. |
| [Equifax: unencrypted data](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | $700M | 147 million records stored unencrypted with poor network segmentation. LUKS2 is mandatory, not optional. |
| [Target: lateral movement](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | $18.5M | Attackers pivoted from an HVAC vendor to payment systems over a flat network. Per-repo isolation prevents this. |
| [Anthem: unencrypted PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | $16M | 79 million health records stored without encryption. LUKS2 AES-256 is always on. |
| [Blackbaud: SaaS breach cascade](https://www.sec.gov/newsroom/press-releases/2023-48) | $49.5M | Ransomware at one SaaS vendor exposed data from 13,000+ customer organizations. Self-hosted means a vendor breach cannot reach your data. |
| [British Airways: poor segmentation](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | GBP 20M | Attackers injected malicious code due to inadequate network controls. Isolated Docker daemons and iptables prevent lateral access. |
| [Google: right to erasure](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | EUR 50M | Difficulty fully erasing data across distributed systems. Cryptographic erasure via LUKS destroy is instant and complete. |

## Important Notice

These pages explain how Rediacc's architecture aligns with compliance requirements. But here's the reality: compliance is bigger than software. You'll need policies, procedures, training, and probably third-party audits. Rediacc handles the infrastructure part. Work with your legal and compliance teams on the rest.

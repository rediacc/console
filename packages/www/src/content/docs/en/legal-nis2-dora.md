---
title: "NIS2 and DORA"
description: "How Rediacc addresses EU NIS2 cybersecurity directive and DORA digital operational resilience requirements."
category: "Legal"
order: 8
language: en
---

NIS2 and DORA are EU regulations that impose cybersecurity and operational resilience requirements on critical infrastructure and financial sector organizations. Both took effect in 2025 and apply broadly across EU industries.

## NIS2 Directive

The Network and Information Security Directive 2 (NIS2) establishes cybersecurity requirements for "essential" and "important" entities across sectors including energy, transport, health, digital infrastructure, and public administration.

Full text: [Directive (EU) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### NIS2 Requirements Mapping

| NIS2 Requirement | Rediacc Capability |
|-----------------|-------------------|
| Risk management measures (Art. 21) | LUKS2 encryption at rest, network isolation per repository, SSH-only access, audit logging (70+ event types including machine operations) |
| Incident handling (Art. 21(2)(b)) | 70+ event types (auth, tokens, config, licensing, machine operations) provide forensic trail. Per-repository isolation limits blast radius. |
| Business continuity (Art. 21(2)(c)) | `rdc repo push/pull` with multi-destination encrypted backup. CoW snapshots for instant rollback. |
| Supply chain security (Art. 21(2)(d)) | Self-hosted eliminates SaaS supply chain risk. No third-party cloud provider processes your data. |
| Network security (Art. 21(2)(e)) | Per-repository Docker daemons, iptables rules, loopback IP isolation (/26 subnets). |
| Encryption (Art. 21(2)(h)) | LUKS2 AES-256 mandatory encryption. Zero-knowledge config store with AES-256-GCM. |
| Access control (Art. 21(2)(i)) | SSH key authentication, scoped API tokens with IP binding, two-factor authentication (TOTP). |
| Incident reporting, 24h early warning (Art. 23) | Audit logging enables rapid incident detection and scoping. |

### Supply Chain Risk

Supply chain security is a central NIS2 concern (Art. 21(2)(d)). Organizations must assess and manage risks from their ICT service providers and suppliers.

Self-hosted Rediacc removes the largest supply chain attack surface, and yes, I know that sounds obvious. Here's why it matters: no third-party SaaS handles your data, no cloud provider has logical access to your infrastructure, and no shared-tenant environment creates exposure to other customers' security posture. SaaS vendor breaches have caused cascading damage across thousands of organizations. [Blackbaud's 2020 ransomware attack exposed data from 13,000+ customer organizations, costing $49.5 million in settlements.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Digital Operational Resilience Act)

DORA establishes requirements for ICT risk management, incident reporting, resilience testing, and third-party risk management for the EU financial sector. It applies to banks, insurance companies, investment firms, crypto-asset service providers, and their critical ICT third-party providers.

Full text: [Regulation (EU) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### DORA Requirements Mapping

| DORA Requirement | Rediacc Capability |
|-----------------|-------------------|
| ICT risk management framework (Art. 6) | Encryption, isolation, audit logging, and backup form the technical controls layer. |
| Protection and prevention (Art. 9) | LUKS2 AES-256 encryption at rest. Network isolation prevents lateral movement. SSH-only access. |
| Detection (Art. 10) | 70+ event types including machine operations (repo lifecycle, backup, sync, terminal). Admin dashboard and portal with per-user, per-team filtering. Machine operations also in system logs for defense in depth. |
| Response and recovery (Art. 11) | CoW snapshots for instant rollback. `rdc repo push/pull` for multi-destination recovery. Fork-based disaster recovery testing. |
| ICT third-party risk (Art. 28-30) | Self-hosted eliminates the "critical ICT third-party provider" classification entirely. |
| Digital operational resilience testing (Art. 24-27) | CoW cloning enables threat-led penetration testing on production-like environments without data exposure. Clone, test, destroy. |

### Third-Party ICT Provider Risk

Here's where DORA actually gets hard: managing critical ICT third-party providers (Art. 28-30). Financial institutions must maintain registers of ICT providers, conduct risk assessments, negotiate specific contractual provisions, and plan exit strategies.

Self-hosted Rediacc avoids this entirely. No ICT third-party provider to register, assess, or monitor. The financial institution controls its own infrastructure directly.

### Resilience Testing

DORA mandates digital operational resilience testing, including threat-led penetration testing (TLPT) for large institutions (Art. 26). Zero-copy cloning handles this directly:

1. Fork the production environment (instant, same machine, no data transfer)
2. Run penetration tests against the fork
3. Destroy the fork when done

Production is never touched, yet the test environment is an exact replica. No data leaves the machine.

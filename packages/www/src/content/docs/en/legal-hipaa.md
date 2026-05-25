---
title: "HIPAA Compliance"
description: "How Rediacc's encryption and isolation architecture maps to HIPAA safeguard requirements for protecting health information."
category: "Legal"
order: 3
language: en
---

The Health Insurance Portability and Accountability Act (HIPAA) is a United States federal law that establishes standards for protecting sensitive patient health information (PHI). It applies to covered entities (healthcare providers, health plans, healthcare clearinghouses) and their business associates.

Full text: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Safeguard Mapping

HIPAA requires administrative, technical, and physical safeguards. The table below maps these to Rediacc's capabilities.

### Technical Safeguards

| Requirement | HIPAA Reference | Rediacc Capability |
|-------------|----------------|-------------------|
| Access control | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | SSH key-based authentication. API tokens with IP binding and scope restrictions. Per-repository Docker daemon isolation prevents cross-repository access. |
| Audit controls | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | 70+ event types covering authentication, API tokens, config operations, licensing, and machine operations (repo lifecycle, backup, sync, terminal). Per-user and per-team trace. Export via admin dashboard, portal activity page, or `rdc audit` CLI. |
| Integrity controls | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | CoW snapshots preserve original data before modifications. `rdc repo validate` verifies repository integrity and backup health (LUKS container, filesystem consistency, configuration). |
| Encryption at rest | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | LUKS2 AES-256 encryption on all repository volumes. Credentials stored only in the operator's local config, never on the server. Config store uses zero-knowledge AES-256-GCM encryption with split-key derivation. Even the server cannot decrypt stored configs. |
| Transmission security | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | All remote operations use SSH. Backup transport is encrypted end-to-end. No unencrypted data transfer. |

### Administrative Safeguards

| Requirement | Rediacc Capability |
|-------------|-------------------|
| Workforce access management | API tokens with scoped permissions. Team-based access control. Token auto-revocation on team removal. |
| Security incident procedures | Audit logs provide forensic trail of all operations. Per-repository isolation limits blast radius. |
| Contingency planning | `rdc repo push/pull` supports multi-destination encrypted backup. CoW snapshots enable instant recovery. |

### Physical Safeguards

| Requirement | Rediacc Capability |
|-------------|-------------------|
| Facility access controls | Self-hosted: your organization controls physical security of your servers. No dependency on third-party data centers for core operations. |
| Workstation security | LUKS encrypts all data at rest. Unmounted repositories are encrypted blobs on disk, unreadable without the operator's credentials. |

## Business Associate Agreement (BAA)

Since Rediacc is self-hosted software that runs on your infrastructure, it does not process, store, or transmit PHI through Rediacc's (the company's) systems. The typical BAA requirement applies to your infrastructure provider (cloud provider or colocation facility), not to Rediacc.

Rediacc operates as a software tool on your servers, similar to an operating system or database engine. It has no access to your data. The optional config store syncs encrypted blobs through Rediacc's servers, but its zero-knowledge design means the server cannot decrypt the contents. It stores only opaque ciphertext.

## Development Environments with PHI

When cloning production environments that contain PHI for development purposes, use the Rediaccfile `up()` lifecycle hook to run sanitization scripts that:

- Strip PHI from database tables
- Replace patient identifiers with synthetic data
- Remove session tokens and API keys

Developers get production-like infrastructure with de-identified data, satisfying the HIPAA minimum necessary standard.

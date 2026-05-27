---
title: "ISO 27001 Compliance"
description: "How Rediacc maps to ISO 27001 information security controls for encryption, access management, and operations security."
category: "Legal"
order: 5
language: en
---

ISO/IEC 27001 is an international standard for information security management systems (ISMS), published by the International Organization for Standardization (ISO) and the International Electrotechnical Commission (IEC). The current version is ISO/IEC 27001:2022.

Reference: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc is one component of the technical controls layer within an ISMS. The table below maps Rediacc's capabilities to relevant Annex A control domains.

## Annex A Controls Mapping

| Control Domain | Control | Rediacc Capability |
|---------------|---------|-------------------|
| **A.8**, Asset management | A.8.1 Inventory of assets | Each repository is a discrete, identifiable asset with a unique GUID. `rdc machine query --name <machine> --repositories` lists all repositories with size, mount state, and container count. |
| **A.8**, Asset management | A.8.24 Use of cryptography | LUKS2 AES-256 mandatory encryption on all repositories. Key management: credentials stored in the operator's local config only, never on the server. |
| **A.9**, Access control | A.9.2 User access management | SSH key authentication. API tokens with IP binding, team scoping, and automatic revocation on team removal. Two-factor authentication (TOTP) support. |
| **A.10**, Cryptography | A.10.1 Cryptographic controls | LUKS2 with configurable key parameters. Per-repository encryption credentials. All remote transport over SSH. Config store implements zero-knowledge encryption: AES-256-GCM with HKDF key derivation, X25519 member key exchange, and time-windowed SDK keys for instant revocation. |
| **A.12**, Operations security | A.12.3 Backup | `rdc repo push/pull` with encrypted offsite storage to multiple destinations (SSH, S3, B2, Azure, GDrive). CoW snapshots for point-in-time recovery. `rdc repo validate` verifies backup health and repository integrity. |
| **A.12**, Operations security | A.12.4 Logging and monitoring | 70+ event types (auth, API tokens, config, licensing, machine operations). Machine health monitoring via `rdc machine query`. Container status and resource monitoring. |
| **A.13**, Communications security | A.13.1 Network security management | Per-repository Docker daemon isolation. iptables rules block cross-repository traffic. Loopback IP subnets (/26) per repository. Reverse proxy with TLS termination for external access. |
| **A.14**, System development | A.14.2 Security in development | Fork-based development environments provide production parity without production data exposure. Rediaccfile lifecycle hooks enable automated data sanitization in cloned environments. |

## Asset Management

Rediacc's repository model naturally supports asset inventory requirements:

- Every repository has a unique GUID assigned at creation
- Repositories are enumerable per machine (`rdc machine query --repositories`)
- Each repository's encryption status, mount state, container count, and disk usage are visible
- Fork relationships track the lineage of cloned environments

## Change Management

The fork-test-promote workflow aligns with ISO 27001's change management requirements:

1. **Fork**: Create an isolated copy of the production environment
2. **Test**: Apply and validate changes in the fork
3. **Promote**: Use `rdc repo takeover` to swap the fork into production
4. **Audit**: All operations are logged with timestamps and actor identification

## Continuous Improvement

- Audit log export supports periodic security reviews
- Machine health checks (`rdc machine query --system`) support operational monitoring
- `rdc repo validate` verifies backup health after each operation

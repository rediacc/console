---
title: "SOC 2 Compliance"
description: "How Rediacc maps to SOC 2 Trust Service Criteria for security, availability, and confidentiality."
category: "Legal"
order: 2
language: en
---

SOC 2 (System and Organization Controls 2) is a framework developed by the American Institute of Certified Public Accountants (AICPA) for evaluating an organization's controls related to security, availability, processing integrity, confidentiality, and privacy.

Reference: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Trust Service Criteria Mapping

| Trust Principle | Criteria | Rediacc Capability |
|----------------|----------|-------------------|
| **Security** (CC6) | Logical access controls, encryption | LUKS2 AES-256 encryption at rest. Credentials stored only in the operator's local config (`~/.config/rediacc/`), never on the server. SSH key-based access. Isolated Docker daemons per repository. |
| **Availability** (A1) | System recovery and resilience | `rdc repo push/pull` with encrypted offsite copies to SSH, S3, B2, Azure, or GDrive. CoW snapshots for instant rollback. Fork-based upgrades for zero-downtime changes. |
| **Processing Integrity** (PI1) | Accurate and complete processing | Deterministic Rediaccfile lifecycle hooks (`up`/`down`) ensure consistent deployments. `rdc repo validate` verifies repository integrity and backup health after unexpected shutdowns or backup operations. |
| **Confidentiality** (C1) | Data protection from unauthorized access | Per-repository encryption with unique LUKS credentials. Network isolation via iptables, separate Docker daemons, and loopback IP subnets. Containers from different repositories cannot see each other. Zero-knowledge config store encrypts configs client-side before upload. The server stores only opaque blobs it cannot decrypt. |
| **Privacy** (P1-P8) | Personal data handling | Self-hosted: no data egress during operations. Audit trail for all data access. Encryption key management under customer control. Config store uses split-key derivation (passkey PRF + server secret) so neither party alone can access data. |

## Audit Trail

Rediacc logs 70+ event types covering:

- **Authentication**: login, logout, password changes, 2FA enable/disable, session revocation
- **Authorization**: API token creation/revocation, role changes, team membership
- **Configuration**: config store push/pull, member management, access failures (IP mismatch, SDK denied)
- **Licensing**: repo license issuance, machine slot tracking, subscription changes
- **Machine operations**: repository create/start/stop/delete, fork, backup push/pull, file sync, terminal sessions

These logs are accessible through the admin dashboard (with filtering by user, team, and date), the portal activity page (with org-scoped type and date filtering for org admins), and the `rdc audit` CLI for programmatic export. Machine operations are also recorded in your system logs for defense in depth.

## Change Management

The fork-based workflow supports controlled change management:

1. Fork a production repository (`rdc repo fork`)
2. Apply and test changes on the fork
3. Validate the fork independently
4. Promote the fork to production (`rdc repo takeover`)

Each step is logged with timestamps and actor identification.

## Access Control

- **Machine access**: SSH key authentication only. No password-based SSH.
- **API tokens**: Scoped permissions, optional IP binding, automatic revocation on team removal.
- **Repository isolation**: Each repository has its own Docker daemon socket. Access to one repository does not grant access to another on the same machine.
- **Config store tokens**: Single-use rotating tokens with IP binding on first use, 24-hour auto-expiry, and 3-request grace window for concurrency. Member access managed via X25519 key exchange with immediate revocation.

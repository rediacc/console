---
title: "SOC 2 Compliance"
description: "Here's the thing about SOC 2: auditors want evidence your controls work. Rediacc gives you the logs, the change-management trail, and everything else they're going to ask for."
category: "Legal"
order: 2
language: en
---

I know what SOC 2 is because I've sat through audit meetings. Auditors use the AICPA framework to check if your controls actually work, not just if you claim they work. Five Trust Service Criteria: security, availability, processing integrity, confidentiality, and privacy.

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

So Rediacc logs 70+ different event types. User actions, system changes, configuration updates, access control modifications, security events, fork operations, audit trails. I know that sounds like a lot, but auditors actually care about seeing this stuff.

- **Authentication**: login, logout, password changes, 2FA enable/disable, session revocation
- **Authorization**: API token creation/revocation, role changes, team membership
- **Configuration**: config store push/pull, member management, access failures (IP mismatch, SDK denied)
- **Licensing**: repo license issuance, machine slot tracking, subscription changes
- **Machine operations**: repository create/start/stop/delete, fork, backup push/pull, file sync, terminal sessions

Two ways to get these logs. Admin dashboard with user, team, and date filtering. Portal activity page for org admins, type and date filtering, with JSON export you can pipe into your own tools. Machine operations also log to your system logs, so you've got defense in depth.

## Change Management

Forks make change management auditable. You fork production, you get a copy of live state. Test it. Review it. Promote it or discard it. Every step timestamped and tied to a person. That's what auditors want to see: no anonymous changes.

1. Fork a production repository (`rdc repo fork`)
2. Apply and test changes on the fork
3. Validate the fork independently
4. Promote the fork to production (`rdc repo takeover`)

Every step: logged. Timestamped. Pinned to a person. No 'I don't know who changed that' moments.

## Access Control

- **Machine access**: SSH key authentication only. No password-based SSH.
- **API tokens**: Scoped permissions, optional IP binding, automatic revocation on team removal.
- **Repository isolation**: Each repository has its own Docker daemon socket. Access to one repository does not grant access to another on the same machine.
- **Config store tokens**: Single-use rotating tokens with IP binding on first use, 24-hour auto-expiry, and 3-request grace window for concurrency. Member access managed via X25519 key exchange with immediate revocation.

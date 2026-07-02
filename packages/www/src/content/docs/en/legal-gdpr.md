---
title: "GDPR Compliance"
description: "How Rediacc's self-hosted architecture maps to GDPR requirements for data protection and privacy."
category: "Legal"
order: 1
language: en
---

The General Data Protection Regulation (GDPR) is the European Union's data protection law, in effect since May 2018. It governs how organizations collect, process, and store personal data of individuals in the EU.

Full text: [Regulation (EU) 2016/679](https://gdpr-info.eu/)

## Article Mapping

The table below maps specific GDPR articles to Rediacc's technical capabilities.

| Article | Requirement | Rediacc Capability |
|---------|-------------|-------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Principles | Data minimization, integrity, confidentiality | CoW clones (`cp --reflink=always`) duplicate data on the same machine without network transfer. LUKS2 AES-256 encrypts all data at rest. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Right to erasure | Delete personal data on request | `rdc repo delete` cryptographically erases the LUKS volume. Deleting a fork removes the cloned copy entirely. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Data protection by design | Privacy by default | Encryption is mandatory, not optional. Each repository gets an isolated Docker daemon and network. No data sharing between repositories. The config store uses zero-knowledge encryption: configs are encrypted client-side with AES-256-GCM before upload, so the server cannot read any plaintext data. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Processor | Third-party data processing obligations | Self-hosted: Rediacc runs on your infrastructure. No data leaves your machine during fork, clone, or backup operations. No SaaS component processes personal data. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Records of processing | Maintain processing activity records | Audit logging tracks 70+ event types: authentication, API tokens, config store operations, licensing, and CLI machine operations (repo lifecycle, backup, sync, terminal). Export via admin dashboard or the portal activity page (JSON export available). |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Security of processing | Appropriate technical measures | LUKS2 AES-256 encryption at rest, network isolation via iptables and separate Docker daemons, loopback IP subnets (/26) per repository. Config store uses triple-layer encryption: time-windowed SDK keys, split-key CEK derivation (passkey + server secret), and org passphrase encryption. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Breach notification | 72-hour notification with forensic trail | Audit logs provide a forensic trail of all operations. Self-hosted architecture limits blast radius to individual repositories. |

## Data Residency

CoW clones never leave the source machine. The `rdc repo fork` command creates a filesystem-level copy using reflinks. No data is transferred over the network.

For cross-machine operations, `rdc repo push/pull` transfers data over SSH. The backup destination receives LUKS-encrypted volumes that cannot be read without the operator's credentials.

## Environment Cloning and Data Masking

When cloning production environments for development or testing, the Rediaccfile `up()` lifecycle hook runs sanitization scripts after a fork is created: strip PII from databases, replace real emails with test addresses, remove API tokens and session data, anonymize log files. The development environment gets production structure without production identities, satisfying the data minimization principle ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Zero-Knowledge Config Store

The optional config store allows syncing CLI configurations across devices. It is designed so the server has zero knowledge of config contents:

- **Client-side encryption**: Configs are encrypted with AES-256-GCM before upload. The encryption key (CEK) is derived from a passkey PRF secret and a server-held secret using HKDF with domain separation. Neither party alone can derive the key.
- **Server sees only opaque blobs**: SSH keys, credentials, IP addresses, network topology. None of this is visible to the server. Only metadata (config IDs, versions, timestamps) is stored in plaintext.
- **Member access via X25519**: When a team member is added, the CEK is encrypted with their X25519 public key and relayed by the server. The server never sees the CEK in plaintext.
- **Immediate revocation**: Removing a member deletes their wrapped CEK and revokes their tokens. Future configs use new SDK epochs inaccessible to the removed member.
- **Rotating tokens**: CLI authentication uses single-use rotating tokens (3-request grace window), IP-bound on first use, with 24-hour auto-expiry.

Even a full server compromise cannot expose config contents. The server never has the key.

For details, see [Config Storage](/en/docs/config-storage).

## Data Controller and Processor

Because Rediacc is self-hosted software, your organization is both the data controller and data processor. Rediacc (the company) does not access, process, or store your data. There is no data processing agreement required with Rediacc for the self-hosted product, as no personal data flows to Rediacc's infrastructure.

The config store is the one component that touches Rediacc's servers (for sync), but its zero-knowledge design means the server stores only encrypted blobs it cannot decrypt.

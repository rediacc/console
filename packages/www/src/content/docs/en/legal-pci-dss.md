---
title: "PCI DSS Compliance"
description: "How Rediacc maps to PCI DSS requirements for protecting payment card data with encryption, network segmentation, and access control."
category: "Legal"
order: 6
language: en
---

The Payment Card Industry Data Security Standard (PCI DSS) is required for any organization that stores, processes, or transmits cardholder data. The current version is PCI DSS v4.0.1.

Reference: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Requirements Mapping

| PCI DSS Requirement | Description | Rediacc Capability |
|---------------------|-------------|-------------------|
| **Req 1**, Network security controls | Install and maintain network security controls | Per-repository iptables rules block all cross-repository traffic. Each repository gets its own loopback IP subnet (/26). |
| **Req 2**, Secure configurations | Apply secure configurations to all system components | Rediaccfile lifecycle hooks enforce deterministic, reproducible configurations. No default credentials. LUKS keys are operator-generated. |
| **Req 3**, Protect stored account data | Protect stored account data with encryption | LUKS2 AES-256 encryption on all repository volumes. Encryption is mandatory, not optional. Cryptographic erasure via LUKS key destruction. |
| **Req 4**, Protect data in transit | Protect cardholder data with strong cryptography during transmission | All remote operations over SSH. Backup transport encrypted end-to-end. No unencrypted data paths. |
| **Req 6**, Secure development | Develop and maintain secure systems and software | CoW cloning creates isolated test environments without exposing production cardholder data to development networks. Fork-test-promote workflow. |
| **Req 7**, Restrict access | Restrict access to system components and cardholder data by business need to know | Per-repository Docker daemon sockets. Access to one repository does not grant access to another. SSH key-based authentication. |
| **Req 8**, Identify users and authenticate | Identify users and authenticate access to system components | SSH key authentication. API tokens with IP binding and scoped permissions. Two-factor authentication (TOTP). |
| **Req 9**, Restrict physical access | Restrict physical access to cardholder data | Self-hosted: physical security is under your direct control. LUKS encryption renders stolen drives unreadable. |
| **Req 10**, Log and monitor | Log and monitor all access to system components and cardholder data | 70+ event types (auth, API tokens, config, licensing, machine operations). Admin dashboard and portal with filtering by user, team, type, and date. `rdc audit` CLI for programmatic export. Machine operations also in system logs for defense in depth. |
| **Req 12**, Organizational policies | Support information security with organizational policies and programs | Self-hosted eliminates third-party processor scope (Req 12.8). Reduces PCI DSS compliance boundary. |

## Network Segmentation

PCI DSS leans hard on segmentation: isolate the cardholder data environment (CDE), or fail the audit. Rediacc gives you that segmentation by default:

- Each repository runs in its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`
- Repositories have isolated loopback IP subnets (127.0.x.x/26, 61 usable IPs per network)
- iptables rules enforced by renet block all cross-daemon traffic
- Containers from different repositories cannot communicate at the network level

A payment processing repository runs on its own Docker daemon and its own loopback subnet, network-isolated from every other application on the same machine. No extra firewall rules to write.

## Scope Reduction

Self-hosted Rediacc reduces PCI DSS compliance scope:

- No third-party cloud provider in the cardholder data flow
- No SaaS vendor to evaluate under Req 12.8 (third-party service providers)
- Physical security controls are under your direct management
- Encryption keys are stored only in the operator's local config

## Enforcement Cases

Weak segmentation and missing encryption are behind the most costly PCI DSS enforcement actions:

- Heartland Payment Systems (2008): attackers moved laterally across 48 databases due to poor network segmentation, exposing 130 million card numbers. [Total cost exceeded $200 million.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): attackers pivoted from an HVAC vendor's network access to point-of-sale systems due to flat network architecture, capturing 40 million payment cards. [Settled for $18.5 million with 47 state AGs.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)

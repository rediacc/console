---
title: "CCPA Compliance"
description: "How Rediacc's self-hosted model addresses California Consumer Privacy Act requirements for consumer data protection."
category: "Legal"
order: 4
language: en
---

The California Consumer Privacy Act (CCPA) is a state law that gives California consumers rights over their personal information, including the right to know what data is collected, the right to delete it, and the right to opt out of its sale.

Reference: [California Attorney General, CCPA](https://oag.ca.gov/privacy/ccpa)

## Consumer Rights Mapping

CCPA focuses on consumer rights related to personal information. Rediacc is a self-hosted tool deployed on your infrastructure, not a third-party service that collects or sells consumer data. The table below maps CCPA rights to how Rediacc supports your organization's compliance.

| CCPA Right | Requirement | Rediacc Capability |
|-----------|-------------|-------------------|
| Right to know (1798.100) | Disclose categories and purposes of data collected | Audit logs track all data operations. Self-hosted: your organization retains full visibility into what data exists in each repository. |
| Right to delete (1798.105) | Delete consumer's personal information on request | `rdc repo destroy` cryptographically erases the LUKS-encrypted volume. Fork deletion removes cloned copies. |
| Right to opt-out (1798.120) | Do not sell or share personal information | Self-hosted architecture: no data transfers to Rediacc or any third party. Data stays on your servers. Config store sync uses zero-knowledge encryption. Even the sync server cannot read the data. |
| Data security (1798.150) | Implement reasonable security measures | LUKS2 AES-256 encryption, network isolation, SSH-only access, isolated Docker daemons, audit logging. Config store uses triple-layer encryption with split-key derivation and rotating single-use tokens. |

## Service Provider Status

Rediacc as software does not access, process, or store consumer data. Your IT team operates Rediacc on your own infrastructure. No data flows to Rediacc the company. The implications:

- Rediacc is not a "service provider" under CCPA (it does not process data on your behalf)
- No data processing agreement is required with Rediacc for the self-hosted product
- Your CCPA obligations are between your organization and your consumers

## Data Inventory

Each Rediacc repository is a discrete, encrypted unit of data with a unique GUID. You can inventory exactly what data exists where:

- `rdc machine query --name <machine> --repositories` lists all repositories on a machine with size and mount status
- Each repository is isolated at the filesystem, network, and container level
- Fork relationships are tracked, so you can identify all copies of a dataset

CCPA requires data mapping. Rediacc's repository model provides it: one GUID per dataset, enumerable per machine, with fork lineage tracked.

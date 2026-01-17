---
title: "Vault"
description: "Manage encrypted vault data for resources."
category: "CLI API Reference"
language: "en"
---

# Vault

Manage encrypted vault data for resources.

## Table of Contents

- [set](#set)

## set

Update vault data for any resource type

#### API Information

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates the encrypted vault configuration for teams, machines, regions, bridges, organization, repositories, storages, or schedules. Vaults store sensitive configuration data and credentials.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `resourceType` | string | Yes | - | Type of resource to update (choices: team, machine, region, bridge, organization, repository, storage, schedule) | machine |
| `name` | string | No | - | Resource name (not needed for 'organization') | web-server-01 |
| `file` | string | No | - | File containing JSON vault data (use '-' for stdin) | vault-config.json |
| `team` | string | No | - | Team name (required for machine, repository, storage, schedule) | dev-team |
| `region` | string | No | - | Region name (required for bridge) | us-east |
| `vault-version` | string | No | - | Vault schema version | 2 |


#### Examples

```bash
rediacc vault set machine web-01 machine-config.json --team prod
```
Update machine vault from file

```bash
echo '{"SSH_PRIVATE_KEY":"..."}' | rediacc vault set team dev-team -
```
Update team vault from stdin

```bash
rediacc vault set organization organization-settings.json
```
Update organization-wide vault

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc vault set --resource-type <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "resourceType": "machine",
    "name": "web-server-01",
    "file": "vault-config.json"
}'
```

#### Notes

Vault data is encrypted with master password. Always backup current vault before updating. Use 'inspect' commands to view current vault.

#### Business Rules

- User must be authenticated to perform this operation
- User must have appropriate access to the entity
- Vault data must be valid JSON format
- Vault data is encrypted with master password before storage
- Maximum vault size is 64KB after encryption
- Organization vault requires organization admin permissions
- Team vault requires team membership
- Entity-specific vaults require team membership
- Previous vault data is completely replaced
- Vault updates are tracked in audit logs for security

#### Success Message

`Successfully updated {resource_type} vault`


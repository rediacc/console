---
title: "Inspect"
description: "Inspect resources and their details."
category: "CLI API Reference"
language: "en"
---

# Inspect

Inspect resources and their details.

## Table of Contents

- [machine](#machine)
- [repository](#repository)

## machine

Get detailed information about a machine

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamMachines`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows comprehensive information about a specific machine including its configuration, status, assigned bridge, and decrypted vault data.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that owns the machine | production |
| `name` | string | Yes | - | Machine name | web-server-01 |


#### Examples

```bash
rediacc inspect machine prod web-01
```
Inspect production web server

```bash
rediacc inspect machine dev database --output json
```
Get machine details in JSON format

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc inspect machine --team <value> --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamMachines" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "production",
    "name": "web-server-01"
}'
```

#### Notes

Shows decrypted vault if master password is set. Includes IP address, SSH credentials, and custom configuration.

#### Business Rules

- Requires team member or higher permissions
- Machine must belong to specified team
- Shows machine GUID and creation timestamp
- Displays current status and assigned bridge
- Vault data is decrypted if master password is set
- Machine names are case-insensitive for lookup
- Shows SSH connection details from vault
- Includes datastore path configuration
- Reveals all custom fields in machine vault
- Access is logged in audit trail

## repository

Get detailed info about a repository

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamRepositories`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows comprehensive information about a specific repository including vault configuration, size, and settings.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that owns the repository | dev-team |
| `name` | string | Yes | - | Repository name | web-app |


#### Examples

```bash
rediacc inspect repository dev-team web-app
```
Inspect web-app repository

```bash
rediacc inspect repository prod api --output json
```
Get repository details in JSON

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc inspect repository --team <value> --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamRepositories" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "dev-team",
    "name": "web-app"
}'
```

#### Notes

Shows decrypted vault if master password is set. Includes size, type, and configuration details.

#### Business Rules

- Requires team member or higher permissions
- Repository must belong to specified team
- Shows repository GUID and creation timestamp
- Displays associated machine and its status
- Vault data is decrypted if master password is set
- Repository names are case-insensitive for lookup
- Shows Docker configuration if present in vault
- Includes mount paths and datastore locations
- Reveals environment variables stored in vault
- Access is logged in audit trail


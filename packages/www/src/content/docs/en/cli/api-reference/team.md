---
title: "Team"
description: "Team management commands."
category: "CLI API Reference"
language: "en"
---

# Team

Team management commands.

## Table of Contents

- [update-team-vault](#update-team-vault)

## update-team-vault

update-team-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateTeamVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `vault` | string | No | - |  |  |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc team update-team-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateTeamVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "vault": "example-vault",
    "vaultVersion": "example-vault_version"
}'
```

#### Success Message

`Operation completed successfully`


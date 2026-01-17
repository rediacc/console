---
title: "Region"
description: "Region management commands."
category: "CLI API Reference"
language: "en"
---

# Region

Region management commands.

## Table of Contents

- [update-region-vault](#update-region-vault)

## update-region-vault

update-region-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateRegionVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `region` | string | Yes | - |  |  |
| `vault` | string | No | - |  |  |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc region update-region-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateRegionVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "region": "example-region",
    "vault": "example-vault",
    "vaultVersion": "example-vault_version"
}'
```

#### Success Message

`Operation completed successfully`


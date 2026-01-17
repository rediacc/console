---
title: "Audit"
description: "Audit logging and compliance commands."
category: "CLI API Reference"
language: "en"
---

# Audit

Audit logging and compliance commands.

## Table of Contents

- [trace](#trace)

## trace

Get detailed audit trail for entity

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetEntityAuditTrace`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Retrieves comprehensive audit information for a specific entity including all changes, access logs, and related operations.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `entityType` | string | Yes | - |  |  |
| `entityIdentifier` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc audit trace
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetEntityAuditTrace" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "entityType": "example-entity_type",
    "entityIdentifier": "example-entity_identifier"
}'
```

#### Business Rules

- User must be authenticated with valid credentials
- Regular users can only view their own audit history
- Team members can view audit for team resources
- Administrators can view all organization entity audits
- Audit retention varies by subscription tier (7-365 days)
- Maximum 100 records shown at once
- Sensitive operations masked for non-administrators
- Entity must exist and belong to your organization
- Region, bridge, permissions require admin access
- Results sorted newest to oldest


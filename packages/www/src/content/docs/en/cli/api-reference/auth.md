---
title: "Authentication"
description: "Authentication and session management commands."
category: "CLI API Reference"
language: "en"
---

# Authentication

Authentication and session management commands.

## Table of Contents

- [privilege](#privilege)
- [status](#status)

## privilege

Grant special privileges to auth request

#### API Information

**Endpoint:** `POST /api/StoredProcedure/PrivilegeAuthenticationRequest`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Elevates an authentication request with special privileges. Used for administrative operations requiring enhanced permissions.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `2FACode` | string | Yes | - |  |  |
| `tFACode` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc auth privilege
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/PrivilegeAuthenticationRequest" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "2FACode": "example-2_f_a_code",
    "tFACode": "example-t_f_a_code"
}'
```

#### Business Rules

- Only available to users with privilege escalation permissions
- May require re-entering password for security verification
- Elevated privileges are temporary and session-specific
- Privilege elevation is logged in audit trail
- Cannot escalate beyond maximum assigned permission level
- Some operations may require approval from another admin
- Elevation automatically expires after timeout period
- Failed elevation attempts are logged and may trigger alerts
- Cannot be used to bypass organization-level restrictions
- Revoked immediately if suspicious activity is detected

#### Success Message

`Successfully privileged authentication request`

## status

Check authentication request status

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetRequestAuthenticationStatus`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Queries the status of a pending authentication request by its hash. Used to verify if an authentication attempt succeeded.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `requestHash` | string | Yes | - | Authentication request hash | a1b2c3d4e5f6... |


#### Examples

```bash
rediacc auth status a1b2c3d4e5f6789
```
Check status of auth request

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc auth status --request-hash <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetRequestAuthenticationStatus" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "requestHash": "a1b2c3d4e5f6..."
}'
```

#### Notes

Request hashes are provided during login attempts. Status includes pending, authorized, or expired.

#### Business Rules

- Requires active authentication token to display status
- Shows current user email, organization, and assigned teams
- Displays token creation time and expiration status
- Lists all permission groups assigned to the user
- Shows whether TFA is enabled for the account
- Indicates if account is activated or pending activation
- Returns error if no valid token is present
- Token details include the token ID (not the full token value)
- Useful for verifying session validity before operations
- Does not refresh or extend token lifetime


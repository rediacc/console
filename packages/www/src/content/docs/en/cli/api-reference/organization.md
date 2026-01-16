---
title: "Organization"
description: "Organization management commands."
category: "CLI API Reference"
language: "en"
---

# Organization

Organization management commands.

## Table of Contents

- [block-user-requests](#block-user-requests)
- [export-data](#export-data)
- [get-vaults](#get-vaults)
- [import-data](#import-data)
- [update-vault](#update-vault)
- [update-vaults](#update-vaults)

## block-user-requests

Block or unblock new user registration requests

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateOrganizationBlockUserRequests`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Controls whether new users can request accounts in your organization. When blocked, only administrators can create new user accounts directly.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `block` | string | Yes | - | Block user requests (true/false) | true |


#### Examples

```bash
rediacc organization block-user-requests true
```
Block new user registrations

```bash
rediacc organization block-user-requests false
```
Allow new user registrations

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization block-user-requests --block <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateOrganizationBlockUserRequests" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "block": "true"
}'
```

#### Notes

Requires organization admin permissions. Existing users are not affected. Useful during maintenance or to control organization growth.

#### Business Rules

- Must be authenticated with organization administrator permissions
- When blocked, self-registration on login page is disabled
- Administrators can still create users manually
- Does not affect existing user accounts or active sessions
- Change takes effect immediately for new requests
- Pending user requests remain in queue when blocking is enabled
- Useful for controlling organization user growth
- Can be toggled on/off as needed without data loss
- Setting is stored at organization level
- Change is logged in audit trail

#### Success Message

`Successfully updated organization user request blocking: {block}`

## export-data

Export all organization data to JSON format

#### API Information

**Endpoint:** `POST /api/StoredProcedure/ExportOrganizationData`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Exports complete organization configuration including teams, users, permissions, regions, bridges, and machines. Vault data is included in encrypted form.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc organization export-data > organization-backup.json
```
Export organization data to file

```bash
rediacc organization export-data | jq '.teams'
```
View exported teams data

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization export-data
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/ExportOrganizationData" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires admin permissions. Export includes all entity configurations and relationships. Vault data remains encrypted.

#### Business Rules

- Must be authenticated with administrator permissions
- Exports all organization entities and configurations
- Vault data is included in encrypted form
- Export can be large for organizations with many resources
- Includes timestamps and version information
- Useful for backup before major changes
- Can be used with import-data for migration
- Operation is logged in audit trail

#### Success Message

`Successfully exported organization data`

## get-vaults

Retrieve all organization vault data

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationVaults`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Fetches all vault configurations stored at the organization level, including encrypted settings and credentials. Useful for backup or inspection.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc organization get-vaults
```
Display all organization vaults

```bash
rediacc organization get-vaults --output json > backup.json
```
Backup vaults to file

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization get-vaults
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationVaults" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires organization admin permissions. Vault data is returned encrypted unless master password is set.

#### Business Rules

- Must be authenticated with organization administrator permissions
- Returns all vault data stored at organization level
- Vault data remains encrypted in response
- Decryption requires master password to be set
- Includes vault version information
- Useful for backup before major changes
- Can export to JSON for archival
- Access is logged in audit trail
- Response may be large for organizations with extensive configs
- Read-only operation with no side effects

## import-data

Import organization data from JSON

#### API Information

**Endpoint:** `POST /api/StoredProcedure/ImportOrganizationData`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Imports organization configuration from a previously exported JSON file. Supports skip mode (default) which skips existing entities, or override mode which updates existing entities.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `vault-file` | string | Yes | - | File containing exported organization data | organization-backup.json |
| `import-mode` | string | No | skip | Import mode: skip or override | override |


#### Examples

```bash
rediacc organization import-data --vault-file backup.json
```
Import with skip mode (default)

```bash
rediacc organization import-data --vault-file backup.json --import-mode override
```
Import with override mode

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization import-data --vault-file <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/ImportOrganizationData" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "vault-file": "organization-backup.json",
    "import-mode": "override"
}'
```

#### Notes

Requires admin permissions. Skip mode preserves existing data. Override mode updates existing entities. Always backup before importing.

#### Business Rules

- Must be authenticated with administrator permissions
- Import data must be from same or compatible version
- Skip mode: existing entities are preserved
- Override mode: existing entities are updated
- Cannot import if organization passphrase has changed
- User accounts must match email addresses
- Import creates audit log entries
- Partial imports may occur if errors encountered
- Vault data must be compatible with current passphrase

#### Success Message

`Successfully imported organization data`

## update-vault

Update organization-wide vault configuration

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateOrganizationVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates the encrypted vault containing organization-wide settings, credentials, and configuration that apply to all teams and users.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `vault` | string | No | - | JSON vault data to store | {"UNIVERSAL_USER_NAME": "system", "API_KEY": "abc123"} |
| `vault-file` | string | No | - | File containing JSON vault data | organization-vault.json |
| `vault-version` | string | No | - | Vault schema version | 2 |


#### Examples

```bash
rediacc organization update-vault --vault-file organization-config.json
```
Update from configuration file

```bash
rediacc organization update-vault --vault '{"UNIVERSAL_USER_NAME":"rediacc"}'
```
Update specific vault field

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization update-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateOrganizationVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "vault": "{"UNIVERSAL_USER_NAME": "system", "API_KEY": "abc123"}",
    "vault-file": "organization-vault.json",
    "vault-version": "2"
}'
```

#### Notes

Requires organization admin permissions. Vault data is encrypted with master password. Changes affect all teams.

#### Business Rules

- Must be authenticated with organization administrator permissions
- Vault data must be valid JSON format
- Maximum vault size is 64KB after encryption
- Vault is encrypted with organization master password
- Previous vault contents are completely replaced
- Common fields: UNIVERSAL_USER_NAME, UNIVERSAL_USER_ID
- Changes propagate to all teams and users
- Vault version helps with schema migrations
- Update is tracked in audit logs
- Cannot be undone - backup before updating

#### Success Message

`Successfully updated organization vault`

## update-vaults

Bulk update multiple organization vaults

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateOrganizationVaults`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates multiple vault configurations at once. Useful for restoring from backup or migrating settings.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `vault` | string | No | - | JSON object containing multiple vaults | {"primary": {...}, "secondary": {...}} |
| `vault-file` | string | No | - | File containing JSON vaults data | all-vaults.json |
| `updates` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc organization update-vaults
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateOrganizationVaults" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "vault": "{"primary": {...}, "secondary": {...}}",
    "vault-file": "all-vaults.json",
    "updates": "example-updates"
}'
```

#### Business Rules

- User must be authenticated with valid credentials
- Only administrators can update organization vaults
- Bulk updates multiple vaults in single operation
- User login attempts blocked during update
- Cannot update if organization has Global Bridge with cloud management
- All vaults must belong to entities within your organization
- Cannot update vault if newer version exists
- TFA vaults cannot be updated through this operation
- Either all updates succeed or none are applied
- Updates are logged with count of vaults modified

#### Success Message

`Successfully updated organization vaults`

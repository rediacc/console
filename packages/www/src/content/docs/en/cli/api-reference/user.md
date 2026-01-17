---
title: "User"
description: "User management commands."
category: "CLI API Reference"
language: "en"
---

# User

User management commands.

## Table of Contents

- [activate](#activate)
- [deactivate](#deactivate)
- [update-email](#update-email)
- [update-password](#update-password)

## activate

Activate a user account

#### API Information

**Endpoint:** `POST /api/StoredProcedure/ActivateUserAccount`

**Authentication:** Required (credential-based with Rediacc-UserEmail and Rediacc-UserHash headers)

#### Details

Activates a newly created user account using an activation code. Users must be activated before they can log in. Default code is AAA111 for testing.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `email` | string | Yes | - | Email address of user to activate | newuser@organization.com |
| `code` | string | No | - | Activation code (default: AAA111) | ABC123 |


#### Examples

```bash
rediacc user activate newuser@organization.com
```
Activate with default code

```bash
rediacc user activate admin@organization.com --code 654321
```
Activate with custom code

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc user activate --email <value>
```

##### Auto-Generated cURL Examples

```bash
# Using credential authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/ActivateUserAccount" \
  -H "Content-Type: application/json" \
  -H "Rediacc-UserEmail: user@organization.com" \
  -H "Rediacc-UserHash: YOUR_PASSWORD_HASH" \
  -d '{
    "email": "newuser@organization.com",
    "code": "123456"
}'
```

#### Notes

No authentication required for activation. Activation codes are set during user creation. Users receive activation instructions via email if configured.

#### Business Rules

- No authentication required for this operation
- Activation code must be exactly 6 characters long
- Code comparison is case-insensitive
- Email must match an existing user account
- User must not already be activated
- Activation code is deleted after successful use
- Account becomes active and can log in
- User can join teams after activation
- Counts toward organization's active user limit
- Activation is logged in audit trail

#### Success Message

`Successfully activated user: {email}`

## deactivate

Deactivate a user account

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateUserToDeactivated`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Deactivates a user account, preventing login while preserving all data and history. The account can be reactivated later if needed.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `email` | string | Yes | - | Email address of user to deactivate | user@organization.com |
| `force` | string | No | - | Skip confirmation prompt | --force |


#### Examples

```bash
rediacc user deactivate employee@organization.com
```
Deactivate with confirmation

```bash
rediacc user deactivate contractor@organization.com --force
```
Deactivate without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc user deactivate --email <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateUserToDeactivated" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "email": "user@organization.com",
    "force": "--force"
}'
```

#### Notes

Deactivated users cannot log in but their data is preserved. Use for employees who leave. Can be reactivated.

#### Business Rules

- Requires user management or admin permissions
- Cannot deactivate your own account
- Cannot deactivate the last admin user
- User's active sessions are terminated
- User immediately loses all access
- All team memberships are preserved
- User's data and history remain intact
- Account can be reactivated with user activate
- Deactivation is logged in audit trail
- Pending tasks assigned to user continue

#### Success Message

`Successfully deactivated user: {email}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to deactivate user '{email}'?`

## update-email

Change a user's email address

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateUserEmail`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates a user's email address across the system. The new email becomes the login identifier. All permissions and data are preserved.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `currentEmail` | string | Yes | - | Current email address | old@organization.com |
| `newEmail` | string | Yes | - | New email address | new@organization.com |


#### Examples

```bash
rediacc user update-email old@organization.com new@organization.com
```
Change user's email

```bash
rediacc user update-email jane.doe@organization.com jane.smith@organization.com
```
Update email after name change

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc user update-email --current-email <value> --new-email <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateUserEmail" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "currentEmail": "old@organization.com",
    "newEmail": "new@organization.com"
}'
```

#### Notes

New email must be unique. User must log in with new email after change. Consider notifying the user.

#### Business Rules

- Requires user management or admin permissions
- New email must not already exist in system
- New email must be valid email format
- Cannot change email to one from different organization domain
- User's active sessions remain valid
- All permissions and team memberships preserved
- Audit history updated with both emails
- User must use new email for future logins
- Change notification sent to both email addresses
- Email change is logged in audit trail

#### Success Message

`Successfully updated user email: {current_email} → {new_email}`

## update-password

Change your password

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateUserPassword`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates the password for the currently authenticated user. The new password is hashed before transmission. You'll need to re-authenticate after changing.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `new-password` | string | Yes | - | New password (will be prompted if not provided) | SecureP@ssw0rd! |


#### Examples

```bash
rediacc user update-password
```
Change password with secure prompt

```bash
rediacc user update-password --new-password 'MyN3wP@ssw0rd!'
```
Change password directly (less secure)

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc user update-password --new-password <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateUserPassword" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "new-password": "SecureP@ssw0rd!"
}'
```

#### Notes

Requires current authentication. Password requirements depend on organization policy. After change, all sessions are invalidated - you must log in again.

#### Business Rules

- User must be authenticated with valid session
- Session-based identity verification (no current password needed)
- New password must be provided as 32-byte hash
- Password is encrypted with organization passphrase
- Change takes effect immediately
- Current session remains active (not logged out)
- Other sessions remain valid until expiration
- Account must be activated to change password
- No password complexity rules enforced by system
- Password change is logged in audit trail

#### Success Message

`Successfully updated user password`


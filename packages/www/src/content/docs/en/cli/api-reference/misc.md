---
title: "Miscellaneous"
description: "Other commands and utilities."
category: "CLI API Reference"
language: "en"
---

# Miscellaneous

Other commands and utilities.

## Table of Contents

- [create-authentication-request](#create-authentication-request)
- [delete-user-request](#delete-user-request)
- [fork-authentication-request](#fork-authentication-request)
- [is-registered](#is-registered)
- [promote-repository-to-grand](#promote-repository-to-grand)
- [update-image-machine-assignment](#update-image-machine-assignment)
- [update-user-vault](#update-user-vault)
- [update-user2-f-a](#update-user2-f-a)

## create-authentication-request

create-authentication-request command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateAuthenticationRequest`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `name` | string | Yes | - |  |  |
| `tFACode` | string | Yes | - |  |  |
| `requestedPermissions` | string | Yes | - |  |  |
| `tokenExpirationHours` | integer | Yes | - |  |  |
| `target` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc create-authentication-request
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateAuthenticationRequest" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "name": "example-name",
    "tFACode": "example-t_f_a_code",
    "requestedPermissions": "example-requested_permissions"
}'
```

## delete-user-request

delete-user-request command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteUserRequest`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

No parameters required.


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc delete-user-request
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteUserRequest" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

## fork-authentication-request

fork-authentication-request command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/ForkAuthenticationRequest`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `childName` | string | Yes | - |  |  |
| `tokenExpirationHours` | integer | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc fork-authentication-request
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/ForkAuthenticationRequest" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "childName": "example-child_name",
    "tokenExpirationHours": 100
}'
```

## is-registered

is-registered command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/IsRegistered`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `userName` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc is-registered
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/IsRegistered" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "userName": "example-user_name"
}'
```

#### Success Message

`Operation completed successfully`

## promote-repository-to-grand

promote-repository-to-grand command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/PromoteRepositoryToGrand`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `repositoryName` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc promote-repository-to-grand
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/PromoteRepositoryToGrand" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "repositoryName": "example-repository_name"
}'
```

## update-image-machine-assignment

update-image-machine-assignment command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateImageMachineAssignment`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `newName` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc update-image-machine-assignment
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateImageMachineAssignment" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "image": "example-image",
    "pool": "example-pool",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## update-user-vault

update-user-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateUserVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `vault` | string | No | - |  |  |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc update-user-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateUserVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "vault": "example-vault",
    "vaultVersion": "example-vault_version"
}'
```

## update-user2-f-a

update-user2-f-a command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateUserTFA`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `enable` | string | Yes | - |  |  |
| `userHash` | string | Yes | - |  |  |
| `currentCode` | string | Yes | - |  |  |
| `generateOnly` | boolean | Yes | - |  |  |
| `verificationCode` | string | Yes | - |  |  |
| `secret` | string | Yes | - |  |  |
| `confirmEnable` | boolean | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc misc update-user2-f-a
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateUserTFA" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "enable": "example-enable",
    "userHash": "example-user_hash",
    "currentCode": "example-current_code"
}'
```


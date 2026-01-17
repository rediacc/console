---
title: "Machine"
description: "Machine-specific operations."
category: "CLI API Reference"
language: "en"
---

# Machine

Machine-specific operations.

## Table of Contents

- [list-machine-assignment-status](#list-machine-assignment-status)
- [update-machine-cluster-assignment](#update-machine-cluster-assignment)
- [update-machine-cluster-removal](#update-machine-cluster-removal)
- [update-machine-vault](#update-machine-vault)

## list-machine-assignment-status

list-machine-assignment-status command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetMachineAssignmentStatus`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `machine` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc machine list-machine-assignment-status
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetMachineAssignmentStatus" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "machine": "example-machine",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## update-machine-cluster-assignment

update-machine-cluster-assignment command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateMachineClusterAssignment`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `cluster` | string | Yes | - |  |  |
| `machine` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc machine update-machine-cluster-assignment
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateMachineClusterAssignment" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "cluster": "example-cluster",
    "machine": "example-machine",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## update-machine-cluster-removal

update-machine-cluster-removal command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateMachineClusterRemoval`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `machine` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc machine update-machine-cluster-removal
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateMachineClusterRemoval" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "machine": "example-machine",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## update-machine-vault

update-machine-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateMachineVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `machine` | string | Yes | - |  |  |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc machine update-machine-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateMachineVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "machine": "example-machine",
    "vaultVersion": "example-vault_version"
}'
```

#### Success Message

`Operation completed successfully`


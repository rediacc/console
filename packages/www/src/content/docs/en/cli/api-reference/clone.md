---
title: "Clone"
description: "Clone resources and configurations."
category: "CLI API Reference"
language: "en"
---

# Clone

Clone resources and configurations.

## Table of Contents

- [list-available-machines-for-clone](#list-available-machines-for-clone)
- [list-clone-machine-assignment-validation](#list-clone-machine-assignment-validation)
- [list-clone-machines](#list-clone-machines)
- [update-clone-machine-assignments](#update-clone-machine-assignments)
- [update-clone-machine-removals](#update-clone-machine-removals)

## list-available-machines-for-clone

list-available-machines-for-clone command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetAvailableMachinesForClone`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc clone list-available-machines-for-clone
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetAvailableMachinesForClone" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## list-clone-machine-assignment-validation

list-clone-machine-assignment-validation command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetCloneMachineAssignmentValidation`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `machineNames` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc clone list-clone-machine-assignment-validation
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetCloneMachineAssignmentValidation" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "machineNames": "example-machine_names"
}'
```

#### Success Message

`Operation completed successfully`

## list-clone-machines

list-clone-machines command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetCloneMachines`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `clone` | string | Yes | - |  |  |
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc clone list-clone-machines
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetCloneMachines" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "clone": "example-clone",
    "snapshot": "example-snapshot",
    "image": "example-image"
}'
```

#### Success Message

`Operation completed successfully`

## update-clone-machine-assignments

update-clone-machine-assignments command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateCloneMachineAssignments`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `clone` | string | Yes | - |  |  |
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `machineNames` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc clone update-clone-machine-assignments
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateCloneMachineAssignments" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "clone": "example-clone",
    "snapshot": "example-snapshot",
    "image": "example-image"
}'
```

#### Success Message

`Operation completed successfully`

## update-clone-machine-removals

update-clone-machine-removals command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateCloneMachineRemovals`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `clone` | string | Yes | - |  |  |
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `machineNames` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc clone update-clone-machine-removals
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateCloneMachineRemovals" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "clone": "example-clone",
    "snapshot": "example-snapshot",
    "image": "example-image"
}'
```

#### Success Message

`Operation completed successfully`


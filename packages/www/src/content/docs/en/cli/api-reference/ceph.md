---
title: "Ceph"
description: "Manage Ceph clusters and pools."
category: "CLI API Reference"
language: "en"
---

# Ceph

Manage Ceph clusters and pools.

## Table of Contents

- [create-cluster](#create-cluster)
- [create-distributed-storage-pool](#create-distributed-storage-pool)
- [create-distributed-storage-rbd-clone](#create-distributed-storage-rbd-clone)
- [create-distributed-storage-rbd-image](#create-distributed-storage-rbd-image)
- [create-distributed-storage-rbd-snapshot](#create-distributed-storage-rbd-snapshot)
- [delete-cluster](#delete-cluster)
- [delete-distributed-storage-pool](#delete-distributed-storage-pool)
- [delete-distributed-storage-rbd-clone](#delete-distributed-storage-rbd-clone)
- [delete-distributed-storage-rbd-image](#delete-distributed-storage-rbd-image)
- [delete-distributed-storage-rbd-snapshot](#delete-distributed-storage-rbd-snapshot)
- [list-distributed-storage-cluster-machines](#list-distributed-storage-cluster-machines)
- [list-distributed-storage-clusters](#list-distributed-storage-clusters)
- [list-distributed-storage-pools](#list-distributed-storage-pools)
- [list-distributed-storage-rbd-clones](#list-distributed-storage-rbd-clones)
- [list-distributed-storage-rbd-images](#list-distributed-storage-rbd-images)
- [list-distributed-storage-rbd-snapshots](#list-distributed-storage-rbd-snapshots)
- [update-distributed-storage-pool-vault](#update-distributed-storage-pool-vault)
- [update-machine-distributed-storage](#update-machine-distributed-storage)
- [update-vault](#update-vault)

## create-cluster

Create a Ceph cluster

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateDistributedStorageCluster`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Creates a cluster configuration for Ceph across multiple machines. Enables redundant storage with automatic replication and failover.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `vault` | string | No | - | JSON configuration for the cluster | {"replication_factor": 3, "storage_class": "ssd"} |
| `vault-file` | string | No | - | File containing JSON vault data | cluster-config.json |
| `cluster` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph create-cluster
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateDistributedStorageCluster" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "vault": "{"replication_factor": 3, "storage_class": "ssd"}",
    "vault-file": "cluster-config.json",
    "cluster": "example-cluster"
}'
```

#### Business Rules

- User must be authenticated with valid credentials
- User must be a member of the specified team
- Cluster name must be unique within the team
- Team must exist in your organization
- Cluster configuration requires specific parameters in vault data
- Pool PG number must be between 1 and 1024
- New clusters start with PENDING status
- No subscription plan restrictions for creating clusters
- Vault data is encrypted using organization master password
- Cluster creation is logged in audit trail

#### Success Message

`Successfully created Ceph cluster: {name} for team {team}`

## create-distributed-storage-pool

create-distributed-storage-pool command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateDistributedStoragePool`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `cluster` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph create-distributed-storage-pool
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateDistributedStoragePool" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "cluster": "example-cluster",
    "team": "example-team",
    "pool": "example-pool"
}'
```

#### Success Message

`Operation completed successfully`

## create-distributed-storage-rbd-clone

create-distributed-storage-rbd-clone command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateDistributedStorageRbdClone`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `clone` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph create-distributed-storage-rbd-clone
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateDistributedStorageRbdClone" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "snapshot": "example-snapshot",
    "image": "example-image",
    "pool": "example-pool"
}'
```

#### Success Message

`Operation completed successfully`

## create-distributed-storage-rbd-image

create-distributed-storage-rbd-image command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateDistributedStorageRbdImage`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `machine` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph create-distributed-storage-rbd-image
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateDistributedStorageRbdImage" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "pool": "example-pool",
    "team": "example-team",
    "image": "example-image"
}'
```

#### Success Message

`Operation completed successfully`

## create-distributed-storage-rbd-snapshot

create-distributed-storage-rbd-snapshot command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateDistributedStorageRbdSnapshot`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `snapshot` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph create-distributed-storage-rbd-snapshot
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateDistributedStorageRbdSnapshot" \
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

## delete-cluster

Delete a Ceph cluster

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteDistributedStorageCluster`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Permanently removes a Ceph cluster configuration. Does not delete data on machines, only the cluster configuration.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `force` | string | No | - | Skip confirmation prompt | --force |
| `cluster` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph delete-cluster
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteDistributedStorageCluster" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "force": "--force",
    "cluster": "example-cluster"
}'
```

#### Business Rules

- User must be authenticated with valid credentials
- User must be either an administrator or team member
- Cluster must exist in the specified team
- Cluster must have zero nodes before deletion
- Cannot delete cluster with machines still attached
- Deletion removes cluster configuration and credentials
- Associated vault data is automatically cleaned up
- Machine Ceph flags remain unchanged
- Operation is permanent and cannot be undone
- Deletion is logged in audit trail for compliance

#### Success Message

`Successfully deleted Ceph cluster: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete Ceph cluster '{name}' from team '{team}'?`

## delete-distributed-storage-pool

delete-distributed-storage-pool command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteDistributedStoragePool`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph delete-distributed-storage-pool
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteDistributedStoragePool" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "pool": "example-pool",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## delete-distributed-storage-rbd-clone

delete-distributed-storage-rbd-clone command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteDistributedStorageRbdClone`

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
rediacc ceph delete-distributed-storage-rbd-clone
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteDistributedStorageRbdClone" \
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

## delete-distributed-storage-rbd-image

delete-distributed-storage-rbd-image command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteDistributedStorageRbdImage`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph delete-distributed-storage-rbd-image
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteDistributedStorageRbdImage" \
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

## delete-distributed-storage-rbd-snapshot

delete-distributed-storage-rbd-snapshot command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteDistributedStorageRbdSnapshot`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph delete-distributed-storage-rbd-snapshot
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteDistributedStorageRbdSnapshot" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "snapshot": "example-snapshot",
    "image": "example-image",
    "pool": "example-pool"
}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-cluster-machines

list-distributed-storage-cluster-machines command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStorageClusterMachines`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `cluster` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-cluster-machines
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStorageClusterMachines" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "cluster": "example-cluster"
}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-clusters

list-distributed-storage-clusters command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStorageClusters`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

No parameters required.


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-clusters
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStorageClusters" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-pools

list-distributed-storage-pools command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStoragePools`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `cluster` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-pools
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStoragePools" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "cluster": "example-cluster"
}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-rbd-clones

list-distributed-storage-rbd-clones command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStorageRbdClones`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `snapshot` | string | Yes | - |  |  |
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-rbd-clones
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStorageRbdClones" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "snapshot": "example-snapshot",
    "image": "example-image",
    "pool": "example-pool"
}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-rbd-images

list-distributed-storage-rbd-images command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStorageRbdImages`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-rbd-images
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStorageRbdImages" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "pool": "example-pool",
    "team": "example-team"
}'
```

#### Success Message

`Operation completed successfully`

## list-distributed-storage-rbd-snapshots

list-distributed-storage-rbd-snapshots command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetDistributedStorageRbdSnapshots`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `image` | string | Yes | - |  |  |
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph list-distributed-storage-rbd-snapshots
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetDistributedStorageRbdSnapshots" \
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

## update-distributed-storage-pool-vault

update-distributed-storage-pool-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateDistributedStoragePoolVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `pool` | string | Yes | - |  |  |
| `team` | string | Yes | - |  |  |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph update-distributed-storage-pool-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateDistributedStoragePoolVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "pool": "example-pool",
    "team": "example-team",
    "vaultVersion": "example-vault_version"
}'
```

#### Success Message

`Operation completed successfully`

## update-machine-distributed-storage

update-machine-distributed-storage command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateMachineDistributedStorage`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `machine` | string | Yes | - |  |  |
| `cluster` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph update-machine-distributed-storage
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateMachineDistributedStorage" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "machine": "example-machine",
    "cluster": "example-cluster"
}'
```

#### Success Message

`Operation completed successfully`

## update-vault

Update cluster configuration vault

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateDistributedStorageClusterVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates the encrypted configuration for a Ceph cluster including replication settings, storage policies, and performance parameters.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `cluster` | string | Yes | - | Cluster name | main-cluster |
| `vault` | string | No | - | JSON configuration data | {"replication_factor": 3, "consistency_level": "strong"} |
| `vault-file` | string | No | - | File containing JSON vault data | cluster-config.json |
| `vault-version` | string | No | - | Vault schema version (default: 1) | 2 |
| `vaultVersion` | string | No | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc ceph update-vault --cluster <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateDistributedStorageClusterVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "cluster": "main-cluster",
    "vault": "{"replication_factor": 3, "consistency_level": "strong"}",
    "vault-file": "cluster-config.json"
}'
```

#### Business Rules

- User must be authenticated with valid credentials
- User must be a member of the team owning the cluster
- Cluster must exist before updating vault
- Vault data must be provided as text (cannot be empty)
- Maximum vault chunk size is 3,072 characters
- Large vaults automatically split into multiple chunks
- Vault data is encrypted with organization master password
- Each update increments vault version number
- Previous vault data is completely replaced
- Update is logged in audit trail

#### Success Message

`Successfully updated Ceph cluster vault: {cluster}`


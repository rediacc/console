---
title: "Remove"
description: "Remove/delete resources from the system."
category: "CLI API Reference"
language: "en"
---

# Remove

Remove/delete resources from the system.

## Table of Contents

- [bridge](#bridge)
- [machine](#machine)
- [queue-item](#queue-item)
- [region](#region)
- [repository](#repository)
- [storage](#storage)
- [team](#team)

## bridge

Delete a bridge from a region

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteBridge`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Removes a bridge configuration. Ensure no machines are assigned to this bridge and no queue items are pending. Running bridge processes should be stopped first.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `region` | string | Yes | - | Region containing the bridge | us-east |
| `bridge` | string | Yes | - |  |  |
| `name` | string | Yes | - |  |  |


#### Examples

```bash
rediacc rm bridge us-east old-bridge
```
Delete bridge with confirmation

```bash
rediacc rm bridge europe decommissioned-bridge --force
```
Force delete without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm bridge --region <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteBridge" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "region": "us-east",
    "bridge": "example-bridge",
    "name": "example-name"
}'
```

#### Notes

Cannot delete if machines are assigned. Reassign machines first using 'update machine-bridge'. Stop bridge process before deletion.

#### Business Rules

- User must be authenticated to perform this operation
- User must belong to the same organization as the bridge
- Bridge name must exist in the specified region
- Bridge must not be assigned to any machines
- Bridge must not have active queue items in PENDING or ASSIGNED states
- Cannot delete bridges currently processing queue items
- Only bridges with FAILED, COMPLETED, or CANCELLED queue items can be deleted
- Deletion will also remove all bridge vault data
- Operation is permanent and cannot be undone
- Bridge deletion is tracked in audit logs for compliance

#### Success Message

`Successfully deleted bridge: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete bridge '{name}' from region '{region}'?`

## machine

Delete a machine from a team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteMachine`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Permanently removes a machine configuration. Does not affect the actual server, only removes it from the Rediacc system. Pending queue items will fail.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that owns the machine | dev-team |
| `machine` | string | Yes | - |  |  |
| `name` | string | Yes | - |  |  |


#### Examples

```bash
rediacc rm machine dev-team old-server
```
Delete machine with confirmation

```bash
rediacc rm machine staging temp-machine --force
```
Delete without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm machine --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteMachine" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "dev-team",
    "machine": "example-machine",
    "name": "example-name"
}'
```

#### Notes

Check for pending queue items before deletion. The actual server is not affected. Consider updating vault to mark as decommissioned instead of deleting.

#### Business Rules

- You must be logged in with valid user account
- Must belong to the same organization that owns the machine
- Must be an active member of the team that owns the machine
- Machine must exist in the specified team
- Cannot delete if machine has pending queue items
- Deletion removes machine configuration and vault data
- Action cannot be undone
- Every deletion is logged in audit trail
- No special admin privileges required beyond team membership
- Actual server is not affected, only Rediacc configuration removed

#### Success Message

`Successfully deleted machine: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete machine '{name}' from team '{team}'?`

## queue-item

Delete a queue item from the system

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteQueueItem`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Removes a pending queue item to prevent execution. Only PENDING or CANCELLED items can be deleted. Running or completed items cannot be removed for audit purposes.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskid` | string | Yes | - |  |  |
| `taskId` | string | Yes | - |  |  |


#### Examples

```bash
rediacc rm queue-item 550e8400-e29b-41d4-a716-446655440000
```
Delete queue item with confirmation

```bash
rediacc rm queue-item 550e8400 --force
```
Force delete using partial task ID

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm queue-item
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteQueueItem" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskid": "example-taskid",
    "taskId": "example-task_id"
}'
```

#### Notes

Cannot delete running or completed items. Use 'queue cancel' for running tasks. Deletion is immediate and permanent.

#### Business Rules

- User must be authenticated to perform this operation
- User must have access to the team that created the queue item
- Queue item must exist with the specified task ID
- Can only delete items in PENDING or CANCELLED states
- Cannot delete items in ASSIGNED or PROCESSING states
- Cannot delete COMPLETED or FAILED items (kept for audit)
- Deletion prevents the task from being executed
- Associated queue vault data will be removed
- Operation is permanent and cannot be undone
- Queue item deletion is tracked in audit logs

#### Success Message

`Successfully deleted queue item: {task_id}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete queue item '{task_id}'?`

## region

Delete a region and all its bridges

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteRegion`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Removes a region and cascades deletion to all bridges within it. Ensure no machines are assigned to bridges in this region. This is a destructive operation.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `name` | string | Yes | - | Region name to delete | old-region |
| `force` | string | No | - | Skip confirmation prompt | --force |


#### Examples

```bash
rediacc rm region test-region
```
Delete region with confirmation

```bash
rediacc rm region deprecated-region --force
```
Force delete without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm region --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteRegion" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "name": "old-region",
    "force": "--force"
}'
```

#### Notes

WARNING: Cascades to all bridges in the region. Cannot delete if bridges have assigned machines. Clear all dependencies first.

#### Business Rules

- User must be authenticated to perform this operation
- User must belong to the same organization as the region
- Region name must exist in the system
- Region must not contain any bridges
- Region must not be referenced by any machines
- Cannot delete regions with active infrastructure
- All bridges must be deleted or moved before region deletion
- Region vault data will be permanently removed
- Operation is permanent and cannot be undone
- Region deletion is tracked in audit logs for compliance

#### Success Message

`Successfully deleted region: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete region '{name}'? This will remove all bridges in the region.`

## repository

Delete a repository from the system

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteRepository`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Permanently removes a repository and all its data. The repository's Docker containers will be stopped, volumes unmounted, and all associated data deleted. This action cannot be undone.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `repository` | string | Yes | - |  |  |


#### Examples

```bash
rediacc rm repository old-app --team dev
```
Delete repository with confirmation

```bash
rediacc rm repository temp-test --team qa --force
```
Force delete without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm repository
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteRepository" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "repository": "example-repository"
}'
```

#### Notes

Ensure all data is backed up before deletion. Running containers will be stopped. Consider using repo_down first.

#### Business Rules

- User must be authenticated to perform this operation
- User must be a member of the specified team
- Repository must exist within the team
- Repository must be offline (not currently mounted)
- Repository must not have active backup or restore operations
- Cannot delete repositories referenced in active schedules
- All associated repository vault data will be deleted
- Repository files on disk will be permanently removed
- Operation is permanent and cannot be undone
- Repository deletion is tracked in audit logs

#### Success Message

`Successfully deleted repository: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete repository '{name}' from team '{team}'?`

## storage

Delete a storage configuration from the system

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteStorage`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Removes a storage configuration including credentials and settings. Does not delete actual data in the external storage system (S3, Azure, etc.), only the Rediacc configuration.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - |  |  |
| `storage` | string | Yes | - |  |  |


#### Examples

```bash
rediacc rm storage old-backup --team ops
```
Delete storage config with confirmation

```bash
rediacc rm storage temp-s3 --team dev --force
```
Force delete without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm storage
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteStorage" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "example-team",
    "storage": "example-storage"
}'
```

#### Notes

Only removes Rediacc configuration. Data in external storage systems remains untouched. Update any schedules using this storage.

#### Business Rules

- User must be authenticated to perform this operation
- User must be a member of the specified team
- Storage configuration must exist within the team
- Storage must not be referenced in active backup schedules
- Storage must not have ongoing transfer operations
- Cannot delete storage with active repository backups
- All associated storage vault data will be deleted
- Cloud storage data is not deleted, only the configuration
- Operation is permanent and cannot be undone
- Storage deletion is tracked in audit logs

#### Success Message

`Successfully deleted storage: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete storage '{name}' from team '{team}'?`

## team

Delete a team and all its resources

#### API Information

**Endpoint:** `POST /api/StoredProcedure/DeleteTeam`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Permanently removes a team and all associated resources including machines, repositories, storages, and schedules. This action cannot be undone.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `name` | string | Yes | - | Name of the team to delete | old-team |
| `force` | string | No | - | Skip confirmation prompt | --force |


#### Examples

```bash
rediacc rm team old-team
```
Delete team with confirmation

```bash
rediacc rm team old-team --force
```
Delete team without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc rm team --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/DeleteTeam" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "name": "old-team",
    "force": "--force"
}'
```

#### Notes

WARNING: This cascades to all team resources. Ensure data is backed up. Requires team ownership or admin permissions.

#### Business Rules

- You must be logged in with valid credentials
- You must be a member of the team to delete it
- Team must belong to your organization
- 'Private Team' cannot be deleted (system requirement)
- Cannot delete the last team in an organization
- Team must have no machines before deletion
- Team must have no repositories before deletion
- Team must have no schedules before deletion
- Team must have no storage configurations before deletion
- Deletion removes all memberships, vault data, and audit logs are created

#### Success Message

`Successfully deleted team: {name}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to delete team '{name}'? This will remove all resources in the team.`


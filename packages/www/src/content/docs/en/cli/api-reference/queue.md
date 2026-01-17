---
title: "Queue"
description: "Queue management and operations."
category: "CLI API Reference"
language: "en"
---

# Queue

Queue management and operations.

## Table of Contents

- [cancel](#cancel)
- [complete](#complete)
- [get-next](#get-next)
- [list](#list)
- [retry](#retry)
- [trace](#trace)
- [update-response](#update-response)

## cancel

Cancel a pending or processing queue item

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CancelQueueItem`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Marks a queue item as cancelled, preventing further processing. If already processing, the bridge will attempt to stop execution gracefully. Completed items cannot be cancelled.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskId` | string | Yes | - | Task ID (GUID) to cancel | 550e8400-e29b-41d4-a716-446655440000 |
| `force` | string | No | - | Skip confirmation prompt | --force |


#### Examples

```bash
rediacc queue cancel 550e8400-e29b-41d4-a716-446655440000
```
Cancel with confirmation

```bash
rediacc queue cancel 550e8400-e29b-41d4-a716-446655440000 --force
```
Cancel without confirmation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue cancel --task-id <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CancelQueueItem" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskId": "550e8400-e29b-41d4-a716-446655440000",
    "force": "--force"
}'
```

#### Notes

Cancellation is immediate for PENDING items. PROCESSING items may continue briefly while the bridge stops gracefully. Check status after cancelling.

#### Business Rules

- Requires team member or higher permissions
- Can only cancel items from your team's queue
- Cannot cancel COMPLETED or FAILED items
- PENDING items are cancelled immediately
- ASSIGNED items are unassigned from bridge
- PROCESSING items receive cancellation signal
- Bridge may complete current operation before stopping
- Cancelled items are marked with CANCELLED status
- Cancellation is logged in queue item history
- Associated resources may need manual cleanup

#### Success Message

`Successfully cancelled queue item: {task_id}`

#### Confirmation Required

This operation requires confirmation: `Are you sure you want to cancel queue item '{task_id}'?`

## complete

Mark a queue item as completed

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateQueueItemToCompleted`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Marks a processing queue item as successfully completed with optional result data. Used by bridges to finalize task execution.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskId` | string | Yes | - | Task ID (GUID) to complete | 550e8400-e29b-41d4-a716-446655440000 |
| `vault` | string | No | - | JSON result data to store | {"status": "success", "output": "Task completed"} |
| `finalStatus` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue complete --task-id <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateQueueItemToCompleted" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskId": "550e8400-e29b-41d4-a716-446655440000",
    "vault": "{"status": "success", "output": "Task completed"}",
    "finalStatus": "example-final_status"
}'
```

#### Business Rules

- Requires authentication with appropriate permissions
- Task must exist and belong to accessible team
- Task must be in PROCESSING or ASSIGNED state
- Cannot complete already COMPLETED or FAILED tasks
- Final vault data is encrypted before storage
- Completion time is recorded automatically
- Status changes to COMPLETED immediately
- Triggers any dependent operations
- Completion is logged in task history
- Bridge that processed task is recorded

#### Success Message

`Successfully completed queue item: {task_id}`

## get-next

Get next queue items for processing

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetQueueItemsNext`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Retrieves and assigns the next available queue items to the caller. Used by bridges to fetch work. Items are automatically marked as ASSIGNED.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `count` | string | No | - | Number of items to retrieve (default: 3) | 5 |


#### Examples

```bash
rediacc queue get-next
```
Get next 3 items (default)

```bash
rediacc queue get-next --count 10
```
Get up to 10 items

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue get-next
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetQueueItemsNext" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "count": "5"
}'
```

#### Notes

Designed for bridges. Items are assigned to caller's identity. Returns empty array if no items available.

#### Business Rules

- Requires bridge or administrative authentication
- Returns only PENDING items from accessible teams
- Items are immediately marked as ASSIGNED
- Assignment prevents other bridges from taking items
- Respects queue priority ordering (1 is highest)
- Maximum count is typically limited to 10
- Returns fewer items if not enough available
- Caller identity is recorded on assigned items
- Items expire if not completed within timeout
- Load balances across available bridges

## list

List queue items with various filters

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamQueueItems`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

View queue items across teams with powerful filtering options. Monitor task status, find stuck items, analyze performance, and track execution history.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | No | - | Filter by team name(s), comma-separated | prod,staging |
| `machine` | string | No | - | Filter by specific machine | web-server-01 |
| `bridge` | string | No | - | Filter by specific bridge | us-east-bridge |
| `status` | string | No | - | Filter by status (PENDING,ASSIGNED,PROCESSING,COMPLETED,FAILED,CANCELLED) | PENDING,PROCESSING |
| `priority` | string | No | - | Filter by exact priority (1-5) | 1 |
| `createdByUserEmail` | string | Yes | - |  |  |
| `minPriority` | string | Yes | - |  |  |
| `maxPriority` | string | Yes | - |  |  |
| `dateFrom` | string | Yes | - |  |  |
| `dateTo` | string | Yes | - |  |  |
| `taskId` | string | Yes | - |  |  |
| `includeCompleted` | string | Yes | - |  |  |
| `includeCancelled` | string | Yes | - |  |  |
| `onlyStale` | string | Yes | - |  |  |
| `staleThresholdMinutes` | string | Yes | - |  |  |
| `maxRecords` | integer | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue list
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamQueueItems" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "prod,staging",
    "machine": "web-server-01",
    "bridge": "us-east-bridge"
}'
```

#### Business Rules

- Requires team member or higher permissions
- Shows queue items for specified team only
- Default limit is 100 items, use --limit to change
- Items are sorted by creation time (newest first)
- Can filter by status: PENDING, ASSIGNED, PROCESSING, COMPLETED, FAILED
- Can filter by specific machine or bridge
- Completed items are retained for 30 days
- Shows task ID, status, priority, and timestamps
- Response data is decrypted if master password is set
- High-priority items (1-2) are highlighted in output

## retry

Retry a failed queue item

#### API Information

**Endpoint:** `POST /api/StoredProcedure/RetryFailedQueueItem`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Creates a new queue item with the same configuration as a failed item. The original item's status remains FAILED. Useful for transient failures or after fixing issues.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskId` | string | Yes | - | Task ID (GUID) of failed item to retry | 550e8400-e29b-41d4-a716-446655440000 |


#### Examples

```bash
rediacc queue retry 550e8400-e29b-41d4-a716-446655440000
```
Retry a failed task

```bash
rediacc queue list --status FAILED --output json | jq -r '.[].taskId' | xargs -I {} rediacc queue retry {}
```
Retry all failed tasks

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue retry --task-id <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/RetryFailedQueueItem" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskId": "550e8400-e29b-41d4-a716-446655440000"
}'
```

#### Notes

Only FAILED items can be retried. Creates a new item with same priority and configuration. Check failure reason before retrying to avoid repeated failures.

#### Business Rules

- Requires team member or higher permissions
- Can only retry FAILED or CANCELLED items
- Original item must belong to your team
- Creates new queue item with fresh task ID
- Copies all parameters from original item
- Resets retry count to zero
- New item gets default priority unless specified
- Original failed item is not modified
- Links to original item for audit trail
- May fail again if underlying issue not resolved

#### Success Message

`Successfully retried queue item: {task_id}`

## trace

Get execution trace for a queue item

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetQueueItemTrace`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Retrieves detailed execution history and logs for a specific queue item, including all state changes, assignments, and bridge interactions.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskId` | string | Yes | - | Task ID (GUID) to trace | 550e8400-e29b-41d4-a716-446655440000 |


#### Examples

```bash
rediacc queue trace 550e8400-e29b-41d4-a716-446655440000
```
Get full trace for task

```bash
rediacc queue trace 550e8400 --output json | jq '.logs'
```
Extract logs from trace

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue trace --task-id <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetQueueItemTrace" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskId": "550e8400-e29b-41d4-a716-446655440000"
}'
```

#### Notes

Shows complete task lifecycle. Useful for debugging failed tasks or monitoring execution progress.

#### Business Rules

- Requires team member or higher permissions
- Task must belong to accessible team
- Shows all state transitions with timestamps
- Includes bridge assignment history
- Contains any error messages or stack traces
- Shows intermediate responses from updates
- Displays retry attempts if any
- Includes cancellation information if cancelled
- Vault data shown if master password is set
- Access is logged in audit trail

## update-response

Update progress/status of a processing queue item

#### API Information

**Endpoint:** `POST /api/StoredProcedure/UpdateQueueItemResponse`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Updates a queue item with intermediate results or progress information while it's being processed. Used by bridges to report progress.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `taskId` | string | Yes | - | Task ID (GUID) to update | 550e8400-e29b-41d4-a716-446655440000 |
| `vault` | string | No | - | JSON progress data | {"progress": 50, "status": "Processing file 2 of 4"} |


#### Examples

```bash
rediacc queue update-response 550e8400 --vault '{"progress":25}'
```
Update task progress to 25%

```bash
rediacc queue update-response 550e8400 --vault-file status.json
```
Update from status file

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc queue update-response --task-id <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/UpdateQueueItemResponse" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "taskId": "550e8400-e29b-41d4-a716-446655440000",
    "vault": "{"progress": 50, "status": "Processing file 2 of 4"}"
}'
```

#### Notes

Used by bridges during task execution. Can be called multiple times. Does not change task state.

#### Business Rules

- Requires bridge or administrative authentication
- Task must be assigned to caller (for bridges)
- Task must be in ASSIGNED or PROCESSING state
- Response vault is encrypted before storage
- Updates are appended to task history
- Does not change overall task status
- Useful for long-running operations
- Each update includes timestamp
- Previous responses are preserved
- Can be used to stream output data

#### Success Message

`Successfully updated queue item response: {task_id}`


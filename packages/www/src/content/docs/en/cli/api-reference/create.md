---
title: "Create"
description: "Create new resources in the system."
category: "CLI API Reference"
language: "en"
---

# Create

Create new resources in the system.

## Table of Contents

- [bridge](#bridge)
- [organization](#organization)
- [machine](#machine)
- [queue-item](#queue-item)
- [region](#region)
- [repository](#repository)
- [storage](#storage)
- [team](#team)
- [user](#user)

## bridge

Create a new bridge for task processing

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateBridge`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Bridges are autonomous queue processors that poll for tasks and execute them on machines via SSH. They run in bridge mode and can process multiple queue items in parallel. Each bridge must belong to a region.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `region` | string | Yes | - | Region where the bridge will be created | us-east |
| `vault` | string | No | - | JSON configuration for the bridge (batch size, timeout settings) | {"batch_size": 5, "poll_interval": 30} |
| `bridge` | string | Yes | - |  |  |
| `name` | string | Yes | - |  |  |


#### Examples

```bash
rediacc create bridge us-east bridge-01
```
Create a basic bridge

```bash
rediacc create bridge us-east high-priority-bridge --vault '{"batch_size":10}'
```
Create bridge with custom batch size

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create bridge --region <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateBridge" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "region": "us-east",
    "vault": "{"batch_size": 5, "poll_interval": 30}",
    "bridge": "example-bridge"
}'
```

#### Notes

After creation, start the bridge with './bridge --bridge-mode token=<token> api_url=<url> master_password=<pwd>'. Use 'rediacc login --target bridge-name' to get a bridge-specific token.

#### Business Rules

- Bridge name must be unique within the region
- Region must exist and belong to the user's organization
- Bridge vault data cannot be null or empty
- Organization must not have exceeded bridge resource limits
- User must have appropriate permissions
- Vault data must be valid JSON format
- Resource limits depend on subscription plan
- Bridge names are case-sensitive
- A bridge user account is automatically created for authentication
- Bridge credentials are stored securely in the vault

#### Success Message

`Successfully created bridge: {name} in region {region}`

## organization

Create a new organization account with admin user

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateNewOrganization`

**Authentication:** Required (credential-based with Rediacc-UserEmail and Rediacc-UserHash headers)

#### Details

Creates a new Rediacc organization along with its admin user account. The email and password parameters are used to create the admin user who will own the organization. This is typically the first step in setting up a new Rediacc deployment.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `activationCode` | string | No | - |  |  |
| `vaultDefaults` | string | No | - |  |  |
| `organizationName` | string | Yes | - |  |  |
| `subscriptionPlan` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create organization
```

##### Auto-Generated cURL Examples

```bash
# Using credential authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateNewOrganization" \
  -H "Content-Type: application/json" \
  -H "Rediacc-UserEmail: user@organization.com" \
  -H "Rediacc-UserHash: YOUR_PASSWORD_HASH" \
  -d '{
    "activationCode": "example-activation_code",
    "vaultDefaults": "example-vault_defaults",
    "organizationName": "example-organization_name"
}'
```

#### Business Rules

- Password hash must be exactly 32 bytes when hashed
- Activation code must be exactly 6 characters
- User email must not already exist in the system
- Email format must be valid (contains @ and .)
- Subscription plan must exist and be active (COMMUNITY, PRO, BUSINESS, or ENTERPRISE)
- Organization name is required and cannot be empty
- Default organization vault configuration will be applied automatically
- COMMUNITY plan gets 10 years subscription, other plans get 30-day trial
- Organization creation is atomic - all or nothing operation
- Email validation checks for proper format with @ symbol and domain

#### Success Message

`Successfully created organization: {name}`

## machine

Create a new machine in a team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateMachine`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Machines are remote servers that execute tasks via SSH. They must be associated with a team and connected through a bridge. Machine names must be unique across the entire organization.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that will own this machine | production-team |
| `bridge` | string | Yes | - | Bridge to connect through (must exist in a region) | us-east-bridge-01 |
| `vault` | string | No | - | JSON with machine config (ip, user, ssh_port, datastore) | {"ip": "10.0.0.5", "user": "rediacc", "datastore": "/mnt/rediacc"} |
| `machine` | string | Yes | - |  |  |
| `name` | string | Yes | - |  |  |


#### Examples

```bash
rediacc create machine production-team us-east-bridge web-01
```
Create a basic machine

```bash
rediacc create machine prod us-bridge db-01 --vault '{"ip":"10.0.0.10"}'
```
Create machine with IP configuration

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create machine --team <value> --bridge <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateMachine" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "production-team",
    "bridge": "us-east-bridge-01",
    "vault": "{"ip": "10.0.0.5", "user": "rediacc", "datastore": "/mnt/rediacc"}"
}'
```

#### Notes

You must be a member of the team. The bridge must exist and be accessible. Machine creation counts against subscription limits.

#### Business Rules

- Machine name must be unique across the entire organization (not just within team)
- User must be a member of the specified team
- Bridge must exist in a region within the organization
- Organization must not have exceeded machine resource limits
- Machine vault data cannot be null or empty
- Vault data must be valid JSON format
- Team must exist within the user's organization
- Resource limits depend on subscription plan
- Machine names are case-sensitive
- Bridge must be accessible and properly configured

#### Success Message

`Successfully created machine: {name} for team {team}`

## queue-item

Create a queue item for task execution

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateQueueItem`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Queue items represent tasks to be executed on machines by bridges. The bridge polls for items, executes them on the target machine via SSH, and reports results back.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that owns the machine | production-team |
| `machine` | string | Yes | - | Target machine for execution | web-server-01 |
| `bridge` | string | Yes | - | Bridge to process this queue item | us-east-bridge-01 |
| `vault` | string | No | - | JSON with task configuration and parameters | {"function": "deploy", "version": "1.2.3"} |
| `priority` | string | No | 3 | Priority level (1=highest, 5=lowest) | 1 |


#### Examples

```bash
rediacc create queue-item prod web-01 us-bridge --priority 3
```
Create standard priority queue item

```bash
rediacc create queue-item prod db-01 bridge-01 --priority 1 --vault-file task.json
```
Create high priority item with task config

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create queue-item --team <value> --machine <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateQueueItem" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "production-team",
    "machine": "web-server-01",
    "bridge": "us-east-bridge-01"
}'
```

#### Notes

Priority 1-2 requires Business/Enterprise subscription. Community/Pro limited to priority 3-5. You must be a team member.

#### Business Rules

- Priority must be between 1 and 5 (1=highest, 5=lowest)
- Priority levels 1-2 require Business or Enterprise subscription
- Community/Pro plans automatically reset priority to 4 (default)
- User must be a member of the team that owns the machine
- Machine must exist and belong to the specified team
- Bridge must exist and be accessible
- Machine can be optional for bridge-only queue items
- Queue vault data must be valid JSON format
- Task execution is subject to subscription concurrency limits
- Bridge must be in the same organization as the machine

#### Success Message

`Successfully created queue item for machine {machine} with priority {priority}`

## region

Create a new region for organizing bridges

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateRegion`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Regions are logical or geographic groupings for bridges. They help organize infrastructure deployment across different locations or environments. Bridges must be associated with a region.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `name` | string | Yes | - | Unique name for the region (e.g., us-east, europe-west) | us-east |
| `vault` | string | No | - | JSON configuration for the region (provider settings, metadata) | {"provider": "aws", "zone": "us-east-1"} |
| `vault-file` | string | No | - | File containing JSON vault configuration | region-config.json |


#### Examples

```bash
rediacc create region us-east
```
Create a basic region

```bash
rediacc create region europe-west --vault '{"provider":"azure","location":"westeurope"}'
```
Create region with provider configuration

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create region --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateRegion" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "name": "us-east",
    "vault": "{"provider": "aws", "zone": "us-east-1"}",
    "vault-file": "region-config.json"
}'
```

#### Notes

Regions cannot be deleted if they contain bridges. Region names must be unique across the organization.

#### Business Rules

- Region name must be unique within the organization
- Region vault data cannot be null or empty
- Organization must not have exceeded region resource limits
- User must pass authentication and authorization checks
- Vault data must be valid JSON format
- Resource limits depend on subscription plan
- Region names are case-sensitive
- Regions with bridges cannot be deleted
- Region creation is tracked in audit log
- Admin permissions may be required depending on organization settings

#### Success Message

`Successfully created region: {name}`

## repository

Create a new repository for code and data storage

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateRepository`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Repositories are isolated environments for storing code, data, or applications. They support Docker-based deployments via Rediaccfile, have dedicated storage volumes, and can be synchronized across machines.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that will own this repository | dev-team |
| `vault` | string | No | - | JSON configuration (size, type, settings) | {"size": "10G", "type": "docker"} |
| `parentRepo` | string | No | - |  |  |
| `repository` | string | Yes | - |  |  |
| `repositoryGuid` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create repository --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateRepository" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "dev-team",
    "vault": "{"size": "10G", "type": "docker"}",
    "parentRepo": "example-parent_repo"
}'
```

#### Business Rules

- Repository name must be unique within the team
- User must be a member of the specified team
- Repository vault data cannot be null or empty
- Organization must not have exceeded repository resource limits
- Team must exist within the user's organization
- Vault data must be valid JSON format
- Parent repository must exist if specified
- Resource limits depend on subscription plan
- Repository names are case-sensitive
- Parent repository must be in the same team
- GUID must be a valid UUID format if specified
- GUID must be unique across all repositories if specified
- GUID is auto-generated if not provided

#### Success Message

`Successfully created repository: {name} for team {team}`

## storage

Create a new storage resource

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateStorage`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Storage resources represent external storage systems like S3 buckets, Azure Blob Storage, or network shares. They're used for backups, archives, and data exchange between systems.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team that will own this storage | data-team |
| `vault` | string | No | - | JSON with storage credentials and configuration | {"type": "s3", "bucket": "my-backups", "region": "us-east-1", "access_key": "...", "secret_key": "..."} |
| `storage` | string | Yes | - |  |  |


#### Examples

```bash
rediacc create storage backup-team s3-archive
```
Create a basic storage resource

```bash
rediacc create storage prod azure-backup --vault-file azure-config.json
```
Create Azure storage with credentials from file

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create storage --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateStorage" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "data-team",
    "vault": "{"type": "s3", "bucket": "my-backups", "region": "us-east-1", "access_key": "...", "secret_key": "..."}",
    "storage": "example-storage"
}'
```

#### Notes

Storage credentials are encrypted in the vault. Supported types include S3, Azure Blob, GCS, SFTP, and SMB. Used with 'repo_push' and 'repo_pull' queue functions.

#### Business Rules

- Storage name must be unique within the team
- User must be a member of the specified team
- Storage vault data cannot be null or empty
- Organization must not have exceeded storage resource limits
- Team must exist within the user's organization
- Vault data must be valid JSON format
- Resource limits depend on subscription plan
- Storage names are case-sensitive
- Credentials in vault are automatically encrypted
- Storage types must be supported (S3, Azure, GCS, SFTP, SMB)

#### Success Message

`Successfully created storage: {name} for team {team}`

## team

Create a new team in your organization

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateTeam`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Teams are organizational units that own machines, repositories, and other resources. Team members can manage all resources within the team.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `name` | string | Yes | - | Unique name for the team | production-team |
| `vault` | string | No | - | JSON object with team configuration (SSH keys, settings) | {"SSH_PRIVATE_KEY": "-----BEGIN RSA..."} |
| `vault-file` | string | No | - | File containing JSON vault data | team-config.json |


#### Examples

```bash
rediacc create team production-team
```
Create a basic team

```bash
rediacc create team dev-team --vault-file team-config.json
```
Create team with vault configuration from file

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create team --name <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateTeam" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "name": "production-team",
    "vault": "{"SSH_PRIVATE_KEY": "-----BEGIN RSA..."}",
    "vault-file": "team-config.json"
}'
```

#### Notes

Team creation counts against your subscription limits. The creator automatically becomes a team member.

#### Business Rules

- Team name must be unique within the organization
- Team vault data cannot be null or empty
- User must pass authentication and authorization checks
- Organization must not have exceeded team resource limits
- Creator is automatically added as a team member
- Team names are case-sensitive
- Vault data must be valid JSON format
- Resource limits depend on subscription plan
- Team creation is tracked in audit log
- Bridge users cannot be added to teams

#### Success Message

`Successfully created team: {name}`

## user

Create a new user in your organization

#### API Information

**Endpoint:** `POST /api/StoredProcedure/CreateNewUser`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Creates a new user account that can access the organization resources. Users must be activated before they can log in.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `activationCode` | string | No | - |  |  |
| `newUserEmail` | string | Yes | - |  |  |
| `newUserHash` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc create user
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/CreateNewUser" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "activationCode": "example-activation_code",
    "newUserEmail": "example-new_user_email",
    "newUserHash": "example-new_user_hash"
}'
```

#### Business Rules

- User email must not already exist in the system
- Password hash must be exactly 32 bytes
- Activation code must be exactly 6 characters
- Email format validation is performed
- Organization must not have exceeded user resource limits
- User creation is atomic with transactional safety
- New users are created in inactive state and must be activated
- Empty user vault is created automatically
- Resource limits depend on subscription plan
- User email must be unique across the entire system

#### Success Message

`Successfully created user: {email}`


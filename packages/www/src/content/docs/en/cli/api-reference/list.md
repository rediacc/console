---
title: "List"
description: "List and view resources."
category: "CLI API Reference"
language: "en"
---

# List

List and view resources.

## Table of Contents

- [audit-logs](#audit-logs)
- [bridges](#bridges)
- [organization-vault](#organization-vault)
- [data-graph](#data-graph)
- [entity-history](#entity-history)
- [list-system-configuration](#list-system-configuration)
- [list-user-vault](#list-user-vault)
- [lookup-data](#lookup-data)
- [regions](#regions)
- [resource-limits](#resource-limits)
- [sessions](#sessions)
- [subscription](#subscription)
- [team-machines](#team-machines)
- [team-members](#team-members)
- [team-repositories](#team-repositories)
- [team-storages](#team-storages)
- [teams](#teams)
- [user-organization](#user-organization)
- [users](#users)

## audit-logs

View audit trail of system changes

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetAuditLogs`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows detailed audit logs of all system modifications including who made changes, when, and what was changed. Essential for compliance, security monitoring, and troubleshooting.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `startDate` | string | Yes | - |  |  |
| `endDate` | string | Yes | - |  |  |
| `entityFilter` | string | Yes | - |  |  |
| `maxRecords` | integer | Yes | - |  |  |


#### Examples

```bash
rediacc list audit-logs --start-date 2024-01-01T00:00:00Z
```
Get audit logs from specific date

```bash
rediacc list audit-logs --entity-filter Team --max-records 100
```
Get last 100 team-related changes

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list audit-logs
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetAuditLogs" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "startDate": "example-start_date",
    "endDate": "example-end_date",
    "entityFilter": "example-entity_filter"
}'
```

#### Notes

Audit logs are retained based on subscription tier. Includes create, update, delete operations and authentication events.

#### Business Rules

- User must be authenticated
- Can only see audit logs for your own organization
- Default time period is 30 days if no start date provided
- Start date must come before end date
- Default limit is 1,000 records, maximum is 10,000
- Administrators see all organization audit logs
- Regular users only see logs for resources they have access to
- Entity type filtering is optional
- Sensitive operations masked for non-administrators
- Users can always view their own user account logs

## bridges

List bridges in a specific region

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetRegionBridges`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Bridges are autonomous queue processors that execute tasks on machines. They poll for queue items and manage SSH connections to target machines.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `region` | string | Yes | - | Name of the region to list bridges from | us-east |


#### Examples

```bash
rediacc list bridges us-east
```
List all bridges in the us-east region

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list bridges --region <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetRegionBridges" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "region": "us-east"
}'
```

#### Notes

Bridges must be running in bridge mode to process queue items.

#### Business Rules

- User must be authenticated with a valid token
- Region must exist within your organization
- Region names are case-sensitive
- Regular users can only see vault data for bridges they have access to through team machines
- Access determined by: user is member of team that has machines using the bridge
- Administrators can see all bridge information including sensitive vault data
- Bridge credentials and user emails only visible to administrators
- Machine count shown for each bridge
- HasAccess indicator shows if user can use the bridge
- Special 'Global Bridges' entry may be shown for cloud-managed bridges

## organization-vault

View organization-wide vault configuration

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Displays the encrypted vault data stored at the organization level. This typically contains global settings and shared credentials.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list organization-vault
```
View organization vault contents

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list organization-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires organization admin permissions. Vault data is automatically decrypted if you have the master password configured.

#### Business Rules

- User must be logged in with valid credentials
- Can only access vault data for your own organization
- Returns organization's main vault content and version
- Includes organization name for identification
- Request must pass security validation
- Cross-organization access not permitted
- GetOrganizationVaults (admin-only) shows ALL vaults across organization
- Administrators can view decrypted credentials and sensitive data
- Two-factor authentication vaults excluded for security
- Bridge users allowed access for automated operations

## data-graph

Display organization infrastructure as a hierarchical graph

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationDataGraphJson`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows the complete infrastructure topology including regions, bridges, teams, machines, and their relationships in a graph format.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list data-graph
```
Display infrastructure graph

```bash
rediacc list data-graph --output json | jq '.graph'
```
Extract graph data for visualization

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list data-graph
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationDataGraphJson" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Useful for understanding infrastructure topology and dependencies. JSON output can be used with graph visualization tools.

#### Business Rules

- User must be authenticated with valid credentials
- Can only view data for your own organization
- Administrators see all infrastructure across the organization
- Regular users only see infrastructure they have access to
- Access determined through team membership chain
- Users see teams they belong to and resources owned by those teams
- Machines only visible if user is member of owning team
- Bridges/regions visible if user has access to machines within them
- Data organized in hierarchical levels for visualization
- Both nodes and relationships filtered based on access rights

## entity-history

View change history for a specific entity

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetEntityHistory`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows the modification history for a specific entity (team, machine, user, etc.) identified by its credential GUID. Includes who made changes, when, and what was changed.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `credential` | string | Yes | - | Entity's unique credential (GUID) | 550e8400-e29b-41d4-a716-446655440000 |
| `entity` | string | Yes | - |  |  |
| `maxRecords` | integer | Yes | - |  |  |


#### Examples

```bash
rediacc list entity-history Machine 550e8400-e29b-41d4-a716-446655440000
```
View history for a specific machine

```bash
rediacc list entity-history Team 123e4567-e89b-12d3-a456-426614174000 --max-records 50
```
View last 50 changes to a team

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list entity-history --credential <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetEntityHistory" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "credential": "550e8400-e29b-41d4-a716-446655440000",
    "entity": "example-entity",
    "maxRecords": 100
}'
```

#### Notes

Get the credential from 'inspect' commands. History includes creates, updates, deletes, and vault changes.

#### Business Rules

- User must be authenticated
- Entity type is required and must be valid
- Entity credential (GUID) is mandatory
- Entity must exist in your organization
- Access rules vary by entity type and user role
- Maximum 5,000 records, default 500
- Users can view their own history, admins see all
- Team/machine/repo access requires membership
- Sensitive operations filtered for non-administrators
- Access denial protects entity existence information

## list-system-configuration

list-system-configuration command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetSystemConfiguration`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `configKey` | string | Yes | - |  |  |


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list list-system-configuration
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetSystemConfiguration" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "configKey": "example-config_key"
}'
```

## list-user-vault

list-user-vault command

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetUserVault`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Parameters

No parameters required.


#### Examples

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list list-user-vault
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetUserVault" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

## lookup-data

Get dropdown/selection data for UI components

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetLookupData`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Provides lookup data used for dropdowns and selection lists in UI components. Returns teams, regions, bridges, machines, users, and other selectable resources based on your permissions.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `context` | string | No | - | Optional context filter (e.g., 'machine_create', 'queue_create') | machine_create |


#### Examples

```bash
rediacc list lookup-data
```
Get all available lookup data

```bash
rediacc list lookup-data --context queue_create
```
Get lookup data specific to queue creation

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list lookup-data
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetLookupData" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "context": "machine_create"
}'
```

#### Notes

Returns different data based on user permissions. Admins see all resources, regular users see only accessible resources.

#### Business Rules

- User must be authenticated with valid token
- User must belong to an organization
- Regular users only see teams they are members of
- Regular users only see machines belonging to their teams
- Regular users only see bridges/regions with accessible machines
- Regular users only see users in shared teams
- Administrators see all organization resources
- Optional context parameter filters data for specific use cases
- Organization isolation enforced - no cross-organization visibility
- All data returned as JSON with value/label pairs

## regions

List all regions in your organization

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationRegions`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows geographic regions where you can deploy bridges and infrastructure. Each region can contain multiple bridges for distributed task processing.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list regions
```
Display all regions with their vault configurations

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list regions
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationRegions" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Regions define geographic or logical boundaries for infrastructure deployment.

#### Business Rules

- User must be authenticated with a valid token
- Token must be active and not expired
- User must belong to an organization
- Only regions within your organization are visible
- Administrators can see full vault data for all regions
- Non-administrators cannot see sensitive vault data
- Bridge count is shown for each region
- Regions are sorted alphabetically by name
- No team membership required to view regions
- Empty result set is returned if no regions exist

## resource-limits

Display organization resource limits and current usage

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationDashboardJson`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows your subscription limits and current usage for all resource types including teams, machines, bridges, repositories, and more. Multiple subscriptions stack their limits.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list resource-limits
```
View resource usage vs limits in table format

```bash
rediacc list resource-limits --output json | jq '.resourceLimits'
```
Extract resource limits data for monitoring

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list resource-limits
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationDashboardJson" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Useful for capacity planning and monitoring when approaching subscription limits. Returns 402 Payment Required when limits are exceeded.

#### Business Rules

- User must be authenticated and belong to an organization
- Resource limits are additive across multiple active subscriptions
- Tracks 8 resource types: regions, teams, bridges, machines, repositories, schedules, storage, users
- Shows current usage count vs total allowed limit
- Usage percentage calculated for each resource type
- Default to Community tier if no active subscription
- Queue priority feature only for Business/Enterprise tiers
- Resource limits by tier: Community (2), Pro (3-10), Business (5-50), Enterprise (10-200)
- Resources at 80% or more flagged as near limit
- Upgrade recommended if 3+ resources at 80% capacity

## sessions

List active sessions and authentication requests

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetUserRequests`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all active authentication sessions including session names, creation time, expiration, permissions, and originating IP addresses. Helps monitor access and detect unauthorized sessions.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list sessions
```
View all active sessions

```bash
rediacc list sessions --output json | jq '.[] | select(.sessionName | contains("CLI"))'
```
Filter CLI sessions

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list sessions
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetUserRequests" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Sessions expire based on tokenExpirationHours setting. Bridge tokens may have extended expiration. Use 'logout' to terminate current session.

#### Business Rules

- Valid session token required with matching verification code
- Only active sessions are accepted (not expired or logged out)
- Token rotation up to 3 times before requiring latest token
- Users can only see their own sessions
- Organization maintenance mode blocks non-administrator access
- Two-factor authentication must be completed if enabled
- Sessions sorted by creation time (newest first)
- Shows session name, creation time, permissions, and expiration
- No administrative override - admins also see only their own sessions
- Zero trust security model with full authentication on every request

## subscription

Show subscription details and billing information

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationDashboardJson`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Displays active subscriptions, plan details, expiration dates, and feature limits. Multiple subscriptions stack their resource limits. Shows both current usage and available capacity.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list subscription
```
View subscription status and limits

```bash
rediacc list subscription --output json | jq '.subscriptions'
```
Extract subscription data for monitoring

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list subscription
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationDashboardJson" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Plans: COMMUNITY (free), PRO, BUSINESS, ENTERPRISE. Higher tiers offer more resources, priority levels, and features like schedules and Ceph.

#### Business Rules

- User must be authenticated with valid session
- Can only view subscription information for your own organization
- Shows highest tier subscription when multiple are active
- Subscription priority: Enterprise > Business > Pro > Community
- Active subscriptions must have ACTIVE status and future end date
- Resource limits are cumulative across all active subscriptions
- Trial subscriptions identified if 45 days or less (non-Community)
- Expiration warnings shown for subscriptions ending within 30 days
- Feature access varies by tier (Analytics for Business/Enterprise, etc.)
- Queue priority features only visible to Business/Enterprise subscribers

## team-machines

List machines in a specific team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamMachines`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all machines assigned to a team including their status, assigned bridge, vault configuration, and queue statistics. Machine names are unique across the organization.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team name to list machines from (comma-separated for multiple teams) | production-team |


#### Examples

```bash
rediacc list team-machines production-team
```
List all machines in production team

```bash
rediacc list team-machines team1,team2
```
List machines from multiple teams

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list team-machines --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamMachines" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "production-team"
}'
```

#### Notes

You must be a member of the team to see its machines. Shows queue count for each machine.

#### Business Rules

- Valid user authentication required with active session
- User must be a member of the team to see machines
- Organization boundary enforced - only see machines in your organization
- Multiple teams supported with comma-separated names
- No team filter returns machines from all your teams
- Shows machine details including bridge, region, queue count
- Vault information includes encrypted credentials and settings
- Results sorted by team name then machine name
- Invalid team names silently filtered out
- Real-time queue count helps understand workload

## team-members

List members of a specific team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamMembers`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all users who have access to a team's resources. Team members can manage all resources within the team.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team name to list members from | production-team |


#### Examples

```bash
rediacc list team-members production-team
```
List all members of production team

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list team-members --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamMembers" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "production-team"
}'
```

#### Notes

You must be a member of the team to view its membership. Shows email addresses and join dates.

#### Business Rules

- User must be authenticated with valid token
- Can only view members of teams you belong to
- Organization boundary restriction applies
- Team filtering with comma-separated names supported
- No team specified returns members from all your teams
- Shows user email and activation status
- Results are deduplicated - each user appears once
- No special permissions required beyond team membership
- Team names are case-sensitive
- No administrative override for non-member access

## team-repositories

List all repositories owned by a team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamRepositories`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all code repositories associated with a team. Repositories are isolated environments for storing code, data, or applications with Docker support.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team name to list repositories from | dev-team |


#### Examples

```bash
rediacc list team-repositories dev-team
```
List all repositories in dev-team

```bash
rediacc list team-repositories prod --output json | jq '.[].repositoryName'
```
Extract repository names from production team

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list team-repositories --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamRepositories" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "dev-team"
}'
```

#### Notes

You must be a member of the team. Shows repository names, credentials, and vault status.

#### Business Rules

- User must be logged in with valid credentials
- User must belong to the organization
- User must be member of the team to view repositories
- Team name filtering with exact case-sensitive match
- Multiple teams supported with comma-separated names
- No team specified returns repositories from all your teams
- Shows repository name, GUID, and parent repository ID
- Vault data decrypted using organization passphrase
- Results sorted by team name then repository name
- Three-level access control: authentication, organization, team

## team-storages

List storage resources for a team

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetTeamStorages`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all external storage configurations for a team. Storage resources represent S3 buckets, Azure Blob Storage, or network shares used for backups and data exchange.

#### Parameters

| Parameter | Type | Required | Default | Description | Example |
|-----------|------|----------|---------|-------------|---------|
| `team` | string | Yes | - | Team name to list storages from | data-team |


#### Examples

```bash
rediacc list team-storages data-team
```
List all storage resources in data-team

```bash
rediacc list team-storages backup --output json | jq '.[] | select(.storageName | contains("s3"))'
```
Find all S3 storage resources

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list team-storages --team <value>
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetTeamStorages" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{
    "team": "data-team"
}'
```

#### Notes

You must be a member of the team. Storage credentials are encrypted in vaults. Used with repo_push/repo_pull functions.

#### Business Rules

- User must be logged in with valid credentials
- User account must be activated
- Can only access storage from your own organization
- Must be member of the team to view storage
- Maintenance mode blocks non-administrator access
- Team name filtering supports comma-separated values
- Shows storage name, team, and decrypted configuration
- Storage credentials automatically decrypted
- Results sorted by team name then storage name
- Failed authentication results in 403 error

## teams

List all teams in your organization

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationTeams`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Displays teams with membership information, resource counts, and vault access. Only shows vault data for teams where you are a member.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list teams
```
List all teams in table format

```bash
rediacc list teams --output json
```
List all teams in JSON format for scripting

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list teams
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationTeams" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires authentication. Vault content is only visible for teams you belong to.

#### Business Rules

- User must be authenticated with valid credentials
- User must belong to an organization to retrieve team information
- All teams in the organization are visible to all users
- Vault data (sensitive information) is only visible for teams where you are a member
- Teams are sorted alphabetically by name
- Statistics show member count, machine count, repository count, schedule count, and storage count
- Encrypted vault data requires organization passphrase for decryption
- No cross-organization access is allowed
- Membership status indicator shows 1 for member, 0 for non-member
- Organization name is included for context

## user-organization

Display which organization the current user belongs to

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetUserOrganization`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows the organization information for the currently authenticated user. Useful for verifying you're logged into the correct organization account.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list user-organization
```
Display current user's organization

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list user-organization
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetUserOrganization" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires authentication. Shows organization name and ID.

#### Business Rules

- Valid authentication token required
- Token rotation required for security
- Active session must not be expired
- Users can only view their own organization information
- No cross-organization access allowed
- Organization name and vault data returned
- Shows team count, region count, and user count statistics
- Each user associated with exactly one organization
- Organization passphrase used to decrypt vault data
- Failed validation returns no organization information

## users

List all users in your organization

#### API Information

**Endpoint:** `POST /api/StoredProcedure/GetOrganizationUsers`

**Authentication:** Required (token-based with Rediacc-RequestToken header)

#### Details

Shows all user accounts including their email, status (active/inactive), permission groups, TFA status, and last login information. Useful for user management and audit purposes.

#### Parameters

No parameters required.


#### Examples

```bash
rediacc list users
```
Display all organization users in table format

```bash
rediacc list users --output json | jq '.[] | select(.isActive == false)'
```
Find all inactive users

##### Auto-Generated CLI Examples

```bash
# Basic usage (required parameters only)
rediacc list users
```

##### Auto-Generated cURL Examples

```bash
# Using token authentication
curl -X POST "https://www.rediacc.com/api/StoredProcedure/GetOrganizationUsers" \
  -H "Content-Type: application/json" \
  -H "Rediacc-RequestToken: YOUR_TOKEN_HERE" \
  -d '{}'
```

#### Notes

Requires authentication. Shows user status, permissions, and security settings. Personal information like passwords is never exposed.

#### Business Rules

- User must be logged in with valid authentication token
- Token must be active and not expired
- User account must be activated
- Token rotation required for security
- Users can only view users from their own organization
- Administrators can see all users and their vault data
- Non-administrators can only see users who share at least one team with them
- Vault data (sensitive information) only visible to administrators
- Shows permission groups (Administrators, Users, or Bridges)
- Organization boundary enforcement prevents cross-organization visibility


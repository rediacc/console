# Rediacc CLI Implementation Plan

## Overview

This document provides a comprehensive plan for implementing a Node.js CLI tool that shares core business logic with the console React application. The CLI will provide command-line access to all Rediacc operations.

---

## Architecture

### Design Principles

1. **Resource-First Commands** - `rediacc <resource> <action> [options]`
2. **Shared Core Logic** - Reuse `src/core/` from console
3. **Platform Adapters** - Node-specific implementations for crypto/storage
4. **Context System** - Reduce repetition with saved defaults
5. **Queue Shortcuts** - Fast path for common operations

### Directory Structure

```
console/
├── src/
│   ├── core/           # Shared business logic (existing)
│   └── ...
└── cli/                # NEW - CLI application
    ├── package.json
    ├── tsconfig.json
    ├── src/
    │   ├── index.ts                    # Entry point
    │   ├── cli.ts                      # Command router
    │   ├── adapters/
    │   │   ├── storage.ts              # File-based storage (~/.rediacc/)
    │   │   └── crypto.ts               # Node crypto implementation
    │   ├── services/
    │   │   ├── api.ts                  # API client wrapper
    │   │   ├── auth.ts                 # Authentication service
    │   │   ├── context.ts              # Context management
    │   │   └── output.ts               # Output formatting
    │   ├── commands/
    │   │   ├── index.ts                # Command registry
    │   │   ├── auth.ts                 # auth login/logout/token
    │   │   ├── company.ts              # company info/vault/export
    │   │   ├── user.ts                 # user list/create/deactivate
    │   │   ├── team.ts                 # team list/create/member
    │   │   ├── region.ts               # region list/create
    │   │   ├── bridge.ts               # bridge list/create
    │   │   ├── machine.ts              # machine list/create
    │   │   ├── storage.ts              # storage list/create
    │   │   ├── repo.ts                 # repo list/create/promote
    │   │   ├── queue.ts                # queue list/create/trace
    │   │   ├── permission.ts           # permission group/add/remove
    │   │   ├── ds.ts                   # distributed storage (cluster/pool/image/snapshot/clone)
    │   │   ├── audit.ts                # audit log/trace/history
    │   │   ├── context.ts              # context set/show/clear
    │   │   └── shortcuts.ts            # run/trace/cancel/retry
    │   ├── utils/
    │   │   ├── prompt.ts               # Interactive prompts
    │   │   ├── spinner.ts              # Loading indicators
    │   │   ├── table.ts                # Table formatting
    │   │   └── errors.ts               # Error handling
    │   └── types/
    │       └── index.ts                # CLI-specific types
    └── bin/
        └── rediacc                     # Executable entry point
```

---

## Core Imports

### From `src/core/`

```typescript
import {
  // Services
  QueueService,

  // Types
  QueueRequestContext,
  QueueItemData,
  QueueItem,
  FunctionRequirements,
  ActiveTask,
  ApiResponse,
  ApiError,
  VaultData,
  VaultContextData,
  IStorageProvider,
  ICryptoProvider,

  // Utilities
  CryptoService,
  SecureMemoryStorage,
  minifyJSON,
  prettifyJSON,
  objectToMinifiedJSON,

  // API Helpers
  extractTableData,
  getFirstRow,
  getResultSet,
  parseNestedJson,

  // Validation
  teamNameSchema,
  machineNameSchema,
  emailSchema,
  // ... all validation schemas
} from '../core'
```

### From `src/api/`

```typescript
import { ApiClient } from '../api/client'
import { initializeApiClient } from '../api/init'
```

### From `src/core/data/`

```typescript
import functionsData from '../core/data/functions.json'
```

---

## Business Logic Extraction Plan

To maximize code reuse between the console and CLI, business logic currently embedded in React components must be extracted into framework-agnostic services in `src/core/`.

### Extraction Priorities

| Priority | Service | Current Location | Benefit |
|----------|---------|-----------------|---------|
| High | `RepositoryRelationshipService` | `MachineRepositoryList`, `CredentialsPage` | Grand/fork detection, affected resources finder |
| High | `VaultStatusParserService` | 6+ components with duplicated parsing | Consistent deployment info extraction |
| High | `ResourceValidationService` | Scattered in components | Delete/promote/assign business rules |
| Medium | `MachineValidationService` | `features/distributed-storage/` | Move to core for CLI access |
| Medium | `ResourceResolutionService` | Various pages | Cross-reference teams/machines/repos |
| Low | `QueueItemAnalysisService` | `QueueItemTraceModal` | Status interpretation, progress calculation |

### Proposed Core Services Structure

```
src/core/
├── services/
│   ├── queue/
│   │   ├── index.ts                # Export QueueService
│   │   ├── service.ts              # Existing QueueService
│   │   ├── status.ts               # Terminal status, status config
│   │   ├── retry.ts                # Retry eligibility, permanent failures
│   │   ├── health.ts               # Stale detection, health checks
│   │   └── filters.ts              # Active/completed filtering
│   ├── repository/
│   │   ├── relationship.ts         # Grand/fork logic, affected resources
│   │   ├── validation.ts           # Delete/promote business rules
│   │   └── index.ts
│   ├── machine/
│   │   ├── validation.ts           # Assignment, cluster rules
│   │   ├── vault-status.ts         # Parse deployment info from vaultStatus
│   │   └── index.ts
│   ├── resource/
│   │   ├── resolution.ts           # Cross-reference lookup utilities
│   │   └── index.ts
│   ├── vault/
│   │   ├── extraction.ts           # Extract typed data from vaults
│   │   └── index.ts
│   ├── functions/
│   │   ├── requirements.ts         # Function requirements checking
│   │   ├── validation.ts           # Parameter validation
│   │   └── index.ts
│   └── bulk/
│       ├── validation.ts           # Bulk operation validation
│       └── index.ts
├── utils/
│   ├── time.ts                     # Relative time, duration, formatting
│   ├── size.ts                     # Parse/format bytes, percentages
│   ├── validation.ts               # GUID, SSH key, priority validation
│   ├── progress-parser.ts          # Extract progress from console output
│   ├── status.ts                   # Progress thresholds, status mapping
│   ├── sorting.ts                  # Type-safe sorter factories
│   ├── batch.ts                    # Batch creation utilities
│   ├── api.ts                      # Property normalization, response helpers
│   └── crypto.ts                   # Vault field detection
├── types/
│   └── ...                         # Existing types
└── index.ts                        # Export all services and utils
```

### Service Design Patterns

All extracted services must follow these patterns:

1. **Pure Functions** - No React hooks, no UI dependencies, no side effects
2. **Type-Safe** - Full TypeScript with exported interfaces for all inputs/outputs
3. **Testable** - Easily mockable dependencies, deterministic outputs
4. **Framework Agnostic** - Must work in both browser (React) and Node.js (CLI)
5. **No External State** - Receive all required data as parameters

**Example Pattern:**

```typescript
// src/core/services/repository/relationship.ts

export interface AffectedResourcesResult {
  isCredential: boolean
  forks: Repository[]
  affectedMachines: AffectedMachine[]
}

export interface AffectedMachine {
  machineName: string
  repoNames: string[]
}

export function getAffectedResources(
  repository: Repository,
  allRepositories: Repository[],
  machines: Machine[]
): AffectedResourcesResult {
  // Pure business logic - no React, no API calls
  // Returns computed result based on inputs
}

export function isCredential(repository: Repository): boolean {
  return !repository.grandGuid || repository.grandGuid === repository.repositoryGuid
}

export function findForksOfCredential(
  credentialGuid: string,
  repositories: Repository[]
): Repository[] {
  return repositories.filter(
    repo => repo.grandGuid === credentialGuid && repo.repositoryGuid !== credentialGuid
  )
}
```

### Key Extraction Candidates

#### Repository Logic

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `getAffectedResources()` | `CredentialsPage.tsx` | `repository/relationship.ts` |
| `groupRepositoriesByName()` | `MachineRepositoryList/index.tsx` | `repository/relationship.ts` |
| Fork detection logic | `MachineRepositoryList/index.tsx` | `repository/validation.ts` |
| Grand/credential identification | Multiple files | `repository/relationship.ts` |
| Promotion eligibility check | `MachineRepositoryList/index.tsx` | `repository/validation.ts` |

#### Machine Logic

| Function | Source File | Target Service |
|----------|-------------|----------------|
| VaultStatus JSON parsing | `MachineRepositoryList`, `MachineTable`, `RepositoryContainerList`, etc. | `machine/vault-status.ts` |
| Machine assignment validation | `features/distributed-storage/services/` | `machine/validation.ts` |
| Cluster exclusivity rules | `features/distributed-storage/hooks/` | `machine/validation.ts` |

#### Resource Resolution

| Function | Source File | Target Service |
|----------|-------------|----------------|
| Team vault lookup | Various pages | `resource/resolution.ts` |
| Machine-to-team mapping | Various pages | `resource/resolution.ts` |
| Bridge-to-region mapping | Various pages | `resource/resolution.ts` |

#### Queue Status & Lifecycle

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `isTerminalStatus()` | `core/services/queue.ts` | `queue/status.ts` |
| Status config mapping | `QueuePage.tsx` | `queue/status.ts` |
| Retry eligibility check | `queueMonitoringService.ts` | `queue/retry.ts` |
| `isPermanentFailure()` | `queueMonitoringService.ts` | `queue/retry.ts` |
| Stale task detection | `queueMonitoringService.ts` | `queue/health.ts` |
| Active/completed filtering | `QueuePage.tsx` | `queue/filters.ts` |
| Priority validation (1-5) | `useManagedQueueItem.ts` | `utils/validation.ts` |

#### Progress Parsing

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `extractMostRecentProgress()` | `QueueItemTraceModal/index.tsx` | `utils/progress-parser.ts` |
| `extractProgressMessage()` | `QueueItemTraceModal/index.tsx` | `utils/progress-parser.ts` |
| Progress thresholds | `DashboardPage.tsx` | `utils/status.ts` |

#### Time & Duration Utilities

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `getRelativeTimeFromUTC()` | `utils/timeUtils.ts` | `utils/time.ts` |
| `formatTimestampAsIs()` | `utils/timeUtils.ts` | `utils/time.ts` |
| Elapsed time calculation | `QueueItemTraceModal/index.tsx` | `utils/time.ts` |
| Duration formatting | Various | `utils/time.ts` |

#### Size & Resource Utilities

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `parseMemorySize()` | `utils/sizeUtils.ts` | `utils/size.ts` |
| `formatBytes()` | `utils/sizeUtils.ts` | `utils/size.ts` |
| `calculateResourcePercent()` | `utils/sizeUtils.ts` | `utils/size.ts` |

#### Validation Utilities

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `isValidGuid()` | `QueuePage.tsx` | `utils/validation.ts` |
| `isValidSSHPublicKey()` | `utils/cryptoGenerators.ts` | `utils/validation.ts` |
| `normalizeProperty()` | `QueueItemTraceModal/index.tsx` | `utils/api.ts` |

#### Vault & Encryption

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `extractMachineData()` | `core/services/queue.ts` | `vault/extraction.ts` |
| `extractCompanyData()` | `core/services/queue.ts` | `vault/extraction.ts` |
| `extractRepositoryData()` | `core/services/queue.ts` | `vault/extraction.ts` |
| `hasVaultFields()` | `api/encryptionMiddleware.ts` | `utils/crypto.ts` |

#### Batch Operations

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `createBatches()` | `bulk-operations.controller.ts` | `utils/batch.ts` |
| `performBulkValidation()` | `bulk-operations.controller.ts` | `bulk/validation.ts` |

#### Sorting & Filtering

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `createSorter()` | `utils/tableSorters.ts` | `utils/sorting.ts` |
| `createStringSorter()` | `utils/tableSorters.ts` | `utils/sorting.ts` |
| `createNumberSorter()` | `utils/tableSorters.ts` | `utils/sorting.ts` |
| `createDateSorter()` | `utils/tableSorters.ts` | `utils/sorting.ts` |

#### Function & Template Logic

| Function | Source File | Target Service |
|----------|-------------|----------------|
| `getFunctionRequirements()` | `services/functionsService.ts` | `functions/requirements.ts` |
| Function parameter validation | Various | `functions/validation.ts` |

### Extraction Summary

| Category | Count | Priority |
|----------|-------|----------|
| Queue Status/Lifecycle | 7 | High |
| Time/Duration Formatting | 4 | High |
| Size Formatting | 3 | High |
| Progress Parsing | 3 | High |
| Validation Utilities | 3 | Medium |
| Vault/Data Extraction | 4 | Medium |
| Batch Operations | 2 | Medium |
| Sorting/Filtering | 4 | Low |
| Function/Template | 2 | Low |
| Repository Logic | 5 | High |
| Machine Logic | 3 | High |
| Resource Resolution | 3 | Medium |

**Total: 43 extraction candidates**

### VaultStatus Parser Service

This is a high-priority extraction due to code duplication across 6+ files. The parser handles:

```typescript
// src/core/services/machine/vault-status.ts

export interface ParsedVaultStatus {
  status: 'completed' | 'pending' | 'failed' | 'unknown'
  repositories: DeployedRepository[]
  rawResult?: string
  error?: string
}

export interface DeployedRepository {
  name: string  // This is the repository GUID
  size?: number
  size_human?: string
  mounted?: boolean
  accessible?: boolean
  docker_running?: boolean
  container_count?: number
  // ... other fields from vaultStatus result
}

export function parseVaultStatus(vaultStatusJson: string | undefined): ParsedVaultStatus {
  if (!vaultStatusJson) {
    return { status: 'unknown', repositories: [] }
  }

  try {
    const data = JSON.parse(vaultStatusJson)

    if (data.status !== 'completed' || !data.result) {
      return { status: data.status || 'unknown', repositories: [] }
    }

    // Clean result string (handle jq errors, trailing content)
    const cleanedResult = cleanResultString(data.result)
    const result = JSON.parse(cleanedResult)

    return {
      status: 'completed',
      repositories: result.repositories || [],
      rawResult: cleanedResult
    }
  } catch (error) {
    return { status: 'unknown', repositories: [], error: String(error) }
  }
}

export function findDeployedRepositories(
  machines: Machine[],
  repositoryGuids: string[]
): Map<string, DeployedRepository[]> {
  // Returns map of machineName -> deployed repos matching the GUIDs
}
```

### Migration Strategy

#### Phase 1: Extract Without Breaking (Week 1-2)

1. Create new service files in `src/core/services/`
2. Copy and adapt logic from components (don't modify components yet)
3. Add comprehensive unit tests for extracted services
4. Export services from `src/core/index.ts`

#### Phase 2: Update Console (Week 3-4)

1. Update React components to import from `src/core/`
2. Replace inline logic with service calls
3. Remove duplicated code from components
4. Verify all existing functionality works

#### Phase 3: CLI Integration (Ongoing)

1. CLI imports services directly from `src/core/`
2. Services work identically in both environments
3. Bug fixes and improvements benefit both platforms

### Usage in CLI

Once extracted, the CLI can use these services directly:

```typescript
// cli/src/commands/repo.ts
import {
  getAffectedResources,
  isCredential,
  findForksOfCredential
} from '../../core/services/repository/relationship'
import { parseVaultStatus } from '../../core/services/machine/vault-status'

async function handleDeleteRepository(repoName: string, options: Options) {
  const repositories = await fetchRepositories(options.team)
  const machines = await fetchMachines(options.team)
  const repo = repositories.find(r => r.repositoryName === repoName)

  const { isCredential, forks, affectedMachines } = getAffectedResources(
    repo,
    repositories,
    machines
  )

  if (isCredential && affectedMachines.length > 0) {
    console.error('Cannot delete credential with active deployments')
    console.error('Affected machines:', affectedMachines.map(m => m.machineName))
    process.exit(1)
  }

  // Proceed with deletion...
}
```

### Testing Requirements

All extracted services must have:

1. **Unit tests** covering all functions
2. **Edge case tests** (empty arrays, null values, malformed JSON)
3. **Integration tests** verifying behavior matches original component logic
4. **Cross-platform tests** ensuring Node.js compatibility

### Success Criteria

- [ ] VaultStatus parsing consolidated into single service (eliminates 6+ duplications)
- [ ] Repository relationship logic extracted and tested
- [ ] All extracted services have >90% test coverage
- [ ] Console components updated to use extracted services
- [ ] CLI successfully uses all extracted services
- [ ] No TypeScript errors in either console or CLI
- [ ] Performance maintained (no regression in console)

---

## Node Adapters

### Storage Adapter

**File:** `cli/src/adapters/storage.ts`

**Purpose:** File-based storage in `~/.rediacc/`

**Implementation Requirements:**
- Implement `IStorageProvider` interface
- Store data in `~/.rediacc/config.json`
- Handle file permissions (0600 for sensitive data)
- Support atomic writes to prevent corruption
- Create directory if not exists

**Key Methods:**
```typescript
class NodeStorageAdapter implements IStorageProvider {
  private configPath: string  // ~/.rediacc/config.json

  async getItem(key: string): Promise<string | null>
  async setItem(key: string, value: string): Promise<void>
  async removeItem(key: string): Promise<void>
  async clear(): Promise<void>
}
```

**Storage Structure:**
```json
{
  "token": "encrypted-token",
  "context": {
    "team": "Default",
    "region": "us-east"
  },
  "apiUrl": "https://api.rediacc.com",
  "masterPassword": "encrypted-password"
}
```

### Crypto Adapter

**File:** `cli/src/adapters/crypto.ts`

**Purpose:** Encryption using Node.js `crypto` module

**Implementation Requirements:**
- Implement `ICryptoProvider` interface
- Use same algorithm as web: AES-256-GCM with PBKDF2
- Match salt length (16), iterations (100000), key length (256), IV length (12)
- Base64 encoding for storage compatibility

**Key Methods:**
```typescript
class NodeCryptoProvider implements ICryptoProvider {
  async encrypt(data: string, password: string): Promise<string>
  async decrypt(data: string, password: string): Promise<string>
  async deriveKey(password: string, salt: Uint8Array): Promise<Buffer>
  async generateHash(data: string): Promise<string>
}
```

---

## Command Structure

### Top-Level Commands

| Command | Description | Shortcut |
|---------|-------------|----------|
| `auth` | Authentication & tokens | `login`, `logout` |
| `company` | Company settings | - |
| `user` | User management | - |
| `team` | Team management | - |
| `region` | Region management | - |
| `bridge` | Bridge management | - |
| `machine` | Machine management | - |
| `storage` | Storage management | - |
| `repo` | Repository management | - |
| `queue` | Queue management | `run`, `trace`, `cancel`, `retry` |
| `permission` | Permission groups | - |
| `ds` | Distributed storage | - |
| `audit` | Audit logs | - |
| `context` | CLI context | - |
| `config` | CLI configuration | - |

### Command Mapping to API Endpoints

#### Authentication (`auth`)

| CLI Command | API Endpoint | Core Service |
|-------------|--------------|--------------|
| `auth login` | `CreateAuthenticationRequest` | `ApiClient.login()` |
| `auth logout` | (clear local token) | - |
| `auth status` | `GetRequestAuthenticationStatus` | `ApiClient.get()` |
| `auth privilege` | `PrivilegeAuthenticationRequest` | `ApiClient.post()` |
| `auth token list` | `GetUserRequests` | `ApiClient.get()` |
| `auth token fork` | `ForkAuthenticationRequest` | `ApiClient.post()` |
| `auth token revoke` | `DeleteUserRequest` | `ApiClient.delete()` |
| `auth tfa enable` | `UpdateUserTFA` | `ApiClient.post()` |
| `auth tfa disable` | `UpdateUserTFA` | `ApiClient.post()` |
| `auth tfa status` | `UpdateUserTFA` | `ApiClient.post()` |

#### Company (`company`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `company info` | `GetUserCompany` | Basic info |
| `company dashboard` | `GetCompanyDashboardJson` | Dashboard data |
| `company vault get` | `GetCompanyVault` | Encrypted |
| `company vault set` | `UpdateCompanyVault` | Requires vaultVersion |
| `company vault list` | `GetCompanyVaults` | All vault types |
| `company export` | `ExportCompanyData` | Full export |
| `company import` | `ImportCompanyData` | With mode flag |
| `company block-requests` | `UpdateCompanyBlockUserRequests` | Security feature |

#### Users (`user`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `user list` | `GetCompanyUsers` | All users |
| `user create` | `CreateNewUser` | Protected, returns activation code |
| `user activate` | `ActivateUserAccount` | Protected |
| `user deactivate` | `UpdateUserToDeactivated` | Soft delete |
| `user exists` | `IsRegistered` | Check existence |
| `user email change` | `UpdateUserEmail` | Change email |
| `user password change` | `UpdateUserPassword` | Protected |
| `user language set` | `UpdateUserLanguage` | Set preference |
| `user vault get` | `GetUserVault` | User's vault |
| `user vault set` | `UpdateUserVault` | Update vault |
| `user permission assign` | `UpdateUserAssignedPermissions` | Assign group |

#### Teams (`team`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `team list` | `GetCompanyTeams` | All teams |
| `team create` | `CreateTeam` | With vault |
| `team rename` | `UpdateTeamName` | Change name |
| `team delete` | `DeleteTeam` | Remove team |
| `team vault get` | `GetCompanyVaults` | Filter by team |
| `team vault set` | `UpdateTeamVault` | Requires vaultVersion |
| `team member list` | `GetTeamMembers` | Team members |
| `team member add` | `CreateTeamMembership` | Add user |
| `team member remove` | `DeleteUserFromTeam` | Remove user |

#### Regions (`region`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `region list` | `GetCompanyRegions` | All regions |
| `region create` | `CreateRegion` | With vault |
| `region rename` | `UpdateRegionName` | Change name |
| `region delete` | `DeleteRegion` | Remove region |
| `region vault get` | (via GetCompanyVaults) | Filter by region |
| `region vault set` | `UpdateRegionVault` | Requires vaultVersion |

#### Bridges (`bridge`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `bridge list` | `GetRegionBridges` | Requires --region |
| `bridge create` | `CreateBridge` | Requires --region |
| `bridge rename` | `UpdateBridgeName` | Requires --region |
| `bridge delete` | `DeleteBridge` | Requires --region |
| `bridge vault get` | (via GetCompanyVaults) | Filter |
| `bridge vault set` | `UpdateBridgeVault` | Requires --region, vaultVersion |
| `bridge reset-auth` | `ResetBridgeAuthorization` | Reset token |

#### Machines (`machine`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `machine list` | `GetTeamMachines` | Uses context team |
| `machine create` | `CreateMachine` | Requires --team, --bridge |
| `machine rename` | `UpdateMachineName` | Change name |
| `machine delete` | `DeleteMachine` | Remove machine |
| `machine vault get` | (via GetCompanyVaults) | Filter |
| `machine vault set` | `UpdateMachineVault` | Requires vaultVersion |
| `machine status` | `UpdateMachineStatus` | Get/set status |
| `machine assign-bridge` | `UpdateMachineAssignedBridge` | Change bridge |
| `machine assign-cluster` | `UpdateMachineClusterAssignment` | Assign to cluster |
| `machine remove-cluster` | `UpdateMachineClusterRemoval` | Remove from cluster |
| `machine assign-storage` | `UpdateMachineDistributedStorage` | Assign storage |

#### Storage (`storage`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `storage list` | `GetTeamStorages` | Uses context team |
| `storage create` | `CreateStorage` | With vault |
| `storage rename` | `UpdateStorageName` | Change name |
| `storage delete` | `DeleteStorage` | Remove storage |
| `storage vault get` | (via GetCompanyVaults) | Filter |
| `storage vault set` | `UpdateStorageVault` | Requires vaultVersion |

#### Repositories (`repo`)

| CLI Command | API Endpoint | Notes |
|-------------|--------------|-------|
| `repo list` | `GetTeamRepositories` | Uses context team |
| `repo create` | `CreateRepository` | With --parent, --tag |
| `repo rename` | `UpdateRepositoryName` | Change name |
| `repo delete` | `DeleteRepository` | Requires --tag |
| `repo vault get` | (via GetCompanyVaults) | Filter |
| `repo vault set` | `UpdateRepositoryVault` | Requires --tag, vaultVersion |
| `repo promote` | `PromoteRepositoryToGrand` | Promote to grand |

#### Queue (`queue`)

| CLI Command | API Endpoint | Core Service |
|-------------|--------------|--------------|
| `queue list` | `GetTeamQueueItems` | `extractTableData()` |
| `queue create` | `CreateQueueItem` | `QueueService.buildQueueVault()` |
| `queue trace` | `GetQueueItemTrace` | `extractTableData()` |
| `queue cancel` | `CancelQueueItem` | - |
| `queue retry` | `RetryFailedQueueItem` | - |
| `queue delete` | `DeleteQueueItem` | - |

#### Shortcuts

| CLI Command | Maps To |
|-------------|---------|
| `run <function>` | `queue create --function <function>` |
| `trace <taskId>` | `queue trace <taskId>` |
| `cancel <taskId>` | `queue cancel <taskId>` |
| `retry <taskId>` | `queue retry <taskId>` |
| `login` | `auth login` |
| `logout` | `auth logout` |

#### Permissions (`permission`)

| CLI Command | API Endpoint |
|-------------|--------------|
| `permission group list` | `GetCompanyPermissionGroups` |
| `permission group create` | `CreatePermissionGroup` |
| `permission group delete` | `DeletePermissionGroup` |
| `permission group show` | `GetPermissionGroupDetails` |
| `permission add` | `CreatePermissionInGroup` |
| `permission remove` | `DeletePermissionFromGroup` |

#### Distributed Storage (`ds`)

| CLI Command | API Endpoint |
|-------------|--------------|
| `ds cluster list` | `GetDistributedStorageClusters` |
| `ds cluster create` | `CreateDistributedStorageCluster` |
| `ds cluster delete` | `DeleteDistributedStorageCluster` |
| `ds cluster vault get/set` | `UpdateDistributedStorageClusterVault` |
| `ds cluster machine list` | `GetDistributedStorageClusterMachines` |
| `ds pool list` | `GetDistributedStoragePools` |
| `ds pool create` | `CreateDistributedStoragePool` |
| `ds pool delete` | `DeleteDistributedStoragePool` |
| `ds pool vault get/set` | `UpdateDistributedStoragePoolVault` |
| `ds image list` | `GetDistributedStorageRbdImages` |
| `ds image create` | `CreateDistributedStorageRbdImage` |
| `ds image delete` | `DeleteDistributedStorageRbdImage` |
| `ds image assign-machine` | `UpdateImageMachineAssignment` |
| `ds snapshot list` | `GetDistributedStorageRbdSnapshots` |
| `ds snapshot create` | `CreateDistributedStorageRbdSnapshot` |
| `ds snapshot delete` | `DeleteDistributedStorageRbdSnapshot` |
| `ds clone list` | `GetDistributedStorageRbdClones` |
| `ds clone create` | `CreateDistributedStorageRbdClone` |
| `ds clone delete` | `DeleteDistributedStorageRbdClone` |
| `ds clone machine list` | `GetCloneMachines` |
| `ds clone machine assign` | `UpdateCloneMachineAssignments` |
| `ds clone machine remove` | `UpdateCloneMachineRemovals` |
| `ds clone machine available` | `GetAvailableMachinesForClone` |
| `ds clone machine validate` | `GetCloneMachineAssignmentValidation` |

#### Audit (`audit`)

| CLI Command | API Endpoint |
|-------------|--------------|
| `audit log` | `GetAuditLogs` |
| `audit trace` | `GetEntityAuditTrace` |
| `audit history` | `GetEntityHistory` |

#### Context (`context`)

| CLI Command | Storage | Notes |
|-------------|---------|-------|
| `context set <key> <value>` | `~/.rediacc/config.json` | team, region |
| `context show` | `~/.rediacc/config.json` | Display current |
| `context clear` | `~/.rediacc/config.json` | Clear one or all |

---

## Services

### API Service

**File:** `cli/src/services/api.ts`

**Purpose:** Wrapper around ApiClient for CLI usage

**Key Functions:**
- `initializeApi()` - Initialize client with stored token
- `callApi(endpoint, params)` - Generic API call with error handling
- `handleApiError(error)` - Format errors for CLI output

**Integration with Core:**
```typescript
import { ApiClient } from '../../api/client'
import { initializeApiClient } from '../../api/init'

const apiClient = new ApiClient()
await initializeApiClient()
```

### Auth Service

**File:** `cli/src/services/auth.ts`

**Purpose:** Authentication flow for CLI

**Key Functions:**
- `login(email, password, options)` - Interactive or non-interactive login
- `logout()` - Clear stored credentials
- `getStoredToken()` - Retrieve token from storage
- `isAuthenticated()` - Check auth status
- `handleTwoFactor(code)` - 2FA flow

**Token Storage:**
- Store encrypted token in `~/.rediacc/config.json`
- Handle token rotation from API responses

### Context Service

**File:** `cli/src/services/context.ts`

**Purpose:** Manage CLI context (defaults)

**Key Functions:**
- `setContext(key, value)` - Set team, region
- `getContext(key)` - Get current value
- `clearContext(key?)` - Clear one or all
- `applyContext(options)` - Merge context with command options

**Context Keys:**
- `team` - Default team name
- `region` - Default region name

**Priority:**
1. Explicit command flags (highest)
2. Context values
3. Required prompts (lowest)

### Output Service

**File:** `cli/src/services/output.ts`

**Purpose:** Format output for different modes

**Output Formats:**
- `table` - Human-readable tables (default)
- `json` - Machine-readable JSON
- `yaml` - YAML format
- `csv` - CSV export

**Key Functions:**
- `formatOutput(data, format)` - Main formatter
- `printTable(data, columns)` - Table output
- `printJson(data)` - JSON output
- `printError(error)` - Error formatting
- `printSuccess(message)` - Success message

---

## Authentication Flow

### Login Flow

```
1. User runs: rediacc login
2. Prompt for email (or use --email flag)
3. Prompt for password (hidden input)
4. Hash password using cryptoProvider.generateHash(password)
5. Call CreateAuthenticationRequest API
6. If 2FA enabled:
   a. Prompt for 2FA code
   b. Call PrivilegeAuthenticationRequest
7. Store encrypted token using cryptoService.encryptString()
8. Store master password (encrypted) for vault operations
9. Display success message
```

### Token Rotation

```
1. API response includes nextRequestToken
2. API client interceptor detects rotation
3. Update stored token automatically
4. No user action required
```

### Master Password

```
1. Required for vault encryption/decryption
2. Prompt on first vault operation
3. Store encrypted in ~/.rediacc/config.json
4. Use for CryptoService initialization
```

---

## Queue Operations

### Using Core QueueService

```typescript
import { QueueService, QueueRequestContext } from '../../core'

// Initialize with CLI notification handler
const queueService = new QueueService({
  emitNotification: (notification) => {
    if (notification.level === 'error') {
      console.error(chalk.red(notification.message))
    } else {
      console.log(notification.message)
    }
  },
  emitMonitoringEvent: (event) => {
    // Optional: track in CLI
  }
})
```

### Building Queue Vault

```typescript
const context: QueueRequestContext = {
  teamName: options.team || getContext('team'),
  machineName: options.machine,
  bridgeName: options.bridge,
  functionName: options.function,
  params: parseParams(options.param), // --param key=value
  priority: options.priority || 3,
  description: `CLI: ${options.function}`,
  addedVia: 'CLI',
  teamVault: await fetchTeamVault(teamName),
  machineVault: await fetchMachineVault(machineName),
  companyVault: await fetchCompanyVault(),
}

const queueVault = await queueService.buildQueueVault(context)
```

### Creating Queue Item

```typescript
const response = await apiClient.post('/CreateQueueItem', {
  teamName: context.teamName,
  machineName: context.machineName,
  bridgeName: context.bridgeName,
  queueVault: queueVault, // Minified JSON string
  priority: context.priority
})

const taskId = getFirstRow(response, 1)?.taskId
console.log(`Task created: ${taskId}`)
```

### Required Vaults for Queue Context

The `QueueService.buildQueueVault()` handles all internal structure construction. The CLI just needs to fetch and provide the required vaults:

```typescript
// Fetch vaults based on function requirements
const companyVault = await fetchCompanyVault()     // Always needed
const teamVault = await fetchTeamVault(teamName)   // For SSH keys
const machineVault = await fetchMachineVault(machineName)  // If function requires machine
const repositoryVault = await fetchRepositoryVault(repoGuid)  // If function requires repo
```

The core service automatically:
- Extracts required fields from each vault
- Ensures SSH keys are base64 encoded
- Builds GENERAL_SETTINGS with user identity (UNIVERSAL_USER_ID, etc.)
- Constructs MACHINES, STORAGE_SYSTEMS, REPO_CREDENTIALS as needed

### Tracing Queue Item

```typescript
const response = await apiClient.get('/GetQueueItemTrace', { taskId })
const trace = extractTableData(response, 0)

// Display status, progress, console output
// Optional: --watch flag for polling
```

---

## Error Handling

### API Errors

```typescript
try {
  const response = await apiClient.post(endpoint, data)
  if (response.failure) {
    throw new ApiError(response.message, {
      status: response.status,
      details: response.errors
    })
  }
  return response
} catch (error) {
  if (error instanceof ApiError) {
    printError(error.message)
    if (error.details) {
      console.error(chalk.dim(JSON.stringify(error.details, null, 2)))
    }
  } else {
    printError('Network error: ' + error.message)
  }
  process.exit(1)
}
```

### Validation Errors

```typescript
import { teamNameSchema } from '../../core'

const result = teamNameSchema.safeParse(teamName)
if (!result.success) {
  printError(`Invalid team name: ${result.error.message}`)
  process.exit(1)
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Authentication required |
| 4 | Permission denied |
| 5 | Resource not found |
| 6 | Network error |

---

## Configuration

### Config File Location

- **Linux/macOS:** `~/.rediacc/config.json`
- **Windows:** `%USERPROFILE%\.rediacc\config.json`

### Config Structure

```json
{
  "version": 1,
  "apiUrl": "https://api.rediacc.com",
  "token": "encrypted:base64...",
  "masterPassword": "encrypted:base64...",
  "context": {
    "team": "Default",
    "region": "us-east"
  },
  "output": {
    "format": "table",
    "color": true
  },
  "aliases": {
    "deploy": "run deploy",
    "backup": "run backup"
  }
}
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `REDIACC_API_URL` | API endpoint | From config |
| `REDIACC_TOKEN` | Auth token | From config |
| `REDIACC_TEAM` | Default team | From context |
| `REDIACC_REGION` | Default region | From context |
| `REDIACC_OUTPUT` | Output format | table |
| `REDIACC_NO_COLOR` | Disable colors | false |

### API URL Structure

The system API URL is constructed as `${baseUrl}/api` where `baseUrl` is the origin (e.g., `https://api.rediacc.com`).

API calls are made to: `${REDIACC_API_URL}/StoredProcedure/{endpoint}`

Example: `https://api.rediacc.com/api/StoredProcedure/GetTeamRepositories`

---

## Dependencies

### Production Dependencies

```json
{
  "commander": "^12.x",           // CLI framework
  "chalk": "^5.x",                // Terminal colors
  "ora": "^8.x",                  // Spinners
  "inquirer": "^9.x",             // Interactive prompts
  "cli-table3": "^0.6.x",         // Table formatting
  "yaml": "^2.x",                 // YAML output
  "axios": "^1.x",                // HTTP client (from core)
  "zod": "^3.x"                   // Validation (from core)
}
```

### Dev Dependencies

```json
{
  "typescript": "^5.x",
  "@types/node": "^20.x",
  "vitest": "^1.x",               // Testing
  "tsx": "^4.x",                  // TypeScript execution
  "pkg": "^5.x"                   // Binary packaging (optional)
}
```

---

## Testing Strategy

### Unit Tests

**Location:** `cli/src/__tests__/`

**Test Files:**
- `adapters/storage.test.ts` - File storage operations
- `adapters/crypto.test.ts` - Encryption/decryption
- `services/auth.test.ts` - Authentication flow
- `services/context.test.ts` - Context management
- `commands/*.test.ts` - Command logic

**Mocking:**
- Mock `ApiClient` for API tests
- Mock file system for storage tests
- Use `vitest` for test runner

### Integration Tests

**Purpose:** Test full command flows

**Approach:**
- Create test account/data
- Run actual commands
- Verify API calls and output

### Manual Testing

**Checklist:**
- [ ] Login flow (email/password)
- [ ] Login flow with 2FA
- [ ] Token rotation
- [ ] Context set/show/clear
- [ ] All resource CRUD operations
- [ ] Queue create with `run`
- [ ] Queue trace with `--watch`
- [ ] Output formats (table/json/yaml)
- [ ] Error handling
- [ ] Help text for all commands

---

## Build & Distribution

### Build Process

```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Create executable
npm run package
```

### Package Scripts

```json
{
  "scripts": {
    "build": "tsc",
    "dev": "tsx src/index.ts",
    "test": "vitest",
    "package": "pkg . --targets node18-linux,node18-macos,node18-win"
  }
}
```

### Distribution

**npm Package:**
```bash
npm publish
# Users install with: npm install -g @rediacc/cli
```

**Standalone Binary:**
- Linux: `rediacc-linux`
- macOS: `rediacc-macos`
- Windows: `rediacc-win.exe`

---

## Implementation Phases

### Phase 1: Foundation

1. Set up CLI project structure
2. Implement Node adapters (storage, crypto)
3. Create API service wrapper
4. Implement auth commands (login/logout)
5. Implement context commands
6. Basic output formatting

### Phase 2: Core Resources

1. Implement team commands
2. Implement machine commands
3. Implement storage commands
4. Implement repo commands
5. Add validation using Zod schemas

### Phase 3: Queue Operations

1. Implement queue commands
2. Implement shortcuts (run/trace/cancel)
3. Integrate QueueService from core
4. Add watch mode for trace

### Phase 4: Infrastructure

1. Implement region commands
2. Implement bridge commands
3. Implement user commands
4. Implement company commands

### Phase 5: Advanced Features

1. Implement distributed storage (ds) commands
2. Implement permission commands
3. Implement audit commands
4. Add aliases support

### Phase 6: Polish

1. Comprehensive testing
2. Documentation
3. Error message improvements
4. Performance optimization
5. Binary packaging

---

## Example Command Implementations

### Login Command

**File:** `cli/src/commands/auth.ts`

```typescript
// Pseudo-code structure
export const authCommands = {
  login: {
    description: 'Authenticate with Rediacc',
    options: [
      { flag: '--email <email>', description: 'Email address' },
      { flag: '--name <name>', description: 'Session name' },
      { flag: '--expires <hours>', description: 'Token expiration' }
    ],
    action: async (options) => {
      // 1. Get email (prompt if not provided)
      // 2. Get password (always prompt, hidden)
      // 3. Hash password using cryptoProvider.generateHash()
      // 4. Call API
      // 5. Handle 2FA if needed
      // 6. Store token using cryptoService.encryptString()
      // 7. Display success
    }
  }
}
```

### Run Command (Shortcut)

**File:** `cli/src/commands/shortcuts.ts`

```typescript
// Pseudo-code structure
export const runCommand = {
  command: 'run <function>',
  description: 'Create a queue item and run a function',
  options: [
    { flag: '--machine <name>', description: 'Target machine' },
    { flag: '--team <name>', description: 'Team name' },
    { flag: '--bridge <name>', description: 'Bridge name' },
    { flag: '--priority <1-5>', description: 'Priority level' },
    { flag: '--param <key=value>', description: 'Function parameter', multiple: true }
  ],
  action: async (functionName, options) => {
    // 1. Apply context defaults
    // 2. Validate function exists
    // 3. Fetch required vaults
    // 4. Build queue vault using QueueService
    // 5. Create queue item
    // 6. Display task ID
    // 7. Optionally start tracing
  }
}
```

### Team List Command

**File:** `cli/src/commands/team.ts`

```typescript
// Pseudo-code structure
export const teamCommands = {
  list: {
    description: 'List all teams',
    options: [
      { flag: '--output <format>', description: 'Output format' }
    ],
    action: async (options) => {
      // 1. Call GetCompanyTeams API
      // 2. Extract table data
      // 3. Format output based on --output flag
      // 4. Display result
    }
  }
}
```

---

## Future Enhancements

### Potential Features

1. **Shell Completion** - Bash/Zsh/Fish completions
2. **Plugin System** - Custom command extensions
3. **Profile Management** - Multiple accounts
4. **Offline Mode** - Queue commands for later execution
5. **Interactive Mode** - REPL-style interface
6. **Web Dashboard Link** - Open console in browser
7. **Update Checker** - Notify of new versions

### Performance Optimizations

1. **Lazy Loading** - Load commands on demand
2. **Response Caching** - Cache frequently accessed data
3. **Parallel Requests** - Batch API calls where possible
4. **Binary Size** - Tree-shake unused code

---

## References

### Core Files to Study

- `src/core/services/queue.ts` - QueueService implementation
- `src/core/types/queue.ts` - Queue type definitions
- `src/core/api/response.ts` - API response helpers
- `src/api/client.ts` - ApiClient implementation
- `src/adapters/crypto.ts` - WebCryptoProvider (reference for Node adapter)
- `src/adapters/storage.ts` - WebStorageAdapter (reference for Node adapter)

### API Endpoints

- See middleware stored procedures in `middleware/scripts/procedures/`
- API whitelist in `middleware/Service/StoredProcedureController.cs`

### Existing CLI (Python)

- Located in `cli-1/` (different implementation, for reference only)
- Do not copy code, but can reference UX patterns

---

## Success Criteria

### Functional Requirements

- [ ] All 98 API endpoints accessible via CLI
- [ ] Core QueueService fully integrated
- [ ] Encryption compatible with web console
- [ ] Context system reduces command verbosity
- [ ] All output formats working (table/json/yaml/csv)

### Non-Functional Requirements

- [ ] Response time < 500ms for simple commands
- [ ] Binary size < 50MB
- [ ] Works offline for help/version
- [ ] Clear error messages with suggestions
- [ ] Consistent command patterns

### Quality Requirements

- [ ] 80%+ test coverage
- [ ] No TypeScript errors
- [ ] ESLint passing
- [ ] Documentation complete
- [ ] Examples for all commands

---

*This document serves as the comprehensive implementation guide for the Rediacc CLI. Update as implementation progresses.*

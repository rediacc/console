/**
 * Parser Module Exports
 */

// Base utilities
export {
  extractRowsByIndex,
  extractFirstByIndex,
  extractPrimaryOrSecondary,
  toBoolean,
  safeJsonParse,
} from './base';

// Parser types
export type { ListParser, SingleParser, CompositeParser, ParserOptions } from './types';

// Teams
export {
  parseGetOrganizationTeams,
  parseGetTeamMembers,
  parseTeamList,
  parseTeamMembers,
} from './teams';

// Machines
export {
  parseGetTeamMachines,
  parseCreateMachine,
  parseMachineList,
} from './machines';

// Queue
export type { QueueCreateResult } from './queue';
export {
  parseGetTeamQueueItems,
  parseGetQueueItemsNext,
  parseCreateQueueItem,
  parseGetQueueItemTrace,
  parseQueueList,
  parseQueueTrace,
} from './queue';

// Auth
export {
  parseGetRequestAuthenticationStatus,
  parseCreateAuthenticationRequest,
  parseUpdateUserTFA,
  parsePrivilegeAuthenticationRequest,
  parseForkAuthenticationRequest,
  parseGetUserRequests,
  parseIsRegistered,
  parseAuthStatus,
  parseLoginResult,
  parseTfaVerification,
} from './auth';

// Ceph
export {
  parseGetCephClusters,
  parseGetCephClusterMachines,
  parseGetCephPools,
  parseGetCephRbdImages,
  parseGetCephRbdSnapshots,
  parseGetCephRbdClones,
  parseGetMachineAssignmentStatus,
  parseGetAvailableMachinesForClone,
  parseGetCloneMachineAssignmentValidation,
  parseGetCloneMachines,
  parseClusters,
  parsePools,
  parseImages,
  parseSnapshots,
  parseClones,
} from './ceph';

// Organization
export {
  parseGetOrganizationDashboard,
  parseOrganizationInfo,
  parseGetOrganizationVault,
  parseGetOrganizationVaults,
  parseDashboard,
  parseOrganizationVault,
} from './organization';

// Audit
export {
  parseGetAuditLogs,
  parseGetEntityAuditTrace,
  parseAuditLogs,
  parseEntityTrace,
} from './audit';

// Permissions
export type {
  PermissionGroupWithPermissions,
  PermissionGroupWithPermissions as PermissionGroupWithParsedPermissions,
} from './permissions';
export {
  parseGetOrganizationPermissionGroups,
  parseGetPermissionGroupDetails,
  parsePermissionGroups,
  parsePermissionDetails,
} from './permissions';

// Repositories
export type { NormalizedRepository } from './repositories';
export {
  parseGetTeamRepositories,
  parseCreateRepository,
  parseRepositoryList,
} from './repositories';

// Resources (Bridges, Regions, Storage)
export {
  parseGetOrganizationRegions,
  parseGetRegionBridges,
  parseCreateBridge,
  parseGetTeamStorages,
  parseCreateStorage,
  parseRegionList,
  parseBridgeList,
  parseStorageList,
} from './resources';

// Users
export {
  parseGetOrganizationUsers,
  parseCreateUser,
  parseUserList,
} from './users';

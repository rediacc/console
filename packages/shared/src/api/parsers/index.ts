/**
 * Parser Module Exports
 */

// Audit
export {
  parseAuditLogs,
  parseEntityTrace,
  parseGetAuditLogs,
  parseGetEntityAuditTrace,
} from './audit';
// Auth
export {
  parseAuthStatus,
  parseCreateAuthenticationRequest,
  parseForkAuthenticationRequest,
  parseGetRequestAuthenticationStatus,
  parseGetUserRequests,
  parseIsRegistered,
  parseLoginResult,
  parsePrivilegeAuthenticationRequest,
  parseTfaVerification,
  parseUpdateUserTFA,
} from './auth';
// Base utilities
export {
  extractFirstByIndex,
  extractPrimaryOrSecondary,
  extractRowsByIndex,
  safeJsonParse,
  toBoolean,
} from './base';
// Ceph
export {
  parseClones,
  parseClusters,
  parseGetAvailableMachinesForClone,
  parseGetCephClusterMachines,
  parseGetCephClusters,
  parseGetCephPools,
  parseGetCephRbdClones,
  parseGetCephRbdImages,
  parseGetCephRbdSnapshots,
  parseGetCloneMachineAssignmentValidation,
  parseGetCloneMachines,
  parseGetMachineAssignmentStatus,
  parseImages,
  parsePools,
  parseSnapshots,
} from './ceph';
// Machines
export {
  parseCreateMachine,
  parseGetTeamMachines,
  parseMachineList,
} from './machines';
// Organization
export {
  parseDashboard,
  parseGetOrganizationDashboard,
  parseGetOrganizationVault,
  parseGetOrganizationVaults,
  parseOrganizationInfo,
  parseOrganizationVault,
} from './organization';
// Permissions
export type {
  PermissionGroupWithPermissions,
  PermissionGroupWithPermissions as PermissionGroupWithParsedPermissions,
} from './permissions';
export {
  parseGetOrganizationPermissionGroups,
  parseGetPermissionGroupDetails,
  parsePermissionDetails,
  parsePermissionGroups,
} from './permissions';
// Queue
export type { QueueCreateResult } from './queue';
export {
  parseCreateQueueItem,
  parseGetQueueItemsNext,
  parseGetQueueItemTrace,
  parseGetTeamQueueItems,
  parseQueueList,
  parseQueueTrace,
} from './queue';
// Repositories
export type { NormalizedRepository } from './repositories';
export {
  parseCreateRepository,
  parseGetTeamRepositories,
  parseRepositoryList,
} from './repositories';
// Resources (Bridges, Regions, Storage)
export {
  parseBridgeList,
  parseCreateBridge,
  parseCreateStorage,
  parseGetOrganizationRegions,
  parseGetRegionBridges,
  parseGetTeamStorages,
  parseRegionList,
  parseStorageList,
} from './resources';
// Teams
export {
  parseGetOrganizationTeams,
  parseGetTeamMembers,
  parseTeamList,
  parseTeamMembers,
} from './teams';
// Parser types
export type { CompositeParser, ListParser, ParserOptions, SingleParser } from './types';

// Users
export {
  parseCreateUser,
  parseGetOrganizationUsers,
  parseUserList,
} from './users';

/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: middleware/AppData/stored-procedures.json
 * Generated at: 2025-12-07T07:11:38Z
 * Schema version: 2.0.0
 * Schema generated: 2025-12-06T10:41:55Z
 *
 * To regenerate, run: ./go deploy prep
 * Or directly: ./_scripts/console-schema.sh --generate
 *
 * This file provides compile-time type safety for API calls by ensuring
 * parameter names and types match the middleware's expected schema.
 */

/* eslint-disable @typescript-eslint/no-empty-object-type */

// ============================================================================
// Procedure Parameter Interfaces
// ============================================================================

export interface ActivateUserAccountParams {
  /** @sqlType char */
  activationCode: string;
}

export interface CancelQueueItemParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
}

export interface CreateAuthenticationRequestParams {
  /** @sqlType nvarchar */
  name: string;
  /** @sqlType nvarchar */
  tFACode: string;
  /** @sqlType nvarchar */
  requestedPermissions: string;
  /** @sqlType int */
  tokenExpirationHours: number;
  /** @sqlType nvarchar */
  target: string;
}

export interface CreateBridgeParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateCephClusterParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateCephPoolParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateCephRbdCloneParams {
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  cloneName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateCephRbdImageParams {
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType nvarchar */
  machineName: string;
}

export interface CreateCephRbdSnapshotParams {
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateMachineParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateNewCompanyParams {
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType char */
  activationCode: string;
  /** @sqlType nvarchar */
  subscriptionPlan: string;
  /** @sqlType nvarchar */
  companyVaultDefaults: string;
  /** @sqlType nvarchar */
  languagePreference: string;
  /** @sqlType nvarchar */
  sshPrivateKeyB64: string;
  /** @sqlType nvarchar */
  sshPublicKeyB64: string;
}

export interface CreateNewUserParams {
  /** @sqlType nvarchar */
  newUserEmail: string;
  /** @sqlType binary */
  newUserHash: string;
  /** @sqlType char */
  activationCode: string;
  /** @sqlType nvarchar */
  languagePreference: string;
}

export interface CreatePermissionGroupParams {
  /** @sqlType nvarchar */
  permissionGroupName: string;
}

export interface CreatePermissionInGroupParams {
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType nvarchar */
  permissionName: string;
}

export interface CreateQueueItemParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  priority: number;
}

export interface CreateRegionParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateRepositoryParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repoName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType nvarchar */
  parentRepoName: string;
  /** @sqlType uniqueidentifier */
  repoGuid: string;
  /** @sqlType nvarchar */
  networkMode: string;
  /** @sqlType nvarchar */
  repoTag: string;
}

export interface CreateStorageParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  storageName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateTeamParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface CreateTeamMembershipParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  newUserEmail: string;
}

export interface DeleteBridgeParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
}

export interface DeleteCephClusterParams {
  /** @sqlType nvarchar */
  clusterName: string;
}

export interface DeleteCephPoolParams {
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface DeleteCephRbdCloneParams {
  /** @sqlType nvarchar */
  cloneName: string;
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface DeleteCephRbdImageParams {
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface DeleteCephRbdSnapshotParams {
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface DeleteMachineParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
}

export interface DeletePermissionFromGroupParams {
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType nvarchar */
  permissionName: string;
}

export interface DeletePermissionGroupParams {
  /** @sqlType nvarchar */
  permissionGroupName: string;
}

export interface DeleteQueueItemParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
}

export interface DeleteRegionParams {
  /** @sqlType nvarchar */
  regionName: string;
}

export interface DeleteRepositoryParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repoName: string;
  /** @sqlType nvarchar */
  repoTag: string;
}

export interface DeleteStorageParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  storageName: string;
}

export interface DeleteTeamParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export interface DeleteUserFromTeamParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  removeUserEmail: string;
}

export interface DeleteUserRequestParams {
  /** @sqlType int */
  targetRequestId: number;
}

export type ExportCompanyDataParams = Record<string, never>;

export interface ForkAuthenticationRequestParams {
  /** @sqlType nvarchar */
  childName: string;
  /** @sqlType int */
  tokenExpirationHours: number;
}

export interface GetAuditLogsParams {
  /** @sqlType datetime2 */
  startDate: string;
  /** @sqlType datetime2 */
  endDate: string;
  /** @sqlType nvarchar */
  entityFilter: string;
  /** @sqlType int */
  maxRecords: number;
}

export interface GetAvailableMachinesForCloneParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetCephClusterMachinesParams {
  /** @sqlType nvarchar */
  clusterName: string;
}

export type GetCephClustersParams = Record<string, never>;

export interface GetCephPoolsParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  clusterName: string;
}

export interface GetCephRbdClonesParams {
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetCephRbdImagesParams {
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetCephRbdSnapshotsParams {
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetCloneMachineAssignmentValidationParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineNames: string;
}

export interface GetCloneMachinesParams {
  /** @sqlType nvarchar */
  cloneName: string;
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export type GetCompanyDashboardJsonParams = Record<string, never>;

export type GetCompanyDataGraphJsonParams = Record<string, never>;

export type GetCompanyPermissionGroupsParams = Record<string, never>;

export type GetCompanyRegionsParams = Record<string, never>;

export type GetCompanyTeamsParams = Record<string, never>;

export type GetCompanyUsersParams = Record<string, never>;

export type GetCompanyVaultParams = Record<string, never>;

export type GetCompanyVaultsParams = Record<string, never>;

export interface GetEntityAuditTraceParams {
  /** @sqlType nvarchar */
  entityType: string;
  /** @sqlType nvarchar */
  entityIdentifier: string;
}

export interface GetEntityHistoryParams {
  /** @sqlType nvarchar */
  entity: string;
  /** @sqlType uniqueidentifier */
  credential: string;
  /** @sqlType int */
  maxRecords: number;
}

export interface GetLookupDataParams {
  /** @sqlType nvarchar */
  context: string;
}

export interface GetMachineAssignmentStatusParams {
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetPermissionGroupDetailsParams {
  /** @sqlType nvarchar */
  permissionGroupName: string;
}

export interface GetQueueItemTraceParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
}

export interface GetQueueItemsNextParams {
  /** @sqlType uniqueidentifier */
  bridgeCredential: string;
  /** @sqlType int */
  itemCount: number;
}

export interface GetRegionBridgesParams {
  /** @sqlType nvarchar */
  regionName: string;
}

export type GetRequestAuthenticationStatusParams = Record<string, never>;

export interface GetSystemConfigurationParams {
  /** @sqlType nvarchar */
  configKey: string;
}

export interface GetTeamMachinesParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetTeamMembersParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetTeamQueueItemsParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType int */
  priority: number;
  /** @sqlType int */
  minPriority: number;
  /** @sqlType int */
  maxPriority: number;
  /** @sqlType datetime2 */
  dateFrom: string;
  /** @sqlType datetime2 */
  dateTo: string;
  /** @sqlType uniqueidentifier */
  taskId: string;
  /** @sqlType bit */
  includeCompleted: boolean;
  /** @sqlType bit */
  includeCancelled: boolean;
  /** @sqlType bit */
  onlyStale: boolean;
  /** @sqlType int */
  staleThresholdMinutes: number;
  /** @sqlType int */
  maxRecords: number;
  /** @sqlType nvarchar */
  createdByUserEmail: string;
}

export interface GetTeamRepositoriesParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export interface GetTeamStoragesParams {
  /** @sqlType nvarchar */
  teamName: string;
}

export type GetUserCompanyParams = Record<string, never>;

export type GetUserRequestsParams = Record<string, never>;

export type GetUserVaultParams = Record<string, never>;

export interface ImportCompanyDataParams {
  /** @sqlType nvarchar */
  companyDataJson: string;
  /** @sqlType nvarchar */
  importMode: string;
}

export interface IsRegisteredParams {
  /** @sqlType nvarchar */
  userName: string;
}

export interface PrivilegeAuthenticationRequestParams {
  /** @sqlType nvarchar */
  tFACode: string;
}

export interface PromoteRepositoryToGrandParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repoName: string;
}

export interface ResetBridgeAuthorizationParams {
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType bit */
  isCloudManaged: boolean;
}

export interface RetryFailedQueueItemParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
}

export interface UpdateBridgeNameParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  currentBridgeName: string;
  /** @sqlType nvarchar */
  newBridgeName: string;
}

export interface UpdateBridgeVaultParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateCephClusterVaultParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateCephPoolVaultParams {
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateCloneMachineAssignmentsParams {
  /** @sqlType nvarchar */
  cloneName: string;
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineNames: string;
}

export interface UpdateCloneMachineRemovalsParams {
  /** @sqlType nvarchar */
  cloneName: string;
  /** @sqlType nvarchar */
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineNames: string;
}

export interface UpdateCompanyBlockUserRequestsParams {
  /** @sqlType bit */
  blockUserRequests: boolean;
}

export interface UpdateCompanyVaultParams {
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateCompanyVaultsParams {
  /** @sqlType nvarchar */
  updates: string;
}

export interface UpdateImageMachineAssignmentParams {
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  newMachineName: string;
}

export interface UpdateMachineAssignedBridgeParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  newBridgeName: string;
}

export interface UpdateMachineCephParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  clusterName: string;
}

export interface UpdateMachineClusterAssignmentParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface UpdateMachineClusterRemovalParams {
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export interface UpdateMachineNameParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  currentMachineName: string;
  /** @sqlType nvarchar */
  newMachineName: string;
}

export interface UpdateMachineStatusParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  machineStatus: string;
}

export interface UpdateMachineVaultParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateQueueItemResponseParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
  /** @sqlType nvarchar */
  vaultContent: string;
}

export interface UpdateQueueItemToCompletedParams {
  /** @sqlType uniqueidentifier */
  taskId: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType nvarchar */
  finalStatus: string;
}

export interface UpdateRegionNameParams {
  /** @sqlType nvarchar */
  currentRegionName: string;
  /** @sqlType nvarchar */
  newRegionName: string;
}

export interface UpdateRegionVaultParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateRepositoryNameParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  currentRepoName: string;
  /** @sqlType nvarchar */
  newRepoName: string;
}

export interface UpdateRepositoryTagParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repoName: string;
  /** @sqlType nvarchar */
  currentTag: string;
  /** @sqlType nvarchar */
  newTag: string;
}

export interface UpdateRepositoryVaultParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repoName: string;
  /** @sqlType nvarchar */
  repoTag: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateStorageNameParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  currentStorageName: string;
  /** @sqlType nvarchar */
  newStorageName: string;
}

export interface UpdateStorageVaultParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  storageName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateTeamNameParams {
  /** @sqlType nvarchar */
  currentTeamName: string;
  /** @sqlType nvarchar */
  newTeamName: string;
}

export interface UpdateTeamVaultParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateUserAssignedPermissionsParams {
  /** @sqlType nvarchar */
  userEmail: string;
  /** @sqlType nvarchar */
  permissionGroupName: string;
}

export interface UpdateUserEmailParams {
  /** @sqlType nvarchar */
  currentUserEmail: string;
  /** @sqlType nvarchar */
  newUserEmail: string;
}

export interface UpdateUserLanguageParams {
  /** @sqlType nvarchar */
  preferredLanguage: string;
}

export interface UpdateUserPasswordParams {
  /** @sqlType binary */
  userNewPass: string;
}

export interface UpdateUserTFAParams {
  /** @sqlType bit */
  enable: boolean;
  /** @sqlType binary */
  userHash: string;
  /** @sqlType nvarchar */
  currentCode: string;
  /** @sqlType bit */
  generateOnly: boolean;
  /** @sqlType nvarchar */
  verificationCode: string;
  /** @sqlType nvarchar */
  secret: string;
  /** @sqlType bit */
  confirmEnable: boolean;
}

export interface UpdateUserToActivatedParams {
  /** @sqlType nvarchar */
  userEmail: string;
}

export interface UpdateUserToDeactivatedParams {
  /** @sqlType nvarchar */
  userEmail: string;
}

export interface UpdateUserVaultParams {
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Union of all valid stored procedure names
 */
export type StoredProcedureName =
  | 'ActivateUserAccount'
  | 'CancelQueueItem'
  | 'CreateAuthenticationRequest'
  | 'CreateBridge'
  | 'CreateCephCluster'
  | 'CreateCephPool'
  | 'CreateCephRbdClone'
  | 'CreateCephRbdImage'
  | 'CreateCephRbdSnapshot'
  | 'CreateMachine'
  | 'CreateNewCompany'
  | 'CreateNewUser'
  | 'CreatePermissionGroup'
  | 'CreatePermissionInGroup'
  | 'CreateQueueItem'
  | 'CreateRegion'
  | 'CreateRepository'
  | 'CreateStorage'
  | 'CreateTeam'
  | 'CreateTeamMembership'
  | 'DeleteBridge'
  | 'DeleteCephCluster'
  | 'DeleteCephPool'
  | 'DeleteCephRbdClone'
  | 'DeleteCephRbdImage'
  | 'DeleteCephRbdSnapshot'
  | 'DeleteMachine'
  | 'DeletePermissionFromGroup'
  | 'DeletePermissionGroup'
  | 'DeleteQueueItem'
  | 'DeleteRegion'
  | 'DeleteRepository'
  | 'DeleteStorage'
  | 'DeleteTeam'
  | 'DeleteUserFromTeam'
  | 'DeleteUserRequest'
  | 'ExportCompanyData'
  | 'ForkAuthenticationRequest'
  | 'GetAuditLogs'
  | 'GetAvailableMachinesForClone'
  | 'GetCephClusterMachines'
  | 'GetCephClusters'
  | 'GetCephPools'
  | 'GetCephRbdClones'
  | 'GetCephRbdImages'
  | 'GetCephRbdSnapshots'
  | 'GetCloneMachineAssignmentValidation'
  | 'GetCloneMachines'
  | 'GetCompanyDashboardJson'
  | 'GetCompanyDataGraphJson'
  | 'GetCompanyPermissionGroups'
  | 'GetCompanyRegions'
  | 'GetCompanyTeams'
  | 'GetCompanyUsers'
  | 'GetCompanyVault'
  | 'GetCompanyVaults'
  | 'GetEntityAuditTrace'
  | 'GetEntityHistory'
  | 'GetLookupData'
  | 'GetMachineAssignmentStatus'
  | 'GetPermissionGroupDetails'
  | 'GetQueueItemTrace'
  | 'GetQueueItemsNext'
  | 'GetRegionBridges'
  | 'GetRequestAuthenticationStatus'
  | 'GetSystemConfiguration'
  | 'GetTeamMachines'
  | 'GetTeamMembers'
  | 'GetTeamQueueItems'
  | 'GetTeamRepositories'
  | 'GetTeamStorages'
  | 'GetUserCompany'
  | 'GetUserRequests'
  | 'GetUserVault'
  | 'ImportCompanyData'
  | 'IsRegistered'
  | 'PrivilegeAuthenticationRequest'
  | 'PromoteRepositoryToGrand'
  | 'ResetBridgeAuthorization'
  | 'RetryFailedQueueItem'
  | 'UpdateBridgeName'
  | 'UpdateBridgeVault'
  | 'UpdateCephClusterVault'
  | 'UpdateCephPoolVault'
  | 'UpdateCloneMachineAssignments'
  | 'UpdateCloneMachineRemovals'
  | 'UpdateCompanyBlockUserRequests'
  | 'UpdateCompanyVault'
  | 'UpdateCompanyVaults'
  | 'UpdateImageMachineAssignment'
  | 'UpdateMachineAssignedBridge'
  | 'UpdateMachineCeph'
  | 'UpdateMachineClusterAssignment'
  | 'UpdateMachineClusterRemoval'
  | 'UpdateMachineName'
  | 'UpdateMachineStatus'
  | 'UpdateMachineVault'
  | 'UpdateQueueItemResponse'
  | 'UpdateQueueItemToCompleted'
  | 'UpdateRegionName'
  | 'UpdateRegionVault'
  | 'UpdateRepositoryName'
  | 'UpdateRepositoryTag'
  | 'UpdateRepositoryVault'
  | 'UpdateStorageName'
  | 'UpdateStorageVault'
  | 'UpdateTeamName'
  | 'UpdateTeamVault'
  | 'UpdateUserAssignedPermissions'
  | 'UpdateUserEmail'
  | 'UpdateUserLanguage'
  | 'UpdateUserPassword'
  | 'UpdateUserTFA'
  | 'UpdateUserToActivated'
  | 'UpdateUserToDeactivated'
  | 'UpdateUserVault'
;

/**
 * Map of procedure names to their parameter types
 */
export interface ProcedureParamsMap {
  ActivateUserAccount: ActivateUserAccountParams;
  CancelQueueItem: CancelQueueItemParams;
  CreateAuthenticationRequest: CreateAuthenticationRequestParams;
  CreateBridge: CreateBridgeParams;
  CreateCephCluster: CreateCephClusterParams;
  CreateCephPool: CreateCephPoolParams;
  CreateCephRbdClone: CreateCephRbdCloneParams;
  CreateCephRbdImage: CreateCephRbdImageParams;
  CreateCephRbdSnapshot: CreateCephRbdSnapshotParams;
  CreateMachine: CreateMachineParams;
  CreateNewCompany: CreateNewCompanyParams;
  CreateNewUser: CreateNewUserParams;
  CreatePermissionGroup: CreatePermissionGroupParams;
  CreatePermissionInGroup: CreatePermissionInGroupParams;
  CreateQueueItem: CreateQueueItemParams;
  CreateRegion: CreateRegionParams;
  CreateRepository: CreateRepositoryParams;
  CreateStorage: CreateStorageParams;
  CreateTeam: CreateTeamParams;
  CreateTeamMembership: CreateTeamMembershipParams;
  DeleteBridge: DeleteBridgeParams;
  DeleteCephCluster: DeleteCephClusterParams;
  DeleteCephPool: DeleteCephPoolParams;
  DeleteCephRbdClone: DeleteCephRbdCloneParams;
  DeleteCephRbdImage: DeleteCephRbdImageParams;
  DeleteCephRbdSnapshot: DeleteCephRbdSnapshotParams;
  DeleteMachine: DeleteMachineParams;
  DeletePermissionFromGroup: DeletePermissionFromGroupParams;
  DeletePermissionGroup: DeletePermissionGroupParams;
  DeleteQueueItem: DeleteQueueItemParams;
  DeleteRegion: DeleteRegionParams;
  DeleteRepository: DeleteRepositoryParams;
  DeleteStorage: DeleteStorageParams;
  DeleteTeam: DeleteTeamParams;
  DeleteUserFromTeam: DeleteUserFromTeamParams;
  DeleteUserRequest: DeleteUserRequestParams;
  ExportCompanyData: ExportCompanyDataParams;
  ForkAuthenticationRequest: ForkAuthenticationRequestParams;
  GetAuditLogs: GetAuditLogsParams;
  GetAvailableMachinesForClone: GetAvailableMachinesForCloneParams;
  GetCephClusterMachines: GetCephClusterMachinesParams;
  GetCephClusters: GetCephClustersParams;
  GetCephPools: GetCephPoolsParams;
  GetCephRbdClones: GetCephRbdClonesParams;
  GetCephRbdImages: GetCephRbdImagesParams;
  GetCephRbdSnapshots: GetCephRbdSnapshotsParams;
  GetCloneMachineAssignmentValidation: GetCloneMachineAssignmentValidationParams;
  GetCloneMachines: GetCloneMachinesParams;
  GetCompanyDashboardJson: GetCompanyDashboardJsonParams;
  GetCompanyDataGraphJson: GetCompanyDataGraphJsonParams;
  GetCompanyPermissionGroups: GetCompanyPermissionGroupsParams;
  GetCompanyRegions: GetCompanyRegionsParams;
  GetCompanyTeams: GetCompanyTeamsParams;
  GetCompanyUsers: GetCompanyUsersParams;
  GetCompanyVault: GetCompanyVaultParams;
  GetCompanyVaults: GetCompanyVaultsParams;
  GetEntityAuditTrace: GetEntityAuditTraceParams;
  GetEntityHistory: GetEntityHistoryParams;
  GetLookupData: GetLookupDataParams;
  GetMachineAssignmentStatus: GetMachineAssignmentStatusParams;
  GetPermissionGroupDetails: GetPermissionGroupDetailsParams;
  GetQueueItemTrace: GetQueueItemTraceParams;
  GetQueueItemsNext: GetQueueItemsNextParams;
  GetRegionBridges: GetRegionBridgesParams;
  GetRequestAuthenticationStatus: GetRequestAuthenticationStatusParams;
  GetSystemConfiguration: GetSystemConfigurationParams;
  GetTeamMachines: GetTeamMachinesParams;
  GetTeamMembers: GetTeamMembersParams;
  GetTeamQueueItems: GetTeamQueueItemsParams;
  GetTeamRepositories: GetTeamRepositoriesParams;
  GetTeamStorages: GetTeamStoragesParams;
  GetUserCompany: GetUserCompanyParams;
  GetUserRequests: GetUserRequestsParams;
  GetUserVault: GetUserVaultParams;
  ImportCompanyData: ImportCompanyDataParams;
  IsRegistered: IsRegisteredParams;
  PrivilegeAuthenticationRequest: PrivilegeAuthenticationRequestParams;
  PromoteRepositoryToGrand: PromoteRepositoryToGrandParams;
  ResetBridgeAuthorization: ResetBridgeAuthorizationParams;
  RetryFailedQueueItem: RetryFailedQueueItemParams;
  UpdateBridgeName: UpdateBridgeNameParams;
  UpdateBridgeVault: UpdateBridgeVaultParams;
  UpdateCephClusterVault: UpdateCephClusterVaultParams;
  UpdateCephPoolVault: UpdateCephPoolVaultParams;
  UpdateCloneMachineAssignments: UpdateCloneMachineAssignmentsParams;
  UpdateCloneMachineRemovals: UpdateCloneMachineRemovalsParams;
  UpdateCompanyBlockUserRequests: UpdateCompanyBlockUserRequestsParams;
  UpdateCompanyVault: UpdateCompanyVaultParams;
  UpdateCompanyVaults: UpdateCompanyVaultsParams;
  UpdateImageMachineAssignment: UpdateImageMachineAssignmentParams;
  UpdateMachineAssignedBridge: UpdateMachineAssignedBridgeParams;
  UpdateMachineCeph: UpdateMachineCephParams;
  UpdateMachineClusterAssignment: UpdateMachineClusterAssignmentParams;
  UpdateMachineClusterRemoval: UpdateMachineClusterRemovalParams;
  UpdateMachineName: UpdateMachineNameParams;
  UpdateMachineStatus: UpdateMachineStatusParams;
  UpdateMachineVault: UpdateMachineVaultParams;
  UpdateQueueItemResponse: UpdateQueueItemResponseParams;
  UpdateQueueItemToCompleted: UpdateQueueItemToCompletedParams;
  UpdateRegionName: UpdateRegionNameParams;
  UpdateRegionVault: UpdateRegionVaultParams;
  UpdateRepositoryName: UpdateRepositoryNameParams;
  UpdateRepositoryTag: UpdateRepositoryTagParams;
  UpdateRepositoryVault: UpdateRepositoryVaultParams;
  UpdateStorageName: UpdateStorageNameParams;
  UpdateStorageVault: UpdateStorageVaultParams;
  UpdateTeamName: UpdateTeamNameParams;
  UpdateTeamVault: UpdateTeamVaultParams;
  UpdateUserAssignedPermissions: UpdateUserAssignedPermissionsParams;
  UpdateUserEmail: UpdateUserEmailParams;
  UpdateUserLanguage: UpdateUserLanguageParams;
  UpdateUserPassword: UpdateUserPasswordParams;
  UpdateUserTFA: UpdateUserTFAParams;
  UpdateUserToActivated: UpdateUserToActivatedParams;
  UpdateUserToDeactivated: UpdateUserToDeactivatedParams;
  UpdateUserVault: UpdateUserVaultParams;
}

/**
 * Map of procedure names to their prefix (Public/Protected)
 */
export interface ProcedurePrefixMap {
  ActivateUserAccount: 'Protected';
  CancelQueueItem: 'Public';
  CreateAuthenticationRequest: 'Protected';
  CreateBridge: 'Public';
  CreateCephCluster: 'Public';
  CreateCephPool: 'Public';
  CreateCephRbdClone: 'Public';
  CreateCephRbdImage: 'Public';
  CreateCephRbdSnapshot: 'Public';
  CreateMachine: 'Public';
  CreateNewCompany: 'Protected';
  CreateNewUser: 'Protected';
  CreatePermissionGroup: 'Public';
  CreatePermissionInGroup: 'Public';
  CreateQueueItem: 'Public';
  CreateRegion: 'Public';
  CreateRepository: 'Public';
  CreateStorage: 'Public';
  CreateTeam: 'Public';
  CreateTeamMembership: 'Public';
  DeleteBridge: 'Public';
  DeleteCephCluster: 'Public';
  DeleteCephPool: 'Public';
  DeleteCephRbdClone: 'Public';
  DeleteCephRbdImage: 'Public';
  DeleteCephRbdSnapshot: 'Public';
  DeleteMachine: 'Public';
  DeletePermissionFromGroup: 'Public';
  DeletePermissionGroup: 'Public';
  DeleteQueueItem: 'Public';
  DeleteRegion: 'Public';
  DeleteRepository: 'Public';
  DeleteStorage: 'Public';
  DeleteTeam: 'Public';
  DeleteUserFromTeam: 'Public';
  DeleteUserRequest: 'Public';
  ExportCompanyData: 'Public';
  ForkAuthenticationRequest: 'Public';
  GetAuditLogs: 'Public';
  GetAvailableMachinesForClone: 'Public';
  GetCephClusterMachines: 'Public';
  GetCephClusters: 'Public';
  GetCephPools: 'Public';
  GetCephRbdClones: 'Public';
  GetCephRbdImages: 'Public';
  GetCephRbdSnapshots: 'Public';
  GetCloneMachineAssignmentValidation: 'Public';
  GetCloneMachines: 'Public';
  GetCompanyDashboardJson: 'Public';
  GetCompanyDataGraphJson: 'Public';
  GetCompanyPermissionGroups: 'Public';
  GetCompanyRegions: 'Public';
  GetCompanyTeams: 'Public';
  GetCompanyUsers: 'Public';
  GetCompanyVault: 'Public';
  GetCompanyVaults: 'Public';
  GetEntityAuditTrace: 'Public';
  GetEntityHistory: 'Public';
  GetLookupData: 'Public';
  GetMachineAssignmentStatus: 'Public';
  GetPermissionGroupDetails: 'Public';
  GetQueueItemTrace: 'Public';
  GetQueueItemsNext: 'Protected';
  GetRegionBridges: 'Public';
  GetRequestAuthenticationStatus: 'Public';
  GetSystemConfiguration: 'Public';
  GetTeamMachines: 'Public';
  GetTeamMembers: 'Public';
  GetTeamQueueItems: 'Public';
  GetTeamRepositories: 'Public';
  GetTeamStorages: 'Public';
  GetUserCompany: 'Public';
  GetUserRequests: 'Public';
  GetUserVault: 'Public';
  ImportCompanyData: 'Public';
  IsRegistered: 'Protected';
  PrivilegeAuthenticationRequest: 'Public';
  PromoteRepositoryToGrand: 'Public';
  ResetBridgeAuthorization: 'Public';
  RetryFailedQueueItem: 'Public';
  UpdateBridgeName: 'Public';
  UpdateBridgeVault: 'Public';
  UpdateCephClusterVault: 'Public';
  UpdateCephPoolVault: 'Public';
  UpdateCloneMachineAssignments: 'Public';
  UpdateCloneMachineRemovals: 'Public';
  UpdateCompanyBlockUserRequests: 'Public';
  UpdateCompanyVault: 'Public';
  UpdateCompanyVaults: 'Public';
  UpdateImageMachineAssignment: 'Public';
  UpdateMachineAssignedBridge: 'Public';
  UpdateMachineCeph: 'Public';
  UpdateMachineClusterAssignment: 'Public';
  UpdateMachineClusterRemoval: 'Public';
  UpdateMachineName: 'Public';
  UpdateMachineStatus: 'Public';
  UpdateMachineVault: 'Public';
  UpdateQueueItemResponse: 'Public';
  UpdateQueueItemToCompleted: 'Public';
  UpdateRegionName: 'Public';
  UpdateRegionVault: 'Public';
  UpdateRepositoryName: 'Public';
  UpdateRepositoryTag: 'Public';
  UpdateRepositoryVault: 'Public';
  UpdateStorageName: 'Public';
  UpdateStorageVault: 'Public';
  UpdateTeamName: 'Public';
  UpdateTeamVault: 'Public';
  UpdateUserAssignedPermissions: 'Public';
  UpdateUserEmail: 'Public';
  UpdateUserLanguage: 'Public';
  UpdateUserPassword: 'Protected';
  UpdateUserTFA: 'Public';
  UpdateUserToActivated: 'Public';
  UpdateUserToDeactivated: 'Public';
  UpdateUserVault: 'Public';
}

/**
 * Get parameter type for a specific procedure
 */
export type ParamsFor<T extends StoredProcedureName> = ProcedureParamsMap[T];

/**
 * Helper to validate procedure parameters at compile time
 */
export function createProcedureParams<T extends StoredProcedureName>(
  _procedure: T,
  params: ProcedureParamsMap[T]
): ProcedureParamsMap[T] {
  return params;
}

// ============================================================================
// Schema Metadata
// ============================================================================

export const API_SCHEMA_METADATA = {
  version: '2.0.0',
  generated: '2025-12-06T10:41:55Z',
  procedureCount: 116,
} as const;

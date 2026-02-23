/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: middleware/AppData/stored-procedures.json
 * Generated at: 2026-01-19T19:58:17Z
 * Schema version: 3.0.0
 * Schema generated: 2026-01-19T19:58:11.2376335Z
 *
 * To regenerate, run: ./go deploy prep
 * Or directly: dotnet run -- --generate-types
 *
 * This file provides compile-time type safety for API calls by ensuring
 * parameter names and types match the middleware's expected schema.
 */

// ============================================================================
// Type-Safe API Base Types
// ============================================================================

/**
 * Result set interface for typed responses.
 * Local type alias matching ApiResultSet from api.ts for self-containment.
 * Not exported to avoid conflicts with the main ApiResultSet export.
 */
type ResultSet<T> = {
  data: T[];
  resultSetIndex?: number;
  resultSetName?: string;
};

/**
 * Base interface for typed API responses.
 * Used by generated TypedResponse interfaces for compile-time type safety.
 */
export interface ApiResponseBase {
  failure: number;
  errors: string[];
  message: string;
  resultSets: ResultSet<unknown>[];
  status?: number;
  isTFAEnabled?: boolean;
  isAuthorized?: boolean;
  authenticationStatus?: string;
  nextRequestToken?: string;
}

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
  tFACode?: string;
  /** @sqlType nvarchar */
  requestedPermissions?: string;
  /** @sqlType int */
  tokenExpirationHours?: number;
  /** @sqlType nvarchar */
  target?: string;
}

export interface CreateBridgeParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateCephClusterParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateCephPoolParams {
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
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
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
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
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateMachineParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateNewOrganizationParams {
  /** @sqlType nvarchar */
  organizationName: string;
  /** @sqlType char */
  activationCode: string;
  /** @sqlType nvarchar */
  subscriptionPlan?: string;
  /** @sqlType nvarchar */
  organizationVaultDefaults: string;
  /** @sqlType nvarchar */
  languagePreference?: string;
  /** @sqlType nvarchar */
  sshPrivateKeyB64?: string;
  /** @sqlType nvarchar */
  sshPublicKeyB64?: string;
}

export interface CreateNewUserParams {
  /** @sqlType nvarchar */
  newUserEmail: string;
  /** @sqlType binary */
  newUserHash: string;
  /** @sqlType nvarchar */
  languagePreference?: string;
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
  machineName?: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  priority?: number;
}

export interface CreateRegionParams {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateRepositoryParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repositoryName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
  /** @sqlType nvarchar */
  parentRepositoryName?: string;
  /** @sqlType uniqueidentifier */
  repositoryGuid?: string;
  /** @sqlType nvarchar */
  networkMode?: string;
  /** @sqlType nvarchar */
  repositoryTag?: string;
}

export interface CreateStorageParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  storageName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
}

export interface CreateTeamParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  vaultContent?: string;
  /** @sqlType int */
  vaultVersion?: number;
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
  repositoryName: string;
  /** @sqlType nvarchar */
  repositoryTag?: string;
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
  targetRequestId?: number;
}

export type ExportOrganizationDataParams = Record<string, never>;

export interface ForkAuthenticationRequestParams {
  /** @sqlType nvarchar */
  childName: string;
  /** @sqlType int */
  tokenExpirationHours?: number;
}

export interface GetAuditLogsParams {
  /** @sqlType datetime2 */
  startDate?: string;
  /** @sqlType datetime2 */
  endDate?: string;
  /** @sqlType nvarchar */
  entityFilter?: string;
  /** @sqlType int */
  maxRecords?: number;
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
  teamName?: string;
  /** @sqlType nvarchar */
  clusterName?: string;
}

export interface GetCephRbdClonesParams {
  /** @sqlType nvarchar */
  snapshotName?: string;
  /** @sqlType nvarchar */
  imageName?: string;
  /** @sqlType nvarchar */
  poolName?: string;
  /** @sqlType nvarchar */
  teamName?: string;
}

export interface GetCephRbdImagesParams {
  /** @sqlType nvarchar */
  poolName?: string;
  /** @sqlType nvarchar */
  teamName?: string;
}

export interface GetCephRbdSnapshotsParams {
  /** @sqlType nvarchar */
  imageName?: string;
  /** @sqlType nvarchar */
  poolName?: string;
  /** @sqlType nvarchar */
  teamName?: string;
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
  maxRecords?: number;
}

export interface GetLookupDataParams {
  /** @sqlType nvarchar */
  context?: string;
}

export interface GetMachineAssignmentStatusParams {
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
}

export type GetOrganizationDashboardParams = Record<string, never>;

export type GetOrganizationPermissionGroupsParams = Record<string, never>;

export type GetOrganizationRegionsParams = Record<string, never>;

export type GetOrganizationTeamsParams = Record<string, never>;

export type GetOrganizationUsersParams = Record<string, never>;

export type GetOrganizationVaultParams = Record<string, never>;

export type GetOrganizationVaultsParams = Record<string, never>;

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
  itemCount?: number;
}

export interface GetRegionBridgesParams {
  /** @sqlType nvarchar */
  regionName: string;
}

export type GetRequestAuthenticationStatusParams = Record<string, never>;

export interface GetSystemConfigurationParams {
  /** @sqlType nvarchar */
  configKey?: string;
}

export interface GetTeamMachinesParams {
  /** @sqlType nvarchar */
  teamName?: string;
}

export interface GetTeamMembersParams {
  /** @sqlType nvarchar */
  teamName?: string;
}

export interface GetTeamQueueItemsParams {
  /** @sqlType nvarchar */
  teamName?: string;
  /** @sqlType nvarchar */
  machineName?: string;
  /** @sqlType nvarchar */
  bridgeName?: string;
  /** @sqlType nvarchar */
  status?: string;
  /** @sqlType int */
  priority?: number;
  /** @sqlType int */
  minPriority?: number;
  /** @sqlType int */
  maxPriority?: number;
  /** @sqlType datetime2 */
  dateFrom?: string;
  /** @sqlType datetime2 */
  dateTo?: string;
  /** @sqlType uniqueidentifier */
  taskId?: string;
  /** @sqlType bit */
  includeCompleted?: boolean;
  /** @sqlType bit */
  includeCancelled?: boolean;
  /** @sqlType bit */
  onlyStale?: boolean;
  /** @sqlType int */
  staleThresholdMinutes?: number;
  /** @sqlType int */
  maxRecords?: number;
  /** @sqlType nvarchar */
  createdByUserEmail?: string;
}

export interface GetTeamRepositoriesParams {
  /** @sqlType nvarchar */
  teamName?: string;
}

export interface GetTeamStoragesParams {
  /** @sqlType nvarchar */
  teamName?: string;
}

export type GetUserOrganizationParams = Record<string, never>;

export type GetUserRequestsParams = Record<string, never>;

export type GetUserVaultParams = Record<string, never>;

export interface ImportOrganizationDataParams {
  /** @sqlType nvarchar */
  organizationDataJson: string;
  /** @sqlType nvarchar */
  importMode?: string;
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
  repositoryName: string;
}

export interface ResetBridgeAuthorizationParams {
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType bit */
  isCloudManaged?: boolean;
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
  clusterName?: string;
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

export interface UpdateOrganizationBlockUserRequestsParams {
  /** @sqlType bit */
  blockUserRequests: boolean;
}

export interface UpdateOrganizationVaultParams {
  /** @sqlType nvarchar */
  vaultContent: string;
  /** @sqlType int */
  vaultVersion: number;
}

export interface UpdateOrganizationVaultsParams {
  /** @sqlType nvarchar */
  updates: string;
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
  finalStatus?: string;
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
  currentRepositoryName: string;
  /** @sqlType nvarchar */
  newRepositoryName: string;
}

export interface UpdateRepositoryTagParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repositoryName: string;
  /** @sqlType nvarchar */
  currentTag: string;
  /** @sqlType nvarchar */
  newTag: string;
}

export interface UpdateRepositoryVaultParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repositoryName: string;
  /** @sqlType nvarchar */
  repositoryTag?: string;
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
  userHash?: string;
  /** @sqlType nvarchar */
  currentCode?: string;
  /** @sqlType bit */
  generateOnly?: boolean;
  /** @sqlType nvarchar */
  verificationCode?: string;
  /** @sqlType nvarchar */
  secret?: string;
  /** @sqlType bit */
  confirmEnable?: boolean;
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
// Procedure Result Set Interfaces
// ============================================================================

export interface ActivateUserAccount_ResultSet0 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type ActivateUserAccountResults = [ActivateUserAccount_ResultSet0[]];

export interface CancelQueueItem_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CancelQueueItem_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  previousStatus: string | null;
  /** @sqlType varchar */
  newStatus: string | null;
}
export interface CancelQueueItem_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  previousStatus: string | null;
  /** @sqlType varchar */
  newStatus: string | null;
}

export type CancelQueueItemResults = [
  CancelQueueItem_ResultSet0[],
  CancelQueueItem_ResultSet1[],
  CancelQueueItem_ResultSet2[],
];

export interface CreateAuthenticationRequest_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
  /** @sqlType datetimeoffset */
  tokenExpiration: string | null;
  /** @sqlType int */
  expirationHours: number | null;
  /** @sqlType nvarchar */
  vaultOrganization: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType nvarchar */
  preferredLanguage: string | null;
  /** @sqlType varchar */
  authenticationStatus: string | null;
}

export type CreateAuthenticationRequestResults = [CreateAuthenticationRequest_ResultSet0[]];

export interface CreateBridge_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateBridge_ResultSet1 {
  /** @sqlType int */
  bridgeId: number | null;
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateBridgeResults = [
  CreateBridge_ResultSet0[],
  CreateBridge_ResultSet1[],
];

export interface CreateCephCluster_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateCephCluster_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type CreateCephClusterResults = [
  CreateCephCluster_ResultSet0[],
  CreateCephCluster_ResultSet1[],
];

export interface CreateCephPool_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateCephPool_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type CreateCephPoolResults = [
  CreateCephPool_ResultSet0[],
  CreateCephPool_ResultSet1[],
];

export interface CreateCephRbdClone_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateCephRbdClone_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type CreateCephRbdCloneResults = [
  CreateCephRbdClone_ResultSet0[],
  CreateCephRbdClone_ResultSet1[],
];

export interface CreateCephRbdImage_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateCephRbdImage_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type CreateCephRbdImageResults = [
  CreateCephRbdImage_ResultSet0[],
  CreateCephRbdImage_ResultSet1[],
];

export interface CreateCephRbdSnapshot_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateCephRbdSnapshot_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type CreateCephRbdSnapshotResults = [
  CreateCephRbdSnapshot_ResultSet0[],
  CreateCephRbdSnapshot_ResultSet1[],
];

export interface CreateMachine_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateMachine_ResultSet1 {
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateMachineResults = [
  CreateMachine_ResultSet0[],
  CreateMachine_ResultSet1[],
];

export interface CreateNewOrganization_ResultSet0 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  languagePreference: string | null;
  /** @sqlType char */
  activationCode: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
}

export type CreateNewOrganizationResults = [CreateNewOrganization_ResultSet0[]];

export interface CreateNewUser_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateNewUser_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  languagePreference: string | null;
  /** @sqlType int */
  activationCode: number | null;
  /** @sqlType nvarchar */
  createdBy: string | null;
}

export type CreateNewUserResults = [
  CreateNewUser_ResultSet0[],
  CreateNewUser_ResultSet1[],
];

export interface CreatePermissionGroup_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreatePermissionGroup_ResultSet1 {
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type CreatePermissionGroupResults = [
  CreatePermissionGroup_ResultSet0[],
  CreatePermissionGroup_ResultSet1[],
];

export interface CreatePermissionInGroup_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreatePermissionInGroup_ResultSet1 {
  /** @sqlType nvarchar */
  permissionName: string | null;
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type CreatePermissionInGroupResults = [
  CreatePermissionInGroup_ResultSet0[],
  CreatePermissionInGroup_ResultSet1[],
];

export interface CreateQueueItem_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateQueueItem_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType datetimeoffset */
  time: string | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType uniqueidentifier */
  bridgeCredential: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType nvarchar */
  createdBy: string | null;
  /** @sqlType nvarchar */
  highPriorityInfo: string | null;
}

export type CreateQueueItemResults = [
  CreateQueueItem_ResultSet0[],
  CreateQueueItem_ResultSet1[],
];

export interface CreateRegion_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateRegion_ResultSet1 {
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateRegionResults = [
  CreateRegion_ResultSet0[],
  CreateRegion_ResultSet1[],
];

export interface CreateRepository_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateRepository_ResultSet1 {
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateRepositoryResults = [
  CreateRepository_ResultSet0[],
  CreateRepository_ResultSet1[],
];

export interface CreateStorage_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateStorage_ResultSet1 {
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateStorageResults = [
  CreateStorage_ResultSet0[],
  CreateStorage_ResultSet1[],
];

export interface CreateTeam_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateTeam_ResultSet1 {
  /** @sqlType nvarchar */
  name: string | null;
}

export type CreateTeamResults = [
  CreateTeam_ResultSet0[],
  CreateTeam_ResultSet1[],
];

export interface CreateTeamMembership_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateTeamMembership_ResultSet1 {
  /** @sqlType nvarchar */
  addedUserEmail: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type CreateTeamMembershipResults = [
  CreateTeamMembership_ResultSet0[],
  CreateTeamMembership_ResultSet1[],
];

export interface DeleteBridge_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteBridgeResults = [DeleteBridge_ResultSet0[]];

export interface DeleteCephCluster_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteCephCluster_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type DeleteCephClusterResults = [
  DeleteCephCluster_ResultSet0[],
  DeleteCephCluster_ResultSet1[],
];

export interface DeleteCephPool_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteCephPool_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type DeleteCephPoolResults = [
  DeleteCephPool_ResultSet0[],
  DeleteCephPool_ResultSet1[],
];

export interface DeleteCephRbdClone_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteCephRbdClone_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type DeleteCephRbdCloneResults = [
  DeleteCephRbdClone_ResultSet0[],
  DeleteCephRbdClone_ResultSet1[],
];

export interface DeleteCephRbdImage_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteCephRbdImage_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type DeleteCephRbdImageResults = [
  DeleteCephRbdImage_ResultSet0[],
  DeleteCephRbdImage_ResultSet1[],
];

export interface DeleteCephRbdSnapshot_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteCephRbdSnapshot_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type DeleteCephRbdSnapshotResults = [
  DeleteCephRbdSnapshot_ResultSet0[],
  DeleteCephRbdSnapshot_ResultSet1[],
];

export interface DeleteMachine_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteMachineResults = [DeleteMachine_ResultSet0[]];

export interface DeletePermissionFromGroup_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeletePermissionFromGroup_ResultSet1 {
  /** @sqlType int */
  permissionsId: number | null;
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType int */
  organizationId: number | null;
  /** @sqlType nvarchar */
  removedPermissionName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type DeletePermissionFromGroupResults = [
  DeletePermissionFromGroup_ResultSet0[],
  DeletePermissionFromGroup_ResultSet1[],
];

export interface DeletePermissionGroup_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeletePermissionGroup_ResultSet1 {
  /** @sqlType nvarchar */
  removedPermissionGroupName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type DeletePermissionGroupResults = [
  DeletePermissionGroup_ResultSet0[],
  DeletePermissionGroup_ResultSet1[],
];

export interface DeleteQueueItem_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteQueueItem_ResultSet1 {
  /** @sqlType varchar */
  result: string | null;
}

export type DeleteQueueItemResults = [
  DeleteQueueItem_ResultSet0[],
  DeleteQueueItem_ResultSet1[],
];

export interface DeleteRegion_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteRegionResults = [DeleteRegion_ResultSet0[]];

export interface DeleteRepository_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteRepositoryResults = [DeleteRepository_ResultSet0[]];

export interface DeleteStorage_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteStorageResults = [DeleteStorage_ResultSet0[]];

export interface DeleteTeam_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type DeleteTeamResults = [DeleteTeam_ResultSet0[]];

export interface DeleteUserFromTeam_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteUserFromTeam_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type DeleteUserFromTeamResults = [
  DeleteUserFromTeam_ResultSet0[],
  DeleteUserFromTeam_ResultSet1[],
];

export interface DeleteUserRequest_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface DeleteUserRequest_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType nvarchar */
  sessionName: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type DeleteUserRequestResults = [
  DeleteUserRequest_ResultSet0[],
  DeleteUserRequest_ResultSet1[],
];

export interface ExportOrganizationData_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ExportOrganizationData_ResultSet1 {
  /** @sqlType nvarchar */
  exportData: string | null;
}

export type ExportOrganizationDataResults = [
  ExportOrganizationData_ResultSet0[],
  ExportOrganizationData_ResultSet1[],
];

export interface ForkAuthenticationRequest_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ForkAuthenticationRequest_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
  /** @sqlType datetimeoffset */
  tokenExpiration: string | null;
  /** @sqlType int */
  expirationHours: number | null;
  /** @sqlType nvarchar */
  vaultOrganization: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType varchar */
  authenticationStatus: string | null;
  /** @sqlType int */
  parentRequestId: number | null;
}

export type ForkAuthenticationRequestResults = [
  ForkAuthenticationRequest_ResultSet0[],
  ForkAuthenticationRequest_ResultSet1[],
];

export interface GetAuditLogs_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetAuditLogs_ResultSet1 {
  /** @sqlType nvarchar */
  entity: string | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string | null;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string | null;
}
export interface GetAuditLogs_ResultSet2 {
  /** @sqlType nvarchar */
  entity: string | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string | null;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string | null;
}

export type GetAuditLogsResults = [
  GetAuditLogs_ResultSet0[],
  GetAuditLogs_ResultSet1[],
  GetAuditLogs_ResultSet2[],
];

export interface GetAvailableMachinesForClone_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetAvailableMachinesForClone_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType varchar */
  status: string | null;
  /** @sqlType varchar */
  description: string | null;
}

export type GetAvailableMachinesForCloneResults = [
  GetAvailableMachinesForClone_ResultSet0[],
  GetAvailableMachinesForClone_ResultSet1[],
];

export interface GetCephClusterMachines_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephClusterMachines_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType datetime2 */
  assignedDate: string | null;
}

export type GetCephClusterMachinesResults = [
  GetCephClusterMachines_ResultSet0[],
  GetCephClusterMachines_ResultSet1[],
];

export interface GetCephClusters_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephClusters_ResultSet1 {
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType int */
  assignedMachineCount: number | null;
  /** @sqlType int */
  poolCount: number | null;
  /** @sqlType nvarchar */
  clusterVault: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type GetCephClustersResults = [
  GetCephClusters_ResultSet0[],
  GetCephClusters_ResultSet1[],
];

export interface GetCephPools_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephPools_ResultSet1 {
  /** @sqlType nvarchar */
  poolName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType int */
  rbdImageCount: number | null;
  /** @sqlType nvarchar */
  poolVault: string | null;
  /** @sqlType nvarchar */
  poolGuid: string | null;
}

export type GetCephPoolsResults = [
  GetCephPools_ResultSet0[],
  GetCephPools_ResultSet1[],
];

export interface GetCephRbdClones_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephRbdClones_ResultSet1 {
  /** @sqlType nvarchar */
  cloneName: string | null;
  /** @sqlType nvarchar */
  snapshotName: string | null;
  /** @sqlType nvarchar */
  imageName: string | null;
  /** @sqlType nvarchar */
  poolName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType datetime2 */
  snapshotCreatedDate: string | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  snapshotGuid: string | null;
}

export type GetCephRbdClonesResults = [
  GetCephRbdClones_ResultSet0[],
  GetCephRbdClones_ResultSet1[],
];

export interface GetCephRbdImages_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephRbdImages_ResultSet1 {
  /** @sqlType nvarchar */
  imageName: string | null;
  /** @sqlType nvarchar */
  poolName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  imageGuid: number | null;
  /** @sqlType int */
  snapshotCount: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
}

export type GetCephRbdImagesResults = [
  GetCephRbdImages_ResultSet0[],
  GetCephRbdImages_ResultSet1[],
];

export interface GetCephRbdSnapshots_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCephRbdSnapshots_ResultSet1 {
  /** @sqlType nvarchar */
  snapshotName: string | null;
  /** @sqlType nvarchar */
  imageName: string | null;
  /** @sqlType nvarchar */
  poolName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  clusterName: string | null;
  /** @sqlType datetime2 */
  createdDate: string | null;
  /** @sqlType int */
  cloneCount: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  snapshotGuid: string | null;
}

export type GetCephRbdSnapshotsResults = [
  GetCephRbdSnapshots_ResultSet0[],
  GetCephRbdSnapshots_ResultSet1[],
];

export interface GetCloneMachineAssignmentValidation_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCloneMachineAssignmentValidation_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  validationStatus: string | null;
  /** @sqlType nvarchar */
  currentAssignment: string | null;
  /** @sqlType nvarchar */
  message: string | null;
}
export interface GetCloneMachineAssignmentValidation_ResultSet2 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType varchar */
  validationStatus: string | null;
  /** @sqlType nvarchar */
  currentAssignment: string | null;
  /** @sqlType nvarchar */
  message: string | null;
}

export type GetCloneMachineAssignmentValidationResults = [
  GetCloneMachineAssignmentValidation_ResultSet0[],
  GetCloneMachineAssignmentValidation_ResultSet1[],
  GetCloneMachineAssignmentValidation_ResultSet2[],
];

export interface GetCloneMachines_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCloneMachines_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType int */
  assignmentId: number | null;
}

export type GetCloneMachinesResults = [
  GetCloneMachines_ResultSet0[],
  GetCloneMachines_ResultSet1[],
];

export interface GetEntityAuditTrace_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetEntityAuditTrace_ResultSet1 {
  /** @sqlType nvarchar */
  action: string | null;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  performedBy: string | null;
  /** @sqlType datetime2 */
  timestamp: string | null;
  /** @sqlType varchar */
  actionType: string | null;
  /** @sqlType nvarchar */
  timeAgo: string | null;
  /** @sqlType varchar */
  iconHint: string | null;
}
export interface GetEntityAuditTrace_ResultSet2 {
  /** @sqlType nvarchar */
  entityType: string | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType int */
  entityId: number | null;
  /** @sqlType int */
  totalAuditRecords: number | null;
  /** @sqlType int */
  visibleAuditRecords: number | null;
  /** @sqlType datetime2 */
  oldestVisibleActivity: string | null;
  /** @sqlType datetime2 */
  lastActivity: string | null;
  /** @sqlType bit */
  hasAccess: boolean | null;
  /** @sqlType bit */
  isAdmin: boolean | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  auditRetentionDays: number | null;
  /** @sqlType bit */
  hasOlderRecords: boolean | null;
  /** @sqlType int */
  relatedCount: number | null;
}

export type GetEntityAuditTraceResults = [
  GetEntityAuditTrace_ResultSet0[],
  GetEntityAuditTrace_ResultSet1[],
  GetEntityAuditTrace_ResultSet2[],
];

export interface GetEntityHistory_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetEntityHistory_ResultSet1 {
  /** @sqlType int */
  auditId: number | null;
  /** @sqlType nvarchar */
  entity: string | null;
  /** @sqlType int */
  entityId: number | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string | null;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType int */
  userId: number | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string | null;
  /** @sqlType varchar */
  actionCategory: string | null;
}
export interface GetEntityHistory_ResultSet2 {
  /** @sqlType nvarchar */
  entityType: string | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType uniqueidentifier */
  entityCredential: string | null;
  /** @sqlType int */
  totalAuditRecords: number | null;
  /** @sqlType datetime2 */
  firstActivity: string | null;
  /** @sqlType datetime2 */
  lastActivity: string | null;
}

export type GetEntityHistoryResults = [
  GetEntityHistory_ResultSet0[],
  GetEntityHistory_ResultSet1[],
  GetEntityHistory_ResultSet2[],
];

export interface GetLookupData_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetLookupData_ResultSet1 {
  /** @sqlType nvarchar */
  dropdownValues: string | null;
}

export type GetLookupDataResults = [
  GetLookupData_ResultSet0[],
  GetLookupData_ResultSet1[],
];

export interface GetMachineAssignmentStatus_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetMachineAssignmentStatus_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  assignmentType: string | null;
  /** @sqlType nvarchar */
  assignmentDetails: string | null;
  /** @sqlType nvarchar */
  status: string | null;
}
export interface GetMachineAssignmentStatus_ResultSet2 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  assignmentType: string | null;
  /** @sqlType nvarchar */
  assignmentDetails: string | null;
  /** @sqlType varchar */
  status: string | null;
}

export type GetMachineAssignmentStatusResults = [
  GetMachineAssignmentStatus_ResultSet0[],
  GetMachineAssignmentStatus_ResultSet1[],
  GetMachineAssignmentStatus_ResultSet2[],
];

export interface GetOrganizationDashboard_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationDashboard_ResultSet1 {
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType nvarchar */
  organizationGuid: string | null;
  /** @sqlType nvarchar */
  planCode: string | null;
}
export interface GetOrganizationDashboard_ResultSet2 {
  /** @sqlType nvarchar */
  planCode: string | null;
  /** @sqlType int */
  quantity: number | null;
  /** @sqlType int */
  totalActivePurchases: number | null;
  /** @sqlType datetime2 */
  startDate: string | null;
  /** @sqlType datetime2 */
  endDate: string | null;
  /** @sqlType int */
  daysRemaining: number | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType bit */
  isActive: boolean | null;
  /** @sqlType bit */
  isTrial: boolean | null;
  /** @sqlType bit */
  isExpiringSoon: boolean | null;
}
export interface GetOrganizationDashboard_ResultSet3 {
  /** @sqlType nvarchar */
  planCode: string | null;
  /** @sqlType int */
  quantity: number | null;
  /** @sqlType datetime2 */
  startDate: string | null;
  /** @sqlType datetime2 */
  endDate: string | null;
  /** @sqlType int */
  daysRemaining: number | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType bit */
  isTrial: boolean | null;
}
export interface GetOrganizationDashboard_ResultSet4 {
  /** @sqlType varchar */
  resourceType: string | null;
  /** @sqlType int */
  resourceLimit: number | null;
  /** @sqlType nvarchar */
  activeSubscriptionTier: string | null;
  /** @sqlType int */
  currentUsage: number | null;
  /** @sqlType bit */
  isLimitReached: boolean | null;
  /** @sqlType decimal */
  usagePercentage: number | null;
}
export interface GetOrganizationDashboard_ResultSet5 {
  /** @sqlType int */
  resourcesAtLimit: number | null;
  /** @sqlType int */
  resourcesNearLimit: number | null;
  /** @sqlType varchar */
  subscriptionStatus: string | null;
  /** @sqlType varchar */
  upgradeRecommendation: string | null;
}
export interface GetOrganizationDashboard_ResultSet6 {
  /** @sqlType bit */
  hasAdvancedAnalytics: boolean | null;
  /** @sqlType bit */
  hasPrioritySupport: boolean | null;
  /** @sqlType bit */
  hasDedicatedAccount: boolean | null;
  /** @sqlType bit */
  hasCustomBranding: boolean | null;
  /** @sqlType bit */
  ceph: boolean | null;
  /** @sqlType bit */
  auditLog: boolean | null;
  /** @sqlType bit */
  advancedQueue: boolean | null;
}
export interface GetOrganizationDashboard_ResultSet7 {
  /** @sqlType nvarchar */
  planCode: string | null;
  /** @sqlType int */
  machineLimit: number | null;
  /** @sqlType int */
  repositoryLimit: number | null;
  /** @sqlType int */
  userLimit: number | null;
  /** @sqlType int */
  maxReservedJobs: number | null;
  /** @sqlType int */
  jobTimeoutHours: number | null;
  /** @sqlType int */
  maxRepositorySize: number | null;
}
export interface GetOrganizationDashboard_ResultSet8 {
  /** @sqlType int */
  pendingCount: number | null;
  /** @sqlType int */
  assignedCount: number | null;
  /** @sqlType int */
  processingCount: number | null;
  /** @sqlType int */
  activeCount: number | null;
  /** @sqlType int */
  completedCount: number | null;
  /** @sqlType int */
  cancelledCount: number | null;
  /** @sqlType int */
  failedCount: number | null;
  /** @sqlType int */
  totalCount: number | null;
  /** @sqlType int */
  staleCount: number | null;
  /** @sqlType int */
  stalePendingCount: number | null;
  /** @sqlType int */
  completedToday: number | null;
  /** @sqlType int */
  cancelledToday: number | null;
  /** @sqlType int */
  createdToday: number | null;
  /** @sqlType int */
  itemsWithRetries: number | null;
  /** @sqlType int */
  maxRetryCount: number | null;
  /** @sqlType int */
  avgRetryCount: number | null;
  /** @sqlType int */
  oldestPendingAgeMinutes: number | null;
  /** @sqlType int */
  avgPendingAgeMinutes: number | null;
  /** @sqlType int */
  highestPriorityPending: number | null;
  /** @sqlType int */
  highPriorityPending: number | null;
  /** @sqlType int */
  normalPriorityPending: number | null;
  /** @sqlType int */
  lowPriorityPending: number | null;
  /** @sqlType bit */
  hasStaleItems: boolean | null;
  /** @sqlType bit */
  hasOldPendingItems: boolean | null;
}
export interface GetOrganizationDashboard_ResultSet9 {
  /** @sqlType int */
  totalUserItems: number | null;
  /** @sqlType int */
  userPendingItems: number | null;
  /** @sqlType int */
  userActiveItems: number | null;
  /** @sqlType int */
  userCompletedToday: number | null;
  /** @sqlType int */
  userHighPriorityActive: number | null;
}
export interface GetOrganizationDashboard_ResultSet10 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  totalItems: number | null;
  /** @sqlType int */
  pendingItems: number | null;
  /** @sqlType int */
  activeItems: number | null;
  /** @sqlType int */
  staleItems: number | null;
}
export interface GetOrganizationDashboard_ResultSet11 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType int */
  totalItems: number | null;
  /** @sqlType int */
  pendingItems: number | null;
  /** @sqlType int */
  activeItems: number | null;
  /** @sqlType int */
  staleItems: number | null;
}
export interface GetOrganizationDashboard_ResultSet12 {
  /** @sqlType nvarchar */
  userName: string | null;
  /** @sqlType int */
  totalItems: number | null;
  /** @sqlType int */
  activeItems: number | null;
  /** @sqlType int */
  completedToday: number | null;
  /** @sqlType int */
  highPriorityActive: number | null;
}
export interface GetOrganizationDashboard_ResultSet13 {
  /** @sqlType int */
  totalMachines: number | null;
  /** @sqlType int */
  availableMachines: number | null;
  /** @sqlType int */
  clusterAssignedMachines: number | null;
  /** @sqlType int */
  imageAssignedMachines: number | null;
  /** @sqlType int */
  cloneAssignedMachines: number | null;
  /** @sqlType int */
  trulyAvailableMachines: number | null;
  /** @sqlType decimal */
  availablePercentage: number | null;
  /** @sqlType decimal */
  clusterPercentage: number | null;
  /** @sqlType decimal */
  imagePercentage: number | null;
  /** @sqlType decimal */
  clonePercentage: number | null;
  /** @sqlType int */
  totalClusters: number | null;
  /** @sqlType int */
  activeClusters: number | null;
  /** @sqlType int */
  avgMachinesPerCluster: number | null;
}
export interface GetOrganizationDashboard_ResultSet14 {
  /** @sqlType int */
  totalMachines: number | null;
  /** @sqlType int */
  availableMachines: number | null;
  /** @sqlType int */
  clusterAssignedMachines: number | null;
  /** @sqlType int */
  imageAssignedMachines: number | null;
  /** @sqlType int */
  cloneAssignedMachines: number | null;
  /** @sqlType int */
  trulyAvailableMachines: number | null;
  /** @sqlType decimal */
  availablePercentage: number | null;
  /** @sqlType decimal */
  clusterPercentage: number | null;
  /** @sqlType decimal */
  imagePercentage: number | null;
  /** @sqlType decimal */
  clonePercentage: number | null;
  /** @sqlType int */
  totalClusters: number | null;
  /** @sqlType int */
  activeClusters: number | null;
  /** @sqlType int */
  avgMachinesPerCluster: number | null;
}
export interface GetOrganizationDashboard_ResultSet15 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  totalMachines: number | null;
  /** @sqlType int */
  availableMachines: number | null;
  /** @sqlType int */
  clusterMachines: number | null;
  /** @sqlType int */
  imageMachines: number | null;
  /** @sqlType int */
  cloneMachines: number | null;
}
export interface GetOrganizationDashboard_ResultSet16 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  totalMachines: number | null;
  /** @sqlType int */
  availableMachines: number | null;
  /** @sqlType int */
  clusterMachines: number | null;
  /** @sqlType int */
  imageMachines: number | null;
  /** @sqlType int */
  cloneMachines: number | null;
}

export type GetOrganizationDashboardResults = [
  GetOrganizationDashboard_ResultSet0[],
  GetOrganizationDashboard_ResultSet1[],
  GetOrganizationDashboard_ResultSet2[],
  GetOrganizationDashboard_ResultSet3[],
  GetOrganizationDashboard_ResultSet4[],
  GetOrganizationDashboard_ResultSet5[],
  GetOrganizationDashboard_ResultSet6[],
  GetOrganizationDashboard_ResultSet7[],
  GetOrganizationDashboard_ResultSet8[],
  GetOrganizationDashboard_ResultSet9[],
  GetOrganizationDashboard_ResultSet10[],
  GetOrganizationDashboard_ResultSet11[],
  GetOrganizationDashboard_ResultSet12[],
  GetOrganizationDashboard_ResultSet13[],
  GetOrganizationDashboard_ResultSet14[],
  GetOrganizationDashboard_ResultSet15[],
  GetOrganizationDashboard_ResultSet16[],
];

export interface GetOrganizationPermissionGroups_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationPermissionGroups_ResultSet1 {
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType int */
  userCount: number | null;
  /** @sqlType int */
  permissionCount: number | null;
  /** @sqlType nvarchar */
  permissions: string | null;
}

export type GetOrganizationPermissionGroupsResults = [
  GetOrganizationPermissionGroups_ResultSet0[],
  GetOrganizationPermissionGroups_ResultSet1[],
];

export interface GetOrganizationRegions_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationRegions_ResultSet1 {
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  bridgeCount: number | null;
}

export type GetOrganizationRegionsResults = [
  GetOrganizationRegions_ResultSet0[],
  GetOrganizationRegions_ResultSet1[],
];

export interface GetOrganizationTeams_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationTeams_ResultSet1 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType bit */
  isMember: boolean | null;
  /** @sqlType int */
  memberCount: number | null;
  /** @sqlType int */
  machineCount: number | null;
  /** @sqlType int */
  repositoryCount: number | null;
  /** @sqlType int */
  storageCount: number | null;
}

export type GetOrganizationTeamsResults = [
  GetOrganizationTeams_ResultSet0[],
  GetOrganizationTeams_ResultSet1[],
];

export interface GetOrganizationUsers_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationUsers_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType bit */
  activated: boolean | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  permissionsName: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  teamCount: number | null;
  /** @sqlType datetimeoffset */
  lastActive: string | null;
}
export interface GetOrganizationUsers_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType bit */
  activated: boolean | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType int */
  vaultContent: number | null;
  /** @sqlType nvarchar */
  permissionsName: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  teamCount: number | null;
  /** @sqlType datetimeoffset */
  lastActive: string | null;
}

export type GetOrganizationUsersResults = [
  GetOrganizationUsers_ResultSet0[],
  GetOrganizationUsers_ResultSet1[],
  GetOrganizationUsers_ResultSet2[],
];

export interface GetOrganizationVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationVault_ResultSet1 {
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType uniqueidentifier */
  organizationCredential: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
}

export type GetOrganizationVaultResults = [
  GetOrganizationVault_ResultSet0[],
  GetOrganizationVault_ResultSet1[],
];

export interface GetOrganizationVaults_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetOrganizationVaults_ResultSet1 {
  /** @sqlType nvarchar */
  entityType: string | null;
  /** @sqlType int */
  entityId: number | null;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType int */
  vaultId: number | null;
  /** @sqlType nvarchar */
  vaultName: string | null;
  /** @sqlType uniqueidentifier */
  credential: string | null;
  /** @sqlType int */
  chunkOrder: number | null;
  /** @sqlType int */
  version: number | null;
  /** @sqlType varbinary */
  encryptedVault: string | null;
  /** @sqlType nvarchar */
  decryptedVault: string | null;
}
export interface GetOrganizationVaults_ResultSet2 {
  /** @sqlType int */
  bridgeId: number | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType uniqueidentifier */
  requestToken: string | null;
  /** @sqlType bit */
  hasRequestToken: boolean | null;
}

export type GetOrganizationVaultsResults = [
  GetOrganizationVaults_ResultSet0[],
  GetOrganizationVaults_ResultSet1[],
  GetOrganizationVaults_ResultSet2[],
];

export interface GetPermissionGroupDetails_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetPermissionGroupDetails_ResultSet1 {
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType nvarchar */
  permissionName: string | null;
}

export type GetPermissionGroupDetailsResults = [
  GetPermissionGroupDetails_ResultSet0[],
  GetPermissionGroupDetails_ResultSet1[],
];

export interface GetQueueItemTrace_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetQueueItemTrace_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType datetimeoffset */
  createdTime: string | null;
  /** @sqlType datetimeoffset */
  assignedTime: string | null;
  /** @sqlType datetimeoffset */
  lastAssigned: string | null;
  /** @sqlType int */
  retryCount: number | null;
  /** @sqlType datetimeoffset */
  lastRetryAt: string | null;
  /** @sqlType nvarchar */
  lastFailureReason: string | null;
  /** @sqlType datetimeoffset */
  lastResponseAt: string | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType varchar */
  priorityLabel: string | null;
  /** @sqlType int */
  secondsToAssignment: number | null;
  /** @sqlType int */
  processingDurationSeconds: number | null;
  /** @sqlType int */
  totalDurationSeconds: number | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  machineId: number | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType int */
  bridgeId: number | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType int */
  regionId: number | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  teamId: number | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  organizationId: number | null;
  /** @sqlType nvarchar */
  createdBy: string | null;
  /** @sqlType int */
  createdByUserId: number | null;
  /** @sqlType varchar */
  healthStatus: string | null;
  /** @sqlType bit */
  isStale: boolean | null;
  /** @sqlType bit */
  isStalePending: boolean | null;
  /** @sqlType bit */
  canBeCancelled: boolean | null;
}
export interface GetQueueItemTrace_ResultSet2 {
  /** @sqlType varchar */
  vaultType: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType bit */
  hasContent: boolean | null;
}
export interface GetQueueItemTrace_ResultSet3 {
  /** @sqlType varchar */
  vaultType: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType bit */
  hasContent: boolean | null;
}
export interface GetQueueItemTrace_ResultSet4 {
  /** @sqlType nvarchar */
  action: string | null;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType datetime2 */
  timestamp: string | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType int */
  secondsSincePrevious: number | null;
}
export interface GetQueueItemTrace_ResultSet5 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType datetimeoffset */
  createdTime: string | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  secondsDifference: number | null;
  /** @sqlType varchar */
  relativePosition: string | null;
  /** @sqlType nvarchar */
  createdBy: string | null;
}
export interface GetQueueItemTrace_ResultSet6 {
  /** @sqlType int */
  avgProcessingTimeSeconds: number | null;
  /** @sqlType float */
  machineSuccessRate: number | null;
  /** @sqlType int */
  currentQueueDepth: number | null;
  /** @sqlType int */
  activeProcessingCount: number | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
}

export type GetQueueItemTraceResults = [
  GetQueueItemTrace_ResultSet0[],
  GetQueueItemTrace_ResultSet1[],
  GetQueueItemTrace_ResultSet2[],
  GetQueueItemTrace_ResultSet3[],
  GetQueueItemTrace_ResultSet4[],
  GetQueueItemTrace_ResultSet5[],
  GetQueueItemTrace_ResultSet6[],
];

export interface GetQueueItemsNext_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetQueueItemsNext_ResultSet1 {
  /** @sqlType nvarchar */
  organizationSubscription: string | null;
  /** @sqlType nvarchar */
  organizationCredential: string | null;
  /** @sqlType nvarchar */
  bridgeCredential: string | null;
}
export interface GetQueueItemsNext_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType datetimeoffset */
  time: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType datetimeoffset */
  assigned: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  retryCount: number | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet3 {
  /** @sqlType nvarchar */
  result: string | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet4 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType datetimeoffset */
  time: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType datetimeoffset */
  assigned: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  retryCount: number | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet5 {
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet6 {
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet7 {
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}

export type GetQueueItemsNextResults = [
  GetQueueItemsNext_ResultSet0[],
  GetQueueItemsNext_ResultSet1[],
  GetQueueItemsNext_ResultSet2[],
  GetQueueItemsNext_ResultSet3[],
  GetQueueItemsNext_ResultSet4[],
  GetQueueItemsNext_ResultSet5[],
  GetQueueItemsNext_ResultSet6[],
  GetQueueItemsNext_ResultSet7[],
];

export interface GetRegionBridges_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetRegionBridges_ResultSet1 {
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  bridgeCredentialsVersion: number | null;
  /** @sqlType nvarchar */
  bridgeCredentials: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType int */
  machineCount: number | null;
  /** @sqlType bit */
  hasAccess: boolean | null;
  /** @sqlType nvarchar */
  bridgeUserEmail: string | null;
  /** @sqlType varchar */
  managementMode: string | null;
  /** @sqlType bit */
  isGlobalBridge: boolean | null;
}

export type GetRegionBridgesResults = [
  GetRegionBridges_ResultSet0[],
  GetRegionBridges_ResultSet1[],
];

export interface GetRequestAuthenticationStatus_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetRequestAuthenticationStatus_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType bit */
  isTFAEnabled: boolean | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType datetimeoffset */
  lastLoginTime: string | null;
  /** @sqlType datetimeoffset */
  tokenExpiration: string | null;
  /** @sqlType nvarchar */
  permissionGroup: string | null;
  /** @sqlType int */
  activeTokenCount: number | null;
  /** @sqlType varchar */
  authenticationStatus: string | null;
}

export type GetRequestAuthenticationStatusResults = [
  GetRequestAuthenticationStatus_ResultSet0[],
  GetRequestAuthenticationStatus_ResultSet1[],
];

export interface GetSystemConfiguration_ResultSet0 {
  /** @sqlType nvarchar */
  configKey: string | null;
  /** @sqlType nvarchar */
  configValue: string | null;
  /** @sqlType nvarchar */
  configDescription: string | null;
  /** @sqlType datetime */
  modifiedDate: string | null;
}
export interface GetSystemConfiguration_ResultSet1 {
  /** @sqlType nvarchar */
  configKey: string | null;
  /** @sqlType nvarchar */
  configValue: string | null;
  /** @sqlType nvarchar */
  configDescription: string | null;
  /** @sqlType datetime */
  modifiedDate: string | null;
}
export interface GetSystemConfiguration_ResultSet2 {
  /** @sqlType nvarchar */
  configKey: string | null;
  /** @sqlType nvarchar */
  configValue: string | null;
  /** @sqlType nvarchar */
  configDescription: string | null;
  /** @sqlType datetime */
  modifiedDate: string | null;
}

export type GetSystemConfigurationResults = [
  GetSystemConfiguration_ResultSet0[],
  GetSystemConfiguration_ResultSet1[],
  GetSystemConfiguration_ResultSet2[],
];

export interface GetTeamMachines_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetTeamMachines_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  vaultStatus: string | null;
  /** @sqlType datetime2 */
  vaultStatusTime: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  queueCount: number | null;
  /** @sqlType nvarchar */
  machineGuid: string | null;
  /** @sqlType nvarchar */
  cephClusterName: string | null;
  /** @sqlType varchar */
  assignmentStatus: string | null;
}

export type GetTeamMachinesResults = [
  GetTeamMachines_ResultSet0[],
  GetTeamMachines_ResultSet1[],
];

export interface GetTeamMembers_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetTeamMembers_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType bit */
  activated: boolean | null;
  /** @sqlType nvarchar */
  teams: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType bit */
  isMember: boolean | null;
  /** @sqlType bit */
  hasAccess: boolean | null;
}
export interface GetTeamMembers_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType bit */
  activated: boolean | null;
  /** @sqlType nvarchar */
  teams: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType bit */
  isMember: boolean | null;
  /** @sqlType bit */
  hasAccess: boolean | null;
}

export type GetTeamMembersResults = [
  GetTeamMembers_ResultSet0[],
  GetTeamMembers_ResultSet1[],
  GetTeamMembers_ResultSet2[],
];

export interface GetTeamQueueItems_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetTeamQueueItems_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType datetime2 */
  createdTime: string | null;
  /** @sqlType int */
  ageInMinutes: number | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  vaultVersionResponse: number | null;
  /** @sqlType nvarchar */
  vaultContentResponse: string | null;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType nvarchar */
  status: string | null;
  /** @sqlType datetime2 */
  assignedTime: string | null;
  /** @sqlType datetime2 */
  lastAssigned: string | null;
  /** @sqlType int */
  minutesSinceAssigned: number | null;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType nvarchar */
  priorityLabel: string | null;
  /** @sqlType varchar */
  healthStatus: string | null;
  /** @sqlType bit */
  canBeCancelled: boolean | null;
  /** @sqlType bit */
  hasResponse: boolean | null;
  /** @sqlType nvarchar */
  createdBy: string | null;
  /** @sqlType int */
  retryCount: number | null;
  /** @sqlType datetimeoffset */
  lastRetryAt: string | null;
  /** @sqlType nvarchar */
  lastFailureReason: string | null;
  /** @sqlType bit */
  permanentlyFailed: boolean | null;
  /** @sqlType int */
  totalDurationSeconds: number | null;
  /** @sqlType int */
  processingDurationSeconds: number | null;
  /** @sqlType datetime2 */
  lastResponseAt: string | null;
}
export interface GetTeamQueueItems_ResultSet2 {
  /** @sqlType int */
  totalCount: number | null;
  /** @sqlType int */
  pendingCount: number | null;
  /** @sqlType int */
  assignedCount: number | null;
  /** @sqlType int */
  processingCount: number | null;
  /** @sqlType int */
  cancellingCount: number | null;
  /** @sqlType int */
  completedCount: number | null;
  /** @sqlType int */
  cancelledCount: number | null;
  /** @sqlType int */
  failedCount: number | null;
  /** @sqlType int */
  staleCount: number | null;
}

export type GetTeamQueueItemsResults = [
  GetTeamQueueItems_ResultSet0[],
  GetTeamQueueItems_ResultSet1[],
  GetTeamQueueItems_ResultSet2[],
];

export interface GetTeamRepositories_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetTeamRepositories_ResultSet1 {
  /** @sqlType nvarchar */
  repositoryName: string | null;
  /** @sqlType uniqueidentifier */
  repositoryGuid: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType uniqueidentifier */
  grandGuid: string | null;
  /** @sqlType uniqueidentifier */
  parentGuid: string | null;
  /** @sqlType int */
  repositoryNetworkId: number | null;
  /** @sqlType nvarchar */
  repositoryNetworkMode: string | null;
  /** @sqlType nvarchar */
  repositoryTag: string | null;
}

export type GetTeamRepositoriesResults = [
  GetTeamRepositories_ResultSet0[],
  GetTeamRepositories_ResultSet1[],
];

export interface GetTeamStorages_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetTeamStorages_ResultSet1 {
  /** @sqlType nvarchar */
  storageName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type GetTeamStoragesResults = [
  GetTeamStorages_ResultSet0[],
  GetTeamStorages_ResultSet1[],
];

export interface GetUserOrganization_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetUserOrganization_ResultSet1 {
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  teamCount: number | null;
  /** @sqlType int */
  regionCount: number | null;
  /** @sqlType int */
  userCount: number | null;
}

export type GetUserOrganizationResults = [
  GetUserOrganization_ResultSet0[],
  GetUserOrganization_ResultSet1[],
];

export interface GetUserRequests_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetUserRequests_ResultSet1 {
  /** @sqlType int */
  requestId: number | null;
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType nvarchar */
  sessionName: string | null;
  /** @sqlType nvarchar */
  ipAddress: string | null;
  /** @sqlType nvarchar */
  userAgent: string | null;
  /** @sqlType datetimeoffset */
  createdAt: string | null;
  /** @sqlType datetimeoffset */
  lastActivity: string | null;
  /** @sqlType bit */
  isActive: boolean | null;
  /** @sqlType int */
  parentRequestId: number | null;
  /** @sqlType nvarchar */
  permissionsName: string | null;
  /** @sqlType datetimeoffset */
  expirationTime: string | null;
}

export type GetUserRequestsResults = [
  GetUserRequests_ResultSet0[],
  GetUserRequests_ResultSet1[],
];

export interface GetUserVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetUserVault_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType uniqueidentifier */
  userCredential: string | null;
}

export type GetUserVaultResults = [
  GetUserVault_ResultSet0[],
  GetUserVault_ResultSet1[],
];

export interface ImportOrganizationData_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ImportOrganizationData_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
  /** @sqlType int */
  importedCount: number | null;
  /** @sqlType int */
  skippedCount: number | null;
  /** @sqlType int */
  errorCount: number | null;
}
export interface ImportOrganizationData_ResultSet2 {
  /** @sqlType int */
  importedCount: number | null;
  /** @sqlType int */
  skippedCount: number | null;
  /** @sqlType int */
  errorCount: number | null;
  /** @sqlType varchar */
  result: string | null;
}
export interface ImportOrganizationData_ResultSet3 {
  /** @sqlType int */
  importedCount: number | null;
  /** @sqlType int */
  skippedCount: number | null;
  /** @sqlType int */
  errorCount: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type ImportOrganizationDataResults = [
  ImportOrganizationData_ResultSet0[],
  ImportOrganizationData_ResultSet1[],
  ImportOrganizationData_ResultSet2[],
  ImportOrganizationData_ResultSet3[],
];

export interface IsRegistered_ResultSet0 {
  /** @sqlType bit */
  isRegistered: boolean | null;
  /** @sqlType nvarchar */
  serverName: string | null;
}
export interface IsRegistered_ResultSet1 {
  /** @sqlType bit */
  isRegistered: boolean | null;
  /** @sqlType nvarchar */
  serverName: string | null;
}

export type IsRegisteredResults = [
  IsRegistered_ResultSet0[],
  IsRegistered_ResultSet1[],
];

export interface PrivilegeAuthenticationRequest_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface PrivilegeAuthenticationRequest_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType bit */
  isTFAEnabled: boolean | null;
}
export interface PrivilegeAuthenticationRequest_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
}

export type PrivilegeAuthenticationRequestResults = [
  PrivilegeAuthenticationRequest_ResultSet0[],
  PrivilegeAuthenticationRequest_ResultSet1[],
  PrivilegeAuthenticationRequest_ResultSet2[],
];

export interface PromoteRepositoryToGrand_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}

export type PromoteRepositoryToGrandResults = [PromoteRepositoryToGrand_ResultSet0[]];

export interface ResetBridgeAuthorization_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ResetBridgeAuthorization_ResultSet1 {
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  managementMode: string | null;
}

export type ResetBridgeAuthorizationResults = [
  ResetBridgeAuthorization_ResultSet0[],
  ResetBridgeAuthorization_ResultSet1[],
];

export interface RetryFailedQueueItem_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface RetryFailedQueueItem_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType int */
  newRetryCount: number | null;
}

export type RetryFailedQueueItemResults = [
  RetryFailedQueueItem_ResultSet0[],
  RetryFailedQueueItem_ResultSet1[],
];

export interface UpdateBridgeName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateBridgeName_ResultSet1 {
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
}

export type UpdateBridgeNameResults = [
  UpdateBridgeName_ResultSet0[],
  UpdateBridgeName_ResultSet1[],
];

export interface UpdateBridgeVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateBridgeVault_ResultSet1 {
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateBridgeVaultResults = [
  UpdateBridgeVault_ResultSet0[],
  UpdateBridgeVault_ResultSet1[],
];

export interface UpdateCephClusterVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCephClusterVault_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateCephClusterVaultResults = [
  UpdateCephClusterVault_ResultSet0[],
  UpdateCephClusterVault_ResultSet1[],
];

export interface UpdateCephPoolVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCephPoolVault_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateCephPoolVaultResults = [
  UpdateCephPoolVault_ResultSet0[],
  UpdateCephPoolVault_ResultSet1[],
];

export interface UpdateCloneMachineAssignments_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCloneMachineAssignments_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateCloneMachineAssignments_ResultSet2 {
  /** @sqlType nvarchar */
  message: string | null;
}
export interface UpdateCloneMachineAssignments_ResultSet3 {
  /** @sqlType nvarchar */
  message: string | null;
}

export type UpdateCloneMachineAssignmentsResults = [
  UpdateCloneMachineAssignments_ResultSet0[],
  UpdateCloneMachineAssignments_ResultSet1[],
  UpdateCloneMachineAssignments_ResultSet2[],
  UpdateCloneMachineAssignments_ResultSet3[],
];

export interface UpdateCloneMachineRemovals_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCloneMachineRemovals_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateCloneMachineRemovals_ResultSet2 {
  /** @sqlType nvarchar */
  message: string | null;
}

export type UpdateCloneMachineRemovalsResults = [
  UpdateCloneMachineRemovals_ResultSet0[],
  UpdateCloneMachineRemovals_ResultSet1[],
  UpdateCloneMachineRemovals_ResultSet2[],
];

export interface UpdateImageMachineAssignment_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateImageMachineAssignment_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateImageMachineAssignment_ResultSet2 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateImageMachineAssignmentResults = [
  UpdateImageMachineAssignment_ResultSet0[],
  UpdateImageMachineAssignment_ResultSet1[],
  UpdateImageMachineAssignment_ResultSet2[],
];

export interface UpdateMachineAssignedBridge_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineAssignedBridge_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
}

export type UpdateMachineAssignedBridgeResults = [
  UpdateMachineAssignedBridge_ResultSet0[],
  UpdateMachineAssignedBridge_ResultSet1[],
];

export interface UpdateMachineCeph_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineCeph_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateMachineCeph_ResultSet2 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateMachineCephResults = [
  UpdateMachineCeph_ResultSet0[],
  UpdateMachineCeph_ResultSet1[],
  UpdateMachineCeph_ResultSet2[],
];

export interface UpdateMachineClusterAssignment_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineClusterAssignment_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateMachineClusterAssignmentResults = [
  UpdateMachineClusterAssignment_ResultSet0[],
  UpdateMachineClusterAssignment_ResultSet1[],
];

export interface UpdateMachineClusterRemoval_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineClusterRemoval_ResultSet1 {
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateMachineClusterRemovalResults = [
  UpdateMachineClusterRemoval_ResultSet0[],
  UpdateMachineClusterRemoval_ResultSet1[],
];

export interface UpdateMachineName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineName_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type UpdateMachineNameResults = [
  UpdateMachineName_ResultSet0[],
  UpdateMachineName_ResultSet1[],
];

export interface UpdateMachineStatus_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineStatus_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  vaultStatus: string | null;
  /** @sqlType datetime2 */
  vaultStatusTime: string | null;
  /** @sqlType nvarchar */
  bridgeName: string | null;
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  queueCount: number | null;
}

export type UpdateMachineStatusResults = [
  UpdateMachineStatus_ResultSet0[],
  UpdateMachineStatus_ResultSet1[],
];

export interface UpdateMachineVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateMachineVault_ResultSet1 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateMachineVaultResults = [
  UpdateMachineVault_ResultSet0[],
  UpdateMachineVault_ResultSet1[],
];

export interface UpdateOrganizationBlockUserRequests_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateOrganizationBlockUserRequests_ResultSet1 {
  /** @sqlType int */
  organizationId: number | null;
  /** @sqlType bit */
  blockUserRequests: boolean | null;
  /** @sqlType int */
  deactivatedTokenCount: number | null;
  /** @sqlType nvarchar */
  result: string | null;
}

export type UpdateOrganizationBlockUserRequestsResults = [
  UpdateOrganizationBlockUserRequests_ResultSet0[],
  UpdateOrganizationBlockUserRequests_ResultSet1[],
];

export interface UpdateOrganizationVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateOrganizationVault_ResultSet1 {
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateOrganizationVaultResults = [
  UpdateOrganizationVault_ResultSet0[],
  UpdateOrganizationVault_ResultSet1[],
];

export interface UpdateOrganizationVaults_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateOrganizationVaults_ResultSet1 {
  /** @sqlType int */
  organizationId: number | null;
  /** @sqlType bit */
  blockUserRequests: boolean | null;
  /** @sqlType int */
  vaultsUpdated: number | null;
  /** @sqlType nvarchar */
  result: string | null;
}

export type UpdateOrganizationVaultsResults = [
  UpdateOrganizationVaults_ResultSet0[],
  UpdateOrganizationVaults_ResultSet1[],
];

export interface UpdateQueueItemResponse_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateQueueItemResponse_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateQueueItemResponse_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateQueueItemResponse_ResultSet3 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateQueueItemResponse_ResultSet4 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
}
export interface UpdateQueueItemResponse_ResultSet5 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateQueueItemResponse_ResultSet6 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType varchar */
  message: string | null;
}
export interface UpdateQueueItemResponse_ResultSet7 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateQueueItemResponseResults = [
  UpdateQueueItemResponse_ResultSet0[],
  UpdateQueueItemResponse_ResultSet1[],
  UpdateQueueItemResponse_ResultSet2[],
  UpdateQueueItemResponse_ResultSet3[],
  UpdateQueueItemResponse_ResultSet4[],
  UpdateQueueItemResponse_ResultSet5[],
  UpdateQueueItemResponse_ResultSet6[],
  UpdateQueueItemResponse_ResultSet7[],
];

export interface UpdateQueueItemToCompleted_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateQueueItemToCompleted_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType nvarchar */
  result: string | null;
}

export type UpdateQueueItemToCompletedResults = [
  UpdateQueueItemToCompleted_ResultSet0[],
  UpdateQueueItemToCompleted_ResultSet1[],
];

export interface UpdateRegionName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateRegionName_ResultSet1 {
  /** @sqlType nvarchar */
  regionName: string | null;
}

export type UpdateRegionNameResults = [
  UpdateRegionName_ResultSet0[],
  UpdateRegionName_ResultSet1[],
];

export interface UpdateRegionVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateRegionVault_ResultSet1 {
  /** @sqlType nvarchar */
  regionName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateRegionVaultResults = [
  UpdateRegionVault_ResultSet0[],
  UpdateRegionVault_ResultSet1[],
];

export interface UpdateRepositoryName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateRepositoryName_ResultSet1 {
  /** @sqlType nvarchar */
  repositoryName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type UpdateRepositoryNameResults = [
  UpdateRepositoryName_ResultSet0[],
  UpdateRepositoryName_ResultSet1[],
];

export interface UpdateRepositoryTag_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateRepositoryTag_ResultSet1 {
  /** @sqlType nvarchar */
  repositoryName: string | null;
  /** @sqlType nvarchar */
  repositoryTag: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type UpdateRepositoryTagResults = [
  UpdateRepositoryTag_ResultSet0[],
  UpdateRepositoryTag_ResultSet1[],
];

export interface UpdateRepositoryVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateRepositoryVault_ResultSet1 {
  /** @sqlType nvarchar */
  repositoryName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateRepositoryVaultResults = [
  UpdateRepositoryVault_ResultSet0[],
  UpdateRepositoryVault_ResultSet1[],
];

export interface UpdateStorageName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateStorageName_ResultSet1 {
  /** @sqlType nvarchar */
  storageName: string | null;
  /** @sqlType nvarchar */
  teamName: string | null;
}

export type UpdateStorageNameResults = [
  UpdateStorageName_ResultSet0[],
  UpdateStorageName_ResultSet1[],
];

export interface UpdateStorageVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateStorageVault_ResultSet1 {
  /** @sqlType nvarchar */
  storageName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateStorageVaultResults = [
  UpdateStorageVault_ResultSet0[],
  UpdateStorageVault_ResultSet1[],
];

export interface UpdateTeamName_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateTeamName_ResultSet1 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType nvarchar */
  organizationName: string | null;
  /** @sqlType int */
  memberCount: number | null;
}

export type UpdateTeamNameResults = [
  UpdateTeamName_ResultSet0[],
  UpdateTeamName_ResultSet1[],
];

export interface UpdateTeamVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateTeamVault_ResultSet1 {
  /** @sqlType nvarchar */
  teamName: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateTeamVaultResults = [
  UpdateTeamVault_ResultSet0[],
  UpdateTeamVault_ResultSet1[],
];

export interface UpdateUserAssignedPermissions_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserAssignedPermissions_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType nvarchar */
  permissionGroupName: string | null;
  /** @sqlType varchar */
  result: string | null;
  /** @sqlType int */
  totalTokenCount: number | null;
  /** @sqlType int */
  tokensDowngraded: number | null;
}

export type UpdateUserAssignedPermissionsResults = [
  UpdateUserAssignedPermissions_ResultSet0[],
  UpdateUserAssignedPermissions_ResultSet1[],
];

export interface UpdateUserEmail_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserEmail_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserEmailResults = [
  UpdateUserEmail_ResultSet0[],
  UpdateUserEmail_ResultSet1[],
];

export interface UpdateUserLanguage_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserLanguage_ResultSet1 {
  /** @sqlType nvarchar */
  preferredLanguage: string | null;
  /** @sqlType varchar */
  message: string | null;
}

export type UpdateUserLanguageResults = [
  UpdateUserLanguage_ResultSet0[],
  UpdateUserLanguage_ResultSet1[],
];

export interface UpdateUserPassword_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserPassword_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserPasswordResults = [
  UpdateUserPassword_ResultSet0[],
  UpdateUserPassword_ResultSet1[],
];

export interface UpdateUserTFA_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserTFA_ResultSet1 {
  /** @sqlType nvarchar */
  secret: string | null;
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  authType: string | null;
  /** @sqlType varchar */
  result: string | null;
}
export interface UpdateUserTFA_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}
export interface UpdateUserTFA_ResultSet3 {
  /** @sqlType nvarchar */
  secret: string | null;
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  authType: string | null;
  /** @sqlType varchar */
  result: string | null;
}
export interface UpdateUserTFA_ResultSet4 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserTFAResults = [
  UpdateUserTFA_ResultSet0[],
  UpdateUserTFA_ResultSet1[],
  UpdateUserTFA_ResultSet2[],
  UpdateUserTFA_ResultSet3[],
  UpdateUserTFA_ResultSet4[],
];

export interface UpdateUserToActivated_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserToActivated_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserToActivatedResults = [
  UpdateUserToActivated_ResultSet0[],
  UpdateUserToActivated_ResultSet1[],
];

export interface UpdateUserToDeactivated_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserToDeactivated_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserToDeactivatedResults = [
  UpdateUserToDeactivated_ResultSet0[],
  UpdateUserToDeactivated_ResultSet1[],
];

export interface UpdateUserVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateUserVault_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string | null;
}

export type UpdateUserVaultResults = [
  UpdateUserVault_ResultSet0[],
  UpdateUserVault_ResultSet1[],
];

// ============================================================================
// Typed Response Interfaces
// ============================================================================

export interface ActivateUserAccountTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<ActivateUserAccount_ResultSet0>,
  ];
}

export interface CancelQueueItemTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CancelQueueItem_ResultSet0>,
    ResultSet<CancelQueueItem_ResultSet1>,
    ResultSet<CancelQueueItem_ResultSet2>,
  ];
}

export interface CreateAuthenticationRequestTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateAuthenticationRequest_ResultSet0>,
  ];
}

export interface CreateBridgeTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateBridge_ResultSet0>,
    ResultSet<CreateBridge_ResultSet1>,
  ];
}

export interface CreateCephClusterTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateCephCluster_ResultSet0>,
    ResultSet<CreateCephCluster_ResultSet1>,
  ];
}

export interface CreateCephPoolTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateCephPool_ResultSet0>,
    ResultSet<CreateCephPool_ResultSet1>,
  ];
}

export interface CreateCephRbdCloneTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateCephRbdClone_ResultSet0>,
    ResultSet<CreateCephRbdClone_ResultSet1>,
  ];
}

export interface CreateCephRbdImageTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateCephRbdImage_ResultSet0>,
    ResultSet<CreateCephRbdImage_ResultSet1>,
  ];
}

export interface CreateCephRbdSnapshotTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateCephRbdSnapshot_ResultSet0>,
    ResultSet<CreateCephRbdSnapshot_ResultSet1>,
  ];
}

export interface CreateMachineTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateMachine_ResultSet0>,
    ResultSet<CreateMachine_ResultSet1>,
  ];
}

export interface CreateNewOrganizationTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateNewOrganization_ResultSet0>,
  ];
}

export interface CreateNewUserTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateNewUser_ResultSet0>,
    ResultSet<CreateNewUser_ResultSet1>,
  ];
}

export interface CreatePermissionGroupTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreatePermissionGroup_ResultSet0>,
    ResultSet<CreatePermissionGroup_ResultSet1>,
  ];
}

export interface CreatePermissionInGroupTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreatePermissionInGroup_ResultSet0>,
    ResultSet<CreatePermissionInGroup_ResultSet1>,
  ];
}

export interface CreateQueueItemTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateQueueItem_ResultSet0>,
    ResultSet<CreateQueueItem_ResultSet1>,
  ];
}

export interface CreateRegionTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateRegion_ResultSet0>,
    ResultSet<CreateRegion_ResultSet1>,
  ];
}

export interface CreateRepositoryTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateRepository_ResultSet0>,
    ResultSet<CreateRepository_ResultSet1>,
  ];
}

export interface CreateStorageTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateStorage_ResultSet0>,
    ResultSet<CreateStorage_ResultSet1>,
  ];
}

export interface CreateTeamTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateTeam_ResultSet0>,
    ResultSet<CreateTeam_ResultSet1>,
  ];
}

export interface CreateTeamMembershipTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<CreateTeamMembership_ResultSet0>,
    ResultSet<CreateTeamMembership_ResultSet1>,
  ];
}

export interface DeleteBridgeTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteBridge_ResultSet0>,
  ];
}

export interface DeleteCephClusterTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteCephCluster_ResultSet0>,
    ResultSet<DeleteCephCluster_ResultSet1>,
  ];
}

export interface DeleteCephPoolTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteCephPool_ResultSet0>,
    ResultSet<DeleteCephPool_ResultSet1>,
  ];
}

export interface DeleteCephRbdCloneTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteCephRbdClone_ResultSet0>,
    ResultSet<DeleteCephRbdClone_ResultSet1>,
  ];
}

export interface DeleteCephRbdImageTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteCephRbdImage_ResultSet0>,
    ResultSet<DeleteCephRbdImage_ResultSet1>,
  ];
}

export interface DeleteCephRbdSnapshotTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteCephRbdSnapshot_ResultSet0>,
    ResultSet<DeleteCephRbdSnapshot_ResultSet1>,
  ];
}

export interface DeleteMachineTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteMachine_ResultSet0>,
  ];
}

export interface DeletePermissionFromGroupTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeletePermissionFromGroup_ResultSet0>,
    ResultSet<DeletePermissionFromGroup_ResultSet1>,
  ];
}

export interface DeletePermissionGroupTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeletePermissionGroup_ResultSet0>,
    ResultSet<DeletePermissionGroup_ResultSet1>,
  ];
}

export interface DeleteQueueItemTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteQueueItem_ResultSet0>,
    ResultSet<DeleteQueueItem_ResultSet1>,
  ];
}

export interface DeleteRegionTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteRegion_ResultSet0>,
  ];
}

export interface DeleteRepositoryTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteRepository_ResultSet0>,
  ];
}

export interface DeleteStorageTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteStorage_ResultSet0>,
  ];
}

export interface DeleteTeamTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteTeam_ResultSet0>,
  ];
}

export interface DeleteUserFromTeamTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteUserFromTeam_ResultSet0>,
    ResultSet<DeleteUserFromTeam_ResultSet1>,
  ];
}

export interface DeleteUserRequestTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<DeleteUserRequest_ResultSet0>,
    ResultSet<DeleteUserRequest_ResultSet1>,
  ];
}

export interface ExportOrganizationDataTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<ExportOrganizationData_ResultSet0>,
    ResultSet<ExportOrganizationData_ResultSet1>,
  ];
}

export interface ForkAuthenticationRequestTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<ForkAuthenticationRequest_ResultSet0>,
    ResultSet<ForkAuthenticationRequest_ResultSet1>,
  ];
}

export interface GetAuditLogsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetAuditLogs_ResultSet0>,
    ResultSet<GetAuditLogs_ResultSet1>,
    ResultSet<GetAuditLogs_ResultSet2>,
  ];
}

export interface GetAvailableMachinesForCloneTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetAvailableMachinesForClone_ResultSet0>,
    ResultSet<GetAvailableMachinesForClone_ResultSet1>,
  ];
}

export interface GetCephClusterMachinesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephClusterMachines_ResultSet0>,
    ResultSet<GetCephClusterMachines_ResultSet1>,
  ];
}

export interface GetCephClustersTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephClusters_ResultSet0>,
    ResultSet<GetCephClusters_ResultSet1>,
  ];
}

export interface GetCephPoolsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephPools_ResultSet0>,
    ResultSet<GetCephPools_ResultSet1>,
  ];
}

export interface GetCephRbdClonesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephRbdClones_ResultSet0>,
    ResultSet<GetCephRbdClones_ResultSet1>,
  ];
}

export interface GetCephRbdImagesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephRbdImages_ResultSet0>,
    ResultSet<GetCephRbdImages_ResultSet1>,
  ];
}

export interface GetCephRbdSnapshotsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCephRbdSnapshots_ResultSet0>,
    ResultSet<GetCephRbdSnapshots_ResultSet1>,
  ];
}

export interface GetCloneMachineAssignmentValidationTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCloneMachineAssignmentValidation_ResultSet0>,
    ResultSet<GetCloneMachineAssignmentValidation_ResultSet1>,
    ResultSet<GetCloneMachineAssignmentValidation_ResultSet2>,
  ];
}

export interface GetCloneMachinesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetCloneMachines_ResultSet0>,
    ResultSet<GetCloneMachines_ResultSet1>,
  ];
}

export interface GetEntityAuditTraceTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetEntityAuditTrace_ResultSet0>,
    ResultSet<GetEntityAuditTrace_ResultSet1>,
    ResultSet<GetEntityAuditTrace_ResultSet2>,
  ];
}

export interface GetEntityHistoryTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetEntityHistory_ResultSet0>,
    ResultSet<GetEntityHistory_ResultSet1>,
    ResultSet<GetEntityHistory_ResultSet2>,
  ];
}

export interface GetLookupDataTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetLookupData_ResultSet0>,
    ResultSet<GetLookupData_ResultSet1>,
  ];
}

export interface GetMachineAssignmentStatusTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetMachineAssignmentStatus_ResultSet0>,
    ResultSet<GetMachineAssignmentStatus_ResultSet1>,
    ResultSet<GetMachineAssignmentStatus_ResultSet2>,
  ];
}

export interface GetOrganizationDashboardTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationDashboard_ResultSet0>,
    ResultSet<GetOrganizationDashboard_ResultSet1>,
    ResultSet<GetOrganizationDashboard_ResultSet2>,
    ResultSet<GetOrganizationDashboard_ResultSet3>,
    ResultSet<GetOrganizationDashboard_ResultSet4>,
    ResultSet<GetOrganizationDashboard_ResultSet5>,
    ResultSet<GetOrganizationDashboard_ResultSet6>,
    ResultSet<GetOrganizationDashboard_ResultSet7>,
    ResultSet<GetOrganizationDashboard_ResultSet8>,
    ResultSet<GetOrganizationDashboard_ResultSet9>,
    ResultSet<GetOrganizationDashboard_ResultSet10>,
    ResultSet<GetOrganizationDashboard_ResultSet11>,
    ResultSet<GetOrganizationDashboard_ResultSet12>,
    ResultSet<GetOrganizationDashboard_ResultSet13>,
    ResultSet<GetOrganizationDashboard_ResultSet14>,
    ResultSet<GetOrganizationDashboard_ResultSet15>,
    ResultSet<GetOrganizationDashboard_ResultSet16>,
  ];
}

export interface GetOrganizationPermissionGroupsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationPermissionGroups_ResultSet0>,
    ResultSet<GetOrganizationPermissionGroups_ResultSet1>,
  ];
}

export interface GetOrganizationRegionsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationRegions_ResultSet0>,
    ResultSet<GetOrganizationRegions_ResultSet1>,
  ];
}

export interface GetOrganizationTeamsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationTeams_ResultSet0>,
    ResultSet<GetOrganizationTeams_ResultSet1>,
  ];
}

export interface GetOrganizationUsersTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationUsers_ResultSet0>,
    ResultSet<GetOrganizationUsers_ResultSet1>,
    ResultSet<GetOrganizationUsers_ResultSet2>,
  ];
}

export interface GetOrganizationVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationVault_ResultSet0>,
    ResultSet<GetOrganizationVault_ResultSet1>,
  ];
}

export interface GetOrganizationVaultsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetOrganizationVaults_ResultSet0>,
    ResultSet<GetOrganizationVaults_ResultSet1>,
    ResultSet<GetOrganizationVaults_ResultSet2>,
  ];
}

export interface GetPermissionGroupDetailsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetPermissionGroupDetails_ResultSet0>,
    ResultSet<GetPermissionGroupDetails_ResultSet1>,
  ];
}

export interface GetQueueItemTraceTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetQueueItemTrace_ResultSet0>,
    ResultSet<GetQueueItemTrace_ResultSet1>,
    ResultSet<GetQueueItemTrace_ResultSet2>,
    ResultSet<GetQueueItemTrace_ResultSet3>,
    ResultSet<GetQueueItemTrace_ResultSet4>,
    ResultSet<GetQueueItemTrace_ResultSet5>,
    ResultSet<GetQueueItemTrace_ResultSet6>,
  ];
}

export interface GetQueueItemsNextTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetQueueItemsNext_ResultSet0>,
    ResultSet<GetQueueItemsNext_ResultSet1>,
    ResultSet<GetQueueItemsNext_ResultSet2>,
    ResultSet<GetQueueItemsNext_ResultSet3>,
    ResultSet<GetQueueItemsNext_ResultSet4>,
    ResultSet<GetQueueItemsNext_ResultSet5>,
    ResultSet<GetQueueItemsNext_ResultSet6>,
    ResultSet<GetQueueItemsNext_ResultSet7>,
  ];
}

export interface GetRegionBridgesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetRegionBridges_ResultSet0>,
    ResultSet<GetRegionBridges_ResultSet1>,
  ];
}

export interface GetRequestAuthenticationStatusTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetRequestAuthenticationStatus_ResultSet0>,
    ResultSet<GetRequestAuthenticationStatus_ResultSet1>,
  ];
}

export interface GetSystemConfigurationTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetSystemConfiguration_ResultSet0>,
    ResultSet<GetSystemConfiguration_ResultSet1>,
    ResultSet<GetSystemConfiguration_ResultSet2>,
  ];
}

export interface GetTeamMachinesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetTeamMachines_ResultSet0>,
    ResultSet<GetTeamMachines_ResultSet1>,
  ];
}

export interface GetTeamMembersTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetTeamMembers_ResultSet0>,
    ResultSet<GetTeamMembers_ResultSet1>,
    ResultSet<GetTeamMembers_ResultSet2>,
  ];
}

export interface GetTeamQueueItemsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetTeamQueueItems_ResultSet0>,
    ResultSet<GetTeamQueueItems_ResultSet1>,
    ResultSet<GetTeamQueueItems_ResultSet2>,
  ];
}

export interface GetTeamRepositoriesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetTeamRepositories_ResultSet0>,
    ResultSet<GetTeamRepositories_ResultSet1>,
  ];
}

export interface GetTeamStoragesTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetTeamStorages_ResultSet0>,
    ResultSet<GetTeamStorages_ResultSet1>,
  ];
}

export interface GetUserOrganizationTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetUserOrganization_ResultSet0>,
    ResultSet<GetUserOrganization_ResultSet1>,
  ];
}

export interface GetUserRequestsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetUserRequests_ResultSet0>,
    ResultSet<GetUserRequests_ResultSet1>,
  ];
}

export interface GetUserVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<GetUserVault_ResultSet0>,
    ResultSet<GetUserVault_ResultSet1>,
  ];
}

export interface ImportOrganizationDataTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<ImportOrganizationData_ResultSet0>,
    ResultSet<ImportOrganizationData_ResultSet1>,
    ResultSet<ImportOrganizationData_ResultSet2>,
    ResultSet<ImportOrganizationData_ResultSet3>,
  ];
}

export interface IsRegisteredTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<IsRegistered_ResultSet0>,
    ResultSet<IsRegistered_ResultSet1>,
  ];
}

export interface PrivilegeAuthenticationRequestTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<PrivilegeAuthenticationRequest_ResultSet0>,
    ResultSet<PrivilegeAuthenticationRequest_ResultSet1>,
    ResultSet<PrivilegeAuthenticationRequest_ResultSet2>,
  ];
}

export interface PromoteRepositoryToGrandTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<PromoteRepositoryToGrand_ResultSet0>,
  ];
}

export interface ResetBridgeAuthorizationTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<ResetBridgeAuthorization_ResultSet0>,
    ResultSet<ResetBridgeAuthorization_ResultSet1>,
  ];
}

export interface RetryFailedQueueItemTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<RetryFailedQueueItem_ResultSet0>,
    ResultSet<RetryFailedQueueItem_ResultSet1>,
  ];
}

export interface UpdateBridgeNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateBridgeName_ResultSet0>,
    ResultSet<UpdateBridgeName_ResultSet1>,
  ];
}

export interface UpdateBridgeVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateBridgeVault_ResultSet0>,
    ResultSet<UpdateBridgeVault_ResultSet1>,
  ];
}

export interface UpdateCephClusterVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateCephClusterVault_ResultSet0>,
    ResultSet<UpdateCephClusterVault_ResultSet1>,
  ];
}

export interface UpdateCephPoolVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateCephPoolVault_ResultSet0>,
    ResultSet<UpdateCephPoolVault_ResultSet1>,
  ];
}

export interface UpdateCloneMachineAssignmentsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateCloneMachineAssignments_ResultSet0>,
    ResultSet<UpdateCloneMachineAssignments_ResultSet1>,
    ResultSet<UpdateCloneMachineAssignments_ResultSet2>,
    ResultSet<UpdateCloneMachineAssignments_ResultSet3>,
  ];
}

export interface UpdateCloneMachineRemovalsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateCloneMachineRemovals_ResultSet0>,
    ResultSet<UpdateCloneMachineRemovals_ResultSet1>,
    ResultSet<UpdateCloneMachineRemovals_ResultSet2>,
  ];
}

export interface UpdateImageMachineAssignmentTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateImageMachineAssignment_ResultSet0>,
    ResultSet<UpdateImageMachineAssignment_ResultSet1>,
    ResultSet<UpdateImageMachineAssignment_ResultSet2>,
  ];
}

export interface UpdateMachineAssignedBridgeTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineAssignedBridge_ResultSet0>,
    ResultSet<UpdateMachineAssignedBridge_ResultSet1>,
  ];
}

export interface UpdateMachineCephTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineCeph_ResultSet0>,
    ResultSet<UpdateMachineCeph_ResultSet1>,
    ResultSet<UpdateMachineCeph_ResultSet2>,
  ];
}

export interface UpdateMachineClusterAssignmentTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineClusterAssignment_ResultSet0>,
    ResultSet<UpdateMachineClusterAssignment_ResultSet1>,
  ];
}

export interface UpdateMachineClusterRemovalTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineClusterRemoval_ResultSet0>,
    ResultSet<UpdateMachineClusterRemoval_ResultSet1>,
  ];
}

export interface UpdateMachineNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineName_ResultSet0>,
    ResultSet<UpdateMachineName_ResultSet1>,
  ];
}

export interface UpdateMachineStatusTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineStatus_ResultSet0>,
    ResultSet<UpdateMachineStatus_ResultSet1>,
  ];
}

export interface UpdateMachineVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateMachineVault_ResultSet0>,
    ResultSet<UpdateMachineVault_ResultSet1>,
  ];
}

export interface UpdateOrganizationBlockUserRequestsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateOrganizationBlockUserRequests_ResultSet0>,
    ResultSet<UpdateOrganizationBlockUserRequests_ResultSet1>,
  ];
}

export interface UpdateOrganizationVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateOrganizationVault_ResultSet0>,
    ResultSet<UpdateOrganizationVault_ResultSet1>,
  ];
}

export interface UpdateOrganizationVaultsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateOrganizationVaults_ResultSet0>,
    ResultSet<UpdateOrganizationVaults_ResultSet1>,
  ];
}

export interface UpdateQueueItemResponseTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateQueueItemResponse_ResultSet0>,
    ResultSet<UpdateQueueItemResponse_ResultSet1>,
    ResultSet<UpdateQueueItemResponse_ResultSet2>,
    ResultSet<UpdateQueueItemResponse_ResultSet3>,
    ResultSet<UpdateQueueItemResponse_ResultSet4>,
    ResultSet<UpdateQueueItemResponse_ResultSet5>,
    ResultSet<UpdateQueueItemResponse_ResultSet6>,
    ResultSet<UpdateQueueItemResponse_ResultSet7>,
  ];
}

export interface UpdateQueueItemToCompletedTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateQueueItemToCompleted_ResultSet0>,
    ResultSet<UpdateQueueItemToCompleted_ResultSet1>,
  ];
}

export interface UpdateRegionNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateRegionName_ResultSet0>,
    ResultSet<UpdateRegionName_ResultSet1>,
  ];
}

export interface UpdateRegionVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateRegionVault_ResultSet0>,
    ResultSet<UpdateRegionVault_ResultSet1>,
  ];
}

export interface UpdateRepositoryNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateRepositoryName_ResultSet0>,
    ResultSet<UpdateRepositoryName_ResultSet1>,
  ];
}

export interface UpdateRepositoryTagTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateRepositoryTag_ResultSet0>,
    ResultSet<UpdateRepositoryTag_ResultSet1>,
  ];
}

export interface UpdateRepositoryVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateRepositoryVault_ResultSet0>,
    ResultSet<UpdateRepositoryVault_ResultSet1>,
  ];
}

export interface UpdateStorageNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateStorageName_ResultSet0>,
    ResultSet<UpdateStorageName_ResultSet1>,
  ];
}

export interface UpdateStorageVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateStorageVault_ResultSet0>,
    ResultSet<UpdateStorageVault_ResultSet1>,
  ];
}

export interface UpdateTeamNameTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateTeamName_ResultSet0>,
    ResultSet<UpdateTeamName_ResultSet1>,
  ];
}

export interface UpdateTeamVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateTeamVault_ResultSet0>,
    ResultSet<UpdateTeamVault_ResultSet1>,
  ];
}

export interface UpdateUserAssignedPermissionsTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserAssignedPermissions_ResultSet0>,
    ResultSet<UpdateUserAssignedPermissions_ResultSet1>,
  ];
}

export interface UpdateUserEmailTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserEmail_ResultSet0>,
    ResultSet<UpdateUserEmail_ResultSet1>,
  ];
}

export interface UpdateUserLanguageTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserLanguage_ResultSet0>,
    ResultSet<UpdateUserLanguage_ResultSet1>,
  ];
}

export interface UpdateUserPasswordTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserPassword_ResultSet0>,
    ResultSet<UpdateUserPassword_ResultSet1>,
  ];
}

export interface UpdateUserTFATypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserTFA_ResultSet0>,
    ResultSet<UpdateUserTFA_ResultSet1>,
    ResultSet<UpdateUserTFA_ResultSet2>,
    ResultSet<UpdateUserTFA_ResultSet3>,
    ResultSet<UpdateUserTFA_ResultSet4>,
  ];
}

export interface UpdateUserToActivatedTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserToActivated_ResultSet0>,
    ResultSet<UpdateUserToActivated_ResultSet1>,
  ];
}

export interface UpdateUserToDeactivatedTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserToDeactivated_ResultSet0>,
    ResultSet<UpdateUserToDeactivated_ResultSet1>,
  ];
}

export interface UpdateUserVaultTypedResponse extends ApiResponseBase {
  resultSets: [
    ResultSet<UpdateUserVault_ResultSet0>,
    ResultSet<UpdateUserVault_ResultSet1>,
  ];
}

// ============================================================================
// Generated Extractor Functions
// ============================================================================
// Named 'extract*' to avoid conflicts with manual 'parse*' functions.
// These provide type-safe extraction from ApiResponseBase.

export function extractActivateUserAccount(response: ApiResponseBase): ActivateUserAccount_ResultSet0[] {
  const resultSet = response.resultSets[0] as { data: ActivateUserAccount_ResultSet0[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractActivateUserAccountFirst(response: ApiResponseBase): ActivateUserAccount_ResultSet0 | null {
  const items = extractActivateUserAccount(response);
  return items[0] ?? null;
}

export function extractCancelQueueItem(response: ApiResponseBase): CancelQueueItem_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CancelQueueItem_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCancelQueueItemFirst(response: ApiResponseBase): CancelQueueItem_ResultSet1 | null {
  const items = extractCancelQueueItem(response);
  return items[0] ?? null;
}

export function extractCreateBridge(response: ApiResponseBase): CreateBridge_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateBridge_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateBridgeFirst(response: ApiResponseBase): CreateBridge_ResultSet1 | null {
  const items = extractCreateBridge(response);
  return items[0] ?? null;
}

export function extractCreateCephCluster(response: ApiResponseBase): CreateCephCluster_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateCephCluster_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateCephClusterFirst(response: ApiResponseBase): CreateCephCluster_ResultSet1 | null {
  const items = extractCreateCephCluster(response);
  return items[0] ?? null;
}

export function extractCreateCephPool(response: ApiResponseBase): CreateCephPool_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateCephPool_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateCephPoolFirst(response: ApiResponseBase): CreateCephPool_ResultSet1 | null {
  const items = extractCreateCephPool(response);
  return items[0] ?? null;
}

export function extractCreateCephRbdClone(response: ApiResponseBase): CreateCephRbdClone_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateCephRbdClone_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateCephRbdCloneFirst(response: ApiResponseBase): CreateCephRbdClone_ResultSet1 | null {
  const items = extractCreateCephRbdClone(response);
  return items[0] ?? null;
}

export function extractCreateCephRbdImage(response: ApiResponseBase): CreateCephRbdImage_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateCephRbdImage_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateCephRbdImageFirst(response: ApiResponseBase): CreateCephRbdImage_ResultSet1 | null {
  const items = extractCreateCephRbdImage(response);
  return items[0] ?? null;
}

export function extractCreateCephRbdSnapshot(response: ApiResponseBase): CreateCephRbdSnapshot_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateCephRbdSnapshot_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateCephRbdSnapshotFirst(response: ApiResponseBase): CreateCephRbdSnapshot_ResultSet1 | null {
  const items = extractCreateCephRbdSnapshot(response);
  return items[0] ?? null;
}

export function extractCreateMachine(response: ApiResponseBase): CreateMachine_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateMachine_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateMachineFirst(response: ApiResponseBase): CreateMachine_ResultSet1 | null {
  const items = extractCreateMachine(response);
  return items[0] ?? null;
}

export function extractCreateNewOrganization(response: ApiResponseBase): CreateNewOrganization_ResultSet0[] {
  const resultSet = response.resultSets[0] as { data: CreateNewOrganization_ResultSet0[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateNewOrganizationFirst(response: ApiResponseBase): CreateNewOrganization_ResultSet0 | null {
  const items = extractCreateNewOrganization(response);
  return items[0] ?? null;
}

export function extractCreateNewUser(response: ApiResponseBase): CreateNewUser_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateNewUser_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateNewUserFirst(response: ApiResponseBase): CreateNewUser_ResultSet1 | null {
  const items = extractCreateNewUser(response);
  return items[0] ?? null;
}

export function extractCreatePermissionGroup(response: ApiResponseBase): CreatePermissionGroup_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreatePermissionGroup_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreatePermissionGroupFirst(response: ApiResponseBase): CreatePermissionGroup_ResultSet1 | null {
  const items = extractCreatePermissionGroup(response);
  return items[0] ?? null;
}

export function extractCreatePermissionInGroup(response: ApiResponseBase): CreatePermissionInGroup_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreatePermissionInGroup_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreatePermissionInGroupFirst(response: ApiResponseBase): CreatePermissionInGroup_ResultSet1 | null {
  const items = extractCreatePermissionInGroup(response);
  return items[0] ?? null;
}

export function extractCreateQueueItem(response: ApiResponseBase): CreateQueueItem_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateQueueItem_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateQueueItemFirst(response: ApiResponseBase): CreateQueueItem_ResultSet1 | null {
  const items = extractCreateQueueItem(response);
  return items[0] ?? null;
}

export function extractCreateRegion(response: ApiResponseBase): CreateRegion_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateRegion_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateRegionFirst(response: ApiResponseBase): CreateRegion_ResultSet1 | null {
  const items = extractCreateRegion(response);
  return items[0] ?? null;
}

export function extractCreateRepository(response: ApiResponseBase): CreateRepository_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateRepository_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateRepositoryFirst(response: ApiResponseBase): CreateRepository_ResultSet1 | null {
  const items = extractCreateRepository(response);
  return items[0] ?? null;
}

export function extractCreateStorage(response: ApiResponseBase): CreateStorage_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateStorage_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateStorageFirst(response: ApiResponseBase): CreateStorage_ResultSet1 | null {
  const items = extractCreateStorage(response);
  return items[0] ?? null;
}

export function extractCreateTeam(response: ApiResponseBase): CreateTeam_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateTeam_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateTeamFirst(response: ApiResponseBase): CreateTeam_ResultSet1 | null {
  const items = extractCreateTeam(response);
  return items[0] ?? null;
}

export function extractCreateTeamMembership(response: ApiResponseBase): CreateTeamMembership_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: CreateTeamMembership_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractCreateTeamMembershipFirst(response: ApiResponseBase): CreateTeamMembership_ResultSet1 | null {
  const items = extractCreateTeamMembership(response);
  return items[0] ?? null;
}

export function extractDeleteCephCluster(response: ApiResponseBase): DeleteCephCluster_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteCephCluster_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteCephClusterFirst(response: ApiResponseBase): DeleteCephCluster_ResultSet1 | null {
  const items = extractDeleteCephCluster(response);
  return items[0] ?? null;
}

export function extractDeleteCephPool(response: ApiResponseBase): DeleteCephPool_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteCephPool_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteCephPoolFirst(response: ApiResponseBase): DeleteCephPool_ResultSet1 | null {
  const items = extractDeleteCephPool(response);
  return items[0] ?? null;
}

export function extractDeleteCephRbdClone(response: ApiResponseBase): DeleteCephRbdClone_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteCephRbdClone_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteCephRbdCloneFirst(response: ApiResponseBase): DeleteCephRbdClone_ResultSet1 | null {
  const items = extractDeleteCephRbdClone(response);
  return items[0] ?? null;
}

export function extractDeleteCephRbdImage(response: ApiResponseBase): DeleteCephRbdImage_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteCephRbdImage_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteCephRbdImageFirst(response: ApiResponseBase): DeleteCephRbdImage_ResultSet1 | null {
  const items = extractDeleteCephRbdImage(response);
  return items[0] ?? null;
}

export function extractDeleteCephRbdSnapshot(response: ApiResponseBase): DeleteCephRbdSnapshot_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteCephRbdSnapshot_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteCephRbdSnapshotFirst(response: ApiResponseBase): DeleteCephRbdSnapshot_ResultSet1 | null {
  const items = extractDeleteCephRbdSnapshot(response);
  return items[0] ?? null;
}

export function extractDeletePermissionFromGroup(response: ApiResponseBase): DeletePermissionFromGroup_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeletePermissionFromGroup_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeletePermissionFromGroupFirst(response: ApiResponseBase): DeletePermissionFromGroup_ResultSet1 | null {
  const items = extractDeletePermissionFromGroup(response);
  return items[0] ?? null;
}

export function extractDeletePermissionGroup(response: ApiResponseBase): DeletePermissionGroup_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeletePermissionGroup_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeletePermissionGroupFirst(response: ApiResponseBase): DeletePermissionGroup_ResultSet1 | null {
  const items = extractDeletePermissionGroup(response);
  return items[0] ?? null;
}

export function extractDeleteQueueItem(response: ApiResponseBase): DeleteQueueItem_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteQueueItem_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteQueueItemFirst(response: ApiResponseBase): DeleteQueueItem_ResultSet1 | null {
  const items = extractDeleteQueueItem(response);
  return items[0] ?? null;
}

export function extractDeleteUserFromTeam(response: ApiResponseBase): DeleteUserFromTeam_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteUserFromTeam_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteUserFromTeamFirst(response: ApiResponseBase): DeleteUserFromTeam_ResultSet1 | null {
  const items = extractDeleteUserFromTeam(response);
  return items[0] ?? null;
}

export function extractDeleteUserRequest(response: ApiResponseBase): DeleteUserRequest_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: DeleteUserRequest_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractDeleteUserRequestFirst(response: ApiResponseBase): DeleteUserRequest_ResultSet1 | null {
  const items = extractDeleteUserRequest(response);
  return items[0] ?? null;
}

export function extractExportOrganizationData(response: ApiResponseBase): ExportOrganizationData_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: ExportOrganizationData_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractExportOrganizationDataFirst(response: ApiResponseBase): ExportOrganizationData_ResultSet1 | null {
  const items = extractExportOrganizationData(response);
  return items[0] ?? null;
}

export function extractForkAuthenticationRequest(response: ApiResponseBase): ForkAuthenticationRequest_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: ForkAuthenticationRequest_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractForkAuthenticationRequestFirst(response: ApiResponseBase): ForkAuthenticationRequest_ResultSet1 | null {
  const items = extractForkAuthenticationRequest(response);
  return items[0] ?? null;
}

export function extractGetAuditLogs(response: ApiResponseBase): GetAuditLogs_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetAuditLogs_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetAuditLogsFirst(response: ApiResponseBase): GetAuditLogs_ResultSet1 | null {
  const items = extractGetAuditLogs(response);
  return items[0] ?? null;
}

export function extractGetAvailableMachinesForClone(response: ApiResponseBase): GetAvailableMachinesForClone_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetAvailableMachinesForClone_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetAvailableMachinesForCloneFirst(response: ApiResponseBase): GetAvailableMachinesForClone_ResultSet1 | null {
  const items = extractGetAvailableMachinesForClone(response);
  return items[0] ?? null;
}

export function extractGetCephClusterMachines(response: ApiResponseBase): GetCephClusterMachines_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephClusterMachines_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephClusterMachinesFirst(response: ApiResponseBase): GetCephClusterMachines_ResultSet1 | null {
  const items = extractGetCephClusterMachines(response);
  return items[0] ?? null;
}

export function extractGetCephClusters(response: ApiResponseBase): GetCephClusters_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephClusters_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephClustersFirst(response: ApiResponseBase): GetCephClusters_ResultSet1 | null {
  const items = extractGetCephClusters(response);
  return items[0] ?? null;
}

export function extractGetCephPools(response: ApiResponseBase): GetCephPools_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephPools_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephPoolsFirst(response: ApiResponseBase): GetCephPools_ResultSet1 | null {
  const items = extractGetCephPools(response);
  return items[0] ?? null;
}

export function extractGetCephRbdClones(response: ApiResponseBase): GetCephRbdClones_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephRbdClones_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephRbdClonesFirst(response: ApiResponseBase): GetCephRbdClones_ResultSet1 | null {
  const items = extractGetCephRbdClones(response);
  return items[0] ?? null;
}

export function extractGetCephRbdImages(response: ApiResponseBase): GetCephRbdImages_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephRbdImages_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephRbdImagesFirst(response: ApiResponseBase): GetCephRbdImages_ResultSet1 | null {
  const items = extractGetCephRbdImages(response);
  return items[0] ?? null;
}

export function extractGetCephRbdSnapshots(response: ApiResponseBase): GetCephRbdSnapshots_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCephRbdSnapshots_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCephRbdSnapshotsFirst(response: ApiResponseBase): GetCephRbdSnapshots_ResultSet1 | null {
  const items = extractGetCephRbdSnapshots(response);
  return items[0] ?? null;
}

export function extractGetCloneMachineAssignmentValidation(response: ApiResponseBase): GetCloneMachineAssignmentValidation_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCloneMachineAssignmentValidation_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCloneMachineAssignmentValidationFirst(response: ApiResponseBase): GetCloneMachineAssignmentValidation_ResultSet1 | null {
  const items = extractGetCloneMachineAssignmentValidation(response);
  return items[0] ?? null;
}

export function extractGetCloneMachines(response: ApiResponseBase): GetCloneMachines_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetCloneMachines_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetCloneMachinesFirst(response: ApiResponseBase): GetCloneMachines_ResultSet1 | null {
  const items = extractGetCloneMachines(response);
  return items[0] ?? null;
}

export function extractGetEntityAuditTrace(response: ApiResponseBase): GetEntityAuditTrace_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetEntityAuditTrace_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetEntityAuditTraceFirst(response: ApiResponseBase): GetEntityAuditTrace_ResultSet1 | null {
  const items = extractGetEntityAuditTrace(response);
  return items[0] ?? null;
}

export function extractGetEntityHistory(response: ApiResponseBase): GetEntityHistory_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetEntityHistory_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetEntityHistoryFirst(response: ApiResponseBase): GetEntityHistory_ResultSet1 | null {
  const items = extractGetEntityHistory(response);
  return items[0] ?? null;
}

export function extractGetLookupData(response: ApiResponseBase): GetLookupData_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetLookupData_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetLookupDataFirst(response: ApiResponseBase): GetLookupData_ResultSet1 | null {
  const items = extractGetLookupData(response);
  return items[0] ?? null;
}

export function extractGetMachineAssignmentStatus(response: ApiResponseBase): GetMachineAssignmentStatus_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetMachineAssignmentStatus_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetMachineAssignmentStatusFirst(response: ApiResponseBase): GetMachineAssignmentStatus_ResultSet1 | null {
  const items = extractGetMachineAssignmentStatus(response);
  return items[0] ?? null;
}

export function extractGetOrganizationDashboard(response: ApiResponseBase): GetOrganizationDashboard_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationDashboard_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationDashboardFirst(response: ApiResponseBase): GetOrganizationDashboard_ResultSet1 | null {
  const items = extractGetOrganizationDashboard(response);
  return items[0] ?? null;
}

export function extractGetOrganizationPermissionGroups(response: ApiResponseBase): GetOrganizationPermissionGroups_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationPermissionGroups_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationPermissionGroupsFirst(response: ApiResponseBase): GetOrganizationPermissionGroups_ResultSet1 | null {
  const items = extractGetOrganizationPermissionGroups(response);
  return items[0] ?? null;
}

export function extractGetOrganizationRegions(response: ApiResponseBase): GetOrganizationRegions_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationRegions_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationRegionsFirst(response: ApiResponseBase): GetOrganizationRegions_ResultSet1 | null {
  const items = extractGetOrganizationRegions(response);
  return items[0] ?? null;
}

export function extractGetOrganizationTeams(response: ApiResponseBase): GetOrganizationTeams_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationTeams_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationTeamsFirst(response: ApiResponseBase): GetOrganizationTeams_ResultSet1 | null {
  const items = extractGetOrganizationTeams(response);
  return items[0] ?? null;
}

export function extractGetOrganizationUsers(response: ApiResponseBase): GetOrganizationUsers_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationUsers_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationUsersFirst(response: ApiResponseBase): GetOrganizationUsers_ResultSet1 | null {
  const items = extractGetOrganizationUsers(response);
  return items[0] ?? null;
}

export function extractGetOrganizationVault(response: ApiResponseBase): GetOrganizationVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationVaultFirst(response: ApiResponseBase): GetOrganizationVault_ResultSet1 | null {
  const items = extractGetOrganizationVault(response);
  return items[0] ?? null;
}

export function extractGetOrganizationVaults(response: ApiResponseBase): GetOrganizationVaults_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetOrganizationVaults_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetOrganizationVaultsFirst(response: ApiResponseBase): GetOrganizationVaults_ResultSet1 | null {
  const items = extractGetOrganizationVaults(response);
  return items[0] ?? null;
}

export function extractGetPermissionGroupDetails(response: ApiResponseBase): GetPermissionGroupDetails_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetPermissionGroupDetails_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetPermissionGroupDetailsFirst(response: ApiResponseBase): GetPermissionGroupDetails_ResultSet1 | null {
  const items = extractGetPermissionGroupDetails(response);
  return items[0] ?? null;
}

export function extractGetQueueItemTrace(response: ApiResponseBase): GetQueueItemTrace_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetQueueItemTrace_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetQueueItemTraceFirst(response: ApiResponseBase): GetQueueItemTrace_ResultSet1 | null {
  const items = extractGetQueueItemTrace(response);
  return items[0] ?? null;
}

export function extractGetQueueItemsNext(response: ApiResponseBase): GetQueueItemsNext_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetQueueItemsNext_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetQueueItemsNextFirst(response: ApiResponseBase): GetQueueItemsNext_ResultSet1 | null {
  const items = extractGetQueueItemsNext(response);
  return items[0] ?? null;
}

export function extractGetRegionBridges(response: ApiResponseBase): GetRegionBridges_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetRegionBridges_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetRegionBridgesFirst(response: ApiResponseBase): GetRegionBridges_ResultSet1 | null {
  const items = extractGetRegionBridges(response);
  return items[0] ?? null;
}

export function extractGetRequestAuthenticationStatus(response: ApiResponseBase): GetRequestAuthenticationStatus_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetRequestAuthenticationStatus_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetRequestAuthenticationStatusFirst(response: ApiResponseBase): GetRequestAuthenticationStatus_ResultSet1 | null {
  const items = extractGetRequestAuthenticationStatus(response);
  return items[0] ?? null;
}

export function extractGetSystemConfiguration(response: ApiResponseBase): GetSystemConfiguration_ResultSet0[] {
  const resultSet = response.resultSets[0] as { data: GetSystemConfiguration_ResultSet0[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetSystemConfigurationFirst(response: ApiResponseBase): GetSystemConfiguration_ResultSet0 | null {
  const items = extractGetSystemConfiguration(response);
  return items[0] ?? null;
}

export function extractGetTeamMachines(response: ApiResponseBase): GetTeamMachines_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetTeamMachines_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetTeamMachinesFirst(response: ApiResponseBase): GetTeamMachines_ResultSet1 | null {
  const items = extractGetTeamMachines(response);
  return items[0] ?? null;
}

export function extractGetTeamMembers(response: ApiResponseBase): GetTeamMembers_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetTeamMembers_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetTeamMembersFirst(response: ApiResponseBase): GetTeamMembers_ResultSet1 | null {
  const items = extractGetTeamMembers(response);
  return items[0] ?? null;
}

export function extractGetTeamQueueItems(response: ApiResponseBase): GetTeamQueueItems_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetTeamQueueItems_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetTeamQueueItemsFirst(response: ApiResponseBase): GetTeamQueueItems_ResultSet1 | null {
  const items = extractGetTeamQueueItems(response);
  return items[0] ?? null;
}

export function extractGetTeamRepositories(response: ApiResponseBase): GetTeamRepositories_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetTeamRepositories_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetTeamRepositoriesFirst(response: ApiResponseBase): GetTeamRepositories_ResultSet1 | null {
  const items = extractGetTeamRepositories(response);
  return items[0] ?? null;
}

export function extractGetTeamStorages(response: ApiResponseBase): GetTeamStorages_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetTeamStorages_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetTeamStoragesFirst(response: ApiResponseBase): GetTeamStorages_ResultSet1 | null {
  const items = extractGetTeamStorages(response);
  return items[0] ?? null;
}

export function extractGetUserOrganization(response: ApiResponseBase): GetUserOrganization_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetUserOrganization_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetUserOrganizationFirst(response: ApiResponseBase): GetUserOrganization_ResultSet1 | null {
  const items = extractGetUserOrganization(response);
  return items[0] ?? null;
}

export function extractGetUserRequests(response: ApiResponseBase): GetUserRequests_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetUserRequests_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetUserRequestsFirst(response: ApiResponseBase): GetUserRequests_ResultSet1 | null {
  const items = extractGetUserRequests(response);
  return items[0] ?? null;
}

export function extractGetUserVault(response: ApiResponseBase): GetUserVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: GetUserVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractGetUserVaultFirst(response: ApiResponseBase): GetUserVault_ResultSet1 | null {
  const items = extractGetUserVault(response);
  return items[0] ?? null;
}

export function extractImportOrganizationData(response: ApiResponseBase): ImportOrganizationData_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: ImportOrganizationData_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractImportOrganizationDataFirst(response: ApiResponseBase): ImportOrganizationData_ResultSet1 | null {
  const items = extractImportOrganizationData(response);
  return items[0] ?? null;
}

export function extractIsRegistered(response: ApiResponseBase): IsRegistered_ResultSet0[] {
  const resultSet = response.resultSets[0] as { data: IsRegistered_ResultSet0[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractIsRegisteredFirst(response: ApiResponseBase): IsRegistered_ResultSet0 | null {
  const items = extractIsRegistered(response);
  return items[0] ?? null;
}

export function extractPrivilegeAuthenticationRequest(response: ApiResponseBase): PrivilegeAuthenticationRequest_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: PrivilegeAuthenticationRequest_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractPrivilegeAuthenticationRequestFirst(response: ApiResponseBase): PrivilegeAuthenticationRequest_ResultSet1 | null {
  const items = extractPrivilegeAuthenticationRequest(response);
  return items[0] ?? null;
}

export function extractResetBridgeAuthorization(response: ApiResponseBase): ResetBridgeAuthorization_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: ResetBridgeAuthorization_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractResetBridgeAuthorizationFirst(response: ApiResponseBase): ResetBridgeAuthorization_ResultSet1 | null {
  const items = extractResetBridgeAuthorization(response);
  return items[0] ?? null;
}

export function extractRetryFailedQueueItem(response: ApiResponseBase): RetryFailedQueueItem_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: RetryFailedQueueItem_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractRetryFailedQueueItemFirst(response: ApiResponseBase): RetryFailedQueueItem_ResultSet1 | null {
  const items = extractRetryFailedQueueItem(response);
  return items[0] ?? null;
}

export function extractUpdateBridgeName(response: ApiResponseBase): UpdateBridgeName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateBridgeName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateBridgeNameFirst(response: ApiResponseBase): UpdateBridgeName_ResultSet1 | null {
  const items = extractUpdateBridgeName(response);
  return items[0] ?? null;
}

export function extractUpdateBridgeVault(response: ApiResponseBase): UpdateBridgeVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateBridgeVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateBridgeVaultFirst(response: ApiResponseBase): UpdateBridgeVault_ResultSet1 | null {
  const items = extractUpdateBridgeVault(response);
  return items[0] ?? null;
}

export function extractUpdateCephClusterVault(response: ApiResponseBase): UpdateCephClusterVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateCephClusterVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateCephClusterVaultFirst(response: ApiResponseBase): UpdateCephClusterVault_ResultSet1 | null {
  const items = extractUpdateCephClusterVault(response);
  return items[0] ?? null;
}

export function extractUpdateCephPoolVault(response: ApiResponseBase): UpdateCephPoolVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateCephPoolVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateCephPoolVaultFirst(response: ApiResponseBase): UpdateCephPoolVault_ResultSet1 | null {
  const items = extractUpdateCephPoolVault(response);
  return items[0] ?? null;
}

export function extractUpdateCloneMachineAssignments(response: ApiResponseBase): UpdateCloneMachineAssignments_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateCloneMachineAssignments_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateCloneMachineAssignmentsFirst(response: ApiResponseBase): UpdateCloneMachineAssignments_ResultSet1 | null {
  const items = extractUpdateCloneMachineAssignments(response);
  return items[0] ?? null;
}

export function extractUpdateCloneMachineRemovals(response: ApiResponseBase): UpdateCloneMachineRemovals_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateCloneMachineRemovals_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateCloneMachineRemovalsFirst(response: ApiResponseBase): UpdateCloneMachineRemovals_ResultSet1 | null {
  const items = extractUpdateCloneMachineRemovals(response);
  return items[0] ?? null;
}

export function extractUpdateImageMachineAssignment(response: ApiResponseBase): UpdateImageMachineAssignment_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateImageMachineAssignment_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateImageMachineAssignmentFirst(response: ApiResponseBase): UpdateImageMachineAssignment_ResultSet1 | null {
  const items = extractUpdateImageMachineAssignment(response);
  return items[0] ?? null;
}

export function extractUpdateMachineAssignedBridge(response: ApiResponseBase): UpdateMachineAssignedBridge_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineAssignedBridge_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineAssignedBridgeFirst(response: ApiResponseBase): UpdateMachineAssignedBridge_ResultSet1 | null {
  const items = extractUpdateMachineAssignedBridge(response);
  return items[0] ?? null;
}

export function extractUpdateMachineCeph(response: ApiResponseBase): UpdateMachineCeph_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineCeph_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineCephFirst(response: ApiResponseBase): UpdateMachineCeph_ResultSet1 | null {
  const items = extractUpdateMachineCeph(response);
  return items[0] ?? null;
}

export function extractUpdateMachineClusterAssignment(response: ApiResponseBase): UpdateMachineClusterAssignment_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineClusterAssignment_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineClusterAssignmentFirst(response: ApiResponseBase): UpdateMachineClusterAssignment_ResultSet1 | null {
  const items = extractUpdateMachineClusterAssignment(response);
  return items[0] ?? null;
}

export function extractUpdateMachineClusterRemoval(response: ApiResponseBase): UpdateMachineClusterRemoval_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineClusterRemoval_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineClusterRemovalFirst(response: ApiResponseBase): UpdateMachineClusterRemoval_ResultSet1 | null {
  const items = extractUpdateMachineClusterRemoval(response);
  return items[0] ?? null;
}

export function extractUpdateMachineName(response: ApiResponseBase): UpdateMachineName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineNameFirst(response: ApiResponseBase): UpdateMachineName_ResultSet1 | null {
  const items = extractUpdateMachineName(response);
  return items[0] ?? null;
}

export function extractUpdateMachineStatus(response: ApiResponseBase): UpdateMachineStatus_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineStatus_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineStatusFirst(response: ApiResponseBase): UpdateMachineStatus_ResultSet1 | null {
  const items = extractUpdateMachineStatus(response);
  return items[0] ?? null;
}

export function extractUpdateMachineVault(response: ApiResponseBase): UpdateMachineVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateMachineVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateMachineVaultFirst(response: ApiResponseBase): UpdateMachineVault_ResultSet1 | null {
  const items = extractUpdateMachineVault(response);
  return items[0] ?? null;
}

export function extractUpdateOrganizationBlockUserRequests(response: ApiResponseBase): UpdateOrganizationBlockUserRequests_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateOrganizationBlockUserRequests_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateOrganizationBlockUserRequestsFirst(response: ApiResponseBase): UpdateOrganizationBlockUserRequests_ResultSet1 | null {
  const items = extractUpdateOrganizationBlockUserRequests(response);
  return items[0] ?? null;
}

export function extractUpdateOrganizationVault(response: ApiResponseBase): UpdateOrganizationVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateOrganizationVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateOrganizationVaultFirst(response: ApiResponseBase): UpdateOrganizationVault_ResultSet1 | null {
  const items = extractUpdateOrganizationVault(response);
  return items[0] ?? null;
}

export function extractUpdateOrganizationVaults(response: ApiResponseBase): UpdateOrganizationVaults_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateOrganizationVaults_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateOrganizationVaultsFirst(response: ApiResponseBase): UpdateOrganizationVaults_ResultSet1 | null {
  const items = extractUpdateOrganizationVaults(response);
  return items[0] ?? null;
}

export function extractUpdateQueueItemResponse(response: ApiResponseBase): UpdateQueueItemResponse_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateQueueItemResponse_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateQueueItemResponseFirst(response: ApiResponseBase): UpdateQueueItemResponse_ResultSet1 | null {
  const items = extractUpdateQueueItemResponse(response);
  return items[0] ?? null;
}

export function extractUpdateQueueItemToCompleted(response: ApiResponseBase): UpdateQueueItemToCompleted_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateQueueItemToCompleted_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateQueueItemToCompletedFirst(response: ApiResponseBase): UpdateQueueItemToCompleted_ResultSet1 | null {
  const items = extractUpdateQueueItemToCompleted(response);
  return items[0] ?? null;
}

export function extractUpdateRegionName(response: ApiResponseBase): UpdateRegionName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateRegionName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateRegionNameFirst(response: ApiResponseBase): UpdateRegionName_ResultSet1 | null {
  const items = extractUpdateRegionName(response);
  return items[0] ?? null;
}

export function extractUpdateRegionVault(response: ApiResponseBase): UpdateRegionVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateRegionVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateRegionVaultFirst(response: ApiResponseBase): UpdateRegionVault_ResultSet1 | null {
  const items = extractUpdateRegionVault(response);
  return items[0] ?? null;
}

export function extractUpdateRepositoryName(response: ApiResponseBase): UpdateRepositoryName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateRepositoryName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateRepositoryNameFirst(response: ApiResponseBase): UpdateRepositoryName_ResultSet1 | null {
  const items = extractUpdateRepositoryName(response);
  return items[0] ?? null;
}

export function extractUpdateRepositoryTag(response: ApiResponseBase): UpdateRepositoryTag_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateRepositoryTag_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateRepositoryTagFirst(response: ApiResponseBase): UpdateRepositoryTag_ResultSet1 | null {
  const items = extractUpdateRepositoryTag(response);
  return items[0] ?? null;
}

export function extractUpdateRepositoryVault(response: ApiResponseBase): UpdateRepositoryVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateRepositoryVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateRepositoryVaultFirst(response: ApiResponseBase): UpdateRepositoryVault_ResultSet1 | null {
  const items = extractUpdateRepositoryVault(response);
  return items[0] ?? null;
}

export function extractUpdateStorageName(response: ApiResponseBase): UpdateStorageName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateStorageName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateStorageNameFirst(response: ApiResponseBase): UpdateStorageName_ResultSet1 | null {
  const items = extractUpdateStorageName(response);
  return items[0] ?? null;
}

export function extractUpdateStorageVault(response: ApiResponseBase): UpdateStorageVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateStorageVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateStorageVaultFirst(response: ApiResponseBase): UpdateStorageVault_ResultSet1 | null {
  const items = extractUpdateStorageVault(response);
  return items[0] ?? null;
}

export function extractUpdateTeamName(response: ApiResponseBase): UpdateTeamName_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateTeamName_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateTeamNameFirst(response: ApiResponseBase): UpdateTeamName_ResultSet1 | null {
  const items = extractUpdateTeamName(response);
  return items[0] ?? null;
}

export function extractUpdateTeamVault(response: ApiResponseBase): UpdateTeamVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateTeamVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateTeamVaultFirst(response: ApiResponseBase): UpdateTeamVault_ResultSet1 | null {
  const items = extractUpdateTeamVault(response);
  return items[0] ?? null;
}

export function extractUpdateUserAssignedPermissions(response: ApiResponseBase): UpdateUserAssignedPermissions_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserAssignedPermissions_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserAssignedPermissionsFirst(response: ApiResponseBase): UpdateUserAssignedPermissions_ResultSet1 | null {
  const items = extractUpdateUserAssignedPermissions(response);
  return items[0] ?? null;
}

export function extractUpdateUserEmail(response: ApiResponseBase): UpdateUserEmail_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserEmail_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserEmailFirst(response: ApiResponseBase): UpdateUserEmail_ResultSet1 | null {
  const items = extractUpdateUserEmail(response);
  return items[0] ?? null;
}

export function extractUpdateUserLanguage(response: ApiResponseBase): UpdateUserLanguage_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserLanguage_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserLanguageFirst(response: ApiResponseBase): UpdateUserLanguage_ResultSet1 | null {
  const items = extractUpdateUserLanguage(response);
  return items[0] ?? null;
}

export function extractUpdateUserPassword(response: ApiResponseBase): UpdateUserPassword_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserPassword_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserPasswordFirst(response: ApiResponseBase): UpdateUserPassword_ResultSet1 | null {
  const items = extractUpdateUserPassword(response);
  return items[0] ?? null;
}

export function extractUpdateUserTFA(response: ApiResponseBase): UpdateUserTFA_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserTFA_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserTFAFirst(response: ApiResponseBase): UpdateUserTFA_ResultSet1 | null {
  const items = extractUpdateUserTFA(response);
  return items[0] ?? null;
}

export function extractUpdateUserToActivated(response: ApiResponseBase): UpdateUserToActivated_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserToActivated_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserToActivatedFirst(response: ApiResponseBase): UpdateUserToActivated_ResultSet1 | null {
  const items = extractUpdateUserToActivated(response);
  return items[0] ?? null;
}

export function extractUpdateUserToDeactivated(response: ApiResponseBase): UpdateUserToDeactivated_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserToDeactivated_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserToDeactivatedFirst(response: ApiResponseBase): UpdateUserToDeactivated_ResultSet1 | null {
  const items = extractUpdateUserToDeactivated(response);
  return items[0] ?? null;
}

export function extractUpdateUserVault(response: ApiResponseBase): UpdateUserVault_ResultSet1[] {
  const resultSet = response.resultSets[1] as { data: UpdateUserVault_ResultSet1[] } | undefined;
  return resultSet?.data ?? [];
}

export function extractUpdateUserVaultFirst(response: ApiResponseBase): UpdateUserVault_ResultSet1 | null {
  const items = extractUpdateUserVault(response);
  return items[0] ?? null;
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
  | 'CreateNewOrganization'
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
  | 'ExportOrganizationData'
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
  | 'GetEntityAuditTrace'
  | 'GetEntityHistory'
  | 'GetLookupData'
  | 'GetMachineAssignmentStatus'
  | 'GetOrganizationDashboard'
  | 'GetOrganizationPermissionGroups'
  | 'GetOrganizationRegions'
  | 'GetOrganizationTeams'
  | 'GetOrganizationUsers'
  | 'GetOrganizationVault'
  | 'GetOrganizationVaults'
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
  | 'GetUserOrganization'
  | 'GetUserRequests'
  | 'GetUserVault'
  | 'ImportOrganizationData'
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
  | 'UpdateImageMachineAssignment'
  | 'UpdateMachineAssignedBridge'
  | 'UpdateMachineCeph'
  | 'UpdateMachineClusterAssignment'
  | 'UpdateMachineClusterRemoval'
  | 'UpdateMachineName'
  | 'UpdateMachineStatus'
  | 'UpdateMachineVault'
  | 'UpdateOrganizationBlockUserRequests'
  | 'UpdateOrganizationVault'
  | 'UpdateOrganizationVaults'
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
  | 'UpdateUserVault';

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
  CreateNewOrganization: CreateNewOrganizationParams;
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
  ExportOrganizationData: ExportOrganizationDataParams;
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
  GetEntityAuditTrace: GetEntityAuditTraceParams;
  GetEntityHistory: GetEntityHistoryParams;
  GetLookupData: GetLookupDataParams;
  GetMachineAssignmentStatus: GetMachineAssignmentStatusParams;
  GetOrganizationDashboard: GetOrganizationDashboardParams;
  GetOrganizationPermissionGroups: GetOrganizationPermissionGroupsParams;
  GetOrganizationRegions: GetOrganizationRegionsParams;
  GetOrganizationTeams: GetOrganizationTeamsParams;
  GetOrganizationUsers: GetOrganizationUsersParams;
  GetOrganizationVault: GetOrganizationVaultParams;
  GetOrganizationVaults: GetOrganizationVaultsParams;
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
  GetUserOrganization: GetUserOrganizationParams;
  GetUserRequests: GetUserRequestsParams;
  GetUserVault: GetUserVaultParams;
  ImportOrganizationData: ImportOrganizationDataParams;
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
  UpdateImageMachineAssignment: UpdateImageMachineAssignmentParams;
  UpdateMachineAssignedBridge: UpdateMachineAssignedBridgeParams;
  UpdateMachineCeph: UpdateMachineCephParams;
  UpdateMachineClusterAssignment: UpdateMachineClusterAssignmentParams;
  UpdateMachineClusterRemoval: UpdateMachineClusterRemovalParams;
  UpdateMachineName: UpdateMachineNameParams;
  UpdateMachineStatus: UpdateMachineStatusParams;
  UpdateMachineVault: UpdateMachineVaultParams;
  UpdateOrganizationBlockUserRequests: UpdateOrganizationBlockUserRequestsParams;
  UpdateOrganizationVault: UpdateOrganizationVaultParams;
  UpdateOrganizationVaults: UpdateOrganizationVaultsParams;
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
  CreateNewOrganization: 'Protected';
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
  ExportOrganizationData: 'Public';
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
  GetEntityAuditTrace: 'Public';
  GetEntityHistory: 'Public';
  GetLookupData: 'Public';
  GetMachineAssignmentStatus: 'Public';
  GetOrganizationDashboard: 'Public';
  GetOrganizationPermissionGroups: 'Public';
  GetOrganizationRegions: 'Public';
  GetOrganizationTeams: 'Public';
  GetOrganizationUsers: 'Public';
  GetOrganizationVault: 'Public';
  GetOrganizationVaults: 'Public';
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
  GetUserOrganization: 'Public';
  GetUserRequests: 'Public';
  GetUserVault: 'Public';
  ImportOrganizationData: 'Public';
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
  UpdateImageMachineAssignment: 'Public';
  UpdateMachineAssignedBridge: 'Public';
  UpdateMachineCeph: 'Public';
  UpdateMachineClusterAssignment: 'Public';
  UpdateMachineClusterRemoval: 'Public';
  UpdateMachineName: 'Public';
  UpdateMachineStatus: 'Public';
  UpdateMachineVault: 'Public';
  UpdateOrganizationBlockUserRequests: 'Public';
  UpdateOrganizationVault: 'Public';
  UpdateOrganizationVaults: 'Public';
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
 * Map of procedure names to their result tuple types
 */
export interface ProcedureResultsMap {
  ActivateUserAccount: ActivateUserAccountResults;
  CancelQueueItem: CancelQueueItemResults;
  CreateAuthenticationRequest: CreateAuthenticationRequestResults;
  CreateBridge: CreateBridgeResults;
  CreateCephCluster: CreateCephClusterResults;
  CreateCephPool: CreateCephPoolResults;
  CreateCephRbdClone: CreateCephRbdCloneResults;
  CreateCephRbdImage: CreateCephRbdImageResults;
  CreateCephRbdSnapshot: CreateCephRbdSnapshotResults;
  CreateMachine: CreateMachineResults;
  CreateNewOrganization: CreateNewOrganizationResults;
  CreateNewUser: CreateNewUserResults;
  CreatePermissionGroup: CreatePermissionGroupResults;
  CreatePermissionInGroup: CreatePermissionInGroupResults;
  CreateQueueItem: CreateQueueItemResults;
  CreateRegion: CreateRegionResults;
  CreateRepository: CreateRepositoryResults;
  CreateStorage: CreateStorageResults;
  CreateTeam: CreateTeamResults;
  CreateTeamMembership: CreateTeamMembershipResults;
  DeleteBridge: DeleteBridgeResults;
  DeleteCephCluster: DeleteCephClusterResults;
  DeleteCephPool: DeleteCephPoolResults;
  DeleteCephRbdClone: DeleteCephRbdCloneResults;
  DeleteCephRbdImage: DeleteCephRbdImageResults;
  DeleteCephRbdSnapshot: DeleteCephRbdSnapshotResults;
  DeleteMachine: DeleteMachineResults;
  DeletePermissionFromGroup: DeletePermissionFromGroupResults;
  DeletePermissionGroup: DeletePermissionGroupResults;
  DeleteQueueItem: DeleteQueueItemResults;
  DeleteRegion: DeleteRegionResults;
  DeleteRepository: DeleteRepositoryResults;
  DeleteStorage: DeleteStorageResults;
  DeleteTeam: DeleteTeamResults;
  DeleteUserFromTeam: DeleteUserFromTeamResults;
  DeleteUserRequest: DeleteUserRequestResults;
  ExportOrganizationData: ExportOrganizationDataResults;
  ForkAuthenticationRequest: ForkAuthenticationRequestResults;
  GetAuditLogs: GetAuditLogsResults;
  GetAvailableMachinesForClone: GetAvailableMachinesForCloneResults;
  GetCephClusterMachines: GetCephClusterMachinesResults;
  GetCephClusters: GetCephClustersResults;
  GetCephPools: GetCephPoolsResults;
  GetCephRbdClones: GetCephRbdClonesResults;
  GetCephRbdImages: GetCephRbdImagesResults;
  GetCephRbdSnapshots: GetCephRbdSnapshotsResults;
  GetCloneMachineAssignmentValidation: GetCloneMachineAssignmentValidationResults;
  GetCloneMachines: GetCloneMachinesResults;
  GetEntityAuditTrace: GetEntityAuditTraceResults;
  GetEntityHistory: GetEntityHistoryResults;
  GetLookupData: GetLookupDataResults;
  GetMachineAssignmentStatus: GetMachineAssignmentStatusResults;
  GetOrganizationDashboard: GetOrganizationDashboardResults;
  GetOrganizationPermissionGroups: GetOrganizationPermissionGroupsResults;
  GetOrganizationRegions: GetOrganizationRegionsResults;
  GetOrganizationTeams: GetOrganizationTeamsResults;
  GetOrganizationUsers: GetOrganizationUsersResults;
  GetOrganizationVault: GetOrganizationVaultResults;
  GetOrganizationVaults: GetOrganizationVaultsResults;
  GetPermissionGroupDetails: GetPermissionGroupDetailsResults;
  GetQueueItemTrace: GetQueueItemTraceResults;
  GetQueueItemsNext: GetQueueItemsNextResults;
  GetRegionBridges: GetRegionBridgesResults;
  GetRequestAuthenticationStatus: GetRequestAuthenticationStatusResults;
  GetSystemConfiguration: GetSystemConfigurationResults;
  GetTeamMachines: GetTeamMachinesResults;
  GetTeamMembers: GetTeamMembersResults;
  GetTeamQueueItems: GetTeamQueueItemsResults;
  GetTeamRepositories: GetTeamRepositoriesResults;
  GetTeamStorages: GetTeamStoragesResults;
  GetUserOrganization: GetUserOrganizationResults;
  GetUserRequests: GetUserRequestsResults;
  GetUserVault: GetUserVaultResults;
  ImportOrganizationData: ImportOrganizationDataResults;
  IsRegistered: IsRegisteredResults;
  PrivilegeAuthenticationRequest: PrivilegeAuthenticationRequestResults;
  PromoteRepositoryToGrand: PromoteRepositoryToGrandResults;
  ResetBridgeAuthorization: ResetBridgeAuthorizationResults;
  RetryFailedQueueItem: RetryFailedQueueItemResults;
  UpdateBridgeName: UpdateBridgeNameResults;
  UpdateBridgeVault: UpdateBridgeVaultResults;
  UpdateCephClusterVault: UpdateCephClusterVaultResults;
  UpdateCephPoolVault: UpdateCephPoolVaultResults;
  UpdateCloneMachineAssignments: UpdateCloneMachineAssignmentsResults;
  UpdateCloneMachineRemovals: UpdateCloneMachineRemovalsResults;
  UpdateImageMachineAssignment: UpdateImageMachineAssignmentResults;
  UpdateMachineAssignedBridge: UpdateMachineAssignedBridgeResults;
  UpdateMachineCeph: UpdateMachineCephResults;
  UpdateMachineClusterAssignment: UpdateMachineClusterAssignmentResults;
  UpdateMachineClusterRemoval: UpdateMachineClusterRemovalResults;
  UpdateMachineName: UpdateMachineNameResults;
  UpdateMachineStatus: UpdateMachineStatusResults;
  UpdateMachineVault: UpdateMachineVaultResults;
  UpdateOrganizationBlockUserRequests: UpdateOrganizationBlockUserRequestsResults;
  UpdateOrganizationVault: UpdateOrganizationVaultResults;
  UpdateOrganizationVaults: UpdateOrganizationVaultsResults;
  UpdateQueueItemResponse: UpdateQueueItemResponseResults;
  UpdateQueueItemToCompleted: UpdateQueueItemToCompletedResults;
  UpdateRegionName: UpdateRegionNameResults;
  UpdateRegionVault: UpdateRegionVaultResults;
  UpdateRepositoryName: UpdateRepositoryNameResults;
  UpdateRepositoryTag: UpdateRepositoryTagResults;
  UpdateRepositoryVault: UpdateRepositoryVaultResults;
  UpdateStorageName: UpdateStorageNameResults;
  UpdateStorageVault: UpdateStorageVaultResults;
  UpdateTeamName: UpdateTeamNameResults;
  UpdateTeamVault: UpdateTeamVaultResults;
  UpdateUserAssignedPermissions: UpdateUserAssignedPermissionsResults;
  UpdateUserEmail: UpdateUserEmailResults;
  UpdateUserLanguage: UpdateUserLanguageResults;
  UpdateUserPassword: UpdateUserPasswordResults;
  UpdateUserTFA: UpdateUserTFAResults;
  UpdateUserToActivated: UpdateUserToActivatedResults;
  UpdateUserToDeactivated: UpdateUserToDeactivatedResults;
  UpdateUserVault: UpdateUserVaultResults;
}

/**
 * Map of procedure names to their typed response interfaces
 */
export interface TypedResponseMap {
  ActivateUserAccount: ActivateUserAccountTypedResponse;
  CancelQueueItem: CancelQueueItemTypedResponse;
  CreateAuthenticationRequest: CreateAuthenticationRequestTypedResponse;
  CreateBridge: CreateBridgeTypedResponse;
  CreateCephCluster: CreateCephClusterTypedResponse;
  CreateCephPool: CreateCephPoolTypedResponse;
  CreateCephRbdClone: CreateCephRbdCloneTypedResponse;
  CreateCephRbdImage: CreateCephRbdImageTypedResponse;
  CreateCephRbdSnapshot: CreateCephRbdSnapshotTypedResponse;
  CreateMachine: CreateMachineTypedResponse;
  CreateNewOrganization: CreateNewOrganizationTypedResponse;
  CreateNewUser: CreateNewUserTypedResponse;
  CreatePermissionGroup: CreatePermissionGroupTypedResponse;
  CreatePermissionInGroup: CreatePermissionInGroupTypedResponse;
  CreateQueueItem: CreateQueueItemTypedResponse;
  CreateRegion: CreateRegionTypedResponse;
  CreateRepository: CreateRepositoryTypedResponse;
  CreateStorage: CreateStorageTypedResponse;
  CreateTeam: CreateTeamTypedResponse;
  CreateTeamMembership: CreateTeamMembershipTypedResponse;
  DeleteBridge: DeleteBridgeTypedResponse;
  DeleteCephCluster: DeleteCephClusterTypedResponse;
  DeleteCephPool: DeleteCephPoolTypedResponse;
  DeleteCephRbdClone: DeleteCephRbdCloneTypedResponse;
  DeleteCephRbdImage: DeleteCephRbdImageTypedResponse;
  DeleteCephRbdSnapshot: DeleteCephRbdSnapshotTypedResponse;
  DeleteMachine: DeleteMachineTypedResponse;
  DeletePermissionFromGroup: DeletePermissionFromGroupTypedResponse;
  DeletePermissionGroup: DeletePermissionGroupTypedResponse;
  DeleteQueueItem: DeleteQueueItemTypedResponse;
  DeleteRegion: DeleteRegionTypedResponse;
  DeleteRepository: DeleteRepositoryTypedResponse;
  DeleteStorage: DeleteStorageTypedResponse;
  DeleteTeam: DeleteTeamTypedResponse;
  DeleteUserFromTeam: DeleteUserFromTeamTypedResponse;
  DeleteUserRequest: DeleteUserRequestTypedResponse;
  ExportOrganizationData: ExportOrganizationDataTypedResponse;
  ForkAuthenticationRequest: ForkAuthenticationRequestTypedResponse;
  GetAuditLogs: GetAuditLogsTypedResponse;
  GetAvailableMachinesForClone: GetAvailableMachinesForCloneTypedResponse;
  GetCephClusterMachines: GetCephClusterMachinesTypedResponse;
  GetCephClusters: GetCephClustersTypedResponse;
  GetCephPools: GetCephPoolsTypedResponse;
  GetCephRbdClones: GetCephRbdClonesTypedResponse;
  GetCephRbdImages: GetCephRbdImagesTypedResponse;
  GetCephRbdSnapshots: GetCephRbdSnapshotsTypedResponse;
  GetCloneMachineAssignmentValidation: GetCloneMachineAssignmentValidationTypedResponse;
  GetCloneMachines: GetCloneMachinesTypedResponse;
  GetEntityAuditTrace: GetEntityAuditTraceTypedResponse;
  GetEntityHistory: GetEntityHistoryTypedResponse;
  GetLookupData: GetLookupDataTypedResponse;
  GetMachineAssignmentStatus: GetMachineAssignmentStatusTypedResponse;
  GetOrganizationDashboard: GetOrganizationDashboardTypedResponse;
  GetOrganizationPermissionGroups: GetOrganizationPermissionGroupsTypedResponse;
  GetOrganizationRegions: GetOrganizationRegionsTypedResponse;
  GetOrganizationTeams: GetOrganizationTeamsTypedResponse;
  GetOrganizationUsers: GetOrganizationUsersTypedResponse;
  GetOrganizationVault: GetOrganizationVaultTypedResponse;
  GetOrganizationVaults: GetOrganizationVaultsTypedResponse;
  GetPermissionGroupDetails: GetPermissionGroupDetailsTypedResponse;
  GetQueueItemTrace: GetQueueItemTraceTypedResponse;
  GetQueueItemsNext: GetQueueItemsNextTypedResponse;
  GetRegionBridges: GetRegionBridgesTypedResponse;
  GetRequestAuthenticationStatus: GetRequestAuthenticationStatusTypedResponse;
  GetSystemConfiguration: GetSystemConfigurationTypedResponse;
  GetTeamMachines: GetTeamMachinesTypedResponse;
  GetTeamMembers: GetTeamMembersTypedResponse;
  GetTeamQueueItems: GetTeamQueueItemsTypedResponse;
  GetTeamRepositories: GetTeamRepositoriesTypedResponse;
  GetTeamStorages: GetTeamStoragesTypedResponse;
  GetUserOrganization: GetUserOrganizationTypedResponse;
  GetUserRequests: GetUserRequestsTypedResponse;
  GetUserVault: GetUserVaultTypedResponse;
  ImportOrganizationData: ImportOrganizationDataTypedResponse;
  IsRegistered: IsRegisteredTypedResponse;
  PrivilegeAuthenticationRequest: PrivilegeAuthenticationRequestTypedResponse;
  PromoteRepositoryToGrand: PromoteRepositoryToGrandTypedResponse;
  ResetBridgeAuthorization: ResetBridgeAuthorizationTypedResponse;
  RetryFailedQueueItem: RetryFailedQueueItemTypedResponse;
  UpdateBridgeName: UpdateBridgeNameTypedResponse;
  UpdateBridgeVault: UpdateBridgeVaultTypedResponse;
  UpdateCephClusterVault: UpdateCephClusterVaultTypedResponse;
  UpdateCephPoolVault: UpdateCephPoolVaultTypedResponse;
  UpdateCloneMachineAssignments: UpdateCloneMachineAssignmentsTypedResponse;
  UpdateCloneMachineRemovals: UpdateCloneMachineRemovalsTypedResponse;
  UpdateImageMachineAssignment: UpdateImageMachineAssignmentTypedResponse;
  UpdateMachineAssignedBridge: UpdateMachineAssignedBridgeTypedResponse;
  UpdateMachineCeph: UpdateMachineCephTypedResponse;
  UpdateMachineClusterAssignment: UpdateMachineClusterAssignmentTypedResponse;
  UpdateMachineClusterRemoval: UpdateMachineClusterRemovalTypedResponse;
  UpdateMachineName: UpdateMachineNameTypedResponse;
  UpdateMachineStatus: UpdateMachineStatusTypedResponse;
  UpdateMachineVault: UpdateMachineVaultTypedResponse;
  UpdateOrganizationBlockUserRequests: UpdateOrganizationBlockUserRequestsTypedResponse;
  UpdateOrganizationVault: UpdateOrganizationVaultTypedResponse;
  UpdateOrganizationVaults: UpdateOrganizationVaultsTypedResponse;
  UpdateQueueItemResponse: UpdateQueueItemResponseTypedResponse;
  UpdateQueueItemToCompleted: UpdateQueueItemToCompletedTypedResponse;
  UpdateRegionName: UpdateRegionNameTypedResponse;
  UpdateRegionVault: UpdateRegionVaultTypedResponse;
  UpdateRepositoryName: UpdateRepositoryNameTypedResponse;
  UpdateRepositoryTag: UpdateRepositoryTagTypedResponse;
  UpdateRepositoryVault: UpdateRepositoryVaultTypedResponse;
  UpdateStorageName: UpdateStorageNameTypedResponse;
  UpdateStorageVault: UpdateStorageVaultTypedResponse;
  UpdateTeamName: UpdateTeamNameTypedResponse;
  UpdateTeamVault: UpdateTeamVaultTypedResponse;
  UpdateUserAssignedPermissions: UpdateUserAssignedPermissionsTypedResponse;
  UpdateUserEmail: UpdateUserEmailTypedResponse;
  UpdateUserLanguage: UpdateUserLanguageTypedResponse;
  UpdateUserPassword: UpdateUserPasswordTypedResponse;
  UpdateUserTFA: UpdateUserTFATypedResponse;
  UpdateUserToActivated: UpdateUserToActivatedTypedResponse;
  UpdateUserToDeactivated: UpdateUserToDeactivatedTypedResponse;
  UpdateUserVault: UpdateUserVaultTypedResponse;
}

/**
 * Map of procedure names to their primary data result set index.
 * - Value 1: Token at index 0, data at index 1 (most public procedures)
 * - Value 0: Data at index 0 (protected procedures without token rotation)
 * - Value -1: No data result sets (token-only or no results)
 */
export const PROCEDURE_PRIMARY_INDEX: Record<StoredProcedureName, number> = {
  ActivateUserAccount: 0,
  CancelQueueItem: 1,
  CreateAuthenticationRequest: -1,
  CreateBridge: 1,
  CreateCephCluster: 1,
  CreateCephPool: 1,
  CreateCephRbdClone: 1,
  CreateCephRbdImage: 1,
  CreateCephRbdSnapshot: 1,
  CreateMachine: 1,
  CreateNewOrganization: 0,
  CreateNewUser: 1,
  CreatePermissionGroup: 1,
  CreatePermissionInGroup: 1,
  CreateQueueItem: 1,
  CreateRegion: 1,
  CreateRepository: 1,
  CreateStorage: 1,
  CreateTeam: 1,
  CreateTeamMembership: 1,
  DeleteBridge: -1,
  DeleteCephCluster: 1,
  DeleteCephPool: 1,
  DeleteCephRbdClone: 1,
  DeleteCephRbdImage: 1,
  DeleteCephRbdSnapshot: 1,
  DeleteMachine: -1,
  DeletePermissionFromGroup: 1,
  DeletePermissionGroup: 1,
  DeleteQueueItem: 1,
  DeleteRegion: -1,
  DeleteRepository: -1,
  DeleteStorage: -1,
  DeleteTeam: -1,
  DeleteUserFromTeam: 1,
  DeleteUserRequest: 1,
  ExportOrganizationData: 1,
  ForkAuthenticationRequest: 1,
  GetAuditLogs: 1,
  GetAvailableMachinesForClone: 1,
  GetCephClusterMachines: 1,
  GetCephClusters: 1,
  GetCephPools: 1,
  GetCephRbdClones: 1,
  GetCephRbdImages: 1,
  GetCephRbdSnapshots: 1,
  GetCloneMachineAssignmentValidation: 1,
  GetCloneMachines: 1,
  GetEntityAuditTrace: 1,
  GetEntityHistory: 1,
  GetLookupData: 1,
  GetMachineAssignmentStatus: 1,
  GetOrganizationDashboard: 1,
  GetOrganizationPermissionGroups: 1,
  GetOrganizationRegions: 1,
  GetOrganizationTeams: 1,
  GetOrganizationUsers: 1,
  GetOrganizationVault: 1,
  GetOrganizationVaults: 1,
  GetPermissionGroupDetails: 1,
  GetQueueItemTrace: 1,
  GetQueueItemsNext: 1,
  GetRegionBridges: 1,
  GetRequestAuthenticationStatus: 1,
  GetSystemConfiguration: 0,
  GetTeamMachines: 1,
  GetTeamMembers: 1,
  GetTeamQueueItems: 1,
  GetTeamRepositories: 1,
  GetTeamStorages: 1,
  GetUserOrganization: 1,
  GetUserRequests: 1,
  GetUserVault: 1,
  ImportOrganizationData: 1,
  IsRegistered: 0,
  PrivilegeAuthenticationRequest: 1,
  PromoteRepositoryToGrand: -1,
  ResetBridgeAuthorization: 1,
  RetryFailedQueueItem: 1,
  UpdateBridgeName: 1,
  UpdateBridgeVault: 1,
  UpdateCephClusterVault: 1,
  UpdateCephPoolVault: 1,
  UpdateCloneMachineAssignments: 1,
  UpdateCloneMachineRemovals: 1,
  UpdateImageMachineAssignment: 1,
  UpdateMachineAssignedBridge: 1,
  UpdateMachineCeph: 1,
  UpdateMachineClusterAssignment: 1,
  UpdateMachineClusterRemoval: 1,
  UpdateMachineName: 1,
  UpdateMachineStatus: 1,
  UpdateMachineVault: 1,
  UpdateOrganizationBlockUserRequests: 1,
  UpdateOrganizationVault: 1,
  UpdateOrganizationVaults: 1,
  UpdateQueueItemResponse: 1,
  UpdateQueueItemToCompleted: 1,
  UpdateRegionName: 1,
  UpdateRegionVault: 1,
  UpdateRepositoryName: 1,
  UpdateRepositoryTag: 1,
  UpdateRepositoryVault: 1,
  UpdateStorageName: 1,
  UpdateStorageVault: 1,
  UpdateTeamName: 1,
  UpdateTeamVault: 1,
  UpdateUserAssignedPermissions: 1,
  UpdateUserEmail: 1,
  UpdateUserLanguage: 1,
  UpdateUserPassword: 1,
  UpdateUserTFA: 1,
  UpdateUserToActivated: 1,
  UpdateUserToDeactivated: 1,
  UpdateUserVault: 1,
} as const;

/**
 * Get parameter type for a specific procedure
 */
export type ParamsFor<T extends StoredProcedureName> = ProcedureParamsMap[T];

/**
 * Get result tuple type for a specific procedure
 */
export type ResultsFor<T extends StoredProcedureName> = ProcedureResultsMap[T];

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
// GUID Parameter Metadata (for runtime validation)
// ============================================================================

/**
 * Map of procedure names to their uniqueidentifier (GUID) parameters.
 * Used by sanitizeGuidParams() to convert empty strings to undefined,
 * since middleware rejects empty strings for GUID validation but allows undefined.
 */
export const PROCEDURE_GUID_PARAMS: Partial<Record<StoredProcedureName, readonly string[]>> = {
  CancelQueueItem: ['taskId'] as const,
  CreateRepository: ['repositoryGuid'] as const,
  DeleteQueueItem: ['taskId'] as const,
  GetEntityHistory: ['credential'] as const,
  GetQueueItemTrace: ['taskId'] as const,
  GetQueueItemsNext: ['bridgeCredential'] as const,
  GetTeamQueueItems: ['taskId'] as const,
  RetryFailedQueueItem: ['taskId'] as const,
  UpdateQueueItemResponse: ['taskId'] as const,
  UpdateQueueItemToCompleted: ['taskId'] as const,
} as const;

// ============================================================================
// Schema Metadata
// ============================================================================

export const API_SCHEMA_METADATA = {
  version: '3.0.0',
  generated: '2026-01-19T19:58:11.2376335Z',
  procedureCount: 115,
} as const;


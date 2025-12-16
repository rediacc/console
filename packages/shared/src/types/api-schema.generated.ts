/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: middleware/AppData/stored-procedures.json
 * Generated at: 2025-12-15T13:53:44Z
 * Schema version: 3.0.0
 * Schema generated: 2025-12-12T14:56:10.0016831Z
 *
 * To regenerate, run: ./go deploy prep
 * Or directly: ./_scripts/console-schema.sh --generate
 *
 * This file provides compile-time type safety for API calls by ensuring
 * parameter names and types match the middleware's expected schema.
 */

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
  subscriptionPlan?: string;
  /** @sqlType nvarchar */
  companyVaultDefaults: string;
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
  /** @sqlType char */
  activationCode: string;
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
  vaultContent: string;
}

export interface CreateRepositoryParams {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  repositoryName: string;
  /** @sqlType nvarchar */
  vaultContent: string;
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

export type ExportCompanyDataParams = Record<string, never>;

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

export type GetUserCompanyParams = Record<string, never>;

export type GetUserRequestsParams = Record<string, never>;

export type GetUserVaultParams = Record<string, never>;

export interface ImportCompanyDataParams {
  /** @sqlType nvarchar */
  companyDataJson: string;
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
  result: string;
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
  result: string;
  /** @sqlType nvarchar */
  previousStatus: string | null;
  /** @sqlType varchar */
  newStatus: string;
}
export interface CancelQueueItem_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType nvarchar */
  previousStatus: string | null;
  /** @sqlType varchar */
  newStatus: string;
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
  vaultCompany: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType nvarchar */
  preferredLanguage: string | null;
  /** @sqlType varchar */
  authenticationStatus: string;
}

export type CreateAuthenticationRequestResults = [CreateAuthenticationRequest_ResultSet0[]];

export interface CreateBridge_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateBridge_ResultSet1 {
  /** @sqlType int */
  bridgeId: number;
  /** @sqlType nvarchar */
  name: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  name: string;
}

export type CreateMachineResults = [
  CreateMachine_ResultSet0[],
  CreateMachine_ResultSet1[],
];

export interface CreateNewCompany_ResultSet0 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType nvarchar */
  languagePreference: string | null;
  /** @sqlType char */
  activationCode: string | null;
  /** @sqlType nvarchar */
  companyName: string | null;
}

export type CreateNewCompanyResults = [CreateNewCompany_ResultSet0[]];

export interface CreateNewUser_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface CreateNewUser_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType nvarchar */
  languagePreference: string | null;
  /** @sqlType char */
  activationCode: string | null;
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
  permissionGroupName: string;
  /** @sqlType varchar */
  result: string;
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
  permissionName: string;
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType varchar */
  result: string;
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
  taskId: string;
  /** @sqlType datetimeoffset */
  time: string;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType uniqueidentifier */
  bridgeCredential: string;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType int */
  priority: number;
  /** @sqlType nvarchar */
  createdBy: string;
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
  name: string;
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
  name: string;
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
  name: string;
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
  name: string;
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
  result: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  message: string;
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
  companyId: number | null;
  /** @sqlType nvarchar */
  removedPermissionName: string | null;
  /** @sqlType varchar */
  result: string;
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
  result: string;
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
  result: string;
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
  result: string;
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
  result: string;
}

export type DeleteUserRequestResults = [
  DeleteUserRequest_ResultSet0[],
  DeleteUserRequest_ResultSet1[],
];

export interface ExportCompanyData_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ExportCompanyData_ResultSet1 {
  /** @sqlType nvarchar */
  exportData: string | null;
}

export type ExportCompanyDataResults = [
  ExportCompanyData_ResultSet0[],
  ExportCompanyData_ResultSet1[],
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
  vaultCompany: string | null;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType varchar */
  authenticationStatus: string;
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
  entity: string;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string;
}
export interface GetAuditLogs_ResultSet2 {
  /** @sqlType nvarchar */
  entity: string;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string;
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
  machineName: string;
  /** @sqlType varchar */
  status: string;
  /** @sqlType varchar */
  description: string;
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
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  clusterName: string;
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
  clusterName: string;
  /** @sqlType int */
  vaultVersion: number;
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
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType int */
  vaultVersion: number;
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
  clusterName: string;
  /** @sqlType datetime2 */
  snapshotCreatedDate: string;
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
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType int */
  imageGuid: number;
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
  snapshotName: string;
  /** @sqlType nvarchar */
  imageName: string;
  /** @sqlType nvarchar */
  poolName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  clusterName: string;
  /** @sqlType datetime2 */
  createdDate: string;
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
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType nvarchar */
  validationStatus: string | null;
  /** @sqlType nvarchar */
  currentAssignment: string | null;
  /** @sqlType nvarchar */
  message: string | null;
}
export interface GetCloneMachineAssignmentValidation_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCloneMachineAssignmentValidation_ResultSet2 {
  /** @sqlType nvarchar */
  machineName: string | null;
  /** @sqlType varchar */
  validationStatus: string;
  /** @sqlType nvarchar */
  currentAssignment: string | null;
  /** @sqlType nvarchar */
  message: string;
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
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType int */
  assignmentId: number;
}

export type GetCloneMachinesResults = [
  GetCloneMachines_ResultSet0[],
  GetCloneMachines_ResultSet1[],
];

export interface GetCompanyDashboardJson_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyDashboardJson_ResultSet1 {
  /** @sqlType nvarchar */
  subscriptionAndResourcesJson: string | null;
}
export interface GetCompanyDashboardJson_ResultSet2 {
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
  /** @sqlType int */
  isTrial: number;
}

export type GetCompanyDashboardJsonResults = [
  GetCompanyDashboardJson_ResultSet0[],
  GetCompanyDashboardJson_ResultSet1[],
  GetCompanyDashboardJson_ResultSet2[],
];

export interface GetCompanyDataGraphJson_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyDataGraphJson_ResultSet1 {
  /** @sqlType nvarchar */
  companyDataGraph: string | null;
}

export type GetCompanyDataGraphJsonResults = [
  GetCompanyDataGraphJson_ResultSet0[],
  GetCompanyDataGraphJson_ResultSet1[],
];

export interface GetCompanyPermissionGroups_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyPermissionGroups_ResultSet1 {
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType int */
  userCount: number | null;
  /** @sqlType int */
  permissionCount: number | null;
  /** @sqlType nvarchar */
  permissions: string | null;
}

export type GetCompanyPermissionGroupsResults = [
  GetCompanyPermissionGroups_ResultSet0[],
  GetCompanyPermissionGroups_ResultSet1[],
];

export interface GetCompanyRegions_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyRegions_ResultSet1 {
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  bridgeCount: number | null;
}

export type GetCompanyRegionsResults = [
  GetCompanyRegions_ResultSet0[],
  GetCompanyRegions_ResultSet1[],
];

export interface GetCompanyTeams_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyTeams_ResultSet1 {
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  isMember: number;
  /** @sqlType int */
  memberCount: number | null;
  /** @sqlType int */
  machineCount: number | null;
  /** @sqlType int */
  repositoryCount: number | null;
  /** @sqlType int */
  storageCount: number | null;
}

export type GetCompanyTeamsResults = [
  GetCompanyTeams_ResultSet0[],
  GetCompanyTeams_ResultSet1[],
];

export interface GetCompanyUsers_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyUsers_ResultSet1 {
  /** @sqlType nvarchar */
  userEmail: string;
  /** @sqlType bit */
  activated: boolean;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  permissionsName: string;
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  teamCount: number | null;
}
export interface GetCompanyUsers_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string;
  /** @sqlType bit */
  activated: boolean;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType int */
  vaultContent: number | null;
  /** @sqlType nvarchar */
  permissionsName: string;
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  teamCount: number | null;
}

export type GetCompanyUsersResults = [
  GetCompanyUsers_ResultSet0[],
  GetCompanyUsers_ResultSet1[],
  GetCompanyUsers_ResultSet2[],
];

export interface GetCompanyVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyVault_ResultSet1 {
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType uniqueidentifier */
  companyCredential: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
}

export type GetCompanyVaultResults = [
  GetCompanyVault_ResultSet0[],
  GetCompanyVault_ResultSet1[],
];

export interface GetCompanyVaults_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetCompanyVaults_ResultSet1 {
  /** @sqlType nvarchar */
  entityType: string;
  /** @sqlType int */
  entityId: number;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType int */
  vaultId: number;
  /** @sqlType nvarchar */
  vaultName: string;
  /** @sqlType uniqueidentifier */
  credential: string;
  /** @sqlType int */
  chunkOrder: number;
  /** @sqlType int */
  version: number;
  /** @sqlType varbinary */
  encryptedVault: string;
  /** @sqlType nvarchar */
  decryptedVault: string | null;
}
export interface GetCompanyVaults_ResultSet2 {
  /** @sqlType int */
  bridgeId: number;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType uniqueidentifier */
  requestToken: string | null;
  /** @sqlType int */
  hasRequestToken: number;
}

export type GetCompanyVaultsResults = [
  GetCompanyVaults_ResultSet0[],
  GetCompanyVaults_ResultSet1[],
  GetCompanyVaults_ResultSet2[],
];

export interface GetEntityAuditTrace_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetEntityAuditTrace_ResultSet1 {
  /** @sqlType nvarchar */
  action: string;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType nvarchar */
  performedBy: string | null;
  /** @sqlType datetime2 */
  timestamp: string;
  /** @sqlType varchar */
  actionType: string;
  /** @sqlType nvarchar */
  timeAgo: string | null;
  /** @sqlType varchar */
  iconHint: string;
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
  /** @sqlType int */
  hasOlderRecords: number;
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
  auditId: number;
  /** @sqlType nvarchar */
  entity: string;
  /** @sqlType int */
  entityId: number;
  /** @sqlType nvarchar */
  entityName: string | null;
  /** @sqlType nvarchar */
  action: string;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType int */
  userId: number | null;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType datetime2 */
  timestamp: string;
  /** @sqlType varchar */
  actionCategory: string;
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
export interface GetMachineAssignmentStatus_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
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

export interface GetPermissionGroupDetails_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetPermissionGroupDetails_ResultSet1 {
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType nvarchar */
  permissionName: string;
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
  taskId: string;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType datetimeoffset */
  createdTime: string;
  /** @sqlType datetimeoffset */
  assignedTime: string | null;
  /** @sqlType datetimeoffset */
  lastAssigned: string | null;
  /** @sqlType int */
  retryCount: number;
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
  machineName: string;
  /** @sqlType int */
  machineId: number | null;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType int */
  bridgeId: number;
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType int */
  regionId: number;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType int */
  teamId: number | null;
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  companyId: number;
  /** @sqlType nvarchar */
  createdBy: string;
  /** @sqlType int */
  createdByUserId: number;
  /** @sqlType varchar */
  healthStatus: string;
  /** @sqlType int */
  isStale: number;
  /** @sqlType int */
  isStalePending: number;
  /** @sqlType int */
  canBeCancelled: number;
}
export interface GetQueueItemTrace_ResultSet2 {
  /** @sqlType varchar */
  vaultType: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  hasContent: number;
}
export interface GetQueueItemTrace_ResultSet3 {
  /** @sqlType varchar */
  vaultType: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  hasContent: number;
}
export interface GetQueueItemTrace_ResultSet4 {
  /** @sqlType nvarchar */
  action: string;
  /** @sqlType nvarchar */
  details: string | null;
  /** @sqlType datetime2 */
  timestamp: string;
  /** @sqlType nvarchar */
  actionByUser: string | null;
  /** @sqlType int */
  secondsSincePrevious: number | null;
}
export interface GetQueueItemTrace_ResultSet5 {
  /** @sqlType uniqueidentifier */
  taskId: string;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType datetimeoffset */
  createdTime: string;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  secondsDifference: number | null;
  /** @sqlType varchar */
  relativePosition: string;
  /** @sqlType nvarchar */
  createdBy: string;
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
  maxConcurrentTasks: number;
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
  companyLicense: string | null;
  /** @sqlType nvarchar */
  companyCredential: string | null;
  /** @sqlType nvarchar */
  bridgeCredential: string | null;
}
export interface GetQueueItemsNext_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string;
  /** @sqlType datetimeoffset */
  time: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType datetimeoffset */
  assigned: string | null;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  retryCount: number;
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
  taskId: string;
  /** @sqlType datetimeoffset */
  time: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType datetimeoffset */
  assigned: string | null;
  /** @sqlType nvarchar */
  status: string;
  /** @sqlType int */
  priority: number | null;
  /** @sqlType int */
  retryCount: number;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet5 {
  /** @sqlType varchar */
  result: string;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet6 {
  /** @sqlType varchar */
  result: string;
  /** @sqlType nvarchar */
  subscriptionTier: string | null;
  /** @sqlType int */
  maxConcurrentTasks: number | null;
  /** @sqlType int */
  currentlyProcessingTasks: number | null;
}
export interface GetQueueItemsNext_ResultSet7 {
  /** @sqlType varchar */
  result: string;
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
  bridgeName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  bridgeCredentialsVersion: number | null;
  /** @sqlType nvarchar */
  bridgeCredentials: string | null;
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType int */
  machineCount: number | null;
  /** @sqlType int */
  hasAccess: number;
  /** @sqlType nvarchar */
  bridgeUserEmail: string | null;
  /** @sqlType varchar */
  managementMode: string;
  /** @sqlType int */
  isGlobalBridge: number;
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
  authenticationStatus: string;
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
  configKey: string;
  /** @sqlType nvarchar */
  configValue: string | null;
  /** @sqlType nvarchar */
  configDescription: string | null;
  /** @sqlType datetime */
  modifiedDate: string | null;
}
export interface GetSystemConfiguration_ResultSet2 {
  /** @sqlType nvarchar */
  configKey: string;
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
  machineName: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  vaultStatus: string | null;
  /** @sqlType datetime2 */
  vaultStatusTime: string | null;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType int */
  queueCount: number | null;
  /** @sqlType nvarchar */
  machineGuid: string | null;
  /** @sqlType nvarchar */
  cephClusterName: string | null;
  /** @sqlType varchar */
  assignmentStatus: string;
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
  userEmail: string;
  /** @sqlType bit */
  activated: boolean;
  /** @sqlType nvarchar */
  teams: string | null;
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType bit */
  isMember: boolean | null;
  /** @sqlType bit */
  hasAccess: boolean | null;
}
export interface GetTeamMembers_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string;
  /** @sqlType bit */
  activated: boolean;
  /** @sqlType nvarchar */
  teams: string | null;
  /** @sqlType nvarchar */
  companyName: string;
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
  vaultVersion: number;
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
  healthStatus: string;
  /** @sqlType int */
  canBeCancelled: number;
  /** @sqlType int */
  hasResponse: number;
  /** @sqlType nvarchar */
  createdBy: string | null;
  /** @sqlType int */
  retryCount: number | null;
  /** @sqlType datetimeoffset */
  lastRetryAt: string | null;
  /** @sqlType nvarchar */
  lastFailureReason: string | null;
  /** @sqlType int */
  permanentlyFailed: number;
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
  repositoryName: string;
  /** @sqlType uniqueidentifier */
  repositoryGuid: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType uniqueidentifier */
  grandGuid: string;
  /** @sqlType uniqueidentifier */
  parentGuid: string | null;
  /** @sqlType int */
  repositoryNetworkId: number;
  /** @sqlType nvarchar */
  repositoryNetworkMode: string;
  /** @sqlType nvarchar */
  repositoryTag: string;
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
  storageName: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  teamName: string;
}

export type GetTeamStoragesResults = [
  GetTeamStorages_ResultSet0[],
  GetTeamStorages_ResultSet1[],
];

export interface GetUserCompany_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetUserCompany_ResultSet1 {
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType int */
  teamCount: number | null;
  /** @sqlType int */
  regionCount: number | null;
  /** @sqlType int */
  userCount: number | null;
}

export type GetUserCompanyResults = [
  GetUserCompany_ResultSet0[],
  GetUserCompany_ResultSet1[],
];

export interface GetUserRequests_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface GetUserRequests_ResultSet1 {
  /** @sqlType int */
  requestId: number;
  /** @sqlType nvarchar */
  userEmail: string;
  /** @sqlType nvarchar */
  sessionName: string;
  /** @sqlType nvarchar */
  ipAddress: string | null;
  /** @sqlType nvarchar */
  userAgent: string | null;
  /** @sqlType datetimeoffset */
  createdAt: string;
  /** @sqlType datetimeoffset */
  lastActivity: string;
  /** @sqlType bit */
  isActive: boolean;
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
  vaultVersion: number;
  /** @sqlType uniqueidentifier */
  userCredential: string | null;
}

export type GetUserVaultResults = [
  GetUserVault_ResultSet0[],
  GetUserVault_ResultSet1[],
];

export interface ImportCompanyData_ResultSet0 {
  /** @sqlType varchar */
  message: string;
  /** @sqlType int */
  importedCount: number;
  /** @sqlType int */
  skippedCount: number;
  /** @sqlType int */
  errorCount: number;
}
export interface ImportCompanyData_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface ImportCompanyData_ResultSet2 {
  /** @sqlType int */
  importedCount: number;
  /** @sqlType int */
  skippedCount: number;
  /** @sqlType int */
  errorCount: number;
  /** @sqlType varchar */
  result: string;
}
export interface ImportCompanyData_ResultSet3 {
  /** @sqlType int */
  importedCount: number | null;
  /** @sqlType int */
  skippedCount: number | null;
  /** @sqlType int */
  errorCount: number | null;
  /** @sqlType varchar */
  result: string;
}

export type ImportCompanyDataResults = [
  ImportCompanyData_ResultSet0[],
  ImportCompanyData_ResultSet1[],
  ImportCompanyData_ResultSet2[],
  ImportCompanyData_ResultSet3[],
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
  result: string;
  /** @sqlType bit */
  isAuthorized: boolean | null;
  /** @sqlType bit */
  hasTFAEnabled: boolean | null;
}
export interface PrivilegeAuthenticationRequest_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType int */
  isAuthorized: number;
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
  result: string;
  /** @sqlType varchar */
  managementMode: string;
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
  result: string;
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
  bridgeName: string;
  /** @sqlType nvarchar */
  regionName: string;
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
  bridgeName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
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
  message: string;
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
  message: string;
}

export type UpdateCephPoolVaultResults = [
  UpdateCephPoolVault_ResultSet0[],
  UpdateCephPoolVault_ResultSet1[],
];

export interface UpdateCloneMachineAssignments_ResultSet0 {
  /** @sqlType varchar */
  message: string;
}
export interface UpdateCloneMachineAssignments_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
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
  /** @sqlType varchar */
  message: string;
}
export interface UpdateCloneMachineRemovals_ResultSet1 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
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

export interface UpdateCompanyBlockUserRequests_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCompanyBlockUserRequests_ResultSet1 {
  /** @sqlType int */
  companyId: number | null;
  /** @sqlType bit */
  blockUserRequests: boolean | null;
  /** @sqlType int */
  deactivatedTokenCount: number | null;
  /** @sqlType nvarchar */
  result: string | null;
}

export type UpdateCompanyBlockUserRequestsResults = [
  UpdateCompanyBlockUserRequests_ResultSet0[],
  UpdateCompanyBlockUserRequests_ResultSet1[],
];

export interface UpdateCompanyVault_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCompanyVault_ResultSet1 {
  /** @sqlType nvarchar */
  companyName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
}

export type UpdateCompanyVaultResults = [
  UpdateCompanyVault_ResultSet0[],
  UpdateCompanyVault_ResultSet1[],
];

export interface UpdateCompanyVaults_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateCompanyVaults_ResultSet1 {
  /** @sqlType int */
  companyId: number | null;
  /** @sqlType int */
  blockUserRequests: number;
  /** @sqlType int */
  vaultsUpdated: number | null;
  /** @sqlType nvarchar */
  result: string | null;
}

export type UpdateCompanyVaultsResults = [
  UpdateCompanyVaults_ResultSet0[],
  UpdateCompanyVaults_ResultSet1[],
];

export interface UpdateImageMachineAssignment_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateImageMachineAssignment_ResultSet1 {
  /** @sqlType varchar */
  message: string;
}
export interface UpdateImageMachineAssignment_ResultSet2 {
  /** @sqlType varchar */
  message: string;
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
  machineName: string;
  /** @sqlType nvarchar */
  teamName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  regionName: string;
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
  message: string;
}
export interface UpdateMachineCeph_ResultSet2 {
  /** @sqlType varchar */
  message: string;
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
  message: string;
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
  message: string;
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
  machineName: string;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  teamName: string;
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
  machineName: string;
  /** @sqlType int */
  vaultVersion: number;
  /** @sqlType nvarchar */
  vaultContent: string | null;
  /** @sqlType nvarchar */
  vaultStatus: string | null;
  /** @sqlType datetime2 */
  vaultStatusTime: string | null;
  /** @sqlType nvarchar */
  bridgeName: string;
  /** @sqlType nvarchar */
  regionName: string;
  /** @sqlType nvarchar */
  teamName: string;
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
  machineName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
}

export type UpdateMachineVaultResults = [
  UpdateMachineVault_ResultSet0[],
  UpdateMachineVault_ResultSet1[],
];

export interface UpdateQueueItemResponse_ResultSet0 {
  /** @sqlType uniqueidentifier */
  nextRequestToken: string | null;
}
export interface UpdateQueueItemResponse_ResultSet1 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType varchar */
  message: string;
}
export interface UpdateQueueItemResponse_ResultSet2 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType varchar */
  message: string;
}
export interface UpdateQueueItemResponse_ResultSet3 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType varchar */
  message: string;
}
export interface UpdateQueueItemResponse_ResultSet4 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
}
export interface UpdateQueueItemResponse_ResultSet5 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType varchar */
  message: string;
}
export interface UpdateQueueItemResponse_ResultSet6 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
  /** @sqlType varchar */
  message: string;
}
export interface UpdateQueueItemResponse_ResultSet7 {
  /** @sqlType uniqueidentifier */
  taskId: string | null;
  /** @sqlType varchar */
  result: string;
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
  regionName: string;
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
  regionName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
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
  repositoryName: string;
  /** @sqlType nvarchar */
  teamName: string;
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
  repositoryName: string;
  /** @sqlType nvarchar */
  repositoryTag: string;
  /** @sqlType nvarchar */
  teamName: string;
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
  repositoryName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
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
  storageName: string;
  /** @sqlType nvarchar */
  teamName: string;
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
  storageName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
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
  teamName: string;
  /** @sqlType nvarchar */
  companyName: string;
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
  teamName: string;
  /** @sqlType int */
  vaultVersion: number | null;
  /** @sqlType varchar */
  result: string;
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
  userEmail: string;
  /** @sqlType nvarchar */
  permissionGroupName: string;
  /** @sqlType varchar */
  result: string;
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
  userEmail: string;
  /** @sqlType varchar */
  result: string;
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
  message: string;
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
  result: string;
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
  authType: string;
  /** @sqlType varchar */
  result: string;
}
export interface UpdateUserTFA_ResultSet2 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string;
}
export interface UpdateUserTFA_ResultSet3 {
  /** @sqlType nvarchar */
  secret: string | null;
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  authType: string;
  /** @sqlType varchar */
  result: string;
}
export interface UpdateUserTFA_ResultSet4 {
  /** @sqlType nvarchar */
  userEmail: string | null;
  /** @sqlType varchar */
  result: string;
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
  userEmail: string;
  /** @sqlType varchar */
  result: string;
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
  userEmail: string;
  /** @sqlType varchar */
  result: string;
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
  result: string;
}

export type UpdateUserVaultResults = [
  UpdateUserVault_ResultSet0[],
  UpdateUserVault_ResultSet1[],
];

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
  CreateNewCompany: CreateNewCompanyResults;
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
  ExportCompanyData: ExportCompanyDataResults;
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
  GetCompanyDashboardJson: GetCompanyDashboardJsonResults;
  GetCompanyDataGraphJson: GetCompanyDataGraphJsonResults;
  GetCompanyPermissionGroups: GetCompanyPermissionGroupsResults;
  GetCompanyRegions: GetCompanyRegionsResults;
  GetCompanyTeams: GetCompanyTeamsResults;
  GetCompanyUsers: GetCompanyUsersResults;
  GetCompanyVault: GetCompanyVaultResults;
  GetCompanyVaults: GetCompanyVaultsResults;
  GetEntityAuditTrace: GetEntityAuditTraceResults;
  GetEntityHistory: GetEntityHistoryResults;
  GetLookupData: GetLookupDataResults;
  GetMachineAssignmentStatus: GetMachineAssignmentStatusResults;
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
  GetUserCompany: GetUserCompanyResults;
  GetUserRequests: GetUserRequestsResults;
  GetUserVault: GetUserVaultResults;
  ImportCompanyData: ImportCompanyDataResults;
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
  UpdateCompanyBlockUserRequests: UpdateCompanyBlockUserRequestsResults;
  UpdateCompanyVault: UpdateCompanyVaultResults;
  UpdateCompanyVaults: UpdateCompanyVaultsResults;
  UpdateImageMachineAssignment: UpdateImageMachineAssignmentResults;
  UpdateMachineAssignedBridge: UpdateMachineAssignedBridgeResults;
  UpdateMachineCeph: UpdateMachineCephResults;
  UpdateMachineClusterAssignment: UpdateMachineClusterAssignmentResults;
  UpdateMachineClusterRemoval: UpdateMachineClusterRemovalResults;
  UpdateMachineName: UpdateMachineNameResults;
  UpdateMachineStatus: UpdateMachineStatusResults;
  UpdateMachineVault: UpdateMachineVaultResults;
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
  generated: '2025-12-12T14:56:10.0016831Z',
  procedureCount: 116,
} as const;

// ============================================================================
// Domain Types (Generated from entity-metadata.json)
// ============================================================================

// Enum/Union Types

/** Type of machine assignment in Ceph */
export type MachineAssignmentType =
  | 'AVAILABLE'
  | 'CLUSTER'
  | 'IMAGE'
  | 'CLONE';

/** Status of a queue item */
export type QueueStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'PROCESSING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'FAILED';

/** Health status of a queue item */
export type QueueHealthStatus =
  | 'PENDING'
  | 'ACTIVE'
  | 'STALE'
  | 'STALE_PENDING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'FAILED'
  | 'UNKNOWN';

/** Relative position in queue */
export type QueueRelativePosition =
  | 'Before'
  | 'After'
  | 'Current';

// Interface Types

/** Status of machine assignment */
export interface MachineAssignmentStatus {
  assignmentType: MachineAssignmentType;
  assignmentDetails: string;
  status?: string;
}

/** Bridge authorization token */
export interface BridgeAuthorizationToken {
  authToken?: string;
}

/** Plugin container information */
export interface PluginContainer {
  name: string;
  image: string;
  status: string;
  [key: string]: unknown;
}

/** Permission definition */
export interface Permission {
  permissionName: string;
  description?: string;
}

/** User request/session information */
export interface UserRequest {
  requestId: number;
  userEmail: string;
  sessionName: string;
  ipAddress: string | null;
  userAgent: string | null;
  createdAt: string;
  lastActivity: string;
  isActive: boolean;
  parentRequestId: number | null;
  permissionsName: string;
  expirationTime: string | null;
}

/** Ceph machine assignment status */
export interface CephMachineAssignmentStatus {
  machineName: string;
  teamName: string;
  assignmentType: string;
  assignmentDetails: string;
  status: string;
}

/** Available machine for Ceph assignment */
export interface CephAvailableMachine {
  machineName: string;
  status: string;
  description: string;
  bridgeName?: string;
  regionName?: string;
}

/** Machine assigned to a Ceph clone */
export interface CephCloneMachine {
  machineName: string;
  bridgeName: string;
  assignmentId: number;
}

/** Validation result for Ceph machine assignment */
export interface CephMachineAssignmentValidation {
  machineName: string;
  isValid: boolean;
  error?: string;
}

/** Company profile information */
export interface CompanyProfile extends Record<string, unknown> {
  companyName?: string;
  Plan?: string;
  planCode?: string;
}

/** Company subscription details */
export interface CompanySubscription extends Record<string, unknown> {
  edition: string;
  planCode: string;
  quantity: number;
  totalActivePurchases: number;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  status: string;
  isActive: number;
  isTrial: number;
  isExpiringSoon?: number;
}

/** Company resource limit */
export interface CompanyResourceLimit {
  resourceType: string;
  resourceLimit: number;
  activeSubscriptionTier: string;
  currentUsage: number;
  isLimitReached: number;
  usagePercentage: number;
}

/** Company account health status */
export interface CompanyAccountHealth {
  resourcesAtLimit: number;
  resourcesNearLimit: number;
  subscriptionStatus: 'Critical' | 'Warning' | 'Good';
  upgradeRecommendation: string;
}

/** Company feature access flags */
export interface CompanyFeatureAccess {
  hasAdvancedAnalytics: number;
  hasPrioritySupport: number;
  hasDedicatedAccount: number;
  hasCustomBranding: number;
}

/** Company plan limits */
export interface CompanyPlanLimits {
  maxActiveJobs: number;
  maxReservedJobs: number;
  jobTimeoutHours: number;
  maxRepoSize: number;
  planCode: string;
}

/** Detailed subscription information */
export interface CompanySubscriptionDetail {
  planCode: string;
  quantity: number;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  status: string;
  isTrial: number;
}

/** Team-level queue issue */
export interface QueueTeamIssue {
  teamName: string;
  totalItems: number;
  pendingItems: number;
  activeItems: number;
  staleItems: number;
}

/** Machine-level queue issue */
export interface QueueMachineIssue {
  machineName: string;
  teamName: string;
  bridgeName: string;
  totalItems: number;
  pendingItems: number;
  activeItems: number;
  staleItems: number;
}

/** Company-wide queue statistics */
export interface CompanyQueueStats {
  pendingCount: number;
  assignedCount: number;
  processingCount: number;
  activeCount: number;
  completedCount: number;
  cancelledCount: number;
  failedCount: number;
  totalCount: number;
  staleCount: number;
  completedToday: number;
  cancelledToday: number;
  failedToday: number;
  createdToday: number;
  oldestPendingAgeMinutes: number;
  avgPendingAgeMinutes: number;
  highestPriorityPending: number | null;
  highPriorityPending: number | null;
  normalPriorityPending: number | null;
  lowPriorityPending: number | null;
  hasStaleItems: number;
  hasOldPendingItems: number;
  teamIssues?: QueueTeamIssue[];
  machineIssues?: QueueMachineIssue[];
}

/** Ceph usage breakdown by team */
export interface CephTeamBreakdown {
  teamName: string;
  totalMachines: number;
  availableMachines: number;
  clusterMachines: number;
  imageMachines: number;
  cloneMachines: number;
}

/** Company-wide Ceph statistics */
export interface CompanyCephStats {
  total_machines: number;
  available_machines: number;
  cluster_assigned_machines: number;
  image_assigned_machines: number;
  clone_assigned_machines: number;
  truly_available_machines: number;
  available_percentage: number;
  cluster_percentage: number;
  image_percentage: number;
  clone_percentage: number;
  total_clusters?: number;
  active_clusters?: number;
  avg_machines_per_cluster?: number;
  team_breakdown: CephTeamBreakdown[];
}

/** Complete dashboard data for a company */
export interface CompanyDashboardData {
  companyInfo: CompanyProfile;
  activeSubscription: CompanySubscription | null;
  resources: CompanyResourceLimit[];
  accountHealth: CompanyAccountHealth | null;
  featureAccess: CompanyFeatureAccess | null;
  planLimits: CompanyPlanLimits | null;
  queueStats?: CompanyQueueStats;
  cephStats?: CompanyCephStats;
  allActiveSubscriptions?: CompanySubscriptionDetail[];
}

/** Company vault details */
export interface CompanyVaultDetails {
  vault: string;
  vaultVersion: number;
  companyCredential?: string | null;
}

/** Company vault record */
export interface CompanyVaultRecord extends Record<string, unknown> {
  entityType?: string;
  entityIdentifier?: string;
  vaultContent?: string;
  vaultVersion?: number;
  vaultType?: string;
}

/** Company vault collections */
export interface CompanyVaultCollections {
  vaults: CompanyVaultRecord[];
  bridgesWithRequestToken: CompanyVaultRecord[];
}

/** Result of company vault update */
export interface CompanyVaultUpdateResult {
  totalUpdated: number;
  failedCount: number;
}

/** Result of company data import */
export interface CompanyImportResult {
  importedCount: number;
  skippedCount: number;
  errorCount: number;
}

/** Result of blocking user requests */
export interface CompanyBlockUserRequestsResult {
  deactivatedCount: number;
}

/** Bridge option for dropdowns */
export interface CompanyDropdownBridge {
  value: string;
  label: string;
  machineCount?: number;
}

/** Region option for dropdowns */
export interface CompanyDropdownRegion {
  regionName: string;
  bridges: CompanyDropdownBridge[];
}

/** Machine option for dropdowns */
export interface CompanyDropdownMachine {
  value: string;
  label: string;
  bridgeName: string;
  regionName: string;
}

/** Complete dropdown data for UI */
export interface CompanyDropdownData {
  teams: Array<{ value: string; label: string }>;
  allTeams: Array<{ value: string; label: string; memberCount: number }>;
  regions: Array<{ value: string; label: string; bridgeCount: number }>;
  machines?: string[];
  bridges?: Array<{ value: string; label: string }>;
  bridgesByRegion: CompanyDropdownRegion[];
  machinesByTeam: Array<{ teamName: string; machines: CompanyDropdownMachine[] }>;
  users: Array<{ value: string; label: string; status: string }>;
  permissionGroups: Array<{ value: string; label: string; userCount: number; permissionCount: number }>;
  permissions: Array<{ name: string; value: string }>;
  subscriptionPlans: Array<{ value: string; label: string; description: string }>;
  requestContext?: string;
  currentUser?: string;
  userRole?: string;
}

/** Node in company data graph */
export interface CompanyGraphNode extends Record<string, unknown> {
  nodeType: string;
  nodeId: string;
  name: string;
  label: string;
  hierarchyLevel: string;
}

/** Relationship in company data graph */
export interface CompanyGraphRelationship {
  source: string;
  target: string;
  relationshipType: string;
  label: string;
}

/** Complete company data graph for visualization */
export interface CompanyDataGraph {
  metadata: { currentUser: string; userRole: string; generatedAt: string; dataFormat: string };
  nodes: Record<string, CompanyGraphNode[]>;
  relationships: Record<string, CompanyGraphRelationship[]>;
  summary: { userTeamCount: number; accessibleMachines: number; totalQueueItems: number; isAdministrator: boolean; companyName: string };
}

/** Queue trace log entry */
export interface QueueTraceLog {
  timestamp?: string;
  action?: string;
  status?: string;
  message?: string;
  details?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

/** Queue vault snapshot */
export interface QueueVaultSnapshot {
  hasContent: boolean;
  vaultVersion?: number;
  vaultContent?: string | Record<string, unknown>;
  updatedAt?: string;
}

/** Queue position entry */
export interface QueuePositionEntry {
  taskId: string;
  status: QueueStatus;
  createdTime: string;
  relativePosition: QueueRelativePosition | string;
}

/** Queue machine statistics */
export interface QueueMachineStats {
  currentQueueDepth: number;
  activeProcessingCount: number;
  maxConcurrentTasks?: number;
}

/** Queue plan information */
export interface QueuePlanInfo {
  planId?: string;
  planName?: string;
  planDescription?: string;
  expiresAt?: string;
}

/** Queue trace summary */
export interface QueueTraceSummary {
  taskId?: string;
  status?: QueueStatus;
  healthStatus?: QueueHealthStatus;
  progress?: string;
  consoleOutput?: string;
  errorMessage?: string;
  lastFailureReason?: string;
  priority?: number;
  retryCount?: number;
  ageInMinutes?: number;
  hasResponse?: boolean;
  teamName?: string;
  machineName?: string;
  bridgeName?: string;
  createdTime?: string;
  updatedTime?: string;
}

/** Complete queue trace information */
export interface QueueTrace {
  summary: QueueTraceSummary | null;
  queueDetails: GetTeamQueueItems_ResultSet1 | null;
  traceLogs: QueueTraceLog[];
  vaultContent: QueueVaultSnapshot | null;
  responseVaultContent: QueueVaultSnapshot | null;
  queuePosition: QueuePositionEntry[];
  machineStats: QueueMachineStats | null;
  planInfo: QueuePlanInfo | null;
}

/** Queue list with statistics */
export interface QueueListResult {
  items: GetTeamQueueItems_ResultSet1[];
  statistics: GetTeamQueueItems_ResultSet2 | null;
}

/** User vault information */
export interface UserVault {
  vault: string;
  vaultVersion: number;
  userCredential: string | null;
}

/** Authentication request status */
export interface AuthRequestStatus {
  isTFAEnabled: boolean;
  isAuthorized: boolean;
  authenticationStatus: string;
}

/** Authentication login result */
export interface AuthLoginResult {
  isAuthorized: boolean;
  authenticationStatus: string;
  vaultCompany: string | null;
  companyName: string | null;
  company?: string | null;
  preferredLanguage?: string | null;
}

/** Enable TFA response */
export interface EnableTfaResponse {
  secret?: string;
  userEmail?: string;
  authType?: string;
  result?: string;
}

/** Verify TFA result */
export interface VerifyTfaResult {
  isAuthorized: boolean;
  result?: string;
  hasTFAEnabled?: boolean;
}

/** Fork session credentials */
export interface ForkSessionCredentials {
  requestToken: string | null;
  nextRequestToken: string | null;
  parentRequestId: number | null;
}

/** Audit trace record */
export interface AuditTraceRecord {
  action: string;
  details: string;
  performedBy: string;
  timestamp: string;
  actionType: string;
  timeAgo: string;
  iconHint: string;
}

/** Audit trace summary */
export interface AuditTraceSummary {
  entityType: string;
  entityName: string;
  entityId: number;
  totalAuditRecords: number;
  visibleAuditRecords: number;
  oldestVisibleActivity: string | null;
  lastActivity: string | null;
  hasAccess: boolean;
  isAdmin: boolean;
  subscriptionTier: string;
  auditRetentionDays: number;
  hasOlderRecords: boolean;
  relatedCount: number;
}

/** Audit trace response */
export interface AuditTraceResponse {
  records: AuditTraceRecord[];
  summary: AuditTraceSummary;
}

// Type Aliases

/** Company export data type */
export type CompanyExportData = Record<string, unknown>;


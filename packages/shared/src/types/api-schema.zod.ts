/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Zod schemas for runtime validation of API responses.
 * Generated alongside api-schema.generated.ts for fail-fast validation.
 *
 * Generated at: 2026-01-14T10:37:46Z
 * Schema version: 3.0.0
 *
 * To regenerate, run: ./go deploy prep
 */

import { z } from 'zod';

// ============================================================================
// Result Set Schemas
// ============================================================================

export const ActivateUserAccount_ResultSet0Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const CancelQueueItem_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CancelQueueItem_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  previousStatus: z.string().nullish(),
  newStatus: z.string().nullish(),
});
export const CancelQueueItem_ResultSet2Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  previousStatus: z.string().nullish(),
  newStatus: z.string().nullish(),
});

export const CreateAuthenticationRequest_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
  tokenExpiration: z.string().nullish(),
  expirationHours: z.number().nullish(),
  vaultOrganization: z.string().nullish(),
  isAuthorized: z.boolean().nullish(),
  preferredLanguage: z.string().nullish(),
  authenticationStatus: z.string().nullish(),
});

export const CreateBridge_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateBridge_ResultSet1Schema = z.object({
  bridgeId: z.number().nullish(),
  name: z.string().nullish(),
});

export const CreateCephCluster_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateCephCluster_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const CreateCephPool_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateCephPool_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const CreateCephRbdClone_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateCephRbdClone_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const CreateCephRbdImage_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateCephRbdImage_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const CreateCephRbdSnapshot_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateCephRbdSnapshot_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const CreateMachine_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateMachine_ResultSet1Schema = z.object({
  name: z.string().nullish(),
});

export const CreateNewOrganization_ResultSet0Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
  languagePreference: z.string().nullish(),
  activationCode: z.string().nullish(),
  organizationName: z.string().nullish(),
});

export const CreateNewUser_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateNewUser_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
  languagePreference: z.string().nullish(),
  activationCode: z.number().nullish(),
  createdBy: z.string().nullish(),
});

export const CreatePermissionGroup_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreatePermissionGroup_ResultSet1Schema = z.object({
  permissionGroupName: z.string().nullish(),
  result: z.string().nullish(),
});

export const CreatePermissionInGroup_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreatePermissionInGroup_ResultSet1Schema = z.object({
  permissionName: z.string().nullish(),
  permissionGroupName: z.string().nullish(),
  result: z.string().nullish(),
});

export const CreateQueueItem_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateQueueItem_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  time: z.string().nullish(),
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  bridgeCredential: z.string().nullish(),
  status: z.string().nullish(),
  priority: z.number().nullish(),
  createdBy: z.string().nullish(),
  highPriorityInfo: z.string().nullish(),
});

export const CreateRegion_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateRegion_ResultSet1Schema = z.object({
  name: z.string().nullish(),
});

export const CreateRepository_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateRepository_ResultSet1Schema = z.object({
  name: z.string().nullish(),
});

export const CreateStorage_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateStorage_ResultSet1Schema = z.object({
  name: z.string().nullish(),
});

export const CreateTeam_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateTeam_ResultSet1Schema = z.object({
  name: z.string().nullish(),
});

export const CreateTeamMembership_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const CreateTeamMembership_ResultSet1Schema = z.object({
  addedUserEmail: z.string().nullish(),
  teamName: z.string().nullish(),
  result: z.string().nullish(),
});

export const DeleteBridge_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeleteCephCluster_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteCephCluster_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const DeleteCephPool_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteCephPool_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const DeleteCephRbdClone_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteCephRbdClone_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const DeleteCephRbdImage_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteCephRbdImage_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const DeleteCephRbdSnapshot_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteCephRbdSnapshot_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const DeleteMachine_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeletePermissionFromGroup_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeletePermissionFromGroup_ResultSet1Schema = z.object({
  permissionsId: z.number().nullish(),
  permissionGroupName: z.string().nullish(),
  organizationId: z.number().nullish(),
  removedPermissionName: z.string().nullish(),
  result: z.string().nullish(),
});

export const DeletePermissionGroup_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeletePermissionGroup_ResultSet1Schema = z.object({
  removedPermissionGroupName: z.string().nullish(),
  result: z.string().nullish(),
});

export const DeleteQueueItem_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteQueueItem_ResultSet1Schema = z.object({
  result: z.string().nullish(),
});

export const DeleteRegion_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeleteRepository_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeleteStorage_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeleteTeam_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const DeleteUserFromTeam_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteUserFromTeam_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  teamName: z.string().nullish(),
  result: z.string().nullish(),
});

export const DeleteUserRequest_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const DeleteUserRequest_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  sessionName: z.string().nullish(),
  result: z.string().nullish(),
});

export const ExportOrganizationData_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const ExportOrganizationData_ResultSet1Schema = z.object({
  exportData: z.string().nullish(),
});

export const ForkAuthenticationRequest_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const ForkAuthenticationRequest_ResultSet1Schema = z.object({
  nextRequestToken: z.string().nullish(),
  tokenExpiration: z.string().nullish(),
  expirationHours: z.number().nullish(),
  vaultOrganization: z.string().nullish(),
  isAuthorized: z.boolean().nullish(),
  authenticationStatus: z.string().nullish(),
  parentRequestId: z.number().nullish(),
});

export const GetAuditLogs_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetAuditLogs_ResultSet1Schema = z.object({
  entity: z.string().nullish(),
  entityName: z.string().nullish(),
  action: z.string().nullish(),
  details: z.string().nullish(),
  actionByUser: z.string().nullish(),
  timestamp: z.string().nullish(),
});
export const GetAuditLogs_ResultSet2Schema = z.object({
  entity: z.string().nullish(),
  entityName: z.string().nullish(),
  action: z.string().nullish(),
  details: z.string().nullish(),
  actionByUser: z.string().nullish(),
  timestamp: z.string().nullish(),
});

export const GetAvailableMachinesForClone_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetAvailableMachinesForClone_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  status: z.string().nullish(),
  description: z.string().nullish(),
});

export const GetCephClusterMachines_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephClusterMachines_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  teamName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  regionName: z.string().nullish(),
  clusterName: z.string().nullish(),
  assignedDate: z.string().nullish(),
});

export const GetCephClusters_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephClusters_ResultSet1Schema = z.object({
  clusterName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  assignedMachineCount: z.number().nullish(),
  poolCount: z.number().nullish(),
  clusterVault: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const GetCephPools_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephPools_ResultSet1Schema = z.object({
  poolName: z.string().nullish(),
  teamName: z.string().nullish(),
  clusterName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  rbdImageCount: z.number().nullish(),
  poolVault: z.string().nullish(),
  poolGuid: z.string().nullish(),
});

export const GetCephRbdClones_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephRbdClones_ResultSet1Schema = z.object({
  cloneName: z.string().nullish(),
  snapshotName: z.string().nullish(),
  imageName: z.string().nullish(),
  poolName: z.string().nullish(),
  teamName: z.string().nullish(),
  clusterName: z.string().nullish(),
  snapshotCreatedDate: z.string().nullish(),
  vaultContent: z.string().nullish(),
  snapshotGuid: z.string().nullish(),
});

export const GetCephRbdImages_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephRbdImages_ResultSet1Schema = z.object({
  imageName: z.string().nullish(),
  poolName: z.string().nullish(),
  teamName: z.string().nullish(),
  clusterName: z.string().nullish(),
  machineName: z.string().nullish(),
  imageGuid: z.number().nullish(),
  snapshotCount: z.number().nullish(),
  vaultContent: z.string().nullish(),
});

export const GetCephRbdSnapshots_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCephRbdSnapshots_ResultSet1Schema = z.object({
  snapshotName: z.string().nullish(),
  imageName: z.string().nullish(),
  poolName: z.string().nullish(),
  teamName: z.string().nullish(),
  clusterName: z.string().nullish(),
  createdDate: z.string().nullish(),
  cloneCount: z.number().nullish(),
  vaultContent: z.string().nullish(),
  snapshotGuid: z.string().nullish(),
});

export const GetCloneMachineAssignmentValidation_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCloneMachineAssignmentValidation_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  validationStatus: z.string().nullish(),
  currentAssignment: z.string().nullish(),
  message: z.string().nullish(),
});
export const GetCloneMachineAssignmentValidation_ResultSet2Schema = z.object({
  machineName: z.string().nullish(),
  validationStatus: z.string().nullish(),
  currentAssignment: z.string().nullish(),
  message: z.string().nullish(),
});

export const GetCloneMachines_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetCloneMachines_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  assignmentId: z.number().nullish(),
});

export const GetEntityAuditTrace_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetEntityAuditTrace_ResultSet1Schema = z.object({
  action: z.string().nullish(),
  details: z.string().nullish(),
  performedBy: z.string().nullish(),
  timestamp: z.string().nullish(),
  actionType: z.string().nullish(),
  timeAgo: z.string().nullish(),
  iconHint: z.string().nullish(),
});
export const GetEntityAuditTrace_ResultSet2Schema = z.object({
  entityType: z.string().nullish(),
  entityName: z.string().nullish(),
  entityId: z.number().nullish(),
  totalAuditRecords: z.number().nullish(),
  visibleAuditRecords: z.number().nullish(),
  oldestVisibleActivity: z.string().nullish(),
  lastActivity: z.string().nullish(),
  hasAccess: z.boolean().nullish(),
  isAdmin: z.boolean().nullish(),
  subscriptionTier: z.string().nullish(),
  auditRetentionDays: z.number().nullish(),
  hasOlderRecords: z.boolean().nullish(),
  relatedCount: z.number().nullish(),
});

export const GetEntityHistory_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetEntityHistory_ResultSet1Schema = z.object({
  auditId: z.number().nullish(),
  entity: z.string().nullish(),
  entityId: z.number().nullish(),
  entityName: z.string().nullish(),
  action: z.string().nullish(),
  details: z.string().nullish(),
  userId: z.number().nullish(),
  actionByUser: z.string().nullish(),
  timestamp: z.string().nullish(),
  actionCategory: z.string().nullish(),
});
export const GetEntityHistory_ResultSet2Schema = z.object({
  entityType: z.string().nullish(),
  entityName: z.string().nullish(),
  entityCredential: z.string().nullish(),
  totalAuditRecords: z.number().nullish(),
  firstActivity: z.string().nullish(),
  lastActivity: z.string().nullish(),
});

export const GetLookupData_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetLookupData_ResultSet1Schema = z.object({
  dropdownValues: z.string().nullish(),
});

export const GetMachineAssignmentStatus_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetMachineAssignmentStatus_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  teamName: z.string().nullish(),
  assignmentType: z.string().nullish(),
  assignmentDetails: z.string().nullish(),
  status: z.string().nullish(),
});
export const GetMachineAssignmentStatus_ResultSet2Schema = z.object({
  machineName: z.string().nullish(),
  teamName: z.string().nullish(),
  assignmentType: z.string().nullish(),
  assignmentDetails: z.string().nullish(),
  status: z.string().nullish(),
});

export const GetOrganizationDashboard_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationDashboard_ResultSet1Schema = z.object({
  organizationName: z.string().nullish(),
  organizationGuid: z.string().nullish(),
  planCode: z.string().nullish(),
});
export const GetOrganizationDashboard_ResultSet2Schema = z.object({
  planCode: z.string().nullish(),
  quantity: z.number().nullish(),
  totalActivePurchases: z.number().nullish(),
  startDate: z.string().nullish(),
  endDate: z.string().nullish(),
  daysRemaining: z.number().nullish(),
  status: z.string().nullish(),
  isActive: z.boolean().nullish(),
  isTrial: z.boolean().nullish(),
  isExpiringSoon: z.boolean().nullish(),
});
export const GetOrganizationDashboard_ResultSet3Schema = z.object({
  planCode: z.string().nullish(),
  quantity: z.number().nullish(),
  startDate: z.string().nullish(),
  endDate: z.string().nullish(),
  daysRemaining: z.number().nullish(),
  status: z.string().nullish(),
  isTrial: z.boolean().nullish(),
});
export const GetOrganizationDashboard_ResultSet4Schema = z.object({
  resourceType: z.string().nullish(),
  resourceLimit: z.number().nullish(),
  activeSubscriptionTier: z.string().nullish(),
  currentUsage: z.number().nullish(),
  isLimitReached: z.boolean().nullish(),
  usagePercentage: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet5Schema = z.object({
  resourcesAtLimit: z.number().nullish(),
  resourcesNearLimit: z.number().nullish(),
  subscriptionStatus: z.string().nullish(),
  upgradeRecommendation: z.string().nullish(),
});
export const GetOrganizationDashboard_ResultSet6Schema = z.object({
  hasAdvancedAnalytics: z.boolean().nullish(),
  hasPrioritySupport: z.boolean().nullish(),
  hasDedicatedAccount: z.boolean().nullish(),
  hasCustomBranding: z.boolean().nullish(),
  ceph: z.boolean().nullish(),
  auditLog: z.boolean().nullish(),
  advancedQueue: z.boolean().nullish(),
});
export const GetOrganizationDashboard_ResultSet7Schema = z.object({
  planCode: z.string().nullish(),
  machineLimit: z.number().nullish(),
  repositoryLimit: z.number().nullish(),
  userLimit: z.number().nullish(),
  maxActiveJobs: z.number().nullish(),
  maxReservedJobs: z.number().nullish(),
  jobTimeoutHours: z.number().nullish(),
  maxRepositorySize: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet8Schema = z.object({
  pendingCount: z.number().nullish(),
  assignedCount: z.number().nullish(),
  processingCount: z.number().nullish(),
  activeCount: z.number().nullish(),
  completedCount: z.number().nullish(),
  cancelledCount: z.number().nullish(),
  failedCount: z.number().nullish(),
  totalCount: z.number().nullish(),
  staleCount: z.number().nullish(),
  stalePendingCount: z.number().nullish(),
  completedToday: z.number().nullish(),
  cancelledToday: z.number().nullish(),
  createdToday: z.number().nullish(),
  itemsWithRetries: z.number().nullish(),
  maxRetryCount: z.number().nullish(),
  avgRetryCount: z.number().nullish(),
  oldestPendingAgeMinutes: z.number().nullish(),
  avgPendingAgeMinutes: z.number().nullish(),
  highestPriorityPending: z.number().nullish(),
  highPriorityPending: z.number().nullish(),
  normalPriorityPending: z.number().nullish(),
  lowPriorityPending: z.number().nullish(),
  hasStaleItems: z.boolean().nullish(),
  hasOldPendingItems: z.boolean().nullish(),
});
export const GetOrganizationDashboard_ResultSet9Schema = z.object({
  totalUserItems: z.number().nullish(),
  userPendingItems: z.number().nullish(),
  userActiveItems: z.number().nullish(),
  userCompletedToday: z.number().nullish(),
  userHighPriorityActive: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet10Schema = z.object({
  teamName: z.string().nullish(),
  totalItems: z.number().nullish(),
  pendingItems: z.number().nullish(),
  activeItems: z.number().nullish(),
  staleItems: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet11Schema = z.object({
  machineName: z.string().nullish(),
  teamName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  totalItems: z.number().nullish(),
  pendingItems: z.number().nullish(),
  activeItems: z.number().nullish(),
  staleItems: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet12Schema = z.object({
  userName: z.string().nullish(),
  totalItems: z.number().nullish(),
  activeItems: z.number().nullish(),
  completedToday: z.number().nullish(),
  highPriorityActive: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet13Schema = z.object({
  totalMachines: z.number().nullish(),
  availableMachines: z.number().nullish(),
  clusterAssignedMachines: z.number().nullish(),
  imageAssignedMachines: z.number().nullish(),
  cloneAssignedMachines: z.number().nullish(),
  trulyAvailableMachines: z.number().nullish(),
  availablePercentage: z.number().nullish(),
  clusterPercentage: z.number().nullish(),
  imagePercentage: z.number().nullish(),
  clonePercentage: z.number().nullish(),
  totalClusters: z.number().nullish(),
  activeClusters: z.number().nullish(),
  avgMachinesPerCluster: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet14Schema = z.object({
  totalMachines: z.number().nullish(),
  availableMachines: z.number().nullish(),
  clusterAssignedMachines: z.number().nullish(),
  imageAssignedMachines: z.number().nullish(),
  cloneAssignedMachines: z.number().nullish(),
  trulyAvailableMachines: z.number().nullish(),
  availablePercentage: z.number().nullish(),
  clusterPercentage: z.number().nullish(),
  imagePercentage: z.number().nullish(),
  clonePercentage: z.number().nullish(),
  totalClusters: z.number().nullish(),
  activeClusters: z.number().nullish(),
  avgMachinesPerCluster: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet15Schema = z.object({
  teamName: z.string().nullish(),
  totalMachines: z.number().nullish(),
  availableMachines: z.number().nullish(),
  clusterMachines: z.number().nullish(),
  imageMachines: z.number().nullish(),
  cloneMachines: z.number().nullish(),
});
export const GetOrganizationDashboard_ResultSet16Schema = z.object({
  teamName: z.string().nullish(),
  totalMachines: z.number().nullish(),
  availableMachines: z.number().nullish(),
  clusterMachines: z.number().nullish(),
  imageMachines: z.number().nullish(),
  cloneMachines: z.number().nullish(),
});

export const GetOrganizationPermissionGroups_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationPermissionGroups_ResultSet1Schema = z.object({
  permissionGroupName: z.string().nullish(),
  userCount: z.number().nullish(),
  permissionCount: z.number().nullish(),
  permissions: z.string().nullish(),
});

export const GetOrganizationRegions_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationRegions_ResultSet1Schema = z.object({
  regionName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  bridgeCount: z.number().nullish(),
});

export const GetOrganizationTeams_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationTeams_ResultSet1Schema = z.object({
  teamName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  organizationName: z.string().nullish(),
  isMember: z.boolean().nullish(),
  memberCount: z.number().nullish(),
  machineCount: z.number().nullish(),
  repositoryCount: z.number().nullish(),
  storageCount: z.number().nullish(),
});

export const GetOrganizationUsers_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationUsers_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  activated: z.boolean().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  permissionsName: z.string().nullish(),
  organizationName: z.string().nullish(),
  teamCount: z.number().nullish(),
  lastActive: z.string().nullish(),
});
export const GetOrganizationUsers_ResultSet2Schema = z.object({
  userEmail: z.string().nullish(),
  activated: z.boolean().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.number().nullish(),
  permissionsName: z.string().nullish(),
  organizationName: z.string().nullish(),
  teamCount: z.number().nullish(),
  lastActive: z.string().nullish(),
});

export const GetOrganizationVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationVault_ResultSet1Schema = z.object({
  organizationName: z.string().nullish(),
  organizationCredential: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
});

export const GetOrganizationVaults_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetOrganizationVaults_ResultSet1Schema = z.object({
  entityType: z.string().nullish(),
  entityId: z.number().nullish(),
  entityName: z.string().nullish(),
  vaultId: z.number().nullish(),
  vaultName: z.string().nullish(),
  credential: z.string().nullish(),
  chunkOrder: z.number().nullish(),
  version: z.number().nullish(),
  encryptedVault: z.string().nullish(),
  decryptedVault: z.string().nullish(),
});
export const GetOrganizationVaults_ResultSet2Schema = z.object({
  bridgeId: z.number().nullish(),
  bridgeName: z.string().nullish(),
  requestToken: z.string().nullish(),
  hasRequestToken: z.boolean().nullish(),
});

export const GetPermissionGroupDetails_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetPermissionGroupDetails_ResultSet1Schema = z.object({
  permissionGroupName: z.string().nullish(),
  permissionName: z.string().nullish(),
});

export const GetQueueItemTrace_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetQueueItemTrace_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  status: z.string().nullish(),
  createdTime: z.string().nullish(),
  assignedTime: z.string().nullish(),
  lastAssigned: z.string().nullish(),
  retryCount: z.number().nullish(),
  lastRetryAt: z.string().nullish(),
  lastFailureReason: z.string().nullish(),
  lastResponseAt: z.string().nullish(),
  priority: z.number().nullish(),
  priorityLabel: z.string().nullish(),
  secondsToAssignment: z.number().nullish(),
  processingDurationSeconds: z.number().nullish(),
  totalDurationSeconds: z.number().nullish(),
  machineName: z.string().nullish(),
  machineId: z.number().nullish(),
  bridgeName: z.string().nullish(),
  bridgeId: z.number().nullish(),
  regionName: z.string().nullish(),
  regionId: z.number().nullish(),
  teamName: z.string().nullish(),
  teamId: z.number().nullish(),
  organizationName: z.string().nullish(),
  organizationId: z.number().nullish(),
  createdBy: z.string().nullish(),
  createdByUserId: z.number().nullish(),
  healthStatus: z.string().nullish(),
  isStale: z.boolean().nullish(),
  isStalePending: z.boolean().nullish(),
  canBeCancelled: z.boolean().nullish(),
});
export const GetQueueItemTrace_ResultSet2Schema = z.object({
  vaultType: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  hasContent: z.boolean().nullish(),
});
export const GetQueueItemTrace_ResultSet3Schema = z.object({
  vaultType: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  hasContent: z.boolean().nullish(),
});
export const GetQueueItemTrace_ResultSet4Schema = z.object({
  action: z.string().nullish(),
  details: z.string().nullish(),
  timestamp: z.string().nullish(),
  actionByUser: z.string().nullish(),
  secondsSincePrevious: z.number().nullish(),
});
export const GetQueueItemTrace_ResultSet5Schema = z.object({
  taskId: z.string().nullish(),
  status: z.string().nullish(),
  createdTime: z.string().nullish(),
  priority: z.number().nullish(),
  secondsDifference: z.number().nullish(),
  relativePosition: z.string().nullish(),
  createdBy: z.string().nullish(),
});
export const GetQueueItemTrace_ResultSet6Schema = z.object({
  avgProcessingTimeSeconds: z.number().nullish(),
  machineSuccessRate: z.number().nullish(),
  currentQueueDepth: z.number().nullish(),
  activeProcessingCount: z.number().nullish(),
  maxConcurrentTasks: z.number().nullish(),
});

export const GetQueueItemsNext_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetQueueItemsNext_ResultSet1Schema = z.object({
  organizationLicense: z.string().nullish(),
  organizationCredential: z.string().nullish(),
  bridgeCredential: z.string().nullish(),
});
export const GetQueueItemsNext_ResultSet2Schema = z.object({
  taskId: z.string().nullish(),
  time: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  teamName: z.string().nullish(),
  assigned: z.string().nullish(),
  status: z.string().nullish(),
  priority: z.number().nullish(),
  retryCount: z.number().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});
export const GetQueueItemsNext_ResultSet3Schema = z.object({
  result: z.string().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});
export const GetQueueItemsNext_ResultSet4Schema = z.object({
  taskId: z.string().nullish(),
  time: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  teamName: z.string().nullish(),
  assigned: z.string().nullish(),
  status: z.string().nullish(),
  priority: z.number().nullish(),
  retryCount: z.number().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});
export const GetQueueItemsNext_ResultSet5Schema = z.object({
  result: z.string().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});
export const GetQueueItemsNext_ResultSet6Schema = z.object({
  result: z.string().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});
export const GetQueueItemsNext_ResultSet7Schema = z.object({
  result: z.string().nullish(),
  subscriptionTier: z.string().nullish(),
  maxConcurrentTasks: z.number().nullish(),
  currentlyProcessingTasks: z.number().nullish(),
});

export const GetRegionBridges_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetRegionBridges_ResultSet1Schema = z.object({
  bridgeName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  bridgeCredentialsVersion: z.number().nullish(),
  bridgeCredentials: z.string().nullish(),
  regionName: z.string().nullish(),
  machineCount: z.number().nullish(),
  hasAccess: z.boolean().nullish(),
  bridgeUserEmail: z.string().nullish(),
  managementMode: z.string().nullish(),
  isGlobalBridge: z.boolean().nullish(),
});

export const GetRequestAuthenticationStatus_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetRequestAuthenticationStatus_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  isTFAEnabled: z.boolean().nullish(),
  isAuthorized: z.boolean().nullish(),
  lastLoginTime: z.string().nullish(),
  tokenExpiration: z.string().nullish(),
  permissionGroup: z.string().nullish(),
  activeTokenCount: z.number().nullish(),
  authenticationStatus: z.string().nullish(),
});

export const GetSystemConfiguration_ResultSet0Schema = z.object({
  configKey: z.string().nullish(),
  configValue: z.string().nullish(),
  configDescription: z.string().nullish(),
  modifiedDate: z.string().nullish(),
});
export const GetSystemConfiguration_ResultSet1Schema = z.object({
  configKey: z.string().nullish(),
  configValue: z.string().nullish(),
  configDescription: z.string().nullish(),
  modifiedDate: z.string().nullish(),
});
export const GetSystemConfiguration_ResultSet2Schema = z.object({
  configKey: z.string().nullish(),
  configValue: z.string().nullish(),
  configDescription: z.string().nullish(),
  modifiedDate: z.string().nullish(),
});

export const GetTeamMachines_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetTeamMachines_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  vaultStatus: z.string().nullish(),
  vaultStatusTime: z.string().nullish(),
  bridgeName: z.string().nullish(),
  regionName: z.string().nullish(),
  teamName: z.string().nullish(),
  queueCount: z.number().nullish(),
  machineGuid: z.string().nullish(),
  cephClusterName: z.string().nullish(),
  assignmentStatus: z.string().nullish(),
});

export const GetTeamMembers_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetTeamMembers_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  activated: z.boolean().nullish(),
  teams: z.string().nullish(),
  organizationName: z.string().nullish(),
  isMember: z.boolean().nullish(),
  hasAccess: z.boolean().nullish(),
});
export const GetTeamMembers_ResultSet2Schema = z.object({
  userEmail: z.string().nullish(),
  activated: z.boolean().nullish(),
  teams: z.string().nullish(),
  organizationName: z.string().nullish(),
  isMember: z.boolean().nullish(),
  hasAccess: z.boolean().nullish(),
});

export const GetTeamQueueItems_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetTeamQueueItems_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  createdTime: z.string().nullish(),
  ageInMinutes: z.number().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  vaultVersionResponse: z.number().nullish(),
  vaultContentResponse: z.string().nullish(),
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  teamName: z.string().nullish(),
  regionName: z.string().nullish(),
  status: z.string().nullish(),
  assignedTime: z.string().nullish(),
  lastAssigned: z.string().nullish(),
  minutesSinceAssigned: z.number().nullish(),
  priority: z.number().nullish(),
  priorityLabel: z.string().nullish(),
  healthStatus: z.string().nullish(),
  canBeCancelled: z.boolean().nullish(),
  hasResponse: z.boolean().nullish(),
  createdBy: z.string().nullish(),
  retryCount: z.number().nullish(),
  lastRetryAt: z.string().nullish(),
  lastFailureReason: z.string().nullish(),
  permanentlyFailed: z.boolean().nullish(),
  totalDurationSeconds: z.number().nullish(),
  processingDurationSeconds: z.number().nullish(),
  lastResponseAt: z.string().nullish(),
});
export const GetTeamQueueItems_ResultSet2Schema = z.object({
  totalCount: z.number().nullish(),
  pendingCount: z.number().nullish(),
  assignedCount: z.number().nullish(),
  processingCount: z.number().nullish(),
  cancellingCount: z.number().nullish(),
  completedCount: z.number().nullish(),
  cancelledCount: z.number().nullish(),
  failedCount: z.number().nullish(),
  staleCount: z.number().nullish(),
});

export const GetTeamRepositories_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetTeamRepositories_ResultSet1Schema = z.object({
  repositoryName: z.string().nullish(),
  repositoryGuid: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  teamName: z.string().nullish(),
  grandGuid: z.string().nullish(),
  parentGuid: z.string().nullish(),
  repositoryNetworkId: z.number().nullish(),
  repositoryNetworkMode: z.string().nullish(),
  repositoryTag: z.string().nullish(),
});

export const GetTeamStorages_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetTeamStorages_ResultSet1Schema = z.object({
  storageName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const GetUserOrganization_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetUserOrganization_ResultSet1Schema = z.object({
  organizationName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  teamCount: z.number().nullish(),
  regionCount: z.number().nullish(),
  userCount: z.number().nullish(),
});

export const GetUserRequests_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetUserRequests_ResultSet1Schema = z.object({
  requestId: z.number().nullish(),
  userEmail: z.string().nullish(),
  sessionName: z.string().nullish(),
  ipAddress: z.string().nullish(),
  userAgent: z.string().nullish(),
  createdAt: z.string().nullish(),
  lastActivity: z.string().nullish(),
  isActive: z.boolean().nullish(),
  parentRequestId: z.number().nullish(),
  permissionsName: z.string().nullish(),
  expirationTime: z.string().nullish(),
});

export const GetUserVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const GetUserVault_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  vaultContent: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  userCredential: z.string().nullish(),
});

export const ImportOrganizationData_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const ImportOrganizationData_ResultSet1Schema = z.object({
  message: z.string().nullish(),
  importedCount: z.number().nullish(),
  skippedCount: z.number().nullish(),
  errorCount: z.number().nullish(),
});
export const ImportOrganizationData_ResultSet2Schema = z.object({
  importedCount: z.number().nullish(),
  skippedCount: z.number().nullish(),
  errorCount: z.number().nullish(),
  result: z.string().nullish(),
});
export const ImportOrganizationData_ResultSet3Schema = z.object({
  importedCount: z.number().nullish(),
  skippedCount: z.number().nullish(),
  errorCount: z.number().nullish(),
  result: z.string().nullish(),
});

export const IsRegistered_ResultSet0Schema = z.object({
  isRegistered: z.boolean().nullish(),
  serverName: z.string().nullish(),
});
export const IsRegistered_ResultSet1Schema = z.object({
  isRegistered: z.boolean().nullish(),
  serverName: z.string().nullish(),
});

export const PrivilegeAuthenticationRequest_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const PrivilegeAuthenticationRequest_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
  isAuthorized: z.boolean().nullish(),
  isTFAEnabled: z.boolean().nullish(),
});
export const PrivilegeAuthenticationRequest_ResultSet2Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
  isAuthorized: z.boolean().nullish(),
});

export const PromoteRepositoryToGrand_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});

export const ResetBridgeAuthorization_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const ResetBridgeAuthorization_ResultSet1Schema = z.object({
  bridgeName: z.string().nullish(),
  result: z.string().nullish(),
  managementMode: z.string().nullish(),
});

export const RetryFailedQueueItem_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const RetryFailedQueueItem_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  newRetryCount: z.number().nullish(),
});

export const UpdateBridgeName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateBridgeName_ResultSet1Schema = z.object({
  bridgeName: z.string().nullish(),
  regionName: z.string().nullish(),
});

export const UpdateBridgeVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateBridgeVault_ResultSet1Schema = z.object({
  bridgeName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateCephClusterVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateCephClusterVault_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateCephPoolVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateCephPoolVault_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateCloneMachineAssignments_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateCloneMachineAssignments_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});
export const UpdateCloneMachineAssignments_ResultSet2Schema = z.object({
  message: z.string().nullish(),
});
export const UpdateCloneMachineAssignments_ResultSet3Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateCloneMachineRemovals_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateCloneMachineRemovals_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});
export const UpdateCloneMachineRemovals_ResultSet2Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateImageMachineAssignment_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateImageMachineAssignment_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});
export const UpdateImageMachineAssignment_ResultSet2Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateMachineAssignedBridge_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineAssignedBridge_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  teamName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  regionName: z.string().nullish(),
});

export const UpdateMachineCeph_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineCeph_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});
export const UpdateMachineCeph_ResultSet2Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateMachineClusterAssignment_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineClusterAssignment_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateMachineClusterRemoval_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineClusterRemoval_ResultSet1Schema = z.object({
  message: z.string().nullish(),
});

export const UpdateMachineName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineName_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  bridgeName: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const UpdateMachineStatus_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineStatus_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  vaultContent: z.string().nullish(),
  vaultStatus: z.string().nullish(),
  vaultStatusTime: z.string().nullish(),
  bridgeName: z.string().nullish(),
  regionName: z.string().nullish(),
  teamName: z.string().nullish(),
  queueCount: z.number().nullish(),
});

export const UpdateMachineVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateMachineVault_ResultSet1Schema = z.object({
  machineName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateOrganizationBlockUserRequests_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateOrganizationBlockUserRequests_ResultSet1Schema = z.object({
  organizationId: z.number().nullish(),
  blockUserRequests: z.boolean().nullish(),
  deactivatedTokenCount: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateOrganizationVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateOrganizationVault_ResultSet1Schema = z.object({
  organizationName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateOrganizationVaults_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateOrganizationVaults_ResultSet1Schema = z.object({
  organizationId: z.number().nullish(),
  blockUserRequests: z.boolean().nullish(),
  vaultsUpdated: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateQueueItemResponse_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  message: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet2Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  message: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet3Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  message: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet4Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet5Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  message: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet6Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
  message: z.string().nullish(),
});
export const UpdateQueueItemResponse_ResultSet7Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateQueueItemToCompleted_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateQueueItemToCompleted_ResultSet1Schema = z.object({
  taskId: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateRegionName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateRegionName_ResultSet1Schema = z.object({
  regionName: z.string().nullish(),
});

export const UpdateRegionVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateRegionVault_ResultSet1Schema = z.object({
  regionName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateRepositoryName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateRepositoryName_ResultSet1Schema = z.object({
  repositoryName: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const UpdateRepositoryTag_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateRepositoryTag_ResultSet1Schema = z.object({
  repositoryName: z.string().nullish(),
  repositoryTag: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const UpdateRepositoryVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateRepositoryVault_ResultSet1Schema = z.object({
  repositoryName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateStorageName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateStorageName_ResultSet1Schema = z.object({
  storageName: z.string().nullish(),
  teamName: z.string().nullish(),
});

export const UpdateStorageVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateStorageVault_ResultSet1Schema = z.object({
  storageName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateTeamName_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateTeamName_ResultSet1Schema = z.object({
  teamName: z.string().nullish(),
  organizationName: z.string().nullish(),
  memberCount: z.number().nullish(),
});

export const UpdateTeamVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateTeamVault_ResultSet1Schema = z.object({
  teamName: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserAssignedPermissions_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserAssignedPermissions_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  permissionGroupName: z.string().nullish(),
  result: z.string().nullish(),
  totalTokenCount: z.number().nullish(),
  tokensDowngraded: z.number().nullish(),
});

export const UpdateUserEmail_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserEmail_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserLanguage_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserLanguage_ResultSet1Schema = z.object({
  preferredLanguage: z.string().nullish(),
  message: z.string().nullish(),
});

export const UpdateUserPassword_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserPassword_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserTFA_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserTFA_ResultSet1Schema = z.object({
  secret: z.string().nullish(),
  userEmail: z.string().nullish(),
  authType: z.string().nullish(),
  result: z.string().nullish(),
});
export const UpdateUserTFA_ResultSet2Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});
export const UpdateUserTFA_ResultSet3Schema = z.object({
  secret: z.string().nullish(),
  userEmail: z.string().nullish(),
  authType: z.string().nullish(),
  result: z.string().nullish(),
});
export const UpdateUserTFA_ResultSet4Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserToActivated_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserToActivated_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserToDeactivated_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserToDeactivated_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  result: z.string().nullish(),
});

export const UpdateUserVault_ResultSet0Schema = z.object({
  nextRequestToken: z.string().nullish(),
});
export const UpdateUserVault_ResultSet1Schema = z.object({
  userEmail: z.string().nullish(),
  vaultVersion: z.number().nullish(),
  result: z.string().nullish(),
});

// ============================================================================
// Validation Functions
// ============================================================================

/**
 * Map of procedure names to their result set schemas.
 * Used by validateApiResponse for dynamic validation.
 */
export const RESULT_SET_SCHEMAS: Record<string, Record<number, z.ZodSchema>> = {
  ActivateUserAccount: {
    0: z.array(ActivateUserAccount_ResultSet0Schema),
  },
  CancelQueueItem: {
    0: z.array(CancelQueueItem_ResultSet0Schema),
    1: z.array(CancelQueueItem_ResultSet1Schema),
    2: z.array(CancelQueueItem_ResultSet2Schema),
  },
  CreateAuthenticationRequest: {
    0: z.array(CreateAuthenticationRequest_ResultSet0Schema),
  },
  CreateBridge: {
    0: z.array(CreateBridge_ResultSet0Schema),
    1: z.array(CreateBridge_ResultSet1Schema),
  },
  CreateCephCluster: {
    0: z.array(CreateCephCluster_ResultSet0Schema),
    1: z.array(CreateCephCluster_ResultSet1Schema),
  },
  CreateCephPool: {
    0: z.array(CreateCephPool_ResultSet0Schema),
    1: z.array(CreateCephPool_ResultSet1Schema),
  },
  CreateCephRbdClone: {
    0: z.array(CreateCephRbdClone_ResultSet0Schema),
    1: z.array(CreateCephRbdClone_ResultSet1Schema),
  },
  CreateCephRbdImage: {
    0: z.array(CreateCephRbdImage_ResultSet0Schema),
    1: z.array(CreateCephRbdImage_ResultSet1Schema),
  },
  CreateCephRbdSnapshot: {
    0: z.array(CreateCephRbdSnapshot_ResultSet0Schema),
    1: z.array(CreateCephRbdSnapshot_ResultSet1Schema),
  },
  CreateMachine: {
    0: z.array(CreateMachine_ResultSet0Schema),
    1: z.array(CreateMachine_ResultSet1Schema),
  },
  CreateNewOrganization: {
    0: z.array(CreateNewOrganization_ResultSet0Schema),
  },
  CreateNewUser: {
    0: z.array(CreateNewUser_ResultSet0Schema),
    1: z.array(CreateNewUser_ResultSet1Schema),
  },
  CreatePermissionGroup: {
    0: z.array(CreatePermissionGroup_ResultSet0Schema),
    1: z.array(CreatePermissionGroup_ResultSet1Schema),
  },
  CreatePermissionInGroup: {
    0: z.array(CreatePermissionInGroup_ResultSet0Schema),
    1: z.array(CreatePermissionInGroup_ResultSet1Schema),
  },
  CreateQueueItem: {
    0: z.array(CreateQueueItem_ResultSet0Schema),
    1: z.array(CreateQueueItem_ResultSet1Schema),
  },
  CreateRegion: {
    0: z.array(CreateRegion_ResultSet0Schema),
    1: z.array(CreateRegion_ResultSet1Schema),
  },
  CreateRepository: {
    0: z.array(CreateRepository_ResultSet0Schema),
    1: z.array(CreateRepository_ResultSet1Schema),
  },
  CreateStorage: {
    0: z.array(CreateStorage_ResultSet0Schema),
    1: z.array(CreateStorage_ResultSet1Schema),
  },
  CreateTeam: {
    0: z.array(CreateTeam_ResultSet0Schema),
    1: z.array(CreateTeam_ResultSet1Schema),
  },
  CreateTeamMembership: {
    0: z.array(CreateTeamMembership_ResultSet0Schema),
    1: z.array(CreateTeamMembership_ResultSet1Schema),
  },
  DeleteBridge: {
    0: z.array(DeleteBridge_ResultSet0Schema),
  },
  DeleteCephCluster: {
    0: z.array(DeleteCephCluster_ResultSet0Schema),
    1: z.array(DeleteCephCluster_ResultSet1Schema),
  },
  DeleteCephPool: {
    0: z.array(DeleteCephPool_ResultSet0Schema),
    1: z.array(DeleteCephPool_ResultSet1Schema),
  },
  DeleteCephRbdClone: {
    0: z.array(DeleteCephRbdClone_ResultSet0Schema),
    1: z.array(DeleteCephRbdClone_ResultSet1Schema),
  },
  DeleteCephRbdImage: {
    0: z.array(DeleteCephRbdImage_ResultSet0Schema),
    1: z.array(DeleteCephRbdImage_ResultSet1Schema),
  },
  DeleteCephRbdSnapshot: {
    0: z.array(DeleteCephRbdSnapshot_ResultSet0Schema),
    1: z.array(DeleteCephRbdSnapshot_ResultSet1Schema),
  },
  DeleteMachine: {
    0: z.array(DeleteMachine_ResultSet0Schema),
  },
  DeletePermissionFromGroup: {
    0: z.array(DeletePermissionFromGroup_ResultSet0Schema),
    1: z.array(DeletePermissionFromGroup_ResultSet1Schema),
  },
  DeletePermissionGroup: {
    0: z.array(DeletePermissionGroup_ResultSet0Schema),
    1: z.array(DeletePermissionGroup_ResultSet1Schema),
  },
  DeleteQueueItem: {
    0: z.array(DeleteQueueItem_ResultSet0Schema),
    1: z.array(DeleteQueueItem_ResultSet1Schema),
  },
  DeleteRegion: {
    0: z.array(DeleteRegion_ResultSet0Schema),
  },
  DeleteRepository: {
    0: z.array(DeleteRepository_ResultSet0Schema),
  },
  DeleteStorage: {
    0: z.array(DeleteStorage_ResultSet0Schema),
  },
  DeleteTeam: {
    0: z.array(DeleteTeam_ResultSet0Schema),
  },
  DeleteUserFromTeam: {
    0: z.array(DeleteUserFromTeam_ResultSet0Schema),
    1: z.array(DeleteUserFromTeam_ResultSet1Schema),
  },
  DeleteUserRequest: {
    0: z.array(DeleteUserRequest_ResultSet0Schema),
    1: z.array(DeleteUserRequest_ResultSet1Schema),
  },
  ExportOrganizationData: {
    0: z.array(ExportOrganizationData_ResultSet0Schema),
    1: z.array(ExportOrganizationData_ResultSet1Schema),
  },
  ForkAuthenticationRequest: {
    0: z.array(ForkAuthenticationRequest_ResultSet0Schema),
    1: z.array(ForkAuthenticationRequest_ResultSet1Schema),
  },
  GetAuditLogs: {
    0: z.array(GetAuditLogs_ResultSet0Schema),
    1: z.array(GetAuditLogs_ResultSet1Schema),
    2: z.array(GetAuditLogs_ResultSet2Schema),
  },
  GetAvailableMachinesForClone: {
    0: z.array(GetAvailableMachinesForClone_ResultSet0Schema),
    1: z.array(GetAvailableMachinesForClone_ResultSet1Schema),
  },
  GetCephClusterMachines: {
    0: z.array(GetCephClusterMachines_ResultSet0Schema),
    1: z.array(GetCephClusterMachines_ResultSet1Schema),
  },
  GetCephClusters: {
    0: z.array(GetCephClusters_ResultSet0Schema),
    1: z.array(GetCephClusters_ResultSet1Schema),
  },
  GetCephPools: {
    0: z.array(GetCephPools_ResultSet0Schema),
    1: z.array(GetCephPools_ResultSet1Schema),
  },
  GetCephRbdClones: {
    0: z.array(GetCephRbdClones_ResultSet0Schema),
    1: z.array(GetCephRbdClones_ResultSet1Schema),
  },
  GetCephRbdImages: {
    0: z.array(GetCephRbdImages_ResultSet0Schema),
    1: z.array(GetCephRbdImages_ResultSet1Schema),
  },
  GetCephRbdSnapshots: {
    0: z.array(GetCephRbdSnapshots_ResultSet0Schema),
    1: z.array(GetCephRbdSnapshots_ResultSet1Schema),
  },
  GetCloneMachineAssignmentValidation: {
    0: z.array(GetCloneMachineAssignmentValidation_ResultSet0Schema),
    1: z.array(GetCloneMachineAssignmentValidation_ResultSet1Schema),
    2: z.array(GetCloneMachineAssignmentValidation_ResultSet2Schema),
  },
  GetCloneMachines: {
    0: z.array(GetCloneMachines_ResultSet0Schema),
    1: z.array(GetCloneMachines_ResultSet1Schema),
  },
  GetEntityAuditTrace: {
    0: z.array(GetEntityAuditTrace_ResultSet0Schema),
    1: z.array(GetEntityAuditTrace_ResultSet1Schema),
    2: z.array(GetEntityAuditTrace_ResultSet2Schema),
  },
  GetEntityHistory: {
    0: z.array(GetEntityHistory_ResultSet0Schema),
    1: z.array(GetEntityHistory_ResultSet1Schema),
    2: z.array(GetEntityHistory_ResultSet2Schema),
  },
  GetLookupData: {
    0: z.array(GetLookupData_ResultSet0Schema),
    1: z.array(GetLookupData_ResultSet1Schema),
  },
  GetMachineAssignmentStatus: {
    0: z.array(GetMachineAssignmentStatus_ResultSet0Schema),
    1: z.array(GetMachineAssignmentStatus_ResultSet1Schema),
    2: z.array(GetMachineAssignmentStatus_ResultSet2Schema),
  },
  GetOrganizationDashboard: {
    0: z.array(GetOrganizationDashboard_ResultSet0Schema),
    1: z.array(GetOrganizationDashboard_ResultSet1Schema),
    2: z.array(GetOrganizationDashboard_ResultSet2Schema),
    3: z.array(GetOrganizationDashboard_ResultSet3Schema),
    4: z.array(GetOrganizationDashboard_ResultSet4Schema),
    5: z.array(GetOrganizationDashboard_ResultSet5Schema),
    6: z.array(GetOrganizationDashboard_ResultSet6Schema),
    7: z.array(GetOrganizationDashboard_ResultSet7Schema),
    8: z.array(GetOrganizationDashboard_ResultSet8Schema),
    9: z.array(GetOrganizationDashboard_ResultSet9Schema),
    10: z.array(GetOrganizationDashboard_ResultSet10Schema),
    11: z.array(GetOrganizationDashboard_ResultSet11Schema),
    12: z.array(GetOrganizationDashboard_ResultSet12Schema),
    13: z.array(GetOrganizationDashboard_ResultSet13Schema),
    14: z.array(GetOrganizationDashboard_ResultSet14Schema),
    15: z.array(GetOrganizationDashboard_ResultSet15Schema),
    16: z.array(GetOrganizationDashboard_ResultSet16Schema),
  },
  GetOrganizationPermissionGroups: {
    0: z.array(GetOrganizationPermissionGroups_ResultSet0Schema),
    1: z.array(GetOrganizationPermissionGroups_ResultSet1Schema),
  },
  GetOrganizationRegions: {
    0: z.array(GetOrganizationRegions_ResultSet0Schema),
    1: z.array(GetOrganizationRegions_ResultSet1Schema),
  },
  GetOrganizationTeams: {
    0: z.array(GetOrganizationTeams_ResultSet0Schema),
    1: z.array(GetOrganizationTeams_ResultSet1Schema),
  },
  GetOrganizationUsers: {
    0: z.array(GetOrganizationUsers_ResultSet0Schema),
    1: z.array(GetOrganizationUsers_ResultSet1Schema),
    2: z.array(GetOrganizationUsers_ResultSet2Schema),
  },
  GetOrganizationVault: {
    0: z.array(GetOrganizationVault_ResultSet0Schema),
    1: z.array(GetOrganizationVault_ResultSet1Schema),
  },
  GetOrganizationVaults: {
    0: z.array(GetOrganizationVaults_ResultSet0Schema),
    1: z.array(GetOrganizationVaults_ResultSet1Schema),
    2: z.array(GetOrganizationVaults_ResultSet2Schema),
  },
  GetPermissionGroupDetails: {
    0: z.array(GetPermissionGroupDetails_ResultSet0Schema),
    1: z.array(GetPermissionGroupDetails_ResultSet1Schema),
  },
  GetQueueItemTrace: {
    0: z.array(GetQueueItemTrace_ResultSet0Schema),
    1: z.array(GetQueueItemTrace_ResultSet1Schema),
    2: z.array(GetQueueItemTrace_ResultSet2Schema),
    3: z.array(GetQueueItemTrace_ResultSet3Schema),
    4: z.array(GetQueueItemTrace_ResultSet4Schema),
    5: z.array(GetQueueItemTrace_ResultSet5Schema),
    6: z.array(GetQueueItemTrace_ResultSet6Schema),
  },
  GetQueueItemsNext: {
    0: z.array(GetQueueItemsNext_ResultSet0Schema),
    1: z.array(GetQueueItemsNext_ResultSet1Schema),
    2: z.array(GetQueueItemsNext_ResultSet2Schema),
    3: z.array(GetQueueItemsNext_ResultSet3Schema),
    4: z.array(GetQueueItemsNext_ResultSet4Schema),
    5: z.array(GetQueueItemsNext_ResultSet5Schema),
    6: z.array(GetQueueItemsNext_ResultSet6Schema),
    7: z.array(GetQueueItemsNext_ResultSet7Schema),
  },
  GetRegionBridges: {
    0: z.array(GetRegionBridges_ResultSet0Schema),
    1: z.array(GetRegionBridges_ResultSet1Schema),
  },
  GetRequestAuthenticationStatus: {
    0: z.array(GetRequestAuthenticationStatus_ResultSet0Schema),
    1: z.array(GetRequestAuthenticationStatus_ResultSet1Schema),
  },
  GetSystemConfiguration: {
    0: z.array(GetSystemConfiguration_ResultSet0Schema),
    1: z.array(GetSystemConfiguration_ResultSet1Schema),
    2: z.array(GetSystemConfiguration_ResultSet2Schema),
  },
  GetTeamMachines: {
    0: z.array(GetTeamMachines_ResultSet0Schema),
    1: z.array(GetTeamMachines_ResultSet1Schema),
  },
  GetTeamMembers: {
    0: z.array(GetTeamMembers_ResultSet0Schema),
    1: z.array(GetTeamMembers_ResultSet1Schema),
    2: z.array(GetTeamMembers_ResultSet2Schema),
  },
  GetTeamQueueItems: {
    0: z.array(GetTeamQueueItems_ResultSet0Schema),
    1: z.array(GetTeamQueueItems_ResultSet1Schema),
    2: z.array(GetTeamQueueItems_ResultSet2Schema),
  },
  GetTeamRepositories: {
    0: z.array(GetTeamRepositories_ResultSet0Schema),
    1: z.array(GetTeamRepositories_ResultSet1Schema),
  },
  GetTeamStorages: {
    0: z.array(GetTeamStorages_ResultSet0Schema),
    1: z.array(GetTeamStorages_ResultSet1Schema),
  },
  GetUserOrganization: {
    0: z.array(GetUserOrganization_ResultSet0Schema),
    1: z.array(GetUserOrganization_ResultSet1Schema),
  },
  GetUserRequests: {
    0: z.array(GetUserRequests_ResultSet0Schema),
    1: z.array(GetUserRequests_ResultSet1Schema),
  },
  GetUserVault: {
    0: z.array(GetUserVault_ResultSet0Schema),
    1: z.array(GetUserVault_ResultSet1Schema),
  },
  ImportOrganizationData: {
    0: z.array(ImportOrganizationData_ResultSet0Schema),
    1: z.array(ImportOrganizationData_ResultSet1Schema),
    2: z.array(ImportOrganizationData_ResultSet2Schema),
    3: z.array(ImportOrganizationData_ResultSet3Schema),
  },
  IsRegistered: {
    0: z.array(IsRegistered_ResultSet0Schema),
    1: z.array(IsRegistered_ResultSet1Schema),
  },
  PrivilegeAuthenticationRequest: {
    0: z.array(PrivilegeAuthenticationRequest_ResultSet0Schema),
    1: z.array(PrivilegeAuthenticationRequest_ResultSet1Schema),
    2: z.array(PrivilegeAuthenticationRequest_ResultSet2Schema),
  },
  PromoteRepositoryToGrand: {
    0: z.array(PromoteRepositoryToGrand_ResultSet0Schema),
  },
  ResetBridgeAuthorization: {
    0: z.array(ResetBridgeAuthorization_ResultSet0Schema),
    1: z.array(ResetBridgeAuthorization_ResultSet1Schema),
  },
  RetryFailedQueueItem: {
    0: z.array(RetryFailedQueueItem_ResultSet0Schema),
    1: z.array(RetryFailedQueueItem_ResultSet1Schema),
  },
  UpdateBridgeName: {
    0: z.array(UpdateBridgeName_ResultSet0Schema),
    1: z.array(UpdateBridgeName_ResultSet1Schema),
  },
  UpdateBridgeVault: {
    0: z.array(UpdateBridgeVault_ResultSet0Schema),
    1: z.array(UpdateBridgeVault_ResultSet1Schema),
  },
  UpdateCephClusterVault: {
    0: z.array(UpdateCephClusterVault_ResultSet0Schema),
    1: z.array(UpdateCephClusterVault_ResultSet1Schema),
  },
  UpdateCephPoolVault: {
    0: z.array(UpdateCephPoolVault_ResultSet0Schema),
    1: z.array(UpdateCephPoolVault_ResultSet1Schema),
  },
  UpdateCloneMachineAssignments: {
    0: z.array(UpdateCloneMachineAssignments_ResultSet0Schema),
    1: z.array(UpdateCloneMachineAssignments_ResultSet1Schema),
    2: z.array(UpdateCloneMachineAssignments_ResultSet2Schema),
    3: z.array(UpdateCloneMachineAssignments_ResultSet3Schema),
  },
  UpdateCloneMachineRemovals: {
    0: z.array(UpdateCloneMachineRemovals_ResultSet0Schema),
    1: z.array(UpdateCloneMachineRemovals_ResultSet1Schema),
    2: z.array(UpdateCloneMachineRemovals_ResultSet2Schema),
  },
  UpdateImageMachineAssignment: {
    0: z.array(UpdateImageMachineAssignment_ResultSet0Schema),
    1: z.array(UpdateImageMachineAssignment_ResultSet1Schema),
    2: z.array(UpdateImageMachineAssignment_ResultSet2Schema),
  },
  UpdateMachineAssignedBridge: {
    0: z.array(UpdateMachineAssignedBridge_ResultSet0Schema),
    1: z.array(UpdateMachineAssignedBridge_ResultSet1Schema),
  },
  UpdateMachineCeph: {
    0: z.array(UpdateMachineCeph_ResultSet0Schema),
    1: z.array(UpdateMachineCeph_ResultSet1Schema),
    2: z.array(UpdateMachineCeph_ResultSet2Schema),
  },
  UpdateMachineClusterAssignment: {
    0: z.array(UpdateMachineClusterAssignment_ResultSet0Schema),
    1: z.array(UpdateMachineClusterAssignment_ResultSet1Schema),
  },
  UpdateMachineClusterRemoval: {
    0: z.array(UpdateMachineClusterRemoval_ResultSet0Schema),
    1: z.array(UpdateMachineClusterRemoval_ResultSet1Schema),
  },
  UpdateMachineName: {
    0: z.array(UpdateMachineName_ResultSet0Schema),
    1: z.array(UpdateMachineName_ResultSet1Schema),
  },
  UpdateMachineStatus: {
    0: z.array(UpdateMachineStatus_ResultSet0Schema),
    1: z.array(UpdateMachineStatus_ResultSet1Schema),
  },
  UpdateMachineVault: {
    0: z.array(UpdateMachineVault_ResultSet0Schema),
    1: z.array(UpdateMachineVault_ResultSet1Schema),
  },
  UpdateOrganizationBlockUserRequests: {
    0: z.array(UpdateOrganizationBlockUserRequests_ResultSet0Schema),
    1: z.array(UpdateOrganizationBlockUserRequests_ResultSet1Schema),
  },
  UpdateOrganizationVault: {
    0: z.array(UpdateOrganizationVault_ResultSet0Schema),
    1: z.array(UpdateOrganizationVault_ResultSet1Schema),
  },
  UpdateOrganizationVaults: {
    0: z.array(UpdateOrganizationVaults_ResultSet0Schema),
    1: z.array(UpdateOrganizationVaults_ResultSet1Schema),
  },
  UpdateQueueItemResponse: {
    0: z.array(UpdateQueueItemResponse_ResultSet0Schema),
    1: z.array(UpdateQueueItemResponse_ResultSet1Schema),
    2: z.array(UpdateQueueItemResponse_ResultSet2Schema),
    3: z.array(UpdateQueueItemResponse_ResultSet3Schema),
    4: z.array(UpdateQueueItemResponse_ResultSet4Schema),
    5: z.array(UpdateQueueItemResponse_ResultSet5Schema),
    6: z.array(UpdateQueueItemResponse_ResultSet6Schema),
    7: z.array(UpdateQueueItemResponse_ResultSet7Schema),
  },
  UpdateQueueItemToCompleted: {
    0: z.array(UpdateQueueItemToCompleted_ResultSet0Schema),
    1: z.array(UpdateQueueItemToCompleted_ResultSet1Schema),
  },
  UpdateRegionName: {
    0: z.array(UpdateRegionName_ResultSet0Schema),
    1: z.array(UpdateRegionName_ResultSet1Schema),
  },
  UpdateRegionVault: {
    0: z.array(UpdateRegionVault_ResultSet0Schema),
    1: z.array(UpdateRegionVault_ResultSet1Schema),
  },
  UpdateRepositoryName: {
    0: z.array(UpdateRepositoryName_ResultSet0Schema),
    1: z.array(UpdateRepositoryName_ResultSet1Schema),
  },
  UpdateRepositoryTag: {
    0: z.array(UpdateRepositoryTag_ResultSet0Schema),
    1: z.array(UpdateRepositoryTag_ResultSet1Schema),
  },
  UpdateRepositoryVault: {
    0: z.array(UpdateRepositoryVault_ResultSet0Schema),
    1: z.array(UpdateRepositoryVault_ResultSet1Schema),
  },
  UpdateStorageName: {
    0: z.array(UpdateStorageName_ResultSet0Schema),
    1: z.array(UpdateStorageName_ResultSet1Schema),
  },
  UpdateStorageVault: {
    0: z.array(UpdateStorageVault_ResultSet0Schema),
    1: z.array(UpdateStorageVault_ResultSet1Schema),
  },
  UpdateTeamName: {
    0: z.array(UpdateTeamName_ResultSet0Schema),
    1: z.array(UpdateTeamName_ResultSet1Schema),
  },
  UpdateTeamVault: {
    0: z.array(UpdateTeamVault_ResultSet0Schema),
    1: z.array(UpdateTeamVault_ResultSet1Schema),
  },
  UpdateUserAssignedPermissions: {
    0: z.array(UpdateUserAssignedPermissions_ResultSet0Schema),
    1: z.array(UpdateUserAssignedPermissions_ResultSet1Schema),
  },
  UpdateUserEmail: {
    0: z.array(UpdateUserEmail_ResultSet0Schema),
    1: z.array(UpdateUserEmail_ResultSet1Schema),
  },
  UpdateUserLanguage: {
    0: z.array(UpdateUserLanguage_ResultSet0Schema),
    1: z.array(UpdateUserLanguage_ResultSet1Schema),
  },
  UpdateUserPassword: {
    0: z.array(UpdateUserPassword_ResultSet0Schema),
    1: z.array(UpdateUserPassword_ResultSet1Schema),
  },
  UpdateUserTFA: {
    0: z.array(UpdateUserTFA_ResultSet0Schema),
    1: z.array(UpdateUserTFA_ResultSet1Schema),
    2: z.array(UpdateUserTFA_ResultSet2Schema),
    3: z.array(UpdateUserTFA_ResultSet3Schema),
    4: z.array(UpdateUserTFA_ResultSet4Schema),
  },
  UpdateUserToActivated: {
    0: z.array(UpdateUserToActivated_ResultSet0Schema),
    1: z.array(UpdateUserToActivated_ResultSet1Schema),
  },
  UpdateUserToDeactivated: {
    0: z.array(UpdateUserToDeactivated_ResultSet0Schema),
    1: z.array(UpdateUserToDeactivated_ResultSet1Schema),
  },
  UpdateUserVault: {
    0: z.array(UpdateUserVault_ResultSet0Schema),
    1: z.array(UpdateUserVault_ResultSet1Schema),
  },
};

/**
 * Error thrown when API response validation fails.
 */
export class ApiValidationError extends Error {
  constructor(
    public procedure: string,
    public resultSetIndex: number,
    public zodError: z.ZodError
  ) {
    super(
      `API validation failed for ${procedure} resultSet[${resultSetIndex}]: ${zodError.message}`
    );
    this.name = 'ApiValidationError';
  }
}

/**
 * Validates an API response against its schema.
 * Throws ApiValidationError if validation fails (fail-fast).
 */
export function validateApiResponse<T>(
  procedureName: string,
  response: { resultSets?: Array<{ data?: unknown[] }> }
): T {
  const schemas = RESULT_SET_SCHEMAS[procedureName];
  if (!schemas) {
    // No schema defined - skip validation
    return response as T;
  }

  const resultSets = response.resultSets ?? [];
  for (const [indexStr, schema] of Object.entries(schemas)) {
    const index = Number(indexStr);
    const data = resultSets[index]?.data ?? [];
    const result = schema.safeParse(data);
    if (!result.success) {
      throw new ApiValidationError(procedureName, index, result.error);
    }
  }

  return response as T;
}

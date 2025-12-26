/**
 * Derived Types - Utility types built on top of generated API schema
 *
 * These types provide convenience wrappers for common patterns like optional
 * vaultContent fields and partial parameter types for filtering.
 */

import type {
  CreateBridgeParams,
  CreateCephClusterParams,
  CreateCephPoolParams,
  CreateCephRbdCloneParams,
  CreateCephRbdImageParams,
  CreateCephRbdSnapshotParams,
  CreateMachineParams,
  CreateQueueItemParams,
  CreateRegionParams,
  CreateRepositoryParams,
  CreateStorageParams,
  CreateTeamParams,
  GetPermissionGroupDetails_ResultSet1,
  GetTeamQueueItemsParams,
} from './api-schema.generated';

// =============================================================================
// UTILITY TYPES
// =============================================================================

/** Makes vaultContent optional with empty JSON default */
export type WithOptionalVault<T extends { vaultContent: string }> = Omit<T, 'vaultContent'> & {
  vaultContent?: string;
};

/** Makes all properties of T optional */
export type OptionalParams<T> = Partial<T>;

// =============================================================================
// CONTAINER TYPES
// =============================================================================

/** Plugin container data */
export interface PluginContainer {
  id: string;
  name: string;
  state: string;
  status?: string;
  image?: string;
  ports?: string;
  created?: string;
  repository?: string;
}

// =============================================================================
// QUEUE TYPES (replaces manual QueueFilters interface)
// =============================================================================

export type QueueFilters = Partial<Omit<GetTeamQueueItemsParams, 'teamName'>> & {
  teamName?: string;
};

// =============================================================================
// FORM VALUE TYPES (for create operations with optional vault)
// =============================================================================

// Core resources
export type StorageFormValues = WithOptionalVault<CreateStorageParams>;
export type MachineFormValues = WithOptionalVault<CreateMachineParams>;
export type TeamFormValues = WithOptionalVault<CreateTeamParams>;
export type BridgeFormValues = WithOptionalVault<CreateBridgeParams>;
export type RegionFormValues = WithOptionalVault<CreateRegionParams>;
export type RepositoryFormValues = WithOptionalVault<CreateRepositoryParams>;
export type QueueItemFormValues = WithOptionalVault<CreateQueueItemParams>;

// Ceph resources
export type ClusterFormValues = WithOptionalVault<CreateCephClusterParams>;
export type PoolFormValues = WithOptionalVault<CreateCephPoolParams>;
export type ImageFormValues = WithOptionalVault<CreateCephRbdImageParams>;
export type SnapshotFormValues = WithOptionalVault<CreateCephRbdSnapshotParams>;
export type CloneFormValues = WithOptionalVault<CreateCephRbdCloneParams>;

// =============================================================================
// COMPUTED TYPES (not from stored procedures)
// =============================================================================

/** Queue statistics summary - computed from queue items */
export interface QueueStatistics {
  totalCount: number;
  pendingCount: number;
  assignedCount: number;
  processingCount: number;
  cancellingCount: number;
  completedCount: number;
  cancelledCount: number;
  failedCount: number;
  staleCount: number;
}

// =============================================================================
// QUEUE DOMAIN TYPES
// =============================================================================

/** Queue health status - derived from status and timing */
export type QueueHealthStatus =
  | 'PENDING'
  | 'ACTIVE'
  | 'STALE'
  | 'STALE_PENDING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'UNKNOWN';

/** Queue item status - raw status from database */
export type QueueStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

/** Queue list result with items and optional statistics */
export interface QueueListResult {
  items: import('./api-schema.generated').GetTeamQueueItems_ResultSet1[];
  statistics: import('./api-schema.generated').GetTeamQueueItems_ResultSet2 | null;
}

/** Queue machine stats from trace */
export interface QueueMachineStats {
  currentQueueDepth?: number | null;
  activeProcessingCount?: number | null;
  maxConcurrentTasks?: number | null;
}

/** Queue plan info from trace */
export interface QueuePlanInfo {
  planName?: string | null;
  planVersion?: number | null;
  estimatedDuration?: number | null;
  [key: string]: unknown;
}

/** Queue position entry for trace */
export interface QueuePositionEntry {
  taskId: string;
  status: string;
  createdTime: string;
  relativePosition?: string;
}

/** Queue trace log entry */
export interface QueueTraceLog {
  timestamp?: string | null;
  level?: string | null;
  message?: string | null;
  source?: string | null;
  [key: string]: unknown;
}

/** Queue trace summary */
export interface QueueTraceSummary {
  taskId?: string;
  status?: QueueStatus;
  healthStatus?: QueueHealthStatus;
  progress?: string | null;
  consoleOutput?: string | null;
  errorMessage?: string | null;
  lastFailureReason?: string | null;
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

/** Queue vault snapshot */
export interface QueueVaultSnapshot {
  hasContent?: boolean;
  vaultVersion?: number | null;
  vaultContent?: string | null;
  updatedAt?: string | null;
}

/** Full queue trace response */
export interface QueueTrace {
  summary: QueueTraceSummary | null;
  queueDetails: import('./api-schema.generated').GetTeamQueueItems_ResultSet1 | null;
  traceLogs: QueueTraceLog[];
  vaultContent: QueueVaultSnapshot | null;
  responseVaultContent: QueueVaultSnapshot | null;
  queuePosition: QueuePositionEntry[];
  machineStats: QueueMachineStats | null;
  planInfo: QueuePlanInfo | null;
}

// =============================================================================
// AUTH DOMAIN TYPES
// =============================================================================

/** Authentication login result */
export interface AuthLoginResult {
  isAuthorized: boolean;
  authenticationStatus: string;
  vaultCompany: string | null;
  companyName: string | null;
  company: string | null;
  preferredLanguage: string | null;
}

/** Authentication request status */
export interface AuthRequestStatus {
  isTFAEnabled: boolean;
  isAuthorized: boolean;
  authenticationStatus: string;
}

/** TFA enable response */
export interface EnableTfaResponse {
  secret?: string | null;
  qrCodeUrl?: string | null;
  backupCodes?: string[] | null;
  [key: string]: unknown;
}

/** Fork session credentials */
export interface ForkSessionCredentials {
  requestToken: string | null;
  nextRequestToken: string | null;
  parentRequestId: number | null;
}

/** User request record - use GetUserRequests_ResultSet1 from api-schema.generated */

/** TFA verification result */
export interface VerifyTfaResult {
  isAuthorized?: boolean;
  result?: string;
  hasTFAEnabled?: boolean;
}

// =============================================================================
// AUDIT DOMAIN TYPES
// =============================================================================

/** Audit trace record */
export interface AuditTraceRecord {
  auditId?: number;
  action?: string;
  actionType?: string;
  entityType?: string;
  entityId?: number;
  entityName?: string;
  userId?: number;
  userEmail?: string;
  timestamp?: string;
  details?: string | null;
  ipAddress?: string | null;
  iconHint?: string;
  performedBy?: string;
  timeAgo?: string;
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

// =============================================================================
// CEPH DOMAIN TYPES
// =============================================================================

/** Ceph available machine for clone assignment */
export interface CephAvailableMachine {
  machineId?: number;
  machineGuid?: string;
  machineName: string;
  teamName?: string;
  assignmentStatus?: string;
  status?: string;
  description?: string;
  bridgeName?: string;
  regionName?: string;
}

/** Ceph clone machine info */
export interface CephCloneMachine {
  machineId?: number;
  machineGuid?: string;
  machineName: string;
  cloneName?: string;
  assignedAt?: string;
}

/** Ceph machine assignment status - matches GetMachineAssignmentStatus result */
export interface CephMachineAssignmentStatus {
  machineName: string | null;
  teamName: string | null;
  assignmentType: string | null;
  assignmentDetails: string | null;
  status: string | null;
}

/** Ceph machine assignment validation */
export interface CephMachineAssignmentValidation {
  machineId?: number;
  machineName?: string;
  isValid?: boolean;
  validationMessage?: string;
  conflictType?: string;
  conflictResource?: string;
}

// =============================================================================
// MACHINE DOMAIN TYPES
// =============================================================================

/** Machine assignment status */
export type MachineAssignmentStatus = 'ASSIGNED' | 'UNASSIGNED';

/** Machine assignment type */
export type MachineAssignmentType = 'AVAILABLE' | 'CLUSTER' | 'IMAGE' | 'CLONE';

// =============================================================================
// USER DOMAIN TYPES
// =============================================================================

/** User vault data */
export interface UserVault {
  vault: string;
  vaultVersion: number;
  userCredential: string | null;
}

// =============================================================================
// PERMISSION DOMAIN TYPES
// =============================================================================

/** Permission record - alias for generated type */
export type Permission = GetPermissionGroupDetails_ResultSet1;

// =============================================================================
// DROPDOWN DOMAIN TYPES
// =============================================================================

/** Generic dropdown option */
export interface DropdownOption {
  value: string;
  label: string;
  status?: string;
}

/** Machine dropdown option with additional properties */
export interface MachineDropdownOption extends DropdownOption {
  bridgeName?: string;
  regionName?: string;
  teamName?: string;
  status?: string;
}

/** Permission dropdown option */
export interface PermissionDropdownOption {
  name: string;
  description?: string;
}

/** Team dropdown option with status */
export interface TeamDropdownOption extends DropdownOption {
  status?: string;
}

/** Bridges grouped by region for dropdown */
export interface RegionBridges {
  regionName: string;
  bridges: DropdownOption[];
}

/** Machines grouped by team for dropdown */
export interface TeamMachines {
  teamName: string;
  machines: MachineDropdownOption[];
}

/** Company-wide dropdown data for forms */
export interface CompanyDropdownData {
  teams: TeamDropdownOption[];
  allTeams: TeamDropdownOption[];
  regions: DropdownOption[];
  machines: MachineDropdownOption[];
  bridges: DropdownOption[];
  bridgesByRegion: RegionBridges[];
  machinesByTeam: TeamMachines[];
  users: DropdownOption[];
  permissionGroups: DropdownOption[];
  permissions: PermissionDropdownOption[];
  subscriptionPlans: DropdownOption[];
}

// =============================================================================
// COMPANY DOMAIN TYPES
// =============================================================================

/** Company info from dashboard */
export interface CompanyInfo {
  companyName?: string;
  companyGuid?: string;
  Plan?: string;
}

/** Active subscription details */
export interface ActiveSubscription {
  planCode?: string;
  totalActivePurchases?: number;
  daysRemaining?: number;
  startDate?: string;
  endDate?: string;
  quantity?: number;
  isTrial?: number;
  isExpiringSoon?: boolean;
}

/** Plan limits from dashboard */
export interface PlanLimits {
  planCode?: string;
  machineLimit?: number;
  repositoryLimit?: number;
  userLimit?: number;
  maxActiveJobs?: number;
  maxReservedJobs?: number;
  jobTimeoutHours?: number;
  maxRepoSize?: number;
}

/** Account health status */
export interface AccountHealth {
  subscriptionStatus?: string;
  resourcesAtLimit?: number;
  resourcesNearLimit?: number;
  upgradeRecommendation?: string;
}

/** Queue team issue from dashboard */
export interface QueueTeamIssue {
  teamName: string;
  staleItems?: number;
  pendingItems?: number;
  activeItems?: number;
}

/** Queue machine issue from dashboard */
export interface QueueMachineIssue {
  machineName: string;
  teamName: string;
  staleItems?: number;
  pendingItems?: number;
  activeItems?: number;
}

/** Queue statistics from dashboard */
export interface DashboardQueueStats {
  pendingCount?: number;
  activeCount?: number;
  completedCount?: number;
  failedCount?: number;
  staleCount?: number;
  hasStaleItems?: number;
  hasOldPendingItems?: number;
  oldestPendingAgeMinutes?: number;
  createdToday?: number;
  completedToday?: number;
  cancelledToday?: number;
  failedToday?: number;
  highestPriorityPending?: number | null;
  highPriorityPending?: number;
  normalPriorityPending?: number;
  lowPriorityPending?: number;
  teamIssues?: QueueTeamIssue[];
  machineIssues?: QueueMachineIssue[];
}

/** Feature access flags */
export interface FeatureAccess {
  ceph?: boolean;
  auditLog?: boolean;
  advancedQueue?: boolean;
  hasAdvancedAnalytics?: boolean;
}

/** Resource usage item */
export interface ResourceUsageItem {
  resourceType: string;
  currentUsage: number;
  resourceLimit: number;
  usagePercentage: number;
  isLimitReached?: number;
  isNearLimit?: number;
}

/** Full company dashboard data */
export interface CompanyDashboardData {
  companyInfo?: CompanyInfo;
  activeSubscription?: ActiveSubscription;
  allActiveSubscriptions?: ActiveSubscription[];
  planLimits?: PlanLimits;
  accountHealth?: AccountHealth;
  queueStats?: DashboardQueueStats;
  featureAccess?: FeatureAccess;
  resources?: ResourceUsageItem[];
  cephStats?: CompanyCephStats;
}

/** Result from UpdateCompanyVaults operation */
export interface CompanyVaultUpdateResult {
  totalUpdated: number;
  failedCount: number;
}

/** Result from ImportCompanyData operation */
export interface CompanyImportResult {
  importedCount: number;
  skippedCount: number;
  errorCount: number;
}

// =============================================================================
// CEPH DASHBOARD TYPES
// =============================================================================

/** Ceph team breakdown for dashboard widget */
export interface CephTeamBreakdown {
  teamName: string;
  totalMachines: number;
  availableMachines: number;
  clusterMachines: number;
  imageMachines: number;
  cloneMachines: number;
}

/** Ceph statistics for company dashboard */
export interface CompanyCephStats {
  total_machines: number;
  truly_available_machines: number;
  cluster_assigned_machines: number;
  cluster_percentage: number;
  image_assigned_machines: number;
  image_percentage: number;
  clone_assigned_machines: number;
  clone_percentage: number;
  total_clusters?: number;
  avg_machines_per_cluster?: number;
  team_breakdown?: CephTeamBreakdown[];
}

/**
 * Derived Types - Utility types built on top of generated API schema
 *
 * These types provide convenience wrappers for common patterns like optional
 * vaultContent fields and partial parameter types for filtering.
 */

import type {
  GetOrganizationDashboard_ResultSet1,
  GetOrganizationDashboard_ResultSet2,
  GetOrganizationDashboard_ResultSet3,
  GetOrganizationDashboard_ResultSet4,
  GetOrganizationDashboard_ResultSet5,
  GetOrganizationDashboard_ResultSet6,
  GetOrganizationDashboard_ResultSet7,
  GetOrganizationDashboard_ResultSet8,
  GetOrganizationDashboard_ResultSet10,
  GetOrganizationDashboard_ResultSet11,
  GetOrganizationDashboard_ResultSet12,
  GetOrganizationDashboard_ResultSet13,
  GetOrganizationDashboard_ResultSet15,
  GetTeamQueueItemsParams,
} from './api-schema.generated';

// =============================================================================
// UTILITY TYPES
// =============================================================================

// Note: WithOptionalVault is no longer needed - vaultContent and vaultVersion
// are now optional with defaults in the generated API types (SQL defaults).
// Use CreateXxxParams directly from api-schema.generated.ts.

// Note: Use Partial<T> directly instead of OptionalParams<T>

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

// Note: Use CreateXxxParams directly from api-schema.generated.ts.
// vaultContent and vaultVersion are optional with SQL defaults.
// Example: Use CreateStorageParams directly for forms.

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
  vaultOrganization: string | null;
  organizationName: string | null;
  organization: string | null;
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
  isTFAEnabled?: boolean;
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

// Note: Use GetPermissionGroupDetails_ResultSet1 directly from api-schema.generated

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

/** Organization-wide dropdown data for forms */
export interface OrganizationDropdownData {
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
// ORGANIZATION DASHBOARD TYPES (from GetOrganizationDashboard result sets)
// =============================================================================

// Note: Use GetOrganizationDashboard_ResultSet* directly from api-schema.generated

/** Full organization dashboard data - composed from result sets */
export interface OrganizationDashboardData {
  organizationInfo: GetOrganizationDashboard_ResultSet1 | null;
  activeSubscription: GetOrganizationDashboard_ResultSet2 | null;
  allActiveSubscriptions: GetOrganizationDashboard_ResultSet3[];
  resources: GetOrganizationDashboard_ResultSet4[];
  accountHealth: GetOrganizationDashboard_ResultSet5 | null;
  featureAccess: GetOrganizationDashboard_ResultSet6 | null;
  planLimits: GetOrganizationDashboard_ResultSet7 | null;
  queueStats: GetOrganizationDashboard_ResultSet8 | null;
  teamIssues: GetOrganizationDashboard_ResultSet10[];
  machineIssues: GetOrganizationDashboard_ResultSet11[];
  activeUsers: GetOrganizationDashboard_ResultSet12[];
  cephStats: GetOrganizationDashboard_ResultSet13 | null;
  cephTeamBreakdown: GetOrganizationDashboard_ResultSet15[];
}

/** Result from UpdateOrganizationVaults operation */
export interface OrganizationVaultUpdateResult {
  totalUpdated: number;
  failedCount: number;
}

/** Result from ImportOrganizationData operation */
export interface OrganizationImportResult {
  importedCount: number;
  skippedCount: number;
  errorCount: number;
}

// =============================================================================
// ORGANIZATION VAULT TYPES
// =============================================================================

/** Organization vault item from GetOrganizationVaults */
export interface OrganizationVaultItem {
  entityType: string;
  entityId: number;
  entityName?: string;
  vaultId: number;
  vaultName: string;
  credential: string;
  decryptedVault?: string;
  version?: number;
}

/** Organization vaults collection */
export interface OrganizationVaultsData {
  allVaults: OrganizationVaultItem[];
}

// =============================================================================
// QUEUE FUNCTION TYPES (for queue vault / bridge functions)
// =============================================================================

/** Queue function parameter definition */
export interface QueueFunctionParameter {
  type: string;
  required?: boolean;
  default?: unknown;
  help?: string;
  label?: string;
  format?: string;
  units?: string[];
  options?: string[];
  ui?: string;
  checkboxOptions?: { value: string; label: string }[];
  enum?: string[];
}

/** Queue function resource requirements */
export interface QueueFunctionRequirements {
  machine?: boolean;
  team?: boolean;
  organization?: boolean;
  repository?: boolean;
  storage?: boolean;
  plugin?: boolean;
  bridge?: boolean;
}

/** Queue function definition (bridge function) */
export interface QueueFunction {
  name: string;
  description: string;
  category: string;
  params: Record<string, QueueFunctionParameter>;
  showInMenu?: boolean;
  requirements?: QueueFunctionRequirements;
}

// =============================================================================
// AUDIT PARAMS TYPE
// =============================================================================

/** Audit logs query parameters */
export interface AuditLogsParams {
  startDate?: string;
  endDate?: string;
  entityFilter?: string;
  maxRecords?: number;
}

// =============================================================================
// API HEALTH TYPES
// =============================================================================

/** API health check response */
export interface ApiHealthResponse {
  status: string;
  version: string;
  environment: string;
  instanceName: string;
  timestamp: string;
  uptime: {
    days: number;
    hours: number;
    minutes: number;
  };
  database: {
    status: string;
    database?: string;
    error?: string;
  };
  shuttingDown?: boolean;
  ciMode?: boolean;
}

export type MachineAssignmentType = 'AVAILABLE' | 'CLUSTER' | 'IMAGE' | 'CLONE';

export interface MachineAssignmentStatus {
  assignmentType: MachineAssignmentType;
  assignmentDetails: string;
  status?: string;
}

export interface Machine {
  machineName: string;
  machineGuid?: string;
  teamName: string;
  bridgeName: string;
  regionName?: string;
  queueCount: number;
  vaultVersion: number;
  vaultContent?: string;
  vaultStatus?: string;
  vaultStatusTime?: string;
  cephClusterName?: string;
  assignmentStatus?: MachineAssignmentStatus;
}

export interface Repo {
  repoName: string;
  repoGuid: string;
  teamName: string;
  vaultVersion: number;
  vaultContent?: string;
  grandGuid?: string;
  parentGuid?: string;
  repoTag?: string;
  repoNetworkId?: number;
  repoNetworkMode?: string;
}

export interface PluginContainer {
  name: string;
  image: string;
  status: string;
  [key: string]: unknown;
}

export interface Team {
  teamName: string;
  memberCount: number;
  machineCount: number;
  repoCount: number;
  storageCount: number;
  vaultContent?: string;
  vaultVersion: number;
}

export interface TeamMember {
  userEmail: string;
  isMember: boolean;
  hasAccess: boolean;
}

export interface Region {
  regionName: string;
  bridgeCount: number;
  vaultVersion: number;
  vaultContent?: string;
}

export interface Bridge {
  bridgeName: string;
  regionName: string;
  machineCount: number;
  vaultVersion: number;
  vaultContent?: string;
  bridgeCredentialsVersion?: number;
  bridgeCredentials?: string;
  bridgeUserEmail?: string;
  hasAccess?: number;
  managementMode?: string;
  isGlobalBridge?: boolean;
}

export interface BridgeAuthorizationToken {
  authToken?: string;
}

export interface Storage {
  storageName: string;
  teamName: string;
  vaultVersion: number;
  vaultContent?: string;
}

export interface CephCluster {
  clusterName: string;
  teamName?: string;
  vaultVersion: number;
  assignedMachineCount?: number;
  poolCount?: number;
  vaultContent?: string;
}

export interface CephPool {
  poolName: string;
  clusterName: string;
  teamName: string;
  vaultVersion?: number;
  rbdImageCount?: number;
  vaultContent?: string;
  poolGuid?: string;
}

export interface CephRbdImage {
  imageName: string;
  poolName: string;
  teamName: string;
  clusterName: string;
  machineName?: string;
  snapshotCount?: number;
  imageGuid?: string;
  vaultContent?: string;
}

export interface CephRbdSnapshot {
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
  clusterName: string;
  createdDate?: string;
  cloneCount?: number;
  snapshotGuid?: string;
  vaultContent?: string;
}

export interface CephRbdClone {
  cloneName: string;
  snapshotName: string;
  imageName: string;
  poolName: string;
  teamName: string;
  clusterName: string;
  snapshotCreatedDate?: string;
  vaultContent?: string;
}

export interface CephMachineAssignmentStatus {
  machineName: string;
  teamName: string;
  assignmentType: string;
  assignmentDetails: string;
  status: string;
}

export interface CephAvailableMachine {
  machineName: string;
  status: string;
  description: string;
  bridgeName?: string;
  regionName?: string;
}

export interface CephCloneMachine {
  machineName: string;
  bridgeName: string;
  assignmentId: number;
}

export interface CephMachineAssignmentValidation {
  machineName: string;
  isValid: boolean;
  error?: string;
}

export interface CompanyProfile extends Record<string, unknown> {
  companyName?: string;
  Plan?: string;
  planCode?: string;
}

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

export interface CompanyResourceLimit {
  resourceType: string;
  resourceLimit: number;
  activeSubscriptionTier: string;
  currentUsage: number;
  isLimitReached: number;
  usagePercentage: number;
}

export interface CompanyAccountHealth {
  resourcesAtLimit: number;
  resourcesNearLimit: number;
  subscriptionStatus: 'Critical' | 'Warning' | 'Good';
  upgradeRecommendation: string;
}

export interface CompanyFeatureAccess {
  hasAdvancedAnalytics: number;
  hasPrioritySupport: number;
  hasDedicatedAccount: number;
  hasCustomBranding: number;
}

export interface CompanyPlanLimits {
  maxActiveJobs: number;
  maxReservedJobs: number;
  jobTimeoutHours: number;
  maxRepoSize: number;
  planCode: string;
}

export interface CompanySubscriptionDetail {
  planCode: string;
  quantity: number;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  status: string;
  isTrial: number;
}

export interface QueueTeamIssue {
  teamName: string;
  totalItems: number;
  pendingItems: number;
  activeItems: number;
  staleItems: number;
}

export interface QueueMachineIssue {
  machineName: string;
  teamName: string;
  bridgeName: string;
  totalItems: number;
  pendingItems: number;
  activeItems: number;
  staleItems: number;
}

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

export interface CephTeamBreakdown {
  teamName: string;
  totalMachines: number;
  availableMachines: number;
  clusterMachines: number;
  imageMachines: number;
  cloneMachines: number;
}

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

export interface CompanyVaultDetails {
  vault: string;
  vaultVersion: number;
  companyCredential?: string | null;
}

export interface CompanyVaultRecord extends Record<string, unknown> {
  entityType?: string;
  entityIdentifier?: string;
  vaultContent?: string;
  vaultVersion?: number;
  vaultType?: string;
}

export interface CompanyVaultCollections {
  vaults: CompanyVaultRecord[];
  bridgesWithRequestToken: CompanyVaultRecord[];
}

export interface CompanyVaultUpdateResult {
  totalUpdated: number;
  failedCount: number;
}

export interface CompanyImportResult {
  importedCount: number;
  skippedCount: number;
  errorCount: number;
}

export type CompanyExportData = Record<string, unknown>;

export interface CompanyBlockUserRequestsResult {
  deactivatedCount: number;
}

export interface CompanyDropdownBridge {
  value: string;
  label: string;
  machineCount?: number;
}

export interface CompanyDropdownRegion {
  regionName: string;
  bridges: CompanyDropdownBridge[];
}

export interface CompanyDropdownMachine {
  value: string;
  label: string;
  bridgeName: string;
  regionName: string;
}

export interface CompanyDropdownData {
  teams: Array<{ value: string; label: string }>;
  allTeams: Array<{ value: string; label: string; memberCount: number }>;
  regions: Array<{ value: string; label: string; bridgeCount: number }>;
  machines?: string[];
  bridges?: Array<{ value: string; label: string }>;
  bridgesByRegion: CompanyDropdownRegion[];
  machinesByTeam: Array<{
    teamName: string;
    machines: CompanyDropdownMachine[];
  }>;
  users: Array<{ value: string; label: string; status: string }>;
  permissionGroups: Array<{
    value: string;
    label: string;
    userCount: number;
    permissionCount: number;
  }>;
  permissions: Array<{ name: string; value: string }>;
  subscriptionPlans: Array<{ value: string; label: string; description: string }>;
  requestContext?: string;
  currentUser?: string;
  userRole?: string;
}

export interface CompanyGraphNode extends Record<string, unknown> {
  nodeType: string;
  nodeId: string;
  name: string;
  label: string;
  hierarchyLevel: string;
}

export interface CompanyGraphRelationship {
  source: string;
  target: string;
  relationshipType: string;
  label: string;
}

export interface CompanyDataGraph {
  metadata: {
    currentUser: string;
    userRole: string;
    generatedAt: string;
    dataFormat: string;
  };
  nodes: Record<string, CompanyGraphNode[]>;
  relationships: Record<string, CompanyGraphRelationship[]>;
  summary: {
    userTeamCount: number;
    accessibleMachines: number;
    totalQueueItems: number;
    isAdministrator: boolean;
    companyName: string;
  };
}

export interface User {
  userEmail: string;
  companyName: string;
  activated: boolean;
  lastActive?: string;
  permissionGroupName?: string;
  permissionsName?: string;
}

export interface PermissionGroup {
  permissionGroupName: string;
  userCount: number;
  permissionCount: number;
  permissions?: string[];
}

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

export interface Permission {
  permissionName: string;
  description?: string;
}

export type QueueStatus =
  | 'PENDING'
  | 'ASSIGNED'
  | 'PROCESSING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'FAILED';

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

export interface QueueItem {
  taskId: string;
  teamName: string;
  machineName: string;
  bridgeName: string;
  regionName: string;
  vaultContent: string;
  vaultVersion: number;
  vaultContentResponse?: string;
  vaultVersionResponse?: number;
  status: QueueStatus;
  priority?: number;
  priorityLabel?: string;
  createdTime: string;
  ageInMinutes: number;
  assignedTime?: string;
  lastAssigned?: string;
  minutesSinceAssigned?: number;
  healthStatus: QueueHealthStatus;
  canBeCancelled: boolean;
  hasResponse: boolean;
  retryCount?: number;
  lastRetryAt?: string;
  lastFailureReason?: string;
  lastResponseAt?: string;
  permanentlyFailed?: boolean;
  createdBy?: string;
  totalDurationSeconds?: number;
  processingDurationSeconds?: number;
  Status?: string;
}

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

export interface QueueTraceLog {
  timestamp?: string;
  action?: string;
  status?: string;
  message?: string;
  details?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface QueueVaultSnapshot {
  hasContent: boolean;
  vaultVersion?: number;
  vaultContent?: string | Record<string, unknown>;
  updatedAt?: string;
}

export type QueueRelativePosition = 'Before' | 'After' | 'Current';

export interface QueuePositionEntry {
  taskId: string;
  status: QueueStatus;
  createdTime: string;
  relativePosition: QueueRelativePosition | string;
}

export interface QueueMachineStats {
  currentQueueDepth: number;
  activeProcessingCount: number;
  maxConcurrentTasks?: number;
}

export interface QueuePlanInfo {
  planId?: string;
  planName?: string;
  planDescription?: string;
  expiresAt?: string;
}

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

export interface QueueTrace {
  summary: QueueTraceSummary | null;
  queueDetails: QueueItem | null;
  traceLogs: QueueTraceLog[];
  vaultContent: QueueVaultSnapshot | null;
  responseVaultContent: QueueVaultSnapshot | null;
  queuePosition: QueuePositionEntry[];
  machineStats: QueueMachineStats | null;
  planInfo: QueuePlanInfo | null;
}

export interface QueueListResult {
  items: QueueItem[];
  statistics: QueueStatistics | null;
}

export interface UserVault {
  vault: string;
  vaultVersion: number;
  userCredential: string | null;
}

export interface AuthRequestStatus {
  isTFAEnabled: boolean;
  isAuthorized: boolean;
  authenticationStatus: string;
}

export interface AuthLoginResult {
  isAuthorized: boolean;
  authenticationStatus: string;
  vaultCompany: string | null;
  companyName: string | null;
  company?: string | null;
  preferredLanguage?: string | null;
}

export interface EnableTfaResponse {
  secret?: string;
  userEmail?: string;
  authType?: string;
  result?: string;
}

export interface VerifyTfaResult {
  isAuthorized: boolean;
  result?: string;
  hasTFAEnabled?: boolean;
}

export interface ForkSessionCredentials {
  requestToken: string | null;
  nextRequestToken: string | null;
  parentRequestId: number | null;
}

export interface AuditLogEntry {
  entity: string;
  entityName: string;
  action: string;
  details: string;
  actionByUser: string;
  timestamp: string;
}

export interface AuditTraceRecord {
  action: string;
  details: string;
  performedBy: string;
  timestamp: string;
  actionType: string;
  timeAgo: string;
  iconHint: string;
}

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

export interface AuditTraceResponse {
  records: AuditTraceRecord[];
  summary: AuditTraceSummary;
}

export type AuditHistoryEntry = AuditLogEntry;

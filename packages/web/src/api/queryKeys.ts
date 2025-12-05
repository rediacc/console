/**
 * Centralized Query Keys Registry
 *
 * Single source of truth for all React Query cache keys across the application.
 * Using this registry ensures consistency, prevents typos, and makes cache
 * invalidation more reliable and maintainable.
 *
 * Pattern follows the structure from distributedStorage.ts with DS_QUERY_KEYS.
 * Each resource has its own namespace with query key factory functions.
 *
 * @example
 * // Instead of: queryKey: ['queue-items', filters]
 * // Use: queryKey: QUERY_KEYS.queue.items(filters)
 *
 * @example
 * // Instead of: queryClient.invalidateQueries({ queryKey: ['teams'] })
 * // Use: queryClient.invalidateQueries({ queryKey: QUERY_KEYS.teams.all })
 */

/**
 * Base key strings for use with mutation factories that expect string arrays
 * The mutation factory wraps each string in an array automatically
 */
export const QUERY_KEY_STRINGS = {
  teams: 'teams',
  teamMembers: 'team-members',
  machines: 'machines',
  users: 'users',
  bridges: 'bridges',
  dropdown: 'dropdown-data',
  permissionGroups: 'permissionGroups',
  permissionGroup: 'permissionGroup',
  company: 'company',
  companyVault: 'company-vault',
  queueItems: 'queue-items',
} as const;

export const QUERY_KEYS = {
  // Queue
  queue: {
    items: (filters?: unknown) => ['queue-items', filters] as const,
    next: (machineName: string, itemCount: number) =>
      ['queue-next', machineName, itemCount] as const,
    itemsByBridge: (bridgeName: string) => ['queue-items-bridge', bridgeName] as const,
    itemTrace: (taskId: string | null) => ['queue-item-trace', taskId] as const,
  },

  // Teams
  teams: {
    all: ['teams'] as const,
    members: (teamName: string) => ['team-members', teamName] as const,
  },

  // Machines
  machines: {
    all: 'machines' as const,
  },

  // Users
  users: {
    all: ['users'] as const,
    requests: ['user-requests'] as const,
    vault: ['user-vault'] as const,
  },

  // Permissions
  permissions: {
    groups: ['permissionGroups'] as const,
    group: (groupName: string) => ['permissionGroup', groupName] as const,
    groupsList: ['permission-groups'] as const,
  },

  // Company
  company: {
    info: ['company-info'] as const,
    base: ['company'] as const,
    vault: (company?: string) => ['company-vault', company] as const,
    allVaults: ['company-all-vaults'] as const,
    exportData: ['company-export-data'] as const,
  },

  // Dashboard
  dashboard: {
    data: ['dashboard'] as const,
  },

  // Audit
  audit: {
    logs: (params?: unknown) => ['auditLogs', params] as const,
    recentLogs: (maxRecords?: number) => ['recentAuditLogs', maxRecords] as const,
    entityTrace: (entityType?: string, entityIdentifier?: string) =>
      ['entityAuditTrace', entityType, entityIdentifier] as const,
  },

  // Storage
  storage: {
    list: (teamFilter?: string | string[]) => ['storage', teamFilter] as const,
  },

  // Bridges
  bridges: {
    list: (regionName?: string) => ['bridges', regionName] as const,
  },

  // Regions
  regions: {
    all: ['regions'] as const,
    bridges: (regionName: string) => ['region-bridges', regionName] as const,
  },

  // Repos
  repos: {
    all: 'repos' as const,
  },

  // Architecture
  architecture: {
    company: ['companyArchitecture'] as const,
  },

  // Two Factor Authentication
  twoFactor: {
    status: (userEmail?: string) => ['tfa-status', userEmail] as const,
  },

  // Vault Protocol
  vaultProtocol: {
    companyVault: ['company-vault'] as const,
  },

  // Health
  health: {
    api: ['apiHealth'] as const,
  },

  // Dropdown Data (cached dropdown options)
  dropdown: {
    data: (context?: string) => ['dropdown-data', context] as const,
  },

  // Distributed Storage (re-exported from distributedStorage.ts)
  distributedStorage: {
    clusters: (teamFilter?: string | string[]) =>
      ['distributed-storage-clusters', teamFilter] as const,
    pools: (teamFilter?: string | string[]) => ['distributed-storage-pools', teamFilter] as const,
    images: (poolName?: string, teamName?: string) =>
      ['distributed-storage-images', poolName, teamName] as const,
    snapshots: (imageName?: string, poolName?: string, teamName?: string) =>
      ['distributed-storage-snapshots', imageName, poolName, teamName] as const,
    clones: (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) =>
      ['distributed-storage-clones', snapshotName, imageName, poolName, teamName] as const,
    clusterMachines: (clusterName: string) =>
      ['distributed-storage-cluster-machines', clusterName] as const,
    machineAssignmentStatus: (machineName: string, teamName: string) =>
      ['machine-assignment-status', machineName, teamName] as const,
    availableMachinesForClone: (teamName: string) =>
      ['available-machines-for-clone', teamName] as const,
    cloneMachines: (
      cloneName: string,
      snapshotName: string,
      imageName: string,
      poolName: string,
      teamName: string
    ) => ['clone-machines', cloneName, snapshotName, imageName, poolName, teamName] as const,
    machineAssignmentValidation: (teamName: string, machineNames: string) =>
      ['machine-assignment-validation', teamName, machineNames] as const,
  },
} as const;

// Type helpers for better TypeScript support
export type QueryKeys = typeof QUERY_KEYS;

// Helper type to extract the return type of query key functions
export type QueryKey<T extends (...args: any[]) => any> = ReturnType<T>;

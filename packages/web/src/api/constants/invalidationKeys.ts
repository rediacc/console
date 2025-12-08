/**
 * Standardized cache invalidation key sets for React Query.
 * Use these instead of hardcoding invalidation arrays in mutations.
 */
export const INVALIDATION_SETS = {
  teamResources: ['teams', 'dropdown-data', 'machines', 'repos'] as const,
  machineResources: ['machines', 'teams', 'dropdown-data'] as const,
  storageResources: ['storage', 'teams'] as const,
  permissionResources: ['permissions', 'permission-groups', 'users'] as const,
  queueResources: ['queue', 'queue-items'] as const,
  bridgeResources: ['bridges', 'teams', 'dropdown-data'] as const,
  regionResources: ['regions', 'dropdown-data'] as const,
  repoResources: ['repos', 'machines', 'teams', 'dropdown-data'] as const,
  companyResources: ['company'] as const,
  userResources: ['users', 'dropdown-data'] as const,
  cephResources: [
    'ceph-clusters',
    'ceph-pools',
    'ceph-images',
    'ceph-snapshots',
    'ceph-clones',
  ] as const,
} as const;

export type InvalidationSet = keyof typeof INVALIDATION_SETS;

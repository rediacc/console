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

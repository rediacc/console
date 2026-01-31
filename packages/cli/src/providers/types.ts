/**
 * StateProvider interfaces - abstract layer for state management.
 * Three implementations: CloudStateProvider, S3StateProvider, LocalStateProvider.
 */

import type { ContextMode } from '../types/index.js';

/** Generic mutation result */
export interface MutationResult {
  success: boolean;
  message?: string;
  [key: string]: unknown;
}

/** Generic resource record */
export type ResourceRecord = Record<string, unknown>;

/** Vault data */
export type VaultData = Record<string, unknown>;

/** Vault item from API */
export interface VaultItem {
  vaultType?: string;
  vaultContent?: string;
  vaultVersion?: number;
  [key: string]: unknown;
}

// ============================================================================
// Sub-Provider Interfaces
// ============================================================================

export interface MachineProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  getVault(params: Record<string, unknown>): Promise<VaultItem[] | { vaults: VaultItem[] }>;
  updateVault(params: Record<string, unknown>): Promise<MutationResult>;
}

export interface QueueProvider {
  list(params: { teamName: string; maxRecords?: number }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<{ taskId?: string }>;
  trace(taskId: string): Promise<ResourceRecord | null>;
  cancel(taskId: string): Promise<void>;
  retry(taskId: string): Promise<void>;
  delete(taskId: string): Promise<void>;
}

export interface StorageProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  getVault(params: Record<string, unknown>): Promise<VaultItem[] | { vaults: VaultItem[] }>;
  updateVault(params: Record<string, unknown>): Promise<MutationResult>;
}

export interface RepositoryProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  getVault(params: Record<string, unknown>): Promise<VaultItem[] | { vaults: VaultItem[] }>;
  updateVault(params: Record<string, unknown>): Promise<MutationResult>;
}

export interface VaultProvider {
  getTeamVault(teamName: string): Promise<VaultData | null>;
  getMachineVault(teamName: string, machineName: string): Promise<VaultData | null>;
  getOrganizationVault(): Promise<VaultData | null>;
  getConnectionVaults(
    teamName: string,
    machineName: string,
    repositoryName?: string
  ): Promise<{
    machineVault: VaultData;
    teamVault: VaultData;
    repositoryVault?: VaultData;
  }>;
}

// ============================================================================
// Aggregate Interface
// ============================================================================

export interface IStateProvider {
  readonly mode: ContextMode;
  readonly machines: MachineProvider;
  readonly queue: QueueProvider;
  readonly storage: StorageProvider;
  readonly repositories: RepositoryProvider;
  readonly vaults: VaultProvider;
}

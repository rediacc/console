/**
 * StateProvider interfaces - abstract layer for state management.
 * Single implementation: LocalStateProvider (config-file backed).
 */

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

/** Machine data including vaultStatus for health/containers/services/repos/vault-status commands */
export interface MachineWithVaultStatusData {
  machineName: string | null;
  vaultStatus?: string | null;
  vaultContent?: string | null;
  vaultVersion?: number | null;
  [key: string]: unknown;
}

export interface MachineProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  /** Get a single machine with vaultStatus data (for health/services/containers/repos) */
  getWithVaultStatus(params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null>;
}

export interface StorageProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  getVault(params: Record<string, unknown>): Promise<VaultItem[] | { vaults: VaultItem[] }>;
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
  readonly machines: MachineProvider;
  readonly storage: StorageProvider;
  readonly vaults: VaultProvider;
}

/** Parsed vault content - either an object or JSON string */
export type VaultContent = Record<string, unknown> | string | null;

export interface QueueRequestContext {
  teamName: string;
  machineName?: string | null;
  bridgeName?: string;
  repositoryGuid?: string;
  repositoryName?: string;
  repositoryNetworkId?: number;
  repositoryNetworkMode?: string;
  repositoryTag?: string;
  storageName?: string;
  functionName: string;
  params: Record<string, unknown>;
  priority: number;
  addedVia: string;
  /** User's preferred language for task output (en, de, es, fr, ja, ar, ru, tr, zh) */
  language?: string;
  teamVault?: VaultContent;
  machineVault?: VaultContent;
  repositoryVault?: VaultContent;
  bridgeVault?: VaultContent;
  organizationVault?: VaultContent;
  organizationCredential?: string;
  storageVault?: VaultContent;
  destinationMachineVault?: VaultContent;
  destinationStorageVault?: VaultContent;
  destinationRepositoryVault?: VaultContent;
  sourceMachineVault?: VaultContent;
  sourceStorageVault?: VaultContent;
  sourceRepositoryVault?: VaultContent;
  allRepositoryCredentials?: Record<string, string>;
  allRepositories?: Record<string, string>;
  additionalStorageData?: Record<string, VaultContent>;
  additionalMachineData?: Record<string, VaultContent>;
}

export interface FunctionRequirements {
  machine?: boolean;
  team?: boolean;
  organization?: boolean;
  repository?: boolean;
  storage?: boolean;
  plugin?: boolean;
  bridge?: boolean;
}

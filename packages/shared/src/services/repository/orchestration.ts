/**
 * Repository orchestration service
 * High-level functions that prepare complete operation contexts
 * These functions return everything the UI/CLI needs to execute operations
 */

import { canBackupToStorage } from './backup-validation';
import { isFork, type RepositoryWithRelations } from './core';
import { canDeleteFork, findForkParent } from './fork-operations';
import { type ChildClone, canDeleteGrandRepo } from './grand-deletion';
import { canPromoteToGrand, findSiblingClones, type SiblingClone } from './promotion';

/**
 * Base operation context
 */
export interface OperationContext {
  status: 'ready' | 'error' | 'blocked' | 'warning';
  errorCode?: string;
}

/**
 * Context for fork deletion operation
 */
export interface ForkDeletionContext extends OperationContext {
  repositoryGuid?: string;
  grandGuid?: string;
  parentName?: string;
  repositoryNetworkId?: number;
  repositoryTag?: string | null;
}

/**
 * Context for grand repository deletion operation
 */
export interface GrandDeletionContext extends OperationContext {
  repositoryGuid?: string;
  childClones: ChildClone[];
  repositoryNetworkId?: number;
  repositoryTag?: string | null;
}

/**
 * Context for promotion operation
 */
export interface PromotionContext extends OperationContext {
  repositoryGuid?: string;
  currentGrandName: string;
  siblingClones: SiblingClone[];
}

/**
 * Context for backup operation
 */
export interface BackupContext extends OperationContext {
  repositoryGuid?: string;
  grandGuid?: string;
  canBackupToStorage: boolean;
  canBackupToMachine: boolean;
  storageBlockReason?: string;
  repositoryNetworkId?: number;
  repositoryNetworkMode?: string;
  repositoryTag?: string | null;
}

/**
 * Context for fork (clone) operation
 */
export interface ForkCreationContext extends OperationContext {
  repositoryGuid?: string;
  grandGuid?: string;
  repositoryNetworkId?: number;
  repositoryNetworkMode?: string;
  repositoryTag?: string | null;
  mounted?: boolean;
}

/**
 * Prepare context for fork deletion
 * Returns all data needed to execute fork deletion
 * @param repositoryName - Name of the repository
 * @param repositoryTag - Tag of the repository
 * @param allRepositories - Array of all repositories
 * @returns Fork deletion context with all required data
 */
export function prepareForkDeletion(
  repositoryName: string,
  repositoryTag: string | undefined,
  allRepositories: RepositoryWithRelations[]
): ForkDeletionContext {
  // Find the repository
  const repositoryData = allRepositories.find(
    (r) => r.repositoryName === repositoryName && r.repositoryTag === (repositoryTag || 'latest')
  );

  if (!repositoryData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: [],
    } as ForkDeletionContext;
  }

  // Validate it's a fork
  const validation = canDeleteFork(repositoryData);
  if (!validation.canDelete) {
    return {
      status: 'error',
      errorCode: 'NOT_A_FORK',
      childClones: [],
    } as ForkDeletionContext;
  }

  // Get parent info
  const parent = findForkParent(repositoryData, allRepositories);

  return {
    status: 'ready',
    repositoryGuid: repositoryData.repositoryGuid,
    grandGuid: repositoryData.grandGuid || undefined,
    parentName: parent?.repositoryName,
    repositoryNetworkId: repositoryData.repositoryNetworkId ?? undefined,
    repositoryTag: repositoryData.repositoryTag ?? undefined,
  };
}

/**
 * Prepare context for grand repository deletion
 * Returns all data needed to execute grand deletion
 * @param repositoryName - Name of the repository
 * @param repositoryTag - Tag of the repository
 * @param allRepositories - Array of all repositories
 * @returns Grand deletion context with all required data
 */
export function prepareGrandDeletion(
  repositoryName: string,
  repositoryTag: string | undefined,
  allRepositories: RepositoryWithRelations[]
): GrandDeletionContext {
  // Find the repository
  const repositoryData = allRepositories.find(
    (r) => r.repositoryName === repositoryName && r.repositoryTag === (repositoryTag || 'latest')
  );

  if (!repositoryData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: [],
    };
  }

  // Validate it's a grand repository
  if (isFork(repositoryData)) {
    return {
      status: 'error',
      errorCode: 'NOT_A_GRAND',
      childClones: [],
    };
  }

  // Check for child clones
  const validation = canDeleteGrandRepo(repositoryData, allRepositories);

  if (!validation.canDelete) {
    return {
      status: 'blocked',
      errorCode: 'HAS_CHILD_CLONES',
      repositoryGuid: repositoryData.repositoryGuid,
      childClones: validation.childClones,
      repositoryNetworkId: repositoryData.repositoryNetworkId ?? undefined,
      repositoryTag: repositoryData.repositoryTag ?? undefined,
    };
  }

  return {
    status: 'ready',
    repositoryGuid: repositoryData.repositoryGuid,
    childClones: [],
    repositoryNetworkId: repositoryData.repositoryNetworkId ?? undefined,
    repositoryTag: repositoryData.repositoryTag ?? undefined,
  };
}

/**
 * Prepare context for promotion operation
 * Returns all data needed to execute promotion
 * @param repositoryName - Name of the repository
 * @param repositoryTag - Tag of the repository
 * @param allRepositories - Array of all repositories
 * @returns Promotion context with all required data
 */
export function preparePromotion(
  repositoryName: string,
  repositoryTag: string | undefined,
  allRepositories: RepositoryWithRelations[]
): PromotionContext {
  // Find the repository
  const repositoryData = allRepositories.find(
    (r) => r.repositoryName === repositoryName && r.repositoryTag === (repositoryTag || 'latest')
  );

  if (!repositoryData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      currentGrandName: '',
      siblingClones: [],
    };
  }

  // Validate it can be promoted
  const validation = canPromoteToGrand(repositoryData);
  if (!validation.canPromote) {
    return {
      status: 'error',
      errorCode: 'ALREADY_GRAND',
      currentGrandName: '',
      siblingClones: [],
    };
  }

  // Get affected siblings
  const { siblingClones, currentGrandName } = findSiblingClones(repositoryData, allRepositories);

  return {
    status: 'ready',
    repositoryGuid: repositoryData.repositoryGuid,
    currentGrandName,
    siblingClones,
  };
}

/**
 * Prepare context for backup operation
 * Returns all data needed to execute backup
 * @param repositoryName - Name of the repository
 * @param repositoryTag - Tag of the repository
 * @param allRepositories - Array of all repositories
 * @returns Backup context with all required data
 */
export function prepareBackup(
  repositoryName: string,
  repositoryTag: string | undefined,
  allRepositories: RepositoryWithRelations[]
): BackupContext {
  // Find the repository
  const repositoryData = allRepositories.find(
    (r) => r.repositoryName === repositoryName && r.repositoryTag === (repositoryTag || 'latest')
  );

  if (!repositoryData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      canBackupToStorage: false,
      canBackupToMachine: false,
    };
  }

  // Check backup capabilities
  const storageValidation = canBackupToStorage(repositoryData);

  return {
    status: 'ready',
    repositoryGuid: repositoryData.repositoryGuid,
    grandGuid: repositoryData.grandGuid || repositoryData.repositoryGuid,
    canBackupToStorage: storageValidation.canBackup,
    canBackupToMachine: true, // Always allowed
    storageBlockReason: storageValidation.reason,
    repositoryNetworkId: repositoryData.repositoryNetworkId ?? undefined,
    repositoryNetworkMode: repositoryData.repositoryNetworkMode ?? undefined,
    repositoryTag: repositoryData.repositoryTag ?? undefined,
  };
}

/**
 * Prepare context for fork (clone) creation
 * Returns all data needed to create a fork
 * @param repositoryName - Name of the repository to fork
 * @param repositoryTag - Tag of the repository to fork
 * @param allRepositories - Array of all repositories
 * @returns Fork creation context with all required data
 */
export function prepareForkCreation(
  repositoryName: string,
  repositoryTag: string | undefined,
  allRepositories: RepositoryWithRelations[]
): ForkCreationContext {
  // Find the repository
  const repositoryData = allRepositories.find(
    (r) => r.repositoryName === repositoryName && r.repositoryTag === (repositoryTag || 'latest')
  );

  if (!repositoryData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
    };
  }

  // Get the grand GUID for the new fork
  // If forking a fork, use the same grand
  // If forking a credential, the credential becomes the grand
  const grandGuid = repositoryData.grandGuid || repositoryData.repositoryGuid;

  return {
    status: 'ready',
    repositoryGuid: repositoryData.repositoryGuid,
    grandGuid,
    repositoryNetworkId: repositoryData.repositoryNetworkId ?? undefined,
    repositoryNetworkMode: repositoryData.repositoryNetworkMode ?? undefined,
    repositoryTag: repositoryData.repositoryTag ?? undefined,
    mounted: repositoryData.mounted,
  };
}

/**
 * Get the grand repository vault for an operation
 * @param repositoryGuid - GUID of the repository
 * @param grandGuid - GUID of the grand repository
 * @param allRepositories - Array of all repositories with vault content
 * @returns The vault content to use for the operation
 */
export function getGrandVaultForOperation(
  repositoryGuid: string,
  grandGuid: string | null | undefined,
  allRepositories: RepositoryWithRelations[]
): string | null | undefined {
  // If has a grand, use the grand's vault
  if (grandGuid && grandGuid !== repositoryGuid) {
    const grandRepo = allRepositories.find((r) => r.repositoryGuid === grandGuid);
    return grandRepo?.vaultContent;
  }

  // Otherwise use the repository's own vault
  const repository = allRepositories.find((r) => r.repositoryGuid === repositoryGuid);
  return repository?.vaultContent;
}

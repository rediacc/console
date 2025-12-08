/**
 * Repo orchestration service
 * High-level functions that prepare complete operation contexts
 * These functions return everything the UI/CLI needs to execute operations
 */

import { canBackupToStorage } from './backup-validation';
import { type RepoWithRelations, isFork } from './core';
import { canDeleteFork, findForkParent } from './fork-operations';
import { canDeleteGrandRepo, type ChildClone } from './grand-deletion';
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
  repoGuid?: string;
  grandGuid?: string;
  parentName?: string;
  repoNetworkId?: number;
  repoTag?: string | null;
}

/**
 * Context for grand repo deletion operation
 */
export interface GrandDeletionContext extends OperationContext {
  repoGuid?: string;
  childClones: ChildClone[];
  repoNetworkId?: number;
  repoTag?: string | null;
}

/**
 * Context for promotion operation
 */
export interface PromotionContext extends OperationContext {
  repoGuid?: string;
  currentGrandName: string;
  siblingClones: SiblingClone[];
}

/**
 * Context for backup operation
 */
export interface BackupContext extends OperationContext {
  repoGuid?: string;
  grandGuid?: string;
  canBackupToStorage: boolean;
  canBackupToMachine: boolean;
  storageBlockReason?: string;
  repoNetworkId?: number;
  repoNetworkMode?: string;
  repoTag?: string | null;
}

/**
 * Context for fork (clone) operation
 */
export interface ForkCreationContext extends OperationContext {
  repoGuid?: string;
  grandGuid?: string;
  repoNetworkId?: number;
  repoNetworkMode?: string;
  repoTag?: string | null;
  mounted?: boolean;
}

/**
 * Prepare context for fork deletion
 * Returns all data needed to execute fork deletion
 * @param repoName - Name of the repo
 * @param repoTag - Tag of the repo
 * @param allRepos - Array of all repos
 * @returns Fork deletion context with all required data
 */
export function prepareForkDeletion(
  repoName: string,
  repoTag: string | undefined,
  allRepos: RepoWithRelations[]
): ForkDeletionContext {
  // Find the repo
  const repoData = allRepos.find(
    (r) => r.repoName === repoName && r.repoTag === (repoTag || 'latest')
  );

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: [],
    } as ForkDeletionContext;
  }

  // Validate it's a fork
  const validation = canDeleteFork(repoData);
  if (!validation.canDelete) {
    return {
      status: 'error',
      errorCode: 'NOT_A_FORK',
      childClones: [],
    } as ForkDeletionContext;
  }

  // Get parent info
  const parent = findForkParent(repoData, allRepos);

  return {
    status: 'ready',
    repoGuid: repoData.repoGuid,
    grandGuid: repoData.grandGuid || undefined,
    parentName: parent?.repoName,
    repoNetworkId: repoData.repoNetworkId ?? undefined,
    repoTag: repoData.repoTag ?? undefined,
  };
}

/**
 * Prepare context for grand repo deletion
 * Returns all data needed to execute grand deletion
 * @param repoName - Name of the repo
 * @param repoTag - Tag of the repo
 * @param allRepos - Array of all repos
 * @returns Grand deletion context with all required data
 */
export function prepareGrandDeletion(
  repoName: string,
  repoTag: string | undefined,
  allRepos: RepoWithRelations[]
): GrandDeletionContext {
  // Find the repo
  const repoData = allRepos.find(
    (r) => r.repoName === repoName && r.repoTag === (repoTag || 'latest')
  );

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: [],
    };
  }

  // Validate it's a grand repo
  if (isFork(repoData)) {
    return {
      status: 'error',
      errorCode: 'NOT_A_GRAND',
      childClones: [],
    };
  }

  // Check for child clones
  const validation = canDeleteGrandRepo(repoData, allRepos);

  if (!validation.canDelete) {
    return {
      status: 'blocked',
      errorCode: 'HAS_CHILD_CLONES',
      repoGuid: repoData.repoGuid,
      childClones: validation.childClones,
      repoNetworkId: repoData.repoNetworkId ?? undefined,
      repoTag: repoData.repoTag ?? undefined,
    };
  }

  return {
    status: 'ready',
    repoGuid: repoData.repoGuid,
    childClones: [],
    repoNetworkId: repoData.repoNetworkId ?? undefined,
    repoTag: repoData.repoTag ?? undefined,
  };
}

/**
 * Prepare context for promotion operation
 * Returns all data needed to execute promotion
 * @param repoName - Name of the repo
 * @param repoTag - Tag of the repo
 * @param allRepos - Array of all repos
 * @returns Promotion context with all required data
 */
export function preparePromotion(
  repoName: string,
  repoTag: string | undefined,
  allRepos: RepoWithRelations[]
): PromotionContext {
  // Find the repo
  const repoData = allRepos.find(
    (r) => r.repoName === repoName && r.repoTag === (repoTag || 'latest')
  );

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      currentGrandName: '',
      siblingClones: [],
    };
  }

  // Validate it can be promoted
  const validation = canPromoteToGrand(repoData);
  if (!validation.canPromote) {
    return {
      status: 'error',
      errorCode: 'ALREADY_GRAND',
      currentGrandName: '',
      siblingClones: [],
    };
  }

  // Get affected siblings
  const { siblingClones, currentGrandName } = findSiblingClones(repoData, allRepos);

  return {
    status: 'ready',
    repoGuid: repoData.repoGuid,
    currentGrandName,
    siblingClones,
  };
}

/**
 * Prepare context for backup operation
 * Returns all data needed to execute backup
 * @param repoName - Name of the repo
 * @param repoTag - Tag of the repo
 * @param allRepos - Array of all repos
 * @returns Backup context with all required data
 */
export function prepareBackup(
  repoName: string,
  repoTag: string | undefined,
  allRepos: RepoWithRelations[]
): BackupContext {
  // Find the repo
  const repoData = allRepos.find(
    (r) => r.repoName === repoName && r.repoTag === (repoTag || 'latest')
  );

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      canBackupToStorage: false,
      canBackupToMachine: false,
    };
  }

  // Check backup capabilities
  const storageValidation = canBackupToStorage(repoData);

  return {
    status: 'ready',
    repoGuid: repoData.repoGuid,
    grandGuid: repoData.grandGuid || repoData.repoGuid,
    canBackupToStorage: storageValidation.canBackup,
    canBackupToMachine: true, // Always allowed
    storageBlockReason: storageValidation.reason,
    repoNetworkId: repoData.repoNetworkId ?? undefined,
    repoNetworkMode: repoData.repoNetworkMode ?? undefined,
    repoTag: repoData.repoTag ?? undefined,
  };
}

/**
 * Prepare context for fork (clone) creation
 * Returns all data needed to create a fork
 * @param repoName - Name of the repo to fork
 * @param repoTag - Tag of the repo to fork
 * @param allRepos - Array of all repos
 * @returns Fork creation context with all required data
 */
export function prepareForkCreation(
  repoName: string,
  repoTag: string | undefined,
  allRepos: RepoWithRelations[]
): ForkCreationContext {
  // Find the repo
  const repoData = allRepos.find(
    (r) => r.repoName === repoName && r.repoTag === (repoTag || 'latest')
  );

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
    };
  }

  // Get the grand GUID for the new fork
  // If forking a fork, use the same grand
  // If forking a credential, the credential becomes the grand
  const grandGuid = repoData.grandGuid || repoData.repoGuid;

  return {
    status: 'ready',
    repoGuid: repoData.repoGuid,
    grandGuid,
    repoNetworkId: repoData.repoNetworkId ?? undefined,
    repoNetworkMode: repoData.repoNetworkMode ?? undefined,
    repoTag: repoData.repoTag ?? undefined,
    mounted: repoData.mounted,
  };
}

/**
 * Get the grand repo vault for an operation
 * @param repoGuid - GUID of the repo
 * @param grandGuid - GUID of the grand repo
 * @param allRepos - Array of all repos with vault content
 * @returns The vault content to use for the operation
 */
export function getGrandVaultForOperation(
  repoGuid: string,
  grandGuid: string | null | undefined,
  allRepos: RepoWithRelations[]
): string | null | undefined {
  // If has a grand, use the grand's vault
  if (grandGuid && grandGuid !== repoGuid) {
    const grandRepo = allRepos.find((r) => r.repoGuid === grandGuid);
    return grandRepo?.vaultContent;
  }

  // Otherwise use the repo's own vault
  const repo = allRepos.find((r) => r.repoGuid === repoGuid);
  return repo?.vaultContent;
}

/**
 * Repository orchestration service
 * High-level functions that prepare complete operation contexts
 * These functions return everything the UI/CLI needs to execute operations
 */

import {
  type RepositoryWithRelations,
  isFork
} from '../repository'
import { canDeleteFork, findForkParent } from './fork-operations'
import { canDeleteGrandRepository, type ChildClone } from './grand-deletion'
import { canPromoteToGrand, findSiblingClones, type SiblingClone } from './promotion'
import { canBackupToStorage } from './backup-validation'

/**
 * Base operation context
 */
export interface OperationContext {
  status: 'ready' | 'error' | 'blocked' | 'warning'
  errorCode?: string
}

/**
 * Context for fork deletion operation
 */
export interface ForkDeletionContext extends OperationContext {
  repositoryGuid?: string
  grandGuid?: string
  parentName?: string
  repoLoopbackIp?: string
  repoTag?: string | null
}

/**
 * Context for grand repository deletion operation
 */
export interface GrandDeletionContext extends OperationContext {
  repositoryGuid?: string
  childClones: ChildClone[]
  repoLoopbackIp?: string
  repoTag?: string | null
}

/**
 * Context for promotion operation
 */
export interface PromotionContext extends OperationContext {
  repositoryGuid?: string
  currentGrandName: string
  siblingClones: SiblingClone[]
}

/**
 * Context for backup operation
 */
export interface BackupContext extends OperationContext {
  repositoryGuid?: string
  grandGuid?: string
  canBackupToStorage: boolean
  canBackupToMachine: boolean
  storageBlockReason?: string
  repoLoopbackIp?: string
  repoNetworkMode?: string
  repoTag?: string | null
}

/**
 * Context for fork (clone) operation
 */
export interface ForkCreationContext extends OperationContext {
  repositoryGuid?: string
  grandGuid?: string
  repoLoopbackIp?: string
  repoNetworkMode?: string
  repoTag?: string | null
  mounted?: boolean
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
  const repoData = allRepositories.find(r =>
    r.repositoryName === repositoryName &&
    r.repoTag === (repositoryTag || 'latest')
  )

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: []
    } as ForkDeletionContext
  }

  // Validate it's a fork
  const validation = canDeleteFork(repoData)
  if (!validation.canDelete) {
    return {
      status: 'error',
      errorCode: 'NOT_A_FORK',
      childClones: []
    } as ForkDeletionContext
  }

  // Get parent info
  const parent = findForkParent(repoData, allRepositories)

  return {
    status: 'ready',
    repositoryGuid: repoData.repositoryGuid,
    grandGuid: repoData.grandGuid || undefined,
    parentName: parent?.repositoryName,
    repoLoopbackIp: (repoData as any).repoLoopbackIp,
    repoTag: repoData.repoTag
  }
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
  const repoData = allRepositories.find(r =>
    r.repositoryName === repositoryName &&
    r.repoTag === (repositoryTag || 'latest')
  )

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      childClones: []
    }
  }

  // Validate it's a grand repository
  if (isFork(repoData)) {
    return {
      status: 'error',
      errorCode: 'NOT_A_GRAND',
      childClones: []
    }
  }

  // Check for child clones
  const validation = canDeleteGrandRepository(repoData, allRepositories)

  if (!validation.canDelete) {
    return {
      status: 'blocked',
      errorCode: 'HAS_CHILD_CLONES',
      repositoryGuid: repoData.repositoryGuid,
      childClones: validation.childClones,
      repoLoopbackIp: (repoData as any).repoLoopbackIp,
      repoTag: repoData.repoTag
    }
  }

  return {
    status: 'ready',
    repositoryGuid: repoData.repositoryGuid,
    childClones: [],
    repoLoopbackIp: (repoData as any).repoLoopbackIp,
    repoTag: repoData.repoTag
  }
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
  const repoData = allRepositories.find(r =>
    r.repositoryName === repositoryName &&
    r.repoTag === (repositoryTag || 'latest')
  )

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      currentGrandName: '',
      siblingClones: []
    }
  }

  // Validate it can be promoted
  const validation = canPromoteToGrand(repoData)
  if (!validation.canPromote) {
    return {
      status: 'error',
      errorCode: 'ALREADY_GRAND',
      currentGrandName: '',
      siblingClones: []
    }
  }

  // Get affected siblings
  const { siblingClones, currentGrandName } = findSiblingClones(repoData, allRepositories)

  return {
    status: 'ready',
    repositoryGuid: repoData.repositoryGuid,
    currentGrandName,
    siblingClones
  }
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
  const repoData = allRepositories.find(r =>
    r.repositoryName === repositoryName &&
    r.repoTag === (repositoryTag || 'latest')
  )

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND',
      canBackupToStorage: false,
      canBackupToMachine: false
    }
  }

  // Check backup capabilities
  const storageValidation = canBackupToStorage(repoData)

  return {
    status: 'ready',
    repositoryGuid: repoData.repositoryGuid,
    grandGuid: repoData.grandGuid || repoData.repositoryGuid,
    canBackupToStorage: storageValidation.canBackup,
    canBackupToMachine: true, // Always allowed
    storageBlockReason: storageValidation.reason,
    repoLoopbackIp: (repoData as any).repoLoopbackIp,
    repoNetworkMode: (repoData as any).repoNetworkMode,
    repoTag: repoData.repoTag
  }
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
  const repoData = allRepositories.find(r =>
    r.repositoryName === repositoryName &&
    r.repoTag === (repositoryTag || 'latest')
  )

  if (!repoData) {
    return {
      status: 'error',
      errorCode: 'NOT_FOUND'
    }
  }

  // Get the grand GUID for the new fork
  // If forking a fork, use the same grand
  // If forking a credential, the credential becomes the grand
  const grandGuid = repoData.grandGuid || repoData.repositoryGuid

  return {
    status: 'ready',
    repositoryGuid: repoData.repositoryGuid,
    grandGuid,
    repoLoopbackIp: (repoData as any).repoLoopbackIp,
    repoNetworkMode: (repoData as any).repoNetworkMode,
    repoTag: repoData.repoTag,
    mounted: (repoData as any).mounted
  }
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
  grandGuid: string | undefined,
  allRepositories: any[]
): string | undefined {
  // If has a grand, use the grand's vault
  if (grandGuid && grandGuid !== repositoryGuid) {
    const grandRepo = allRepositories.find(r => r.repositoryGuid === grandGuid)
    return grandRepo?.vaultContent
  }

  // Otherwise use the repository's own vault
  const repo = allRepositories.find(r => r.repositoryGuid === repositoryGuid)
  return repo?.vaultContent
}

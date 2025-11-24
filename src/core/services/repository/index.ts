/**
 * Repository services barrel export
 * Re-exports all repository validation and operation services
 */

// Re-export main repository service
export {
  type RepositoryWithRelations,
  type AffectedMachine,
  type AffectedResourcesResult,
  type GroupedRepository,
  type DeletionValidationResult,
  isCredential,
  isFork,
  findForksOfCredential,
  findCredential,
  getAffectedResources,
  groupRepositoriesByName,
  getCredentials,
  getForks,
  canDeleteRepository,
  validateRepositoryDeletion,
  getRepositoryDisplayName
} from '../repository'

// Export promotion validation
export {
  type PromotionValidationResult,
  type SiblingClone,
  type SiblingClonesResult,
  canPromoteToGrand,
  findSiblingClones,
  getPromotionContext
} from './promotion'

// Export grand deletion validation
export {
  type ChildClone,
  type GrandDeletionValidationResult,
  canDeleteGrandRepository,
  findChildClones,
  isOrphanGrand
} from './grand-deletion'

// Export fork operations
export {
  type ForkDeletionValidationResult,
  type ForkParent,
  canDeleteFork,
  findForkParent,
  getForkRelationship,
  canForkRepository,
  getGrandGuidForFork
} from './fork-operations'

// Export backup validation
export {
  type BackupValidationResult,
  canBackupToStorage,
  canBackupToMachine,
  getBackupOptions,
  validateBackupDestination
} from './backup-validation'

// Export orchestration functions
export {
  type OperationContext,
  type ForkDeletionContext,
  type GrandDeletionContext,
  type PromotionContext,
  type BackupContext,
  type ForkCreationContext,
  prepareForkDeletion,
  prepareGrandDeletion,
  preparePromotion,
  prepareBackup,
  prepareForkCreation,
  getGrandVaultForOperation
} from './orchestration'

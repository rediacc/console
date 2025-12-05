/**
 * Repo services barrel export
 * Re-exports all repo validation and operation services
 */

// Re-export main repo service
export {
  type RepoWithRelations,
  type AffectedMachine,
  type AffectedResourcesResult,
  type GroupedRepo,
  type DeletionValidationResult,
  isCredential,
  isFork,
  findForksOfCredential,
  findCredential,
  getAffectedResources,
  groupReposByName,
  getCredentials,
  getForks,
  canDeleteRepo,
  validateRepoDeletion,
  getRepoDisplayName,
} from '../repo';

// Export promotion validation
export {
  type PromotionValidationResult,
  type SiblingClone,
  type SiblingClonesResult,
  canPromoteToGrand,
  findSiblingClones,
  getPromotionContext,
} from './promotion';

// Export grand deletion validation
export {
  type ChildClone,
  type GrandDeletionValidationResult,
  canDeleteGrandRepo,
  findChildClones,
  isOrphanGrand,
} from './grand-deletion';

// Export fork operations
export {
  type ForkDeletionValidationResult,
  type ForkParent,
  canDeleteFork,
  findForkParent,
  getForkRelationship,
  canForkRepo,
  getGrandGuidForFork,
} from './fork-operations';

// Export backup validation
export {
  type BackupValidationResult,
  canBackupToStorage,
  canBackupToMachine,
  getBackupOptions,
  validateBackupDestination,
} from './backup-validation';

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
  getGrandVaultForOperation,
} from './orchestration';

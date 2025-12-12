/**
 * Grand repository deletion validation service
 * Handles validation for deleting grand (credential) repositories
 */

import { isCredential, isFork, type RepositoryWithRelations } from './core';

/**
 * Child clone information
 */
export interface ChildClone {
  repositoryGuid: string;
  repositoryName: string;
  repositoryTag?: string | null;
}

/**
 * Result of grand deletion validation
 */
export interface GrandDeletionValidationResult {
  canDelete: boolean;
  reason?: string;
  childClones: ChildClone[];
}

/**
 * Check if a grand repository can be deleted
 * Grand repositories with child clones cannot be deleted
 * @param repository - Repository to check for deletion eligibility
 * @param allRepositories - Array of all repositories
 * @returns Validation result with canDelete flag, reason if blocked, and child clones
 */
export function canDeleteGrandRepo(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): GrandDeletionValidationResult {
  // Must be a grand repository (credential)
  if (isFork(repository)) {
    return {
      canDelete: false,
      reason: 'Repository is a fork, not a grand repository',
      childClones: [],
    };
  }

  // Find child clones
  const childClones = findChildClones(repository, allRepositories);

  // Block deletion if has child clones
  if (childClones.length > 0) {
    return {
      canDelete: false,
      reason: `Grand repository has ${childClones.length} active clone${childClones.length > 1 ? 's' : ''}`,
      childClones,
    };
  }

  return {
    canDelete: true,
    childClones: [],
  };
}

/**
 * Find all child clones of a grand repository
 * Child clones are repositories that have this repository as their grandGuid
 * @param grandRepo - The grand repository
 * @param allRepositories - Array of all repositories
 * @returns Array of child clones
 */
export function findChildClones(
  grandRepo: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): ChildClone[] {
  const grandGuid = grandRepo.repositoryGuid;

  return allRepositories
    .filter(
      (r) => r.grandGuid === grandGuid && r.repositoryGuid !== grandGuid // Exclude the grand repository itself
    )
    .map((r) => ({
      repositoryGuid: r.repositoryGuid,
      repositoryName: r.repositoryName,
      repositoryTag: r.repositoryTag,
    }));
}

/**
 * Check if a repository is a grand repository with no children
 * @param repository - Repository to check
 * @param allRepositories - Array of all repositories
 * @returns True if the repository is a grand with no children
 */
export function isOrphanGrand(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): boolean {
  if (!isCredential(repository)) {
    return false;
  }

  const childClones = findChildClones(repository, allRepositories);
  return childClones.length === 0;
}

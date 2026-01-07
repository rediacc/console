/**
 * Fork operations validation service
 * Handles validation for fork-specific operations like deletion
 */

import { isFork, type RepositoryWithRelations } from './core';

/**
 * Result of fork deletion validation
 */
export interface ForkDeletionValidationResult {
  canDelete: boolean;
  reason?: string;
}

/**
 * Fork parent information
 */
export interface ForkParent {
  repositoryGuid: string | null;
  repositoryName: string | null;
  repositoryTag?: string | null;
}

/**
 * Check if a fork can be deleted
 * Validates that the repository is actually a fork before deletion
 * @param repository - Repository to check for deletion eligibility
 * @returns Validation result with canDelete flag and reason if blocked
 */
export function canDeleteFork(repository: RepositoryWithRelations): ForkDeletionValidationResult {
  // Must be a fork (has grandGuid different from self)
  if (!isFork(repository)) {
    return {
      canDelete: false,
      reason: 'Repository is not a fork (cannot delete grand repository as fork)',
    };
  }

  return {
    canDelete: true,
  };
}

/**
 * Find the grand/parent repository of a fork
 * @param fork - The fork repository
 * @param allRepositories - Array of all repositories
 * @returns The parent repository or null if not found
 */
export function findForkParent(
  fork: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): ForkParent | null {
  if (!isFork(fork)) {
    return null;
  }

  const grandGuid = fork.grandGuid;

  if (!grandGuid) {
    return null;
  }

  const parent = allRepositories.find((r) => r.repositoryGuid === grandGuid);

  if (!parent) {
    return null;
  }

  return {
    repositoryGuid: parent.repositoryGuid,
    repositoryName: parent.repositoryName,
    repositoryTag: parent.repositoryTag,
  };
}

/**
 * Get the fork's relationship information
 * @param repository - Repository to get relationship info for
 * @param allRepositories - Array of all repositories
 * @returns Relationship info including parent and sibling count
 */
export function getForkRelationship(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): {
  isFork: boolean;
  parent: ForkParent | null;
  siblingCount: number;
} {
  if (!isFork(repository)) {
    return {
      isFork: false,
      parent: null,
      siblingCount: 0,
    };
  }

  const parent = findForkParent(repository, allRepositories);

  // Count siblings (other forks with same grandGuid, excluding self)
  const siblingCount = allRepositories.filter(
    (r) =>
      r.grandGuid === repository.grandGuid &&
      r.repositoryGuid !== repository.repositoryGuid &&
      r.grandGuid !== r.repositoryGuid // Exclude the grand itself
  ).length;

  return {
    isFork: true,
    parent,
    siblingCount,
  };
}

/**
 * Check if a repository can be forked
 * Any repository can be forked (creates a new fork pointing to the same grand)
 * @param _repo - Repository to check (unused, all repositories can be forked)
 * @returns True (forking is always allowed)
 */
export function canForkRepo(_repo: RepositoryWithRelations): boolean {
  // Any repository can be forked
  // If it's a fork, the new fork will share the same grandGuid
  // If it's a credential, the new fork will point to it as grand
  return true;
}

/**
 * Get the grandGuid to use when forking a repository
 * @param repository - Repository being forked
 * @returns The grandGuid for the new fork, or null if repository has no GUID
 */
export function getGrandGuidForFork(repository: RepositoryWithRelations): string | null {
  // If forking a fork, use the same grand
  // If forking a credential, the credential becomes the grand
  return repository.grandGuid ?? repository.repositoryGuid;
}

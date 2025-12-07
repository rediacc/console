/**
 * Fork operations validation service
 * Handles validation for fork-specific operations like deletion
 */

import { type RepoWithRelations, isFork } from './core';

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
  repoGuid: string;
  repoName: string;
  repoTag?: string | null;
}

/**
 * Check if a fork can be deleted
 * Validates that the repo is actually a fork before deletion
 * @param repo - Repo to check for deletion eligibility
 * @returns Validation result with canDelete flag and reason if blocked
 */
export function canDeleteFork(repo: RepoWithRelations): ForkDeletionValidationResult {
  // Must be a fork (has grandGuid different from self)
  if (!isFork(repo)) {
    return {
      canDelete: false,
      reason: 'Repo is not a fork (cannot delete grand repo as fork)',
    };
  }

  return {
    canDelete: true,
  };
}

/**
 * Find the grand/parent repo of a fork
 * @param fork - The fork repo
 * @param allRepos - Array of all repos
 * @returns The parent repo or null if not found
 */
export function findForkParent(
  fork: RepoWithRelations,
  allRepos: RepoWithRelations[]
): ForkParent | null {
  if (!isFork(fork)) {
    return null;
  }

  const grandGuid = fork.grandGuid;

  if (!grandGuid) {
    return null;
  }

  const parent = allRepos.find((r) => r.repoGuid === grandGuid);

  if (!parent) {
    return null;
  }

  return {
    repoGuid: parent.repoGuid,
    repoName: parent.repoName,
    repoTag: parent.repoTag,
  };
}

/**
 * Get the fork's relationship information
 * @param repo - Repo to get relationship info for
 * @param allRepos - Array of all repos
 * @returns Relationship info including parent and sibling count
 */
export function getForkRelationship(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[]
): {
  isFork: boolean;
  parent: ForkParent | null;
  siblingCount: number;
} {
  if (!isFork(repo)) {
    return {
      isFork: false,
      parent: null,
      siblingCount: 0,
    };
  }

  const parent = findForkParent(repo, allRepos);

  // Count siblings (other forks with same grandGuid, excluding self)
  const siblingCount = allRepos.filter(
    (r) =>
      r.grandGuid === repo.grandGuid && r.repoGuid !== repo.repoGuid && r.grandGuid !== r.repoGuid // Exclude the grand itself
  ).length;

  return {
    isFork: true,
    parent,
    siblingCount,
  };
}

/**
 * Check if a repo can be forked
 * Any repo can be forked (creates a new fork pointing to the same grand)
 * @param _repo - Repo to check (unused, all repos can be forked)
 * @returns True (forking is always allowed)
 */
export function canForkRepo(_repo: RepoWithRelations): boolean {
  // Any repo can be forked
  // If it's a fork, the new fork will share the same grandGuid
  // If it's a credential, the new fork will point to it as grand
  return true;
}

/**
 * Get the grandGuid to use when forking a repo
 * @param repo - Repo being forked
 * @returns The grandGuid for the new fork
 */
export function getGrandGuidForFork(repo: RepoWithRelations): string {
  // If forking a fork, use the same grand
  // If forking a credential, the credential becomes the grand
  return repo.grandGuid || repo.repoGuid;
}

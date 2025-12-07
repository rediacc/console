/**
 * Grand repo deletion validation service
 * Handles validation for deleting grand (credential) repos
 */

import { type RepoWithRelations, isCredential, isFork } from './core';

/**
 * Child clone information
 */
export interface ChildClone {
  repoGuid: string;
  repoName: string;
  repoTag?: string | null;
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
 * Check if a grand repo can be deleted
 * Grand repos with child clones cannot be deleted
 * @param repo - Repo to check for deletion eligibility
 * @param allRepos - Array of all repos
 * @returns Validation result with canDelete flag, reason if blocked, and child clones
 */
export function canDeleteGrandRepo(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[]
): GrandDeletionValidationResult {
  // Must be a grand repo (credential)
  if (isFork(repo)) {
    return {
      canDelete: false,
      reason: 'Repo is a fork, not a grand repo',
      childClones: [],
    };
  }

  // Find child clones
  const childClones = findChildClones(repo, allRepos);

  // Block deletion if has child clones
  if (childClones.length > 0) {
    return {
      canDelete: false,
      reason: `Grand repo has ${childClones.length} active clone${childClones.length > 1 ? 's' : ''}`,
      childClones,
    };
  }

  return {
    canDelete: true,
    childClones: [],
  };
}

/**
 * Find all child clones of a grand repo
 * Child clones are repos that have this repo as their grandGuid
 * @param grandRepo - The grand repo
 * @param allRepos - Array of all repos
 * @returns Array of child clones
 */
export function findChildClones(
  grandRepo: RepoWithRelations,
  allRepos: RepoWithRelations[]
): ChildClone[] {
  const grandGuid = grandRepo.repoGuid;

  return allRepos
    .filter(
      (r) => r.grandGuid === grandGuid && r.repoGuid !== grandGuid // Exclude the grand repo itself
    )
    .map((r) => ({
      repoGuid: r.repoGuid,
      repoName: r.repoName,
      repoTag: r.repoTag,
    }));
}

/**
 * Check if a repo is a grand repo with no children
 * @param repo - Repo to check
 * @param allRepos - Array of all repos
 * @returns True if the repo is a grand with no children
 */
export function isOrphanGrand(repo: RepoWithRelations, allRepos: RepoWithRelations[]): boolean {
  if (!isCredential(repo)) {
    return false;
  }

  const childClones = findChildClones(repo, allRepos);
  return childClones.length === 0;
}

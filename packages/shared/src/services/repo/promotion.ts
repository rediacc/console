/**
 * Repo promotion validation service
 * Handles validation for promoting forks to grand repos
 */

import { type RepoWithRelations, isFork } from './core';

/**
 * Result of promotion validation
 */
export interface PromotionValidationResult {
  canPromote: boolean;
  reason?: string;
}

/**
 * Sibling clone information
 */
export interface SiblingClone {
  repoGuid: string;
  repoName: string;
  repoTag?: string | null;
}

/**
 * Result of finding sibling clones
 */
export interface SiblingClonesResult {
  siblingClones: SiblingClone[];
  currentGrandName: string;
}

/**
 * Check if a fork can be promoted to grand repo
 * A fork can be promoted if it has a grandGuid different from its own repoGuid
 * @param repo - Repo to check for promotion eligibility
 * @returns Validation result with canPromote flag and reason if blocked
 */
export function canPromoteToGrand(repo: RepoWithRelations): PromotionValidationResult {
  // Must be a fork (has grandGuid different from self)
  if (!isFork(repo)) {
    return {
      canPromote: false,
      reason: 'Repo is already a grand repo (credential)',
    };
  }

  // Fork with valid grandGuid can be promoted
  return {
    canPromote: true,
  };
}

/**
 * Find sibling clones that will be affected by promoting a fork to grand
 * Siblings are other repos that share the same grandGuid
 * @param repo - The fork being promoted
 * @param allRepos - Array of all repos
 * @returns Sibling clones and current grand name
 */
export function findSiblingClones(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[]
): SiblingClonesResult {
  const grandGuid = repo.grandGuid;

  if (!grandGuid) {
    return {
      siblingClones: [],
      currentGrandName: '',
    };
  }

  // Find the current grand repo
  const currentGrand = allRepos.find((r) => r.repoGuid === grandGuid);
  const currentGrandName = currentGrand?.repoName || 'original';

  // Find sibling clones (exclude the repo being promoted and the original)
  const siblingClones = allRepos
    .filter(
      (r) => r.grandGuid === grandGuid && r.repoGuid !== repo.repoGuid && r.grandGuid !== r.repoGuid // Exclude original repos
    )
    .map((r) => ({
      repoGuid: r.repoGuid,
      repoName: r.repoName,
      repoTag: r.repoTag,
    }));

  return {
    siblingClones,
    currentGrandName,
  };
}

/**
 * Get full promotion context including validation and affected siblings
 * @param repo - Repo to promote
 * @param allRepos - Array of all repos
 * @returns Complete promotion context
 */
export function getPromotionContext(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[]
): {
  canPromote: boolean;
  reason?: string;
  siblingClones: SiblingClone[];
  currentGrandName: string;
} {
  const validation = canPromoteToGrand(repo);

  if (!validation.canPromote) {
    return {
      ...validation,
      siblingClones: [],
      currentGrandName: '',
    };
  }

  const siblings = findSiblingClones(repo, allRepos);

  return {
    canPromote: true,
    ...siblings,
  };
}

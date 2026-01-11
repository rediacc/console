/**
 * Repository promotion validation service
 * Handles validation for promoting forks to grand repositories
 */

import { isFork, type RepositoryWithRelations } from './core';
import { DEFAULTS } from '../../config';

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
  repositoryGuid: string | null;
  repositoryName: string | null;
  repositoryTag?: string | null;
}

/**
 * Result of finding sibling clones
 */
export interface SiblingClonesResult {
  siblingClones: SiblingClone[];
  currentGrandName: string | null;
}

/**
 * Check if a fork can be promoted to grand repository
 * A fork can be promoted if it has a grandGuid different from its own repositoryGuid
 * @param repository - Repository to check for promotion eligibility
 * @returns Validation result with canPromote flag and reason if blocked
 */
export function canPromoteToGrand(repository: RepositoryWithRelations): PromotionValidationResult {
  // Must be a fork (has grandGuid different from self)
  if (!isFork(repository)) {
    return {
      canPromote: false,
      reason: 'Repository is already a grand repository (credential)',
    };
  }

  // Fork with valid grandGuid can be promoted
  return {
    canPromote: true,
  };
}

/**
 * Find sibling clones that will be affected by promoting a fork to grand
 * Siblings are other repositories that share the same grandGuid
 * @param repository - The fork being promoted
 * @param allRepositories - Array of all repositories
 * @returns Sibling clones and current grand name
 */
export function findSiblingClones(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): SiblingClonesResult {
  const grandGuid = repository.grandGuid;

  if (!grandGuid) {
    return {
      siblingClones: [],
      currentGrandName: null,
    };
  }

  // Find the current grand repository
  const currentGrand = allRepositories.find((r) => r.repositoryGuid === grandGuid);
  const currentGrandName = currentGrand?.repositoryName ?? DEFAULTS.STATUS.ORIGINAL;

  // Find sibling clones (exclude the repository being promoted and the original)
  const siblingClones = allRepositories
    .filter(
      (r) =>
        r.grandGuid === grandGuid &&
        r.repositoryGuid !== repository.repositoryGuid &&
        r.grandGuid !== r.repositoryGuid // Exclude original repositories
    )
    .map((r) => ({
      repositoryGuid: r.repositoryGuid,
      repositoryName: r.repositoryName,
      repositoryTag: r.repositoryTag,
    }));

  return {
    siblingClones,
    currentGrandName,
  };
}

/**
 * Get full promotion context including validation and affected siblings
 * @param repository - Repository to promote
 * @param allRepositories - Array of all repositories
 * @returns Complete promotion context
 */
export function getPromotionContext(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): {
  canPromote: boolean;
  reason?: string;
  siblingClones: SiblingClone[];
  currentGrandName: string | null;
} {
  const validation = canPromoteToGrand(repository);

  if (!validation.canPromote) {
    return {
      ...validation,
      siblingClones: [],
      currentGrandName: '',
    };
  }

  const siblings = findSiblingClones(repository, allRepositories);

  return {
    canPromote: true,
    ...siblings,
  };
}

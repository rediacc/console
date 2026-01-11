/**
 * Repository relationship service
 * Handles grand/fork detection, affected resources, and repository grouping
 */

import { DEFAULTS } from '../../config';
import { type MachineWithVaultStatus, parseVaultStatus } from '../machine';

/**
 * Repository information for relationship analysis
 * Uses type to allow any object with the required properties
 * Note: Fields are nullable to match generated API types
 */
export type RepositoryWithRelations = {
  repositoryGuid: string | null;
  repositoryName: string | null;
  grandGuid?: string | null;
  repositoryTag?: string | null;
  teamName?: string | null;
  repositoryNetworkId?: number | null;
  repositoryNetworkMode?: string | null;
  mounted?: boolean | null;
  vaultContent?: string | null;
};

/**
 * Affected machine information
 * Note: machineName is nullable to match generated API types
 */
export interface AffectedMachine {
  machineName: string | null;
  repositoryNames: string[];
}

/**
 * Result of getAffectedResources
 */
export interface AffectedResourcesResult {
  isCredential: boolean;
  forks: RepositoryWithRelations[];
  affectedMachines: AffectedMachine[];
}

/**
 * Grouped repository result
 */
export interface GroupedRepository {
  name: string;
  credential: RepositoryWithRelations | null;
  forks: RepositoryWithRelations[];
  allRepositories: RepositoryWithRelations[];
}

/**
 * Check if a repository is a credential (grand repository)
 * A credential is a repository where grandGuid is null/undefined or equals its own repositoryGuid
 * @param repository - Repository to check
 * @returns True if the repository is a credential
 */
export function isCredential(repository: RepositoryWithRelations): boolean {
  if (!repository.repositoryGuid) return false;
  return !repository.grandGuid || repository.grandGuid === repository.repositoryGuid;
}

/**
 * Check if a repository is a fork
 * A fork has a grandGuid that differs from its repositoryGuid
 * @param repository - Repository to check
 * @returns True if the repository is a fork
 */
export function isFork(repository: RepositoryWithRelations): boolean {
  if (!repository.repositoryGuid) return false;
  return !!repository.grandGuid && repository.grandGuid !== repository.repositoryGuid;
}

/**
 * Find all forks of a credential
 * @param credentialGuid - The credential's repository GUID
 * @param repositories - Array of all repositories
 * @returns Array of repositories that are forks of this credential
 */
export function findForksOfCredential(
  credentialGuid: string,
  repositories: RepositoryWithRelations[]
): RepositoryWithRelations[] {
  return repositories.filter(
    (repository) =>
      repository.repositoryGuid &&
      repository.grandGuid === credentialGuid &&
      repository.repositoryGuid !== credentialGuid
  );
}

/**
 * Find the credential (grand) repository for a given repository
 * @param repository - Repository to find the credential for
 * @param repositories - Array of all repositories
 * @returns The credential repository or null if not found
 */
export function findCredential(
  repository: RepositoryWithRelations,
  repositories: RepositoryWithRelations[]
): RepositoryWithRelations | null {
  if (isCredential(repository)) {
    return repository;
  }

  return (
    repositories.find((repository) => repository.repositoryGuid === repository.grandGuid) ?? null
  );
}

/**
 * Find affected repositories based on credential relationship
 */
function findAffectedRepositories(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  repoIsCredential: boolean,
  credentialGuid: string | null | undefined
): RepositoryWithRelations[] {
  if (!repoIsCredential) {
    return [repository]; // For forks, only the fork itself is affected
  }
  return allRepositories.filter(
    (repo) => repo.grandGuid === credentialGuid || repo.repositoryGuid === credentialGuid
  );
}

/**
 * Get display name for a deployed repository
 */
function getDeployedRepoDisplayName(
  deployed: { name: string; repositoryGuid?: string },
  affectedRepos: RepositoryWithRelations[]
): string {
  const repository = affectedRepos.find(
    (r) => r.repositoryGuid === deployed.name || r.repositoryGuid === deployed.repositoryGuid
  );
  if (!repository) {
    return deployed.name;
  }
  const tag = repository.repositoryTag ? `:${repository.repositoryTag}` : '';
  return `${repository.repositoryName}${tag}`;
}

/**
 * Find affected machine from parsed vault status
 */
function findAffectedMachine(
  machine: MachineWithVaultStatus,
  affectedRepoGuids: (string | null)[],
  affectedRepos: RepositoryWithRelations[]
): AffectedMachine | null {
  const parsed = parseVaultStatus(machine.vaultStatus);

  if (parsed.status !== 'completed' || parsed.repositories.length === 0) {
    return null;
  }

  const deployedAffected = parsed.repositories.filter(
    (deployedRepo) =>
      affectedRepoGuids.includes(deployedRepo.name) ||
      (deployedRepo.repositoryGuid && affectedRepoGuids.includes(deployedRepo.repositoryGuid))
  );

  if (deployedAffected.length === 0) {
    return null;
  }

  const repositoryNames = deployedAffected.map((deployed) =>
    getDeployedRepoDisplayName(deployed, affectedRepos)
  );

  return {
    machineName: machine.machineName,
    repositoryNames,
  };
}

/**
 * Get affected resources when deleting a repository
 * @param repository - Repository being deleted
 * @param allRepositories - Array of all repositories
 * @param machines - Array of machines with vault status
 * @returns Affected resources information
 */
export function getAffectedResources(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  machines: MachineWithVaultStatus[]
): AffectedResourcesResult {
  const repoIsCredential = isCredential(repository);
  const credentialGuid = repoIsCredential ? repository.repositoryGuid : repository.grandGuid;

  const affectedRepos = findAffectedRepositories(
    repository,
    allRepositories,
    repoIsCredential,
    credentialGuid
  );
  const affectedRepoGuids = affectedRepos.map((repo) => repo.repositoryGuid);

  const affectedMachines = machines
    .map((machine) => findAffectedMachine(machine, affectedRepoGuids, affectedRepos))
    .filter((result): result is AffectedMachine => result !== null);

  const forks =
    repoIsCredential && credentialGuid
      ? findForksOfCredential(credentialGuid, allRepositories)
      : [];

  return {
    isCredential: repoIsCredential,
    forks,
    affectedMachines,
  };
}

/**
 * Group repositories by their name (combining credentials and forks)
 * @param repositories - Array of all repositories
 * @returns Map of repository name to grouped repository
 */
export function groupRepositoriesByName(
  repositories: RepositoryWithRelations[]
): Map<string, GroupedRepository> {
  const grouped = new Map<string, GroupedRepository>();

  for (const repository of repositories) {
    const name = repository.repositoryName ?? DEFAULTS.STATUS.UNKNOWN;

    if (!grouped.has(name)) {
      grouped.set(name, {
        name,
        credential: null,
        forks: [],
        allRepositories: [],
      });
    }

    const group = grouped.get(name)!;
    group.allRepositories.push(repository);

    if (isCredential(repository)) {
      group.credential = repository;
    } else {
      group.forks.push(repository);
    }
  }

  return grouped;
}

/**
 * Get all credentials (grand repositories) from a list
 * @param repositories - Array of all repositories
 * @returns Array of credential repositories
 */
export function getCredentials(repositories: RepositoryWithRelations[]): RepositoryWithRelations[] {
  return repositories.filter(isCredential);
}

/**
 * Get all forks from a list
 * @param repositories - Array of all repositories
 * @returns Array of fork repositories
 */
export function getForks(repositories: RepositoryWithRelations[]): RepositoryWithRelations[] {
  return repositories.filter(isFork);
}

/**
 * Check if a repository can be safely deleted
 * @param repository - Repository to check
 * @param allRepositories - Array of all repositories
 * @param machines - Array of machines with vault status
 * @returns Object with canDelete flag and reason if blocked
 */
export function canDeleteRepo(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  machines: MachineWithVaultStatus[]
): { canDelete: boolean; reason?: string; affectedMachines?: AffectedMachine[] } {
  const { isCredential: repoIsCredential, affectedMachines } = getAffectedResources(
    repository,
    allRepositories,
    machines
  );

  // Credentials with deployments cannot be deleted
  if (repoIsCredential && affectedMachines.length > 0) {
    return {
      canDelete: false,
      reason: 'Credential has active deployments',
      affectedMachines,
    };
  }

  // Forks with deployments can be deleted (with warning)
  return {
    canDelete: true,
    affectedMachines: affectedMachines.length > 0 ? affectedMachines : undefined,
  };
}

/**
 * Comprehensive deletion validation result
 */
export interface DeletionValidationResult {
  /** Whether deletion is allowed (may require confirmation for warnings) */
  canDelete: boolean;
  /** Whether deletion should be blocked completely (credential with active deployments) */
  shouldBlock: boolean;
  /** Whether deletion should show a warning (fork with deployments) */
  shouldWarn: boolean;
  /** Reason for block or warning */
  reason?: string;
  /** Machines affected by the deletion */
  affectedMachines?: AffectedMachine[];
  /** Child clones that depend on this credential */
  childClones?: RepositoryWithRelations[];
}

/** Format count with plural suffix */
function pluralize(count: number, singular: string): string {
  return `${count} ${singular}${count > 1 ? 's' : ''}`;
}

/** Build block result for credential with deployments */
function buildCredentialWithDeploymentsBlock(
  affectedMachines: AffectedMachine[],
  forks: RepositoryWithRelations[]
): DeletionValidationResult {
  const deploymentText = pluralize(affectedMachines.length, 'deployment');
  const reason =
    forks.length > 0
      ? `Credential has ${deploymentText} with ${pluralize(forks.length, 'fork')}`
      : `Credential has ${pluralize(affectedMachines.length, 'active deployment')}`;

  return {
    canDelete: false,
    shouldBlock: true,
    shouldWarn: false,
    reason,
    affectedMachines,
    childClones: forks,
  };
}

/** Build block result for credential with forks */
function buildCredentialWithForksBlock(forks: RepositoryWithRelations[]): DeletionValidationResult {
  return {
    canDelete: false,
    shouldBlock: true,
    shouldWarn: false,
    reason: `Credential has ${pluralize(forks.length, 'fork')} that must be deleted first`,
    childClones: forks,
  };
}

/** Build warning result for fork with deployments */
function buildForkWithDeploymentsWarning(
  affectedMachines: AffectedMachine[]
): DeletionValidationResult {
  return {
    canDelete: true,
    shouldBlock: false,
    shouldWarn: true,
    reason: `Fork has ${pluralize(affectedMachines.length, 'deployment')} that will lose access`,
    affectedMachines,
  };
}

/** Build allow result */
function buildAllowResult(): DeletionValidationResult {
  return {
    canDelete: true,
    shouldBlock: false,
    shouldWarn: false,
  };
}

/**
 * Comprehensive repository deletion validation
 * Provides detailed information for UI to display appropriate dialogs
 * @param repository - Repository to validate for deletion
 * @param allRepositories - Array of all repositories
 * @param machines - Array of machines with vault status
 * @returns Detailed validation result with block/warn/allow status
 */
export function validateRepoDeletion(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  machines: MachineWithVaultStatus[]
): DeletionValidationResult {
  const repoIsCredential = isCredential(repository);
  const { affectedMachines, forks } = getAffectedResources(repository, allRepositories, machines);

  const hasDeployments = affectedMachines.length > 0;
  const hasForks = forks.length > 0;

  // Case 1: Credential with deployments - BLOCK
  if (repoIsCredential && hasDeployments) {
    return buildCredentialWithDeploymentsBlock(affectedMachines, forks);
  }

  // Case 2: Credential with forks but no deployments - BLOCK
  if (repoIsCredential && hasForks) {
    return buildCredentialWithForksBlock(forks);
  }

  // Case 3: Fork with deployments - WARN but allow
  if (!repoIsCredential && hasDeployments) {
    return buildForkWithDeploymentsWarning(affectedMachines);
  }

  // Case 4: No issues - ALLOW
  return buildAllowResult();
}

/**
 * Get the display name for a repository (including tag if present)
 * @param repository - Repository to get display name for
 * @returns Display name with optional tag
 */
export function getRepositoryDisplayName(repository: RepositoryWithRelations): string {
  const name = repository.repositoryName ?? DEFAULTS.STATUS.UNKNOWN;
  return repository.repositoryTag ? `${name}:${repository.repositoryTag}` : name;
}

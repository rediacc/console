/**
 * Repository relationship service
 * Handles grand/fork detection, affected resources, and repository grouping
 */

import { parseVaultStatus, type MachineWithVaultStatus } from './machine'

/**
 * Repository information for relationship analysis
 * Uses type to allow any object with the required properties
 */
export type RepositoryWithRelations = {
  repositoryGuid: string
  repositoryName: string
  grandGuid?: string | null
  repoTag?: string | null
  teamName?: string
}

/**
 * Affected machine information
 */
export interface AffectedMachine {
  machineName: string
  repoNames: string[]
}

/**
 * Result of getAffectedResources
 */
export interface AffectedResourcesResult {
  isCredential: boolean
  forks: RepositoryWithRelations[]
  affectedMachines: AffectedMachine[]
}

/**
 * Grouped repository result
 */
export interface GroupedRepository {
  name: string
  credential: RepositoryWithRelations | null
  forks: RepositoryWithRelations[]
  allRepositories: RepositoryWithRelations[]
}

/**
 * Check if a repository is a credential (grand repository)
 * A credential is a repository where grandGuid is null/undefined or equals its own repositoryGuid
 * @param repository - Repository to check
 * @returns True if the repository is a credential
 */
export function isCredential(repository: RepositoryWithRelations): boolean {
  return !repository.grandGuid || repository.grandGuid === repository.repositoryGuid
}

/**
 * Check if a repository is a fork
 * A fork has a grandGuid that differs from its repositoryGuid
 * @param repository - Repository to check
 * @returns True if the repository is a fork
 */
export function isFork(repository: RepositoryWithRelations): boolean {
  return !!repository.grandGuid && repository.grandGuid !== repository.repositoryGuid
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
    repo => repo.grandGuid === credentialGuid && repo.repositoryGuid !== credentialGuid
  )
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
    return repository
  }

  return repositories.find(
    repo => repo.repositoryGuid === repository.grandGuid
  ) || null
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
  const repoIsCredential = isCredential(repository)
  const credentialGuid = repoIsCredential ? repository.repositoryGuid : repository.grandGuid

  // Find all repositories that use this credential
  const affectedRepos = repoIsCredential
    ? allRepositories.filter(repo =>
        repo.grandGuid === credentialGuid || repo.repositoryGuid === credentialGuid
      )
    : [repository] // For forks, only the fork itself is affected

  const affectedRepoGuids = affectedRepos.map(repo => repo.repositoryGuid)

  // Find machines that have any of these repositories deployed
  const affectedMachines: AffectedMachine[] = []

  for (const machine of machines) {
    const parsed = parseVaultStatus(machine.vaultStatus)

    if (parsed.status === 'completed' && parsed.repositories.length > 0) {
      // Find deployed repos that match our affected GUIDs
      const deployedAffected = parsed.repositories.filter(deployedRepo =>
        affectedRepoGuids.includes(deployedRepo.name) ||
        (deployedRepo.repositoryGuid && affectedRepoGuids.includes(deployedRepo.repositoryGuid))
      )

      if (deployedAffected.length > 0) {
        // Map GUIDs back to repo names for display
        const repoNames = deployedAffected.map(deployed => {
          const repo = affectedRepos.find(r =>
            r.repositoryGuid === deployed.name ||
            r.repositoryGuid === deployed.repositoryGuid
          )
          return repo
            ? `${repo.repositoryName}${repo.repoTag ? `:${repo.repoTag}` : ''}`
            : deployed.name
        })

        affectedMachines.push({
          machineName: machine.machineName,
          repoNames
        })
      }
    }
  }

  // Get forks (repos that use this as their grand, excluding the credential itself)
  const forks = repoIsCredential && credentialGuid
    ? allRepositories.filter(repo =>
        repo.grandGuid === credentialGuid && repo.repositoryGuid !== credentialGuid
      )
    : []

  return {
    isCredential: repoIsCredential,
    forks,
    affectedMachines
  }
}

/**
 * Group repositories by their name (combining credentials and forks)
 * @param repositories - Array of all repositories
 * @returns Map of repository name to grouped repository
 */
export function groupRepositoriesByName(
  repositories: RepositoryWithRelations[]
): Map<string, GroupedRepository> {
  const grouped = new Map<string, GroupedRepository>()

  for (const repo of repositories) {
    const name = repo.repositoryName

    if (!grouped.has(name)) {
      grouped.set(name, {
        name,
        credential: null,
        forks: [],
        allRepositories: []
      })
    }

    const group = grouped.get(name)!
    group.allRepositories.push(repo)

    if (isCredential(repo)) {
      group.credential = repo
    } else {
      group.forks.push(repo)
    }
  }

  return grouped
}

/**
 * Get all credentials (grand repositories) from a list
 * @param repositories - Array of all repositories
 * @returns Array of credential repositories
 */
export function getCredentials(
  repositories: RepositoryWithRelations[]
): RepositoryWithRelations[] {
  return repositories.filter(isCredential)
}

/**
 * Get all forks from a list
 * @param repositories - Array of all repositories
 * @returns Array of fork repositories
 */
export function getForks(
  repositories: RepositoryWithRelations[]
): RepositoryWithRelations[] {
  return repositories.filter(isFork)
}

/**
 * Check if a repository can be safely deleted
 * @param repository - Repository to check
 * @param allRepositories - Array of all repositories
 * @param machines - Array of machines with vault status
 * @returns Object with canDelete flag and reason if blocked
 */
export function canDeleteRepository(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  machines: MachineWithVaultStatus[]
): { canDelete: boolean; reason?: string; affectedMachines?: AffectedMachine[] } {
  const { isCredential: repoIsCredential, affectedMachines } = getAffectedResources(
    repository,
    allRepositories,
    machines
  )

  // Credentials with deployments cannot be deleted
  if (repoIsCredential && affectedMachines.length > 0) {
    return {
      canDelete: false,
      reason: 'Credential has active deployments',
      affectedMachines
    }
  }

  // Forks with deployments can be deleted (with warning)
  return {
    canDelete: true,
    affectedMachines: affectedMachines.length > 0 ? affectedMachines : undefined
  }
}

/**
 * Comprehensive deletion validation result
 */
export interface DeletionValidationResult {
  /** Whether deletion is allowed (may require confirmation for warnings) */
  canDelete: boolean
  /** Whether deletion should be blocked completely (credential with active deployments) */
  shouldBlock: boolean
  /** Whether deletion should show a warning (fork with deployments) */
  shouldWarn: boolean
  /** Reason for block or warning */
  reason?: string
  /** Machines affected by the deletion */
  affectedMachines?: AffectedMachine[]
  /** Child clones that depend on this credential */
  childClones?: RepositoryWithRelations[]
}

/**
 * Comprehensive repository deletion validation
 * Provides detailed information for UI to display appropriate dialogs
 * @param repository - Repository to validate for deletion
 * @param allRepositories - Array of all repositories
 * @param machines - Array of machines with vault status
 * @returns Detailed validation result with block/warn/allow status
 */
export function validateRepositoryDeletion(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[],
  machines: MachineWithVaultStatus[]
): DeletionValidationResult {
  const repoIsCredential = isCredential(repository)
  const { affectedMachines, forks } = getAffectedResources(
    repository,
    allRepositories,
    machines
  )

  // Case 1: Credential with deployments - BLOCK
  if (repoIsCredential && affectedMachines.length > 0) {
    return {
      canDelete: false,
      shouldBlock: true,
      shouldWarn: false,
      reason: forks.length > 0
        ? `Credential has ${affectedMachines.length} deployment${affectedMachines.length > 1 ? 's' : ''} with ${forks.length} fork${forks.length > 1 ? 's' : ''}`
        : `Credential has ${affectedMachines.length} active deployment${affectedMachines.length > 1 ? 's' : ''}`,
      affectedMachines,
      childClones: forks
    }
  }

  // Case 2: Credential with forks but no deployments - BLOCK
  // (Can't delete credential if forks exist, they would become orphaned)
  if (repoIsCredential && forks.length > 0) {
    return {
      canDelete: false,
      shouldBlock: true,
      shouldWarn: false,
      reason: `Credential has ${forks.length} fork${forks.length > 1 ? 's' : ''} that must be deleted first`,
      childClones: forks
    }
  }

  // Case 3: Fork with deployments - WARN but allow
  if (!repoIsCredential && affectedMachines.length > 0) {
    return {
      canDelete: true,
      shouldBlock: false,
      shouldWarn: true,
      reason: `Fork has ${affectedMachines.length} deployment${affectedMachines.length > 1 ? 's' : ''} that will lose access`,
      affectedMachines
    }
  }

  // Case 4: Credential without deployments or forks, or fork without deployments - ALLOW
  return {
    canDelete: true,
    shouldBlock: false,
    shouldWarn: false
  }
}

/**
 * Get the display name for a repository (including tag if present)
 * @param repository - Repository to get display name for
 * @returns Display name with optional tag
 */
export function getRepositoryDisplayName(repository: RepositoryWithRelations): string {
  return repository.repoTag
    ? `${repository.repositoryName}:${repository.repoTag}`
    : repository.repositoryName
}

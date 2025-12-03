/**
 * Repo relationship service
 * Handles grand/fork detection, affected resources, and repo grouping
 */

import { parseVaultStatus, type MachineWithVaultStatus } from './machine'

/**
 * Repo information for relationship analysis
 * Uses type to allow any object with the required properties
 */
export type RepoWithRelations = {
  repoGuid: string
  repoName: string
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
  forks: RepoWithRelations[]
  affectedMachines: AffectedMachine[]
}

/**
 * Grouped repo result
 */
export interface GroupedRepo {
  name: string
  credential: RepoWithRelations | null
  forks: RepoWithRelations[]
  allRepos: RepoWithRelations[]
}

/**
 * Check if a repo is a credential (grand repo)
 * A credential is a repo where grandGuid is null/undefined or equals its own repoGuid
 * @param repo - Repo to check
 * @returns True if the repo is a credential
 */
export function isCredential(repo: RepoWithRelations): boolean {
  return !repo.grandGuid || repo.grandGuid === repo.repoGuid
}

/**
 * Check if a repo is a fork
 * A fork has a grandGuid that differs from its repoGuid
 * @param repo - Repo to check
 * @returns True if the repo is a fork
 */
export function isFork(repo: RepoWithRelations): boolean {
  return !!repo.grandGuid && repo.grandGuid !== repo.repoGuid
}

/**
 * Find all forks of a credential
 * @param credentialGuid - The credential's repo GUID
 * @param repos - Array of all repos
 * @returns Array of repos that are forks of this credential
 */
export function findForksOfCredential(
  credentialGuid: string,
  repos: RepoWithRelations[]
): RepoWithRelations[] {
  return repos.filter(
    repo => repo.grandGuid === credentialGuid && repo.repoGuid !== credentialGuid
  )
}

/**
 * Find the credential (grand) repo for a given repo
 * @param repo - Repo to find the credential for
 * @param repos - Array of all repos
 * @returns The credential repo or null if not found
 */
export function findCredential(
  repo: RepoWithRelations,
  repos: RepoWithRelations[]
): RepoWithRelations | null {
  if (isCredential(repo)) {
    return repo
  }

  return repos.find(
    repo => repo.repoGuid === repo.grandGuid
  ) || null
}

/**
 * Get affected resources when deleting a repo
 * @param repo - Repo being deleted
 * @param allRepos - Array of all repos
 * @param machines - Array of machines with vault status
 * @returns Affected resources information
 */
export function getAffectedResources(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[],
  machines: MachineWithVaultStatus[]
): AffectedResourcesResult {
  const repoIsCredential = isCredential(repo)
  const credentialGuid = repoIsCredential ? repo.repoGuid : repo.grandGuid

  // Find all repos that use this credential
  const affectedRepos = repoIsCredential
    ? allRepos.filter(repo =>
        repo.grandGuid === credentialGuid || repo.repoGuid === credentialGuid
      )
    : [repo] // For forks, only the fork itself is affected

  const affectedRepoGuids = affectedRepos.map(repo => repo.repoGuid)

  // Find machines that have any of these repos deployed
  const affectedMachines: AffectedMachine[] = []

  for (const machine of machines) {
    const parsed = parseVaultStatus(machine.vaultStatus)

    if (parsed.status === 'completed' && parsed.repos.length > 0) {
      // Find deployed repos that match our affected GUIDs
      const deployedAffected = parsed.repos.filter(deployedRepo =>
        affectedRepoGuids.includes(deployedRepo.name) ||
        (deployedRepo.repoGuid && affectedRepoGuids.includes(deployedRepo.repoGuid))
      )

      if (deployedAffected.length > 0) {
        // Map GUIDs back to repo names for display
        const repoNames = deployedAffected.map(deployed => {
          const repo = affectedRepos.find(r =>
            r.repoGuid === deployed.name ||
            r.repoGuid === deployed.repoGuid
          )
          return repo
            ? `${repo.repoName}${repo.repoTag ? `:${repo.repoTag}` : ''}`
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
    ? allRepos.filter(repo =>
        repo.grandGuid === credentialGuid && repo.repoGuid !== credentialGuid
      )
    : []

  return {
    isCredential: repoIsCredential,
    forks,
    affectedMachines
  }
}

/**
 * Group repos by their name (combining credentials and forks)
 * @param repos - Array of all repos
 * @returns Map of repo name to grouped repo
 */
export function groupReposByName(
  repos: RepoWithRelations[]
): Map<string, GroupedRepo> {
  const grouped = new Map<string, GroupedRepo>()

  for (const repo of repos) {
    const name = repo.repoName

    if (!grouped.has(name)) {
      grouped.set(name, {
        name,
        credential: null,
        forks: [],
        allRepos: []
      })
    }

    const group = grouped.get(name)!
    group.allRepos.push(repo)

    if (isCredential(repo)) {
      group.credential = repo
    } else {
      group.forks.push(repo)
    }
  }

  return grouped
}

/**
 * Get all credentials (grand repos) from a list
 * @param repos - Array of all repos
 * @returns Array of credential repos
 */
export function getCredentials(
  repos: RepoWithRelations[]
): RepoWithRelations[] {
  return repos.filter(isCredential)
}

/**
 * Get all forks from a list
 * @param repos - Array of all repos
 * @returns Array of fork repos
 */
export function getForks(
  repos: RepoWithRelations[]
): RepoWithRelations[] {
  return repos.filter(isFork)
}

/**
 * Check if a repo can be safely deleted
 * @param repo - Repo to check
 * @param allRepos - Array of all repos
 * @param machines - Array of machines with vault status
 * @returns Object with canDelete flag and reason if blocked
 */
export function canDeleteRepo(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[],
  machines: MachineWithVaultStatus[]
): { canDelete: boolean; reason?: string; affectedMachines?: AffectedMachine[] } {
  const { isCredential: repoIsCredential, affectedMachines } = getAffectedResources(
    repo,
    allRepos,
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
  childClones?: RepoWithRelations[]
}

/**
 * Comprehensive repo deletion validation
 * Provides detailed information for UI to display appropriate dialogs
 * @param repo - Repo to validate for deletion
 * @param allRepos - Array of all repos
 * @param machines - Array of machines with vault status
 * @returns Detailed validation result with block/warn/allow status
 */
export function validateRepoDeletion(
  repo: RepoWithRelations,
  allRepos: RepoWithRelations[],
  machines: MachineWithVaultStatus[]
): DeletionValidationResult {
  const repoIsCredential = isCredential(repo)
  const { affectedMachines, forks } = getAffectedResources(
    repo,
    allRepos,
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
 * Get the display name for a repo (including tag if present)
 * @param repo - Repo to get display name for
 * @returns Display name with optional tag
 */
export function getRepoDisplayName(repo: RepoWithRelations): string {
  return repo.repoTag
    ? `${repo.repoName}:${repo.repoTag}`
    : repo.repoName
}

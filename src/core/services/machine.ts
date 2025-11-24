/**
 * VaultStatus parser service for machine deployment information
 * This service consolidates duplicated parsing logic from 6+ components
 */

import { isValidGuid } from '../utils/validation'

/**
 * Status of the vault status check
 */
export type VaultStatusState = 'completed' | 'pending' | 'failed' | 'unknown'

/**
 * Parsed vault status result
 */
export interface ParsedVaultStatus {
  status: VaultStatusState
  repositories: DeployedRepository[]
  rawResult?: string
  error?: string
}

/**
 * Information about a deployed repository on a machine
 */
export interface DeployedRepository {
  /** Repository name or GUID */
  name: string
  /** Repository GUID (if resolved) */
  repositoryGuid?: string
  /** Grand GUID (if resolved) */
  grandGuid?: string
  /** Size in bytes */
  size?: number
  /** Human-readable size */
  size_human?: string
  /** Whether the repository is mounted */
  mounted?: boolean
  /** Whether the repository is accessible */
  accessible?: boolean
  /** Whether Docker is running */
  docker_running?: boolean
  /** Number of containers */
  container_count?: number
  /** Additional properties from vault status */
  [key: string]: unknown
}

/**
 * Repository information for resolution
 */
export interface RepositoryInfo {
  repositoryGuid: string
  repositoryName: string
  grandGuid?: string
}

/**
 * Clean the result string from vault status
 * Handles jq errors and trailing content
 * @param result - Raw result string
 * @returns Cleaned result string
 */
export function cleanResultString(result: string): string {
  if (!result) return result

  let cleaned = result

  // Handle trailing content after JSON
  const jsonEndMatch = cleaned.match(/(\}[\s\n]*$)/)
  if (jsonEndMatch) {
    const lastBraceIndex = cleaned.lastIndexOf('}')
    if (lastBraceIndex < cleaned.length - 10) {
      cleaned = cleaned.substring(0, lastBraceIndex + 1)
    }
  }

  // Handle jq errors appearing after valid JSON
  const newlineIndex = cleaned.indexOf('\njq:')
  if (newlineIndex > 0) {
    cleaned = cleaned.substring(0, newlineIndex)
  }

  return cleaned.trim()
}

/**
 * Parse vault status JSON string into structured data
 * @param vaultStatusJson - The vault status JSON string from the machine
 * @returns Parsed vault status with repositories
 */
export function parseVaultStatus(vaultStatusJson: string | undefined | null): ParsedVaultStatus {
  if (!vaultStatusJson) {
    return { status: 'unknown', repositories: [] }
  }

  // Check for error prefixes
  if (vaultStatusJson.trim().startsWith('jq:') ||
      vaultStatusJson.trim().startsWith('error:') ||
      !vaultStatusJson.trim().startsWith('{')) {
    return { status: 'unknown', repositories: [], error: 'Invalid vault status format' }
  }

  try {
    const data = JSON.parse(vaultStatusJson)

    if (data.status !== 'completed' || !data.result) {
      return {
        status: (data.status as VaultStatusState) || 'unknown',
        repositories: []
      }
    }

    // Clean and parse the result
    const cleanedResult = cleanResultString(data.result)
    const result = JSON.parse(cleanedResult)

    const repositories: DeployedRepository[] = []
    if (result?.repositories && Array.isArray(result.repositories)) {
      repositories.push(...result.repositories)
    }

    return {
      status: 'completed',
      repositories,
      rawResult: cleanedResult
    }
  } catch (error) {
    return {
      status: 'unknown',
      repositories: [],
      error: error instanceof Error ? error.message : String(error)
    }
  }
}

/**
 * Resolve repository names from GUIDs using a repository list
 * @param repositories - Array of deployed repositories
 * @param repositoryList - Array of repository information for resolution
 * @returns Repositories with resolved names
 */
export function resolveRepositoryNames(
  repositories: DeployedRepository[],
  repositoryList: RepositoryInfo[]
): DeployedRepository[] {
  return repositories.map(repo => {
    // Check if name is a GUID
    if (isValidGuid(repo.name)) {
      const matchingRepo = repositoryList.find(r => r.repositoryGuid === repo.name)
      if (matchingRepo) {
        return {
          ...repo,
          name: matchingRepo.repositoryName,
          repositoryGuid: matchingRepo.repositoryGuid,
          grandGuid: matchingRepo.grandGuid
        }
      }
    }
    return repo
  })
}

/**
 * Machine information with vault status
 * Uses generic to allow any machine type that has the required properties
 */
export type MachineWithVaultStatus = {
  machineName: string
  vaultStatus?: string | null
}

/**
 * Find deployed repositories across multiple machines
 * @param machines - Array of machines with vault status
 * @param repositoryGuids - Array of repository GUIDs to find
 * @returns Map of machine name to deployed repositories matching the GUIDs
 */
export function findDeployedRepositories(
  machines: MachineWithVaultStatus[],
  repositoryGuids: string[]
): Map<string, DeployedRepository[]> {
  const result = new Map<string, DeployedRepository[]>()

  for (const machine of machines) {
    const parsed = parseVaultStatus(machine.vaultStatus)

    if (parsed.status === 'completed' && parsed.repositories.length > 0) {
      const matchingRepos = parsed.repositories.filter(repo => {
        // Check if repo name (which might be GUID) matches
        return repositoryGuids.includes(repo.name) ||
               (repo.repositoryGuid && repositoryGuids.includes(repo.repositoryGuid))
      })

      if (matchingRepos.length > 0) {
        result.set(machine.machineName, matchingRepos)
      }
    }
  }

  return result
}

/**
 * Get all deployed repositories from a machine
 * @param machine - Machine with vault status
 * @param repositoryList - Optional repository list for name resolution
 * @returns Array of deployed repositories
 */
export function getMachineRepositories(
  machine: MachineWithVaultStatus,
  repositoryList?: RepositoryInfo[]
): DeployedRepository[] {
  const parsed = parseVaultStatus(machine.vaultStatus)

  if (parsed.status !== 'completed') {
    return []
  }

  if (repositoryList && repositoryList.length > 0) {
    return resolveRepositoryNames(parsed.repositories, repositoryList)
  }

  return parsed.repositories
}

/**
 * Check if a specific repository is deployed on a machine
 * @param machine - Machine with vault status
 * @param repositoryGuid - Repository GUID to check
 * @returns True if the repository is deployed
 */
export function isRepositoryDeployed(
  machine: MachineWithVaultStatus,
  repositoryGuid: string
): boolean {
  const repositories = getMachineRepositories(machine)

  return repositories.some(repo =>
    repo.name === repositoryGuid ||
    repo.repositoryGuid === repositoryGuid
  )
}

/**
 * Get summary of deployed repositories on a machine
 * @param machine - Machine with vault status
 * @returns Summary object with counts and status
 */
export function getDeploymentSummary(machine: MachineWithVaultStatus): {
  status: VaultStatusState
  totalRepositories: number
  mountedCount: number
  dockerRunningCount: number
} {
  const parsed = parseVaultStatus(machine.vaultStatus)

  if (parsed.status !== 'completed') {
    return {
      status: parsed.status,
      totalRepositories: 0,
      mountedCount: 0,
      dockerRunningCount: 0
    }
  }

  return {
    status: 'completed',
    totalRepositories: parsed.repositories.length,
    mountedCount: parsed.repositories.filter(r => r.mounted).length,
    dockerRunningCount: parsed.repositories.filter(r => r.docker_running).length
  }
}

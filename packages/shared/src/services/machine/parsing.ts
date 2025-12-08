/**
 * VaultStatus parser service for machine deployment information
 * This service consolidates duplicated parsing logic from 6+ components
 */

import { isValidGuid } from '../../validation';

/**
 * Status of the vault status check
 */
export type VaultStatusState = 'completed' | 'pending' | 'failed' | 'unknown';

/**
 * Parsed vault status result
 */
export interface ParsedVaultStatus {
  status: VaultStatusState;
  repos: DeployedRepo[];
  rawResult?: string;
  error?: string;
}

/**
 * Information about a deployed repo on a machine
 */
export interface DeployedRepo {
  /** Repo name or GUID */
  name: string;
  /** Repo GUID (if resolved) */
  repoGuid?: string;
  /** Grand GUID (if resolved) */
  grandGuid?: string | null;
  /** Size in bytes */
  size?: number;
  /** Human-readable size */
  size_human?: string;
  /** Whether the repo is mounted */
  mounted?: boolean;
  /** Whether the repo is accessible */
  accessible?: boolean;
  /** Whether Docker is running */
  docker_running?: boolean;
  /** Number of containers */
  container_count?: number;
  /** Additional properties from vault status */
  [key: string]: unknown;
}

/**
 * Repo information for resolution
 */
export interface RepoInfo {
  repoGuid: string;
  repoName: string;
  grandGuid?: string | null;
}

/**
 * Clean the result string from vault status
 * Handles jq errors and trailing content
 * @param result - Raw result string
 * @returns Cleaned result string
 */
export function cleanResultString(result: string): string {
  if (!result) return result;

  let cleaned = result;

  // Handle trailing content after JSON
  const jsonEndMatch = cleaned.match(/(\}[\s\n]*$)/);
  if (jsonEndMatch) {
    const lastBraceIndex = cleaned.lastIndexOf('}');
    if (lastBraceIndex < cleaned.length - 10) {
      cleaned = cleaned.substring(0, lastBraceIndex + 1);
    }
  }

  // Handle jq errors appearing after valid JSON
  const newlineIndex = cleaned.indexOf('\njq:');
  if (newlineIndex > 0) {
    cleaned = cleaned.substring(0, newlineIndex);
  }

  return cleaned.trim();
}

/**
 * Parse vault status JSON string into structured data
 * @param vaultStatusJson - The vault status JSON string from the machine
 * @returns Parsed vault status with repos
 */
export function parseVaultStatus(vaultStatusJson: string | undefined | null): ParsedVaultStatus {
  if (!vaultStatusJson) {
    return { status: 'unknown', repos: [] };
  }

  // Check for error prefixes
  if (
    vaultStatusJson.trim().startsWith('jq:') ||
    vaultStatusJson.trim().startsWith('error:') ||
    !vaultStatusJson.trim().startsWith('{')
  ) {
    return { status: 'unknown', repos: [], error: 'Invalid vault status format' };
  }

  try {
    const data = JSON.parse(vaultStatusJson);

    if (data.status !== 'completed' || !data.result) {
      return {
        status: (data.status as VaultStatusState) || 'unknown',
        repos: [],
      };
    }

    // Clean and parse the result
    const cleanedResult = cleanResultString(data.result);
    const result = JSON.parse(cleanedResult);

    const repos: DeployedRepo[] = [];
    if (result?.repositories && Array.isArray(result.repositories)) {
      repos.push(...result.repositories);
    }

    return {
      status: 'completed',
      repos,
      rawResult: cleanedResult,
    };
  } catch (error) {
    return {
      status: 'unknown',
      repos: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Resolve repo names from GUIDs using a repo list
 * @param repos - Array of deployed repos
 * @param repoList - Array of repo information for resolution
 * @returns Repos with resolved names
 */
export function resolveRepoNames(repos: DeployedRepo[], repoList: RepoInfo[]): DeployedRepo[] {
  return repos.map((repo) => {
    // Check if name is a GUID
    if (isValidGuid(repo.name)) {
      const matchingRepo = repoList.find((r) => r.repoGuid === repo.name);
      if (matchingRepo) {
        return {
          ...repo,
          name: matchingRepo.repoName,
          repoGuid: matchingRepo.repoGuid,
          grandGuid: matchingRepo.grandGuid,
        };
      }
    }
    return repo;
  });
}

/**
 * Machine information with vault status
 * Uses generic to allow any machine type that has the required properties
 */
export type MachineWithVaultStatus = {
  machineName: string;
  vaultStatus?: string | null;
};

/**
 * Find deployed repos across multiple machines
 * @param machines - Array of machines with vault status
 * @param repoGuids - Array of repo GUIDs to find
 * @returns Map of machine name to deployed repos matching the GUIDs
 */
export function findDeployedRepos(
  machines: MachineWithVaultStatus[],
  repoGuids: string[]
): Map<string, DeployedRepo[]> {
  const result = new Map<string, DeployedRepo[]>();

  for (const machine of machines) {
    const parsed = parseVaultStatus(machine.vaultStatus);

    if (parsed.status === 'completed' && parsed.repos.length > 0) {
      const matchingRepos = parsed.repos.filter((repo) => {
        // Check if repo name (which might be GUID) matches
        return (
          repoGuids.includes(repo.name) || (repo.repoGuid && repoGuids.includes(repo.repoGuid))
        );
      });

      if (matchingRepos.length > 0) {
        result.set(machine.machineName, matchingRepos);
      }
    }
  }

  return result;
}

/**
 * Get all deployed repos from a machine
 * @param machine - Machine with vault status
 * @param repoList - Optional repo list for name resolution
 * @returns Array of deployed repos
 */
export function getMachineRepos(
  machine: MachineWithVaultStatus,
  repoList?: RepoInfo[]
): DeployedRepo[] {
  const parsed = parseVaultStatus(machine.vaultStatus);

  if (parsed.status !== 'completed') {
    return [];
  }

  if (repoList && repoList.length > 0) {
    return resolveRepoNames(parsed.repos, repoList);
  }

  return parsed.repos;
}

/**
 * Check if a specific repo is deployed on a machine
 * @param machine - Machine with vault status
 * @param repoGuid - Repo GUID to check
 * @returns True if the repo is deployed
 */
export function isRepoDeployed(machine: MachineWithVaultStatus, repoGuid: string): boolean {
  const repos = getMachineRepos(machine);

  return repos.some((repo) => repo.name === repoGuid || repo.repoGuid === repoGuid);
}

/**
 * Get summary of deployed repos on a machine
 * @param machine - Machine with vault status
 * @returns Summary object with counts and status
 */
export function getDeploymentSummary(machine: MachineWithVaultStatus): {
  status: VaultStatusState;
  totalRepos: number;
  mountedCount: number;
  dockerRunningCount: number;
} {
  const parsed = parseVaultStatus(machine.vaultStatus);

  if (parsed.status !== 'completed') {
    return {
      status: parsed.status,
      totalRepos: 0,
      mountedCount: 0,
      dockerRunningCount: 0,
    };
  }

  return {
    status: 'completed',
    totalRepos: parsed.repos.length,
    mountedCount: parsed.repos.filter((r) => r.mounted).length,
    dockerRunningCount: parsed.repos.filter((r) => r.docker_running).length,
  };
}

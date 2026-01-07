/**
 * VaultStatus parser service for machine deployment information
 * This service consolidates duplicated parsing logic from 6+ components
 */

import {
  isListResult,
  getContainers,
  getSystemContainers,
  getServices,
  getSystemInfo,
  getBlockDevices,
  getNetworkInterfaces,
  getHealthSummary as getListHealthSummary,
  type ListResult,
  type ContainerInfo,
  type ServiceInfo,
  type SystemInfo,
  type BlockDevice,
  type NetworkInterface,
} from '../../queue-vault/data/list-types.generated';
import { isValidGuid } from '../../validation';

// Re-export list types for CLI consumers
export type { ListResult, ContainerInfo, ServiceInfo, SystemInfo, BlockDevice, NetworkInterface };

/**
 * Status of the vault status check
 */
export type VaultStatusState = 'completed' | 'pending' | 'failed' | 'unknown';

/**
 * Parsed vault status result
 */
export interface ParsedVaultStatus {
  status: VaultStatusState;
  repositories: DeployedRepo[];
  rawResult?: string;
  error?: string;
}

/**
 * Information about a deployed repository on a machine
 */
export interface DeployedRepo {
  /** Repository name or GUID */
  name: string;
  /** Repository GUID (if resolved) */
  repositoryGuid?: string;
  /** Grand GUID (if resolved) */
  grandGuid?: string | null;
  /** Size in bytes */
  size?: number;
  /** Human-readable size */
  size_human?: string;
  /** Whether the repository is mounted */
  mounted?: boolean;
  /** Whether the repository is accessible */
  accessible?: boolean;
  /** Whether Docker is running */
  docker_running?: boolean;
  /** Number of containers */
  container_count?: number;
  /** Additional properties from vault status */
  [key: string]: unknown;
}

/**
 * Repository information for resolution
 */
export interface RepoInfo {
  repositoryGuid: string;
  repositoryName: string;
  grandGuid?: string | null;
}

/**
 * Check if vault data appears to be encrypted (base64, not JSON)
 */
function isEncryptedVaultData(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length < 40 || trimmed.startsWith('{')) {
    return false;
  }
  try {
    JSON.parse(trimmed);
    return false;
  } catch {
    return /^[A-Za-z0-9+/]+=*$/.test(trimmed);
  }
}

/**
 * Parse vault status JSON string into structured data.
 * Expects raw ListResult format from 'renet list all --json'.
 *
 * @param vaultStatusJson - The vault status JSON string from the machine
 * @returns Parsed vault status with repositories
 */
export function parseVaultStatus(vaultStatusJson: string | undefined | null): ParsedVaultStatus {
  if (!vaultStatusJson) {
    return { status: 'unknown', repositories: [] };
  }

  if (isEncryptedVaultData(vaultStatusJson)) {
    return { status: 'unknown', repositories: [], error: 'encrypted' };
  }

  const trimmed = vaultStatusJson.trim();
  if (!trimmed.startsWith('{')) {
    return { status: 'unknown', repositories: [], error: 'Invalid vault status format' };
  }

  try {
    const data = JSON.parse(vaultStatusJson);

    const repositories: DeployedRepo[] = [];
    if (data.repositories && Array.isArray(data.repositories)) {
      repositories.push(...data.repositories);
    }

    return {
      status: 'completed',
      repositories,
      rawResult: vaultStatusJson,
    };
  } catch (error) {
    return {
      status: 'unknown',
      repositories: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Resolve repository names from GUIDs using a repository list
 * @param repositories - Array of deployed repositories
 * @param repositoryList - Array of repository information for resolution
 * @returns Repositories with resolved names
 */
export function resolveRepositoryNames(
  repositories: DeployedRepo[],
  repositoryList: RepoInfo[]
): DeployedRepo[] {
  return repositories.map((repository) => {
    // Check if name is a GUID
    if (isValidGuid(repository.name)) {
      const matchingRepository = repositoryList.find((r) => r.repositoryGuid === repository.name);
      if (matchingRepository) {
        return {
          ...repository,
          name: matchingRepository.repositoryName,
          repositoryGuid: matchingRepository.repositoryGuid,
          grandGuid: matchingRepository.grandGuid,
        };
      }
    }
    return repository;
  });
}

/**
 * Machine information with vault status
 * Uses generic to allow any machine type that has the required properties
 * Note: machineName is nullable to match generated API types
 */
export type MachineWithVaultStatus = {
  machineName: string | null;
  vaultStatus?: string | null;
};

/**
 * Find deployed repositories across multiple machines
 * @param machines - Array of machines with vault status
 * @param repositoryGuids - Array of repository GUIDs to find
 * @returns Map of machine name to deployed repositories matching the GUIDs
 */
export function findDeployedRepositories(
  machines: MachineWithVaultStatus[],
  repositoryGuids: string[]
): Map<string, DeployedRepo[]> {
  const result = new Map<string, DeployedRepo[]>();

  for (const machine of machines) {
    // Skip machines without a name
    if (!machine.machineName) {
      continue;
    }

    const parsed = parseVaultStatus(machine.vaultStatus);

    if (parsed.status === 'completed' && parsed.repositories.length > 0) {
      const matchingRepositories = parsed.repositories.filter((repository) => {
        // Check if repository name (which might be GUID) matches
        return (
          repositoryGuids.includes(repository.name) ||
          (repository.repositoryGuid && repositoryGuids.includes(repository.repositoryGuid))
        );
      });

      if (matchingRepositories.length > 0) {
        result.set(machine.machineName, matchingRepositories);
      }
    }
  }

  return result;
}

/**
 * Get all deployed repositories from a machine
 * @param machine - Machine with vault status
 * @param repositoryList - Optional repository list for name resolution
 * @returns Array of deployed repositories
 */
export function getMachineRepositories(
  machine: MachineWithVaultStatus,
  repositoryList?: RepoInfo[]
): DeployedRepo[] {
  const parsed = parseVaultStatus(machine.vaultStatus);

  if (parsed.status !== 'completed') {
    return [];
  }

  if (repositoryList && repositoryList.length > 0) {
    return resolveRepositoryNames(parsed.repositories, repositoryList);
  }

  return parsed.repositories;
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
  const repositories = getMachineRepositories(machine);

  return repositories.some(
    (repository) =>
      repository.name === repositoryGuid || repository.repositoryGuid === repositoryGuid
  );
}

/**
 * Get summary of deployed repositories on a machine
 * @param machine - Machine with vault status
 * @returns Summary object with counts and status
 */
export function getDeploymentSummary(machine: MachineWithVaultStatus): {
  status: VaultStatusState;
  totalRepositories: number;
  mountedCount: number;
  dockerRunningCount: number;
} {
  const parsed = parseVaultStatus(machine.vaultStatus);

  if (parsed.status !== 'completed') {
    return {
      status: parsed.status,
      totalRepositories: 0,
      mountedCount: 0,
      dockerRunningCount: 0,
    };
  }

  return {
    status: 'completed',
    totalRepositories: parsed.repositories.length,
    mountedCount: parsed.repositories.filter((r) => r.mounted).length,
    dockerRunningCount: parsed.repositories.filter((r) => r.docker_running).length,
  };
}

/**
 * Parse vault status and return the full ListResult data.
 * Returns null if parsing fails or data is encrypted.
 */
export function parseListResult(vaultStatusJson: string | undefined | null): ListResult | null {
  if (!vaultStatusJson) {
    return null;
  }

  if (isEncryptedVaultData(vaultStatusJson)) {
    return null;
  }

  const trimmed = vaultStatusJson.trim();
  if (!trimmed.startsWith('{')) {
    return null;
  }

  try {
    const data = JSON.parse(vaultStatusJson);
    if (isListResult(data)) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Get containers from a machine's vault status.
 * Returns containers from repository Docker instances.
 */
export function getMachineContainers(machine: MachineWithVaultStatus): ContainerInfo[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return getContainers(listResult);
}

/**
 * Get system containers from a machine's vault status.
 * Returns containers from system-level Docker.
 */
export function getMachineSystemContainers(machine: MachineWithVaultStatus): ContainerInfo[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return getSystemContainers(listResult);
}

/**
 * Get all containers (both repository and system) from a machine.
 */
export function getAllMachineContainers(machine: MachineWithVaultStatus): ContainerInfo[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return [...getContainers(listResult), ...getSystemContainers(listResult)];
}

/**
 * Get systemd services from a machine's vault status.
 */
export function getMachineServices(machine: MachineWithVaultStatus): ServiceInfo[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return getServices(listResult);
}

/**
 * Get system info from a machine's vault status.
 */
export function getMachineSystemInfo(machine: MachineWithVaultStatus): SystemInfo | null {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return null;
  }
  return getSystemInfo(listResult);
}

/**
 * Get block devices from a machine's vault status.
 */
export function getMachineBlockDevices(machine: MachineWithVaultStatus): BlockDevice[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return getBlockDevices(listResult);
}

/**
 * Get network interfaces from a machine's vault status.
 */
export function getMachineNetworkInterfaces(machine: MachineWithVaultStatus): NetworkInterface[] {
  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult) {
    return [];
  }
  return getNetworkInterfaces(listResult);
}

/**
 * Health check result for CI/CD pipelines.
 */
export interface MachineHealthResult {
  /** Overall health status */
  healthy: boolean;
  /** Exit code for CI (0=healthy, 1=warning, 2=error, 3=critical) */
  exitCode: number;
  /** Human-readable status message */
  message: string;
  /** Detailed health breakdown */
  details: {
    system: {
      memoryPercent: string | null;
      diskPercent: string | null;
      datastorePercent: string | null;
      uptime: string | null;
    };
    containers: {
      total: number;
      running: number;
      healthy: number;
      unhealthy: number;
      failingStreak: number;
    };
    services: {
      total: number;
      active: number;
      failed: number;
      restarting: number;
    };
    storage: {
      smartHealthy: number;
      smartFailing: number;
      maxTemperature: number | null;
    };
    repositories: {
      total: number;
      mounted: number;
      dockerRunning: number;
    };
  };
  /** Issues found during health check */
  issues: string[];
}

/**
 * Perform comprehensive health check on a machine.
 * Returns structured health data with CI-friendly exit codes.
 *
 * Exit codes:
 * - 0: All healthy
 * - 1: Warnings (high utilization, minor issues)
 * - 2: Errors (unhealthy containers, failed services)
 * - 3: Critical (SMART failing, crash loops)
 */
export function getMachineHealth(machine: MachineWithVaultStatus): MachineHealthResult {
  const listResult = parseListResult(machine.vaultStatus);
  const issues: string[] = [];
  let exitCode = 0;

  // Default empty result
  const defaultDetails = {
    system: {
      memoryPercent: null,
      diskPercent: null,
      datastorePercent: null,
      uptime: null,
    },
    containers: {
      total: 0,
      running: 0,
      healthy: 0,
      unhealthy: 0,
      failingStreak: 0,
    },
    services: {
      total: 0,
      active: 0,
      failed: 0,
      restarting: 0,
    },
    storage: {
      smartHealthy: 0,
      smartFailing: 0,
      maxTemperature: null,
    },
    repositories: {
      total: 0,
      mounted: 0,
      dockerRunning: 0,
    },
  };

  if (!listResult) {
    return {
      healthy: false,
      exitCode: 2,
      message: 'No status data available',
      details: defaultDetails,
      issues: ['No vault status data'],
    };
  }

  const systemInfo = getSystemInfo(listResult);
  const containers = getContainers(listResult);
  const services = getServices(listResult);
  const blockDevices = getBlockDevices(listResult);
  const healthSummary = getListHealthSummary(listResult);

  // System checks
  const systemDetails = {
    memoryPercent: systemInfo?.memory.use_percent ?? null,
    diskPercent: systemInfo?.disk.use_percent ?? null,
    datastorePercent: systemInfo?.datastore.use_percent ?? null,
    uptime: systemInfo?.uptime ?? null,
  };

  // Parse percentages and check thresholds
  const parsePercent = (val: string | null): number | null => {
    if (!val) return null;
    const match = val.match(/(\d+)/);
    return match ? parseInt(match[1], 10) : null;
  };

  const memPct = parsePercent(systemDetails.memoryPercent);
  const diskPct = parsePercent(systemDetails.diskPercent);
  const dsPct = parsePercent(systemDetails.datastorePercent);

  if (memPct !== null && memPct > 90) {
    issues.push(`Memory usage critical: ${memPct}%`);
    exitCode = Math.max(exitCode, 2);
  } else if (memPct !== null && memPct > 80) {
    issues.push(`Memory usage high: ${memPct}%`);
    exitCode = Math.max(exitCode, 1);
  }

  if (diskPct !== null && diskPct > 95) {
    issues.push(`Disk usage critical: ${diskPct}%`);
    exitCode = Math.max(exitCode, 2);
  } else if (diskPct !== null && diskPct > 85) {
    issues.push(`Disk usage high: ${diskPct}%`);
    exitCode = Math.max(exitCode, 1);
  }

  if (dsPct !== null && dsPct > 95) {
    issues.push(`Datastore usage critical: ${dsPct}%`);
    exitCode = Math.max(exitCode, 2);
  } else if (dsPct !== null && dsPct > 85) {
    issues.push(`Datastore usage high: ${dsPct}%`);
    exitCode = Math.max(exitCode, 1);
  }

  // Container checks
  const runningContainers = containers.filter((c) => c.state === 'running').length;
  const maxFailingStreak = Math.max(0, ...containers.map((c) => c.health?.failing_streak ?? 0));

  const containerDetails = {
    total: containers.length,
    running: runningContainers,
    healthy: healthSummary.containersHealthy,
    unhealthy: healthSummary.containersUnhealthy,
    failingStreak: maxFailingStreak,
  };

  if (healthSummary.containersUnhealthy > 0) {
    issues.push(`${healthSummary.containersUnhealthy} unhealthy container(s)`);
    exitCode = Math.max(exitCode, 2);
  }

  if (maxFailingStreak > 5) {
    issues.push(`Container health check failing streak: ${maxFailingStreak}`);
    exitCode = Math.max(exitCode, 3);
  } else if (maxFailingStreak > 2) {
    issues.push(`Container health check failing streak: ${maxFailingStreak}`);
    exitCode = Math.max(exitCode, 1);
  }

  // Service checks
  const restartingServices = services.filter(
    (s) => s.restart_count > 3 || s.sub_state === 'auto-restart'
  ).length;

  const serviceDetails = {
    total: services.length,
    active: healthSummary.servicesActive,
    failed: healthSummary.servicesFailed,
    restarting: restartingServices,
  };

  if (healthSummary.servicesFailed > 0) {
    issues.push(`${healthSummary.servicesFailed} failed service(s)`);
    exitCode = Math.max(exitCode, 2);
  }

  if (restartingServices > 0) {
    issues.push(`${restartingServices} service(s) in restart loop`);
    exitCode = Math.max(exitCode, 3);
  }

  // Storage checks
  let smartHealthy = 0;
  let smartFailing = 0;
  let maxTemp: number | null = null;

  for (const device of blockDevices) {
    if (device.smart_health === 'PASSED' || device.smart_health === 'OK') {
      smartHealthy++;
    } else if (device.smart_health && device.smart_health !== 'N/A') {
      smartFailing++;
    }
    if (device.temperature !== undefined) {
      maxTemp = maxTemp === null ? device.temperature : Math.max(maxTemp, device.temperature);
    }
  }

  const storageDetails = {
    smartHealthy,
    smartFailing,
    maxTemperature: maxTemp,
  };

  if (smartFailing > 0) {
    issues.push(`${smartFailing} storage device(s) with SMART failure`);
    exitCode = Math.max(exitCode, 3);
  }

  if (maxTemp !== null && maxTemp > 60) {
    issues.push(`Storage temperature high: ${maxTemp}°C`);
    exitCode = Math.max(exitCode, 1);
  }

  // Repository checks
  const repositoryDetails = {
    total: healthSummary.repositoriesTotal,
    mounted: healthSummary.repositoriesMounted,
    dockerRunning: listResult.repositories.filter((r) => r.docker_running).length,
  };

  const unmountedCount = repositoryDetails.total - repositoryDetails.mounted;
  if (unmountedCount > 0) {
    issues.push(`${unmountedCount} repository(ies) not mounted`);
    exitCode = Math.max(exitCode, 1);
  }

  // Generate message
  let message: string;
  if (exitCode === 0) {
    message = 'All systems healthy';
  } else if (exitCode === 1) {
    message = 'System has warnings';
  } else if (exitCode === 2) {
    message = 'System has errors';
  } else {
    message = 'System has critical issues';
  }

  return {
    healthy: exitCode === 0,
    exitCode,
    message,
    details: {
      system: systemDetails,
      containers: containerDetails,
      services: serviceDetails,
      storage: storageDetails,
      repositories: repositoryDetails,
    },
    issues,
  };
}

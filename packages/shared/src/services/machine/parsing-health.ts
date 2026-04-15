/**
 * Machine health check utilities.
 * Extracted from parsing.ts to keep file size manageable.
 */

import {
  type BlockDevice,
  type ContainerInfo,
  getBlockDevices,
  getContainers,
  getHealthSummary as getListHealthSummary,
  getLicenseStatuses,
  getServices,
  getSystemInfo,
  type ListResult,
  type ServiceInfo,
  type SystemInfo,
} from '../../queue-vault/data/list-types.generated';
import { type MachineWithVaultStatus, parseListResult } from './parsing-types';

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
    licenses: {
      total: number;
      valid: number;
      expired: number;
      machineMismatch: number;
      missing: number;
      invalidSignature: number;
    };
  };
  /** Issues found during health check */
  issues: string[];
}

/** Health check context passed between helper functions */
interface HealthCheckContext {
  issues: string[];
  exitCode: number;
}

/** Parse a percentage string like "85%" to a number */
function parsePercent(val: string | null): number | null {
  if (!val) return null;
  const match = /(\d+)/.exec(val);
  return match ? Number.parseInt(match[1], 10) : null;
}

/** Get default empty health details */
function getDefaultHealthDetails(): MachineHealthResult['details'] {
  return {
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
    licenses: {
      total: 0,
      valid: 0,
      expired: 0,
      machineMismatch: 0,
      missing: 0,
      invalidSignature: 0,
    },
  };
}

/** Check system resource usage (memory, disk, datastore) */
function checkSystemUsage(
  systemInfo: SystemInfo | null,
  ctx: HealthCheckContext
): MachineHealthResult['details']['system'] {
  const systemDetails = {
    memoryPercent: systemInfo?.memory.use_percent ?? null,
    diskPercent: systemInfo?.disk.use_percent ?? null,
    datastorePercent: systemInfo?.datastore.use_percent ?? null,
    uptime: systemInfo?.uptime ?? null,
  };

  const memPct = parsePercent(systemDetails.memoryPercent);
  const diskPct = parsePercent(systemDetails.diskPercent);
  const dsPct = parsePercent(systemDetails.datastorePercent);

  checkUsageThreshold(memPct, 'Memory', 90, 80, ctx);
  checkUsageThreshold(diskPct, 'Disk', 95, 85, ctx);
  checkUsageThreshold(dsPct, 'Datastore', 95, 85, ctx);

  return systemDetails;
}

/** Check a single usage threshold */
function checkUsageThreshold(
  value: number | null,
  name: string,
  criticalThreshold: number,
  warningThreshold: number,
  ctx: HealthCheckContext
): void {
  if (value === null) return;

  if (value > criticalThreshold) {
    ctx.issues.push(`${name} usage critical: ${value}%`);
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  } else if (value > warningThreshold) {
    ctx.issues.push(`${name} usage high: ${value}%`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }
}

/** Check container health */
function checkContainers(
  containers: ContainerInfo[],
  healthSummary: ReturnType<typeof getListHealthSummary>,
  ctx: HealthCheckContext
): MachineHealthResult['details']['containers'] {
  const runningContainers = containers.filter((c) => c.state === 'running').length;
  const maxFailingStreak = containers.reduce(
    (max, c) => Math.max(max, c.health?.failing_streak ?? 0),
    0
  );

  if (healthSummary.containersUnhealthy > 0) {
    ctx.issues.push(`${healthSummary.containersUnhealthy} unhealthy container(s)`);
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }

  if (maxFailingStreak > 5) {
    ctx.issues.push(`Container health check failing streak: ${maxFailingStreak}`);
    ctx.exitCode = Math.max(ctx.exitCode, 3);
  } else if (maxFailingStreak > 2) {
    ctx.issues.push(`Container health check failing streak: ${maxFailingStreak}`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }

  return {
    total: containers.length,
    running: runningContainers,
    healthy: healthSummary.containersHealthy,
    unhealthy: healthSummary.containersUnhealthy,
    failingStreak: maxFailingStreak,
  };
}

/** Check service health */
function checkServices(
  services: ServiceInfo[],
  healthSummary: ReturnType<typeof getListHealthSummary>,
  ctx: HealthCheckContext
): MachineHealthResult['details']['services'] {
  const restartingServices = services.filter(
    (s) => s.restart_count > 3 || s.sub_state === 'auto-restart'
  ).length;

  if (healthSummary.servicesFailed > 0) {
    ctx.issues.push(`${healthSummary.servicesFailed} failed service(s)`);
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }

  if (restartingServices > 0) {
    ctx.issues.push(`${restartingServices} service(s) in restart loop`);
    ctx.exitCode = Math.max(ctx.exitCode, 3);
  }

  return {
    total: services.length,
    active: healthSummary.servicesActive,
    failed: healthSummary.servicesFailed,
    restarting: restartingServices,
  };
}

/** Storage metrics collected from block devices */
interface StorageMetrics {
  smartHealthy: number;
  smartFailing: number;
  maxTemperature: number | null;
}

/** Check if SMART health indicates a healthy device */
function isSmartHealthy(smartHealth: string | undefined): boolean {
  return smartHealth === 'PASSED' || smartHealth === 'OK';
}

/** Check if SMART health indicates a failing device */
function isSmartFailing(smartHealth: string | undefined): boolean {
  return Boolean(smartHealth) && smartHealth !== 'N/A' && !isSmartHealthy(smartHealth);
}

/** Collect storage metrics from block devices */
function collectStorageMetrics(blockDevices: BlockDevice[]): StorageMetrics {
  let smartHealthy = 0;
  let smartFailing = 0;
  let maxTemp: number | null = null;

  for (const device of blockDevices) {
    if (isSmartHealthy(device.smart_health)) {
      smartHealthy++;
    } else if (isSmartFailing(device.smart_health)) {
      smartFailing++;
    }
    if (device.temperature !== undefined) {
      maxTemp = maxTemp === null ? device.temperature : Math.max(maxTemp, device.temperature);
    }
  }

  return { smartHealthy, smartFailing, maxTemperature: maxTemp };
}

/** Check storage health */
function checkStorage(
  blockDevices: BlockDevice[],
  ctx: HealthCheckContext
): MachineHealthResult['details']['storage'] {
  const metrics = collectStorageMetrics(blockDevices);

  if (metrics.smartFailing > 0) {
    ctx.issues.push(`${metrics.smartFailing} storage device(s) with SMART failure`);
    ctx.exitCode = Math.max(ctx.exitCode, 3);
  }

  if (metrics.maxTemperature !== null && metrics.maxTemperature > 60) {
    ctx.issues.push(`Storage temperature high: ${metrics.maxTemperature}°C`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }

  return metrics;
}

/** Check repository health */
function checkRepositories(
  listResult: ListResult,
  healthSummary: ReturnType<typeof getListHealthSummary>,
  ctx: HealthCheckContext
): MachineHealthResult['details']['repositories'] {
  const repositoryDetails = {
    total: healthSummary.repositoriesTotal,
    mounted: healthSummary.repositoriesMounted,
    dockerRunning: listResult.repositories.filter((r) => r.docker_running).length,
  };

  const unmountedCount = repositoryDetails.total - repositoryDetails.mounted;
  if (unmountedCount > 0) {
    ctx.issues.push(`${unmountedCount} repository(ies) not mounted`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }

  return repositoryDetails;
}

/** Check license statuses */
function checkLicenses(
  listResult: ListResult,
  ctx: HealthCheckContext
): MachineHealthResult['details']['licenses'] {
  const statuses = getLicenseStatuses(listResult);
  const details = {
    total: statuses.length,
    valid: 0,
    expired: 0,
    machineMismatch: 0,
    missing: 0,
    invalidSignature: 0,
  };

  for (const s of statuses) {
    switch (s.status) {
      case 'valid':
        details.valid++;
        break;
      case 'expired':
        details.expired++;
        break;
      case 'machine_mismatch':
        details.machineMismatch++;
        break;
      case 'missing':
        details.missing++;
        break;
      case 'invalid_signature':
      case 'sequence_regression':
        details.invalidSignature++;
        break;
    }
  }

  if (details.expired > 0) {
    ctx.issues.push(`${details.expired} repo license(s) expired`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }
  if (details.machineMismatch > 0) {
    ctx.issues.push(`${details.machineMismatch} repo license(s) have machine ID mismatch`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }
  if (details.invalidSignature > 0) {
    ctx.issues.push(`${details.invalidSignature} repo license(s) have invalid signatures`);
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }
  if (details.total > 0 && details.missing === details.total) {
    ctx.issues.push('All repo licenses are missing');
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }

  return details;
}

/** Get health message based on exit code */
function getHealthMessage(exitCode: number): string {
  const messages: Record<number, string> = {
    0: 'All systems healthy',
    1: 'System has warnings',
    2: 'System has errors',
  };
  return messages[exitCode] ?? 'System has critical issues';
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

  if (!listResult) {
    return {
      healthy: false,
      exitCode: 2,
      message: 'No status data available',
      details: getDefaultHealthDetails(),
      issues: ['No vault status data'],
    };
  }

  const ctx: HealthCheckContext = { issues: [], exitCode: 0 };

  const systemInfo = getSystemInfo(listResult);
  const containers = getContainers(listResult);
  const services = getServices(listResult);
  const blockDevices = getBlockDevices(listResult);
  const healthSummary = getListHealthSummary(listResult);

  const systemDetails = checkSystemUsage(systemInfo, ctx);
  const containerDetails = checkContainers(containers, healthSummary, ctx);
  const serviceDetails = checkServices(services, healthSummary, ctx);
  const storageDetails = checkStorage(blockDevices, ctx);
  const repositoryDetails = checkRepositories(listResult, healthSummary, ctx);
  const licenseDetails = checkLicenses(listResult, ctx);

  return {
    healthy: ctx.exitCode === 0,
    exitCode: ctx.exitCode,
    message: getHealthMessage(ctx.exitCode),
    details: {
      system: systemDetails,
      containers: containerDetails,
      services: serviceDetails,
      storage: storageDetails,
      repositories: repositoryDetails,
      licenses: licenseDetails,
    },
    issues: ctx.issues,
  };
}

/**
 * Machine health check utilities.
 * Extracted from parsing.ts to keep file size manageable.
 */

import {
  type BlockDevice,
  type ContainerInfo,
  getBlockDevices,
  getContainers,
  getLicenseStatuses,
  getHealthSummary as getListHealthSummary,
  getServices,
  getSystemInfo,
  type ListResult,
  type ServiceInfo,
  type SystemInfo,
} from '../../renet-contract/data/list-types.generated.js';
import { type MachineWithVaultStatus, parseListResult } from './parsing-types.js';

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

/**
 * SMART states that mean "we could not read it", not "the disk is dying".
 *
 * Virtualised disks are the common case: a QEMU/KVM guest sees a virtual block
 * device with no SMART data at all and reports `unknown`. Counting that as a
 * failure raises the highest-severity health issue on every VM, which is worse
 * than saying nothing — an alert that always fires teaches people to ignore the
 * ones that matter.
 */
const SMART_INDETERMINATE = new Set(['N/A', 'unknown', 'UNKNOWN', 'Unknown', '-', '']);

/** Check if SMART health indicates a failing device */
function isSmartFailing(smartHealth: string | undefined): boolean {
  if (!smartHealth) return false;
  if (SMART_INDETERMINATE.has(smartHealth.trim())) return false;
  return !isSmartHealthy(smartHealth);
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

  // Only repos that are SUPPOSED to be up count as a problem. A repo with
  // autostart off is deliberately parked — reporting it as unhealthy every time
  // is the same cry-wolf failure as flagging a virtual disk's unknown SMART
  // state, and it buries the repos that really did fall over.
  const unmountedCount = listResult.repositories.filter((r) => r.autostart && !r.mounted).length;
  if (unmountedCount > 0) {
    ctx.issues.push(`${unmountedCount} repository(ies) not mounted`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }

  return repositoryDetails;
}

/**
 * Days after which a repo's last successful backup is worth reporting.
 *
 * Set above the longest schedule in normal use (a weekly job legitimately leaves
 * a repo six days old) so an on-schedule estate stays silent. The incident this
 * exists for showed repos at 10 and 11 days while every other surface reported
 * success.
 */
const BACKUP_STALE_DAYS = 10;

/**
 * Report repos whose backups have gone stale, or that were skipped outright.
 *
 * This is the check that catches a backup job succeeding while covering less
 * than it should — the failure mode that unit status, exit codes and
 * `backup status` all miss by construction, because the job genuinely succeeds.
 */
function checkBackupCoverage(listResult: ListResult, ctx: HealthCheckContext): void {
  const coverage = listResult.backup_coverage;
  if (!coverage) return; // no backup has ever run; absent is not a claim of health

  const stale = coverage.repos.filter((r) => r.age_days >= BACKUP_STALE_DAYS);
  if (stale.length > 0) {
    ctx.issues.push(
      `${stale.length} repository(ies) not backed up in over ${BACKUP_STALE_DAYS} days`
    );
    ctx.exitCode = Math.max(ctx.exitCode, 1);
  }

  // A repo with no successful backup on record AND a recorded skip is a real
  // incident. Without the skip it is most likely newly created and simply has
  // not had its first run yet — flagging that would fire on every new repo.
  const neverBackedUp = coverage.repos.filter((r) => r.age_days < 0 && Boolean(r.last_skipped_at));
  if (neverBackedUp.length > 0) {
    ctx.issues.push(`${neverBackedUp.length} repository(ies) have never been backed up`);
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }
}

/**
 * Whether a licence has entered its refresh window.
 *
 * An absent or unparseable timestamp means "no window published" and must not be
 * read as overdue — the server owns this hint, and inventing urgency from a
 * missing field would fire on every machine whose licences predate the field.
 */
function isPastRefreshWindow(refreshRecommendedAt: string | undefined): boolean {
  if (!refreshRecommendedAt) return false;
  const due = Date.parse(refreshRecommendedAt);
  if (Number.isNaN(due)) return false;
  return due <= Date.now();
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

  // Licences carry a soft window (refreshRecommendedAt) before they hard-expire,
  // so a lapse is predictable rather than sudden. Saying so while everything
  // still works is the only warning that arrives in time to act on: once a
  // licence actually expires, the backup has already started skipping that repo.
  // Severity stays below expired — this is "action is due", not "something broke".
  const dueForRefresh = statuses.filter(
    (s) => s.runtimeValid && isPastRefreshWindow(s.refreshRecommendedAt)
  ).length;
  if (dueForRefresh > 0) {
    ctx.issues.push(`${dueForRefresh} repo license(s) due for refresh`);
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
  } else if (details.missing > 0) {
    // A repo without a license is silently dropped from backups (the sync skips
    // unlicensed repos and still exits 0), so a partial outage is exactly the
    // case that needs saying out loud — previously only an all-missing estate
    // raised anything, and losing 3 of 11 licenses reported nothing at all.
    ctx.issues.push(`${details.missing} repo license(s) missing`);
    ctx.exitCode = Math.max(ctx.exitCode, 1);
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
  checkBackupCoverage(listResult, ctx);
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

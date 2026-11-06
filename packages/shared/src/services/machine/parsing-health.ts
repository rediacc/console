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
import {
  type FindingSeverity,
  type FindingTarget,
  type HealthFinding,
  severityOfExit,
  withFix,
} from './findings.js';
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
  /** The same issues as coded findings (D-remedy), each with its fix from the findings table */
  findings: HealthFinding[];
}

/** Health check context passed between helper functions */
interface HealthCheckContext {
  issues: string[];
  findings: HealthFinding[];
  exitCode: number;
}

/** One coded finding, its fix from the table; it raises the exit code to `exitCode`. */
function raise(
  ctx: HealthCheckContext,
  exitCode: number,
  finding: { code: string; subject: string; detail: string; target?: FindingTarget },
  severity: FindingSeverity = severityOfExit(exitCode)
): void {
  ctx.findings.push(withFix({ ...finding, severity }));
  ctx.exitCode = Math.max(ctx.exitCode, exitCode);
}

/** An issue string and its finding: the issue text stays exactly what it was, the finding names each subject. */
function issue(
  ctx: HealthCheckContext,
  exitCode: number,
  text: string,
  finding: { code: string; subject: string; target?: FindingTarget },
  severity?: FindingSeverity
): void {
  ctx.issues.push(text);
  raise(ctx, exitCode, { ...finding, detail: text }, severity);
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

  checkUsageThreshold(memPct, 'Memory', 90, 80, ctx, {
    code: 'memory.usage.high',
    subject: 'memory',
  });
  checkUsageThreshold(diskPct, 'Disk', 95, 85, ctx, { code: 'disk.usage.high', subject: 'disk' });
  checkUsageThreshold(dsPct, 'Datastore', 95, 85, ctx, {
    code: 'datastore.usage.high',
    subject: 'datastore',
  });

  return systemDetails;
}

/** Check a single usage threshold */
function checkUsageThreshold(
  value: number | null,
  name: string,
  criticalThreshold: number,
  warningThreshold: number,
  ctx: HealthCheckContext,
  finding: { code: string; subject: string; target?: FindingTarget }
): void {
  if (value === null) return;

  if (value > criticalThreshold) {
    issue(ctx, 2, `${name} usage critical: ${value}%`, finding);
  } else if (value > warningThreshold) {
    issue(ctx, 1, `${name} usage high: ${value}%`, finding);
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
    containerFindings(
      ctx,
      2,
      'container.unhealthy',
      containers.filter((c) => c.health?.status === 'unhealthy'),
      'unhealthy'
    );
    // The summary counts what the per-container records may not name; the verdict never drops below it.
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }

  const looping = containers.filter((c) => /^restarting\b/i.test(c.status ?? ''));
  if (looping.length > 0) {
    ctx.issues.push(`${looping.length} container(s) in restart loop`);
    containerFindings(ctx, 3, 'container.restart-loop', looping, 'in a restart loop');
  }

  const streakText = `Container health check failing streak: ${maxFailingStreak}`;
  const streaking = containers.filter((c) => (c.health?.failing_streak ?? 0) > 2);
  if (maxFailingStreak > 5) {
    ctx.issues.push(streakText);
    containerFindings(ctx, 3, 'container.health-streak', streaking, 'health check failing streak');
  } else if (maxFailingStreak > 2) {
    ctx.issues.push(streakText);
    containerFindings(ctx, 1, 'container.health-streak', streaking, 'health check failing streak');
  }

  return {
    total: containers.length,
    running: runningContainers,
    healthy: healthSummary.containersHealthy,
    unhealthy: healthSummary.containersUnhealthy,
    failingStreak: maxFailingStreak,
  };
}

/** One finding per container, naming it and its repository, so a fix can restart exactly that container. */
function containerFindings(
  ctx: HealthCheckContext,
  exitCode: number,
  code: string,
  containers: ContainerInfo[],
  what: string
): void {
  for (const c of containers) {
    raise(ctx, exitCode, {
      code,
      subject: c.name,
      detail: `Container ${c.name} ${what} (${c.status})`,
      target: { container: c.name, repository: c.repository || undefined },
    });
  }
}

/** Check service health */
function checkServices(
  services: ServiceInfo[],
  healthSummary: ReturnType<typeof getListHealthSummary>,
  ctx: HealthCheckContext
): MachineHealthResult['details']['services'] {
  const restarting = services.filter((s) => s.restart_count > 3 || s.sub_state === 'auto-restart');
  const restartingServices = restarting.length;

  if (healthSummary.servicesFailed > 0) {
    ctx.issues.push(`${healthSummary.servicesFailed} failed service(s)`);
    serviceFindings(
      ctx,
      2,
      'service.failed',
      services.filter((s) => s.active_state === 'failed'),
      'failed'
    );
    ctx.exitCode = Math.max(ctx.exitCode, 2);
  }

  if (restartingServices > 0) {
    ctx.issues.push(`${restartingServices} service(s) in restart loop`);
    serviceFindings(ctx, 3, 'service.restart-loop', restarting, 'keeps restarting');
  }

  return {
    total: services.length,
    active: healthSummary.servicesActive,
    failed: healthSummary.servicesFailed,
    restarting: restartingServices,
  };
}

/** One finding per systemd unit, naming it, so the operator command restarts exactly that unit. */
function serviceFindings(
  ctx: HealthCheckContext,
  exitCode: number,
  code: string,
  services: ServiceInfo[],
  what: string
): void {
  for (const s of services) {
    const unit = s.service_name || s.name;
    raise(ctx, exitCode, {
      code,
      subject: unit,
      detail: `Service ${unit} ${what} (restarts: ${s.restart_count})`,
      target: { unit, repository: s.repository || undefined },
    });
  }
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
    issue(ctx, 3, `${metrics.smartFailing} storage device(s) with SMART failure`, {
      code: 'storage.smart.failing',
      subject: 'storage',
    });
  }

  if (metrics.maxTemperature !== null && metrics.maxTemperature > 60) {
    issue(ctx, 1, `Storage temperature high: ${metrics.maxTemperature}°C`, {
      code: 'storage.temperature.high',
      subject: 'storage',
    });
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

  // Only repos that are SUPPOSED to be up count as a problem. A repo with autostart off is deliberately parked — reporting it as unhealthy every time is the same cry-wolf failure as flagging a virtual disk's unknown SMART state, and it buries the repos that really did fall over.
  const unmounted = listResult.repositories.filter((r) => r.autostart && !r.mounted);
  if (unmounted.length > 0) {
    ctx.issues.push(`${unmounted.length} repository(ies) not mounted`);
    for (const r of unmounted) {
      raise(ctx, 1, {
        code: 'repo.unmounted',
        subject: r.repo_name ?? r.name,
        detail: `Repository ${r.repo_name ?? r.name} is set to autostart but not mounted`,
        target: { repository: r.name, networkId: r.network_id },
      });
    }
  }

  for (const repo of listResult.repositories) {
    const pct = parsePercent(repo.disk_space?.use_percent ?? null);
    if (pct === null) continue;
    checkUsageThreshold(pct, `Repository ${repo.name} disk`, 95, 85, ctx, {
      code: 'repo.disk.high',
      subject: repo.repo_name ?? repo.name,
      target: { repository: repo.name, networkId: repo.network_id },
    });
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
    issue(
      ctx,
      1,
      `${stale.length} repository(ies) not backed up in over ${BACKUP_STALE_DAYS} days`,
      {
        code: 'backup.stale',
        subject: 'backup',
      }
    );
  }

  // A repo with no successful backup on record AND a recorded skip is a real incident. Without the skip it is most likely newly created and simply has not had its first run yet — flagging that would fire on every new repo.
  const neverBackedUp = coverage.repos.filter((r) => r.age_days < 0 && Boolean(r.last_skipped_at));
  if (neverBackedUp.length > 0) {
    issue(ctx, 2, `${neverBackedUp.length} repository(ies) have never been backed up`, {
      code: 'backup.never',
      subject: 'backup',
    });
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

  // Licences carry a soft window (refreshRecommendedAt) before they hard-expire, so a lapse is predictable rather than sudden. Saying so while everything still works is the only warning that arrives in time to act on: once a licence actually expires, the backup has already started skipping that repo. Severity stays below expired — this is "action is due", not "something broke".
  const dueForRefresh = statuses.filter(
    (s) => s.runtimeValid && isPastRefreshWindow(s.refreshRecommendedAt)
  ).length;
  const license = { subject: 'licenses' };
  if (dueForRefresh > 0) {
    issue(ctx, 0, `${dueForRefresh} repo license(s) due for refresh`, {
      ...license,
      code: 'license.refresh-due',
    });
  }

  if (details.expired > 0) {
    issue(ctx, 1, `${details.expired} repo license(s) expired`, {
      ...license,
      code: 'license.expired',
    });
  }
  if (details.machineMismatch > 0) {
    issue(ctx, 1, `${details.machineMismatch} repo license(s) have machine ID mismatch`, {
      ...license,
      code: 'license.machine-mismatch',
    });
  }
  if (details.invalidSignature > 0) {
    issue(ctx, 2, `${details.invalidSignature} repo license(s) have invalid signatures`, {
      ...license,
      code: 'license.invalid-signature',
    });
  }
  if (details.total > 0 && details.missing === details.total) {
    issue(ctx, 2, 'All repo licenses are missing', { ...license, code: 'license.missing' });
  } else if (details.missing > 0) {
    // A repo without a license is silently dropped from backups (the sync skips unlicensed repos and still exits 0), so a partial outage is exactly the
    // case that needs saying out loud — previously only an all-missing estate
    // raised anything, and losing 3 of 11 licenses reported nothing at all.
    issue(ctx, 1, `${details.missing} repo license(s) missing`, {
      ...license,
      code: 'license.missing',
    });
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
      findings: [
        withFix({
          code: 'machine.status.unavailable',
          severity: 'error',
          subject: machine.machineName ?? 'machine',
          detail: 'No vault status data',
        }),
      ],
    };
  }

  const ctx: HealthCheckContext = { issues: [], findings: [], exitCode: 0 };

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
    findings: ctx.findings,
  };
}

// Certificate expiry (G5, D-certs): the proxy's ACME certificates from the listing's `certificates` section. Traefik renews 30 days ahead, so a certificate under 21 days means at least nine days of failed renewals.

/** Days left below which a certificate is a warning. */
export const CERT_EXPIRY_WARNING_DAYS = 21;
/** Days left below which a certificate is an error. */
export const CERT_EXPIRY_ERROR_DAYS = 7;

/** The listing's `certificates` section (renet pkg/list CertificatesSection). */
export interface CertificatesSectionInput {
  status: string;
  certificates: { main: string; sans?: string[]; not_after: string }[] | null;
  error?: string;
}

/** One certificate finding: `cert.expiry.near`, or `cert.store.unreadable` when acme.json could not be read. */
export interface CertificateFinding {
  code: 'cert.expiry.near' | 'cert.store.unreadable';
  severity: 'warning' | 'error';
  subject: string;
  detail: string;
  daysLeft?: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function certificateFinding(
  cert: { main: string; not_after: string },
  now: Date
): CertificateFinding | null {
  const notAfter = Date.parse(cert.not_after);
  if (Number.isNaN(notAfter)) return null;
  const daysLeft = Math.floor((notAfter - now.getTime()) / DAY_MS);
  if (daysLeft >= CERT_EXPIRY_WARNING_DAYS) return null;
  return {
    code: 'cert.expiry.near',
    severity: daysLeft < CERT_EXPIRY_ERROR_DAYS ? 'error' : 'warning',
    subject: cert.main,
    daysLeft,
    detail:
      daysLeft < 0
        ? `Certificate ${cert.main} expired ${-daysLeft} day(s) ago (${cert.not_after})`
        : `Certificate ${cert.main} expires in ${daysLeft} day(s) (${cert.not_after})`,
  };
}

/**
 * Judge each certificate's expiry: under 21 days a warning, under 7 an error, each naming the certificate. An absent section (no proxy on the machine) raises nothing; a section renet could not read is one warning, never a clean machine.
 */
export function checkCertificateExpiry(
  section: CertificatesSectionInput | null | undefined,
  now: Date = new Date()
): CertificateFinding[] {
  if (!section) return [];
  if (section.status !== 'ok') {
    return [
      {
        code: 'cert.store.unreadable',
        severity: 'warning',
        subject: 'acme.json',
        detail: `proxy certificate store unreadable: ${section.error ?? section.status}`,
      },
    ];
  }
  return (section.certificates ?? [])
    .map((cert) => certificateFinding(cert, now))
    .filter((f): f is CertificateFinding => f !== null);
}

// The ACME shared-CNAME class (G6, D-certs, F17): lego follows a CNAME on `_acme-challenge.<name>` and writes the challenge TXT at the chain's end, so an end that is not itself an `_acme-challenge.` name, or one end shared by several names, makes those renewals collide.

/** A certificates section that carries where each name's challenge lands (renet pkg/list ChallengeInfo). */
export interface ChallengeSectionInput {
  status: string;
  certificates: { main: string; challenges?: { name: string; cname?: string }[] }[] | null;
  delegated_names?: string[];
}

/** One `acme.challenge.cname-shared` finding: the chain end, and the certificate names that land there. */
export interface AcmeChallengeFinding {
  code: 'acme.challenge.cname-shared';
  severity: 'warning';
  subject: string;
  names: string[];
  detail: string;
}

const stripWildcard = (name: string): string => name.replace(/^\*\./, '').toLowerCase();

/** Map each challenge chain end to the (wildcard-stripped) names landing there, delegated names and ends left out. */
function challengeEnds(section: ChallengeSectionInput): Map<string, Set<string>> {
  const delegated = new Set((section.delegated_names ?? []).map(stripWildcard));
  const ends = new Map<string, Set<string>>();
  const challenges = (section.certificates ?? []).flatMap((cert) => cert.challenges ?? []);
  for (const ch of challenges) {
    const name = stripWildcard(ch.name);
    const end = (ch.cname ?? '').toLowerCase();
    if (!end || delegated.has(name) || delegated.has(end)) continue;
    ends.set(end, (ends.get(end) ?? new Set<string>()).add(name));
  }
  return ends;
}

/**
 * Report the F17 shape: a challenge chain that ends at a name not beginning `_acme-challenge.`, or two names sharing
 * one end. A name (or end) in the proxy's `delegated_names` is a deliberate delegation and never reported; a name with
 * no CNAME raises nothing.
 */
export function checkAcmeChallengeCnames(
  section: ChallengeSectionInput | null | undefined
): AcmeChallengeFinding[] {
  if (section?.status !== 'ok') return [];
  const findings: AcmeChallengeFinding[] = [];
  for (const [end, nameSet] of challengeEnds(section)) {
    const names = [...nameSet].sort((a, b) => a.localeCompare(b));
    if (end.startsWith('_acme-challenge.') && names.length < 2) continue;
    findings.push({
      code: 'acme.challenge.cname-shared',
      severity: 'warning',
      subject: end,
      names,
      detail: `ACME challenge for ${names.join(', ')} follows a CNAME to ${end}; renewals there collide`,
    });
  }
  return findings;
}

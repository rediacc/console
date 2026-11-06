import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type {
  JobInfo,
  JobOrigin,
  ListResult,
  RepositoryResources,
  StorageHealthResult,
  SystemInfo,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import {
  getBlockDevices,
  getContainers,
  getHealthSummary,
  getLicenseStatuses,
  getNetworkInterfaces,
  getRepositories,
  getServices,
  getSystemContainers,
} from '@rediacc/shared/renet-contract/data/list-types.generated';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import type { RuntimeRepoLicenseStatus } from '../../services/account/license.js';
import {
  type FailedVerifyRepo,
  failedVerifyRepos,
  formatSpan,
  type MissedTargetRepo,
  type StaleBackupRepo,
} from '../../services/backup/backup-schedule-coverage.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import type { RenetProcess } from '../../services/renet/renet-daemons.js';
import type { InfraConfig, MachineConfig } from '../../types/index.js';
import { ambiguous, notFound } from '../../utils/cli-exit-error.js';
import { extractAutoRoute, extractCustomDomain } from '../../utils/domain-helpers.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import {
  createGuidResolver,
  createRepoNameResolver,
  loadGuidMap,
  type RepoNameSource,
  resolveGuids,
} from '../../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import {
  filterRepositoriesBySearch,
  runContainerHealthCheck,
  runServiceStabilityCheck,
} from './status-checks.js';

/** Resolves a repo GUID + server repo_name to a display name and its source. */
type RepoNameResolver = (
  guid: string,
  serverRepoName?: string
) => { name: string; source: RepoNameSource };

import { setExitCode, writeStderr, writeStdout } from '../../services/core/request-context.js';

/** Parse size strings like "71.9G", "180.3G" into GB numbers. */
function parseSizeToGb(size: string | undefined): number {
  if (!size) return 0;
  const match = /^([\d.]+)\s*(G|T|M)/i.exec(size);
  if (!match) return 0;
  const val = Number.parseFloat(match[1]);
  const unit = match[2].toUpperCase();
  if (unit === 'T') return val * 1024;
  if (unit === 'M') return val / 1024;
  return val;
}

/**
 * Section renderer for table output.
 * Each section maps a ListResult section to a header + flat table rows.
 */
interface SectionRenderer {
  title: string;
  getData: (result: ListResult) => Record<string, unknown>[];
}

function flattenSystem(sys: SystemInfo): Record<string, unknown> {
  return {
    machine_id: sys.machine_id ? `${sys.machine_id.slice(0, 16)}...` : '-',
    hostname: sys.hostname,
    os: sys.os_name,
    kernel: sys.kernel,
    cpu: `${sys.cpu_model} (${sys.cpu_count} cores)`,
    memory: `${sys.memory.used} / ${sys.memory.total}`,
    disk: `${sys.disk.used} / ${sys.disk.total} (${sys.disk.use_percent})`,
    datastore: `${sys.datastore.used} / ${sys.datastore.total} (${sys.datastore.use_percent})`,
    uptime: sys.uptime,
  };
}

const BYTES_PER_GB = 1024 ** 3;

/**
 * Fragmentation as a comparable number: extents per GB (what renet's
 * low/moderate/high label is bucketed from: <100 / <1000 / >=1000). Shown
 * instead of the bare label so repos can be compared directly. Falls back to the
 * raw extent count when size is unknown.
 *
 * NOTE: this counts extents of the repo's copy-on-write IMAGE file on the pool
 * btrfs, not the files inside the mounted volume. High values are an expected
 * artifact of CoW under random writes, not inner-fs fragmentation, and are
 * informational only (defragmentation is unsupported: it would unshare reflinked
 * forks/snapshots and inflate pool usage). See storageHealthFragmentationNote.
 */
export function fragmentationPerGb(extents: number, sizeBytes: number): string {
  if (sizeBytes <= 0) return `${extents}`;
  return `${Math.round(extents / (sizeBytes / BYTES_PER_GB))}/GB`;
}

/**
 * Build the rows for the Storage Health table from the renet `storage_health`
 * section. Names are resolved like the Repositories section (config > server
 * repo_name > GUID) and server-sourced ones get the ' *' marker. The `*_human`
 * fields are pre-formatted by renet and displayed as-is; fragmentation is shown
 * as a numeric extents/GB ratio. Returns [] when no storage-health data is
 * present (so the section is skipped).
 */
export function buildStorageHealthRows(
  storageHealth: ListResult['storage_health'],
  repoName: RepoNameResolver
): Record<string, unknown>[] {
  return (storageHealth?.repositories ?? []).map((sh) => {
    const { name, source } = repoName(sh.guid, sh.name);
    return {
      name: source === 'server' ? `${name} *` : name,
      quota: formatBytesShort(sh.quota_bytes),
      allocated: formatBytesShort(sh.allocated_bytes),
      exclusive: sh.exclusive_human,
      shared: sh.shared_human,
      reclaimable: reclaimableDisplay(sh),
      discards: discardsDisplay(sh),
      divergence: `${sh.divergence_percent.toFixed(1)}%`,
      fragmentation: fragmentationPerGb(sh.extents, sh.size),
    };
  });
}

/** Reclaimable = allocated-vs-fs-used gap a `repo trim` could free; '-' when
 * unmounted (the inner filesystem is sealed, so the gap is unknown). */
function reclaimableDisplay(sh: { mounted: boolean; reclaimable_human?: string }): string {
  if (!sh.mounted) return '-';
  return sh.reclaimable_human ?? formatBytesShort(0);
}

function discardsDisplay(sh: { mounted: boolean; discards_enabled: boolean }): string {
  if (!sh.mounted) return '-';
  return sh.discards_enabled ? 'on' : 'off';
}

/** Format raw byte counts compactly (the `*_human` fields arrive
 * pre-formatted from renet; quota/allocated are raw numbers). */
function formatBytesShort(bytes: number | undefined): string {
  const b = bytes ?? 0;
  const tb = 1024 ** 4;
  const gb = 1024 ** 3;
  const mb = 1024 ** 2;
  if (b >= tb) return `${(b / tb).toFixed(1)} TB`;
  if (b >= gb) return `${(b / gb).toFixed(1)} GB`;
  if (b >= mb) return `${(b / mb).toFixed(1)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${b} B`;
}

/** The marker of a repository whose cgroup has no memory.max (PLAN-repo-resource-limits Decision 5). */
export const NO_MEMORY_CAP = 'no cap';

/**
 * The resource cells of a repository row: memory as "current / max", the OOM kills at the cap, and the RAM volume as
 * "used / size". A repository with no memory.max shows NO_MEMORY_CAP for its max; one with no resources section
 * (unmounted, or no cgroup) shows '-'.
 */
export function repoResourceCells(r: RepositoryResources | undefined): {
  memory: string;
  oomKills: number | string;
  ram: string;
} {
  if (!r) return { memory: '-', oomKills: '-', ram: '-' };
  const max = r.memory_max > 0 ? formatBytesShort(r.memory_max) : NO_MEMORY_CAP;
  return {
    memory: `${formatBytesShort(r.memory_current)} / ${max}`,
    oomKills: r.oom_kills,
    ram: r.ram_size > 0 ? `${formatBytesShort(r.ram_used)} / ${formatBytesShort(r.ram_size)}` : '-',
  };
}

/** The display names of the repositories whose cgroup runs without a memory.max: any one of them can take the host's memory. */
export function uncappedRepoNames(listResult: ListResult, repoName: RepoNameResolver): string[] {
  return getRepositories(listResult)
    .filter((repo) => repo.resources !== undefined && repo.resources.memory_max === 0)
    .map((repo) => repoName(repo.name, repo.repo_name).name);
}

function getSections(
  resolve: (guid: string) => string,
  repoName: RepoNameResolver,
  licenseDetail: LicenseDetail,
  baseDomain?: string,
  machineName?: string
): SectionRenderer[] {
  return [
    {
      title: 'System',
      getData: (r) => (r.system ? [flattenSystem(r.system)] : []),
    },
    {
      title: 'Repositories',
      getData: (r) =>
        getRepositories(r).map((repo) => {
          const { name, source } = repoName(repo.name, repo.repo_name);
          return {
            // Mark names that came from the machine (not in local config) with ' *'.
            name: source === 'server' ? `${name} *` : name,
            guid: repo.name,
            size: repo.size_human,
            mounted: repo.mounted ? 'Yes' : 'No',
            docker: repo.docker_running ? 'Yes' : 'No',
            running: repo.containers_running ? 'Yes' : 'No',
            autostart: repo.autostart ? 'Yes' : 'No',
            containers: repo.container_count,
            disk: repo.disk_space?.use_percent ?? '-',
            ...repoResourceCells(repo.resources),
            modified: repo.modified_human,
          };
        }),
    },
    {
      title: 'Storage Health',
      getData: (r) => buildStorageHealthRows(r.storage_health, repoName),
    },
    {
      // How long ago each repo was actually uploaded, read from the state the backup job merges across runs. A backup can report success while covering less than it used to, a repo loses its licence, or a transfer window closes before the largest images are reached, and the exit status says nothing. The growing age here is what reveals it.
      title: 'Backup Coverage',
      getData: (r) =>
        (r.backup_coverage?.repos ?? []).map((b) => ({
          repository: resolve(b.guid),
          lastBackup: b.last_success_at ?? DEFAULTS.STATUS.NEVER,
          // -1 means no successful backup is on record; showing it as a number
          // would read as "0 days ago", the opposite of the truth.
          ageDays: b.age_days < 0 ? '-' : b.age_days,
          lastSkipped: b.last_skipped_at ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
          skipReason: b.last_skip_reason ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
        })),
    },
    {
      // Rendered by default, not only under --strict. The watchdog maintains this registry precisely to catch the slow silent failure, a container whose healthcheck has been failing for days, and it is worth nothing
      // if seeing it requires already suspecting it and passing a flag. The
      // table is empty when nothing is drifting, so a healthy machine stays
      // quiet; --strict still controls the CI exit code.
      title: 'Health Drift',
      getData: (r) =>
        (r.health_drift?.entries ?? []).map((e) => ({
          container: e.container,
          repository: e.repo ? resolve(e.repo) : '-',
          status: e.status,
          failingStreak: e.failing_streak,
          firstSeen: e.first_seen,
          lastSeen: e.last_seen,
        })),
    },
    {
      title: 'Containers',
      getData: (r) =>
        getContainers(r).map((c) => ({
          name: c.name,
          state: c.state,
          status: c.status,
          health: c.health?.status ?? '-',
          cpu: c.cpu_percent ?? '-',
          memory: c.memory_usage ?? '-',
          repository: resolve(c.repository),
          autoRoute: extractAutoRoute(c.labels, baseDomain, machineName),
          domain: extractCustomDomain(c.labels, baseDomain),
        })),
    },
    {
      title: 'Services',
      getData: (r) =>
        getServices(r).map((s) => ({
          name: s.service_name,
          state: s.active_state,
          sub: s.sub_state,
          restarts: s.restart_count,
          memory: s.memory_human,
          repository: resolve(s.repository),
        })),
    },
    {
      title: 'System Containers',
      getData: (r) =>
        getSystemContainers(r).map((c) => ({
          name: c.name,
          state: c.state,
          status: c.status,
          health: c.health?.status ?? '-',
          cpu: c.cpu_percent ?? '-',
          memory: c.memory_usage ?? '-',
        })),
    },
    {
      title: 'Network Interfaces',
      getData: (r) =>
        getNetworkInterfaces(r).map((iface) => ({
          name: iface.name,
          state: iface.state,
          mac: iface.mac_address,
          ipv4: iface.ipv4_addresses.join(', '),
          ipv6: iface.ipv6_addresses.join(', '),
          mtu: iface.mtu,
        })),
    },
    {
      title: 'Block Devices',
      getData: (r) =>
        getBlockDevices(r).map((d) => ({
          name: d.name,
          model: d.model,
          size: d.size_human,
          type: d.type,
          health: d.smart_health,
          partitions: d.partitions.length,
        })),
    },
    {
      title: 'Licenses',
      getData: (r) => {
        const currentMachineId = r.system?.machine_id;
        return getLicenseStatuses(r).map((l) => {
          const extra = licenseDetail?.get(l.repositoryGuid);
          return {
            repository: resolve(l.repositoryGuid),
            status: l.status,
            issued: l.issuedAt ? relativeTime(l.issuedAt) : '-',
            expires: l.hardExpiresAt ? relativeTime(l.hardExpiresAt) : '-',
            machine_match: getMachineMatch(currentMachineId, l.machineId),
            datastore: extra?.datastoreId?.slice(0, 8) ?? '-',
            // The whole reason this column exists: a blocked-backup marker means unattended backups have been failing on licensing since that timestamp, and nothing else in this output says so.
            backups: licenseDetailBackups(licenseDetail, extra),
            renewed: formatRenewalOutcome(extra?.lastRenewal),
          };
        });
      },
    },
  ];
}

/**
 * The `renewed` cell. A bare `refused` tells the operator that unattended
 * renewal is failing but not why, and the why is what decides the next move: a
 * lapsed subscription is a billing problem, a revoked delegation cert is an
 * on-prem problem. The server's `code` is the stable identifier for that, so it
 * rides in the cell; the prose stays in `subscription status -m <machine>`.
 */
function formatRenewalOutcome(renewal: RuntimeRepoLicenseStatus['lastRenewal']): string {
  if (!renewal) return '-';
  if (!renewal.code) return renewal.outcome;
  return `${renewal.outcome}: ${renewal.code}`;
}

/**
 * Blocked-backup markers, printed under the table as errors.
 *
 * A column alone is not enough for this one. The marker is the only signal that
 * a machine's scheduled backups have silently stopped copying data, and a
 * single cell in a wide table on a machine with thirty repos is exactly where
 * that gets missed.
 */
function renderBlockedBackupAlerts(licenseDetail: LicenseDetail): void {
  if (!licenseDetail) return;
  for (const entry of licenseDetail.values()) {
    const marker = entry.blockedBackup;
    if (!marker) continue;
    outputService.error(
      t('commands.machine.status.licenseBackupBlocked', {
        repositoryGuid: entry.repositoryGuid,
        at: marker.at,
        reason: marker.reason,
        message: marker.message,
      })
    );
  }
}

function getMachineMatch(
  currentMachineId: string | undefined,
  licenseMachineId: string | undefined
): string {
  if (!currentMachineId || !licenseMachineId) return '-';
  return licenseMachineId === currentMachineId ? 'Yes' : 'No';
}

const MS_PER_DAY = 1000 * 60 * 60 * 24;

function relativeTime(iso: string): string {
  const now = Date.now();
  const target = new Date(iso).getTime();
  const diffMs = target - now;
  const absDays = Math.abs(Math.round(diffMs / MS_PER_DAY));
  if (absDays === 0) return 'today';
  if (diffMs > 0) return `in ${absDays}d`;
  return `${absDays}d ago`;
}

function printSummary(result: ListResult): void {
  const health = getHealthSummary(result);
  const parts: string[] = [];

  parts.push(`${health.repositoriesMounted}/${health.repositoriesTotal} repos mounted`);

  const totalContainers =
    health.containersHealthy + health.containersUnhealthy + health.containersNoHealth;
  if (totalContainers > 0) {
    parts.push(`${totalContainers} containers`);
  }
  if (health.containersUnhealthy > 0) {
    parts.push(`${health.containersUnhealthy} unhealthy`);
  }
  if (health.servicesFailed > 0) {
    parts.push(`${health.servicesFailed} failed services`);
  }

  outputService.info(parts.join(' | '));
}

function flattenConnection(config: MachineConfig): Record<string, unknown> {
  return {
    ip: config.ip,
    user: config.user,
    port: config.port ?? DEFAULTS.SSH.PORT,
    datastore: config.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
  };
}

function flattenInfra(infra: InfraConfig): Record<string, unknown> {
  return {
    baseDomain: infra.baseDomain ?? '-',
    publicIPv4: infra.publicIPv4 ?? '-',
    publicIPv6: infra.publicIPv6 ?? '-',
    tcpPorts: infra.tcpPorts?.join(', ') ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
    udpPorts: infra.udpPorts?.join(', ') ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
  };
}

/** Map CLI flag names to renet section names. */
const SECTION_FLAGS = [
  { flag: 'system', section: 'system' },
  { flag: 'repositories', section: 'repositories' },
  { flag: 'containers', section: 'containers' },
  { flag: 'services', section: 'services' },
  { flag: 'network', section: 'network' },
  { flag: 'blockDevices', section: 'block' },
  { flag: 'licenses', section: 'licenses' },
  { flag: 'storageHealth', section: 'storage-health' },
  { flag: 'datastores', section: 'datastores' },
] as const;

interface QueryOptions {
  debug?: boolean;
  system?: boolean;
  repositories?: boolean;
  containers?: boolean;
  services?: boolean;
  network?: boolean;
  blockDevices?: boolean;
  licenses?: boolean;
  storageHealth?: boolean;
  datastores?: boolean;
  strict?: boolean;
  healthCheck?: boolean;
  stabilityCheck?: boolean;
  search?: string;
}

interface StorageSummary {
  effectiveFree: string;
  limitedBy: 'datastore' | 'disk';
  datastorePool: string;
  datastorePath: string;
  recommendation: string | null;
}

/**
 * Single source of truth for the derived storage summary. Returns null when the
 * system section is absent (e.g. renet error or older renet) so callers never
 * emit a fabricated "0.0G", the storage summary must reflect real data or none.
 */
export function deriveStorageSummary(sys: SystemInfo | undefined): StorageSummary | null {
  if (!sys?.disk.available || !sys.datastore.available) return null;
  const diskFreeGb = parseSizeToGb(sys.disk.available);
  const dsFreeGb = parseSizeToGb(sys.datastore.available);
  const effectiveFreeGb = Math.min(diskFreeGb, dsFreeGb);
  return {
    effectiveFree: `${effectiveFreeGb.toFixed(1)}G`,
    limitedBy: dsFreeGb <= diskFreeGb ? 'datastore' : 'disk',
    datastorePool: sys.datastore.total,
    datastorePath: sys.datastore.path ?? NETWORK_DEFAULTS.DATASTORE_PATH,
    recommendation: effectiveFreeGb < 10 ? 'Low storage. Expand with: rdc datastore resize' : null,
  };
}

function printStorageSummary(sys: SystemInfo | undefined): void {
  const summary = deriveStorageSummary(sys);
  if (!summary) return;
  const warning = summary.recommendation ? ` ${summary.recommendation}` : '';
  outputService.info(
    `\nStorage: ${summary.effectiveFree} effective free (limited by ${summary.limitedBy}). Datastore pool: ${summary.datastorePool}.${warning}`
  );
}

/** Pool fill level + the space transfer snapshots and staging pin, shown under
 * the storage-health table (rediacc/renet#76). */
export function renderPoolSummary(pool: StorageHealthResult['pool']): void {
  if (!pool) return;
  outputService.info(
    t('commands.machine.status.storageHealthPoolSummary', {
      used: pool.used_human,
      free: pool.free_human,
      percent: pool.used_percent.toFixed(1),
    })
  );
  if (pool.active_transfer_snapshots > 0 || pool.stale_transfer_snapshots > 0) {
    outputService.info(
      t('commands.machine.status.storageHealthPoolSnapshots', {
        pinned: pool.transfer_pinned_human,
        active: pool.active_transfer_snapshots,
        stale: pool.stale_transfer_snapshots,
      })
    );
  }
}

function renderTableMode(
  listResult: ListResult,
  machineConfig: MachineConfig | undefined,
  infra: InfraConfig | undefined,
  resolve: (guid: string) => string,
  repoName: RepoNameResolver,
  licenseDetail: LicenseDetail,
  machineName?: string
): void {
  const tableSections = getSections(
    resolve,
    repoName,
    licenseDetail,
    infra?.baseDomain,
    machineName
  );
  printSummary(listResult);

  if (machineConfig) {
    outputService.info(`\n${t('commands.machine.status.connection')}`);
    writeStdout(`${outputService.formatTable([flattenConnection(machineConfig)])}\n`);
  }
  if (infra) {
    outputService.info(`\n${t('commands.machine.status.infrastructure')}`);
    writeStdout(`${outputService.formatTable([flattenInfra(infra)])}\n`);
  }
  for (const section of tableSections) {
    const data = section.getData(listResult);
    if (data.length === 0) continue;
    outputService.info(`\n${section.title}`);
    writeStdout(`${outputService.formatTable(data)}\n`);
  }

  const uncapped = uncappedRepoNames(listResult, repoName);
  if (uncapped.length > 0) {
    outputService.info(
      t('commands.machine.status.noMemoryCap', {
        count: uncapped.length,
        names: uncapped.join(', '),
      })
    );
  }

  const repoServerSourced = getRepositories(listResult).some(
    (r) => repoName(r.name, r.repo_name).source === 'server'
  );
  const healthServerSourced = (listResult.storage_health?.repositories ?? []).some(
    (sh) => repoName(sh.guid, sh.name).source === 'server'
  );
  if (repoServerSourced || healthServerSourced) {
    outputService.info(t('commands.repo.list.serverNameLegend'));
  }

  if (listResult.storage_health) {
    outputService.info(
      t('commands.machine.status.storageHealthSummary', {
        summary: listResult.storage_health.savings_human,
      })
    );
    outputService.info(t('commands.machine.status.storageHealthFragmentationNote'));

    renderPoolSummary(listResult.storage_health.pool);
  }

  printStorageSummary(listResult.system);
}

export function buildEnrichedJson(
  listResult: ListResult,
  machineConfig: MachineConfig | undefined,
  infra: InfraConfig | undefined,
  resolve: (guid: string) => string,
  repoName: RepoNameResolver,
  licenseDetail: LicenseDetail,
  machineName: string
): Record<string, unknown> {
  const baseDomain = infra?.baseDomain;
  return {
    ...listResult,
    connection: machineConfig ? flattenConnection(machineConfig) : null,
    repositories: getRepositories(listResult).map((repo) => {
      const { name, source } = repoName(repo.name, repo.repo_name);
      return {
        ...repo,
        name,
        guid: repo.name,
        name_source: source,
        url:
          baseDomain && machineName
            ? `https://*.${name}.${machineName}.${baseDomain}`
            : DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
      };
    }),
    containers: getContainers(listResult).map((c) => ({
      ...c,
      repository: resolve(c.repository),
      repository_guid: c.repository,
      domain: extractCustomDomain(c.labels, baseDomain),
      autoRoute: extractAutoRoute(c.labels, baseDomain, machineName),
    })),
    services: resolveGuids(getServices(listResult), resolve, 'repository'),
    infra: infra ?? null,
    storage: deriveStorageSummary(listResult.system),
    // Scripted consumers get the marker and the datastore scope too; a
    // `machine status -o json | jq` health check should not have to shell out to renet separately to learn that backups are blocked.
    // Unknown detail is marked on each entry, as the table's backups cell says `unknown`: a `.blockedBackup` check must not read a missing field as not blocked.
    license_statuses: getLicenseStatuses(listResult).map((l) => ({
      ...l,
      ...(licenseDetail === undefined
        ? { backups: 'unknown' }
        : (licenseDetail.get(l.repositoryGuid) ?? {})),
    })),
  };
}

export function collectSections(options: QueryOptions): string[] {
  const sections: string[] = [];
  for (const { flag, section } of SECTION_FLAGS) {
    if (options[flag]) sections.push(section);
  }
  // The storage summary is derived from the system section, so ensure it is always collected when a section subset is requested. Cheap renet-side (~sub-10ms, no shell-outs). An empty list means a full query, which already includes system.
  if (sections.length > 0 && !sections.includes('system')) sections.push('system');
  return sections;
}

/**
 * Resolve the target machine from the positional name. When omitted, the sole
 * registered machine is used; more than one is an AMBIGUOUS refusal (exit 11)
 * listing the candidates, never a guess (spec/03 §5.2).
 */
async function resolveStatusMachine(name: string | undefined): Promise<string> {
  if (name) return name;
  const machines = await configService.listMachines();
  if (machines.length === 1) return machines[0].name;
  if (machines.length === 0) {
    throw notFound(t('commands.machine.list.noMachines'));
  }
  throw ambiguous(
    t('commands.machine.status.ambiguous', { machines: machines.map((m) => m.name).join(', ') })
  );
}

/**
 * The sections a `machine status` job asks `list-all` for. The licence detail and the stale-binary probe ride
 * the same job as the rest (its `licenses` and `stale-processes` sections), so a filtered run asks for both next
 * to what it was asked for. Undefined is the full listing.
 */
function requestedSections(sections: string[]): string[] | undefined {
  return sections.length > 0
    ? [...new Set([...sections, 'licenses', 'stale-processes'])]
    : undefined;
}

/**
 * What `machine status` renders from a finished `list-all` job: the listing plus the local config and the
 * backup standing derived from it.
 *
 * The licence detail is read whenever the Licenses section will be rendered (no section flags = every section).
 * It answers what `renet list` cannot: which datastore holds each licence, whether a scheduled backup is blocked,
 * and what the last unattended renewal did.
 */
async function gatherStatus(
  machineName: string,
  sections: string[],
  listResult: ListResult
): Promise<{
  listResult: ListResult;
  guidMap: Awaited<ReturnType<typeof loadGuidMap>>;
  machineConfig: MachineConfig | undefined;
  licenseDetail: LicenseDetail;
  staleBinary: RenetProcess[] | null;
  staleBackups: StaleBackupRepo[];
  missedTargets: MissedTargetRepo[];
  failedVerifies: FailedVerifyRepo[];
}> {
  const [guidMap, machineConfig] = await Promise.all([
    loadGuidMap(),
    configService.getLocalMachine(machineName).catch(() => undefined),
  ]);
  const wantsLicenses = sections.length === 0 || sections.includes('licenses');
  const licenseDetail = wantsLicenses ? licenseDetailOf(listResult) : new Map();
  if (wantsLicenses && licenseDetail === undefined) {
    outputService.warn(t('commands.machine.status.licenseDetailUnreadable'));
  }

  return {
    listResult,
    guidMap,
    machineConfig,
    licenseDetail,
    staleBinary: staleBinariesOf(listResult),
    staleBackups: await fetchStaleBackups(machineName, listResult),
    missedTargets: await fetchMissedTargets(machineName, listResult),
    failedVerifies: failedVerifyRepos(listResult.backup_coverage),
  };
}

/** The per-repo licence detail of a listing by repository GUID; undefined (unknown, never "none") when the listing has no licences section or an entry is not the shape the table reads. */
export type LicenseDetail = Map<string, RuntimeRepoLicenseStatus> | undefined;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** The fields the status table and the blocked-backup alert read: a mismatch there would render as `undefined` cells. */
function isLicenseEntry(entry: unknown): entry is RuntimeRepoLicenseStatus {
  if (!isObject(entry)) return false;
  const { repositoryGuid, status, datastoreId, blockedBackup, lastRenewal } = entry;
  if (typeof repositoryGuid !== 'string' || typeof status !== 'string') return false;
  if (datastoreId !== undefined && typeof datastoreId !== 'string') return false;
  if (
    blockedBackup !== undefined &&
    !(isObject(blockedBackup) && typeof blockedBackup.reason === 'string')
  ) {
    return false;
  }
  return (
    lastRenewal === undefined || (isObject(lastRenewal) && typeof lastRenewal.outcome === 'string')
  );
}

export function licenseDetailOf(listResult: ListResult): LicenseDetail {
  const entries: unknown = listResult.license_statuses;
  if (!Array.isArray(entries) || !entries.every(isLicenseEntry)) return undefined;
  return new Map(entries.map((entry) => [entry.repositoryGuid, entry]));
}

/** The `backups` cell: unknown detail is never `ok`. */
function licenseDetailBackups(
  licenseDetail: LicenseDetail,
  extra: RuntimeRepoLicenseStatus | undefined
): string {
  if (licenseDetail === undefined) return 'unknown';
  return extra?.blockedBackup ? `BLOCKED ${extra.blockedBackup.reason}` : 'ok';
}

/**
 * renet processes still running a replaced binary, from the listing's `stale-processes` section. Null when
 * the section is absent (a renet that predates it) or /proc was unreadable: unknown is never "none stale".
 */
export function staleBinariesOf(listResult: ListResult): RenetProcess[] | null {
  const section = listResult.stale_processes;
  if (section?.status !== 'ok' || !section.processes) return null;
  return section.processes.map((p) => ({ pid: p.pid, unit: p.unit || '-', exe: p.exe }));
}

/** Repos whose latest run missed their declared target and that are not yet stale (D-rpo). */
export async function fetchMissedTargets(
  machineName: string,
  listResult: ListResult
): Promise<MissedTargetRepo[]> {
  if (!listResult.backup_coverage) return [];
  const config = await configService.getCurrent().catch(() => null);
  if (!config) return [];
  const { machineBackupTargetStatus } = await import(
    '../../services/backup/backup-schedule-coverage.js'
  );
  return machineBackupTargetStatus(config, machineName, listResult.backup_coverage).missed;
}

/** Repos whose last backup is older than 2x the schedule covering them (G7), or than T + grace for a declared target. */
export async function fetchStaleBackups(
  machineName: string,
  listResult: ListResult
): Promise<StaleBackupRepo[]> {
  if (!listResult.backup_coverage) return [];
  const config = await configService.getCurrent().catch(() => null);
  if (!config) return [];
  const { machineStaleBackups } = await import('../../services/backup/backup-schedule-coverage.js');
  return machineStaleBackups(config, machineName, listResult.backup_coverage);
}

/** Table rows for the stale-binary section. */
export function staleBinaryRows(procs: RenetProcess[]): Record<string, unknown>[] {
  return procs.map((p) => ({ pid: p.pid, unit: p.unit, exe: p.exe }));
}

/** Table rows for the stale-backup section. */
export function staleBackupRows(
  stale: StaleBackupRepo[],
  resolve: (guid: string) => string
): Record<string, unknown>[] {
  return stale.map((b) => ({
    repository: resolve(b.guid),
    lastBackup: b.lastSuccessAt,
    age: formatSpan(b.ageSeconds),
    scheduleEvery: formatSpan(b.intervalSeconds),
    target: b.targetSeconds === undefined ? '-' : formatSpan(b.targetSeconds),
  }));
}

/** Table rows for the missed-target section. */
export function missedTargetRows(
  missed: MissedTargetRepo[],
  resolve: (guid: string) => string
): Record<string, unknown>[] {
  return missed.map((m) => ({
    repository: resolve(m.guid),
    target: formatSpan(m.targetSeconds),
    achieved: m.achievedRpoMs === undefined ? '-' : formatSpan(m.achievedRpoMs / 1000),
    ticksMissed: m.ticksMissed ?? 0,
    hookFailures: m.hookFailures ?? 0,
  }));
}

/** Table rows for the failed-verify section. */
export function verifyFailureRows(
  failed: FailedVerifyRepo[],
  resolve: (guid: string) => string
): Record<string, unknown>[] {
  return failed.map((f) => ({
    repository: resolve(f.guid),
    verdict: f.status,
    verifiedAt: f.verifiedAt ?? '-',
  }));
}

/** The staleness sections and their warnings, printed after the main tables. */
function renderStaleness(
  staleBinary: RenetProcess[] | null,
  staleBackups: StaleBackupRepo[],
  resolve: (guid: string) => string,
  failedVerifies: FailedVerifyRepo[] = [],
  missedTargets: MissedTargetRepo[] = []
): void {
  if (staleBinary && staleBinary.length > 0) {
    outputService.info(`\n${t('commands.machine.status.staleBinarySection')}`);
    writeStdout(`${outputService.formatTable(staleBinaryRows(staleBinary))}\n`);
    outputService.warn(
      t('commands.machine.status.staleBinaryWarning', { count: staleBinary.length })
    );
  }
  if (staleBackups.length > 0) {
    outputService.info(`\n${t('commands.machine.status.staleBackupSection')}`);
    writeStdout(`${outputService.formatTable(staleBackupRows(staleBackups, resolve))}\n`);
    outputService.warn(
      t('commands.machine.status.staleBackupWarning', { count: staleBackups.length })
    );
  }
  if (missedTargets.length > 0) {
    outputService.info(`\n${t('commands.machine.status.missedTargetSection')}`);
    writeStdout(`${outputService.formatTable(missedTargetRows(missedTargets, resolve))}\n`);
    outputService.warn(
      t('commands.machine.status.missedTargetWarning', { count: missedTargets.length })
    );
  }
  if (failedVerifies.length > 0) {
    outputService.info(`\n${t('commands.machine.status.verifyFailureSection')}`);
    writeStdout(`${outputService.formatTable(verifyFailureRows(failedVerifies, resolve))}\n`);
    outputService.warn(
      t('commands.machine.status.verifyFailureWarning', { count: failedVerifies.length })
    );
  }
}

/** Who started a job, as one cell: client, config name, then the actor or SSH user. */
function formatJobOrigin(origin: JobOrigin | undefined): string {
  if (!origin) return '-';
  const who = origin.actor ?? origin.ssh_user;
  const head = [origin.client, origin.config_name].filter(Boolean).join(' ');
  const text = who ? `${head} (${who})`.trim() : head;
  return text || '-';
}

/**
 * The running-jobs section (PLAN-detached-jobs J21): the header and one line per live or recently
 * finished job, each naming the exact command that attaches to it. Empty when renet reports no
 * jobs, or is too old to report the section at all.
 */
export function runningJobLines(
  jobs: JobInfo[] | undefined,
  resolve: (guid: string) => string
): string[] {
  if (!jobs || jobs.length === 0) return [];
  return [
    t('commands.machine.status.runningJobsSection'),
    ...jobs.map((j) =>
      t('commands.machine.status.runningJobsRow', {
        id: j.job_id,
        verb: j.function ?? j.command ?? '-',
        repo: j.repo_guid ? resolve(j.repo_guid) : '-',
        startedAt: j.started_at,
        origin: formatJobOrigin(j.origin),
        state: j.state,
        attach: j.attach,
      })
    ),
  ];
}

/**
 * The jobs a `repository_status` record carries (renet filters them to the repo's GUID, so nothing is
 * left to filter here). Anything that is not a record with a `jobs` array, an older renet's answer
 * included, yields none.
 */
export function jobsOfStatusRecord(record: unknown): JobInfo[] {
  const jobs = (record as { jobs?: unknown } | null)?.jobs;
  return Array.isArray(jobs) ? (jobs as JobInfo[]) : [];
}

/** The jobs section for JSON output, with each repo GUID resolved to its name. */
export function enrichJobs(
  jobs: JobInfo[] | undefined,
  resolve: (guid: string) => string
): (JobInfo & { repository?: string })[] {
  return (jobs ?? []).map((j) => (j.repo_guid ? { ...j, repository: resolve(j.repo_guid) } : j));
}

/**
 * The printed `machine status --output json` document: the enriched sections, then `jobs` (always
 * present, an empty array when renet reports none), `stale_binary` and `backup_staleness`.
 */
export function statusJsonDocument(
  enriched: Record<string, unknown>,
  jobs: JobInfo[] | undefined,
  resolve: (guid: string) => string,
  staleBinary: RenetProcess[] | null,
  staleBackups: StaleBackupRepo[],
  failedVerifies: FailedVerifyRepo[] = [],
  missedTargets: MissedTargetRepo[] = []
): Record<string, unknown> {
  return {
    ...enriched,
    jobs: enrichJobs(jobs, resolve),
    stale_binary: staleBinary,
    backup_staleness: staleBackups,
    verify_failures: failedVerifies,
    target_misses: missedTargets,
  };
}

function renderRunningJobs(jobs: JobInfo[] | undefined, resolve: (guid: string) => string): void {
  const lines = runningJobLines(jobs, resolve);
  if (lines.length === 0) return;
  outputService.info(`\n${lines[0]}`);
  for (const line of lines.slice(1)) outputService.info(line);
}

/** The flags the render step needs, carried on the ticket as step params: scalars only, never a secret. */
type StatusRenderOptions = Pick<
  QueryOptions,
  'healthCheck' | 'stabilityCheck' | 'search' | 'strict' | 'storageHealth'
> & { syncCerts?: boolean };

/** The plan params of the `renderMachineStatus` step: the section filter and the render flags that were set. */
function statusStepParams(
  machineName: string,
  sections: string[],
  options: StatusRenderOptions
): Record<string, string | boolean> {
  return {
    machine: machineName,
    sections: sections.join(','),
    ...(options.healthCheck && { healthCheck: true }),
    ...(options.stabilityCheck && { stabilityCheck: true }),
    ...(options.search && { search: options.search }),
    ...(options.strict && { strict: true }),
    ...(options.storageHealth && { storageHealth: true }),
    ...(options.syncCerts && { syncCerts: true }),
  };
}

/** The `renderMachineStatus` step: render the listing the `list-all` job produced, as tables or as data. */
async function renderStatusFromJob(
  machineName: string,
  sections: string[],
  output: string | undefined,
  options: StatusRenderOptions
): Promise<void> {
  const { parseMachineStatus } = await import('../../services/machine/machine-status.js');
  const {
    listResult,
    guidMap,
    machineConfig,
    licenseDetail,
    staleBinary,
    staleBackups,
    missedTargets,
    failedVerifies,
  } = await gatherStatus(machineName, sections, parseMachineStatus(output));

  const infra = machineConfig?.infra;
  const format = getOutputFormat();
  const resolve = createGuidResolver(guidMap);
  const repoName = createRepoNameResolver(guidMap);

  // Folded-in section refinements (06 §6.1): --health-check / --stability-check
  // gate and return; --search narrows the repositories section.
  if (options.healthCheck) {
    runContainerHealthCheck(listResult, format, resolve);
    return;
  }
  if (options.stabilityCheck) {
    runServiceStabilityCheck(listResult, format, resolve);
    return;
  }
  if (options.search) {
    listResult.repositories = filterRepositoriesBySearch(
      listResult.repositories,
      options.search,
      (guid, serverName) => repoName(guid, serverName).name
    );
  }

  if (format === 'table') {
    renderTableMode(
      listResult,
      machineConfig,
      infra,
      resolve,
      repoName,
      licenseDetail,
      machineName
    );
    renderBlockedBackupAlerts(licenseDetail);
    renderStaleness(staleBinary, staleBackups, resolve, failedVerifies, missedTargets);
    renderRunningJobs(listResult.jobs, resolve);
  } else {
    const enriched = buildEnrichedJson(
      listResult,
      machineConfig,
      infra,
      resolve,
      repoName,
      licenseDetail,
      machineName
    );
    outputService.print(
      statusJsonDocument(
        enriched,
        listResult.jobs,
        resolve,
        staleBinary,
        staleBackups,
        failedVerifies,
        missedTargets
      ),
      format
    );
  }

  // Hint: nudge toward --storage-health (stderr so it doesn't break JSON piping)
  if (!options.storageHealth) {
    writeStderr(`\n${t('commands.machine.status.storageHealthHint')}\n`);
  }

  // --strict: exit non-zero when any container has crossed the health-drift threshold. Lets CI scripts gate deploys on post-deploy convergence without hand-parsing the JSON.
  // Exit code 2 matches the precedent in machine/health.ts (0 = clean,
  // 1 = warn, 2 = error).
  if (options.strict && (listResult.health_drift?.entries.length ?? 0) > 0) {
    const count = listResult.health_drift?.entries.length ?? 0;
    writeStderr(`\n${t('commands.machine.status.strictDriftDetected', { count })}\n`);
    setExitCode(2);
  }

  if (options.syncCerts) {
    await runOptInCertSync(machineName);
  }
}

bindStepHandler('renderMachineStatus', async ({ machine, output, params }) => {
  // The spinner of the attached call ends before the table prints; in a ticket's later run there is none.
  stopSpinner(true);
  const sections =
    typeof params.sections === 'string' && params.sections ? params.sections.split(',') : [];
  await renderStatusFromJob(machine, sections, output, {
    healthCheck: params.healthCheck === true,
    stabilityCheck: params.stabilityCheck === true,
    search: typeof params.search === 'string' ? params.search : undefined,
    strict: params.strict === true,
    storageHealth: params.storageHealth === true,
    syncCerts: params.syncCerts === true,
  });
});

export function registerStatusCommand(machine: Command): void {
  machine
    .command('status')
    .argument('[name]', t('options.name'))
    .summary(t('commands.machine.status.descriptionShort'))
    .description(t('commands.machine.status.description'))
    .option('--debug', t('options.debug'))
    .option('--system', t('options.querySystem'))
    .option('--repositories', t('options.queryRepositories'))
    .option('--containers', t('options.queryContainers'))
    .option('--services', t('options.queryServices'))
    .option('--network', t('options.queryNetwork'))
    .option('--block-devices', t('options.queryBlockDevices'))
    .option('--licenses', t('options.queryLicenses'))
    .option('--storage-health', t('options.queryStorageHealth'))
    .option('--datastores', t('options.queryDatastores'))
    .option('--health-check', t('commands.machine.status.healthCheck'))
    .option('--stability-check', t('commands.machine.status.stabilityCheck'))
    .option('--search <text>', t('options.searchRepos'))
    .option('--sync-certs', t('options.querySyncCerts'))
    .option('--strict', t('options.queryStrict'))
    .action(async (name: string | undefined, options: QueryOptions & { syncCerts?: boolean }) => {
      try {
        const machineName = await resolveStatusMachine(name);
        const sections = collectSections(options);

        // One read job; the render is its step, so a ticket handed back early prints nothing half-done.
        const { machineStatusJob } = await import('../../services/machine/machine-status.js');
        // The job captures its output, so nothing else shows while the machine lists itself.
        startSpinner(t('commands.machine.status.fetching', { machine: machineName }));
        let outcome: Awaited<ReturnType<typeof runCommandJob>>;
        try {
          outcome = await runCommandJob(
            'machine status',
            await machineStatusJob(machineName, {
              debug: options.debug,
              sections: requestedSections(sections),
            }),
            [planStep('renderMachineStatus', statusStepParams(machineName, sections, options))]
          );
        } catch (error) {
          stopSpinner(false);
          throw error;
        }
        stopSpinner(outcome.kind !== 'pending' && outcome.result.success);
        if (outcome.kind === 'pending') {
          const code = pendingExitCode(outcome);
          if (code !== undefined) setExitCode(code);
          return;
        }
        if (!outcome.result.success) {
          renderLocalExecutionFailure(
            outcome.result,
            t('commands.machine.status.fetching', { machine: machineName })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

// Opt-in cert-cache sync after `rdc machine query --sync-certs`. Opt-in because this is a read-only query command today and a network-touching side effect would surprise operators who don't expect it.
async function runOptInCertSync(machineName: string): Promise<void> {
  try {
    const { downloadCertCache } = await import('../../services/account/cert-cache.js');
    await downloadCertCache(machineName, { silent: false });
  } catch (err) {
    outputService.warn(
      t('commands.machine.status.syncCertsFailed', {
        error: err instanceof Error ? err.message : String(err),
      })
    );
  }
}

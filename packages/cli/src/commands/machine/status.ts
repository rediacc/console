import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type {
  ListResult,
  StorageHealthResult,
  SystemInfo,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import {
  getBlockDevices,
  getContainers,
  getHealthSummary,
  getLicenseStatuses,
  getNetworkInterfaces,
  getRepositories,
  getServices,
  getSystemContainers,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import type { InfraConfig, MachineConfig, OutputFormat } from '../../types/index.js';
import { extractAutoRoute, extractCustomDomain } from '../../utils/domain-helpers.js';
import { handleError } from '../../utils/errors.js';
import {
  createGuidResolver,
  createRepoNameResolver,
  loadGuidMap,
  type RepoNameSource,
  resolveGuids,
} from '../../utils/guid-resolver.js';

/** Resolves a repo GUID + server repo_name to a display name and its source. */
type RepoNameResolver = (
  guid: string,
  serverRepoName?: string
) => { name: string; source: RepoNameSource };
import { withSpinner } from '../../utils/spinner.js';

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
  const gb = 1024 ** 3;
  const mb = 1024 ** 2;
  if (b >= gb) return `${(b / gb).toFixed(1)} GB`;
  if (b >= mb) return `${(b / mb).toFixed(1)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${b} B`;
}

function getSections(
  resolve: (guid: string) => string,
  repoName: RepoNameResolver,
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
            autostart: repo.autostart ? 'Yes' : 'No',
            containers: repo.container_count,
            disk: repo.disk_space?.use_percent ?? '-',
            modified: repo.modified_human,
          };
        }),
    },
    {
      title: 'Storage Health',
      getData: (r) => buildStorageHealthRows(r.storage_health, repoName),
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
        return getLicenseStatuses(r).map((l) => ({
          repository: resolve(l.repositoryGuid),
          status: l.status,
          issued: l.issuedAt ? relativeTime(l.issuedAt) : '-',
          expires: l.hardExpiresAt ? relativeTime(l.hardExpiresAt) : '-',
          machine_match: getMachineMatch(currentMachineId, l.machineId),
        }));
      },
    },
  ];
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
  strict?: boolean;
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
 * emit a fabricated "0.0G" — the storage summary must reflect real data or none.
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

/** Pool fill level + backup-snapshot pinning, shown under the storage-health
 * table (rediacc/renet#76). */
function renderPoolSummary(pool: StorageHealthResult['pool']): void {
  if (!pool) return;
  outputService.info(
    t('commands.machine.query.storageHealthPoolSummary', {
      used: pool.used_human,
      free: pool.free_human,
      percent: pool.used_percent.toFixed(1),
    })
  );
  if (pool.active_backup_snapshots > 0 || pool.stale_backup_snapshots > 0) {
    outputService.info(
      t('commands.machine.query.storageHealthPoolSnapshots', {
        pinned: pool.backup_snapshot_pinned_human,
        active: pool.active_backup_snapshots,
        stale: pool.stale_backup_snapshots,
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
  machineName?: string
): void {
  const tableSections = getSections(resolve, repoName, infra?.baseDomain, machineName);
  printSummary(listResult);

  if (machineConfig) {
    outputService.info(`\n${t('commands.machine.query.connection')}`);
    process.stdout.write(`${outputService.formatTable([flattenConnection(machineConfig)])}\n`);
  }
  if (infra) {
    outputService.info(`\n${t('commands.machine.query.infrastructure')}`);
    process.stdout.write(`${outputService.formatTable([flattenInfra(infra)])}\n`);
  }
  for (const section of tableSections) {
    const data = section.getData(listResult);
    if (data.length === 0) continue;
    outputService.info(`\n${section.title}`);
    process.stdout.write(`${outputService.formatTable(data)}\n`);
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
      t('commands.machine.query.storageHealthSummary', {
        summary: listResult.storage_health.savings_human,
      })
    );
    outputService.info(t('commands.machine.query.storageHealthFragmentationNote'));

    renderPoolSummary(listResult.storage_health.pool);
  }

  printStorageSummary(listResult.system);
}

function buildEnrichedJson(
  listResult: ListResult,
  machineConfig: MachineConfig | undefined,
  infra: InfraConfig | undefined,
  resolve: (guid: string) => string,
  repoName: RepoNameResolver,
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
  };
}

export function collectSections(options: QueryOptions): string[] {
  const sections: string[] = [];
  for (const { flag, section } of SECTION_FLAGS) {
    if (options[flag]) sections.push(section);
  }
  // The storage summary is derived from the system section, so ensure it is
  // always collected when a section subset is requested. Cheap renet-side
  // (~sub-10ms, no shell-outs). An empty list means a full query, which
  // already includes system.
  if (sections.length > 0 && !sections.includes('system')) sections.push('system');
  return sections;
}

export function registerQueryCommand(machine: Command, program: Command): void {
  machine
    .command('query')
    .summary(t('commands.machine.query.descriptionShort'))
    .description(t('commands.machine.query.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('--debug', t('options.debug'))
    .option('--system', t('options.querySystem'))
    .option('--repositories', t('options.queryRepositories'))
    .option('--containers', t('options.queryContainers'))
    .option('--services', t('options.queryServices'))
    .option('--network', t('options.queryNetwork'))
    .option('--block-devices', t('options.queryBlockDevices'))
    .option('--licenses', t('options.queryLicenses'))
    .option('--storage-health', t('options.queryStorageHealth'))
    .option('--sync-certs', t('options.querySyncCerts'))
    .option('--strict', t('options.queryStrict'))
    .action(async (options: QueryOptions & { name: string; syncCerts?: boolean }) => {
      try {
        const machineName = options.name;
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        const sections = collectSections(options);

        const { fetchMachineStatus } = await import('../../services/machine-status.js');

        const [listResult, guidMap, machineConfig] = await Promise.all([
          withSpinner(
            t('commands.machine.query.fetching', { machine: machineName }),
            () =>
              fetchMachineStatus(machineName, {
                debug: options.debug,
                sections: sections.length > 0 ? sections : undefined,
              }),
            t('commands.machine.query.fetched')
          ),
          loadGuidMap(),
          configService.getLocalMachine(machineName).catch(() => undefined),
        ]);

        const infra = machineConfig?.infra;
        const format = program.opts().output as OutputFormat;
        const resolve = createGuidResolver(guidMap);
        const repoName = createRepoNameResolver(guidMap);

        if (format === 'json') {
          const enriched = buildEnrichedJson(
            listResult,
            machineConfig,
            infra,
            resolve,
            repoName,
            machineName
          );
          outputService.print(enriched, format);
        } else {
          renderTableMode(listResult, machineConfig, infra, resolve, repoName, machineName);
        }

        // Hint: nudge toward --storage-health (stderr so it doesn't break JSON piping)
        if (!options.storageHealth) {
          process.stderr.write(`\n${t('commands.machine.query.storageHealthHint')}\n`);
        }

        // --strict: exit non-zero when any container has crossed the
        // health-drift threshold. Lets CI scripts gate deploys on
        // post-deploy convergence without hand-parsing the JSON.
        // Exit code 2 matches the precedent in machine/health.ts (0 = clean,
        // 1 = warn, 2 = error).
        if (options.strict && (listResult.health_drift?.entries.length ?? 0) > 0) {
          const count = listResult.health_drift?.entries.length ?? 0;
          process.stderr.write(`\n${t('commands.machine.query.strictDriftDetected', { count })}\n`);
          process.exitCode = 2;
        }

        if (options.syncCerts) {
          await runOptInCertSync(machineName);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

// Opt-in cert-cache sync after `rdc machine query --sync-certs`. Opt-in
// because this is a read-only query command today and a network-touching
// side effect would surprise operators who don't expect it.
async function runOptInCertSync(machineName: string): Promise<void> {
  try {
    const { downloadCertCache } = await import('../../services/cert-cache.js');
    await downloadCertCache(machineName, { silent: false });
  } catch (err) {
    outputService.warn(
      t('commands.machine.query.syncCertsFailed', {
        error: err instanceof Error ? err.message : String(err),
      })
    );
  }
}

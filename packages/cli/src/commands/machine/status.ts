import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { ListResult, SystemInfo } from '@rediacc/shared/queue-vault/data/list-types.generated';
import {
  getBlockDevices,
  getContainers,
  getHealthSummary,
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
import { createGuidResolver, loadGuidMap, resolveGuids } from '../../utils/guid-resolver.js';
import { withSpinner } from '../../utils/spinner.js';

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

function getSections(resolve: (guid: string) => string): SectionRenderer[] {
  return [
    {
      title: 'System',
      getData: (r) => (r.system ? [flattenSystem(r.system)] : []),
    },
    {
      title: 'Repositories',
      getData: (r) =>
        getRepositories(r).map((repo) => ({
          name: resolve(repo.name),
          guid: repo.name,
          size: repo.size_human,
          mounted: repo.mounted ? 'Yes' : 'No',
          docker: repo.docker_running ? 'Yes' : 'No',
          containers: repo.container_count,
          disk: repo.disk_space?.use_percent ?? '-',
          modified: repo.modified_human,
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
  ];
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
] as const;

interface QueryOptions {
  debug?: boolean;
  system?: boolean;
  repositories?: boolean;
  containers?: boolean;
  services?: boolean;
  network?: boolean;
  blockDevices?: boolean;
}

function renderTableMode(
  listResult: ListResult,
  machineConfig: MachineConfig | undefined,
  infra: InfraConfig | undefined,
  resolve: (guid: string) => string
): void {
  const tableSections = getSections(resolve);
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
}

export function registerQueryCommand(machine: Command, program: Command): void {
  machine
    .command('query <name>')
    .summary(t('commands.machine.query.descriptionShort'))
    .description(t('commands.machine.query.description'))
    .option('--debug', t('options.debug'))
    .option('--system', t('options.querySystem'))
    .option('--repositories', t('options.queryRepositories'))
    .option('--containers', t('options.queryContainers'))
    .option('--services', t('options.queryServices'))
    .option('--network', t('options.queryNetwork'))
    .option('--block-devices', t('options.queryBlockDevices'))
    .action(async (name: string, options: QueryOptions) => {
      try {
        const machineName = name;
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        // Collect requested sections from flags
        const sections: string[] = [];
        for (const { flag, section } of SECTION_FLAGS) {
          if (options[flag]) sections.push(section);
        }

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

        if (format === 'json') {
          const baseDomain = infra?.baseDomain;
          const enriched = {
            ...listResult,
            connection: machineConfig ? flattenConnection(machineConfig) : null,
            repositories: resolveGuids(getRepositories(listResult), resolve),
            containers: getContainers(listResult).map((c) => ({
              ...c,
              repository: resolve(c.repository),
              repository_guid: c.repository,
              domain: extractCustomDomain(c.labels, baseDomain),
              autoRoute: extractAutoRoute(c.labels, baseDomain, machineName),
            })),
            services: resolveGuids(getServices(listResult), resolve, 'repository'),
            infra: infra ?? null,
          };
          outputService.print(enriched, format);
          return;
        }

        renderTableMode(listResult, machineConfig, infra, resolve);
      } catch (error) {
        handleError(error);
      }
    });
}

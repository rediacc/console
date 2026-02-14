import { Command } from 'commander';
import type { ListResult, SystemInfo } from '@rediacc/shared/queue-vault/data/list-types.generated';
import {
  getContainers,
  getRepositories,
  getServices,
  getBlockDevices,
  getNetworkInterfaces,
  getSystemContainers,
  getHealthSummary,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

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

const SECTIONS: SectionRenderer[] = [
  {
    title: 'System',
    getData: (r) => (r.system ? [flattenSystem(r.system)] : []),
  },
  {
    title: 'Repositories',
    getData: (r) =>
      getRepositories(r).map((repo) => ({
        name: repo.name,
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
        repository: c.repository,
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
        repository: s.repository,
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

export function registerStatusCommand(machine: Command, program: Command): void {
  machine
    .command('status <name>')
    .description(t('commands.machine.status.description'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { debug?: boolean }) => {
      try {
        const machineName = name;
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        const { fetchMachineStatus } = await import('../../services/machine-status.js');

        const listResult = await withSpinner(
          t('commands.machine.status.fetching', { machine: machineName }),
          () => fetchMachineStatus(machineName, { debug: options.debug }),
          t('commands.machine.status.fetched')
        );

        const format = program.opts().output as OutputFormat;

        if (format === 'json') {
          outputService.print(listResult, format);
          return;
        }

        // Table mode: render sections with headers
        printSummary(listResult);

        for (const section of SECTIONS) {
          const data = section.getData(listResult);
          if (data.length === 0) continue;
          outputService.info(`\n${section.title}`);
          process.stdout.write(`${outputService.formatTable(data)}\n`);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

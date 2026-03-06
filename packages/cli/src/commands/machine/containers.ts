import { type ContainerInfo, getMachineContainers } from '@rediacc/shared/services/machine';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../../utils/guid-resolver.js';
import { withSpinner } from '../../utils/spinner.js';

function displayUnhealthyContainers(
  unhealthy: ContainerInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g
): void {
  outputService.error(t('commands.machine.containers.unhealthyFound', { count: unhealthy.length }));
  if (format === 'json') {
    outputService.print(unhealthy, format);
  } else {
    for (const c of unhealthy) {
      outputService.info(`  - ${c.name} (${resolve(c.repository)})`);
    }
  }
  process.exitCode = 2;
}

function handleHealthCheck(
  containers: ContainerInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g
): void {
  const unhealthy = containers.filter((c) => c.health?.status === 'unhealthy');
  if (unhealthy.length > 0) {
    displayUnhealthyContainers(unhealthy, format, resolve);
  } else {
    outputService.success(t('commands.machine.containers.allHealthy'));
  }
}

function formatContainersForTable(
  containers: ContainerInfo[],
  resolve: (guid: string) => string = (g) => g
) {
  return containers.map((c) => ({
    name: c.name,
    status: c.status,
    state: c.state,
    health: c.health?.status ?? 'none',
    cpu: c.cpu_percent ?? '-',
    memory: c.memory_usage ?? '-',
    repository: resolve(c.repository),
  }));
}

export function registerContainersCommand(machine: Command, program: Command): void {
  machine
    .command('containers <name>')
    .description(t('commands.machine.containers.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--health-check', t('commands.machine.containers.healthCheck'))
    .action(async (name: string, options: { team?: string; healthCheck?: boolean }) => {
      try {
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        const opts = await configService.applyDefaults(options);

        if (provider.isCloud && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const [machine, guidMap] = await Promise.all([
          withSpinner(
            t('commands.machine.containers.fetching'),
            () =>
              provider.machines.getWithVaultStatus({
                teamName: opts.team as string,
                machineName: name,
              }),
            t('commands.machine.containers.fetched')
          ),
          loadGuidMap(),
        ]);
        const resolve = createGuidResolver(guidMap);

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const containers = getMachineContainers(machine);
        const format = program.opts().output as OutputFormat;

        if (options.healthCheck) {
          handleHealthCheck(containers, format, resolve);
          return;
        }

        if (containers.length === 0) {
          outputService.info(t('commands.machine.containers.noContainers'));
          return;
        }

        const tableData = formatContainersForTable(containers, resolve);
        outputService.print(tableData, format);
      } catch (error) {
        handleError(error);
      }
    });
}

import { Command } from 'commander';
import { parseGetTeamMachines } from '@rediacc/shared/api';
import {
  type ContainerInfo,
  getMachineContainers,
  type MachineWithVaultStatus,
} from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

function displayUnhealthyContainers(unhealthy: ContainerInfo[], format: OutputFormat): void {
  outputService.error(t('commands.machine.containers.unhealthyFound', { count: unhealthy.length }));
  if (format === 'json') {
    outputService.print(unhealthy, format);
  } else {
    for (const c of unhealthy) {
      outputService.info(`  - ${c.name} (${c.repository})`);
    }
  }
  process.exitCode = 2;
}

function handleHealthCheck(containers: ContainerInfo[], format: OutputFormat): void {
  const unhealthy = containers.filter((c) => c.health?.status === 'unhealthy');
  if (unhealthy.length > 0) {
    displayUnhealthyContainers(unhealthy, format);
  } else {
    outputService.success(t('commands.machine.containers.allHealthy'));
  }
}

function formatContainersForTable(containers: ContainerInfo[]) {
  return containers.map((c) => ({
    name: c.name,
    status: c.status,
    state: c.state,
    health: c.health?.status ?? 'none',
    cpu: c.cpu_percent ?? '-',
    memory: c.memory_usage ?? '-',
    repository: c.repository,
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
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.machine.containers.fetching'),
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          t('commands.machine.containers.fetched')
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const containers = getMachineContainers(machine);
        const format = program.opts().output as OutputFormat;

        if (options.healthCheck) {
          handleHealthCheck(containers, format);
          return;
        }

        if (containers.length === 0) {
          outputService.info(t('commands.machine.containers.noContainers'));
          return;
        }

        const tableData = formatContainersForTable(containers);
        outputService.print(tableData, format);
      } catch (error) {
        handleError(error);
      }
    });
}

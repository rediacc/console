import { Command } from 'commander';
import { getMachineServices, type ServiceInfo } from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

function isServiceUnstable(service: ServiceInfo): boolean {
  return (
    service.active_state === 'failed' ||
    service.restart_count > 3 ||
    service.sub_state === 'auto-restart'
  );
}

function displayUnstableServices(unstable: ServiceInfo[], format: OutputFormat): void {
  outputService.error(t('commands.machine.services.unstableFound', { count: unstable.length }));
  if (format === 'json') {
    outputService.print(unstable, format);
  } else {
    for (const s of unstable) {
      outputService.info(`  - ${s.service_name} (${s.active_state}, ${s.restart_count} restarts)`);
    }
  }
  process.exitCode = 2;
}

function handleStabilityCheck(services: ServiceInfo[], format: OutputFormat): void {
  const unstable = services.filter(isServiceUnstable);
  if (unstable.length > 0) {
    displayUnstableServices(unstable, format);
  } else {
    outputService.success(t('commands.machine.services.allStable'));
  }
}

function formatServicesForTable(services: ServiceInfo[]) {
  return services.map((s) => ({
    name: s.service_name,
    state: s.active_state,
    subState: s.sub_state,
    restarts: s.restart_count,
    memory: s.memory_human,
    repository: s.repository,
  }));
}

export function registerServicesCommand(machine: Command, program: Command): void {
  machine
    .command('services <name>')
    .description(t('commands.machine.services.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--stability-check', t('commands.machine.services.stabilityCheck'))
    .action(async (name: string, options: { team?: string; stabilityCheck?: boolean }) => {
      try {
        const provider = await getStateProvider();
        if (provider.mode === 'cloud') {
          await authService.requireAuth();
        }
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const machine = await withSpinner(
          t('commands.machine.services.fetching'),
          () =>
            provider.machines.getWithVaultStatus({
              teamName: opts.team as string,
              machineName: name,
            }),
          t('commands.machine.services.fetched')
        );

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const services = getMachineServices(machine);
        const format = program.opts().output as OutputFormat;

        if (options.stabilityCheck) {
          handleStabilityCheck(services, format);
          return;
        }

        if (services.length === 0) {
          outputService.info(t('commands.machine.services.noServices'));
          return;
        }

        const tableData = formatServicesForTable(services);
        outputService.print(tableData, format);
      } catch (error) {
        handleError(error);
      }
    });
}

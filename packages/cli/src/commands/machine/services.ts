import { getMachineServices, type ServiceInfo } from '@rediacc/shared/services/machine';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { createGuidResolver, resolveGuids, loadGuidMap } from '../../utils/guid-resolver.js';
import { withSpinner } from '../../utils/spinner.js';

function isServiceUnstable(service: ServiceInfo): boolean {
  return (
    service.active_state === 'failed' ||
    service.restart_count > 3 ||
    service.sub_state === 'auto-restart'
  );
}

function displayUnstableServices(
  unstable: ServiceInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g
): void {
  outputService.error(t('commands.machine.services.unstableFound', { count: unstable.length }));
  if (format === 'json') {
    outputService.print(resolveGuids(unstable, resolve, 'repository'), format);
  } else {
    for (const s of unstable) {
      outputService.info(
        `  - ${s.service_name} (${s.active_state}, ${s.restart_count} restarts, ${resolve(s.repository)})`
      );
    }
  }
  process.exitCode = 2;
}

function handleStabilityCheck(
  services: ServiceInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g
): void {
  const unstable = services.filter(isServiceUnstable);
  if (unstable.length > 0) {
    displayUnstableServices(unstable, format, resolve);
  } else {
    outputService.success(t('commands.machine.services.allStable'));
  }
}

function formatServicesForTable(
  services: ServiceInfo[],
  resolve: (guid: string) => string = (g) => g
) {
  return services.map((s) => ({
    name: s.service_name,
    state: s.active_state,
    subState: s.sub_state,
    restarts: s.restart_count,
    memory: s.memory_human,
    repository: resolve(s.repository),
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
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        const opts = await configService.applyDefaults(options);

        if (provider.isCloud && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const [machine, guidMap] = await Promise.all([
          withSpinner(
            t('commands.machine.services.fetching'),
            () =>
              provider.machines.getWithVaultStatus({
                teamName: opts.team as string,
                machineName: name,
              }),
            t('commands.machine.services.fetched')
          ),
          loadGuidMap(),
        ]);

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const resolve = createGuidResolver(guidMap);
        const services = getMachineServices(machine);
        const format = program.opts().output as OutputFormat;

        if (options.stabilityCheck) {
          handleStabilityCheck(services, format, resolve);
          return;
        }

        if (services.length === 0) {
          outputService.info(t('commands.machine.services.noServices'));
          return;
        }

        if (format === 'json') {
          outputService.print(resolveGuids(services, resolve, 'repository'), format);
        } else {
          const tableData = formatServicesForTable(services, resolve);
          outputService.print(tableData, format);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

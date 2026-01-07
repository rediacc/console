import { Command } from 'commander';
import { parseGetTeamMachines } from '@rediacc/shared/api';
import { getMachineServices, type MachineWithVaultStatus } from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerServicesCommand(machine: Command, program: Command): void {
  machine
    .command('services <name>')
    .description(t('commands.machine.services.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--stability-check', t('commands.machine.services.stabilityCheck'))
    .action(async (name: string, options: { team?: string; stabilityCheck?: boolean }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.machine.services.fetching'),
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          t('commands.machine.services.fetched')
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const services = getMachineServices(machine);
        const format = program.opts().output as OutputFormat;

        if (options.stabilityCheck) {
          // Stability check mode - check for failed/restarting services
          const unstable = services.filter(
            (s) =>
              s.active_state === 'failed' || s.restart_count > 3 || s.sub_state === 'auto-restart'
          );
          if (unstable.length > 0) {
            outputService.error(
              t('commands.machine.services.unstableFound', { count: unstable.length })
            );
            if (format === 'json') {
              outputService.print(unstable, format);
            } else {
              for (const s of unstable) {
                outputService.info(
                  `  - ${s.service_name} (${s.active_state}, ${s.restart_count} restarts)`
                );
              }
            }
            process.exitCode = 2;
          } else {
            outputService.success(t('commands.machine.services.allStable'));
          }
          return;
        }

        if (services.length === 0) {
          outputService.info(t('commands.machine.services.noServices'));
          return;
        }

        // Format services for table output
        const tableData = services.map((s) => ({
          name: s.service_name,
          state: s.active_state,
          subState: s.sub_state,
          restarts: s.restart_count,
          memory: s.memory_human,
          repository: s.repository,
        }));

        outputService.print(tableData, format);
      } catch (error) {
        handleError(error);
      }
    });
}

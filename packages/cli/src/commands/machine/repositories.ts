import { Command } from 'commander';
import { parseListResult } from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerRepositoriesCommand(machine: Command, program: Command): void {
  machine
    .command('repos <name>')
    .description(t('commands.machine.repos.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--search <text>', t('options.searchRepos'))
    .action(async (name: string, options: { team?: string; search?: string }) => {
      try {
        const provider = await getStateProvider();
        if (provider.mode === 'cloud') {
          await authService.requireAuth();
        }
        const opts = await contextService.applyDefaults(options);

        if (provider.mode === 'cloud' && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const machine = await withSpinner(
          t('commands.machine.repos.fetching'),
          () =>
            provider.machines.getWithVaultStatus({
              teamName: opts.team as string,
              machineName: name,
            }),
          t('commands.machine.repos.fetched')
        );

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        // Get full list result for detailed repository info
        const listResult = parseListResult(machine.vaultStatus);
        const format = program.opts().output as OutputFormat;

        if (!listResult || listResult.repositories.length === 0) {
          outputService.info(t('commands.machine.repos.noRepos'));
          return;
        }

        let repositories = listResult.repositories;

        // Filter by search term
        if (options.search) {
          const searchTerm = options.search.toLowerCase();
          repositories = repositories.filter(
            (repository) =>
              repository.name.toLowerCase().includes(searchTerm) ||
              (repository.mount_path
                ? repository.mount_path.toLowerCase().includes(searchTerm)
                : false)
          );
        }

        if (repositories.length === 0) {
          outputService.info(t('commands.machine.repos.noRepos'));
          return;
        }

        if (format === 'json') {
          outputService.print(repositories, format);
        } else {
          // Format for enhanced table output
          const tableData = repositories.map((r) => ({
            name: r.name,
            size: r.size_human,
            mounted: r.mounted ? 'Yes' : 'No',
            docker: r.docker_running ? 'Yes' : 'No',
            containers: r.container_count,
            diskUsed: r.disk_space?.use_percent ?? '-',
            modified: r.modified_human || '-',
            rediaccfile: r.has_rediaccfile ? 'Yes' : 'No',
          }));
          outputService.print(tableData, format);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

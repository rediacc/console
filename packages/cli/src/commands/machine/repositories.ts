import { getContainers, getServices } from '@rediacc/shared/queue-vault/data/list-types.generated';
import { parseListResult } from '@rediacc/shared/services/machine';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { extractAutoRoute, extractCustomDomain } from '../../utils/domain-helpers.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../../utils/guid-resolver.js';
import { withSpinner } from '../../utils/spinner.js';

export function registerRepositoriesCommand(machine: Command, program: Command): void {
  machine
    .command('repos <name>')
    .summary(t('commands.machine.repos.descriptionShort'))
    .description(t('commands.machine.repos.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--search <text>', t('options.searchRepos'))
    .action(async (name: string, options: { team?: string; search?: string }) => {
      try {
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        const opts = await configService.applyDefaults(options);

        if (provider.isCloud && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const [machine, guidMap, machineConfig] = await Promise.all([
          withSpinner(
            t('commands.machine.repos.fetching'),
            () =>
              provider.machines.getWithVaultStatus({
                teamName: opts.team as string,
                machineName: name,
              }),
            t('commands.machine.repos.fetched')
          ),
          loadGuidMap(),
          configService.getLocalMachine(name).catch(() => undefined),
        ]);
        const resolve = createGuidResolver(guidMap);

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
              resolve(repository.name).toLowerCase().includes(searchTerm) ||
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
          const containers = getContainers(listResult);
          const services = getServices(listResult);
          const baseDomain = machineConfig?.infra?.baseDomain;

          const enriched = repositories.map((repo) => ({
            ...repo,
            name: resolve(repo.name),
            guid: repo.name,
            containers: containers
              .filter((c) => c.repository === repo.name)
              .map((c) => ({
                ...c,
                repository: resolve(c.repository),
                repository_guid: c.repository,
                domain: extractCustomDomain(c.labels, baseDomain),
                autoRoute: extractAutoRoute(c.labels, baseDomain, name),
              })),
            services: services
              .filter((s) => s.repository === repo.name)
              .map((s) => ({
                ...s,
                repository: resolve(s.repository),
                repository_guid: s.repository,
              })),
          }));
          outputService.print(enriched, format);
        } else {
          // Format for enhanced table output
          const tableData = repositories.map((r) => ({
            name: resolve(r.name),
            guid: r.name,
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
